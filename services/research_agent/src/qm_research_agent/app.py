"""Private authenticated API, with fixed construction-time operator identity."""

import re
import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from pydantic import SecretStr

from qm_research_agent.artifacts import verified_bytes
from quantmesh.research.job_options import ResearchJobOptions, job_options
from quantmesh.research.job_store import JobStore
from quantmesh.research.jobs import (
    DatasetRejected,
    IdempotencyConflict,
    ResearchJobRequest,
    StoreUnavailable,
)


def create_app(
    store: JobStore,
    *,
    operator_id: str,
    token: SecretStr,
    configured_dataset_ids: tuple[str, ...] = (),
    actual_build: str | None = None,
) -> FastAPI:
    from quantmesh.research.job_store import _identifier

    _identifier(operator_id)
    if not isinstance(token, SecretStr) or len(token.get_secret_value()) < 16:
        raise ValueError("private authentication required")
    # The bootstrap supplies a measured pin after source admission. Direct
    # fixture callers remain unqualified; no expected/configured SHA is guessed.
    if actual_build is not None and (
        not isinstance(actual_build, str) or re.fullmatch(r"[0-9a-f]{40}", actual_build) is None
    ):
        raise ValueError("invalid actual build")

    def authenticate(authorization: Annotated[str | None, Header()] = None):
        expected = "Bearer " + token.get_secret_value()
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(401, "unauthorized")

    app = FastAPI(
        dependencies=[Depends(authenticate)], docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_body(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "invalid_request"}, status_code=422)

    @app.exception_handler(StoreUnavailable)
    async def unavailable(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "service_unavailable"}, status_code=503)

    @app.exception_handler(IdempotencyConflict)
    async def conflict(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "idempotency_conflict"}, status_code=409)

    @app.exception_handler(DatasetRejected)
    async def dataset(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "dataset_rejected"}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "not_found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "invalid_request"}, status_code=422)

    @app.get("/v1/options", response_model=ResearchJobOptions)
    def options():
        return job_options(store.lake_root, configured_dataset_ids)

    @app.post("/v1/jobs")
    def submit(request: ResearchJobRequest, idempotency_key: Annotated[str, Header()]):
        if request.dataset.dataset_id not in configured_dataset_ids:
            raise DatasetRejected("no_qualified_inputs")
        return store.submit(operator_id, idempotency_key, request)

    @app.get("/v1/jobs/{job_id}")
    def status(job_id: str):
        return store.get(operator_id, job_id)

    @app.post("/v1/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return store.request_cancel(operator_id, job_id)

    @app.get("/v1/jobs/{job_id}/artifacts/{artifact_id}")
    def artifact(job_id: str, artifact_id: str):
        job = store.get(operator_id, job_id)
        refs = job.artifacts + (
            [job.analysis.output_artifact] if job.analysis and job.analysis.output_artifact else []
        )
        ref = next((ref for ref in refs if ref.artifact_id == artifact_id), None)
        if ref is None:
            raise KeyError("not found")
        try:
            raw = verified_bytes(store.artifact_root, job, ref)
        except (ValueError, OSError):
            raise HTTPException(409, "artifact_invalid") from None
        return Response(raw, media_type="application/json")

    @app.get("/health")
    def health():
        # Exercise a database transaction, not a constant synthetic green.
        try:
            store.get(operator_id, "health-nonexistent")
        except KeyError:
            pass
        return {
            "schema_version": 1,
            "advisory_only": True,
            "actual_build": actual_build,
            # This API starts neither execution loop. Native containment and
            # configured real-model evidence are separate deployment gates.
            "capabilities": {"worker": "pending_containment", "model": "unavailable"},
        }

    return app
