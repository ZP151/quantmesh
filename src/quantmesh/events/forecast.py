"""Calibration forecast reports on the M5 report-stack discipline (issue #36).

A ``ForecastReport`` evaluates how well a venue's implied probabilities
calibrate to outcomes, in the same shape as the M5 ``StrategyReport``
(ADR-0005): a deterministic setup-only ``id`` over the pinned
universe of event markets, the count-based window spec and the bin
configuration; results and artifact paths ride along as outputs; the
registry persists records as JSONL with atomic appends, fail-closed
reads with line attribution, and duplicate ids refused.

Point-in-time replay is enforced by construction: each window's
metrics consume only its test observations (a contiguous tail of the
market's own timestamp-sorted observation grid, all at or before the
window's ``test_end``), and a resolution event participates only from
its ``resolved_at`` — an observation older than the resolution never
sees the outcome, even though the market resolved. Unresolved windows
report ``brier=None`` rather than a fabricated number, and a split
(multi-outcome) resolution is refused: a binary Brier needs a binary
resolution (the fractional-payoff case is a documented future
extension).

The train segment bounds the window structure (parity with the M5
walk-forward); a forecasting model trained on it is a future extension
— today's probabilities are the venue's own, so this report is an
*evaluation* of the market's implied prices.
"""

import csv
import hashlib
import json
import math
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from quantmesh._fs import atomic_replace
from quantmesh.events.calibration import (
    CalibrationBin,
    brier_by_bin,
    liquidity_weighted_brier,
)
from quantmesh.events.models import EventMarket
from quantmesh.settings import settings

__all__ = [
    "FORECASTS_FILE",
    "ForecastMarket",
    "ForecastObservation",
    "ForecastReport",
    "ForecastReportRegistry",
    "ForecastWindowResult",
    "ForecastWindowSpec",
    "MarketForecast",
    "forecast_artifact_paths",
    "forecast_report_id",
    "run_forecast",
    "run_forecast_report",
]

FORECASTS_FILE = "forecasts.jsonl"

ID_PATTERN = "^[0-9a-f]{16}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"

_N_BINS_MIN = 1
_N_BINS_MAX = 100


class ForecastObservation(BaseModel):
    """One point-in-time observation of a market's implied probability."""

    timestamp: datetime
    probability: float = Field(ge=0, le=1)
    liquidity_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "ForecastObservation":
        if self.timestamp.tzinfo is None:
            raise ValueError("observation timestamp must be timezone-aware")
        return self


class ForecastMarket(BaseModel):
    """One event market plus its timestamp-sorted observation grid."""

    market: EventMarket
    observations: list[ForecastObservation] = Field(min_length=1)

    @model_validator(mode="after")
    def observations_are_ordered(self) -> "ForecastMarket":
        for left, right in zip(self.observations, self.observations[1:]):
            if left.timestamp >= right.timestamp:
                raise ValueError(
                    f"market {self.market.venue_market_id!r}: observations must be "
                    "strictly ascending in time (a tie cannot be ordered point-in-time)"
                )
        return self


class ForecastWindowSpec(BaseModel):
    """Count-based evaluation windows over each market's observation grid.

    Mirrors the M5 ``WalkForwardSpec``: ``train_observations`` must be
    at least 2, ``step_observations`` at least ``test_observations`` so
    evaluation segments never overlap, and the split is calendar-free —
    a pinned grid pins the windows.
    """

    train_observations: int = Field(ge=2)
    test_observations: int = Field(ge=1)
    step_observations: int = Field(ge=1)

    @model_validator(mode="after")
    def segments_never_overlap(self) -> "ForecastWindowSpec":
        if self.step_observations < self.test_observations:
            raise ValueError(
                f"step_observations ({self.step_observations}) must be >= "
                f"test_observations ({self.test_observations})"
            )
        return self

    def test_starts(self, n_observations: int) -> list[int]:
        """Indices where each test segment begins in a grid of ``n``."""
        starts = []
        candidate = self.train_observations
        while candidate + self.test_observations <= n_observations:
            starts.append(candidate)
            candidate += self.step_observations
        if not starts:
            raise ValueError(
                f"grid of {n_observations} observations cannot host "
                f"{self.model_dump()}"
            )
        return starts


class ForecastWindowResult(BaseModel):
    """One evaluation segment's outcome over resolved observations."""

    index: int = Field(ge=0)
    train_end: datetime
    test_start: datetime
    test_end: datetime
    brier: float | None = Field(default=None, ge=0)
    liquidity_weighted_brier: float | None = Field(default=None, ge=0)
    calibration_bins: list[CalibrationBin] = Field(default_factory=list)
    n_observations: int = Field(ge=0)
    n_resolved: int = Field(ge=0)

    @field_validator("brier", "liquidity_weighted_brier")
    @classmethod
    def values_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError(f"window value must be finite, got {value}")
        return value

    @model_validator(mode="after")
    def timestamps_are_aware(self) -> "ForecastWindowResult":
        for name in ("train_end", "test_start", "test_end"):
            if getattr(self, name).tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        return self


class MarketForecast(BaseModel):
    """One market's latest probability and evaluation windows.

    The latest observation is retained alongside the evaluation output so
    operator surfaces can show the probability that was actually observed
    without reconstructing or inventing a current quote from a report that
    only contains historical windows.
    """

    market_id: str = Field(min_length=1)
    latest_probability: float | None = Field(default=None, ge=0, le=1)
    latest_probability_at: datetime | None = None
    latest_liquidity_confidence: float | None = Field(default=None, ge=0, le=1)
    windows: list[ForecastWindowResult] = Field(min_length=1)

    @model_validator(mode="after")
    def latest_timestamp_is_aware(self) -> "MarketForecast":
        if self.latest_probability_at is not None and self.latest_probability_at.tzinfo is None:
            raise ValueError("latest_probability_at must be timezone-aware")
        return self


def _market_identity(market: EventMarket) -> dict:
    """The setup surface of one market: identity, not state."""
    return {
        "venue": market.venue.value,
        "venue_market_id": market.venue_market_id,
        "event_ticker": market.event_ticker,
        "title": market.title,
        "category": market.category,
        "start_at": market.start_at.isoformat() if market.start_at else None,
        "expiry_at": market.expiry_at.isoformat() if market.expiry_at else None,
        "outcomes": [
            {"name": outcome.name, "venue_outcome_id": outcome.venue_outcome_id}
            for outcome in market.outcomes
        ],
        "resolution_rule": {
            "rule_text": market.resolution_rule.rule_text,
            "fingerprint": market.resolution_rule.fingerprint,
        },
        "resolution": market.resolution,
        "resolved_at": market.resolved_at.isoformat() if market.resolved_at else None,
    }


def forecast_report_id(
    *,
    commit: str,
    universe: list[EventMarket],
    window_spec: ForecastWindowSpec,
    n_bins: int,
) -> str:
    """Deterministic identity of a forecast report: setup only, never results.

    The universe hashes over its sorted member identities, so member
    order does not change the identity (ADR-0005 decision 2, applied to
    event markets).
    """
    setup = {
        "commit": commit,
        "universe": sorted(
            (_market_identity(market) for market in universe),
            key=lambda identity: (identity["venue"], identity["venue_market_id"]),
        ),
        "window_spec": window_spec.model_dump(),
        "n_bins": n_bins,
    }
    canonical = json.dumps(setup, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"forecast-report\0{canonical}".encode()).hexdigest()[:16]


def _outcome_value(market: EventMarket, timestamp: datetime) -> float | None:
    """The binary outcome observable at ``timestamp``, or None.

    Convention: ``outcomes[0]`` is the positive side and a resolution
    naming it is 1.0 (the Polymarket and Kalshi adapters always emit
    the YES/true outcome first). The resolution participates only from
    its own ``resolved_at``: before that instant the outcome is
    unknown even though the market is resolved today (the point-in-time
    replay rule, enforced here).
    """
    if not market.resolution:
        return None
    if len(market.resolution) > 1:
        raise ValueError(
            f"market {market.venue_market_id!r} has a split resolution "
            f"{market.resolution}; a binary Brier needs a binary resolution"
        )
    if market.resolved_at is None:
        raise ValueError(
            f"market {market.venue_market_id!r} is resolved but carries no "
            "resolved_at — a resolution without a timestamp cannot be "
            "replayed point-in-time"
        )
    if timestamp < market.resolved_at:
        return None
    return 1.0 if market.resolution[0] == market.outcomes[0].name else 0.0


def run_forecast(
    markets: list[ForecastMarket],
    *,
    window_spec: ForecastWindowSpec,
    n_bins: int = 10,
) -> tuple[dict[str, float | int | None], list[MarketForecast]]:
    """Evaluate every market's implied probabilities over the window spec.

    Returns (aggregate metrics, per-market windows). Pure: no I/O, no
    randomness, deterministic over its inputs.
    """
    if n_bins < _N_BINS_MIN or n_bins > _N_BINS_MAX:
        raise ValueError(f"n_bins must be in [{_N_BINS_MIN}, {_N_BINS_MAX}]")
    if not markets:
        raise ValueError("forecast needs at least one market")
    seen: set[tuple[str, str]] = set()
    for market in markets:
        key = (market.market.venue.value, market.market.venue_market_id)
        if key in seen:
            raise ValueError(f"universe lists {key} more than once")
        seen.add(key)

    per_market: list[MarketForecast] = []
    for entry in markets:
        market = entry.market
        windows: list[ForecastWindowResult] = []
        for index, test_start in enumerate(
            window_spec.test_starts(len(entry.observations))
        ):
            test = entry.observations[test_start : test_start + window_spec.test_observations]
            resolved_pairs = [
                (observation, outcome)
                for observation in test
                if (outcome := _outcome_value(market, observation.timestamp)) is not None
            ]
            predictions = [observation.probability for observation, _ in resolved_pairs]
            outcomes = [outcome for _, outcome in resolved_pairs]
            confidences = [
                observation.liquidity_confidence for observation, _ in resolved_pairs
            ]
            brier_value = None
            weighted = None
            bins: list[CalibrationBin] = []
            if resolved_pairs:
                brier_value = round(
                    sum((p - o) ** 2 for p, o in zip(predictions, outcomes))
                    / len(predictions),
                    6,
                )
                total_weight = sum(confidences)
                if total_weight > 0:
                    weighted = liquidity_weighted_brier(
                        predictions, outcomes, confidences
                    )
                # An all-zero-confidence window has no liquidity-weighted
                # estimate, only the plain one.
                bins = brier_by_bin(predictions, outcomes, n_bins)
            windows.append(
                ForecastWindowResult(
                    index=index,
                    train_end=entry.observations[test_start - 1].timestamp,
                    test_start=test[0].timestamp,
                    test_end=test[-1].timestamp,
                    brier=brier_value,
                    liquidity_weighted_brier=weighted,
                    calibration_bins=bins,
                    n_observations=len(test),
                    n_resolved=len(resolved_pairs),
                )
            )
        per_market.append(
            MarketForecast(
                market_id=f"{market.venue.value}:{market.venue_market_id}",
                latest_probability=entry.observations[-1].probability,
                latest_probability_at=entry.observations[-1].timestamp,
                latest_liquidity_confidence=entry.observations[-1].liquidity_confidence,
                windows=windows,
            )
        )

    evaluated = [w for market in per_market for w in market.windows if w.brier is not None]
    all_windows = [w for market in per_market for w in market.windows]
    metrics: dict[str, float | int | None] = {
        "n_windows_total": len(all_windows),
        "n_evaluated_windows": len(evaluated),
        "n_observations": sum(w.n_observations for w in all_windows),
        "n_resolved": sum(w.n_resolved for w in all_windows),
    }
    if evaluated:
        metrics["mean_brier"] = round(
            sum(w.brier for w in evaluated) / len(evaluated), 6
        )
        weighted_values = [
            w.liquidity_weighted_brier for w in evaluated if w.liquidity_weighted_brier is not None
        ]
        metrics["mean_liquidity_weighted_brier"] = (
            round(sum(weighted_values) / len(weighted_values), 6) if weighted_values else None
        )
    else:
        metrics["mean_brier"] = None
        metrics["mean_liquidity_weighted_brier"] = None
    return metrics, per_market


class ForecastReport(BaseModel):
    """One recorded forecast evaluation: pinned setup plus observed results."""

    id: str = Field(pattern=ID_PATTERN)
    commit: str = Field(pattern=COMMIT_PATTERN)
    universe: list[EventMarket] = Field(min_length=1)
    window_spec: ForecastWindowSpec
    n_bins: int = Field(ge=_N_BINS_MIN, le=_N_BINS_MAX)
    created_at: datetime
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    markets: list[MarketForecast] = Field(min_length=1)

    @field_validator("metrics")
    @classmethod
    def metrics_are_finite(
        cls, values: dict[str, float | int | None]
    ) -> dict[str, float | int | None]:
        for name, value in values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"metric {name!r} is not finite ({value})")
        return values

    @model_validator(mode="after")
    def report_is_consistent(self) -> "ForecastReport":
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        if len(self.markets) != len(self.universe):
            raise ValueError(
                f"{len(self.markets)} market evaluations for {len(self.universe)} "
                "universe members"
            )
        evaluated_ids = {market.market_id for market in self.markets}
        universe_ids = {
            f"{market.venue.value}:{market.venue_market_id}"
            for market in self.universe
        }
        if evaluated_ids != universe_ids:
            raise ValueError(
                f"evaluated markets {sorted(evaluated_ids)} disagree with the "
                f"universe {sorted(universe_ids)}"
            )
        expected = forecast_report_id(
            commit=self.commit,
            universe=self.universe,
            window_spec=self.window_spec,
            n_bins=self.n_bins,
        )
        if self.id != expected:
            raise ValueError(
                f"report id {self.id!r} does not match its pinned setup (expected {expected!r})"
            )
        return self


def forecast_artifact_paths(root: Path, report: ForecastReport) -> dict[str, Path]:
    """Deterministic artifact locations (ADR-0005 decision 7, applied)."""
    directory = root / report.id
    return {
        "report.json": directory / "report.json",
        "windows.csv": directory / "windows.csv",
        "calibration.csv": directory / "calibration.csv",
    }


def _write_artifacts(
    root: Path, report: ForecastReport
) -> None:
    """Write byte-stable artifacts; ``created_at`` is excluded so the
    same setup reproduces identical bytes across registry roots."""
    paths = forecast_artifact_paths(root, report)
    directory = paths["report.json"].parent
    directory.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude={"created_at"})
    paths["report.json"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with paths["windows.csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "market_id",
                "window_index",
                "train_end",
                "test_start",
                "test_end",
                "brier",
                "liquidity_weighted_brier",
                "n_observations",
                "n_resolved",
            ]
        )
        for market in report.markets:
            for window in market.windows:
                writer.writerow(
                    [
                        market.market_id,
                        window.index,
                        window.train_end.isoformat(),
                        window.test_start.isoformat(),
                        window.test_end.isoformat(),
                        "" if window.brier is None else window.brier,
                        (
                            ""
                            if window.liquidity_weighted_brier is None
                            else window.liquidity_weighted_brier
                        ),
                        window.n_observations,
                        window.n_resolved,
                    ]
                )
    with paths["calibration.csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "market_id",
                "window_index",
                "bin",
                "lo",
                "hi",
                "count",
                "mean_prediction",
                "observed_frequency",
                "brier",
            ]
        )
        for market in report.markets:
            for window in market.windows:
                for bin_row in window.calibration_bins:
                    writer.writerow(
                        [
                            market.market_id,
                            window.index,
                            bin_row.bin,
                            bin_row.lo,
                            bin_row.hi,
                            bin_row.count,
                            (
                                ""
                                if bin_row.mean_prediction is None
                                else bin_row.mean_prediction
                            ),
                            (
                                ""
                                if bin_row.observed_frequency is None
                                else bin_row.observed_frequency
                            ),
                            "" if bin_row.brier is None else bin_row.brier,
                        ]
                    )


class ForecastReportRegistry:
    """Append-only store of forecast reports under one registry root.

    Same discipline as the M5 ``ReportRegistry`` (atomic appends,
    fail-closed reads with line attribution, duplicate ids refused)
    minus the lake pin: a forecast report's setup *is* the recorded
    universe of event markets, so recording is the pin.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.reports_dir

    def record(self, report: ForecastReport) -> ForecastReport:
        existing = self.all()
        if any(record.id == report.id for record in existing):
            raise ValueError(f"forecast report {report.id!r} already recorded")
        self._append(report, existing)
        return report

    def get(self, report_id_value: str) -> ForecastReport:
        for report in self.all():
            if report.id == report_id_value:
                return report
        raise ValueError(f"no forecast report recorded with id {report_id_value!r}")

    def all(self) -> list[ForecastReport]:
        return self._read()

    def _append(self, report: ForecastReport, existing: list[ForecastReport]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / FORECASTS_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{FORECASTS_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in existing + [report]:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[ForecastReport]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"forecast registry root {self.root} is not a directory")
        path = self.root / FORECASTS_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"forecast registry {path} is unreadable") from error
        records = []
        seen: dict[str, int] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = ForecastReport.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(
                    f"forecast registry {path} line {line_number} is invalid"
                ) from error
            if record.id in seen:
                raise ValueError(
                    f"forecast registry {path} lines {seen[record.id]} and "
                    f"{line_number} share a report id"
                )
            seen[record.id] = line_number
            records.append(record)
        return records


def current_commit() -> str:
    """HEAD of the git repository the registry runs in; else fail closed."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise ValueError("cannot resolve the code commit; pass commit explicitly") from error
    if not head:
        raise ValueError("cannot resolve the code commit; pass commit explicitly")
    return head


def run_forecast_report(
    markets: list[ForecastMarket],
    *,
    window_spec: ForecastWindowSpec,
    n_bins: int = 10,
    commit: str | None = None,
    registry: ForecastReportRegistry | None = None,
) -> ForecastReport:
    """Evaluate, persist, and record one forecast report.

    The report ID is the hash of the setup (commit + pinned universe +
    window spec + bins); artifacts are written byte-stable under
    ``registry_root/<id>/`` and the record is appended to the registry.
    """
    registry = registry if registry is not None else ForecastReportRegistry()
    if commit is None:
        commit = current_commit()
    universe = [entry.market for entry in markets]
    metrics, per_market = run_forecast(markets, window_spec=window_spec, n_bins=n_bins)
    report = ForecastReport(
        id=forecast_report_id(
            commit=commit, universe=universe, window_spec=window_spec, n_bins=n_bins
        ),
        commit=commit,
        universe=universe,
        window_spec=window_spec,
        n_bins=n_bins,
        created_at=datetime.now(UTC),
        metrics=metrics,
        markets=per_market,
    )
    _write_artifacts(registry.root, report)
    registry.record(report)
    return report
