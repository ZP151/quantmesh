"""Reliability and drawdown limits over recorded metrics, with breach
alerts through the M7 AlertLedger (M10 Phase A, issue #58).

The limits are a small, pinned contract (``ReliabilityLimits``); the
evaluation is pure and deterministic over a window of metric samples
(the equity gauge series for drawdown, the
``consecutive_reconciliation_mismatches`` gauge for reconciliation
health). Every breach emits one ``AlertRecord`` on the M7 ledger with
source ``ops:limits`` — the M9 risk screen renders it with no further
work, and the ledger's duplicate refusal makes an identical
re-detection a no-op (same ``detected_at``), never a repeat.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from quantmesh.ops.metrics import Metric
from quantmesh.research.drift import AlertLedger, AlertRecord, alert_id

EQUITY_METRIC = "equity"  # gauge, unit "usd" — the paper equity series
MISMATCH_METRIC = "consecutive_reconciliation_mismatches"  # gauge, unit "count"


class ReliabilityLimits(BaseModel):
    """The defined reliability/drawdown limits over paper operation."""

    max_drawdown_fraction: float = Field(default=0.25, gt=0, lt=1)
    max_consecutive_mismatches: int = Field(default=5, ge=0)


@dataclass(frozen=True)
class LimitBreach:
    """One measured limit crossing, ready to render into an alert."""

    limit: str
    measured: float
    limit_value: float
    measured_at: datetime


def _drawdown_fraction(equity: list[float]) -> float:
    """Max peak-to-trough drawdown over the series: the deepest trough
    relative to the running peak. Empty or single-sample series have
    no drawdown."""
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak
            worst = max(worst, drawdown)
    return worst


def evaluate_limits(
    metrics: Sequence[Metric],
    limits: ReliabilityLimits,
    *,
    since: datetime | None = None,
) -> list[LimitBreach]:
    """Evaluate the limits over the recorded window, oldest first.

    Drawdown uses every equity sample in the window; the reconciliation
    limit is crossed when any mismatch sample in the window is at or
    above the limit. Breaches are deterministic: sorted by measured_at
    then by limit name.
    """
    window = [
        metric
        for metric in metrics
        if since is None or metric.measured_at >= since
    ]
    window.sort(key=lambda metric: (metric.measured_at, metric.name))
    equity = [metric.value for metric in window if metric.name == EQUITY_METRIC]
    mismatches = [
        metric.value for metric in window if metric.name == MISMATCH_METRIC
    ]
    breaches: list[LimitBreach] = []
    if equity:
        drawdown = _drawdown_fraction(equity)
        if drawdown >= limits.max_drawdown_fraction:
            breaches.append(
                LimitBreach(
                    limit="max_drawdown_fraction",
                    measured=drawdown,
                    limit_value=limits.max_drawdown_fraction,
                    measured_at=window[-1].measured_at,
                )
            )
    if mismatches and max(mismatches) >= limits.max_consecutive_mismatches:
        worst = max(mismatches)
        at = next(
            metric.measured_at
            for metric in reversed(window)
            if metric.name == MISMATCH_METRIC and metric.value == worst
        )
        breaches.append(
            LimitBreach(
                limit="max_consecutive_mismatches",
                measured=worst,
                limit_value=limits.max_consecutive_mismatches,
                measured_at=at,
            )
        )
    return breaches


def record_breach_alerts(
    ledger: AlertLedger,
    breaches: Sequence[LimitBreach],
    *,
    now: datetime | None = None,
) -> list[AlertRecord]:
    """Persist every breach as an ``ops:limits`` alert (kind
    ``reliability_limit``); the ledger refuses an identical
    re-detection."""
    detected_at = (now if now is not None else datetime.now(UTC)).astimezone(UTC)
    recorded: list[AlertRecord] = []
    for breach in breaches:
        record = AlertRecord(
            id=alert_id(
                kind="reliability_limit",
                source="ops:limits",
                detected_at=detected_at,
                observed={
                    "limit": breach.limit,
                    "measured": breach.measured,
                    "limit_value": breach.limit_value,
                },
            ),
            kind="reliability_limit",
            source="ops:limits",
            detected_at=detected_at,
            message=(
                f"limit {breach.limit} breached: measured {breach.measured} "
                f"at or beyond limit {breach.limit_value}"
            ),
            observed={
                "limit": breach.limit,
                "measured": breach.measured,
                "limit_value": breach.limit_value,
            },
        )
        ledger.record(record)
        recorded.append(record)
    return recorded
