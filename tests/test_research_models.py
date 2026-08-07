"""Model registry: byte-addressed artifacts, setup-only identity (issue #39).

The registry mirrors the M3 experiment-registry discipline: model
identity pins the setup (commit, type, hyperparameters, feature-set
digest, dataset, revision, training window bounds) — never metrics or
weights — artifacts are byte-addressed with the sha256 recorded and
re-verified on load, and the acceptance drill proves a pinned spec
fits identical bytes across registry roots.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from research_fixtures import pinned_lake

from quantmesh.data.lake import Lake
from quantmesh.domain.models import Venue
from quantmesh.research.features import (
    FeatureKind,
    FeatureSpec,
    compute_features,
    feature_id,
)
from quantmesh.research.models import (
    MODEL_TYPES,
    LinearModel,
    ModelRegistry,
    ModelSpec,
    artifact_path,
    fit_model,
    model_id,
)

COMMIT = "c" * 40
DATASET = "equities"
TRAIN_START = datetime(2026, 1, 5, tzinfo=UTC)
TRAIN_END = datetime(2026, 1, 7, tzinfo=UTC)
FEATURESET = "f" * 16


def _mid(**overrides) -> str:
    fields = dict(
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
        model_type="linear",
        hyperparameters={},
        featureset_id_value=FEATURESET,
        train_start=TRAIN_START,
        train_end=TRAIN_END,
    )
    fields.update(overrides)
    return model_id(**fields)


def spec(**overrides) -> ModelSpec:
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
        fields["id"] = _mid(
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


def frame(n: int = 50) -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=n, freq="h", tz="UTC")
    x = np.linspace(1.0, 3.0, n)
    return pd.DataFrame({"x": x, "z": x**2 - 1.0}, index=index)


def target(frame_: pd.DataFrame) -> pd.Series:
    return pd.Series(
        2.0 * frame_["x"].to_numpy() - 1.0 * frame_["z"].to_numpy() + 0.5,
        index=frame_.index,
    )


def drill_features(lake_root, **overrides) -> list:
    """The two-drill-feature specs over the fixture lake (issue #39 drill)."""
    base = dict(
        kind=FeatureKind.BAR,
        venue=Venue.MOOMOO,
        symbol="AAA",
        interval="1h",
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
    )
    specs = []
    for name, window in (("momentum", 10), ("realized_vol", 10)):
        parameters = {"window": window}
        fields = {**base, "name": name, "parameters": parameters}
        fields.update(overrides)
        fields["id"] = feature_id(
            dataset=fields["dataset"],
            revision=fields["revision"],
            commit=fields["commit"],
            name=fields["name"],
            kind=fields["kind"],
            venue=fields["venue"],
            symbol=fields["symbol"],
            interval=fields["interval"],
            parameters=fields["parameters"],
        )
        specs.append(
            FeatureSpec(
                id=fields["id"],
                name=fields["name"],
                kind=fields["kind"],
                venue=fields["venue"],
                symbol=fields["symbol"],
                interval=fields["interval"],
                dataset=fields["dataset"],
                revision=fields["revision"],
                commit=fields["commit"],
                parameters=fields["parameters"],
            )
        )
    return specs


# --- linear model codec ------------------------------------------------------


class TestLinearModel:
    def test_closed_form_fit(self) -> None:
        X = frame()
        model = LinearModel.fit(X, target(X))
        np.testing.assert_allclose(model.weights, [2.0, -1.0], rtol=1e-9)
        assert model.intercept == pytest.approx(0.5, abs=1e-9)

    def test_predict_matches(self) -> None:
        X = frame()
        model = LinearModel.fit(X, target(X))
        np.testing.assert_allclose(model.predict(X), target(X).to_numpy(), rtol=1e-9)

    def test_validation_failures(self) -> None:
        X = frame()
        y = target(X)
        with pytest.raises(ValueError, match="without features"):
            LinearModel.fit(pd.DataFrame(index=X.index), y)
        with pytest.raises(ValueError, match="duplicate feature columns"):
            LinearModel.fit(pd.concat([X, X["x"]], axis=1), y)
        with pytest.raises(ValueError, match="same index"):
            LinearModel.fit(X, y.iloc[1:])
        with pytest.raises(ValueError, match="non-finite"):
            y_nan = y.copy()
            y_nan.iloc[0] = np.nan
            LinearModel.fit(X, y_nan)
        with pytest.raises(ValueError, match="non-finite"):
            X_nan = X.copy()
            X_nan.iloc[0, 0] = np.nan
            LinearModel.fit(X_nan, y)
        with pytest.raises(ValueError, match="boolean"):
            LinearModel.fit(X, y, train_mask=pd.Series([1] * len(X), index=X.index))
        with pytest.raises(ValueError, match="exactly the feature index"):
            LinearModel.fit(X, y, train_mask=pd.Series([True] * len(X)))
        with pytest.raises(ValueError, match="selects no rows"):
            LinearModel.fit(
                X, y, train_mask=pd.Series([False] * len(X), index=X.index)
            )

    def test_train_mask_selects_a_subset(self) -> None:
        X = frame()
        # The plain target lies exactly in the span of {1, x, z}, so any
        # subset fits identically; a deterministic wobble outside the
        # span makes the mask observable.
        y = target(X) + 0.1 * np.sin(2.0 * np.pi * X["x"].to_numpy())
        mask = pd.Series([True] * 40 + [False] * (len(X) - 40), index=X.index)
        subset = LinearModel.fit(X, y, train_mask=mask)
        full = LinearModel.fit(X, y)
        assert not np.allclose(subset.weights, full.weights)

    def test_predict_column_order_pinned(self) -> None:
        X = frame()
        model = LinearModel.fit(X, target(X))
        with pytest.raises(ValueError, match="do not match trained order"):
            model.predict(X[["z", "x"]])
        with pytest.raises(ValueError, match="non-finite"):
            model.predict(X.assign(x=np.inf))

    def test_bytes_round_trip_and_stability(self) -> None:
        X = frame()
        first = LinearModel.fit(X, target(X))
        second = LinearModel.fit(X, target(X))
        assert first.to_bytes() == second.to_bytes()
        restored = LinearModel.from_bytes(first.to_bytes())
        np.testing.assert_allclose(restored.weights, first.weights)
        assert restored.intercept == first.intercept
        assert restored.feature_names == first.feature_names

    def test_from_bytes_failures(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            LinearModel.from_bytes(b"\xff\xfe not json")
        with pytest.raises(ValueError, match="unknown format"):
            LinearModel.from_bytes(b'{"format": "other"}')
        with pytest.raises(ValueError, match="features or weights"):
            LinearModel.from_bytes(b'{"format": "quantmesh-linear-v1"}')
        with pytest.raises(ValueError, match="features but"):
            LinearModel.from_bytes(
                b'{"format": "quantmesh-linear-v1", "features": ["a", "b"], '
                b'"weights": [1.0], "intercept": 0.0}'
            )
        with pytest.raises(ValueError, match="must be finite"):
            LinearModel.from_bytes(
                b'{"format": "quantmesh-linear-v1", "features": ["a"], '
                b'"weights": [Infinity], "intercept": 0.0}'
            )

    def test_constructor_validation(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            LinearModel(np.array([1.0, 2.0]), 0.0, ("a",))
        with pytest.raises(ValueError, match="must be finite"):
            LinearModel(np.array([np.inf]), 0.0, ("a",))


# --- spec identity -----------------------------------------------------------


class TestModelSpec:
    def test_same_setup_same_id(self) -> None:
        assert spec().id == spec().id

    def test_any_setup_change_changes_the_id(self) -> None:
        base = spec()
        variations = [
            spec(hyperparameters={"alpha": 1}),
            spec(featureset_id="e" * 16),
            spec(dataset="crypto"),
            spec(revision=2),
            spec(commit="d" * 40),
            spec(train_start=TRAIN_START - timedelta(hours=1)),
            spec(train_end=TRAIN_END + timedelta(hours=1)),
        ]
        assert all(variant.id != base.id for variant in variations)

    def test_unknown_model_type_refused(self) -> None:
        assert MODEL_TYPES == ("linear",)
        with pytest.raises(ValueError, match="unknown model type"):
            spec(model_type="lightgbm")

    def test_window_validation(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            spec(train_start=datetime(2026, 1, 5))
        with pytest.raises(ValueError, match="train_start < train_end"):
            spec(train_start=TRAIN_END, train_end=TRAIN_START)

    def test_wrong_id_and_other_pins_refused(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            spec(id="0" * 16)
        with pytest.raises(ValueError, match="not finite"):
            spec(hyperparameters={"alpha": float("inf")})
        with pytest.raises(ValueError, match="commit"):
            spec(commit="short")
        with pytest.raises(ValueError, match="dataset"):
            spec(dataset="Bad Name!")


class TestFitModel:
    def test_linear_dispatch(self) -> None:
        X = frame()
        model = fit_model(spec(), X, target(X))
        assert isinstance(model, LinearModel)
        np.testing.assert_allclose(model.predict(X), target(X).to_numpy(), rtol=1e-9)


# --- registry discipline -----------------------------------------------------


class TestModelRegistry:
    def test_record_writes_artifact_and_record(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record(spec=spec(), artifact_bytes=b"artifact")
        assert (
            artifact_path(tmp_path / "registry", recorded.id).read_bytes()
            == b"artifact"
        )
        assert recorded.artifact_sha256 == hashlib.sha256(b"artifact").hexdigest()
        assert registry.get(recorded.id) == recorded
        assert recorded.id == recorded.spec.id

    def test_load_reverifies_sha(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record(spec=spec(), artifact_bytes=b"payload")
        record, data = registry.load(recorded.id)
        assert data == b"payload"
        assert record.artifact_sha256 == recorded.artifact_sha256

    def test_tampered_artifact_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record(spec=spec(), artifact_bytes=b"payload")
        artifact_path(tmp_path / "registry", recorded.id).write_bytes(b"tampered")
        with pytest.raises(ValueError, match="does not match the recorded sha256"):
            registry.load(recorded.id)

    def test_missing_artifact_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record(spec=spec(), artifact_bytes=b"payload")
        artifact_path(tmp_path / "registry", recorded.id).unlink()
        with pytest.raises(ValueError, match="unreadable"):
            registry.load(recorded.id)

    def test_duplicate_refused(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        registry.record(spec=spec(), artifact_bytes=b"payload")
        with pytest.raises(ValueError, match="already recorded"):
            registry.record(spec=spec(), artifact_bytes=b"payload")

    def test_unpinned_dataset_refused_before_write(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        with pytest.raises(ValueError, match="no manifest"):
            registry.record(spec=spec(dataset="ghost"), artifact_bytes=b"payload")
        assert not (tmp_path / "registry").exists()

    def test_metrics_must_be_finite(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        with pytest.raises(ValueError, match="not finite"):
            registry.record(
                spec=spec(), metrics={"mse": float("nan")}, artifact_bytes=b"x"
            )

    def test_persists_across_instances(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        first = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = first.record(spec=spec(), artifact_bytes=b"payload")
        second = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        assert second.get(recorded.id) == recorded
        assert second.load(recorded.id)[1] == b"payload"

    def test_corrupted_line_and_duplicate_ids(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record(spec=spec(), artifact_bytes=b"payload")
        path = tmp_path / "registry" / "models.jsonl"
        path.write_text('{"broken": true}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="line 1 is invalid"):
            registry.all()
        path.write_text(
            recorded.model_dump_json() + "\n" + recorded.model_dump_json() + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="share an id"):
            registry.all()

    def test_root_is_a_file_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        root = tmp_path / "registry"
        root.write_text("nope", encoding="utf-8")
        registry = ModelRegistry(root, lake_root=tmp_path)
        with pytest.raises(ValueError, match="not a directory"):
            registry.all()

    def test_resolve_opens_the_pinned_dataset(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = ModelRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record(spec=spec(), artifact_bytes=b"payload")
        dataset = registry.resolve(recorded.id)
        assert dataset.manifest.dataset == DATASET


# --- acceptance drill: byte-identical fits across registry roots ------------


class TestAcceptanceDrill:
    def _frames_and_target(self, lake_root) -> tuple[pd.DataFrame, pd.Series]:
        frames = compute_features(drill_features(lake_root), lake_root=lake_root)
        bars = Lake(lake_root).dataset(DATASET).read_bars(
            interval="1h", venue=Venue.MOOMOO, symbol="AAA"
        )
        closes = pd.Series(
            [bar.close for bar in bars], index=[bar.timestamp for bar in bars]
        )
        target_series = closes.pct_change(1).dropna()
        # Frames start at the window warm-up (t=10), the target at t=1;
        # reindex aligns the target onto the frame index.
        X = pd.DataFrame(
            {name: frames[name] for name in ("momentum", "realized_vol")}
        ).dropna()
        return X, target_series.reindex(X.index)

    def test_pinned_spec_fits_identical_bytes_across_roots(self, tmp_path) -> None:
        lake_a = tmp_path / "lake-a"
        lake_b = tmp_path / "lake-b"
        pinned_lake(lake_a)
        pinned_lake(lake_b)
        X_a, y_a = self._frames_and_target(lake_a)
        X_b, y_b = self._frames_and_target(lake_b)
        spec_a = spec()
        spec_b = spec()
        assert spec_a.id == spec_b.id

        mask = pd.Series([True] * 40 + [False] * (len(X_a) - 40), index=X_a.index)
        model_a = fit_model(spec_a, X_a, y_a, train_mask=mask)
        model_b = fit_model(spec_b, X_b, y_b, train_mask=mask)

        registry_a = ModelRegistry(tmp_path / "registry-a", lake_root=lake_a)
        registry_b = ModelRegistry(tmp_path / "registry-b", lake_root=lake_b)
        record_a = registry_a.record(
            spec=spec_a, metrics={"n_train": 40}, artifact_bytes=model_a.to_bytes()
        )
        record_b = registry_b.record(
            spec=spec_b, metrics={"n_train": 40}, artifact_bytes=model_b.to_bytes()
        )
        # The artifact is byte-identical across registry roots and the
        # recorded sha256 agrees; only created_at differs between records.
        assert record_a.artifact_sha256 == record_b.artifact_sha256
        assert record_a.id == record_b.id
        assert record_a.metrics == record_b.metrics
        restored = LinearModel.from_bytes(registry_b.load(record_b.id)[1])
        np.testing.assert_allclose(restored.predict(X_a), model_a.predict(X_a))
