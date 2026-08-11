"""Read-only venue-aware historical instrument API."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from quantmesh.data.layout import validate_symbol
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Side, Venue
from quantmesh.instruments.contracts import (
    ComparisonSeries,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    InstrumentWorkspace,
    LiveTailLineage,
    PaperProposal,
    ProposalConfirmation,
    ProposalStatus,
)
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.instruments.proposals import PaperDecisionService
from quantmesh.instruments.workspace import InstrumentWorkspaceService
from quantmesh.live.contract import Provenance, UpdateKind
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


class ProposalCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: Venue
    symbol: str
    artifact_id: str
    side: Side
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)


class ProposalConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_token: str = Field(min_length=1, max_length=128)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _guard_json_origin(request: Request, surface: str) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    try:
        hostname = urlsplit(origin).hostname
        loopback = hostname == "localhost" or (
            hostname is not None and ip_address(hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback:
        raise HTTPException(
            status_code=403,
            detail=f"{surface} refused: cross-origin send is not loopback",
        )


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
        raise _unprocessable(f"compare supports at most {_MAX_COMPARE_QUERY_VALUES} query values")
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
        coverage_scope=series.coverage_scope,
        gaps=series.gaps,
        duplicates=series.duplicates,
        limitations=limitations,
        resolution_fallback=series.resolution_fallback,
    )


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


def _join_live_tail(
    series: HistoricalSeries,
    feed: LiveFeed | None,
    *,
    as_of: datetime,
) -> HistoricalSeries:
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
    if not isinstance(received_at, datetime) or received_at.tzinfo is None:
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
    if not isinstance(data_time, datetime) or data_time.tzinfo is None:
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
        or not isinstance(snapshot.predecessor_data_time, datetime)
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
    return _rebuild_series(
        series,
        bars=(*retained, live_bar),
        limitations=limitations,
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
        except HistoryUnavailableError as error:
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

    @router.get(
        "/instruments/{venue}/{symbol}/workspace",
        response_model=InstrumentWorkspace,
        name="instrument_workspace",
    )
    def workspace(
        request: Request,
        venue: Venue,
        symbol: str,
        selected_range: Annotated[HistoryRange, Query(alias="range")],
        compare: Annotated[list[str] | None, Query()] = None,
    ) -> InstrumentWorkspace:
        _validate_api_symbol(symbol, field="symbol")
        peers = _parse_compare(compare, primary=(venue, symbol))
        history = getattr(request.app.state, "history", None)
        if not isinstance(history, HistoryService):
            raise HTTPException(
                status_code=404,
                detail="no instrument workspace service is attached",
            )
        forecasts = getattr(request.app.state, "price_forecasts", None)
        decisions = getattr(request.app.state, "proposal_service", None)
        if not isinstance(decisions, PaperDecisionService):
            decisions = getattr(request.app.state, "paper_decisions", None)
        clock = getattr(request.app.state, "instrument_clock", None)
        if not callable(clock):

            def clock() -> datetime:
                return datetime.now(UTC)

        service = InstrumentWorkspaceService(
            history=history,
            forecasts=forecasts,
            account_provider=lambda: request.app.state.account,
            marks_provider=lambda: request.app.state.marks,
            live_feed=getattr(request.app.state, "live", None),
            decisions=(decisions if isinstance(decisions, PaperDecisionService) else None),
            now=clock,
        )
        try:
            return service.render(venue, symbol, selected_range, peers=peers)
        except HistoryUnavailableError as error:
            raise HTTPException(
                status_code=404,
                detail=f"instrument workspace unavailable: {error}",
            ) from error

    @router.post(
        "/paper/proposals",
        response_model=PaperProposal,
        name="create_paper_proposal",
    )
    def create_proposal(request: Request, body: ProposalCreateBody) -> PaperProposal:
        _guard_json_origin(request, "paper proposal")
        _validate_api_symbol(body.symbol, field="symbol")
        registry = getattr(request.app.state, "price_forecasts", None)
        decisions = getattr(request.app.state, "proposal_service", None)
        if not isinstance(decisions, PaperDecisionService):
            decisions = getattr(request.app.state, "paper_decisions", None)
        if not callable(getattr(registry, "get", None)) or not isinstance(
            decisions, PaperDecisionService
        ):
            raise HTTPException(status_code=404, detail="no paper proposal service is attached")
        try:
            artifact = registry.get(body.artifact_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if artifact.instrument.venue is not body.venue or artifact.instrument.symbol != body.symbol:
            raise _unprocessable("proposal venue and symbol must match the forecast artifact")
        try:
            return decisions.propose(
                artifact.id,
                side=body.side,
                quantity=body.quantity,
                limit_price=body.limit_price,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post(
        "/paper/proposals/{proposal_id}/confirm",
        response_model=ProposalConfirmation,
        responses={409: {"model": ProposalConfirmation}},
        name="confirm_paper_proposal",
    )
    def confirm_proposal(
        request: Request,
        proposal_id: str,
        body: ProposalConfirmBody,
    ) -> ProposalConfirmation | JSONResponse:
        _guard_json_origin(request, "paper proposal confirmation")
        decisions = getattr(request.app.state, "proposal_service", None)
        if not isinstance(decisions, PaperDecisionService):
            decisions = getattr(request.app.state, "paper_decisions", None)
        if not isinstance(decisions, PaperDecisionService):
            raise HTTPException(status_code=404, detail="no paper proposal service is attached")
        try:
            before = decisions.ledger.get(proposal_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        result = decisions.confirm(
            proposal_id,
            confirmation=body.confirmation_token,
            now=decisions.current_time(),
        )
        if before.status is ProposalStatus.BLOCKED:
            return JSONResponse(status_code=409, content=jsonable_encoder(result))
        if before.status is not ProposalStatus.PENDING:
            return result
        if result.proposal.status is ProposalStatus.CONFIRMED:
            return result
        return JSONResponse(status_code=409, content=jsonable_encoder(result))

    return router
