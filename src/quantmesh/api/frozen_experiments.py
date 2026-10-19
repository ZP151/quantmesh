"""Bounded local frozen-evidence API; fixed errors and attachment-only originals."""

import hashlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from quantmesh.api.research_jobs import _SafeRoute
from quantmesh.data.objects import ObjectIntegrityError
from quantmesh.research.frozen_experiments import (
    DOWNLOADS,
    MAX_ARCHIVE_BYTES,
    FrozenExperimentCatalog,
    FrozenExperimentInputError,
    FrozenExperimentTooLarge,
    FrozenSnapshotMissing,
)


def create_frozen_experiments_router() -> APIRouter:
    router = APIRouter(prefix="/research/frozen-experiments", route_class=_SafeRoute)

    def catalog(request: Request) -> FrozenExperimentCatalog:
        authority = getattr(request.app.state, "frozen_experiments", None)
        if authority is None:
            raise HTTPException(503, "frozen_experiment_runtime_unavailable")
        return authority

    def call(operation, *args):
        try:
            return operation(*args)
        except FrozenExperimentTooLarge:
            raise HTTPException(413, "frozen_experiment_too_large") from None
        except FrozenSnapshotMissing:
            raise HTTPException(422, "frozen_experiment_snapshot_required") from None
        except FrozenExperimentInputError:
            raise HTTPException(422, "frozen_experiment_invalid") from None
        except ObjectIntegrityError:
            raise HTTPException(409, "frozen_experiment_integrity_failed") from None
        except KeyError:
            raise HTTPException(404, "frozen_experiment_unknown") from None
        except (OSError, ValueError):
            raise HTTPException(503, "frozen_experiment_runtime_unavailable") from None

    def response(value, status=200):
        return JSONResponse(
            value, status_code=status, headers={"Cache-Control": "private, no-store"}
        )

    @router.get("")
    def list_experiments(request: Request):
        return response({"schema_version": 1, "experiments": call(catalog(request).list)})

    @router.post("", status_code=201)
    async def import_experiment(request: Request):
        from quantmesh.api.workstation import _json_guard_origin

        _json_guard_origin(request, "frozen experiments")
        authority = catalog(request)
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/zip"
        ):
            raise HTTPException(415, "frozen_experiment_content_type")
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                length = int(declared)
                if length < 0:
                    raise ValueError("negative length")
            except ValueError:
                raise HTTPException(422, "frozen_experiment_invalid") from None
            if length > MAX_ARCHIVE_BYTES:
                raise HTTPException(413, "frozen_experiment_too_large")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_ARCHIVE_BYTES:
                raise HTTPException(413, "frozen_experiment_too_large")
            payload.extend(chunk)
        return response(call(authority.import_archive, bytes(payload)), 201)

    @router.get("/{package_id}")
    def get_experiment(package_id: str, request: Request):
        return response(call(catalog(request).get, package_id))

    @router.get("/{package_id}/artifacts/{kind}")
    def download(package_id: str, kind: str, request: Request):
        payload = call(catalog(request).artifact_bytes, package_id, kind)
        digest = hashlib.sha256(payload).hexdigest()
        filename = "archive.zip" if kind == "archive" else DOWNLOADS[kind].rsplit("/", 1)[-1]
        return Response(
            payload,
            media_type="application/zip" if kind == "archive" else "application/octet-stream",
            headers={
                "X-Content-SHA256": digest,
                "ETag": f'"{digest}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="{package_id}-{filename}"',
            },
        )

    return router
