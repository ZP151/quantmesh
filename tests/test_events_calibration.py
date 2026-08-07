"""Pure calibration transforms (issue #36, Phase C).

Every formula in ``events.calibration`` is a pure function of its
quote/series inputs and fails closed — these tests pin the documented
arithmetic (fee-aware mid, liquidity confidence, history fallback) and
the Brier reliability-curve data.
"""

from datetime import UTC, datetime

import pytest

from quantmesh.events.calibration import (
    _FALLBACK_THRESHOLD,
    _SPREAD_FLOOR,
    _TIGHT_SPREAD_TICKS,
    _WIDE_SPREAD_TICKS,
    brier,
    brier_by_bin,
    brier_score,
    fee_adjusted_mid,
    history_signal,
    implied_probability,
    liquidity_confidence,
    liquidity_weighted_brier,
    with_history_fallback,
)
from quantmesh.events.models import EventVenue, MarketQuote

_TS = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _quote(
    *,
    bid: float | None = 0.49,
    ask: float | None = 0.51,
    last: float | None = None,
    bid_depth: float = 1000.0,
    ask_depth: float = 1000.0,
    tick_size: float = 0.01,
    fee_bps: float = 0.0,
    venue: EventVenue = EventVenue.KALSHI,
) -> MarketQuote:
    return MarketQuote(
        venue=venue,
        symbol=f"test-{bid}-{ask}",
        timestamp=_TS,
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        tick_size=tick_size,
        taker_fee_bps=fee_bps,
    )


class TestFeeAdjustedMid:
    def test_mid_shift_by_fee_times_half_spread(self):
        # Break-even center: buyer pays a(1+f), seller nets b(1-f); the
        # midpoint of that interval is mid + f*(a-b)/2 = mid + fee*half_spread.
        quote = _quote(bid=0.49, ask=0.51, fee_bps=1000)
        assert fee_adjusted_mid(quote) == pytest.approx(0.501)
        estimate = implied_probability(quote)
        assert estimate.spread_adjustment == pytest.approx(0.001)
        assert estimate.probability == pytest.approx(0.501)
        assert estimate.basis == "mid"

    def test_kalshi_zero_fee_is_zero_adjustment(self):
        quote = _quote(bid=0.49, ask=0.51, fee_bps=0)
        assert fee_adjusted_mid(quote) == pytest.approx(0.5)
        assert implied_probability(quote).spread_adjustment == 0.0

    def test_one_sided_quote_uses_last_trade_without_adjustment(self):
        quote = _quote(bid=None, ask=None, last=0.6)
        assert fee_adjusted_mid(quote) == pytest.approx(0.6)
        estimate = implied_probability(quote)
        assert estimate.basis == "last"
        assert estimate.spread_adjustment == 0.0

    def test_no_price_surface_fails_closed(self):
        quote = _quote(bid=None, ask=None, last=None)
        with pytest.raises(ValueError, match="no price surface"):
            fee_adjusted_mid(quote)
        with pytest.raises(ValueError, match="no price surface"):
            implied_probability(quote)


class TestLiquidityConfidence:
    def test_tight_spread_saturated_depth_is_full_confidence(self):
        quote = _quote(bid=0.49, ask=0.51, bid_depth=2000, ask_depth=2000)
        assert liquidity_confidence(quote) == 1.0

    def test_depth_halved_halves_the_score(self):
        quote = _quote(bid=0.49, ask=0.51, bid_depth=500, ask_depth=500)
        assert liquidity_confidence(quote) == pytest.approx(0.5)

    def test_wide_spread_floors_at_floor(self):
        # 10 ticks of spread is the documented floor.
        quote = _quote(bid=0.45, ask=0.55, tick_size=0.01)
        ticks = (quote.best_ask - quote.best_bid) / quote.tick_size
        assert ticks == pytest.approx(_WIDE_SPREAD_TICKS)
        assert liquidity_confidence(quote) == pytest.approx(_SPREAD_FLOOR)

    def test_two_ticks_still_counts_tight(self):
        quote = _quote(bid=0.48, ask=0.52, tick_size=0.02)
        ticks = (quote.best_ask - quote.best_bid) / quote.tick_size
        assert ticks == pytest.approx(_TIGHT_SPREAD_TICKS)
        assert liquidity_confidence(quote) == pytest.approx(1.0)

    def test_one_sided_book_is_halved(self):
        quote = _quote(bid=None, ask=None, last=0.5, bid_depth=2000, ask_depth=0)
        # Depth score 1.0, spread score 0.5 (one side unobserved).
        assert liquidity_confidence(quote) == pytest.approx(0.5)

    def test_confidence_rounds_to_four_decimals(self):
        quote = _quote(bid=0.49, ask=0.51, bid_depth=333, ask_depth=333)
        assert len(str(liquidity_confidence(quote)).split(".")[1]) <= 4


class TestHistorySignal:
    def test_mean_and_volatility(self):
        mean, vol = history_signal([0.4, 0.5, 0.6])
        assert mean == pytest.approx(0.5)
        assert vol == pytest.approx(0.08165, abs=1e-5)

    def test_empty_fails_closed(self):
        with pytest.raises(ValueError, match="at least one"):
            history_signal([])

    def test_out_of_range_price_fails_closed(self):
        with pytest.raises(ValueError, match="not a probability"):
            history_signal([0.5, 1.5])

    def test_non_finite_price_fails_closed(self):
        with pytest.raises(ValueError, match="not a probability"):
            history_signal([0.5, float("nan")])


class TestHistoryFallback:
    def test_thin_book_blends_quote_toward_history_mean(self):
        # Depth score 0.1, tight spread -> confidence 0.1 < threshold.
        quote = _quote(bid=0.49, ask=0.51, bid_depth=100, ask_depth=100)
        assert implied_probability(quote).liquidity_confidence == pytest.approx(0.1)
        estimate = with_history_fallback(quote, [0.0, 1.0])
        assert estimate.probability == pytest.approx(0.1 * 0.5 + 0.9 * 0.5)
        assert estimate.basis.startswith("mid+history")

    def test_liquid_book_is_not_diluted(self):
        quote = _quote(bid=0.49, ask=0.51, bid_depth=2000, ask_depth=2000)
        assert liquidity_confidence(quote) >= _FALLBACK_THRESHOLD
        estimate = with_history_fallback(quote, [0.0, 1.0])
        assert estimate.probability == pytest.approx(0.5)
        assert estimate.basis == "mid"

    def test_series_volatility_is_surfaced_in_the_basis(self):
        quote = _quote(bid=0.49, ask=0.51, bid_depth=100, ask_depth=100)
        estimate = with_history_fallback(quote, [0.5, 0.5])
        assert "vol=0.0000" in estimate.basis


class TestBrier:
    def test_single_pair(self):
        assert brier(0.5, 1) == pytest.approx(0.25)
        assert brier(0.0, 0) == pytest.approx(0.0)

    def test_mean_over_pairs(self):
        assert brier_score([0.0, 1.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_length_mismatch_fails_closed(self):
        with pytest.raises(ValueError, match="vs"):
            brier_score([0.5], [0.0, 1.0])

    def test_out_of_range_prediction_fails_closed(self):
        with pytest.raises(ValueError, match="not a probability"):
            brier_score([1.5], [0.0])

    def test_non_binary_outcome_fails_closed(self):
        with pytest.raises(ValueError, match="not 0 or 1"):
            brier_score([0.5], [0.5])

    def test_empty_series_fails_closed(self):
        with pytest.raises(ValueError, match="at least one"):
            brier_score([], [])


class TestBrierByBin:
    def test_bins_partition_predictions(self):
        bins = brier_by_bin([0.05, 0.95, 1.0], [0.0, 1.0, 1.0], n_bins=10)
        assert [b.count for b in bins] == [1, 0, 0, 0, 0, 0, 0, 0, 0, 2]
        assert bins[0].mean_prediction == pytest.approx(0.05)
        assert bins[0].observed_frequency == pytest.approx(0.0)
        assert bins[9].mean_prediction == pytest.approx(0.975)
        assert bins[9].observed_frequency == pytest.approx(1.0)

    def test_upper_bound_lands_in_last_bin(self):
        bins = brier_by_bin([1.0], [1.0], n_bins=10)
        assert bins[9].count == 1
        assert bins[9].lo == pytest.approx(0.9)

    def test_empty_bins_stay_none(self):
        bins = brier_by_bin([0.5], [1.0], n_bins=10)
        assert bins[3].count == 0
        assert bins[3].mean_prediction is None
        assert bins[3].observed_frequency is None
        assert bins[3].brier is None

    def test_bin_boundary_is_half_open(self):
        bins = brier_by_bin([0.2, 0.19999], [1.0, 0.0], n_bins=10)
        assert bins[2].count == 1
        assert bins[2].mean_prediction == pytest.approx(0.2)
        assert bins[1].count == 1

    def test_non_positive_bins_fails_closed(self):
        with pytest.raises(ValueError, match="n_bins"):
            brier_by_bin([0.5], [1.0], n_bins=0)


class TestLiquidityWeightedBrier:
    def test_weighted_mean(self):
        score = liquidity_weighted_brier([0.0, 1.0], [1.0, 0.0], [1.0, 0.5])
        # (1*1 + 0.5*1) / 1.5
        assert score == pytest.approx(1.0)

    def test_zero_total_weight_fails_closed(self):
        with pytest.raises(ValueError, match="sum to zero"):
            liquidity_weighted_brier([0.0, 1.0], [1.0, 0.0], [0.0, 0.0])

    def test_confidence_length_mismatch_fails_closed(self):
        with pytest.raises(ValueError, match="confidences"):
            liquidity_weighted_brier([0.5], [1.0], [0.5, 0.5])

    def test_out_of_range_confidence_fails_closed(self):
        with pytest.raises(ValueError, match="confidence"):
            liquidity_weighted_brier([0.5], [1.0], [1.1])
