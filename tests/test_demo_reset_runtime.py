"""Concurrency checks for the attached deterministic demo runtime."""

import time
from pathlib import Path
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from quantmesh.demo import runtime as demo_runtime
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app

SCENARIO = DemoScenario(workspace_history=False)


def test_runtime_returns_typed_degradation_instead_of_reading_half_reset_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_demo_app(
        root=tmp_path / "demo",
        seed=SCENARIO.seed,
        workspace_history=False,
        host="127.0.0.1",
    )
    entered = Event()
    release = Event()
    original_reset = demo_runtime.reset_demo_root

    def paused_reset(root: Path, scenario: DemoScenario, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return original_reset(root, scenario, **kwargs)

    monkeypatch.setattr(demo_runtime, "reset_demo_root", paused_reset)
    reset_result: list[int] = []
    with TestClient(app) as client:
        thread = Thread(
            target=lambda: reset_result.append(client.post("/api/demo/reset").status_code),
            daemon=True,
        )
        thread.start()
        assert entered.wait(timeout=10)
        during_reset = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
        release.set()
        thread.join(timeout=60)

        assert during_reset.status_code == 503
        assert during_reset.json()["detail"] == "demo reset in progress"
        assert during_reset.headers["X-QuantMesh-Source"] == "demo"
        assert during_reset.headers["X-QuantMesh-Synthetic"] == "true"
        assert during_reset.headers["X-QuantMesh-Anchor"] == SCENARIO.anchor.isoformat()
        assert reset_result == [200]
        assert client.get("/api/health").status_code == 200


def test_reset_drains_an_admitted_order_before_reseeding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_demo_app(
        root=tmp_path / "demo",
        seed=SCENARIO.seed,
        workspace_history=False,
        host="127.0.0.1",
    )
    order_entered = Event()
    release_order = Event()
    reset_entered = Event()
    account_type = type(app.state.page_context.account)
    original_submit = account_type.submit
    original_reset = demo_runtime.reset_demo_root

    def paused_submit(account, *args, **kwargs):
        order_entered.set()
        assert release_order.wait(timeout=10)
        return original_submit(account, *args, **kwargs)

    def observed_reset(root: Path, scenario: DemoScenario, **kwargs):
        reset_entered.set()
        return original_reset(root, scenario, **kwargs)

    monkeypatch.setattr(account_type, "submit", paused_submit)
    monkeypatch.setattr(demo_runtime, "reset_demo_root", observed_reset)
    order_status: list[int] = []
    reset_status: list[int] = []
    with TestClient(app) as client:
        pristine_orders = client.get("/api/demo/status").json()["surfaces"]["orders"]["rows"]
        order_thread = Thread(
            target=lambda: order_status.append(client.post(
                "/api/demo/order",
                json={
                    "venue": "moomoo",
                    "symbol": "NVDA",
                    "side": "BUY",
                    "quantity": 1,
                },
            ).status_code),
            daemon=True,
        )
        order_thread.start()
        assert order_entered.wait(timeout=10)
        reset_thread = Thread(
            target=lambda: reset_status.append(client.post("/api/demo/reset").status_code),
            daemon=True,
        )
        reset_thread.start()
        deadline = time.monotonic() + 10
        while not app.state.demo.resetting and time.monotonic() < deadline:
            time.sleep(0.01)

        assert app.state.demo.resetting is True
        assert reset_entered.is_set() is False
        blocked = client.get("/api/health")
        assert blocked.status_code == 503
        assert blocked.headers["X-QuantMesh-Source"] == "demo"

        release_order.set()
        order_thread.join(timeout=60)
        reset_thread.join(timeout=60)

        assert order_status == [200]
        assert reset_status == [200]
        assert reset_entered.is_set() is True
        restored = client.get("/api/demo/status")
        assert restored.status_code == 200
        assert restored.json()["surfaces"]["orders"]["rows"] == pristine_orders


def test_demo_order_and_kill_switch_share_one_account_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(
        root=root,
        seed=SCENARIO.seed,
        workspace_history=False,
        host="127.0.0.1",
    )
    submit_entered = Event()
    release_submit = Event()
    kill_finished = Event()
    account_type = type(app.state.account_store.get())
    original_submit = account_type.submit

    def paused_submit(account, *args, **kwargs):
        submit_entered.set()
        assert release_submit.wait(timeout=10)
        return original_submit(account, *args, **kwargs)

    monkeypatch.setattr(account_type, "submit", paused_submit)
    responses: dict[str, object] = {}
    with TestClient(app) as client:
        order_thread = Thread(
            target=lambda: responses.__setitem__(
                "order",
                client.post(
                    "/api/demo/order",
                    json={
                        "venue": "moomoo",
                        "symbol": "NVDA",
                        "side": "BUY",
                        "quantity": 1,
                    },
                ),
            ),
            daemon=True,
        )
        order_thread.start()
        assert submit_entered.wait(timeout=10)

        def engage() -> None:
            responses["kill"] = client.post(
                "/api/kill-switch",
                json={"action": "engage"},
            )
            kill_finished.set()

        kill_thread = Thread(target=engage, daemon=True)
        kill_thread.start()
        time.sleep(0.1)
        assert kill_finished.is_set() is False

        release_submit.set()
        order_thread.join(timeout=30)
        kill_thread.join(timeout=30)

        assert responses["order"].status_code == 200
        assert responses["kill"].status_code == 200
        assert client.get("/api/account").json()["kill_switch"] is True

    assert app.state.account.kill_switch is True
    assert app.state.page_context.account.kill_switch is True
    assert app.state.account_store.get().kill_switch is True
