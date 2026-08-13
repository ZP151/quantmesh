"""Manifest-gated selection and normalization of observed market history."""

import math
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.data.manifest import DatasetManifest
from quantmesh.domain.market_data import Bar, find_gaps, interval_to_timedelta
from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import (
    ComparisonPoint,
    ComparisonSeries,
    CoverageSnapshot,
    DatasetBinding,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
)

_PREFERRED_INTERVAL = {
    HistoryRange.ONE_DAY: "5m",
    HistoryRange.FIVE_DAYS: "30m",
    HistoryRange.ONE_MONTH: "1h",
    HistoryRange.THREE_MONTHS: "1d",
    HistoryRange.SIX_MONTHS: "1d",
    HistoryRange.ONE_YEAR: "1d",
}
_WINDOW = {
    HistoryRange.ONE_DAY: timedelta(days=1),
    HistoryRange.FIVE_DAYS: timedelta(days=5),
    HistoryRange.ONE_MONTH: timedelta(days=31),
    HistoryRange.THREE_MONTHS: timedelta(days=93),
    HistoryRange.SIX_MONTHS: timedelta(days=186),
    HistoryRange.ONE_YEAR: timedelta(days=366),
}
_CONTINUOUS_CALENDAR = "24/7"
_NEW_YORK = ZoneInfo("America/New_York")


class ReadableDataset(Protocol):
    """Narrow surface required from the manifest-gated lake Dataset."""

    name: str
    manifest: DatasetManifest

    def read_bars(
        self,
        *,
        interval: str,
        venue: Venue,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]: ...


# Expected absence must be reported as ``HistoryUnavailableError`` by the
# loader. Plain ``ValueError`` and validation faults are programmer errors and
# deliberately propagate to the API's sanitized 500 boundary.
DatasetLoader = Callable[[str], ReadableDataset]
Clock = Callable[[], datetime]


class HistoryUnavailableError(ValueError):
    """Expected request or dataset unavailability at the history boundary."""


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise HistoryUnavailableError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _key(venue: Venue, symbol: str) -> str:
    return f"{venue.value}:{symbol}"


class HistoryService:
    """Resolve one observed series without bypassing the current manifest gate."""

    def __init__(
        self,
        bindings: Iterable[DatasetBinding],
        *,
        dataset_loader: DatasetLoader,
        now: Clock | None = None,
    ) -> None:
        self._bindings = tuple(bindings)
        self._dataset_loader = dataset_loader
        self._now = now or (lambda: datetime.now(UTC))
        seen: set[tuple[Venue, str, timedelta]] = set()
        for current in self._bindings:
            resolution = interval_to_timedelta(current.interval)
            identity = (current.venue, current.symbol, resolution)
            if identity in seen:
                raise ValueError(
                    "ambiguous dataset bindings for "
                    f"{current.venue.value}:{current.symbol} at resolution {resolution}"
                )
            seen.add(identity)

    def history(
        self,
        venue: Venue,
        symbol: str,
        range: HistoryRange,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalSeries:
        """Return one manifest-provenanced observed window or fail closed."""
        if not isinstance(venue, Venue):
            raise TypeError("venue must be a Venue")
        if not isinstance(range, HistoryRange):
            raise TypeError("range must be a HistoryRange")
        selected_as_of = _aware_utc(as_of if as_of is not None else self._now(), "as_of")
        selected, fallback = self._select_binding(venue, symbol, range)
        dataset = self._dataset_loader(selected.dataset_id)
        dataset_name = getattr(dataset, "name", None)
        if dataset_name != selected.dataset_id:
            raise HistoryUnavailableError(
                f"dataset identity {dataset_name!r} does not match binding {selected.dataset_id!r}"
            )
        dataset_manifest = getattr(dataset, "manifest", None)
        if not isinstance(dataset_manifest, DatasetManifest):
            raise HistoryUnavailableError(
                "dataset loader did not return a manifest-gated Dataset"
            )
        if dataset_manifest.dataset != selected.dataset_id:
            raise HistoryUnavailableError(
                f"manifest identity {dataset_manifest.dataset!r} does not match binding "
                f"{selected.dataset_id!r}"
            )
        matching_coverage = [
            item
            for item in dataset_manifest.coverage
            if item.interval == selected.interval
            and item.venue is venue
            and item.symbol == symbol
        ]
        if len(matching_coverage) != 1:
            raise HistoryUnavailableError(
                "manifest coverage must contain exactly one bound "
                f"{selected.interval}/{venue.value}/{symbol} series"
            )
        manifest_coverage = matching_coverage[0]
        normalized_coverage = CoverageSnapshot(
            interval=manifest_coverage.interval,
            venue=manifest_coverage.venue,
            symbol=manifest_coverage.symbol,
            start=_aware_utc(manifest_coverage.start, "coverage start"),
            end=_aware_utc(manifest_coverage.end, "coverage end"),
            rows=manifest_coverage.rows,
        )
        start = selected_as_of - _WINDOW[range]
        rows = dataset.read_bars(
            interval=selected.interval,
            venue=venue,
            symbol=symbol,
            start=start,
            end=selected_as_of,
        )
        if not rows:
            raise HistoryUnavailableError(
                f"empty requested window for {venue.value}:{symbol} {range.value}"
            )
        historical = self._validate_and_convert_rows(
            rows,
            selected=selected,
            start=start,
            as_of=selected_as_of,
            coverage=normalized_coverage,
        )
        timestamps = [item.timestamp for item in historical]
        if selected.calendar == _CONTINUOUS_CALENDAR:
            gaps = tuple(find_gaps(timestamps, interval=selected.interval))
            limitations: tuple[str, ...] = ()
        elif selected.calendar == "XNYS" and selected.interval == "1d":
            sessions = CalendarService().sessions(
                "XNYS",
                historical[0].timestamp.astimezone(_NEW_YORK).date(),
                historical[-1].timestamp.astimezone(_NEW_YORK).date(),
                policy=SessionPolicy.REGULAR,
            )
            observed_dates = {
                item.timestamp.astimezone(_NEW_YORK).date() for item in historical
            }
            gaps = tuple(
                session.open_at
                for session in sessions
                if session.session_date not in observed_dates
            )
            limitations = ()
        else:
            gaps = ()
            limitations = (
                "Gap detection requires a session calendar and was not run for "
                f"{selected.calendar}.",
            )
        if selected.adjustment != "unadjusted":
            limitations += (
                "adjusted_close is unavailable without immutable adjustment lineage.",
            )
        return HistoricalSeries(
            instrument=historical[0].instrument,
            range=range,
            as_of=selected_as_of,
            bars=tuple(historical),
            dataset_id=selected.dataset_id,
            dataset_revision=dataset_manifest.revision,
            source=dataset_manifest.source,
            license=dataset_manifest.license,
            generated_at=_aware_utc(dataset_manifest.generated_at, "generated_at"),
            interval=selected.interval,
            calendar=selected.calendar,
            adjustment=selected.adjustment,
            coverage=normalized_coverage,
            gaps=gaps,
            duplicates=(),
            limitations=limitations,
            resolution_fallback=fallback,
        )

    def compare(
        self,
        *,
        primary: tuple[Venue, str],
        peers: Iterable[tuple[Venue, str]],
        range: HistoryRange,
        as_of: datetime | None = None,
    ) -> ComparisonSeries:
        """Rebase closes over timestamps observed by every requested series."""
        identities = [primary, *peers]
        keys = tuple(_key(venue, symbol) for venue, symbol in identities)
        if len(keys) < 2:
            raise HistoryUnavailableError(
                "comparison requires a primary and at least one peer"
            )
        if len(set(keys)) != len(keys):
            raise HistoryUnavailableError("duplicate comparison instrument")
        selected_as_of = _aware_utc(as_of if as_of is not None else self._now(), "as_of")
        comparison_bindings = self._select_comparison_bindings(identities, range)
        comparison_reader = HistoryService(
            comparison_bindings,
            dataset_loader=self._dataset_loader,
            now=lambda: selected_as_of,
        )
        series = [
            comparison_reader.history(venue, symbol, range, as_of=selected_as_of)
            for venue, symbol in identities
        ]
        for current in series:
            if any(item.is_live_tail for item in current.bars):
                raise HistoryUnavailableError("comparison cannot include live-tail values")
            if any(getattr(item, "is_forecast", False) for item in current.bars):
                raise HistoryUnavailableError("comparison cannot include forecast values")
        by_timestamp = [
            {item.timestamp: item.close for item in current.bars} for current in series
        ]
        shared = set(by_timestamp[0])
        for values in by_timestamp[1:]:
            shared.intersection_update(values)
        timestamps = sorted(shared)
        if len(timestamps) < 2:
            raise HistoryUnavailableError(
                "comparison requires at least two shared observed points"
            )
        bases = [values[timestamps[0]] for values in by_timestamp]
        if any(not math.isfinite(base) or base <= 0 for base in bases):
            raise HistoryUnavailableError(
                "comparison base closes must be finite and positive"
            )
        points = tuple(
            ComparisonPoint(
                timestamp=timestamp,
                values={
                    key: by_timestamp[index][timestamp] / bases[index] * 100.0
                    for index, key in enumerate(keys)
                },
            )
            for timestamp in timestamps
        )
        limitations = tuple(
            dict.fromkeys(
                limitation
                for current in series
                for limitation in current.limitations
            )
        )
        resolution_fallbacks = tuple(
            dict.fromkeys(
                current.resolution_fallback
                for current in series
                if current.resolution_fallback is not None
            )
        )
        if resolution_fallbacks:
            limitations = (
                *limitations,
                "Comparison uses shared observed resolution fallback "
                f"{', '.join(resolution_fallbacks)}.",
            )
        return ComparisonSeries(
            range=range,
            as_of=selected_as_of,
            keys=keys,
            points=points,
            limitations=limitations,
        )

    def _select_comparison_bindings(
        self,
        identities: list[tuple[Venue, str]],
        requested_range: HistoryRange,
    ) -> tuple[DatasetBinding, ...]:
        """Select one observed resolution available for every instrument.

        Comparison never resamples or forward-fills. When the preferred
        resolution is not common to every instrument, use the finest common
        coarser binding and preserve its fallback in each returned series.
        """
        preferred_step = interval_to_timedelta(_PREFERRED_INTERVAL[requested_range])
        candidates: list[dict[timedelta, DatasetBinding]] = []
        for venue, symbol in identities:
            by_resolution = {
                interval_to_timedelta(binding.interval): binding
                for binding in self._bindings
                if binding.venue is venue
                and binding.symbol == symbol
                and interval_to_timedelta(binding.interval) >= preferred_step
            }
            if not by_resolution:
                raise HistoryUnavailableError(
                    f"no preferred or coarser comparison binding for {venue.value}:{symbol}"
                )
            candidates.append(by_resolution)
        shared_resolutions = set(candidates[0])
        for current in candidates[1:]:
            shared_resolutions.intersection_update(current)
        if not shared_resolutions:
            raise HistoryUnavailableError(
                "comparison instruments have no shared observed resolution"
            )
        selected_resolution = min(shared_resolutions)
        return tuple(current[selected_resolution] for current in candidates)

    def _select_binding(
        self,
        venue: Venue,
        symbol: str,
        requested_range: HistoryRange,
    ) -> tuple[DatasetBinding, str | None]:
        candidates = [
            item for item in self._bindings if item.venue is venue and item.symbol == symbol
        ]
        if not candidates:
            raise HistoryUnavailableError(f"unknown venue/symbol {venue.value}:{symbol}")
        preferred = _PREFERRED_INTERVAL[requested_range]
        preferred_step = interval_to_timedelta(preferred)
        exact = [
            item
            for item in candidates
            if interval_to_timedelta(item.interval) == preferred_step
        ]
        if exact:
            return exact[0], None
        coarser = [
            item
            for item in candidates
            if interval_to_timedelta(item.interval) > preferred_step
        ]
        if not coarser:
            raise HistoryUnavailableError(
                f"no preferred or coarser binding for {venue.value}:{symbol} "
                f"({preferred} requested)"
            )
        selected = min(coarser, key=lambda item: interval_to_timedelta(item.interval))
        return selected, f"{preferred}->{selected.interval}"

    @staticmethod
    def _validate_and_convert_rows(
        rows: list[Bar],
        *,
        selected: DatasetBinding,
        start: datetime,
        as_of: datetime,
        coverage: CoverageSnapshot,
    ) -> list[HistoricalBar]:
        converted: list[HistoricalBar] = []
        timestamps: list[datetime] = []
        expected_instrument = None
        for row in rows:
            if getattr(row, "is_live_tail", False):
                raise HistoryUnavailableError("historical reader returned a live-tail row")
            if getattr(row, "is_forecast", False):
                raise HistoryUnavailableError("historical reader returned a forecast row")
            if not isinstance(row, Bar):
                raise HistoryUnavailableError(
                    "historical reader must return canonical Bar rows"
                )
            timestamp = _aware_utc(row.timestamp, "bar timestamp")
            if timestamp > as_of:
                raise HistoryUnavailableError("historical reader returned future leakage")
            if timestamp < start:
                raise HistoryUnavailableError(
                    "historical reader returned data outside the requested window"
                )
            if timestamp < coverage.start or timestamp > coverage.end:
                raise HistoryUnavailableError(
                    "historical reader returned data outside manifest coverage"
                )
            if row.interval != selected.interval:
                raise HistoryUnavailableError("historical reader returned a mixed interval")
            identity = (row.instrument.venue, row.instrument.symbol)
            selected_identity = (selected.venue, selected.symbol)
            if identity != selected_identity:
                raise HistoryUnavailableError("historical reader returned a mixed instrument")
            if expected_instrument is None:
                expected_instrument = row.instrument
            elif row.instrument != expected_instrument:
                raise HistoryUnavailableError(
                    "historical reader returned inconsistent instrument metadata"
                )
            timestamps.append(timestamp)
            converted.append(
                HistoricalBar(
                    instrument=row.instrument,
                    timestamp=timestamp,
                    interval=row.interval,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    adjusted_close=None,
                    is_live_tail=False,
                )
            )
        if len(set(timestamps)) != len(timestamps):
            raise HistoryUnavailableError("historical reader returned a duplicate timestamp")
        if timestamps != sorted(timestamps):
            raise HistoryUnavailableError("historical reader returned a non-monotonic series")
        if start <= coverage.start and as_of >= coverage.end:
            if len(timestamps) != coverage.rows:
                raise HistoryUnavailableError(
                    "manifest coverage row count does not match the full requested read"
                )
            if timestamps[0] != coverage.start or timestamps[-1] != coverage.end:
                raise HistoryUnavailableError(
                    "manifest coverage extent does not match the full requested read"
                )
        return converted
