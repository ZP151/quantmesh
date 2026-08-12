"""Phase C-3 browser E2E (iteration 0015): the Live Market Cockpit over
the real local stack, driven by Playwright chromium.

The entire wire is real and loopback-only: uvicorn serves the
workstation app with the live feed attached (the assembly ``--live``
runs), the Hyperliquid supervisor talks through
``LiveHyperliquidTransport`` to the scripted fixture venue on an
ephemeral port, and the browser walks the cockpit watchlist, the
instrument detail (chart / per-side book / trade tape), the stale
transition after the venue goes quiet, and the keyboard + mobile
checks. The venue plan plays a burst of real frames at connect, then
keeps every channel fresh on a 4 s cadence for a long window (20 min)
so the browser tests can never outrun the freshness phase, no matter
how slow module setup is under full-suite load. The stale-transition
test then flips the venue's ``quiet`` event — the venue stops sending
frames but the socket stays open — which deterministically ages the
last ``received_at`` past the feed's lag and flips the watchlist badge
to Stale while the transport stays connected.

The frame shapes mirror the canonical wire formats in
``test_live_supervisor`` (Phase B drilled them against this protocol).
Skips cleanly when playwright or chromium is missing (the ``e2e`` extra
is dev-only, ADR-0011 decision 7) and when the pinned port is already
bound, so a pipeline without the browser stays green.
"""

import asyncio
import json
import re
import socket
import threading
import urllib.request
from collections.abc import Callable
from datetime import timedelta
from typing import cast

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, LiveHyperliquidTransport
from tests.fixture_ws_venue import ScriptedVenue

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is not installed (dev-only e2e extra: pip install -e '.[dev,e2e]')",
)

# The SPA is the default surface; pin it explicitly so the RC1 legacy
# module (which flips the flag at import) cannot leak into this one.
workstation.settings.legacy_ui = False


@pytest.fixture(scope="session", autouse=True)
def _restore_legacy_ui() -> None:
    """Keep the SPA the default surface for the whole session; the RC1
    legacy module re-flips its own flag when it runs."""
    workstation.settings.legacy_ui = False
    yield


HOST = "127.0.0.1"
PORT = 8645  # 8643 (spa e2e) and 8644 (SSE drill) are taken by their suites
BASE_URL = f"http://{HOST}:{PORT}"

# The feed's freshness policy: a real quote older than the lag is
# Stale. The venue's keep-alive cadence (4 s) stays under it while
# frames flow, and the quiet tail crosses it ~5 s after the last frame.
FEED_LAG = timedelta(seconds=5)
FEED_STALE = timedelta(seconds=10)

# The venue plan: a burst at connect, then KEEPALIVE_CYCLES refresh
# frames every 1 s (one full BBO/candle/trade/book cycle every 4 s).
# The window is deliberately long (20 min): module
# setup (uvicorn boot, feed attach, browser launch) and the browser
# tests all happen inside it, so a slow full-suite run can never push
# the freshness phase past. The quiet tail is NOT clock-bound: the
# stale-transition test triggers the venue's ``quiet`` event, which
# stops the frames with the socket still open.
KEEPALIVE_CYCLES = 300
KEEPALIVE_DELAY = 1.0


# -- canonical frame shapes (mirror test_live_supervisor) ---------------------


def _bbo(coin: str) -> dict:
    return {
        "channel": "bbo",
        "data": {
            "coin": coin,
            "time": 1_750_000_000_000,
            "bid": 100.0,
            "bidSz": 1.0,
            "ask": 100.5,
            "askSz": 2.0,
        },
    }


def _candle(coin: str, open_: float, close: float, t: int) -> dict:
    return {
        "channel": "candle",
        "data": {
            "t": t,
            "T": t + 60_000,
            "s": coin,
            "i": "1m",
            "o": open_,
            "c": close,
            "h": max(open_, close),
            "l": min(open_, close),
            "v": 1.0,
            "n": 1,
        },
    }


def _trade(coin: str, tid: int, px: float = 100.3, side: str = "B") -> dict:
    return {
        "channel": "trades",
        "data": [
            {"coin": coin, "tid": tid, "px": px, "sz": 0.5, "side": side, "time": 1_750_000_000_000}
        ],
    }


def _l2(coin: str) -> dict:
    return {
        "channel": "l2Book",
        "data": {
            "coin": coin,
            "time": 1_750_000_000_000,
            "levels": [
                [{"px": "100.0", "sz": "1.0", "n": 1}, {"px": "99.5", "sz": "2.0", "n": 1}],
                [{"px": "100.5", "sz": "0.5", "n": 1}],
            ],
            "type": "book",
        },
    }


def _mids() -> dict:
    return {"channel": "allMids", "data": {"mids": {"BTC": 100.25}}}


def _asset_ctx() -> dict:
    ctx = {"funding": 1.25e-05, "markPx": 100.3, "oraclePx": 100.1, "openInterest": 123.4}
    return {"channel": "activeAssetCtx", "data": {"BTC": ctx}}


def _venue_plan() -> list[tuple[float, object]]:
    """Burst + keep-alive cycles + quiet tail (see module docstring).

    Trade tids stay consecutive across the whole plan (1..2 +
    KEEPALIVE_CYCLES), so the sequence-continuity drill never flags a
    gap. Quote prices are constant, so every snapshot the browser sees
    carries the same row. The quiet tail is not clock-bound: the stale
    test flips the venue's ``quiet`` event to stop the frames.
    """
    cycle_t0 = 1_750_000_120_000
    plan: list[tuple[float, object]] = [
        (0.0, frame)
        for frame in (
            _bbo("BTC"),
            _mids(),
            _asset_ctx(),
            _candle("BTC", 100.0, 100.25, 1_750_000_000_000),
            _candle("BTC", 100.25, 100.1, 1_750_000_060_000),
            _trade("BTC", 1),
            _trade("BTC", 2),
            _l2("BTC"),
        )
    ]
    for cycle in range(KEEPALIVE_CYCLES):
        plan.extend(
            [
                (KEEPALIVE_DELAY, _bbo("BTC")),
                (KEEPALIVE_DELAY, _candle("BTC", 100.1, 100.1, cycle_t0 + cycle * 60_000)),
                (KEEPALIVE_DELAY, _trade("BTC", 3 + cycle)),
                (KEEPALIVE_DELAY, _l2("BTC")),
            ]
        )
    plan.append((3600.0, {"__cmd": "close"}))
    return plan


# -- the scripted venue on its own loop ----------------------------------------


@pytest.fixture(scope="module")
def venue_url() -> tuple[str, Callable[[], None]]:
    """The ScriptedVenue on its own asyncio loop in a daemon thread (the
    sync Playwright thread cannot run the venue's loop). Yields the URL
    and a thread-safe trigger that flips the venue's ``quiet`` event —
    the deterministic "venue went quiet" condition for the stale test."""
    loop = asyncio.new_event_loop()
    holder: dict[str, object] = {}
    ready = threading.Event()

    def runner() -> None:
        asyncio.set_event_loop(loop)

        async def serve() -> None:
            quiet = asyncio.Event()
            holder["quiet"] = quiet
            async with ScriptedVenue(plan=_venue_plan(), quiet=quiet) as venue:
                holder["url"] = venue.url
                held: asyncio.Future[None] = asyncio.get_running_loop().create_future()
                holder["held"] = held
                ready.set()
                await held

        try:
            loop.run_until_complete(serve())
        except asyncio.CancelledError:
            # Fixture teardown cancels the held future to release the
            # scripted venue. That is the expected shutdown signal, not
            # an unhandled thread failure.
            pass
        finally:
            loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    if not ready.wait(timeout=10):
        raise AssertionError("the scripted venue never came up")

    def quiet_trigger() -> None:
        quiet = cast(asyncio.Event, holder["quiet"])
        loop.call_soon_threadsafe(quiet.set)

    try:
        yield (str(holder["url"]), quiet_trigger)
    finally:
        held = holder.get("held")
        if held is not None:
            loop.call_soon_threadsafe(cast(asyncio.Future, held).cancel)
        thread.join(timeout=5)


# -- the workstation server with the feed attached -----------------------------


def _port_in_use() -> bool:
    with socket.socket() as probe:
        try:
            probe.bind((HOST, PORT))
        except OSError:
            return True
    return False


def _wait_for_server() -> None:
    for _ in range(400):
        if _port_in_use():
            return
        threading.Event().wait(0.1)
    raise AssertionError(f"uvicorn never came up on {HOST}:{PORT}")


def _wait_for_feed() -> None:
    """The lifespan pump must have delivered the burst before the tests
    start, so the watchlist snapshot always carries the quote row."""
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/live/state", timeout=1) as response:
                body = json.loads(response.read())
        except OSError:
            body = {}
        if body.get("instruments"):
            return
        threading.Event().wait(0.1)
    raise AssertionError("the live feed never delivered a frame")


@pytest.fixture(scope="module")
def base_url(venue_url: tuple[str, Callable[[], None]]) -> str:
    url, _trigger = venue_url
    if _port_in_use():
        pytest.skip(f"port {PORT} is already bound — the pinned E2E port must be free")
    account = PaperAccount(cash=100_000.0)
    feed = LiveFeed(lag=FEED_LAG, stale=FEED_STALE)
    supervisor = HyperliquidVenueSupervisor(LiveHyperliquidTransport(url))
    supervisor.subscribe(["BTC"])
    feed.attach(supervisor)
    app = create_workstation_app(account=account, live_feed=feed, host=HOST)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_for_server()
        _wait_for_feed()
        yield BASE_URL
    finally:
        server.should_exit = True
        thread.join(timeout=15)


# -- browser fixtures (mirror test_spa_e2e) ------------------------------------


@pytest.fixture(scope="module")
def browser():
    """Module scope on purpose: an open ``sync_playwright()`` context
    keeps its asyncio loop *running* on the main thread (the dispatcher
    greenlet parks inside ``run_until_complete``), so a session-scoped
    context would still be open when a later test module enters
    ``sync_playwright()`` — which then refuses "Sync API inside the
    asyncio loop". Closing the context with this module keeps every
    later E2E module safe."""
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


def _main_text(page) -> str:
    return page.locator("main").inner_text()


# -- the cockpit in the browser ------------------------------------------------


def test_watchlist_populates_and_streams(page, base_url) -> None:
    """The cockpit board over the real feed: Real badge, quote numbers,
    the connector-health panel and the live-stream banner."""
    page.goto(f"{base_url}/app/cockpit")
    page.get_by_role("heading", name="Live cockpit", exact=True).first.wait_for()
    page.get_by_text("Real", exact=True).first.wait_for()
    text = _main_text(page)
    for expected in ("$100.00", "$100.50", "$100.25", "49.9", "$100.30"):
        assert expected in text
    assert "Connector health" in text
    # the venue badge and the BTC source chip both report connected
    assert page.locator("main").get_by_text("connected", exact=True).count() >= 2
    assert "Local stream connected over WebSocket" in text


def test_instrument_detail_chart_book_and_tape(page, base_url) -> None:
    """Detail screen over the live stream: the SVG chart draws once two
    closes arrive on this screen's own subscription, the per-side book
    and the trade tape fill from the keep-alive cycles, and the back
    link returns to the watchlist."""
    page.goto(f"{base_url}/app/cockpit")
    page.get_by_text("Real", exact=True).first.wait_for()
    page.get_by_role("link", name="BTC", exact=True).click()
    page.get_by_role("heading", name="BTC", exact=True).first.wait_for()
    page.get_by_text("Real", exact=True).first.wait_for()  # the header badge
    # the chart card counts the closes it drew
    page.get_by_text(re.compile(r"\d+ points")).first.wait_for()
    # the per-side book from the latest l2 snapshots
    page.get_by_text("$99.50", exact=True).first.wait_for()
    text = _main_text(page)
    assert "Bids" in text and "Asks" in text
    assert "mid $100.25" in text
    assert "$100.30" in text  # the trade tape carries the latest trade
    page.get_by_role("link", name="Back to watchlist").click()
    page.get_by_role("heading", name="Live cockpit", exact=True).first.wait_for()


def test_stale_transition_when_the_venue_goes_quiet(
    page, base_url, venue_url: tuple[str, Callable[[], None]]
) -> None:
    """The venue's ``quiet`` event stops the frames (socket stays open),
    so no frame is newer than the feed's 5 s lag; a snapshot refetch
    then flips the badge to Stale — while the transport (and its
    banner) stays live and the trade sequence shows no gap. The
    transition is deterministic: the trigger, not the wall clock,
    starts the quiet tail."""
    _url, quiet_trigger = venue_url
    quiet_trigger()
    page.goto(f"{base_url}/app/cockpit")
    main = page.locator("main")
    main.get_by_text("Stale", exact=True).first.wait_for(timeout=60_000)
    text = main.inner_text()
    assert "Local stream connected over WebSocket" in text
    assert "gap" not in text.lower()


def test_keyboard_only_walk(page, base_url) -> None:
    """Keyboard-only: Tab lands focus on the watchlist, Enter activates
    the symbol link into the detail screen, and the way back is a link."""
    page.goto(f"{base_url}/app/cockpit")
    page.get_by_role("heading", name="Live cockpit", exact=True).first.wait_for()

    page.keyboard.press("Tab")
    focused = page.evaluate(
        "(() => { const el = document.activeElement;"
        " return el ? el.getAttribute('aria-label') || el.tagName : null; })()"
    )
    assert focused, "nothing is focused after the first Tab"

    link = page.get_by_role("link", name="BTC", exact=True)
    link.focus()
    link.press("Enter")
    page.get_by_role("heading", name="BTC", exact=True).first.wait_for()
    page.get_by_role("link", name="Back to watchlist").wait_for()


def test_replay_card_honestly_reports_no_lake(page, base_url) -> None:
    """The E2E workstation runs without a replay lake (the ``--live``
    assembly is what mounts one), so the recorded-replay card must fail
    closed over the real wire: honest no-lake copy and no window
    actions, never an empty table pretending a replay exists."""
    page.goto(f"{base_url}/app/cockpit")
    main = page.locator("main")
    main.get_by_text("Recorded replay", exact=True).first.wait_for()
    text = main.inner_text()
    assert "No replay lake attached" in text
    assert "Replay 5 min" not in text


def test_tablet_viewport_has_no_horizontal_overflow(browser, base_url) -> None:
    """768×1024: the cockpit board, connector health and recorded-replay
    card fit the page without pushing the body horizontally."""
    page = browser.new_page(viewport={"width": 768, "height": 1024})
    try:
        page.goto(f"{base_url}/app/cockpit")
        page.get_by_role("heading", name="Live cockpit", exact=True).first.wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "the page body overflows horizontally at 768 px"
        )
    finally:
        page.close()


def test_mobile_viewport_scrolls_the_table_not_the_body(browser, base_url) -> None:
    """390×844: the board fits the page; the wide quote table scrolls
    inside its own overflow container instead of pushing the body."""
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.goto(f"{base_url}/app/cockpit")
        page.get_by_role("heading", name="Live cockpit", exact=True).first.wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "the page body overflows horizontally at 390 px"
        )
        scrolls = page.locator("table").evaluate(
            "el => { const wrap = el.closest('.overflow-x-auto');"
            " return wrap !== null && wrap.scrollWidth > wrap.clientWidth; }"
        )
        assert scrolls, "the table container should scroll horizontally at 390 px"
    finally:
        page.close()
