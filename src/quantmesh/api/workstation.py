"""Local frontend workstation (M9, issues #51-#52).

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
except two named surfaces (ADR-0011 decisions 3-4): the watchlist
store (the one UI-owned write surface, on the ADR-0006 discipline) and
the paper-level kill switch (Phase E). Page providers receive injected
read surfaces — account, marks, markets, watchlist — and render them
as data; no provider is ever constructed inside a route.
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
)


def _page_routes() -> list[tuple[str, str]]:
    return [(page.route, page.label) for page in PAGES]


def create_workstation_app(
    *,
    account: PaperAccount,
    marks: dict[str, float] | None = None,
    markets: Mapping[str, Mapping[str, float]] | None = None,
    watchlist: WatchlistStore | None = None,
    host: str | None = None,
) -> FastAPI:
    """The workstation app: the M1 read-only API plus HTML screens.

    `host` overrides `settings.workstation_host` for tests and explicit
    construction; both are refused unless loopback. `marks` is held by
    reference like `create_app` — mutating it after creation is the way
    the operator supplies updated mark prices. `markets` maps venue to
    symbol -> mark and is injected by the operator; `watchlist` binds
    the UI-owned watchlist store (defaults to `settings.watchlists_dir`).
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
    )

    for page in PAGES:
        app.add_api_route(
            page.route,
            _renderer(app, page),
            methods=["GET"],
            response_class=HTMLResponse,
        )

    _register_watchlist_forms(app)

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


def _render_page(
    app: FastAPI, page: Page, request: Request, extra: dict[str, object]
) -> HTMLResponse:
    context = app.state.page_context
    return app.state.templates.TemplateResponse(
        request=request,
        name=page.template,
        context={
            "page_title": page.title,
            "nav_routes": _page_routes(),
            "app_name": settings.app_name,
            "environment": settings.environment,
            "version": __version__,
            "kill_switch": context.account.kill_switch,
            **page.provider(context),
            **extra,
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
