"""The deterministic demo runtime (iteration 0014 Phase B).

``create_demo_app`` assembles a full workstation app over one labeled
demo root: it seeds the root on first start (or loads an existing one),
binds every injected surface — account, marks, markets, watchlist,
registries, ledgers — to files under that root (never the operator's
data dirs), and attaches the demo control surface:

- ``GET /api/demo/status`` — the provenance contract: mode, marker,
  scenario, per-surface source/synthetic/updated_at/rows, health. All
  deterministic, all derived from the root's own ``provenance.json``.
- ``POST /api/demo/reset`` — marker-guarded atomic replacement through
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

from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Condition, Lock
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from quantmesh.api.app import _order_summary
from quantmesh.api.workstation import (
    PageContext,
    _json_guard_origin,
    create_workstation_app,
)
from quantmesh.data.lake import Lake
from quantmesh.demo.datalink import DatalinkService, datalink_router
from quantmesh.demo.manifest import MARKER_NAME, DemoScenario
from quantmesh.demo.seeder import (
    DemoRootError,
    DemoSeeded,
    build_demo_reset_archive,
    build_trusted_demo_reset_image,
    is_demo_root,
    load_demo_root,
    persist_demo_account,
    reset_demo_root,
    retained_demo_reset_paths,
    seed_demo_root,
)
from quantmesh.domain.models import Instrument, OrderRequest, Quote, Side
from quantmesh.execution.account_store import PaperAccountStore, recover_account_from_journal
from quantmesh.instruments.copilot import PacketCopilotService
from quantmesh.settings import settings


class _DemoOrderBody(BaseModel):
    """One demo paper order: the SPA's simulated submit (the Phase C
    tracer bullet). Gated exactly like the workstation's other write
    surfaces and filled through the seeded provider pipeline, so the
    browser places an order through the real domain services — never a
    UI-only fixture. ``idempotency_key`` is the M10 replay guard: a
    retry with the same key returns the original order, never a
    duplicate."""

    venue: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    idempotency_key: str | None = None


class _RetainedResetAcknowledgeBody(BaseModel):
    """Explicitly acknowledge manual cleanup; never delete a path."""

    path: str
    confirmation: Literal["ACKNOWLEDGE_MANUAL_CLEANUP"]


@dataclass
class DemoRuntime:
    """The mutable runtime handle: the root, the scenario it was seeded
    with (re-loaded from provenance on an existing root), and the
    current in-memory assembly. ``seeded`` is replaced on reset; the
    root and scenario are the identity of the demo session."""

    root: Path
    scenario: DemoScenario
    seeded: DemoSeeded
    trusted_ownership_text: str = field(repr=False)
    trusted_reset_archive: bytes = field(repr=False)
    reset_lock: Lock = field(default_factory=Lock, repr=False)
    request_gate: Condition = field(default_factory=Condition, repr=False)
    active_requests: int = 0
    resetting: bool = False
    retained_reset_acknowledgements: dict[Path, bool] = field(default_factory=dict)


def _label_demo_response(response, runtime: DemoRuntime):
    response.headers["X-QuantMesh-Source"] = "demo"
    response.headers["X-QuantMesh-Synthetic"] = "true"
    response.headers["X-QuantMesh-Anchor"] = runtime.scenario.anchor.isoformat()
    return response


def _status(runtime: DemoRuntime) -> dict[str, object]:
    """The provenance contract: everything derives from the root's own
    records, never from the wall clock."""
    seeded = runtime.seeded
    surfaces = {name: dict(value) for name, value in seeded.provenance["surfaces"].items()}
    lake_root = seeded.root / "market" / "lake"
    history_rows = 0
    for path in sorted(lake_root.iterdir()):
        if path.is_dir():
            coverage = Lake(lake_root).dataset(path.name).manifest.coverage
            history_rows += sum(item.rows for item in coverage)
    surfaces["history"]["rows"] = history_rows
    forecast_root = seeded.root / "research" / "price-forecasts"
    surfaces["price_forecasts"]["rows"] = (
        sum(1 for path in forecast_root.iterdir() if path.is_dir()) if forecast_root.exists() else 0
    )
    surfaces["paper_proposals"]["rows"] = len(seeded.proposal_ledger.all())
    surfaces["decision_packets"]["rows"] = len(seeded.decision_packets.all())
    surfaces["orders"]["rows"] = len(seeded.journal.all())
    retained_paths = retained_demo_reset_paths(runtime.root)
    retained_set = set(retained_paths)
    runtime.retained_reset_acknowledgements = {
        path: acknowledged
        for path, acknowledged in runtime.retained_reset_acknowledgements.items()
        if path in retained_set
    }
    for path in retained_paths:
        runtime.retained_reset_acknowledgements.setdefault(path, False)
    return {
        "mode": "demo",
        "root": str(runtime.root),
        "marker": MARKER_NAME,
        "source": "demo",
        "synthetic": True,
        "scenario": seeded.provenance["scenario"],
        "surfaces": surfaces,
        "last_update": runtime.scenario.anchor.isoformat(),
        "health": {"status": "ok", "seed": runtime.scenario.seed},
        "retained_resets": [
            {
                "path": str(path),
                "acknowledged": runtime.retained_reset_acknowledgements[path],
                "exists": True,
            }
            for path in retained_paths
        ],
        "retained_reset_cleanup": {
            "mode": "manual-only",
            "automatic_deletion_supported": False,
            "instructions": (
                "Stop QuantMesh, inspect each retained path, then remove it manually "
                "with an operator-chosen filesystem tool. QuantMesh never deletes it."
            ),
        },
    }


def _apply_seeded(app: FastAPI, seeded: DemoSeeded) -> None:
    """Swap every injected surface for the fresh assembly, in place.

    Replaces ``app.state.account``, ``app.state.marks`` and the page
    context so the M1 JSON routes, every page provider and the kernel
    gate read the reset state (the kill-switch precedent). All
    registries stay bound to the same files under the demo root, which
    reset rewrote in place.
    """
    account_store = getattr(app.state, "account_store", None)
    if account_store is not None:
        account_store.replace(seeded.account)
    else:
        app.state.account = seeded.account
    app.state.marks = seeded.marks
    app.state.history = seeded.history
    app.state.price_forecasts = seeded.price_forecasts
    app.state.decision_packets = seeded.decision_packets
    app.state.packet_copilot_store = seeded.packet_copilot
    packet_service = getattr(app.state, "decision_packet_service", None)
    if packet_service is not None:
        packet_service.store = seeded.decision_packets
    copilot = getattr(app.state, "packet_copilot", None)
    if isinstance(copilot, PacketCopilotService):
        copilot.packet_store = seeded.decision_packets
        copilot.store = seeded.packet_copilot
        copilot.decision_log = seeded.decisions
    workspace = getattr(app.state, "instrument_workspace", None)
    if workspace is not None:
        clear_staged_drafts = getattr(workspace, "clear_staged_drafts", None)
        if callable(clear_staged_drafts):
            clear_staged_drafts()
        workspace._decision_packets = seeded.decision_packets  # noqa: SLF001
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


def _workspace_demo_quote(
    seeded: DemoSeeded,
    instrument: Instrument,
    now,
) -> Quote:
    venue = instrument.venue.value
    book = seeded.providers.order_books(venue, instrument.symbol)[0]
    bid = book.bids[0].price if book.bids else None
    ask = book.asks[0].price if book.asks else None
    return Quote(
        instrument=instrument,
        timestamp=now,
        bid=bid,
        ask=ask,
        last=((bid + ask) / 2 if bid is not None and ask is not None else bid or ask),
        volume=sum(level.quantity for level in (*book.bids, *book.asks)),
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
        _json_guard_origin(request, "demo reset")
        if not runtime.reset_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="demo reset already in progress")
        with runtime.request_gate:
            runtime.resetting = True
            while runtime.active_requests > 0:
                runtime.request_gate.wait()
        try:
            try:
                # Reset with the scenario the root was seeded with (loaded
                # from its provenance on restart), so a reset reproduces
                # the exact same root — byte-identical replay.
                seeded = reset_demo_root(
                    runtime.root,
                    runtime.seeded.scenario,
                    trusted_ownership_text=runtime.trusted_ownership_text,
                    trusted_reset_archive=runtime.trusted_reset_archive,
                )
            except DemoRootError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            runtime.seeded = seeded
            _apply_seeded(request.app, seeded)
            # The datalink session (connector probes, import sessions, the
            # public-data cache) is part of the demo session: reset restores
            # the pristine root, so it clears too.
            datalink = getattr(request.app.state, "datalink", None)
            if isinstance(datalink, DatalinkService):
                datalink.reset()
            return _status(runtime)
        finally:
            with runtime.request_gate:
                runtime.resetting = False
                runtime.request_gate.notify_all()
            runtime.reset_lock.release()

    @router.post("/demo/retained-reset/acknowledge")
    def acknowledge_retained_reset(
        request: Request,
        body: _RetainedResetAcknowledgeBody,
    ) -> dict[str, object]:
        """Acknowledge a visible retained path without touching the filesystem."""
        runtime = getattr(request.app.state, "demo", None)
        if runtime is None:
            raise HTTPException(status_code=404, detail="no demo runtime is attached")
        _json_guard_origin(request, "retained demo reset acknowledgement")
        candidate = Path(body.path)
        retained = set(retained_demo_reset_paths(runtime.root))
        if candidate not in retained:
            raise HTTPException(status_code=404, detail="retained reset path is not present")
        runtime.retained_reset_acknowledgements[candidate] = True
        return _status(runtime)

    @router.post("/demo/order")
    def demo_order(request: Request, body: _DemoOrderBody) -> dict[str, object]:
        """One simulated paper order through the real pipeline.

        The SPA tracer bullet: submit against the seeded order book's
        touch (the providers serve the same walk the board renders),
        through the paper account's own risk gate — a kill switch or a
        broken limit refuses with the gate's own message. The order is
        recorded in the seeded journal (a public service append) and
        the fresh account replaces ``app.state`` and the page context,
        so the JSON surface, every page and the kernel gate agree.
        Timestamps derive from the scenario anchor, never the wall
        clock, so a replay session can reproduce the same session.
        Reset restores the pristine root.
        """
        runtime = getattr(request.app.state, "demo", None)
        if runtime is None:
            raise HTTPException(status_code=404, detail="no demo runtime is attached")
        _json_guard_origin(request, "demo order")
        providers = runtime.seeded.providers
        if (body.venue, body.symbol) not in providers.universe():
            raise HTTPException(
                status_code=404,
                detail=(
                    f"demo order refused: {body.venue}:{body.symbol} is outside the seeded universe"
                ),
            )
        instrument = providers.instrument(body.venue, body.symbol)
        book = providers.order_books(body.venue, body.symbol)[0]
        best_bid = book.bids[0].price if book.bids else None
        best_ask = book.asks[0].price if book.asks else None
        quote = Quote(
            instrument=instrument,
            timestamp=runtime.scenario.anchor,
            bid=best_bid,
            ask=best_ask,
            last=(
                (best_bid + best_ask) / 2
                if best_bid is not None and best_ask is not None
                else best_bid
            ),
            # The available liquidity is the depth the board renders —
            # the matcher's "missing volume" gate needs a real number.
            volume=sum(level.quantity for level in (*book.bids, *book.asks)),
        )
        store = getattr(request.app.state, "account_store", None)
        if not isinstance(store, PaperAccountStore):
            raise HTTPException(status_code=503, detail="paper account authority is not bound")
        with store.transaction():
            context = request.app.state.page_context
            result = store.get().submit(
                OrderRequest(
                    instrument=instrument,
                    side=Side.BUY if body.side == "BUY" else Side.SELL,
                    quantity=body.quantity,
                    limit_price=body.limit_price,
                    idempotency_key=body.idempotency_key,
                ),
                quote,
                now=runtime.scenario.anchor,
            )
            if result.rejection is not None:
                raise HTTPException(status_code=409, detail=result.rejection)
            # A replay returns the original order and a fresh account copy;
            # the journal already holds it (and refuses duplicates), so only
            # first-time submissions append.
            if context.journal is not None and result.replay_of is None:
                context.journal.record(result.order)
            store.replace(result.account)
        return {
            "order": _order_summary(result.order),
            "account": {
                "cash": result.account.cash,
                "equity": result.account.equity(runtime.seeded.marks),
            },
        }

    return router


def create_demo_app(
    *,
    root: Path | None = None,
    seed: int | None = None,
    workspace_history: bool = True,
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
    scenario = DemoScenario(
        seed=seed if seed is not None else settings.demo_seed,
        workspace_history=workspace_history,
    )
    existing = is_demo_root(root)
    seeded = load_demo_root(root, scenario) if existing else seed_demo_root(root, scenario)
    if existing:
        recovered_account = recover_account_from_journal(
            seeded.account,
            seeded.journal.all(),
        )
        if recovered_account != seeded.account:
            # Demo orders are journal-first. If a process stops after the
            # append but before the account snapshot is published, replay the
            # validated trailing suffix once and make that aggregate durable
            # before exposing any workstation surface.
            persist_demo_account(root, recovered_account)
            seeded = replace(seeded, account=recovered_account)
    if existing:
        trusted_ownership_text, trusted_reset_archive = build_trusted_demo_reset_image(
            seeded.scenario
        )
    else:
        trusted_ownership_text = (root / "QUANTMESH_DEMO_OWNERSHIP.json").read_text(
            encoding="utf-8"
        )
        trusted_reset_archive = build_demo_reset_archive(root)
    packet_copilot = PacketCopilotService(
        packet_store=seeded.decision_packets,
        store=seeded.packet_copilot,
        decision_log=seeded.decisions,
        analyst_gateway=None,
        critic_gateway=None,
        analyst_model=None,
        critic_model=None,
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
        history=seeded.history,
        price_forecasts=seeded.price_forecasts,
        proposal_ledger=seeded.proposal_ledger,
        decision_packets=seeded.decision_packets,
        packet_copilot_store=seeded.packet_copilot,
        packet_copilot=packet_copilot,
        account_sink=lambda account: persist_demo_account(root, account),
        demo_quote_provider=lambda instrument, now: _workspace_demo_quote(
            seeded,
            instrument,
            now,
        ),
        workspace_clock=lambda: seeded.scenario.anchor,
        host=host,
    )
    paper_decisions = getattr(app.state, "paper_decisions", None)
    if paper_decisions is not None:
        journal_keys = {
            order.idempotency_key
            for order in seeded.journal.all()
            if order.idempotency_key is not None
        }
        for proposal in seeded.proposal_ledger.all():
            has_crash_window_order = (
                proposal.status.value == "pending" and f"proposal:{proposal.id}" in journal_keys
            )
            if proposal.order_id is not None or has_crash_window_order:
                paper_decisions.confirm(
                    proposal.id,
                    confirmation=proposal.confirmation_token,
                    now=max(seeded.scenario.anchor, proposal.created_at),
                )
    app.state.demo = DemoRuntime(
        root=root,
        scenario=seeded.scenario,
        seeded=seeded,
        trusted_ownership_text=trusted_ownership_text,
        trusted_reset_archive=trusted_reset_archive,
    )
    router = demo_router()
    app.include_router(router)
    app.include_router(
        router,
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )
    # Phase D: connector panel, the credential-free public data path and
    # file import — mounted under /api only (the SPA's surface).
    app.state.datalink = DatalinkService(root=root)
    app.include_router(
        datalink_router(),
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )

    @app.middleware("http")
    async def demo_provenance_headers(request: Request, call_next):
        """Label every response with the demo provenance while attached."""
        runtime = getattr(request.app.state, "demo", None)
        admitted = False
        is_reset = request.url.path.endswith("/demo/reset")
        if runtime is not None and not is_reset:
            with runtime.request_gate:
                if runtime.resetting:
                    return _label_demo_response(
                        JSONResponse(
                            status_code=503,
                            content={"detail": "demo reset in progress"},
                        ),
                        runtime,
                    )
                runtime.active_requests += 1
                admitted = True
        try:
            response = await call_next(request)
        finally:
            if runtime is not None and admitted:
                with runtime.request_gate:
                    runtime.active_requests -= 1
                    if runtime.active_requests == 0:
                        runtime.request_gate.notify_all()
        runtime = getattr(request.app.state, "demo", None)
        if runtime is not None:
            _label_demo_response(response, runtime)
        return response

    return app
