"""Fixed-size complete-row retrieval within one existing DuckDB snapshot."""

import hashlib
import threading

import duckdb
import pytest

from quantmesh.live.buffer import _SCHEMA, _UPDATE_COLUMNS, LiveBuffer, _row_to_update


class RecordedConnection:
    def __init__(self, connection, *, mutate=None, fault=None):
        self.connection = connection
        self.calls = []
        self.mutate = mutate
        self.fault = fault
        self.is_wide = False
        self.wide_count = 0

    def execute(self, sql, parameters=None):
        self.calls.append((sql, parameters))
        self.is_wide = sql.startswith(f"SELECT {_UPDATE_COLUMNS}")
        if self.is_wide:
            self.wide_count += 1
            if self.fault and self.wide_count == 2:
                if self.fault == "sql":
                    self.connection.execute("SELECT * FROM owned_missing_table")
                if self.fault == "oom":
                    raise duckdb.OutOfMemoryException("owned batch resource refusal")
                raise RuntimeError("owned batch fault")
        if parameters is not None:
            self.connection.execute(sql, parameters)
        else:
            self.connection.execute(sql)
        return self

    def fetchone(self):
        return self.connection.fetchone()

    def fetchall(self):
        rows = self.connection.fetchall()
        if self.is_wide and self.mutate:
            rows = self.mutate(rows, self.wide_count)
        return rows


@pytest.fixture
def lake():
    connection = duckdb.connect(":memory:")
    connection.execute(_SCHEMA)
    connection.execute("""INSERT INTO market_updates SELECT i+1,'hyperliquid','BTC',
      CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END,'synthetic',
      TIMESTAMPTZ '2026-10-24 12:00:00+00',TIMESTAMPTZ '2026-10-24 12:00:01+00',
      i//2,false,'complete','owned-'||i::VARCHAR,NULL,NULL,NULL,
      CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END,
      CASE WHEN i%31=0 THEN 'owned barrier '||i::VARCHAR ELSE NULL END,
      CASE WHEN i%31=0 THEN '{}' ELSE
      json_object('open',100,'high',101,'low',99,'close',100,'interval','5m') END
      FROM range(300) r(i)""")
    value = LiveBuffer.__new__(LiveBuffer)
    value._con = connection
    value._connection_lock = threading.RLock()
    value.read_unavailable = False
    yield value, connection
    connection.close()


def test_tail_complete_rows_are_fetched_in_fixed_batches(lake):
    value, connection = lake
    expected = [
        _row_to_update(r)
        for r in connection.execute(
            f"SELECT {_UPDATE_COLUMNS} FROM market_updates ORDER BY local_seq"
        ).fetchall()
    ]
    recorded = RecordedConnection(connection)
    value._con = recorded
    actual = value.replay(tail=True, limit=10000)
    assert actual == expected
    wide = [
        (sql, parameters)
        for sql, parameters in recorded.calls
        if sql.startswith(f"SELECT {_UPDATE_COLUMNS}")
    ]
    assert len(wide) == 3
    assert all(0 < len(parameters[2:]) <= 128 for _, parameters in wide)
    assert all(
        parameters[:2] == [min(parameters[2:]), max(parameters[2:])] for _, parameters in wide
    )
    assert len(recorded.calls) == 8  # Two tx probes, BEGIN, keys, three batches, COMMIT.


def test_caller_transaction_is_not_committed_or_rolled_back(lake):
    value, connection = lake
    other = connection.cursor()
    connection.execute("BEGIN TRANSACTION")
    connection.execute(
        "UPDATE market_updates SET state_note='caller uncommitted' WHERE local_seq=1"
    )
    before = connection.execute("SELECT txid_current()").fetchone()[0]
    recorded = RecordedConnection(connection)
    value._con = recorded
    assert value.replay(tail=True, limit=300)[0].state_note == "caller uncommitted"
    assert connection.execute("SELECT txid_current()").fetchone()[0] == before
    seen = other.execute("SELECT state_note FROM market_updates WHERE local_seq=1").fetchone()[0]
    assert seen != "caller uncommitted"
    assert not any(sql in {"BEGIN TRANSACTION", "COMMIT", "ROLLBACK"} for sql, _ in recorded.calls)
    connection.execute("ROLLBACK")
    other.close()


def test_writer_between_batches_cannot_change_selected_snapshot(lake):
    value, connection = lake
    other = connection.cursor()
    expected = value.replay(tail=True, limit=300)

    def mutate(rows, count):
        if count == 1:
            other.execute("DELETE FROM market_updates WHERE local_seq=299")
            other.execute("UPDATE market_updates SET source_event_id='changed' WHERE local_seq=298")
        return rows

    recorded = RecordedConnection(connection, mutate=mutate)
    value._con = recorded
    assert value.replay(tail=True, limit=300) == expected
    assert recorded.wide_count == 3
    assert other.execute("SELECT count(*) FROM market_updates").fetchone()[0] == 299
    other.close()


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_duplicate_selected_keys_refuse(lake, duplicate):
    value, connection = lake

    def mutate(rows, count):
        return [*rows, rows[0]] if duplicate else rows[1:]

    value._con = RecordedConnection(connection, mutate=mutate)
    with pytest.raises(ValueError, match="tail rows do not match selected keys"):
        value.replay(tail=True, limit=300)
    # The owned transaction is closed even on non-SQL validation errors.
    connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


def test_batch_fault_rolls_back_only_owned_transaction(lake):
    value, connection = lake
    value._con = RecordedConnection(connection, fault=True)
    with pytest.raises(RuntimeError, match="owned batch fault"):
        value.replay(tail=True, limit=300)
    connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


@pytest.mark.parametrize("caller_owned", [False, True])
def test_real_sql_failure_preserves_transaction_ownership(lake, caller_owned):
    value, connection = lake
    if caller_owned:
        connection.execute("BEGIN TRANSACTION")
        connection.execute("UPDATE market_updates SET state_note='uncommitted' WHERE local_seq=1")
    recorded = RecordedConnection(connection, fault="sql")
    value._con = recorded
    with pytest.raises(duckdb.CatalogException):
        value.replay(tail=True, limit=300)
    if caller_owned:
        assert not any(sql == "ROLLBACK" for sql, _ in recorded.calls)
        # DuckDB1.5.5 catalog errors leave the caller transaction usable. Do
        # not impose another version's error-abort behavior or reset its state.
        assert (
            connection.execute(
                "SELECT state_note FROM market_updates WHERE local_seq=1"
            ).fetchone()[0]
            == "uncommitted"
        )
        connection.execute("ROLLBACK")
        assert (
            connection.execute(
                "SELECT state_note FROM market_updates WHERE local_seq=1"
            ).fetchone()[0]
            != "uncommitted"
        )
    connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


def test_resource_refusal_does_not_return_partial_batches(lake):
    value, connection = lake
    value._con = RecordedConnection(connection, fault="oom")
    with pytest.raises(duckdb.OutOfMemoryException, match="owned batch resource refusal"):
        value.replay(tail=True, limit=300)
    connection.execute("BEGIN TRANSACTION")
    connection.execute("ROLLBACK")


def test_connection_lock_covers_all_batches(lake):
    value, connection = lake
    attempted, acquired = threading.Event(), threading.Event()
    worker = None

    def mutate(rows, count):
        nonlocal worker
        if count == 1:

            def wait_for_lock():
                attempted.set()
                with value._connection_lock:
                    acquired.set()

            worker = threading.Thread(target=wait_for_lock)
            worker.start()
            assert attempted.wait(1)
            assert not acquired.wait(0.02)
        return rows

    value._con = RecordedConnection(connection, mutate=mutate)
    assert len(value.replay(tail=True, limit=300)) == 300
    worker.join(timeout=1)
    assert not worker.is_alive() and acquired.is_set()


def test_forward_path_has_no_transaction_or_batch_queries(lake):
    value, connection = lake
    recorded = RecordedConnection(connection)
    value._con = recorded
    assert len(value.replay(limit=17)) == 17
    assert len(recorded.calls) == 1


def test_wide_default_tail_refusal_and_bounded_full_row_equivalence():
    # A generated view avoids writing wide data. This stricter32MiB model is
    # explicitly not the POSIX archive/128MiB native failure reproduction.
    connection = duckdb.connect(
        ":memory:",
        config={
            "memory_limit": "32MiB",
            "threads": 1,
            "max_temp_directory_size": "0B",
        },
    )
    connection.execute("""CREATE VIEW market_updates AS SELECT i+1 local_seq,
      'hyperliquid' venue,'BTC' instrument,
      CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END kind,'synthetic' provenance,
      TIMESTAMPTZ '2026-10-23 16:00:00+00'+i*INTERVAL '1 second' data_time,
      TIMESTAMPTZ '2026-10-23 16:00:00+00'+(i+i%5)*INTERVAL '1 second' received_at,
      i//2 AS "sequence",false sequence_gap,'complete' continuity,
      'owned-'||md5(i::VARCHAR) source_event_id,NULL::VARCHAR content_digest,
      NULL::VARCHAR snapshot_epoch,NULL::VARCHAR continuity_evidence_json,
      CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END state,
      CASE WHEN i%31=0 THEN repeat(md5(i::VARCHAR),256) ELSE NULL END state_note,
      CASE WHEN i%31=0 THEN '{}' ELSE
      json_object('open',100,'high',101,'low',99,'close',100,'interval','5m',
      'volume',42,'final',true,'padding',repeat(md5(i::VARCHAR),256)) END payload_json
      FROM range(16000) r(i)""")
    key = (
        "SELECT local_seq FROM market_updates "
        "QUALIFY ROW_NUMBER() OVER (ORDER BY local_seq DESC) <= ?"
    )
    keys = [r[0] for r in connection.execute(key, [10000]).fetchall()]
    assert len(keys) == 10000
    # Frozen9cdf wide membership query must genuinely refuse in this model.
    with pytest.raises(duckdb.OutOfMemoryException):
        connection.execute(
            f"SELECT {_UPDATE_COLUMNS} FROM market_updates WHERE local_seq IN ({key})",
            [10000],
        ).fetchall()
    value = LiveBuffer.__new__(LiveBuffer)
    recorded = RecordedConnection(connection)
    value._con = recorded
    value._connection_lock = threading.RLock()
    value.read_unavailable = False
    try:
        actual = value.replay(tail=True, limit=10000)
        assert len(actual) == 10000
        observed = hashlib.sha256()
        for row in actual:
            observed.update(row.model_dump_json().encode())
        expected = hashlib.sha256()
        for offset in range(0, len(keys), 128):
            batch = sorted(keys)[offset : offset + 128]
            marks = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT {_UPDATE_COLUMNS} FROM market_updates "
                f"WHERE local_seq IN ({marks}) ORDER BY local_seq",
                batch,
            ).fetchall()
            for row in rows:
                expected.update(_row_to_update(row).model_dump_json().encode())
        assert observed.hexdigest() == expected.hexdigest()
        assert recorded.wide_count == 79
        assert len(recorded.calls) == 84
    finally:
        connection.close()
