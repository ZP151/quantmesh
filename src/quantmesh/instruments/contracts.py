"""Strict API-ready contracts for venue-aware instrument history."""

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from quantmesh.data.layout import validate_dataset_name, validate_symbol
from quantmesh.data.manifest import SeriesCoverage
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import IDEMPOTENCY_KEY_PATTERN, Instrument, Side, Venue
from quantmesh.domain.orders import Order, OrderEventType, OrderStatus, OrderType
from quantmesh.live.contract import Provenance

AdjustmentMode = Literal["unadjusted", "split-adjusted", "total-return"]
_COMPARISON_KEY = re.compile(r"^[a-z0-9_-]+:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORECAST_ID_PATTERN = r"^forecast-[0-9a-f]{24}$"
_FORECAST_ID = re.compile(FORECAST_ID_PATTERN)
PROPOSAL_ID_PATTERN = r"^proposal-[0-9a-f]{24}$"
_PROPOSAL_ID = re.compile(PROPOSAL_ID_PATTERN)


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class StrictContract(BaseModel):
    """Shared fail-closed configuration for public response models."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )


class HistoryRange(StrEnum):
    """Supported chart windows and their stable wire values."""

    ONE_DAY = "1d"
    FIVE_DAYS = "5d"
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    ONE_YEAR = "1y"


class InstrumentSnapshot(Instrument):
    """Detached, deeply immutable view of the canonical Instrument schema."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )

    metadata: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_is_detached(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @field_serializer("metadata")
    def serialize_metadata(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)


class CoverageSnapshot(SeriesCoverage):
    """Detached, frozen UTC view of canonical manifest coverage."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )

    @field_validator("start", "end", mode="before")
    @classmethod
    def json_coverage_times_are_parsed(cls, value: object, info) -> object:
        if info.mode == "json" and isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("start", "end")
    @classmethod
    def coverage_times_are_utc(cls, value: datetime, info) -> datetime:
        return _utc(value, info.field_name)


def _instrument_snapshot(value: object) -> object:
    if not isinstance(value, Instrument):
        return value
    return InstrumentSnapshot(
        symbol=value.symbol,
        venue=value.venue,
        instrument_type=value.instrument_type,
        currency=value.currency,
        metadata=dict(value.metadata),
    )


def _coverage_snapshot(value: object) -> object:
    if not isinstance(value, SeriesCoverage):
        return value
    return CoverageSnapshot(
        interval=value.interval,
        venue=value.venue,
        symbol=value.symbol,
        start=value.start,
        end=value.end,
        rows=value.rows,
    )


class DatasetBinding(StrictContract):
    """Route one venue/symbol/resolution to a manifest-gated dataset ID.

    The exact spelling ``24/7`` is the only calendar declared continuous for
    fixed-grid gap detection. Every other calendar is treated as session-based.
    """

    dataset_id: str
    interval: str
    venue: Venue
    symbol: str
    calendar: str = Field(min_length=1)
    adjustment: AdjustmentMode = "unadjusted"

    @field_validator("dataset_id")
    @classmethod
    def dataset_id_is_canonical(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator("interval")
    @classmethod
    def interval_is_canonical(cls, value: str) -> str:
        interval_to_timedelta(value)
        return value

    @field_validator("symbol")
    @classmethod
    def symbol_is_canonical(cls, value: str) -> str:
        validate_symbol(value)
        return value

    @field_validator("calendar")
    @classmethod
    def calendar_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("calendar must not be blank")
        return value


class LiveTailLineage(StrictContract):
    """Positive, point-in-time evidence attached only to a live-tail bar."""

    source: str = Field(min_length=1)
    venue: Venue
    instrument: str
    provenance: Literal[Provenance.REAL, Provenance.DELAYED]
    data_time: datetime
    received_at: datetime
    interval: str
    sequence: int = Field(ge=0)
    predecessor_sequence: int = Field(ge=0)
    predecessor_data_time: datetime
    sequence_gap: Literal[False]
    continuity_proven: Literal[True]
    freshness_label: Literal["real", "delayed"]
    age_ms: int = Field(ge=0)

    @field_validator("source")
    @classmethod
    def source_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must not be blank")
        return value

    @field_validator("instrument")
    @classmethod
    def instrument_is_canonical(cls, value: str) -> str:
        validate_symbol(value)
        return value

    @field_validator("data_time", "received_at", "predecessor_data_time")
    @classmethod
    def lineage_times_are_utc(cls, value: datetime, info) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("interval")
    @classmethod
    def interval_is_canonical(cls, value: str) -> str:
        interval_to_timedelta(value)
        return value

    @model_validator(mode="after")
    def freshness_matches_provenance(self) -> "LiveTailLineage":
        if self.freshness_label != self.provenance.value:
            raise ValueError("freshness_label must match live provenance")
        duration = interval_to_timedelta(self.interval)
        same_bar = self.data_time == self.predecessor_data_time
        next_bar = self.data_time == self.predecessor_data_time + duration
        if not (same_bar or next_bar):
            raise ValueError(
                "live lineage data_time must be the same or exactly one interval "
                "after its predecessor"
            )
        if same_bar and self.sequence < self.predecessor_sequence:
            raise ValueError("same-bar live lineage sequence must be non-regressive")
        if next_bar and self.sequence <= self.predecessor_sequence:
            raise ValueError("next-bar live lineage sequence must advance")
        return self


class HistoricalBar(StrictContract):
    """One observed OHLCV bar returned by the history service."""

    instrument: InstrumentSnapshot
    timestamp: datetime
    interval: str
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    adjusted_close: float | None = Field(default=None, gt=0)
    is_live_tail: bool = False
    live_lineage: LiveTailLineage | None = None

    @field_validator("instrument", mode="before")
    @classmethod
    def instrument_is_a_detached_snapshot(cls, value: object) -> object:
        return _instrument_snapshot(value)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "timestamp")

    @field_validator("interval")
    @classmethod
    def interval_is_canonical(cls, value: str) -> str:
        interval_to_timedelta(value)
        return value

    @model_validator(mode="after")
    def candle_is_consistent(self) -> "HistoricalBar":
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.is_live_tail != (self.live_lineage is not None):
            raise ValueError("is_live_tail must be true if and only if live_lineage exists")
        if self.live_lineage is not None and (
            self.live_lineage.venue != self.instrument.venue
            or self.live_lineage.instrument != self.instrument.symbol
            or self.live_lineage.data_time != self.timestamp
            or self.live_lineage.interval != self.interval
        ):
            raise ValueError("live_lineage must match the bar instrument, timestamp, and interval")
        return self


class HistoricalSeries(StrictContract):
    """Observed history and the exact manifest provenance used to read it."""

    instrument: InstrumentSnapshot
    range: HistoryRange
    as_of: datetime
    bars: tuple[HistoricalBar, ...] = Field(min_length=1)
    dataset_id: str
    dataset_revision: int = Field(ge=1)
    source: str = Field(min_length=1)
    license: str = Field(min_length=1)
    generated_at: datetime
    interval: str
    calendar: str = Field(min_length=1)
    adjustment: AdjustmentMode
    coverage: CoverageSnapshot
    coverage_scope: Literal["historical-only"] = "historical-only"
    gaps: tuple[datetime, ...] = Field(default_factory=tuple)
    duplicates: tuple[datetime, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)
    resolution_fallback: str | None = None

    @field_validator("instrument", mode="before")
    @classmethod
    def instrument_is_a_detached_snapshot(cls, value: object) -> object:
        return _instrument_snapshot(value)

    @field_validator("coverage", mode="before")
    @classmethod
    def coverage_is_a_detached_snapshot(cls, value: object) -> object:
        return _coverage_snapshot(value)

    @field_validator("dataset_id")
    @classmethod
    def dataset_id_is_canonical(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator("interval")
    @classmethod
    def interval_is_canonical(cls, value: str) -> str:
        interval_to_timedelta(value)
        return value

    @field_validator("as_of", "generated_at")
    @classmethod
    def provenance_times_are_utc(cls, value: datetime, info) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("gaps", "duplicates")
    @classmethod
    def quality_times_are_utc(cls, value: tuple[datetime, ...], info) -> tuple[datetime, ...]:
        normalized = tuple(_utc(item, info.field_name) for item in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError(f"{info.field_name} must be unique and chronological")
        return normalized

    @field_validator("limitations")
    @classmethod
    def limitations_are_unique_and_nonblank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("limitations must be non-blank and unique")
        return value

    @field_validator("resolution_fallback")
    @classmethod
    def fallback_is_explicit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split("->")
        if len(parts) != 2:
            raise ValueError("resolution_fallback must be '<preferred>-><selected>'")
        preferred, selected = parts
        if interval_to_timedelta(selected) <= interval_to_timedelta(preferred):
            raise ValueError("resolution_fallback must select a coarser interval")
        return value

    @model_validator(mode="after")
    def observed_series_is_self_consistent(self) -> "HistoricalSeries":
        identity = (self.instrument.venue, self.instrument.symbol)
        live_indices = [index for index, item in enumerate(self.bars) if item.is_live_tail]
        if len(live_indices) > 1:
            raise ValueError("series may contain at most one live-tail bar")
        if live_indices and live_indices[0] != len(self.bars) - 1:
            raise ValueError("live-tail bar must be final")
        timestamps = [item.timestamp for item in self.bars]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            raise ValueError("bars must be strictly chronological and unique")
        if any((item.instrument.venue, item.instrument.symbol) != identity for item in self.bars):
            raise ValueError("bars must preserve one venue/symbol identity")
        if any(item.interval != self.interval for item in self.bars):
            raise ValueError("bars must use the selected interval")
        if any(item.timestamp > self.as_of for item in self.bars):
            raise ValueError("historical bars cannot contain future leakage")
        if (
            self.coverage.interval != self.interval
            or self.coverage.venue != self.instrument.venue
            or self.coverage.symbol != self.instrument.symbol
        ):
            raise ValueError("coverage must describe the returned series")
        if any(
            not item.is_live_tail
            and not (self.coverage.start <= item.timestamp <= self.coverage.end)
            for item in self.bars
        ):
            raise ValueError("historical bars must remain inside manifest coverage")
        for item in self.bars:
            if item.live_lineage is None:
                continue
            if item.live_lineage.received_at > self.as_of:
                raise ValueError("live lineage received_at must not exceed series as_of")
            expected_age_ms = int(
                (self.as_of - item.live_lineage.received_at).total_seconds() * 1000
            )
            if item.live_lineage.age_ms != expected_age_ms:
                raise ValueError("live lineage age_ms must exactly equal as_of minus received_at")
        return self


class ComparisonPoint(StrictContract):
    """Normalized closes for one timestamp shared by every comparison series."""

    timestamp: datetime
    values: Mapping[str, float] = Field(min_length=1)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "timestamp")

    @field_validator("values")
    @classmethod
    def values_are_finite_and_keyed(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        if any(_COMPARISON_KEY.fullmatch(key) is None for key in value):
            raise ValueError("comparison keys must use 'venue:symbol'")
        if any(not math.isfinite(item) or item <= 0 for item in value.values()):
            raise ValueError("comparison values must be finite and positive")
        return MappingProxyType(dict(value))

    @field_serializer("values")
    def serialize_values(self, value: Mapping[str, float]) -> dict[str, float]:
        return dict(value)


class ComparisonSeries(StrictContract):
    """Close-price comparison over the exact shared observed timestamps."""

    range: HistoryRange
    as_of: datetime
    keys: tuple[str, ...] = Field(min_length=2)
    points: tuple[ComparisonPoint, ...] = Field(min_length=2)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("as_of")
    @classmethod
    def as_of_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "as_of")

    @field_validator("keys")
    @classmethod
    def keys_are_stable_and_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("comparison keys must be unique")
        if any(_COMPARISON_KEY.fullmatch(key) is None for key in value):
            raise ValueError("comparison keys must use 'venue:symbol'")
        return value

    @field_validator("limitations")
    @classmethod
    def limitations_are_unique_and_nonblank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("limitations must be non-blank and unique")
        return value

    @model_validator(mode="after")
    def points_match_the_declared_key_order(self) -> "ComparisonSeries":
        timestamps = [point.timestamp for point in self.points]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            raise ValueError("comparison points must be strictly chronological and unique")
        if any(tuple(point.values) != self.keys for point in self.points):
            raise ValueError("comparison point values must follow the declared key order")
        if any(point.timestamp > self.as_of for point in self.points):
            raise ValueError("comparison points cannot contain future leakage")
        return self


class ForecastPoint(StrictContract):
    """One future session and its ordered price quantiles."""

    session: int = Field(ge=1)
    timestamp: datetime
    p025: float = Field(gt=0)
    p10: float = Field(gt=0)
    p25: float = Field(gt=0)
    p50: float = Field(gt=0)
    p75: float = Field(gt=0)
    p90: float = Field(gt=0)
    p975: float = Field(gt=0)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "timestamp")

    @model_validator(mode="after")
    def quantiles_are_ordered(self) -> "ForecastPoint":
        values = (
            self.p025,
            self.p10,
            self.p25,
            self.p50,
            self.p75,
            self.p90,
            self.p975,
        )
        if tuple(sorted(values)) != values:
            raise ValueError("forecast price quantiles must be ordered")
        return self


class ForecastPath(StrictContract):
    """A complete price path for one predeclared horizon."""

    sessions: Literal[7, 30, 126]
    points: tuple[ForecastPoint, ...]

    @model_validator(mode="after")
    def path_matches_horizon(self) -> "ForecastPath":
        if len(self.points) != self.sessions:
            raise ValueError("forecast path length must match sessions")
        if tuple(point.session for point in self.points) != tuple(range(1, self.sessions + 1)):
            raise ValueError("forecast path sessions must be contiguous from one")
        timestamps = tuple(point.timestamp for point in self.points)
        if timestamps != tuple(sorted(set(timestamps))):
            raise ValueError("forecast path timestamps must be unique and chronological")
        return self


class OOSForecast(StrictContract):
    """One chronological out-of-sample point prediction and outcome."""

    sessions: Literal[7, 30, 126]
    origin_at: datetime
    target_at: datetime
    predicted: float = Field(gt=0)
    benchmark: float = Field(gt=0)
    actual: float = Field(gt=0)
    residual_log: float
    p025: float | None = Field(default=None, gt=0)
    p10: float | None = Field(default=None, gt=0)
    p25: float | None = Field(default=None, gt=0)
    p75: float | None = Field(default=None, gt=0)
    p90: float | None = Field(default=None, gt=0)
    p975: float | None = Field(default=None, gt=0)

    @field_validator("origin_at", "target_at")
    @classmethod
    def oos_times_are_utc(cls, value: datetime, info) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def oos_row_is_consistent(self) -> "OOSForecast":
        if self.target_at <= self.origin_at:
            raise ValueError("OOS target must be after its origin")
        expected = math.log(self.actual / self.predicted)
        if not math.isclose(self.residual_log, expected, rel_tol=0, abs_tol=1e-12):
            raise ValueError("OOS residual_log must equal log(actual / predicted)")
        intervals = (
            self.p025,
            self.p10,
            self.p25,
            self.p75,
            self.p90,
            self.p975,
        )
        if any(value is None for value in intervals):
            if any(value is not None for value in intervals):
                raise ValueError("OOS interval quantiles must be all present or all absent")
        else:
            present = tuple(value for value in intervals if value is not None)
            if not (
                present[0]
                <= present[1]
                <= present[2]
                <= self.predicted
                <= present[3]
                <= present[4]
                <= present[5]
            ):
                raise ValueError("OOS interval quantiles must surround the prediction")
        return self


class ForecastMetrics(StrictContract):
    """Promotion evidence for one horizon."""

    sessions: Literal[7, 30, 126]
    residual_count: int = Field(ge=0)
    interval_test_count: int = Field(ge=0)
    validation_start: datetime | None = None
    validation_end: datetime | None = None
    test_start: datetime | None = None
    test_end: datetime | None = None
    mae: float = Field(ge=0)
    rmse: float = Field(ge=0)
    benchmark_mae: float = Field(ge=0)
    coverage_50: float = Field(ge=0, le=1)
    coverage_80: float = Field(ge=0, le=1)
    coverage_95: float = Field(ge=0, le=1)

    @field_validator("validation_start", "validation_end", "test_start", "test_end")
    @classmethod
    def metric_times_are_utc(cls, value: datetime | None, info) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def boundaries_and_counts_are_consistent(self) -> "ForecastMetrics":
        if self.interval_test_count > self.residual_count:
            raise ValueError("interval_test_count cannot exceed residual_count")
        validation_present = self.validation_start is not None or self.validation_end is not None
        if validation_present != (self.residual_count > 0):
            raise ValueError("validation boundaries must exist exactly when residuals exist")
        if (
            self.validation_start is not None
            and self.validation_end is not None
            and self.validation_start > self.validation_end
        ):
            raise ValueError("validation_start cannot be after validation_end")
        test_present = self.test_start is not None or self.test_end is not None
        if test_present != (self.interval_test_count > 0):
            raise ValueError("test boundaries must exist exactly when interval tests exist")
        if (
            self.test_start is not None
            and self.test_end is not None
            and self.test_start > self.test_end
        ):
            raise ValueError("test_start cannot be after test_end")
        return self


class PriceForecastArtifact(StrictContract):
    """Replayable forecast evidence; eligibility is data, never an assertion."""

    id: str
    instrument: InstrumentSnapshot
    dataset_id: str
    dataset_revision: int = Field(ge=1)
    source: str = Field(min_length=1)
    license: str = Field(min_length=1)
    dataset_generated_at: datetime
    coverage: CoverageSnapshot
    calendar: str = Field(min_length=1)
    adjustment: AdjustmentMode
    target: Literal["unadjusted-close", "split-adjusted-close", "total-return-close"]
    history_start: datetime
    history_sessions: int = Field(ge=1)
    history_digest: str
    gap_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    age_sessions: int = Field(ge=0)
    generated_at: datetime
    train_start: datetime
    train_end: datetime
    validation_start: datetime | None = None
    validation_end: datetime | None = None
    test_start: datetime | None = None
    test_end: datetime | None = None
    model_name: Literal["median-log-drift-conformal"]
    model_version: str = Field(min_length=1)
    config_digest: str
    benchmark_name: Literal["last-price-random-walk"]
    paths: tuple[ForecastPath, ...]
    oos: tuple[OOSForecast, ...]
    metrics: tuple[ForecastMetrics, ...]
    eligible: bool
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(min_length=1)
    artifact_hashes: Mapping[str, str]

    @field_validator("id")
    @classmethod
    def id_is_canonical(cls, value: str) -> str:
        if _FORECAST_ID.fullmatch(value) is None:
            raise ValueError("forecast id must be forecast- plus 24 lowercase hex characters")
        return value

    @field_validator("instrument", mode="before")
    @classmethod
    def instrument_is_a_detached_snapshot(cls, value: object) -> object:
        return _instrument_snapshot(value)

    @field_validator("dataset_id")
    @classmethod
    def dataset_id_is_canonical(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator(
        "history_start",
        "dataset_generated_at",
        "generated_at",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
    )
    @classmethod
    def artifact_times_are_utc(cls, value: datetime | None, info) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @field_validator("coverage", mode="before")
    @classmethod
    def coverage_is_a_detached_snapshot(cls, value: object) -> object:
        return _coverage_snapshot(value)

    @field_validator("source", "license", "model_version")
    @classmethod
    def lineage_strings_are_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @field_validator("config_digest", "history_digest")
    @classmethod
    def config_digest_is_sha256(cls, value: str) -> str:
        if _SHA256.fullmatch(value) is None:
            raise ValueError("config_digest must be lowercase sha256")
        return value

    @field_validator("blockers", "limitations")
    @classmethod
    def messages_are_unique_and_nonblank(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError(f"{info.field_name} must be non-blank and unique")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def hashes_are_complete_and_immutable(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        expected = {"report.json", "paths.csv", "oos.csv"}
        if set(value) != expected:
            raise ValueError(f"artifact_hashes must contain exactly {sorted(expected)}")
        if any(_SHA256.fullmatch(digest) is None for digest in value.values()):
            raise ValueError("artifact hashes must be lowercase sha256")
        return MappingProxyType(dict(value))

    @field_serializer("artifact_hashes")
    def serialize_hashes(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @model_validator(mode="after")
    def artifact_is_self_consistent(self) -> "PriceForecastArtifact":
        if (
            self.history_start > self.train_start
            or self.train_start > self.train_end
            or self.generated_at < self.train_end
            or self.generated_at < self.dataset_generated_at
        ):
            raise ValueError("forecast training and generation times are inconsistent")
        if self.adjustment != "unadjusted":
            raise ValueError("forecast artifacts currently support unadjusted close only")
        expected_target = f"{self.adjustment}-close"
        if self.target != expected_target:
            raise ValueError("forecast target must match the recorded adjustment mode")
        if (
            self.coverage.interval != "1d"
            or self.coverage.venue != self.instrument.venue
            or self.coverage.symbol != self.instrument.symbol
            or self.coverage.start > self.history_start
            or self.coverage.end < self.train_end
        ):
            raise ValueError("forecast coverage must contain its daily training history")
        if tuple(path.sessions for path in self.paths) != (7, 30, 126):
            raise ValueError("forecast paths must be ordered 7, 30, 126")
        if tuple(metric.sessions for metric in self.metrics) != (7, 30, 126):
            raise ValueError("forecast metrics must be ordered 7, 30, 126")
        oos_order = tuple((row.sessions, row.origin_at, row.target_at) for row in self.oos)
        if oos_order != tuple(sorted(oos_order)):
            raise ValueError("OOS rows must be ordered by horizon, origin, target")
        counts = {horizon: 0 for horizon in (7, 30, 126)}
        for row in self.oos:
            counts[row.sessions] += 1
        if any(metric.residual_count != counts[metric.sessions] for metric in self.metrics):
            raise ValueError("metric residual counts must match OOS rows")
        for path in self.paths:
            if any(point.timestamp <= self.train_end for point in path.points):
                raise ValueError("forecast path timestamps must be after train_end")
        validation_targets = tuple(row.target_at for row in self.oos)
        expected_validation = (
            (min(validation_targets), max(validation_targets))
            if validation_targets
            else (None, None)
        )
        if (self.validation_start, self.validation_end) != expected_validation:
            raise ValueError("artifact validation boundaries must match OOS targets")
        test_targets = tuple(row.target_at for row in self.oos if row.p10 is not None)
        expected_test = (min(test_targets), max(test_targets)) if test_targets else (None, None)
        if (self.test_start, self.test_end) != expected_test:
            raise ValueError("artifact test boundaries must match interval-tested targets")
        if self.eligible != (not self.blockers):
            raise ValueError("eligible must be true if and only if blockers are empty")
        return self


class ProposalStatus(StrEnum):
    """Append-only paper proposal lifecycle."""

    PENDING = "pending"
    BLOCKED = "blocked"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class PaperProposal(StrictContract):
    """Immutable forecast-to-paper intent; creation never places an order."""

    id: str
    artifact_id: str
    instrument: InstrumentSnapshot
    dataset_id: str
    dataset_revision: int = Field(ge=1)
    forecast_generated_at: datetime
    model_version: str = Field(min_length=1)
    config_digest: str
    history_digest: str
    side: Side
    quantity: float = Field(gt=0)
    order_type: OrderType
    limit_price: float | None = Field(default=None, gt=0)
    created_at: datetime
    confirmation_token: str
    status: ProposalStatus
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    order_id: str | None = None
    quote_provenance: Literal["real", "demo-synthetic"] | None = None

    @field_validator("id")
    @classmethod
    def id_is_canonical(cls, value: str) -> str:
        if _PROPOSAL_ID.fullmatch(value) is None:
            raise ValueError("proposal id must be proposal- plus 24 lowercase hex characters")
        return value

    @field_validator("artifact_id")
    @classmethod
    def artifact_id_is_canonical(cls, value: str) -> str:
        if _FORECAST_ID.fullmatch(value) is None:
            raise ValueError("artifact_id is not a canonical forecast id")
        return value

    @field_validator("instrument", mode="before")
    @classmethod
    def instrument_is_a_detached_snapshot(cls, value: object) -> object:
        return _instrument_snapshot(value)

    @field_validator("dataset_id")
    @classmethod
    def dataset_id_is_canonical(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator("forecast_generated_at", "created_at")
    @classmethod
    def proposal_times_are_utc(cls, value: datetime, info) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("config_digest", "history_digest", "confirmation_token")
    @classmethod
    def digests_are_sha256(cls, value: str, info) -> str:
        if _SHA256.fullmatch(value) is None:
            raise ValueError(f"{info.field_name} must be lowercase sha256")
        return value

    @field_validator("blockers")
    @classmethod
    def blockers_are_unique_and_nonblank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("proposal blockers must be non-blank and unique")
        return value

    @model_validator(mode="after")
    def proposal_state_is_consistent(self) -> "PaperProposal":
        if self.created_at < self.forecast_generated_at:
            raise ValueError("proposal cannot predate its forecast artifact")
        if (self.order_type is OrderType.LIMIT) != (self.limit_price is not None):
            raise ValueError("proposal order_type must match limit_price presence")
        if self.status is ProposalStatus.PENDING:
            if self.blockers or self.order_id is not None or self.quote_provenance is not None:
                raise ValueError("pending proposal cannot carry blockers or order evidence")
        elif self.status is ProposalStatus.BLOCKED:
            if not self.blockers or self.order_id is not None or self.quote_provenance is not None:
                raise ValueError("blocked proposal requires blockers and no order evidence")
        elif self.status is ProposalStatus.CONFIRMED:
            if self.blockers or self.order_id is None or self.quote_provenance is None:
                raise ValueError("confirmed proposal requires order and quote evidence")
        elif self.status is ProposalStatus.REJECTED and (
            not self.blockers or self.order_id is None or self.quote_provenance is None
        ):
            raise ValueError("rejected proposal requires blocker, order and quote evidence")
        return self


class ProposalEvent(StrictContract):
    """One durable proposal state transition."""

    proposal_id: str
    sequence: int = Field(ge=1)
    recorded_at: datetime
    proposal: PaperProposal

    @field_validator("proposal_id")
    @classmethod
    def proposal_id_is_canonical(cls, value: str) -> str:
        if _PROPOSAL_ID.fullmatch(value) is None:
            raise ValueError("proposal_id is not canonical")
        return value

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "recorded_at")

    @model_validator(mode="after")
    def event_identity_matches(self) -> "ProposalEvent":
        if self.proposal_id != self.proposal.id:
            raise ValueError("proposal event identity does not match its snapshot")
        if self.recorded_at < self.proposal.created_at:
            raise ValueError("proposal event cannot predate proposal creation")
        return self


class OrderEventSnapshot(StrictContract):
    """Deeply immutable public copy of one paper-order event."""

    sequence: int = Field(ge=1)
    timestamp: datetime
    event_type: OrderEventType
    status: OrderStatus
    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    reason: str | None = None
    broker_fill_id: str | None = None
    fee: float | None = Field(default=None, ge=0)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "timestamp")


class OrderSnapshot(StrictContract):
    """Deeply immutable response snapshot of a replay-validated paper order."""

    order_id: str
    instrument: InstrumentSnapshot
    side: Side
    quantity: float = Field(gt=0)
    order_type: OrderType
    limit_price: float | None = Field(default=None, gt=0)
    created_at: datetime
    client_order_id: str | None = None
    idempotency_key: str | None = Field(default=None, pattern=IDEMPOTENCY_KEY_PATTERN)
    broker_order_id: str | None = None
    status: OrderStatus
    filled_quantity: float = Field(ge=0)
    events: tuple[OrderEventSnapshot, ...] = Field(default_factory=tuple)

    @field_validator("instrument", mode="before")
    @classmethod
    def instrument_is_a_detached_snapshot(cls, value: object) -> object:
        return _instrument_snapshot(value)

    @field_validator("created_at")
    @classmethod
    def created_at_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "created_at")

    @model_validator(mode="after")
    def snapshot_is_consistent(self) -> "OrderSnapshot":
        if self.filled_quantity > self.quantity and not math.isclose(
            self.filled_quantity, self.quantity
        ):
            raise ValueError("filled_quantity cannot exceed order quantity")
        if (self.order_type is OrderType.LIMIT) != (self.limit_price is not None):
            raise ValueError("order_type must match limit_price presence")
        return self


class ProposalConfirmation(StrictContract):
    """Typed result of an explicit confirmation attempt."""

    proposal: PaperProposal
    order: OrderSnapshot | None = None
    blocker: str | None = None
    quote_provenance: Literal["real", "demo-synthetic"] | None = None

    @field_validator("order", mode="before")
    @classmethod
    def order_is_a_detached_snapshot(cls, value: object) -> object:
        if isinstance(value, Order):
            payload = value.model_dump()
            payload["events"] = tuple(payload["events"])
            return payload
        return value

    @model_validator(mode="after")
    def result_matches_proposal(self) -> "ProposalConfirmation":
        terminal = self.proposal.status in {
            ProposalStatus.CONFIRMED,
            ProposalStatus.REJECTED,
        }
        if terminal != (self.order is not None):
            raise ValueError("terminal confirmation result must carry its order")
        if self.order is not None and self.order.order_id != self.proposal.order_id:
            raise ValueError("confirmation order must match proposal order_id")
        if self.quote_provenance != self.proposal.quote_provenance:
            raise ValueError("confirmation quote provenance must match proposal")
        if self.proposal.status in {ProposalStatus.BLOCKED, ProposalStatus.REJECTED}:
            if self.blocker is None:
                raise ValueError("blocked or rejected confirmation requires a blocker")
        return self


class WorkspaceLiveEvidence(StrictContract):
    """One truthful latest quote view; absent data stays explicitly absent."""

    status: Literal["available", "degraded", "unavailable"]
    reason: str | None = None
    source: str | None = None
    provenance: str | None = None
    label: str | None = None
    data_time: datetime | None = None
    received_at: datetime | None = None
    age_ms: int | None = Field(default=None, ge=0)
    sequence: int | None = Field(default=None, ge=0)
    sequence_gap: bool | None = None
    bid: float | None = Field(default=None, gt=0)
    ask: float | None = Field(default=None, gt=0)
    last: float | None = Field(default=None, gt=0)

    @field_validator("data_time", "received_at")
    @classmethod
    def live_times_are_utc(cls, value: datetime | None, info) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def availability_is_explicit(self) -> "WorkspaceLiveEvidence":
        if self.status == "available":
            if (
                self.reason is not None
                or self.source is None
                or self.provenance is None
                or self.data_time is None
                or self.received_at is None
            ):
                raise ValueError("available live evidence requires lineage and no reason")
        elif self.reason is None:
            raise ValueError("degraded or unavailable live evidence requires a reason")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("workspace bid cannot exceed ask")
        return self


class WorkspaceForecast(StrictContract):
    """Forecast evidence needed by the workspace, without bulky OOS rows."""

    artifact_id: str
    generated_at: datetime
    target: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime | None = None
    validation_end: datetime | None = None
    test_start: datetime | None = None
    test_end: datetime | None = None
    model_name: str
    model_version: str
    config_digest: str
    dataset_id: str
    dataset_revision: int = Field(ge=1)
    history_digest: str
    benchmark_name: str
    synthetic: bool
    eligible: bool
    blockers: tuple[str, ...]
    limitations: tuple[str, ...]
    paths: tuple[ForecastPath, ...]
    metrics: tuple[ForecastMetrics, ...]

    @field_validator("artifact_id")
    @classmethod
    def artifact_id_is_canonical(cls, value: str) -> str:
        if _FORECAST_ID.fullmatch(value) is None:
            raise ValueError("workspace forecast artifact_id is not canonical")
        return value

    @field_validator(
        "generated_at",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
    )
    @classmethod
    def forecast_times_are_utc(cls, value: datetime | None, info) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @field_validator("config_digest", "history_digest")
    @classmethod
    def forecast_digests_are_sha256(cls, value: str, info) -> str:
        if _SHA256.fullmatch(value) is None:
            raise ValueError(f"{info.field_name} must be lowercase sha256")
        return value

    @model_validator(mode="after")
    def eligibility_is_explicit(self) -> "WorkspaceForecast":
        if self.eligible != (not self.blockers):
            raise ValueError("workspace forecast eligibility must match blockers")
        return self


class WorkspaceMarkStatus(StrictContract):
    status: Literal["available", "stale", "unavailable"]
    provenance: str
    received_at: datetime | None = None
    reason: str | None = None

    @field_validator("received_at")
    @classmethod
    def received_at_is_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "received_at")


class WorkspacePosition(StrictContract):
    quantity: float
    average_cost: float = Field(ge=0)
    realized_pnl: float
    mark: float | None = Field(default=None, gt=0)
    unrealized_pnl: float | None = None
    mark_status: WorkspaceMarkStatus | None = None


class WorkspaceRisk(StrictContract):
    cash: float = Field(ge=0)
    equity: float | None = Field(default=None, ge=0)
    starting_cash: float = Field(ge=0)
    max_order_quantity: float | None = Field(default=None, gt=0)
    max_notional: float | None = Field(default=None, gt=0)
    max_position_quantity: float | None = Field(default=None, gt=0)
    global_kill_switch: bool
    venue_kill_switch: bool
    mark_available: bool
    valuation_complete: bool
    valuation_reason: str | None = None

    @model_validator(mode="after")
    def valuation_is_explicit(self) -> "WorkspaceRisk":
        if self.valuation_complete != (self.equity is not None):
            raise ValueError("complete workspace valuation must have exact equity")
        if self.valuation_complete != (self.valuation_reason is None):
            raise ValueError("incomplete workspace valuation must name a reason")
        return self


class ProposalCapability(StrictContract):
    allowed: bool
    blockers: tuple[str, ...]
    proposals: tuple[PaperProposal, ...]

    @model_validator(mode="after")
    def capability_matches_blockers(self) -> "ProposalCapability":
        if self.allowed != (not self.blockers):
            raise ValueError("proposal capability must match blockers")
        return self


class InstrumentWorkspace(StrictContract):
    """Point-in-time read model for one venue-aware decision workspace."""

    generated_at: datetime
    instrument: InstrumentSnapshot
    history: HistoricalSeries
    comparison: ComparisonSeries | None = None
    live: WorkspaceLiveEvidence
    forecast: WorkspaceForecast | None = None
    forecast_unavailable_reason: str | None = None
    position: WorkspacePosition | None = None
    risk: WorkspaceRisk
    proposal: ProposalCapability

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "generated_at")

    @field_validator("instrument", mode="before")
    @classmethod
    def instrument_is_a_detached_snapshot(cls, value: object) -> object:
        return _instrument_snapshot(value)

    @model_validator(mode="after")
    def identities_match(self) -> "InstrumentWorkspace":
        if self.instrument != self.history.instrument:
            raise ValueError("workspace instrument must match history")
        if (self.forecast is None) != (self.forecast_unavailable_reason is not None):
            raise ValueError(
                "workspace must carry either forecast evidence or an unavailable reason"
            )
        if self.forecast is not None and any(
            point.timestamp <= self.forecast.train_end
            for path in self.forecast.paths
            for point in path.points
        ):
            raise ValueError("workspace forecast paths must remain future-only")
        return self
