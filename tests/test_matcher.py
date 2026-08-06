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
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderType,
)
from quantmesh.execution.matcher import MatchResult, PaperMatcher

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
QUOTE_TS = NOW


def make_quote(
    *, bid: float | None = 99.0, ask: float | None = 100.0, volume: float | None = 100
) -> Quote:
    return Quote(
        instrument=INSTRUMENT,
        timestamp=QUOTE_TS,
        bid=bid,
        ask=ask,
        volume=volume,
    )


def make_order(side: Side, quantity: float = 10, order_type: OrderType = OrderType.MARKET) -> Order:
    return Order(
        order_id=f"o-{side.value}-{quantity}-{order_type.value}",
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=None if order_type is OrderType.MARKET else 100.0,
        created_at=NOW,
    )


def matcher(**overrides: object) -> PaperMatcher:
    values: dict[str, object] = {
        "slippage_bps": 0.0,
        "max_quote_age": timedelta(seconds=30),
    }
    values.update(overrides)
    return PaperMatcher(**values)


def test_market_buy_fills_at_the_ask_with_no_slippage() -> None:
    result = matcher().match(make_order(Side.BUY), make_quote(), now=NOW)

    assert result.rejection is None
    assert len(result.fills) == 1
    assert result.fills[0].quantity == 10
    assert result.fills[0].price == 100.0


def test_market_buy_pays_slippage_above_the_ask() -> None:
    result = matcher(slippage_bps=50).match(make_order(Side.BUY), make_quote(), now=NOW)

    assert result.fills[0].price == 100.5


def test_market_sell_fills_at_the_bid_minus_slippage() -> None:
    result = matcher(slippage_bps=50).match(make_order(Side.SELL), make_quote(), now=NOW)

    assert result.fills[0].price == 98.505


def test_market_order_without_a_touch_fails_closed() -> None:
    quote = make_quote(ask=None)

    result = matcher().match(make_order(Side.BUY), quote, now=NOW)

    assert result.fills == []
    assert "missing" in result.rejection


def test_stale_quote_fails_closed_for_market_orders() -> None:
    quote = make_quote()
    late = QUOTE_TS + timedelta(seconds=31)

    result = matcher().match(make_order(Side.BUY), quote, now=late)

    assert result.fills == []
    assert "stale" in result.rejection


def test_market_order_with_zero_volume_fails_closed() -> None:
    result = matcher().match(make_order(Side.BUY), make_quote(volume=0), now=NOW)

    assert result.fills == []
    assert "liquidity" in result.rejection


def test_terminated_order_is_rejected_by_the_matcher() -> None:
    order = OrderStateMachine.apply(make_order(Side.BUY), OrderEventType.CANCELED)

    with pytest.raises(ValueError, match="terminal"):
        matcher().match(order, make_quote(), now=NOW)


def test_limit_buy_fills_at_the_ask_when_crossed() -> None:
    order = make_order(Side.BUY, order_type=OrderType.LIMIT)
    result = matcher(slippage_bps=50).match(order, make_quote(), now=NOW)

    assert result.rejection is None
    assert result.fills[0].quantity == 10
    assert result.fills[0].price == 100.0  # touch, not slippage-adjusted


def test_limit_buy_does_not_fill_above_the_limit() -> None:
    order = make_order(Side.BUY, order_type=OrderType.LIMIT)
    result = matcher().match(order, make_quote(ask=100.5), now=NOW)

    assert result.fills == []
    assert result.rejection is None  # still working, not failed closed


def test_limit_buy_does_not_fill_without_an_ask() -> None:
    order = make_order(Side.BUY, order_type=OrderType.LIMIT)
    result = matcher().match(order, make_quote(ask=None), now=NOW)

    assert result.fills == []
    assert "missing" in result.rejection


def test_limit_sell_fills_at_the_bid_when_crossed() -> None:
    order = make_order(Side.SELL, order_type=OrderType.LIMIT)
    result = matcher().match(order, make_quote(bid=101.0), now=NOW)

    assert result.fills[0].price == 101.0


def test_limit_sell_does_not_fill_below_the_limit() -> None:
    order = make_order(Side.SELL, order_type=OrderType.LIMIT)
    result = matcher().match(order, make_quote(bid=99.0), now=NOW)

    assert result.fills == []
    assert result.rejection is None


def test_limit_order_against_stale_quote_fails_closed() -> None:
    result = matcher().match(
        make_order(Side.BUY, order_type=OrderType.LIMIT),
        make_quote(),
        now=QUOTE_TS + timedelta(seconds=31),
    )

    assert result.fills == []
    assert "stale" in result.rejection


def test_market_order_partially_fills_when_depth_is_limited() -> None:
    result = matcher().match(make_order(Side.BUY, quantity=10), make_quote(volume=4), now=NOW)

    assert result.rejection is None
    assert len(result.fills) == 1
    assert result.fills[0].quantity == 4


def test_missing_volume_fails_closed_for_market_orders() -> None:
    result = matcher().match(make_order(Side.BUY), make_quote(volume=None), now=NOW)

    assert result.fills == []
    assert "volume" in result.rejection


def test_missing_volume_fails_closed_for_limit_orders() -> None:
    order = make_order(Side.BUY, order_type=OrderType.LIMIT)
    result = matcher().match(order, make_quote(volume=None), now=NOW)

    assert result.fills == []
    assert "volume" in result.rejection


def test_limit_order_partially_fills_when_depth_is_limited() -> None:
    order = make_order(Side.BUY, order_type=OrderType.LIMIT, quantity=10)
    result = matcher().match(order, make_quote(volume=3), now=NOW)

    assert result.fills[0].quantity == 3


def test_partially_filled_order_matches_only_the_remainder() -> None:
    order = make_order(Side.BUY, quantity=10)
    order = OrderStateMachine.apply(order, OrderEventType.ACCEPTED)
    order = OrderStateMachine.apply(
        order, OrderEventType.FILL, fill=Fill(timestamp=NOW, quantity=4, price=100.0)
    )

    result = matcher().match(order, make_quote(volume=10), now=NOW)

    assert result.fills[0].quantity == 6


def test_naive_quote_timestamp_raises_a_clear_error() -> None:
    quote = Quote(
        instrument=INSTRUMENT,
        timestamp=datetime(2026, 8, 7, 12, 0, 0),
        bid=99.0,
        ask=100.0,
        volume=100,
    )

    with pytest.raises(ValueError, match="timezone"):
        matcher().match(make_order(Side.BUY), quote, now=NOW)


def test_match_result_cannot_combine_fills_and_rejection() -> None:
    with pytest.raises(ValidationError):
        MatchResult(
            order_id="o-1",
            fills=[Fill(timestamp=NOW, quantity=1, price=100.0)],
            rejection="stale quote",
        )


def test_match_step_gives_time_priority_in_submission_order() -> None:
    first = make_order(Side.BUY, quantity=6)
    second = make_order(Side.BUY, quantity=6)

    results = matcher().match_step([first, second], make_quote(volume=10), now=NOW)

    assert [r.fills[0].quantity for r in results] == [6, 4]


def test_match_step_skips_terminal_orders() -> None:
    canceled = OrderStateMachine.apply(make_order(Side.BUY), OrderEventType.CANCELED)
    working = make_order(Side.BUY, quantity=2)

    results = matcher().match_step([canceled, working], make_quote(volume=10), now=NOW)

    assert len(results) == 1
    assert results[0].fills[0].quantity == 2


def test_match_is_deterministic_across_repeated_calls() -> None:
    quote = make_quote()
    order = make_order(Side.BUY)

    first = matcher(slippage_bps=37).match(order, quote, now=NOW)
    second = matcher(slippage_bps=37).match(order, quote, now=NOW)

    assert first.model_dump() == second.model_dump()
