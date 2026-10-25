"""Five bounded development-replay interfaces; no public input qualification."""

import asyncio
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from quantmesh.research.spy_replay import (
    DecisionRequest,
    ReplayError,
    ReplayJob,
    ReplayOptions,
    ReplayRequest,
    digest,
)

_STATUS = {
    "not_found": 404,
    "idempotency_conflict": 409,
    "decision_conflict": 409,
    "capacity_exceeded": 409,
    "job_not_succeeded": 409,
    "artifact_invalid": 409,
    "service_closed": 409,
    "invalid_request": 422,
    "input_not_qualified": 422,
    "input_pin_mismatch": 422,
    "paper_not_authorized": 422,
    "service_unavailable": 503,
}


class _Route(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe(request):
            try:
                if request.method == "POST":
                    from quantmesh.api.workstation import _json_guard_origin

                    _json_guard_origin(request, "SPY replay")
                    raw = bytearray()
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > 8192:
                            raise HTTPException(422, "invalid_request")
                        raw.extend(chunk)
                    from quantmesh.research.spy_replay import _json

                    _json(raw)  # Duplicate keys/nonfinite JSON cannot change signed pins.

                    async def receive():
                        return {"type": "http.request", "body": bytes(raw), "more_body": False}

                    request = Request(request.scope, receive)
                return await handler(request)
            except HTTPException:
                raise
            except RequestValidationError:
                raise HTTPException(422, "invalid_request") from None
            except ReplayError as error:
                code = str(error)
                raise HTTPException(
                    _STATUS.get(code, 503), code if code in _STATUS else "service_unavailable"
                ) from None
            except (ValueError, UnicodeError):
                raise HTTPException(422, "invalid_request") from None
            except Exception:
                raise HTTPException(503, "service_unavailable") from None

        return safe


def create_spy_replay_router():
    router = APIRouter(prefix="/research/spy-replay", route_class=_Route)

    def authority(request):
        service = getattr(request.app.state, "spy_replay", None)
        if service is None:
            raise ReplayError("service_unavailable")
        return service

    @router.get("", response_model=ReplayOptions)
    def options(request: Request):
        service = getattr(request.app.state, "spy_replay", None)
        return (
            service.options()
            if service is not None
            else ReplayOptions(configured=False, unavailable_reason="not_configured", input=None)
        )

    @router.post("/jobs", response_model=ReplayJob, status_code=201)
    def submit(
        body: ReplayRequest, request: Request, response: Response, idempotency_key: UUID = Header()
    ):
        job, created = authority(request).submit(body, idempotency_key)
        response.status_code = 201 if created else 200
        return job

    @router.get("/jobs/{job_id}", response_model=ReplayJob)
    def status(job_id: UUID, request: Request):
        return authority(request).get(job_id)

    @router.get("/jobs/{job_id}/artifact")
    def artifact(job_id: UUID, request: Request, kind: Literal["report", "decision"] = "report"):
        raw = authority(request).artifact(job_id, kind)
        return Response(
            raw,
            media_type="application/json",
            headers={
                "X-Content-SHA256": digest(raw),
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="spy-replay-{job_id}-{kind}.json"',
            },
        )

    @router.post("/jobs/{job_id}/decision", response_model=ReplayJob, status_code=201)
    def decide(
        job_id: UUID,
        body: DecisionRequest,
        request: Request,
        response: Response,
        idempotency_key: UUID = Header(),
    ):
        job, created = authority(request).decide(job_id, body, idempotency_key)
        response.status_code = 201 if created else 200
        return job

    return router


def attach_spy_replay_runtime(app, service):
    """Own this service through the original app lifespan, including failed startup."""
    original = app.router.lifespan_context
    app.state.spy_replay = service

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original(app):
                yield
        finally:
            task = asyncio.create_task(asyncio.to_thread(service.close))
            cancelled = False
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
            task.result()
            if cancelled:
                raise asyncio.CancelledError

    app.router.lifespan_context = lifespan
