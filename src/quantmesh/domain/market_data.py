"""Venue-agnostic normalized market-data models and data-quality primitives.

M3 slice #1 (issue #14): canonical `Bar`, `OrderBook` and `TradeEvent`
schemas plus the monotonicity, gap and duplication primitives that the
data lake's quality checks build on (iteration 0005). Domain layer only:
no I/O, no new dependencies. Provider-specific fields stay in adapter
payloads, never in these canonical models.
"""

import re
from collections.abc import Callable, Hashable, Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Instrument, Side

_INTERVAL_PATTERN = re.compile(r"^(\d+)([smhdw])$")
_INTERVAL_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def interval_to_timedelta(interval: str) -> timedelta:
    """Convert a compact interval like ``"5m"``, ``"1h"`` or ``"1d"`` to a timedelta.

    Raises ValueError for unparseable intervals so downstream quality
    checks fail closed instead of guessing.
    """
    match = _INTERVAL_PATTERN.match(interval)
    if match is None:
        raise ValueError(
            f"unsupported interval {interval!r} (expected a compact form like '5m', '1h', '1d')"
        )
    amount, unit = match.groups()
    return timedelta(seconds=int(amount) * _INTERVAL_SECONDS[unit])


def _require_tz_aware(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return timestamp


class Bar(BaseModel):
    """One interval-aligned OHLCV bar; ``timestamp`` is the bar open time."""

    instrument: Instrument
    timestamp: datetime
    interval: str = "1m"
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @model_validator(mode="after")
    def timestamp_must_be_aware(self) -> "Bar":
        _require_tz_aware(self.timestamp)
        return self

    @model_validator(mode="after")
    def interval_must_parse(self) -> "Bar":
        interval_to_timedelta(self.interval)
        return self

    @model_validator(mode="after")
    def candles_are_consistent(self) -> "Bar":
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError(
                f"high {self.high} below max(open, close) {max(self.open, self.close)} "
                f"or low {self.low} above min(open, close) {min(self.open, self.close)}"
            )
        return self


class DepthLevel(BaseModel):
    """One price level in an order book; prices are strictly ordered per side."""

    price: float = Field(gt=0)
    quantity: float = Field(ge=0)


class OrderBook(BaseModel):
    """Aggregated depth snapshot; bids strictly descending, asks strictly ascending.

    Duplicate price levels within a side are rejected: they are duplicate
    observations, which the quality primitives exist to detect.
    """

    instrument: Instrument
    timestamp: datetime
    bids: list[DepthLevel] = Field(default_factory=list)
    asks: list[DepthLevel] = Field(default_factory=list)

    @model_validator(mode="after")
    def timestamp_must_be_aware(self) -> "OrderBook":
        _require_tz_aware(self.timestamp)
        return self

    @model_validator(mode="after")
    def levels_are_strictly_ordered(self) -> "OrderBook":
        if any(b1.price <= b2.price for b1, b2 in zip(self.bids, self.bids[1:])):
            raise ValueError("bids must be strictly descending (best first)")
        if any(a1.price >= a2.price for a1, a2 in zip(self.asks, self.asks[1:])):
            raise ValueError("asks must be strictly ascending (best first)")
        return self


class TradeEvent(BaseModel):
    """One executed trade as reported by a venue; sequence is per venue."""

    instrument: Instrument
    timestamp: datetime
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    aggressor_side: Side | None = None
    venue_sequence: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def timestamp_must_be_aware(self) -> "TradeEvent":
        _require_tz_aware(self.timestamp)
        return self


def monotonic_violations(values: Sequence[object]) -> list[tuple[int, int]]:
    """Return ``(i - 1, i)`` index pairs where the series decreases.

    Non-decreasing is allowed (equal neighbours are not violations).
    Works on any orderable series (timestamps, venue sequences, prices).
    """
    return [
        (i - 1, i) for i in range(1, len(values)) if values[i] < values[i - 1]
    ]


def _identity(value: object) -> Hashable:
    return value


def find_duplicates(
    rows: Sequence[object],
    *,
    key: Callable[[object], Hashable] | None = None,
) -> dict[Hashable, list[int]]:
    """Return ``key -> row indices`` for every key seen more than once.

    The default key is the row itself, which works for hashable rows such
    as ``(timestamp, sequence)`` tuples; pass ``key=`` for model instances
    (e.g. ``lambda trade: (trade.timestamp, trade.venue_sequence)``).
    """
    if key is None:
        key = _identity
    seen: dict[Hashable, list[int]] = {}
    for index, row in enumerate(rows):
        seen.setdefault(key(row), []).append(index)
    return {k: indices for k, indices in seen.items() if len(indices) > 1}


def find_gaps(timestamps: Sequence[datetime], *, interval: str) -> list[datetime]:
    """Return expected observation times missing from an interval-aligned series.

    ``timestamps`` must be strictly increasing and timezone-aware. Between
    two observations that are exactly ``k * interval`` apart, the ``k - 1``
    expected ticks are reported. Misaligned series and non-increasing input
    raise ValueError (fail closed) instead of producing partial detections.
    """
    step = interval_to_timedelta(interval)
    gaps: list[datetime] = []
    for previous, current in zip(timestamps, timestamps[1:]):
        if previous.tzinfo is None or current.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        if current <= previous:
            raise ValueError(
                "timestamps must be strictly increasing (run monotonic_violations first)"
            )
        delta = current - previous
        if delta % step != timedelta(0):
            raise ValueError(
                f"series not aligned to interval {interval!r} between {previous} and {current}"
            )
        missing = int(delta / step) - 1
        for k in range(1, missing + 1):
            gaps.append(previous + k * step)
    return gaps
