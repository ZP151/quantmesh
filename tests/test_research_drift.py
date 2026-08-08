"""M7 Phase E tests: drift/failure detection and signal promotion (issue #43).

The drift statistics are pure numpy (PSI, the KS statistic, and the
Kolmogorov asymptotic p-value) and are cross-checked against scipy
where it is installed. Detection is fail-closed on data it cannot
judge; failure detection runs on broken data — that is its job. The
alert and promotion ledgers follow the ADR-0006 JSONL discipline
(atomic appends, fail-closed reads with line attribution, duplicate
refusal). The acceptance drill runs the pipeline report over the
fixture universe and promotes its evidence (exit criterion 1), then
injects feature drift, stale input, and NaN rows and records the
alerts (exit criterion 2).
"""

import importlib.util
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from quantmesh.data.lake import Lake
from quantmesh.domain.models import Venue
from quantmesh.research.drift import (
    AlertLedger,
    AlertRecord,
    DriftReport,
    FailureCheck,
    FeatureDriftReport,
    PredictionDrift,
    PromotionEvidence,
    PromotionLedger,
    PromotionRecord,
    StalenessCheck,
    alert_id,
    build_drift_report,
    detect_failures,
    detect_feature_drift,
    detect_prediction_drift,
    detect_staleness,
    evidence_from_report,
    ks_p_value,
    ks_statistic,
    promote_signal,
    promotion_id,
    psi,
    record_report_alerts,
)
from quantmesh.research.features import FeatureKind, FeatureSpec, compute_feature, feature_id
from quantmesh.research.pipelines import run_pipeline_report
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    report_id,
)
from tests.research_fixtures import SYMBOLS, pinned_lake

COMMIT = "c" * 40
DATASET = "equities"
T0 = datetime(2026, 1, 5, tzinfo=UTC)
COSTS = CostModel(fee_bps=1, half_spread_bps=1, slippage_bps=1)
WINDOW = WalkForwardSpec(train_bars=30, test_bars=10, step_bars=10)
UNIVERSE = [UniverseMember(venue=Venue.MOOMOO, symbol=symbol) for symbol in SYMBOLS]


def _library(name: str) -> None:
    if importlib.util.find_spec(name) is None:
        pytest.skip(f"{name} is not installed; install quantmesh[research]")


def _reference_frame(n: int = 120) -> pd.DataFrame:
    """Two clean deterministic features: a uniform spread and a sine,
    on an hourly DatetimeIndex like computed feature frames."""
    t = np.linspace(0, 1, n)
    return pd.DataFrame(
        {
            "momentum": t,
            "log_return": 0.5 + 0.5 * np.sin(2 * np.pi * t),
        },
        index=pd.date_range(T0, periods=n, freq="1h"),
    )


def _drill_feature(name: str, symbol: str, *, window: int) -> FeatureSpec:
    return FeatureSpec(
        id=feature_id(
            dataset=DATASET,
            revision=1,
            commit=COMMIT,
            name=name,
            kind=FeatureKind.BAR,
            venue=Venue.MOOMOO,
            symbol=symbol,
            interval="1h",
            parameters={"window": window},
        ),
        name=name,
        kind=FeatureKind.BAR,
        venue=Venue.MOOMOO,
        symbol=symbol,
        interval="1h",
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
        parameters={"window": window},
    )


def _drill_featureset() -> list[FeatureSpec]:
    return [
        _drill_feature(name, symbol, window=window)
        for symbol in SYMBOLS
        for name, window in (("momentum", 10), ("log_return", 5), ("realized_vol", 5))
    ]


def _make_report(**overrides) -> StrategyReport:
    fields = dict(
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
        strategy="momentum",
        interval="1h",
        universe=UNIVERSE,
        window_spec=WINDOW,
        costs=COSTS,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        metrics={},
        evidence={},
        windows=[],
    )
    fields.update(overrides)
    fields["id"] = report_id(
        dataset=fields["dataset"],
        revision=fields["revision"],
        commit=fields["commit"],
        strategy=fields["strategy"],
        interval=fields["interval"],
        universe=fields["universe"],
        window_spec=fields["window_spec"],
        costs=fields["costs"],
    )
    return StrategyReport(**fields)


def _full_evidence_report() -> StrategyReport:
    return _make_report(
        strategy="logistic",
        evidence={
            "benchmark:momentum": "b" * 16,
            "benchmark:risk_parity": "e" * 16,
            "ablation:drop:log_return": "a" * 16,
            "windows_oos": True,
        },
    )


class TestPsi:
    def test_identical_samples_are_zero(self) -> None:
        sample = np.linspace(0.0, 1.0, 50)
        assert psi(sample, sample) == 0.0

    def test_shifted_sample_drifts(self) -> None:
        reference = np.linspace(0.0, 1.0, 50)
        assert psi(reference, reference + 0.5) > 0.25

    def test_pinned_arithmetic(self) -> None:
        """Reference uniform on [0,1]; current adds ten values far above
        the range. Nine bins hold one current value each (share 0.05 vs
        0.1) and the top bin holds eleven (0.55 vs 0.1):
        PSI = 9 * 0.05 * ln(2) + 0.45 * ln(5.5)."""
        reference = np.linspace(0.0, 1.0, 10)
        current = np.concatenate([np.linspace(0.0, 1.0, 10), np.full(10, 5.0)])
        expected = 9 * 0.05 * np.log(2.0) + 0.45 * np.log(5.5)
        assert psi(reference, current) == pytest.approx(float(expected), abs=1e-4)

    def test_short_sample_refused(self) -> None:
        with pytest.raises(ValueError, match="short sample"):
            psi(np.linspace(0.0, 1.0, 9), np.linspace(0.0, 1.0, 50))

    def test_non_finite_refused(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            psi(np.linspace(0.0, 1.0, 50), np.array([0.1] * 10 + [np.nan] * 40))

    def test_degenerate_reference_refused(self) -> None:
        with pytest.raises(ValueError, match="degenerate"):
            psi(np.full(50, 1.0), np.linspace(0.0, 1.0, 50))

    def test_two_dimensional_refused(self) -> None:
        with pytest.raises(ValueError, match="not a 1-D sample"):
            psi(np.zeros((10, 2)), np.zeros((10, 2)))

    def test_non_numeric_refused(self) -> None:
        with pytest.raises(ValueError, match="non-numeric"):
            psi(np.array(["a"] * 20), np.array(["b"] * 20))

    def test_bins_below_two_refused(self) -> None:
        with pytest.raises(ValueError, match="bins must be at least 2"):
            psi(np.linspace(0.0, 1.0, 50), np.linspace(0.0, 1.0, 50), bins=1)


class TestKsStatistic:
    def test_identical_samples_are_zero(self) -> None:
        sample = np.linspace(0.0, 1.0, 50)
        assert ks_statistic(sample, sample) == 0.0

    def test_disjoint_samples_p_value_vanishes(self) -> None:
        reference = np.linspace(0.0, 1.0, 50)
        current = np.linspace(2.0, 3.0, 50)
        assert ks_statistic(reference, current) == pytest.approx(1.0)
        assert ks_p_value(ks_statistic(reference, current), 50, 50) < 1e-6

    def test_identical_samples_p_value_is_one(self) -> None:
        sample = np.linspace(0.0, 1.0, 50)
        assert ks_p_value(ks_statistic(sample, sample), 50, 50) == 1.0

    def test_cross_checked_against_scipy(self) -> None:
        """The pure-numpy statistic and the asymptotic p-value match
        scipy's two-sample KS on the same fixed-seed samples."""
        _library("scipy")
        from scipy import stats

        rng = np.random.default_rng(7)
        reference = rng.normal(0.0, 1.0, 200)
        current = rng.normal(0.4, 1.0, 200)
        scipy_result = stats.ks_2samp(reference, current, mode="asymp")
        statistic = ks_statistic(reference, current)
        assert statistic == pytest.approx(scipy_result.statistic, abs=1e-12)
        assert ks_p_value(statistic, 200, 200) == pytest.approx(
            scipy_result.pvalue, abs=1e-3
        )

    def test_short_sample_refused(self) -> None:
        with pytest.raises(ValueError, match="short sample"):
            ks_statistic(np.linspace(0.0, 1.0, 9), np.linspace(0.0, 1.0, 50))

    def test_non_finite_refused(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            ks_statistic(np.linspace(0.0, 1.0, 50), np.array([np.inf] * 50))

    def test_non_finite_statistic_p_value_refused(self) -> None:
        with pytest.raises(ValueError, match="non-finite KS statistic"):
            ks_p_value(np.nan, 50, 50)


class TestFeatureDrift:
    def test_clean_frame_has_no_drift(self) -> None:
        frame = _reference_frame()
        report = detect_feature_drift(frame, frame)
        assert report.flagged == []
        assert all(check.psi_value == 0.0 for check in report.checks)
        assert all(check.ks_p_value == 1.0 for check in report.checks)

    def test_shifted_feature_flagged(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["momentum"] = current["momentum"] + 1.0
        report = detect_feature_drift(reference, current)
        assert report.flagged == ["momentum"]
        momentum = next(check for check in report.checks if check.feature == "momentum")
        assert momentum.psi_value > 0.25

    def test_reference_digest_pins_reference(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["momentum"] = current["momentum"] + 1.0
        other = reference.copy()
        other["log_return"] = other["log_return"] + 0.01
        first = detect_feature_drift(reference, current)
        second = detect_feature_drift(other, current)
        assert first.reference_digest != second.reference_digest
        assert all(
            len(str(report.reference_digest)) == 16 for report in (first, second)
        )

    def test_missing_column_refused(self) -> None:
        reference = _reference_frame()
        with pytest.raises(ValueError, match="missing from the current frame"):
            detect_feature_drift(reference, reference[["momentum"]])

    def test_extra_column_refused(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["extra"] = 0.0
        with pytest.raises(ValueError, match="outside the reference"):
            detect_feature_drift(reference, current)

    def test_short_sample_refused_with_feature_named(self) -> None:
        """The first sorted column trips with its name attributed."""
        reference = _reference_frame(120)
        current = _reference_frame(9)
        with pytest.raises(ValueError, match="'log_return'.*short sample"):
            detect_feature_drift(reference, current)

    def test_nan_refused_with_feature_named(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current.iloc[10, current.columns.get_loc("momentum")] = np.nan
        with pytest.raises(ValueError, match="'momentum'.*non-finite"):
            detect_feature_drift(reference, current)

    def test_empty_frames_refused(self) -> None:
        with pytest.raises(ValueError, match="reference frame is empty"):
            detect_feature_drift(_reference_frame(0), _reference_frame())

    def test_flagged_tamper_refused(self) -> None:
        frame = _reference_frame()
        report = detect_feature_drift(frame, frame)
        with pytest.raises(ValidationError, match="do not match the checks"):
            FeatureDriftReport.model_validate({**report.model_dump(), "flagged": ["momentum"]})

    def test_unsorted_checks_refused(self) -> None:
        frame = _reference_frame()
        report = detect_feature_drift(frame, frame)
        with pytest.raises(ValidationError, match="not sorted"):
            FeatureDriftReport.model_validate(
                {**report.model_dump(), "checks": list(reversed(report.checks))}
            )

    def test_thresholds_are_setup_on_the_record(self) -> None:
        frame = _reference_frame()
        report = detect_feature_drift(frame, frame, psi_threshold=0.5)
        assert report.psi_threshold == 0.5


class TestPredictionDrift:
    def test_clean_scores_do_not_drift(self) -> None:
        training = np.linspace(0.2, 0.8, 100)
        report = detect_prediction_drift(training, training.copy())
        assert not report.drifted
        assert report.ks_p_value == 1.0

    def test_shifted_scores_drift(self) -> None:
        training = np.linspace(0.2, 0.8, 100)
        live = np.linspace(0.35, 0.95, 100)
        report = detect_prediction_drift(training, live)
        assert report.drifted
        assert report.ks_p_value < 0.05

    def test_alpha_is_a_knob(self) -> None:
        training = np.linspace(0.2, 0.8, 100)
        live = np.linspace(0.35, 0.95, 100)
        assert detect_prediction_drift(training, live, ks_alpha=0.05).drifted
        assert not detect_prediction_drift(training, live, ks_alpha=1e-12).drifted

    def test_training_digest_is_deterministic_and_sensitive(self) -> None:
        training = np.linspace(0.2, 0.8, 100)
        first = detect_prediction_drift(training, training.copy())
        second = detect_prediction_drift(training, training.copy())
        assert first.training_digest == second.training_digest
        other = detect_prediction_drift(training + 0.01, training.copy())
        assert other.training_digest != first.training_digest

    def test_short_sample_refused(self) -> None:
        with pytest.raises(ValueError, match="short sample"):
            detect_prediction_drift(np.linspace(0.2, 0.8, 9), np.linspace(0.2, 0.8, 50))

    def test_non_finite_refused(self) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            detect_prediction_drift(
                np.linspace(0.2, 0.8, 50), np.array([np.nan] * 50)
            )

    def test_drifted_tamper_refused(self) -> None:
        training = np.linspace(0.2, 0.8, 100)
        report = detect_prediction_drift(training, training.copy())
        with pytest.raises(ValidationError, match="does not match the KS p-value"):
            PredictionDrift.model_validate({**report.model_dump(), "drifted": True})


class TestStaleness:
    def _frame(self) -> pd.DataFrame:
        index = pd.date_range(T0, periods=60, freq="1h")
        return pd.DataFrame({"momentum": np.linspace(0.0, 1.0, 60)}, index=index)

    def test_fresh_input_is_not_stale(self) -> None:
        frame = self._frame()
        check = detect_staleness(
            frame, now=T0 + timedelta(hours=63), max_age=timedelta(hours=6)
        )
        assert not check.stale
        assert check.latest_timestamp == T0 + timedelta(hours=59)
        assert check.age == timedelta(hours=4)

    def test_old_input_is_stale(self) -> None:
        frame = self._frame()
        check = detect_staleness(
            frame, now=T0 + timedelta(hours=63), max_age=timedelta(hours=2)
        )
        assert check.stale
        assert check.age == timedelta(hours=4)

    def test_boundary_is_not_stale(self) -> None:
        """The matcher's rule is strict: latest + max_age < now is stale;
        equality at the boundary is not."""
        frame = self._frame()
        check = detect_staleness(
            frame, now=T0 + timedelta(hours=63), max_age=timedelta(hours=4)
        )
        assert not check.stale

    def test_future_timestamp_refused(self) -> None:
        frame = self._frame()
        with pytest.raises(ValueError, match="in the future"):
            detect_staleness(
                frame, now=T0 + timedelta(hours=1), max_age=timedelta(hours=24)
            )

    def test_missing_timestamp_refused(self) -> None:
        index = pd.DatetimeIndex([T0, pd.NaT, T0 + timedelta(hours=2)])
        frame = pd.DataFrame({"momentum": [0.0, 0.5, 1.0]}, index=index)
        with pytest.raises(ValueError, match="missing timestamp"):
            detect_staleness(
                frame, now=T0 + timedelta(hours=3), max_age=timedelta(hours=24)
            )

    def test_naive_timestamps_refused(self) -> None:
        index = pd.date_range(T0.replace(tzinfo=None), periods=10, freq="1h")
        frame = pd.DataFrame({"momentum": np.linspace(0.0, 1.0, 10)}, index=index)
        with pytest.raises(ValueError, match="timezone-aware"):
            detect_staleness(
                frame, now=T0 + timedelta(hours=20), max_age=timedelta(hours=24)
            )

    def test_naive_now_refused(self) -> None:
        with pytest.raises(ValueError, match="now must be timezone-aware"):
            detect_staleness(
                self._frame(),
                now=datetime(2026, 1, 6),
                max_age=timedelta(hours=24),
            )

    def test_empty_frame_refused(self) -> None:
        frame = self._frame().iloc[0:0]
        with pytest.raises(ValueError, match="empty frame"):
            detect_staleness(
                frame, now=T0 + timedelta(hours=60), max_age=timedelta(hours=24)
            )

    def test_missing_timestamp_column_refused(self) -> None:
        with pytest.raises(ValueError, match="carry no 'ts' column"):
            detect_staleness(
                self._frame(),
                timestamp_column="ts",
                now=T0 + timedelta(hours=60),
                max_age=timedelta(hours=24),
            )

    def test_timestamp_column_mode(self) -> None:
        frame = self._frame()
        frame["ts"] = frame.index
        check = detect_staleness(
            frame,
            timestamp_column="ts",
            now=T0 + timedelta(hours=100),
            max_age=timedelta(hours=24),
        )
        assert check.stale
        assert check.timestamp_column == "ts"

    def test_unparseable_column_refused(self) -> None:
        frame = self._frame()
        frame["ts"] = "not a timestamp"
        with pytest.raises(ValueError, match="does not parse as timestamps"):
            detect_staleness(
                frame,
                timestamp_column="ts",
                now=T0 + timedelta(hours=70),
                max_age=timedelta(hours=24),
            )

    def test_age_tamper_refused(self) -> None:
        frame = self._frame()
        check = detect_staleness(
            frame, now=T0 + timedelta(hours=70), max_age=timedelta(hours=24)
        )
        with pytest.raises(ValidationError, match="does not match now minus latest"):
            StalenessCheck.model_validate(
                {**check.model_dump(), "age": check.age + timedelta(hours=1)}
            )


class TestFailures:
    def test_complete_clean_frame(self) -> None:
        frame = _reference_frame()
        check = detect_failures(frame, expected_columns={"momentum", "log_return"})
        assert check.missing_features == []
        assert check.nan_rows == 0
        assert check.coverage_ratio == 1.0
        assert not check.collapsed

    def test_missing_feature_named(self) -> None:
        frame = _reference_frame()
        check = detect_failures(frame, expected_columns={"momentum", "log_return", "realized_vol"})
        assert check.missing_features == ["realized_vol"]

    def test_nan_rows_counted(self) -> None:
        frame = _reference_frame(100)
        frame.iloc[0, frame.columns.get_loc("momentum")] = np.nan
        frame.iloc[1, frame.columns.get_loc("log_return")] = np.nan
        check = detect_failures(frame, expected_columns={"momentum", "log_return"})
        assert check.nan_rows == 2
        assert check.coverage_ratio == pytest.approx(0.98)
        assert not check.collapsed

    def test_nan_threshold_collapses(self) -> None:
        frame = _reference_frame(100)
        frame.iloc[:10, frame.columns.get_loc("momentum")] = np.nan
        check = detect_failures(frame, expected_columns={"momentum", "log_return"})
        assert check.nan_rows == 10
        assert check.collapsed

    def test_min_rows_collapses(self) -> None:
        frame = _reference_frame(3)
        check = detect_failures(frame, expected_columns={"momentum"}, min_rows=5)
        assert check.collapsed
        assert check.coverage_ratio == 1.0

    def test_empty_frame_collapses(self) -> None:
        check = detect_failures(_reference_frame(0), expected_columns={"momentum"})
        assert check.total_rows == 0
        assert check.coverage_ratio == 0.0
        assert check.collapsed

    def test_expected_columns_are_sorted(self) -> None:
        frame = _reference_frame()
        check = detect_failures(frame, expected_columns={"log_return", "momentum"})
        assert check.expected_columns == ["log_return", "momentum"]

    def test_collapsed_tamper_refused(self) -> None:
        frame = _reference_frame()
        check = detect_failures(frame, expected_columns={"momentum"})
        with pytest.raises(ValidationError, match="does not match"):
            FailureCheck.model_validate({**check.model_dump(), "collapsed": True})


class TestAlertRecord:
    def _alert(self, **overrides) -> AlertRecord:
        fields = dict(
            kind="feature_drift",
            source="feature:momentum",
            detected_at=datetime(2026, 8, 8, tzinfo=UTC),
            message="feature 'momentum' drifted",
            observed={"psi": 1.079053224},
        )
        fields.update(overrides)
        fields.setdefault(
            "id",
            alert_id(
                kind=fields["kind"],
                source=fields["source"],
                detected_at=fields["detected_at"],
                observed=fields["observed"],
            ),
        )
        return AlertRecord(**fields)

    def test_id_is_order_independent(self) -> None:
        first = self._alert(observed={"a": 1.0, "b": 2})
        second = self._alert(observed={"b": 2, "a": 1.0})
        assert first.id == second.id

    def test_id_is_sensitive_to_every_input(self) -> None:
        base = self._alert()
        assert self._alert(kind="staleness").id != base.id
        assert self._alert(source="feature:log_return").id != base.id
        assert self._alert(detected_at=datetime(2026, 8, 9, tzinfo=UTC)).id != base.id
        assert self._alert(observed={"psi": 2.0}).id != base.id

    def test_tampered_id_refused(self) -> None:
        alert = self._alert()
        with pytest.raises(ValidationError, match="does not match its setup"):
            AlertRecord.model_validate({**alert.model_dump(), "id": "0" * 16})

    def test_naive_detected_at_refused(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            self._alert(detected_at=datetime(2026, 8, 8))

    def test_unknown_kind_refused(self) -> None:
        with pytest.raises(ValidationError):
            self._alert(kind="explosion")

    def test_non_finite_observed_refused(self) -> None:
        with pytest.raises(ValidationError, match="not finite"):
            self._alert(observed={"psi": np.inf})

    def test_round_trips_through_json_with_stable_id(self) -> None:
        alert = self._alert()
        reloaded = AlertRecord.model_validate_json(alert.model_dump_json())
        assert reloaded == alert


class TestBuildDriftReport:
    def test_clean_checks_produce_no_alerts(self) -> None:
        frame = _reference_frame()
        report = build_drift_report(
            feature=detect_feature_drift(frame, frame),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert report.alerts == []

    def test_feature_drift_alert_derived(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["momentum"] = current["momentum"] + 1.0
        report = build_drift_report(
            feature=detect_feature_drift(reference, current),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert [alert.kind for alert in report.alerts] == ["feature_drift"]
        alert = report.alerts[0]
        assert alert.source == "feature:momentum"
        assert alert.observed["psi"] > 0.25

    def test_all_conditions_alert(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["momentum"] = current["momentum"] + 1.0
        training = np.linspace(0.2, 0.8, 100)
        live = np.linspace(0.35, 0.95, 100)
        stale_frame = pd.DataFrame(
            {"momentum": np.linspace(0.0, 1.0, 60)},
            index=pd.date_range(T0, periods=60, freq="1h"),
        )
        stale = detect_staleness(
            stale_frame,
            now=T0 + timedelta(hours=100),
            max_age=timedelta(hours=24),
        )
        broken = reference.copy()
        broken.iloc[:10, broken.columns.get_loc("momentum")] = np.nan
        report = build_drift_report(
            feature=detect_feature_drift(reference, current),
            prediction=detect_prediction_drift(training, live),
            staleness=stale,
            failures=detect_failures(broken, expected_columns={"momentum", "log_return"}),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        kinds = sorted(alert.kind for alert in report.alerts)
        assert kinds == ["failure", "feature_drift", "prediction_drift", "staleness"]
        assert report.staleness is not None and report.staleness.stale
        failure_sources = sorted(a.source for a in report.alerts if a.kind == "failure")
        assert failure_sources == ["features:nan"]

    def test_nan_collapse_produces_no_coverage_alert(self) -> None:
        """One root cause stays one alert: a NaN-driven collapse alerts
        as NaN, not as coverage too."""
        frame = _reference_frame(100)
        frame.iloc[:10, frame.columns.get_loc("momentum")] = np.nan
        report = build_drift_report(
            failures=detect_failures(frame, expected_columns={"momentum"}),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert [a.source for a in report.alerts] == ["features:nan"]

    def test_row_count_collapse_alerts_as_coverage(self) -> None:
        frame = _reference_frame(3)
        report = build_drift_report(
            failures=detect_failures(frame, expected_columns={"momentum"}, min_rows=5),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert [a.source for a in report.alerts] == ["features:coverage"]

    def test_deterministic_with_fixed_generated_at(self) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["momentum"] = current["momentum"] + 1.0
        first = build_drift_report(
            feature=detect_feature_drift(reference, current),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        second = build_drift_report(
            feature=detect_feature_drift(reference, current),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert first.alerts == second.alerts

    def test_default_generated_at_is_now_aware(self) -> None:
        report = build_drift_report()
        assert report.generated_at.tzinfo is not None


def _failure_alert(**overrides) -> AlertRecord:
    fields = dict(
        kind="failure",
        source="features:nan",
        detected_at=datetime(2026, 8, 8, tzinfo=UTC),
        message="nan rows",
        observed={"nan_rows": 1},
    )
    fields.update(overrides)
    fields.setdefault(
        "id",
        alert_id(
            kind=fields["kind"],
            source=fields["source"],
            detected_at=fields["detected_at"],
            observed=fields["observed"],
        ),
    )
    return AlertRecord(**fields)


class TestAlertLedger:
    def test_record_and_read_back(self, tmp_path) -> None:
        ledger = AlertLedger(root=tmp_path / "alerts")
        alert = _failure_alert()
        ledger.record(alert)
        assert ledger.get(alert.id) == alert
        assert ledger.all() == [alert]
        assert ledger.path.is_file()

    def test_duplicate_refused(self, tmp_path) -> None:
        ledger = AlertLedger(root=tmp_path / "alerts")
        ledger.record(_failure_alert())
        with pytest.raises(ValueError, match="already recorded"):
            ledger.record(_failure_alert())

    def test_corrupted_line_attributed(self, tmp_path) -> None:
        ledger = AlertLedger(root=tmp_path / "alerts")
        ledger.record(_failure_alert())
        with ledger.path.open("a", encoding="utf-8") as handle:
            handle.write("not an alert line\n")
        with pytest.raises(ValueError, match="line 2 is invalid"):
            ledger.all()

    def test_shared_id_refused(self, tmp_path) -> None:
        ledger = AlertLedger(root=tmp_path / "alerts")
        alert = _failure_alert()
        ledger.record(alert)
        with ledger.path.open("a", encoding="utf-8") as handle:
            handle.write(alert.model_dump_json() + "\n")
        with pytest.raises(ValueError, match="share a record id"):
            ledger.all()

    def test_root_guard(self, tmp_path) -> None:
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("i am a file", encoding="utf-8")
        ledger = AlertLedger(root=not_a_dir)
        with pytest.raises(ValueError, match="is not a directory"):
            ledger.record(_failure_alert())

    def test_record_report_alerts_persists_all(self, tmp_path) -> None:
        reference = _reference_frame()
        current = reference.copy()
        current["momentum"] = current["momentum"] + 1.0
        report = build_drift_report(
            feature=detect_feature_drift(reference, current),
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        ledger = AlertLedger(root=tmp_path / "alerts")
        record_report_alerts(ledger, report)
        assert ledger.all() == report.alerts
        with pytest.raises(ValueError, match="already recorded"):
            record_report_alerts(ledger, report)


class TestPromotionEvidence:
    def test_full_bundle_accepted(self) -> None:
        evidence = PromotionEvidence(
            benchmark_ids=["b" * 16, "a" * 16],
            ablation_ids=["a" * 16],
            oos_report_id="c" * 16,
        )
        assert evidence.benchmark_ids == ["a" * 16, "b" * 16]

    def test_empty_benchmarks_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            PromotionEvidence(
                benchmark_ids=[], ablation_ids=["a" * 16], oos_report_id="c" * 16
            )

    def test_empty_ablations_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            PromotionEvidence(
                benchmark_ids=["b" * 16], ablation_ids=[], oos_report_id="c" * 16
            )

    def test_non_report_id_refused(self) -> None:
        with pytest.raises(ValidationError, match="non-report id"):
            PromotionEvidence(
                benchmark_ids=["not-hex"], ablation_ids=["a" * 16], oos_report_id="c" * 16
            )

    def test_evidence_from_report_extracts_bundle(self) -> None:
        report = _full_evidence_report()
        evidence = evidence_from_report(report)
        assert evidence.benchmark_ids == ["b" * 16, "e" * 16]
        assert evidence.ablation_ids == ["a" * 16]
        assert evidence.oos_report_id == report.id

    def test_report_without_benchmarks_refused(self) -> None:
        report = _make_report(
            strategy="logistic",
            evidence={"ablation:drop:log_return": "a" * 16, "windows_oos": True},
        )
        with pytest.raises(ValidationError, match="at least one"):
            evidence_from_report(report)

    def test_report_without_ablations_refused(self) -> None:
        report = _make_report(
            strategy="logistic",
            evidence={"benchmark:momentum": "b" * 16, "windows_oos": True},
        )
        with pytest.raises(ValidationError, match="at least one"):
            evidence_from_report(report)

    def test_report_without_oos_windows_refused(self) -> None:
        report = _make_report(
            strategy="logistic",
            evidence={"benchmark:momentum": "b" * 16, "ablation:drop:log_return": "a" * 16},
        )
        with pytest.raises(ValueError, match="no out-of-sample windows"):
            evidence_from_report(report)

    def test_non_report_id_evidence_refused(self) -> None:
        report = _make_report(
            strategy="logistic",
            evidence={
                "benchmark:momentum": 123,
                "ablation:drop:log_return": "a" * 16,
                "windows_oos": True,
            },
        )
        with pytest.raises(ValueError, match="is not a report id"):
            evidence_from_report(report)


class TestPromotion:
    def _evidence(self) -> PromotionEvidence:
        return PromotionEvidence(
            benchmark_ids=["b" * 16, "a" * 16],
            ablation_ids=["a" * 16],
            oos_report_id="c" * 16,
        )

    def test_promote_with_full_bundle(self, tmp_path) -> None:
        ledger = PromotionLedger(root=tmp_path / "promotions")
        record = promote_signal(
            signal_name="logistic_aaa",
            evidence=self._evidence(),
            ledger=ledger,
            promoted_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert isinstance(record, PromotionRecord)
        assert record.benchmark_report_ids == ["a" * 16, "b" * 16]
        assert record.ablation_report_ids == ["a" * 16]
        assert record.oos_report_id == "c" * 16
        assert not record.kill_switch
        assert ledger.get(record.id) == record

    def test_identical_evidence_is_same_promotion(self, tmp_path) -> None:
        """Identity pins the evidence, never the outcome — even
        ``promoted_at`` differs, the same evidence is refused."""
        ledger = PromotionLedger(root=tmp_path / "promotions")
        promote_signal(
            signal_name="logistic_aaa",
            evidence=self._evidence(),
            ledger=ledger,
            promoted_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        with pytest.raises(ValueError, match="already recorded"):
            promote_signal(
                signal_name="logistic_aaa",
                evidence=self._evidence(),
                ledger=ledger,
                promoted_at=datetime(2026, 8, 9, tzinfo=UTC),
            )

    def test_identity_changes_with_signal_or_evidence(self) -> None:
        base = promotion_id(
            signal_name="logistic_aaa",
            benchmark_report_ids=["a" * 16, "b" * 16],
            ablation_report_ids=["a" * 16],
            oos_report_id="c" * 16,
            kill_switch=False,
        )
        assert promotion_id(
            signal_name="logistic_bbb",
            benchmark_report_ids=["a" * 16, "b" * 16],
            ablation_report_ids=["a" * 16],
            oos_report_id="c" * 16,
            kill_switch=False,
        ) != base
        assert promotion_id(
            signal_name="logistic_aaa",
            benchmark_report_ids=["a" * 16, "b" * 16],
            ablation_report_ids=["c" * 16],
            oos_report_id="c" * 16,
            kill_switch=False,
        ) != base

    def test_kill_switch_is_recorded_and_report_only(self, tmp_path) -> None:
        ledger = PromotionLedger(root=tmp_path / "promotions")
        record = promote_signal(
            signal_name="logistic_aaa",
            evidence=self._evidence(),
            kill_switch=True,
            ledger=ledger,
            promoted_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        assert record.kill_switch is True
        assert record.id != promotion_id(
            signal_name="logistic_aaa",
            benchmark_report_ids=record.benchmark_report_ids,
            ablation_report_ids=record.ablation_report_ids,
            oos_report_id=record.oos_report_id,
            kill_switch=False,
        )

    def test_bad_signal_name_refused(self, tmp_path) -> None:
        ledger = PromotionLedger(root=tmp_path / "promotions")
        with pytest.raises(ValidationError):
            promote_signal(
                signal_name="Logistic AAA",
                evidence=self._evidence(),
                ledger=ledger,
            )

    def test_tampered_id_refused(self, tmp_path) -> None:
        ledger = PromotionLedger(root=tmp_path / "promotions")
        record = promote_signal(
            signal_name="logistic_aaa",
            evidence=self._evidence(),
            ledger=ledger,
            promoted_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        with pytest.raises(ValidationError, match="does not match its evidence"):
            PromotionRecord.model_validate({**record.model_dump(), "id": "0" * 16})

    def test_ledger_discipline(self, tmp_path) -> None:
        ledger = PromotionLedger(root=tmp_path / "promotions")
        promote_signal(
            signal_name="logistic_aaa",
            evidence=self._evidence(),
            ledger=ledger,
            promoted_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        with ledger.path.open("a", encoding="utf-8") as handle:
            handle.write("not a promotion line\n")
        with pytest.raises(ValueError, match="line 2 is invalid"):
            ledger.all()


class TestAcceptanceDrill:
    def _run(self, tmp_path):
        """The fixture-universe pipeline report with a full evidence
        bundle; returns report, registry and the drill root."""
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "registry", lake_root=root / "lake")
        report = run_pipeline_report(
            pipeline="logistic",
            featureset=_drill_featureset(),
            dataset=DATASET,
            revision=1,
            interval="1h",
            universe=UNIVERSE,
            window_spec=WINDOW,
            costs=COSTS,
            ablations=("log_return",),
            commit=COMMIT,
            registry=registry,
        )
        return report, registry, root

    def test_promotion_links_full_evidence(self, tmp_path) -> None:
        """Exit criterion 1: every promoted signal carries a promotion
        record linking benchmark, ablation and out-of-sample evidence."""
        _library("sklearn")
        report, registry, root = self._run(tmp_path)
        ledger = PromotionLedger(root=root / "promotions")
        record = promote_signal(
            signal_name="logistic_aaa",
            evidence=evidence_from_report(report),
            ledger=ledger,
        )
        assert record.oos_report_id == report.id
        for benchmark_id in record.benchmark_report_ids:
            assert registry.get(benchmark_id).strategy in (
                "momentum",
                "risk_parity",
                "low_volatility",
            )
        for ablation_id in record.ablation_report_ids:
            ablation = registry.get(ablation_id)
            assert ablation.pipeline_digest != report.pipeline_digest
        assert ledger.all() == [record]
        # Re-promoting the identical evidence is the same promotion.
        with pytest.raises(ValueError, match="already recorded"):
            promote_signal(
                signal_name="logistic_aaa",
                evidence=evidence_from_report(report),
                ledger=ledger,
            )

    def test_injected_drift_detected_and_alerted(self, tmp_path) -> None:
        """Exit criterion 2: injected drift and stale data are detected
        and alerted. Feature drift runs on a clean perturbed frame; the
        broken frame (NaN + aged timestamps) refuses the drift test and
        instead reports failures and staleness."""
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        dataset = Lake(root / "lake").dataset(DATASET)
        aaa = [spec for spec in _drill_featureset() if spec.symbol == "AAA"]
        reference = pd.DataFrame({spec.name: compute_feature(spec, dataset) for spec in aaa})
        reference = reference.dropna()
        assert not reference.empty

        current_clean = reference.copy()
        current_clean["momentum"] = current_clean["momentum"] + 1.0
        drift = detect_feature_drift(reference, current_clean)
        assert drift.flagged == ["momentum"]

        current_broken = reference.copy()
        broken_rows = current_broken.index[: int(0.2 * len(current_broken))]
        current_broken.loc[broken_rows, "momentum"] = np.nan
        current_broken.index = current_broken.index - pd.Timedelta(days=3)
        failures = detect_failures(
            current_broken, expected_columns=list(reference.columns)
        )
        assert failures.nan_rows > 0
        assert failures.collapsed
        staleness = detect_staleness(
            current_broken,
            now=T0 + timedelta(hours=72),
            max_age=timedelta(hours=24),
        )
        assert staleness.stale
        # A frame too broken for the drift test fails closed — the
        # failure check is the gate that catches it instead.
        with pytest.raises(ValueError, match="non-finite"):
            detect_feature_drift(reference, current_broken)

        report = build_drift_report(
            feature=drift,
            staleness=staleness,
            failures=failures,
            generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        )
        ledger = AlertLedger(root=root / "alerts")
        record_report_alerts(ledger, report)
        recorded = ledger.all()
        assert {alert.kind for alert in recorded} == {"feature_drift", "staleness", "failure"}
        assert {alert.source for alert in recorded} == {
            "feature:momentum",
            "features:index",
            "features:nan",
        }
        assert isinstance(report, DriftReport)
