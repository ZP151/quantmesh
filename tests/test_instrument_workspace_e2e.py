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
from pathlib import Path

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.demo.runtime import create_demo_app

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is not installed (install the e2e extra)",
)

HOST = "127.0.0.1"
WORKSPACE_PATH = "/app/instruments/moomoo/NVDA?range=6m"


def _wait_for_server(server: uvicorn.Server) -> None:
    for _ in range(600):
        if server.started:
            return
        threading.Event().wait(0.1)
    raise AssertionError("uvicorn never started on its reserved loopback socket")


@pytest.fixture(scope="module", autouse=True)
def _spa_surface() -> None:
    prior = workstation.settings.legacy_ui
    workstation.settings.legacy_ui = False
    yield
    workstation.settings.legacy_ui = prior


@pytest.fixture(scope="module")
def base_url(tmp_path_factory) -> str:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    root = Path(tmp_path_factory.mktemp("instrument-workspace-e2e")) / "demo"
    app = create_demo_app(root=root, host=HOST)
    # Task 2 closes the configured direct-proposal bypass. This pre-Task-3
    # browser regression deliberately exercises the legacy unconfigured
    # proposal client; Task 3 replaces it with the packet action API.
    app.state.decision_packet_service = None
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
    reset = page.get_by_role("button", name="Reset demo session")
    reset.click()
    page.get_by_text("Confirm reset", exact=True).wait_for()
    with page.expect_response(
        lambda response: response.url.endswith("/api/demo/reset"),
        timeout=90_000,
    ) as response:
        reset.click()
    assert response.value.status == 200


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

    # Authoritative refetch preserves success evidence until the operator
    # explicitly starts a distinct second intent.
    page.get_by_role("button", name="Start another paper proposal").click()
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
