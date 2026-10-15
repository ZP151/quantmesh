"""Typed, sanitized workstation facade over one configured research authority."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from quantmesh.research.job_options import ResearchJobOptions
from quantmesh.research.jobs import (
    DatasetRejected,
    IdempotencyConflict,
    JobRecord,
    ResearchJobRequest,
    StoreUnavailable,
)
from quantmesh.research.service_client import ArtifactInvalid


class _SafeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe(request):
            try:
                return await handler(request)
            except HTTPException:
                raise
            except RequestValidationError:
                raise HTTPException(422, "invalid_request") from None
            except ArtifactInvalid:
                raise HTTPException(409, "artifact_invalid") from None
            except IdempotencyConflict:
                raise HTTPException(409, "idempotency_conflict") from None
            except DatasetRejected:
                raise HTTPException(422, "dataset_rejected") from None
            except KeyError:
                raise HTTPException(404, "not_found") from None
            except StoreUnavailable:
                raise HTTPException(503, "service_unavailable") from None
            except ValueError:
                raise HTTPException(422, "invalid_request") from None
            except Exception:
                raise HTTPException(503, "service_unavailable") from None

        return safe


def create_research_jobs_router(client=None) -> APIRouter:
    router = APIRouter(route_class=_SafeRoute)

    def authority():
        if client is None:
            raise StoreUnavailable("service_unavailable")
        return client

    @router.get("/research/job-options", response_model=ResearchJobOptions)
    def options():
        return authority().options()

    @router.post("/research/jobs", response_model=JobRecord)
    def submit(request: ResearchJobRequest, idempotency_key: Annotated[str, Header()]):
        return authority().submit(request, idempotency_key)

    @router.get("/research/jobs/{job_id}", response_model=JobRecord)
    def status(job_id: str):
        return authority().get(job_id)

    @router.post("/research/jobs/{job_id}/cancel", response_model=JobRecord)
    def cancel(job_id: str):
        return authority().cancel(job_id)

    @router.get(
        "/research/jobs/{job_id}/artifacts/{artifact_id}",
        responses={200: {"content": {"application/json": {"schema": {"type": "object"}}}}},
    )
    def artifact(job_id: str, artifact_id: str):
        return Response(
            authority().artifact(job_id, artifact_id),
            media_type="application/json",
            headers={"Cache-Control": "private, no-store"},
        )

    return router
