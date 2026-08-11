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
import shutil
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

from pydantic import ValidationError

from quantmesh.data.lake import Dataset, Lake
from quantmesh.domain.models import InstrumentType
from quantmesh.instruments.contracts import (
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
MODEL_NAME = "median-log-drift-conformal"
BENCHMARK_NAME = "last-price-random-walk"
QUANTILES = (0.025, 0.10, 0.25, 0.75, 0.90, 0.975)
FILES = ("report.json", "paths.csv", "oos.csv")


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
            calibration_count=0,
            mae=0.0,
            rmse=0.0,
            benchmark_mae=0.0,
            coverage_50=0.0,
            coverage_80=0.0,
            coverage_95=0.0,
        )
    errors = [row.actual - row.predicted for row in rows]
    benchmark_errors = [row.actual - row.benchmark for row in rows]
    calibration_count, coverage_80 = _coverage(rows, "p10", "p90")
    _, coverage_50 = _coverage(rows, "p25", "p75")
    _, coverage_95 = _coverage(rows, "p025", "p975")
    return ForecastMetrics(
        sessions=horizon,
        residual_count=len(rows),
        calibration_count=calibration_count,
        mae=sum(abs(value) for value in errors) / len(errors),
        rmse=math.sqrt(sum(value * value for value in errors) / len(errors)),
        benchmark_mae=sum(abs(value) for value in benchmark_errors) / len(benchmark_errors),
        coverage_50=coverage_50,
        coverage_80=coverage_80,
        coverage_95=coverage_95,
    )


def _unexplained_session_gaps(series: HistoricalSeries) -> tuple[datetime, ...]:
    timestamps = tuple(bar.timestamp for bar in series.bars)
    continuous = series.instrument.instrument_type in {
        InstrumentType.SPOT,
        InstrumentType.PERPETUAL,
    }
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
    return _canonical_json(artifact.model_dump(mode="json", exclude={"artifact_hashes"}))


def _report_file(artifact: PriceForecastArtifact) -> bytes:
    return _canonical_json(artifact.model_dump(mode="json"))


def _expected_hashes(artifact: PriceForecastArtifact) -> dict[str, str]:
    # report.json pins the canonical report payload excluding the digest map
    # itself, avoiding an impossible self-referential file hash.
    return {
        "report.json": _sha256(_report_core(artifact)),
        "paths.csv": _sha256(_paths_csv(artifact.paths)),
        "oos.csv": _sha256(_oos_csv(artifact.oos)),
    }


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
    if any(bar.is_live_tail for bar in series.bars):
        raise ValueError("price forecast refuses a live-tail bar")
    if generated_at < series.bars[-1].timestamp:
        raise ValueError("generated_at cannot precede the last observed bar")

    continuous = series.instrument.instrument_type in {
        InstrumentType.SPOT,
        InstrumentType.PERPETUAL,
    }
    oos_by_horizon = {
        horizon: rolling_oos_forecasts(series.bars, horizon=horizon) for horizon in HORIZONS
    }
    metrics = tuple(_metrics(horizon, oos_by_horizon[horizon]) for horizon in HORIZONS)
    paths = tuple(
        _path(
            series.bars,
            horizon=horizon,
            residuals=[row.residual_log for row in oos_by_horizon[horizon]],
            continuous=continuous,
        )
        for horizon in HORIZONS
    )
    oos = tuple(row for horizon in HORIZONS for row in oos_by_horizon[horizon])

    blockers: list[str] = []
    if len(series.bars) < 315:
        blockers.append(f"history has {len(series.bars)} sessions; at least 315 are required")
    if series.gaps:
        blockers.append(f"history declares {len(series.gaps)} unexplained gap(s)")
    if series.duplicates:
        blockers.append(f"history declares {len(series.duplicates)} duplicate(s)")
    derived_gaps = _unexplained_session_gaps(series)
    if derived_gaps:
        blockers.append(
            f"history contains {len(derived_gaps)} unexplained weekday gap(s)"
            if not continuous
            else f"history contains {len(derived_gaps)} unexplained daily gap(s)"
        )
    required = {7: 30, 30: 30, 126: 12}
    for metric in metrics:
        minimum = required[metric.sessions]
        if metric.residual_count < minimum:
            blockers.append(
                f"{metric.sessions}-session horizon has {metric.residual_count} residuals; "
                f"at least {minimum} are required"
            )
        if metric.calibration_count == 0 or not 0.60 <= metric.coverage_80 <= 0.98:
            blockers.append(
                f"{metric.sessions}-session 80% coverage {metric.coverage_80:.6f} "
                "is outside [0.60, 0.98]"
            )
        if metric.residual_count and metric.mae > metric.benchmark_mae * 1.10:
            blockers.append(
                f"{metric.sessions}-session MAE {metric.mae:.6f} exceeds 110% of "
                f"benchmark MAE {metric.benchmark_mae:.6f}"
            )
    age = _session_age(series.bars[-1].timestamp, generated_at, continuous=continuous)
    if age > 1:
        blockers.append(f"artifact age is {age} sessions; it exceeds one session")

    config = {
        "benchmark": BENCHMARK_NAME,
        "coverage_gate": [0.60, 0.98],
        "horizons": list(HORIZONS),
        "model": MODEL_NAME,
        "residual_minimums": {str(key): value for key, value in required.items()},
        "return_window": RETURN_WINDOW,
    }
    config_digest = _sha256(_canonical_json(config))
    bar_digest = _sha256(
        _canonical_json(
            [
                [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
                for bar in series.bars
            ]
        )
    )
    identity = {
        "bar_digest": bar_digest,
        "config_digest": config_digest,
        "dataset": series.dataset_id,
        "generated_at": generated_at.isoformat(),
        "instrument": series.instrument.model_dump(mode="json"),
        "model_version": model_version,
        "revision": series.dataset_revision,
    }
    artifact_id = f"forecast-{_sha256(_canonical_json(identity))[:24]}"
    limitations = (
        "Prototype baseline uses weekday sessions for equities and does not "
        "model exchange holidays.",
        "Intervals are empirical and do not imply a probability of profit or execution outcome.",
        "The artifact is research evidence; the paper kernel remains the only order authority.",
    )
    common: dict[str, object] = {
        "id": artifact_id,
        "instrument": series.instrument,
        "dataset_id": series.dataset_id,
        "dataset_revision": series.dataset_revision,
        "source": series.source,
        "license": series.license,
        "generated_at": generated_at,
        "train_start": series.bars[0].timestamp,
        "train_end": series.bars[-1].timestamp,
        "model_name": MODEL_NAME,
        "model_version": model_version,
        "config_digest": config_digest,
        "benchmark_name": BENCHMARK_NAME,
        "paths": paths,
        "oos": oos,
        "metrics": metrics,
        "eligible": not blockers,
        "blockers": tuple(blockers),
        "limitations": limitations,
    }
    placeholder = PriceForecastArtifact(
        **common,
        artifact_hashes={name: "0" * 64 for name in FILES},
    )
    return PriceForecastArtifact(
        **common,
        artifact_hashes=_expected_hashes(placeholder),
    )


class PriceForecastRegistry:
    """Crash-safe append-only forecast directories with lake pin checks."""

    def __init__(self, root: Path | None = None, *, lake_root: Path | None = None) -> None:
        self.root = root if root is not None else settings.reports_dir / "forecasts"
        self.lake_root = lake_root if lake_root is not None else settings.lake_root

    def _safe_root(self) -> None:
        if self.root.exists() and (not self.root.is_dir() or self.root.is_symlink()):
            raise ValueError(f"forecast registry root {self.root} is not a safe directory")

    def resolve_pin(self, artifact: PriceForecastArtifact) -> Dataset:
        dataset = Lake(self.lake_root).dataset(artifact.dataset_id)
        if dataset.manifest.revision != artifact.dataset_revision:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} is now revision "
                f"{dataset.manifest.revision}, but the pin asks for revision "
                f"{artifact.dataset_revision}"
            )
        if dataset.manifest.source != artifact.source:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} source no longer matches the artifact pin"
            )
        if dataset.manifest.license != artifact.license:
            raise ValueError(
                f"dataset {artifact.dataset_id!r} license no longer matches the artifact pin"
            )
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
        if (
            coverage is None
            or coverage.start > artifact.train_start
            or coverage.end < artifact.train_end
        ):
            raise ValueError("dataset pin no longer covers the artifact training window")
        return dataset

    def record(self, artifact: PriceForecastArtifact) -> PriceForecastArtifact:
        self._safe_root()
        self.resolve_pin(artifact)
        expected = _expected_hashes(artifact)
        if dict(artifact.artifact_hashes) != expected:
            raise ValueError("forecast artifact hashes do not match its canonical payloads")
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / artifact.id
        if target.exists():
            raise ValueError(f"forecast artifact {artifact.id!r} already recorded")
        temp = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{artifact.id}.", suffix=".tmp"))
        try:
            (temp / "report.json").write_bytes(_report_file(artifact))
            (temp / "paths.csv").write_bytes(_paths_csv(artifact.paths))
            (temp / "oos.csv").write_bytes(_oos_csv(artifact.oos))
            os.replace(temp, target)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        return artifact

    def get(self, artifact_id: str) -> PriceForecastArtifact:
        if not artifact_id.startswith("forecast-") or len(artifact_id) != 33:
            raise ValueError("invalid forecast artifact id")
        self._safe_root()
        directory = self.root / artifact_id
        if not directory.exists() or not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"no forecast artifact recorded with id {artifact_id!r}")
        paths = {name: directory / name for name in FILES}
        for name, path in paths.items():
            if not path.is_file() or path.is_symlink():
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
            if not path.is_dir() or path.is_symlink():
                raise ValueError(f"forecast registry contains unsafe entry {path}")
            records.append(self.get(path.name))
        ids = [record.id for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError("forecast registry contains duplicate ids")
        return records
