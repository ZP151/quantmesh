"""M9 workstation server shell (issue #51, Phase A).

The workstation app is the M1 read-only API plus server-rendered Jinja2
screens: a route -> template -> provider registry pinned by test, a
loopback-only bind refused at construction, and the accessibility
posture (skip link, landmarks, visible focus) rendered from the first
screen on.
"""

import dataclasses
import re
import sys
import types
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from quantmesh import __version__
from quantmesh.ai.decisions import DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.retrieval import Citation, DocumentIndex
from quantmesh.api import workstation
from quantmesh.api.app import create_app
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.api.workstation import (
    LEGACY_TO_SPA,
    PAGES,
    PageContext,
    WorkstationConfigError,
    create_workstation_app,
)
from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.events.forecast import (
    ForecastMarket,
    ForecastObservation,
    ForecastReport,
    ForecastReportRegistry,
    ForecastWindowSpec,
    forecast_report_id,
    run_forecast,
    run_forecast_report,
)
from quantmesh.events.mapping import (
    MAPPINGS_FILE,
    EvidenceKind,
    MappingEvidence,
    MappingLedger,
    MappingRecord,
    MappingStatus,
)
from quantmesh.events.models import EventMarket, EventVenue, Outcome, ResolutionRule
from quantmesh.execution.accounting import (
    FeeModel,
    PaperAccount,
    PaperMatcher,
    RiskLimits,
)
from quantmesh.execution.journal import OrderJournal
from quantmesh.hyperliquid.risk import RiskLimits as HyperliquidRiskLimits
from quantmesh.ops.enablement import GATE_TEXT, ApprovalLedger
from quantmesh.research.drift import (
    AlertLedger,
    AlertRecord,
    PromotionLedger,
    PromotionRecord,
    alert_id,
    promotion_id,
)
from quantmesh.research.experiments import Experiment, ExperimentRegistry, experiment_id
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    report_id,
)
from quantmesh.settings import settings

INSTRUMENT = Instrument(symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY)
POSITION_KEY = "internal:AAPL"
NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
MARKS = {POSITION_KEY: 95.0}


def make_request(side: Side, quantity: float, limit_price: float | None = None) -> OrderRequest:
    return OrderRequest(
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
    )


def make_quote(*, bid: float = 99.0, ask: float = 100.0) -> Quote:
    return Quote(instrument=INSTRUMENT, timestamp=NOW, bid=bid, ask=ask, volume=100)


def sample_account() -> PaperAccount:
    """Buy 10 @ 100, sell 4 @ 110, leave a non-crossed limit buy working."""
    account = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    account = account.submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account
    account = account.submit(
        make_request(Side.SELL, 4), make_quote(bid=110.0, ask=111.0), now=NOW
    ).account
    account = account.submit(
        make_request(Side.BUY, 10, limit_price=99.0), make_quote(), now=NOW
    ).account
    return account


@pytest.fixture(autouse=True)
def _legacy_ui(monkeypatch) -> None:
    """The rendering tests pin the RC1 Jinja2 pages, so the suite runs
    in legacy mode (ADR-0013 decision 6, the rollback switch). The SPA
    surface tests override to the default mode explicitly. Restored by
    monkeypatch after every test."""
    monkeypatch.setattr(workstation.settings, "legacy_ui", True)


def client(
    account: PaperAccount | None = None,
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
) -> TestClient:
    return TestClient(
        create_workstation_app(
            account=account or sample_account(),
            marks=marks,
            markets=markets,
            watchlist=watchlist,
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
    )


COMMIT = "a" * 40
CRYPTO = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
SPEC = WalkForwardSpec(train_bars=10, test_bars=5, step_bars=10)
COSTS = CostModel(fee_bps=5, half_spread_bps=2, slippage_bps=1)
UNIVERSE = [UniverseMember(venue=Venue.INTERNAL, symbol="AAPL")]


def _bars(count: int = 3) -> list[Bar]:
    return [
        Bar(
            instrument=CRYPTO,
            timestamp=NOW - timedelta(hours=1) + timedelta(minutes=index),
            interval="1m",
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=10.0 + index,
        )
        for index in range(count)
    ]


def pinned_lake(tmp_path) -> Path:
    lake_root = tmp_path / "lake"
    Lake(lake_root).write_bars("algo", _bars())
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    return lake_root


def experiment_registry(tmp_path) -> tuple[ExperimentRegistry, Path]:
    """A real registry: lake-pinned records through the record() gate."""
    lake_root = pinned_lake(tmp_path)
    registry = ExperimentRegistry(root=tmp_path / "experiments", lake_root=lake_root)
    registry.record(
        dataset="algo",
        revision=1,
        commit=COMMIT,
        parameters={"lookback": 20, "rebalance": "daily"},
        metrics={"sharpe": 1.5, "max_drawdown": -0.12, "optimized": True, "note": None},
    )
    return registry, lake_root


def make_report(
    *, strategy: str, interval: str = "1d", evidence=None, metrics=None
) -> StrategyReport:
    report_id_value = report_id(
        dataset="algo",
        revision=1,
        commit=COMMIT,
        strategy=strategy,
        interval=interval,
        universe=UNIVERSE,
        window_spec=SPEC,
        costs=COSTS,
    )
    return StrategyReport(
        id=report_id_value,
        dataset="algo",
        revision=1,
        commit=COMMIT,
        strategy=strategy,
        interval=interval,
        universe=UNIVERSE,
        window_spec=SPEC,
        costs=COSTS,
        created_at=NOW,
        metrics=metrics or {},
        evidence=evidence or {},
    )


def promotion_setup(
    tmp_path, *, kill_switch: bool = False
) -> tuple[PromotionLedger, ReportRegistry]:
    """A promotion with its full evidence bundle, hand-written as JSONL."""
    benchmark = make_report(strategy="momentum", metrics={"sharpe": 1.4})
    ablation = make_report(strategy="mean_reversion", metrics={"sharpe": 0.9})
    # A different interval gives the OOS report a distinct setup — the
    # registry refuses two reports sharing an id.
    oos = make_report(strategy="momentum", interval="1h", evidence={"windows_oos": True})
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    (reports_root / "reports.jsonl").write_text(
        "\n".join(report.model_dump_json() for report in (benchmark, ablation, oos)) + "\n",
        encoding="utf-8",
    )
    promotion = PromotionRecord(
        id=promotion_id(
            signal_name="momentum_plus",
            benchmark_report_ids=[benchmark.id],
            ablation_report_ids=[ablation.id],
            oos_report_id=oos.id,
            kill_switch=kill_switch,
        ),
        signal_name="momentum_plus",
        benchmark_report_ids=[benchmark.id],
        ablation_report_ids=[ablation.id],
        oos_report_id=oos.id,
        kill_switch=kill_switch,
        promoted_at=NOW,
    )
    promotions_root = tmp_path / "promotions"
    promotions_root.mkdir()
    (promotions_root / "promotions.jsonl").write_text(
        promotion.model_dump_json() + "\n", encoding="utf-8"
    )
    return PromotionLedger(root=promotions_root), ReportRegistry(root=reports_root)


class TestConstruction:
    def test_home_renders_as_html(self) -> None:
        response = client().get("/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        html = response.text
        assert "QuantMesh" in html
        assert "Overview" in html
        assert "Skip to main content" in html

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.1", "example.com", "::"])
    def test_non_loopback_host_refused(self, host: str) -> None:
        with pytest.raises(WorkstationConfigError, match="loopback"):
            create_workstation_app(account=sample_account(), host=host)

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.99.99.99"])
    def test_loopback_hosts_accepted(self, host: str) -> None:
        app = create_workstation_app(account=sample_account(), host=host)
        assert TestClient(app).get("/").status_code == 200

    def test_settings_host_applies_when_not_overridden(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "workstation_host", "0.0.0.0")
        with pytest.raises(WorkstationConfigError, match="loopback"):
            create_workstation_app(account=sample_account())


class TestPageRegistry:
    def test_routes_are_unique_and_registered(self) -> None:
        routes = [page.route for page in PAGES]
        assert len(routes) == len(set(routes))
        # APIRoute only: the M1 kernel API is registered through
        # include_router (FastAPI >= 0.14x wraps those in a lazy
        # _IncludedRouter entry) while the page routes are added
        # directly and stay plain APIRoutes.
        app_routes = {route.path for route in client().app.routes if isinstance(route, APIRoute)}
        for route in routes:
            assert route in app_routes

    def test_every_page_registered_as_get(self) -> None:
        app = client().app
        paths = {page.route: page for page in PAGES}
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path in paths:
                assert "GET" in route.methods

    def test_every_template_loads(self) -> None:
        templates = client().app.state.templates
        for page in PAGES:
            assert templates.env.get_template(page.template) is not None

    def test_autoescape_is_on(self) -> None:
        env = client().app.state.templates.env
        # select_autoescape: a callable that must escape html templates.
        assert callable(env.autoescape)
        assert env.autoescape("home.html") is True

    def test_every_page_renders_through_its_provider(self) -> None:
        app_client = client()
        app = app_client.app
        context = app.state.page_context
        assert isinstance(context, PageContext)
        for page in PAGES:
            response = app_client.get(page.route)
            assert response.status_code == 200, page.route
            assert page.title in response.text


class TestLayoutAndAccessibility:
    def test_landmarks_and_skip_link(self) -> None:
        html = client().get("/").text

        assert 'href="#main"' in html
        assert '<main id="main">' in html
        assert '<nav aria-label="Primary">' in html
        assert "<header>" in html
        assert "<footer>" in html

    def test_account_values_rendered(self) -> None:
        account = sample_account()
        html = client(account, marks=dict(MARKS)).get("/").text

        assert f"{account.cash:.2f}" in html
        assert f"{account.starting_cash:.2f}" in html
        assert f"{account.equity(MARKS):.2f}" in html

    def test_kill_switch_state_rendered(self) -> None:
        html = client().get("/").text
        assert 'data-kill-switch="false"' in html
        assert "disarmed" in html

        engaged = sample_account().model_copy(update={"kill_switch": True})
        html = client(engaged).get("/").text
        assert 'data-kill-switch="true"' in html
        assert "ENGAGED" in html

    def test_marks_rendered(self) -> None:
        html = client(marks=dict(MARKS)).get("/").text
        assert "internal:AAPL" in html
        assert "95.0000" in html

    def test_missing_marks_notice_rendered(self) -> None:
        html = client(marks={}).get("/").text
        assert "Positions without a mark" in html
        assert "internal:AAPL" in html

    def test_markup_is_escaped(self) -> None:
        evil = "<img src=x onerror=alert(1)>"
        html = client(marks={evil: 5.0}).get("/").text

        assert "<img src=x" not in html
        assert "&lt;img" in html

    def test_static_css_served_locally(self) -> None:
        response = client().get("/static/style.css")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")
        assert ":focus-visible" in response.text


class TestM1SurfaceStillServed:
    def test_json_endpoints_match_create_app(self) -> None:
        account = sample_account()
        marks = dict(MARKS)
        plain = TestClient(create_app(account=account, marks=marks))
        station = TestClient(create_workstation_app(account=account, marks=marks))

        for path in ("/health", "/account", "/positions", "/orders", "/pnl", "/kill-switch"):
            assert station.get(path).status_code == 200, path
            assert station.get(path).json() == plain.get(path).json()

    def test_version_and_app_name_in_footer(self) -> None:
        html = client().get("/").text
        assert __version__ in html
        assert settings.app_name in html


class TestSpaSurface:
    """ADR-0013 Phase A: the default operator surface is the React SPA.

    Every legacy route 302s to its /app counterpart, the committed
    bundle is served under /app (deep links fall through to
    index.html), the kernel API is double-mounted at /api with unique
    operation ids, a missing bundle serves an instructive 503, and the
    two write surfaces stay registered behind the same origin guard.
    """

    @pytest.fixture
    def spa_client(self, monkeypatch) -> TestClient:
        """A default-mode (SPA) client: overrides the autouse legacy pin."""
        monkeypatch.setattr(workstation.settings, "legacy_ui", False)
        return client()

    def test_legacy_routes_redirect_to_their_spa_paths(self, spa_client) -> None:
        for legacy, spa in LEGACY_TO_SPA.items():
            response = spa_client.get(legacy, follow_redirects=False)
            assert response.status_code == 302, legacy
            assert response.headers["location"] == spa, legacy

    def test_detail_routes_redirect_to_spa_listings(self, spa_client) -> None:
        for path in ("/experiments/anything", "/documents/anything"):
            response = spa_client.get(path, follow_redirects=False)
            assert response.status_code == 302, path
            assert response.headers["location"].startswith("/app/"), path

    def test_spa_root_and_deep_links_serve_the_bundle(self, spa_client) -> None:
        for path in ("/app/", "/app/markets", "/app/trading/orders"):
            response = spa_client.get(path)
            assert response.status_code == 200, path
            assert "QuantMesh" in response.text

    def test_bare_app_path_redirects_to_trailing_slash(self, spa_client) -> None:
        response = spa_client.get("/app", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/app/"

    def test_kernel_api_served_under_api_prefix(self, spa_client) -> None:
        positions = spa_client.get("/api/positions").json()
        assert len(positions) == 1
        assert positions[0]["key"] == POSITION_KEY
        assert spa_client.get("/api/orders").status_code == 200
        assert spa_client.get("/api/kill-switch").status_code == 200

    def test_openapi_operation_ids_are_unique_across_mounts(self, spa_client) -> None:
        paths = spa_client.get("/openapi.json").json()["paths"]
        ids = [
            operation["operationId"]
            for path in paths.values()
            for operation in path.values()
            if "operationId" in operation
        ]
        assert len(ids) == len(set(ids)), "duplicate operation ids in /openapi.json"
        assert any(identifier.startswith("api_") for identifier in ids)

    def test_missing_bundle_serves_instructive_503(self, spa_client, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(workstation, "SPA_INDEX", tmp_path / "absent" / "index.html")

        response = spa_client.get("/app/")

        assert response.status_code == 503
        assert "QUANTMESH_LEGACY_UI" in response.text
        assert "build_frontend" in response.text

    def test_traversal_probes_fall_through_to_the_bundle(self, spa_client) -> None:
        for url in (
            "/app/..%2f..%2fpyproject.toml",
            "/app/%2e%2e/%2e%2e/pyproject.toml",
            "/app/..%2F..%2Fsrc%2Fquantmesh%2Fsettings.py",
        ):
            response = spa_client.get(url)
            assert response.status_code == 200, url
            assert "<!doctype html>" in response.text

    def test_assets_and_root_bundle_files_served(self, spa_client) -> None:
        assert spa_client.get("/app/favicon.svg").status_code == 200
        assert spa_client.get("/app/icons.svg").status_code == 200
        # Every hashed asset resolves through the mount.
        index = spa_client.get("/app/").text
        match = re.search(r'src="(/app/assets/[^"]+\.js)"', index)
        assert match is not None
        assert spa_client.get(match.group(1)).status_code == 200

    def test_write_surfaces_stay_registered_in_spa_mode(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(workstation.settings, "legacy_ui", False)
        watched = WatchlistStore(root=tmp_path / "watchlists")
        app_client = client(watchlist=watched)

        response = app_client.post("/watchlist/add", data={"symbol": "SOL"}, follow_redirects=False)
        assert response.status_code == 303
        assert [record.symbol for record in watched.all()] == ["SOL"]

        response = app_client.post(
            "/kill-switch",
            data={"action": "engage", "confirm": "confirm"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        # The JSON surface agrees with the flipped account.
        assert app_client.get("/api/kill-switch").json()["kill_switch"] is True
        assert app_client.get("/api/account").json()["kill_switch"] is True


class TestConsoleScript:
    def test_main_refuses_non_loopback_before_uvicorn(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "workstation_host", "0.0.0.0")
        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda **kw: None))

        with pytest.raises(WorkstationConfigError, match="loopback"):
            workstation.main([])

    def test_main_serves_on_loopback_with_settings_bind(self, monkeypatch) -> None:
        calls: dict = {}

        def fake_run(*args, **kwargs) -> None:
            calls.update(kwargs)

        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr(settings, "workstation_host", "127.0.0.1")
        monkeypatch.setattr(settings, "workstation_port", 9876)

        workstation.main([])

        assert calls["host"] == "127.0.0.1"
        assert calls["port"] == 9876

    def test_main_allows_a_loopback_operator_port_override(self, monkeypatch) -> None:
        calls: dict = {}

        def fake_run(*args, **kwargs) -> None:
            calls.update(kwargs)

        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr(settings, "workstation_host", "127.0.0.1")
        monkeypatch.setattr(settings, "workstation_port", 8765)

        workstation.main(["--port", "8766"])

        assert calls["host"] == "127.0.0.1"
        assert calls["port"] == 8766

    def test_main_live_wires_workspace_forecasts_and_paper_services(
        self, tmp_path, monkeypatch
    ) -> None:
        calls: dict = {}

        def fake_run(app, *args, **kwargs) -> None:  # noqa: ANN001
            calls["app"] = app
            calls.update(kwargs)

        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr(settings, "workstation_host", "127.0.0.1")
        monkeypatch.setattr(settings, "workstation_port", 8767)
        monkeypatch.setattr(settings, "live_watchlist", "BTC")
        monkeypatch.setattr(settings, "prediction_watchlist", "")
        monkeypatch.setattr(settings, "moomoo_watchlist", "")
        monkeypatch.setattr(settings, "lake_root", tmp_path / "lake")
        monkeypatch.setattr(settings, "orders_dir", tmp_path / "orders")

        workstation.main(["--live"])

        app = calls["app"]
        assert app.state.history is not None
        assert app.state.instrument_workspace is not None
        assert app.state.price_forecasts is not None
        assert app.state.paper_decisions is not None
        assert app.state.proposal_service is app.state.paper_decisions
        assert app.state.live.replay_buffer is not None
        assert calls["host"] == "127.0.0.1"
        assert calls["port"] == 8767
        app.state.live.replay_buffer.close()

        # Policy state survives restart, but derived sequence state cannot be
        # invented without matching durable journal orders.
        restored = app.state.account.model_copy(update={"kill_switch": True})
        app.state.account_store.replace(restored)
        workstation.main(["--live"])
        restarted = calls["app"]
        assert restarted.state.account.kill_switch is True
        assert restarted.state.account.order_sequence == 0
        restarted.state.live.replay_buffer.close()

    def test_main_refuses_an_out_of_range_port_override(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda **kw: None))

        with pytest.raises(SystemExit, match="2"):
            workstation.main(["--port", "65536"])


class TestPhaseBScreens:
    """Phase B screens (issue #52): overview venue cards + watchlist
    snapshot, cross-venue instruments, and the watchlist write surface.

    The watchlist is the one UI-owned write surface (ADR-0011 decision
    3): add/remove round-trip through the form endpoints, duplicates and
    malformed symbols refused with a typed error page (role="alert"),
    hostile symbols escaped on render, and an unbound store refusing
    writes fail-closed instead of crashing.
    """

    MARKETS = {
        "hyperliquid": {"BTC": 65_000.0, "ETH": 3_200.0},
        "moomoo": {"AAPL": 210.0, "BTC": 65_010.0},
    }

    @staticmethod
    def watched(tmp_path) -> WatchlistStore:
        return WatchlistStore(root=tmp_path / "watchlists")

    def test_overview_venue_cards_sorted(self, tmp_path) -> None:
        html = client(markets=dict(self.MARKETS), watchlist=self.watched(tmp_path)).get("/").text

        assert "<h3>hyperliquid (2 instruments)</h3>" in html
        assert "<h3>moomoo (2 instruments)</h3>" in html
        assert html.index("hyperliquid") < html.index("moomoo")
        # Per-venue instruments sorted: BTC before ETH, AAPL before BTC.
        assert html.index(">BTC<") < html.index(">ETH<")
        assert html.index(">AAPL<") < html.index(">BTC<", html.index("moomoo"))

    def test_overview_renders_venue_marks(self, tmp_path) -> None:
        html = client(markets=dict(self.MARKETS), watchlist=self.watched(tmp_path)).get("/").text

        assert "65000.0000" in html
        assert "65010.0000" in html
        assert "3200.0000" in html
        assert "210.0000" in html

    def test_overview_watchlist_snapshot_sorted_with_marks(self, tmp_path) -> None:
        watched = self.watched(tmp_path)
        watched.add("SOL", now=NOW)
        watched.add("ETH", now=NOW)
        html = client(markets=dict(self.MARKETS), watchlist=watched).get("/").text

        # Legacy unscoped rows remain readable but never guess a venue/mark.
        assert html.index(">ETH<") < html.index(">SOL<")
        assert "no mark" in html

    def test_watchlist_json_preserves_same_symbol_venue_identity(self, tmp_path) -> None:
        watched = self.watched(tmp_path)
        watched.add("BTC", venue="hyperliquid", now=NOW)
        watched.add("BTC", venue="moomoo", now=NOW)
        app_client = client(markets=dict(self.MARKETS), watchlist=watched)

        assert app_client.get("/api/watchlist").json()["entries"] == [
            {"venue": "hyperliquid", "symbol": "BTC", "mark": 65_000.0},
            {"venue": "moomoo", "symbol": "BTC", "mark": 65_010.0},
        ]

    def test_overview_empty_watchlist_prompt(self, tmp_path) -> None:
        html = client(markets=dict(self.MARKETS), watchlist=self.watched(tmp_path)).get("/").text

        assert "Watchlist is empty" in html

    def test_instruments_cross_venue_sorted(self, tmp_path) -> None:
        html = (
            client(markets=dict(self.MARKETS), watchlist=self.watched(tmp_path))
            .get("/instruments")
            .text
        )

        # Venue-major, symbol-minor: hyperliquid BTC, ETH, then moomoo AAPL, BTC.
        assert html.index(">hyperliquid<") < html.index(">moomoo<")
        assert html.index(">BTC<") < html.index(">ETH<")
        assert html.index(">AAPL<") > html.index(">ETH<")
        assert "65000.0000" in html and "65010.0000" in html

    def test_watchlist_empty_state(self, tmp_path) -> None:
        html = client(watchlist=self.watched(tmp_path)).get("/watchlist").text

        assert "The watchlist is empty." in html

    def test_add_via_form_redirects_and_persists(self, tmp_path) -> None:
        watched = self.watched(tmp_path)
        app_client = client(markets=dict(self.MARKETS), watchlist=watched)

        response = app_client.post("/watchlist/add", data={"symbol": "ETH"}, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/watchlist"
        assert [(record.venue.value, record.symbol) for record in watched.all()] == [
            ("hyperliquid", "ETH")
        ]
        html = app_client.get("/watchlist").text
        assert ">ETH<" in html
        assert "3200.0000" in html

    def test_duplicate_add_renders_error_page(self, tmp_path) -> None:
        watched = self.watched(tmp_path)
        watched.add("ETH", now=NOW)
        app_client = client(watchlist=watched)

        response = app_client.post("/watchlist/add", data={"symbol": "ETH"})

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "is already on the watchlist" in response.text
        assert "ETH" in response.text
        assert len(watched.all()) == 1

    def test_invalid_add_renders_error_page_and_writes_nothing(self, tmp_path) -> None:
        watched = self.watched(tmp_path)
        app_client = client(watchlist=watched)

        response = app_client.post("/watchlist/add", data={"symbol": "   "})

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "cannot add" in response.text
        assert watched.all() == []

    def test_remove_via_form_redirects_and_gone(self, tmp_path) -> None:
        watched = self.watched(tmp_path)
        watched.add("ETH", now=NOW)
        app_client = client(watchlist=watched)

        response = app_client.post(
            "/watchlist/remove", data={"symbol": "ETH"}, follow_redirects=False
        )

        assert response.status_code == 303
        assert watched.all() == []
        assert "The watchlist is empty." in app_client.get("/watchlist").text

    def test_remove_unknown_renders_error_page(self, tmp_path) -> None:
        app_client = client(watchlist=self.watched(tmp_path))

        response = app_client.post("/watchlist/remove", data={"symbol": "BTC"})

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "is not on the watchlist" in response.text
        assert "BTC" in response.text

    def test_unbound_watchlist_refuses_writes_fail_closed(self, tmp_path) -> None:
        app_client = client(watchlist=self.watched(tmp_path))
        app_client.app.state.page_context = dataclasses.replace(
            app_client.app.state.page_context, watchlist=None
        )

        response = app_client.post("/watchlist/add", data={"symbol": "ETH"})

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "no watchlist store is bound" in response.text
        assert "The watchlist is empty." in app_client.get("/watchlist").text

    def test_hostile_symbol_escaped_on_render(self, tmp_path) -> None:
        app_client = client(watchlist=self.watched(tmp_path))

        response = app_client.post(
            "/watchlist/add", data={"symbol": "<b>bad</b>"}, follow_redirects=False
        )
        assert response.status_code == 303

        html = app_client.get("/watchlist").text
        assert "&lt;b&gt;bad&lt;/b&gt;" in html
        assert "<b>bad</b>" not in html


class TestPhaseCResearchScreens:
    """Phase C screens (issue #53): experiment comparison and strategy
    promotion.

    The research registries are injected read surfaces (ADR-0011
    decision 4): unbound registries render typed empty states, a
    promotion evidence id that cannot resolve renders a typed "missing
    evidence" state, and the experiment detail page links its lake pin
    (with a typed state when the pin is stale or the lake is gone).
    """

    def test_experiments_page_renders_records_side_by_side(self, tmp_path) -> None:
        registry, _ = experiment_registry(tmp_path)
        recorded = registry.all()[0]

        html = client(experiments=registry).get("/experiments").text

        assert recorded.id in html
        assert "algo" in html
        assert "lookback=20" in html
        assert "rebalance=daily" in html
        assert "sharpe=1.5" in html
        assert "max_drawdown=-0.12" in html
        assert "optimized=true" in html
        assert "note=—" in html
        assert "1 experiment record." in html

    def test_experiments_newest_first(self, tmp_path) -> None:
        first = Experiment(
            id=experiment_id(
                dataset="algo", revision=1, commit=COMMIT, parameters={"lookback": 10}
            ),
            dataset="algo",
            revision=1,
            commit=COMMIT,
            parameters={"lookback": 10},
            metrics={"sharpe": 1.0},
            created_at=NOW,
        )
        second = Experiment(
            id=experiment_id(
                dataset="algo", revision=1, commit=COMMIT, parameters={"lookback": 20}
            ),
            dataset="algo",
            revision=1,
            commit=COMMIT,
            parameters={"lookback": 20},
            metrics={"sharpe": 1.5},
            created_at=NOW + timedelta(hours=1),
        )
        root = tmp_path / "experiments"
        root.mkdir()
        (root / "experiments.jsonl").write_text(
            first.model_dump_json() + "\n" + second.model_dump_json() + "\n",
            encoding="utf-8",
        )

        html = client(experiments=ExperimentRegistry(root=root)).get("/experiments").text

        assert html.index(f">{second.id}<") < html.index(f">{first.id}<")

    def test_experiment_detail_renders_record_and_lake_pin(self, tmp_path) -> None:
        registry, _ = experiment_registry(tmp_path)
        recorded = registry.all()[0]

        html = client(experiments=registry).get(f"/experiments/{recorded.id}").text

        assert recorded.id in html
        assert "lookback=20" in html
        assert "Lake pin" in html
        assert '<th scope="row">Manifest revision</th><td>1</td>' in html
        assert '<th scope="row">Series</th><td>1</td>' in html

    def test_experiment_detail_stale_pin_renders_typed_state(self, tmp_path) -> None:
        registry, lake_root = experiment_registry(tmp_path)
        recorded = registry.all()[0]
        # Advance the manifest: the pinned revision no longer describes
        # the data on disk, so the pin refuses to resolve.
        ManifestWriter(lake_root).generate("algo", source="fixture", license="test")

        html = client(experiments=registry).get(f"/experiments/{recorded.id}").text

        assert "Lake pin unavailable" in html
        assert 'role="alert"' in html
        assert "lookback=20" in html  # the record itself still renders

    def test_experiment_detail_unknown_id_renders_error_page(self, tmp_path) -> None:
        registry, _ = experiment_registry(tmp_path)

        html = client(experiments=registry).get("/experiments/ffffffffffffffff").text

        assert 'role="alert"' in html
        assert "no experiment recorded" in html

    def test_experiment_pages_unbound_typed_empty_states(self) -> None:
        html = client().get("/experiments").text
        assert "No experiment registry is bound." in html

        detail = client().get("/experiments/ffffffffffffffff").text
        assert "no experiment registry is bound" in detail

    def test_experiments_empty_registry_state(self, tmp_path) -> None:
        registry = ExperimentRegistry(root=tmp_path / "experiments")
        html = client(experiments=registry).get("/experiments").text
        assert "The experiment registry is empty." in html

    def test_promotions_page_renders_resolved_evidence(self, tmp_path) -> None:
        ledger, reports = promotion_setup(tmp_path)

        html = client(promotions=ledger, reports=reports).get("/promotions").text

        assert "momentum_plus" in html
        assert "momentum @ algo (rev 1)" in html
        assert "mean_reversion @ algo (rev 1)" in html
        assert "windows_oos: yes" in html
        assert "none" in html  # kill-switch column, report-only flag not set

    def test_promotions_missing_evidence_renders_typed_state(self, tmp_path) -> None:
        ledger, reports = promotion_setup(tmp_path)
        path = tmp_path / "reports" / "reports.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        oos_line = next(line for line in lines if "windows_oos" in line)
        path.write_text(
            "\n".join(line for line in lines if line != oos_line) + "\n",
            encoding="utf-8",
        )

        html = client(promotions=ledger, reports=reports).get("/promotions").text

        assert 'class="missing-evidence"' in html
        assert "missing evidence" in html
        assert "windows_oos: yes" not in html
        # The rest of the bundle still resolves.
        assert "momentum @ algo (rev 1)" in html

    def test_promotions_without_report_registry_typed_state(self, tmp_path) -> None:
        ledger, _ = promotion_setup(tmp_path)

        html = client(promotions=ledger).get("/promotions").text

        assert "no report registry is bound" in html
        assert 'class="missing-evidence"' in html

    def test_promotions_kill_switch_flag_renders_recorded(self, tmp_path) -> None:
        ledger, reports = promotion_setup(tmp_path, kill_switch=True)

        html = client(promotions=ledger, reports=reports).get("/promotions").text

        assert "gate" in html
        assert "(recorded)" in html

    def test_promotions_unbound_and_empty_ledger_states(self, tmp_path) -> None:
        assert "No promotion ledger is bound." in client().get("/promotions").text

        empty = PromotionLedger(root=tmp_path / "promotions")
        html = client(promotions=empty).get("/promotions").text
        assert "The promotion ledger is empty." in html


_EVENT_T0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
_HOUR = timedelta(hours=1)
_FORECAST_SPEC = ForecastWindowSpec(
    train_observations=10, test_observations=5, step_observations=10
)


def _event_market(
    venue_market_id: str,
    *,
    venue: EventVenue = EventVenue.KALSHI,
    resolution: list[str] | None = None,
    resolved_at: datetime | None = None,
) -> EventMarket:
    return EventMarket(
        venue=venue,
        venue_market_id=venue_market_id,
        event_ticker=f"event-{venue_market_id}",
        title=f"Will {venue_market_id} happen?",
        category="test",
        outcomes=[
            Outcome(name="Yes", venue_outcome_id="yes"),
            Outcome(name="No", venue_outcome_id="no"),
        ],
        resolution_rule=ResolutionRule.of("fixture rule text"),
        resolution=list(resolution or []),
        resolved_at=resolved_at,
    )


def _observation(index: int) -> ForecastObservation:
    return ForecastObservation(
        timestamp=_EVENT_T0 + index * _HOUR,
        probability=0.4 + 0.01 * index,
        liquidity_confidence=0.8,
    )


def _observation_grid(count: int = 30) -> list[ForecastObservation]:
    return [_observation(index) for index in range(count)]


def _forecast_registry(tmp_path: Path) -> ForecastReportRegistry:
    return ForecastReportRegistry(root=tmp_path / "forecasts")


def forecast_setup(tmp_path: Path) -> tuple[ForecastReportRegistry, ForecastReport]:
    """One registry with a two-market report: the first market resolved
    (windows evaluated), the second unresolved (windows render
    'pending')."""
    registry = _forecast_registry(tmp_path)
    report = run_forecast_report(
        [
            ForecastMarket(
                market=_event_market(
                    "mkt-r", resolution=["Yes"], resolved_at=_EVENT_T0 + 3 * _HOUR
                ),
                observations=_observation_grid(),
            ),
            ForecastMarket(market=_event_market("mkt-u"), observations=_observation_grid()),
        ],
        window_spec=_FORECAST_SPEC,
        n_bins=5,
        commit=COMMIT,
        registry=registry,
    )
    return registry, report


def _forecast_report(*, market_id: str, created_at: datetime) -> ForecastReport:
    """A record without artifacts (record-only, like a ledger replay);
    its page renders the typed missing-artifacts state."""
    universe = [_event_market(market_id)]
    metrics, per_market = run_forecast(
        [ForecastMarket(market=_event_market(market_id), observations=_observation_grid(20))],
        window_spec=_FORECAST_SPEC,
        n_bins=5,
    )
    return ForecastReport(
        id=forecast_report_id(
            commit=COMMIT, universe=universe, window_spec=_FORECAST_SPEC, n_bins=5
        ),
        commit=COMMIT,
        universe=universe,
        window_spec=_FORECAST_SPEC,
        n_bins=5,
        created_at=created_at,
        metrics=metrics,
        markets=per_market,
    )


class TestPhaseDPortfolioAndPredictionScreens:
    """M9-4 (#54): portfolio screens over the M1 surface and the M6
    forecast prediction views. The prediction views render only what the
    report records — unresolved windows render 'pending' and a current
    probability is never fabricated from a record that holds window
    results (ADR-0011 decision 4)."""

    # --- portfolio screens ---

    def test_positions_render_unrealized_pnl_matching_json(self) -> None:
        account = sample_account()
        app_client = client(account, marks=dict(MARKS))

        html = app_client.get("/portfolio/positions").text
        body = app_client.get("/positions").json()

        assert len(body) == 1
        position = body[0]
        assert position["key"] in html
        assert str(position["quantity"]) in html
        assert str(position["average_cost"]) in html
        assert str(position["unrealized_pnl"]) in html

    def test_portfolio_html_routes_never_shadow_the_json_surface(self) -> None:
        app_client = client(marks=dict(MARKS))
        for route in ("/positions", "/orders", "/pnl"):
            response = app_client.get(route)
            assert response.headers["content-type"].startswith("application/json"), route
        for route in ("/portfolio/positions", "/portfolio/orders", "/portfolio/pnl"):
            response = app_client.get(route)
            assert response.headers["content-type"].startswith("text/html"), route
            assert "<!doctype html>" in response.text

    def test_positions_without_marks_name_the_missing_mark(self) -> None:
        html = client(marks={}).get("/portfolio/positions").text

        assert "no mark" in html
        assert "internal:AAPL" in html

    def test_positions_empty_state(self) -> None:
        html = client(PaperAccount(cash=10_000.0)).get("/portfolio/positions").text

        assert "No positions." in html

    def test_orders_render_event_streams_and_fills_matching_json(self) -> None:
        account = sample_account()
        app_client = client(account, marks=dict(MARKS))

        html = app_client.get("/portfolio/orders").text
        body = app_client.get("/orders").json()

        assert len(body) == 3
        for order in body:
            assert order["order_id"] in html
            assert str(order["filled_quantity"]) in html
            for event in order["events"]:
                assert event["event_type"] in html
                assert str(event["sequence"]) in html
        # The two market orders carry one fill each; the resting limit
        # order carries none (its fills cell renders 0).
        assert "fill" in html
        assert ">0</td>" in html

    def test_rejected_order_renders_reason(self) -> None:
        rejected = (
            PaperAccount(
                cash=10_000.0,
                fee_model=FeeModel(fee_bps=10),
                matcher=PaperMatcher(slippage_bps=0.0),
                risk_limits=RiskLimits(max_order_quantity=10),
            )
            .submit(make_request(Side.BUY, 15), make_quote(), now=NOW)
            .account
        )

        html = client(rejected).get("/portfolio/orders").text

        assert "rejected" in html
        assert "exceeds limit" in html

    def test_orders_empty_state(self) -> None:
        html = client(PaperAccount(cash=10_000.0)).get("/portfolio/orders").text

        assert "No orders." in html

    def test_pnl_page_matches_json_surface(self) -> None:
        account = sample_account()
        app_client = client(account, marks=dict(MARKS))

        html = app_client.get("/portfolio/pnl").text
        body = app_client.get("/pnl").json()

        for key in (
            "starting_cash",
            "realized_pnl",
            "unrealized_pnl",
            "equity",
            "total_pnl",
        ):
            assert str(body[key]) in html, key
        assert "Cash" in html
        assert "Total fees" in html
        assert str(body["marks"][POSITION_KEY]) in html

    def test_pnl_names_positions_without_marks(self) -> None:
        html = client(marks={}).get("/portfolio/pnl").text

        assert "No mark for: internal:AAPL" in html
        assert "understated" in html

    # --- prediction views ---

    def test_forecasts_unbound_typed_empty_state(self) -> None:
        html = client().get("/forecasts").text

        assert "No forecast report registry is bound." in html

    def test_forecasts_empty_registry_state(self, tmp_path) -> None:
        registry = _forecast_registry(tmp_path)

        html = client(forecasts=registry).get("/forecasts").text

        assert "0 forecast reports." in html

    def test_forecast_report_renders_cards_windows_and_calibration(self, tmp_path) -> None:
        registry, report = forecast_setup(tmp_path)

        html = client(forecasts=registry).get("/forecasts").text

        # Report identity, setup and aggregate metrics.
        assert report.id in html
        assert report.commit in html
        assert "train 10, test 5, step 10" in html
        assert "n_windows_total" in html
        assert str(report.metrics["n_windows_total"]) in html

        # Market cards: identity plus the evaluation note.
        assert "Will mkt-r happen?" in html
        assert "kalshi" in html
        assert "mkt-r" in html
        assert "event-mkt-r" in html
        assert "resolved" in html
        assert "mid-derived implied probabilities" in html

        # Evaluated windows carry the recorded Brier numbers...
        evaluated = report.markets[0].windows[1]
        assert evaluated.brier is not None
        assert str(evaluated.brier) in html
        assert str(evaluated.liquidity_weighted_brier) in html
        # ...and unresolved windows render pending, never a number.
        # (count the rendered text, not the class attribute)
        unresolved = report.markets[1]
        assert all(window.brier is None for window in unresolved.windows)
        assert html.count(">pending</span>") == 2 * len(unresolved.windows)

        # Calibration bins render the model's numbers; empty bins render
        # an en dash, never "None".
        populated = report.markets[0].windows[0].calibration_bins[2]
        assert populated.count > 0
        assert str(populated.observed_frequency) in html
        assert "—" in html
        assert "None" not in html

        # run_forecast_report writes the artifacts; the page says so.
        assert "Artifacts present: report.json, windows.csv, calibration.csv." in html

    def test_forecast_missing_artifacts_render_typed_state(self, tmp_path) -> None:
        registry, report = forecast_setup(tmp_path)
        (tmp_path / "forecasts" / report.id / "calibration.csv").unlink()

        html = client(forecasts=registry).get("/forecasts").text

        assert "Forecast artifacts missing" in html
        assert "calibration.csv" in html
        assert "Artifacts present" not in html
        # The record still renders.
        assert report.id in html
        assert "pending" in html

    def test_forecast_reports_render_newest_first(self, tmp_path) -> None:
        registry = _forecast_registry(tmp_path)
        older = _forecast_report(market_id="mkt-a", created_at=_EVENT_T0 + _HOUR)
        newer = _forecast_report(market_id="mkt-b", created_at=_EVENT_T0 + 2 * _HOUR)
        registry.record(older)
        registry.record(newer)

        html = client(forecasts=registry).get("/forecasts").text

        assert html.index(newer.id) < html.index(older.id)
        # record() writes no artifacts: the typed state renders.
        assert "Forecast artifacts missing" in html


def _alert_record(
    *,
    kind: str,
    source: str,
    detected_at: datetime,
    message: str,
    observed: dict[str, object] | None = None,
) -> AlertRecord:
    observed = observed or {}
    return AlertRecord(
        id=alert_id(kind=kind, source=source, detected_at=detected_at, observed=observed),
        kind=kind,
        source=source,
        detected_at=detected_at,
        message=message,
        observed=observed,
    )


def _alert_setup(tmp_path) -> tuple[AlertLedger, list[AlertRecord]]:
    """Two alerts: an older feature drift, a newer staleness."""
    ledger = AlertLedger(root=tmp_path / "alerts")
    records = [
        _alert_record(
            kind="feature_drift",
            source="feature:momentum",
            detected_at=NOW - timedelta(hours=2),
            message="momentum drifted",
            observed={"psi": 1.07905},
        ),
        _alert_record(
            kind="staleness",
            source="features:index",
            detected_at=NOW - timedelta(hours=1),
            message="index is stale",
            observed={"age_hours": 30},
        ),
    ]
    for record in records:
        ledger.record(record)
    return ledger, records


def _journal_setup(tmp_path) -> tuple[OrderJournal, list[object]]:
    """The journal holds the sample account's three orders."""
    journal = OrderJournal(root=tmp_path / "journal")
    orders = list(sample_account().orders.values())
    for order in orders:
        journal.record(order)
    return journal, orders


def _mapping_setup(tmp_path, *, recorded_at: datetime) -> MappingLedger:
    """One MATCHED pair on two evidence kinds, hand-written as JSONL."""
    ledger = MappingLedger(root=tmp_path / "mappings")
    record = MappingRecord(
        pair_key="a" * 16,
        status=MappingStatus.MATCHED,
        evidence=[
            MappingEvidence(kind=EvidenceKind.OUTCOME_SET, detail="yes/no"),
            MappingEvidence(kind=EvidenceKind.TITLE, detail="same title"),
        ],
        commit="b" * 40,
        recorded_at=recorded_at,
    )
    mappings_dir = tmp_path / "mappings"
    mappings_dir.mkdir(parents=True, exist_ok=True)
    (mappings_dir / MAPPINGS_FILE).write_text(record.model_dump_json() + "\n", encoding="utf-8")
    return ledger


class _Claim(BaseModel):
    claim: str
    confidence: float
    citations: list[str]


def _decision_setup(tmp_path, *, recorded_at: datetime) -> tuple[DecisionLog, DecisionRecord]:
    """One analyst decision record through the real construction path."""
    log = DecisionLog(root=tmp_path / "decisions")
    record = DecisionRecord.for_stage(
        run_id="c" * 16,
        role="analyst",
        model=ModelMeta(name="fixture-model", version="1.0", endpoint_kind="scripted"),
        prompt="What is the state of the market?",
        schema_id="analyst-claim-v1",
        output=_Claim(
            claim="The market is calm.",
            confidence=0.7,
            citations=["experiment:a1b2c3d4e5f60718", "document:doc-1", "audit:paper-1"],
        ),
        citations=[
            Citation(source_kind="experiment", source_id="a1b2c3d4e5f60718"),
            Citation(source_kind="document", source_id="doc-1"),
            Citation(source_kind="audit", source_id="paper-1"),
        ],
        recorded_at=recorded_at,
    )
    log.record(record)
    return log, record


def _document_setup(tmp_path) -> DocumentIndex:
    """One ingested news document."""
    source = tmp_path / "news.txt"
    source.write_text("The Fed holds rates steady at the July meeting.", encoding="utf-8")
    index = DocumentIndex(root=tmp_path / "documents")
    index.ingest_file(source, kind="news", doc_id="doc-1")
    return index


class TestPhaseERiskAuditAndKillSwitch:
    """Phase E screens (issue #55): the risk page, the audit explorer
    and the global kill-switch control (ADR-0011 decision 6)."""

    def test_risk_page_renders_typed_states_and_default_limits(self) -> None:
        html = client().get("/risk").text

        # Unbound surfaces render their typed empty states.
        assert "No alert ledger is bound." in html
        assert "No M5 posture is bound." in html
        # The paper kernel's pre-trade limits default to none -> en dash.
        assert html.count(">—</dd>") == 3
        assert "disarmed" in html

    def test_risk_page_renders_customized_paper_limits(self) -> None:
        account = sample_account().model_copy(
            update={
                "risk_limits": RiskLimits(
                    max_order_quantity=10.0,
                    max_notional=25_000.0,
                    max_position_quantity=50.0,
                )
            }
        )

        html = client(account=account).get("/risk").text

        assert ">10.0</dd>" in html
        assert ">25000.0</dd>" in html
        assert ">50.0</dd>" in html
        # No M5 posture injected -> the typed unbound state still renders.
        assert "No M5 posture is bound." in html

    def test_risk_page_renders_hl_posture_defaults_when_injected(self) -> None:
        html = client(hl_posture=HyperliquidRiskLimits()).get("/risk").text

        assert ">3.0</dd>" in html
        assert ">500</dd>" in html
        assert ">false</dd>" in html
        assert ">30</dd>" in html
        # The accounting surface still renders with its en dashes.
        assert html.count(">—</dd>") == 3

    def test_risk_page_renders_customized_hl_posture(self) -> None:
        html = (
            client(
                hl_posture=HyperliquidRiskLimits(
                    max_leverage=4.5,
                    min_liquidation_distance_bps=700.0,
                    reduce_only=True,
                    stale_data_window_s=60,
                )
            )
            .get("/risk")
            .text
        )

        assert ">4.5</dd>" in html
        assert ">700.0</dd>" in html
        assert ">true</dd>" in html
        assert ">60</dd>" in html

    def test_risk_page_renders_alerts_with_sources_newest_first(self, tmp_path) -> None:
        ledger, records = _alert_setup(tmp_path)

        html = client(alerts=ledger).get("/risk").text

        assert "feature:momentum" in html
        assert "features:index" in html
        assert "momentum drifted" in html
        assert "index is stale" in html
        assert "psi" in html
        assert "1.07905" in html
        # Newest alert first: the staleness record (NOW-1h) precedes the
        # drift record (NOW-2h) in the table.
        assert html.index("index is stale") < html.index("momentum drifted")

    def test_audit_page_renders_typed_unbound_state(self) -> None:
        html = client().get("/audit").text

        # Each ledger chip renders its typed unbound state.
        assert html.count('class="missing-mark">unbound</span>') == 3
        assert "Order journal:" in html
        assert "Mappings ledger:" in html
        assert "Decision log:" in html
        assert "No audit entries" in html

    def test_audit_page_merges_three_ledgers_chronologically(self, tmp_path) -> None:
        journal, orders = _journal_setup(tmp_path)
        mappings = _mapping_setup(tmp_path, recorded_at=NOW - timedelta(hours=2))
        decisions, record = _decision_setup(tmp_path, recorded_at=NOW - timedelta(hours=1))

        html = client(journal=journal, mappings=mappings, decisions=decisions).get("/audit").text

        assert "Order journal: bound" in html
        assert "Mappings ledger: bound" in html
        assert "Decision log: bound" in html
        order_id = orders[0].order_id
        mapping_anchor = f'id="mapping-{"a" * 16}"'
        decision_anchor = f'id="decision-{record.decision_id}"'
        # Newest first: order (NOW) -> decision (NOW-1h) -> mapping (NOW-2h).
        assert html.index(f'id="order-{order_id}"') < html.index(decision_anchor)
        assert html.index(decision_anchor) < html.index(mapping_anchor)
        # The order entry renders its event stream incl. fills.
        assert ">fill</td>" in html
        assert ">accepted</td>" in html
        # The mapping entry renders its verdict and evidence.
        assert ">matched</dd>" in html
        assert ">title</code>" in html
        assert "same title" in html
        # The decision entry renders model metadata and the verdict.
        assert "fixture-model" in html
        assert "scripted" in html
        # The verdict JSON renders in the heading, quote-escaped (&#34;).
        assert record.verdict.replace('"', "&#34;") in html

    def test_audit_citations_render_resolvable_links(self, tmp_path) -> None:
        journal, _ = _journal_setup(tmp_path)
        decisions, _ = _decision_setup(tmp_path, recorded_at=NOW - timedelta(hours=1))
        documents = _document_setup(tmp_path)

        html = client(journal=journal, decisions=decisions, documents=documents).get("/audit").text

        assert 'href="/experiments/a1b2c3d4e5f60718"' in html
        assert 'href="/documents/doc-1"' in html
        assert 'href="/audit#order-paper-1"' in html
        assert "experiment:a1b2c3d4e5f60718" in html
        assert "document:doc-1" in html
        assert "audit:paper-1" in html

    def test_document_detail_renders_the_record(self, tmp_path) -> None:
        documents = _document_setup(tmp_path)

        html = client(documents=documents).get("/documents/doc-1").text

        assert "Document doc-1" in html
        assert ">news</dd>" in html
        assert "The Fed holds rates steady" in html

    def test_document_detail_unknown_id_renders_typed_error(self, tmp_path) -> None:
        documents = _document_setup(tmp_path)

        response = client(documents=documents).get("/documents/absent")

        assert 'role="alert"' in response.text
        assert "no document" in response.text

    def test_document_detail_unbound_index_renders_typed_error(self) -> None:
        response = client().get("/documents/doc-1")

        assert 'role="alert"' in response.text
        assert "no document index is bound" in response.text

    def test_kill_switch_engage_round_trip(self) -> None:
        app_client = client()

        response = app_client.post(
            "/kill-switch",
            data={"action": "engage", "confirm": "confirm"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/kill-switch/control"
        # The M1 JSON surface and the page context agree.
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": True,
            "kill_switches": {},
        }
        context = app_client.app.state.page_context
        assert context.account.kill_switch is True
        assert app_client.app.state.account.kill_switch is True
        # The header reflects the state on every page.
        overview = app_client.get("/").text
        assert 'data-kill-switch="true"' in overview
        assert "ENGAGED" in overview
        # The control page reflects it too.
        control = app_client.get("/kill-switch/control").text
        assert "ENGAGED" in control
        assert 'name="action" value="disarm" checked' in control

    def test_kill_switch_disarm_round_trip(self) -> None:
        app_client = client()
        app_client.post("/kill-switch", data={"action": "engage", "confirm": "confirm"})

        response = app_client.post(
            "/kill-switch",
            data={"action": "disarm", "confirm": "confirm"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": False,
            "kill_switches": {},
        }
        assert 'data-kill-switch="false"' in app_client.get("/").text

    def test_kill_switch_hostile_posts_refused(self) -> None:
        app_client = client()

        hostile = (
            {"action": "engage"},
            {"action": "engage", "confirm": "yes"},
            {"action": "flip", "confirm": "confirm"},
            {},
        )
        for payload in hostile:
            response = app_client.post("/kill-switch", data=payload)
            assert response.status_code == 200
            assert 'role="alert"' in response.text
            assert "refused" in response.text
        # A non-form body is refused too.
        response = app_client.post("/kill-switch", json={"action": "engage", "confirm": "confirm"})
        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "refused" in response.text
        # The account was never touched.
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": False,
            "kill_switches": {},
        }
        assert app_client.app.state.page_context.account.kill_switch is False


class TestPhaseCPerVenueKillSwitch:
    """M10 Phase C (issue #60): the kill-switch control flips per-venue
    switches on the same account object — same confirm-gated POST
    contract, one `venue` field. The M1 JSON surface, the page context
    and the kernel gate agree on the state (ADR-0012 decision 3)."""

    MARKETS = {"moomoo": {"AAA": 100.0}, "hyperliquid": {"BTC": 100.0}}

    def test_per_venue_rows_render_from_markets(self) -> None:
        app_client = client(markets=self.MARKETS)

        html = app_client.get("/kill-switch/control").text

        assert "Per-venue kill switches" in html
        assert 'name="venue" value="hyperliquid"' in html
        assert 'name="venue" value="moomoo"' in html
        # Everything disarmed, the global form untouched.
        assert "Block moomoo paper orders" in html
        assert 'name="action" value="engage" checked' in html

    def test_per_venue_engage_round_trip(self) -> None:
        app_client = client(markets=self.MARKETS)

        response = app_client.post(
            "/kill-switch",
            data={"action": "engage", "confirm": "confirm", "venue": "moomoo"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/kill-switch/control"
        # Only the venue flipped: global bit and the other venue are
        # untouched, and the surfaces agree.
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": False,
            "kill_switches": {"moomoo": True},
        }
        context = app_client.app.state.page_context
        assert context.account.kill_switches == {Venue.MOOMOO: True}
        # The header still shows the global state; the control page
        # names the venue as refused.
        assert 'data-kill-switch="false"' in app_client.get("/").text
        control = app_client.get("/kill-switch/control").text
        assert "REFUSED" in control
        assert 'value="disarm" checked' in control
        assert "moomoo" in control

    def test_per_venue_disarm_leaves_other_venues_engaged(self) -> None:
        account = sample_account().model_copy(
            update={"kill_switches": {Venue.MOOMOO: True, Venue.HYPERLIQUID: True}}
        )
        app_client = client(account=account, markets=self.MARKETS)

        response = app_client.post(
            "/kill-switch",
            data={"action": "disarm", "confirm": "confirm", "venue": "moomoo"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": False,
            "kill_switches": {"hyperliquid": True},
        }
        assert app_client.app.state.page_context.account.kill_switches == {Venue.HYPERLIQUID: True}

    def test_hostile_venue_refused_without_touching_state(self) -> None:
        app_client = client(markets=self.MARKETS)

        response = app_client.post(
            "/kill-switch",
            data={"action": "engage", "confirm": "confirm", "venue": "not-a-venue"},
        )

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "unknown venue" in response.text
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": False,
            "kill_switches": {},
        }

    def test_account_flags_render_without_markets(self) -> None:
        account = sample_account().model_copy(update={"kill_switches": {Venue.MOOMOO: True}})

        html = client(account=account).get("/kill-switch/control").text

        assert "Per-venue kill switches" in html
        assert "Block moomoo paper orders" in html
        assert "REFUSED" in html


class TestWriteSurfaceOriginGuard:
    """M10 Phase D (issue #61), threat model T-14: the three write
    surfaces (watchlist add/remove, kill switch) refuse a POST whose
    Origin is present but not loopback. Browser CSRF always sends the
    attacker's Origin; an absent Origin (CLI, drill, non-browser
    client) stays allowed — every pre-existing POST test pins that
    path."""

    def test_hostile_origin_kill_switch_post_is_refused(self) -> None:
        app_client = client()

        response = app_client.post(
            "/kill-switch",
            data={"action": "engage", "confirm": "confirm"},
            headers={"Origin": "http://evil.example"},
        )

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "cross-origin send" in response.text
        # The switch never flipped.
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": False,
            "kill_switches": {},
        }

    def test_loopback_origin_kill_switch_post_flips(self) -> None:
        app_client = client()

        response = app_client.post(
            "/kill-switch",
            data={"action": "engage", "confirm": "confirm"},
            headers={"Origin": "http://127.0.0.1:8642"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert app_client.get("/kill-switch").json() == {
            "kill_switch": True,
            "kill_switches": {},
        }

    def test_hostile_origin_watchlist_post_is_refused(self, tmp_path) -> None:
        store = WatchlistStore(root=tmp_path / "watchlists")
        app_client = client(watchlist=store)

        response = app_client.post(
            "/watchlist/add",
            data={"symbol": "SOL"},
            headers={"Origin": "http://evil.example"},
        )

        assert response.status_code == 200
        assert 'role="alert"' in response.text
        assert "cross-origin send" in response.text
        assert app_client.get("/watchlist").text.count("SOL") == 0

    def test_loopback_origin_watchlist_add_succeeds(self, tmp_path) -> None:
        store = WatchlistStore(root=tmp_path / "watchlists")
        app_client = client(watchlist=store)

        response = app_client.post(
            "/watchlist/add",
            data={"symbol": "SOL"},
            headers={"Origin": "http://localhost:8642"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "SOL" in app_client.get("/watchlist").text

    def test_absent_origin_stays_allowed(self, tmp_path) -> None:
        # The non-browser path: no Origin header at all, like the
        # E2E/drill clients — pinned explicitly so the threat model's
        # claim ("absent Origin is allowed") is a tested fact.
        store = WatchlistStore(root=tmp_path / "watchlists")
        app_client = client(watchlist=store)

        response = app_client.post("/watchlist/add", data={"symbol": "SOL"}, follow_redirects=False)

        assert response.status_code == 303
        assert "SOL" in app_client.get("/watchlist").text


class TestEnablementScreen:
    """The M10 Phase E enablement screen: read-only per-venue state and
    the recorded gate. There is deliberately no form and no POST —
    transitions are CLI/operator-owned (ADR-0012 decision 5)."""

    def test_unbound_ledger_renders_typed_empty_state(self) -> None:
        html = client().get("/enablement").text

        assert "No enablement ledger is bound." in html
        # The recorded gate renders verbatim on every state of the page.
        assert GATE_TEXT in html

    def test_bound_ledger_renders_per_venue_states(self, tmp_path) -> None:
        ledger = ApprovalLedger(root=tmp_path / "enablement")
        ledger.request(Venue.MOOMOO, actor="operator-alpha", acted_at=NOW)
        ledger.approve(Venue.MOOMOO, actor="operator-alpha", acted_at=NOW, gate_text=GATE_TEXT)
        ledger.request(Venue.HYPERLIQUID, actor="operator-alpha", acted_at=NOW)

        html = client(enablement=ledger).get("/enablement").text

        assert "No enablement ledger is bound." not in html
        assert "<code>moomoo</code>" in html
        assert "<code>hyperliquid</code>" in html
        assert "enabled" in html
        assert "pending" in html
        assert "disabled" not in html  # no venue is disabled in this fixture
        assert GATE_TEXT in html

    def test_empty_ledger_says_every_venue_disabled(self, tmp_path) -> None:
        html = (
            client(enablement=ApprovalLedger(root=tmp_path / "enablement")).get("/enablement").text
        )

        assert "No enablement records yet" in html
        assert GATE_TEXT in html

    def test_page_is_read_only(self, tmp_path) -> None:
        ledger = ApprovalLedger(root=tmp_path / "enablement")
        app_client = client(enablement=ledger)

        # No write surface exists: a POST is refused, and the ledger
        # cannot be changed through the UI by construction.
        assert app_client.post("/enablement", data={"venue": "moomoo"}).status_code == 405
        assert "No enablement ledger is bound." not in app_client.get("/enablement").text
        assert ledger.all() == []

    def test_nav_reaches_the_enablement_screen(self) -> None:
        html = client().get("/").text
        assert '<a href="/enablement">Enablement</a>' in html
