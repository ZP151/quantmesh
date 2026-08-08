"""Local frontend workstation (M9, issues #51-#54).

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
except two named surfaces (ADR-0011 decisions 3 and 6): the watchlist
store (the one UI-owned write surface, on the ADR-0006 discipline) and
the paper-level kill switch (Phase E). Page providers receive injected
read surfaces — account, marks, markets, watchlist, the research
registries (experiments, promotions, reports) and the forecast report
registry (Phase D) — and render them as data; no provider is ever
constructed inside a route. Research registries are optional
injections: an unbound registry renders a typed empty state, a
promotion evidence link that cannot resolve renders a typed "missing
evidence" state, an unresolved forecast window renders "pending", and
a missing forecast artifact renders a typed state — never a crash and
never a fabricated number (ADR-0011 decisions 4-5).

Portfolio screens (positions, orders, P&L) render the M1 surface:
positions compute unrealized P&L exactly like the `/positions`
endpoint, orders serialize through the same `_order_summary` the JSON
endpoint uses, and the P&L page mirrors `/pnl`. The screens live under
`/portfolio/*` so they never shadow the M1 JSON routes on the same app
object (ADR-0011 decision 5).
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
from quantmesh.api.app import _order_summary, create_app
from quantmesh.api.watchlist import WatchlistError, WatchlistStore
from quantmesh.domain.orders import Order
from quantmesh.events.forecast import ForecastReportRegistry, forecast_artifact_paths
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
    forecasts: ForecastReportRegistry | None = None


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


def _positions_provider(context: PageContext) -> dict[str, object]:
    """Portfolio positions over the M1 surface: unrealized P&L computed
    exactly like the `/positions` endpoint, missing marks named."""
    marks = dict(context.marks)
    positions = [
        {
            "key": key,
            "instrument": position.instrument.model_dump(mode="json"),
            "quantity": position.quantity,
            "average_cost": position.average_cost,
            "realized_pnl": position.realized_pnl,
            "unrealized_pnl": (
                (marks[key] - position.average_cost) * position.quantity
                if key in marks
                else None
            ),
        }
        for key, position in context.account.positions.items()
    ]
    return {"positions": positions}


def _order_view(order: Order) -> dict:
    """One order as render data: the exact M1 summary plus its fills.

    `_order_summary` is the same function the JSON `/orders` endpoint
    serializes with, so the HTML screen and the API surface cannot
    drift apart (ADR-0011 decision 1); fills are the order's own
    fill events, extracted here for the screen.
    """
    view = _order_summary(order)
    view["fills"] = [
        event for event in view["events"] if event["event_type"] == "fill"
    ]
    return view


def _orders_provider(context: PageContext) -> dict[str, object]:
    orders = [
        _order_view(order)
        for order in sorted(
            context.account.orders.values(),
            key=lambda item: (item.created_at, item.order_id),
            reverse=True,
        )
    ]
    return {"orders": orders}


def _pnl_provider(context: PageContext) -> dict[str, object]:
    """Account summary and P&L, mirroring the `/pnl` endpoint exactly:
    equity-based numbers consume only the injected marks, and positions
    without a mark are named so understated equity is never silent."""
    account = context.account
    marks = dict(context.marks)
    return {
        "starting_cash": (
            account.starting_cash if account.starting_cash is not None else account.cash
        ),
        "cash": account.cash,
        "total_fees": account.total_fees,
        "order_sequence": account.order_sequence,
        "realized_pnl": account.realized_pnl,
        "unrealized_pnl": account.unrealized_pnl(marks),
        "equity": account.equity(marks),
        "total_pnl": account.total_pnl(marks),
        "marks": marks,
        "missing_marks": sorted(
            key for key in account.positions if key not in marks
        ),
    }


def _window_view(window: object) -> dict[str, object]:
    """One evaluation window as render data. Unresolved windows keep
    ``brier=None`` — the template renders "pending", never a number."""
    return {
        "index": window.index,
        "train_end": window.train_end.isoformat(),
        "test_start": window.test_start.isoformat(),
        "test_end": window.test_end.isoformat(),
        "brier": window.brier,
        "liquidity_weighted_brier": window.liquidity_weighted_brier,
        "n_observations": window.n_observations,
        "n_resolved": window.n_resolved,
        "calibration_bins": [
            {
                "bin": bin_row.bin,
                "lo": repr(bin_row.lo),
                "hi": repr(bin_row.hi),
                "count": bin_row.count,
                "mean_prediction": bin_row.mean_prediction,
                "observed_frequency": bin_row.observed_frequency,
                "brier": bin_row.brier,
            }
            for bin_row in window.calibration_bins
        ],
    }


def _market_view(report: object, market: object) -> dict[str, object]:
    """One market's evaluation card: identity plus the windows that
    evaluate its implied probabilities.

    A forecast report records window results, not the observation grid,
    so a "current probability" cannot be rendered from it — the card
    shows the evaluation of the venue's mid-derived probabilities, and
    an unresolved window renders "pending", never a fabricated number.
    The universe member is matched back by composite id.
    """
    member = next(
        (
            candidate
            for candidate in report.universe
            if f"{candidate.venue.value}:{candidate.venue_market_id}"
            == market.market_id
        ),
        None,
    )
    windows = [_window_view(window) for window in market.windows]
    return {
        "market_id": market.market_id,
        "title": member.title if member is not None else market.market_id,
        "event_ticker": member.event_ticker if member is not None else None,
        "venue": member.venue.value if member is not None else None,
        "venue_market_id": member.venue_market_id if member is not None else None,
        "expiry_at": (
            member.expiry_at.isoformat()
            if member is not None and member.expiry_at is not None
            else None
        ),
        "resolved": bool(member.resolution) if member is not None else False,
        "n_evaluated_windows": sum(1 for window in windows if window["brier"] is not None),
        "windows": windows,
    }


def _forecast_view(registry: ForecastReportRegistry, report: object) -> dict[str, object]:
    """One forecast report as render data: setup, aggregate metrics, the
    per-market cards and the artifact state on disk. A report whose
    artifacts are missing renders a typed state naming the absent files
    — the record still renders."""
    paths = forecast_artifact_paths(registry.root, report)
    present = {name: path.exists() for name, path in paths.items()}
    return {
        "id": report.id,
        "commit": report.commit,
        "created_at": report.created_at.isoformat(),
        "window_spec": {
            "train": report.window_spec.train_observations,
            "test": report.window_spec.test_observations,
            "step": report.window_spec.step_observations,
        },
        "n_bins": report.n_bins,
        "metrics": _fmt_map(report.metrics),
        "markets": [_market_view(report, market) for market in report.markets],
        "artifacts_present": all(present.values()),
        "artifacts": present,
    }


def _forecasts_provider(context: PageContext) -> dict[str, object]:
    registry = context.forecasts
    reports = []
    if registry is not None:
        # Newest first, id as the deterministic tie-break.
        ordered = sorted(
            registry.all(), key=lambda item: (item.created_at, item.id), reverse=True
        )
        reports = [_forecast_view(registry, report) for report in ordered]
    return {"reports": reports, "registry_bound": registry is not None}


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
    # Portfolio screens under /portfolio/* so the M1 JSON endpoints
    # (/positions, /orders, /pnl) stay served on the same app object.
    Page(
        "/portfolio/positions",
        "positions.html",
        "QuantMesh — Positions",
        _positions_provider,
        "Positions",
    ),
    Page(
        "/portfolio/orders",
        "orders.html",
        "QuantMesh — Orders",
        _orders_provider,
        "Orders",
    ),
    Page(
        "/portfolio/pnl",
        "pnl.html",
        "QuantMesh — PnL",
        _pnl_provider,
        "P&L",
    ),
    Page(
        "/forecasts",
        "forecasts.html",
        "QuantMesh — Forecasts",
        _forecasts_provider,
        "Forecasts",
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
    forecasts: ForecastReportRegistry | None = None,
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
    and the forecast report registry (`forecasts`) are optional
    read-only injections: unbound, their pages render a typed empty
    state (ADR-0011 decision 4).
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
        forecasts=forecasts,
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
