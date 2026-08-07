"""Local Parquet/DuckDB research data lake (ADR-0003).

Canonical partition layout, relative to the lake root:

    <dataset>/<interval>/<venue>/<symbol>/<date>/shard-0000.parquet

The date is the UTC date of the observation. One shard file per
(dataset, interval, venue, symbol, date); writing a day's bars again
replaces that day's shard wholesale. Reads return bars in stored order;
data-quality checks are the gate before a dataset is trusted, and
consumers order explicitly when they need to.

Every path component is validated against a whitelist before any I/O —
dataset, interval, symbol and day — so no name can escape the lake root,
cross partitions, or break the COPY statement.
"""

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from quantmesh.domain.market_data import (
    Bar,
    find_duplicates,
    find_gaps,
    interval_to_timedelta,
    monotonic_violations,
)
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.settings import Settings

_DATASET_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_DAY_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SHARD = "shard-0000.parquet"


def validate_dataset_name(dataset: str) -> None:
    """Reject dataset names that could escape the lake root or break tooling."""
    if _DATASET_PATTERN.fullmatch(dataset) is None:
        raise ValueError(
            f"invalid dataset name {dataset!r} "
            "(expected lowercase [a-z0-9], separators only inside)"
        )


def _validate_symbol(symbol: str) -> None:
    if _SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError(
            f"invalid symbol {symbol!r} "
            "(expected [A-Za-z0-9], separators and dots only inside)"
        )


def _validate_day(day: str) -> None:
    if _DAY_PATTERN.fullmatch(day) is None:
        raise ValueError(f"invalid day {day!r} (expected an ISO UTC date like 2026-08-07)")


def _require_aware(timestamp: datetime | None, name: str) -> None:
    if timestamp is not None and timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


@dataclass(frozen=True)
class LakeQuality:
    """Data-quality report for one (dataset, interval, venue, symbol) series."""

    dataset: str
    interval: str
    venue: Venue
    symbol: str
    rows: int
    out_of_order: list[tuple[int, int]]
    duplicates: dict[datetime, list[int]]
    gaps: list[datetime]


class Lake:
    """Deterministic read/write surface over the canonical Parquet layout."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_settings(cls, settings: Settings) -> "Lake":
        return cls(settings.lake_root)

    def shard_file(
        self, dataset: str, interval: str, venue: Venue, symbol: str, day: str
    ) -> Path:
        validate_dataset_name(dataset)
        interval_to_timedelta(interval)
        _validate_symbol(symbol)
        _validate_day(day)
        return self.root / dataset / interval / venue.value / symbol / day / _SHARD

    def write_bars(self, dataset: str, bars: Sequence[Bar]) -> None:
        """Write bars into their partition paths, one shard per UTC date.

        Re-writing a day's bars replaces that day's shard wholesale; old
        days are never touched. Timestamps are normalized to UTC on
        write, so identical input produces byte-identical files for a
        given duckdb version. Each shard is written to a temp file and
        atomically renamed into place; if a call fails partway, re-run it
        — writes are idempotent day-shard replacements.
        """
        validate_dataset_name(dataset)
        if not bars:
            raise ValueError("write_bars requires at least one bar")
        for current in bars:
            _validate_symbol(current.instrument.symbol)
        groups: dict[tuple[str, Venue, str, str], list[Bar]] = {}
        for current in bars:
            key = (
                current.interval,
                current.instrument.venue,
                current.instrument.symbol,
                current.timestamp.astimezone(UTC).date().isoformat(),
            )
            groups.setdefault(key, []).append(current)
        for (interval, venue, symbol, day), group in groups.items():
            path = self.shard_file(dataset, interval, venue, symbol, day)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame = pd.DataFrame(
                {
                    "timestamp": [b.timestamp.astimezone(UTC) for b in group],
                    "open": [b.open for b in group],
                    "high": [b.high for b in group],
                    "low": [b.low for b in group],
                    "close": [b.close for b in group],
                    "volume": [b.volume for b in group],
                    "instrument_type": [b.instrument.instrument_type.value for b in group],
                    "currency": [b.instrument.currency for b in group],
                }
            )
            temp = path.with_name(f"{_SHARD}.tmp")
            try:
                with duckdb.connect() as con:
                    con.register("frame", frame)
                    con.execute(
                        f"COPY (SELECT * FROM frame) TO '{_sql_literal(temp.as_posix())}' "
                        "(FORMAT PARQUET)"
                    )
                os.replace(temp, path)
            finally:
                if temp.exists():
                    temp.unlink()

    def read_bars(
        self,
        dataset: str,
        *,
        interval: str,
        venue: Venue,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        """Read every stored bar for the partition, in stored (file) order.

        ``start``/``end`` filter inclusively on the UTC timestamp and must
        be timezone-aware. Returns an empty list when the partition does
        not exist.
        """
        validate_dataset_name(dataset)
        interval_to_timedelta(interval)
        _validate_symbol(symbol)
        _require_aware(start, "start")
        _require_aware(end, "end")
        partition = self.root / dataset / interval / venue.value / symbol
        files = sorted(
            path
            for path in partition.glob(f"*/{_SHARD}")
            if _DAY_PATTERN.fullmatch(path.parent.name) is not None
        )
        if not files:
            return []
        bars: list[Bar] = []
        with duckdb.connect() as con:
            for file in files:
                query = f"SELECT * FROM read_parquet('{_sql_literal(file.as_posix())}')"
                for ts, open_, high, low, close, volume, instrument_type, currency in (
                    con.execute(query).fetchall()
                ):
                    normalized = (
                        ts.astimezone(UTC) if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
                    )
                    if start is not None and normalized < start:
                        continue
                    if end is not None and normalized > end:
                        continue
                    bars.append(
                        Bar(
                            instrument=Instrument(
                                symbol=symbol,
                                venue=venue,
                                instrument_type=InstrumentType(instrument_type),
                                currency=currency,
                            ),
                            timestamp=normalized,
                            interval=interval,
                            open=open_,
                            high=high,
                            low=low,
                            close=close,
                            volume=volume,
                        )
                    )
        return bars

    def quality(
        self, dataset: str, *, interval: str, venue: Venue, symbol: str
    ) -> LakeQuality:
        """Run the slice #14 quality primitives over the stored series.

        Gaps are computed on the sorted unique timestamps so duplicate
        rows are reported by ``duplicates`` rather than crashing the gap
        check; misaligned series still fail closed.
        """
        bars = self.read_bars(dataset, interval=interval, venue=venue, symbol=symbol)
        timestamps = [b.timestamp for b in bars]
        gaps = find_gaps(sorted(set(timestamps)), interval=interval)
        return LakeQuality(
            dataset=dataset,
            interval=interval,
            venue=venue,
            symbol=symbol,
            rows=len(bars),
            out_of_order=monotonic_violations(timestamps),
            duplicates=find_duplicates(bars, key=lambda b: b.timestamp),
            gaps=gaps,
        )
