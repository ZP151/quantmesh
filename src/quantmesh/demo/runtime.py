"""The deterministic demo runtime (iteration 0014 Phase B).

``create_demo_app`` assembles a full workstation app over one labeled
demo root: it seeds the root on first start (or loads an existing one),
binds every injected surface — account, marks, markets, watchlist,
registries, ledgers — to files under that root (never the operator's
data dirs), and attaches the demo control surface:

- ``GET /api/demo/status`` — the provenance contract: mode, marker,
  scenario, per-surface source/synthetic/updated_at/rows, health. All
  deterministic, all derived from the root's own ``provenance.json``.
- ``POST /api/demo/reset`` — marker-guarded wipe and re-seed through
  ``reset_demo_root``; the fresh assembly replaces ``app.state`` in
  place, so the JSON surface, every page and the kernel gate agree on
  the new state (the kill-switch precedent, ADR-0012 decision 3). A
  root without the marker is refused — the demo runtime never touches
  a non-demo root.
- Provenance headers on every response while the runtime is attached:
  ``X-QuantMesh-Source: demo``, ``X-QuantMesh-Synthetic: true`` and
  the fixed scenario anchor, so a mixed client sees the label without
  asking.

Both endpoints are double-mounted at the root and under ``/api`` like
the observability router (one registration, ``api_`` operation id
prefix), so the SPA and the RC1 contract call the same handlers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, HTTPException, Request

from quantmesh.api.workstation import PageContext, _is_loopback, create_workstation_app
from quantmesh.demo.manifest import MARKER_NAME, DemoScenario
from quantmesh.demo.seeder import (
    DemoRootError,
    DemoSeeded,
    is_demo_root,
    load_demo_root,
    reset_demo_root,
    seed_demo_root,
)
from quantmesh.settings import settings


@dataclass
class DemoRuntime:
    """The mutable runtime handle: the root, the scenario it was seeded
    with (re-loaded from provenance on an existing root), and the
    current in-memory assembly. ``seeded`` is replaced on reset; the
    root and scenario are the identity of the demo session."""

    root: Path
    scenario: DemoScenario
    seeded: DemoSeeded


def _status(runtime: DemoRuntime) -> dict[str, object]:
    """The provenance contract: everything derives from the root's own
    records, never from the wall clock."""
    seeded = runtime.seeded
    return {
        "mode": "demo",
        "root": str(runtime.root),
        "marker": MARKER_NAME,
        "source": "demo",
        "synthetic": True,
        "scenario": seeded.provenance["scenario"],
        "surfaces": seeded.provenance["surfaces"],
        "last_update": runtime.scenario.anchor.isoformat(),
        "health": {"status": "ok", "seed": runtime.scenario.seed},
    }


def _guard_origin(request: Request, surface: str) -> None:
    """Refuse a demo write POST whose Origin is present but not
    loopback (the threat model T-14 discipline the workstation's other
    write surfaces apply); raises a typed HTTP error for the JSON
    surface."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    try:
        hostname = urlsplit(origin).hostname
    except ValueError:
        hostname = None
    if hostname is not None and _is_loopback(hostname):
        return
    raise HTTPException(
        status_code=403,
        detail=f"{surface} refused: cross-origin send (Origin {origin!r} is not loopback)",
    )


def _apply_seeded(app: FastAPI, seeded: DemoSeeded) -> None:
    """Swap every injected surface for the fresh assembly, in place.

    Replaces ``app.state.account``, ``app.state.marks`` and the page
    context so the M1 JSON routes, every page provider and the kernel
    gate read the reset state (the kill-switch precedent). All
    registries stay bound to the same files under the demo root, which
    reset rewrote in place.
    """
    app.state.account = seeded.account
    app.state.marks = seeded.marks
    app.state.page_context = PageContext(
        account=seeded.account,
        marks=seeded.marks,
        markets=seeded.markets,
        watchlist=seeded.watchlist,
        experiments=seeded.experiments,
        promotions=seeded.promotions,
        reports=seeded.reports,
        forecasts=seeded.forecasts,
        alerts=seeded.alerts,
        journal=seeded.journal,
        mappings=seeded.mappings,
        decisions=seeded.decisions,
        documents=seeded.documents,
        hl_posture=None,
        enablement=seeded.enablement,
    )


def demo_router() -> APIRouter:
    """The demo control surface: status + marker-guarded reset.

    Mounted at the root (``/demo/status``) and under ``/api`` (the SPA
    surface, ``/api/demo/status``) like the observability router.
    Handlers read ``request.app.state.demo``, so both mounts share the
    same runtime handle.
    """
    router = APIRouter()

    @router.get("/demo/status")
    def demo_status(request: Request) -> dict[str, object]:
        runtime = getattr(request.app.state, "demo", None)
        if runtime is None:
            raise HTTPException(status_code=404, detail="no demo runtime is attached")
        return _status(runtime)

    @router.post("/demo/reset")
    def demo_reset(request: Request) -> dict[str, object]:
        runtime = getattr(request.app.state, "demo", None)
        if runtime is None:
            raise HTTPException(status_code=404, detail="no demo runtime is attached")
        _guard_origin(request, "demo reset")
        try:
            # Reset with the scenario the root was seeded with (loaded
            # from its provenance on restart), so a reset reproduces
            # the exact same root — byte-identical replay.
            seeded = reset_demo_root(runtime.root, runtime.seeded.scenario)
        except DemoRootError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        runtime.seeded = seeded
        _apply_seeded(request.app, seeded)
        return _status(runtime)

    return router


def create_demo_app(
    *,
    root: Path | None = None,
    seed: int | None = None,
    host: str | None = None,
) -> FastAPI:
    """A workstation app bound to one labeled demo root.

    Seeds ``root`` on first start; an existing marker-carrying root is
    loaded (a restart is a read, never a re-seed) with its scenario
    reconstructed from provenance, so a mismatched default seed can
    never misread the root. Every injected surface is bound under
    ``root`` — the operator's lake, orders, reports and other non-demo
    dirs are never opened.
    """
    root = Path(root) if root is not None else Path(settings.demo_root)
    scenario = DemoScenario(seed=seed if seed is not None else settings.demo_seed)
    seeded = (
        load_demo_root(root, scenario) if is_demo_root(root) else seed_demo_root(root, scenario)
    )
    app = create_workstation_app(
        account=seeded.account,
        marks=seeded.marks,
        markets=seeded.markets,
        watchlist=seeded.watchlist,
        experiments=seeded.experiments,
        promotions=seeded.promotions,
        reports=seeded.reports,
        forecasts=seeded.forecasts,
        alerts=seeded.alerts,
        journal=seeded.journal,
        mappings=seeded.mappings,
        decisions=seeded.decisions,
        documents=seeded.documents,
        enablement=seeded.enablement,
        host=host,
    )
    app.state.demo = DemoRuntime(root=root, scenario=seeded.scenario, seeded=seeded)
    router = demo_router()
    app.include_router(router)
    app.include_router(
        router,
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )

    @app.middleware("http")
    async def demo_provenance_headers(request: Request, call_next):
        """Label every response with the demo provenance while attached."""
        response = await call_next(request)
        runtime = getattr(request.app.state, "demo", None)
        if runtime is not None:
            response.headers["X-QuantMesh-Source"] = "demo"
            response.headers["X-QuantMesh-Synthetic"] = "true"
            response.headers["X-QuantMesh-Anchor"] = runtime.scenario.anchor.isoformat()
        return response

    return app
