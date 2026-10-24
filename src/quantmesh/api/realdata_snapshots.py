"""Local snapshot import/read/download facade with fixed public error codes."""

import hashlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from quantmesh.api.local_csv_snapshots import create_local_csv_snapshots_router
from quantmesh.api.research_jobs import _SafeRoute
from quantmesh.data.objects import ObjectIntegrityError
from quantmesh.research.realdata_snapshots import (
    MAX_ARCHIVE_BYTES,
    SnapshotCatalog,
    SnapshotInputError,
    SnapshotTooLarge,
)


def create_realdata_snapshots_router() -> APIRouter:
    router = APIRouter(prefix="/research/data-snapshots", route_class=_SafeRoute)
    router.include_router(create_local_csv_snapshots_router())

    def catalog(request: Request) -> SnapshotCatalog:
        authority = getattr(request.app.state, "research_snapshots", None)
        if authority is None:
            raise HTTPException(503, "snapshot_runtime_unavailable")
        return authority

    def call(operation, *args):
        try:
            return operation(*args)
        except SnapshotTooLarge:
            raise HTTPException(413, "snapshot_too_large") from None
        except SnapshotInputError:
            raise HTTPException(422, "snapshot_invalid") from None
        except ObjectIntegrityError:
            raise HTTPException(409, "snapshot_integrity_failed") from None
        except KeyError:
            raise HTTPException(404, "snapshot_unknown") from None
        except (OSError, ValueError):
            raise HTTPException(503, "snapshot_runtime_unavailable") from None

    def json_response(value, status=200):
        return JSONResponse(
            value, status_code=status, headers={"Cache-Control": "private, no-store"}
        )

    @router.get("")
    def list_snapshots(request: Request):
        return json_response({"schema_version": 1, "snapshots": call(catalog(request).list)})

    @router.post("", status_code=201)
    async def import_snapshot(request: Request):
        from quantmesh.api.workstation import _json_guard_origin

        _json_guard_origin(request, "research snapshots")
        authority = catalog(request)
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/zip"
        ):
            raise HTTPException(415, "snapshot_content_type")
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                length = int(declared)
                if length < 0:
                    raise ValueError("negative length")
            except ValueError:
                raise HTTPException(422, "snapshot_invalid") from None
            if length > MAX_ARCHIVE_BYTES:
                raise HTTPException(413, "snapshot_too_large")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_ARCHIVE_BYTES:
                raise HTTPException(413, "snapshot_too_large")
            payload.extend(chunk)
        return json_response(call(authority.import_archive, bytes(payload)), 201)

    @router.get("/{snapshot_id}")
    def get_snapshot(snapshot_id: str, request: Request):
        return json_response(call(catalog(request).get, snapshot_id))

    def download(request, snapshot_id, *, report):
        authority = catalog(request)
        operation = authority.report_bytes if report else authority.archive_bytes
        payload = call(operation, snapshot_id)
        digest = hashlib.sha256(payload).hexdigest()
        extension = "json" if report else "zip"
        suffix = "report" if report else "snapshot"
        return Response(
            payload,
            media_type="application/json" if report else "application/zip",
            headers={
                "X-Content-SHA256": digest,
                "ETag": f'"{digest}"',
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="{snapshot_id}-{suffix}.{extension}"',
            },
        )

    @router.get("/{snapshot_id}/archive")
    def download_archive(snapshot_id: str, request: Request):
        return download(request, snapshot_id, report=False)

    @router.get("/{snapshot_id}/report")
    def download_report(snapshot_id: str, request: Request):
        return download(request, snapshot_id, report=True)

    return router
