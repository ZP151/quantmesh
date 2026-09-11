"""Read-only comparison of frozen forecasts and exact realized daily closes."""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from quantmesh.instruments.scenario_lab import effective_horizon

if TYPE_CHECKING:
    from quantmesh.instruments.reviews import DecisionOutcomeSnapshot


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class ForecastOutcomeRow(_Contract):
    session: int = Field(ge=1)
    timestamp: datetime
    p10: float = Field(gt=0)
    p50: float = Field(gt=0)
    p90: float = Field(gt=0)
    actual_close: float | None = None
    absolute_error: float | None = None
    within_interval: bool | None = None


class ForecastOutcomeComparison(_Contract):
    """Descriptive errors for one path, never calibration or trading authority."""

    policy_version: Literal["exact-close-v1"] = "exact-close-v1"
    outcome_id: str
    forecast_artifact_id: str | None
    horizon_sessions: Literal[7, 30]
    status: Literal["complete", "pending", "partial", "unavailable"]
    reason: str | None = None
    observed_sessions: int = Field(default=0, ge=0, le=30)
    rows: tuple[ForecastOutcomeRow, ...] = ()
    mean_absolute_error: float | None = None
    benchmark_mae: float | None = None
    interval_hits: int | None = None
    interval_coverage: float | None = None
    terminal_error: float | None = None


def compare_forecast_outcome(outcome: DecisionOutcomeSnapshot) -> ForecastOutcomeComparison:
    """Project validated snapshot evidence without reads or durable schema changes."""
    root = outcome.root_packet
    horizon = effective_horizon(root)
    evidence = root.evidence
    path = outcome.path
    identity = {
        "outcome_id": outcome.outcome_id,
        "forecast_artifact_id": evidence.forecast_artifact_id,
        "horizon_sessions": horizon,
    }
    forecast = next((item for item in evidence.forecast_paths if item.sessions == horizon), None)
    if (
        evidence.forecast_artifact_id is None
        or forecast is None
        or len(forecast.points) != horizon
        or not path.expected_session_times
    ):
        return ForecastOutcomeComparison(
            **identity,
            status="unavailable",
            reason="Exact selected forecast evidence is unavailable.",
        )
    expected = tuple(point.timestamp for point in forecast.points)
    if path.expected_session_times != expected:
        return ForecastOutcomeComparison(
            **identity,
            status="unavailable",
            reason="Outcome timestamps do not match the exact selected forecast.",
        )

    closes = {bar.timestamp: bar.close for bar in path.bars}
    rows = tuple(
        ForecastOutcomeRow(
            session=point.session,
            timestamp=point.timestamp,
            p10=point.p10,
            p50=point.p50,
            p90=point.p90,
            actual_close=closes.get(point.timestamp),
            absolute_error=(
                abs(closes[point.timestamp] - point.p50) if point.timestamp in closes else None
            ),
            within_interval=(
                point.p10 <= closes[point.timestamp] <= point.p90
                if point.timestamp in closes
                else None
            ),
        )
        for point in forecast.points
    )
    observed = sum(row.actual_close is not None for row in rows)
    status = path.status
    if status == "complete" and observed != horizon:
        status = "partial"
    if status != "complete":
        return ForecastOutcomeComparison(
            **identity,
            status=status,
            reason={
                "pending": "The selected forecast horizon has not completed.",
                "partial": (
                    "The exact realized path is incomplete; aggregate scores are unavailable."
                ),
                "unavailable": "Validated realized closes are unavailable.",
            }[status],
            observed_sessions=observed,
            rows=rows,
        )

    hits = sum(row.within_interval is True for row in rows)
    return ForecastOutcomeComparison(
        **identity,
        status="complete",
        observed_sessions=observed,
        rows=rows,
        mean_absolute_error=math.fsum(row.absolute_error for row in rows) / horizon,
        benchmark_mae=math.fsum(
            abs(row.actual_close - root.market_state.latest_close) for row in rows
        )
        / horizon,
        interval_hits=hits,
        interval_coverage=hits / horizon,
        terminal_error=rows[-1].actual_close - rows[-1].p50,
    )
