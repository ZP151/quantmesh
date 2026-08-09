"""Phase F E2E (issue #56): the workstation over real uvicorn, driven
by Playwright chromium.

The suite boots uvicorn on an OS-reserved loopback socket over a fixture
universe (built exactly like the unit-drill universes) and walks the
core paper workflow — overview, watchlist add, instruments, positions,
orders, P&L — then drives the critical controls (navigation, kill
switch) with keyboard only, and takes accessibility snapshots on the
registry's list screens (the two detail pages need a bound registry,
which the fixture leaves unbound). It skips cleanly when playwright is
not installed or the
chromium browser is missing: the `e2e` extra is dev-only (ADR-0011
decision 7), so a pipeline without the browser must stay green, never
fail.
"""

import socket
import threading
from datetime import UTC, datetime

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.api.workstation import create_workstation_app
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.execution.accounting import FeeModel, PaperAccount, PaperMatcher

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is not installed (dev-only e2e extra: pip install -e '.[dev,e2e]')",
)

# This suite walks the RC1 Jinja2 pages (ADR-0013 decision 6, the
# rollback switch): the SPA is the default surface now, so the walk
# pins legacy mode for the whole module. The SPA walk lands with the
# app shell in Phase C, and the Phase E Playwright pass exercises the
# demo workflow in the browser.
workstation.settings.legacy_ui = True


@pytest.fixture(scope="session", autouse=True)
def _restore_legacy_ui() -> None:
    """The RC1 E2E exercises the legacy Jinja2 surface. Re-pin the flag
    at setup: an autouse session fixture from an earlier-imported module
    (test_spa_e2e.py) runs after this module's import-time pin and would
    otherwise leave the SPA mounted on the E2E port. Restore the default
    once the module's tests are done."""
    workstation.settings.legacy_ui = True
    yield
    workstation.settings.legacy_ui = False

HOST = "127.0.0.1"
NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
POSITION_KEY = "internal:AAPL"
MARKETS = {
    "hyperliquid": {"BTC": 65_000.0, "ETH": 3_200.0},
    "moomoo": {"AAPL": 210.0},
}


def _quote() -> Quote:
    return Quote(instrument=INSTRUMENT, timestamp=NOW, bid=99.0, ask=100.0, volume=100)


def _build_app(root) -> object:
    """The fixture universe: the sample account (3 orders, 6 AAPL held,
    marks), the venue markets, and a fresh watchlist store."""
    account = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    for side, quantity in ((Side.BUY, 10), (Side.SELL, 4), (Side.BUY, 10)):
        account = account.submit(
            OrderRequest(instrument=INSTRUMENT, side=side, quantity=quantity),
            _quote(),
            now=NOW,
        ).account
    return create_workstation_app(
        account=account,
        marks={POSITION_KEY: 95.0},
        markets=dict(MARKETS),
        watchlist=WatchlistStore(root=root / "watchlists"),
    )


def _wait_for_server(server: uvicorn.Server) -> None:
    for _ in range(200):  # 10 s of 50 ms polls
        if server.started:
            return
        threading.Event().wait(0.05)
    raise AssertionError("uvicorn never came up on its reserved loopback socket")


@pytest.fixture(scope="session")
def base_url(tmp_path_factory) -> str:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    app = _build_app(tmp_path_factory.mktemp("e2e"))
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    try:
        _wait_for_server(server)
        yield f"http://{HOST}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()


@pytest.fixture(scope="module")
def browser():
    """Module scope: an open ``sync_playwright()`` context keeps its
    asyncio loop running on the main thread, which makes any *later*
    ``sync_playwright()`` entry raise "Sync API inside the asyncio
    loop". Closing the context with this module keeps later E2E
    modules safe (see the identical fixture in test_spa_e2e.py)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            launched = p.chromium.launch()
        except Exception as exc:  # chromium not installed -> clean skip
            pytest.skip(f"chromium is not installed ({exc}) — run `playwright install chromium`")
        yield launched
        launched.close()


@pytest.fixture()
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


def _active(page) -> dict:
    """The focused element as a plain dict of the properties the
    keyboard tests inspect (a DOM node cannot cross evaluate)."""
    return page.evaluate(
        "(() => { const el = document.activeElement; "
        "return el ? {tag: el.tagName, name: el.name, type: el.type,"
        " href: el.getAttribute('href')} : {}; })()"
    )


def _tab_to(page, predicate, *, limit=80) -> bool:
    """Press Tab until the active element satisfies `predicate`.

    The nav is fixed (the page registry), so the sequence is
    deterministic; the loop only avoids hard-coding the count.
    """
    for _ in range(limit):
        if predicate(_active(page)):
            return True
        page.keyboard.press("Tab")
    return False


def test_core_paper_workflow_walk(page, base_url) -> None:
    """Exit criterion 1: overview -> watchlist add -> instruments ->
    positions -> orders -> P&L, purely through the web UI."""
    page.goto(base_url)
    page.get_by_role("heading", name="Overview", exact=True).wait_for()
    main = page.locator("main")
    assert "Paper account" in main.inner_text()
    assert "hyperliquid" in main.inner_text()

    # Watchlist: empty, then add a symbol through the form (the one
    # UI-owned write surface).
    page.get_by_role("link", name="Watchlist", exact=True).click()
    page.get_by_role("heading", name="Watchlist", exact=True).wait_for()
    assert "The watchlist is empty." in main.inner_text()
    page.get_by_label("Symbol", exact=True).fill("SOL")
    page.get_by_role("button", name="Add to watchlist").click()
    page.get_by_role("heading", name="Watchlist", exact=True).wait_for()
    assert "SOL" in main.inner_text()

    page.get_by_role("link", name="Instruments", exact=True).click()
    page.get_by_role("heading", name="Instruments", exact=True).wait_for()
    assert "Cross-venue instruments" in main.inner_text()

    page.get_by_role("link", name="Positions", exact=True).click()
    page.get_by_role("heading", name="Positions", exact=True).wait_for()
    assert "AAPL" in main.inner_text()
    # The mark (95.0) is not rendered itself — it lives in the mark-derived
    # unrealized P&L (95.0 − 100.0 average) × 16 held = −80.0.
    assert "-80.0" in main.inner_text()

    page.get_by_role("link", name="Orders", exact=True).click()
    page.get_by_role("heading", name="Orders", exact=True).wait_for()
    orders_text = main.inner_text()
    assert "paper-1" in orders_text
    assert "fill" in orders_text

    page.get_by_role("link", name="P&L", exact=True).click()
    # pnl.html names both the h1 and the P&L-section h2 "P&L"; .first pins
    # the page heading (the h1 comes first in the DOM).
    page.get_by_role("heading", name="P&L", exact=True).first.wait_for()
    assert "Equity" in main.inner_text()


def test_keyboard_only_navigation(page, base_url) -> None:
    """Exit criterion 2: navigation operates with Tab and Enter only."""
    page.goto(base_url)
    page.get_by_role("heading", name="Overview", exact=True).wait_for()

    # Focus starts at the skip link, then the first primary nav link.
    assert _tab_to(page, lambda el: el.get("href") == "#main")
    assert _tab_to(page, lambda el: el.get("href") == "/instruments")
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Instruments", exact=True).wait_for()
    assert "/instruments" in page.url

    # From the landing page the same two tabs still lead to the nav.
    assert _tab_to(page, lambda el: el.get("href") == "#main")
    assert _tab_to(page, lambda el: el.get("href") == "/watchlist")
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Watchlist", exact=True).wait_for()
    assert "/watchlist" in page.url

    # The promotion view (a criterion-5 critical control) is reachable
    # the same way from the watchlist page.
    assert _tab_to(page, lambda el: el.get("href") == "#main")
    assert _tab_to(page, lambda el: el.get("href") == "/promotions")
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Promotions", exact=True).wait_for()
    assert "/promotions" in page.url


def test_kill_switch_keyboard_only(page, base_url) -> None:
    """Exit criterion 2: the kill-switch control flips with Tab/Space/
    Enter only — global engage then disarm, and a per-venue engage then
    disarm round trip through the same confirm-gated POST (M10 Phase C).
    The per-venue forms follow the global form in the DOM, so the tab
    sequence reaches the global controls first."""
    page.goto(f"{base_url}/kill-switch/control")
    page.get_by_role("heading", name="Paper kernel kill switch", exact=True).wait_for()
    assert "disarmed" in page.locator("body").inner_text()

    def on_radio_group(_el: dict) -> bool:
        return page.evaluate("document.activeElement.name") == "action"

    def on_confirm(_el: dict) -> bool:
        return page.evaluate("document.activeElement.name") == "confirm"

    def on_submit(_el: dict) -> bool:
        return page.evaluate("document.activeElement.type") == "submit"

    def on_moomoo_radio(_el: dict) -> bool:
        # A radio inside the moomoo per-venue form (which carries the
        # hidden venue field) — the global form has none.
        return page.evaluate(
            """() => {
                const el = document.activeElement;
                if (el.name !== "action") return false;
                return el.closest("form").querySelector(
                    'input[name="venue"]'
                )?.value === "moomoo";
            }"""
        )

    # The radio group: ArrowDown/ArrowUp move within it, Space selects.
    assert _tab_to(page, on_radio_group)
    page.keyboard.press("ArrowDown")  # engage -> disarm
    assert page.get_by_role("radio", name="Disarm").is_checked()
    page.keyboard.press("ArrowUp")  # disarm -> engage
    assert page.get_by_role("radio", name="Engage").is_checked()

    assert _tab_to(page, on_confirm)
    page.keyboard.press("Space")
    assert page.get_by_role(
        "checkbox", name="I confirm this is the global paper-level kill switch"
    ).is_checked()
    assert _tab_to(page, on_submit)
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Paper kernel kill switch", exact=True).wait_for()
    assert "ENGAGED" in page.locator("body").inner_text()

    # Disarm round trip: the checked radio is now "disarm".
    assert _tab_to(page, on_radio_group)
    assert page.get_by_role("radio", name="Disarm").is_checked()
    assert _tab_to(page, on_confirm)
    page.keyboard.press("Space")
    assert _tab_to(page, on_submit)
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Paper kernel kill switch", exact=True).wait_for()
    assert "disarmed" in page.locator("body").inner_text()

    # Per-venue engage round trip (M10 Phase C): tab past the global
    # form to the moomoo controls, submit the venue form unchanged —
    # the global state stays disarmed while moomoo is refused.
    assert _tab_to(page, on_moomoo_radio)
    assert page.get_by_role(
        "radio", name="Block moomoo paper orders"
    ).is_checked()
    assert _tab_to(page, on_confirm)
    page.keyboard.press("Space")
    assert page.get_by_role(
        "checkbox", name="I confirm this is the per-venue kill switch for moomoo"
    ).is_checked()
    assert _tab_to(page, on_submit)
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Paper kernel kill switch", exact=True).wait_for()
    assert "REFUSED" in page.locator("body").inner_text()
    assert "The global kill switch is disarmed." in page.locator("body").inner_text()

    # Per-venue disarm: the checked radio is now "Allow moomoo paper orders".
    assert _tab_to(page, on_moomoo_radio)
    assert page.get_by_role(
        "radio", name="Allow moomoo paper orders"
    ).is_checked()
    assert _tab_to(page, on_confirm)
    page.keyboard.press("Space")
    assert _tab_to(page, on_submit)
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="Paper kernel kill switch", exact=True).wait_for()
    assert "REFUSED" not in page.locator("body").inner_text()
    assert "Paper orders on moomoo are allowed." in page.locator("body").inner_text()


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/", "Overview"),
        ("/watchlist", "Watchlist"),
        ("/experiments", "Experiments"),
        ("/promotions", "Promotions"),
        ("/forecasts", "Forecasts"),
        ("/instruments", "Instruments"),
        ("/portfolio/positions", "Positions"),
        ("/portfolio/orders", "Orders"),
        ("/portfolio/pnl", "P&L"),
        ("/risk", "Risk"),
        ("/audit", "Audit explorer"),  # audit.html's h1 is "Audit explorer", not "Audit"
        ("/kill-switch/control", "Paper kernel kill switch"),
        ("/enablement", "Enablement"),
    ],
)
def test_accessibility_snapshots(page, base_url, path: str, heading: str) -> None:
    """Exit criterion 2: every screen exposes the landmarks and its
    heading to assistive technology (aria snapshot)."""
    page.goto(base_url + path)
    # .first: /portfolio/pnl names both the h1 and a section h2 "P&L".
    page.get_by_role("heading", name=heading, exact=True).first.wait_for()
    snapshot = page.locator("body").aria_snapshot()
    assert '- navigation "Primary":' in snapshot
    assert "\n- main:" in snapshot
    assert f'- heading "{heading}"' in snapshot
    assert "- banner:" in snapshot
