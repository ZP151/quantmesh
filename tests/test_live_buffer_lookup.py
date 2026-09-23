"""Retained-lake identity lookups stay selective without weakening exact scope."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer, LiveIdentityConflictError
from quantmesh.live.contract import MarketUpdate, UpdateKind
from tests.live_clock import freeze_buffer_clock

NOW = datetime(2026, 9, 13, 10, tzinfo=UTC)


def _update(
    index=0,
    *,
    venue=Venue.HYPERLIQUID,
    instrument="BTC",
    kind=UpdateKind.QUOTE,
    event_id=None,
    price=100.0,
):
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance="real",
        data_time=NOW + timedelta(milliseconds=index),
        received_at=NOW + timedelta(milliseconds=index),
        sequence=index,
        source_event_id=event_id or hashlib.sha256(f"observed-{index}".encode()).hexdigest(),
        payload={"bid": price, "ask": price + 0.5}
        if kind is UpdateKind.QUOTE
        else {"price": price, "size": 1.0, "side": "buy"},
    )


class _LookupProbe:
    """Explain the actual admission SQL before executing it, including true misses."""

    def __init__(self, connection):
        self.connection = connection
        self.lookups = []

    def execute(self, query, parameters=None):
        if query.startswith("SELECT local_seq, content_digest FROM market_updates"):
            plan = self.connection.execute("EXPLAIN ANALYZE " + query, parameters).fetchone()[1]
            self.lookups.append((query, tuple(parameters), plan))
        if parameters is None:
            return self.connection.execute(query)
        return self.connection.execute(query, parameters)

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_actual_append_lookup_uses_index_on_retained_hit_and_hash_miss(tmp_path, monkeypatch):
    freeze_buffer_clock(monkeypatch, NOW + timedelta(minutes=1))
    rows = [
        _update(
            index,
            venue=Venue.HYPERLIQUID if index % 2 else Venue.MOOMOO,
            instrument=("BTC", "ETH", "SOL")[index % 3],
            kind=UpdateKind.QUOTE if index % 4 else UpdateKind.TRADE,
        )
        for index in range(4096)
    ]
    with LiveBuffer(tmp_path) as buffer:
        receipts = buffer.append_many(rows)
        assert receipts[-1] == 4096
        buffer._con.execute("CHECKPOINT")

    with LiveBuffer(tmp_path) as buffer:
        probe = _LookupProbe(buffer._con)
        buffer._con = probe
        duplicate = buffer.append(rows[-1])
        inserted = buffer.append(_update(5000))
        assert duplicate == 4096 and duplicate.inserted is False
        assert inserted == 4097 and inserted.inserted is True
        assert len(probe.lookups) == 2
        for _query, _parameters, plan in probe.lookups:
            assert "Index Scan" in plan, plan
            assert "Sequential Scan" not in plan, plan
        assert buffer.quarantined() == []


def test_shared_source_id_remains_scoped_and_conflicts_still_quarantine(tmp_path):
    rows = [
        _update(event_id="shared"),
        _update(event_id="shared", venue=Venue.MOOMOO),
        _update(event_id="shared", instrument="ETH"),
        _update(event_id="shared", kind=UpdateKind.TRADE),
    ]
    with LiveBuffer(tmp_path) as buffer:
        assert list(buffer.append_many(rows)) == [1, 2, 3, 4]
        for sequence, row in enumerate(rows, 1):
            receipt = buffer.append(
                row.model_copy(update={"received_at": NOW + timedelta(seconds=1)})
            )
            assert receipt == sequence and receipt.inserted is False
        # Existing source ID in another scope must not suppress a new stream.
        new_scope = _update(event_id="shared", instrument="SOL")
        assert buffer.append(new_scope) == 5
        conflict = _update(event_id="shared", price=99.0)
        with pytest.raises(LiveIdentityConflictError):
            buffer.append(conflict)
        assert buffer.replay() == [*rows, new_scope]
        [quarantined] = buffer.quarantined()
        assert quarantined["existing_content_digest"] == rows[0].content_digest
        assert quarantined["conflicting_content_digest"] == conflict.content_digest


@pytest.mark.parametrize("column", ["venue", "instrument", "kind"])
def test_lookup_scope_columns_cannot_contain_null(tmp_path, column):
    with LiveBuffer(tmp_path) as buffer:
        original = _update()
        buffer.append(original)
        with pytest.raises(duckdb.ConstraintException, match="NOT NULL"):
            buffer._con.execute(f"UPDATE market_updates SET {column} = NULL WHERE local_seq = 1")
        assert buffer.replay() == [original]


def _assert_lookup_index(buffer):
    assert buffer._con.execute(
        "SELECT is_unique FROM duckdb_indexes() "
        "WHERE index_name = 'idx_updates_source_event_lookup'"
    ).fetchall() == [(False,)]
    assert buffer._con.execute(
        "SELECT is_unique FROM duckdb_indexes() WHERE index_name = 'idx_updates_source_identity'"
    ).fetchall() == [(True,)]
    assert buffer._con.execute(
        "SELECT version FROM live_schema_metadata WHERE component = 'market_updates'"
    ).fetchone() == (2,)


def test_prior_schema_reopen_adds_lookup_without_changing_rows_or_quarantine(tmp_path, monkeypatch):
    freeze_buffer_clock(monkeypatch, NOW + timedelta(minutes=1))
    original = _update(event_id="retained")
    with LiveBuffer(tmp_path) as buffer:
        buffer.append(original)
        with pytest.raises(LiveIdentityConflictError):
            buffer.append(_update(event_id="retained", price=99.0))
        retained_quarantine = buffer.quarantined()
        buffer._con.execute("DROP INDEX IF EXISTS idx_updates_source_event_lookup")
    for _ in range(2):
        with LiveBuffer(tmp_path) as buffer:
            _assert_lookup_index(buffer)
            assert buffer.replay() == [original]
            assert buffer.quarantined() == retained_quarantine
            assert buffer.append(original).inserted is False


def test_legacy_missing_identity_column_migrates_before_lookup_index(tmp_path, monkeypatch):
    freeze_buffer_clock(monkeypatch, NOW + timedelta(minutes=1))
    path = tmp_path / "live" / "updates.duckdb"
    path.parent.mkdir()
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE market_updates ("
            "local_seq BIGINT PRIMARY KEY, venue VARCHAR NOT NULL, "
            "instrument VARCHAR NOT NULL, kind VARCHAR NOT NULL, "
            "provenance VARCHAR NOT NULL, data_time TIMESTAMPTZ NOT NULL, "
            "received_at TIMESTAMPTZ NOT NULL, sequence BIGINT, "
            "sequence_gap BOOLEAN NOT NULL DEFAULT FALSE, state VARCHAR, "
            "state_note VARCHAR, payload_json VARCHAR NOT NULL)"
        )
        connection.execute(
            "INSERT INTO market_updates VALUES "
            "(7, 'hyperliquid', 'BTC', 'quote', 'real', ?, ?, 9, true, NULL, NULL, ?)",
            [NOW, NOW, json.dumps({"bid": 100.0, "ask": 100.5})],
        )
    with LiveBuffer(tmp_path) as buffer:
        _assert_lookup_index(buffer)
        [migrated] = buffer.replay()
        assert migrated.source_event_id == "legacy-v1:7"
        assert migrated.continuity.value == "known-gap"
    with LiveBuffer(tmp_path) as buffer:
        _assert_lookup_index(buffer)
        assert buffer.replay() == [migrated]
        assert buffer.append(migrated) == 7
