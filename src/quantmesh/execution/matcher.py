"""Deterministic quote-based matching for the paper-trading kernel.

Fills are a pure function of (order, quote, simulation time): no randomness,
no clock reads inside the matcher. Stale or missing quote data fails closed
with a rejection instead of a phantom fill.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Quote, Side
from quantmesh.domain.orders import Fill, Order, OrderStateMachine, OrderType


class MatchResult(BaseModel):
    """Outcome of matching one order: fills, or a fail-closed rejection."""

    order_id: str
    fills: list[Fill] = []
    rejection: str | None = None

    @model_validator(mode="after")
    def fills_and_rejection_are_exclusive(self) -> "MatchResult":
        if self.fills and self.rejection is not None:
            raise ValueError("fills and rejection are mutually exclusive")
        return self


class PaperMatcher(BaseModel):
    """Matches orders against a single quote, deterministically."""

    slippage_bps: float = Field(default=5.0, ge=0)
    max_quote_age: timedelta = Field(default=timedelta(seconds=30))

    def match(
        self, order: Order, quote: Quote, *, now: datetime
    ) -> MatchResult:
        if order.status in OrderStateMachine.TERMINAL_STATES:
            raise ValueError(
                f"cannot match terminal order in {order.status.value!r}"
            )
        return self._match(order, quote, now=now, available=quote.volume)

    def match_step(
        self, orders: Sequence[Order], quote: Quote, *, now: datetime
    ) -> list[MatchResult]:
        """Match orders against one quote in submission order (time priority).

        Earlier orders consume depth first, so the fill sequence is fully
        deterministic for a given input order. Terminal orders are skipped
        silently and yield no result.
        """
        available = quote.volume
        results: list[MatchResult] = []
        for order in orders:
            if order.status in OrderStateMachine.TERMINAL_STATES:
                continue
            result = self._match(order, quote, now=now, available=available)
            results.append(result)
            if available is not None and result.fills:
                available -= sum(fill.quantity for fill in result.fills)
        return results

    def _match(
        self, order: Order, quote: Quote, *, now: datetime, available: float | None
    ) -> MatchResult:
        if quote.timestamp.tzinfo is None:
            raise ValueError("quote timestamp must be timezone-aware")
        if quote.timestamp + self.max_quote_age < now:
            return MatchResult(order_id=order.order_id, rejection="stale quote")
        touch = quote.ask if order.side is Side.BUY else quote.bid
        if touch is None:
            side = "ask" if order.side is Side.BUY else "bid"
            return MatchResult(
                order_id=order.order_id, rejection=f"missing {side} quote"
            )
        if available is None:
            return MatchResult(order_id=order.order_id, rejection="missing volume")
        if available == 0:
            return MatchResult(order_id=order.order_id, rejection="no liquidity")
        if order.order_type is OrderType.LIMIT:
            if order.limit_price is None:
                return MatchResult(
                    order_id=order.order_id, rejection="limit order without a price"
                )
            crossed = (
                touch <= order.limit_price
                if order.side is Side.BUY
                else touch >= order.limit_price
            )
            if not crossed:
                return MatchResult(order_id=order.order_id)
            price = touch
        else:
            sign = 1.0 if order.side is Side.BUY else -1.0
            factor = 1.0 + sign * self.slippage_bps / 10_000
            price = round(touch * factor, 6)

        quantity = min(order.remaining_quantity, available)
        if quantity <= 0:
            return MatchResult(order_id=order.order_id, rejection="no liquidity")
        return MatchResult(
            order_id=order.order_id,
            fills=[Fill(timestamp=now, quantity=quantity, price=price)],
        )
