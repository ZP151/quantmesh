"""Latest bootstrap: real owned DuckDB controls, not native/archive qualification."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from pydantic import ValidationError

from quantmesh.live.buffer import _SCHEMA, _UPDATE_COLUMNS, LiveBuffer, _row_to_update
from quantmesh.live.feed import LiveFeed

AT = datetime(2026, 10, 23, 16, tzinfo=UTC)


def raw_row(key, *, venue="hyperliquid", symbol="BTC", kind="quote", payload=None, identity=None):
    return (
        key,
        venue,
        symbol,
        kind,
        "synthetic",
        AT + timedelta(seconds=key),
        AT + timedelta(seconds=key, milliseconds=100),
        None if key % 5 == 0 else key,
        key % 17 == 0,
        "known-gap" if key % 17 == 0 else "complete",
        identity,
        None,
        None,
        None,
        "disconnected" if kind == "status" else None,
        f"barrier-{key}" if kind == "status" else None,
        json.dumps(
            payload if payload is not None else {"bid": key + 1, "ask": key + 2},
            separators=(",", ":"),
        ),
    )


def oracle(rows, venue=None, instrument=None):
    """Independent Python stream map, not the SQL grouping implementation."""
    winners = {}
    for row in rows:
        if venue is not None and row[1] != venue or instrument is not None and row[2] != instrument:
            continue
        body = json.loads(row[-1])
        channel = (
            body.get("side")
            if row[3] == "l2_snapshot"
            else ("allMids" if "mid" in body else "activeAssetCtx")
            if row[3] == "metrics"
            else ""
        )
        stream = row[1:4] + (channel,)
        if stream not in winners or row[0] > winners[stream][0]:
            winners[stream] = row
    return sorted(winners.values(), key=lambda row: row[0])


def stored(root, rows, *, nullable_kind=False):
    path = root / "live/updates.duckdb"
    path.parent.mkdir(parents=True)
    with duckdb.connect(str(path)) as connection:
        connection.execute(_SCHEMA)
        connection.execute("INSERT INTO live_schema_metadata VALUES ('market_updates',2)")
        if nullable_kind:
            connection.execute("ALTER TABLE market_updates ALTER COLUMN kind DROP NOT NULL")
        connection.execute("BEGIN TRANSACTION")
        connection.executemany(
            "INSERT INTO market_updates VALUES (" + ",".join("?" for _ in range(17)) + ")", rows
        )
        connection.execute("COMMIT")
        connection.execute("CHECKPOINT")
    return path


def generated(root):
    """Persisted tiny VIEW fixture; layout differs from the real stored archive."""
    path = root / "live/updates.duckdb"
    path.parent.mkdir(parents=True)
    with duckdb.connect(str(path)) as connection:
        connection.execute(_SCHEMA)
        connection.execute("DROP TABLE market_updates")
        connection.execute("""CREATE VIEW market_updates AS SELECT i+1 local_seq,
          'hyperliquid' venue,'S'||(i%700)::VARCHAR instrument,
          CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END kind,'synthetic' provenance,
          TIMESTAMPTZ '2026-10-23 16:00:00+00'+i*INTERVAL '1 second' data_time,
          TIMESTAMPTZ '2026-10-23 16:00:01+00'+i*INTERVAL '1 second' received_at,
          i AS sequence,false sequence_gap,'complete' continuity,
          'owned-'||i::VARCHAR source_event_id,NULL::VARCHAR content_digest,
          NULL::VARCHAR snapshot_epoch,NULL::VARCHAR continuity_evidence_json,
          CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END state,
          CASE WHEN i%31=0 THEN repeat(md5(i::VARCHAR),256) ELSE NULL END state_note,
          CASE WHEN i%31=0 THEN '{}' ELSE
          json_object('open',100,'high',101,'low',99,'close',100,'interval','1m',
          'volume',42,'final',true,'padding',repeat(md5(i::VARCHAR),256)) END payload_json
          FROM range(16000)r(i)""")
        connection.execute("CHECKPOINT")
    return path


def generated_oracle():
    winners = {}
    for index in range(16000):
        winners[(index % 700, index % 31 == 0)] = index
    rows = []
    for index in sorted(winners.values()):
        token = hashlib.md5(str(index).encode(), usedforsecurity=False).hexdigest()
        status = index % 31 == 0
        body = (
            {}
            if status
            else {
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "interval": "1m",
                "volume": 42,
                "final": True,
                "padding": token * 256,
            }
        )
        rows.append(
            (
                index + 1,
                "hyperliquid",
                f"S{index % 700}",
                "status" if status else "candle",
                "synthetic",
                AT + timedelta(seconds=index),
                AT + timedelta(seconds=index + 1),
                index,
                False,
                "complete",
                f"owned-{index}",
                None,
                None,
                None,
                "disconnected" if status else None,
                token * 256 if status else None,
                json.dumps(body, separators=(",", ":")),
            )
        )
    return rows


def test_real_readonly_feed_bootstrap_128mib_preserves_all_complete_winners(tmp_path):
    # Exact production connection settings, but a tiny generated VIEW, not native stored layout.
    path = generated(tmp_path / "archive")
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    expected = [_row_to_update(row) for row in generated_oracle()]
    with LiveBuffer(tmp_path / "archive", read_only=True) as reader:
        settings = reader._con.execute(
            "SELECT current_setting('memory_limit'),current_setting('threads'),"
            "current_setting('max_temp_directory_size')"
        ).fetchone()
        assert settings == ("128.0 MiB", 1, "0 bytes")
        feed = LiveFeed(
            lake=reader
        )  # real native failing call chain; no substitute feed/connection
        assert feed.replay_buffer is reader
        assert reader.latest() == expected
        state = feed.latest_state(now=AT + timedelta(days=1))["instruments"]
        assert len(state) == 700
        assert sum(len(value["kinds"]) for value in state.values()) == len(expected)
    assert before == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    assert sorted(p.name for p in path.parent.iterdir()) == ["updates.duckdb"]


@pytest.fixture
def varied_rows():
    rows = []
    for venue in ("hyperliquid", "moomoo"):
        for symbol in ("BTC", "X'OR1=1"):
            bodies = [
                ("quote", {"bid": 100, "ask": 101}),
                ("trade", {"price": 100, "size": 2, "side": "buy"}),
                ("status", {}),
                (
                    "candle",
                    {
                        "open": 100,
                        "high": 101,
                        "low": 99,
                        "close": 100,
                        "volume": 42,
                        "interval": "1m",
                    },
                ),
                ("l2_snapshot", {"side": "bid", "levels": [[100, 1]]}),
                ("l2_snapshot", {"side": "ask", "levels": [[101, 2]]}),
                ("metrics", {"mark": 101}),
                ("metrics", {"mid": None}),
                ("metrics", {"mid": 100}),
            ]
            for revision in range(3):
                for kind, body in bodies:
                    key = len(rows) + 1
                    rows.append(
                        raw_row(
                            key,
                            venue=venue,
                            symbol=symbol,
                            kind=kind,
                            payload=body,
                            identity=None if key % 5 == 0 else f"event-{key}",
                        )
                    )
    enriched = []
    for row in rows:
        if row[3] == "l2_snapshot":
            row = (*row[:12], f"epoch-{row[0]}", *row[13:])
        if row[8]:
            evidence = json.dumps(
                {
                    "channel": row[3],
                    "disconnected_at": AT.isoformat(),
                    "last_durable_source_event_id": None,
                    "first_recovered_source_event_id": f"recovered-{row[0]}",
                    "recovered_at": row[5].isoformat(),
                    "recovery_source": "owned-test",
                }
            )
            row = (*row[:13], evidence, *row[14:])
        if row[0] % 2 == 0 and json.loads(row[-1]).get("mid", 0) is not None:
            row = (*row[:11], _row_to_update(row).content_digest, *row[12:])
        enriched.append(row)
    return enriched


@pytest.mark.parametrize(
    "venue,instrument",
    [(None, None), ("hyperliquid", None), (None, "BTC"), ("moomoo", "X'OR1=1"), ("missing", "BTC")],
)
def test_full_stored_equivalence_filters_channels_status_and_revisions(
    tmp_path, varied_rows, venue, instrument
):
    # Deliberately repeated identities across independent venue/stream scopes.
    varied_rows[0] = (*varied_rows[0][:10], "cross-scope", *varied_rows[0][11:])
    varied_rows[-1] = (*varied_rows[-1][:10], "cross-scope", *varied_rows[-1][11:])
    path = stored(tmp_path, varied_rows)
    before = path.read_bytes()
    with LiveBuffer(tmp_path, read_only=True) as reader:
        selected = oracle(varied_rows, venue, instrument)
        expected = [_row_to_update(row) for row in selected]
        observer = Observe(reader._con)
        reader._con = observer
        assert reader.latest(venue=venue, instrument=instrument) == expected
        assert sorted(observer.complete_rows, key=lambda row: row[0]) == selected
    assert path.read_bytes() == before


@pytest.mark.parametrize("bad_kind", [None, "unknown-kind"])
def test_null_or_unknown_kind_keeps_original_validation_refusal(tmp_path, bad_kind):
    stored(tmp_path, [raw_row(1, kind=bad_kind)], nullable_kind=True)
    with LiveBuffer(tmp_path, read_only=True) as reader:
        with pytest.raises(ValidationError):
            reader.latest()


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("l2_snapshot", {"side": None, "levels": [[100, 1]]}),
        ("l2_snapshot", {"levels": [[100, 1]]}),
        ("metrics", {"mid": None}),
    ],
)
def test_invalid_channel_winners_keep_original_validation_refusal(tmp_path, kind, payload):
    stored(tmp_path, [raw_row(1, kind=kind, payload=payload)])
    with LiveBuffer(tmp_path, read_only=True) as reader:
        with pytest.raises(ValidationError):
            reader.latest()


def test_all_keys_over_ten_thousand_and_empty_are_not_capped(tmp_path):
    rows = [raw_row(i + 1, symbol=f"S{i}", identity=f"event-{i}") for i in range(10037)]
    stored(tmp_path, rows)
    with LiveBuffer(tmp_path, read_only=True) as reader:
        assert reader.latest() == [_row_to_update(row) for row in rows]
        assert reader.latest(venue="missing") == []


class Observe:
    """Real connection observer for cross-statement snapshot/cancellation behavior."""

    def __init__(self, connection, after_first=None, fault=None):
        self.connection = connection
        self.after_first = after_first
        self.fault = fault
        self.count = 0
        self.complete_rows = []

    def execute(self, query, params=None):
        wide = query.startswith(f"SELECT {_UPDATE_COLUMNS}")
        if wide:
            self.count += 1
            if self.count == 2 and self.fault is not None:
                raise self.fault
        self.wide = wide
        self.connection.execute(query, params) if params is not None else self.connection.execute(
            query
        )
        return self

    def fetchall(self):
        rows = self.connection.fetchall()
        if self.wide:
            self.complete_rows.extend(rows)
        if self.wide and self.count == 1 and self.after_first:
            self.after_first()
        return rows

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_one_snapshot_survives_writer_between_complete_batches(tmp_path):
    rows = [raw_row(i + 1, symbol=f"S{i}", identity=f"event-{i}") for i in range(300)]
    rows = [(*row[:11], _row_to_update(row).content_digest, *row[12:]) for row in rows]
    path = stored(tmp_path, rows)
    with LiveBuffer(tmp_path, retention_days=0) as reader, duckdb.connect(str(path)) as writer:

        def mutate():
            writer.execute("DELETE FROM market_updates WHERE local_seq=299")
            writer.execute(
                "UPDATE market_updates SET source_event_id='changed' WHERE local_seq=298"
            )

        observer = Observe(reader._con, after_first=mutate)
        reader._con = observer
        assert reader.latest() == [_row_to_update(row) for row in rows]
        assert observer.count == 3
        assert writer.execute("SELECT COUNT(*) FROM market_updates").fetchone()[0] == 299


def test_success_keeps_caller_transaction_open_and_uncommitted(tmp_path):
    rows = [raw_row(i + 1, symbol=f"S{i}", identity=f"event-{i}") for i in range(300)]
    rows = [(*row[:11], _row_to_update(row).content_digest, *row[12:]) for row in rows]
    path = stored(tmp_path, rows)
    with LiveBuffer(tmp_path, retention_days=0) as reader, duckdb.connect(str(path)) as other:
        connection = reader._con
        connection.execute("BEGIN TRANSACTION")
        connection.execute(
            "UPDATE market_updates SET source_event_id='uncommitted' WHERE local_seq=1"
        )
        changed = [(*rows[0][:10], "uncommitted", *rows[0][11:]), *rows[1:]]
        assert reader.latest() == [_row_to_update(row) for row in changed]
        assert (
            other.execute(
                "SELECT source_event_id FROM market_updates WHERE local_seq=1"
            ).fetchone()[0]
            == "event-0"
        )
        connection.execute("ROLLBACK")
        assert reader.latest() == [_row_to_update(row) for row in rows]


@pytest.mark.parametrize("caller_owned", [False, True])
@pytest.mark.parametrize("fault", [KeyboardInterrupt, duckdb.OutOfMemoryException])
def test_failure_and_cancellation_never_return_partial_or_commit_caller(
    tmp_path, caller_owned, fault
):
    rows = [raw_row(i + 1, symbol=f"S{i}", identity=f"event-{i}") for i in range(300)]
    rows = [(*row[:11], _row_to_update(row).content_digest, *row[12:]) for row in rows]
    path = stored(tmp_path, rows)
    with LiveBuffer(tmp_path, retention_days=0) as reader, duckdb.connect(str(path)) as other:
        connection = reader._con
        if caller_owned:
            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                "UPDATE market_updates SET source_event_id='uncommitted' WHERE local_seq=1"
            )
        reader._con = Observe(connection, fault=fault("owned interruption"))
        with pytest.raises(fault):
            reader.latest()
        if caller_owned:
            assert (
                connection.execute(
                    "SELECT source_event_id FROM market_updates WHERE local_seq=1"
                ).fetchone()[0]
                == "uncommitted"
            )
            assert (
                other.execute(
                    "SELECT source_event_id FROM market_updates WHERE local_seq=1"
                ).fetchone()[0]
                == "event-0"
            )
            connection.execute("ROLLBACK")
        connection.execute("BEGIN TRANSACTION")
        connection.execute("ROLLBACK")


def test_real_resource_refusal_is_explicit_with_no_partial_success(tmp_path):
    stored(tmp_path, [raw_row(1)])
    with LiveBuffer(tmp_path, read_only=True) as reader:
        # Explicit lower-cap refusal, not a production128MiB certificate.
        reader._con.execute("SET memory_limit='2MiB'")
        with pytest.raises(duckdb.OutOfMemoryException):
            reader.latest()
