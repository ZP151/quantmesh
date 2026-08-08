"""M7 Phase C tests: ensemble combination and uncertainty calibration (issue #41).

The Phase C contract, pinned by test:

- Member weights derive from validation windows only. The proof is
  end-to-end: a lake whose final test segment's closes are scaled
  changes the evaluation surface (test features and outcomes) while
  every validation slice stays untouched, and the flip demands every
  window's weights stay identical.
- Disagreement-based epistemic uncertainty: identical members produce
  zero disagreement by construction, divergent members positive.
- Calibration reuses the M6 ``brier_by_bin`` discipline directly
  (half-open bins, empty-bin ``None``).
- Reports follow the M5/M6 stack: setup-only ids, byte-stable
  artifacts, an append-only JSONL registry with the lake-pin gate at
  record, and byte-identical artifacts across independent roots.
"""

import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Venue
from quantmesh.events.calibration import CalibrationBin, brier_by_bin
from quantmesh.research.ensemble import (
    EnsembleReport,
    EnsembleReportRegistry,
    EnsembleSpec,
    PipelineUnavailableError,
    ensemble_artifact_paths,
    ensemble_id,
    ensemble_predict,
    ensemble_report_id,
    inverse_error_weights,
    nnls_weights,
    run_ensemble_report,
)
from quantmesh.research.features import FeatureKind, FeatureRegistry
from quantmesh.research.models import ModelSpec, model_id
from quantmesh.research.reports import UniverseMember, WalkForwardSpec
from tests.research_fixtures import SYMBOLS, fixture_bars, pinned_lake

COMMIT = "c" * 40
DATASET = "equities"
TRAIN_START = pd.Timestamp("2026-01-05T00:00:00Z").to_pydatetime()
TRAIN_END = pd.Timestamp("2026-01-06T00:00:00Z").to_pydatetime()

WINDOW = WalkForwardSpec(train_bars=30, test_bars=10, step_bars=10)
UNIVERSE = [UniverseMember(venue=Venue.MOOMOO, symbol=symbol) for symbol in SYMBOLS]
LIBRARIES = ("sklearn", "lightgbm", "arch", "scipy")


def _library(name: str) -> None:
    if importlib.util.find_spec(name) is None:
        pytest.skip(f"{name} is not installed; install quantmesh[research]")


def _register_features(root, lake_root, *, dataset: str = DATASET) -> tuple[FeatureRegistry, str]:
    """Record the drill feature set through the Phase A registry (lake-pin
    gated); returns the registry and the set's digest for member specs."""
    registry = FeatureRegistry(root=root, lake_root=lake_root)
    feature_ids = []
    for symbol in SYMBOLS:
        for name, window in (("momentum", 10), ("log_return", 5), ("realized_vol", 5)):
            spec = registry.record_spec(
                name=name,
                kind=FeatureKind.BAR,
                venue=Venue.MOOMOO,
                symbol=symbol,
                interval="1h",
                dataset=dataset,
                revision=1,
                commit=COMMIT,
                parameters={"window": window},
            )
            feature_ids.append(spec.id)
    feature_set = registry.record_set(name="drill", feature_ids=feature_ids)
    return registry, feature_set.id


def _member(
    featureset_id: str,
    *,
    model_type: str = "logistic",
    dataset: str = DATASET,
    train_start=TRAIN_START,
    train_end=TRAIN_END,
) -> ModelSpec:
    return ModelSpec(
        id=model_id(
            dataset=dataset,
            revision=1,
            commit=COMMIT,
            model_type=model_type,
            hyperparameters={},
            featureset_id_value=featureset_id,
            train_start=train_start,
            train_end=train_end,
        ),
        model_type=model_type,
        hyperparameters={},
        featureset_id=featureset_id,
        dataset=dataset,
        revision=1,
        commit=COMMIT,
        train_start=train_start,
        train_end=train_end,
    )


def _ensemble_spec(
    members: list[ModelSpec],
    *,
    weight_method: str = "inverse_error",
    validation_bars: int = 5,
) -> EnsembleSpec:
    return EnsembleSpec(
        members=members,
        weight_method=weight_method,
        validation_bars=validation_bars,
        id=ensemble_id(
            members=members,
            weight_method=weight_method,
            validation_bars=validation_bars,
        ),
    )


def _pair(
    featureset_id: str = "e" * 16,
    *,
    model_types: tuple[str, ...] = ("logistic", "lightgbm"),
    dataset: str = DATASET,
) -> list[ModelSpec]:
    """Member specs over one featureset, in the given kinds."""
    return [
        _member(featureset_id, model_type=kind, dataset=dataset) for kind in model_types
    ]


def _perturbed_bars(symbol: str, n: int = 60, *, factor: float = 1.05) -> list[Bar]:
    """Fixture bars whose final test segment's closes are scaled.

    Only the last segment is perturbed: the later windows' validation
    slices are train-side bars of their own window, so scaling an
    earlier segment would legitimately change later weights. Scaling
    the final segment changes the evaluation surface (test features
    and outcomes) while every validation slice stays untouched.
    """
    bars = fixture_bars(symbol, n)
    last_start = WINDOW.test_starts(n)[-1]
    return [
        bar.model_copy(
            update={
                "open": bar.open * factor,
                "high": bar.high * factor,
                "low": bar.low * factor,
                "close": bar.close * factor,
            }
        )
        if last_start <= index < n
        else bar
        for index, bar in enumerate(bars)
    ]


def _flipped_lake(root, *, name: str = DATASET) -> None:
    """A lake holding perturbed bars under the SAME dataset name, so every
    setup id (featureset, member, spec, report) stays identical across the
    flip — only the test-segment bytes differ (the column-order confound)."""
    lake = Lake(root)
    for symbol in SYMBOLS:
        lake.write_bars(name, _perturbed_bars(symbol))
    ManifestWriter(root).generate(name, source="fixture", license="test")


class TestWeightFunctions:
    def test_inverse_error_weights_arithmetic(self) -> None:
        assert inverse_error_weights([0.1, 0.3]) == [0.75, 0.25]

    def test_inverse_error_zero_error_dominates(self) -> None:
        assert inverse_error_weights([0.1, 0.0, 0.2]) == [0.0, 1.0, 0.0]

    def test_inverse_error_refuses_non_finite_or_negative(self) -> None:
        with pytest.raises(ValueError, match="finite and non-negative"):
            inverse_error_weights([0.1, -0.2])
        with pytest.raises(ValueError, match="finite and non-negative"):
            inverse_error_weights([0.1, np.nan])

    def test_inverse_error_refuses_all_zero(self) -> None:
        with pytest.raises(ValueError, match="all member validation errors are zero"):
            inverse_error_weights([0.0, 0.0])

    def test_inverse_error_refuses_empty(self) -> None:
        with pytest.raises(ValueError, match="at least one member error"):
            inverse_error_weights([])

    def test_nnls_known_small_case(self) -> None:
        """y equals the second member's column, so nnls must put all
        weight on that member — the optimum is unique here."""
        _library("scipy")
        predictions = np.array([[0.5, 0.2], [0.7, 0.9], [0.1, 0.3], [0.6, 0.4]])
        outcomes = np.array([0.2, 0.9, 0.3, 0.4])
        assert nnls_weights(predictions, outcomes) == [0.0, 1.0]

    def test_nnls_weights_sum_to_one(self) -> None:
        _library("scipy")
        rng = np.random.default_rng(7)
        predictions = rng.uniform(0.0, 1.0, size=(12, 3))
        outcomes = (rng.uniform(0.0, 1.0, size=12) > 0.5).astype(float)
        weights = nnls_weights(predictions, outcomes)
        assert len(weights) == 3
        assert all(weight >= 0.0 for weight in weights)
        assert abs(sum(weights) - 1.0) < 1e-9

    def test_nnls_refuses_too_few_observations(self) -> None:
        _library("scipy")
        with pytest.raises(ValueError, match="at least as many validation observations"):
            nnls_weights(np.ones((2, 3)), np.zeros(2))

    def test_nnls_refuses_non_finite(self) -> None:
        _library("scipy")
        with pytest.raises(ValueError, match="finite"):
            nnls_weights(np.array([[np.nan, 0.5], [0.2, 0.4]]), np.array([0.0, 1.0]))


class TestEnsemblePredict:
    def test_identical_members_zero_disagreement(self) -> None:
        assert ensemble_predict([0.3, 0.3, 0.3], [0.2, 0.5, 0.3]) == (0.3, 0.0)

    def test_divergent_members_positive_disagreement(self) -> None:
        assert ensemble_predict([0.1, 0.9], [0.5, 0.5]) == (0.5, 0.16)

    def test_weights_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ensemble_predict([0.5, 0.5], [1.5, -0.5])

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to one"):
            ensemble_predict([0.5, 0.5], [0.7, 0.7])

    def test_one_prediction_per_member(self) -> None:
        with pytest.raises(ValueError, match="one prediction per member"):
            ensemble_predict([0.5], [0.5, 0.5])


class TestEnsembleSpec:
    def test_id_changes_with_every_setup_field(self) -> None:
        members = _pair()
        base = ensemble_id(members=members, weight_method="inverse_error", validation_bars=5)
        assert (
            ensemble_id(members=members[::-1], weight_method="inverse_error", validation_bars=5)
            == base
        )
        assert ensemble_id(members=members, weight_method="nnls", validation_bars=5) != base
        assert (
            ensemble_id(members=members, weight_method="inverse_error", validation_bars=10)
            != base
        )
        assert ensemble_id(
            members=members[:-1], weight_method="inverse_error", validation_bars=5
        ) != base

    def test_member_order_never_changes_identity(self) -> None:
        members = _pair()
        spec = _ensemble_spec(members)
        swapped = _ensemble_spec(members[::-1])
        assert spec.id == swapped.id

    def test_member_kinds_refused(self) -> None:
        for kind in ("linear", "hmm", "garch"):
            with pytest.raises(ValueError, match="only probabilistic classifiers"):
                _ensemble_spec(_pair(model_types=(kind, "logistic")))

    def test_duplicate_members_refused(self) -> None:
        member = _member("e" * 16, model_type="logistic")
        with pytest.raises(ValueError, match="members must be unique"):
            _ensemble_spec([member, member])

    def test_at_least_two_members(self) -> None:
        with pytest.raises(ValidationError):
            EnsembleSpec(
                members=[_member("e" * 16, model_type="logistic")],
                weight_method="inverse_error",
                validation_bars=5,
                id="0" * 16,
            )

    def test_unknown_weight_method_refused(self) -> None:
        with pytest.raises(ValidationError):
            EnsembleSpec(
                members=[
                    _member("e" * 16, model_type="logistic"),
                    _member("e" * 16, model_type="lightgbm"),
                ],
                weight_method="stacking",
                validation_bars=5,
                id="0" * 16,
            )

    def test_id_is_setup_only(self) -> None:
        members = _pair()
        with pytest.raises(ValueError, match="does not match its setup"):
            EnsembleSpec(
                members=members,
                weight_method="inverse_error",
                validation_bars=5,
                id="0" * 16,
            )


class TestEnsembleReport:
    def _drill(
        self,
        tmp_path,
        *,
        weight_method: str = "inverse_error",
        validation_bars: int = 5,
        n_bins: int = 5,
        dataset: str = DATASET,
        model_types: tuple[str, ...] = ("logistic", "lightgbm"),
        flip: bool = False,
    ):
        """One full harness run on a fresh lake + registries; returns the
        report, the registry and the root. ``flip`` swaps in a lake whose
        final test segment's closes are scaled under the same dataset
        name — the flip test's run B."""
        root = tmp_path / "drill"
        if flip:
            _flipped_lake(root / "lake")
        else:
            pinned_lake(root / "lake")
        feature_registry, featureset_id_value = _register_features(
            root / "features", root / "lake", dataset=dataset
        )
        members = _pair(featureset_id_value, model_types=model_types, dataset=dataset)
        spec = _ensemble_spec(members, weight_method=weight_method, validation_bars=validation_bars)
        registry = EnsembleReportRegistry(root=root / "registry", lake_root=root / "lake")
        report = run_ensemble_report(
            spec=spec,
            dataset=dataset,
            revision=1,
            interval="1h",
            universe=UNIVERSE,
            window_spec=WINDOW,
            n_bins=n_bins,
            commit=COMMIT,
            registry=registry,
            feature_registry=feature_registry,
        )
        return report, registry, root

    def test_full_report_inverse_error(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, registry, _ = self._drill(tmp_path)
        assert len(report.windows) == 3
        assert registry.get(report.id).id == report.id
        assert report.metrics["n_windows"] == 3
        assert report.metrics["n_calibration_pairs"] == 87
        assert len(report.calibration) == report.n_bins == 5
        assert sum(bin_row.count for bin_row in report.calibration) == 87
        for window in report.windows:
            assert abs(sum(window.weights) - 1.0) < 1e-6
            assert all(weight >= 0.0 for weight in window.weights)
            assert window.n_validation_observations == 15
            assert window.n_fit_observations > 0
            assert window.mean_disagreement >= 0.0
        # Window 0 and 1 end before the grid end (every label resolves);
        # the final window's newest bar has no outcome yet, so it drops
        # one pair per symbol (M6 precedent).
        assert [window.n_test_observations for window in report.windows] == [30, 30, 27]
        assert [window.brier is not None for window in report.windows] == [True, True, True]

    def test_nnls_report(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        _library("scipy")
        report, _, _ = self._drill(tmp_path, weight_method="nnls")
        for window in report.windows:
            assert abs(sum(window.weights) - 1.0) < 1e-6
        assert report.metrics["n_windows"] == 3

    def test_weights_derive_from_validation_only(self, tmp_path) -> None:
        """The Phase C acceptance: flipping the final test segment's
        closes changes test features and outcomes but leaves every
        window's weights identical — the weight functions receive only
        validation rows by construction."""
        _library("sklearn")
        _library("lightgbm")
        report_a, _, _ = self._drill(tmp_path / "a")
        report_b, _, _ = self._drill(tmp_path / "b", flip=True)
        # The flip perturbs only test bytes: the setup (featureset,
        # members, spec, windowing) is identical, so the report ids are
        # identical too — a different id would prove a leaked setup.
        assert report_a.id == report_b.id
        assert [window.weights for window in report_a.windows] == [
            window.weights for window in report_b.windows
        ]
        # Window 0 is entirely untouched by the flip: identical evidence
        # down to the per-window Brier. Window 1's last test label is
        # direction(close[50]) — close 50 is the first perturbed bar —
        # so its Brier legitimately changes while its weights do not.
        assert [window.model_dump() for window in report_a.windows[:1]] == [
            window.model_dump() for window in report_b.windows[:1]
        ]
        # The flipped windows' evaluation surfaces did change: their
        # Briers and the calibration pool differ.
        assert report_a.windows[-1].brier != report_b.windows[-1].brier
        assert report_a.calibration != report_b.calibration

    def test_identical_members_zero_disagreement(self, tmp_path) -> None:
        """Two logistic members over the same featureset are the same
        model on the same bars: identical predictions, zero weighted
        variance, and equal validation errors give exactly 0.5/0.5.
        The members differ only in their recorded train bounds (setup
        history), which the walk-forward refits ignore."""
        _library("sklearn")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        feature_registry, featureset_id_value = _register_features(
            root / "features", root / "lake"
        )
        later = pd.Timestamp("2026-01-05T06:00:00Z").to_pydatetime()
        members = [
            _member(featureset_id_value, model_type="logistic"),
            _member(
                featureset_id_value,
                model_type="logistic",
                train_start=later,
                train_end=pd.Timestamp("2026-01-06T06:00:00Z").to_pydatetime(),
            ),
        ]
        spec = _ensemble_spec(members, validation_bars=5)
        registry = EnsembleReportRegistry(root=root / "registry", lake_root=root / "lake")
        report = run_ensemble_report(
            spec=spec,
            dataset=DATASET,
            revision=1,
            interval="1h",
            universe=UNIVERSE,
            window_spec=WINDOW,
            n_bins=5,
            commit=COMMIT,
            registry=registry,
            feature_registry=feature_registry,
        )
        for window in report.windows:
            assert window.weights == [0.5, 0.5]
            assert window.mean_disagreement == 0.0
        assert report.metrics["mean_disagreement"] == 0.0

    def test_report_id_changes_with_setup(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, _, _ = self._drill(tmp_path)
        other = ensemble_report_id(
            commit=report.commit,
            spec=report.spec,
            dataset=report.dataset,
            revision=report.revision,
            interval=report.interval,
            universe=report.universe,
            window_spec=report.window_spec,
            n_bins=report.n_bins + 1,
        )
        assert other != report.id
        assert ensemble_report_id(
            commit="d" * 40,
            spec=report.spec,
            dataset=report.dataset,
            revision=report.revision,
            interval=report.interval,
            universe=report.universe,
            window_spec=report.window_spec,
            n_bins=report.n_bins,
        ) != report.id
        assert ensemble_report_id(
            commit=report.commit,
            spec=_ensemble_spec(report.spec.members, validation_bars=10),
            dataset=report.dataset,
            revision=report.revision,
            interval=report.interval,
            universe=report.universe,
            window_spec=report.window_spec,
            n_bins=report.n_bins,
        ) != report.id

    def test_report_validator_rejects_mismatched_id(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, _, _ = self._drill(tmp_path)
        with pytest.raises(ValueError, match="does not match its setup"):
            EnsembleReport.model_validate({**report.model_dump(), "id": "0" * 16})

    def test_train_window_must_exceed_validation(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        feature_registry, featureset_id_value = _register_features(root / "features", root / "lake")
        members = [
            _member(featureset_id_value, model_type="logistic"),
            _member(featureset_id_value, model_type="lightgbm"),
        ]
        spec = _ensemble_spec(members, validation_bars=29)
        with pytest.raises(ValueError, match="validation slice by at least 2 bars"):
            run_ensemble_report(
                spec=spec,
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                commit=COMMIT,
                registry=EnsembleReportRegistry(root=root / "registry", lake_root=root / "lake"),
                feature_registry=feature_registry,
            )

    def test_warm_up_longer_than_train_window_refused(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        feature_registry, featureset_id_value = _register_features(root / "features", root / "lake")
        members = [
            _member(featureset_id_value, model_type="logistic"),
            _member(featureset_id_value, model_type="lightgbm"),
        ]
        spec = _ensemble_spec(members, validation_bars=2)
        with pytest.raises(ValueError, match="feature warm-up"):
            run_ensemble_report(
                spec=spec,
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WalkForwardSpec(train_bars=5, test_bars=10, step_bars=10),
                commit=COMMIT,
                registry=EnsembleReportRegistry(root=root / "registry", lake_root=root / "lake"),
                feature_registry=feature_registry,
            )

    def test_unrecorded_featureset_refused(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        feature_registry, _ = _register_features(root / "features", root / "lake")
        members = [
            _member("d" * 16, model_type="logistic"),
            _member("d" * 16, model_type="lightgbm"),
        ]
        spec = _ensemble_spec(members)
        with pytest.raises(ValueError, match="no feature set recorded"):
            run_ensemble_report(
                spec=spec,
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                commit=COMMIT,
                registry=EnsembleReportRegistry(root=root / "registry", lake_root=root / "lake"),
                feature_registry=feature_registry,
            )

    def test_member_grids_must_align(self, tmp_path) -> None:
        """A member whose features warm up deeper cannot contribute
        probabilities on the same bars — the ensemble refuses instead
        of silently mixing row sets."""
        _library("sklearn")
        _library("lightgbm")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        feature_registry = FeatureRegistry(root=root / "features", lake_root=root / "lake")
        ids_a = []
        for symbol in SYMBOLS:
            for name, window in (("momentum", 10), ("log_return", 5), ("realized_vol", 5)):
                spec = feature_registry.record_spec(
                    name=name, kind=FeatureKind.BAR, venue=Venue.MOOMOO, symbol=symbol,
                    interval="1h", dataset=DATASET, revision=1, commit=COMMIT,
                    parameters={"window": window},
                )
                ids_a.append(spec.id)
        ids_b = []
        for symbol in SYMBOLS:
            spec = feature_registry.record_spec(
                name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO, symbol=symbol,
                interval="1h", dataset=DATASET, revision=1, commit=COMMIT,
                parameters={"window": 40},
            )
            ids_b.append(spec.id)
        featureset_a = feature_registry.record_set(name="shallow", feature_ids=ids_a)
        featureset_b = feature_registry.record_set(name="deep", feature_ids=ids_b)
        members = [
            _member(featureset_a.id, model_type="logistic"),
            _member(featureset_b.id, model_type="lightgbm"),
        ]
        spec = _ensemble_spec(members)
        with pytest.raises(ValueError, match="align on the same bar grid"):
            run_ensemble_report(
                spec=spec,
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                commit=COMMIT,
                registry=EnsembleReportRegistry(root=root / "registry", lake_root=root / "lake"),
                feature_registry=feature_registry,
            )

    def test_calibration_reuses_the_m6_discipline(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, _, _ = self._drill(tmp_path, n_bins=5)
        assert all(isinstance(bin_row, CalibrationBin) for bin_row in report.calibration)
        # The curve sits on brier_by_bin's half-open bin grid.
        assert [bin_row.lo for bin_row in report.calibration] == [k / 5 for k in range(5)]
        assert [bin_row.hi for bin_row in report.calibration] == [(k + 1) / 5 for k in range(5)]
        assert sum(bin_row.count for bin_row in report.calibration) == report.metrics[
            "n_calibration_pairs"
        ]
        # Empty bins stay None (the M6 discipline, pinned here directly).
        bins = brier_by_bin([0.25, 0.30, 0.22, 0.28], [0.0, 1.0, 0.0, 1.0], n_bins=10)
        assert bins[0].count == 0
        assert bins[0].mean_prediction is None
        assert bins[0].observed_frequency is None

    def test_registry_refuses_duplicate(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, registry, _ = self._drill(tmp_path)
        with pytest.raises(ValueError, match="already recorded"):
            registry.record(report)

    def test_registry_refuses_dangling_pin(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, registry, root = self._drill(tmp_path)
        # Bump the dataset revision: any NEW report pinning revision 1
        # now dangles, and recording it must refuse before writing. The
        # recorded report itself is already in the store (duplicate
        # refusal fires first), so the probe is a hand-built second
        # report with a fresh spec.
        lake = Lake(root / "lake")
        for symbol in SYMBOLS:
            lake.write_bars(DATASET, fixture_bars(symbol, 70))
        ManifestWriter(root / "lake").generate(DATASET, source="fixture", license="test")
        spec = _ensemble_spec(report.spec.members, validation_bars=3)
        fresh = EnsembleReport(
            id=ensemble_report_id(
                commit=COMMIT,
                spec=spec,
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                n_bins=5,
            ),
            commit=COMMIT,
            spec=spec,
            dataset=DATASET,
            revision=1,
            interval="1h",
            universe=UNIVERSE,
            window_spec=WINDOW,
            n_bins=5,
            created_at=report.created_at,
            metrics={},
            windows=[],
            calibration=[],
        )
        path = root / "registry" / "ensembles.jsonl"
        before = path.read_text(encoding="utf-8")
        with pytest.raises(ValueError, match="now revision 2"):
            registry.record(fresh)
        assert path.read_text(encoding="utf-8") == before

    def test_registry_fail_closed_reads(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, registry, root = self._drill(tmp_path)
        path = root / "registry" / "ensembles.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{not json}\n")
        with pytest.raises(ValueError, match="line 2 is invalid"):
            registry.all()
        # Duplicate ids in the store fail closed too.
        path.write_text(
            report.model_dump_json() + "\n" + report.model_dump_json() + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="share a report id"):
            registry.all()

    def test_registry_root_not_dir(self, tmp_path) -> None:
        _library("sklearn")
        _library("lightgbm")
        report, _, root = self._drill(tmp_path)
        path = tmp_path / "not-a-dir"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            EnsembleReportRegistry(root=path).record(report)

    def test_acceptance_drill_across_roots(self, tmp_path) -> None:
        """The Phase C acceptance: identical ids and byte-identical
        artifacts from two independent roots (ADR-0009 determinism)."""
        _library("sklearn")
        _library("lightgbm")
        report_a, registry_a, root_a = self._drill(tmp_path / "a")
        report_b, registry_b, root_b = self._drill(tmp_path / "b")
        assert report_a.id == report_b.id
        assert report_a.metrics == report_b.metrics
        assert [window.model_dump() for window in report_a.windows] == [
            window.model_dump() for window in report_b.windows
        ]
        assert report_a.calibration == report_b.calibration
        for name in ("report.json", "windows.csv", "calibration.csv"):
            path_a = ensemble_artifact_paths(root_a / "registry", report_a)[name]
            path_b = ensemble_artifact_paths(root_b / "registry", report_b)[name]
            assert path_a.read_bytes() == path_b.read_bytes()


class TestUnavailable:
    """Typed errors without the research extra (ADR-0009 decision 6)."""

    def _fake_imports(self, monkeypatch) -> None:
        real_import = importlib.import_module

        def fake_import(name, *args, **kwargs):
            if name.split(".")[0] in LIBRARIES:
                raise ImportError(f"no {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fake_import)

    def test_module_imports_without_research_stack(self, monkeypatch) -> None:
        """Importing the ensemble surface never touches scipy."""
        self._fake_imports(monkeypatch)
        import quantmesh.research.ensemble  # noqa: F401

    def test_nnls_unavailable_without_scipy(self, monkeypatch) -> None:
        self._fake_imports(monkeypatch)
        with pytest.raises(PipelineUnavailableError, match="scipy"):
            nnls_weights(np.ones((4, 2)), np.zeros(4))
