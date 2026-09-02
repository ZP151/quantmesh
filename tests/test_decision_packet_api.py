from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import HistoryRange

SCENARIO = DemoScenario()


def _draft(client: TestClient, symbol: str = "NVDA") -> dict[str, object]:
    response = client.get(f"/api/instruments/moomoo/{symbol}/workspace?range=6m")
    assert response.status_code == 200
    return response.json()["decision"]["draft"]


def _save(client: TestClient, draft: dict[str, object], symbol: str = "NVDA"):
    return client.post(
        "/api/decision-packets",
        json={
            "venue": "moomoo",
            "symbol": symbol,
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )


def test_workspace_uses_the_bound_packet_service_and_save_refuses_expected_id_drift(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    original = app.state.instrument_workspace

    class RecordingWorkspace:
        def __init__(self) -> None:
            self.calls = 0

        def render(self, *args, **kwargs):
            self.calls += 1
            return original.render(*args, **kwargs)

    recording = RecordingWorkspace()
    app.state.instrument_workspace = recording

    with TestClient(app) as client:
        draft = _draft(client)
        mismatch = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": "packet-" + "f" * 24,
            },
        )

    assert recording.calls == 2
    assert draft["as_of"] == SCENARIO.anchor.isoformat().replace("+00:00", "Z")
    assert mismatch.status_code == 409
    assert "expected" in mismatch.json()["detail"].lower()
    assert app.state.decision_packets.latest(
        Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS
    ) is None


@pytest.mark.parametrize("disposition", ["reject", "watch"])
def test_reject_and_watch_are_exactly_reopenable_and_idempotent(
    tmp_path: Path,
    disposition: str,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft)
        assert saved.status_code == 200
        path = f"/api/decision-packets/{saved.json()['packet_id']}/actions"
        payload = {
            "disposition": disposition,
            "operator_reason": "Wait for the observed entry condition.",
            "side": None,
            "quantity": None,
            "limit_price": None,
        }
        first = client.post(path, json=payload)
        replay = client.post(path, json=payload)
        exact = client.get(
            f"/api/decision-packets/{first.json()['packet']['packet_id']}"
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert first.json()["packet"]["version"] == 2
    assert first.json()["proposal"] is None
    assert exact.status_code == 200
    assert exact.json() == first.json()["packet"]
    assert app.state.paper_decisions.ledger.all() == ()


def test_stale_packet_blocks_paper_without_creating_a_proposal(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    stale_at = SCENARIO.anchor + timedelta(days=3)
    app.state.instrument_workspace._now = lambda: stale_at  # noqa: SLF001

    with TestClient(app) as client:
        draft = _draft(client)
        codes = [item["code"] for item in draft["paper_capability"]["blockers"]]
        saved = _save(client, draft)
        blocked = client.post(
            f"/api/decision-packets/{saved.json()['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert {"history-freshness", "forecast-freshness"}.issubset(codes)
    assert saved.status_code == 200
    assert blocked.status_code == 409
    assert app.state.paper_decisions.ledger.all() == ()


def test_untrusted_packet_blocks_paper_without_creating_a_proposal(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    artifact = next(
        item
        for item in app.state.price_forecasts.all()
        if item.instrument.symbol == "NVDA"
    )
    untrusted = artifact.model_copy(
        update={"eligible": False, "blockers": ("quality evaluation failed",)}
    )

    class UntrustedForecasts:
        @staticmethod
        def all():
            return [untrusted]

    app.state.instrument_workspace._forecasts = UntrustedForecasts()  # noqa: SLF001

    with TestClient(app) as client:
        draft = _draft(client)
        codes = [item["code"] for item in draft["paper_capability"]["blockers"]]
        saved = _save(client, draft)
        blocked = client.post(
            f"/api/decision-packets/{saved.json()['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert "forecast-ineligible" in codes
    assert saved.status_code == 200
    assert blocked.status_code == 409
    assert app.state.paper_decisions.ledger.all() == ()


def test_packet_bound_paper_action_never_confirms_and_risk_refusal_stays_bound(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft).json()
        before_orders = len(app.state.demo.seeded.journal.all())
        action = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        replay = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        result = action.json()
        assert result["proposal"]["status"] == "pending"
        assert len(app.state.demo.seeded.journal.all()) == before_orders

        account_store = app.state.account_store
        account_store.replace(account_store.get().model_copy(update={"kill_switch": True}))
        refused = client.post(
            f"/api/paper/proposals/{result['proposal']['id']}/confirm",
            json={"confirmation_token": result["proposal"]["confirmation_token"]},
        )

    assert action.status_code == 200
    assert replay.json() == result
    assert result["packet"]["proposal_id"] == result["proposal"]["id"]
    assert refused.status_code == 409
    assert refused.json()["proposal"]["status"] == "rejected"
    assert refused.json()["order"]["status"] == "rejected"
    assert result["packet"]["packet_id"] == app.state.decision_packets.latest(
        Venue.MOOMOO,
        "NVDA",
        HistoryRange.SIX_MONTHS,
    ).packet_id


def test_legacy_proposal_route_requires_an_exact_packet_artifact_binding(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft).json()
        aapl = next(
            artifact
            for artifact in app.state.price_forecasts.all()
            if artifact.instrument.symbol == "AAPL"
        )
        bare = client.post(
            "/api/paper/proposals",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "artifact_id": draft["evidence"]["forecast_artifact_id"],
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        mismatch = client.post(
            "/api/paper/proposals",
            json={
                "venue": "moomoo",
                "symbol": "AAPL",
                "artifact_id": aapl.id,
                "decision_packet_id": saved["packet_id"],
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert bare.status_code == 409
    assert "decision packet" in bare.json()["detail"].lower()
    assert mismatch.status_code == 409
    assert "artifact" in mismatch.json()["detail"].lower()
    assert app.state.paper_decisions.ledger.all() == ()


def test_clean_demo_restart_reopens_identical_packet_bytes(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft).json()
        action = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "watch",
                "operator_reason": "Wait for a verified breakout.",
                "side": None,
                "quantity": None,
                "limit_price": None,
            },
        ).json()
    packet_path = root / "decisions" / "packets" / "decision-packets.jsonl"
    before = packet_path.read_bytes()

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        reopened = client.get(
            f"/api/decision-packets/{action['packet']['packet_id']}"
        )

    assert reopened.status_code == 200
    assert reopened.json() == action["packet"]
    assert packet_path.read_bytes() == before
