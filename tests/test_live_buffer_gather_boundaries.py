"""New acquisition boundaries, including actual join multiplicity and large keys."""

import threading
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from quantmesh.live.buffer import _SCHEMA, _UPDATE_COLUMNS, LiveBuffer

BASE_KEY = 1 << 40
START = datetime(2026, 10, 22, 23, 44, 1, tzinfo=UTC)
END = START + timedelta(days=1)


class Calls:
    def __init__(self, connection, *, before_payload=None):
        self.connection = connection
        self.calls = []
        self.payload = []
        self.before_payload = before_payload

    def execute(self, query, parameters=None):
        self.calls.append((query, parameters))
        if query.startswith(f"SELECT {_UPDATE_COLUMNS}"):
            self.payload.append((query, parameters))
            if self.before_payload:
                self.before_payload(len(self.payload))
        if parameters is None:
            self.connection.execute(query)
        else:
            self.connection.execute(query, parameters)
        return self

    def __getattr__(self, name):
        return getattr(self.connection, name)


def lake_for(connection):
    lake = LiveBuffer.__new__(LiveBuffer)
    lake._con, lake._connection_lock = connection, threading.RLock()
    lake.read_unavailable = False
    return lake


@pytest.fixture
def small_source():
    connection = duckdb.connect(
        ":memory:",
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    )
    connection.execute(_SCHEMA)
    connection.execute(f"""INSERT INTO market_updates SELECT {BASE_KEY}+i,
      'hyperliquid',CASE WHEN i%5=0 THEN 'ETH' ELSE 'BTC' END,
      CASE WHEN i%7=0 THEN 'status' ELSE 'candle' END,'synthetic',
      TIMESTAMPTZ '2026-10-23 00:00:00+00',TIMESTAMPTZ '2026-10-23 00:00:01+00',
      i,false,'complete','owned-'||i::VARCHAR,NULL,NULL,NULL,
      CASE WHEN i%7=0 THEN 'disconnected' ELSE NULL END,
      CASE WHEN i%7=0 THEN '状态-'||i::VARCHAR ELSE NULL END,
      CASE WHEN i%7=0 THEN '{{}}' ELSE
      '{{"open":100,"high":101,"low":99,"close":100,"interval":"1m","volume":1}}'
      END FROM range(96)r(i)""")
    yield connection
    connection.close()


KEYS = "SELECT local_seq FROM market_updates WHERE instrument='BTC'"


@pytest.mark.parametrize("caller_owned", [False, True])
def test_grouped_gather_preserves_large_keys_snapshot_and_transaction(small_source, caller_owned):
    connection = small_source
    writer = connection.cursor()
    if caller_owned:
        connection.execute("BEGIN TRANSACTION")
        connection.execute(
            "UPDATE market_updates SET source_event_id='caller-pending' WHERE local_seq=?",
            [BASE_KEY + 1],
        )
    transaction = connection.execute("SELECT txid_current()").fetchone()[0]
    expected = connection.execute(
        f"SELECT {_UPDATE_COLUMNS} FROM market_updates WHERE instrument='BTC' ORDER BY local_seq"
    ).fetchall()

    def modify(count):
        if count == 1:
            writer.execute("DELETE FROM market_updates WHERE local_seq=?", [BASE_KEY + 93])
            writer.execute(
                "UPDATE market_updates SET source_event_id='concurrent' WHERE local_seq=?",
                [BASE_KEY + 94],
            )

    trace = Calls(connection, before_payload=modify)
    lake = lake_for(trace)
    try:
        with lake._connection_lock:
            assert lake._tail_rows(KEYS, []) == expected
        assert len(trace.payload) == 3
        assert all(len(row) == 17 for row in expected)
        if caller_owned:
            assert connection.execute("SELECT txid_current()").fetchone()[0] == transaction
            assert not any(q in {"BEGIN TRANSACTION", "ROLLBACK", "COMMIT"} for q, _ in trace.calls)
        else:
            assert sum(q == "ROLLBACK" for q, _ in trace.calls) == 1
            connection.execute("BEGIN TRANSACTION")
            connection.execute("ROLLBACK")
    finally:
        if caller_owned:
            connection.execute("ROLLBACK")
        writer.close()


@pytest.mark.parametrize("caller_owned", [False, True])
@pytest.mark.parametrize("failure", ["missing", "duplicate"])
def test_real_join_missing_and_duplicate_rows_refuse_without_resetting_caller(
    small_source, caller_owned, failure
):
    connection = small_source
    if failure == "duplicate":
        connection.execute("ALTER TABLE market_updates RENAME TO owned_rows")
        connection.execute(f"""CREATE VIEW market_updates AS
          SELECT * FROM owned_rows UNION ALL
          SELECT * FROM owned_rows WHERE local_seq={BASE_KEY + 1}""")
        query = "SELECT DISTINCT local_seq FROM market_updates WHERE instrument='BTC'"
    else:
        query = KEYS + f" UNION ALL SELECT {BASE_KEY + 999}"
    if caller_owned:
        connection.execute("BEGIN TRANSACTION")
    transaction = connection.execute("SELECT txid_current()").fetchone()[0]
    trace = Calls(connection)
    lake = lake_for(trace)
    with pytest.raises(ValueError, match="tail rows do not match selected keys"):
        with lake._connection_lock:
            lake._tail_rows(query, [])
    if caller_owned:
        assert connection.execute("SELECT txid_current()").fetchone()[0] == transaction
        assert not any(q == "ROLLBACK" for q, _ in trace.calls)
    else:
        connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


@pytest.mark.parametrize("caller_owned", [False, True])
@pytest.mark.parametrize("failure", ["sql", "cancel"])
def test_grouped_failure_or_cancellation_never_returns_prefix(small_source, caller_owned, failure):
    connection = small_source
    if caller_owned:
        connection.execute("BEGIN TRANSACTION")
    transaction = connection.execute("SELECT txid_current()").fetchone()[0]

    def fail(count):
        if count == 2:
            if failure == "sql":
                connection.execute("SELECT * FROM owned_missing_relation")
            raise KeyboardInterrupt("owned injected cancellation")

    trace = Calls(connection, before_payload=fail)
    lake = lake_for(trace)
    exception = duckdb.CatalogException if failure == "sql" else KeyboardInterrupt
    with pytest.raises(exception):
        with lake._connection_lock:
            lake._tail_rows(KEYS, [])
    assert len(trace.payload) == 2
    if caller_owned:
        assert connection.execute("SELECT txid_current()").fetchone()[0] == transaction
        assert not any(q == "ROLLBACK" for q, _ in trace.calls)
    else:
        connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


def test_null_rank_aggregate_has_no_empty_key_relation(small_source):
    trace = Calls(small_source)
    lake = lake_for(trace)
    with lake._connection_lock:
        assert lake._tail_rows("SELECT NULL::BIGINT", []) == []
    assert trace.payload == []
    assert sum(q == "ROLLBACK" for q, _ in trace.calls) == 1


@pytest.mark.parametrize("selected", [False, True])
def test_grouped_replay_decodes_only_selected_payload_and_refuses_corruption(
    small_source, selected
):
    connection = small_source
    key = BASE_KEY + (94 if selected else 95)
    connection.execute("UPDATE market_updates SET payload_json='{' WHERE local_seq=?", [key])
    lake = lake_for(connection)
    if selected:
        import json

        with pytest.raises(json.JSONDecodeError):
            lake.replay(instrument="BTC", tail=True, limit=10000)
    else:
        result = lake.replay(instrument="BTC", tail=True, limit=10000)
        assert len(result) == 76
        assert all(row.instrument == "BTC" for row in result)
    connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


def test_default10000_preserves_scope_dualutc_and_has318_statement_bound():
    connection = duckdb.connect(
        ":memory:",
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    )
    connection.execute(_SCHEMA)
    connection.execute(f"""INSERT INTO market_updates SELECT {BASE_KEY}+i,
      CASE WHEN i%101=0 THEN 'moomoo' ELSE 'hyperliquid' END,
      CASE WHEN i%5=0 THEN 'ETH' ELSE 'BTC' END,
      CASE WHEN i%37=0 THEN 'ticker' WHEN i%7=0 THEN 'status' ELSE 'candle' END,'synthetic',
      CASE WHEN i%997=0 THEN TIMESTAMPTZ '2026-10-23 23:44:01+00'
           WHEN i%991=0 THEN TIMESTAMPTZ '2026-10-22 23:44:00+00'
           ELSE TIMESTAMPTZ '2026-10-22 23:44:01+00'+i*INTERVAL '1 second' END,
      CASE WHEN i%997=0 THEN TIMESTAMPTZ '2026-10-23 23:44:02+00'
           WHEN i%991=0 THEN TIMESTAMPTZ '2026-10-22 23:44:01+00'
           ELSE TIMESTAMPTZ '2026-10-22 23:44:01+00'+(i+1)*INTERVAL '1 second' END,
      i,false,'complete','owned-'||i::VARCHAR,NULL,NULL,NULL,
      CASE WHEN i%7=0 THEN 'disconnected' ELSE NULL END,
      CASE WHEN i%7=0 THEN '状态-'||i::VARCHAR ELSE NULL END,
      CASE WHEN i%7=0 THEN '{{}}' ELSE
      '{{"open":100,"high":101,"low":99,"close":100,"interval":"1m","volume":1}}'
      END FROM range(16017)r(i)""")
    for index, instant in [(20000, START), (20001, END)]:
        connection.execute(
            "INSERT INTO market_updates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                BASE_KEY + index,
                "hyperliquid",
                "BTC",
                "status",
                "synthetic",
                instant,
                instant,
                index,
                False,
                "complete",
                f"owned-{index}",
                None,
                None,
                None,
                "disconnected",
                "inclusive endpoint",
                "{}",
            ],
        )
    expected = [
        i
        for i in range(16017)
        if i % 101 != 0 and i % 5 != 0 and i % 37 != 0 and i % 997 != 0 and i % 991 != 0
    ]
    expected = [*expected, 20000, 20001][-10000:]
    trace = Calls(connection)
    lake = lake_for(trace)
    try:
        actual = lake.replay(
            venue="hyperliquid",
            instrument="BTC",
            kinds={"candle", "status"},
            start=START,
            end=END,
            data_time_start=START,
            data_time_end=END,
            tail=True,
            limit=10000,
        )
        assert [row.sequence for row in actual] == expected
        assert [row.source_event_id for row in actual] == [f"owned-{i}" for i in expected]
        assert len(actual) == 10000
        assert all(
            START <= row.data_time <= END and START <= row.received_at <= END for row in actual
        )
        assert len(trace.payload) == 313
        assert [len(parameters) - 2 for _, parameters in trace.payload] == [32] * 312 + [16]
        assert len(trace.calls) == 318
        assert not any(query == "COMMIT" for query, _ in trace.calls)
    finally:
        connection.close()
