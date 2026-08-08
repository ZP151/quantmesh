"""Portfolio accounting for the paper-trading kernel.

Cash, positions and P&L are a pure function of the fill history: every
application returns a new account state. Fees, spread and slippage are
explicit so costs stay visible in P&L. The account is the aggregate root
of the kernel: submission is risk-gated, then matched, then applied.
"""

import math
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Instrument, OrderRequest, Quote, Side
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
)
from quantmesh.execution.matcher import PaperMatcher

DEFAULT_FEE_BPS = 10.0


def position_key(instrument: Instrument) -> str:
    return f"{instrument.venue.value}:{instrument.symbol}"


class FeeModel(BaseModel):
    """Deterministic fee schedule applied to fill notional."""

    fee_bps: float = Field(default=DEFAULT_FEE_BPS, ge=0)
    min_fee: float = Field(default=0.0, ge=0)

    def for_notional(self, notional: float) -> float:
        fee = round(notional * self.fee_bps / 10_000, 6)
        return max(self.min_fee, fee)


class Position(BaseModel):
    """Derived quantity, average cost and realized P&L for one instrument."""

    instrument: Instrument
    quantity: float = 0
    average_cost: float = 0
    realized_pnl: float = 0


class RiskLimits(BaseModel):
    """Deterministic pre-trade limits enforced before acceptance."""

    max_order_quantity: float | None = Field(default=None, gt=0)
    max_notional: float | None = Field(default=None, gt=0)
    max_position_quantity: float | None = Field(default=None, gt=0)


class SubmissionResult(BaseModel):
    """Outcome of a risk-gated order submission."""

    order: Order
    account: "PaperAccount"
    fills: list[Fill] = []
    rejection: str | None = None
    replay_of: str | None = None


class PaperAccount(BaseModel):
    """Simulated portfolio with deterministic cash, positions and P&L."""

    cash: float = Field(ge=0)
    positions: dict[str, Position] = Field(default_factory=dict)
    orders: dict[str, Order] = Field(default_factory=dict)
    total_fees: float = 0
    total_funding: float = 0
    realized_pnl: float = 0
    order_sequence: int = Field(default=0, ge=0)
    starting_cash: float | None = None
    fee_model: FeeModel = Field(default_factory=FeeModel)
    risk_limits: RiskLimits = Field(default_factory=RiskLimits)
    matcher: PaperMatcher = Field(default_factory=PaperMatcher)
    kill_switch: bool = False

    @model_validator(mode="after")
    def capture_starting_cash(self) -> "PaperAccount":
        if self.starting_cash is None:
            self.starting_cash = self.cash
        return self

    def submit(
        self, request: OrderRequest, quote: Quote, *, now: datetime
    ) -> SubmissionResult:
        # M10 Phase B (issue #59): the idempotency key is the replay unit.
        # A keyed submission first looks for any recorded order carrying
        # the same key — the retry returns that original order with
        # `replay_of` naming it, never duplicated, never re-gated, and
        # the account state is unchanged (a rejected or accepted original
        # replays as itself, not as a re-submission), regardless of any
        # other request fields the client regenerated on retry. Detection
        # happens BEFORE the sequence is consumed and the risk gate runs.
        # Without a key, identity falls back to `client_order_id` (which
        # may itself derive from the key when it was absent: `paper-<key>`).
        key = request.idempotency_key
        if key is not None:
            for existing in self.orders.values():
                if existing.idempotency_key == key:
                    return SubmissionResult(
                        order=existing, account=self, replay_of=existing.order_id
                    )
        order_id = request.client_order_id or (
            f"paper-{key}" if key is not None else None
        )
        if order_id is not None and order_id in self.orders:
            raise ValueError(f"order id already exists: {order_id}")
        sequence = self.order_sequence + 1
        if order_id is None:
            order_id = f"paper-{sequence}"
        order = Order.from_request(request, order_id=order_id, created_at=now)

        reasons = self._risk_reasons(request, quote)
        if reasons:
            return self._reject(order, reasons, now, sequence)

        result = self.matcher.match(order, quote, now=now)
        if result.rejection is not None:
            return self._reject(order, [result.rejection], now, sequence)
        if not result.fills:
            order = OrderStateMachine.apply(order, OrderEventType.ACCEPTED, timestamp=now)
            return SubmissionResult(order=order, account=self._with_order(order, sequence))

        order = OrderStateMachine.apply(order, OrderEventType.ACCEPTED, timestamp=now)
        account = self
        for item in result.fills:
            order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=item, timestamp=now)
            account = account.apply_fill(order, item)
        return SubmissionResult(
            order=order,
            account=account._with_order(order, sequence),
            fills=result.fills,
        )

    def _risk_reasons(self, request: OrderRequest, quote: Quote) -> list[str]:
        reasons: list[str] = []
        if self.kill_switch:
            reasons.append("kill switch enabled")
        limits = self.risk_limits
        if (
            limits.max_order_quantity is not None
            and request.quantity > limits.max_order_quantity
        ):
            reasons.append(
                f"order quantity {request.quantity} exceeds limit "
                f"{limits.max_order_quantity}"
            )
        reference = request.limit_price
        if reference is None:
            reference = quote.ask if request.side is Side.BUY else quote.bid
        # Market orders estimate costs at the slippage-adjusted touch so a
        # cash or notional check cannot pass only to be overrun by slippage.
        if reference is not None and request.limit_price is None:
            sign = 1.0 if request.side is Side.BUY else -1.0
            reference = round(reference * (1.0 + sign * self.matcher.slippage_bps / 10_000), 6)
        notional = request.quantity * reference if reference is not None else None
        if (
            limits.max_notional is not None
            and notional is not None
            and notional > limits.max_notional
        ):
            reasons.append(f"notional {notional} exceeds limit {limits.max_notional}")
        key = position_key(request.instrument)
        position = self.positions.get(key)
        if request.side is Side.BUY:
            if notional is not None:
                estimated = notional + self.fee_model.for_notional(notional)
                if estimated > self.cash:
                    reasons.append(
                        f"insufficient cash {self.cash} for estimated cost {estimated}"
                    )
            if limits.max_position_quantity is not None:
                held = position.quantity if position else 0
                if held + request.quantity > limits.max_position_quantity:
                    reasons.append(
                        f"position limit: {held + request.quantity} exceeds "
                        f"{limits.max_position_quantity}"
                    )
        elif position is None or position.quantity < request.quantity:
            reasons.append(
                f"insufficient position {position.quantity if position else 0}"
            )
        return reasons

    def _reject(
        self, order: Order, reasons: list[str], now: datetime, sequence: int
    ) -> SubmissionResult:
        reason = "; ".join(reasons)
        order = OrderStateMachine.apply(
            order, OrderEventType.REJECTED, reason=reason, timestamp=now
        )
        return SubmissionResult(
            order=order, account=self._with_order(order, sequence), rejection=reason
        )

    def _with_order(self, order: Order, sequence: int) -> "PaperAccount":
        orders = dict(self.orders)
        orders[order.order_id] = order
        return self.model_copy(
            update={"orders": orders, "order_sequence": sequence}
        )

    def apply_funding(self, charges: dict[str, float]) -> "PaperAccount":
        """Apply deterministic funding payments to open positions.

        Each charge is a signed cash amount keyed by position key
        (positive = the position pays, negative = receives), applied
        against the current mark-implied notional by the caller — the
        account itself only books the cash move (the M5 FundingLedger
        precedent: funding is a fee-like journal entry). Charges for
        positions the account does not hold, non-finite charges, and
        charges that would push cash negative all fail closed.
        """
        total = 0.0
        for key, charge in charges.items():
            if key not in self.positions:
                raise ValueError(
                    f"funding charge for unknown position {key!r}; "
                    "the account cannot be charged for what it does not hold"
                )
            if not math.isfinite(charge):
                raise ValueError(f"non-finite funding charge for {key!r}")
            total += charge
        if not math.isfinite(total):
            raise ValueError("funding charges do not sum to a finite amount")
        if self.cash - total < 0:
            raise ValueError(
                f"funding payments of {total:.6f} exceed cash {self.cash:.6f}; "
                "margin beyond the cash account is out of scope for the "
                "paper kernel"
            )
        return self.model_copy(
            update={"cash": self.cash - total, "total_funding": self.total_funding + total}
        )

    def apply_fill(self, order: Order, fill: Fill) -> "PaperAccount":
        notional = fill.quantity * fill.price
        fee = self.fee_model.for_notional(notional)
        key = position_key(order.instrument)
        position = self.positions.get(key)
        closing = False

        if order.side is Side.BUY:
            cash = self.cash - notional - fee
            realized_pnl = self.realized_pnl
            if position is None:
                updated_position = Position(
                    instrument=order.instrument,
                    quantity=fill.quantity,
                    average_cost=fill.price,
                )
            else:
                quantity = position.quantity + fill.quantity
                average_cost = (
                    position.quantity * position.average_cost + notional
                ) / quantity
                updated_position = position.model_copy(
                    update={"quantity": quantity, "average_cost": average_cost}
                )
        else:
            if position is None or position.quantity < fill.quantity:
                raise ValueError(
                    f"cannot sell {fill.quantity} without a position of "
                    f"{position.quantity if position else 0}"
                )
            cash = self.cash + notional - fee
            realized = (fill.price - position.average_cost) * fill.quantity - fee
            realized_pnl = self.realized_pnl + realized
            quantity = position.quantity - fill.quantity
            closing = math.isclose(quantity, 0) or quantity < 0
            updated_position = position.model_copy(
                update={
                    "quantity": quantity,
                    "realized_pnl": position.realized_pnl + realized,
                }
            )

        positions = dict(self.positions)
        if closing:
            positions.pop(key, None)
        else:
            positions[key] = updated_position
        return self.model_copy(
            update={
                "cash": cash,
                "positions": positions,
                "total_fees": self.total_fees + fee,
                "realized_pnl": realized_pnl,
            }
        )

    def unrealized_pnl(self, mark_prices: dict[str, float]) -> float:
        return sum(
            (mark_prices[key] - position.average_cost) * position.quantity
            for key, position in self.positions.items()
            if key in mark_prices
        )

    def equity(self, mark_prices: dict[str, float]) -> float:
        return self.cash + sum(
            mark_prices[key] * position.quantity
            for key, position in self.positions.items()
            if key in mark_prices
        )

    def total_pnl(self, mark_prices: dict[str, float]) -> float:
        """Net P&L against the starting cash; fees, spread and slippage are all in."""
        starting = self.starting_cash if self.starting_cash is not None else self.cash
        return self.equity(mark_prices) - starting
