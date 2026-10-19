"""Bounded, same-origin local synthetic paper controls; no supplied evidence paths."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from quantmesh.ops.paper_controls import PaperControlError, PaperControls


class TransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    reason: str = Field(min_length=1, max_length=240, pattern=r"\S")
    revision: str = Field(default="", max_length=64, pattern=r"^([a-f0-9]{64})?$")
    confirmation: bool = False
    target: Literal["moomoo", "hyperliquid", "polymarket", "kalshi"] | None = None


class PreflightBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    target: Literal["moomoo", "hyperliquid", "polymarket", "kalshi"] | None = None


def _service(request: Request) -> PaperControls:
    service = getattr(request.app.state, "paper_controls", None)
    if not isinstance(service, PaperControls):
        raise HTTPException(status_code=503, detail="paper_controls_unavailable")
    return service


async def _body(request: Request) -> object:
    # Read incrementally before Pydantic parsing, including chunked requests.
    from quantmesh.api.workstation import _json_guard_origin

    _json_guard_origin(request, "paper controls")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(status_code=413, detail="paper_control_body_too_large")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="paper_control_invalid_body") from None


def _attachment(raw: bytes, name: str) -> Response:
    return Response(
        content=raw,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-SHA256": hashlib.sha256(raw).hexdigest(),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


def paper_controls_router() -> APIRouter:
    router = APIRouter(prefix="/paper-controls", tags=["synthetic-paper-controls"])

    @router.get("")
    def status(request: Request) -> dict:
        return _service(request).status()

    @router.post("/preflight")
    async def preflight(request: Request) -> dict:
        service = _service(request)
        try:
            body = PreflightBody.model_validate(await _body(request))
        except ValidationError:
            raise HTTPException(status_code=422, detail="paper_control_invalid_body")
        return service.preflight(body.target)

    @router.post("/{action}")
    async def transition(request: Request, action: Literal["pause", "resume"]) -> dict:
        service = _service(request)
        try:
            body = TransitionBody.model_validate(await _body(request))
        except ValidationError:
            raise HTTPException(status_code=422, detail="paper_control_invalid_body") from None
        return service.transition(action, **body.model_dump())

    @router.get("/audit")
    def audit(request: Request) -> Response:
        return _attachment(_service(request).audit_bytes(), "synthetic-paper-audit.jsonl")

    @router.get("/receipts/{identifier}")
    def receipt(request: Request, identifier: str) -> Response:
        if len(identifier) != 64 or any(c not in "0123456789abcdef" for c in identifier):
            raise HTTPException(status_code=404, detail="receipt_not_found")
        try:
            result = _service(request).receipt(identifier)
        except PaperControlError:
            raise HTTPException(status_code=404, detail="receipt_not_found") from None
        return _attachment(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode(),
            f"paper-receipt-{identifier}.json",
        )

    return router
