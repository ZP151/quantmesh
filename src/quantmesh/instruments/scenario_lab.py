"""Deterministic selected-horizon evidence qualification for the Scenario Lab."""

from datetime import datetime, timedelta
from typing import Literal

from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.instruments.contracts import (
    DecisionPacket,
    HistoricalSeries,
    ScenarioLabSnapshot,
    WorkspaceForecast,
)


def effective_horizon(packet: DecisionPacket) -> int:
    """Legacy packets retain the original 30-session interpretation."""
    return packet.scenario_lab.selected_horizon if packet.scenario_lab is not None else 30


def evidence_is_stale(history: HistoricalSeries, timestamp: datetime, as_of: datetime) -> bool:
    """Use the pinned XNYS daily grid for new lab evidence, including holidays."""
    if timestamp >= as_of:
        return False
    if history.calendar == "XNYS":
        try:
            return (
                CalendarService().expected_bar_count(
                    "XNYS",
                    timestamp + timedelta(microseconds=1),
                    as_of + timedelta(microseconds=1),
                    interval="1d",
                    policy=SessionPolicy.REGULAR,
                )
                > 1
            )
        except ValueError:
            return True
    return as_of - timestamp > timedelta(days=1)


def assess_scenario_lab(
    history: HistoricalSeries,
    forecast: WorkspaceForecast | None,
    *,
    horizon: Literal[7, 30],
    as_of: datetime,
) -> ScenarioLabSnapshot:
    """Qualify evidence, with strict improvement and no invented directional probability."""
    failures: list[str] = []
    cautions: list[str] = []
    if history.interval != "1d" or history.gaps or history.duplicates or history.limitations:
        failures.append("daily history is unavailable or has quality limitations")
    if any(bar.timestamp > as_of or bar.is_live_tail for bar in history.bars):
        failures.append("history contains future knowledge or a live tail")
    if history.generated_at > as_of:
        failures.append("history generation violates as-of chronology")
    if history.source != "demo-synthetic" and history.manifest_id is None:
        failures.append("history is missing exact manifest evidence")
    if evidence_is_stale(history, history.generated_at, as_of):
        cautions.append("history evidence is stale")
    if evidence_is_stale(history, history.bars[-1].timestamp, as_of):
        cautions.append("latest observed daily bar is stale")
    if forecast is None:
        failures.append("selected forecast evidence is unavailable")
    else:
        if (
            history.dataset_id != forecast.dataset_id
            or history.dataset_revision != forecast.dataset_revision
            or history.manifest_id != forecast.manifest_id
            or history.quality_evaluation_id != forecast.quality_evaluation_id
            or (history.source == "demo-synthetic") != forecast.synthetic
            or history.bars[-1].timestamp != forecast.train_end
        ):
            failures.append(
                "history does not match the exact forecast dataset, manifest or as-of cut"
            )
        path = next((p for p in forecast.paths if p.sessions == horizon), None)
        metric = next((m for m in forecast.metrics if m.sessions == horizon), None)
        if path is None or metric is None:
            failures.append(f"selected {horizon}-session path or metrics are unavailable")
        if (
            forecast.generated_at > as_of
            or forecast.train_end > as_of
            or any(
                point.timestamp <= forecast.train_end
                for item in forecast.paths
                for point in item.points
            )
            or (
                metric is not None
                and any(
                    timestamp is not None and timestamp > forecast.train_end
                    for timestamp in (
                        metric.validation_start,
                        metric.validation_end,
                        metric.test_start,
                        metric.test_end,
                    )
                )
            )
        ):
            failures.append("forecast evidence violates as-of chronology")
        if evidence_is_stale(history, forecast.generated_at, as_of):
            cautions.append("forecast evidence is stale")
        if not forecast.eligible or forecast.blockers:
            cautions.extend(forecast.blockers or ("artifact-wide eligibility failed",))
        if metric is not None:
            if metric.residual_count == 0 or metric.interval_test_count == 0:
                failures.append("selected horizon has no resolved residuals or evaluated intervals")
            if metric.residual_count < 30:
                cautions.append("at least 30 resolved residuals are required")
            if metric.interval_test_count < 30:
                cautions.append("at least 30 evaluated intervals are required")
            if not 0.60 <= metric.coverage_80 <= 0.98:
                cautions.append("empirical 80% coverage is outside [0.60, 0.98]")
            if metric.mae >= metric.benchmark_mae:
                cautions.append("MAE must be strictly below last-price random-walk MAE")
    return ScenarioLabSnapshot(
        selected_horizon=horizon,
        history=history,
        confidence="abstain" if failures else "low-confidence" if cautions else "qualified",
        reasons=tuple(dict.fromkeys(failures + cautions)),
    )
