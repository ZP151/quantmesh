"""Local frontend workstation (M9, issues #51-#55; M11, ADR-0013).

`create_workstation_app` supersets the M1 read-only `create_app` with
the operator surface. Since ADR-0013 that surface is the React SPA by
default: the committed bundle is served under `/app`, every legacy
route 302s to its SPA counterpart, and `/app/{path:path}` falls
through to `index.html` so react-router deep links work on refresh —
no node toolchain at serve time. With `QUANTMESH_LEGACY_UI=1` the RC1
Jinja2 pages mount instead (the ADR's same-release rollback switch): a
strict route -> template -> data provider registry, a shared layout
with keyboard/accessibility posture (skip link, landmarks, visible
focus, local stylesheet — no CDN), and static assets served by the
same process.

Construction is fail-closed on the bind surface: a non-loopback
`settings.workstation_host` is a typed `WorkstationConfigError` — the
workstation is a local surface, never env-escalable (ADR-0011 decision
2, the ADR-0010 loopback discipline). The data plane is read-only
except two named surfaces (ADR-0011 decisions 3 and 6): the watchlist
store (the one UI-owned write surface, on the ADR-0006 discipline) and
the paper-level kill switch, a form control that flips the injected
paper account's global flag or one venue's flag (M10 Phase C) — the
accounting risk gate refuses new order submissions while the global
switch or the order's venue switch is engaged, with no model
involvement. Both write surfaces stay registered in SPA mode: the SPA
calls the same loopback POSTs. Page providers receive injected read surfaces — account, marks,
markets, watchlist, the research registries (experiments, promotions,
reports), the forecast report registry (Phase D), and the Phase E
surfaces (the alert ledger, the audit journals — orders, mappings,
decisions — and the document index) — and render them as data; no
provider is ever constructed inside a route. Research registries are
optional injections: an unbound registry renders a typed empty state,
a promotion evidence link that cannot resolve renders a typed "missing
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

import asyncio
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from quantmesh import __version__
from quantmesh.ai.decisions import DecisionLog
from quantmesh.ai.retrieval import DocumentIndex
from quantmesh.api.app import _order_summary, create_app
from quantmesh.api.watchlist import WatchlistError, WatchlistRecord, WatchlistStore
from quantmesh.domain.models import Instrument, Quote, Venue
from quantmesh.domain.orders import Order
from quantmesh.events.forecast import ForecastReportRegistry, forecast_artifact_paths
from quantmesh.events.mapping import MappingLedger
from quantmesh.execution.account_store import (
    PaperAccountFile,
    PaperAccountStore,
    recover_account_from_journal,
)
from quantmesh.execution.accounting import PaperAccount
from quantmesh.execution.journal import OrderJournal
from quantmesh.hyperliquid.risk import RiskLimits as HyperliquidRiskLimits
from quantmesh.instruments.api import instrument_router
from quantmesh.instruments.forecast import PriceForecastRegistry
from quantmesh.instruments.history import HistoryService
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.instruments.proposals import PaperDecisionService, ProposalLedger
from quantmesh.instruments.workspace import InstrumentWorkspaceService
from quantmesh.live.api import live_router
from quantmesh.live.contract import UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.fence import QuoteFence
from quantmesh.live.marks import (
    AccountValuationSnapshot,
    LiveMarkSnapshot,
    account_valuation_snapshot,
    live_mark_snapshot,
)
from quantmesh.live.prediction import PredictionBoard
from quantmesh.ops.enablement import GATE_TEXT, ApprovalLedger
from quantmesh.research.drift import AlertLedger, PromotionLedger
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.research.reports import ReportRegistry
from quantmesh.settings import settings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
# The committed SPA bundle (ADR-0013 decision 2): vite builds with
# base "/app/" into frontend/dist, and tools/build_frontend.py copies
# the result here so the Python package serves it — no node runtime at
# serve time. The bundle is part of the package data, so a missing
# directory means a checkout predating the build.
SPA_DIR = STATIC_DIR / "app"
SPA_INDEX = SPA_DIR / "index.html"
SPA_ASSETS = SPA_DIR / "assets"
# The bundle's root-level files (vite public/) are the only non-asset
# paths served directly; everything else under /app falls through to
# index.html for react-router. A whitelist stays fail-closed — no
# filesystem traversal surface on the loopback bind.
_BUNDLE_ROOT_FILES = frozenset({"favicon.svg", "icons.svg"})

# ADR-0013 decision 3: in SPA mode every legacy route 302s to the /app
# path whose SPA screen supersedes it; react-router owns deep links
# from there. The parameterized detail pages redirect to their SPA
# listing until Phase C adds the real detail routes.
LEGACY_TO_SPA: dict[str, str] = {
    "/": "/app/",
    "/instruments": "/app/markets",
    "/watchlist": "/app/markets/watchlist",
    "/experiments": "/app/research/experiments",
    "/promotions": "/app/research/promotions",
    "/forecasts": "/app/research/forecasts",
    "/portfolio/positions": "/app/trading/positions",
    "/portfolio/orders": "/app/trading/orders",
    "/portfolio/pnl": "/app/trading/pnl",
    "/risk": "/app/risk",
    "/audit": "/app/ops/audit",
    "/kill-switch/control": "/app/ops/kill-switch",
    "/enablement": "/app/ops/enablement",
}


def _spa_missing_page() -> str:
    """The instructive 503 body served when the SPA bundle is absent.

    The bundle is committed to the package, so a missing bundle means
    the checkout predates the frontend build (or the package was
    trimmed). Name the recovery paths: build once, or set
    QUANTMESH_LEGACY_UI=1 to remount the RC1 pages from this same
    release. Never a blank page.
    """
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>QuantMesh — frontend bundle missing</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:44rem;"
        "margin:3rem auto;padding:0 1rem;line-height:1.5}"
        "code{background:#f2f2f2;padding:.1em .35em;border-radius:4px}"
        "</style></head><body>"
        "<h1>Frontend bundle missing</h1>"
        "<p>This workstation serves the QuantMesh web app (ADR-0013), but "
        f"<code>{SPA_DIR}</code> does not contain a build. The bundle is "
        "committed to the package, so this usually means the checkout "
        "predates the frontend build.</p>"
        "<p>Recovery:</p><ul>"
        "<li>Run <code>python tools/build_frontend.py</code> and restart.</li>"
        "<li>Or set <code>QUANTMESH_LEGACY_UI=1</code> and restart to "
        "remount the RC1 server-rendered pages from this same release "
        "(the ADR-0013 rollback switch).</li>"
        "</ul></body></html>"
    )


class WorkstationConfigError(ValueError):
    """The workstation was constructed with an invalid configuration."""


def _is_loopback(host: str) -> bool:
    """Loopback only: localhost, IPv6 ::1, and the whole 127.0.0.0/8."""
    return host in {"localhost", "::1"} or host.startswith("127.")


def _guard_origin(app: FastAPI, request: Request, redirect: str, surface: str) -> Response | None:
    """Refuse a write-surface POST whose Origin is present but not
    loopback (threat model T-14, docs/threat-model.md).

    Browser CSRF — a hostile page in the user's browser POSTing to the
    loopback bind — always sends an Origin naming the attacker's site;
    a same-origin form send names the loopback host. An absent Origin
    is allowed: a non-browser client (CLI, drill) cannot be
    distinguished from a same-origin send, and refusing it would break
    every non-browser consumer of the two write surfaces. Returns the
    typed error page to return, or None when the origin passes.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return None
    try:
        hostname = urlsplit(origin).hostname
    except ValueError:
        hostname = None
    if hostname is not None and _is_loopback(hostname):
        return None
    return _error_page(
        app,
        request,
        redirect,
        f"{surface} POST refused: cross-origin send (Origin {origin!r} is not loopback)",
    )


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
    alerts: AlertLedger | None = None
    journal: OrderJournal | None = None
    mappings: MappingLedger | None = None
    decisions: DecisionLog | None = None
    documents: DocumentIndex | None = None
    hl_posture: HyperliquidRiskLimits | None = None
    enablement: ApprovalLedger | None = None


@dataclass(frozen=True)
class Page:
    """One workstation screen: route -> template -> data provider."""

    route: str
    template: str
    title: str
    provider: Callable[[PageContext], dict[str, object]]
    label: str


def _watchlist_entry(
    markets: Mapping[str, Mapping[str, float]],
    record: WatchlistRecord,
) -> dict[str, object]:
    venue = record.venue.value if record.venue is not None else None
    mark = markets.get(venue, {}).get(record.symbol) if venue is not None else None
    return {"venue": venue, "symbol": record.symbol, "mark": mark}


def _overview_provider(context: PageContext) -> dict[str, object]:
    account = context.account
    venues = []
    for venue in sorted(context.markets):
        instruments = [
            {"symbol": symbol, "mark": context.markets[venue][symbol]}
            for symbol in sorted(context.markets[venue])
        ]
        venues.append({"venue": venue, "instruments": instruments})
    watchlist_entries = (
        [
            _watchlist_entry(context.markets, record)
            for record in sorted(
                context.watchlist.all(),
                key=lambda item: (item.symbol, item.venue.value if item.venue else ""),
            )
        ]
        if context.watchlist is not None
        else []
    )
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
        "missing_marks": sorted(key for key in account.positions if key not in context.marks),
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
        _watchlist_entry(context.markets, record)
        for record in sorted(
            records,
            key=lambda item: (item.symbol, item.venue.value if item.venue else ""),
        )
    ]
    return {"entries": entries, "venues": sorted(context.markets)}


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
            links.append({"id": report_id_value, "resolved": False, "reason": "missing evidence"})
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
                    "ablations": _resolve_report_links(record.ablation_report_ids, context.reports),
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
                (marks[key] - position.average_cost) * position.quantity if key in marks else None
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
    view["fills"] = [event for event in view["events"] if event["event_type"] == "fill"]
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
        "missing_marks": sorted(key for key in account.positions if key not in marks),
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

    The forecast report retains its latest observed probability explicitly;
    expose that value and its timestamp rather than fabricating a current
    quote from window results. An unresolved window renders "pending", never
    a fabricated calibration score. The universe member is matched back by
    composite id.
    """
    member = next(
        (
            candidate
            for candidate in report.universe
            if f"{candidate.venue.value}:{candidate.venue_market_id}" == market.market_id
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
        "latest_probability": market.latest_probability,
        "latest_probability_at": (
            market.latest_probability_at.isoformat()
            if market.latest_probability_at is not None
            else None
        ),
        "latest_liquidity_confidence": market.latest_liquidity_confidence,
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
        ordered = sorted(registry.all(), key=lambda item: (item.created_at, item.id), reverse=True)
        reports = [_forecast_view(registry, report) for report in ordered]
    return {"reports": reports, "registry_bound": registry is not None}


def _risk_provider(context: PageContext) -> dict[str, object]:
    """The risk screen: the injected account's own pre-trade limits
    (the accounting `RiskLimits` the paper kernel enforces), the M5
    Hyperliquid pre-submission posture as an optional injected surface
    (typed unbound state), and the M7 alert ledger with source
    attribution."""
    limits = context.account.risk_limits
    alerts = []
    if context.alerts is not None:
        # Newest first, id as the deterministic tie-break.
        ordered = sorted(
            context.alerts.all(),
            key=lambda record: (record.detected_at, record.id),
            reverse=True,
        )
        alerts = [
            {
                "id": record.id,
                "kind": record.kind,
                "source": record.source,
                "detected_at": record.detected_at.isoformat(),
                "message": record.message,
                "observed": _fmt_map(record.observed),
            }
            for record in ordered
        ]
    posture = context.hl_posture
    return {
        "paper_limits": {
            "kill_switch": context.account.kill_switch,
            "max_order_quantity": limits.max_order_quantity,
            "max_notional": limits.max_notional,
            "max_position_quantity": limits.max_position_quantity,
        },
        "hl_posture": (
            None
            if posture is None
            else {
                "max_leverage": posture.max_leverage,
                "min_liquidation_distance_bps": posture.min_liquidation_distance_bps,
                "reduce_only": posture.reduce_only,
                "stale_data_window_s": posture.stale_data_window_s,
            }
        ),
        "alerts": alerts,
        "alerts_bound": context.alerts is not None,
    }


def _citation_href(citation: object) -> str:
    """A decision citation's browse target: experiment records resolve
    to their detail page, documents to theirs, audit citations to the
    journal entry on the audit page itself (anchor)."""
    if citation.source_kind == "experiment":
        return f"/experiments/{quote(citation.source_id, safe='')}"
    if citation.source_kind == "document":
        return f"/documents/{quote(citation.source_id, safe='')}"
    return f"/audit#order-{quote(citation.source_id, safe='')}"


def _decision_view(record: object) -> dict[str, object]:
    """One decision record as render data: model metadata and the
    citations as resolvable links (ADR-0011 decision 6)."""
    return {
        "decision_id": record.decision_id,
        "run_id": record.run_id,
        "role": record.role,
        "model": {
            "name": record.model.name,
            "version": record.model.version,
            "endpoint_kind": record.model.endpoint_kind,
        },
        "prompt_digest": record.prompt_digest,
        "schema_id": record.schema_id,
        "verdict": record.verdict,
        "output_digest": record.output_digest,
        "refusal": record.refusal,
        "recorded_at": record.recorded_at.isoformat(),
        "citations": [
            {
                "source_kind": citation.source_kind,
                "source_id": citation.source_id,
                "span": (
                    f"{citation.span[0]}–{citation.span[1]}" if citation.span is not None else None
                ),
                "href": _citation_href(citation),
            }
            for citation in record.citations
        ],
    }


def _audit_provider(context: PageContext) -> dict[str, object]:
    """One chronological view over the M2 order journal (with events),
    the M6 mapping ledger and the M8 decision log — every entry carries
    its source record's id and anchor. Each ledger is an optional
    injection; unbound ledgers render a typed line, never a crash."""
    entries: list[dict[str, object]] = []
    if context.journal is not None:
        for order in sorted(
            context.journal.all(),
            key=lambda item: (item.created_at, item.order_id),
            reverse=True,
        ):
            entries.append(
                {
                    "kind": "order",
                    "at": order.created_at.isoformat(),
                    "anchor": f"order-{quote(order.order_id, safe='')}",
                    "order": _order_view(order),
                }
            )
    if context.mappings is not None:
        for record in sorted(
            context.mappings.all(),
            key=lambda item: (item.recorded_at, item.pair_key),
            reverse=True,
        ):
            entries.append(
                {
                    "kind": "mapping",
                    "at": record.recorded_at.isoformat(),
                    "anchor": f"mapping-{quote(record.pair_key, safe='')}",
                    "mapping": {
                        "pair_key": record.pair_key,
                        "status": record.status.value,
                        "commit": record.commit,
                        "recorded_at": record.recorded_at.isoformat(),
                        "evidence": [
                            {"kind": item.kind.value, "detail": item.detail}
                            for item in record.evidence
                        ],
                    },
                }
            )
    if context.decisions is not None:
        for record in sorted(
            context.decisions.all(),
            key=lambda item: (item.recorded_at, item.decision_id),
            reverse=True,
        ):
            entries.append(
                {
                    "kind": "decision",
                    "at": record.recorded_at.isoformat(),
                    "anchor": f"decision-{quote(record.decision_id, safe='')}",
                    "decision": _decision_view(record),
                }
            )
    entries.sort(
        key=lambda entry: (entry["at"], entry["kind"], entry["anchor"]),
        reverse=True,
    )
    return {
        "entries": entries,
        "journal_bound": context.journal is not None,
        "mappings_bound": context.mappings is not None,
        "decisions_bound": context.decisions is not None,
    }


def _kill_switch_provider(context: PageContext) -> dict[str, object]:
    """The kill-switch page: the global flag, the per-venue flags over
    the venues the workstation knows (the injected markets; the
    account's own flags when markets is empty), and the confirmation
    forms. Global and per-venue live on the same account object the
    form flips, so the JSON surface, the page context and the kernel
    gate cannot disagree (ADR-0012 decision 3)."""
    account = context.account
    names = {venue.value for venue in account.kill_switches}
    names.update(context.markets)
    kill_switches: dict[str, bool] = {}
    for name in sorted(names):
        try:
            venue = Venue(name)
        except ValueError:
            # A markets key that is not a venue cannot be engaged; it is
            # never rendered as a control.
            continue
        kill_switches[name] = account.kill_switches.get(venue, False)
    return {"kill_switch": account.kill_switch, "kill_switches": kill_switches}


def _enablement_provider(context: PageContext) -> dict[str, object]:
    """The enablement screen (M10 Phase E): read-only per-venue state
    derived from the approval ledger, plus the recorded live-enablement
    gate text. There is deliberately no form and no POST: enablement
    transitions are CLI/operator-owned and never permitted from the
    UI."""
    ledger = context.enablement
    states = []
    if ledger is not None:
        for venue in sorted(ledger.states()):
            states.append({"venue": venue.value, "state": ledger.state(venue).value})
    return {
        "states": states,
        "bound": ledger is not None,
        "gate_text": GATE_TEXT,
    }


def _json_context(request: Request) -> PageContext:
    """The page context every JSON route renders; a plain M1 app (no
    workstation context) is a typed 404, never an attribute error."""
    context = getattr(request.app.state, "page_context", None)
    if context is None:
        raise HTTPException(status_code=404, detail="no workstation context is attached")
    provider = getattr(request.app.state, "mark_snapshot_provider", None)
    if callable(provider):
        state = provider()
        if isinstance(state, AccountValuationSnapshot):
            return replace(
                context,
                account=state.account,
                marks=dict(state.marks),
            )
        return replace(
            context,
            account=request.app.state.account,
            marks=dict(state["marks"]),
        )
    return context


def _json_guard_origin(request: Request, surface: str) -> None:
    """Refuse a JSON write POST whose Origin is present but not
    loopback (threat model T-14), as a typed 403 for the JSON surface
    instead of the HTML error page the form endpoints render."""
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


class _KillSwitchBody(BaseModel):
    """The JSON kill-switch flip the SPA shell calls. The form endpoint
    stays the RC1 contract; both flip the same account object and
    replace it in app.state and the page context, so the JSON surface,
    every page and the kernel gate agree (ADR-0011 decision 6)."""

    action: Literal["engage", "disarm"]
    venue: str | None = None


def spa_router() -> APIRouter:
    """The SPA JSON read surface (iteration 0014 Phase C).

    One route per screen, rendering through the exact page providers
    the RC1 templates use — the same functions, the same dicts — so
    the browser and the legacy screens can never disagree. The surface
    is a strict superset of the M1 API: /api/overview, /api/markets,
    /api/watchlist, /api/experiments, /api/promotions, /api/forecasts,
    /api/risk, /api/audit and /api/enablement, plus the JSON
    kill-switch POST the shell's persistent control calls.
    """
    router = APIRouter()

    def read(route: str, name: str, provider: Callable[[PageContext], dict[str, object]]) -> None:
        def handle(request: Request) -> dict[str, object]:
            return provider(_json_context(request))

        router.add_api_route(route, handle, methods=["GET"], name=name)

    read("/overview", "overview", _overview_provider)
    read("/markets", "markets", _instruments_provider)
    read("/watchlist", "watchlist", _watchlist_provider)
    read("/experiments", "experiments", _experiments_provider)
    read("/promotions", "promotions", _promotions_provider)
    read("/forecasts", "forecasts", _forecasts_provider)
    read("/risk", "risk", _risk_provider)
    read("/audit", "audit", _audit_provider)
    read("/enablement", "enablement", _enablement_provider)

    @router.post("/kill-switch")
    def kill_switch_json(request: Request, body: _KillSwitchBody) -> dict[str, object]:
        _json_guard_origin(request, "kill-switch")
        venue_enum = None
        if body.venue is not None:
            try:
                venue_enum = Venue(body.venue)
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"kill-switch POST refused: unknown venue {body.venue!r}",
                ) from None

        def flip(current: PaperAccount) -> PaperAccount:
            if venue_enum is None:
                return current.model_copy(update={"kill_switch": body.action == "engage"})
            kill_switches = dict(current.kill_switches)
            if body.action == "engage":
                kill_switches[venue_enum] = True
            else:
                kill_switches.pop(venue_enum, None)
            return current.model_copy(update={"kill_switches": kill_switches})

        store: PaperAccountStore = request.app.state.account_store
        flipped = store.update(flip)
        return _kill_switch_provider(replace(_json_context(request), account=flipped))

    return router


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
    Page("/risk", "risk.html", "QuantMesh — Risk", _risk_provider, "Risk"),
    Page("/audit", "audit.html", "QuantMesh — Audit", _audit_provider, "Audit"),
    # The M1 JSON surface owns GET /kill-switch (first-registered wins),
    # so the HTML control page lives at /kill-switch/control; the POST
    # handler shares /kill-switch with the JSON GET without shadowing.
    Page(
        "/kill-switch/control",
        "kill_switch.html",
        "QuantMesh — Kill Switch",
        _kill_switch_provider,
        "Kill switch",
    ),
    Page(
        "/enablement",
        "enablement.html",
        "QuantMesh — Enablement",
        _enablement_provider,
        "Enablement",
    ),
)


def _page_routes() -> list[tuple[str, str]]:
    return [(page.route, page.label) for page in PAGES]


def _feed_lifespan(feed: LiveFeed) -> Callable[[FastAPI], object]:
    """The app lifespan for an attached feed: start the pump with the
    app and stop it on shutdown.

    The pump's supervisor tasks reconnect forever; only this shutdown
    cancels them. An attached feed is the live read-only path
    (ADR-0014 decision 4); the deterministic drills drive the feed's
    ingest surface directly and never start the pump against the
    network. Starlette calls the returned callable with the app and
    uses the resulting async context manager as the lifespan.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(feed.run())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return lifespan


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
    alerts: AlertLedger | None = None,
    journal: OrderJournal | None = None,
    mappings: MappingLedger | None = None,
    decisions: DecisionLog | None = None,
    documents: DocumentIndex | None = None,
    hl_posture: HyperliquidRiskLimits | None = None,
    enablement: ApprovalLedger | None = None,
    history: HistoryService | None = None,
    price_forecasts: PriceForecastRegistry | None = None,
    proposal_ledger: ProposalLedger | None = None,
    account_sink: Callable[[PaperAccount], None] | None = None,
    demo_quote_provider: Callable[[Instrument, datetime], Quote] | None = None,
    workspace_clock: Callable[[], datetime] | None = None,
    live_feed: LiveFeed | None = None,
    prediction: PredictionBoard | None = None,
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
    state (ADR-0011 decision 4). The Phase E surfaces are the same
    kind of injection: the alert ledger (`alerts`), the audit journals
    (`journal`, `mappings`, `decisions`), the document index
    (`documents`) and the M5 Hyperliquid pre-submission posture
    (`hl_posture`) — unbound, the risk and audit pages render typed
    lines naming the missing surface. The M10 Phase E enablement
    ledger (`enablement`) is the same kind of injection: the
    /enablement screen renders per-venue state and the recorded
    live-enablement gate, read-only — transitions are CLI/operator-
    owned and never permitted from the UI. The kill-switch POST flips
    the injected account's flag in both `app.state` and the page
    context, so the JSON surface and every page agree (ADR-0011
    decision 6). `history` (iteration 0020 Task 6) attaches the
    manifest-gated historical instrument service. Its read-only router
    mounts at both the root and `/api`; without the service it returns a
    typed 404 and never constructs data inside a request. `live_feed`
    (iteration 0015 Phase C) attaches the live
    read-only feed: the /api/live surface mounts either way (404
    without a feed), and an attached feed starts its pump with the app
    lifespan and stops it on shutdown. `prediction` (iteration 0015
    Phase E) attaches the prediction comparison board: /live/prediction
    mounts either way (404 without a board), and an attached board
    renders the cross-venue comparison from the feed's latest state —
    no board without its feed, no fabricated probability.
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
        alerts=alerts,
        journal=journal,
        mappings=mappings,
        decisions=decisions,
        documents=documents,
        hl_posture=hl_posture,
        enablement=enablement,
    )
    effective_history = (
        LiveHistoryService(history, live_feed) if live_feed is not None else history
    )
    app.state.history = effective_history
    app.state.price_forecasts = price_forecasts
    clock = workspace_clock if workspace_clock is not None else lambda: datetime.now(UTC)
    app.state.instrument_clock = clock

    def publish_account(updated: PaperAccount) -> None:
        if account_sink is not None:
            account_sink(updated)
        app.state.account = updated
        app.state.page_context = replace(app.state.page_context, account=updated)

    account_store = PaperAccountStore(account, publish=publish_account)
    app.state.account_store = account_store

    def mark_snapshot_provider(as_of: datetime | None = None) -> AccountValuationSnapshot:
        valuation_at = clock() if as_of is None else as_of
        current = account_store.get()
        if live_feed is None:
            return account_valuation_snapshot(
                current,
                LiveMarkSnapshot(marks=dict(app.state.marks), statuses={}),
            )
        snapshot = live_mark_snapshot(
            current,
            base_marks=dict(app.state.marks),
            feed=live_feed,
            as_of=valuation_at,
        )
        return account_valuation_snapshot(current, snapshot)

    app.state.mark_snapshot_provider = mark_snapshot_provider

    def replace_account(updated: PaperAccount) -> None:
        account_store.replace(updated)

    app.state.replace_account = replace_account

    paper_decisions = None
    if price_forecasts is not None and proposal_ledger is not None:
        paper_decisions = PaperDecisionService(
            ledger=proposal_ledger,
            forecast_registry=price_forecasts,
            account_provider=account_store.get,
            account_sink=replace_account,
            account_transaction=account_store.transaction,
            journal=journal,
            snapshot_provider=(
                (
                    lambda instrument, now: live_feed.snapshot_exact(
                        instrument.venue,
                        instrument.symbol,
                        UpdateKind.QUOTE,
                        as_of=now,
                    )
                )
                if live_feed is not None
                else lambda _instrument, _now: None
            ),
            quote_fence=QuoteFence(),
            demo_quote_provider=demo_quote_provider,
            now=clock,
        )
        app.state.paper_decisions = paper_decisions
        app.state.proposal_service = paper_decisions
    if effective_history is not None:
        app.state.instrument_workspace = InstrumentWorkspaceService(
            history=effective_history,
            forecasts=price_forecasts,
            account_provider=account_store.get,
            marks_provider=lambda: mark_snapshot_provider(clock()).marks,
            valuation_provider=mark_snapshot_provider,
            live_feed=live_feed,
            decisions=paper_decisions,
            now=clock,
        )

    # The SPA JSON surface (Phase C) in both modes: a strict superset
    # of the M1 API, so a client that wants JSON has one source of
    # truth regardless of the render mode. Same api_ operation-id
    # discipline as the observability router.
    app.include_router(
        spa_router(),
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )

    # Venue-aware observed history is double-mounted like the live surface:
    # root for direct local clients and /api for the SPA. Both handlers read
    # the same injected service and optional feed from app.state.
    router = instrument_router()
    app.include_router(router)
    app.include_router(
        router,
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )

    # The live feed surface (iteration 0015 Phase C, ADR-0014 decision
    # 4): WebSocket + SSE stream, latest-state and connector health,
    # double-mounted like the demo router. Without an attached feed the
    # handlers answer 404 ("no live feed is attached"), so the
    # workstation is unchanged when no live watchlist is configured.
    live = live_router()
    app.include_router(live)
    app.include_router(
        live,
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )
    if live_feed is not None:
        app.state.live = live_feed
        app.router.lifespan_context = _feed_lifespan(live_feed)
    if prediction is not None:
        # The comparison surface (Phase E): the board renders the
        # feed's latest state; without an attached feed the handler
        # still answers "no live feed is attached" — never a board
        # fabricating numbers from an empty state.
        app.state.prediction = prediction

    if settings.legacy_ui:
        # RC1 rollback mode (ADR-0013 decision 6): the Jinja2 pages
        # mount exactly as they did in RC1, including the detail pages.
        for page in PAGES:
            app.add_api_route(
                page.route,
                _renderer(app, page),
                methods=["GET"],
                response_class=HTMLResponse,
            )
        _register_watchlist_forms(app)
        _register_experiment_detail(app)
        _register_kill_switch(app)
        _register_document_detail(app)
    else:
        # SPA mode (default): every legacy route 302s to its SPA
        # counterpart and the compiled bundle is served under /app.
        # The two write surfaces stay registered — the SPA calls the
        # same loopback POSTs behind the same origin guard.
        _register_spa_redirects(app)
        _register_watchlist_forms(app)
        _register_kill_switch(app)
        _register_spa_serving(app)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def _spa_redirect(route: str) -> Callable[[Request], RedirectResponse]:
    """302 to the SPA path superseding one legacy page (ADR-0013)."""
    target = LEGACY_TO_SPA[route]

    def redirect(request: Request) -> RedirectResponse:
        return RedirectResponse(target, status_code=302)

    return redirect


def _register_spa_redirects(app: FastAPI) -> None:
    """Legacy page routes -> SPA deep links (ADR-0013 decision 3).

    Every RC1 page route 302s to the /app path whose SPA screen
    supersedes it. The parameterized detail pages (experiment,
    document) redirect to their SPA listing — the SPA gains the real
    detail routes in Phase C, at which point these targets move.
    """

    for page in PAGES:
        app.add_api_route(
            page.route,
            _spa_redirect(page.route),
            methods=["GET"],
            response_class=RedirectResponse,
        )

    @app.get("/experiments/{experiment_id}", include_in_schema=False)
    def experiment_detail_redirect(request: Request, experiment_id: str) -> RedirectResponse:
        return RedirectResponse(LEGACY_TO_SPA["/experiments"], status_code=302)

    @app.get("/documents/{document_id}", include_in_schema=False)
    def document_detail_redirect(request: Request, document_id: str) -> RedirectResponse:
        return RedirectResponse(LEGACY_TO_SPA["/audit"], status_code=302)


def _register_spa_serving(app: FastAPI) -> None:
    """Serve the committed SPA bundle (ADR-0013 decision 2).

    ``/app/assets/*`` is the bundle's asset directory (vite ``base:
    "/app/"``); every other ``/app`` path falls through to
    ``index.html`` so react-router deep links work on refresh. The
    mount is skipped when the bundle directory is absent (StaticFiles
    refuses a missing directory) — the fallback then serves the
    instructive 503, never a blank page.
    """
    if SPA_ASSETS.is_dir():
        app.mount(
            "/app/assets",
            StaticFiles(directory=str(SPA_ASSETS)),
            name="app-assets",
        )
    else:
        # No bundle on disk (checkout predates the frontend build);
        # /app/assets 404s and the fallback below names the problem.
        pass

    @app.get("/app", include_in_schema=False)
    def spa_root(request: Request) -> Response:
        # The catch-all matches "/app/" (path=""), not "/app" — make
        # the bare path resolve so a bookmarked URL never 404s.
        return RedirectResponse("/app/", status_code=302)

    @app.get("/app/{path:path}", include_in_schema=False)
    def spa_fallback(request: Request, path: str) -> Response:
        if not SPA_INDEX.is_file():
            return HTMLResponse(_spa_missing_page(), status_code=503)
        if path in _BUNDLE_ROOT_FILES:
            file = SPA_DIR / path
            if file.is_file():
                return FileResponse(file)
        return HTMLResponse(SPA_INDEX.read_bytes())


def _register_watchlist_forms(app: FastAPI) -> None:
    @app.post("/watchlist/add", response_class=HTMLResponse)
    def watchlist_add(
        request: Request,
        symbol: str = Form(...),
        venue: str | None = Form(None),
    ) -> Response:
        refused = _guard_origin(app, request, "/watchlist", "watchlist")
        if refused is not None:
            return refused
        context = app.state.page_context
        if context.watchlist is None:
            return _error_page(app, request, "/watchlist", "no watchlist store is bound")
        try:
            selected_venue = venue.strip() if venue and venue.strip() else None
            if selected_venue is None:
                matches = [name for name, rows in context.markets.items() if symbol in rows]
                if len(matches) == 1:
                    selected_venue = matches[0]
            context.watchlist.add(symbol, venue=selected_venue)
        except WatchlistError as error:
            return _error_page(app, request, "/watchlist", str(error))
        return RedirectResponse("/watchlist", status_code=303)

    @app.post("/watchlist/remove", response_class=HTMLResponse)
    def watchlist_remove(
        request: Request,
        symbol: str = Form(...),
        venue: str | None = Form(None),
    ) -> Response:
        refused = _guard_origin(app, request, "/watchlist", "watchlist")
        if refused is not None:
            return refused
        context = app.state.page_context
        if context.watchlist is None:
            return _error_page(app, request, "/watchlist", "no watchlist store is bound")
        try:
            selected_venue = venue.strip() if venue and venue.strip() else None
            context.watchlist.remove(symbol, venue=selected_venue)
        except WatchlistError as error:
            return _error_page(app, request, "/watchlist", str(error))
        return RedirectResponse("/watchlist", status_code=303)


def _renderer(app: FastAPI, page: Page) -> Callable[[Request], HTMLResponse]:
    def render(request: Request) -> HTMLResponse:
        return _render_page(app, page, request, {})

    return render


def _error_page(app: FastAPI, request: Request, route: str, message: str) -> HTMLResponse:
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
                **_base_context(f"QuantMesh — Experiment {experiment.id}", context.account),
                "experiment": _experiment_view(experiment),
                "pin": pin,
                "pin_error": pin_error,
            },
        )


def _register_kill_switch(app: FastAPI) -> None:
    """POST /kill-switch: the global and per-venue kill switches
    (ADR-0011 decision 6, ADR-0012 decision 3, the second UI-owned
    write surface).

    The confirmation is part of the form itself: the submit must carry
    `action` in {engage, disarm} AND the literal `confirm=confirm`
    field — a hostile POST (non-form body, missing or wrong fields) is
    refused with a typed error page and the account is never touched.
    An optional `venue` field targets the per-venue map: a named venue
    flips only that venue's switch (disarm removes it — absence reads
    disarmed), leaving the global bit and every other venue untouched;
    a venue that is not a known `Venue` is refused with a typed error
    page. A successful flip replaces the injected account in both
    `app.state` and the page context, so the M1 JSON surface, every
    page and the kernel gate agree on the state. Enforcement lives in
    the accounting risk gate, not in any AI surface.
    """

    @app.post("/kill-switch", response_class=HTMLResponse)
    def kill_switch_post(
        request: Request,
        action: str | None = Form(default=None),
        confirm: str | None = Form(default=None),
        venue: str | None = Form(default=None),
    ) -> Response:
        refused = _guard_origin(app, request, "/kill-switch/control", "kill-switch")
        if refused is not None:
            return refused
        if action not in ("engage", "disarm") or confirm != "confirm":
            return _error_page(
                app,
                request,
                "/kill-switch/control",
                "kill-switch POST refused: expected a confirm form "
                "(action=engage|disarm and confirm=confirm)",
            )
        venue_enum = None
        if venue is not None:
            try:
                venue_enum = Venue(venue)
            except ValueError:
                return _error_page(
                    app,
                    request,
                    "/kill-switch/control",
                    f"kill-switch POST refused: unknown venue {venue!r}",
                )
        def flip(current: PaperAccount) -> PaperAccount:
            if venue_enum is None:
                return current.model_copy(update={"kill_switch": action == "engage"})
            kill_switches = dict(current.kill_switches)
            if action == "engage":
                kill_switches[venue_enum] = True
            else:
                kill_switches.pop(venue_enum, None)
            return current.model_copy(update={"kill_switches": kill_switches})

        store: PaperAccountStore = app.state.account_store
        store.update(flip)
        return RedirectResponse("/kill-switch/control", status_code=303)


def _register_document_detail(app: FastAPI) -> None:
    """GET /documents/{id}: one document record, the browse target of
    the M8 `document:` citations on the audit page.

    Read-only, outside the page registry (a parameterized route does
    not fit the pinned route -> template -> provider triple). An
    unbound index or an unknown id renders a typed error page, never a
    crash.
    """

    @app.get("/documents/{document_id}", response_class=HTMLResponse)
    def document_detail(request: Request, document_id: str) -> HTMLResponse:
        context = app.state.page_context
        if context.documents is None:
            return _error_page(app, request, "/audit", "no document index is bound")
        try:
            document = context.documents.get(document_id)
        except ValueError as error:
            return _error_page(app, request, "/audit", str(error))
        return app.state.templates.TemplateResponse(
            request=request,
            name="document_detail.html",
            context={
                **_base_context(f"QuantMesh — Document {document.id}", context.account),
                "document": {
                    "id": document.id,
                    "kind": document.kind,
                    "source_path": document.source_path,
                    "ingested_at": document.ingested_at.isoformat(),
                    "content": document.content,
                },
            },
        )


def main(argv: list[str] | None = None) -> None:
    """quantmesh-workstation: serve the workstation over loopback.

    Binds a fresh empty paper account as the safe local bootstrap;
    operators who want their real account/journal surfaces wired start
    the app programmatically with `create_workstation_app(account=...)`.
    With ``--demo`` the labeled deterministic scenario is served
    instead: `--demo-root` picks the demo root (default
    ``~/.quantmesh/demo``), `--seed` overrides the scenario seed, and
    the app exposes ``/api/demo/status`` plus the marker-guarded reset.
    ``--live`` attaches the live read-only market feed over the public
    Hyperliquid WS (ADR-0014): the watchlist is
    ``QUANTMESH_LIVE_WATCHLIST`` (comma-separated perp coins), the
    replay lake lives under the operator's data root, and the cockpit
    renders real, freshness-labeled quotes. When
    ``QUANTMESH_PREDICTION_WATCHLIST`` is also set (Phase E), the
    prediction comparison screen attaches with read-only Polymarket
    and Kalshi supervisors over their public WebSockets — every venue
    stays read-only market data, never order paths. When
    ``QUANTMESH_MOOMOO_WATCHLIST`` is set (Phase F), the cockpit
    attaches the Moomoo OpenD surface: read-only polls of a local
    OpenD daemon (``US.AAPL``-style codes), whose venue timestamps
    drive the real/stale labels — a quiet or absent daemon renders
    honestly unavailable, never fabricated real-time. ``--demo`` and
    ``--live`` are mutually exclusive — the demo session stays the
    labeled deterministic runtime, live stays labeled real.
    """
    import argparse

    import uvicorn  # deferred: only the console script touches it

    parser = argparse.ArgumentParser(prog="quantmesh-workstation")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="serve the labeled deterministic demo scenario instead of an empty paper account",
    )
    parser.add_argument(
        "--demo-root",
        type=Path,
        default=None,
        help="demo root (default: settings.demo_root, ~/.quantmesh/demo)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="demo scenario seed (default: settings.demo_seed)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "attach the live read-only market feed "
            "(QUANTMESH_LIVE_WATCHLIST = comma-separated perp coins; "
            "QUANTMESH_PREDICTION_WATCHLIST adds the prediction board)"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="loopback port override (default: QUANTMESH_WORKSTATION_PORT or 8765)",
    )
    args = parser.parse_args(argv)

    host = settings.workstation_host
    if not _is_loopback(host):
        raise WorkstationConfigError(
            f"workstation host must be loopback, got {host!r} "
            "(non-loopback binds are refused at construction)"
        )
    port = settings.workstation_port if args.port is None else args.port
    if not 1 <= port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.demo and args.live:
        raise SystemExit(
            "--demo and --live are mutually exclusive: the demo runtime is the "
            "labeled deterministic session"
        )
    if args.demo:
        from quantmesh.demo.runtime import create_demo_app

        app = create_demo_app(
            root=args.demo_root,
            seed=args.seed,
            host=host,
        )
    else:
        account = PaperAccount(cash=100_000.0)
        if args.live:
            from quantmesh.data.lake import Lake
            from quantmesh.execution.journal import OrderJournal
            from quantmesh.instruments.forecast import PriceForecastRegistry
            from quantmesh.instruments.history import HistoryService
            from quantmesh.instruments.live_history import discover_history_bindings
            from quantmesh.instruments.proposals import ProposalLedger
            from quantmesh.live.buffer import LiveBuffer
            from quantmesh.live.feed import LiveFeed
            from quantmesh.live.hyperliquid import (
                HyperliquidVenueSupervisor,
                LiveHyperliquidTransport,
            )

            watchlist = [
                coin.strip().upper() for coin in settings.live_watchlist.split(",") if coin.strip()
            ]
            if not watchlist:
                raise SystemExit(
                    "--live requires a watchlist: set QUANTMESH_LIVE_WATCHLIST "
                    "(e.g. BTC,ETH,SOL,HYPE)"
                )
            replay = LiveBuffer(root=settings.lake_root)
            account_snapshot = PaperAccountFile(settings.orders_dir)
            account = account_snapshot.load_or_create(account)
            journal = OrderJournal(settings.orders_dir)
            recovered_account = recover_account_from_journal(account, journal.all())
            if recovered_account != account:
                account_snapshot.save(recovered_account)
                account = recovered_account
            feed = LiveFeed(lake=replay)
            supervisor = HyperliquidVenueSupervisor(
                LiveHyperliquidTransport(settings.hyperliquid_ws_url)
            )
            supervisor.subscribe(watchlist)
            feed.attach(supervisor)
            prediction = None
            if settings.prediction_watchlist:
                # The prediction comparison surface (Phase E): the board
                # parses the operator's event pairs; each configured
                # venue gets a read-only supervisor over its public WS,
                # with the REST book boundaries as resync sources (the
                # Polymarket CLOB SDK is keyless by construction and the
                # Kalshi transport pins the public host). A venue with
                # no pairs is not attached at all — no idle sockets, no
                # fabricated health rows for an unconfigured venue.
                from quantmesh.kalshi.transport import HttpxKalshiTransport
                from quantmesh.live.kalshi import (
                    KalshiOrderbookSource,
                    KalshiVenueSupervisor,
                )
                from quantmesh.live.polymarket import (
                    ClobBookSource,
                    PolymarketVenueSupervisor,
                )
                from quantmesh.live.prediction import (
                    PredictionBoard,
                    parse_prediction_watchlist,
                )
                from quantmesh.polymarket.transport import SdkPolyTransport

                board = PredictionBoard(parse_prediction_watchlist(settings.prediction_watchlist))
                watchlists = board.venues()
                pm_watchlist = watchlists[Venue.POLYMARKET]
                if pm_watchlist:
                    pm = PolymarketVenueSupervisor(
                        LiveHyperliquidTransport(settings.polymarket_ws_url),
                        book_source=ClobBookSource(SdkPolyTransport()),
                    )
                    pm.subscribe(pm_watchlist)
                    feed.attach(pm)
                ks_watchlist = watchlists[Venue.KALSHI]
                if ks_watchlist:
                    ks = KalshiVenueSupervisor(
                        LiveHyperliquidTransport(settings.kalshi_ws_url),
                        book_source=KalshiOrderbookSource(HttpxKalshiTransport()),
                    )
                    ks.subscribe(ks_watchlist)
                    feed.attach(ks)
                prediction = board
            if settings.moomoo_watchlist:
                # The Moomoo OpenD surface (Phase F): read-only polls of
                # a local OpenD daemon for the operator's equity
                # watchlist. Availability is decided by the daemon
                # itself — a probe failure keeps the surface honestly
                # unavailable (the pump's disconnect path; stale venue
                # clocks are blocked at dispatch), never fabricated.
                # Last price + volume only: no bid/ask on the wire, so
                # no QUOTE is emitted and paper orders stay impossible
                # for these instruments by construction.
                from quantmesh.live.moomoo import (
                    MoomooVenueSupervisor,
                    MoomooVenueTransport,
                )
                from quantmesh.moomoo.opend import MoomooOpenDClient

                symbols = [s.strip() for s in settings.moomoo_watchlist.split(",") if s.strip()]
                moomoo = MoomooVenueSupervisor(
                    MoomooVenueTransport(
                        MoomooOpenDClient.from_settings(settings),
                        poll_interval=timedelta(seconds=settings.moomoo_poll_interval_s),
                    ),
                    market=settings.moomoo_market,
                )
                moomoo.subscribe(symbols)
                feed.attach(moomoo)
            bindings = discover_history_bindings(settings.lake_root)
            history = (
                HistoryService(bindings, dataset_loader=Lake(settings.lake_root).dataset)
                if bindings
                else None
            )
            app = create_workstation_app(
                account=account,
                history=history,
                price_forecasts=PriceForecastRegistry(
                    lake_root=settings.lake_root,
                    bindings=bindings,
                ),
                proposal_ledger=ProposalLedger(settings.orders_dir / "proposals"),
                journal=journal,
                account_sink=account_snapshot.save,
                live_feed=feed,
                prediction=prediction,
                host=host,
            )
        else:
            app = create_workstation_app(account=account, host=host)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
