"""Packaged live charts: loopback feed/replay through both instrument entry paths.

The clock and normalized observations are deterministic. No external provider,
HTTP mocking, paper action, or order path participates in this browser witness.
"""

from __future__ import annotations

import json
import re
import socket
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.directory import build_live_market_directory
from quantmesh.live.feed import LiveFeed

playwright = pytest.importorskip("playwright.sync_api", reason="the e2e extra is unavailable")
expect = playwright.expect
HOST = "127.0.0.1"
SYMBOLS = ("BTC", "ETH", "SOL")


class _ChartStation:
    def __init__(self, root: Path):
        self.anchor = datetime.now(UTC).replace(second=0, microsecond=0)
        self.now = self.anchor + timedelta(seconds=10)
        self.buffer = LiveBuffer(root)
        self.feed = LiveFeed(lake=self.buffer)
        for symbol in SYMBOLS:
            self.feed.ingest(
                [
                    self.candle(symbol, self.anchor - timedelta(minutes=1), 100),
                    self.candle(symbol, self.anchor, 101),
                    MarketUpdate(
                        venue="hyperliquid",
                        instrument=symbol,
                        kind=UpdateKind.QUOTE,
                        provenance=Provenance.REAL,
                        data_time=self.now,
                        received_at=self.now,
                        payload={"bid": 100, "ask": 102, "bid_size": 1, "ask_size": 2},
                    ),
                ]
            )
        self.listener = socket.socket()
        self.listener.bind((HOST, 0))
        self.listener.listen(128)
        self.port = self.listener.getsockname()[1]
        self.app = create_workstation_app(
            account=PaperAccount(cash=100_000),
            live_feed=self.feed,
            markets=build_live_market_directory(hyperliquid_symbols=SYMBOLS),
            workspace_clock=lambda: self.now,
            host=HOST,
        )
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host=HOST,
                port=self.port,
                log_level="warning",
                timeout_graceful_shutdown=1,
            )
        )
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.listener]}, daemon=True
        )
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            if not self.thread.is_alive():
                raise AssertionError("packaged live chart station exited during startup")
            threading.Event().wait(0.05)
        else:
            self.close()
            raise AssertionError("packaged live chart station did not start")

    @property
    def url(self):
        return f"http://{HOST}:{self.port}"

    def candle(self, symbol: str, opened: datetime, close: float):
        return MarketUpdate(
            venue="hyperliquid",
            instrument=symbol,
            kind=UpdateKind.CANDLE,
            provenance=Provenance.REAL,
            data_time=opened,
            received_at=self.now,
            sequence=int(opened.timestamp() * 1000),
            payload={
                "interval": "1m",
                "open": 100,
                "high": 110,
                "low": 90,
                "close": close,
                "volume": 10,
                "final": False,
            },
        )

    def publish(self, *, append: bool = False):
        opened = self.anchor + timedelta(minutes=1) if append else self.anchor
        self.now = opened + timedelta(seconds=20 if append else 15)
        self.feed.publish_threadsafe(self.candle("BTC", opened, 103 if append else 102))

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=8)
        self.listener.close()
        self.buffer.close()
        assert not self.thread.is_alive(), "isolated chart station failed to stop"


@pytest.fixture
def chart_station(tmp_path, monkeypatch):
    monkeypatch.setattr(workstation.settings, "legacy_ui", False)
    station = _ChartStation(tmp_path / "live-chart-replay")
    try:
        yield station
    finally:
        station.close()


@pytest.fixture
def chart_page():
    with playwright.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except Exception as error:
            pytest.skip(f"chromium is unavailable ({error})")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(12_000)
        try:
            yield page
        finally:
            page.close()
            browser.close()


def _close_cells(page, symbol):
    table = page.get_by_role("table", name=f"{symbol} chart data", exact=True)
    return (
        table.get_by_role("row")
        .filter(
            has=page.get_by_role("cell", name="Observed close", exact=True),
        )
        .locator("td:nth-child(3)")
    )


def _open_live_symbol(page, station, surface, symbol):
    page.goto(f"{station.url}/app/{surface}")
    live = page.get_by_role("region", name="Live instruments", exact=True)
    expect(live).to_be_visible()
    link = live.get_by_role("link", name=symbol, exact=True)
    expect(link).to_have_attribute(
        "href", f"/app/instruments/hyperliquid/{symbol}?range=1d&mode=line"
    )
    link.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(rf"/app/instruments/hyperliquid/{symbol}\?range=1d&mode=line$"))
    expect(page.get_by_role("img", name=f"{symbol} market chart", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Line", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(_close_cells(page, symbol)).to_have_text(["100", "101"])
    expect(page.get_by_text("WebSocket", exact=True)).to_be_visible()


def test_packaged_live_charts_update_and_replay_from_both_entry_paths(chart_station, chart_page):
    station, page = chart_station, chart_page
    streamed = []

    def watch_socket(ws):
        assert ws.url == f"ws://{HOST}:{station.port}/api/live/ws"
        ws.on("framereceived", lambda payload: streamed.append(json.loads(payload)))

    page.on("websocket", watch_socket)
    _open_live_symbol(page, station, "markets", "BTC")
    initial_url = page.url
    station.publish()
    expect(_close_cells(page, "BTC")).to_have_text(["100", "102"])
    assert page.url == initial_url
    assert any(
        row["instrument"] == "BTC" and row["kind"] == "candle" and row["payload"]["close"] == 102
        for row in streamed
    )

    station.publish(append=True)
    expect(_close_cells(page, "BTC")).to_have_text(["100", "102", "103"])
    assert page.url == initial_url
    payload = page.request.get(
        f"{station.url}/api/instruments/hyperliquid/BTC/history?range=1d",
    ).json()["primary"]
    assert payload["resolution_fallback"] == "5m->1m"
    assert payload["source"] == "hyperliquid-live-replay"
    assert payload["coverage"]["rows"] == 3
    assert [bar["close"] for bar in payload["bars"]] == [100, 102, 103]

    candles = page.get_by_role("button", name="Candles", exact=True)
    candles.focus()
    page.keyboard.press("Enter")
    expect(candles).to_have_attribute("aria-pressed", "true")
    line = page.get_by_role("button", name="Line", exact=True)
    line.focus()
    page.keyboard.press("Space")
    expect(line).to_have_attribute("aria-pressed", "true")
    page.reload()
    expect(_close_cells(page, "BTC")).to_have_text(["100", "102", "103"])
    expect(page.get_by_role("button", name="Line", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )

    _open_live_symbol(page, station, "markets/watchlist", "ETH")
    _open_live_symbol(page, station, "markets/watchlist", "SOL")
    assert station.app.state.account_store.get().cash == 100_000
