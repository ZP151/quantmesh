from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.instruments.inbox import DecisionInboxError

SCENARIO = DemoScenario()


def _draft(client: TestClient, symbol: str = "NVDA") -> dict[str, object]:
    response = client.get(f"/api/instruments/moomoo/{symbol}/workspace?range=6m")
    assert response.status_code == 200
    return response.json()["decision"]["draft"]


def _save_draft(client: TestClient, symbol: str = "NVDA") -> dict[str, object]:
    draft = _draft(client, symbol)
    response = client.post(
        "/api/decision-packets",
        json={
            "venue": "moomoo",
            "symbol": symbol,
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )
    assert response.status_code == 200
    return response.json()


def _save_and_act(
    client: TestClient,
    symbol: str,
    *,
    disposition: str,
) -> dict[str, object]:
    saved = _save_draft(client, symbol)
    response = client.post(
        f"/api/decision-packets/{saved['packet_id']}/actions",
        json={
            "disposition": disposition,
            "operator_reason": (
                "Wait for the observed entry condition."
                if disposition in {"reject", "watch"}
                else None
            ),
            "side": "buy" if disposition == "paper_proposal" else None,
            "quantity": 1.0 if disposition == "paper_proposal" else None,
            "limit_price": None,
        },
    )
    assert response.status_code == 200
    return response.json()


def _owned_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".decision-packets.lock"
    }


def _entry(payload: dict[str, object], venue: str | None, symbol: str) -> dict[str, object]:
    return next(
        item
        for item in payload["entries"]
        if item["venue"] == venue and item["symbol"] == symbol
    )


def test_inbox_is_read_only_and_pending_action_beats_newer_draft(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        pending = _save_and_act(client, "NVDA", disposition="paper_proposal")
        before = _owned_bytes(root)
        app.state.instrument_workspace._now = lambda: SCENARIO.anchor + timedelta(minutes=1)
        newer = _save_draft(client, "NVDA")
        response = client.get("/api/decision-packets")
        after = _owned_bytes(root)

    assert response.status_code == 200
    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["packet_id"] == pending["packet"]["packet_id"]
    assert nvda["packet_id"] != newer["packet_id"]
    assert nvda["attention_state"] == "paper_pending_confirmation"
    assert before != after  # The newer draft is the only intervening write.
    assert after == _owned_bytes(root)


def test_inbox_reports_not_started_and_venue_less_watchlist_as_unavailable(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    app.state.page_context.watchlist.add("QQQ", venue=None, now=SCENARIO.anchor)

    with TestClient(app) as client:
        response = client.get("/api/decision-packets")

    assert response.status_code == 200
    nvda = _entry(response.json(), "moomoo", "NVDA")
    qqq = _entry(response.json(), None, "QQQ")
    assert nvda["attention_state"] == "not_started"
    assert qqq["attention_state"] == "unavailable"
    assert "venue" in qqq["attention_reason"].lower()


def test_inbox_projects_terminal_actions_and_missing_proposal_link(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        rejected = _save_and_act(client, "NVDA", disposition="reject")
        watched = _save_and_act(client, "AAPL", disposition="watch")
        draft = _save_draft(client, "NVDA")
        response = client.get("/api/decision-packets")

    assert response.status_code == 200
    assert _entry(response.json(), "moomoo", "NVDA")["packet_id"] == rejected["packet"]["packet_id"]
    assert _entry(response.json(), "moomoo", "NVDA")["attention_state"] == "rejected"
    assert _entry(response.json(), "moomoo", "AAPL")["packet_id"] == watched["packet"]["packet_id"]
    assert _entry(response.json(), "moomoo", "AAPL")["attention_state"] == "watching"
    assert draft["disposition"] == "draft"


def test_inbox_reports_a_missing_paper_proposal_link_as_unavailable(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        linked = _save_and_act(client, "NVDA", disposition="paper_proposal")
        proposal_path = app.state.paper_decisions.ledger.root / "proposals.jsonl"
        proposal_path.write_text("", encoding="utf-8")
        unavailable = client.get("/api/decision-packets")

    assert linked["proposal"]["id"].startswith("proposal-")
    assert unavailable.status_code == 200
    assert _entry(unavailable.json(), "moomoo", "NVDA")["attention_state"] == "unavailable"


def test_inbox_corrupt_packet_replay_is_safe_409(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        app.state.decision_packets.path.write_text("{broken-json\n", encoding="utf-8")
        response = client.get("/api/decision-packets")

    assert response.status_code == 409
    assert response.json() == {
        "code": "decision_inbox_replay_unavailable",
        "message": (
            "Decision Inbox is unavailable because stored decision state cannot be replayed."
        ),
    }


def test_inbox_configured_mark_is_unavailable_for_freshness_and_position_is_context_only(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        _save_and_act(client, "NVDA", disposition="paper_proposal")
        response = client.get("/api/decision-packets")

    assert response.status_code == 200
    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["mark_context"]["status"] == "unavailable"
    assert nvda["mark_context"]["reason"] == "configured mark has no freshness evidence"
    assert nvda["position_context"] is not None
    assert nvda["position_context"]["attribution"] == "current-account-context-only"


def test_inbox_error_contract_has_only_safe_machine_fields() -> None:
    error = DecisionInboxError(
        code="decision_inbox_replay_unavailable",
        message="Decision Inbox is unavailable because stored decision state cannot be replayed.",
    )
    assert error.model_dump() == {
        "code": "decision_inbox_replay_unavailable",
        "message": (
            "Decision Inbox is unavailable because stored decision state cannot be replayed."
        ),
    }
