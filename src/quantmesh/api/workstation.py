"""Local frontend workstation shell (M9, issue #51).

`create_workstation_app` supersets the M1 read-only `create_app` with
server-rendered Jinja2 pages: a strict route -> template -> data
provider registry, a shared layout with keyboard/accessibility posture
(skip link, landmarks, visible focus, local stylesheet — no CDN), and
static assets served by the same process. No node toolchain, no build
step.

Construction is fail-closed on the bind surface: a non-loopback
`settings.workstation_host` is a typed `WorkstationConfigError` — the
workstation is a local surface, never env-escalable (ADR-0011 decision
2, the ADR-0010 loopback discipline). The data plane is read-only: page
providers receive the injected account and marks and render them as
data; nothing on this layer creates or cancels orders.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from quantmesh import __version__
from quantmesh.api.app import create_app
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


@dataclass(frozen=True)
class Page:
    """One workstation screen: route -> template -> data provider."""

    route: str
    template: str
    title: str
    provider: Callable[[PageContext], dict[str, object]]


def _home_provider(context: PageContext) -> dict[str, object]:
    account = context.account
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
    }


# The shell phase ships the home screen; later phases append screens to
# this registry, which the page-registry test pins (every route
# registered, every template loadable, autoescape on).
PAGES: tuple[Page, ...] = (
    Page("/", "home.html", "QuantMesh — Home", _home_provider),
)


def _page_routes() -> list[str]:
    return [page.route for page in PAGES]


def create_workstation_app(
    *,
    account: PaperAccount,
    marks: dict[str, float] | None = None,
    host: str | None = None,
) -> FastAPI:
    """The workstation app: the M1 read-only API plus HTML screens.

    `host` overrides `settings.workstation_host` for tests and explicit
    construction; both are refused unless loopback. `marks` is held by
    reference like `create_app` — mutating it after creation is the way
    the operator supplies updated mark prices.
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
    app.state.page_context = PageContext(account=account, marks=marks if marks is not None else {})

    for page in PAGES:
        app.add_api_route(
            page.route,
            _renderer(app, page),
            methods=["GET"],
            response_class=HTMLResponse,
        )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def _renderer(app: FastAPI, page: Page) -> Callable[[Request], HTMLResponse]:
    def render(request: Request) -> HTMLResponse:
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
            },
        )

    return render


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
