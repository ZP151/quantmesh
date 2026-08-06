import math
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Instrument, OrderRequest, Side


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class OrderEventType(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FILL = "fill"
    CANCELED = "canceled"


class Fill(BaseModel):
    """A venue-confirmed or simulator-generated execution event."""

    timestamp: datetime
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)


class OrderEvent(BaseModel):
    """One append-only lifecycle record; state is derived from this history."""

    sequence: int
    timestamp: datetime
    event_type: OrderEventType
    status: OrderStatus
    quantity: float | None = None
    price: float | None = None
    reason: str | None = None


class Order(BaseModel):
    """Replayable order; state fields must agree with the event history."""

    order_id: str
    instrument: Instrument
    side: Side
    quantity: float = Field(gt=0)
    order_type: OrderType
    limit_price: float | None = Field(default=None, gt=0)
    created_at: datetime
    client_order_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = Field(default=0, ge=0)
    events: list[OrderEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def filled_quantity_cannot_exceed_quantity(self) -> "Order":
        if self.filled_quantity > self.quantity and not math.isclose(
            self.filled_quantity, self.quantity
        ):
            raise ValueError(
                f"filled_quantity {self.filled_quantity} exceeds quantity {self.quantity}"
            )
        return self

    @classmethod
    def from_request(
        cls, request: OrderRequest, *, order_id: str, created_at: datetime
    ) -> "Order":
        return cls(
            order_id=order_id,
            instrument=request.instrument,
            side=request.side,
            quantity=request.quantity,
            order_type=(
                OrderType.LIMIT if request.limit_price is not None else OrderType.MARKET
            ),
            limit_price=request.limit_price,
            created_at=created_at,
            client_order_id=request.client_order_id,
        )

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)

    @property
    def average_fill_price(self) -> float | None:
        fills = [
            (event.quantity, event.price)
            for event in self.events
            if event.event_type is OrderEventType.FILL
            and event.quantity is not None
            and event.price is not None
        ]
        if not fills:
            return None
        notional = sum(quantity * price for quantity, price in fills)
        return notional / sum(quantity for quantity, _ in fills)


class OrderStateMachine:
    """Explicit order-state transitions; state is only changed through here."""

    TERMINAL_STATES = frozenset(
        {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}
    )
    TRANSITIONS: dict[OrderEventType, tuple[OrderStatus, ...]] = {
        OrderEventType.ACCEPTED: (OrderStatus.PENDING,),
        OrderEventType.REJECTED: (OrderStatus.PENDING, OrderStatus.ACCEPTED),
        OrderEventType.CANCELED: (
            OrderStatus.PENDING,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        ),
        OrderEventType.FILL: (
            OrderStatus.PENDING,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        ),
    }

    @staticmethod
    def apply(
        order: Order,
        event_type: OrderEventType,
        *,
        fill: Fill | None = None,
        reason: str | None = None,
        timestamp: datetime | None = None,
    ) -> Order:
        if order.status in OrderStateMachine.TERMINAL_STATES:
            raise ValueError(
                f"cannot apply {event_type.value!r} to terminal order in {order.status.value!r}"
            )
        if order.status not in OrderStateMachine.TRANSITIONS[event_type]:
            raise ValueError(f"{event_type.value!r} not allowed from {order.status.value!r}")

        event_time = timestamp or datetime.now(UTC)
        status = order.status

        if event_type is OrderEventType.FILL:
            if fill is None:
                raise ValueError("fill event requires a Fill payload")
            remaining = order.quantity - order.filled_quantity
            if fill.quantity > remaining and not math.isclose(fill.quantity, remaining):
                raise ValueError(
                    f"overfill: {order.filled_quantity + fill.quantity} "
                    f"exceeds order quantity {order.quantity}"
                )
            filled_quantity = order.filled_quantity + fill.quantity
            order = order.model_copy(update={"filled_quantity": filled_quantity})
            status = (
                OrderStatus.FILLED
                if math.isclose(filled_quantity, order.quantity)
                else OrderStatus.PARTIALLY_FILLED
            )
        elif event_type is OrderEventType.ACCEPTED:
            status = OrderStatus.ACCEPTED
        elif event_type is OrderEventType.REJECTED:
            status = OrderStatus.REJECTED
        elif event_type is OrderEventType.CANCELED:
            status = OrderStatus.CANCELED

        event = OrderEvent(
            sequence=len(order.events) + 1,
            timestamp=event_time,
            event_type=event_type,
            status=status,
            quantity=fill.quantity if fill is not None else None,
            price=fill.price if fill is not None else None,
            reason=reason,
        )
        return order.model_copy(update={"status": status, "events": [*order.events, event]})
