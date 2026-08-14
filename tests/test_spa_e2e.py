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

import socket
import threading
from pathlib import Path

import pytest
import uvicorn

from quantmesh.api import workstation
from quantmesh.demo.datalink import ConnectorState, DatalinkService
from quantmesh.demo.runtime import create_demo_app
from quantmesh.hyperliquid.errors import HyperliquidSDKMissingError

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
def base_url(tmp_path_factory) -> str:
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
        yield f"http://{HOST}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()


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


def test_data_catalog_populated_state_has_no_mobile_overflow(
    page, base_url
) -> None:
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
        + "".join(
            f"2026-08-0{i},100,101,99,100.5,1000\n" for i in range(1, 5)
        )
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
