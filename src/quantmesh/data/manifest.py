"""Legacy mutable Parquet dataset manifests (schema version 1, issue #16).

A manifest pins what a dataset claims to be: source, canonical timezone
(must be UTC — the lake normalizes to UTC), revision, license and the
observed coverage of every series. ``ManifestWriter.generate`` scans the
shards on disk and writes ``<dataset>/manifest.json``; the lake's
``Lake.dataset()`` gate refuses to open a dataset without a valid, fresh
manifest. Experiments pin ``(dataset, revision)`` and trust that the
bytes match the declaration — the M3 "pinned dataset" exit criterion.

This interface remains for existing Parquet consumers. New trusted-data
pipelines publish content-addressed objects and immutable schema-version-2
manifests through :mod:`quantmesh.data.artifacts`.

Freshness is declared coverage: series set, per-series row counts and
first/last timestamps. A same-count, same-range content change is not
detected by the gate; bumping the revision via regeneration is the
honest record of "the bytes changed".
"""

import os
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import duckdb
from pydantic import BaseModel, Field, ValidationError, model_validator

from quantmesh._fs import atomic_replace
from quantmesh.data.layout import shards_in, validate_dataset_name, validate_symbol
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue

MANIFEST_NAME = "manifest.json"


class DatasetClass(StrEnum):
    """Trust-relevant classification of the bytes declared by a manifest."""

    OBSERVED = "observed"
    SYNTHETIC = "synthetic"


def _utc(value: datetime | None) -> datetime | None:
    """Normalize a duckdb timestamp (local zone) to UTC; NULL stays None."""
    if value is None:
        return None
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SeriesCoverage(BaseModel):
    """One (interval, venue, symbol) series observed in the dataset."""

    interval: str
    venue: Venue
    symbol: str
    start: datetime
    end: datetime
    rows: int = Field(ge=1)

    @model_validator(mode="after")
    def series_is_consistent(self) -> "SeriesCoverage":
        interval_to_timedelta(self.interval)
        validate_symbol(self.symbol)
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("coverage timestamps must be timezone-aware")
        if self.start > self.end:
            raise ValueError(f"coverage start {self.start} after end {self.end}")
        return self


class DatasetManifest(BaseModel):
    """Versioned manifest beside one dataset (``<dataset>/manifest.json``)."""

    schema_version: int = 1
    dataset: str
    source: str = Field(min_length=1)
    data_class: DatasetClass | None = None
    timezone: str = "UTC"
    license: str = Field(min_length=1)
    revision: int = Field(ge=1)
    generated_at: datetime
    coverage: list[SeriesCoverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def manifest_is_consistent(self) -> "DatasetManifest":
        if self.schema_version != 1:
            raise ValueError(f"unsupported manifest schema_version {self.schema_version}")
        validate_dataset_name(self.dataset)
        if self.timezone != "UTC":
            raise ValueError("manifest timezone must be 'UTC' — the lake is UTC-normalized")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        seen: set[tuple[str, Venue, str]] = set()
        for entry in self.coverage:
            key = (entry.interval, entry.venue, entry.symbol)
            if key in seen:
                raise ValueError(f"duplicate coverage entry for {key}")
            seen.add(key)
        return self


def scan_series(
    root: Path, dataset: str
) -> dict[tuple[str, Venue, str], tuple[int, datetime, datetime]]:
    """(interval, venue, symbol) -> (rows, first, last) as stored on disk.

    Timestamps are normalized to UTC. Stray directories that do not
    match the canonical layout raise (fail closed): generation and the
    freshness gate must never guess about bytes they cannot classify.
    """
    base = root / dataset
    if not base.exists():
        return {}
    result: dict[tuple[str, Venue, str], tuple[int, datetime, datetime]] = {}
    with duckdb.connect() as con:
        for interval_dir in sorted(base.iterdir()):
            if interval_dir.is_symlink():
                raise ValueError(f"symlink in lake layout is not allowed: {interval_dir}")
            if not interval_dir.is_dir():
                continue  # manifest.json and friends are not partitions
            interval_to_timedelta(interval_dir.name)
            for venue_dir in sorted(interval_dir.iterdir()):
                if venue_dir.is_symlink():
                    raise ValueError(f"symlink in lake layout is not allowed: {venue_dir}")
                if not venue_dir.is_dir():
                    continue
                venue = Venue(venue_dir.name)
                for symbol_dir in sorted(venue_dir.iterdir()):
                    if symbol_dir.is_symlink():
                        raise ValueError(f"symlink in lake layout is not allowed: {symbol_dir}")
                    if not symbol_dir.is_dir():
                        continue
                    validate_symbol(symbol_dir.name)
                    shards = shards_in(symbol_dir)
                    if not shards:
                        continue
                    rows = 0
                    first: datetime | None = None
                    last: datetime | None = None
                    for shard in shards:
                        quoted = shard.as_posix().replace("'", "''")
                        try:
                            count, start, end = con.execute(
                                f"SELECT count(*), min(timestamp), max(timestamp) "
                                f"FROM read_parquet('{quoted}')"
                            ).fetchone()
                        except duckdb.Error as error:
                            raise ValueError(
                                f"shard {shard} is unreadable: {error}"
                            ) from error
                        if count == 0:
                            raise ValueError(
                                f"shard {shard} has no rows (crash orphan?); remove or re-write it"
                            )
                        rows += count
                        first_utc = _utc(start)
                        last_utc = _utc(end)
                        if first is None or first_utc < first:
                            first = first_utc
                        if last is None or last_utc > last:
                            last = last_utc
                    result[(interval_dir.name, venue, symbol_dir.name)] = (rows, first, last)
    return result


class ManifestWriter:
    """Writes ``<dataset>/manifest.json`` from the current lake state."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def generate(
        self,
        dataset: str,
        *,
        source: str,
        license: str,
        data_class: DatasetClass | None = None,
        revision: int | None = None,
        rewritten: frozenset[tuple[str, Venue, str]] = frozenset(),
        generated_at: datetime | None = None,
    ) -> DatasetManifest:
        """Scan the dataset's shards and write a fresh manifest.

        ``revision`` defaults to the previous manifest's revision + 1
        (1 when none exists); pass it explicitly to pin a revision.
        ``rewritten`` lists the (interval, venue, symbol) series this
        call just rebuilt from an authoritative source (the provider);
        only those may lose rows or trailing range versus the previous
        manifest. Any other shrink — a vanished series, fewer rows, a
        start pushed forward or an end pulled back — is refused: a
        manifest must never declare *less* than it did before, because
        regeneration from lossy bytes erases the evidence of data loss
        (removing ``<dataset>/manifest.json`` first is the explicit
        recovery for deliberate changes). Raises when a previous
        manifest exists but is unreadable: regeneration is explicit
        recovery, not silent overwrite. Concurrent generation is not
        supported — the last writer wins — but a unique temp file per
        call means a race can never corrupt or mix manifest bytes.
        ``generated_at`` defaults to the current time; pin it explicitly
        when the manifest must be byte-reproducible (demo seed, replay).
        """
        validate_dataset_name(dataset)
        if not (self.root / dataset).is_dir():
            raise ValueError(f"dataset {dataset!r} does not exist in the lake")
        if not source.strip() or not license.strip():
            raise ValueError("source and license must be non-empty")
        scan = scan_series(self.root, dataset)
        previous = self._previous_manifest(dataset)
        if previous is not None:
            self._require_no_coverage_loss(dataset, previous, scan, rewritten)
        effective_data_class = (
            data_class
            if data_class is not None
            else previous.data_class
            if previous is not None
            else None
        )
        if revision is None:
            revision = (previous.revision if previous is not None else 0) + 1
        if revision < 1:
            raise ValueError(f"revision must be >= 1, got {revision}")
        manifest = DatasetManifest(
            dataset=dataset,
            source=source,
            data_class=effective_data_class,
            timezone="UTC",
            license=license,
            revision=revision,
            generated_at=generated_at or datetime.now(UTC),
            coverage=[
                SeriesCoverage(
                    interval=interval,
                    venue=venue,
                    symbol=symbol,
                    start=start,
                    end=end,
                    rows=rows,
                )
                for (interval, venue, symbol), (rows, start, end) in sorted(scan.items())
            ],
        )
        path = self.root / dataset / MANIFEST_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{MANIFEST_NAME}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(manifest.model_dump_json(indent=2))
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return manifest

    def _previous_manifest(self, dataset: str) -> DatasetManifest | None:
        path = self.root / dataset / MANIFEST_NAME
        if not path.exists():
            return None
        try:
            previous = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, UnicodeDecodeError, OSError) as error:
            raise ValueError(
                f"existing manifest {path} is unreadable; remove it to regenerate from scratch"
            ) from error
        if previous.dataset != dataset:
            raise ValueError(
                f"existing manifest is for dataset {previous.dataset!r}, not {dataset!r}"
            )
        return previous

    def _require_no_coverage_loss(
        self,
        dataset: str,
        previous: DatasetManifest,
        scan: dict[tuple[str, Venue, str], tuple[int, datetime, datetime]],
        rewritten: frozenset[tuple[str, Venue, str]],
    ) -> None:
        """Refuse to declare less coverage than the previous manifest did.

        The fetch window can only rebuild the *last* stored day of one
        series, so a shrink that is not on a ``rewritten`` series — or
        that pushes a rewritten series' start forward — cannot come from
        ingestion and is treated as possible data loss.
        """
        problems: list[str] = []
        for entry in previous.coverage:
            key = (entry.interval, entry.venue, entry.symbol)
            observed = scan.get(key)
            if observed is None:
                problems.append(f"series {key} vanished (was {entry.rows} rows)")
                continue
            rows, start, end = observed
            if start > entry.start:
                problems.append(
                    f"series {key} start moved forward {entry.start.date()} -> {start.date()}"
                )
            if key in rewritten:
                continue  # this call rebuilt the series from an authoritative source
            if rows < entry.rows:
                problems.append(f"series {key} rows shrank {entry.rows} -> {rows}")
            if end < entry.end:
                problems.append(
                    f"series {key} end moved backward {entry.end.date()} -> {end.date()}"
                )
        if problems:
            raise ValueError(
                f"refusing to regenerate manifest for {dataset!r}: "
                + "; ".join(problems)
                + f" — possible data loss, investigate first "
                f"(remove {self.root / dataset / MANIFEST_NAME} to override)"
            )
