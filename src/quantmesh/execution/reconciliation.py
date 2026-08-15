"""Shared reconciliation contract and engine (ADR-0006, M5 Phase B).

The finding kinds, severities, tolerances, report/adoption shapes and the
numeric comparison engine of ADR-0006 are venue-neutral: the Moomoo binding
(``quantmesh.moomoo.reconciliation``) and the Hyperliquid binding
(``quantmesh.hyperliquid.reconciliation``) both classify broker snapshots
against the journal with the same vocabulary and the same comparison math, so
a report from either venue reads the same way. Venue-specific wire shapes and
status mapping (Moomoo's explicit per-order statuses and deal rows;
Hyperliquid's derived surface status and fill identity) stay in each adapter,
which populate the shared engine's views.
"""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from quantmesh.domain.models import Side, Venue
from quantmesh.domain.orders import Order, OrderStateMachine, OrderStatus


class FindingKind(StrEnum):
    MAPPING = "mapping"
    QUANTITY = "quantity"
    PRICE = "price"
    FEE = "fee"
    STATUS = "status"
    TIMESTAMP = "timestamp"
    POSITION = "position"
    REVOKED_FILL = "revoked_fill"
    MISSING_DATA = "missing_data"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ReconcileTolerance(BaseModel):
    """Declared tolerances for one reconciliation run (ADR-0006 d. 3).

    Defaults are exact — the simulated/testnet environments are
    deterministic, so any tolerance is an explicit operator decision.
    """

    qty_bps: float = Field(default=0, ge=0)
    price_bps: float = Field(default=0, ge=0)
    fee_abs: float = Field(default=0, ge=0)
    time_skew_s: float = Field(default=0, ge=0)
    position_qty_bps: float = Field(default=0, ge=0)


class ReconciliationFinding(BaseModel):
    """One typed violation or refusal-relevant note (ADR-0006 d. 3)."""

    kind: FindingKind
    severity: Severity
    message: str
    order_id: str | None = None
    observed: str | None = None
    expected: str | None = None


class OrderOutcome(BaseModel):
    """One broker order's classification against the journal."""

    broker_order_id: str | None = None
    internal_order_id: str | None = None
    status: str  # matched | pending | missing | divergent
    findings: list[ReconciliationFinding] = Field(default_factory=list)
    # The field keeps ADR-0006's original name even though the
    # Hyperliquid binding recovers mappings via the cloid channel
    # (client_order_id): it is the same semantic — the client-order-id
    # echo the venue kept.
    recovered_via_remark: bool = False


class ReconciliationReport(BaseModel):
    """Deterministic result of one run: outcomes plus typed findings."""

    tolerance: ReconcileTolerance
    outcomes: list[OrderOutcome] = Field(default_factory=list)
    missing_internal: list[str] = Field(default_factory=list)
    position_findings: list[ReconciliationFinding] = Field(default_factory=list)

    @property
    def findings(self) -> list[ReconciliationFinding]:
        order_findings = [
            finding
            for outcome in self.outcomes
            for finding in outcome.findings
        ]
        return order_findings + self.position_findings

    @property
    def counts(self) -> dict[str, int]:
        counts = {"matched": 0, "pending": 0, "missing": 0, "divergent": 0}
        for outcome in self.outcomes:
            counts[outcome.status] += 1
        counts["missing"] += len(self.missing_internal)
        return counts


class AdoptionResult(BaseModel):
    """What a reconciliation apply imported, and what it refused."""

    updated: dict[str, Order] = Field(default_factory=dict)
    refused: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- shared engine helpers ----------------------------------------------------


def finding(
    kind: FindingKind,
    severity: Severity,
    message: str,
    *,
    order_id: str | None = None,
    observed: str | None = None,
    expected: str | None = None,
) -> ReconciliationFinding:
    """Build one typed violation or refusal-relevant note (ADR-0006 d. 3)."""
    return ReconciliationFinding(
        kind=kind,
        severity=severity,
        message=message,
        order_id=order_id,
        observed=observed,
        expected=expected,
    )


def dedupe_by_id(items: list, key) -> list:
    """De-duplicate a list by ``key``, keeping the last occurrence."""
    seen: dict = {}
    for item in items:
        seen[key(item)] = item
    return list(seen.values())


def is_terminal(status: OrderStatus) -> bool:
    """True when the journal status is terminal (ADR-0006 progress rule)."""
    return status in OrderStateMachine.TERMINAL_STATES


def compare_positions(
    *,
    broker_by_symbol: dict[str, float],
    internal: list[Order],
    venue: Venue,
    noun: str,
    tolerance: ReconcileTolerance,
) -> list[ReconciliationFinding]:
    """Account-level position deltas per symbol (ADR-0006 d. 3).

    The venue provides its net position per symbol (signed); the journal's net
    is filled quantity signed by side, filtered to ``venue``. The ``noun``
    ("broker" / "venue") is the only wording difference between bindings.
    """
    pos_tol = tolerance.position_qty_bps / 10_000.0
    findings: list[ReconciliationFinding] = []
    internal_by_symbol: dict[str, float] = {}
    for order in internal:
        if order.instrument.venue is not venue:
            continue
        sign = 1.0 if order.side is Side.BUY else -1.0
        total = sum(fill.quantity for fill in order.fills)
        internal_by_symbol[order.instrument.symbol] = (
            internal_by_symbol.get(order.instrument.symbol, 0.0) + sign * total
        )
    for symbol in sorted(set(broker_by_symbol) | set(internal_by_symbol)):
        broker_qty = broker_by_symbol.get(symbol, 0.0)
        internal_qty = internal_by_symbol.get(symbol, 0.0)
        if broker_qty == 0.0 and internal_qty == 0.0:
            continue
        if broker_qty == 0.0:
            findings.append(
                finding(
                    FindingKind.POSITION,
                    Severity.ERROR,
                    f"journal net position {internal_qty:g} for {symbol} has no "
                    f"{noun} position",
                    observed=f"{internal_qty:g}",
                    expected="0",
                )
            )
            continue
        if internal_qty == 0.0:
            findings.append(
                finding(
                    FindingKind.POSITION,
                    Severity.ERROR,
                    f"{noun} position {broker_qty:g} for {symbol} is unexplained by "
                    "the journal",
                    observed=f"{broker_qty:g}",
                    expected="0",
                )
            )
            continue
        delta = abs(broker_qty - internal_qty) / max(1.0, abs(internal_qty))
        if delta > pos_tol:
            findings.append(
                finding(
                    FindingKind.POSITION,
                    Severity.ERROR,
                    f"position drift for {symbol}: {noun} {broker_qty:g} vs journal "
                    f"{internal_qty:g}",
                    observed=f"{broker_qty:g}",
                    expected=f"{internal_qty:g}",
                )
            )
    return findings


def compare_quantities(
    *,
    broker_qty: float | None,
    broker_filled_qty: float,
    order: Order,
    tolerance: ReconcileTolerance,
    noun: str,
    fmt: Callable[[float], str] = lambda value: f"{value}",
) -> list[ReconciliationFinding]:
    """Order-quantity and fill-side quantity drift (ADR-0006 d. 3).

    ``broker_qty`` is None when the venue does not declare the original order
    size (Hyperliquid's inactive rows); the fill-side compare still runs.
    """
    findings: list[ReconciliationFinding] = []
    qty_tol = tolerance.qty_bps / 10_000.0
    if broker_qty is not None:
        diff = broker_qty - order.quantity
        if abs(diff) / order.quantity > qty_tol:
            findings.append(
                finding(
                    FindingKind.QUANTITY,
                    Severity.ERROR,
                    f"order quantity drift: {noun} {fmt(broker_qty)} vs journal "
                    f"{fmt(order.quantity)}",
                    order_id=order.order_id,
                    observed=fmt(broker_qty),
                    expected=fmt(order.quantity),
                )
            )
    fill_diff = broker_filled_qty - order.filled_quantity
    if fill_diff < -qty_tol * order.quantity:
        findings.append(
            finding(
                FindingKind.QUANTITY,
                Severity.ERROR,
                f"journal shows more fills than the {noun}: {noun} "
                f"{fmt(broker_filled_qty)} vs journal {fmt(order.filled_quantity)}",
                order_id=order.order_id,
                observed=fmt(broker_filled_qty),
                expected=fmt(order.filled_quantity),
            )
        )
    return findings


def compare_prices(
    *,
    broker_limit_price: float | None,
    broker_average_price: float | None,
    order: Order,
    tolerance: ReconcileTolerance,
    noun: str,
) -> list[ReconciliationFinding]:
    """Limit-price and execution-price drift (ADR-0006 d. 3)."""
    findings: list[ReconciliationFinding] = []
    price_tol = tolerance.price_bps / 10_000.0
    if order.limit_price is not None and broker_limit_price is not None:
        if abs(broker_limit_price - order.limit_price) / order.limit_price > price_tol:
            findings.append(
                finding(
                    FindingKind.PRICE,
                    Severity.ERROR,
                    f"limit price drift: {noun} {broker_limit_price} vs journal "
                    f"{order.limit_price}",
                    order_id=order.order_id,
                    observed=f"{broker_limit_price}",
                    expected=f"{order.limit_price}",
                )
            )
    if broker_average_price is not None and order.average_fill_price is not None:
        drift = abs(broker_average_price - order.average_fill_price)
        if drift / order.average_fill_price > price_tol:
            findings.append(
                finding(
                    FindingKind.PRICE,
                    Severity.ERROR,
                    f"execution price drift: {noun} avg {broker_average_price} vs "
                    f"journal avg {order.average_fill_price}",
                    order_id=order.order_id,
                    observed=f"{broker_average_price}",
                    expected=f"{order.average_fill_price}",
                )
            )
    return findings
