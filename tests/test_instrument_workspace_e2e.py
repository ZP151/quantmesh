"""Browser acceptance for the integrated instrument decision workspace.

The suite uses the same deterministic demo assembly as the operator command and
drives the packaged React bundle over a real uvicorn socket. It proves the
inspect-to-paper loop, the race-time kill-switch refusal, reset recovery,
keyboard operation, Simplified-Chinese rendering, reduced motion, and the
390 px responsive boundary.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.demo.runtime import create_demo_app

playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is not installed (install the e2e extra)",
)
playwright_expect = playwright.expect

HOST = "127.0.0.1"
WORKSPACE_PATH = "/app/instruments/moomoo/NVDA?range=6m"


def _wait_for_server(server: uvicorn.Server) -> None:
    for _ in range(600):
        if server.started:
            return
        threading.Event().wait(0.1)
    raise AssertionError("uvicorn never started on its reserved loopback socket")


class _PackagedDemo:
    """One packaged-app socket that can be rebuilt over the same durable root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.port = 0
        self.app = None
        self.server = None
        self.thread = None
        self.listener = None
        self._start()

    def __str__(self) -> str:
        return f"http://{HOST}:{self.port}"

    def _start(self) -> None:
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, self.port))
        listener.listen(128)
        self.port = listener.getsockname()[1]
        app = create_demo_app(root=self.root, host=HOST)
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=self.port, log_level="warning"))
        thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [listener]},
            daemon=True,
        )
        self.app = app
        self.server = server
        self.thread = thread
        self.listener = listener
        thread.start()
        _wait_for_server(server)

    def close(self) -> None:
        if self.server is None or self.thread is None or self.listener is None:
            return
        self.server.should_exit = True
        self.thread.join(timeout=15)
        self.listener.close()
        self.server = None
        self.thread = None
        self.listener = None

    def restart(self) -> None:
        self.close()
        self._start()


class _OneSymbolFailureWorkspace:
    def __init__(self, delegate, symbol: str) -> None:
        self.delegate = delegate
        self.symbol = symbol

    def render(self, venue, symbol, selected_range, *, peers=()):
        if symbol == self.symbol:
            raise OSError("bounded local acceptance failure")
        return self.delegate.render(venue, symbol, selected_range, peers=peers)


@pytest.fixture(scope="module", autouse=True)
def _spa_surface() -> None:
    prior = workstation.settings.legacy_ui
    workstation.settings.legacy_ui = False
    yield
    workstation.settings.legacy_ui = prior


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    root = Path(tmp_path_factory.mktemp("instrument-workspace-e2e")) / "demo"
    runtime = _PackagedDemo(root)
    try:
        yield runtime
    finally:
        runtime.close()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch()
        except Exception as error:
            pytest.skip(f"chromium is not installed ({error})")
        yield launched
        launched.close()


@pytest.fixture()
def page(browser):
    opened = browser.new_page()
    yield opened
    opened.close()


def _proposal_token(page) -> str:
    token = (
        page.get_by_text("Displayed confirmation token", exact=True)
        .locator("..")
        .locator("code")
        .inner_text()
    )
    assert re.fullmatch(r"[0-9a-f]{64}", token)
    return token


def _reset_from_shell(page) -> None:
    reset = page.get_by_role(
        "button",
        name=re.compile(r"^(?:Reset demo session|重置演示会话)$"),
    )
    reset.click()
    # The confirmation copy remains mounted but is visually hidden below the
    # shell's ``sm`` breakpoint; attachment still proves the armed state was
    # committed before the second activation.
    page.get_by_text(
        re.compile(r"^(?:Confirm reset|确认重置)$"),
    ).wait_for(state="attached")
    with page.expect_response(
        lambda response: response.url.endswith("/api/demo/reset"),
        timeout=90_000,
    ) as response:
        reset.click()
    assert response.value.status == 200


def _save_registered_watch(
    page,
    base_url: _PackagedDemo,
    symbol: str,
) -> str:
    page.goto(f"{base_url}/app/instruments/moomoo/{symbol}?range=6m")
    page.get_by_role("heading", name=symbol, exact=True).wait_for()
    page.get_by_label("Decision reason").fill(f"Keep this exact {symbol} packet under watch")
    page.get_by_role("button", name="Watch decision").click()
    page.get_by_text("Watching", exact=True).wait_for()
    packet_match = re.search(r"[?&]packet=([^&]+)", page.url)
    assert packet_match is not None
    packet_id = packet_match.group(1)
    with page.expect_response(
        lambda response: (
            response.request.method == "POST" and response.url.endswith("/watch-conditions")
        ),
        timeout=90_000,
    ) as response:
        page.get_by_role("button", name="Save & check", exact=True).click()
    assert response.value.status == 200
    page.get_by_role("button", name="Check now", exact=True).wait_for()
    return packet_id


def test_nvda_inspect_to_paper_loop_and_race_refusal(page, base_url) -> None:
    page.goto(f"{base_url}{WORKSPACE_PATH}")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    main = page.get_by_role("main")

    # URL-backed observed market controls and API-produced comparison.
    page.get_by_role("button", name="1M", exact=True).click()
    page.wait_for_url(re.compile(r"range=1m"))
    page.get_by_role("button", name="Line", exact=True).click()
    assert "mode=line" in page.url
    page.get_by_role("button", name="Volume", exact=True).click()
    page.get_by_role("button", name="SMA 20", exact=True).click()
    page.get_by_role("textbox", name="Comparison instrument").fill("moomoo:AAPL")
    page.get_by_role("button", name="Add comparison").click()
    page.wait_for_url(re.compile(r"compare=moomoo%3AAAPL"))
    page.get_by_text(re.compile(r"Indexed to 100")).wait_for()
    chart_table = page.get_by_role("table", name=re.compile(r"NVDA chart data"))
    assert "moomoo:AAPL" in chart_table.inner_text()

    # Forecast quality and immutable lineage are inspectable before action.
    assert "30 sessions" in main.inner_text()
    assert "last-price-random-walk" in main.inner_text()
    assert "Dataset revision" in main.inner_text()
    assert "Config digest" in main.inner_text()
    assert "History digest" in main.inner_text()

    # Return to the evidence-backed 6m packet before creating a proposal; the
    # 1m chart exploration above has no matching promoted forecast and must
    # remain fail-closed for Paper.
    page.get_by_role("button", name="6M", exact=True).click()
    page.wait_for_url(re.compile(r"range=6m"))
    page.get_by_text("Ready to decide", exact=True).wait_for()

    # Stage one creates only a preview; stage two requires the exact token.
    page.get_by_label("Quantity", exact=True).fill("10")
    page.get_by_role("button", name="Create paper proposal").click()
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    assert "moomoo" in main.inner_text()
    assert "NVDA" in main.inner_text()
    token = _proposal_token(page)
    confirm = page.get_by_role("button", name="Confirm paper proposal")
    assert confirm.is_disabled()
    page.get_by_label("Confirmation token").fill(token)
    assert confirm.is_enabled()
    confirm.click()
    page.get_by_text("Paper order created", exact=True).wait_for()
    assert "Filled" in main.inner_text()
    assert "demo-synthetic" in main.inner_text()
    audit_link = page.get_by_role("link", name="Open audit lineage")
    assert "/ops/audit?order=" in (audit_link.get_attribute("href") or "")

    # A distinct race-time intent starts from a reset DecisionPacket lineage;
    # the prior immutable packet already owns its one terminal child.
    _reset_from_shell(page)
    page.goto(f"{base_url}{WORKSPACE_PATH}")
    page.get_by_role("button", name="Create paper proposal").wait_for()
    assert "Unavailable" not in page.get_by_text("Unrealized P&L").locator("..").inner_text()
    assert "Disarmed" in page.get_by_text("Global kill switch").locator("..").inner_text()
    page.get_by_label("Quantity", exact=True).fill("11")
    page.get_by_role("button", name="Create paper proposal").click()
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    race_token = _proposal_token(page)

    # Engage after preview: confirmation is re-evaluated by the kernel and
    # returns the typed 409 refusal. The browser never supplies that verdict.
    page.goto(f"{base_url}/app/ops/kill-switch")
    page.get_by_role("heading", name="Kill switch", exact=True).first.wait_for()
    page.get_by_role("button", name="Engage global kill switch").click()
    page.get_by_role("button", name="Disarm global kill switch").wait_for()
    page.goto(f"{base_url}{WORKSPACE_PATH}")
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    page.get_by_label("Confirmation token").fill(race_token)
    with page.expect_response(
        lambda response: "/api/paper/proposals/" in response.url
        and response.url.endswith("/confirm")
    ) as refused:
        page.get_by_role("button", name="Confirm paper proposal").click()
    assert refused.value.status == 409
    page.get_by_text(re.compile(r"kill switch", re.IGNORECASE)).last.wait_for()
    assert page.get_by_role("button", name="Confirm paper proposal").is_disabled()

    # Product reset clears proposal/order mutations and restores safety state.
    _reset_from_shell(page)
    page.goto(f"{base_url}/app/ops/kill-switch")
    page.get_by_role("button", name="Engage global kill switch").wait_for()
    page.goto(f"{base_url}{WORKSPACE_PATH}")
    page.get_by_role("button", name="Create paper proposal").wait_for()


def test_mobile_daily_session_refreshes_and_reopens_exact_packet_after_restart(
    page,
    base_url: _PackagedDemo,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/app/settings")
    _reset_from_shell(page)
    packet_ids = {
        symbol: _save_registered_watch(page, base_url, symbol) for symbol in ("NVDA", "AAPL")
    }

    started = time.perf_counter()
    page.goto(f"{base_url}/app/markets/watchlist")
    page.get_by_role("heading", name="Watchlist", exact=True).first.wait_for()
    page.get_by_role("button", name="All 4", exact=True).wait_for()
    assert page.get_by_text(re.compile(r"Readiness evaluated")).first.is_visible()
    assert page.get_by_text(re.compile(r"Last local check")).first.is_visible()
    assert page.get_by_text("unavailable", exact=True).first.is_visible()
    main_text = page.get_by_role("main").inner_text()
    assert re.search(r"\b(provider|OpenD|automatic|real(?:-money)?)\b", main_text, re.I) is None

    refresh = page.get_by_role("button", name="Refresh session", exact=True)
    refresh.focus()
    with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and response.url.endswith("/api/decision-session/refresh")
        ),
        timeout=90_000,
    ) as response:
        page.keyboard.press("Enter")
    assert response.value.status == 200
    page.get_by_text("2 watches checked · 0 triggered", exact=True).wait_for()
    playwright_expect(refresh).to_be_focused()

    no_action = page.get_by_role("button", name="No action 2", exact=True)
    no_action.focus()
    page.keyboard.press("Enter")
    assert no_action.get_attribute("aria-pressed") == "true"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    row = page.get_by_role("row").filter(has_text="NVDA")
    exact_link = row.get_by_role("link", name="Open exact packet", exact=True)
    expected_path = f"/app/instruments/moomoo/NVDA?range=6m&packet={packet_ids['NVDA']}"
    assert exact_link.get_attribute("href") == expected_path
    exact_link.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"{base_url}{expected_path}")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    elapsed = time.perf_counter() - started
    assert elapsed < 120
    print(f"TASK4B_USER_FLOW_SECONDS={elapsed:.3f}")

    base_url.restart()
    page.goto(f"{base_url}/app/markets/watchlist")
    page.get_by_role("heading", name="Watchlist", exact=True).first.wait_for()
    restarted_row = page.get_by_role("row").filter(has_text="NVDA")
    assert (
        restarted_row.get_by_role("link", name="Open exact packet", exact=True).get_attribute(
            "href"
        )
        == expected_path
    )
    assert page.get_by_text(re.compile(r"Last local check")).first.is_visible()

    restarted_workspace = base_url.app.state.instrument_workspace
    base_url.app.state.instrument_workspace = _OneSymbolFailureWorkspace(
        restarted_workspace,
        "AAPL",
    )
    with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and response.url.endswith("/api/decision-session/refresh")
        ),
        timeout=90_000,
    ) as partial_response:
        page.get_by_role("button", name="Refresh session", exact=True).click()
    assert partial_response.value.status == 200
    page.get_by_text("1 of 2 watches checked", exact=True).wait_for()
    failures = page.get_by_label("Watches not evaluated")
    assert failures.get_by_text(packet_ids["AAPL"], exact=True).is_visible()
    assert failures.get_by_text("Local workspace is unavailable.", exact=True).is_visible()

    base_url.app.state.instrument_workspace = restarted_workspace
    page.goto(f"{base_url}/app/settings")
    page.get_by_label("Interface language").select_option("zh-CN")
    page.get_by_role("heading", name="全局设置", exact=True).first.wait_for()
    page.goto(f"{base_url}/app/markets/watchlist")
    page.get_by_role("heading", name="自选", exact=True).first.wait_for()
    chinese_refresh = page.get_by_role("button", name="刷新会话", exact=True)
    chinese_refresh.focus()
    with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and response.url.endswith("/api/decision-session/refresh")
        ),
        timeout=90_000,
    ) as chinese_response:
        page.keyboard.press("Enter")
    assert chinese_response.value.status == 200
    page.get_by_text("已检查 2 个观察 · 已触发 0 个", exact=True).wait_for()
    assert chinese_refresh.evaluate("element => element === document.activeElement")
    assert page.get_by_role("button", name="受阻 2", exact=True).is_visible()
    assert page.get_by_text(re.compile(r"上次本地检查")).first.is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    chinese_text = page.get_by_role("main").inner_text()
    assert re.search(r"\b(provider|OpenD|automatic|real(?:-money)?)\b", chinese_text, re.I) is None

    _reset_from_shell(page)


def test_keyboard_locale_reduced_motion_and_mobile_boundary(browser, base_url) -> None:
    context = browser.new_context(
        reduced_motion="reduce",
        viewport={"width": 390, "height": 844},
    )
    page = context.new_page()
    try:
        page.goto(f"{base_url}/app/settings")
        page.get_by_label("Interface language").select_option("zh-CN")
        page.get_by_role("heading", name="全局设置", exact=True).first.wait_for()
        page.goto(f"{base_url}{WORKSPACE_PATH}")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()

        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.get_by_role("main").count() == 1
        page.get_by_role("img", name=re.compile("NVDA 市场图表")).wait_for()
        page.get_by_role("table", name=re.compile("NVDA 图表数据")).wait_for()
        assert "30 个交易日" in page.get_by_role("main").inner_text()
        assert "创建模拟提案" in page.get_by_role("main").inner_text()

        # Keyboard activation keeps the same URL-backed control semantics.
        range_button = page.get_by_role("button", name="1M", exact=True)
        range_button.focus()
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r"range=1m"))
        focused_style = range_button.evaluate(
            "element => { const style = getComputedStyle(element); "
            "return { boxShadow: style.boxShadow, outline: style.outlineStyle, "
            "transitionSeconds: Math.max(0, ...style.transitionDuration.split(',').map(value => { "
            "const duration = value.trim(); "
            "return duration.endsWith('ms') ? parseFloat(duration) / 1000 : parseFloat(duration); "
            "}).filter(Number.isFinite)) }; }"
        )
        assert focused_style["boxShadow"] != "none" or focused_style["outline"] != "none"
        assert focused_style["transitionSeconds"] <= 0.001

        line = page.get_by_role("button", name="折线", exact=True)
        line.focus()
        page.keyboard.press("Enter")
        assert "mode=line" in page.url
        volume = page.get_by_role("button", name="成交量", exact=True)
        volume.focus()
        page.keyboard.press("Enter")
        assert "volume=1" in page.url
    finally:
        context.close()
