import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.research.experiments import ExperimentRegistry, experiment_id

BTC = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
COMMIT = "a" * 40


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    lake_root = tmp_path / "lake"
    registry_root = tmp_path / "experiments"
    return lake_root, registry_root


def _make_bars(count: int = 3) -> list[Bar]:
    return [
        Bar(
            instrument=BTC,
            timestamp=T0 + timedelta(minutes=index),
            interval="1m",
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=10.0 + index,
        )
        for index in range(count)
    ]


def _pinned_dataset(lake_root: Path, name: str = "algo") -> None:
    Lake(lake_root).write_bars(name, _make_bars())
    ManifestWriter(lake_root).generate(name, source="fixture", license="test")


def _record(
    registry: ExperimentRegistry,
    *,
    dataset: str = "algo",
    revision: int = 1,
    parameters: dict | None = None,
    metrics: dict | None = None,
):
    return registry.record(
        dataset=dataset,
        revision=revision,
        commit=COMMIT,
        parameters=parameters,
        metrics=metrics,
    )


def test_record_links_pinned_inputs(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    recorded = _record(
        ExperimentRegistry(root=registry_root, lake_root=lake_root),
        parameters={"lookback": 20, "rebalance": "daily"},
        metrics={"sharpe": 1.5, "max_drawdown": -0.12},
    )

    assert len(recorded.id) == 16
    assert set(recorded.id) <= set("0123456789abcdef")
    assert recorded.dataset == "algo"
    assert recorded.revision == 1
    assert recorded.commit == COMMIT
    assert recorded.parameters == {"lookback": 20, "rebalance": "daily"}
    assert recorded.metrics == {"sharpe": 1.5, "max_drawdown": -0.12}
    assert recorded.created_at.tzinfo is UTC


def test_experiment_id_is_deterministic_setup_only() -> None:
    parameters = {"lr": 0.01, "depth": 3}

    assert experiment_id("algo", 1, COMMIT, parameters) == experiment_id(
        "algo", 1, COMMIT, parameters
    )
    assert experiment_id("algo", 1, COMMIT, parameters) != experiment_id(
        "algo", 2, COMMIT, parameters
    )
    assert experiment_id("algo", 1, COMMIT, parameters) != experiment_id(
        "algo", 1, COMMIT, {"lr": 0.02, "depth": 3}
    )


def test_trusted_lineage_is_part_of_experiment_identity() -> None:
    parameters = {"lr": 0.01}
    legacy = experiment_id("algo", 1, COMMIT, parameters)
    trusted = experiment_id(
        "algo",
        1,
        COMMIT,
        parameters,
        manifest_id="1" * 64,
        quality_evaluation_id="2" * 64,
    )

    assert trusted != legacy


def test_registry_refuses_unverified_trusted_experiment_lineage(tmp_path: Path) -> None:
    registry = ExperimentRegistry(
        root=tmp_path / "registry",
        lake_root=tmp_path / "lake",
    )

    with pytest.raises(ValueError, match="requires a data catalog"):
        registry.record(
            dataset="algo",
            revision=1,
            manifest_id="1" * 64,
            quality_evaluation_id="2" * 64,
            commit=COMMIT,
        )


def test_registry_resolves_trusted_experiment_through_exact_catalog(
    tmp_path: Path,
) -> None:
    marker = object()

    class Catalog:
        def open_research_dataset(self, *args, **kwargs):
            assert args == ("1" * 64,)
            assert kwargs == {
                "evaluation_id": "2" * 64,
                "dataset_id": "algo",
                "compatibility_revision": 1,
            }
            return marker

    registry = ExperimentRegistry(
        root=tmp_path / "registry",
        lake_root=tmp_path / "lake",
        trusted_catalog=Catalog(),
    )
    recorded = registry.record(
        dataset="algo",
        revision=1,
        manifest_id="1" * 64,
        quality_evaluation_id="2" * 64,
        commit=COMMIT,
    )

    assert registry.resolve(recorded.id) is marker


def test_metrics_do_not_change_experiment_identity(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    registry = ExperimentRegistry(root=registry_root, lake_root=lake_root)
    _record(registry, metrics={"sharpe": 1.5})

    with pytest.raises(ValueError, match="already recorded"):
        _record(registry, metrics={"sharpe": 2.0})


def test_different_parameters_are_new_experiments(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    registry = ExperimentRegistry(root=registry_root, lake_root=lake_root)
    first = _record(registry, parameters={"lookback": 20})
    second = _record(registry, parameters={"lookback": 40})

    assert first.id != second.id
    assert [record.id for record in registry.all()] == [first.id, second.id]


def test_record_rejects_invalid_dataset_name(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    with pytest.raises(ValidationError):
        _record(ExperimentRegistry(root=registry_root, lake_root=lake_root), dataset="Bad Name")


def test_record_rejects_nonpositive_revision(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    with pytest.raises(ValidationError):
        _record(ExperimentRegistry(root=registry_root, lake_root=lake_root), revision=0)


def test_record_rejects_bad_commit(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    registry = ExperimentRegistry(root=registry_root, lake_root=lake_root)

    with pytest.raises(ValidationError):
        registry.record(dataset="algo", revision=1, commit="not-a-hash")


def test_record_requires_the_pinned_dataset(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots

    with pytest.raises(ValueError, match="no manifest"):
        _record(ExperimentRegistry(root=registry_root, lake_root=lake_root))


def test_record_rejects_stale_pin(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    with pytest.raises(ValueError, match="pins manifest revision"):
        _record(
            ExperimentRegistry(root=registry_root, lake_root=lake_root),
            revision=2,
        )


def test_commit_defaults_to_current_head(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    recorded = ExperimentRegistry(root=registry_root, lake_root=lake_root).record(
        dataset="algo", revision=1
    )

    assert len(recorded.commit) == 40
    assert set(recorded.commit) <= set("0123456789abcdef")


def test_commit_resolution_fails_closed(
    roots: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="pass commit explicitly"):
        ExperimentRegistry(root=registry_root, lake_root=lake_root).record(
            dataset="algo", revision=1
        )


def test_get_roundtrip_and_missing(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    recorded = _record(ExperimentRegistry(root=registry_root, lake_root=lake_root))

    registry = ExperimentRegistry(root=registry_root, lake_root=lake_root)
    assert registry.get(recorded.id) == recorded
    with pytest.raises(ValueError, match="no experiment"):
        registry.get("0" * 16)


def test_registry_persists_across_instances(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    first = _record(
        ExperimentRegistry(root=registry_root, lake_root=lake_root),
        parameters={"lookback": 20},
    )
    second = _record(
        ExperimentRegistry(root=registry_root, lake_root=lake_root),
        parameters={"lookback": 40},
    )

    fresh = ExperimentRegistry(root=registry_root, lake_root=lake_root)
    assert [record.id for record in fresh.all()] == [first.id, second.id]
    assert fresh.get(first.id).metrics == {}
    assert fresh.get(second.id).metrics == {}


def test_corrupt_registry_line_fails_closed(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    _record(ExperimentRegistry(root=registry_root, lake_root=lake_root))
    path = registry_root / "experiments.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    with pytest.raises(ValueError, match="line 2 is invalid"):
        ExperimentRegistry(root=registry_root, lake_root=lake_root).all()


def test_tampered_record_fails_closed(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    recorded = _record(ExperimentRegistry(root=registry_root, lake_root=lake_root))
    path = registry_root / "experiments.jsonl"
    tampered = path.read_text(encoding="utf-8").replace(
        f'"id":"{recorded.id}"', '"id":"0000000000000000"', 1
    )
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(ValueError, match="line 1 is invalid"):
        ExperimentRegistry(root=registry_root, lake_root=lake_root).all()


def test_resolve_reopens_pinned_dataset_on_clean_checkout(
    roots: tuple[Path, Path], tmp_path: Path
) -> None:
    """M3 exit criterion: manifest → lake → experiment registry."""
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    recorded = _record(
        ExperimentRegistry(root=registry_root, lake_root=lake_root),
        parameters={"lookback": 20},
        metrics={"sharpe": 1.5},
    )

    fresh = tmp_path / "checkout"
    fresh_lake = fresh / "lake"
    fresh_registry = fresh / "experiments"
    shutil.copytree(lake_root, fresh_lake)
    shutil.copytree(registry_root, fresh_registry)

    dataset = ExperimentRegistry(root=fresh_registry, lake_root=fresh_lake).resolve(
        recorded.id
    )
    assert dataset.manifest.revision == 1
    bars = dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    assert [b.timestamp for b in bars] == [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]

    # The pin is a promise about the bytes: a regenerated manifest voids it.
    ManifestWriter(fresh_lake).generate("algo", source="fixture", license="test")
    with pytest.raises(ValueError, match="pins manifest revision"):
        ExperimentRegistry(root=fresh_registry, lake_root=fresh_lake).resolve(recorded.id)


def test_resolve_rejects_unknown_id(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    with pytest.raises(ValueError, match="no experiment"):
        ExperimentRegistry(root=registry_root, lake_root=lake_root).resolve("0" * 16)


def test_non_finite_parameter_fails_closed(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    with pytest.raises(ValidationError, match="not finite"):
        _record(
            ExperimentRegistry(root=registry_root, lake_root=lake_root),
            parameters={"loss": float("nan")},
        )


def test_non_finite_metric_fails_closed(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)

    with pytest.raises(ValidationError, match="not finite"):
        _record(
            ExperimentRegistry(root=registry_root, lake_root=lake_root),
            metrics={"sharpe": float("inf")},
        )


def test_duplicate_id_in_file_fails_closed(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    _record(
        ExperimentRegistry(root=registry_root, lake_root=lake_root),
        metrics={"sharpe": 1.0},
    )
    path = registry_root / "experiments.jsonl"
    line = path.read_text(encoding="utf-8").splitlines()[0]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.replace('"sharpe":1.0', '"sharpe":99.0') + "\n")

    with pytest.raises(ValueError, match="share an experiment id"):
        ExperimentRegistry(root=registry_root, lake_root=lake_root).all()


def test_registry_root_is_a_file_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    root.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        ExperimentRegistry(root=root, lake_root=tmp_path).all()


def test_duplicate_still_reported_after_lake_advances(roots: tuple[Path, Path]) -> None:
    lake_root, registry_root = roots
    _pinned_dataset(lake_root)
    registry = ExperimentRegistry(root=registry_root, lake_root=lake_root)
    _record(registry)
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")

    with pytest.raises(ValueError, match="already recorded"):
        _record(registry)
