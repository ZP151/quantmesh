"""Exact frozen forecast versus realized-close response projections."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_decision_packets import NOW, _history_for_composition, packet, watch_child
from test_scenario_lab import compose, lab_forecast, pinned_forecast  # noqa: F401

from quantmesh.instruments.api import instrument_router
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.instruments.reviews import DecisionOutcomeReviewService, DecisionReviewStore
from quantmesh.instruments.workspace import _forecast_summary


def station(tmp_path, *, horizon=7, actuals=None, days=30, registry=None, forecast=None):
    forecast = forecast or lab_forecast()
    root = compose(horizon, forecast=forecast)
    packets = DecisionPacketStore(tmp_path / "packets")
    packets.record(root)
    child = packets.record(watch_child(root))
    selected = next(path for path in forecast.paths if path.sessions == (horizon or 30))
    base = _history_for_composition()
    actuals = (
        actuals
        if actuals is not None
        else {point.timestamp: point.p50 for point in selected.points}
    )
    bars = tuple(
        base.bars[-1].model_copy(
            update={
                "timestamp": timestamp,
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
            }
        )
        for timestamp, close in sorted(actuals.items())
    )
    series = base.model_copy(
        update={
            "as_of": NOW + timedelta(days=days),
            "bars": bars,
            "coverage": base.coverage.model_copy(
                update={
                    "start": bars[0].timestamp if bars else NOW,
                    "end": bars[-1].timestamp if bars else NOW,
                    "rows": len(bars),
                }
            ),
        }
    )
    source = SimpleNamespace(series=series)
    if registry is None:
        artifact = SimpleNamespace(
            **forecast.model_dump(exclude={"paths"}),
            id=forecast.artifact_id,
            instrument=root.instrument,
            paths=forecast.paths,
            calendar=base.calendar,
            adjustment=base.adjustment,
        )
        registry = SimpleNamespace(get=lambda artifact_id: artifact)
    service = DecisionOutcomeReviewService(
        packet_store=packets,
        review_store=DecisionReviewStore(tmp_path / "reviews"),
        forecast_registry=registry,
        history=SimpleNamespace(history=lambda *args, **kwargs: source.series),
        proposal_ledger=None,
        journal=None,
        monitoring=None,
        now=lambda: NOW + timedelta(days=days),
    )
    return service, child, source


def assert_no_scores(comparison):
    for field in (
        "mean_absolute_error",
        "benchmark_mae",
        "interval_hits",
        "interval_coverage",
        "terminal_error",
    ):
        assert getattr(comparison, field) is None


def test_complete_scores_are_hand_calculated_and_interval_edges_are_inclusive(tmp_path):
    # Frozen medians 161..167, intervals median +/- 8, and root last close 159.
    actuals = dict(
        zip(
            (point.timestamp for point in lab_forecast().paths[0].points),
            (153.0, 170.0, 163.0, 173.0, 156.0, 168.0, 164.0),
            strict=True,
        )
    )
    service, child, _ = station(tmp_path, actuals=actuals)
    state = service.preview(child.packet_id)
    comparison = state.forecast_comparison
    assert comparison.status == "complete"
    assert comparison.reason is None
    assert comparison.policy_version == "exact-close-v1"
    assert comparison.outcome_id == state.outcome.outcome_id
    assert comparison.forecast_artifact_id == state.root_packet.evidence.forecast_artifact_id
    assert comparison.horizon_sessions == comparison.observed_sessions == 7
    assert [row.absolute_error for row in comparison.rows] == [8, 8, 0, 9, 9, 2, 3]
    assert [row.within_interval for row in comparison.rows] == [
        True,
        True,
        True,
        False,
        False,
        True,
        True,
    ]
    assert comparison.mean_absolute_error == pytest.approx(39 / 7)
    assert state.root_packet.market_state.latest_close == 159
    assert comparison.benchmark_mae == pytest.approx(52 / 7)
    assert comparison.interval_hits == 5
    assert comparison.interval_coverage == pytest.approx(5 / 7)
    assert comparison.terminal_error == -3


@pytest.mark.parametrize("horizon", [7, 30, None])
def test_selected_seven_thirty_and_legacy_horizon(tmp_path, horizon):
    service, child, _ = station(tmp_path, horizon=horizon)
    comparison = service.preview(child.packet_id).forecast_comparison
    assert comparison.horizon_sessions == (horizon or 30)
    assert len(comparison.rows) == (horizon or 30)
    assert comparison.mean_absolute_error == 0


def test_missing_middle_timestamp_never_shifts_actuals_or_produces_aggregate_scores(tmp_path):
    points = lab_forecast().paths[0].points
    actuals = {point.timestamp: point.p50 + 1 for point in points if point.session != 3}
    # Unscheduled bar must not fill the missing session or count as an observation.
    actuals[points[2].timestamp + timedelta(hours=1)] = 200.0
    service, child, _ = station(tmp_path, actuals=actuals)
    comparison = service.preview(child.packet_id).forecast_comparison
    assert comparison.status == "partial"
    assert comparison.reason
    assert comparison.observed_sessions == 6
    assert comparison.rows[2].actual_close is None
    assert comparison.rows[2].absolute_error is None
    assert comparison.rows[2].within_interval is None
    assert comparison.rows[3].actual_close == points[3].p50 + 1
    assert_no_scores(comparison)


@pytest.mark.parametrize(
    "days,observations,status", [(2, 2, "pending"), (0, 0, "pending"), (30, 0, "unavailable")]
)
def test_pending_or_empty_paths_never_report_zero_performance(tmp_path, days, observations, status):
    actuals = {
        point.timestamp: point.p50 for point in lab_forecast().paths[0].points[:observations]
    }
    service, child, _ = station(tmp_path, actuals=actuals, days=days)
    comparison = service.preview(child.packet_id).forecast_comparison
    assert comparison.status == status
    assert comparison.reason
    assert comparison.observed_sessions == observations
    assert len(comparison.rows) == 7
    assert_no_scores(comparison)


def test_missing_exact_forecast_or_mismatched_expected_times_refuses_comparison(tmp_path):
    from quantmesh.instruments.forecast_outcomes import compare_forecast_outcome

    service, child, _ = station(tmp_path)
    complete = service.preview(child.packet_id).outcome
    # Defense at the pure projection boundary in addition to durable validation.
    malformed = complete.model_copy(
        update={
            "path": complete.path.model_copy(
                update={
                    "expected_session_times": complete.path.expected_session_times[1:],
                }
            )
        }
    )
    comparison = compare_forecast_outcome(malformed)
    assert comparison.status == "unavailable"
    assert "timestamp" in comparison.reason
    assert comparison.rows == ()
    assert_no_scores(comparison)
    service.forecast_registry = None
    comparison = service.preview(child.packet_id).forecast_comparison
    assert comparison.status == "unavailable"
    assert comparison.rows == ()
    assert_no_scores(comparison)


def test_real_registry_api_saved_comparison_wins_after_history_replacement_and_restart(
    tmp_path, request
):
    registry, artifact, _ = request.getfixturevalue("pinned_forecast")
    service, child, source = station(
        tmp_path, registry=registry, forecast=_forecast_summary(artifact), days=60
    )
    app = FastAPI()
    app.include_router(instrument_router())
    app.state.packet_reviews = service
    client = TestClient(app)
    url = f"/decision-packets/{child.packet_id}/outcome-review"
    preview = client.get(url)
    assert preview.status_code == 200
    frozen = preview.json()["forecast_comparison"]
    assert frozen["status"] == "complete"
    saved = client.post(
        url,
        json={
            "expected_outcome_id": frozen["outcome_id"],
            "classification": "mixed",
            "note": "Exact path review",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["forecast_comparison"] == frozen
    review_bytes = tuple(path.read_bytes() for path in (tmp_path / "reviews").glob("*.jsonl"))
    assert review_bytes
    assert all(b"forecast_comparison" not in payload for payload in review_bytes)
    assert "forecast_comparison" not in saved.json()["outcome"]
    assert "forecast_comparison" not in saved.json()["review"]
    source.series = source.series.model_copy(update={"bars": ()})
    service.review_store = DecisionReviewStore(tmp_path / "reviews")
    replay = client.get(url)
    assert replay.status_code == 200
    assert replay.json()["outcome"]["outcome_id"] != frozen["outcome_id"]
    assert replay.json()["forecast_comparison"] == frozen
    assert (
        tuple(path.read_bytes() for path in (tmp_path / "reviews").glob("*.jsonl")) == review_bytes
    )
    assert packet().packet_id == "packet-d6709c5629b810b53bd23219"
