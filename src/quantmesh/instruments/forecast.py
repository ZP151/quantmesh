"""Truthful deterministic price-path forecasts and append-only artifacts.

The baseline deliberately stays small: a 252-observed-return median drift,
chronological rolling out-of-sample residuals, and empirical conformal bands.
It is a research aid, not order authority.  Eligibility is computed from the
recorded evidence and every consumer must preserve its blockers.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Protocol

from pydantic import ValidationError

from quantmesh._fs import atomic_replace
from quantmesh.data.artifacts import ArtifactLayer
from quantmesh.data.capabilities import DataKind
from quantmesh.data.lake import Lake
from quantmesh.domain.models import InstrumentType
from quantmesh.instruments.contracts import (
    FORECAST_ID_PATTERN,
    DatasetBinding,
    ForecastMetrics,
    ForecastPath,
    ForecastPoint,
    HistoricalBar,
    HistoricalSeries,
    OOSForecast,
    PriceForecastArtifact,
)
from quantmesh.settings import settings

HORIZONS = (7, 30, 126)
RETURN_WINDOW = 252
MAX_FORECAST_SESSIONS = 650
MODEL_NAME = "median-log-drift-conformal"
BENCHMARK_NAME = "last-price-random-walk"
QUANTILES = (0.025, 0.10, 0.25, 0.75, 0.90, 0.975)
FILES = ("report.json", "paths.csv", "oos.csv")
LIMITATIONS = (
    "Prototype baseline uses weekday sessions for equities and does not model exchange holidays.",
    "Intervals are empirical and do not imply a probability of profit or execution outcome.",
    "The artifact is research evidence; the paper kernel remains the only order authority.",
)


class TrustedForecastCatalog(Protocol):
    def require_research(self, manifest_id: str) -> Any: ...

    def open_research_dataset(
        self,
        manifest_id: str,
        *,
        evaluation_id: str,
        dataset_id: str,
        compatibility_revision: int,
    ) -> Any: ...


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _quantile(values: Sequence[float], probability: float) -> float:
    """Type-7 empirical quantile, implemented locally for stable semantics."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _centered_residual_quantiles(values: Sequence[float]) -> tuple[float, ...]:
    center = _quantile(values, 0.5)
    return tuple(_quantile(values, probability) - center for probability in QUANTILES)


def _drift(closes: Sequence[float], origin: int) -> float:
    """Median of exactly the 252 returns ending at ``origin`` when available."""
    start = max(1, origin - RETURN_WINDOW + 1)
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(start, origin + 1)]
    return median(returns) if returns else 0.0


def rolling_oos_forecasts(
    bars: Sequence[HistoricalBar], *, horizon: int
) -> tuple[OOSForecast, ...]:
    """Chronological OOS rows with intervals fitted only to then-known outcomes.

    An origin is admitted only after 252 observed returns (253 closes).  Its
    interval may use an earlier row only once that row's target has occurred;
    overlapping unresolved targets can therefore never leak into the band.
    """
    if horizon not in HORIZONS:
        raise ValueError(f"unsupported forecast horizon {horizon}")
    closes = [bar.close for bar in bars]
    rows: list[OOSForecast] = []
    resolved: list[tuple[int, float]] = []
    first_origin = RETURN_WINDOW
    last_origin = len(bars) - horizon - 1
    for origin in range(first_origin, last_origin + 1):
        usable = [residual for target, residual in resolved if target <= origin]
        drift = _drift(closes, origin)
        predicted = closes[origin] * math.exp(drift * horizon)
        target = origin + horizon
        actual = closes[target]
        quantiles: dict[str, float | None] = {
            "p025": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "p975": None,
        }
        if usable:
            centered = _centered_residual_quantiles(usable)
            quantiles = {
                name: predicted * math.exp(offset)
                for name, offset in zip(quantiles, centered, strict=True)
            }
        residual = math.log(actual / predicted)
        rows.append(
            OOSForecast(
                sessions=horizon,
                origin_at=bars[origin].timestamp,
                target_at=bars[target].timestamp,
                predicted=predicted,
                benchmark=closes[origin],
                actual=actual,
                residual_log=residual,
                **quantiles,
            )
        )
        resolved.append((target, residual))
    return tuple(rows)


def _future_sessions(last: datetime, count: int, *, continuous: bool) -> tuple[datetime, ...]:
    result: list[datetime] = []
    candidate = last
    while len(result) < count:
        candidate += timedelta(days=1)
        if continuous or candidate.weekday() < 5:
            result.append(candidate)
    return tuple(result)


def _path(
    bars: Sequence[HistoricalBar],
    *,
    horizon: int,
    residuals: Sequence[float],
    continuous: bool,
) -> ForecastPath:
    closes = [bar.close for bar in bars]
    drift = _drift(closes, len(closes) - 1)
    centered = _centered_residual_quantiles(residuals)
    dates = _future_sessions(bars[-1].timestamp, horizon, continuous=continuous)
    points: list[ForecastPoint] = []
    for session, timestamp in enumerate(dates, start=1):
        predicted = closes[-1] * math.exp(drift * session)
        scale = math.sqrt(session / horizon)
        values = tuple(predicted * math.exp(offset * scale) for offset in centered)
        points.append(
            ForecastPoint(
                session=session,
                timestamp=timestamp,
                p025=values[0],
                p10=values[1],
                p25=values[2],
                p50=predicted,
                p75=values[3],
                p90=values[4],
                p975=values[5],
            )
        )
    return ForecastPath(sessions=horizon, points=tuple(points))


def _coverage(rows: Sequence[OOSForecast], low: str, high: str) -> tuple[int, float]:
    evaluated = [row for row in rows if getattr(row, low) is not None]
    if not evaluated:
        return 0, 0.0
    covered = sum(
        getattr(row, low) <= row.actual <= getattr(row, high)  # type: ignore[operator]
        for row in evaluated
    )
    return len(evaluated), covered / len(evaluated)


def _metrics(horizon: int, rows: Sequence[OOSForecast]) -> ForecastMetrics:
    if not rows:
        return ForecastMetrics(
            sessions=horizon,
            residual_count=0,
            interval_test_count=0,
            validation_start=None,
            validation_end=None,
            test_start=None,
            test_end=None,
            mae=0.0,
            rmse=0.0,
            benchmark_mae=0.0,
            coverage_50=0.0,
            coverage_80=0.0,
            coverage_95=0.0,
        )
    errors = [row.actual - row.predicted for row in rows]
    benchmark_errors = [row.actual - row.benchmark for row in rows]
    tested = [row for row in rows if row.p10 is not None]
    interval_test_count, coverage_80 = _coverage(rows, "p10", "p90")
    _, coverage_50 = _coverage(rows, "p25", "p75")
    _, coverage_95 = _coverage(rows, "p025", "p975")
    return ForecastMetrics(
        sessions=horizon,
        residual_count=len(rows),
        interval_test_count=interval_test_count,
        validation_start=rows[0].target_at,
        validation_end=rows[-1].target_at,
        test_start=tested[0].target_at if tested else None,
        test_end=tested[-1].target_at if tested else None,
        mae=sum(abs(value) for value in errors) / len(errors),
        rmse=math.sqrt(sum(value * value for value in errors) / len(errors)),
        benchmark_mae=sum(abs(value) for value in benchmark_errors) / len(benchmark_errors),
        coverage_50=coverage_50,
        coverage_80=coverage_80,
        coverage_95=coverage_95,
    )


def _unexplained_bar_gaps(bars: Sequence[object], *, continuous: bool) -> tuple[datetime, ...]:
    timestamps = tuple(bar.timestamp for bar in bars)
    gaps: list[datetime] = []
    for left, right in zip(timestamps, timestamps[1:]):
        candidate = left + timedelta(days=1)
        while candidate.date() < right.date():
            if continuous or candidate.weekday() < 5:
                gaps.append(candidate)
            candidate += timedelta(days=1)
        if right.date() == left.date():
            gaps.append(right)
    return tuple(gaps)


def _session_age(train_end: datetime, generated_at: datetime, *, continuous: bool) -> int:
    count = 0
    candidate = train_end + timedelta(days=1)
    while candidate.date() <= generated_at.date():
        if continuous or candidate.weekday() < 5:
            count += 1
        candidate += timedelta(days=1)
    return count


def _paths_csv(paths: Sequence[ForecastPath]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        ["horizon", "session", "timestamp", "p025", "p10", "p25", "p50", "p75", "p90", "p975"]
    )
    for path in paths:
        for point in path.points:
            writer.writerow(
                [
                    path.sessions,
                    point.session,
                    point.timestamp.isoformat(),
                    point.p025,
                    point.p10,
                    point.p25,
                    point.p50,
                    point.p75,
                    point.p90,
                    point.p975,
                ]
            )
    return output.getvalue().encode("utf-8")


def _oos_csv(rows: Sequence[OOSForecast]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    names = [
        "horizon",
        "origin_at",
        "target_at",
        "predicted",
        "benchmark",
        "actual",
        "residual_log",
        "p025",
        "p10",
        "p25",
        "p75",
        "p90",
        "p975",
    ]
    writer.writerow(names)
    for row in rows:
        writer.writerow(
            [
                row.sessions,
                row.origin_at.isoformat(),
                row.target_at.isoformat(),
                row.predicted,
                row.benchmark,
                row.actual,
                row.residual_log,
                *("" if getattr(row, name) is None else getattr(row, name) for name in names[7:]),
            ]
        )
    return output.getvalue().encode("utf-8")


def _report_core(artifact: PriceForecastArtifact) -> bytes:
    excluded = {"artifact_hashes"}
    if artifact.manifest_id is None:
        excluded.update({"manifest_id", "quality_evaluation_id"})
    return _canonical_json(artifact.model_dump(mode="json", exclude=excluded))


def _report_file(artifact: PriceForecastArtifact) -> bytes:
    excluded = (
        {"manifest_id", "quality_evaluation_id"}
        if artifact.manifest_id is None
        else set()
    )
    return _canonical_json(artifact.model_dump(mode="json", exclude=excluded))


def _expected_hashes(artifact: PriceForecastArtifact) -> dict[str, str]:
    # report.json pins the canonical report payload excluding the digest map
    # itself, avoiding an impossible self-referential file hash.
    return {
        "report.json": _sha256(_report_core(artifact)),
        "paths.csv": _sha256(_paths_csv(artifact.paths)),
        "oos.csv": _sha256(_oos_csv(artifact.oos)),
    }


def _config() -> dict[str, object]:
    return {
        "benchmark": BENCHMARK_NAME,
        "coverage_gate": [0.60, 0.98],
        "horizons": list(HORIZONS),
        "model": MODEL_NAME,
        "max_forecast_sessions": MAX_FORECAST_SESSIONS,
        "residual_minimums": {"7": 30, "30": 30, "126": 12},
        "return_window": RETURN_WINDOW,
    }


def _bar_digest(bars: Sequence[object]) -> str:
    return _sha256(
        _canonical_json(
            [
                [
                    bar.timestamp.isoformat(),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                ]
                for bar in bars
            ]
        )
    )


def _identity(
    *,
    artifact: PriceForecastArtifact | None = None,
    series: HistoricalSeries | None = None,
    generated_at: datetime | None = None,
    model_version: str | None = None,
    config_digest: str | None = None,
    history_digest: str | None = None,
    bars: Sequence[HistoricalBar] | None = None,
    gap_count: int | None = None,
    duplicate_count: int | None = None,
    age_sessions: int | None = None,
) -> dict[str, object]:
    if artifact is not None:
        identity = {
            "adjustment": artifact.adjustment,
            "age_sessions": artifact.age_sessions,
            "bar_digest": artifact.history_digest,
            "calendar": artifact.calendar,
            "config_digest": artifact.config_digest,
            "coverage": artifact.coverage.model_dump(mode="json"),
            "dataset": artifact.dataset_id,
            "dataset_generated_at": artifact.dataset_generated_at.isoformat(),
            "duplicate_count": artifact.duplicate_count,
            "gap_count": artifact.gap_count,
            "generated_at": artifact.generated_at.isoformat(),
            "history_sessions": artifact.history_sessions,
            "history_start": artifact.history_start.isoformat(),
            "instrument": artifact.instrument.model_dump(mode="json"),
            "license": artifact.license,
            "limitations": list(artifact.limitations),
            "model_version": artifact.model_version,
            "revision": artifact.dataset_revision,
            "source": artifact.source,
            "target": artifact.target,
            "train_end": artifact.train_end.isoformat(),
            "train_start": artifact.train_start.isoformat(),
        }
        if artifact.manifest_id is not None:
            identity["manifest_id"] = artifact.manifest_id
            identity["quality_evaluation_id"] = artifact.quality_evaluation_id
        return identity
    if (
        series is None
        or generated_at is None
        or model_version is None
        or config_digest is None
        or history_digest is None
        or bars is None
        or gap_count is None
        or duplicate_count is None
        or age_sessions is None
    ):
        raise ValueError("forecast identity inputs are incomplete")
    identity = {
        "adjustment": series.adjustment,
        "age_sessions": age_sessions,
        "bar_digest": history_digest,
        "calendar": series.calendar,
        "config_digest": config_digest,
        "coverage": series.coverage.model_dump(mode="json"),
        "dataset": series.dataset_id,
        "dataset_generated_at": series.generated_at.isoformat(),
        "duplicate_count": duplicate_count,
        "gap_count": gap_count,
        "generated_at": generated_at.isoformat(),
        "history_sessions": len(bars),
        "history_start": bars[0].timestamp.isoformat(),
        "instrument": series.instrument.model_dump(mode="json"),
        "license": series.license,
        "limitations": list(LIMITATIONS),
        "model_version": model_version,
        "revision": series.dataset_revision,
        "source": series.source,
        "target": f"{series.adjustment}-close",
        "train_end": bars[-1].timestamp.isoformat(),
        "train_start": bars[max(0, len(bars) - RETURN_WINDOW - 1)].timestamp.isoformat(),
    }
    if series.manifest_id is not None:
        identity["manifest_id"] = series.manifest_id
        identity["quality_evaluation_id"] = series.quality_evaluation_id
    return identity


def _promotion_blockers(
    *,
    history_sessions: int,
    gap_count: int,
    duplicate_count: int,
    continuous: bool,
    age_sessions: int,
    metrics: Sequence[ForecastMetrics],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if history_sessions < 315:
        blockers.append(f"history has {history_sessions} sessions; at least 315 are required")
    if duplicate_count:
        blockers.append(f"history contains {duplicate_count} duplicate timestamp(s)")
    if gap_count:
        kind = "daily" if continuous else "weekday"
        blockers.append(f"history contains {gap_count} unexplained {kind} gap(s)")
    required = {7: 30, 30: 30, 126: 12}
    for metric in metrics:
        minimum = required[metric.sessions]
        if metric.residual_count < minimum:
            blockers.append(
                f"{metric.sessions}-session horizon has {metric.residual_count} residuals; "
                f"at least {minimum} are required"
            )
        if metric.interval_test_count == 0 or not 0.60 <= metric.coverage_80 <= 0.98:
            blockers.append(
                f"{metric.sessions}-session 80% coverage {metric.coverage_80:.6f} "
                "is outside [0.60, 0.98]"
            )
        if metric.residual_count and metric.mae > metric.benchmark_mae * 1.10:
            blockers.append(
                f"{metric.sessions}-session MAE {metric.mae:.6f} exceeds 110% of "
                f"benchmark MAE {metric.benchmark_mae:.6f}"
            )
    if age_sessions > 1:
        blockers.append(f"artifact age is {age_sessions} sessions; it exceeds one session")
    return tuple(blockers)


def validate_price_forecast_artifact(
    artifact: PriceForecastArtifact,
) -> PriceForecastArtifact:
    """Validate internal structure only; registry pin validation establishes trust."""
    try:
        artifact = PriceForecastArtifact.model_validate(artifact.model_dump())
    except ValidationError as error:
        raise ValueError("forecast artifact contract is internally inconsistent") from error
    if artifact.config_digest != _sha256(_canonical_json(_config())):
        raise ValueError("forecast config_digest does not match the declared model setup")
    if artifact.limitations != LIMITATIONS:
        raise ValueError("forecast limitations do not match the canonical risk disclosure")
    expected_id = f"forecast-{_sha256(_canonical_json(_identity(artifact=artifact)))[:24]}"
    if artifact.id != expected_id:
        raise ValueError("forecast id does not match its immutable setup")
    grouped = {
        horizon: tuple(row for row in artifact.oos if row.sessions == horizon)
        for horizon in HORIZONS
    }
    expected_metrics = tuple(_metrics(horizon, grouped[horizon]) for horizon in HORIZONS)
    if artifact.metrics != expected_metrics:
        raise ValueError("forecast metrics do not match the recorded OOS rows")
    for horizon, rows in grouped.items():
        expected_count = max(0, artifact.history_sessions - RETURN_WINDOW - horizon)
        if len(rows) != expected_count:
            raise ValueError(f"{horizon}-session OOS count does not match history_sessions")
        if any(row.target_at > artifact.train_end for row in rows):
            raise ValueError("OOS outcomes cannot be after train_end")
    continuous = artifact.instrument.instrument_type in {
        InstrumentType.SPOT,
        InstrumentType.PERPETUAL,
    }
    expected_blockers = _promotion_blockers(
        history_sessions=artifact.history_sessions,
        gap_count=artifact.gap_count,
        duplicate_count=artifact.duplicate_count,
        continuous=continuous,
        age_sessions=artifact.age_sessions,
        metrics=artifact.metrics,
    )
    if artifact.blockers != expected_blockers or artifact.eligible != (not expected_blockers):
        raise ValueError("forecast eligibility does not match its promotion evidence")
    return artifact


def _validate_against_bars(artifact: PriceForecastArtifact, bars: Sequence[object]) -> None:
    if len(bars) != artifact.history_sessions or _bar_digest(bars) != artifact.history_digest:
        raise ValueError("dataset pin history bytes do not match the forecast artifact")
    if not bars:
        raise ValueError("forecast artifact cannot resolve an empty history")
    expected_instrument = artifact.instrument.model_dump(mode="json")
    if any(bar.instrument.model_dump(mode="json") != expected_instrument for bar in bars):
        raise ValueError("pinned history instrument does not match the forecast artifact")
    expected_train_start = bars[max(0, len(bars) - RETURN_WINDOW - 1)].timestamp
    if (
        artifact.history_start != bars[0].timestamp
        or artifact.train_start != expected_train_start
        or artifact.train_end != bars[-1].timestamp
    ):
        raise ValueError("forecast training boundaries do not match pinned history")
    continuous = artifact.instrument.instrument_type in {
        InstrumentType.SPOT,
        InstrumentType.PERPETUAL,
    }
    timestamps = tuple(bar.timestamp for bar in bars)
    duplicate_count = len(timestamps) - len(set(timestamps))
    gap_count = len(_unexplained_bar_gaps(bars, continuous=continuous))
    age_sessions = _session_age(
        bars[-1].timestamp,
        artifact.generated_at,
        continuous=continuous,
    )
    if (
        artifact.duplicate_count != duplicate_count
        or artifact.gap_count != gap_count
        or artifact.age_sessions != age_sessions
    ):
        raise ValueError("forecast quality evidence does not match pinned history")
    expected_by_horizon = {
        horizon: rolling_oos_forecasts(bars, horizon=horizon) for horizon in HORIZONS
    }
    expected_oos = tuple(row for horizon in HORIZONS for row in expected_by_horizon[horizon])
    if artifact.oos != expected_oos:
        raise ValueError("forecast OOS rows do not match pinned history")
    expected_paths = tuple(
        _path(
            bars,
            horizon=horizon,
            residuals=[row.residual_log for row in expected_by_horizon[horizon]],
            continuous=continuous,
        )
        for horizon in HORIZONS
    )
    if artifact.paths != expected_paths:
        raise ValueError("forecast paths do not match pinned history")
    expected_blockers = _promotion_blockers(
        history_sessions=len(bars),
        gap_count=gap_count,
        duplicate_count=duplicate_count,
        continuous=continuous,
        age_sessions=age_sessions,
        metrics=artifact.metrics,
    )
    if artifact.blockers != expected_blockers or artifact.eligible != (not expected_blockers):
        raise ValueError("forecast eligibility does not match pinned history")


def run_price_forecast(
    series: HistoricalSeries,
    *,
    generated_at: datetime,
    model_version: str,
) -> PriceForecastArtifact:
    """Build one deterministic artifact without mutating a registry."""
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    generated_at = generated_at.astimezone(UTC)
    if not model_version.strip():
        raise ValueError("model_version must not be blank")
    if series.interval != "1d":
        raise ValueError("price forecast requires manifest-gated daily history")
    if series.adjustment != "unadjusted":
        raise ValueError("price forecast currently supports unadjusted close only")
    if any(bar.is_live_tail for bar in series.bars):
        raise ValueError("price forecast refuses a live-tail bar")
    if generated_at < series.bars[-1].timestamp:
        raise ValueError("generated_at cannot precede the last observed bar")
    if generated_at < series.generated_at:
        raise ValueError("generated_at cannot precede the dataset manifest generation")

    bars = tuple(series.bars[-MAX_FORECAST_SESSIONS:])
    continuous = series.instrument.instrument_type in {
        InstrumentType.SPOT,
        InstrumentType.PERPETUAL,
    }
    oos_by_horizon = {horizon: rolling_oos_forecasts(bars, horizon=horizon) for horizon in HORIZONS}
    metrics = tuple(_metrics(horizon, oos_by_horizon[horizon]) for horizon in HORIZONS)
    paths = tuple(
        _path(
            bars,
            horizon=horizon,
            residuals=[row.residual_log for row in oos_by_horizon[horizon]],
            continuous=continuous,
        )
        for horizon in HORIZONS
    )
    oos = tuple(row for horizon in HORIZONS for row in oos_by_horizon[horizon])

    timestamps = tuple(bar.timestamp for bar in bars)
    duplicate_count = len(timestamps) - len(set(timestamps))
    gap_count = len(_unexplained_bar_gaps(bars, continuous=continuous))
    age = _session_age(bars[-1].timestamp, generated_at, continuous=continuous)
    blockers = _promotion_blockers(
        history_sessions=len(bars),
        gap_count=gap_count,
        duplicate_count=duplicate_count,
        continuous=continuous,
        age_sessions=age,
        metrics=metrics,
    )
    config_digest = _sha256(_canonical_json(_config()))
    history_digest = _bar_digest(bars)
    identity = _identity(
        series=series,
        generated_at=generated_at,
        model_version=model_version,
        config_digest=config_digest,
        history_digest=history_digest,
        bars=bars,
        gap_count=gap_count,
        duplicate_count=duplicate_count,
        age_sessions=age,
    )
    artifact_id = f"forecast-{_sha256(_canonical_json(identity))[:24]}"
    common: dict[str, object] = {
        "id": artifact_id,
        "instrument": series.instrument,
        "dataset_id": series.dataset_id,
        "dataset_revision": series.dataset_revision,
        "manifest_id": series.manifest_id,
        "quality_evaluation_id": series.quality_evaluation_id,
        "source": series.source,
        "license": series.license,
        "dataset_generated_at": series.generated_at,
        "coverage": series.coverage,
        "calendar": series.calendar,
        "adjustment": series.adjustment,
        "target": f"{series.adjustment}-close",
        "history_start": bars[0].timestamp,
        "history_sessions": len(bars),
        "history_digest": history_digest,
        "gap_count": gap_count,
        "duplicate_count": duplicate_count,
        "age_sessions": age,
        "generated_at": generated_at,
        "train_start": bars[max(0, len(bars) - RETURN_WINDOW - 1)].timestamp,
        "train_end": bars[-1].timestamp,
        "validation_start": min((row.target_at for row in oos), default=None),
        "validation_end": max((row.target_at for row in oos), default=None),
        "test_start": min((row.target_at for row in oos if row.p10 is not None), default=None),
        "test_end": max((row.target_at for row in oos if row.p10 is not None), default=None),
        "model_name": MODEL_NAME,
        "model_version": model_version,
        "config_digest": config_digest,
        "benchmark_name": BENCHMARK_NAME,
        "paths": paths,
        "oos": oos,
        "metrics": metrics,
        "eligible": not blockers,
        "blockers": blockers,
        "limitations": LIMITATIONS,
    }
    placeholder = PriceForecastArtifact(
        **common,
        artifact_hashes={name: "0" * 64 for name in FILES},
    )
    artifact = PriceForecastArtifact(
        **common,
        artifact_hashes=_expected_hashes(placeholder),
    )
    return validate_price_forecast_artifact(artifact)


def _path_is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    if hasattr(path, "is_junction") and path.is_junction():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x400)


def _reject_reparse_components(path: Path) -> None:
    for component in (path, *path.parents):
        if component.exists() and _path_is_link_or_reparse(component):
            raise ValueError(
                f"forecast registry path component {component} is a link or reparse point"
            )


class PriceForecastRegistry:
    """Crash-safe append-only forecast directories with lake pin checks."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        lake_root: Path | None = None,
        bindings: Iterable[DatasetBinding] = (),
        trusted_catalog: TrustedForecastCatalog | None = None,
    ) -> None:
        self.root = root if root is not None else settings.reports_dir / "forecasts"
        self.lake_root = lake_root if lake_root is not None else settings.lake_root
        self._bindings = tuple(bindings)
        self.trusted_catalog = trusted_catalog

    def _safe_root(self) -> None:
        _reject_reparse_components(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise ValueError(f"forecast registry root {self.root} is not a safe directory")

    def resolve_pin(self, artifact: PriceForecastArtifact) -> Any:
        matches = [
            binding
            for binding in self._bindings
            if binding.dataset_id == artifact.dataset_id
            and binding.interval == "1d"
            and binding.venue is artifact.instrument.venue
            and binding.symbol == artifact.instrument.symbol
        ]
        if len(matches) != 1:
            raise ValueError("forecast pin requires exactly one trusted daily dataset binding")
        binding = matches[0]
        if binding.calendar != artifact.calendar or binding.adjustment != artifact.adjustment:
            raise ValueError("forecast calendar or adjustment does not match its trusted binding")
        if artifact.manifest_id is not None:
            if self.trusted_catalog is None or artifact.quality_evaluation_id is None:
                raise ValueError("trusted forecast lineage requires a data catalog")
            dataset = self.trusted_catalog.open_research_dataset(
                artifact.manifest_id,
                evaluation_id=artifact.quality_evaluation_id,
                dataset_id=artifact.dataset_id,
                compatibility_revision=artifact.dataset_revision,
            )
            catalog_entry = self.trusted_catalog.require_research(
                artifact.manifest_id
            )
            if (
                dataset.manifest.layer is not ArtifactLayer.ADJUSTED
                or dataset.manifest.data_kind is not DataKind.BARS
                or dataset.manifest.interval != "1d"
            ):
                raise ValueError(
                    "trusted forecast input must be an adjusted daily bar manifest"
                )
            dataset_revision = dataset.manifest.compatibility_revision
            dataset_source = catalog_entry.provider_id
            dataset_license = catalog_entry.source_rights_id
            dataset_generated_at = dataset.manifest.created_at
        else:
            dataset = Lake(self.lake_root).dataset(artifact.dataset_id)
            dataset_revision = dataset.manifest.revision
            dataset_source = dataset.manifest.source
            dataset_license = dataset.manifest.license
            dataset_generated_at = dataset.manifest.generated_at
        if dataset_revision != artifact.dataset_revision:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} is now revision "
                f"{dataset_revision}, but the pin asks for revision "
                f"{artifact.dataset_revision}"
            )
        if dataset_source != artifact.source:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} source no longer matches the artifact pin"
            )
        if dataset_license != artifact.license:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} license no longer matches the artifact pin"
            )
        if dataset_generated_at.astimezone(UTC) != artifact.dataset_generated_at:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} manifest generation no longer matches "
                "the artifact pin"
            )
        if artifact.generated_at < artifact.dataset_generated_at:
            raise ValueError("forecast predates the pinned dataset manifest")
        if artifact.manifest_id is not None:
            observed_coverage = artifact.coverage.model_validate(
                {
                    "interval": dataset.manifest.interval,
                    "venue": artifact.instrument.venue,
                    "symbol": artifact.instrument.symbol,
                    "start": dataset.manifest.event_start,
                    "end": dataset.manifest.event_end,
                    "rows": len(dataset.manifest.row_identities),
                }
            )
        else:
            coverage = next(
                (
                    item
                    for item in dataset.manifest.coverage
                    if item.interval == "1d"
                    and item.venue == artifact.instrument.venue
                    and item.symbol == artifact.instrument.symbol
                ),
                None,
            )
            if coverage is None:
                raise ValueError("dataset pin no longer covers the artifact training window")
            observed_coverage = artifact.coverage.model_validate(coverage.model_dump())
        if observed_coverage != artifact.coverage:
            raise ValueError("dataset coverage no longer exactly matches the artifact pin")
        if artifact.manifest_id is not None:
            bars = [
                bar
                for bar in dataset.read_bars()
                if artifact.history_start <= bar.timestamp <= artifact.train_end
            ]
        else:
            bars = dataset.read_bars(
                interval="1d",
                venue=artifact.instrument.venue,
                symbol=artifact.instrument.symbol,
                start=artifact.history_start,
                end=artifact.train_end,
            )
        _validate_against_bars(artifact, bars)
        return dataset

    def record(self, artifact: PriceForecastArtifact) -> PriceForecastArtifact:
        self._safe_root()
        validate_price_forecast_artifact(artifact)
        self.resolve_pin(artifact)
        expected = _expected_hashes(artifact)
        if dict(artifact.artifact_hashes) != expected:
            raise ValueError("forecast artifact hashes do not match its canonical payloads")
        self.root.mkdir(parents=True, exist_ok=True)
        self._safe_root()
        target = self.root / artifact.id
        if target.exists():
            raise ValueError(f"forecast artifact {artifact.id!r} already recorded")
        temp = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{artifact.id}.", suffix=".tmp"))
        try:
            (temp / "report.json").write_bytes(_report_file(artifact))
            (temp / "paths.csv").write_bytes(_paths_csv(artifact.paths))
            (temp / "oos.csv").write_bytes(_oos_csv(artifact.oos))
            atomic_replace(temp, target)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        return artifact

    def get(self, artifact_id: str) -> PriceForecastArtifact:
        if re.fullmatch(FORECAST_ID_PATTERN, artifact_id) is None:
            raise ValueError("invalid forecast artifact id")
        self._safe_root()
        directory = self.root / artifact_id
        if not directory.exists() or not directory.is_dir() or _path_is_link_or_reparse(directory):
            raise ValueError(f"no forecast artifact recorded with id {artifact_id!r}")
        paths = {name: directory / name for name in FILES}
        entries = {path.name for path in directory.iterdir()}
        if entries != set(FILES):
            raise ValueError(f"forecast artifact {directory} must contain exactly {sorted(FILES)}")
        for name, path in paths.items():
            if not path.is_file() or _path_is_link_or_reparse(path):
                raise ValueError(f"forecast artifact {path} is missing or unsafe")
        try:
            observed_report = paths["report.json"].read_bytes()
            artifact = PriceForecastArtifact.model_validate_json(observed_report)
        except (OSError, UnicodeDecodeError, ValidationError) as error:
            raise ValueError(f"forecast artifact {paths['report.json']} is invalid") from error
        if artifact.id != artifact_id:
            raise ValueError(
                f"forecast artifact directory {artifact_id!r} contains report {artifact.id!r}"
            )
        if observed_report != _report_file(artifact):
            raise ValueError(f"forecast artifact {paths['report.json']} is not canonical")
        validate_price_forecast_artifact(artifact)
        expected = _expected_hashes(artifact)
        if dict(artifact.artifact_hashes) != expected:
            raise ValueError(f"forecast artifact {paths['report.json']} hash is invalid")
        canonical = {
            "paths.csv": _paths_csv(artifact.paths),
            "oos.csv": _oos_csv(artifact.oos),
        }
        for name, expected_bytes in canonical.items():
            try:
                observed = paths[name].read_bytes()
            except OSError as error:
                raise ValueError(f"forecast artifact {paths[name]} is unreadable") from error
            if observed != expected_bytes or _sha256(observed) != artifact.artifact_hashes[name]:
                raise ValueError(f"forecast artifact {paths[name]} does not match report.json")
        self.resolve_pin(artifact)
        return artifact

    def all(self) -> list[PriceForecastArtifact]:
        self._safe_root()
        if not self.root.exists():
            return []
        records: list[PriceForecastArtifact] = []
        for path in sorted(self.root.iterdir()):
            if path.name.startswith("."):
                raise ValueError(f"forecast registry contains partial entry {path}")
            if not path.is_dir() or _path_is_link_or_reparse(path):
                raise ValueError(f"forecast registry contains unsafe entry {path}")
            records.append(self.get(path.name))
        ids = [record.id for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError("forecast registry contains duplicate ids")
        return records
