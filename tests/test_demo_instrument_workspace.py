from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from quantmesh.data.lake import Lake
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.demo.seeder import seed_demo_root
from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import HistoryRange

SCENARIO = DemoScenario()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_seeded_demo_has_deep_history_and_truthful_forecast_examples(tmp_path: Path) -> None:
    seeded = seed_demo_root(tmp_path / "demo", SCENARIO)
    dataset = Lake(seeded.root / "market" / "lake").dataset("demo-moomoo-nvda")
    coverage = {
        item.interval: item.rows
        for item in dataset.manifest.coverage
        if item.venue is Venue.MOOMOO and item.symbol == "NVDA"
    }

    assert coverage["1d"] == 650
    assert coverage["5m"] >= 78
    assert coverage["30m"] >= 60
    assert coverage["1h"] >= 120
    assert (
        len(
            seeded.history.history(
                Venue.MOOMOO,
                "NVDA",
                HistoryRange.SIX_MONTHS,
                as_of=SCENARIO.anchor,
            ).bars
        )
        >= 120
    )

    forecasts = seeded.price_forecasts.all()
    nvda = next(item for item in forecasts if item.instrument.symbol == "NVDA")
    aapl = next(item for item in forecasts if item.instrument.symbol == "AAPL")
    assert nvda.history_sessions == 650
    assert nvda.eligible is True
    assert aapl.history_sessions == 650
    assert aapl.eligible is True
    assert aapl.blockers == ()
    assert seeded.proposal_ledger.all() == ()


def test_demo_workspace_forecast_to_paper_loop_resets_to_seeded_state(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        assert client.get("/api/demo/status").status_code == 200
        pristine = _tree_digest(tmp_path / "demo")
        pristine_account = (tmp_path / "demo" / "account.json").read_bytes()
        workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
        assert workspace.status_code == 200
        body = workspace.json()
        assert body["forecast"]["eligible"] is True
        assert body["forecast"]["synthetic"] is True
        assert body["proposal"]["allowed"] is True

        saved = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": body["decision"]["draft"]["packet_id"],
            },
        )
        assert saved.status_code == 200
        preview = client.post(
            f"/api/decision-packets/{saved.json()['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        assert preview.status_code == 200
        proposal = preview.json()["proposal"]
        assert proposal["status"] == "pending"
        assert client.get("/api/demo/status").json()["surfaces"]["paper_proposals"]["rows"] == 1

        confirmed = client.post(
            f"/api/paper/proposals/{proposal['id']}/confirm",
            json={"confirmation_token": proposal["confirmation_token"]},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["proposal"]["status"] == "confirmed"
        assert confirmed.json()["proposal"]["quote_provenance"] == "demo-synthetic"
        status = client.get("/api/demo/status").json()
        assert status["surfaces"]["orders"]["rows"] == 9
        after_confirm = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
        confirmed_quantity = after_confirm["position"]["quantity"]

        # Crash-window fixture: journal is durable, but account persistence and
        # the terminal proposal transition did not land. Startup must finish
        # this exact order; it must not execute an unrelated pending proposal.
        (tmp_path / "demo" / "account.json").write_bytes(pristine_account)
        proposal_path = tmp_path / "demo" / "orders" / "proposals" / "proposals.jsonl"
        pending_event = proposal_path.read_text(encoding="utf-8").splitlines()[0]
        proposal_path.write_text(f"{pending_event}\n", encoding="utf-8")

    restarted = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        restored_before_reset = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
        assert restored_before_reset["position"]["quantity"] == confirmed_quantity
        assert restored_before_reset["proposal"]["proposals"][0]["status"] == "confirmed"

        reset = client.post("/api/demo/reset")
        assert reset.status_code == 200
        assert reset.json()["surfaces"]["paper_proposals"]["rows"] == 0
        assert reset.json()["surfaces"]["decision_packets"]["rows"] == 0
        assert _tree_digest(tmp_path / "demo") == pristine
        restored = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
        assert restored.status_code == 200
        assert restored.json()["proposal"]["proposals"] == []


def test_demo_reset_discards_staged_drafts_from_the_replaced_root(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    workspace = app.state.instrument_workspace
    workspace._now = lambda: SCENARIO.anchor + timedelta(minutes=1)  # noqa: SLF001

    with TestClient(app) as client:
        before_reset = client.get(
            "/api/instruments/moomoo/NVDA/workspace?range=6m"
        ).json()["decision"]["draft"]
        workspace._now = lambda: SCENARIO.anchor + timedelta(minutes=2)  # noqa: SLF001
        reset = client.post("/api/demo/reset")
        revived = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": before_reset["packet_id"],
            },
        )

    assert reset.status_code == 200
    assert revived.status_code == 409
    assert "expected" in revived.json()["detail"].lower()
    assert app.state.decision_packets.all() == ()


@pytest.mark.parametrize("disposition", ["reject", "watch", "paper_proposal"])
def test_nvda_decision_packet_action_is_durable_in_under_two_minutes_and_reopens_exactly(
    tmp_path: Path,
    disposition: str,
) -> None:
    root = tmp_path / disposition / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")

    started = perf_counter()
    with TestClient(app) as client:
        workspace_response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
        assert workspace_response.status_code == 200
        workspace = workspace_response.json()
        draft = workspace["decision"]["draft"]
        assert draft["instrument"]["symbol"] == "NVDA"
        assert {scenario["kind"] for scenario in draft["scenarios"]} == {
            "bull",
            "base",
            "bear",
        }
        assert draft["evidence"]["forecast_synthetic"] is True

        saved_response = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": draft["packet_id"],
            },
        )
        assert saved_response.status_code == 200
        saved = saved_response.json()
        action_body = {
            "disposition": disposition,
            "operator_reason": (
                None if disposition == "paper_proposal" else f"Acceptance {disposition}"
            ),
            "side": "buy" if disposition == "paper_proposal" else None,
            "quantity": 1.0 if disposition == "paper_proposal" else None,
            "limit_price": None,
        }
        action_response = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json=action_body,
        )
        assert action_response.status_code == 200
        action = action_response.json()
        packet = action["packet"]
        assert packet["parent_packet_id"] == saved["packet_id"]
        assert packet["disposition"] == disposition
        assert packet["packet_id"].startswith("packet-")
        if disposition == "paper_proposal":
            assert action["proposal"]["id"] == packet["proposal_id"]
            assert action["proposal"]["status"] == "pending"
        else:
            assert action["proposal"] is None
        assert client.get(
            f"/api/decision-packets/{packet['packet_id']}"
        ).json() == packet

    elapsed = perf_counter() - started
    assert elapsed < 120

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        assert client.get(
            f"/api/decision-packets/{packet['packet_id']}"
        ).json() == packet
        reopened = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
        assert reopened["decision"]["latest"] == packet


@pytest.mark.parametrize("disposition", ["reject", "watch", "paper_proposal"])
def test_aapl_decision_packet_action_is_durable_in_under_two_minutes_and_reopens_exactly(
    tmp_path: Path,
    disposition: str,
) -> None:
    root = tmp_path / disposition / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    orders_before = app.state.account_store.get().orders
    journal_before = app.state.page_context.journal.all()

    started = perf_counter()
    with TestClient(app) as client:
        workspace_response = client.get("/api/instruments/moomoo/AAPL/workspace?range=6m")
        assert workspace_response.status_code == 200
        workspace = workspace_response.json()
        assert workspace["forecast"]["eligible"] is True
        assert workspace["proposal"]["allowed"] is True
        draft = workspace["decision"]["draft"]

        saved_response = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "AAPL",
                "selected_range": "6m",
                "expected_packet_id": draft["packet_id"],
            },
        )
        assert saved_response.status_code == 200
        saved = saved_response.json()
        action_response = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": disposition,
                "operator_reason": (
                    None if disposition == "paper_proposal" else f"Acceptance {disposition}"
                ),
                "side": "buy" if disposition == "paper_proposal" else None,
                "quantity": 1.0 if disposition == "paper_proposal" else None,
                "limit_price": None,
            },
        )
        assert action_response.status_code == 200
        action = action_response.json()
        packet = action["packet"]
        assert packet["parent_packet_id"] == saved["packet_id"]
        assert packet["disposition"] == disposition
        if disposition == "paper_proposal":
            proposal = action["proposal"]
            assert proposal["id"] == packet["proposal_id"]
            assert proposal["status"] == "pending"
            assert proposal["order_id"] is None
            assert app.state.account_store.get().orders == orders_before
            assert app.state.page_context.journal.all() == journal_before
        else:
            assert action["proposal"] is None
        assert client.get(f"/api/decision-packets/{packet['packet_id']}").json() == packet

    elapsed = perf_counter() - started
    assert elapsed < 120

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        assert client.get(f"/api/decision-packets/{packet['packet_id']}").json() == packet


@pytest.mark.parametrize("safe_disposition", ["reject", "watch"])
def test_stale_nvda_blocks_paper_but_keeps_nonpaper_decisions_and_creates_nothing(
    tmp_path: Path,
    safe_disposition: str,
) -> None:
    app = create_demo_app(
        root=tmp_path / safe_disposition / "demo",
        seed=SCENARIO.seed,
        host="127.0.0.1",
    )
    stale_now = SCENARIO.anchor + timedelta(days=10)
    app.state.instrument_workspace._now = lambda: stale_now  # noqa: SLF001
    app.state.paper_decisions._now = lambda: stale_now  # noqa: SLF001
    orders_before = app.state.account_store.get().orders

    with TestClient(app) as client:
        workspace = client.get(
            "/api/instruments/moomoo/NVDA/workspace?range=6m"
        ).json()
        draft = workspace["decision"]["draft"]
        assert draft["paper_capability"]["allowed"] is False
        assert {
            blocker["code"] for blocker in draft["paper_capability"]["blockers"]
        } & {"history-freshness", "forecast-freshness"}
        saved = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": draft["packet_id"],
            },
        ).json()

        paper = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        assert paper.status_code == 409

        safe = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": safe_disposition,
                "operator_reason": "Wait for fresh evidence",
                "side": None,
                "quantity": None,
                "limit_price": None,
            },
        )
        assert safe.status_code == 200
        assert safe.json()["packet"]["disposition"] == safe_disposition

    assert app.state.proposal_service.ledger.all() == ()
    assert app.state.account_store.get().orders == orders_before


def test_second_confirmation_risk_refusal_retains_packet_and_proposal_without_a_fill(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    filled_before = sum(
        order.status.value == "filled" for order in app.state.account_store.get().orders.values()
    )
    accepted_before = sum(
        order.status.value == "accepted"
        for order in app.state.account_store.get().orders.values()
    )

    with TestClient(app) as client:
        workspace = client.get(
            "/api/instruments/moomoo/NVDA/workspace?range=6m"
        ).json()
        draft = workspace["decision"]["draft"]
        saved = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": draft["packet_id"],
            },
        ).json()
        action = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        ).json()
        packet = action["packet"]
        proposal = action["proposal"]
        app.state.account_store.update(
            lambda account: account.model_copy(update={"kill_switch": True})
        )

        refused = client.post(
            f"/api/paper/proposals/{proposal['id']}/confirm",
            json={"confirmation_token": proposal["confirmation_token"]},
        )
        assert refused.status_code == 409
        result = refused.json()
        assert packet["proposal_id"] == proposal["id"] == result["proposal"]["id"]
        assert result["proposal"]["status"] == "rejected"
        assert result["order"]["status"] == "rejected"
        assert "kill switch" in result["blocker"].lower()
        assert client.get(
            f"/api/decision-packets/{packet['packet_id']}"
        ).json() == packet

    filled_after = sum(
        order.status.value == "filled" for order in app.state.account_store.get().orders.values()
    )
    accepted_after = sum(
        order.status.value == "accepted"
        for order in app.state.account_store.get().orders.values()
    )
    assert filled_after == filled_before
    assert accepted_after == accepted_before
