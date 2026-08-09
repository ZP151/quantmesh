"""Phase E-3 browser E2E (iteration 0015): the prediction comparison
board over the real local stack, driven by Playwright chromium.

The entire wire is real and loopback-only: uvicorn serves the
workstation app with the feed and the demo prediction board attached,
the Polymarket and Kalshi supervisors talk through
``LiveHyperliquidTransport`` to two scripted fixture venues (the
wire-agnostic ``ScriptedVenue`` replays each protocol's own frame
shapes on its own ephemeral port), and the Kalshi REST book boundary
is a canned in-memory source — the exact shape the live assembly
wires, with HTTP swapped for a recorded payload. The browser walks
the comparison screen: per-pair venue rows (implied probability,
bid/ask, diff), the honest unavailable state of a single-venue pair,
the calibration link into the existing forecast surface, the stale
transition after the venues go quiet, and the keyboard + mobile
checks.

The venue plans play a burst of frames at connect, then keep every
channel fresh on a 4 s cadence for ~40 s (the window these tests run
in), then go silent for an hour with the sockets still open — the
quiet-venue condition that deterministically flips the board's
labels to Stale while the transports stay connected.

Skips cleanly when playwright or chromium is missing (the ``e2e``
extra is dev-only, ADR-0011 decision 7) and when the pinned port is
already bound, so a pipeline without the browser stays green.
"""

import asyncio
import json
import socket
import threading
import urllib.request
from datetime import timedelta
from typing import cast

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.api.workstation import create_workstation_app
from quantmesh.domain.models import Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import LiveHyperliquidTransport
from quantmesh.live.kalshi import KalshiOrderbookSource, KalshiVenueSupervisor
from quantmesh.live.polymarket import PolymarketVenueSupervisor
from quantmesh.live.prediction import demo_board
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
PORT = 8646  # 8643/8644/8645 are taken by the other suites
BASE_URL = f"http://{HOST}:{PORT}"

# The feed's freshness policy: a real quote older than the lag is
# Stale. The venues' keep-alive cadence (4 s) stays under it while
# frames flow, and the quiet tail crosses it ~5 s after the last frame.
FEED_LAG = timedelta(seconds=5)
FEED_STALE = timedelta(seconds=10)

KEEPALIVE_CYCLES = 10
KEEPALIVE_DELAY = 4.0

# A fixed frame epoch; the plans are static, so every reconnect (there
# are none in this fixture) would replay the same wire.
T0_US = 1_753_000_000_000_000

# The demo board's pairs, with the prices the plans must keep quoting.
PM_TOKENS = [
    ("0xasset-btc-100k", 0.60, 0.65),
    ("0xasset-eth-5k", 0.50, 0.54),
    ("0xasset-solo", 0.30, 0.34),
]
KALSHI_TICKERS = [
    ("KXBTD-26JUN26-1000-C", 62),
    ("KXETHD-30SEP26-5000-C", 48),
]


# -- canonical frame shapes (mirror test_live_prediction) ---------------------


def _pm_book(
    token: str, bids: list[tuple[float, float]], asks: list[tuple[float, float]], t: int
) -> dict:
    return {
        "event_type": "book",
        "asset_id": token,
        "timestamp": str(t),
        "bids": [{"price": str(p), "size": str(s)} for p, s in bids],
        "asks": [{"price": str(p), "size": str(s)} for p, s in asks],
    }


def _pm_price_change(token: str, bid: float, ask: float, t: int) -> dict:
    return {
        "event_type": "price_change",
        "asset_id": token,
        "timestamp": str(t),
        "price_changes": [
            {"side": "BUY", "price": str(bid)},
            {"side": "SELL", "price": str(ask)},
        ],
    }


def _kalshi_market(ticker: str, last: int, t: int) -> dict:
    return {
        "type": "market",
        "ticker": ticker,
        "ts": t,
        "msg": {"last_price": last, "volume": 1000, "open_interest": 500},
    }


def _kalshi_delta(ticker: str, side: str, delta: list[tuple[int, int]], t: int) -> dict:
    return {
        "type": "orderbook_delta",
        "ticker": ticker,
        "ts": t,
        "msg": {"side": side, "delta": [{"price": p, "count": c} for p, c in delta]},
    }


class _CannedKalshiBooks:
    """The Kalshi REST boundary for the E2E: recorded wire payloads per
    ticker (no HTTP — the venue fixture is local). The best levels
    produce the board numbers the browser asserts: btc-100k quotes at
    65.0 % (YES 0.62 / NO 0.32 → ask 0.68), eth-5k at 49.0 %."""

    def __init__(self) -> None:
        # Ladders are ascending worst-first — the recorded live wire
        # order _parse_levels enforces (fails closed on reorder).
        self.books = {
            "KXBTD-26JUN26-1000-C": {
                "orderbook_fp": {
                    "yes_dollars": [["0.58", "60"], ["0.62", "100"]],
                    "no_dollars": [["0.28", "40"], ["0.32", "80"]],
                }
            },
            "KXETHD-30SEP26-5000-C": {
                "orderbook_fp": {
                    "yes_dollars": [["0.44", "30"], ["0.48", "40"]],
                    "no_dollars": [["0.46", "25"], ["0.50", "20"]],
                }
            },
        }

    def orderbook(self, ticker: str) -> object:
        return self.books[ticker]


# -- the venue plans -----------------------------------------------------------


def pm_plan() -> list[tuple[float, object]]:
    """Book burst at connect, then keep-alive price changes for every
    token each cycle, then an hour of silence with the socket open."""
    plan: list[tuple[float, object]] = [
        (
            0.0,
            _pm_book(
                token,
                [(bid, 100.0), (round(bid - 0.05, 2), 200.0)],
                [(ask, 75.0), (round(ask + 0.05, 2), 50.0)],
                T0_US,
            ),
        )
        for token, bid, ask in PM_TOKENS
    ]
    for cycle in range(KEEPALIVE_CYCLES):
        t = T0_US + (cycle + 1) * 60_000_000
        for index, (token, bid, ask) in enumerate(PM_TOKENS):
            delay = KEEPALIVE_DELAY if index == 0 else 0.0
            plan.append((delay, _pm_price_change(token, bid, ask, t)))
    plan.append((3600.0, {"__cmd": "close"}))
    return plan


def kalshi_plan() -> list[tuple[float, object]]:
    """Market burst at connect (the REST seed already quotes the book),
    then per-cycle market + best-level delta churn (alternating +1/-1
    keeps the quotes fresh without moving the prices), then silence."""
    plan: list[tuple[float, object]] = [
        (0.0, _kalshi_market(ticker, last, T0_US)) for ticker, last in KALSHI_TICKERS
    ]
    for cycle in range(KEEPALIVE_CYCLES):
        t = T0_US + (cycle + 1) * 60_000_000
        sign = 1 if cycle % 2 == 0 else -1
        for index, (ticker, last) in enumerate(KALSHI_TICKERS):
            delay = KEEPALIVE_DELAY if index == 0 else 0.0
            plan.append((delay, _kalshi_market(ticker, last, t)))
            plan.append((0.0, _kalshi_delta(ticker, "yes", [(last, sign)], t)))
    plan.append((3600.0, {"__cmd": "close"}))
    return plan


# -- one scripted venue per protocol, each on its own loop --------------------


def _venue_fixture(name: str, plan: list[tuple[float, object]]):
    """The proven single-venue pattern (test_live_e2e) for one
    protocol; the sync Playwright thread cannot run the venue's loop."""

    @pytest.fixture(scope="module")
    def venue_url() -> str:
        loop = asyncio.new_event_loop()
        holder: dict[str, object] = {}
        ready = threading.Event()

        def runner() -> None:
            asyncio.set_event_loop(loop)

            async def serve() -> None:
                async with ScriptedVenue(plan=plan) as venue:
                    holder["url"] = venue.url
                    held: asyncio.Future[None] = asyncio.get_running_loop().create_future()
                    holder["held"] = held
                    ready.set()
                    await held

            loop.run_until_complete(serve())

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        if not ready.wait(timeout=10):
            raise AssertionError(f"the {name} scripted venue never came up")
        try:
            yield str(holder["url"])
        finally:
            held = holder.get("held")
            if held is not None:
                loop.call_soon_threadsafe(cast(asyncio.Future, held).cancel)
            thread.join(timeout=5)

    return venue_url


pm_venue_url = _venue_fixture("polymarket", pm_plan())
ks_venue_url = _venue_fixture("kalshi", kalshi_plan())


# -- the workstation server with the feed and the board attached --------------


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
    """The lifespan pump must have delivered the burst and the Kalshi
    REST seed before the tests start, so the comparison always carries
    both venues' probabilities for the btc-100k pair."""
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/live/prediction", timeout=1) as response:
                rows = json.loads(response.read())
        except OSError:
            rows = []
        btc = next((row for row in rows if row.get("event_key") == "btc-100k"), None)
        if btc is not None and btc.get("diff") == -2.5:
            return
        threading.Event().wait(0.1)
    raise AssertionError("the prediction board never delivered both venues")


@pytest.fixture(scope="module")
def base_url(pm_venue_url: str, ks_venue_url: str) -> str:
    if _port_in_use():
        pytest.skip(f"port {PORT} is already bound — the pinned E2E port must be free")
    account = PaperAccount(cash=100_000.0)
    feed = LiveFeed(lag=FEED_LAG, stale=FEED_STALE)
    board = demo_board()
    watchlists = board.venues()
    pm = PolymarketVenueSupervisor(LiveHyperliquidTransport(pm_venue_url))
    pm.subscribe(watchlists[Venue.POLYMARKET])
    feed.attach(pm)
    ks = KalshiVenueSupervisor(
        LiveHyperliquidTransport(ks_venue_url),
        book_source=KalshiOrderbookSource(_CannedKalshiBooks()),
    )
    ks.subscribe(watchlists[Venue.KALSHI])
    feed.attach(ks)
    app = create_workstation_app(account=account, live_feed=feed, prediction=board, host=HOST)
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


# -- the comparison board in the browser ---------------------------------------


def test_comparison_renders_both_venues(page, base_url) -> None:
    """The board over the real feed: per-venue implied probabilities,
    the signed cross-venue diffs, quote numbers and the calibration
    link into the existing forecast surface."""
    page.goto(f"{base_url}/app/prediction")
    page.get_by_role("heading", name="Prediction markets", exact=True).first.wait_for()
    page.get_by_text("62.5%", exact=True).first.wait_for()
    text = _main_text(page)
    for expected in (
        "BTC above $100k on 2026-06-26",
        "62.5%",
        "65.0%",
        "-2.5 pp",
        "ETH above $5,000 on 2026-09-30",
        "52.0%",
        "49.0%",
        "+3.0 pp",
        "$0.60 / $0.65",
        "$0.62 / $0.68",
        "Polymarket − Kalshi",
    ):
        assert expected in text
    # every venue row is real while the plans stream
    assert page.locator("main").get_by_text("Real", exact=True).count() == 5
    # the calibration surface exists already; the board links to it,
    # never re-fabricating a calibration number here
    href = page.get_by_role("link", name="Calibration & forecast history").get_attribute("href")
    assert href == "/app/research/forecasts"


def test_single_venue_pair_renders_honest_unavailable(page, base_url) -> None:
    """The solo Polymarket pair has no Kalshi symbol configured: its
    Kalshi side renders an honest dash and the Unavailable label —
    never a fabricated probability — and the pair has no diff."""
    page.goto(f"{base_url}/app/prediction")
    page.get_by_text("Solo Polymarket pair (Kalshi unconfigured)").first.wait_for()
    text = _main_text(page)
    assert "32.0%" in text  # the real Polymarket side
    assert "Unavailable" in text  # the honest absent Kalshi side
    assert "0.34" in text  # the real side's ask still renders


def test_stale_transition_when_the_venues_go_quiet(page, base_url) -> None:
    """After the plans' quiet tail starts, no frame is newer than the
    feed's 5 s lag, so a snapshot refetch flips the board's labels to
    Stale — while the transports stay connected and the numbers (the
    last real quotes) stay visible, honestly labeled."""
    page.goto(f"{base_url}/app/prediction")
    main = page.locator("main")
    main.get_by_text("Stale", exact=True).first.wait_for(timeout=60_000)
    text = main.inner_text()
    assert "62.5%" in text  # the last real numbers remain, labeled stale


def test_keyboard_walk_to_calibration(page, base_url) -> None:
    """Keyboard-only: the calibration link is focusable and Enter
    activates it into the forecast surface."""
    page.goto(f"{base_url}/app/prediction")
    page.get_by_role("heading", name="Prediction markets", exact=True).first.wait_for()
    link = page.get_by_role("link", name="Calibration & forecast history")
    link.focus()
    link.press("Enter")
    page.get_by_role("heading", name="Forecasts", exact=True).first.wait_for()


def test_mobile_viewport_stacks_the_pairs(browser, base_url) -> None:
    """390×844: the board fits the page; the venue blocks stack in the
    single column instead of pushing the body wide."""
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.goto(f"{base_url}/app/prediction")
        page.get_by_role("heading", name="Prediction markets", exact=True).first.wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "the page body overflows horizontally at 390 px"
        )
    finally:
        page.close()
