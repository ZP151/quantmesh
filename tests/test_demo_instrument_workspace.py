from __future__ import annotations

import hashlib
from pathlib import Path

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
    assert aapl.eligible is False
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

        preview = client.post(
            "/api/paper/proposals",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "artifact_id": body["forecast"]["artifact_id"],
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        assert preview.status_code == 200
        proposal = preview.json()
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
        assert _tree_digest(tmp_path / "demo") == pristine
        restored = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
        assert restored.status_code == 200
        assert restored.json()["proposal"]["proposals"] == []
