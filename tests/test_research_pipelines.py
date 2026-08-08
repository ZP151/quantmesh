"""M7 Phase B tests: baseline pipelines and their report harness (issue #40).

The four pipeline kinds (logistic, lightgbm, hmm, garch) are lazy
import-guarded on the research extra (ADR-0009 decision 6): typed
``PipelineUnavailableError`` without the libraries, real fits with them
(CI installs ``.[dev,research]``). No-lookahead is proven twice: the
label construction is causal by test (future closes cannot change past
labels), and the HMM signal is a manual forward filter whose prefix is
invariant to appended observations (two-directional smoothing would
fail that test). The HMM estimator itself is pure numpy — it fits
under the fully faked import guard, and its hyperparameters are
rejected when non-empty. The acceptance drill runs the pipeline
report on the fixture lake universe across two roots and demands
identical ids and byte-identical artifacts.
"""

import hashlib
import importlib
import importlib.util
import json
import math

import numpy as np
import pandas as pd
import pytest

from quantmesh.domain.models import Venue
from quantmesh.research.baselines import run_walk_forward
from quantmesh.research.features import FeatureKind, FeatureSpec, feature_id
from quantmesh.research.models import ModelRegistry, ModelSpec, fit_model, model_id
from quantmesh.research.pipelines import (
    PIPELINE_KINDS,
    GARCHPipeline,
    HMMPipeline,
    LightGBMPipeline,
    LogisticPipeline,
    PipelineUnavailableError,
    _forward_filter,
    direction_labels,
    normalize_hyperparameters,
    pipeline_digest,
    run_pipeline_report,
)
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    UniverseMember,
    WalkForwardSpec,
)
from tests.research_fixtures import SYMBOLS, fixture_bars, pinned_lake

COMMIT = "c" * 40
DATASET = "equities"
FEATURESET = "e" * 16
TRAIN_START = pd.Timestamp("2026-01-05T00:00:00Z").to_pydatetime()
TRAIN_END = pd.Timestamp("2026-01-06T00:00:00Z").to_pydatetime()

COSTS = CostModel(fee_bps=1, half_spread_bps=1, slippage_bps=1)
WINDOW = WalkForwardSpec(train_bars=30, test_bars=10, step_bars=10)
UNIVERSE = [UniverseMember(venue=Venue.MOOMOO, symbol=symbol) for symbol in SYMBOLS]
LIBRARIES = ("sklearn", "lightgbm", "arch")


def _library(name: str) -> None:
    if importlib.util.find_spec(name) is None:
        pytest.skip(f"{name} is not installed; install quantmesh[research]")


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


def _spec(**overrides) -> ModelSpec:
    fields = dict(
        model_type="linear",
        hyperparameters={},
        featureset_id=FEATURESET,
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
        train_start=TRAIN_START,
        train_end=TRAIN_END,
    )
    fields.update(overrides)
    if "id" not in fields:
        fields["id"] = model_id(
            dataset=fields["dataset"],
            revision=fields["revision"],
            commit=fields["commit"],
            model_type=fields["model_type"],
            hyperparameters=fields["hyperparameters"],
            featureset_id_value=fields["featureset_id"],
            train_start=fields["train_start"],
            train_end=fields["train_end"],
        )
    return ModelSpec(**fields)


class TestPipelineDigest:
    def test_kinds_are_the_strategy_set(self) -> None:
        assert PIPELINE_KINDS == ("logistic", "lightgbm", "hmm", "garch")

    def test_digest_changes_with_every_setup_field(self) -> None:
        base = pipeline_digest("logistic", {}, FEATURESET)
        assert pipeline_digest("lightgbm", {}, FEATURESET) != base
        assert pipeline_digest("logistic", {"C": 0.5}, FEATURESET) != base
        assert pipeline_digest("logistic", {}, "f" * 16) != base

    def test_digest_normalizes_defaults(self) -> None:
        defaults = {
            "n_estimators": 20,
            "num_leaves": 7,
            "learning_rate": 0.05,
            "min_child_samples": 3,
            "deterministic": True,
            "num_threads": 1,
            "seed": 42,
            "verbosity": -1,
        }
        assert pipeline_digest("lightgbm", {}, FEATURESET) == pipeline_digest(
            "lightgbm", defaults, FEATURESET
        )

    def test_unknown_kind_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown pipeline kind"):
            normalize_hyperparameters("xgboost", {})
        with pytest.raises(ValueError, match="unknown pipeline kind"):
            pipeline_digest("xgboost", {}, FEATURESET)

    def test_bad_setup_refused(self) -> None:
        with pytest.raises(ValueError, match="valid identifier"):
            normalize_hyperparameters("logistic", {"bad name": 1})
        with pytest.raises(ValueError, match="finite"):
            normalize_hyperparameters("logistic", {"C": float("inf")})
        with pytest.raises(ValueError, match="is not a featureset id"):
            pipeline_digest("logistic", {}, "not-an-id")

    def test_normalize_merges_defaults(self) -> None:
        merged = normalize_hyperparameters("lightgbm", {"num_leaves": 15})
        assert merged["num_leaves"] == 15
        assert merged["seed"] == 42


class TestUnavailable:
    """Typed errors without the research extra (ADR-0009 decision 6)."""

    def _fake_imports(self, monkeypatch):
        real_import = importlib.import_module

        def fake_import(name, *args, **kwargs):
            if name.split(".")[0] in LIBRARIES:
                raise ImportError(f"no {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fake_import)

    def test_logistic_unavailable(self, monkeypatch) -> None:
        self._fake_imports(monkeypatch)
        with pytest.raises(PipelineUnavailableError, match="scikit-learn"):
            LogisticPipeline().fit(pd.DataFrame({"x": [1.0, 2.0]}), pd.Series([0.0, 1.0]))

    def test_lightgbm_unavailable(self, monkeypatch) -> None:
        self._fake_imports(monkeypatch)
        with pytest.raises(PipelineUnavailableError, match="lightgbm"):
            LightGBMPipeline().fit(pd.DataFrame({"x": [1.0, 2.0]}), pd.Series([0.0, 1.0]))

    def test_hmm_needs_no_optional_library(self, monkeypatch) -> None:
        """The HMM estimator is pure numpy: it fits and signals under
        the fully faked import guard, proving it depends on no
        optional library (ADR-0009 decision 6 boundary)."""
        self._fake_imports(monkeypatch)
        series = _gaussian_regimes()
        pipeline = HMMPipeline().fit({"A": series})
        signal = pipeline.signals({"A": series})["A"]
        assert ((signal >= 0.0) & (signal <= 1.0)).all()

    def test_garch_unavailable(self, monkeypatch) -> None:
        self._fake_imports(monkeypatch)
        with pytest.raises(PipelineUnavailableError, match="arch"):
            GARCHPipeline().fit({"A": pd.Series([0.1, -0.2])})

    def test_rehydrate_is_also_guarded(self, monkeypatch) -> None:
        self._fake_imports(monkeypatch)
        artifact = json.dumps(
            {
                "format": "quantmesh-logistic-v1",
                "hyperparameters": {},
                "coef": [0.5],
                "intercept": 0.0,
                "classes": [0, 1],
            }
        ).encode()
        with pytest.raises(PipelineUnavailableError, match="scikit-learn"):
            LogisticPipeline.from_bytes(artifact)


class TestLogisticPipeline:
    def test_fit_predict_and_round_trip(self) -> None:
        _library("sklearn")
        x = np.linspace(-1.0, 1.0, 40)
        frame = pd.DataFrame({"x": x, "x2": x**2})
        target = pd.Series((x > 0).astype(float))
        pipeline = LogisticPipeline().fit(frame, target)
        assert np.array_equal(pipeline.predict(frame), target.to_numpy())
        assert (pipeline.predict_proba(frame)[x > 0] > 0.5).all()
        assert (pipeline.predict_proba(frame)[x <= 0] < 0.5).all()
        rehydrated = LogisticPipeline.from_bytes(pipeline.to_bytes())
        assert np.allclose(rehydrated.predict_proba(frame), pipeline.predict_proba(frame))

    def test_deterministic_bytes(self) -> None:
        _library("sklearn")
        x = np.linspace(-1.0, 1.0, 40)
        frame = pd.DataFrame({"x": x, "x2": x**2})
        target = pd.Series((x > 0).astype(float))
        first = LogisticPipeline().fit(frame, target)
        second = LogisticPipeline().fit(frame, target)
        assert first.to_bytes() == second.to_bytes()

    def test_single_class_refused(self) -> None:
        _library("sklearn")
        with pytest.raises(ValueError, match="both 0/1 classes"):
            LogisticPipeline().fit(
                pd.DataFrame({"x": [1.0, 2.0, 3.0]}), pd.Series([0.0, 0.0, 0.0])
            )

    def test_non_binary_labels_refused(self) -> None:
        _library("sklearn")
        with pytest.raises(ValueError, match="both 0/1 classes"):
            LogisticPipeline().fit(
                pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]}),
                pd.Series([0.0, 1.0, 2.0, 0.0]),
            )

    def test_unfitted_refused(self) -> None:
        with pytest.raises(ValueError, match="fit\\(\\) before"):
            LogisticPipeline().predict_proba(pd.DataFrame({"x": [1.0]}))
        with pytest.raises(ValueError, match="fit\\(\\) before"):
            LogisticPipeline().to_bytes()

    def test_foreign_artifact_refused(self) -> None:
        with pytest.raises(ValueError, match="format is not"):
            LogisticPipeline.from_bytes(b'{"format": "quantmesh-other-v1"}')
        with pytest.raises(ValueError, match="not valid JSON"):
            LogisticPipeline.from_bytes(b"not json")


class TestLightGBMPipeline:
    @staticmethod
    def _step_frame() -> tuple[pd.DataFrame, pd.Series]:
        # A threshold signal, learnable with high confidence by the
        # small default model (shallow trees, low learning rate); the
        # XOR pattern defeats it because single-feature root splits on
        # XOR data have zero gain, so no tree is ever grown.
        x = np.linspace(-1.0, 1.0, 60)
        frame = pd.DataFrame({"x": x})
        target = pd.Series((x > 0.1).astype(float))
        return frame, target

    def test_fit_predict_and_round_trip(self) -> None:
        _library("lightgbm")
        frame, target = self._step_frame()
        pipeline = LightGBMPipeline().fit(frame, target)
        assert np.array_equal(pipeline.predict(frame), target.to_numpy())
        rehydrated = LightGBMPipeline.from_bytes(pipeline.to_bytes())
        assert np.allclose(rehydrated.predict_proba(frame), pipeline.predict_proba(frame))

    def test_deterministic_bytes(self) -> None:
        _library("lightgbm")
        frame, target = self._step_frame()
        first = LightGBMPipeline().fit(frame, target)
        second = LightGBMPipeline().fit(frame, target)
        assert first.to_bytes() == second.to_bytes()

    def test_single_class_refused(self) -> None:
        _library("lightgbm")
        with pytest.raises(ValueError, match="both 0/1 classes"):
            LightGBMPipeline().fit(
                pd.DataFrame({"x": [1.0, 2.0, 3.0]}), pd.Series([0.0, 0.0, 0.0])
            )


def _regime_returns(n: int = 60) -> pd.Series:
    """Deterministic two-regime series: quiet, volatile, quiet."""
    values = []
    for t in range(n):
        volume = 0.05 if 20 <= t < 40 else 0.005
        values.append(volume * math.sin(t))
    return pd.Series(values)


def _gaussian_regimes(n: int = 60, seed: int = 42) -> pd.Series:
    """Two-scale Gaussian regime draw: quiet, volatile, quiet.

    PCG64 via ``default_rng`` is stable across numpy versions. The
    10x scale ratio makes squared-return emissions separate ~100x in
    expectation — the variance-regime structure the HMM estimator is
    built for (a threshold on squared returns splits it cleanly).
    """
    rng = np.random.default_rng(seed)
    scales = np.repeat([0.005, 0.05, 0.005], 20)[:n]
    return pd.Series(rng.normal(0.0, scales))


class TestHMMPipeline:
    def test_regime_signal_separates_blocks(self) -> None:
        series = _gaussian_regimes()
        pipeline = HMMPipeline().fit({"A": series})
        signal = pipeline.signals({"A": series})["A"]
        assert ((signal >= 0.0) & (signal <= 1.0)).all()
        quiet_first = float(np.mean(signal[:20]))
        volatile = float(np.mean(signal[20:40]))
        quiet_last = float(np.mean(signal[40:]))
        assert volatile > quiet_first + 0.3
        assert volatile > quiet_last + 0.3

    def test_hyperparameters_rejected(self) -> None:
        with pytest.raises(ValueError, match="take no hyperparameters"):
            HMMPipeline({"tol": 1e-3})

    def test_no_variance_contrast_fails_closed(self) -> None:
        flat = pd.Series(np.repeat(0.01, 60))
        with pytest.raises(ValueError, match="no variance contrast"):
            HMMPipeline().fit({"A": flat})

    def test_deterministic_fit_and_round_trip(self) -> None:
        series = _gaussian_regimes()
        first = HMMPipeline().fit({"A": series})
        second = HMMPipeline().fit({"A": series})
        assert first.to_bytes() == second.to_bytes()
        rehydrated = HMMPipeline.from_bytes(first.to_bytes())
        assert np.allclose(
            rehydrated.signals({"A": series})["A"],
            first.signals({"A": series})["A"],
        )

    def test_signal_does_not_depend_on_future(self) -> None:
        """The filter is causal: appending observations cannot change
        the past signal. Two-directional smoothing would fail this;
        the manual forward filter passes it."""
        series = _gaussian_regimes()
        fixed = HMMPipeline.from_bytes(HMMPipeline().fit({"A": series}).to_bytes())
        extended = pd.concat([series, pd.Series([9.0, -9.0, 9.0])])
        full = fixed.signals({"A": series})["A"]
        with_future = fixed.signals({"A": extended})["A"]
        assert np.allclose(full, with_future[: len(series)])

    def test_forward_filter_is_causal(self) -> None:
        means = np.asarray([0.0, 0.0])
        variances = np.asarray([0.01, 1.0])
        transmat = np.asarray([[0.95, 0.05], [0.1, 0.9]])
        startprob = np.asarray([0.9, 0.1])
        values = np.asarray([0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7])
        full = _forward_filter(values, means, variances, transmat, startprob)
        for t in range(1, len(values)):
            prefix = _forward_filter(values[:t], means, variances, transmat, startprob)
            assert np.allclose(prefix[t - 1], full[t - 1])
        assert np.argmax(variances) == 1  # the wide-variance state is the signal

    def test_unfitted_refused(self) -> None:
        with pytest.raises(ValueError, match="fit\\(\\) before"):
            HMMPipeline().signals({"A": pd.Series([0.1])})
        with pytest.raises(ValueError, match="fit\\(\\) before"):
            HMMPipeline().to_bytes()


class TestGARCHPipeline:
    def test_fit_signal_and_round_trip(self) -> None:
        _library("arch")
        series = _regime_returns()
        pipeline = GARCHPipeline().fit({"A": series})
        signal = pipeline.signals({"A": series})["A"]
        assert ((signal > 0.0) & (signal <= 1.0)).all()
        # Calm segments carry higher weight than the volatile one.
        assert float(np.mean(signal[:20])) > float(np.mean(signal[20:40]))
        assert float(np.mean(signal[40:])) > float(np.mean(signal[20:40]))
        rehydrated = GARCHPipeline.from_bytes(pipeline.to_bytes())
        assert np.allclose(
            rehydrated.signals({"A": series})["A"],
            signal,
        )

    def test_deterministic_fit(self) -> None:
        _library("arch")
        series = _regime_returns()
        first = GARCHPipeline().fit({"A": series})
        second = GARCHPipeline().fit({"A": series})
        assert first.to_bytes() == second.to_bytes()

    def test_unfitted_refused(self) -> None:
        with pytest.raises(ValueError, match="fit\\(\\) before"):
            GARCHPipeline().signals({"A": pd.Series([0.1])})
        with pytest.raises(ValueError, match="fit\\(\\) before"):
            GARCHPipeline().to_bytes()


class TestDirectionLabels:
    def test_leading_one_bar_labels(self) -> None:
        closes = pd.Series([1.0, 2.0, 3.0, 2.0, 5.0])
        labels = direction_labels(closes)
        assert labels.tolist() == [1.0, 1.0, 0.0, 1.0]
        assert list(labels.index) == [0, 1, 2, 3]  # the last bar has no label

    def test_labels_are_causal(self) -> None:
        closes = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        labels = direction_labels(closes)
        altered = closes.copy()
        altered.iloc[3:] = 100.0
        assert labels.iloc[:3].equals(direction_labels(altered).iloc[:3])
        # and the future change only moved the label it directly touches
        assert direction_labels(altered).iloc[3] == 0.0

    def test_equal_closes_label_zero(self) -> None:
        assert direction_labels(pd.Series([1.0, 1.0, 2.0])).tolist() == [0.0, 1.0]


class TestWalkForwardProvider:
    def test_provider_is_called_per_window_with_train_slices(self) -> None:
        calls: list[tuple[int, int]] = []

        def provider(train_start: int, test_start: int) -> dict[str, float]:
            calls.append((train_start, test_start))
            return {symbol: float(index) for index, symbol in enumerate(SYMBOLS)}

        bars = {symbol: fixture_bars(symbol) for symbol in SYMBOLS}
        result = run_walk_forward(
            bars,
            strategy="logistic",
            window_spec=WINDOW,
            costs=COSTS,
            window_signal_provider=provider,
        )
        assert calls == [(0, 30), (10, 40), (20, 50)]
        assert len(result.windows) == 3
        # The provider's constants rank AAA < BBB < CCC, so the top half
        # (BBB, CCC) is held equal weight in every window: the first
        # window opens the position (one-way turnover 1.0 from zero
        # holdings), the later windows hold the same weights and trade
        # nothing (turnover 0.0).
        turnover = [window.turnover for window in result.windows]
        assert [round(value, 9) for value in turnover] == [1.0, 0.0, 0.0]
        symbols = {trade[1] for trade in result.trades}
        assert symbols == {"BBB", "CCC"}

    def test_provider_missing_refused(self) -> None:
        bars = {symbol: fixture_bars(symbol) for symbol in SYMBOLS}
        with pytest.raises(ValueError, match="needs a window_signal_provider"):
            run_walk_forward(
                bars,
                strategy="logistic",
                window_spec=WINDOW,
                costs=COSTS,
            )


class TestModelDispatch:
    def test_logistic_dispatch_fits_and_records(self, tmp_path) -> None:
        _library("sklearn")
        x = np.linspace(-1.0, 1.0, 40)
        frame = pd.DataFrame({"x": x, "x2": x**2})
        target = pd.Series((x > 0).astype(float))
        spec = _spec(model_type="logistic")
        model = fit_model(spec, frame, target)
        assert isinstance(model, LogisticPipeline)
        assert np.array_equal(model.predict(frame), target.to_numpy())
        registry = ModelRegistry(root=tmp_path / "models", lake_root=tmp_path / "lake")
        pinned_lake(tmp_path / "lake")
        registry.record(spec=spec, metrics={"acc": 1.0}, artifact_bytes=model.to_bytes())
        record, data = registry.load(spec.id)
        assert record.artifact_sha256 == hashlib.sha256(data).hexdigest()
        rehydrated = LogisticPipeline.from_bytes(data)
        assert np.allclose(rehydrated.predict_proba(frame), model.predict_proba(frame))

    def test_lightgbm_dispatch(self) -> None:
        _library("lightgbm")
        x = np.linspace(-1.0, 1.0, 60)
        frame = pd.DataFrame({"x": x})
        target = pd.Series((x > 0.1).astype(float))
        model = fit_model(_spec(model_type="lightgbm"), frame, target)
        assert isinstance(model, LightGBMPipeline)
        assert np.array_equal(model.predict(frame), target.to_numpy())

    def test_return_pipelines_refuse_fit_model(self) -> None:
        with pytest.raises(ValueError, match="not fit_model"):
            fit_model(_spec(model_type="hmm"), pd.DataFrame({"x": [1.0]}), pd.Series([0.0]))
        with pytest.raises(ValueError, match="not fit_model"):
            fit_model(_spec(model_type="garch"), pd.DataFrame({"x": [1.0]}), pd.Series([0.0]))


class TestRunPipelineReport:
    def _drill(
        self, tmp_path, *, pipeline: str = "logistic", ablations: tuple[str, ...] = ()
    ):
        """One full harness run on a fresh lake + registry; returns the
        report, the registry and the root."""
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "registry", lake_root=root / "lake")
        report = run_pipeline_report(
            pipeline=pipeline,
            featureset=_drill_featureset(),
            dataset=DATASET,
            revision=1,
            interval="1h",
            universe=UNIVERSE,
            window_spec=WINDOW,
            costs=COSTS,
            ablations=ablations,
            commit=COMMIT,
            registry=registry,
        )
        return report, registry, root

    def test_full_report_with_benchmarks_and_ablation(self, tmp_path) -> None:
        _library("sklearn")
        report, registry, _ = self._drill(tmp_path, ablations=("log_return",))
        assert report.strategy == "logistic"
        assert report.pipeline_digest is not None
        assert report.evidence["windows_oos"] is True
        assert len(report.windows) == 3
        assert report.metrics["n_windows"] == 3
        for name in ("momentum", "risk_parity", "low_volatility"):
            benchmark_id = report.evidence[f"benchmark:{name}"]
            assert isinstance(benchmark_id, str)
            benchmark = registry.get(benchmark_id)
            assert benchmark.strategy == name
            assert benchmark.evidence == {}
        ablation_id = report.evidence["ablation:drop:log_return"]
        assert isinstance(ablation_id, str)
        assert ablation_id != report.id
        ablation = registry.get(ablation_id)
        assert ablation.pipeline_digest != report.pipeline_digest
        # The ablation's reduced feature set changes its identity.
        assert ablation.metrics["n_windows"] == report.metrics["n_windows"]
        # Every recorded report is reproducible: five runs in the registry.
        assert len(registry.all()) == 5

    def test_report_id_changes_with_hyperparameters(self, tmp_path) -> None:
        _library("sklearn")
        _, registry, root = self._drill(tmp_path)
        base = registry.all()[-1]
        registry_2 = ReportRegistry(root=root / "registry2", lake_root=root / "lake")
        other = run_pipeline_report(
            pipeline="logistic",
            hyperparameters={"C": 0.25},
            featureset=_drill_featureset(),
            dataset=DATASET,
            revision=1,
            interval="1h",
            universe=UNIVERSE,
            window_spec=WINDOW,
            costs=COSTS,
            commit=COMMIT,
            registry=registry_2,
        )
        assert other.id != base.id

    def test_warm_up_longer_than_train_window_refused(self, tmp_path) -> None:
        _library("sklearn")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "registry", lake_root=root / "lake")
        with pytest.raises(ValueError, match="warm-up"):
            run_pipeline_report(
                pipeline="logistic",
                featureset=_drill_featureset(),
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WalkForwardSpec(train_bars=5, test_bars=10, step_bars=10),
                costs=COSTS,
                commit=COMMIT,
                registry=registry,
            )

    def test_unknown_pipeline_refused_before_any_work(self, tmp_path) -> None:
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "registry", lake_root=root / "lake")
        with pytest.raises(ValueError, match="unknown pipeline kind"):
            run_pipeline_report(
                pipeline="xgboost",
                featureset=_drill_featureset(),
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                costs=COSTS,
                commit=COMMIT,
                registry=registry,
            )

    def test_features_outside_universe_refused(self, tmp_path) -> None:
        _library("sklearn")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "registry", lake_root=root / "lake")
        outsider = _drill_feature("momentum", "ZZZ", window=10)
        with pytest.raises(ValueError, match="outside the universe"):
            run_pipeline_report(
                pipeline="logistic",
                featureset=_drill_featureset() + [outsider],
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                costs=COSTS,
                commit=COMMIT,
                registry=registry,
            )

    def test_ablation_that_empties_the_set_refused(self, tmp_path) -> None:
        _library("sklearn")
        root = tmp_path / "drill"
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "registry", lake_root=root / "lake")
        with pytest.raises(ValueError, match="would leave no features"):
            run_pipeline_report(
                pipeline="logistic",
                featureset=[_drill_feature("momentum", symbol, window=10) for symbol in SYMBOLS],
                dataset=DATASET,
                revision=1,
                interval="1h",
                universe=UNIVERSE,
                window_spec=WINDOW,
                costs=COSTS,
                ablations=("momentum",),
                commit=COMMIT,
                registry=registry,
            )

    def test_acceptance_drill_across_roots(self, tmp_path) -> None:
        """The Phase B acceptance: identical ids and byte-identical
        artifacts from two independent roots (ADR-0009 determinism)."""
        _library("sklearn")
        report_a, registry_a, _ = self._drill(tmp_path / "a", ablations=("log_return",))
        report_b, registry_b, _ = self._drill(tmp_path / "b", ablations=("log_return",))
        assert report_a.id == report_b.id
        assert report_a.pipeline_digest == report_b.pipeline_digest
        assert report_a.metrics == report_b.metrics
        assert report_a.evidence == report_b.evidence
        ids_a = sorted(record.id for record in registry_a.all())
        ids_b = sorted(record.id for record in registry_b.all())
        assert ids_a == ids_b
        from quantmesh.research.reports import artifact_paths

        for name in ("report.json", "equity_curve.csv", "trades.csv"):
            path_a = artifact_paths(tmp_path / "a" / "drill" / "registry", report_a)[name]
            path_b = artifact_paths(tmp_path / "b" / "drill" / "registry", report_b)[name]
            assert path_a.read_bytes() == path_b.read_bytes()
