"""Feature registry: versioned features, deterministic computation (issue #39).

The registry mirrors the M3 experiment-registry discipline: setup-only
identity (commit + name + kind + venue + symbol + interval + dataset +
revision + parameters), lake-pin validation at record and resolve,
JSONL with atomic appends and fail-closed reads. Computation is
deterministic by construction — pure pandas builtins over pinned bars,
warm-up trimmed, frames finite — and the acceptance drill proves a
pinned feature set reproduces identical frames across registry and
lake roots (a clean checkout).
"""

import math

import pandas as pd
import pytest
from research_fixtures import fixture_bars, pinned_lake

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.models import Venue
from quantmesh.research.features import (
    FEATURES,
    FeatureKind,
    FeatureRegistry,
    FeatureSpec,
    compute_feature,
    compute_features,
    feature_id,
    featureset_id,
    frame_digest,
)

COMMIT = "c" * 40
DATASET = "equities"


def _fid(**overrides) -> str:
    fields = dict(
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
        name="momentum",
        kind=FeatureKind.BAR,
        venue=Venue.MOOMOO,
        symbol="AAA",
        interval="1h",
        parameters={"window": 10},
    )
    fields.update(overrides)
    return feature_id(**fields)


def spec(**overrides) -> FeatureSpec:
    fields = dict(
        name="momentum",
        kind=FeatureKind.BAR,
        venue=Venue.MOOMOO,
        symbol="AAA",
        interval="1h",
        dataset=DATASET,
        revision=1,
        commit=COMMIT,
        parameters={"window": 10},
    )
    fields.update(overrides)
    if "window" in fields:
        parameters = dict(fields.get("parameters") or {})
        parameters["window"] = fields.pop("window")
        fields["parameters"] = parameters
    if "id" not in fields:
        fields["id"] = _fid(
            **{k: v for k, v in fields.items() if k != "id"},
        )
    return FeatureSpec(**fields)


def assert_close(actual: pd.Series, expected: pd.Series) -> None:
    """Closed-form pinning within float noise (1 ulp-class differences)."""
    pd.testing.assert_series_equal(
        actual, expected, check_exact=False, rtol=1e-12, atol=1e-12
    )


# --- identity ----------------------------------------------------------------


class TestFeatureId:
    def test_same_setup_same_id(self) -> None:
        assert _fid() == _fid()

    def test_any_setup_change_changes_the_id(self) -> None:
        base = _fid()
        variations = [
            _fid(revision=2),
            _fid(commit="d" * 40),
            _fid(name="log_return"),
            _fid(venue=Venue.HYPERLIQUID),
            _fid(symbol="BBB"),
            _fid(interval="5m"),
            _fid(dataset="crypto"),
            _fid(parameters={"window": 20}),
            _fid(parameters={"window": 10, "extra": 1}),
        ]
        assert all(variant != base for variant in variations)

    def test_featureset_id_is_order_insensitive(self) -> None:
        first = featureset_id("set", ["a" * 16, "b" * 16])
        assert first == featureset_id("set", ["b" * 16, "a" * 16])
        assert first != featureset_id("set2", ["a" * 16, "b" * 16])


# --- model validation --------------------------------------------------------


class TestFeatureSpec:
    def test_wrong_id_refused(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            spec(id="0" * 16)

    def test_invalid_name_refused(self) -> None:
        for name in ("1abc", "Aaa", "abc-def", "abc.def"):
            with pytest.raises(ValueError, match="name"):
                spec(name=name)

    def test_unknown_builtin_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown feature"):
            spec(name="magic_feature")

    def test_parameter_contract_refused(self) -> None:
        with pytest.raises(ValueError, match="requires parameter 'window'"):
            spec(parameters={})
        with pytest.raises(ValueError, match="must be an int"):
            spec(parameters={"window": "10"})
        with pytest.raises(ValueError, match="must be >= 2"):
            spec(parameters={"window": 1})
        with pytest.raises(ValueError, match="accepts only parameter 'window'"):
            spec(parameters={"window": 10, "extra": 2})
        with pytest.raises(ValueError, match="not finite"):
            spec(parameters={"window": float("nan")})

    def test_commit_interval_symbol_dataset_refused(self) -> None:
        with pytest.raises(ValueError, match="commit"):
            spec(commit="nope")
        with pytest.raises(ValueError, match="interval"):
            spec(interval="quarterly")
        with pytest.raises(ValueError, match="symbol"):
            spec(symbol="")
        with pytest.raises(ValueError, match="dataset"):
            spec(dataset="Bad Name!")


# --- builtin arithmetic (closed form) ---------------------------------------


class TestBuiltins:
    def _linear(self, n: int = 40) -> pd.Series:
        return pd.Series(
            [100.0 + i for i in range(n)],
            index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
        )

    def _geometric(self, n: int = 40) -> pd.Series:
        return pd.Series(
            [100.0 * 1.01**i for i in range(n)],
            index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
        )

    def test_momentum_closed_form(self) -> None:
        closes = self._linear()
        frame = FEATURES["momentum"](closes, {"window": 10})
        # The leading window is the NaN warm-up; the valid suffix must be
        # the closed form exactly.
        expected = pd.Series(
            [10.0 / (90.0 + t) for t in range(10, len(closes))],
            index=closes.index[10:],
        )
        assert_close(frame.iloc[10:], expected)

    def test_log_return_closed_form(self) -> None:
        closes = self._linear()
        frame = FEATURES["log_return"](closes, {"window": 10})
        expected = pd.Series(
            [math.log((100.0 + t) / (90.0 + t)) for t in range(10, len(closes))],
            index=closes.index[10:],
        )
        assert_close(frame.iloc[10:], expected)

    def test_rolling_mean_closed_form(self) -> None:
        closes = self._linear()
        frame = FEATURES["rolling_mean"](closes, {"window": 10})
        expected = pd.Series(
            [100.0 + t - 4.5 for t in range(9, len(closes))],
            index=closes.index[9:],
        )
        assert_close(frame.iloc[9:], expected)

    def test_rolling_std_of_consecutive_ints(self) -> None:
        closes = self._linear()
        frame = FEATURES["rolling_std"](closes, {"window": 10})
        expected = pd.Series(
            [math.sqrt((10**2 - 1) / 12.0)] * (len(closes) - 9),
            index=closes.index[9:],
        )
        assert_close(frame.iloc[9:], expected)

    def test_realized_vol_of_geometric_prices_is_zero(self) -> None:
        closes = self._geometric()
        frame = FEATURES["realized_vol"](closes, {"window": 10})
        # Log-diff makes the first return NaN, so the window lands one
        # bar later than the other builtins.
        expected = pd.Series(
            [0.0] * (len(closes) - 11),
            index=closes.index[11:],
        )
        assert_close(frame.iloc[11:], expected)

    def test_all_builtins_reject_bad_parameters(self) -> None:
        for name in FEATURES:
            with pytest.raises(ValueError, match="requires parameter"):
                FEATURES[name](self._linear(), {})


# --- computation over the lake ----------------------------------------------


class TestComputeFeature:
    def test_momentum_frame_matches_the_bars(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        bars = fixture_bars("AAA", 60)
        closes = pd.Series(
            [bar.close for bar in bars], index=[bar.timestamp for bar in bars]
        )
        dataset = Lake(tmp_path).dataset(DATASET)
        frame = compute_feature(spec(window=10), dataset)
        assert len(frame) == 50
        assert frame.index.is_monotonic_increasing
        assert frame.index[0] == closes.index[10]
        assert frame.iloc[0] == pytest.approx(closes.iloc[10] / closes.iloc[0] - 1.0)
        assert math.isfinite(frame.iloc[-1])

    def test_empty_partition_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        dataset = Lake(tmp_path).dataset(DATASET)
        with pytest.raises(ValueError, match="no bars"):
            compute_feature(spec(symbol="ZZZ"), dataset)

    def test_duplicate_timestamps_fail_closed(self, tmp_path) -> None:
        lake = Lake(tmp_path)
        bars = fixture_bars("AAA", 10)
        # write_bars replaces a day's shard wholesale, so a second call
        # cannot create duplicates; a single call with duplicate
        # timestamps does (the lake reports them via quality().duplicates).
        lake.write_bars(DATASET, bars + bars)
        ManifestWriter(tmp_path).generate(DATASET, source="fixture", license="test")
        dataset = Lake(tmp_path).dataset(DATASET)
        with pytest.raises(ValueError, match="strictly ascending"):
            compute_feature(spec(window=2), dataset)

    def test_missing_dataset_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        with pytest.raises(ValueError, match="no manifest"):
            compute_features([spec(dataset="nope")], lake_root=tmp_path)


class TestComputeFeatures:
    def test_empty_and_duplicate_lists_fail_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        with pytest.raises(ValueError, match="no feature specs"):
            compute_features([], lake_root=tmp_path)
        with pytest.raises(ValueError, match="duplicate feature names"):
            compute_features([spec(), spec()], lake_root=tmp_path)

    def test_wrong_revision_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        with pytest.raises(ValueError, match="manifest revision"):
            compute_features([spec(revision=7)], lake_root=tmp_path)

    def test_frames_keyed_by_name_and_finite(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        frames = compute_features(
            [spec(name="momentum", window=10), spec(name="realized_vol", window=10)],
            lake_root=tmp_path,
        )
        assert set(frames) == {"momentum", "realized_vol"}
        for frame in frames.values():
            assert frame.notna().all()
            assert len(frame) == 50
        assert frames["momentum"].index.equals(frames["realized_vol"].index)

    def test_frame_digest_order_insensitive_and_sensitive(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        specs = [spec(name="momentum", window=10), spec(name="log_return", window=10)]
        frames = compute_features(specs, lake_root=tmp_path)
        assert frame_digest(frames) == frame_digest(dict(reversed(list(frames.items()))))
        other = compute_features([spec(name="momentum", window=20)], lake_root=tmp_path)
        assert frame_digest({"momentum": other["momentum"]}) != frame_digest(
            {"momentum": frames["momentum"]}
        )


# --- registry discipline -----------------------------------------------------


class TestFeatureRegistry:
    def test_record_and_read_back(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        assert registry.all_specs() == [recorded]
        assert registry.get_spec(recorded.id) == recorded

    def test_duplicate_spec_refused(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        with pytest.raises(ValueError, match="already recorded"):
            registry.record_spec(
                name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
                symbol="AAA", interval="1h", dataset=DATASET, revision=1,
                commit=COMMIT, parameters={"window": 10},
            )

    def test_unpinned_dataset_refused_before_write(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        with pytest.raises(ValueError, match="no manifest"):
            registry.record_spec(
                name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
                symbol="AAA", interval="1h", dataset="ghost", revision=1,
                commit=COMMIT, parameters={"window": 10},
            )
        assert not (tmp_path / "registry").exists()

    def test_wrong_revision_refused_before_write(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        with pytest.raises(ValueError, match="manifest revision"):
            registry.record_spec(
                name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
                symbol="AAA", interval="1h", dataset=DATASET, revision=9,
                commit=COMMIT, parameters={"window": 10},
            )
        assert not (tmp_path / "registry").exists()

    def test_feature_set_requires_recorded_members(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        with pytest.raises(ValueError, match="unrecorded features"):
            registry.record_set(name="momentum_set", feature_ids=["a" * 16])
        momentum = registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        volatility = registry.record_spec(
            name="realized_vol", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        feature_set = registry.record_set(
            name="momentum_set", feature_ids=[volatility.id, momentum.id]
        )
        assert feature_set.feature_ids == sorted([momentum.id, volatility.id])
        assert registry.get_set(feature_set.id) == feature_set

    def test_duplicate_set_refused(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        momentum = registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        registry.record_set(name="set", feature_ids=[momentum.id])
        with pytest.raises(ValueError, match="already recorded"):
            registry.record_set(name="set", feature_ids=[momentum.id])

    def test_persists_across_instances(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        first = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        momentum = first.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        volatility = first.record_spec(
            name="realized_vol", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        first.record_set(name="set", feature_ids=[momentum.id, volatility.id])
        second = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        assert {record.id for record in second.all_specs()} == {
            momentum.id,
            volatility.id,
        }
        assert second.all_sets()[0].feature_ids == sorted([momentum.id, volatility.id])

    def test_corrupted_line_read_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        path = tmp_path / "registry" / "features.jsonl"
        path.write_text('{"broken": true}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="line 1 is invalid"):
            registry.all_specs()

    def test_duplicate_id_lines_refused(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        recorded = registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        path = tmp_path / "registry" / "features.jsonl"
        path.write_text(
            recorded.model_dump_json() + "\n" + recorded.model_dump_json() + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="share an id"):
            registry.all_specs()

    def test_root_is_a_file_fails_closed(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        root = tmp_path / "registry"
        root.write_text("nope", encoding="utf-8")
        registry = FeatureRegistry(root, lake_root=tmp_path)
        with pytest.raises(ValueError, match="not a directory"):
            registry.all_specs()

    def test_resolve_opens_the_pinned_dataset(self, tmp_path) -> None:
        pinned_lake(tmp_path)
        registry = FeatureRegistry(tmp_path / "registry", lake_root=tmp_path)
        momentum = registry.record_spec(
            name="momentum", kind=FeatureKind.BAR, venue=Venue.MOOMOO,
            symbol="AAA", interval="1h", dataset=DATASET, revision=1,
            commit=COMMIT, parameters={"window": 10},
        )
        dataset = registry.resolve(momentum.id)
        assert dataset.manifest.dataset == DATASET
        assert dataset.manifest.revision == 1


# --- acceptance drill: clean-checkout reproducibility -----------------------


class TestAcceptanceDrill:
    def _drill_specs(self) -> list[FeatureSpec]:
        return [spec(name="momentum", window=10), spec(name="realized_vol", window=10)]

    def test_pinned_feature_set_reproduces_identical_frames(self, tmp_path) -> None:
        # Two identical lake roots (a clean checkout) and two registry
        # roots: the recorded setup reproduces byte-identical frames.
        lake_a = tmp_path / "lake-a"
        lake_b = tmp_path / "lake-b"
        pinned_lake(lake_a)
        pinned_lake(lake_b)
        registry_a = FeatureRegistry(tmp_path / "registry-a", lake_root=lake_a)
        registry_b = FeatureRegistry(tmp_path / "registry-b", lake_root=lake_b)
        recorded_a = [
            registry_a.record_spec(**spec.model_dump(exclude={"id"}))
            for spec in self._drill_specs()
        ]
        recorded_b = [
            registry_b.record_spec(**spec.model_dump(exclude={"id"}))
            for spec in self._drill_specs()
        ]
        assert [record.id for record in recorded_a] == [record.id for record in recorded_b]
        feature_set = registry_a.record_set(
            name="drill_set", feature_ids=[record.id for record in recorded_a]
        )
        frames_a = compute_features(self._drill_specs(), lake_root=lake_a)
        frames_b = compute_features(self._drill_specs(), lake_root=lake_b)
        for name in frames_a:
            pd.testing.assert_series_equal(frames_a[name], frames_b[name])
        assert frame_digest(frames_a) == frame_digest(frames_b)
        # The recorded set pins the recorded members.
        assert feature_set.feature_ids == sorted(record.id for record in recorded_a)
        assert registry_b.all_sets() == []
        assert registry_a.get_set(feature_set.id).feature_ids == feature_set.feature_ids
