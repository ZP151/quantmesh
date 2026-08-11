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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
from pydantic import ValidationError

from quantmesh.data.layout import (
    SHARD_NAME,
    shards_in,
    validate_dataset_name,
    validate_day,
    validate_symbol,
)
from quantmesh.data.manifest import MANIFEST_NAME, DatasetManifest, scan_series
from quantmesh.domain.market_data import (
    Bar,
    find_duplicates,
    find_gaps,
    interval_to_timedelta,
    monotonic_violations,
)
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.settings import Settings


def _require_aware(timestamp: datetime | None, name: str) -> None:
    if timestamp is not None and timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _reject_symlinks(root: Path, path: Path) -> None:
    """Reject symlinked components between the root and the target path.

    The manifest scan already rejects links at every layout level; the
    raw ``Lake`` read/write surface must too — a linked interval, venue
    or symbol directory could otherwise point reads at bytes outside the
    root or land writes outside it. The terminal path itself is checked
    as well as its parents: ``read_bars`` hands over the symbol
    directory, and a shard file may itself be a link.
    """
    if path.is_symlink():
        raise ValueError(f"symlink in lake layout is not allowed: {path}")
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"symlink in lake layout is not allowed: {parent}")


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

    def shard_file(self, dataset: str, interval: str, venue: Venue, symbol: str, day: str) -> Path:
        validate_dataset_name(dataset)
        interval_to_timedelta(interval)
        validate_symbol(symbol)
        validate_day(day)
        return self.root / dataset / interval / venue.value / symbol / day / SHARD_NAME

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
            validate_symbol(current.instrument.symbol)
            _reject_symlinks(
                self.root,
                self.shard_file(
                    dataset,
                    current.interval,
                    current.instrument.venue,
                    current.instrument.symbol,
                    current.timestamp.astimezone(UTC).date().isoformat(),
                ),
            )
        groups: dict[tuple[str, Venue, str, str], list[Bar]] = {}
        for current in bars:
            key = (
                current.interval,
                current.instrument.venue,
                current.instrument.symbol,
                current.timestamp.astimezone(UTC).date().isoformat(),
            )
            groups.setdefault(key, []).append(current)
        with duckdb.connect() as con:
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
                temp = path.with_name(f"{SHARD_NAME}.tmp")
                try:
                    con.register("frame", frame)
                    con.execute(
                        f"COPY (SELECT * FROM frame) TO '{_sql_literal(temp.as_posix())}' "
                        "(FORMAT PARQUET)"
                    )
                    con.unregister("frame")
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
        validate_symbol(symbol)
        _require_aware(start, "start")
        _require_aware(end, "end")
        partition = self.root / dataset / interval / venue.value / symbol
        _reject_symlinks(self.root, partition)
        files = shards_in(partition)
        if not files:
            return []
        bars: list[Bar] = []
        with duckdb.connect() as con:
            for file in files:
                query = f"SELECT * FROM read_parquet('{_sql_literal(file.as_posix())}')"
                try:
                    rows = con.execute(query).fetchall()
                except duckdb.Error as error:
                    raise ValueError(f"shard {file} is unreadable: {error}") from error
                for ts, open_, high, low, close, volume, instrument_type, currency in rows:
                    if ts is None:
                        raise ValueError(
                            f"shard {file} contains NULL timestamps — tampered or corrupt"
                        )
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

    def quality(self, dataset: str, *, interval: str, venue: Venue, symbol: str) -> LakeQuality:
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

    def dataset(self, name: str) -> "Dataset":
        """The manifest-gated queryable view of one dataset (issue #16).

        Refuses to open a dataset that has no manifest, an unreadable or
        version-mismatched manifest, a manifest for a different name, a
        non-UTC timezone, or declared coverage that no longer matches
        the shards on disk (stale data must be regenerated before
        querying). The raw ``Lake`` remains the storage surface;
        experiments read through this gate so pinned revisions mean
        something.
        """
        validate_dataset_name(name)
        manifest_path = self.root / name / MANIFEST_NAME
        if not manifest_path.exists():
            raise ValueError(
                f"dataset {name!r} has no manifest — generate one (ManifestWriter) before querying"
            )
        try:
            manifest = DatasetManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (ValidationError, UnicodeDecodeError, OSError) as error:
            raise ValueError(f"dataset {name!r} manifest is invalid: {error}") from error
        if manifest.dataset != name:
            raise ValueError(f"manifest dataset {manifest.dataset!r} does not match {name!r}")
        scan = scan_series(self.root, name)
        declared = {
            (c.interval, c.venue, c.symbol): (c.rows, c.start, c.end) for c in manifest.coverage
        }
        if scan != declared:
            raise ValueError(
                f"dataset {name!r} manifest is stale — on-disk coverage differs; regenerate"
            )
        return Dataset(self, name, manifest)


class Dataset:
    """Queryable view of a manifest-gated dataset (ADR-0003, issue #16).

    A ``Dataset`` is a point-in-time view: it is validated against the
    shards when opened, and must be re-opened after any write so the
    manifest gate can check freshness again. Prefer constructing via
    ``Lake.dataset()``; direct construction still enforces that the
    manifest belongs to the dataset name.
    """

    def __init__(self, lake: Lake, name: str, manifest: DatasetManifest) -> None:
        if manifest.dataset != name:
            raise ValueError(f"manifest dataset {manifest.dataset!r} does not match {name!r}")
        self._lake = lake
        self.name = name
        self.manifest = manifest

    def read_bars(
        self,
        *,
        interval: str,
        venue: Venue,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        """Read the dataset's bars; the dataset name is bound by the gate."""
        return self._lake.read_bars(
            self.name,
            interval=interval,
            venue=venue,
            symbol=symbol,
            start=start,
            end=end,
        )

    def quality(self, *, interval: str, venue: Venue, symbol: str) -> LakeQuality:
        """Quality report for one series of the dataset."""
        return self._lake.quality(self.name, interval=interval, venue=venue, symbol=symbol)
