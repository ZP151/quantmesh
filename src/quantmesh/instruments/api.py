"""Read-only venue-aware historical instrument API."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from quantmesh.data.layout import validate_symbol
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import (
    ComparisonSeries,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
)
from quantmesh.instruments.history import HistoryService
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed

_MAX_COMPARE_INSTRUMENTS = 3
_MAX_COMPARE_QUERY_VALUES = 8
_MAX_SYMBOL_LENGTH = 64
_MAX_COMPARE_VALUE_LENGTH = 256
_LIVE_REJECTION_PREFIX = "Live candle was not joined: "


class HistoricalPayload(BaseModel):
    """Stable wire envelope for observed history and optional comparison."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    primary: HistoricalSeries
    comparison: ComparisonSeries | None = None


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _validate_api_symbol(symbol: str, *, field: str) -> str:
    if len(symbol) > _MAX_SYMBOL_LENGTH:
        raise _unprocessable(f"{field} exceeds {_MAX_SYMBOL_LENGTH} characters")
    try:
        validate_symbol(symbol)
    except ValueError as error:
        raise _unprocessable(str(error)) from error
    return symbol


def _parse_compare(
    raw_values: list[str] | None,
    *,
    primary: tuple[Venue, str],
) -> tuple[tuple[Venue, str], ...]:
    if raw_values is None:
        return ()
    if len(raw_values) > _MAX_COMPARE_QUERY_VALUES:
        raise _unprocessable(
            f"compare supports at most {_MAX_COMPARE_QUERY_VALUES} query values"
        )
    peers: list[tuple[Venue, str]] = []
    seen: set[tuple[Venue, str]] = set()
    for raw in raw_values:
        if not raw or len(raw) > _MAX_COMPARE_VALUE_LENGTH:
            raise _unprocessable("compare values must be non-empty and at most 256 characters")
        tokens = raw.split(",")
        if any(not token for token in tokens):
            raise _unprocessable("compare must use comma-separated 'venue:symbol' values")
        for token in tokens:
            if token.count(":") != 1:
                raise _unprocessable("compare must use comma-separated 'venue:symbol' values")
            venue_raw, symbol = token.split(":", 1)
            try:
                venue = Venue(venue_raw)
            except ValueError as error:
                raise _unprocessable(f"unknown comparison venue {venue_raw!r}") from error
            _validate_api_symbol(symbol, field="comparison symbol")
            identity = (venue, symbol)
            if identity == primary:
                raise _unprocessable("compare cannot contain the primary instrument")
            if identity in seen:
                continue
            if len(peers) >= _MAX_COMPARE_INSTRUMENTS:
                raise _unprocessable(
                    f"compare supports at most {_MAX_COMPARE_INSTRUMENTS} instruments"
                )
            seen.add(identity)
            peers.append(identity)
    return tuple(peers)


def _latest_candle(
    feed: LiveFeed,
    *,
    venue: Venue,
    symbol: str,
) -> MarketUpdate | None:
    """Read the feed's exact typed cache key, avoiding its symbol-only UI projection.

    ``latest_state`` intentionally groups rows for the cockpit by symbol. That
    projection cannot distinguish the same symbol on two venues, while this join
    must. The feed's cache is the owned typed source of truth used to build that
    projection, so this narrow read uses its exact venue/symbol/kind key.
    """

    update = feed._latest.get((venue.value, symbol, UpdateKind.CANDLE.value))
    return update if isinstance(update, MarketUpdate) else None


def _append_limitation(series: HistoricalSeries, reason: str) -> HistoricalSeries:
    limitation = f"{_LIVE_REJECTION_PREFIX}{reason}"
    limitations = tuple(dict.fromkeys((*series.limitations, limitation)))
    return _rebuild_series(series, bars=series.bars, limitations=limitations)


def _rebuild_series(
    series: HistoricalSeries,
    *,
    bars: tuple[HistoricalBar, ...],
    limitations: tuple[str, ...],
) -> HistoricalSeries:
    """Revalidate every field instead of mutating Task 5's frozen response."""

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
        gaps=series.gaps,
        duplicates=series.duplicates,
        limitations=limitations,
        resolution_fallback=series.resolution_fallback,
    )


def _numeric_candle(payload: dict[str, object]) -> tuple[dict[str, float] | None, str | None]:
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


def _join_live_tail(
    series: HistoricalSeries,
    feed: LiveFeed | None,
    *,
    as_of: datetime,
) -> HistoricalSeries:
    if feed is None:
        return series
    update = _latest_candle(
        feed,
        venue=series.instrument.venue,
        symbol=series.instrument.symbol,
    )
    if update is None:
        return series
    if update.provenance not in (Provenance.REAL, Provenance.DELAYED):
        return _append_limitation(series, "provenance is not real or delayed")
    if type(update.sequence) is not int or update.sequence < 0:
        return _append_limitation(series, "sequence is absent or invalid")
    if update.sequence_gap is not False:
        return _append_limitation(series, "sequence continuity is not proven")
    payload_interval = update.payload.get("interval")
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
    data_time = update.data_time
    if not isinstance(data_time, datetime) or data_time.tzinfo is None:
        return _append_limitation(series, "data_time must be timezone-aware")
    data_time = data_time.astimezone(UTC)
    if data_time > as_of:
        return _append_limitation(series, "data_time is later than the request time")
    values, numeric_error = _numeric_candle(update.payload)
    if numeric_error is not None or values is None:
        return _append_limitation(series, numeric_error or "OHLCV payload is invalid")

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
    )
    return _rebuild_series(
        series,
        bars=(*retained, live_bar),
        limitations=series.limitations,
    )


def instrument_router() -> APIRouter:
    router = APIRouter(tags=["instruments"])

    @router.get(
        "/instruments/{venue}/{symbol}/history",
        response_model=HistoricalPayload,
        name="instrument_history",
    )
    def history(
        request: Request,
        venue: Venue,
        symbol: str,
        selected_range: Annotated[HistoryRange, Query(alias="range")],
        compare: Annotated[list[str] | None, Query()] = None,
    ) -> HistoricalPayload:
        _validate_api_symbol(symbol, field="symbol")
        peers = _parse_compare(compare, primary=(venue, symbol))
        service = getattr(request.app.state, "history", None)
        if not isinstance(service, HistoryService):
            raise HTTPException(status_code=404, detail="no historical service is attached")
        as_of = datetime.now(UTC)
        try:
            primary = service.history(venue, symbol, selected_range, as_of=as_of)
            comparison = (
                service.compare(
                    primary=(venue, symbol),
                    peers=peers,
                    range=selected_range,
                    as_of=as_of,
                )
                if peers
                else None
            )
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail=f"historical data unavailable: {error}",
            ) from error
        feed = getattr(request.app.state, "live", None)
        primary = _join_live_tail(
            primary,
            feed if isinstance(feed, LiveFeed) else None,
            as_of=as_of,
        )
        return HistoricalPayload(primary=primary, comparison=comparison)

    return router
