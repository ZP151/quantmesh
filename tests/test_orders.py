from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Side,
    Venue,
)
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderStatus,
    OrderType,
)

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
CREATED_AT = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make_limit_order(**overrides: object) -> Order:
    values: dict[str, object] = {
        "order_id": "o-1",
        "instrument": INSTRUMENT,
        "side": Side.BUY,
        "quantity": 10,
        "order_type": OrderType.LIMIT,
        "limit_price": 100.0,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return Order(**values)


def test_new_order_starts_pending_with_no_fills() -> None:
    order = make_limit_order()

    assert order.status is OrderStatus.PENDING
    assert order.filled_quantity == 0
    assert order.events == []
    assert order.remaining_quantity == 10
    assert order.average_fill_price is None


def test_quantity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_limit_order(quantity=0)


def test_limit_price_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_limit_order(limit_price=-1.0)


def test_market_order_allows_no_limit_price() -> None:
    order = Order(
        order_id="o-2",
        instrument=INSTRUMENT,
        side=Side.SELL,
        quantity=5,
        order_type=OrderType.MARKET,
        created_at=CREATED_AT,
    )

    assert order.limit_price is None


def fill(quantity: float, price: float) -> Fill:
    return Fill(timestamp=CREATED_AT, quantity=quantity, price=price)


@pytest.mark.parametrize(
    ("start", "event", "filled_before", "fill_qty", "expected"),
    [
        # Acceptance events.
        (OrderStatus.PENDING, OrderEventType.ACCEPTED, 0, None, OrderStatus.ACCEPTED),
        (OrderStatus.PENDING, OrderEventType.REJECTED, 0, None, OrderStatus.REJECTED),
        (OrderStatus.PENDING, OrderEventType.CANCELED, 0, None, OrderStatus.CANCELED),
        # Fills from pending and working states.
        (OrderStatus.PENDING, OrderEventType.FILL, 0, 4, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.PENDING, OrderEventType.FILL, 0, 10, OrderStatus.FILLED),
        (OrderStatus.ACCEPTED, OrderEventType.FILL, 0, 4, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.ACCEPTED, OrderEventType.FILL, 0, 10, OrderStatus.FILLED),
        (
            OrderStatus.PARTIALLY_FILLED,
            OrderEventType.FILL,
            4,
            4,
            OrderStatus.PARTIALLY_FILLED,
        ),
        (OrderStatus.PARTIALLY_FILLED, OrderEventType.FILL, 4, 6, OrderStatus.FILLED),
        # Post-acceptance rejection and cancellation of the working remainder.
        (OrderStatus.ACCEPTED, OrderEventType.REJECTED, 0, None, OrderStatus.REJECTED),
        (OrderStatus.ACCEPTED, OrderEventType.CANCELED, 0, None, OrderStatus.CANCELED),
        (
            OrderStatus.PARTIALLY_FILLED,
            OrderEventType.CANCELED,
            4,
            None,
            OrderStatus.CANCELED,
        ),
    ],
)
def test_valid_transitions_follow_the_explicit_table(
    start: OrderStatus,
    event: OrderEventType,
    filled_before: float,
    fill_qty: float | None,
    expected: OrderStatus,
) -> None:
    order = make_limit_order(
        status=start, filled_quantity=filled_before, events=[]
    )
    fill_event = fill(fill_qty, 100.0) if fill_qty is not None else None

    updated = OrderStateMachine.apply(order, event, fill=fill_event)

    assert updated.status is expected


@pytest.mark.parametrize(
    "terminal",
    [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED],
)
def test_terminal_states_reject_every_event(terminal: OrderStatus) -> None:
    order = make_limit_order(status=terminal, filled_quantity=10, events=[])

    for event in OrderEventType:
        with pytest.raises(ValueError, match="terminal"):
            OrderStateMachine.apply(order, event, fill=fill(1, 100.0))


def test_accepting_an_accepted_order_is_rejected() -> None:
    order = OrderStateMachine.apply(make_limit_order(), OrderEventType.ACCEPTED)

    with pytest.raises(ValueError, match="not allowed"):
        OrderStateMachine.apply(order, OrderEventType.ACCEPTED)


def test_working_order_cannot_be_accepted_again() -> None:
    order = OrderStateMachine.apply(make_limit_order(), OrderEventType.ACCEPTED)
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(4, 100.0))

    with pytest.raises(ValueError, match="not allowed"):
        OrderStateMachine.apply(order, OrderEventType.ACCEPTED)


def test_partially_filled_order_cannot_be_rejected() -> None:
    order = OrderStateMachine.apply(make_limit_order(), OrderEventType.ACCEPTED)
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(4, 100.0))

    with pytest.raises(ValueError, match="not allowed"):
        OrderStateMachine.apply(order, OrderEventType.REJECTED)


def test_fractional_quantities_reach_filled_without_float_error() -> None:
    order = make_limit_order(quantity=0.3)
    order = OrderStateMachine.apply(order, OrderEventType.ACCEPTED)
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(0.1, 100.0))

    updated = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(0.2, 100.0))

    assert updated.status is OrderStatus.FILLED
    assert updated.remaining_quantity == 0


def test_orders_cannot_be_constructed_with_more_filled_than_quantity() -> None:
    with pytest.raises(ValidationError):
        make_limit_order(filled_quantity=11)


def test_fill_events_are_recorded_with_sequence_and_payload() -> None:
    order = OrderStateMachine.apply(make_limit_order(), OrderEventType.ACCEPTED)
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(4, 99.5))
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(6, 101.0))

    assert [event.sequence for event in order.events] == [1, 2, 3]
    fill_events = [event for event in order.events if event.event_type is OrderEventType.FILL]
    assert [(e.quantity, e.price, e.status) for e in fill_events] == [
        (4, 99.5, OrderStatus.PARTIALLY_FILLED),
        (6, 101.0, OrderStatus.FILLED),
    ]
    assert order.filled_quantity == 10
    assert order.remaining_quantity == 0
    assert order.status is OrderStatus.FILLED


def test_average_fill_price_is_weighted_by_quantity() -> None:
    order = OrderStateMachine.apply(make_limit_order(), OrderEventType.ACCEPTED)
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(5, 100.0))
    order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(5, 110.0))

    assert order.average_fill_price == 105.0


def test_overfill_is_rejected_and_order_untouched() -> None:
    order = OrderStateMachine.apply(make_limit_order(), OrderEventType.ACCEPTED)

    with pytest.raises(ValueError, match="overfill"):
        OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill(11, 100.0))

    assert order.filled_quantity == 0


def test_fill_without_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="requires a Fill"):
        OrderStateMachine.apply(make_limit_order(), OrderEventType.FILL)


def test_rejection_and_cancellation_record_the_reason() -> None:
    rejected = OrderStateMachine.apply(
        make_limit_order(), OrderEventType.REJECTED, reason="stale quote"
    )
    canceled = OrderStateMachine.apply(
        make_limit_order(), OrderEventType.CANCELED, reason="user request"
    )

    assert rejected.events[-1].reason == "stale quote"
    assert canceled.events[-1].reason == "user request"


def test_apply_returns_a_new_order_without_mutating_the_input() -> None:
    original = make_limit_order()

    updated = OrderStateMachine.apply(original, OrderEventType.ACCEPTED)

    assert original.status is OrderStatus.PENDING
    assert original.events == []
    assert updated.status is OrderStatus.ACCEPTED


def test_from_request_infers_limit_order_type() -> None:
    request = OrderRequest(
        instrument=INSTRUMENT,
        side=Side.BUY,
        quantity=10,
        limit_price=100.0,
        client_order_id="cli-1",
    )

    order = Order.from_request(request, order_id="o-1", created_at=CREATED_AT)

    assert order.order_id == "o-1"
    assert order.instrument == INSTRUMENT
    assert order.side is Side.BUY
    assert order.quantity == 10
    assert order.order_type is OrderType.LIMIT
    assert order.limit_price == 100.0
    assert order.created_at == CREATED_AT
    assert order.status is OrderStatus.PENDING
    assert order.events == []


def test_from_request_infers_market_order_type() -> None:
    request = OrderRequest(instrument=INSTRUMENT, side=Side.SELL, quantity=5)

    order = Order.from_request(request, order_id="o-2", created_at=CREATED_AT)

    assert order.order_type is OrderType.MARKET
    assert order.limit_price is None


def test_from_request_carries_the_client_order_id() -> None:
    request = OrderRequest(
        instrument=INSTRUMENT,
        side=Side.BUY,
        quantity=10,
        client_order_id="cli-7",
    )

    order = Order.from_request(request, order_id="o-9", created_at=CREATED_AT)

    assert order.client_order_id == "cli-7"
