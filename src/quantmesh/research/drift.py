"""M7 Phase E: drift and failure detection with evidence-disciplined
signal promotion (issue #43).

The drift surface is pure numpy — PSI and the two-sample KS statistic
with the Kolmogorov asymptotic p-value — so detection runs without the
research extra; the acceptance tests cross-check both against scipy.
Detection is fail-closed on data it cannot judge (short samples,
non-finite values, missing columns, an untrusted clock), while failure
detection runs *on* broken data — that is its job.

Alerts and promotions are append-only JSONL ledgers on the ADR-0006
discipline (atomic temp+replace appends, fail-closed reads with line
attribution, duplicate refusal). An alert's identity includes its
detection time: the same condition re-detected later is a new event
(monitoring semantics), while an identical replay is refused
(determinism semantics). A promotion pins the evidence, never the
outcome: the record links the full benchmark/ablation/OOS bundle and
its id is a pure function of that bundle, the signal name, and the
report-only kill-switch flag (enforcement is M10).
"""

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Generic, Literal, TypeVar

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from quantmesh.research.features import frame_digest
from quantmesh.research.reports import ID_PATTERN, Parameter, StrategyReport
from quantmesh.settings import settings

MIN_DRIFT_SAMPLES = 10
DRIFT_BINS = 10
PSI_EPSILON = 1e-6
ALERTS_FILE = "alerts.jsonl"
PROMOTIONS_FILE = "promotions.jsonl"
ALERT_KIND = Literal["feature_drift", "prediction_drift", "staleness", "failure"]

_T = TypeVar("_T", bound="BaseModel")


# ---------------------------------------------------------------------------
# Drift statistics — pure numpy, deterministic


def _as_float_sample(values: object, label: str) -> np.ndarray:
    """A 1-D finite float sample, or a typed refusal. Dates and strings
    are non-numeric, never silently coerced."""
    sample = np.asarray(values)
    if sample.ndim != 1:
        raise ValueError(f"{label} is not a 1-D sample (got {sample.ndim} dimensions)")
    if sample.dtype.kind not in "biuf":
        raise ValueError(f"{label} contains non-numeric values")
    sample = sample.astype(float)
    if not np.isfinite(sample).all():
        raise ValueError(f"{label} contains non-finite values")
    if len(sample) < MIN_DRIFT_SAMPLES:
        raise ValueError(
            f"short sample: {label} has {len(sample)} observations "
            f"(need at least {MIN_DRIFT_SAMPLES})"
        )
    return sample


def _bin_shares(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Counts per half-open bin over explicit edges. Values outside the
    edge range fall into the edge bins (searchsorted clips) instead of
    being dropped — a current distribution that shifted out of the
    reference range is exactly the drift we must not lose."""
    indices = np.clip(np.searchsorted(edges, values, side="right") - 1, 0, len(edges) - 2)
    counts = np.bincount(indices, minlength=len(edges) - 1)
    return counts.astype(float) / len(values)


def psi(reference: object, current: object, *, bins: int = DRIFT_BINS) -> float:
    """Population stability index of ``current`` against ``reference``.

    Bin edges come from the reference quantiles, so the reference
    shares are equal by construction; both share series are clamped to
    ``PSI_EPSILON`` so a bin the other sample empties still contributes
    a finite term. Fail-closed on short samples, non-finite values,
    and references too degenerate to split into distinct bins.
    """
    if bins < 2:
        raise ValueError(f"bins must be at least 2 (got {bins})")
    reference_values = _as_float_sample(reference, "the reference sample")
    current_values = _as_float_sample(current, "the current sample")
    edges = np.unique(np.quantile(reference_values, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 2:
        raise ValueError("the reference sample is degenerate: cannot split into bins")
    reference_shares = np.maximum(_bin_shares(reference_values, edges), PSI_EPSILON)
    current_shares = np.maximum(_bin_shares(current_values, edges), PSI_EPSILON)
    return float(
        np.sum((current_shares - reference_shares) * np.log(current_shares / reference_shares))
    )


def ks_statistic(reference: object, current: object) -> float:
    """Two-sample Kolmogorov-Smirnov statistic: the largest vertical gap
    between the empirical CDFs, evaluated at every pooled value (the sup
    over the line), pure numpy and exact."""
    a = np.sort(_as_float_sample(reference, "the reference sample"))
    b = np.sort(_as_float_sample(current, "the current sample"))
    pooled = np.sort(np.concatenate([a, b]))
    ecdf_a = np.searchsorted(a, pooled, side="right") / len(a)
    ecdf_b = np.searchsorted(b, pooled, side="right") / len(b)
    return float(np.max(np.abs(ecdf_a - ecdf_b)))


def ks_p_value(statistic: float, n_reference: int, n_current: int) -> float:
    """Two-sample KS p-value from the asymptotic Kolmogorov series.

    p = 2 * sum((−1)^(k−1) * exp(−2 k² λ²)) with λ = D sqrt(n1 n2 / (n1
    + n2)) — the textbook two-sample distribution, matching scipy's
    asymptotic mode (the acceptance test cross-checks it). The series
    diverges as λ → 0, so statistically unresolvable comparisons
    (λ < 0.1) are pinned to 1.0: an error below 1e-3 there can never
    trip a threshold. Non-finite statistics and short samples refuse.
    """
    if not math.isfinite(statistic):
        raise ValueError(f"non-finite KS statistic {statistic}")
    if n_reference < MIN_DRIFT_SAMPLES or n_current < MIN_DRIFT_SAMPLES:
        raise ValueError("short samples have no KS p-value")
    lam = statistic * math.sqrt(n_reference * n_current / (n_reference + n_current))
    if lam < 0.1:
        return 1.0
    total = 0.0
    sign = 1.0
    for k in range(1, 1001):
        term = math.exp(-2.0 * k * k * lam * lam)
        total += sign * term
        sign = -sign
        if term < 1e-12:
            break
    return min(1.0, max(0.0, 2.0 * total))


# ---------------------------------------------------------------------------
# Detection surface


class FeatureCheck(BaseModel):
    """One feature's drift evidence: PSI and KS against the reference."""

    feature: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    psi_value: float
    ks_statistic: float
    ks_p_value: float

    @model_validator(mode="after")
    def values_are_finite(self) -> "FeatureCheck":
        for name in ("psi_value", "ks_statistic", "ks_p_value"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"{name} is not finite ({value})")
        return self


class FeatureDriftReport(BaseModel):
    """Per-feature drift of a current frame against a pinned reference.

    The reference frame is the contract: the current frame must carry
    exactly the reference's columns — a missing feature is
    failure-detected by ``detect_failures``, never silently dropped
    from the test. ``flagged`` is derived from the thresholds and the
    record refuses a flagged list that contradicts its own checks.
    """

    reference_digest: str = Field(pattern=ID_PATTERN)
    psi_threshold: float = Field(default=0.25, gt=0)
    ks_alpha: float = Field(default=0.05, gt=0, le=1)
    checks: list[FeatureCheck]
    flagged: list[str]

    @model_validator(mode="after")
    def report_is_consistent(self) -> "FeatureDriftReport":
        names = [check.feature for check in self.checks]
        if names != sorted(names):
            raise ValueError("feature checks are not sorted by feature name")
        if len(set(names)) != len(names):
            raise ValueError("duplicate feature checks")
        expected = sorted(
            check.feature
            for check in self.checks
            if check.psi_value > self.psi_threshold or check.ks_p_value < self.ks_alpha
        )
        if self.flagged != expected:
            raise ValueError(
                f"flagged features {self.flagged} do not match the checks (expected {expected})"
            )
        return self


def detect_feature_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    psi_threshold: float = 0.25,
    ks_alpha: float = 0.05,
    bins: int = DRIFT_BINS,
) -> FeatureDriftReport:
    """Drift of every reference column in ``current`` (PSI and KS each).

    Fail-closed: empty frames, columns the current frame misses or
    adds, and any column that cannot support the statistics (short,
    non-finite, degenerate) refuse with the column named. The
    reference digest pins the reference frame on the report.
    """
    if reference.empty:
        raise ValueError("the reference frame is empty")
    if current.empty:
        raise ValueError("the current frame is empty")
    missing = sorted(set(reference.columns) - set(current.columns))
    if missing:
        raise ValueError(f"reference features missing from the current frame: {missing}")
    extra = sorted(set(current.columns) - set(reference.columns))
    if extra:
        raise ValueError(f"current frame carries features outside the reference: {extra}")
    digest = frame_digest({name: reference[name] for name in sorted(reference.columns)})
    checks: list[FeatureCheck] = []
    flagged: list[str] = []
    for name in sorted(reference.columns):
        try:
            statistic = ks_statistic(reference[name], current[name])
            psi_value = psi(reference[name], current[name], bins=bins)
            p_value = ks_p_value(statistic, len(reference[name]), len(current[name]))
        except ValueError as error:
            raise ValueError(f"feature {name!r}: {error}") from error
        check = FeatureCheck(
            feature=name,
            psi_value=psi_value,
            ks_statistic=statistic,
            ks_p_value=p_value,
        )
        checks.append(check)
        if psi_value > psi_threshold or p_value < ks_alpha:
            flagged.append(name)
    return FeatureDriftReport(
        reference_digest=digest,
        psi_threshold=psi_threshold,
        ks_alpha=ks_alpha,
        checks=checks,
        flagged=flagged,
    )


def _scores_digest(scores: np.ndarray) -> str:
    """Content hash of a score vector: the exact float reprs in order —
    a result-style identity for the reference window, like
    ``frame_digest`` for frames."""
    payload = " ".join(repr(float(value)) for value in scores)
    return hashlib.sha256(f"scores\0{payload}".encode()).hexdigest()[:16]


class PredictionDrift(BaseModel):
    """Score-distribution drift of live predictions against the training
    window (KS). ``training_digest`` pins the reference window's scores;
    ``drifted`` is derived from the p-value under ``ks_alpha``."""

    training_digest: str = Field(pattern=ID_PATTERN)
    ks_alpha: float = Field(default=0.05, gt=0, le=1)
    ks_statistic: float
    ks_p_value: float
    drifted: bool

    @model_validator(mode="after")
    def report_is_consistent(self) -> "PredictionDrift":
        for name in ("ks_statistic", "ks_p_value"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"{name} is not finite ({value})")
        if self.drifted != (self.ks_p_value < self.ks_alpha):
            raise ValueError(
                f"drifted {self.drifted} does not match the KS p-value "
                f"{self.ks_p_value} under alpha {self.ks_alpha}"
            )
        return self


def detect_prediction_drift(
    training_scores: object, live_scores: object, *, ks_alpha: float = 0.05
) -> PredictionDrift:
    """KS drift of live prediction scores against the training window's
    score distribution. Fail-closed on short or non-finite samples."""
    training = _as_float_sample(training_scores, "the training scores")
    live = _as_float_sample(live_scores, "the live scores")
    statistic = ks_statistic(training, live)
    p_value = ks_p_value(statistic, len(training), len(live))
    return PredictionDrift(
        training_digest=_scores_digest(training),
        ks_alpha=ks_alpha,
        ks_statistic=statistic,
        ks_p_value=p_value,
        drifted=p_value < ks_alpha,
    )


class StalenessCheck(BaseModel):
    """How old the feature input is, under the M5 stale-data discipline:
    a missing or future timestamp is a refusal, and ``stale`` follows
    the matcher's rule (``latest + max_age < now``)."""

    timestamp_column: str | None
    latest_timestamp: datetime
    now: datetime
    age: timedelta
    max_age: timedelta
    stale: bool

    @model_validator(mode="after")
    def check_is_consistent(self) -> "StalenessCheck":
        if self.latest_timestamp.tzinfo is None or self.now.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        self.latest_timestamp = self.latest_timestamp.astimezone(UTC)
        self.now = self.now.astimezone(UTC)
        if self.age != self.now - self.latest_timestamp:
            raise ValueError(
                f"age {self.age} does not match now minus latest "
                f"({self.now - self.latest_timestamp})"
            )
        if self.stale != ((self.latest_timestamp + self.max_age) < self.now):
            raise ValueError(f"stale {self.stale} does not match the age under {self.max_age}")
        return self


def detect_staleness(
    features: pd.DataFrame,
    *,
    timestamp_column: str | None = None,
    now: datetime,
    max_age: timedelta,
) -> StalenessCheck:
    """Staleness of the feature frame's latest timestamp.

    ``timestamp_column`` names the timestamp column; None (the default)
    uses the frame's DatetimeIndex — the natural shape of computed
    feature frames. Fail-closed, per the M5 stale-data discipline: an
    empty frame, a missing timestamp column, a missing (NaT) or
    unparseable timestamp, a naive timestamp, or a latest timestamp in
    the future (the clock or the feed is untrustworthy) all refuse.
    Stale means ``latest + max_age < now`` — the matcher's rule, strict
    at the boundary.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if features.empty:
        raise ValueError("cannot measure staleness on an empty frame")
    if timestamp_column is None:
        if not isinstance(features.index, pd.DatetimeIndex):
            raise ValueError(
                "the feature frame index is not datetime-like; pass timestamp_column"
            )
        index = features.index
    else:
        if timestamp_column not in features.columns:
            raise ValueError(f"features carry no {timestamp_column!r} column")
        try:
            index = pd.DatetimeIndex(pd.to_datetime(features[timestamp_column]))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{timestamp_column!r} does not parse as timestamps") from error
    if len(index) == 0:
        raise ValueError("features carry no timestamps")
    if index.tz is None:
        raise ValueError("timestamps must be timezone-aware")
    if index.isna().any():
        raise ValueError("features carry a missing timestamp")
    latest = index.tz_convert(UTC).max().to_pydatetime()
    if latest > now:
        raise ValueError(
            f"the latest timestamp {latest.isoformat()} is in the future "
            f"(now {now.isoformat()}); the clock or the feed is untrustworthy"
        )
    age = now - latest
    return StalenessCheck(
        timestamp_column=timestamp_column,
        latest_timestamp=latest,
        now=now,
        age=age,
        max_age=max_age,
        stale=(latest + max_age) < now,
    )


class FailureCheck(BaseModel):
    """Feature-input failures: missing features, NaN rows, coverage
    collapse. ``coverage_ratio`` is the share of rows with no NaN in
    any expected column (0.0 for an empty frame); ``collapsed`` fires
    below ``min_rows`` or at a NaN share of ``nan_threshold`` or more."""

    expected_columns: list[str]
    missing_features: list[str]
    nan_rows: int = Field(ge=0)
    total_rows: int = Field(ge=0)
    nan_threshold: float = Field(default=0.05, gt=0, le=1)
    min_rows: int = Field(default=1, ge=1)
    coverage_ratio: float = Field(ge=0, le=1)
    collapsed: bool

    @model_validator(mode="after")
    def check_is_consistent(self) -> "FailureCheck":
        if self.expected_columns != sorted(set(self.expected_columns)):
            raise ValueError("expected_columns must be sorted without duplicates")
        if self.missing_features != sorted(set(self.missing_features)):
            raise ValueError("missing_features must be sorted without duplicates")
        if not set(self.missing_features) <= set(self.expected_columns):
            raise ValueError("missing_features references a column outside expected_columns")
        expected_coverage = (
            (self.total_rows - self.nan_rows) / self.total_rows if self.total_rows else 0.0
        )
        if abs(self.coverage_ratio - expected_coverage) > 1e-9:
            raise ValueError(
                f"coverage_ratio {self.coverage_ratio} does not match "
                f"{self.total_rows} rows with {self.nan_rows} NaN"
            )
        expected_collapsed = self.total_rows < self.min_rows or (
            self.total_rows > 0 and self.nan_rows / self.total_rows >= self.nan_threshold
        )
        if self.collapsed != expected_collapsed:
            raise ValueError(
                f"collapsed {self.collapsed} does not match {self.total_rows} rows, "
                f"{self.nan_rows} NaN under min {self.min_rows} / "
                f"nan_threshold {self.nan_threshold}"
            )
        return self


def detect_failures(
    features: pd.DataFrame,
    *,
    expected_columns: set[str] | frozenset[str] | list[str],
    min_rows: int = 1,
    nan_threshold: float = 0.05,
) -> FailureCheck:
    """Failure detection over the feature frame — the one check that
    must run *on* broken data, so an empty or NaN-filled frame reports
    a collapse instead of refusing. Missing expected columns are named;
    NaN rows count rows with any NaN across the expected columns that
    are present."""
    expected = sorted(set(expected_columns))
    present = [name for name in expected if name in features.columns]
    missing = [name for name in expected if name not in features.columns]
    total_rows = len(features)
    nan_rows = int(features[present].isna().any(axis=1).sum()) if present and total_rows else 0
    coverage_ratio = (total_rows - nan_rows) / total_rows if total_rows else 0.0
    collapsed = total_rows < min_rows or (
        total_rows > 0 and nan_rows / total_rows >= nan_threshold
    )
    return FailureCheck(
        expected_columns=expected,
        missing_features=missing,
        nan_rows=nan_rows,
        total_rows=total_rows,
        nan_threshold=nan_threshold,
        min_rows=min_rows,
        coverage_ratio=coverage_ratio,
        collapsed=collapsed,
    )


# ---------------------------------------------------------------------------
# Alerts


def alert_id(
    *,
    kind: str,
    source: str,
    detected_at: datetime,
    observed: dict[str, Parameter],
) -> str:
    """Setup-only alert identity: kind, source, detection time, and the
    observed evidence under canonical sorted JSON. The detection time is
    part of the identity — a re-detection later is a new event; an
    identical replay is a duplicate (refused by the ledger)."""
    canonical = json.dumps(
        {
            "kind": kind,
            "source": source,
            "detected_at": detected_at.astimezone(UTC).isoformat(),
            "observed": observed,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"alert\0{canonical}".encode()).hexdigest()[:16]


class AlertRecord(BaseModel):
    """One detected condition on the alert ledger."""

    id: str = Field(pattern=ID_PATTERN)
    kind: ALERT_KIND
    source: str = Field(min_length=1)
    detected_at: datetime
    message: str = Field(min_length=1)
    observed: dict[str, Parameter] = Field(default_factory=dict)

    @field_validator("observed")
    @classmethod
    def observed_are_finite(cls, values: dict[str, Parameter]) -> dict[str, Parameter]:
        for name, value in values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"observed {name!r} is not finite ({value})")
        return values

    @model_validator(mode="after")
    def alert_is_consistent(self) -> "AlertRecord":
        if self.detected_at.tzinfo is None:
            raise ValueError("detected_at must be timezone-aware")
        self.detected_at = self.detected_at.astimezone(UTC)
        expected = alert_id(
            kind=self.kind,
            source=self.source,
            detected_at=self.detected_at,
            observed=self.observed,
        )
        if self.id != expected:
            raise ValueError(
                f"alert id {self.id!r} does not match its setup (expected {expected!r})"
            )
        return self


class DriftReport(BaseModel):
    """The composed drift surface: every check that ran plus the alerts
    the flagged conditions imply (unrecorded — ``record_report_alerts``
    persists them). A frame too broken for the drift test (fail-closed)
    still contributes its failure and staleness alerts."""

    generated_at: datetime
    feature: FeatureDriftReport | None = None
    prediction: PredictionDrift | None = None
    staleness: StalenessCheck | None = None
    failures: FailureCheck | None = None
    alerts: list[AlertRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def report_is_consistent(self) -> "DriftReport":
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        self.generated_at = self.generated_at.astimezone(UTC)
        return self


def _observed_alert(
    *, kind: str, source: str, detected_at: datetime, message: str, observed: dict[str, Parameter]
) -> AlertRecord:
    return AlertRecord(
        id=alert_id(kind=kind, source=source, detected_at=detected_at, observed=observed),
        kind=kind,
        source=source,
        detected_at=detected_at,
        message=message,
        observed=observed,
    )


def build_drift_report(
    *,
    feature: FeatureDriftReport | None = None,
    prediction: PredictionDrift | None = None,
    staleness: StalenessCheck | None = None,
    failures: FailureCheck | None = None,
    generated_at: datetime | None = None,
) -> DriftReport:
    """Assemble the composed report; alerts are derived from the flagged
    conditions: one per drifted feature, one per drifted prediction,
    one for staleness, and one per failure condition (missing, NaN,
    coverage — the coverage alert fires only when the collapse is not
    NaN-driven, so one root cause stays one alert)."""
    detected_at = generated_at if generated_at is not None else datetime.now(UTC)
    alerts: list[AlertRecord] = []
    if feature is not None:
        for check in feature.checks:
            if check.psi_value > feature.psi_threshold or check.ks_p_value < feature.ks_alpha:
                alerts.append(
                    _observed_alert(
                        kind="feature_drift",
                        source=f"feature:{check.feature}",
                        detected_at=detected_at,
                        message=(
                            f"feature {check.feature!r} drifted (PSI "
                            f"{check.psi_value:.4g} over {feature.psi_threshold:.4g} or KS p "
                            f"{check.ks_p_value:.4g} under {feature.ks_alpha:.4g})"
                        ),
                        observed={
                            "psi": check.psi_value,
                            "ks_statistic": check.ks_statistic,
                            "ks_p_value": check.ks_p_value,
                        },
                    )
                )
    if prediction is not None and prediction.drifted:
        alerts.append(
            _observed_alert(
                kind="prediction_drift",
                source=f"prediction:{prediction.training_digest}",
                detected_at=detected_at,
                message=(
                    f"live predictions drifted from the training window (KS p "
                    f"{prediction.ks_p_value:.4g} under {prediction.ks_alpha:.4g})"
                ),
                observed={
                    "ks_statistic": prediction.ks_statistic,
                    "ks_p_value": prediction.ks_p_value,
                },
            )
        )
    if staleness is not None and staleness.stale:
        alerts.append(
            _observed_alert(
                kind="staleness",
                source=f"features:{staleness.timestamp_column or 'index'}",
                detected_at=detected_at,
                message=(
                    f"feature input is stale: latest timestamp "
                    f"{staleness.latest_timestamp.isoformat()} is {staleness.age} old "
                    f"(max {staleness.max_age})"
                ),
                observed={
                    "latest_timestamp": staleness.latest_timestamp.isoformat(),
                    "age_s": staleness.age.total_seconds(),
                    "max_age_s": staleness.max_age.total_seconds(),
                },
            )
        )
    if failures is not None:
        if failures.missing_features:
            alerts.append(
                _observed_alert(
                    kind="failure",
                    source="features:missing",
                    detected_at=detected_at,
                    message=f"missing features: {failures.missing_features}",
                    observed={"missing_features": failures.missing_features},
                )
            )
        if failures.nan_rows:
            alerts.append(
                _observed_alert(
                    kind="failure",
                    source="features:nan",
                    detected_at=detected_at,
                    message=(
                        f"{failures.nan_rows} of {failures.total_rows} feature rows carry "
                        f"NaN (coverage {failures.coverage_ratio:.4g})"
                    ),
                    observed={
                        "nan_rows": failures.nan_rows,
                        "total_rows": failures.total_rows,
                        "coverage_ratio": failures.coverage_ratio,
                    },
                )
            )
        if failures.collapsed and not failures.nan_rows:
            alerts.append(
                _observed_alert(
                    kind="failure",
                    source="features:coverage",
                    detected_at=detected_at,
                    message=(
                        f"coverage collapsed: {failures.total_rows} rows below the "
                        f"{failures.min_rows}-row floor"
                    ),
                    observed={"total_rows": failures.total_rows, "min_rows": failures.min_rows},
                )
            )
    return DriftReport(
        generated_at=detected_at,
        feature=feature,
        prediction=prediction,
        staleness=staleness,
        failures=failures,
        alerts=alerts,
    )


def record_report_alerts(ledger: "AlertLedger", report: DriftReport) -> None:
    """Persist every derived alert; the ledger refuses duplicates — an
    identical replay of the same detection is the same event."""
    for alert in report.alerts:
        ledger.record(alert)


# ---------------------------------------------------------------------------
# Signal promotion


def promotion_id(
    *,
    signal_name: str,
    benchmark_report_ids: list[str],
    ablation_report_ids: list[str],
    oos_report_id: str,
    kill_switch: bool,
) -> str:
    """Setup-only promotion identity: the signal name and the full
    evidence bundle — never outcomes. The kill-switch flag is part of
    the setup: the same evidence under a gate is a different decision
    (report-only until M10 enforces it)."""
    canonical = json.dumps(
        {
            "signal_name": signal_name,
            "benchmark_report_ids": sorted(benchmark_report_ids),
            "ablation_report_ids": sorted(ablation_report_ids),
            "oos_report_id": oos_report_id,
            "kill_switch": kill_switch,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"promotion\0{canonical}".encode()).hexdigest()[:16]


def _sorted_report_ids(values: list[str], field_name: str) -> list[str]:
    for value in values:
        if not re.fullmatch(ID_PATTERN, value):
            raise ValueError(f"{field_name} contains a non-report id {value!r}")
    unique = sorted(set(values))
    if not unique:
        raise ValueError(
            f"{field_name} must be non-empty: the full evidence bundle requires at least one"
        )
    return unique


class PromotionEvidence(BaseModel):
    """The full evidence bundle a promotion requires: at least one
    benchmark report id, at least one ablation report id, and the OOS
    report id. A partial bundle is refused at construction — a
    promotion never records against incomplete evidence. Ids are kept
    sorted and deduplicated, so member order never changes identity."""

    benchmark_ids: list[str]
    ablation_ids: list[str]
    oos_report_id: str = Field(pattern=ID_PATTERN)

    @field_validator("benchmark_ids", "ablation_ids")
    @classmethod
    def ids_are_valid(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _sorted_report_ids(values, info.field_name)


def evidence_from_report(report: StrategyReport) -> PromotionEvidence:
    """The evidence bundle off a pipeline report: the benchmark and
    ablation ids recorded under ``evidence`` (issue #40) and the
    report's own id as the out-of-sample walk-forward evidence. A
    report without the full bundle — no benchmarks, no ablations, or
    no OOS windows — is refused: such a report cannot back a
    promotion."""
    benchmarks: list[str] = []
    ablations: list[str] = []
    for key, value in report.evidence.items():
        if key.startswith("benchmark:") or key.startswith("ablation:drop:"):
            if not isinstance(value, str):
                raise ValueError(f"evidence {key!r} is not a report id ({value!r})")
            if key.startswith("benchmark:"):
                benchmarks.append(value)
            else:
                ablations.append(value)
    if report.evidence.get("windows_oos") is not True:
        raise ValueError(
            f"report {report.id!r} has no out-of-sample windows; it cannot back a promotion"
        )
    return PromotionEvidence(
        benchmark_ids=benchmarks,
        ablation_ids=ablations,
        oos_report_id=report.id,
    )


class PromotionRecord(BaseModel):
    """One promoted signal. Identity pins the evidence bundle and the
    signal name — never the outcomes — so the same evidence is the same
    promotion, refused by the ledger even when ``promoted_at`` differs
    (like ``created_at`` on reports, it is a result, outside identity).
    The kill-switch flag is report-only until M10 enforces it."""

    id: str = Field(pattern=ID_PATTERN)
    signal_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    benchmark_report_ids: list[str]
    ablation_report_ids: list[str]
    oos_report_id: str = Field(pattern=ID_PATTERN)
    kill_switch: bool = False
    promoted_at: datetime

    @field_validator("benchmark_report_ids", "ablation_report_ids")
    @classmethod
    def ids_are_valid(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _sorted_report_ids(values, info.field_name)

    @model_validator(mode="after")
    def record_is_consistent(self) -> "PromotionRecord":
        if self.promoted_at.tzinfo is None:
            raise ValueError("promoted_at must be timezone-aware")
        self.promoted_at = self.promoted_at.astimezone(UTC)
        expected = promotion_id(
            signal_name=self.signal_name,
            benchmark_report_ids=self.benchmark_report_ids,
            ablation_report_ids=self.ablation_report_ids,
            oos_report_id=self.oos_report_id,
            kill_switch=self.kill_switch,
        )
        if self.id != expected:
            raise ValueError(
                f"promotion id {self.id!r} does not match its evidence (expected {expected!r})"
            )
        return self


def promote_signal(
    *,
    signal_name: str,
    evidence: PromotionEvidence,
    kill_switch: bool = False,
    ledger: "PromotionLedger | None" = None,
    promoted_at: datetime | None = None,
) -> PromotionRecord:
    """Promote a signal against its full evidence bundle and record the
    promotion. The bundle is required at the type level — a partial
    ``PromotionEvidence`` cannot even be constructed — and the ledger
    refuses a re-promotion of identical evidence (the same evidence is
    the same promotion). The kill-switch flag rides on the record,
    report-only: enforcement lands in M10."""
    record = PromotionRecord(
        id=promotion_id(
            signal_name=signal_name,
            benchmark_report_ids=evidence.benchmark_ids,
            ablation_report_ids=evidence.ablation_ids,
            oos_report_id=evidence.oos_report_id,
            kill_switch=kill_switch,
        ),
        signal_name=signal_name,
        benchmark_report_ids=evidence.benchmark_ids,
        ablation_report_ids=evidence.ablation_ids,
        oos_report_id=evidence.oos_report_id,
        kill_switch=kill_switch,
        promoted_at=promoted_at if promoted_at is not None else datetime.now(UTC),
    )
    ledger = ledger if ledger is not None else PromotionLedger()
    return ledger.record(record)


# ---------------------------------------------------------------------------
# Ledgers


class _JsonlLedger(Generic[_T]):
    """The ADR-0006 JSONL discipline, shared by the alert and promotion
    ledgers: atomic temp+replace appends, fail-closed reads with line
    attribution, duplicate-id refusal, and a root guard before any
    write. Subclasses pin the record type, file name, message kind, and
    default root."""

    _record_type: type[_T]
    _file_name: str
    _kind: str
    _default_dir: Path

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else self._default_dir

    @property
    def path(self) -> Path:
        return self.root / self._file_name

    def record(self, record: _T) -> _T:
        existing = self._read() if self.path.exists() else []
        if any(item.id == record.id for item in existing):
            raise ValueError(f"{self._kind} record {record.id!r} already recorded")
        self._append(record, existing)
        return record

    def get(self, record_id_value: str) -> _T:
        matches = [item for item in self._read() if item.id == record_id_value]
        if not matches:
            raise ValueError(f"no {self._kind} recorded with id {record_id_value!r}")
        return matches[0]

    def all(self) -> list[_T]:
        return self._read()

    def _append(self, record: _T, existing: list[_T]) -> None:
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise ValueError(f"{self._kind} ledger root {self.root} is not a directory")
        line = record.model_dump_json() + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=self.root,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            try:
                for item in existing:
                    handle.write(item.model_dump_json() + "\n")
                handle.write(line)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        os.replace(temporary, self.path)

    def _read(self) -> list[_T]:
        if not self.path.exists():
            return []
        if not self.path.is_file():
            raise ValueError(f"{self._kind} ledger path {self.path} is not a file")
        records: list[_T] = []
        with self.path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = self._record_type.model_validate_json(line)
                except Exception as error:  # noqa: BLE001 — attribution below
                    raise ValueError(
                        f"{self._kind} ledger {self.path} line {index} is invalid: {error}"
                    ) from error
                if any(item.id == record.id for item in records):
                    raise ValueError(
                        f"{self._kind} ledger {self.path} lines share a record id "
                        f"{record.id!r}"
                    )
                records.append(record)
        return records


class AlertLedger(_JsonlLedger[AlertRecord]):
    """Append-only JSONL ledger of detected conditions."""

    _record_type = AlertRecord
    _file_name = ALERTS_FILE
    _kind = "alert"
    _default_dir = settings.alerts_dir


class PromotionLedger(_JsonlLedger[PromotionRecord]):
    """Append-only JSONL ledger of promoted signals."""

    _record_type = PromotionRecord
    _file_name = PROMOTIONS_FILE
    _kind = "promotion"
    _default_dir = settings.promotions_dir
