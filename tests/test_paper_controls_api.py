"""Narrow paper control routes and existing bypasses use tiny account fixtures."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app, main
from quantmesh.demo.runtime import demo_router
from quantmesh.execution.accounting import PaperAccount, RiskLimits
from quantmesh.execution.journal import OrderJournal
from quantmesh.ops.paper_controls import PaperControls


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "demo" / "account.json"
    path.parent.mkdir()
    account = PaperAccount(cash=1000)
    path.write_text(account.model_dump_json())
    journal = OrderJournal(path.parent / "orders")
    journal._store.write([])
    app = create_workstation_app(
        account=account,
        journal=journal,
        account_sink=lambda a: path.write_text(a.model_dump_json()),
    )
    app.state.paper_controls = PaperControls(
        root=tmp_path / "controls",
        account_store=app.state.account_store,
        account_path=path,
        journal=journal,
        scenario="api-tiny",
        limits=RiskLimits(max_order_quantity=2, max_notional=500, max_position_quantity=5),
    )
    app.include_router(demo_router())
    app.include_router(demo_router(), prefix="/api")
    from quantmesh.domain.models import Instrument, InstrumentType, Venue

    instrument = Instrument(
        symbol="TINY", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
    )
    book = SimpleNamespace(
        bids=[SimpleNamespace(price=99, quantity=10)],
        asks=[SimpleNamespace(price=100, quantity=10)],
    )
    providers = SimpleNamespace(
        universe=lambda: [("moomoo", "TINY")],
        instrument=lambda *_: instrument,
        order_books=lambda *_: [book],
    )
    app.state.demo = SimpleNamespace(
        seeded=SimpleNamespace(providers=providers, marks={}),
        scenario=SimpleNamespace(anchor=datetime(2026, 10, 20, tzinfo=UTC)),
    )
    with TestClient(app) as client:
        yield client, app
    app.state.paper_controls.close()


def test_api_status_preflight_confirmation_replay_and_download(api):
    client, app = api
    status = client.get("/api/paper-controls").json()
    assert status["paused"] and status["synthetic"] and status["paper"]
    preflight = client.post("/api/paper-controls/preflight", json={}).json()
    payload = dict(
        key="api-1",
        reason="Checked local rehearsal",
        revision=preflight["revision"],
        confirmation=True,
    )
    assert (
        client.post(
            "/api/paper-controls/resume", json={**payload, "confirmation": False}
        ).status_code
        == 409
    )
    first = client.post("/api/paper-controls/resume", json=payload)
    assert first.status_code == 200, first.text
    assert not first.json()["status"]["paused"]
    audit = client.get("/api/paper-controls/audit")
    import hashlib

    assert audit.headers["x-content-sha256"] == hashlib.sha256(audit.content).hexdigest()
    receipt = client.get("/api/paper-controls/receipts/" + first.json()["receipt"]["id"])
    assert receipt.json() == first.json()["receipt"]
    client.post("/api/paper-controls/pause", json={"key": "api-2", "reason": "Inspect"})
    replay = client.post("/api/paper-controls/resume", json=payload).json()
    assert replay["replay"] and replay["status"]["paused"]
    assert app.state.account_store.get().kill_switch


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/kill-switch", {"action": "disarm"}),
        ("/api/kill-switch", {"action": "disarm", "venue": "moomoo"}),
    ],
)
def test_old_json_disarm_cannot_bypass(api, path, body):
    client, app = api
    assert client.post(path, json=body).status_code == 409
    assert app.state.account_store.get().kill_switch


def test_old_html_disarm_and_both_reset_mounts_refused(api):
    client, app = api
    assert (
        client.post("/kill-switch", data={"action": "disarm", "confirm": "confirm"}).status_code
        == 409
    )
    for path in ("/demo/reset", "/api/demo/reset"):
        assert client.post(path).status_code == 409
    assert app.state.account_store.get().kill_switch


def test_legacy_engage_is_audited(api):
    client, app = api
    count = len(app.state.paper_controls._records())
    assert client.post("/api/kill-switch", json={"action": "engage"}).status_code == 200
    assert len(app.state.paper_controls._records()) == count + 2


def test_fresh_paused_order_has_zero_effect_then_resume_fill_and_historical_replay(api):
    client, app = api
    c = app.state.paper_controls
    payload = {
        "venue": "moomoo",
        "symbol": "TINY",
        "side": "BUY",
        "quantity": 1,
        "idempotency_key": "tiny-order",
    }
    before_account = c.account_path.read_bytes()
    before_journal = c.journal._store.path.read_bytes()
    assert client.post("/api/demo/order", json=payload).status_code == 409
    assert c.account_path.read_bytes() == before_account
    assert c.journal._store.path.read_bytes() == before_journal
    revision = client.post("/api/paper-controls/preflight", json={}).json()["revision"]
    assert (
        client.post(
            "/api/paper-controls/resume",
            json={
                "key": "resume-fill",
                "reason": "Checked",
                "revision": revision,
                "confirmation": True,
            },
        ).status_code
        == 200
    )
    accepted = client.post("/api/demo/order", json=payload)
    assert accepted.status_code == 200, accepted.text
    assert app.state.account_store.get().order_sequence == 1
    client.post("/api/paper-controls/pause", json={"key": "pause-fill", "reason": "Inspect"})
    before_account = c.account_path.read_bytes()
    before_journal = c.journal._store.path.read_bytes()
    replay = client.post("/api/demo/order", json=payload)
    assert replay.status_code == 200
    assert c.account_path.read_bytes() == before_account
    assert c.journal._store.path.read_bytes() == before_journal
    assert (
        client.post("/api/demo/order", json={**payload, "idempotency_key": "new-order"}).status_code
        == 409
    )
    c.journal._store.path.write_text("corrupt-journal")
    refused = client.post("/api/demo/order", json={**payload, "idempotency_key": "other"})
    assert (
        refused.status_code == 409 and refused.json()["detail"] == "paper_control_evidence_blocked"
    )
    assert c.journal._store.path.read_text() == "corrupt-journal"


def test_origin_size_schema_default_off(api):
    client, _ = api
    assert (
        client.post(
            "/api/paper-controls/preflight", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/paper-controls/pause", content=b"x" * 5000).status_code == 413
    for value in ({"key": "x", "reason": ""}, {"key": "x", "reason": "ok", "path": "private"}, []):
        assert client.post("/api/paper-controls/pause", json=value).status_code == 422
    with TestClient(create_workstation_app(account=PaperAccount(cash=1000))) as other:
        assert other.get("/api/paper-controls").status_code == 503
        assert other.post("/api/kill-switch", json={"action": "disarm"}).status_code == 200


@pytest.mark.parametrize(
    "args",
    [
        ["--paper-control-root", "x"],
        ["--demo", "--live", "--paper-control-root", "x"],
        ["--demo", "--paper-control-root", "x", "--paper-max-notional", "5"],
        [
            "--demo",
            "--paper-control-root",
            "x",
            "--paper-max-order-quantity",
            "NaN",
            "--paper-max-notional",
            "5",
            "--paper-max-position-quantity",
            "10",
        ],
        ["--demo", "--paper-max-order-quantity", "1"],
        ["--demo", "--demo-root", "x", "--paper-control-root", "x/inside"],
    ],
)
def test_cli_invalid_settings_refused_before_seeding(args, monkeypatch):
    monkeypatch.setattr(
        "quantmesh.demo.runtime.create_demo_app", lambda **_: pytest.fail("seed reached")
    )
    with pytest.raises(SystemExit):
        main(args)


@pytest.mark.parametrize(
    "caps",
    [
        [],
        [
            "--paper-max-order-quantity",
            "2",
            "--paper-max-notional",
            "500",
            "--paper-max-position-quantity",
            "4",
        ],
    ],
)
def test_valid_cli_passes_explicit_limits_or_missing_limits_without_silent_defaults(
    tmp_path,
    monkeypatch,
    caps,
):
    from unittest.mock import Mock

    assembly = Mock(return_value=create_workstation_app(account=PaperAccount(cash=1000)))
    monkeypatch.setattr("quantmesh.demo.runtime.create_demo_app", assembly)
    monkeypatch.setattr("uvicorn.run", Mock())
    main(
        [
            "--demo",
            "--demo-root",
            str(tmp_path / "demo"),
            "--paper-control-root",
            str(tmp_path / "controls"),
            *caps,
        ]
    )
    assert assembly.call_args.kwargs["paper_control_root"] == tmp_path / "controls"
    expected = RiskLimits(max_order_quantity=2, max_notional=500, max_position_quantity=4)
    assert assembly.call_args.kwargs["paper_limits"] == (expected if caps else None)


def test_legacy_html_has_no_apparent_disarm_when_controlled(tmp_path, monkeypatch):
    from quantmesh.api.workstation import settings

    monkeypatch.setattr(settings, "legacy_ui", True)
    app = create_workstation_app(account=PaperAccount(cash=1000))
    app.state.paper_controls = object()
    with TestClient(app) as client:
        response = client.get("/kill-switch/control")
        assert response.status_code == 409
        assert "current evidence and explicit confirmation" in response.text
        assert "<form" not in response.text


def test_real_demo_control_attachment_preserves_lifespan_releases_leases_and_cold_pauses(
    tmp_path,
    monkeypatch,
):
    from contextlib import asynccontextmanager

    from quantmesh.demo import runtime

    events = []
    workstation = runtime.create_workstation_app

    def workstation_with_existing_lifespan(**kwargs):
        app = workstation(**kwargs)
        existing = app.router.lifespan_context

        @asynccontextmanager
        async def existing_lifespan(app):
            events.append("prior-start")
            try:
                async with existing(app):
                    yield
            finally:
                events.append("prior-stop")

        app.router.lifespan_context = existing_lifespan
        return app

    monkeypatch.setattr(runtime, "create_workstation_app", workstation_with_existing_lifespan)
    options = dict(
        root=tmp_path / "real-demo",
        workspace_history=False,
        paper_control_root=tmp_path / "real-controls",
        paper_limits=RiskLimits(
            max_order_quantity=2, max_notional=500, max_position_quantity=1_000_000
        ),
    )
    app = runtime.create_demo_app(**options)
    assert (
        app.state.paper_decisions.fresh_submission_guard
        == app.state.paper_controls.validate_fresh_submission
    )
    assert events == []
    with TestClient(app) as client:
        assert events == ["prior-start"]
        status = client.get("/api/paper-controls").json()
        assert status["paused"] and not status["blocked"]
        preflight = client.post("/api/paper-controls/preflight", json={}).json()
        first = client.post(
            "/api/paper-controls/resume",
            json={
                "key": "real-lifecycle-resume",
                "reason": "Reviewed real synthetic assembly",
                "revision": preflight["revision"],
                "confirmation": True,
            },
        )
        assert first.status_code == 200, first.text
        assert not first.json()["status"]["paused"]
        receipt = first.json()["receipt"]
    assert events == ["prior-start", "prior-stop"]
    assert all(lease.handle is None for lease in app.state.paper_controls._leases)

    # This uses the actual retained demo, including account/journal/audit loading.
    cold = runtime.create_demo_app(**options)
    with TestClient(cold) as client:
        status = client.get("/api/paper-controls").json()
        assert status["paused"] and not status["blocked"]
        assert client.get("/api/paper-controls/receipts/" + receipt["id"]).json() == receipt
    assert events == ["prior-start", "prior-stop", "prior-start", "prior-stop"]
    assert all(lease.handle is None for lease in cold.state.paper_controls._leases)
