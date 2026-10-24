"""Typed local daily CSV facade under the existing snapshot opt-in."""

import hashlib

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from quantmesh.data.objects import ObjectIntegrityError
from quantmesh.research.local_csv_snapshots import (
    MAX_REQUEST_BYTES,
    LocalCsvCatalog,
    LocalCsvList,
    LocalCsvReference,
    LocalCsvReport,
    LocalCsvRequest,
)
from quantmesh.research.realdata_snapshots import SnapshotInputError, SnapshotTooLarge, _json


class _LocalCsvRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def bounded(request):
            try:
                if request.method == "POST":
                    from quantmesh.api.workstation import _json_guard_origin

                    _json_guard_origin(request, "local CSV snapshots")
                    content_type = request.headers.get("content-type", "").split(";", 1)[0]
                    if content_type.strip().lower() != "application/json":
                        raise HTTPException(415, "local_csv_content_type")
                    declared = request.headers.get("content-length")
                    if declared is not None:
                        length = int(declared)
                        if length < 0:
                            raise ValueError("invalid length")
                        if length > MAX_REQUEST_BYTES:
                            raise SnapshotTooLarge("local_csv_too_large")
                    raw = bytearray()
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
                            raise SnapshotTooLarge("local_csv_too_large")
                        raw.extend(chunk)
                    _json(bytes(raw))  # Strict duplicate/nonfinite JSON check before typed parse.

                    async def receive():
                        return {"type": "http.request", "body": bytes(raw), "more_body": False}

                    request = Request(request.scope, receive)
                result = await original(request)
                result.headers["Cache-Control"] = "private, no-store"
                return result
            except HTTPException:
                raise
            except SnapshotTooLarge:
                raise HTTPException(413, "local_csv_too_large") from None
            except ObjectIntegrityError:
                raise HTTPException(409, "local_csv_integrity_failed") from None
            except KeyError:
                raise HTTPException(404, "local_csv_unknown") from None
            except (SnapshotInputError, RequestValidationError, ValueError, TypeError):
                raise HTTPException(422, "local_csv_invalid") from None
            except Exception:
                raise HTTPException(503, "snapshot_runtime_unavailable") from None

        return bounded


def create_local_csv_snapshots_router() -> APIRouter:
    router = APIRouter(prefix="/local-csv", route_class=_LocalCsvRoute)

    def catalog(request: Request) -> LocalCsvCatalog:
        parent = getattr(request.app.state, "research_snapshots", None)
        if parent is None:
            raise HTTPException(503, "snapshot_runtime_unavailable")
        current = getattr(request.app.state, "local_csv_snapshots", None)
        if current is None:
            current = LocalCsvCatalog(parent.root / "local-csv", clock=parent.clock)
            request.app.state.local_csv_snapshots = current
        return current

    @router.get("", response_model=LocalCsvList)
    def list_local_csv(request: Request):
        return LocalCsvList(snapshots=catalog(request).list())

    @router.post("", response_model=LocalCsvReport, status_code=201)
    def import_local_csv(payload: LocalCsvRequest, request: Request):
        return catalog(request).import_csv(payload)

    @router.get("/{snapshot_id}", response_model=LocalCsvReport)
    def get_local_csv(snapshot_id: str, request: Request):
        return catalog(request).get(snapshot_id)

    @router.get("/{snapshot_id}/reference", response_model=LocalCsvReference)
    def get_local_csv_reference(snapshot_id: str, request: Request):
        return catalog(request).reference(snapshot_id)

    def download(request, snapshot_id, kind):
        authority = catalog(request)
        method, extension, media_type = {
            "original": (authority.original_bytes, "csv", "text/csv; charset=utf-8"),
            "report": (authority.report_bytes, "json", "application/json"),
            "reference": (authority.reference_bytes, "json", "application/json"),
        }[kind]
        payload = method(snapshot_id)
        digest = hashlib.sha256(payload).hexdigest()
        return Response(
            payload,
            media_type=media_type,
            headers={
                "X-Content-SHA256": digest,
                "ETag": f'"{digest}"',
                "Cache-Control": "private, no-store",
                "Content-Disposition": (f'attachment; filename="{snapshot_id}-{kind}.{extension}"'),
            },
        )

    @router.get("/{snapshot_id}/original.csv")
    def download_local_csv_original(snapshot_id: str, request: Request):
        return download(request, snapshot_id, "original")

    @router.get("/{snapshot_id}/report")
    def download_local_csv_report(snapshot_id: str, request: Request):
        return download(request, snapshot_id, "report")

    @router.get("/{snapshot_id}/reference.json")
    def download_local_csv_reference(snapshot_id: str, request: Request):
        return download(request, snapshot_id, "reference")

    return router
