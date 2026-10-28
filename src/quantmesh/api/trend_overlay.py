"""Read-only, fixed synthetic policy inspection, independent of research runtimes."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from quantmesh.research.trend_overlay_trace import _canonical, build_trace

CaseId = Literal["campaign", "exit-cap", "cash-cap"]


class TraceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TraceAccount(TraceModel):
    cash: str
    shares: int
    receivable: str


class TraceAction(TraceModel):
    session: int
    kind: str
    signal: str
    reason: str
    requested: int | None
    stages: list[str]
    averages: list[str]


class TraceSizing(TraceModel):
    action: TraceAction
    session: int
    price: str
    requested: int
    allowed: int
    participation_cap: int
    cost_bps: str
    fee_at_allowed: str
    constraints: list[str]


class TraceCampaign(TraceModel):
    shares: int
    initial_price: str | None
    initial_quantity: int
    consumed: list[str]
    pending_full_exit: str | None
    full_exit_origin: TraceAction | None
    last_close: int
    last_fill: int
    terminal_session: int | None
    pending: TraceAction | None
    execution: TraceSizing | None


class TraceClose(TraceModel):
    session: int
    closes: list[str]
    available: bool
    terminal: bool
    unsupported_action: bool


class TraceOpen(TraceModel):
    session: int
    price: str
    prior_volumes: list[str]
    cost_bps: str


class TraceFill(TraceModel):
    session: int
    quantity: int
    price: str


class TraceRow(TraceModel):
    episode: str
    close_session: int
    close_input: TraceClose
    supplied_account: TraceAccount
    campaign_before: TraceCampaign
    action: TraceAction
    sizing: TraceSizing | None
    supplied_fill: TraceFill | None
    open_input: TraceOpen | None = None
    cancelled_remainder: int | None = None
    friction_for_supplied_fill: str | None = None
    campaign_after: TraceCampaign


class TraceSource(TraceModel):
    policy_sha256: str
    trace_runner_sha256: str
    fixture_origin_cli_sha256: str


class TraceArms(TraceModel):
    overlay_off: list[TraceRow]
    overlay_on: list[TraceRow]


class TrendOverlayTrace(TraceModel):
    schema_version: Literal[1]
    candidate: Literal["doublema_daily_overlay_candidate_v1"]
    case: CaseId
    evidence_kind: Literal["synthetic_policy_trace"]
    account_and_fill_inputs: Literal["explicitly_supplied_fixture"]
    assumptions: list[str]
    fixture_sha256: str
    source_identity: TraceSource
    arms: TraceArms
    trace_sha256: str


def trend_overlay_router() -> APIRouter:
    router = APIRouter()

    @router.get(
        "/research/trend-overlay/{case_id}",
        response_model=TrendOverlayTrace,
        response_model_exclude_unset=True,
    )
    async def trend_overlay_trace(case_id: CaseId, request: Request):
        if request.query_params:
            raise HTTPException(400, "fixed_case_only")
        async for chunk in request.stream():
            if chunk:
                raise HTTPException(400, "fixed_case_only")
        trace = build_trace(case_id)
        TrendOverlayTrace.model_validate(trace)
        return Response(
            content=_canonical(trace),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    return router
