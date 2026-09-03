from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.domain.models import Side
from quantmesh.instruments.contracts import (
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    ProposalStatus,
)
from quantmesh.instruments.reviews import (
    DecisionOutcomeReviewService,
    DecisionReviewRecord,
    DecisionReviewStore,
)

SCENARIO = DemoScenario()


def _canonical_id(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _rehash_outer_review(record: dict[str, object]) -> dict[str, object]:
    outcome = record["outcome"]
    outcome["outcome_id"] = _canonical_id(
        "outcome", {key: value for key, value in outcome.items() if key != "outcome_id"}
    )
    record["review_id"] = _canonical_id(
        "review", {key: value for key, value in record.items() if key != "review_id"}
    )
    return record


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


def _complete_series(
    app,
    packet_id: str,
    *,
    closes: list[float] | None = None,
    ambiguous_index: int | None = None,
):
    root_packet, packet = app.state.decision_packets.lineage(packet_id)
    artifact = app.state.price_forecasts.get(root_packet.evidence.forecast_artifact_id)
    forecast_path = next(path for path in artifact.paths if path.sessions == 30)
    values = closes or [root_packet.risk_plan.entry_price] * 30
    bars = tuple(
        HistoricalBar(
            instrument=root_packet.instrument,
            timestamp=point.timestamp,
            interval="1d",
            open=close,
            high=(
                root_packet.risk_plan.target_price + 1 if index == ambiguous_index else close + 0.25
            ),
            low=(
                root_packet.risk_plan.stop_price - 1 if index == ambiguous_index else close - 0.25
            ),
            close=close,
            volume=1_000_000,
        )
        for index, (point, close) in enumerate(zip(forecast_path.points, values, strict=True))
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
    return root_packet, packet, forecast_path, complete


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


def test_review_replay_rejects_outer_rehashed_embedded_packet_and_path_tampering(
    tmp_path: Path,
) -> None:
    packet_root = tmp_path / "packet-demo"
    app = create_demo_app(root=packet_root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet = _action_packet(client, "reject")
    preview = app.state.packet_reviews.preview(packet["packet_id"])
    app.state.packet_reviews.save(
        packet["packet_id"],
        expected_outcome_id=preview.outcome.outcome_id,
        classification="inconclusive",
        note=None,
    )
    store = DecisionReviewStore(packet_root / "decisions" / "reviews")
    record = json.loads(store.path.read_text(encoding="utf-8"))
    record["outcome"]["packet"]["operator_reason"] = "outer hashes were recomputed"
    store.path.write_text(
        json.dumps(_rehash_outer_review(record), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1 is invalid"):
        store.for_packet(packet["packet_id"])

    path_root = tmp_path / "path-demo"
    path_app = create_demo_app(root=path_root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(path_app) as client:
        path_packet = _action_packet(client, "watch")
    _, action_packet, forecast_path, complete = _complete_series(path_app, path_packet["packet_id"])

    class CompleteHistory:
        def history(self, *args, **kwargs):
            return complete

    path_app.state.packet_reviews.history = CompleteHistory()
    path_app.state.packet_reviews._now = lambda: forecast_path.points[-1].timestamp  # noqa: SLF001
    path_preview = path_app.state.packet_reviews.preview(action_packet.packet_id)
    path_app.state.packet_reviews.save(
        action_packet.packet_id,
        expected_outcome_id=path_preview.outcome.outcome_id,
        classification="supported",
        note=None,
    )
    path_store = DecisionReviewStore(path_root / "decisions" / "reviews")
    record = json.loads(path_store.path.read_text(encoding="utf-8"))
    record["outcome"]["path"]["bars"][-1]["close"] += 0.1
    path_store.path.write_text(
        json.dumps(_rehash_outer_review(record), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1 is invalid"):
        path_store.for_packet(action_packet.packet_id)


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
    root_packet, packet, forecast_path, complete = _complete_series(
        app,
        packet.packet_id,
        closes=closes,
        ambiguous_index=2,
    )
    bars = complete.bars

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
    assert preview.outcome.path.expected_session_times == tuple(
        point.timestamp for point in forecast_path.points
    )
    assert preview.outcome.attribution_policy_version == "strict-close-v1"
    assert preview.outcome.attribution_basis == "completed_daily_close"
    assert preview.outcome.attribution_equality == "equality_does_not_cross"
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


def test_path_rejects_missing_forecast_session_future_generation_and_live_tail(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet_json = _action_packet(client, "watch")
    _, packet, forecast_path, complete = _complete_series(app, packet_json["packet_id"])
    service = app.state.packet_reviews
    service._now = lambda: forecast_path.points[-1].timestamp  # noqa: SLF001

    class FixedHistory:
        series = complete

        def history(self, *args, **kwargs):
            return self.series

    history = FixedHistory()
    service.history = history
    missing = complete.model_copy(update={"bars": complete.bars[:10] + complete.bars[11:]})
    history.series = missing
    partial = service.preview(packet.packet_id)
    assert partial.outcome.evidence_status == "partial"
    assert "expected 30-session timestamp" in partial.outcome.path.reason

    history.series = complete.model_copy(
        update={"generated_at": forecast_path.points[-1].timestamp + timedelta(seconds=1)}
    )
    future = service.preview(packet.packet_id)
    assert future.outcome.evidence_status == "unavailable"
    assert "generated after the review clock" in future.outcome.path.reason

    live_bar = complete.bars[0].model_copy(update={"is_live_tail": True})
    history.series = complete.model_copy(update={"bars": (live_bar, *complete.bars[1:])})
    live = service.preview(packet.packet_id)
    assert live.outcome.evidence_status == "unavailable"
    assert "live tail" in live.outcome.path.reason


def test_post_recomposes_immediately_before_append_and_refuses_source_drift(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        packet_json = _action_packet(client, "watch")
    _, packet, forecast_path, complete = _complete_series(app, packet_json["packet_id"])
    changed = complete.model_copy(
        update={
            "bars": (
                *complete.bars[:-1],
                complete.bars[-1].model_copy(update={"close": complete.bars[-1].close + 0.1}),
            ),
        }
    )

    class DriftingHistory:
        calls = 0

        def history(self, *args, **kwargs):
            self.calls += 1
            return complete if self.calls <= 2 else changed

    service = app.state.packet_reviews
    service.history = DriftingHistory()
    service._now = lambda: forecast_path.points[-1].timestamp  # noqa: SLF001
    preview = service.preview(packet.packet_id)

    with pytest.raises(ValueError, match="source evidence changed before review append"):
        service.save(
            packet.packet_id,
            expected_outcome_id=preview.outcome.outcome_id,
            classification="supported",
            note=None,
        )
    assert service.review_store.all() == ()


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

    paper = preview.outcome.paper
    sell_paper = paper.model_copy(
        update={
            "proposal": paper.proposal.model_copy(update={"side": Side.SELL}),
            "order": paper.order.model_copy(update={"side": Side.SELL}),
        }
    )
    _, sell_deviation, sell_mark, _ = DecisionOutcomeReviewService._metrics(
        preview.root_packet,
        preview.outcome.path,
        sell_paper,
    )
    average = paper.order.average_fill_price
    assert average is not None
    expected_deviation = (
        preview.root_packet.risk_plan.entry_price - average
    ) / preview.root_packet.risk_plan.risk_per_unit
    assert sell_deviation.value == pytest.approx(expected_deviation)
    if preview.outcome.path.bars:
        expected_mark = (
            average - preview.outcome.path.bars[-1].close
        ) / preview.root_packet.risk_plan.risk_per_unit
        assert sell_mark.value == pytest.approx(expected_mark)

    saved_review = app.state.packet_reviews.save(
        action["packet"]["packet_id"],
        expected_outcome_id=preview.outcome.outcome_id,
        classification="inconclusive",
        note=None,
    )
    assert saved_review.review is not None
    store = app.state.packet_reviews.review_store
    original = json.loads(store.path.read_text(encoding="utf-8"))
    record = json.loads(json.dumps(original))
    record["outcome"]["paper"]["proposal"]["quantity"] += 1
    store.path.write_text(
        json.dumps(_rehash_outer_review(record), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1 is invalid"):
        store.for_packet(action["packet"]["packet_id"])
    record = json.loads(json.dumps(original))
    future_order_at = datetime.fromisoformat(record["outcome"]["evaluated_at"]) + timedelta(hours=1)
    record["outcome"]["paper"]["order"]["created_at"] = future_order_at.isoformat().replace(
        "+00:00", "Z"
    )
    for offset, event in enumerate(record["outcome"]["paper"]["order"]["events"], 1):
        event["timestamp"] = (
            (future_order_at + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")
        )
    rehashed = _rehash_outer_review(record)
    with pytest.raises(ValueError, match="order evidence exceeds its evaluation boundary"):
        DecisionReviewRecord.model_validate_json(json.dumps(rehashed))
    record = json.loads(json.dumps(original))
    record["outcome"]["paper"]["order"]["quantity"] += 1
    store.path.write_text(
        json.dumps(_rehash_outer_review(record), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1 is invalid"):
        store.for_packet(action["packet"]["packet_id"])


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
    saved_review = app.state.packet_reviews.save(
        action["packet"]["packet_id"],
        expected_outcome_id=preview.outcome.outcome_id,
        classification="inconclusive",
        note="Risk refusal is exact and has no fill.",
    )
    restarted = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    reopened = restarted.state.packet_reviews.preview(action["packet"]["packet_id"])
    assert reopened.review.review_id == saved_review.review.review_id
    assert reopened.review.outcome.outcome_id == preview.outcome.outcome_id
    assert reopened.review.outcome.paper.reason == preview.outcome.paper.reason

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
    watch_saved = watch_app.state.packet_reviews.save(
        watch_packet["packet_id"],
        expected_outcome_id=watch_preview.outcome.outcome_id,
        classification="inconclusive",
        note=None,
    )
    assert watch_saved.review is not None
    store = watch_app.state.packet_reviews.review_store
    record = json.loads(store.path.read_text(encoding="utf-8"))
    record["outcome"]["monitoring"]["evaluations"][0]["evaluation_id"] = (
        "evaluation-ffffffffffffffffffffffff"
    )
    store.path.write_text(
        json.dumps(_rehash_outer_review(record), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1 is invalid"):
        store.for_packet(watch_packet["packet_id"])


def test_pending_blocked_and_accepted_unfilled_paper_states_are_exact(tmp_path: Path) -> None:
    pending_app = create_demo_app(
        root=tmp_path / "pending-demo", seed=SCENARIO.seed, host="127.0.0.1"
    )
    with TestClient(pending_app) as client:
        workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m").json()
        saved = _save(client, workspace["decision"]["draft"]).json()
        action = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": 1.0,
            },
        ).json()
        pending = pending_app.state.packet_reviews.preview(action["packet"]["packet_id"])
        assert pending.outcome.paper.state == "pending_no_order"
        confirmed = client.post(
            f"/api/paper/proposals/{action['proposal']['id']}/confirm",
            json={"confirmation_token": action["proposal"]["confirmation_token"]},
        )
        assert confirmed.status_code == 200
    accepted = pending_app.state.packet_reviews.preview(action["packet"]["packet_id"])
    assert accepted.outcome.paper.state == "accepted_unfilled"
    assert accepted.outcome.paper.order.fills == []

    blocked_app = create_demo_app(
        root=tmp_path / "blocked-demo", seed=SCENARIO.seed, host="127.0.0.1"
    )
    with TestClient(blocked_app) as client:
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
        ledger = blocked_app.state.paper_decisions.ledger
        proposal = ledger.get(action["proposal"]["id"])
        ledger.transition(
            proposal.model_validate(
                proposal.model_dump()
                | {"status": ProposalStatus.BLOCKED, "blockers": ("exact blocker",)}
            ),
            recorded_at=SCENARIO.anchor,
        )
    blocked = blocked_app.state.packet_reviews.preview(action["packet"]["packet_id"])
    assert blocked.outcome.paper.state == "blocked"
    assert blocked.outcome.paper.reason == "exact blocker"
