"""Shared reconciliation contract types (ADR-0006, M5 Phase B).

The finding kinds, severities, tolerances, and report/adoption shapes of
ADR-0006 are venue-neutral: the Moomoo binding (``quantmesh.moomoo.
reconciliation``) and the Hyperliquid binding (``quantmesh.hyperliquid.
reconciliation``) both classify broker snapshots against the journal with
the same vocabulary, so a report from either venue reads the same way.
The comparison and adoption *engines* stay venue-local because the wire
shapes differ (Moomoo reports explicit per-order statuses and deal rows;
Hyperliquid derives order status from its surface and reports fills with
their own identity) — the discipline, not the code, is shared.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

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
