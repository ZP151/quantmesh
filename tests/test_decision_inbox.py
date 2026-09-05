from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quantmesh.api.watchlist import WatchlistStore
from quantmesh.api.workstation import create_workstation_app
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.domain.models import Instrument, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.inbox import (
    DecisionInboxError,
    DecisionInboxMarkContext,
    DecisionInboxMonitoringSummary,
    DecisionInboxPositionContext,
    DecisionInboxReviewSummary,
    DecisionInboxService,
)
from quantmesh.instruments.monitoring import DecisionWatchObservation, WatchConditionKind
from quantmesh.instruments.reviews import ReviewClassification

SCENARIO = DemoScenario()


def test_baseline_inbox_preserves_persisted_watchlist_without_packet_services(
    tmp_path: Path,
) -> None:
    watchlist = WatchlistStore(tmp_path / "watchlist")
    watchlist.add("NVDA", venue=Venue.MOOMOO, now=SCENARIO.anchor)
    watchlist.add("UNKNOWN", venue=None, now=SCENARIO.anchor)
    app = create_workstation_app(
        account=PaperAccount(cash=100_000),
        watchlist=WatchlistStore(tmp_path / "watchlist"),
        markets={"moomoo": {"NVDA": 184.2}},
        workspace_clock=lambda: SCENARIO.anchor,
        host="127.0.0.1",
    )
    with TestClient(app) as client:
        response = client.get("/api/decision-packets")
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 2
    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["attention_state"] == "not_started"
    assert nvda["mark_context"]["value"] == 184.2
    assert _entry(response.json(), None, "UNKNOWN")["attention_state"] == "unavailable"
    for row in response.json()["entries"]:
        assert row["packet_id"] is None
        assert row["paper"] is None
        assert row["monitoring"] is None
        assert row["review"] is None


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
        item for item in payload["entries"] if item["venue"] == venue and item["symbol"] == symbol
    )


def test_inbox_is_read_only_and_pending_action_beats_newer_draft(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        pending = _save_and_act(client, "NVDA", disposition="paper_proposal")
        app.state.instrument_workspace._now = lambda: SCENARIO.anchor + timedelta(minutes=1)
        newer = _save_draft(client, "NVDA")
        before_get = _owned_bytes(root)
        response = client.get("/api/decision-packets")
        after_get = _owned_bytes(root)

    assert response.status_code == 200
    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["packet_id"] == pending["packet"]["packet_id"]
    assert nvda["packet_id"] != newer["packet_id"]
    assert nvda["attention_state"] == "paper_pending_confirmation"
    assert before_get == after_get


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


def test_inbox_projects_a_saved_draft_when_no_terminal_action_exists(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        draft = _save_draft(client, "NVDA")
        response = client.get("/api/decision-packets")

    assert response.status_code == 200
    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["packet_id"] == draft["packet_id"]
    assert nvda["attention_state"] == "draft"


def test_inbox_prefers_newer_passive_terminal_action_over_older_open_paper(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        paper = _save_and_act(client, "NVDA", disposition="paper_proposal")
        proposal = paper["proposal"]
        confirmation = client.post(
            f"/api/paper/proposals/{proposal['id']}/confirm",
            json={"confirmation_token": proposal["confirmation_token"]},
        )
        app.state.instrument_workspace._now = lambda: SCENARIO.anchor + timedelta(minutes=1)
        rejected = _save_and_act(client, "NVDA", disposition="reject")
        app.state.packet_reviews._now = lambda: SCENARIO.anchor + timedelta(minutes=1)
        response = client.get("/api/decision-packets")

    assert confirmation.status_code == 200
    assert response.status_code == 200
    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["packet_id"] == rejected["packet"]["packet_id"]
    assert nvda["attention_state"] == "rejected"


@pytest.mark.parametrize(
    ("advance", "expected_state"),
    [
        (timedelta(days=3), "blocked"),
        (timedelta(0), "paper_open"),
    ],
)
def test_inbox_projects_confirmed_and_blocked_paper_lifecycle_states(
    tmp_path: Path,
    advance: timedelta,
    expected_state: str,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        action = _save_and_act(client, "NVDA", disposition="paper_proposal")
        proposal = action["proposal"]
        app.state.paper_decisions._now = lambda: SCENARIO.anchor + advance
        confirmation = client.post(
            f"/api/paper/proposals/{proposal['id']}/confirm",
            json={"confirmation_token": proposal["confirmation_token"]},
        )
        response = client.get("/api/decision-packets")

    assert confirmation.status_code == (409 if advance else 200)
    assert response.status_code == 200
    assert _entry(response.json(), "moomoo", "NVDA")["attention_state"] == expected_state


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


@pytest.mark.parametrize("field", ["id", "config_digest"])
def test_inbox_fails_closed_for_packet_proposal_evidence_identity_mismatch(
    tmp_path: Path,
    field: str,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        _save_and_act(client, "NVDA", disposition="paper_proposal")
        proposal = app.state.paper_decisions.ledger.all()[0]
        forged = proposal.model_copy(
            update={
                field: "proposal-" + "f" * 24 if field == "id" else "f" * 64,
            }
        )
        app.state.packet_reviews.proposal_ledger = SimpleNamespace(get=lambda _id: forged)
        response = client.get("/api/decision-packets")

    assert response.status_code == 409
    assert response.json()["code"] == "decision_inbox_replay_unavailable"


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
    assert nvda["position_context"] is None

    position = app.state.account.positions["moomoo:NVDA"]
    allowed = DecisionInboxService._position_context(
        Venue.MOOMOO,
        "NVDA",
        app.state.account,
        DecisionInboxMarkContext(value=100.0, status="available"),
    )
    assert allowed == DecisionInboxPositionContext(
        quantity=position.quantity,
        average_cost=position.average_cost,
        realized_pnl=position.realized_pnl,
        mark=100.0,
        attribution="current-account-context-only",
    )


def test_inbox_contracts_reject_noncanonical_future_monitoring_and_review_ids() -> None:
    with pytest.raises(ValidationError):
        DecisionInboxMonitoringSummary(
            registration_id="registration-not-canonical",
            latest_evaluation_id="evaluation-" + "0" * 24,
            triggered=False,
        )
    with pytest.raises(ValidationError):
        DecisionInboxReviewSummary(
            review_id="review-not-canonical",
            state=ReviewClassification.INCONCLUSIVE,
        )


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


@pytest.mark.parametrize("lifecycle", ["pending", "risk_rejected", "filled", "reviewed", "watch"])
def test_shadow_paper_watch_review_exact_ids_and_restart(tmp_path: Path, lifecycle: str) -> None:
    root = tmp_path / lifecycle
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        action = _save_and_act(
            client, "NVDA", disposition="watch" if lifecycle == "watch" else "paper_proposal"
        )
        packet_id = action["packet"]["packet_id"]
        if lifecycle in {"risk_rejected", "filled", "reviewed"}:
            if lifecycle == "risk_rejected":
                app.state.account_store.update(
                    lambda account: account.model_copy(update={"kill_switch": True})
                )
            proposal = action["proposal"]
            confirmation = client.post(
                f"/api/paper/proposals/{proposal['id']}/confirm",
                json={"confirmation_token": proposal["confirmation_token"]},
            )
            assert confirmation.status_code == (409 if lifecycle == "risk_rejected" else 200)
        if lifecycle == "watch":
            packet = app.state.decision_packets.get(packet_id)
            service = app.state.packet_monitoring
            registration = service.register(packet_id, (WatchConditionKind.ENTRY_ZONE,))
            for sequence, price in enumerate(
                (packet.risk_plan.entry_price * 1.1, packet.risk_plan.entry_price), start=1
            ):
                timestamp = SCENARIO.anchor + timedelta(seconds=sequence)
                service.check(
                    registration.registration_id,
                    DecisionWatchObservation(
                        evaluated_at=timestamp,
                        instrument=Instrument.model_validate(packet.instrument.model_dump()),
                        price=price,
                        source="local-workspace",
                        provenance="demo-synthetic",
                        data_time=timestamp,
                        received_at=timestamp,
                        sequence=sequence,
                        sequence_gap=False,
                    ),
                )
            app.state.packet_reviews._now = lambda: SCENARIO.anchor + timedelta(seconds=2)
        preview = app.state.packet_reviews.preview(packet_id)
        if lifecycle == "reviewed":
            preview = app.state.packet_reviews.save(
                packet_id,
                expected_outcome_id=preview.outcome.outcome_id,
                classification="inconclusive",
                note="Entry only; no attributable exit.",
            )
        before = _owned_bytes(root)
        response = client.get("/api/decision-packets")
        assert response.status_code == 200
        row = _entry(response.json(), "moomoo", "NVDA")
        assert before == _owned_bytes(root)
        assert row["packet_id"] == packet_id
        assert (
            row["attention_state"]
            == {
                "pending": "paper_pending_confirmation",
                "risk_rejected": "blocked",
                "filled": "paper_open",
                "reviewed": "reviewed",
                "watch": "watch_triggered",
            }[lifecycle]
        )
        assert row["outcome_id"] == preview.outcome.outcome_id
        assert row["evidence_status"] == preview.outcome.evidence_status
        if lifecycle == "watch":
            assert row["monitoring"]["registration_id"] == registration.registration_id
            assert row["monitoring"]["latest_evaluation_id"] == (
                preview.outcome.monitoring.evaluations[-1].evaluation_id
            )
            assert row["monitoring"]["event_ids"] == list(preview.outcome.monitoring.event_ids)
            assert row["monitoring"]["triggered"] is True
        else:
            paper = row["paper"]
            assert paper["proposal_id"] == action["proposal"]["id"]
            order = preview.outcome.paper.order
            assert paper["order_id"] == (order.order_id if order else None)
            assert paper["order_status"] == (order.status if order else None)
            assert paper["filled_quantity"] == (
                sum(fill.quantity for fill in order.fills) if order else None
            )
        if lifecycle == "reviewed":
            assert row["review"]["review_id"] == preview.review.review_id
            assert row["review"]["outcome_id"] == preview.review.outcome.outcome_id
        if lifecycle == "filled":
            journal = app.state.packet_reviews.journal
            forged_order = preview.outcome.paper.order.model_copy(
                update={"order_id": "other-order"}
            )
            app.state.packet_reviews.journal = SimpleNamespace(get=lambda _id: forged_order)
            unavailable = client.get("/api/decision-packets")
            assert unavailable.status_code == 409
            assert unavailable.json()["code"] == "decision_inbox_replay_unavailable"
            app.state.packet_reviews.journal = journal
    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    if lifecycle == "watch":
        restarted.state.packet_reviews._now = lambda: SCENARIO.anchor + timedelta(seconds=2)
    with TestClient(restarted) as client:
        assert _entry(client.get("/api/decision-packets").json(), "moomoo", "NVDA") == row


def test_shadow_pending_paper_stays_neutral_when_confirmation_freshness_fails(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        action = _save_and_act(client, "NVDA", disposition="paper_proposal")
        app.state.decision_inbox._now = lambda: SCENARIO.anchor + timedelta(days=3)
        row = _entry(client.get("/api/decision-packets").json(), "moomoo", "NVDA")
        assert row["attention_state"] == "paper_pending_confirmation"
        assert "confirmation currently fails freshness" in row["attention_reason"]
        assert row["paper"]["proposal_id"] == action["proposal"]["id"]
        assert row["paper"]["order_id"] is None


def test_shadow_missing_exact_order_is_unavailable_without_fallback(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        action = _save_and_act(client, "NVDA", disposition="paper_proposal")
        proposal = action["proposal"]
        assert (
            client.post(
                f"/api/paper/proposals/{proposal['id']}/confirm",
                json={"confirmation_token": proposal["confirmation_token"]},
            ).status_code
            == 200
        )

        def missing_order(_order_id: str):
            raise ValueError("missing exact order")

        app.state.packet_reviews.journal = SimpleNamespace(get=missing_order)
        response = client.get("/api/decision-packets")
        assert response.status_code == 200
        row = _entry(response.json(), "moomoo", "NVDA")
        assert row["attention_state"] == "unavailable"
        assert row["packet_id"] == action["packet"]["packet_id"]
        assert row["paper"]["order_id"] is None
