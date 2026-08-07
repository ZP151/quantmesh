"""Deterministic scenario shocks replayed through the M2 paper kernel
(M7 Phase D, issue #42).

Four shock classes, each a pure, deterministic transform of a step's
inputs:

- ``GapShock`` — scales a market's bid/ask/last by ``1 +/- gap``
  (a gap move on top of the base quote, so shocks compose with fixture
  data);
- ``FundingShock`` — charges ``marked notional x rate`` (signed;
  negative receives) through the kernel's ``PaperAccount.apply_funding``
  (the M5 FundingLedger precedent: funding is a fee-like entry);
- ``LiquidationShock`` — when marked equity falls below
  ``equity_floor x starting equity``, force-closes every position at
  the current shocked bid in one sweep; a floor the flush cannot
  restore fails closed;
- ``EventMisresolutionShock`` — event-keyed holdings (M6) mark to
  zero: the held side lost. Event sleeves are marked-only (no
  execution path exists for event contracts), so the shock acts on
  the harness's event value, never on the kernel.

``run_scenario`` replays steps in order: shocks transform the quotes,
funding is charged, step orders submit through ``PaperAccount.submit``
(risk-gated, matched, applied — the M2 kernel verbatim), event shocks
and the liquidation cascade run, and each step snapshots
cash/equity/positions/fees/funding. Everything is deterministic: no
RNG, no clock reads inside the harness.
"""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import OrderRequest, Quote, Side, Venue
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
)
from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.portfolio.exposure import PortfolioHolding, holding_key


class GapShock(BaseModel):
    """A deterministic gap move applied to a market's quote: every
    price scales by ``1 - gap`` (down) or ``1 + gap`` (up). Volume is
    untouched; a gap of 1.0 would make prices zero — refused."""

    kind: Literal["gap"] = "gap"
    venue: Venue
    symbol: str = Field(min_length=1)
    direction: Literal["up", "down"]
    gap_fraction: float = Field(gt=0, lt=1)

    def apply(self, quote: Quote) -> Quote:
        factor = 1.0 + self.gap_fraction if self.direction == "up" else 1.0 - self.gap_fraction
        return quote.model_copy(
            update={
                "bid": quote.bid * factor if quote.bid is not None else None,
                "ask": quote.ask * factor if quote.ask is not None else None,
                "last": quote.last * factor if quote.last is not None else None,
            }
        )

    @property
    def target_key(self) -> str:
        return f"{self.venue.value}:{self.symbol}"


class FundingShock(BaseModel):
    """A funding payment on one position: charge = marked notional x
    rate (signed; negative receives). Applied through the kernel."""

    kind: Literal["funding"] = "funding"
    venue: Venue
    symbol: str = Field(min_length=1)
    rate: float = Field(gt=-1, lt=1)

    @property
    def target_key(self) -> str:
        return f"{self.venue.value}:{self.symbol}"


class LiquidationShock(BaseModel):
    """A forced-close cascade: whenever marked equity drops below
    ``equity_floor x starting equity``, every position is force-closed
    at the current shocked bid in one sweep (the flush). Closing at
    the bid converts mark to cash, so the sweep can restore equity
    only when the closeable bid sits above the triggering mark; a
    floor the sweep cannot reach fails closed."""

    kind: Literal["liquidation"] = "liquidation"
    equity_floor: float = Field(ge=0, le=1)


class EventMisresolutionShock(BaseModel):
    """One M6 event resolves against the held side: every holding
    under the event key marks to zero (the event sleeve is marked-only
    — no execution path exists for event contracts)."""

    kind: Literal["event_misresolution"] = "event_misresolution"
    event_key: str = Field(min_length=1)


Shock = Annotated[
    GapShock | FundingShock | LiquidationShock | EventMisresolutionShock,
    Field(discriminator="kind"),
]


class ScenarioStep(BaseModel):
    """One replay step: shocks active at ``at``, then the step's
    orders submitted through the kernel against the shocked quotes."""

    at: datetime
    shocks: list[Shock] = Field(default_factory=list)
    orders: list[OrderRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "ScenarioStep":
        if self.at.tzinfo is None:
            raise ValueError(f"scenario step timestamp {self.at} must be timezone-aware")
        return self


def _canonical_step(step: ScenarioStep) -> dict:
    """Shocks and orders within a step sort canonically (their order
    is not setup — the replay applies shocks then orders); steps
    themselves stay in timeline order."""
    return {
        "at": step.at.isoformat(),
        "shocks": sorted(
            (item.model_dump(mode="json") for item in step.shocks),
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
        "orders": sorted(
            (
                {
                    "instrument": item.instrument.model_dump(mode="json"),
                    "side": item.side.value,
                    "quantity": item.quantity,
                    "limit_price": item.limit_price,
                    "client_order_id": item.client_order_id,
                }
                for item in step.orders
            ),
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
    }


def scenario_id(*, steps: list[ScenarioStep]) -> str:
    """Setup-only 16-hex id over the timeline: steps in order, shocks
    and orders canonical within a step."""
    canonical = json.dumps(
        {"steps": [_canonical_step(step) for step in steps]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"scenario\0{canonical}".encode()).hexdigest()[:16]


class Scenario(BaseModel):
    """A deterministic timeline of shocks and orders."""

    steps: list[ScenarioStep] = Field(min_length=1)
    id: str = Field(pattern="^[0-9a-f]{16}$")

    @model_validator(mode="after")
    def steps_advance(self) -> "Scenario":
        for previous, current in zip(self.steps, self.steps[1:]):
            if current.at <= previous.at:
                raise ValueError(
                    f"scenario steps must advance in time: {previous.at} -> {current.at}"
                )
        expected = scenario_id(steps=self.steps)
        if self.id != expected:
            raise ValueError(
                f"scenario id {self.id!r} does not match its timeline "
                f"(expected {expected!r})"
            )
        return self


def _shocked_quotes(quotes: dict[str, Quote], shocks: list[Shock]) -> dict[str, Quote]:
    shocked = dict(quotes)
    for shock in shocks:
        if isinstance(shock, GapShock):
            key = shock.target_key
            if key not in shocked:
                raise ValueError(f"gap shock targets {key!r}, which has no base quote")
            shocked[key] = shock.apply(shocked[key])
        elif isinstance(shock, FundingShock):
            key = shock.target_key
            if key not in shocked:
                raise ValueError(f"funding shock targets {key!r}, which has no base quote")
    return shocked


def _funding_charges(
    account: PaperAccount,
    shocks: list[Shock],
    quotes: dict[str, Quote],
) -> dict[str, float]:
    charges: dict[str, float] = {}
    for shock in shocks:
        if not isinstance(shock, FundingShock):
            continue
        key = shock.target_key
        if key not in account.positions:
            raise ValueError(
                f"funding shock targets {key!r}, which the account does not hold"
            )
        position = account.positions[key]
        quote = quotes[key]
        mark = (
            quote.bid
            if position.quantity < 0
            else quote.ask if quote.ask is not None else quote.bid
        )
        if mark is None:
            raise ValueError(f"funding shock needs a mark for {key!r}, got none")
        notional = position.quantity * mark
        charges[key] = round(notional * shock.rate, 6)
    return charges


def _marked_equity(
    account: PaperAccount,
    quotes: dict[str, Quote],
    event_value: float,
) -> float:
    """Marked equity; every kernel position must have a mark (a
    position without one would silently vanish from the equity line —
    fail closed instead)."""
    marks: dict[str, float] = {}
    for key, quote in quotes.items():
        reference = quote.last if quote.last is not None else quote.bid
        if reference is None:
            raise ValueError(f"no mark available for {key!r} (need last or bid)")
        marks[key] = reference
    missing = set(account.positions) - set(marks)
    if missing:
        raise ValueError(
            f"no mark for position {sorted(missing)[0]!r}; equity would be "
            "silently understated"
        )
    return account.equity(marks) + event_value


def _liquidation_cascade(
    account: PaperAccount,
    quotes: dict[str, Quote],
    shock: LiquidationShock,
    starting_equity: float,
    event_value: float,
    now: datetime,
) -> tuple[PaperAccount, int]:
    """Force-close every position at the current shocked bid in one
    sweep whenever marked equity is below the floor; the post-sweep
    equity must hold the floor (a floor the flush cannot restore fails
    closed). Returns the account and the sweep count (0 or 1)."""
    floor = shock.equity_floor * starting_equity
    if _marked_equity(account, quotes, event_value) >= floor:
        return account, 0
    for key in list(account.positions):
        quote = quotes[key]
        if quote.bid is None:
            raise ValueError(
                f"liquidation needs a bid for {key!r}, got none (cannot "
                "force-close without a price)"
            )
        position = account.positions[key]
        order = Order.from_request(
            OrderRequest(
                instrument=position.instrument,
                side=Side.SELL,
                quantity=abs(position.quantity),
                limit_price=quote.bid,
                paper=True,
                client_order_id=None,
            ),
            order_id=f"liquidation-{key}",
            created_at=now,
        )
        order = OrderStateMachine.apply(order, OrderEventType.ACCEPTED, timestamp=now)
        fill = Fill(timestamp=now, quantity=abs(position.quantity), price=quote.bid)
        order = OrderStateMachine.apply(order, OrderEventType.FILL, fill=fill, timestamp=now)
        account = account.apply_fill(order, fill)
    if _marked_equity(account, quotes, event_value) < floor:
        raise ValueError(
            f"liquidation cannot satisfy the {shock.equity_floor} equity floor: "
            "the flush converts mark to cash, so the floor must sit below "
            "the post-sweep equity"
        )
    return account, 1


class ScenarioRunWindow(BaseModel):
    """One snapshot of the replay after a step."""

    index: int = Field(ge=0)
    at: datetime
    cash: float
    equity: float
    event_value: float
    positions: dict[str, float]
    total_fees: float
    total_funding: float
    fills: int
    rejections: list[str] = Field(default_factory=list)


class ScenarioRun(BaseModel):
    """The deterministic outcome of replaying one scenario."""

    scenario_id: str
    windows: list[ScenarioRunWindow] = Field(min_length=1)
    metrics: dict[str, float]

    def final_equity(self) -> float:
        return self.windows[-1].equity


def run_scenario(
    account: PaperAccount,
    scenario: Scenario,
    *,
    quotes: dict[str, Quote],
    holdings: list[PortfolioHolding],
) -> ScenarioRun:
    """Replay the scenario through the M2 kernel.

    ``quotes`` are the base quotes keyed by ``venue:symbol`` — they
    must cover every market holding and every order's instrument, and
    be timezone-aware. Event holdings are marked-only sleeves at
    ``weight x held_probability``; an event misresolution zeroes them.
    """
    event_value = sum(
        holding.weight * holding.held_probability
        for holding in holdings
        if holding.event_key is not None
    )
    held_events = {
        holding.event_key for holding in holdings if holding.event_key is not None
    }
    for holding in holdings:
        key = holding_key(holding)
        if holding.event_key is None and key not in quotes:
            raise ValueError(
                f"market holding {key!r} has no base quote (and is not an event holding)"
            )
    for step in scenario.steps:
        for order in step.orders:
            key = position_key(order.instrument)
            if key not in quotes:
                raise ValueError(
                    f"step order for {key!r} has no base quote to match against"
                )
    starting_equity = _marked_equity(account, quotes, event_value)

    windows: list[ScenarioRunWindow] = []
    total_fills = 0
    total_liquidation_rounds = 0
    for index, step in enumerate(scenario.steps):
        shocked = _shocked_quotes(quotes, step.shocks)
        charges = _funding_charges(account, step.shocks, shocked)
        if charges:
            account = account.apply_funding(charges)
        rejections: list[str] = []
        fills = 0
        for order_request in step.orders:
            key = position_key(order_request.instrument)
            submission = account.submit(order_request, shocked[key], now=step.at)
            account = submission.account
            fills += len(submission.fills)
            if submission.rejection is not None:
                rejections.append(submission.rejection)
        total_fills += fills
        for shock in step.shocks:
            if isinstance(shock, EventMisresolutionShock):
                if shock.event_key not in held_events:
                    raise ValueError(
                        f"misresolution shock targets unknown event {shock.event_key!r}"
                    )
                for holding in holdings:
                    if holding.event_key == shock.event_key:
                        event_value -= holding.weight * holding.held_probability
                held_events.discard(shock.event_key)
            elif isinstance(shock, LiquidationShock):
                account, rounds = _liquidation_cascade(
                    account, shocked, shock, starting_equity, event_value, step.at
                )
                total_liquidation_rounds += rounds
        windows.append(
            ScenarioRunWindow(
                index=index,
                at=step.at,
                cash=account.cash,
                equity=_marked_equity(account, shocked, event_value),
                event_value=event_value,
                positions={
                    key: position.quantity
                    for key, position in sorted(account.positions.items())
                },
                total_fees=account.total_fees,
                total_funding=account.total_funding,
                fills=fills,
                rejections=rejections,
            )
        )
    peak = starting_equity
    max_drawdown = 0.0
    for window in windows:
        peak = max(peak, window.equity)
        max_drawdown = max(max_drawdown, (peak - window.equity) / starting_equity)
    return ScenarioRun(
        scenario_id=scenario.id,
        windows=windows,
        metrics={
            "n_steps": len(windows),
            "final_equity": round(windows[-1].equity, 6),
            "max_drawdown": round(max_drawdown, 6),
            "n_fills": total_fills,
            "n_rejections": sum(len(window.rejections) for window in windows),
            "n_liquidation_rounds": float(total_liquidation_rounds),
        },
    )
