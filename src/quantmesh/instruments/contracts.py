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
from quantmesh.domain.models import Instrument, Venue
from quantmesh.live.contract import Provenance

AdjustmentMode = Literal["unadjusted", "split-adjusted", "total-return"]
_COMPARISON_KEY = re.compile(r"^[a-z0-9_-]+:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORECAST_ID = re.compile(r"^forecast-[0-9a-f]{24}$")


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
    calibration_count: int = Field(ge=0)
    mae: float = Field(ge=0)
    rmse: float = Field(ge=0)
    benchmark_mae: float = Field(ge=0)
    coverage_50: float = Field(ge=0, le=1)
    coverage_80: float = Field(ge=0, le=1)
    coverage_95: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> "ForecastMetrics":
        if self.calibration_count > self.residual_count:
            raise ValueError("calibration_count cannot exceed residual_count")
        return self


class PriceForecastArtifact(StrictContract):
    """Replayable forecast evidence; eligibility is data, never an assertion."""

    id: str
    instrument: InstrumentSnapshot
    dataset_id: str
    dataset_revision: int = Field(ge=1)
    source: str = Field(min_length=1)
    license: str = Field(min_length=1)
    generated_at: datetime
    train_start: datetime
    train_end: datetime
    model_name: Literal["median-log-drift-conformal"]
    model_version: str = Field(min_length=1)
    config_digest: str
    benchmark_name: Literal["last-price-random-walk"]
    paths: tuple[ForecastPath, ...]
    oos: tuple[OOSForecast, ...]
    metrics: tuple[ForecastMetrics, ...]
    eligible: bool
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)
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

    @field_validator("generated_at", "train_start", "train_end")
    @classmethod
    def artifact_times_are_utc(cls, value: datetime, info) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("source", "license", "model_version")
    @classmethod
    def lineage_strings_are_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @field_validator("config_digest")
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
        if self.train_start > self.train_end or self.generated_at < self.train_end:
            raise ValueError("forecast training and generation times are inconsistent")
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
        if self.eligible != (not self.blockers):
            raise ValueError("eligible must be true if and only if blockers are empty")
        return self
