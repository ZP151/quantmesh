"""Replay lake round-trip, filtering and retention (0015 Phase A, ADR-0014)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import quantmesh.live.buffer as buffer_module
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


class _FailStatusWriteOnce:
    """DuckDB boundary proxy that fails after the replay-event insert."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._armed = True
        self.error = RuntimeError("injected source_status write failure")

    def execute(self, query: str, parameters: object = None) -> Any:
        if self._armed and query.startswith("INSERT INTO source_status"):
            self._armed = False
            raise self.error
        if parameters is None:
            return self._connection.execute(query)
        return self._connection.execute(query, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


@pytest.fixture
def buffer(tmp_path: Path) -> LiveBuffer:
    yield LiveBuffer(tmp_path, retention_days=7)
    # closed by the test itself where needed; GC otherwise


class TestAppendReplayRoundTrip:
    def test_status_append_is_atomic_and_retry_reuses_the_local_sequence(
        self, tmp_path: Path
    ) -> None:
        lake = LiveBuffer(tmp_path)
        failing_connection = _FailStatusWriteOnce(lake._con)
        lake._con = failing_connection
        status = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.STATUS,
            {},
            state=SourceState.DISCONNECTED,
            state_note="fault drill",
        )
        try:
            with pytest.raises(
                RuntimeError, match="injected source_status write failure"
            ) as caught:
                lake.append(status)
            assert caught.value is failing_connection.error

            assert lake.replay() == []
            assert lake.statuses() == []

            assert lake.append(status) == 1
            assert lake.replay() == [status]
            assert lake.statuses() == [
                {
                    "venue": Venue.HYPERLIQUID.value,
                    "instrument": "BTC",
                    "state": SourceState.DISCONNECTED.value,
                    "note": "fault drill",
                    "changed_at": status.received_at,
                }
            ]
        finally:
            lake.close()

    def test_non_status_append_commits_for_a_reopened_long_lived_lake(
        self, tmp_path: Path
    ) -> None:
        lake = LiveBuffer(tmp_path)
        update = _quote("BTC", sequence=7)
        assert lake.append(update) == 1
        lake.close()

        reopened = LiveBuffer(tmp_path)
        try:
            assert reopened.replay() == [update]
        finally:
            reopened.close()

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

    def test_constructor_pins_utc_even_when_connection_opens_non_utc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_connect = buffer_module.duckdb.connect

        def non_utc_connect(*args: object, **kwargs: object):
            connection = real_connect(*args, **kwargs)
            connection.execute("SET TimeZone = 'America/New_York'")
            return connection

        monkeypatch.setattr(buffer_module.duckdb, "connect", non_utc_connect)
        lake = buffer_module.LiveBuffer(tmp_path)
        try:
            lake.append(_quote("BTC"))
            [row] = lake.replay()
            assert row.received_at.isoformat().endswith("+00:00")
        finally:
            lake.close()


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

    def test_local_sequence_reconstructs_same_timestamp_cutoff(
        self, buffer: LiveBuffer
    ) -> None:
        timestamp = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        first_seq = buffer.append(_quote("BTC", bid=100.0, received_at=timestamp))
        buffer.append(_quote("BTC", bid=101.0, received_at=timestamp))

        rows = buffer.replay(through_local_seq=first_seq)

        assert len(rows) == 1
        assert rows[0].payload["bid"] == 100.0
        assert len(buffer.replay(end=timestamp)) == 2

    def test_local_sequence_cutoff_must_be_positive(self, buffer: LiveBuffer) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            buffer.replay(through_local_seq=0)


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
