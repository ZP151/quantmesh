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
    def metadata_is_detached(
        cls, value: Mapping[str, str]
    ) -> Mapping[str, str]:
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
    def quality_times_are_utc(
        cls, value: tuple[datetime, ...], info
    ) -> tuple[datetime, ...]:
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
    def values_are_finite_and_keyed(
        cls, value: Mapping[str, float]
    ) -> Mapping[str, float]:
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
