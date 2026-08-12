"""Read-only venue-aware historical instrument API."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from quantmesh.data.layout import validate_symbol
from quantmesh.domain.models import Side, Venue
from quantmesh.instruments.contracts import (
    ComparisonSeries,
    HistoricalSeries,
    HistoryRange,
    InstrumentWorkspace,
    PaperProposal,
    ProposalConfirmation,
    ProposalStatus,
)
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.instruments.proposals import PaperDecisionService
from quantmesh.instruments.workspace import InstrumentWorkspaceService
from quantmesh.live.feed import LiveFeed

_MAX_COMPARE_INSTRUMENTS = 3
_MAX_COMPARE_QUERY_VALUES = 8
_MAX_SYMBOL_LENGTH = 64
_MAX_COMPARE_VALUE_LENGTH = 256


class HistoricalPayload(BaseModel):
    """Stable wire envelope for observed history and optional comparison."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    primary: HistoricalSeries
    comparison: ComparisonSeries | None = None


class ProposalCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

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
        if not isinstance(service, (HistoryService, LiveHistoryService)):
            raise HTTPException(status_code=404, detail="no historical service is attached")
        live = getattr(request.app.state, "live", None)
        if isinstance(live, LiveFeed) and not isinstance(service, LiveHistoryService):
            service = LiveHistoryService(service, live)
        clock = getattr(request.app.state, "instrument_clock", None)
        as_of = clock() if callable(clock) else datetime.now(UTC)
        if not isinstance(as_of, datetime) or as_of.tzinfo is None:
            raise HTTPException(status_code=500, detail="instrument clock is invalid")
        as_of = as_of.astimezone(UTC)
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
        live = getattr(request.app.state, "live", None)
        if not isinstance(history, (HistoryService, LiveHistoryService)):
            raise HTTPException(
                status_code=404,
                detail="no instrument workspace service is attached",
            )
        effective_history = history
        if isinstance(live, LiveFeed) and not isinstance(history, LiveHistoryService):
            effective_history = LiveHistoryService(history, live)
        forecasts = getattr(request.app.state, "price_forecasts", None)
        decisions = getattr(request.app.state, "proposal_service", None)
        if not isinstance(decisions, PaperDecisionService):
            decisions = getattr(request.app.state, "paper_decisions", None)
        clock = getattr(request.app.state, "instrument_clock", None)
        if not callable(clock):

            def clock() -> datetime:
                return datetime.now(UTC)

        service = InstrumentWorkspaceService(
            history=effective_history,
            forecasts=forecasts,
            account_provider=lambda: request.app.state.account,
            marks_provider=lambda: request.app.state.marks,
            valuation_provider=(
                request.app.state.mark_snapshot_provider
                if callable(getattr(request.app.state, "mark_snapshot_provider", None))
                else None
            ),
            live_feed=live if isinstance(live, LiveFeed) else None,
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
