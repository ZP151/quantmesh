"""Local frontend workstation (M9, issues #51-#53).

`create_workstation_app` supersets the M1 read-only `create_app` with
server-rendered Jinja2 pages: a strict route -> template -> data
provider registry, a shared layout with keyboard/accessibility posture
(skip link, landmarks, visible focus, local stylesheet — no CDN), and
static assets served by the same process. No node toolchain, no build
step.

Construction is fail-closed on the bind surface: a non-loopback
`settings.workstation_host` is a typed `WorkstationConfigError` — the
workstation is a local surface, never env-escalable (ADR-0011 decision
2, the ADR-0010 loopback discipline). The data plane is read-only
except two named surfaces (ADR-0011 decisions 3 and 5): the watchlist
store (the one UI-owned write surface, on the ADR-0006 discipline) and
the paper-level kill switch (Phase E). Page providers receive injected
read surfaces — account, marks, markets, watchlist, and the research
registries (experiments, promotions, reports) — and render them as
data; no provider is ever constructed inside a route. Research
registries are optional injections: an unbound registry renders a
typed empty state, and a promotion evidence link that cannot resolve
renders a typed "missing evidence" state — never a crash
(ADR-0011 decision 4).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from quantmesh import __version__
from quantmesh.api.app import create_app
from quantmesh.api.watchlist import WatchlistError, WatchlistStore
from quantmesh.execution.accounting import PaperAccount
from quantmesh.research.drift import PromotionLedger
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.research.reports import ReportRegistry
from quantmesh.settings import settings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


class WorkstationConfigError(ValueError):
    """The workstation was constructed with an invalid configuration."""


def _is_loopback(host: str) -> bool:
    """Loopback only: localhost, IPv6 ::1, and the whole 127.0.0.0/8."""
    return host in {"localhost", "::1"} or host.startswith("127.")


@dataclass(frozen=True)
class PageContext:
    """Everything a page provider may read: injected, never fetched."""

    account: PaperAccount
    marks: Mapping[str, float] = field(default_factory=dict)
    markets: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    watchlist: WatchlistStore | None = None
    experiments: ExperimentRegistry | None = None
    promotions: PromotionLedger | None = None
    reports: ReportRegistry | None = None


@dataclass(frozen=True)
class Page:
    """One workstation screen: route -> template -> data provider."""

    route: str
    template: str
    title: str
    provider: Callable[[PageContext], dict[str, object]]
    label: str


def _mark_for(markets: Mapping[str, Mapping[str, float]], symbol: str) -> float | None:
    """The first venue's mark for a symbol, venues sorted — deterministic."""
    for venue in sorted(markets):
        if symbol in markets[venue]:
            return markets[venue][symbol]
    return None


def _overview_provider(context: PageContext) -> dict[str, object]:
    account = context.account
    venues = []
    for venue in sorted(context.markets):
        instruments = [
            {"symbol": symbol, "mark": context.markets[venue][symbol]}
            for symbol in sorted(context.markets[venue])
        ]
        venues.append({"venue": venue, "instruments": instruments})
    watchlist_entries = [
        {"symbol": record.symbol, "mark": _mark_for(context.markets, record.symbol)}
        for record in sorted(context.watchlist.all(), key=lambda item: item.symbol)
    ] if context.watchlist is not None else []
    return {
        "account": {
            "cash": account.cash,
            "starting_cash": (
                account.starting_cash if account.starting_cash is not None else account.cash
            ),
            "equity": account.equity(context.marks),
            "kill_switch": account.kill_switch,
        },
        "marks": dict(context.marks),
        "missing_marks": sorted(
            key for key in account.positions if key not in context.marks
        ),
        "venues": venues,
        "watchlist": watchlist_entries,
    }


def _instruments_provider(context: PageContext) -> dict[str, object]:
    instruments = [
        {"venue": venue, "symbol": symbol, "mark": context.markets[venue][symbol]}
        for venue in sorted(context.markets)
        for symbol in sorted(context.markets[venue])
    ]
    return {"instruments": instruments}


def _watchlist_provider(context: PageContext) -> dict[str, object]:
    records = context.watchlist.all() if context.watchlist is not None else []
    entries = [
        {"symbol": record.symbol, "mark": _mark_for(context.markets, record.symbol)}
        for record in sorted(records, key=lambda item: item.symbol)
    ]
    return {"entries": entries}


def _fmt_parameter(value: object) -> str:
    """Byte-stable display of a registry parameter/metric value.

    The registries accept str | int | float | bool | None; every value
    renders to one deterministic string: floats via ``repr`` (shortest
    round-trip), bools lowercased, None as an en dash.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _fmt_map(values: Mapping[str, object]) -> dict[str, str]:
    return {key: _fmt_parameter(value) for key, value in values.items()}


def _experiment_view(experiment: object) -> dict[str, object]:
    """One experiment record as render data; shared by the comparison
    page and the detail page so the two views can never disagree."""
    return {
        "id": experiment.id,
        "dataset": experiment.dataset,
        "revision": experiment.revision,
        "commit": experiment.commit,
        "created_at": experiment.created_at.isoformat(),
        "parameters": _fmt_map(experiment.parameters),
        "metrics": _fmt_map(experiment.metrics),
    }


def _experiments_provider(context: PageContext) -> dict[str, object]:
    registry = context.experiments
    experiments = []
    if registry is not None:
        # Newest first, id as the deterministic tie-break.
        ordered = sorted(registry.all(), key=lambda e: (e.created_at, e.id), reverse=True)
        experiments = [_experiment_view(experiment) for experiment in ordered]
    return {"experiments": experiments, "registry_bound": registry is not None}


def _resolve_report_links(
    report_ids: list[str], registry: ReportRegistry | None
) -> list[dict[str, object]]:
    """Resolve evidence ids through the report registry; a missing
    report renders as a typed unresolved state, never a crash."""
    links = []
    for report_id_value in report_ids:
        if registry is None:
            links.append(
                {
                    "id": report_id_value,
                    "resolved": False,
                    "reason": "no report registry is bound",
                }
            )
            continue
        try:
            report = registry.get(report_id_value)
        except ValueError:
            links.append(
                {"id": report_id_value, "resolved": False, "reason": "missing evidence"}
            )
            continue
        links.append(
            {
                "id": report_id_value,
                "resolved": True,
                "strategy": report.strategy,
                "dataset": report.dataset,
                "revision": report.revision,
                "interval": report.interval,
                "metrics": _fmt_map(report.metrics),
                "windows_oos": report.evidence.get("windows_oos") is True,
            }
        )
    return links


def _promotions_provider(context: PageContext) -> dict[str, object]:
    ledger = context.promotions
    promotions = []
    if ledger is not None:
        # Newest first, id as the deterministic tie-break.
        ordered = sorted(
            ledger.all(), key=lambda record: (record.promoted_at, record.id), reverse=True
        )
        for record in ordered:
            oos = _resolve_report_links([record.oos_report_id], context.reports)[0]
            promotions.append(
                {
                    "id": record.id,
                    "signal_name": record.signal_name,
                    "promoted_at": record.promoted_at.isoformat(),
                    "kill_switch": record.kill_switch,
                    "benchmarks": _resolve_report_links(
                        record.benchmark_report_ids, context.reports
                    ),
                    "ablations": _resolve_report_links(
                        record.ablation_report_ids, context.reports
                    ),
                    "oos": oos,
                }
            )
    return {"promotions": promotions, "registry_bound": ledger is not None}


# The page registry, pinned by the page-registry test (every route
# registered, every template loadable, autoescape on, every page
# renders through its provider). Later phases append screens here.
PAGES: tuple[Page, ...] = (
    Page("/", "overview.html", "QuantMesh — Overview", _overview_provider, "Overview"),
    Page(
        "/instruments",
        "instruments.html",
        "QuantMesh — Instruments",
        _instruments_provider,
        "Instruments",
    ),
    Page(
        "/watchlist",
        "watchlist.html",
        "QuantMesh — Watchlist",
        _watchlist_provider,
        "Watchlist",
    ),
    Page(
        "/experiments",
        "experiments.html",
        "QuantMesh — Experiments",
        _experiments_provider,
        "Experiments",
    ),
    Page(
        "/promotions",
        "promotions.html",
        "QuantMesh — Promotions",
        _promotions_provider,
        "Promotions",
    ),
)


def _page_routes() -> list[tuple[str, str]]:
    return [(page.route, page.label) for page in PAGES]


def create_workstation_app(
    *,
    account: PaperAccount,
    marks: dict[str, float] | None = None,
    markets: Mapping[str, Mapping[str, float]] | None = None,
    watchlist: WatchlistStore | None = None,
    experiments: ExperimentRegistry | None = None,
    promotions: PromotionLedger | None = None,
    reports: ReportRegistry | None = None,
    host: str | None = None,
) -> FastAPI:
    """The workstation app: the M1 read-only API plus HTML screens.

    `host` overrides `settings.workstation_host` for tests and explicit
    construction; both are refused unless loopback. `marks` is held by
    reference like `create_app` — mutating it after creation is the way
    the operator supplies updated mark prices. `markets` maps venue to
    symbol -> mark and is injected by the operator; `watchlist` binds
    the UI-owned watchlist store (defaults to `settings.watchlists_dir`).
    The research registries (`experiments`, `promotions`, `reports`)
    are optional read-only injections: unbound, their pages render a
    typed empty state (ADR-0011 decision 4).
    """
    host = settings.workstation_host if host is None else host
    if not _is_loopback(host):
        raise WorkstationConfigError(
            f"workstation host must be loopback, got {host!r} "
            "(non-loopback binds are refused at construction)"
        )

    app = create_app(account=account, marks=marks)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates
    app.state.page_context = PageContext(
        account=account,
        marks=marks if marks is not None else {},
        markets=markets if markets is not None else {},
        watchlist=watchlist if watchlist is not None else WatchlistStore(),
        experiments=experiments,
        promotions=promotions,
        reports=reports,
    )

    for page in PAGES:
        app.add_api_route(
            page.route,
            _renderer(app, page),
            methods=["GET"],
            response_class=HTMLResponse,
        )

    _register_watchlist_forms(app)
    _register_experiment_detail(app)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def _register_watchlist_forms(app: FastAPI) -> None:
    @app.post("/watchlist/add", response_class=HTMLResponse)
    def watchlist_add(request: Request, symbol: str = Form(...)) -> Response:
        context = app.state.page_context
        if context.watchlist is None:
            return _error_page(app, request, "/watchlist", "no watchlist store is bound")
        try:
            context.watchlist.add(symbol)
        except WatchlistError as error:
            return _error_page(app, request, "/watchlist", str(error))
        return RedirectResponse("/watchlist", status_code=303)

    @app.post("/watchlist/remove", response_class=HTMLResponse)
    def watchlist_remove(request: Request, symbol: str = Form(...)) -> Response:
        context = app.state.page_context
        if context.watchlist is None:
            return _error_page(app, request, "/watchlist", "no watchlist store is bound")
        try:
            context.watchlist.remove(symbol)
        except WatchlistError as error:
            return _error_page(app, request, "/watchlist", str(error))
        return RedirectResponse("/watchlist", status_code=303)


def _renderer(app: FastAPI, page: Page) -> Callable[[Request], HTMLResponse]:
    def render(request: Request) -> HTMLResponse:
        return _render_page(app, page, request, {})

    return render


def _error_page(
    app: FastAPI, request: Request, route: str, message: str
) -> HTMLResponse:
    page = next(item for item in PAGES if item.route == route)
    return _render_page(app, page, request, {"error": message})


def _base_context(page_title: str, account: PaperAccount) -> dict[str, object]:
    """The shared layout context every screen starts from."""
    return {
        "page_title": page_title,
        "nav_routes": _page_routes(),
        "app_name": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
        "kill_switch": account.kill_switch,
    }


def _render_page(
    app: FastAPI, page: Page, request: Request, extra: dict[str, object]
) -> HTMLResponse:
    context = app.state.page_context
    return app.state.templates.TemplateResponse(
        request=request,
        name=page.template,
        context={
            **_base_context(page.title, context.account),
            **page.provider(context),
            **extra,
        },
    )


def _register_experiment_detail(app: FastAPI) -> None:
    """GET /experiments/{id}: one experiment record with its lake pin.

    Read-only, outside the page registry (a parameterized route does
    not fit the pinned route -> template -> provider triple). The pin
    is resolved through the registry's lake gate and rendered as a
    typed state: unavailable (missing lake, stale pin, moved manifest)
    is named, never a crash.
    """

    @app.get("/experiments/{experiment_id}", response_class=HTMLResponse)
    def experiment_detail(request: Request, experiment_id: str) -> HTMLResponse:
        context = app.state.page_context
        if context.experiments is None:
            return _error_page(app, request, "/experiments", "no experiment registry is bound")
        try:
            experiment = context.experiments.get(experiment_id)
        except ValueError as error:
            return _error_page(app, request, "/experiments", str(error))

        pin: dict[str, object] | None = None
        pin_error: str | None = None
        try:
            dataset = context.experiments.resolve(experiment_id)
            pin = {
                "name": dataset.name,
                "revision": dataset.manifest.revision,
                "series": len(dataset.manifest.coverage),
            }
        except ValueError as error:
            pin_error = str(error)

        return app.state.templates.TemplateResponse(
            request=request,
            name="experiment_detail.html",
            context={
                **_base_context(
                    f"QuantMesh — Experiment {experiment.id}", context.account
                ),
                "experiment": _experiment_view(experiment),
                "pin": pin,
                "pin_error": pin_error,
            },
        )


def main() -> None:
    """quantmesh-workstation: serve the workstation over loopback.

    Binds a fresh empty paper account as the safe local bootstrap;
    operators who want their real account/journal surfaces wired start
    the app programmatically with `create_workstation_app(account=...)`.
    """
    import uvicorn  # deferred: only the console script touches it

    host = settings.workstation_host
    if not _is_loopback(host):
        raise WorkstationConfigError(
            f"workstation host must be loopback, got {host!r} "
            "(non-loopback binds are refused at construction)"
        )
    account = PaperAccount(cash=100_000.0)
    app = create_workstation_app(account=account, host=host)
    uvicorn.run(app, host=host, port=settings.workstation_port)
