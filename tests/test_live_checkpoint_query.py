"""Checkpoint query plan and complete-row behavior on a real tiny DuckDB lake."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from quantmesh.live.buffer import LiveBuffer, LiveIdentityConflictError, _row_to_update
from quantmesh.live.contract import MarketUpdate

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _quote(event_id: str) -> MarketUpdate:
    return MarketUpdate(
        venue="hyperliquid",
        instrument="BTC",
        kind="quote",
        provenance="real",
        data_time=NOW,
        received_at=NOW,
        source_event_id=event_id,
        payload={"bid": 100, "ask": 101},
    )


class _CheckpointPlanProbe:
    """Explain the actual production statement, then execute it against DuckDB."""

    def __init__(self, connection):
        self.connection = connection
        self.plans = []

    def execute(self, query, parameters=None):
        plan = self.connection.execute("EXPLAIN " + query, parameters).fetchone()[1]
        self.plans.append(plan)
        return self.connection.execute(query, parameters)

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_actual_checkpoint_query_avoids_wide_row_window_and_second_scan(tmp_path):
    with LiveBuffer(tmp_path, retention_days=0) as lake:
        lake.append_many([_quote(f"quote-{index}") for index in range(16)])
        probe = _CheckpointPlanProbe(lake._con)
        lake._con = probe

        rows = lake.recovery_checkpoints(venue="hyperliquid", instruments=["BTC"])

        assert [row.source_event_id for row in rows] == ["quote-15"]
        assert len(probe.plans) == 1
        plan = probe.plans[0]
        assert "WINDOW" not in plan, plan
        assert plan.count("SEQ_SCAN") == 1, plan


def _event(event_id, *, kind="quote", payload=None, **overrides):
    fields = {
        "venue": "hyperliquid",
        "instrument": "BTC",
        "kind": kind,
        "provenance": "real",
        "data_time": NOW,
        "received_at": NOW,
        "source_event_id": event_id,
        "payload": {"bid": 100, "ask": 101} if payload is None else payload,
    }
    return MarketUpdate(**(fields | overrides))


def _candle(event_id, *, final=True, **overrides):
    return _event(
        event_id,
        kind="candle",
        payload={"open": 99, "high": 102, "low": 98, "close": 100, "volume": 3, "final": final},
        **overrides,
    )


@pytest.fixture
def checkpoint_lake(tmp_path):
    events = [
        _event("quote-old", data_time=NOW + timedelta(days=1), sequence=999),
        _event(
            "quote-winner",
            data_time=NOW - timedelta(days=1),
            received_at=NOW.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=2),
            payload={"bid": 81, "ask": 82, "marker": "完整行"},
            provenance="delayed",
        ),
        _event("mid-old", kind="metrics", payload={"mid": 100}),
        _event("ctx-old", kind="metrics", payload={"mark_price": 101}),
        _event("mid-winner", kind="metrics", payload={"mid": 102}),
        _event("ctx-winner", kind="metrics", payload={"mark_price": 103, "funding_rate": 0.001}),
        _candle("candle-complete"),
        _candle(
            "candle-recovered",
            continuity="recovered",
            continuity_evidence={
                "channel": "candle",
                "disconnected_at": NOW - timedelta(minutes=1),
                "last_durable_source_event_id": "candle-complete",
                "first_recovered_source_event_id": "candle-recovered",
                "recovered_at": NOW,
                "recovery_source": "fixed-local-fixture",
            },
        ),
        _candle("candle-provisional", final=False),
        _candle("candle-gapped", continuity="known-gap"),
        _event(
            "candle-missing-final",
            kind="candle",
            payload={"open": 99, "high": 102, "low": 98, "close": 100, "volume": 3},
        ),
        _candle("candle-unrecoverable", continuity="unrecoverable"),
        _candle("candle-disconnected", continuity="unknown-after-disconnect"),
        _event("trade-winner", kind="trade", payload={"price": 100, "size": 2, "side": "buy"}),
        _event("status-old", kind="status", payload={}, state="disconnected", state_note="old"),
        _event("status-winner", kind="status", payload={}, state="connected", state_note="恢复"),
        _event("eth-quote", instrument="ETH"),
        _event("sol-excluded", instrument="SOL"),
        _event("moomoo-quote", venue="moomoo"),
        _candle("moomoo-provisional", venue="moomoo", final=False, continuity="known-gap"),
        _candle("eth-ineligible-only", instrument="ETH", final=False),
        _event("delta-bid", kind="l2_delta", payload={"side": "bid", "levels": [[99, 1]]}),
        _event("delta-ask-winner", kind="l2_delta", payload={"side": "ask", "levels": [[101, 2]]}),
    ]
    for epoch in ("old-book", "winner-book"):
        for side in ("bid", "ask"):
            events.append(
                _event(
                    f"{epoch}-{side}",
                    kind="l2_snapshot",
                    snapshot_epoch=epoch,
                    payload={"side": side, "levels": [[99 if side == "bid" else 101, 3]]},
                )
            )
    with LiveBuffer(tmp_path, retention_days=0) as lake:
        # Valid typed events, real production row insertion, deliberately sparse PKs.
        # These are read-path fixtures; ingestion atomicity is covered in buffer tests.
        for index, event in enumerate(events, start=1):
            lake._insert_update(index * 101, event)
        with pytest.raises(LiveIdentityConflictError):
            lake.append(_event("quote-winner", payload={"bid": 900, "ask": 901}))
        assert len(lake.quarantined()) == 1
        yield lake, {event.source_event_id: event for event in events}


def _legacy_checkpoints(lake, venue, instruments):
    """Frozen pre-issue201 oracle, executed on the same real fixture table."""
    if not instruments:
        return []
    placeholders = ", ".join("?" for _ in instruments)
    candle_filter = (
        " AND (kind != 'candle' OR (json_extract_string(payload_json, '$.final') = 'true' "
        "AND continuity IN ('complete', 'recovered')))"
        if venue == "hyperliquid"
        else ""
    )
    rows = lake._con.execute(
        "SELECT local_seq, venue, instrument, kind, provenance, data_time, received_at, "
        "sequence, sequence_gap, continuity, source_event_id, content_digest, "
        "snapshot_epoch, continuity_evidence_json, state, state_note, payload_json "
        f"FROM market_updates WHERE venue = ? AND instrument IN ({placeholders})"
        f"{candle_filter} QUALIFY ROW_NUMBER() OVER ("
        "PARTITION BY venue, instrument, kind, "
        "CASE WHEN kind = 'l2_snapshot' THEN json_extract_string(payload_json, '$.side') "
        "WHEN kind = 'metrics' THEN CASE WHEN json_extract(payload_json, '$.mid') IS NOT NULL "
        "THEN 'allMids' ELSE 'activeAssetCtx' END ELSE '' END "
        "ORDER BY local_seq DESC) = 1 ORDER BY local_seq",
        [venue, *instruments],
    ).fetchall()
    return [_row_to_update(row) for row in rows]


@pytest.mark.parametrize(
    ("venue", "instruments", "expected_ids"),
    [
        (
            "hyperliquid",
            ["BTC", "ETH"],
            [
                "quote-winner",
                "mid-winner",
                "ctx-winner",
                "candle-recovered",
                "trade-winner",
                "status-winner",
                "eth-quote",
                "delta-ask-winner",
                "winner-book-bid",
                "winner-book-ask",
            ],
        ),
        ("hyperliquid", ["ETH"], ["eth-quote"]),
        ("hyperliquid", ["SOL"], ["sol-excluded"]),
        ("moomoo", ["BTC"], ["moomoo-quote", "moomoo-provisional"]),
        ("hyperliquid", ["BTC') OR true --"], []),
        ("hyperliquid", [], []),
        ("hyperliquid", ["MISSING"], []),
        ("polymarket", ["BTC"], []),
    ],
)
def test_checkpoint_winners_match_legacy_complete_events(
    checkpoint_lake,
    venue,
    instruments,
    expected_ids,
):
    lake, events = checkpoint_lake
    before = lake.replay(limit=100)
    old = _legacy_checkpoints(lake, venue, instruments)

    current = lake.recovery_checkpoints(venue=venue, instruments=instruments)

    assert [row.source_event_id for row in current] == expected_ids
    assert current == [events[event_id] for event_id in expected_ids]
    assert [row.model_dump_json() for row in current] == [row.model_dump_json() for row in old]
    assert lake.replay(limit=100) == before
    assert len(lake.quarantined()) == 1
