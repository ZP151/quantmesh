"""StrategyReport contract and ReportRegistry discipline (issue #27, Phase C).

The report is identified by its setup, never its results (ADR-0005):
the same dataset + revision + commit + strategy + interval + universe +
window spec + costs hash to the same 16-hex ID, and a registry record
is refused when the pin is dangling or the ID does not match the setup.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from research_fixtures import pinned_lake

from quantmesh.domain.models import Venue
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    WindowResult,
    artifact_paths,
    report_id,
)

COMMIT = "a" * 40
AAA = UniverseMember(venue=Venue.MOOMOO, symbol="AAA")
BBB = UniverseMember(venue=Venue.MOOMOO, symbol="BBB")
CCC = UniverseMember(venue=Venue.MOOMOO, symbol="CCC")
UNIVERSE = [AAA, BBB, CCC]
SPEC = WalkForwardSpec(train_bars=30, test_bars=10, step_bars=10)
COSTS = CostModel(fee_bps=5, half_spread_bps=5, slippage_bps=2)
T0 = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)


def make_id(
    *,
    strategy: str = "momentum",
    interval: str = "1d",
    universe: list[UniverseMember] | None = None,
    spec: WalkForwardSpec = SPEC,
    costs: CostModel = COSTS,
    dataset: str = "equities",
) -> str:
    return report_id(
        dataset=dataset,
        revision=1,
        commit=COMMIT,
        strategy=strategy,
        interval=interval,
        universe=universe if universe is not None else UNIVERSE,
        window_spec=spec,
        costs=costs,
    )


def make_report(strategy: str = "momentum", **overrides) -> StrategyReport:
    values = dict(
        id=make_id(strategy=strategy),
        dataset="equities",
        revision=1,
        commit=COMMIT,
        strategy=strategy,
        interval="1d",
        universe=UNIVERSE,
        window_spec=SPEC,
        costs=COSTS,
        created_at=T0,
        metrics={"total_return": 0.1, "n_windows": 3},
        windows=[
            WindowResult(
                index=0,
                train_end=T0,
                test_start=T0,
                test_end=T0,
                window_return=0.03,
                turnover=1.0,
                cost=0.0017,
                n_trades=2,
            )
        ],
    )
    values.update(overrides)
    return StrategyReport(**values)


# --- CostModel ---------------------------------------------------------------

def test_cost_model_rate_sums_bps() -> None:
    assert CostModel(fee_bps=100, half_spread_bps=50, slippage_bps=25).rate() == 0.0175


def test_cost_model_zero_is_allowed() -> None:
    assert CostModel(fee_bps=0, half_spread_bps=0, slippage_bps=0).rate() == 0.0


@pytest.mark.parametrize("field", ["fee_bps", "half_spread_bps", "slippage_bps"])
def test_cost_model_rejects_negative(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        CostModel(**{field: -1.0, "half_spread_bps": 0, "slippage_bps": 0})


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_cost_model_rejects_non_finite(value: float) -> None:
    # NaN fails the ge=0 constraint; inf passes it and hits the finite
    # validator — both are refused at the boundary.
    with pytest.raises(ValidationError):
        CostModel(fee_bps=value, half_spread_bps=0, slippage_bps=0)


# --- WalkForwardSpec ---------------------------------------------------------

def test_window_spec_rejects_one_bar_train() -> None:
    with pytest.raises(ValidationError, match="train_bars"):
        WalkForwardSpec(train_bars=1, test_bars=10, step_bars=10)


def test_window_spec_rejects_overlapping_segments() -> None:
    with pytest.raises(ValidationError, match="never overlap"):
        WalkForwardSpec(train_bars=30, test_bars=10, step_bars=5)


def test_window_spec_test_starts() -> None:
    assert SPEC.test_starts(60) == [30, 40, 50]
    assert SPEC.test_starts(59) == [30, 40]


def test_window_spec_insufficient_grid_fails_closed() -> None:
    with pytest.raises(ValueError, match="cannot host"):
        SPEC.test_starts(35)


# --- UniverseMember ----------------------------------------------------------

def test_universe_member_rejects_empty_symbol() -> None:
    with pytest.raises(ValidationError, match="symbol"):
        UniverseMember(venue=Venue.MOOMOO, symbol="")


# --- report_id ---------------------------------------------------------------

def test_report_id_is_deterministic_and_order_independent() -> None:
    assert make_id() == make_id()
    assert make_id(universe=list(reversed(UNIVERSE))) == make_id()


def test_report_id_changes_with_setup() -> None:
    assert make_id(strategy="risk_parity") != make_id()
    assert make_id(interval="5m") != make_id()
    assert make_id(costs=CostModel(fee_bps=1, half_spread_bps=0, slippage_bps=0)) != make_id()
    assert make_id(dataset="other") != make_id()


# --- StrategyReport ----------------------------------------------------------

def test_report_round_trips_through_model() -> None:
    report = make_report()
    rebuilt = StrategyReport.model_validate_json(report.model_dump_json())
    assert rebuilt == report
    assert rebuilt.created_at == T0


def test_report_rejects_id_mismatch() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        make_report(id="f" * 16)


def test_report_rejects_unknown_strategy() -> None:
    with pytest.raises(ValidationError, match="unknown strategy"):
        make_report(strategy="pairs")


def test_report_rejects_bad_interval() -> None:
    with pytest.raises(ValidationError, match="interval"):
        make_report(interval="fortnight")


def test_report_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_report(created_at=datetime(2026, 8, 8, 12, 0))


def test_report_rejects_non_finite_metric() -> None:
    with pytest.raises(ValidationError, match="not finite"):
        make_report(metrics={"total_return": float("inf")})


# --- artifact paths ----------------------------------------------------------

def test_artifact_paths_derive_from_report_id() -> None:
    report = make_report()
    paths = artifact_paths(Path("/tmp/reports"), report)
    assert paths == {
        "report.json": Path("/tmp/reports") / report.id / "report.json",
        "equity_curve.csv": Path("/tmp/reports") / report.id / "equity_curve.csv",
        "trades.csv": Path("/tmp/reports") / report.id / "trades.csv",
    }


# --- ReportRegistry ----------------------------------------------------------

@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    lake_root = tmp_path / "lake"
    registry_root = tmp_path / "reports"
    return lake_root, registry_root


def test_registry_records_and_reads_back(roots) -> None:
    lake_root, registry_root = roots
    pinned_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    report = make_report()

    recorded = registry.record(report)

    assert recorded == report
    assert registry.get(report.id) == report
    assert registry.all() == [report]
    assert (registry_root / "reports.jsonl").exists()


def test_registry_refuses_duplicate_id(roots) -> None:
    lake_root, registry_root = roots
    pinned_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    registry.record(make_report())
    with pytest.raises(ValueError, match="already recorded"):
        registry.record(make_report())


def test_registry_refuses_dangling_pin(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    with pytest.raises(ValueError):
        registry.record(make_report())  # no manifest for "equities" at all


def test_registry_refuses_revision_mismatch(roots) -> None:
    lake_root, registry_root = roots
    pinned_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    report = make_report()  # pins revision 1
    # a fresh manifest is revision 2, so the pin no longer matches
    from quantmesh.data.manifest import ManifestWriter

    ManifestWriter(lake_root).generate("equities", source="fixture", license="test")
    with pytest.raises(ValueError, match="revision"):
        registry.record(report)


def test_registry_resolve_returns_pinned_dataset(roots) -> None:
    lake_root, registry_root = roots
    pinned_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    report = make_report()
    registry.record(report)
    dataset = registry.resolve(report.id)
    assert dataset.name == "equities"
    bars = dataset.read_bars(interval="1h", venue=Venue.MOOMOO, symbol="AAA")
    assert len(bars) == 60


def test_registry_read_fails_closed_on_corrupt_line(roots) -> None:
    _, registry_root = roots
    registry_root.mkdir(parents=True)
    (registry_root / "reports.jsonl").write_text(
        "not json\n", encoding="utf-8"
    )
    registry = ReportRegistry(root=registry_root)
    with pytest.raises(ValueError, match="line 1"):
        registry.all()


def test_registry_read_fails_closed_on_duplicate_ids(roots) -> None:
    lake_root, registry_root = roots
    pinned_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    registry.record(make_report())
    line = (registry_root / "reports.jsonl").read_text(encoding="utf-8")
    (registry_root / "reports.jsonl").write_text(line + line, encoding="utf-8")
    with pytest.raises(ValueError, match="share a report id"):
        registry.all()


def test_registry_resolve_refuses_moved_manifest(roots) -> None:
    lake_root, registry_root = roots
    pinned_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    report = make_report()
    registry.record(report)
    from quantmesh.data.manifest import ManifestWriter

    ManifestWriter(lake_root).generate("equities", source="fixture", license="test")
    with pytest.raises(ValueError, match="revision"):
        registry.resolve(report.id)
