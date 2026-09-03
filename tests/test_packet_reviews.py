from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.instruments.contracts import HistoricalBar, HistoricalSeries, HistoryRange
from quantmesh.instruments.reviews import DecisionReviewStore

SCENARIO = DemoScenario()


def _save(client: TestClient, draft: dict[str, object]):
    return client.post(
        "/api/decision-packets",
        json={
            "venue": "moomoo",
            "symbol": "NVDA",
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )


def _action_packet(client: TestClient, disposition: str = "reject") -> dict[str, object]:
    workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
    draft = workspace["decision"]["draft"]
    saved = client.post(
        "/api/decision-packets",
        json={
            "venue": "moomoo",
            "symbol": "NVDA",
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )
    assert saved.status_code == 200
    action = client.post(
        f"/api/decision-packets/{saved.json()['packet_id']}/actions",
        json={
            "disposition": disposition,
            "operator_reason": f"Review the exact {disposition} decision.",
            "side": None,
            "quantity": None,
            "limit_price": None,
        },
    )
    assert action.status_code == 200
    return action.json()["packet"]


def _ledger_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "decisions/reviews" not in path.as_posix()
    }


def test_review_is_one_atomic_idempotent_restart_safe_record(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet = _action_packet(client)
        before_preview = _ledger_bytes(root)
        state = app.state.packet_reviews.preview(packet["packet_id"])
        assert _ledger_bytes(root) == before_preview
        assert state.packet_id == packet["packet_id"]
        assert state.outcome.packet == state.root_packet.model_copy(
            update={
                "packet_id": packet["packet_id"],
                "version": packet["version"],
                "parent_packet_id": packet["parent_packet_id"],
                "created_at": state.outcome.packet.created_at,
                "disposition": state.outcome.packet.disposition,
                "operator_reason": state.outcome.packet.operator_reason,
            }
        )
        assert state.outcome.evidence_status in {"pending", "partial", "unavailable"}
        assert state.outcome.realized_paper_r.status == "unavailable"

        before_save = _ledger_bytes(root)
        first = app.state.packet_reviews.save(
            packet["packet_id"],
            expected_outcome_id=state.outcome.outcome_id,
            classification="inconclusive",
            note="  Need   complete exit evidence.  ",
        )
        assert first.review is not None
        assert first.review.note == "Need complete exit evidence."
        assert first.review.outcome == state.outcome
        assert _ledger_bytes(root) == before_save

        replay = app.state.packet_reviews.save(
            packet["packet_id"],
            expected_outcome_id=state.outcome.outcome_id,
            classification="inconclusive",
            note="Need complete exit evidence.",
        )
        assert replay == first
        with pytest.raises(ValueError, match="different review"):
            app.state.packet_reviews.save(
                packet["packet_id"],
                expected_outcome_id=state.outcome.outcome_id,
                classification="supported",
                note=None,
            )

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    reopened = restarted.state.packet_reviews.preview(packet["packet_id"])
    assert reopened.review == first.review
    assert reopened.review.review_id.startswith("review-")
    assert reopened.review.outcome.outcome_id == state.outcome.outcome_id


def test_preview_refuses_drafts_and_corrupt_review_store(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
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
        with pytest.raises(ValueError, match="non-draft"):
            app.state.packet_reviews.preview(saved["packet_id"])

        packet = _action_packet(client, "watch")
        preview = app.state.packet_reviews.preview(packet["packet_id"])
        app.state.packet_reviews.save(
            packet["packet_id"],
            expected_outcome_id=preview.outcome.outcome_id,
            classification="inconclusive",
            note=None,
        )

    store = DecisionReviewStore(root / "decisions" / "reviews")
    store.path.write_text("{broken-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1 is invalid"):
        store.for_packet(packet["packet_id"])


def test_partial_or_unavailable_outcome_rejects_conclusive_classification(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet = _action_packet(client, "watch")
        preview = app.state.packet_reviews.preview(packet["packet_id"])
        assert preview.outcome.evidence_status != "complete"
        with pytest.raises(ValueError, match="only inconclusive"):
            app.state.packet_reviews.save(
                packet["packet_id"],
                expected_outcome_id=preview.outcome.outcome_id,
                classification="mixed",
                note=None,
            )


def test_outcome_fence_is_stable_between_requests_when_no_local_evidence_changes(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet = _action_packet(client, "watch")
    service = app.state.packet_reviews
    service._now = lambda: SCENARIO.anchor  # noqa: SLF001
    preview = service.preview(packet["packet_id"])
    service._now = lambda: SCENARIO.anchor + timedelta(seconds=1)  # noqa: SLF001

    saved = service.save(
        packet["packet_id"],
        expected_outcome_id=preview.outcome.outcome_id,
        classification="inconclusive",
        note=None,
    )

    assert saved.review is not None
    assert saved.review.outcome == preview.outcome


def test_complete_daily_path_uses_strict_thresholds_and_discloses_same_bar_ambiguity(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet_json = _action_packet(client, "watch")
    root_packet, packet = app.state.decision_packets.lineage(packet_json["packet_id"])
    artifact = app.state.price_forecasts.get(root_packet.evidence.forecast_artifact_id)
    forecast_path = next(path for path in artifact.paths if path.sessions == 30)
    support = root_packet.market_state.support
    resistance = root_packet.market_state.resistance
    invalidation = root_packet.market_state.invalidation
    entry = root_packet.risk_plan.entry_price
    closes = [
        resistance,
        resistance + 1,
        support - 0.5,
        invalidation - 0.5,
        entry,
        *([entry] * 25),
    ]
    bars = tuple(
        HistoricalBar(
            instrument=root_packet.instrument,
            timestamp=point.timestamp,
            interval="1d",
            open=close,
            high=(root_packet.risk_plan.target_price + 1 if index == 2 else close + 0.25),
            low=(root_packet.risk_plan.stop_price - 1 if index == 2 else close - 0.25),
            close=close,
            volume=1_000_000,
        )
        for index, (point, close) in enumerate(zip(forecast_path.points, closes, strict=True))
    )
    baseline = app.state.history.history(
        root_packet.instrument.venue,
        root_packet.instrument.symbol,
        HistoryRange.ONE_YEAR,
        as_of=root_packet.as_of,
    )
    complete = HistoricalSeries.model_validate(
        baseline.model_dump()
        | {
            "as_of": forecast_path.points[-1].timestamp,
            "bars": bars,
            "coverage": baseline.coverage.model_dump()
            | {
                "start": bars[0].timestamp,
                "end": bars[-1].timestamp,
                "rows": len(bars),
            },
            "gaps": (),
            "duplicates": (),
        }
    )

    class CompleteHistory:
        def history(self, *args, **kwargs):
            return complete

    service = app.state.packet_reviews
    service.history = CompleteHistory()
    service._now = lambda: forecast_path.points[-1].timestamp  # noqa: SLF001
    preview = service.preview(packet.packet_id)

    assert preview.outcome.evidence_status == "complete"
    assert preview.outcome.path.path_digest is not None
    assert preview.outcome.path.license == complete.license
    assert preview.outcome.path.generated_at == complete.generated_at
    assert preview.outcome.path.interval == "1d"
    assert preview.outcome.path.adjustment == "unadjusted"
    bull, base, bear = preview.outcome.scenarios
    assert bull.threshold_at == bars[1].timestamp
    assert base.threshold_at == bars[0].timestamp
    assert bear.threshold_at == bars[2].timestamp
    assert bull.invalidation_at == bars[2].timestamp
    assert bear.invalidation_state == "unavailable"
    assert preview.outcome.target_stop_ordering == "ambiguous_same_bar"
    assert preview.outcome.gross_path_r.value == pytest.approx(0.0)
    saved = service.save(
        packet.packet_id,
        expected_outcome_id=preview.outcome.outcome_id,
        classification="supported",
        note="Observed path reached the pinned horizon.",
    )
    assert saved.review.classification == "supported"


def test_filled_open_entry_has_fill_metrics_but_never_fabricates_realized_r(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
        saved = _save(client, workspace["decision"]["draft"]).json()
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
        confirmed = client.post(
            f"/api/paper/proposals/{action['proposal']['id']}/confirm",
            json={"confirmation_token": action["proposal"]["confirmation_token"]},
        )
        assert confirmed.status_code == 200

    preview = app.state.packet_reviews.preview(action["packet"]["packet_id"])
    assert preview.outcome.paper.state == "filled_open"
    assert preview.outcome.entry_fill_deviation_r.status == "available"
    assert preview.outcome.mark_to_market_paper_r.status == "unavailable"
    assert preview.outcome.realized_paper_r.status == "unavailable"
    assert "exit fills" in preview.outcome.realized_paper_r.reason


def test_risk_refusal_and_operator_invoked_watch_coverage_remain_exact(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
        saved = _save(client, workspace["decision"]["draft"]).json()
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
        app.state.account_store.update(
            lambda account: account.model_copy(update={"kill_switch": True})
        )
        refused = client.post(
            f"/api/paper/proposals/{action['proposal']['id']}/confirm",
            json={"confirmation_token": action["proposal"]["confirmation_token"]},
        )
        assert refused.status_code == 409

    preview = app.state.packet_reviews.preview(action["packet"]["packet_id"])
    assert preview.outcome.paper.state == "risk_rejected"
    assert "kill switch" in preview.outcome.paper.reason.lower()
    assert preview.outcome.paper.order.fills == []
    assert preview.outcome.realized_paper_r.status == "unavailable"

    watch_app = create_demo_app(root=tmp_path / "watch-demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(watch_app) as client:
        watch_packet = _action_packet(client, "watch")
        checked = client.post(
            f"/api/decision-packets/{watch_packet['packet_id']}/watch-conditions",
            json={"kinds": ["entry_zone"]},
        )
        assert checked.status_code == 200
    watch_preview = watch_app.state.packet_reviews.preview(watch_packet["packet_id"])
    assert watch_preview.outcome.monitoring.registration is not None
    assert watch_preview.outcome.monitoring.status in {"coverage_incomplete", "triggered"}
    if watch_preview.outcome.monitoring.status == "coverage_incomplete":
        assert watch_preview.outcome.monitoring.event_ids == ()
