"""Scheduled ingestion and coverage gap detection (issue #19).

``Ingestor`` drives the provider registry into the lake: fetch new
bars for a job, write them, regenerate the manifest so the dataset
stays queryable. Each run re-opens the UTC day of the last stored
tick, so that day's shard is rebuilt wholesale from the provider
(ADR-0003 semantics) — a provider correction, retraction or extension
of the latest day is picked up (the no-op check compares full OHLCV
content, not just timestamps), earlier days are never re-fetched, and
a run that changes nothing and whose manifest is still fresh writes
nothing and leaves the revision untouched. A manifest that has gone
stale (a write that never regenerated it, manual tampering) is healed
by regeneration on the next run. M3 ships no wall-clock timer —
fixture data does not grow on its own, and a deterministic run loop
is the honest shape for a no-execution-surface milestone: the caller
triggers ``run`` (cron, notebook, CI).

``coverage_gaps`` compares observed lake coverage against a dataset's
manifest — the diagnostic the manifest gate cannot give you, because
the gate refuses stale datasets outright. It reports series that
vanished, day shards within a declared range that are absent, and
bytes on disk the manifest never declared. Expected days come from
the interval grid anchored at the declared start (a 1w series expects
its weekly ticks, not every calendar day); trading calendars are not
modeled, so a daily equity series with weekend gaps still reports
Sat/Sun as missing. The gate's own quality checks (issue #15) detect
duplicated and out-of-order observations; together they cover the M3
exit criterion that missing, duplicated and out-of-order data is
detected.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel, ValidationError, model_validator

from quantmesh.data.lake import Lake
from quantmesh.data.layout import shards_in, validate_dataset_name
from quantmesh.data.manifest import (
    MANIFEST_NAME,
    DatasetClass,
    DatasetManifest,
    ManifestWriter,
    scan_series,
)
from quantmesh.data.providers import ProviderRegistry
from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.domain.models import Instrument, Venue
from quantmesh.settings import settings


class IngestionJob(BaseModel):
    """What one scheduled run fetches and where it lands."""

    dataset: str
    instrument: Instrument
    interval: str
    cadence: str | None = None

    @model_validator(mode="after")
    def job_is_consistent(self) -> "IngestionJob":
        validate_dataset_name(self.dataset)
        interval_to_timedelta(self.interval)
        if self.cadence is not None:
            interval_to_timedelta(self.cadence)
        return self


class Ingestor:
    """Scheduled ingestion: providers → lake → fresh manifest (issue #19)."""

    def __init__(
        self,
        registry: ProviderRegistry,
        lake_root: Path | None = None,
        *,
        source: str = "ingestion",
        license: str = "fixture-only",
        data_class: DatasetClass | None = None,
    ) -> None:
        self.registry = registry
        self.lake = Lake(lake_root if lake_root is not None else settings.lake_root)
        self.source = source
        self.license = license
        self.data_class = data_class

    def ingest(self, job: IngestionJob) -> DatasetManifest | None:
        """Fetch new bars for the job and land them, then re-manifest.

        The window re-opens the UTC day of the last stored tick, so the
        latest day's shard is rebuilt from the provider's full data for
        that day. Returns the fresh manifest after a write, ``None``
        when the provider changed nothing and the manifest is still
        fresh, or a regenerated manifest when the bytes are unchanged
        but the manifest had gone stale (a write that never regenerated
        it is healed on the next run). Regeneration refuses to declare
        coverage that shrank — a manifest must never bless data loss
        (``ManifestWriter``), so a vanished series or an interior day
        stays flagged by ``coverage_gaps`` instead of being healed
        away.
        """
        provider = self.registry.get(job.instrument.venue)
        stored = self.lake.read_bars(
            job.dataset,
            interval=job.interval,
            venue=job.instrument.venue,
            symbol=job.instrument.symbol,
        )
        bars = provider.fetch_bars(
            job.instrument, interval=job.interval, start=self._day_start(stored)
        )
        if not bars:
            # Nothing fetched, but stored data exists: a manifest that
            # fell behind must still be healed (a quiet provider must
            # never leave a gated dataset healing-forever-unreachable).
            return self._heal_if_stale(job) if stored else None
        if self._unchanged(stored, bars):
            return self._heal_if_stale(job)
        self.lake.write_bars(job.dataset, bars)
        return ManifestWriter(self.lake.root).generate(
            job.dataset,
            source=self.source,
            license=self.license,
            data_class=self.data_class,
            rewritten=frozenset([(job.interval, job.instrument.venue, job.instrument.symbol)]),
        )

    def run(self, jobs: Sequence[IngestionJob]) -> list[DatasetManifest | None]:
        """Run every job in order; a ``None`` slot means nothing new."""
        return [self.ingest(job) for job in jobs]

    def _day_start(self, stored: Sequence) -> datetime | None:
        if not stored:
            return None
        last_day = max(bar.timestamp for bar in stored).astimezone(UTC).date()
        return datetime.combine(last_day, time.min, tzinfo=UTC)

    def _unchanged(self, stored: Sequence, bars: Sequence) -> bool:
        """True when writing ``bars`` would change no shard on disk.

        The wholesale day replacement means a run is a no-op only when
        the fetched window is content-identical to the stored last day
        — same timestamps *and* same OHLCV — and brings no new day.
        Comparing content, not just timestamps, is what lets provider
        corrections and retractions of the latest day land.
        """
        if not stored or not bars:
            return False

        def key(bar: Bar) -> tuple:
            return (bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)

        last_day = max(bar.timestamp for bar in stored).astimezone(UTC).date()
        same_day = [bar for bar in bars if bar.timestamp.astimezone(UTC).date() == last_day]
        if len(same_day) != len(bars):
            return False  # new days beyond the stored frontier
        stored_last_day = [
            bar for bar in stored if bar.timestamp.astimezone(UTC).date() == last_day
        ]
        return sorted(key(bar) for bar in same_day) == sorted(key(bar) for bar in stored_last_day)

    def _heal_if_stale(self, job: IngestionJob) -> DatasetManifest | None:
        """Regenerate the manifest when the bytes on disk disagree with it.

        Returns ``None`` when the manifest is fresh. A stale or missing
        manifest (a previous write without regeneration, a crash, manual
        tampering) is healed by a full regeneration so the dataset stays
        queryable; if that regeneration fails too (corrupt shards, or
        coverage that shrank since the declaration — possible data
        loss), the error propagates — every run fails loudly instead of
        silently no-op'ing forever.
        """
        try:
            self.lake.dataset(job.dataset)
        except ValueError:
            return ManifestWriter(self.lake.root).generate(
                job.dataset,
                source=self.source,
                license=self.license,
                data_class=self.data_class,
            )
        return None


@dataclass(frozen=True)
class SeriesGap:
    """Declared vs observed coverage of one (interval, venue, symbol) series.

    ``None`` marks a side that does not exist: declared-only entries are
    missing series, observed-only entries were never declared. Day lists
    hold ISO UTC dates.
    """

    interval: str
    venue: Venue
    symbol: str
    declared_rows: int | None
    observed_rows: int | None
    declared_start: datetime | None
    declared_end: datetime | None
    observed_start: datetime | None
    observed_end: datetime | None
    missing_days: list[str]
    unexpected_days: list[str]


@dataclass(frozen=True)
class CoverageReport:
    """Everything the manifest declared and the lake actually holds."""

    dataset: str
    series: list[SeriesGap]


def _days_between(start: datetime, end: datetime) -> list[str]:
    days = []
    current = start.date()
    last = end.date()
    while current <= last:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _expected_days(start: datetime, end: datetime, interval: str) -> list[str]:
    """ISO UTC dates the interval grid anchored at ``start`` crosses by ``end``.

    Intervals of a day or finer land on every calendar date in the
    range; coarser intervals (``1w``, ``2d``, ...) land on a subset.
    Trading calendars are not modeled — a daily equity series with
    weekend gaps still reports Sat/Sun as missing, which is a
    venue-calendar question, not a grid question.
    """
    step = interval_to_timedelta(interval)
    if step <= timedelta(days=1):
        return _days_between(start, end)
    days = []
    cursor = start.astimezone(UTC)
    while cursor <= end:
        days.append(cursor.date().isoformat())
        cursor += step
    return days


def _present_days(
    root: Path, dataset: str, interval: str, venue: Venue, symbol: str
) -> list[str]:
    symbol_dir = root / dataset / interval / venue.value / symbol
    return sorted({shard.parent.name for shard in shards_in(symbol_dir)})


def coverage_gaps(root: Path, dataset: str) -> CoverageReport:
    """Compare observed lake coverage against the dataset's manifest.

    The manifest gate refuses stale datasets outright, so this report is
    the diagnostic that says *what* is off: vanished series, missing day
    shards inside a declared range, and bytes the manifest never
    declared. Fails closed on a missing, invalid or foreign manifest, on
    a dataset that holds no series at all (a coverage report must never
    bless total data loss as "clean"), and on layout corruption
    (symlinks, crash orphans) via the shared scan. Blind spot shared
    with the lake gate: a day shard replaced with different bars of the
    same row count and same first/last timestamp is invisible here —
    nothing in M3 compares content; a content fingerprint in the
    manifest is the recorded follow-up.
    """
    validate_dataset_name(dataset)
    manifest_path = root / dataset / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(
            f"dataset {dataset!r} has no manifest — generate one (ManifestWriter) "
            "before checking coverage"
        )
    try:
        manifest = DatasetManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (ValidationError, UnicodeDecodeError, OSError) as error:
        raise ValueError(f"dataset {dataset!r} manifest is invalid: {error}") from error
    if manifest.dataset != dataset:
        raise ValueError(f"manifest dataset {manifest.dataset!r} does not match {dataset!r}")

    observed = scan_series(root, dataset)
    if not manifest.coverage and not observed:
        raise ValueError(
            f"dataset {dataset!r} holds no series at all — coverage is meaningless; "
            "data may have been lost"
        )
    declared = {
        (entry.interval, entry.venue, entry.symbol): entry for entry in manifest.coverage
    }
    series: list[SeriesGap] = []
    for key, entry in declared.items():
        found = observed.get(key)
        rows, start, end = found if found else (None, None, None)
        declared_days = _expected_days(entry.start, entry.end, entry.interval)
        present_days = _present_days(root, dataset, entry.interval, entry.venue, entry.symbol)
        series.append(
            SeriesGap(
                interval=entry.interval,
                venue=entry.venue,
                symbol=entry.symbol,
                declared_rows=entry.rows,
                observed_rows=rows,
                declared_start=entry.start,
                declared_end=entry.end,
                observed_start=start,
                observed_end=end,
                missing_days=sorted(set(declared_days) - set(present_days)),
                unexpected_days=sorted(set(present_days) - set(declared_days)),
            )
        )
    for (interval, venue, symbol), (rows, start, end) in observed.items():
        if (interval, venue, symbol) in declared:
            continue
        series.append(
            SeriesGap(
                interval=interval,
                venue=venue,
                symbol=symbol,
                declared_rows=None,
                observed_rows=rows,
                declared_start=None,
                declared_end=None,
                observed_start=start,
                observed_end=end,
                missing_days=[],
                unexpected_days=_present_days(root, dataset, interval, venue, symbol),
            )
        )
    return CoverageReport(dataset=dataset, series=series)
