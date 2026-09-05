"""Phase E SPA E2E (iteration 0014): the React app over a real demo
runtime, driven by Playwright chromium.

The suite boots uvicorn on an OS-reserved loopback socket over a fresh demo
root (``create_demo_app`` — the same assembly the operator starts with
``--demo``, datalink routes included) and walks the Phase E checklist in
the browser: the complete demo paper workflow, the provider-failure
fallback on the connectors screen, CSV import validation with rejection
reasons, and the two-click reset. It skips cleanly when playwright or
chromium is missing (the ``e2e`` extra is dev-only, ADR-0011 decision 7)
and when the browser is unavailable, so a pipeline without the browser
stays green. Reserving the socket before starting uvicorn avoids a
check-then-bind race with another process on shared CI runners.
"""

import hashlib
import json
import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import pytest
import uvicorn
from fastapi import FastAPI

from quantmesh.ai.decisions import ModelMeta
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.api import workstation
from quantmesh.demo.datalink import ConnectorState, DatalinkService
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.hyperliquid.errors import HyperliquidSDKMissingError
from quantmesh.instruments.copilot import PacketCopilotService

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
SCENARIO = DemoScenario()


@dataclass(frozen=True)
class _DemoStation:
    app: FastAPI
    root: Path
    url: str


@contextmanager
def _serve_restarted_demo(root: Path):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    app = create_demo_app(root=root, host=HOST)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    try:
        _wait_for_server(server)
        yield _DemoStation(app=app, root=root, url=f"http://{HOST}:{port}")
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()


class _MissingSdkTransport:
    """Deterministic public-data failure for the browser fallback walk."""

    def l2_book(self, symbol: str, *, at=None) -> dict:
        raise HyperliquidSDKMissingError("SDK intentionally unavailable in SPA E2E")

    def candles(self, symbol, interval, *, start, end):
        raise NotImplementedError

    def funding_history(self, symbol, *, start, end):
        raise NotImplementedError

    def meta(self) -> dict:
        raise NotImplementedError

    def spot_meta(self) -> dict:
        raise NotImplementedError


def _offline_moomoo_probe() -> ConnectorState:
    return ConnectorState(
        venue="moomoo",
        kind="execution-sim",
        mode="sandbox",
        credentials_required=True,
        read_only=False,
        wired=False,
        state="unavailable",
        detail="Offline deterministic SPA E2E probe; no OpenD contact.",
    )


def _wait_for_server(server: uvicorn.Server) -> None:
    for _ in range(400):  # seeding a demo root can take ~40 s
        if server.started:
            return
        threading.Event().wait(0.1)
    raise AssertionError("uvicorn never came up on its reserved loopback socket")


@pytest.fixture(scope="session")
def demo_station(tmp_path_factory) -> _DemoStation:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    root = Path(tmp_path_factory.mktemp("spa-e2e")) / "demo"
    app = create_demo_app(root=root, host=HOST)
    app.state.datalink = DatalinkService(
        root=app.state.demo.root,
        rest=_MissingSdkTransport(),
        moomoo_probe=_offline_moomoo_probe,
    )
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    try:
        _wait_for_server(server)
        yield _DemoStation(app=app, root=root, url=f"http://{HOST}:{port}")
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()


@pytest.fixture(scope="session")
def base_url(demo_station: _DemoStation) -> str:
    return demo_station.url


@pytest.fixture(scope="module")
def browser():
    """Module scope on purpose: an open ``sync_playwright()`` context
    keeps its asyncio loop *running* on the main thread (the dispatcher
    greenlet parks inside ``run_until_complete``), so a session-scoped
    context would still be open when a later test module enters
    ``sync_playwright()`` — which then refuses "Sync API inside the
    asyncio loop" (the Phase F gate caught exactly this). Closing the
    context with this module keeps every later E2E module safe."""
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


def _wait_demo_attached(page) -> None:
    """The shell's provenance line switches from the operator-mode
    placeholder once the demo-status query settles."""
    page.get_by_text("Deterministic paper session", exact=False).first.wait_for()


def _reset_demo(page, base_url: str) -> None:
    response = page.request.post(f"{base_url}/api/demo/reset")
    assert response.status == 200


def _decision_packet_id(page) -> str:
    packet_id = page.locator('code[title^="packet-"]').first.inner_text()
    assert packet_id.startswith("packet-")
    return packet_id


def _proposal_id(page) -> str:
    proposal_id = (
        page.get_by_label("Decision rail")
        .get_by_text("Proposal ID", exact=True)
        .locator("..")
        .locator("dd")
        .inner_text()
    )
    assert proposal_id.startswith("proposal-")
    return proposal_id


def _packet_fact(packet: dict, pointer: str) -> object:
    value: object = packet
    for part in pointer.removeprefix("/").split("/"):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _packet_citation(packet: dict, pointer: str) -> dict[str, object]:
    value = _packet_fact(packet, pointer)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "source_kind": "packet",
        "source_id": packet["packet_id"],
        "span": None,
        "json_pointer": pointer,
        "value_digest": hashlib.sha256(encoded).hexdigest(),
    }


def _copilot_script(packet: dict) -> tuple[list[dict], list[dict]]:
    def item(text: str, pointer: str) -> dict[str, object]:
        return {"text": text, "citations": [_packet_citation(packet, pointer)]}

    report = {
        "packet_id": packet["packet_id"],
        "base_explanation": item(
            "The stored market structure is the base evidence.",
            "/market_state/trend",
        ),
        "bull_challenge": item(
            "The bull case still requires its stored trigger.",
            "/scenarios/0/trigger",
        ),
        "bear_challenge": item(
            "The bear scenario remains a contrary case.",
            "/scenarios/2/thesis",
        ),
        "evidence_gaps_or_contradictions": [
            item(
                "The packet names the limits of its history evidence.",
                "/evidence/history_limitations",
            )
        ],
        "limitations": [item("Scenario confidence is packet-bounded.", "/scenarios/1/confidence")],
        "operator_questions": [item("Will the stored support hold?", "/market_state/support")],
    }
    critic = {
        "packet_id": packet["packet_id"],
        "verdict": "pass",
        "flagged_items": [],
    }
    return (
        [{"content": json.dumps(report, sort_keys=True)}],
        [{"content": json.dumps(critic, sort_keys=True)}],
    )


def test_demo_paper_workflow_through_the_ui(page, base_url) -> None:
    """The complete loop in the browser: overview evidence -> paper
    order -> fill -> positions/P&L -> audit lineage."""
    page.goto(f"{base_url}/app/")
    _wait_demo_attached(page)
    page.get_by_text("hyperliquid", exact=False).first.wait_for()
    text = _main_text(page)
    assert "Deterministic paper session" in text

    # Paper order: hyperliquid SOL-USD BUY 10 through the real pipeline.
    page.goto(f"{base_url}/app/trading/order")
    page.get_by_role("heading", name="Paper order", exact=True).first.wait_for()
    page.get_by_label("Venue").select_option("hyperliquid")
    page.get_by_label("Symbol").select_option("SOL-USD")
    page.get_by_label("Quantity").fill("10")
    page.get_by_role("button", name="Submit paper order").click()
    page.get_by_text("filled", exact=False).first.wait_for()
    order_text = _main_text(page)
    assert "paper-" in order_text

    # Positions: the SOL fill landed. (The order result card and the
    # sidebar both carry a Positions link — scope to the screen.)
    main = page.get_by_role("main")
    main.get_by_role("link", name="Positions", exact=True).click()
    page.get_by_role("heading", name="Positions", exact=True).first.wait_for()
    page.get_by_text("SOL", exact=False).first.wait_for()

    # P&L advanced and the audit trail holds the order. (The Positions
    # screen only links to the order ticket, so the sidebar carries the
    # onward navigation.)
    page.get_by_role("link", name="P&L", exact=True).click()
    page.get_by_role("heading", name="P&L", exact=True).first.wait_for()
    page.get_by_role("link", name="Audit", exact=True).click()
    page.get_by_role("heading", name="Audit", exact=True).first.wait_for()
    assert "order" in _main_text(page)


def test_connector_panel_and_provider_failure(page, base_url) -> None:
    """Connectors render diagnostics for every venue; the public fetch
    degrades deterministically into a labeled synthetic fallback (the
    vendored SDK is absent in this environment)."""
    page.goto(f"{base_url}/app/ops/connectors")
    page.get_by_role("heading", name="Connectors", exact=True).first.wait_for()
    _wait_demo_attached(page)
    text = _main_text(page)
    for venue in ("demo", "Hyperliquid", "Moomoo", "polymarket", "kalshi"):
        assert venue in text

    # Probe all: hyperliquid reports the missing-software degraded state.
    page.get_by_role("button", name="Probe all").click()
    page.get_by_text("Missing software", exact=False).first.wait_for()
    assert "degraded" in _main_text(page)

    # Public fetch: select one symbol, then the fallback rows arrive
    # labeled synthetic with the degraded reason.
    page.get_by_role("button", name="BTC-USD", exact=True).click()
    page.get_by_role("button", name="Fetch 1 snapshot").click()
    page.get_by_text("fixture-fallback", exact=False).first.wait_for()
    fallback_text = _main_text(page)
    assert "missing-software" in fallback_text
    assert "synthetic" in fallback_text.lower()


def test_data_catalog_populated_state_has_no_mobile_overflow(page, base_url) -> None:
    """The package-served route remains bounded with production-length
    manifest, report, checkpoint and run identities at the minimum viewport."""
    manifest_id = "a" * 64
    report_id = "b" * 64
    run_id = "c" * 64
    entry = {
        "adjustment_policy": "split-adjusted-v1",
        "calendar_version": "XNYS-2026a",
        "canonical_instrument": "moomoo:AAPL",
        "compatibility_revision": 2,
        "current_manifest_id": manifest_id,
        "data_kind": "bars",
        "dataset_id": "moomoo-aapl-1d",
        "entitlement": "available",
        "event_end": "2026-08-13T20:00:00Z",
        "event_start": "2026-08-01T13:30:00Z",
        "interval": "1d",
        "is_current": True,
        "knowledge_end": "2026-08-13T20:05:00Z",
        "knowledge_start": "2026-08-01T13:35:00Z",
        "latest_checkpoint": {
            "attempt": 1,
            "generation": 4,
            "job_id": "d" * 64,
            "last_complete_source_event": "2026-08-13T20:00:00Z",
            "provider_cursor": "cursor-42",
            "quality_report_id": report_id,
            "run_id": run_id,
            "updated_at": "2026-08-13T20:06:00Z",
        },
        "layer": "adjusted",
        "manifest_id": manifest_id,
        "object_digests": ["e" * 64],
        "parent_manifest_ids": ["f" * 64],
        "provider_access": "authenticated-read-only",
        "provider_id": "moomoo",
        "quality": {
            "duplicate_count": 0,
            "evaluated_at": "2026-08-13T20:06:00Z",
            "evaluation_id": "1" * 64,
            "expected_count": 9,
            "freshness_seconds": 360,
            "gap_count": 0,
            "hash_mismatch_count": 0,
            "issue_codes": [],
            "latency_seconds": 12,
            "observed_count": 9,
            "order_violation_count": 0,
            "overlap_conflict_count": 0,
            "pagination_terminal": True,
            "policy_id": "2" * 64,
            "report_id": report_id,
            "schema_mismatch_count": 0,
            "source_rights_known": True,
            "status": "pass",
            "synthetic_row_count": 0,
            "unavailable_reason": None,
        },
        "row_count": 9,
        "session_policy": "regular",
        "source_rights_id": "rights-moomoo-read-only",
        "trusted_for_research": True,
    }
    page.route(
        f"**/api/data/catalog/{manifest_id}",
        lambda route: route.fulfill(json={"entry": entry, "ancestors": []}),
    )
    page.route("**/api/data/catalog", lambda route: route.fulfill(json=[entry]))
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/app/ops/data")
    page.get_by_role("heading", name="Trusted data catalog", exact=True).first.wait_for()
    _wait_demo_attached(page)
    page.get_by_text(manifest_id, exact=True).wait_for()
    assert run_id in _main_text(page)
    page.get_by_role("button", name="Show lineage").click()
    page.get_by_role("heading", name="Exact quality checks", exact=True).wait_for()
    page.get_by_text("Checkpoint run ID", exact=True).wait_for()
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1


def test_csv_import_validation_and_commit(page, base_url) -> None:
    """Upload -> preview -> mapping -> commit: rejected rows carry their
    reason, the accepted bars land under an operator-import manifest."""
    page.goto(f"{base_url}/app/ops/imports")
    page.get_by_role("heading", name="Data imports", exact=True).first.wait_for()
    _wait_demo_attached(page)

    csv_text = (
        "timestamp,open,high,low,close,volume\n"
        + "".join(f"2026-08-0{i},100,101,99,100.5,1000\n" for i in range(1, 5))
        + "2026-08-05,oops,106,104,105,1500\n"
    )
    page.set_input_files(
        "input[type=file]",
        {"name": "smoke-e2e.csv", "mimeType": "text/csv", "buffer": csv_text.encode()},
    )
    page.get_by_role("button", name="Commit dataset (5 rows)").wait_for()

    page.get_by_label("Dataset name").fill("e2e-import")
    page.get_by_label("Symbol").fill("E2E")
    page.get_by_role("button", name="Commit dataset (5 rows)").click()

    page.get_by_text("4 accepted", exact=False).first.wait_for()
    result = _main_text(page)
    assert "1 rejected" in result
    assert "not a number" in result  # row 5's rejection reason
    assert "e2e-import" in result  # the manifest card + the committed list


def test_two_click_reset_restores_the_seed(page, base_url) -> None:
    """The armed-confirm reset clears the browser-visible state: the
    import is gone and the seeded order set is back."""
    page.goto(f"{base_url}/app/")
    _wait_demo_attached(page)

    # The button's accessible name stays "Reset demo session" (its
    # aria-label) even while armed — the armed state shows as text.
    # The response only arrives after the full re-seed, so it is the
    # completion signal (the label reverts via a 3 s timer either way).
    reset_button = page.get_by_role("button", name="Reset demo session")
    reset_button.click()
    page.get_by_text("Confirm reset", exact=True).wait_for()
    with page.expect_response(
        lambda response: response.url.endswith("/api/demo/reset")
    ) as reset_info:
        reset_button.click()
    assert reset_info.value.status == 200

    page.goto(f"{base_url}/app/ops/imports")
    page.get_by_role("heading", name="Data imports", exact=True).first.wait_for()
    _wait_demo_attached(page)
    assert "No operator-imported datasets yet" in _main_text(page)


def test_keyboard_only_walk(page, base_url) -> None:
    """The paper-order form works with keyboard only: Tab lands focus
    and the venue select opens with Arrow keys."""
    page.goto(f"{base_url}/app/trading/order")
    page.get_by_role("heading", name="Paper order", exact=True).first.wait_for()
    _wait_demo_attached(page)

    page.keyboard.press("Tab")
    focused = page.evaluate(
        "(() => { const el = document.activeElement;"
        " return el ? el.getAttribute('aria-label') || el.tagName : null; })()"
    )
    assert focused, "nothing is focused after the first Tab"

    page.get_by_label("Venue").focus()
    page.get_by_label("Venue").press("ArrowDown")
    assert "hyperliquid" in page.get_by_label("Venue").input_value()


@pytest.mark.parametrize(
    ("disposition", "reason", "button_name", "phase"),
    [
        ("reject", "Reject until invalidation improves", "Reject decision", "Rejected"),
        ("watch", "Wait for the entry zone", "Watch decision", "Watching"),
        ("paper_proposal", None, "Create paper proposal", "Paper proposed"),
    ],
)
def test_nvda_workspace_reaches_each_durable_decision_in_under_two_minutes(
    page,
    base_url,
    disposition: str,
    reason: str | None,
    button_name: str,
    phase: str,
) -> None:
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    started = perf_counter()
    main = page.get_by_role("main")
    workspace_url = page.url

    assert main.get_by_role("region", name="Market canvas").count() == 1
    assert main.get_by_role("region", name="Market structure and key levels").count() == 1
    assert main.get_by_role("region", name="Evidence").count() == 1
    assert main.get_by_role("region", name="Scenarios").locator("article").count() == 3
    assert main.get_by_role("complementary", name="Decision").count() == 1
    assert main.get_by_role("region", name="Risk plan").count() == 1
    assert main.get_by_role("region", name="DecisionPacket actions").count() == 1
    text = main.inner_text()
    for fact in (
        "Bull",
        "Base",
        "Bear",
        "Paper only · explicit confirmation required",
    ):
        assert fact in text

    if reason is not None:
        decision_reason = page.get_by_label("Decision reason")
        if disposition == "watch":
            decision_reason.focus()
            page.keyboard.type(reason)
        else:
            decision_reason.fill(reason)
    with page.expect_response(
        lambda response: (
            "/api/decision-packets/" in response.url and response.url.endswith("/actions")
        )
    ) as saved:
        action = page.get_by_role("button", name=button_name)
        if disposition == "watch":
            action.focus()
            page.keyboard.press("Enter")
        else:
            action.click()
    assert saved.value.status == 200
    page.get_by_text(phase, exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    elapsed = perf_counter() - started
    print(f"ticker_to_{disposition}_seconds={elapsed:.3f}")
    assert elapsed < 120
    assert page.url == f"{workspace_url}&packet={packet_id}"

    exact = page.request.get(f"{base_url}/api/decision-packets/{packet_id}")
    assert exact.status == 200
    assert exact.json()["packet_id"] == packet_id
    assert exact.json()["disposition"] == disposition
    if disposition == "paper_proposal":
        proposal_id = _proposal_id(page)
        assert proposal_id == exact.json()["proposal_id"]
        assert page.get_by_role("button", name="Confirm paper proposal").is_disabled()


def test_decision_inbox_opens_the_exact_saved_packet(page, base_url) -> None:
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    page.get_by_label("Decision reason").fill("Reopen this exact Watch packet")
    page.get_by_role("button", name="Watch decision").click()
    page.get_by_text("Watching", exact=True).wait_for()
    packet_id = _decision_packet_id(page)

    page.goto(f"{base_url}/app/markets/watchlist")
    page.get_by_role("heading", name="Watchlist", exact=True).first.wait_for()
    inbox_link = page.get_by_role("link", name="Open exact packet")
    expected_path = f"/app/instruments/moomoo/NVDA?range=6m&packet={packet_id}"
    assert inbox_link.get_attribute("href") == expected_path
    assert page.get_by_text("Watching", exact=True).is_visible()
    inbox_link.click()
    page.wait_for_url(f"{base_url}{expected_path}")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    assert _decision_packet_id(page) == packet_id


def test_aapl_decision_inbox_opens_a_saved_watch_packet_after_reload(page, base_url) -> None:
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/AAPL?range=6m")
    page.get_by_role("heading", name="AAPL", exact=True).wait_for()
    started = perf_counter()
    page.get_by_label("Decision reason").fill("Reopen this exact AAPL Watch packet")
    page.get_by_role("button", name="Watch decision").click()
    page.get_by_text("Watching", exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    elapsed = perf_counter() - started
    print(f"ticker_to_aapl_watch_seconds={elapsed:.3f}")
    assert elapsed < 120

    page.goto(f"{base_url}/app/markets/watchlist")
    page.get_by_role("heading", name="Watchlist", exact=True).first.wait_for()
    aapl_row = page.get_by_role("row").filter(has_text="AAPL")
    inbox_link = aapl_row.get_by_role("link", name="Open exact packet")
    expected_path = f"/app/instruments/moomoo/AAPL?range=6m&packet={packet_id}"
    assert inbox_link.get_attribute("href") == expected_path
    inbox_link.click()
    page.wait_for_url(f"{base_url}{expected_path}")
    page.reload()
    page.get_by_role("heading", name="AAPL", exact=True).wait_for()
    assert _decision_packet_id(page) == packet_id


@pytest.mark.parametrize("symbol", ["BTC-USD", "SOL-USD"])
def test_crypto_degraded_inbox_keeps_paper_blocked_and_saves_exact_watch_at_mobile_width(
    page,
    base_url,
    symbol: str,
) -> None:
    _reset_demo(page, base_url)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/app/markets/watchlist")
    page.get_by_role("heading", name="Watchlist", exact=True).first.wait_for()
    crypto_row = page.get_by_role("row").filter(has_text=symbol)
    crypto_row.get_by_role("link", name="Open workspace").click()
    page.get_by_role("heading", name=symbol, exact=True).wait_for()

    main = page.get_by_role("main")
    actions = main.get_by_role("region", name="DecisionPacket actions")
    main_text = main.inner_text()
    assert "No promoted forecast is available." in main_text
    page.get_by_label("Decision reason").fill("Watch until forecast evidence is available")
    assert page.get_by_role("button", name="Reject decision").is_enabled()
    assert page.get_by_role("button", name="Watch decision").is_enabled()
    assert page.get_by_role("button", name="Create paper proposal").is_disabled()

    with page.expect_response(
        lambda response: (
            "/api/decision-packets/" in response.url and response.url.endswith("/actions")
        )
    ) as saved:
        actions.get_by_role("button", name="Watch decision").click()
    assert saved.value.status == 200
    page.get_by_text("Watching", exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    assert f"packet={packet_id}" in page.url
    page.reload()
    page.get_by_role("heading", name=symbol, exact=True).wait_for()
    assert _decision_packet_id(page) == packet_id
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_nvda_packet_copilot_valid_reload_and_unavailable_paths(
    page,
    base_url,
    demo_station: _DemoStation,
) -> None:
    service = demo_station.app.state.packet_copilot
    assert isinstance(service, PacketCopilotService)
    original_analyst = service.analyst_gateway
    original_critic = service.critic_gateway
    original_analyst_model = service.analyst_model
    original_critic_model = service.critic_model
    model = ModelMeta(name="fixture-copilot", version="v1", endpoint_kind="scripted")
    try:
        _reset_demo(page, base_url)
        page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        page.get_by_label("Decision reason").fill("Inspect the packet-bound explanation")
        page.get_by_role("button", name="Watch decision").click()
        page.get_by_text("Watching", exact=True).wait_for()
        packet_id = _decision_packet_id(page)
        packet_response = page.request.get(f"{base_url}/api/decision-packets/{packet_id}")
        assert packet_response.status == 200
        packet_before = packet_response.json()
        proposals_before = demo_station.app.state.paper_decisions.ledger.all()
        orders_before = demo_station.app.state.account_store.get().orders
        analyst_script, critic_script = _copilot_script(packet_before)
        service.analyst_gateway = ModelGateway(
            ScriptedModelTransport(analyst_script), model_name=model.name
        )
        service.critic_gateway = ModelGateway(
            ScriptedModelTransport(critic_script), model_name=model.name
        )
        service.analyst_model = model
        service.critic_model = model

        action = page.get_by_role("button", name="Explain & challenge")
        action.wait_for(state="visible")
        assert action.is_enabled()
        action.focus()
        with page.expect_response(
            lambda response: (
                response.url.endswith(f"/api/decision-packets/{packet_id}/copilot")
                and response.request.method == "POST"
            )
        ) as accepted:
            page.keyboard.press("Enter")
        assert accepted.value.status == 200
        page.get_by_text("The stored market structure is the base evidence.").wait_for()
        copilot = page.get_by_test_id("packet-copilot")
        for section in (
            "Base explanation",
            "Bull challenge",
            "Bear challenge",
            "Evidence gaps or contradictions",
            "Limitations",
            "Operator questions",
        ):
            assert copilot.get_by_role("heading", name=section).count() == 1
        copilot.get_by_text("1 packet fact").first.click()
        assert copilot.get_by_text("/market_state/trend", exact=True).count() == 1
        assert (
            page.request.get(f"{base_url}/api/decision-packets/{packet_id}").json() == packet_before
        )
        assert demo_station.app.state.paper_decisions.ledger.all() == proposals_before
        assert demo_station.app.state.account_store.get().orders == orders_before

        page.reload()
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        page.get_by_text("The stored market structure is the base evidence.").wait_for()

        _reset_demo(page, base_url)
        service.analyst_gateway = None
        service.critic_gateway = None
        page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        displayed_draft_id = _decision_packet_id(page)
        persisted = page.request.post(
            f"{base_url}/api/decision-packets",
            data={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": displayed_draft_id,
            },
        )
        assert persisted.status == 200
        assert persisted.json()["packet_id"] == displayed_draft_id
        degraded_packet_id = displayed_draft_id
        page.reload()
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        assert _decision_packet_id(page) == degraded_packet_id
        degraded_packet = page.request.get(
            f"{base_url}/api/decision-packets/{degraded_packet_id}"
        ).json()
        proposals_before = demo_station.app.state.paper_decisions.ledger.all()
        orders_before = demo_station.app.state.account_store.get().orders
        main = page.get_by_role("main")
        assert main.get_by_role("region", name="Market canvas").count() >= 1
        assert main.get_by_role("region", name="Evidence").count() >= 1
        assert main.get_by_role("region", name="Scenarios").count() >= 1
        assert main.get_by_role("region", name="Risk plan").count() >= 1
        action_region = main.get_by_role("region", name="DecisionPacket actions")
        assert action_region.count() == 1
        action_state_before = action_region.inner_text()
        with page.expect_response(
            lambda response: (
                response.url.endswith(f"/api/decision-packets/{degraded_packet_id}/copilot")
                and response.request.method == "POST"
            )
        ) as unavailable:
            page.get_by_role("button", name="Explain & challenge").click()
        assert unavailable.value.status == 200
        page.get_by_text(
            "Copilot is temporarily unavailable. The DecisionPacket and decision "
            "actions are unaffected."
        ).wait_for()
        assert action_region.inner_text() == action_state_before
        assert (
            page.request.get(f"{base_url}/api/decision-packets/{degraded_packet_id}").json()
            == degraded_packet
        )
        assert demo_station.app.state.paper_decisions.ledger.all() == proposals_before
        assert demo_station.app.state.account_store.get().orders == orders_before
    finally:
        service.analyst_gateway = original_analyst
        service.critic_gateway = original_critic
        service.analyst_model = original_analyst_model
        service.critic_model = original_critic_model
        _reset_demo(page, base_url)


def test_nvda_packet_monitoring_is_packet_bound_and_survives_workspace_reload(
    page,
    base_url,
    demo_station: _DemoStation,
) -> None:
    """The local disclosure has no proposal, order, or navigation authority."""
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    workspace_url = page.url
    page.get_by_label("Decision reason").fill("Persist a packet-bound local check")
    page.get_by_role("button", name="Watch decision").click()
    page.get_by_text("Watching", exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    packet_before = page.request.get(f"{base_url}/api/decision-packets/{packet_id}").json()
    proposals_before = demo_station.app.state.paper_decisions.ledger.all()
    orders_before = demo_station.app.state.account_store.get().orders

    monitoring = page.get_by_test_id("packet-monitoring")
    monitoring.get_by_role("button", name="Save & check").wait_for()
    with page.expect_response(
        lambda response: (
            response.url.endswith(f"/api/decision-packets/{packet_id}/watch-conditions")
            and response.request.method == "POST"
        )
    ) as checked:
        monitoring.get_by_role("button", name="Save & check").click()
    assert checked.value.status == 200
    body = checked.value.json()
    assert body["packet_id"] == packet_id
    assert len(body["registration"]["conditions"]) == 4
    monitoring.get_by_role("button", name="Check now").wait_for()

    page.reload()
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    assert page.url == f"{workspace_url}&packet={packet_id}"
    recovered = page.get_by_test_id("packet-monitoring")
    recovered.get_by_role("button", name="Check now").wait_for()
    assert page.request.get(f"{base_url}/api/decision-packets/{packet_id}").json() == packet_before
    assert demo_station.app.state.paper_decisions.ledger.all() == proposals_before
    assert demo_station.app.state.account_store.get().orders == orders_before


def test_nvda_filled_open_packet_review_saves_and_reopens_exact_identity(
    page,
    base_url,
    demo_station: _DemoStation,
) -> None:
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()

    page.get_by_label("Optional limit").fill("")
    page.get_by_role("button", name="Create paper proposal").click()
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    proposal_id = _proposal_id(page)
    token = (
        page.get_by_text("Displayed confirmation token", exact=True)
        .locator("..")
        .locator("code")
        .inner_text()
    )
    page.get_by_label("Confirmation token").fill(token)
    page.get_by_role("button", name="Confirm paper proposal").click()
    page.get_by_text("Paper order created", exact=True).wait_for()

    # Reopen the same workspace so the preview is recomposed from the exact
    # terminal proposal/order snapshot, not an earlier pending query cache.
    page.reload()
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    review = page.get_by_test_id("packet-outcome-review")
    review.get_by_text("Realized paper R", exact=True).wait_for()
    assert review.get_by_text("Filled open", exact=True).is_visible()
    assert review.get_by_text("Unavailable", exact=True).count() >= 1
    review.get_by_label("Review note (optional)").fill(
        "Entry filled; exit and complete fees remain unavailable."
    )
    with page.expect_response(
        lambda response: (
            response.url.endswith(f"/api/decision-packets/{packet_id}/outcome-review")
            and response.request.method == "POST"
        )
    ) as saved:
        review.get_by_role("button", name="Save review").click()
    assert saved.value.status == 200
    body = saved.value.json()
    assert body["packet_id"] == packet_id
    assert body["outcome"]["paper"]["proposal"]["id"] == proposal_id
    assert body["outcome"]["paper"]["state"] == "filled_open"
    assert body["outcome"]["realized_paper_r"]["status"] == "unavailable"
    review_id = body["review"]["review_id"]
    outcome_id = body["outcome"]["outcome_id"]
    review.get_by_text(review_id, exact=True).wait_for()

    with _serve_restarted_demo(demo_station.root) as restarted:
        replay = restarted.app.state.packet_reviews.preview(packet_id)
        assert replay.review.review_id == review_id
        assert replay.review.outcome.outcome_id == outcome_id
        page.goto(f"{restarted.url}/app/instruments/moomoo/NVDA?range=6m")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        reopened = page.get_by_test_id("packet-outcome-review")
        reopened.get_by_text("Review saved", exact=True).wait_for()
        assert reopened.get_by_text(review_id, exact=True).is_visible()
        assert reopened.get_by_text(outcome_id, exact=True).is_visible()
        assert _decision_packet_id(page) == packet_id


def test_shadow_decision_inbox_replays_paper_review_and_exact_keyboard_navigation(
    page,
    base_url,
    demo_station: _DemoStation,
    tmp_path: Path,
) -> None:
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    page.get_by_label("Optional limit").fill("")
    page.get_by_role("button", name="Create paper proposal").click()
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    proposal_id = _proposal_id(page)
    token = (
        page.get_by_text("Displayed confirmation token", exact=True)
        .locator("..")
        .locator("code")
        .inner_text()
    )
    page.get_by_label("Confirmation token").fill(token)
    page.get_by_role("button", name="Confirm paper proposal").click()
    page.get_by_text("Paper order created", exact=True).wait_for()
    page.reload()
    review = page.get_by_test_id("packet-outcome-review")
    review.get_by_text("Filled open", exact=True).wait_for()
    with page.expect_response(
        lambda response: (
            response.url.endswith(f"/api/decision-packets/{packet_id}/outcome-review")
            and response.request.method == "POST"
        )
    ) as saved:
        review.get_by_role("button", name="Save review").click()
    assert saved.value.status == 200
    saved_review = saved.value.json()
    outcome_id = saved_review["outcome"]["outcome_id"]
    review_id = saved_review["review"]["review_id"]
    order_id = saved_review["outcome"]["paper"]["order"]["order_id"]

    page.goto(f"{base_url}/app/instruments/moomoo/AAPL?range=6m")
    page.get_by_role("heading", name="AAPL", exact=True).wait_for()
    page.get_by_label("Optional limit").fill("")
    page.get_by_role("button", name="Create paper proposal").click()
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    pending_id = _proposal_id(page)
    pending_packet = _decision_packet_id(page)

    with _serve_restarted_demo(demo_station.root) as restarted:
        before_orders = restarted.app.state.account_store.get().orders
        page.goto(f"{restarted.url}/app/markets/watchlist")
        nvda = page.get_by_role("row").filter(has=page.get_by_role("cell", name="NVDA", exact=True))
        nvda.get_by_text("Reviewed", exact=True).wait_for()
        nvda.locator("summary").click()
        for identity in (packet_id, proposal_id, order_id, outcome_id, review_id):
            assert nvda.get_by_text(identity, exact=True).is_visible()
        page.screenshot(path=str(tmp_path / "shadow-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.emulate_media(reduced_motion="reduce")
        assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
        summary = nvda.locator("summary")
        summary.focus()
        page.keyboard.press("Enter")
        assert not nvda.locator("details").evaluate("element => element.open")
        page.keyboard.press("Enter")
        assert nvda.locator("details").evaluate("element => element.open")
        aapl = page.get_by_role("row").filter(has=page.get_by_role("cell", name="AAPL", exact=True))
        assert aapl.get_by_text("Pending confirmation", exact=True).is_visible()
        aapl.locator("summary").click()
        assert aapl.get_by_text(pending_id, exact=True).is_visible()
        snapshot = page.request.get(f"{restarted.url}/api/decision-packets").json()
        pending = next(row for row in snapshot["entries"] if row["symbol"] == "AAPL")
        assert pending["packet_id"] == pending_packet
        assert pending["paper"]["order_id"] is None
        assert restarted.app.state.account_store.get().orders == before_orders
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(tmp_path / "shadow-mobile.png"), full_page=True)
        summary.focus()
        page.keyboard.press("Tab")
        exact = nvda.get_by_role("link", name="Open exact packet")
        assert exact.evaluate("element => element === document.activeElement")
        page.keyboard.press("Enter")
        page.wait_for_url(f"**/instruments/moomoo/NVDA?range=6m&packet={packet_id}")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        assert _decision_packet_id(page) == packet_id
        page.get_by_test_id("packet-outcome-review").get_by_text(review_id, exact=True).wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_stale_nvda_keeps_reject_and_watch_but_disables_paper_and_writes_no_order(
    page,
    base_url,
    demo_station: _DemoStation,
) -> None:
    _reset_demo(page, base_url)
    workspace = demo_station.app.state.instrument_workspace
    paper_decisions = demo_station.app.state.paper_decisions
    original_workspace_clock = workspace._now  # noqa: SLF001
    original_proposal_clock = paper_decisions._now  # noqa: SLF001
    stale_now = SCENARIO.anchor + timedelta(days=10)
    workspace._now = lambda: stale_now  # noqa: SLF001
    paper_decisions._now = lambda: stale_now  # noqa: SLF001
    proposals_before = paper_decisions.ledger.all()
    orders_before = demo_station.app.state.account_store.get().orders
    try:
        page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        page.get_by_text("Evidence blocked", exact=True).wait_for()
        main = page.get_by_role("main")
        blockers = main.get_by_role("region", name="Paper blockers")
        assert blockers.count() == 1
        assert blockers.inner_text().strip()

        reason = page.get_by_label("Decision reason")
        reason.fill("Wait for fresh evidence")
        assert page.get_by_role("button", name="Reject decision").is_enabled()
        assert page.get_by_role("button", name="Watch decision").is_enabled()
        assert page.get_by_role("button", name="Create paper proposal").is_disabled()
        assert paper_decisions.ledger.all() == proposals_before
        assert demo_station.app.state.account_store.get().orders == orders_before
    finally:
        workspace._now = original_workspace_clock  # noqa: SLF001
        paper_decisions._now = original_proposal_clock  # noqa: SLF001
        _reset_demo(page, base_url)


def test_nvda_second_confirmation_refusal_keeps_packet_and_proposal_visible(
    page,
    base_url,
    demo_station: _DemoStation,
) -> None:
    _reset_demo(page, base_url)
    page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
    page.get_by_role("heading", name="NVDA", exact=True).wait_for()
    filled_before = sum(
        order.status.value == "filled"
        for order in demo_station.app.state.account_store.get().orders.values()
    )
    accepted_before = sum(
        order.status.value == "accepted"
        for order in demo_station.app.state.account_store.get().orders.values()
    )

    page.get_by_role("button", name="Create paper proposal").click()
    page.get_by_text("Immutable proposal preview", exact=True).wait_for()
    packet_id = _decision_packet_id(page)
    proposal_id = _proposal_id(page)
    token = (
        page.get_by_text("Displayed confirmation token", exact=True)
        .locator("..")
        .locator("code")
        .inner_text()
    )
    engaged = page.request.post(
        f"{base_url}/api/kill-switch",
        data={"action": "engage", "venue": None},
    )
    assert engaged.status == 200

    page.get_by_label("Confirmation token").fill(token)
    with page.expect_response(
        lambda response: response.url.endswith(f"/api/paper/proposals/{proposal_id}/confirm")
    ) as refused:
        page.get_by_role("button", name="Confirm paper proposal").click()
    assert refused.value.status == 409
    page.get_by_text("Proposal rejected", exact=True).wait_for()
    assert packet_id in page.get_by_role("main").inner_text()
    assert proposal_id in page.get_by_role("main").inner_text()
    assert "Rejected" in page.get_by_role("main").inner_text()
    filled_after = sum(
        order.status.value == "filled"
        for order in demo_station.app.state.account_store.get().orders.values()
    )
    accepted_after = sum(
        order.status.value == "accepted"
        for order in demo_station.app.state.account_store.get().orders.values()
    )
    assert filled_after == filled_before
    assert accepted_after == accepted_before
    _reset_demo(page, base_url)


def test_nvda_decision_safety_copy_keyboard_reduced_motion_and_mobile_boundary(
    browser,
    base_url,
) -> None:
    context = browser.new_context(
        reduced_motion="reduce",
        viewport={"width": 390, "height": 844},
    )
    page = context.new_page()
    try:
        _reset_demo(page, base_url)
        page.goto(f"{base_url}/app/settings")
        page.get_by_label("Interface language").select_option("zh-CN")
        page.get_by_role("heading", name="全局设置", exact=True).first.wait_for()
        page.goto(f"{base_url}/app/instruments/moomoo/NVDA?range=6m")
        page.get_by_role("heading", name="NVDA", exact=True).wait_for()
        main = page.get_by_role("main")
        assert "仅模拟盘 · 必须明确确认" in main.inner_text()
        assert main.get_by_role("region", name="DecisionPacket 操作").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        reason = page.get_by_label("决策原因")
        reason.focus()
        page.keyboard.type("等待入场区")
        watch = page.get_by_role("button", name="观察决策")
        watch.focus()
        focused_style = watch.evaluate(
            "element => { const style = getComputedStyle(element); "
            "return { boxShadow: style.boxShadow, outline: style.outlineStyle, "
            "transitionSeconds: Math.max(0, ...style.transitionDuration.split(',').map(value => { "
            "const duration = value.trim(); "
            "return duration.endsWith('ms') ? parseFloat(duration) / 1000 : parseFloat(duration); "
            "}).filter(Number.isFinite)) }; }"
        )
        assert focused_style["boxShadow"] != "none" or focused_style["outline"] != "none"
        assert focused_style["transitionSeconds"] <= 0.001
        page.keyboard.press("Enter")
        page.get_by_text("观察中", exact=True).wait_for()
        assert _decision_packet_id(page).startswith("packet-")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        context.close()
