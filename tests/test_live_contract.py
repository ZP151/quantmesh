"""MarketUpdate contract validation (iteration 0015 Phase A, ADR-0014).

The contract is the fail-closed boundary every venue stream must pass
through: unknown enums, naive timestamps, malformed payloads and
inconsistent quotes are rejected here rather than silently tolerated
downstream.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Venue
from quantmesh.live.contract import (
    ContinuityState,
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)


def test_continuity_states_are_an_exact_stable_contract() -> None:
    assert [state.value for state in ContinuityState] == [
        "complete",
        "known-gap",
        "unknown-after-disconnect",
        "recovered",
        "unrecoverable",
    ]


def test_legacy_sequence_gap_maps_to_known_gap() -> None:
    update = _update(UpdateKind.QUOTE, _quote(), sequence_gap=True)

    assert update.continuity is ContinuityState.KNOWN_GAP
    assert update.sequence_gap is True


def test_noncomplete_continuity_preserves_legacy_gap_surface() -> None:
    update = _update(
        UpdateKind.CANDLE,
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
        continuity=ContinuityState.RECOVERED,
    )

    assert update.sequence_gap is True
    assert update.source_event_id
    assert len(update.content_digest) == 64


@pytest.mark.parametrize("continuity", list(ContinuityState))
def test_continuity_and_legacy_gap_have_one_exact_mapping(
    continuity: ContinuityState,
) -> None:
    update = _update(UpdateKind.QUOTE, _quote(), continuity=continuity)

    assert update.sequence_gap is (continuity is not ContinuityState.COMPLETE)


def test_explicit_contradictory_gap_and_continuity_are_rejected() -> None:
    with pytest.raises(ValidationError, match="contradicts continuity"):
        _update(
            UpdateKind.QUOTE,
            _quote(),
            continuity=ContinuityState.RECOVERED,
            sequence_gap=False,
        )


def test_content_digest_ignores_receipt_but_changes_with_source_content() -> None:
    original = _update(UpdateKind.QUOTE, _quote())
    redelivery = original.model_copy(
        update={"received_at": original.received_at.replace(microsecond=1)}
    )
    changed = _update(UpdateKind.QUOTE, _quote(bid=100.1))

    assert redelivery.content_digest == original.content_digest
    assert changed.content_digest != original.content_digest


def _quote(**overrides: object) -> dict:
    payload = {"bid": 100.0, "ask": 100.5, "bid_size": 1.0, "ask_size": 2.0}
    payload.update(overrides)
    return payload


def _update(kind: UpdateKind, payload: dict, **overrides: object) -> MarketUpdate:
    values: dict[str, object] = {
        "venue": Venue.HYPERLIQUID,
        "instrument": "BTC",
        "kind": kind,
        "provenance": Provenance.REAL,
        "data_time": datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
        "payload": payload,
    }
    values.update(overrides)
    return MarketUpdate.model_validate(values)


class TestAwareTimestamps:
    def test_naive_data_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(
                UpdateKind.QUOTE,
                _quote(),
                data_time=datetime(2026, 8, 9, 10, 0, 0),  # naive
            )

    def test_naive_received_at_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(
                UpdateKind.QUOTE,
                _quote(),
                received_at=datetime(2026, 8, 9, 10, 0, 0),  # naive
            )

    def test_aware_timestamps_accepted(self) -> None:
        update = _update(UpdateKind.QUOTE, _quote())
        assert update.data_time.tzinfo is not None
        assert update.received_at.tzinfo is not None


class TestEnumStrictness:
    def test_unknown_venue_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(), venue="bogus-exchange")

    def test_unknown_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update("orderbook", _quote())

    def test_unknown_provenance_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(), provenance="imagination")

    def test_negative_sequence_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(), sequence=-1)


class TestQuote:
    def test_missing_bid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, {"ask": 100.5})

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(bid=-0.01))

    def test_ask_below_bid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(bid=101.0, ask=100.5))

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(ask_size=-1))

    def test_healthy_quote_accepted(self) -> None:
        update = _update(UpdateKind.QUOTE, _quote())
        assert update.kind is UpdateKind.QUOTE


class TestTrade:
    def test_zero_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.TRADE, {"price": 0, "size": 1, "side": "buy"})

    def test_missing_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.TRADE, {"price": 100.0, "side": "buy"})

    def test_bad_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.TRADE, {"price": 100.0, "size": 1, "side": "hold"})

    def test_healthy_trade_accepted(self) -> None:
        update = _update(UpdateKind.TRADE, {"price": 100.25, "size": 0.5, "side": "sell"})
        assert update.kind is UpdateKind.TRADE


class TestCandle:
    def _candle(self, **overrides: object) -> dict:
        payload = {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.5, "volume": 10}
        payload.update(overrides)
        return payload

    def test_high_below_close_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.CANDLE, self._candle(high=101.0))

    def test_low_above_open_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.CANDLE, self._candle(low=100.5))

    def test_missing_ohlc_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.CANDLE, {"open": 100.0, "high": 102.0, "low": 99.0})

    def test_volume_optional(self) -> None:
        update = _update(
            UpdateKind.CANDLE,
            {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.5},
        )
        assert update.payload.get("volume", 0) == 0


class TestL2:
    def _levels(self) -> list[list[float]]:
        return [[99.5, 3.0], [99.0, 5.0]]

    def test_snapshot_without_levels_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.L2_SNAPSHOT, {"side": "bid", "levels": []})

    def test_missing_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.L2_SNAPSHOT, {"levels": self._levels()})

    def test_unsorted_levels_rejected(self) -> None:
        # 99.5 → 98.0 (down) then 99.0 (up): not monotonic
        with pytest.raises(ValidationError):
            _update(
                UpdateKind.L2_SNAPSHOT,
                {"side": "bid", "levels": [[99.5, 3.0], [98.0, 5.0], [99.0, 4.0]]},
            )

    def test_duplicate_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(
                UpdateKind.L2_SNAPSHOT,
                {"side": "bid", "levels": [[99.5, 3.0], [99.5, 5.0]]},
            )

    def test_descending_levels_accepted(self) -> None:
        # bids arrive best-first at some venues: descending is valid
        update = _update(
            UpdateKind.L2_SNAPSHOT,
            {"side": "bid", "levels": [[99.5, 3.0], [99.0, 5.0]]},
        )
        assert update.kind is UpdateKind.L2_SNAPSHOT

    def test_malformed_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.L2_SNAPSHOT, {"side": "bid", "levels": [["99.5"]]})

    def test_zero_price_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.L2_SNAPSHOT, {"side": "bid", "levels": [[0, 3.0]]})

    def test_empty_delta_accepted(self) -> None:
        update = _update(UpdateKind.L2_DELTA, {"side": "ask", "levels": []})
        assert update.kind is UpdateKind.L2_DELTA


class TestMetrics:
    def test_non_numeric_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.METRICS, {"funding_rate": "half a percent"})

    def test_numeric_metrics_accepted(self) -> None:
        update = _update(
            UpdateKind.METRICS,
            {"funding_rate": 0.0001, "open_interest": 1234.5},
        )
        assert update.kind is UpdateKind.METRICS


class TestStatus:
    def test_status_requires_state(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.STATUS, {})

    def test_status_rejects_payload(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.STATUS, {"extra": 1}, state=SourceState.CONNECTED)

    def test_healthy_status_accepted(self) -> None:
        update = _update(
            UpdateKind.STATUS,
            {},
            state=SourceState.STALE,
            state_note="no frames for 90s",
        )
        assert update.state is SourceState.STALE

    def test_state_fields_on_non_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _update(UpdateKind.QUOTE, _quote(), state=SourceState.CONNECTED)


class TestDefaultReceivedAt:
    def test_received_at_defaults_to_aware_now(self) -> None:
        update = _update(UpdateKind.QUOTE, _quote())
        assert update.received_at.tzinfo is not None
        assert (datetime.now(UTC) - update.received_at).total_seconds() < 60
