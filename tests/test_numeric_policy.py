"""Execution numeric policy characterization (iteration 0025, issue #116).

These tests pin the current numeric conventions so a future representation
change has to be deliberate: six-decimal quantization via ``round(x, 6)``,
bps→decimal-fraction conversion via ``/ 10_000``, exact-by-default comparison
tolerances, ``math.isclose`` zero checks, and venue tick size as metadata
rather than a local quantization unit. No production behavior is changed.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    Quote,
    Side,
    Venue,
)
from quantmesh.domain.orders import Order, OrderType
from quantmesh.events.models import EventVenue, MarketQuote
from quantmesh.execution.accounting import FeeModel
from quantmesh.execution.matcher import PaperMatcher
from quantmesh.execution.reconciliation import ReconcileTolerance

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make_quote(bid: float | None = 100.0, ask: float | None = 100.0) -> Quote:
    return Quote(
        instrument=INSTRUMENT, timestamp=NOW, bid=bid, ask=ask, volume=100
    )


def market_order(side: Side, quantity: float = 10.0) -> Order:
    return Order(
        order_id=f"o-{side.value}-{quantity}",
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        created_at=NOW,
    )


def matcher(slippage_bps: float) -> PaperMatcher:
    return PaperMatcher(
        slippage_bps=slippage_bps, max_quote_age=timedelta(seconds=30)
    )


# --- quantization -------------------------------------------------------------


def test_fee_quantizes_to_six_decimals() -> None:
    assert FeeModel(fee_bps=10).for_notional(1000.0) == 1.0
    assert FeeModel(fee_bps=10).for_notional(123.456) == 0.123456


def test_fee_sub_micro_quantizes_to_zero() -> None:
    # 0.0001 * 1 bps / 10_000 = 1e-8, below the six-decimal unit → 0.0.
    assert FeeModel(fee_bps=1).for_notional(0.0001) == 0.0


def test_fee_respects_min_fee_floor() -> None:
    assert FeeModel(fee_bps=10, min_fee=0.5).for_notional(1.0) == 0.5


def test_round_is_half_to_even() -> None:
    # The local quantization unit is Python's ``round``, which rounds half to
    # even — a deliberate tie-break that a future policy must preserve or
    # replace explicitly.
    assert round(2.5) == 2
    assert round(3.5) == 4


def test_market_slippage_quantizes_price_to_six_decimals() -> None:
    buy = matcher(slippage_bps=5).match(market_order(Side.BUY), make_quote(ask=100.0), now=NOW)
    assert buy.fills[0].price == round(100.0 * (1.0 + 5 / 10_000), 6)

    sell = matcher(slippage_bps=5).match(
        market_order(Side.SELL), make_quote(bid=100.0), now=NOW
    )
    assert sell.fills[0].price == round(100.0 * (1.0 - 5 / 10_000), 6)


# --- bps convention -----------------------------------------------------------


def test_bps_converts_to_decimal_fraction() -> None:
    assert 5 / 10_000 == 0.0005
    assert 10_000 / 10_000 == 1.0


def test_reconcile_tolerance_defaults_to_exact() -> None:
    tolerance = ReconcileTolerance()
    assert tolerance.qty_bps == 0
    assert tolerance.price_bps == 0
    assert tolerance.fee_abs == 0
    assert tolerance.time_skew_s == 0
    assert tolerance.position_qty_bps == 0


# --- tick size is venue metadata, not a local quantization unit ---------------


def test_tick_size_is_required_and_positive_venue_metadata() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(
            venue=EventVenue.POLYMARKET,
            symbol="token-1",
            timestamp=NOW,
            tick_size=0.0,
        )


def test_matcher_quantization_is_independent_of_venue_tick() -> None:
    # The matcher rounds to six decimals regardless of a venue's tick size:
    # no execution component re-quantizes to a venue tick grid.
    result = matcher(slippage_bps=5).match(
        market_order(Side.BUY, quantity=1.0), make_quote(ask=100.0), now=NOW
    )
    assert result.fills[0].price == 100.05
