"""Calibration forecast reports: window structure, point-in-time replay,
registry discipline and byte-stable artifacts (issue #36, Phase C).
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.events.forecast import (
    FORECASTS_FILE,
    ForecastMarket,
    ForecastObservation,
    ForecastReport,
    ForecastReportRegistry,
    ForecastWindowSpec,
    forecast_artifact_paths,
    forecast_report_id,
    run_forecast,
    run_forecast_report,
)
from quantmesh.events.models import EventMarket, EventVenue, Outcome, ResolutionRule

_T0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
_HOUR = timedelta(hours=1)


def _market(
    venue_market_id: str = "mkt-1",
    *,
    venue: EventVenue = EventVenue.KALSHI,
    resolution: list[str] | None = None,
    resolved_at: datetime | None = None,
    title: str = "Will it rain?",
) -> EventMarket:
    return EventMarket(
        venue=venue,
        venue_market_id=venue_market_id,
        event_ticker="event-1",
        title=title,
        category="test",
        outcomes=[
            Outcome(name="Yes", venue_outcome_id="yes"),
            Outcome(name="No", venue_outcome_id="no"),
        ],
        resolution_rule=ResolutionRule.of("fixture rule text"),
        resolution=list(resolution or []),
        resolved_at=resolved_at,
    )


def _obs(
    index: int, probability: float | None = None, confidence: float = 1.0
) -> ForecastObservation:
    p = 0.3 + 0.01 * index if probability is None else probability
    return ForecastObservation(
        timestamp=_T0 + index * _HOUR,
        probability=p,
        liquidity_confidence=confidence,
    )


def _grid(n: int, **kwargs) -> list[ForecastObservation]:
    return [_obs(index, **kwargs) for index in range(n)]


def _spec(train: int = 5, test: int = 5, step: int | None = None) -> ForecastWindowSpec:
    return ForecastWindowSpec(
        train_observations=train,
        test_observations=test,
        step_observations=step if step is not None else test,
    )


class TestObservationAndMarketValidation:
    def test_naive_timestamp_refused(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            ForecastObservation(
                timestamp=datetime(2026, 8, 1, 0, 0),
                probability=0.5,
                liquidity_confidence=1.0,
            )

    def test_out_of_range_probability_refused(self):
        with pytest.raises(ValueError):
            ForecastObservation(timestamp=_T0, probability=1.5)

    def test_unsorted_observations_refused(self):
        with pytest.raises(ValueError, match="strictly ascending"):
            ForecastMarket(
                market=_market(),
                observations=[_obs(2), _obs(0), _obs(1)],
            )

    def test_duplicate_timestamp_refused(self):
        with pytest.raises(ValueError, match="strictly ascending"):
            ForecastMarket(market=_market(), observations=[_obs(0), _obs(0)])

    def test_empty_observation_grid_refused(self):
        with pytest.raises(ValueError):
            ForecastMarket(market=_market(), observations=[])


class TestWindowSpec:
    def test_minimum_training_bounds(self):
        with pytest.raises(ValueError):
            ForecastWindowSpec(
                train_observations=1, test_observations=1, step_observations=1
            )

    def test_step_cannot_smaller_than_test(self):
        with pytest.raises(ValueError, match="step_observations"):
            _spec(train=2, test=3, step=2)

    def test_test_starts_walk_the_grid(self):
        assert _spec(train=10, test=5).test_starts(30) == [10, 15, 20, 25]

    def test_exactly_fitting_grid_has_one_start(self):
        assert _spec(train=5, test=5).test_starts(10) == [5]

    def test_insufficient_grid_fails_closed(self):
        with pytest.raises(ValueError, match="cannot host"):
            _spec(train=5, test=5).test_starts(9)


class TestReportId:
    def test_setup_only_and_deterministic(self):
        commit = "cafe1234567"
        universe = [_market("a"), _market("b")]
        first = forecast_report_id(
            commit=commit, universe=universe, window_spec=_spec(), n_bins=10
        )
        again = forecast_report_id(
            commit=commit, universe=universe, window_spec=_spec(), n_bins=10
        )
        assert first == again
        assert len(first) == 16
        assert set(first) <= set("0123456789abcdef")

    def test_universe_order_invariance(self):
        universe = [_market("a"), _market("b")]
        assert forecast_report_id(
            commit="cafe1234567", universe=universe, window_spec=_spec(), n_bins=10
        ) == forecast_report_id(
            commit="cafe1234567", universe=list(reversed(universe)), window_spec=_spec(), n_bins=10
        )

    def test_each_setup_element_changes_the_id(self):
        base = dict(commit="cafe1234567", universe=[_market("a")], window_spec=_spec(), n_bins=10)
        baseline = forecast_report_id(**base)
        assert forecast_report_id(**{**base, "commit": "cafe1234568"}) != baseline
        assert forecast_report_id(**{**base, "n_bins": 5}) != baseline
        other_spec = _spec(train=6, test=5, step=5)
        assert forecast_report_id(**{**base, "window_spec": other_spec}) != baseline


class TestRunForecast:
    def test_window_boundaries_and_structure(self):
        grid = _grid(5)
        metrics, per_market = run_forecast(
            [ForecastMarket(market=_market("m"), observations=grid)],
            window_spec=_spec(train=2, test=1, step=1),
        )
        windows = per_market[0].windows
        assert [w.index for w in windows] == [0, 1, 2]
        window = windows[1]
        assert window.train_end == _T0 + 2 * _HOUR
        assert window.test_start == _T0 + 3 * _HOUR
        assert window.test_end == _T0 + 3 * _HOUR
        assert window.n_observations == 1
        assert window.n_resolved == 0
        assert window.brier is None
        assert window.calibration_bins == []
        assert metrics["n_windows_total"] == 3
        assert metrics["n_evaluated_windows"] == 0
        assert metrics["mean_brier"] is None

    def test_unresolved_market_never_evaluates(self):
        market = _market(resolution=None)
        _, per_market = run_forecast(
            [ForecastMarket(market=market, observations=_grid(10))],
            window_spec=_spec(train=5, test=5),
        )
        assert all(window.brier is None for window in per_market[0].windows)

    def test_resolved_market_evaluates_with_calibration_bins(self):
        market = _market(resolution=["Yes"], resolved_at=_T0 + 20 * _HOUR)
        _, per_market = run_forecast(
            [ForecastMarket(market=market, observations=_grid(30))],
            window_spec=_spec(train=10, test=5, step=5),
        )
        windows = per_market[0].windows
        assert [w.index for w in windows] == [0, 1, 2, 3]
        assert windows[3].n_resolved == 5
        assert windows[3].brier is not None
        assert len(windows[3].calibration_bins) == 10
        assert metrics_market_ids_are_composite(per_market) == {"kalshi:mkt-1"}

    def test_all_zero_confidence_window_has_no_weighted_estimate(self):
        grid = [
            ForecastObservation(
                timestamp=_T0 + index * _HOUR,
                probability=0.5,
                liquidity_confidence=0.0,
            )
            for index in range(4)
        ]
        market = _market(resolution=["Yes"], resolved_at=_T0 + 3 * _HOUR)
        _, per_market = run_forecast(
            [ForecastMarket(market=market, observations=grid)],
            window_spec=_spec(train=2, test=1, step=1),
        )
        windows = per_market[0].windows
        # Window 1 (observation at T+3h, on the resolution) is resolved
        # but carries no weight: the estimate is plain brier only.
        assert windows[0].n_resolved == 0
        assert windows[1].n_resolved == 1
        assert windows[1].brier == pytest.approx(0.25)
        assert windows[1].liquidity_weighted_brier is None

    def test_split_resolution_is_refused(self):
        market = _market(resolution=["Yes", "No"], resolved_at=_T0 + 20 * _HOUR)
        with pytest.raises(ValueError, match="split resolution"):
            run_forecast(
                [ForecastMarket(market=market, observations=_grid(30))],
                window_spec=_spec(train=5, test=5, step=5),
            )

    def test_resolution_without_timestamp_is_refused(self):
        market = _market(resolution=["Yes"], resolved_at=None)
        with pytest.raises(ValueError, match="cannot be replayed"):
            run_forecast(
                [ForecastMarket(market=market, observations=_grid(30))],
                window_spec=_spec(train=5, test=5, step=5),
            )

    def test_duplicate_universe_membership_refused(self):
        with pytest.raises(ValueError, match="more than once"):
            run_forecast(
                [
                    ForecastMarket(market=_market("m"), observations=_grid(10)),
                    ForecastMarket(market=_market("m"), observations=_grid(10)),
                ],
                window_spec=_spec(train=5, test=5),
            )

    def test_empty_universe_refused(self):
        with pytest.raises(ValueError, match="at least one market"):
            run_forecast([], window_spec=_spec(train=5, test=5))

    def test_out_of_range_bins_refused(self):
        with pytest.raises(ValueError, match="n_bins"):
            run_forecast(
                [ForecastMarket(market=_market(), observations=_grid(10))],
                window_spec=_spec(train=5, test=5),
                n_bins=101,
            )


def metrics_market_ids_are_composite(per_market):
    return {market.market_id for market in per_market}


class TestPointInTimeReplay:
    """The acceptance property: resolution events participate only from
    their own timestamp onward.

    A window that closed before the resolution stays None even after the
    market resolves; flipping the resolution changes only the windows
    that overlap the resolution timestamp, never the earlier ones — the
    outcome cannot leak backward into windows that could not have seen
    it.
    """

    def _replay_report(self, resolution: list[str]) -> list:
        market = _market("mkt-replay", resolution=resolution, resolved_at=_T0 + 12 * _HOUR)
        _, per_market = run_forecast(
            [ForecastMarket(market=market, observations=_grid(20))],
            window_spec=_spec(train=5, test=5, step=5),
        )
        return per_market[0].windows

    def test_windows_before_resolution_stay_unresolved(self):
        windows = self._replay_report(["No"])
        assert [w.index for w in windows] == [0, 1, 2]
        # Window 0 closes at T+9h, 3h before the resolution: no outcome.
        assert windows[0].brier is None
        assert windows[0].n_resolved == 0
        # Window 1 spans T+10h..T+14h: observations 10-11 are strictly
        # older than the resolution (T+12h) and never see it; 12-14 are
        # at or after the resolution instant and do.
        assert windows[1].n_resolved == 3
        # Brier over p = 0.42, 0.43, 0.44 against outcome No (0.0).
        assert windows[1].brier == pytest.approx(0.184967)
        assert windows[2].n_resolved == 5
        assert windows[2].brier == pytest.approx(0.2211)

    def test_resolution_flip_never_leaks_into_closed_windows(self):
        before = self._replay_report(["No"])
        after = self._replay_report(["Yes"])
        # The pre-resolution window cannot observe either outcome.
        assert before[0].brier is None
        assert after[0].brier is None
        # The overlapping and post-resolution windows flip with the outcome.
        assert before[1].brier == pytest.approx(0.184967)
        assert after[1].brier == pytest.approx(0.324967)
        assert before[2].brier == pytest.approx(0.2211)
        assert after[2].brier == pytest.approx(0.2811)


class TestReportModel:
    def test_wrong_id_refused(self):
        market = _market("a")
        metrics, per_market = run_forecast(
            [ForecastMarket(market=market, observations=_grid(10))],
            window_spec=_spec(train=5, test=5, step=5),
        )
        with pytest.raises(ValueError, match="does not match"):
            ForecastReport(
                id="0" * 16,
                commit="cafe1234567",
                universe=[market],
                window_spec=_spec(train=5, test=5, step=5),
                n_bins=10,
                created_at=_T0,
                metrics=metrics,
                markets=per_market,
            )

    def test_market_count_mismatch_refused(self):
        first_market = _market("a")
        second_market = _market("b")
        metrics, per_market = run_forecast(
            [ForecastMarket(market=first_market, observations=_grid(10))],
            window_spec=_spec(train=5, test=5, step=5),
        )
        with pytest.raises(ValueError, match="evaluations"):
            ForecastReport(
                id=forecast_report_id(
                    commit="cafe1234567",
                    universe=[first_market, second_market],
                    window_spec=_spec(train=5, test=5, step=5),
                    n_bins=10,
                ),
                commit="cafe1234567",
                universe=[first_market, second_market],
                window_spec=_spec(train=5, test=5, step=5),
                n_bins=10,
                created_at=_T0,
                metrics=metrics,
                markets=per_market,
            )

    def test_naive_created_at_refused(self):
        market = _market("a")
        metrics, per_market = run_forecast(
            [ForecastMarket(market=market, observations=_grid(10))],
            window_spec=_spec(train=5, test=5, step=5),
        )
        with pytest.raises(ValueError, match="timezone-aware"):
            ForecastReport(
                id=forecast_report_id(
                    commit="cafe1234567",
                    universe=[market],
                    window_spec=_spec(train=5, test=5, step=5),
                    n_bins=10,
                ),
                commit="cafe1234567",
                universe=[market],
                window_spec=_spec(train=5, test=5, step=5),
                n_bins=10,
                created_at=datetime(2026, 8, 1),
                metrics=metrics,
                markets=per_market,
            )


class TestRegistry:
    def _report(self, registry_root, markets) -> ForecastReport:
        return run_forecast_report(
            markets,
            window_spec=_spec(train=5, test=5, step=5),
            n_bins=10,
            commit="cafe1234567",
            registry=ForecastReportRegistry(registry_root),
        )

    def test_record_get_all_round_trip(self, tmp_path):
        root = tmp_path / "registry"
        report = self._report(root, [ForecastMarket(market=_market("a"), observations=_grid(10))])
        registry = ForecastReportRegistry(root)
        assert registry.get(report.id) is not None
        assert [record.id for record in registry.all()] == [report.id]

    def test_duplicate_record_refused(self, tmp_path):
        root = tmp_path / "registry"
        report = self._report(root, [ForecastMarket(market=_market("a"), observations=_grid(10))])
        with pytest.raises(ValueError, match="already recorded"):
            ForecastReportRegistry(root).record(report)

    def test_corrupted_line_fails_closed_with_attribution(self, tmp_path):
        root = tmp_path / "registry"
        root.mkdir()
        (root / FORECASTS_FILE).write_text("this is not json\n", encoding="utf-8")
        with pytest.raises(ValueError, match="line 1 is invalid"):
            ForecastReportRegistry(root).all()

    def test_duplicate_id_in_file_fails_closed(self, tmp_path):
        root_a = tmp_path / "a"
        report = self._report(
            root_a, [ForecastMarket(market=_market("a"), observations=_grid(10))]
        )
        root_b = tmp_path / "b"
        root_b.mkdir()
        line = json.dumps(report.model_dump(mode="json"))
        (root_b / FORECASTS_FILE).write_text(f"{line}\n{line}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="share a report id"):
            ForecastReportRegistry(root_b).all()

    def test_records_persist_across_instances(self, tmp_path):
        root = tmp_path / "registry"
        report = self._report(root, [ForecastMarket(market=_market("a"), observations=_grid(10))])
        fresh = ForecastReportRegistry(root)
        assert fresh.get(report.id).id == report.id


class TestArtifacts:
    def test_byte_stable_across_registry_roots(self, tmp_path):
        markets = [
            ForecastMarket(market=_market("a"), observations=_grid(10)),
            ForecastMarket(market=_market("b"), observations=_grid(14)),
        ]
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        first = run_forecast_report(
            markets,
            window_spec=_spec(train=5, test=5, step=5),
            commit="cafe1234567",
            registry=ForecastReportRegistry(root_a),
        )
        second = run_forecast_report(
            markets,
            window_spec=_spec(train=5, test=5, step=5),
            commit="cafe1234567",
            registry=ForecastReportRegistry(root_b),
        )
        assert first.id == second.id
        paths_a = forecast_artifact_paths(root_a, first)
        paths_b = forecast_artifact_paths(root_b, second)
        for name, path_a in paths_a.items():
            assert path_a.read_bytes() == paths_b[name].read_bytes()

    def test_created_at_excluded_from_report_json(self, tmp_path):
        root = tmp_path / "registry"
        report = run_forecast_report(
            [ForecastMarket(market=_market("a"), observations=_grid(10))],
            window_spec=_spec(train=5, test=5, step=5),
            commit="cafe1234567",
            registry=ForecastReportRegistry(root),
        )
        text = forecast_artifact_paths(root, report)["report.json"].read_text(
            encoding="utf-8"
        )
        assert "created_at" not in text
        payload = json.loads(text)
        assert payload["id"] == report.id
        assert "metrics" in payload

    def test_windows_csv_shape(self, tmp_path):
        root = tmp_path / "registry"
        report = run_forecast_report(
            [ForecastMarket(market=_market("a"), observations=_grid(10))],
            window_spec=_spec(train=5, test=5, step=5),
            commit="cafe1234567",
            registry=ForecastReportRegistry(root),
        )
        rows = forecast_artifact_paths(root, report)["windows.csv"].read_text(
            encoding="utf-8"
        ).splitlines()
        assert rows[0].split(",") == [
            "market_id",
            "window_index",
            "train_end",
            "test_start",
            "test_end",
            "brier",
            "liquidity_weighted_brier",
            "n_observations",
            "n_resolved",
        ]
        assert rows[1].split(",") == [
            "kalshi:a",
            "0",
            "2026-08-01T04:00:00+00:00",
            "2026-08-01T05:00:00+00:00",
            "2026-08-01T09:00:00+00:00",
            "",
            "",
            "5",
            "0",
        ]

    def test_calibration_csv_has_one_row_per_bin(self, tmp_path):
        root = tmp_path / "registry"
        # The market resolves at T+4h, before the window's observations
        # (T+5h..T+9h), so all five land in one reliability bin.
        market = _market("a", resolution=["Yes"], resolved_at=_T0 + 4 * _HOUR)
        report = run_forecast_report(
            [ForecastMarket(market=market, observations=_grid(10))],
            window_spec=_spec(train=5, test=5, step=5),
            commit="cafe1234567",
            registry=ForecastReportRegistry(root),
        )
        text = forecast_artifact_paths(root, report)["calibration.csv"].read_text(
            encoding="utf-8"
        )
        lines = text.splitlines()
        assert len(lines) == 1 + 10  # header + one row per bin
        # Every bin is emitted; empty bins stay blank. Line 1 is bin 0
        # (count 0); p = 0.35..0.39 all fall in bin 3 (line 4).
        assert lines[1].split(",") == [
            "kalshi:a",
            "0",
            "0",
            "0.0",
            "0.1",
            "0",
            "",
            "",
            "",
        ]
        assert lines[4].split(",") == [
            "kalshi:a",
            "0",
            "3",
            "0.3",
            "0.4",
            "5",
            "0.37",
            "1.0",
            "0.3971",
        ]


class TestRunForecastReport:
    def test_end_to_end(self, tmp_path):
        root = tmp_path / "registry"
        markets = [ForecastMarket(market=_market("a"), observations=_grid(10))]
        report = run_forecast_report(
            markets,
            window_spec=_spec(train=5, test=5, step=5),
            commit="cafe1234567",
            registry=ForecastReportRegistry(root),
        )
        assert report.id == forecast_report_id(
            commit="cafe1234567",
            universe=[markets[0].market],
            window_spec=_spec(train=5, test=5, step=5),
            n_bins=10,
        )
        assert report.metrics["n_windows_total"] == 1
        assert report.metrics["n_evaluated_windows"] == 0
        for path in forecast_artifact_paths(root, report).values():
            assert path.exists()
        assert len(ForecastReportRegistry(root).all()) == 1
