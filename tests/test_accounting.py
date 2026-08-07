from datetime import UTC, datetime

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStatus,
    OrderType,
)
from quantmesh.execution.accounting import FeeModel, PaperAccount, RiskLimits
from quantmesh.execution.matcher import PaperMatcher

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
POSITION_KEY = "internal:AAPL"
NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make_order(side: Side, quantity: float, price: float | None = None) -> Order:
    return Order(
        order_id=f"o-{side.value}",
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
        limit_price=price,
        created_at=NOW,
    )


def fill(quantity: float, price: float) -> Fill:
    return Fill(timestamp=NOW, quantity=quantity, price=price)


def account(**overrides: object) -> PaperAccount:
    values: dict[str, object] = {
        "cash": 10_000.0,
        "fee_model": FeeModel(fee_bps=10),
        "matcher": PaperMatcher(slippage_bps=0.0),
    }
    values.update(overrides)
    return PaperAccount(**values)


def test_buy_fill_debits_cash_by_notional_plus_fee() -> None:
    updated = account().apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))

    assert updated.cash == 10_000.0 - 1000.0 - 1.0
    position = updated.positions[POSITION_KEY]
    assert position.quantity == 10
    assert position.average_cost == 100.0
    assert updated.total_fees == 1.0


def test_second_buy_reweights_the_average_cost() -> None:
    updated = account()
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 110.0))

    position = updated.positions[POSITION_KEY]
    assert position.quantity == 20
    assert position.average_cost == 105.0


def test_sell_credits_cash_and_records_realized_pnl() -> None:
    updated = account()
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))
    updated = updated.apply_fill(make_order(Side.SELL, 10), fill(10, 110.0))

    assert updated.cash == 10_000.0 - 1001.0 + 1098.9
    assert POSITION_KEY not in updated.positions
    assert updated.realized_pnl == 1100.0 - 1000.0 - 1.1
    assert updated.total_fees == 1.0 + 1.1


def test_partial_sell_keeps_the_position_open() -> None:
    updated = account()
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))
    updated = updated.apply_fill(make_order(Side.SELL, 10), fill(4, 110.0))

    position = updated.positions[POSITION_KEY]
    assert position.quantity == 6
    assert position.average_cost == 100.0
    assert position.realized_pnl == 440.0 - 400.0 - 0.44


def test_unrealized_pnl_uses_the_mark_price() -> None:
    updated = account()
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))

    assert updated.unrealized_pnl({POSITION_KEY: 110.0}) == 100.0


def test_total_pnl_is_equity_based_and_net_of_all_costs() -> None:
    updated = account()
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))
    updated = updated.apply_fill(make_order(Side.SELL, 10), fill(4, 110.0))

    # Cash 9438.56 + mark of 6 shares at 95 -> equity 10008.56 vs starting 10000.
    assert updated.total_pnl({POSITION_KEY: 95.0}) == pytest.approx(8.56)


def test_buy_and_hold_pnl_shows_entry_fees() -> None:
    updated = account()
    updated = updated.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))

    assert updated.total_pnl({POSITION_KEY: 100.0}) == pytest.approx(-1.0)
    assert updated.realized_pnl == 0
    assert updated.unrealized_pnl({POSITION_KEY: 100.0}) == 0


def make_quote(
    *, bid: float | None = 99.0, ask: float | None = 100.0, volume: float | None = 100
) -> Quote:
    return Quote(
        instrument=INSTRUMENT,
        timestamp=NOW,
        bid=bid,
        ask=ask,
        volume=volume,
    )


def make_request(
    side: Side,
    quantity: float,
    limit_price: float | None = None,
    client_order_id: str | None = "cli-1",
) -> OrderRequest:
    return OrderRequest(
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        client_order_id=client_order_id,
    )


def test_kill_switch_blocks_submission() -> None:
    account_ = account(kill_switch=True)

    result = account_.submit(make_request(Side.BUY, 10), make_quote(), now=NOW)

    assert result.rejection == "kill switch enabled"
    assert result.order.status is OrderStatus.REJECTED
    assert result.fills == []
    assert result.account.cash == 10_000.0


def test_max_order_quantity_is_enforced() -> None:
    account_ = account(risk_limits=RiskLimits(max_order_quantity=10))

    result = account_.submit(make_request(Side.BUY, 15), make_quote(), now=NOW)

    assert "quantity" in result.rejection
    assert result.order.status is OrderStatus.REJECTED


def test_max_notional_is_enforced_for_limit_orders() -> None:
    account_ = account(risk_limits=RiskLimits(max_notional=50_000))

    result = account_.submit(
        make_request(Side.BUY, 1000, limit_price=100.0), make_quote(), now=NOW
    )

    assert "notional" in result.rejection


def test_buy_above_available_cash_is_rejected() -> None:
    account_ = account(cash=9_000.0)

    result = account_.submit(make_request(Side.BUY, 100), make_quote(), now=NOW)

    assert "cash" in result.rejection


def test_position_limit_is_enforced() -> None:
    account_ = account(risk_limits=RiskLimits(max_position_quantity=12))
    account_ = account_.apply_fill(make_order(Side.BUY, 10), fill(10, 100.0))

    result = account_.submit(make_request(Side.BUY, 5), make_quote(), now=NOW)

    assert "position" in result.rejection


def test_selling_without_a_position_is_rejected() -> None:
    result = account().submit(make_request(Side.SELL, 5), make_quote(), now=NOW)

    assert "position" in result.rejection


def test_submit_fills_a_market_buy_and_updates_the_account() -> None:
    account_ = account()

    result = account_.submit(make_request(Side.BUY, 10), make_quote(), now=NOW)

    assert result.rejection is None
    assert len(result.fills) == 1
    assert result.fills[0].quantity == 10
    assert result.fills[0].price == 100.0
    assert result.order.status is OrderStatus.FILLED
    assert result.order.events[-1].event_type is OrderEventType.FILL
    assert result.account.cash == 10_000.0 - 1000.0 - 1.0
    assert result.account.orders[result.order.order_id].status is OrderStatus.FILLED


def test_submit_leaves_a_non_crossed_limit_order_working() -> None:
    account_ = account()
    request = make_request(Side.BUY, 10, limit_price=99.0)

    result = account_.submit(request, make_quote(ask=100.0), now=NOW)

    assert result.rejection is None
    assert result.fills == []
    assert result.order.status is OrderStatus.ACCEPTED
    assert result.account.cash == 10_000.0


def test_submit_fails_closed_on_a_stale_quote() -> None:
    account_ = account()
    quote = make_quote()
    late = NOW.replace(hour=NOW.hour + 1)

    result = account_.submit(make_request(Side.BUY, 10), quote, now=late)

    assert result.rejection == "stale quote"
    assert result.order.status is OrderStatus.REJECTED
    assert result.account.cash == 10_000.0


def test_submit_is_deterministic_for_identical_inputs() -> None:
    quote = make_quote()
    request = make_request(Side.BUY, 10)

    first = account().submit(request, quote, now=NOW)
    second = account().submit(request, quote, now=NOW)

    assert first.model_dump() == second.model_dump()


def test_submit_rejects_a_reused_client_order_id() -> None:
    account_ = account()
    account_ = account_.submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account

    with pytest.raises(ValueError, match="order id already exists"):
        account_.submit(make_request(Side.BUY, 10), make_quote(), now=NOW)


def test_submit_is_deterministic_without_a_client_order_id() -> None:
    quote = make_quote()
    request = make_request(Side.BUY, 10, client_order_id=None)

    first = account().submit(request, quote, now=NOW)
    second = account().submit(request, quote, now=NOW)

    assert first.model_dump() == second.model_dump()
    assert first.order.order_id == "paper-1"


def test_market_buy_cannot_overdraw_cash_when_slippage_applies() -> None:
    account_ = account(
        cash=1001.0, matcher=PaperMatcher(slippage_bps=5.0)
    )

    result = account_.submit(make_request(Side.BUY, 10), make_quote(), now=NOW)

    # Estimated cost 100.05 * 10 + 1.0005 fee = 1001.5005 > 1001 cash.
    assert "cash" in result.rejection
    assert result.order.status is OrderStatus.REJECTED
