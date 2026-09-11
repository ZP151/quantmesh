"""Fast selected-horizon evidence, immutable replay and refusal regressions."""

from datetime import timedelta

import pytest
from test_decision_packets import (
    NOW,
    _history_for_composition,
    _ready_risk,
    _workspace_forecast,
    packet,
    watch_child,
)

from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.contracts import (
    DecisionPacket,
    ForecastPath,
    HistoryRange,
    ProposalCapability,
    WorkspaceLiveEvidence,
)
from quantmesh.instruments.decision_analysis import compose_decision_packet
from quantmesh.instruments.decision_packets import DecisionPacketStore, decision_packet_id


def lab_forecast():
    forecast = _workspace_forecast()
    metric = forecast.metrics[0].model_copy(
        update={
            "residual_count": 60,
            "interval_test_count": 30,
            "validation_start": NOW - timedelta(days=59),
            "validation_end": NOW,
            "test_start": NOW - timedelta(days=29),
            "test_end": NOW,
        }
    )
    return forecast.model_copy(
        update={
            "paths": (
                ForecastPath(sessions=7, points=forecast.paths[0].points[:7]),
                forecast.paths[0],
            ),
            "metrics": (metric.model_copy(update={"sessions": 7}), metric),
        }
    )


def compose(horizon=7, *, forecast=None, history=None, as_of=NOW):
    return compose_decision_packet(
        history=history or _history_for_composition(),
        forecast=forecast or lab_forecast(),
        live=WorkspaceLiveEvidence(status="unavailable", reason="fixture"),
        risk=_ready_risk(),
        proposal=ProposalCapability(allowed=True, blockers=(), proposals=()),
        account=PaperAccount(cash=10_000),
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=as_of,
        horizon=horizon,
    )


def test_legacy_serialization_preserves_pre_extension_canonical_id():
    legacy = packet()
    assert legacy.packet_id == "packet-d6709c5629b810b53bd23219"
    assert "scenario_lab" not in legacy.model_dump()
    assert "scenario_lab" not in legacy.model_dump_json()
    assert DecisionPacket.model_validate_json(legacy.model_dump_json()) == legacy


@pytest.mark.parametrize(
    "calendar,elapsed_days,allowed",
    [("XNYS", 5, True), ("legacy", 5, False), ("XNYS", 7, False)],
)
def test_legacy_route_dispatches_daily_freshness_by_forecast_version(
    calendar, elapsed_days, allowed
):
    from quantmesh.instruments.forecast import _canonical_json, _config, _sha256

    # Friday September 4 at New York midnight; Monday September 7 is Labor Day.
    base = _history_for_composition()
    offset = timedelta(days=1, hours=8)
    as_of = NOW + timedelta(days=elapsed_days)
    bars = tuple(bar.model_copy(update={"timestamp": bar.timestamp + offset}) for bar in base.bars)
    history = base.model_copy(
        update={
            "calendar": "XNYS",
            "as_of": as_of,
            "generated_at": as_of,
            "bars": bars,
            "coverage": base.coverage.model_copy(
                update={"start": bars[0].timestamp, "end": bars[-1].timestamp}
            ),
        }
    )
    forecast = _workspace_forecast()
    forecast = forecast.model_copy(
        update={
            "config_digest": _sha256(_canonical_json(_config(calendar))),
            "generated_at": as_of,
            "train_start": bars[0].timestamp,
            "train_end": bars[-1].timestamp,
            "paths": tuple(
                path.model_copy(
                    update={
                        "points": tuple(
                            point.model_copy(
                                update={"timestamp": point.timestamp + timedelta(days=8)}
                            )
                            for point in path.points
                        )
                    }
                )
                for path in forecast.paths
            ),
        }
    )
    result = compose(None, history=history, forecast=forecast, as_of=as_of)
    assert result.scenario_lab is None
    assert result.paper_capability.allowed is allowed, result.paper_capability.blockers
    assert (
        any(blocker.code == "history-freshness" for blocker in result.paper_capability.blockers)
        is not allowed
    )


def test_selected_horizon_changes_targets_and_survives_store_restart(tmp_path):
    seven, thirty = compose(7), compose(30)
    assert seven.scenario_lab.selected_horizon == 7
    assert seven.scenario_lab.confidence == "qualified"
    assert seven.scenario_lab.history == _history_for_composition()
    assert [s.target for s in seven.scenarios] == [172.0, 167.0, 162.0]
    assert all(s.probability is None for s in seven.scenarios)
    assert seven.packet_id != thirty.packet_id
    store = DecisionPacketStore(tmp_path)
    store.record(seven)
    store.record(thirty)
    saved = store.record(watch_child(seven))
    assert DecisionPacketStore(tmp_path).get(saved.packet_id) == saved


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"mae": 3.0}, "MAE"),
        ({"mae": 3.1}, "MAE"),
        ({"residual_count": 29, "interval_test_count": 29}, "residual"),
        ({"interval_test_count": 29}, "interval"),
        ({"coverage_80": 0.59}, "coverage"),
    ],
)
def test_selected_evidence_requires_strict_improvement_and_sample_gate(change, reason):
    forecast = lab_forecast()
    forecast = forecast.model_copy(
        update={
            "metrics": (
                forecast.metrics[0].model_copy(update=change),
                forecast.metrics[1],
            )
        }
    )
    result = compose(forecast=forecast)
    assert result.scenario_lab.confidence == "low-confidence"
    assert reason in " ".join(result.scenario_lab.reasons)
    assert not result.paper_capability.allowed


@pytest.mark.parametrize(
    "change",
    [
        {"paths": ()},
        {"metrics": ()},
        {"dataset_revision": 2},
        {"generated_at": NOW + timedelta(seconds=1)},
    ],
)
def test_missing_or_misbound_selected_evidence_abstains(change):
    result = compose(forecast=lab_forecast().model_copy(update=change))
    assert result.scenario_lab.confidence == "abstain"
    assert not result.paper_capability.allowed


def test_stale_and_artifact_wide_blockers_cannot_be_relaxed():
    for change in (
        {"generated_at": NOW - timedelta(days=2)},
        {"eligible": False, "blockers": ("126-session coverage failed",)},
    ):
        result = compose(forecast=lab_forecast().model_copy(update=change))
        assert result.scenario_lab.confidence != "qualified"
        assert not result.paper_capability.allowed


def test_child_cannot_change_frozen_horizon_or_history(tmp_path):
    root = compose()
    store = DecisionPacketStore(tmp_path)
    store.record(root)
    child = watch_child(root)
    altered = child.model_copy(
        update={"scenario_lab": child.scenario_lab.model_copy(update={"selected_horizon": 30})}
    )
    altered = altered.model_copy(update={"packet_id": decision_packet_id(altered)})
    with pytest.raises(ValueError, match="semantic facts"):
        store.record(altered)


@pytest.fixture(scope="module")
def pinned_forecast(tmp_path_factory):
    from test_price_forecast import _binding, _write_matching_lake

    from quantmesh.instruments.forecast import PriceForecastRegistry, run_price_forecast

    location = tmp_path_factory.mktemp("exact-lab")
    series = _history_for_composition()
    _write_matching_lake(location / "lake", series)
    registry = PriceForecastRegistry(
        location / "forecasts", lake_root=location / "lake", bindings=(_binding(series),)
    )
    artifact = run_price_forecast(series, generated_at=NOW, model_version="fixture-v1")
    registry.record(artifact)
    return registry, artifact, series


def workspace_for(tmp_path, pinned_forecast, *, replacement=None):
    from types import SimpleNamespace

    from quantmesh.instruments.workspace import InstrumentWorkspaceService

    registry, _, series = pinned_forecast
    history = SimpleNamespace(history=lambda *args, **kwargs: replacement or series)
    return InstrumentWorkspaceService(
        history=history,
        forecasts=registry,
        account_provider=lambda: PaperAccount(cash=10_000),
        marks_provider=lambda: {},
        decision_packets=DecisionPacketStore(tmp_path),
        now=lambda: NOW,
    )


def test_workspace_save_binds_exact_horizon_and_reopens_without_current_history(
    tmp_path,
    pinned_forecast,
):
    from quantmesh.domain.models import Venue
    from quantmesh.instruments.decision_packets import DecisionPacketService

    _, artifact, _ = pinned_forecast
    workspace = workspace_for(tmp_path, pinned_forecast)
    service = DecisionPacketService(
        store=DecisionPacketStore(tmp_path), workspace_provider=lambda: workspace, proposals=None
    )
    rendered = workspace.render(
        Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS, horizon=7, forecast_id=artifact.id
    )
    draft = rendered.decision.draft
    assert rendered.forecast.artifact_id == artifact.id
    with pytest.raises(ValueError, match="scope|horizon"):
        service.save_draft(
            Venue.MOOMOO,
            "NVDA",
            HistoryRange.SIX_MONTHS,
            expected_packet_id=draft.packet_id,
            horizon=30,
        )
    saved = service.save_draft(
        Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS, expected_packet_id=draft.packet_id, horizon=7
    )
    assert saved.scenario_lab.history == rendered.history
    workspace.clear_staged_drafts()
    replay = DecisionPacketStore(tmp_path).get(saved.packet_id)
    assert replay.scenario_lab.selected_horizon == 7
    assert replay.scenario_lab.history.bars[-1].close == 159.0


@pytest.mark.parametrize("mismatch", ["missing", "revision", "bytes"])
def test_exact_forecast_never_falls_back_or_accepts_misbound_chart(
    tmp_path,
    pinned_forecast,
    mismatch,
):
    from quantmesh.domain.models import Venue

    _, artifact, series = pinned_forecast
    replacement = series
    if mismatch == "revision":
        replacement = series.model_copy(update={"dataset_revision": 99})
    if mismatch == "bytes":
        replacement = series.model_copy(
            update={
                "bars": series.bars[:-1] + (series.bars[-1].model_copy(update={"volume": 999.0}),)
            }
        )
    workspace = workspace_for(tmp_path, pinned_forecast, replacement=replacement)
    result = workspace.render(
        Venue.MOOMOO,
        "NVDA",
        HistoryRange.SIX_MONTHS,
        horizon=7,
        forecast_id="forecast-" + "f" * 24 if mismatch == "missing" else artifact.id,
    )
    assert result.forecast is None
    assert result.forecast_unavailable_reason
    assert result.decision.draft.scenario_lab.confidence == "abstain"
    assert not result.decision.draft.paper_capability.allowed
    from quantmesh.instruments.decision_packets import DecisionPacketService

    refused_id = "forecast-" + "f" * 24 if mismatch == "missing" else artifact.id
    service = DecisionPacketService(
        store=DecisionPacketStore(tmp_path), workspace_provider=lambda: workspace, proposals=None
    )
    with pytest.raises(ValueError, match="scope"):
        workspace.staged_draft(
            result.decision.draft.packet_id,
            venue=Venue.MOOMOO,
            symbol="NVDA",
            selected_range=HistoryRange.SIX_MONTHS,
            horizon=7,
            forecast_id="forecast-wrong",
        )
    saved = service.save_draft(
        Venue.MOOMOO,
        "NVDA",
        HistoryRange.SIX_MONTHS,
        expected_packet_id=result.decision.draft.packet_id,
        horizon=7,
        forecast_id=refused_id,
    )
    assert saved == result.decision.draft
    assert (
        DecisionPacketStore(tmp_path).record(watch_child(saved)).scenario_lab == saved.scenario_lab
    )


def test_monitor_and_review_choose_seven_but_legacy_keeps_thirty(tmp_path, pinned_forecast):
    from quantmesh.instruments.monitoring import DecisionWatchService, DecisionWatchStore
    from quantmesh.instruments.reviews import DecisionOutcomeReviewService, DecisionReviewStore
    from quantmesh.instruments.workspace import _forecast_summary

    registry, artifact, _ = pinned_forecast
    seven = compose(forecast=_forecast_summary(artifact))
    legacy = compose(None, forecast=_forecast_summary(artifact))
    packets = DecisionPacketStore(tmp_path / "packets")
    monitor = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitor"),
        forecast_registry=registry,
    )
    review = DecisionOutcomeReviewService(
        packet_store=packets,
        review_store=DecisionReviewStore(tmp_path / "reviews"),
        forecast_registry=registry,
        history=None,
        proposal_ledger=None,
        journal=None,
        monitoring=None,
    )
    for candidate, expected in ((seven, 7), (legacy, 30)):
        target = artifact.paths[0 if expected == 7 else 1].points[-1].timestamp
        assert monitor._drift_definition(candidate).target_at == target
        _, times, error = review._forecast_target(candidate)
        assert error is None
        assert len(times) == expected
        path = review._path(candidate, artifact, times, None, NOW)
        assert path.target_at == target


def test_http_selected_query_and_save_roundtrip(tmp_path, pinned_forecast):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from quantmesh.instruments.api import instrument_router
    from quantmesh.instruments.decision_packets import DecisionPacketService

    _, artifact, _ = pinned_forecast
    app = FastAPI()
    workspace = workspace_for(tmp_path, pinned_forecast)
    app.state.instrument_workspace = workspace
    app.state.decision_packets = DecisionPacketStore(tmp_path)
    app.state.decision_packet_service = DecisionPacketService(
        store=app.state.decision_packets,
        workspace_provider=lambda: workspace,
        proposals=None,
    )
    app.include_router(instrument_router(), prefix="/api")
    with TestClient(app) as client:
        response = client.get(
            "/api/instruments/moomoo/NVDA/workspace",
            params={"range": "6m", "horizon": 7, "forecast_id": artifact.id},
        )
        assert response.status_code == 200, response.text
        draft = response.json()["decision"]["draft"]
        assert draft["scenario_lab"]["selected_horizon"] == 7
        saved = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "horizon": 7,
                "forecast_id": artifact.id,
                "expected_packet_id": draft["packet_id"],
            },
        )
        assert saved.status_code == 200, saved.text
        action = client.post(
            f"/api/decision-packets/{draft['packet_id']}/actions",
            json={
                "disposition": "watch",
                "operator_reason": "Wait for evidence",
            },
        )
        assert action.status_code == 200, action.text
        assert action.json()["packet"]["scenario_lab"] == draft["scenario_lab"]
        assert (
            client.get(
                "/api/instruments/moomoo/NVDA/workspace", params={"range": "6m", "horizon": 126}
            ).status_code
            == 422
        )


def test_outcome_replay_rejects_changed_selected_session_sequence(tmp_path, pinned_forecast):
    from quantmesh.instruments.reviews import (
        DecisionOutcomeReviewService,
        DecisionOutcomeSnapshot,
        DecisionReviewStore,
    )
    from quantmesh.instruments.workspace import _forecast_summary

    registry, artifact, _ = pinned_forecast
    root = compose(forecast=_forecast_summary(artifact))
    store = DecisionPacketStore(tmp_path / "packets")
    store.record(root)
    child = store.record(watch_child(root))
    reviews = DecisionOutcomeReviewService(
        packet_store=store,
        review_store=DecisionReviewStore(tmp_path / "reviews"),
        forecast_registry=registry,
        history=None,
        proposal_ledger=None,
        journal=None,
        monitoring=None,
        now=lambda: NOW,
    )
    outcome = reviews.preview(child.packet_id).outcome
    wrong_times = tuple(point.timestamp for point in artifact.paths[1].points)
    altered = outcome.model_dump()
    altered["path"].update(target_at=wrong_times[-1], expected_session_times=wrong_times)
    altered["horizon_target_at"] = wrong_times[-1]
    import hashlib
    import json

    altered_json = outcome.model_copy(
        update={
            "path": outcome.path.model_copy(
                update={"target_at": wrong_times[-1], "expected_session_times": wrong_times}
            ),
            "horizon_target_at": wrong_times[-1],
        }
    ).model_dump(mode="json", exclude={"outcome_id"})
    altered["outcome_id"] = (
        "outcome-"
        + hashlib.sha256(
            json.dumps(altered_json, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
    )
    with pytest.raises(ValueError, match="selected|forecast timestamps"):
        DecisionOutcomeSnapshot.model_validate(altered)


def test_new_lab_and_proposal_age_skip_xnys_holidays_while_legacy_keeps_weekdays():
    from datetime import UTC, datetime

    from test_scenario_calendar import _xnys_series

    from quantmesh.instruments.forecast import run_price_forecast
    from quantmesh.instruments.proposals import forecast_freshness_blocker
    from quantmesh.instruments.workspace import _forecast_summary

    series = _xnys_series(datetime(2026, 12, 24, 5, tzinfo=UTC)).model_copy(
        update={
            "source": "demo-synthetic",
            "range": HistoryRange.SIX_MONTHS,
        }
    )
    current = datetime(2026, 12, 28, 22, tzinfo=UTC)
    xnys = run_price_forecast(
        series,
        generated_at=series.as_of,
        model_version="drift-conformal-xnys-v2",
        session_calendar="XNYS",
    )
    legacy = run_price_forecast(series, generated_at=series.as_of, model_version="fixture-v1")
    assert forecast_freshness_blocker(xnys, current) is None
    assert forecast_freshness_blocker(legacy, current) is not None
    result = compose(
        history=series.model_copy(update={"as_of": current}),
        forecast=_forecast_summary(xnys),
        as_of=current,
    )
    assert not any("stale" in reason for reason in result.scenario_lab.reasons)
    assert not any(
        blocker.code.endswith("freshness") for blocker in result.paper_capability.blockers
    )
    after_two_sessions = datetime(2026, 12, 29, 22, tzinfo=UTC)
    assert forecast_freshness_blocker(xnys, after_two_sessions) is not None
