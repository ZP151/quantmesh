"""Replay lake round-trip, filtering and retention (0015 Phase A, ADR-0014)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)


def _update(
    venue: Venue,
    instrument: str,
    kind: UpdateKind,
    payload: dict,
    *,
    data_time: datetime | None = None,
    received_at: datetime | None = None,
    sequence: int | None = None,
    sequence_gap: bool = False,
    provenance: Provenance = Provenance.REAL,
    state: SourceState | None = None,
    state_note: str | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=data_time or datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
        received_at=received_at or datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
        sequence=sequence,
        sequence_gap=sequence_gap,
        payload=payload,
        state=state,
        state_note=state_note,
    )


def _quote(instrument: str, bid: float = 100.0, **overrides: object) -> MarketUpdate:
    return _update(
        Venue.HYPERLIQUID,
        instrument,
        UpdateKind.QUOTE,
        {"bid": bid, "ask": bid + 0.5},
        **overrides,
    )


@pytest.fixture
def buffer(tmp_path: Path) -> LiveBuffer:
    yield LiveBuffer(tmp_path, retention_days=7)
    # closed by the test itself where needed; GC otherwise


class TestAppendReplayRoundTrip:
    def test_all_kinds_round_trip(self, buffer: LiveBuffer) -> None:
        updates = [
            _quote("BTC"),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.TRADE,
                {"price": 100.25, "size": 0.5, "side": "sell"},
                sequence=7,
            ),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                {"open": 99.0, "high": 101.0, "low": 98.5, "close": 100.0, "volume": 3},
            ),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.L2_SNAPSHOT,
                {"side": "bid", "levels": [[99.5, 3.0], [99.0, 5.0]]},
            ),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.METRICS,
                {"funding_rate": 0.0001, "open_interest": 42.0},
            ),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.CONNECTED,
            ),
        ]
        for update in updates:
            buffer.append(update)
        replayed = buffer.replay()
        assert len(replayed) == len(updates)
        for original, row in zip(updates, replayed):
            assert row.venue is original.venue
            assert row.instrument == original.instrument
            assert row.kind is original.kind
            assert row.provenance is original.provenance
            assert row.data_time == original.data_time
            assert row.sequence == original.sequence
            assert row.sequence_gap == original.sequence_gap
            assert row.payload == original.payload
            assert row.state == original.state
            assert row.state_note == original.state_note

    def test_provenance_and_gap_flags_persist(self, buffer: LiveBuffer) -> None:
        update = _quote(
            "BTC",
            provenance=Provenance.DELAYED,
            sequence_gap=True,
            received_at=datetime(2026, 8, 9, 10, 0, 5, tzinfo=UTC),
        )
        buffer.append(update)
        [row] = buffer.replay()
        assert row.provenance is Provenance.DELAYED
        assert row.sequence_gap is True

    def test_local_seq_is_monotonic_across_venues(self, buffer: LiveBuffer) -> None:
        first = _quote("BTC")
        second = _update(
            Venue.POLYMARKET,
            "trump-2028",
            UpdateKind.QUOTE,
            {"bid": 0.48, "ask": 0.52},
        )
        assert buffer.append(first) == 1
        assert buffer.append(second) == 2


class TestReplayFilters:
    def _seed(self, buffer: LiveBuffer) -> None:
        for symbol in ("BTC", "ETH"):
            buffer.append(_quote(symbol))
        buffer.append(
            _update(
                Venue.POLYMARKET,
                "trump-2028",
                UpdateKind.QUOTE,
                {"bid": 0.48, "ask": 0.52},
                received_at=datetime(2026, 8, 9, 11, 0, 0, tzinfo=UTC),
            )
        )
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.TRADE,
                {"price": 100.25, "size": 0.5, "side": "buy"},
                received_at=datetime(2026, 8, 9, 11, 30, 0, tzinfo=UTC),
            )
        )

    def test_filter_by_venue(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(venue=Venue.POLYMARKET.value)
        assert [r.instrument for r in rows] == ["trump-2028"]

    def test_filter_by_instrument(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(instrument="ETH")
        assert [r.instrument for r in rows] == ["ETH"]

    def test_filter_by_kinds(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(kinds={UpdateKind.TRADE.value})
        assert [r.kind for r in rows] == [UpdateKind.TRADE]

    def test_filter_by_time_window(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        start = datetime(2026, 8, 9, 11, 0, 0, tzinfo=UTC)
        end = datetime(2026, 8, 9, 11, 30, 0, tzinfo=UTC)
        rows = buffer.replay(start=start, end=end)
        assert len(rows) == 2  # polymarket quote + trade at exactly 11:00/11:30

    def test_limit_applies_oldest_first(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(limit=2)
        assert len(rows) == 2
        assert [r.instrument for r in rows] == ["BTC", "ETH"]


class TestLatest:
    def test_one_row_per_venue_instrument_kind(self, buffer: LiveBuffer) -> None:
        buffer.append(_quote("BTC", bid=100.0))
        buffer.append(_quote("BTC", bid=100.5))
        buffer.append(_quote("ETH", bid=2000.0))
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.TRADE,
                {"price": 100.25, "size": 0.5, "side": "buy"},
            )
        )
        latest = buffer.latest()
        by_key = {(r.venue, r.instrument, r.kind): r for r in latest}
        assert len(by_key) == 3
        assert by_key[(Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE)].payload["bid"] == 100.5
        assert by_key[(Venue.HYPERLIQUID, "ETH", UpdateKind.QUOTE)].payload["bid"] == 2000.0
        assert by_key[(Venue.HYPERLIQUID, "BTC", UpdateKind.TRADE)].payload["price"] == 100.25

    def test_latest_scope_filters(self, buffer: LiveBuffer) -> None:
        buffer.append(_quote("BTC"))
        buffer.append(
            _update(
                Venue.POLYMARKET,
                "trump-2028",
                UpdateKind.QUOTE,
                {"bid": 0.48, "ask": 0.52},
            )
        )
        rows = buffer.latest(venue=Venue.POLYMARKET.value)
        assert len(rows) == 1
        assert rows[0].instrument == "trump-2028"


class TestStatusUpsert:
    def test_last_status_wins_per_source(self, buffer: LiveBuffer) -> None:
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.CONNECTED,
                received_at=datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
            )
        )
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.STALE,
                state_note="no frames for 90s",
                received_at=datetime(2026, 8, 9, 10, 5, 0, tzinfo=UTC),
            )
        )
        statuses = buffer.statuses()
        assert len(statuses) == 1
        assert statuses[0]["state"] == SourceState.STALE.value
        assert statuses[0]["note"] == "no frames for 90s"

    def test_status_rows_are_separate_per_source(self, buffer: LiveBuffer) -> None:
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.CONNECTED,
            )
        )
        buffer.append(
            _update(
                Venue.POLYMARKET,
                "trump-2028",
                UpdateKind.STATUS,
                {},
                state=SourceState.UNAVAILABLE,
            )
        )
        assert len(buffer.statuses()) == 2


class TestRetention:
    def test_old_rows_pruned_fresh_kept(self, tmp_path: Path) -> None:
        past = datetime.now(UTC) - timedelta(days=10)
        buffer = LiveBuffer(tmp_path, retention_days=1)
        try:
            buffer.append(_quote("BTC", received_at=past))
            buffer.append(_quote("ETH", received_at=datetime.now(UTC)))
            assert buffer.prune() == 1
            rows = buffer.replay()
            assert [r.instrument for r in rows] == ["ETH"]
        finally:
            buffer.close()

    def test_zero_retention_disables_pruning(self, tmp_path: Path) -> None:
        past = datetime.now(UTC) - timedelta(days=10)
        buffer = LiveBuffer(tmp_path, retention_days=0)
        try:
            buffer.append(_quote("BTC", received_at=past))
            assert buffer.prune() == 0
            assert len(buffer.replay()) == 1
        finally:
            buffer.close()


class TestFailClosed:
    def test_corrupt_payload_raises_on_replay(self, tmp_path: Path) -> None:
        buffer = LiveBuffer(tmp_path)
        try:
            buffer.append(_quote("BTC"))
            buffer._con.execute(
                "UPDATE market_updates SET payload_json = ? WHERE instrument = 'BTC'",
                ["{not json"],
            )
            with pytest.raises(Exception):
                buffer.replay()
        finally:
            buffer.close()

    def test_invalid_payload_never_enters_lake(self, tmp_path: Path) -> None:
        buffer = LiveBuffer(tmp_path)
        try:
            with pytest.raises(ValidationError):
                buffer.append(
                    _update(
                        Venue.HYPERLIQUID,
                        "BTC",
                        UpdateKind.QUOTE,
                        {"bid": 101.0, "ask": 100.0},  # ask below bid
                    )
                )
            assert buffer.replay() == []
        finally:
            buffer.close()

    def test_replay_rejects_unknown_kind_row(self, tmp_path: Path) -> None:
        buffer = LiveBuffer(tmp_path)
        try:
            buffer.append(_quote("BTC"))
            buffer._con.execute("UPDATE market_updates SET kind = 'orderbook'")
            with pytest.raises(ValidationError):
                buffer.replay()
        finally:
            buffer.close()

    def test_json_round_trip_of_payload_shape(self, buffer: LiveBuffer) -> None:
        payload = {"levels": [[99.5, 3.0], [99.0, 5.0]], "side": "bid"}
        buffer.append(
            _update(Venue.HYPERLIQUID, "BTC", UpdateKind.L2_SNAPSHOT, payload)
        )
        [row] = buffer.replay()
        assert row.payload == payload
        # stored form is stable JSON text, ready for Parquet-style reads
        stored = buffer._con.execute(
            "SELECT payload_json FROM market_updates"
        ).fetchone()[0]
        assert json.loads(stored) == payload
