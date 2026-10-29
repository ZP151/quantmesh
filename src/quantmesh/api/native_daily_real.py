"""Fixed local candidate API; accepts references, never data paths or authority flags."""

import asyncio
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response

from quantmesh.api.research_jobs import _SafeRoute
from quantmesh.research.native_daily_real import (
    Contract,
    Digest,
    NativeDailyService,
    NativeDecisionRequest,
    NativeError,
    NativeRequest,
    ObjectRef,
    _loads,
    digest,
)


class _NativeRoute(_SafeRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            if request.method == "POST":
                from quantmesh.api.workstation import _json_guard_origin

                _json_guard_origin(request, "native daily research")
                raw = bytearray()
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > 8192:
                        raise HTTPException(422, "invalid_request")
                    raw.extend(chunk)
                try:
                    _loads(raw)
                except (ValueError, TypeError, RecursionError):
                    raise HTTPException(422, "invalid_request") from None

                async def receive():
                    return {"type": "http.request", "body": bytes(raw), "more_body": False}

                request = Request(request.scope, receive)
            return await handler(request)

        return guarded


class NativeJobView(Contract):
    job_id: str
    request: NativeRequest
    request_digest: Digest
    state: Literal["not_run", "running", "succeeded", "failed", "interrupted"]
    admission_status: Literal["INSUFFICIENT", "REJECT", "ACCEPTED_ENGINEERING"]
    admission: ObjectRef
    admission_reasons: list[str]
    report: ObjectRef | None
    decision: ObjectRef | None
    trial_consumed: bool
    created_at: str
    completed_at: str | None
    financial_qualification: Literal["INSUFFICIENT"]
    paper_allowed: Literal[False]
    live_allowed: Literal[False]


def create_native_daily_router():
    router = APIRouter(prefix="/research/native-daily", route_class=_NativeRoute)

    def authority(request):
        service = getattr(request.app.state, "native_daily", None)
        if service is None:
            raise HTTPException(503, "service_unavailable")
        return service

    def call(function, *args):
        try:
            return function(*args)
        except NativeError as error:
            code = str(error)
            known = {
                "not_found": 404,
                "invalid_request": 422,
                "idempotency_conflict": 409,
                "decision_conflict": 409,
                "capacity_exceeded": 409,
                "artifact_invalid": 409,
                "artifact_unavailable": 409,
                "service_closed": 409,
            }
            raise HTTPException(
                known.get(code, 503), code if code in known else "service_unavailable"
            ) from None

    @router.get("/options")
    def options(request: Request):
        service = getattr(request.app.state, "native_daily", None)
        if service is None:
            return {
                "configured": False,
                "candidate": "doublema_daily_overlay_candidate_v1",
                "kernel": "native-daily-v2",
                "packages": [],
                "grants": [],
                "real_input_enabled": False,
                "financial_qualification": "INSUFFICIENT",
                "paper_allowed": False,
                "live_allowed": False,
            }
        return call(service.options)

    @router.post("/jobs", response_model=NativeJobView, status_code=201)
    def submit(
        body: NativeRequest, request: Request, response: Response, idempotency_key: UUID = Header()
    ):
        job, fresh = call(authority(request).submit, body, str(idempotency_key))
        response.status_code = 201 if fresh else 200
        return job

    @router.get("/jobs/{job_id}", response_model=NativeJobView)
    def read(job_id: UUID, request: Request):
        return call(authority(request).read, str(job_id))

    @router.get("/jobs/{job_id}/artifact")
    def artifact(job_id: UUID, request: Request, kind: Literal["admission", "report", "decision"]):
        raw = call(authority(request).artifact, str(job_id), kind)
        return Response(
            raw,
            media_type="application/json",
            headers={
                "X-Content-SHA256": digest(raw),
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="native-daily-{job_id}-{kind}.json"',
            },
        )

    @router.post("/jobs/{job_id}/decision", response_model=NativeJobView, status_code=201)
    def decide(
        job_id: UUID,
        body: NativeDecisionRequest,
        request: Request,
        response: Response,
        idempotency_key: UUID = Header(),
    ):
        job, fresh = call(authority(request).decide, str(job_id), body, str(idempotency_key))
        response.status_code = 201 if fresh else 200
        return job

    return router


def attach_native_daily_runtime(app, service: NativeDailyService):
    original = app.router.lifespan_context
    app.state.native_daily = service

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original(app):
                yield
        finally:
            task = asyncio.create_task(asyncio.to_thread(service.close))
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            task.result()

    app.router.lifespan_context = lifespan
