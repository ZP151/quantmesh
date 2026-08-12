"""Shared historical + continuity-safe live-tail composition."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import MANIFEST_NAME, DatasetClass
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.contracts import (
    ComparisonSeries,
    CoverageSnapshot,
    DatasetBinding,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    LiveTailLineage,
)
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)
from quantmesh.live.feed import LiveFeed

_LIVE_REJECTION_PREFIX = "Live candle was not joined: "
_WINDOW = {
    HistoryRange.ONE_DAY: timedelta(days=1),
    HistoryRange.FIVE_DAYS: timedelta(days=5),
    HistoryRange.ONE_MONTH: timedelta(days=31),
    HistoryRange.THREE_MONTHS: timedelta(days=93),
    HistoryRange.SIX_MONTHS: timedelta(days=186),
    HistoryRange.ONE_YEAR: timedelta(days=366),
}
_PREFERRED_INTERVAL = {
    HistoryRange.ONE_DAY: "5m",
    HistoryRange.FIVE_DAYS: "30m",
    HistoryRange.ONE_MONTH: "1h",
    HistoryRange.THREE_MONTHS: "1d",
    HistoryRange.SIX_MONTHS: "1d",
    HistoryRange.ONE_YEAR: "1d",
}


def discover_history_bindings(lake_root: Path) -> tuple[DatasetBinding, ...]:
    """Discover only explicitly observed manifest-gated datasets."""
    lake = Lake(Path(lake_root))
    bindings: list[DatasetBinding] = []
    for manifest_path in sorted(Path(lake_root).glob(f"*/{MANIFEST_NAME}")):
        dataset = lake.dataset(manifest_path.parent.name)
        if dataset.manifest.data_class is not DatasetClass.OBSERVED:
            continue
        for coverage in dataset.manifest.coverage:
            bindings.append(
                DatasetBinding(
                    dataset_id=dataset.name,
                    interval=coverage.interval,
                    venue=coverage.venue,
                    symbol=coverage.symbol,
                    calendar="XNYS" if coverage.venue is Venue.MOOMOO else "24/7",
                    adjustment="unadjusted",
                )
            )
    return tuple(bindings)


def _rebuild_series(
    series: HistoricalSeries,
    *,
    bars: tuple[HistoricalBar, ...],
    limitations: tuple[str, ...],
) -> HistoricalSeries:
    return HistoricalSeries(
        instrument=series.instrument,
        range=series.range,
        as_of=series.as_of,
        bars=bars,
        dataset_id=series.dataset_id,
        dataset_revision=series.dataset_revision,
        source=series.source,
        license=series.license,
        generated_at=series.generated_at,
        interval=series.interval,
        calendar=series.calendar,
        adjustment=series.adjustment,
        coverage=series.coverage,
        coverage_scope=series.coverage_scope,
        gaps=series.gaps,
        duplicates=series.duplicates,
        limitations=limitations,
        resolution_fallback=series.resolution_fallback,
    )


def _append_limitation(series: HistoricalSeries, reason: str) -> HistoricalSeries:
    limitation = f"{_LIVE_REJECTION_PREFIX}{reason}"
    limitations = tuple(dict.fromkeys((*series.limitations, limitation)))
    return _rebuild_series(series, bars=series.bars, limitations=limitations)


def _numeric_candle(payload: Mapping[str, object]) -> tuple[dict[str, float] | None, str | None]:
    values: dict[str, float] = {}
    for field in ("open", "high", "low", "close", "volume"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"{field} must be a finite number"
        number = float(value)
        if not math.isfinite(number):
            return None, f"{field} must be a finite number"
        values[field] = number
    if any(values[field] <= 0 for field in ("open", "high", "low", "close")):
        return None, "OHLC prices must be positive"
    if values["volume"] < 0:
        return None, "volume must be non-negative"
    if values["high"] < max(values["open"], values["close"]) or values["low"] > min(
        values["open"], values["close"]
    ):
        return None, "OHLC values are inconsistent"
    return values, None


def join_live_tail(
    series: HistoricalSeries,
    feed: LiveFeed | None,
    *,
    as_of: datetime,
) -> HistoricalSeries:
    """Join exactly one proven fresh candle to a historical series."""
    if feed is None:
        return series
    snapshot = feed.snapshot_exact(
        series.instrument.venue,
        series.instrument.symbol,
        UpdateKind.CANDLE,
        as_of=as_of,
    )
    if snapshot is None:
        return series
    if snapshot.provenance not in (Provenance.REAL, Provenance.DELAYED):
        return _append_limitation(series, "provenance is not real or delayed")
    received_at = snapshot.received_at
    if received_at.tzinfo is None:
        return _append_limitation(series, "received_at must be timezone-aware")
    received_at = received_at.astimezone(UTC)
    if received_at > as_of:
        return _append_limitation(series, "received_at is later than the request time")
    if as_of - received_at > feed.lag:
        return _append_limitation(series, "received_at is outside the live freshness horizon")
    if snapshot.age_ms is None or snapshot.freshness_label not in ("real", "delayed"):
        return _append_limitation(series, "freshness evidence is absent or invalid")
    payload_interval = snapshot.payload.get("interval")
    if not isinstance(payload_interval, str):
        return _append_limitation(series, "payload interval is absent or invalid")
    try:
        interval_to_timedelta(payload_interval)
    except ValueError:
        return _append_limitation(series, "payload interval is absent or invalid")
    if payload_interval != series.interval:
        return _append_limitation(
            series,
            f"payload interval {payload_interval!r} does not exactly match {series.interval!r}",
        )
    if series.adjustment != "unadjusted":
        return _append_limitation(
            series,
            "adjusted historical series cannot be matched to an unadjusted live candle",
        )
    data_time = snapshot.data_time
    if data_time.tzinfo is None:
        return _append_limitation(series, "data_time must be timezone-aware")
    data_time = data_time.astimezone(UTC)
    if data_time > as_of:
        return _append_limitation(series, "data_time is later than the request time")
    values, numeric_error = _numeric_candle(snapshot.payload)
    if numeric_error is not None or values is None:
        return _append_limitation(series, numeric_error or "OHLCV payload is invalid")
    if type(snapshot.sequence) is not int or snapshot.sequence < 0:
        return _append_limitation(series, "sequence is absent or invalid")
    if snapshot.sequence_gap is not False or not snapshot.continuity_proven:
        return _append_limitation(series, "sequence continuity is not proven")
    if (
        type(snapshot.predecessor_sequence) is not int
        or snapshot.predecessor_sequence < 0
        or snapshot.predecessor_data_time is None
        or snapshot.predecessor_data_time.tzinfo is None
    ):
        return _append_limitation(series, "sequence predecessor evidence is absent or invalid")

    last = series.bars[-1]
    expected_next = last.timestamp + interval_to_timedelta(series.interval)
    if data_time == last.timestamp:
        retained = series.bars[:-1]
    elif data_time == expected_next:
        retained = series.bars
    elif data_time < last.timestamp:
        return _append_limitation(series, "data_time is older than the final historical bar")
    else:
        return _append_limitation(series, "data_time is not the next contiguous interval")

    live_bar = HistoricalBar(
        instrument=series.instrument,
        timestamp=data_time,
        interval=series.interval,
        open=values["open"],
        high=values["high"],
        low=values["low"],
        close=values["close"],
        volume=values["volume"],
        adjusted_close=None,
        is_live_tail=True,
        live_lineage=LiveTailLineage(
            source=snapshot.source,
            venue=snapshot.venue,
            instrument=snapshot.instrument,
            provenance=snapshot.provenance,
            data_time=data_time,
            received_at=received_at,
            interval=payload_interval,
            sequence=snapshot.sequence,
            predecessor_sequence=snapshot.predecessor_sequence,
            predecessor_data_time=snapshot.predecessor_data_time,
            sequence_gap=False,
            continuity_proven=True,
            freshness_label=snapshot.freshness_label,
            age_ms=snapshot.age_ms,
        ),
    )
    limitations = tuple(
        dict.fromkeys(
            (
                *series.limitations,
                "manifest coverage is historical-only; the live-tail bar is excluded",
            )
        )
    )
    return _rebuild_series(series, bars=(*retained, live_bar), limitations=limitations)


def _instrument(venue: Venue, symbol: str) -> Instrument:
    if venue is Venue.MOOMOO:
        kind = InstrumentType.EQUITY
    elif venue is Venue.HYPERLIQUID:
        kind = InstrumentType.PERPETUAL
    else:
        kind = InstrumentType.PREDICTION
    return Instrument(symbol=symbol, venue=venue, instrument_type=kind, currency="USD")


def _replay_series(
    feed: LiveFeed,
    venue: Venue,
    symbol: str,
    selected_range: HistoryRange,
    *,
    as_of: datetime,
) -> HistoricalSeries:
    buffer = feed.replay_buffer
    if buffer is None:
        raise HistoryUnavailableError("no manifest history or live replay buffer is attached")
    window_start = as_of - _WINDOW[selected_range]
    updates = buffer.replay(
        venue=venue.value,
        instrument=symbol,
        kinds={UpdateKind.CANDLE.value, UpdateKind.STATUS.value},
        start=window_start,
        end=as_of,
        data_time_start=window_start,
        data_time_end=as_of,
        limit=10_000,
        tail=True,
    )
    by_interval: dict[str, list] = {}
    for update in updates:
        interval = update.payload.get("interval")
        if isinstance(interval, str):
            try:
                interval_to_timedelta(interval)
            except ValueError:
                continue
            by_interval.setdefault(interval, []).append(update)
    if not by_interval:
        raise HistoryUnavailableError(
            f"no replay candles for {venue.value}:{symbol} {selected_range.value}"
        )
    preferred_interval = _PREFERRED_INTERVAL[selected_range]
    preferred = interval_to_timedelta(preferred_interval)
    eligible_intervals = tuple(
        value for value in by_interval if interval_to_timedelta(value) >= preferred
    )
    if not eligible_intervals:
        raise HistoryUnavailableError(
            "no replay candles at the preferred or a coarser resolution for "
            f"{venue.value}:{symbol} {selected_range.value}"
        )
    interval = min(
        eligible_intervals,
        key=lambda value: (
            interval_to_timedelta(value),
            value != preferred_interval,
            value,
        ),
    )

    segment: list[tuple[MarketUpdate, dict[str, float]]] = []
    for update in updates:
        if update.kind is UpdateKind.STATUS:
            if update.state in (SourceState.DISCONNECTED, SourceState.UNAVAILABLE):
                segment = []
            continue
        if update.payload.get("interval") != interval:
            continue
        values, error = _numeric_candle(update.payload)
        if (
            error is not None
            or values is None
            or update.provenance not in (Provenance.REAL, Provenance.DELAYED)
            or update.sequence_gap
            or type(update.sequence) is not int
        ):
            segment = []
            continue
        if not segment:
            segment = [(update, values)]
            continue
        previous = segment[-1][0]
        same = update.data_time == previous.data_time and update.sequence >= previous.sequence
        next_bar = (
            update.data_time == previous.data_time + interval_to_timedelta(interval)
            and update.sequence > previous.sequence
        )
        if same:
            segment[-1] = (update, values)
        elif next_bar:
            segment.append((update, values))
        else:
            segment = [(update, values)]
    if len(segment) < 2:
        raise HistoryUnavailableError(
            f"live replay continuity is not proven for {venue.value}:{symbol}"
        )
    instrument = _instrument(venue, symbol)
    bars = tuple(
        HistoricalBar(
            instrument=instrument,
            timestamp=update.data_time,
            interval=interval,
            open=values["open"],
            high=values["high"],
            low=values["low"],
            close=values["close"],
            volume=values["volume"],
        )
        for update, values in segment
    )
    generated_at = max(update.received_at for update, _values in segment)
    return HistoricalSeries(
        instrument=instrument,
        range=selected_range,
        as_of=as_of,
        bars=bars,
        dataset_id=f"live-replay-{venue.value}-{symbol.lower()}",
        dataset_revision=1,
        source=f"{venue.value}-live-replay",
        license="venue-public-market-data",
        generated_at=generated_at,
        interval=interval,
        calendar="XNYS" if venue is Venue.MOOMOO else "24/7",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval=interval,
            venue=venue,
            symbol=symbol,
            start=bars[0].timestamp,
            end=bars[-1].timestamp,
            rows=len(bars),
        ),
        limitations=(
            "Manifest history unavailable; showing continuity-checked local live replay only.",
        ),
        resolution_fallback=(
            None
            if interval_to_timedelta(interval) == preferred
            else f"{preferred_interval}->{interval}"
        ),
    )


class LiveHistoryService:
    """One shared history authority for both history and workspace APIs."""

    def __init__(self, historical: HistoryService | None, feed: LiveFeed) -> None:
        self._historical = historical
        self._feed = feed

    def history(
        self,
        venue: Venue,
        symbol: str,
        range: HistoryRange,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalSeries:
        selected_as_of = as_of if as_of is not None else datetime.now(UTC)
        if selected_as_of.tzinfo is None:
            raise HistoryUnavailableError("as_of must be timezone-aware")
        selected_as_of = selected_as_of.astimezone(UTC)
        observed = None
        if self._historical is not None:
            try:
                observed = self._historical.history(
                    venue,
                    symbol,
                    range,
                    as_of=selected_as_of,
                )
            except HistoryUnavailableError:
                observed = None
        if observed is None:
            observed = _replay_series(
                self._feed,
                venue,
                symbol,
                range,
                as_of=selected_as_of,
            )
        return join_live_tail(observed, self._feed, as_of=selected_as_of)

    def compare(
        self,
        *,
        primary: tuple[Venue, str],
        peers: Sequence[tuple[Venue, str]],
        range: HistoryRange,
        as_of: datetime | None = None,
    ) -> ComparisonSeries:
        if self._historical is None:
            raise HistoryUnavailableError(
                "comparison requires manifest-backed history for every instrument"
            )
        return self._historical.compare(
            primary=primary,
            peers=peers,
            range=range,
            as_of=as_of,
        )
