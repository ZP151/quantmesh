"""M9 workstation server shell (issue #51, Phase A).

The workstation app is the M1 read-only API plus server-rendered Jinja2
screens: a route -> template -> provider registry pinned by test, a
loopback-only bind refused at construction, and the accessibility
posture (skip link, landmarks, visible focus) rendered from the first
screen on.
"""

import sys
import types
from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from quantmesh import __version__
from quantmesh.api import workstation
from quantmesh.api.app import create_app
from quantmesh.api.workstation import (
    PAGES,
    PageContext,
    WorkstationConfigError,
    create_workstation_app,
)
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.execution.accounting import FeeModel, PaperAccount, PaperMatcher
from quantmesh.settings import settings

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
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


def client(
    account: PaperAccount | None = None, marks: dict[str, float] | None = None
) -> TestClient:
    return TestClient(
        create_workstation_app(account=account or sample_account(), marks=marks)
    )


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
        app_routes = {route.path for route in client().app.routes}
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
            assert "Overview" in response.text


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


class TestConsoleScript:
    def test_main_refuses_non_loopback_before_uvicorn(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "workstation_host", "0.0.0.0")
        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda **kw: None))

        with pytest.raises(WorkstationConfigError, match="loopback"):
            workstation.main()

    def test_main_serves_on_loopback_with_settings_bind(self, monkeypatch) -> None:
        calls: dict = {}

        def fake_run(*args, **kwargs) -> None:
            calls.update(kwargs)

        monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr(settings, "workstation_host", "127.0.0.1")
        monkeypatch.setattr(settings, "workstation_port", 9876)

        workstation.main()

        assert calls["host"] == "127.0.0.1"
        assert calls["port"] == 9876
