"""Baseline strategies, walk-forward backtester, and end-to-end reports (issue #27).

The backtester is deterministic by construction — no random generator
anywhere — and fail closed: misaligned series, insufficient bars, and
undefined risk-parity inputs are errors, not silent adjustments. The
end-to-end runner pins the dataset through the lake's manifest gate and
produces artifacts whose bytes are reproducible.
"""

from datetime import timedelta

import pytest
from research_fixtures import START, SYMBOLS, fixture_bars, pinned_lake

from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.research.baselines import (
    mean_reversion_weights,
    momentum_weights,
    risk_parity_weights,
    run_baseline_report,
    run_walk_forward,
)
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    UniverseMember,
    WalkForwardSpec,
)

COMMIT = "b" * 40
UNIVERSE = [
    UniverseMember(venue=Venue.MOOMOO, symbol=symbol) for symbol in SYMBOLS
]
SPEC = WalkForwardSpec(train_bars=30, test_bars=10, step_bars=10)
COSTS = CostModel(fee_bps=5, half_spread_bps=5, slippage_bps=2)
ZERO_COSTS = CostModel(fee_bps=0, half_spread_bps=0, slippage_bps=0)


def fixture_series(n: int = 60) -> dict[str, list[Bar]]:
    return {symbol: fixture_bars(symbol, n) for symbol in SYMBOLS}


def flat_series(symbol: str, n: int = 60) -> list[Bar]:
    instrument = Instrument(
        symbol=symbol,
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )
    return [
        Bar(
            instrument=instrument,
            timestamp=START + timedelta(hours=index),
            interval="1h",
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1000.0,
        )
        for index in range(n)
    ]


# --- strategy weight functions -----------------------------------------------

def test_momentum_weights_long_top_half() -> None:
    weights = momentum_weights({"A": 0.1, "B": 0.0, "C": -0.1})
    assert weights == {"A": 0.5, "B": 0.5, "C": 0.0}


def test_mean_reversion_weights_long_bottom_half() -> None:
    weights = mean_reversion_weights({"A": 0.1, "B": 0.0, "C": -0.1})
    assert weights == {"A": 0.0, "B": 0.5, "C": 0.5}


def test_weight_ties_break_on_symbol() -> None:
    returns = {"A": 0.1, "B": 0.1, "C": 0.0}
    assert momentum_weights(returns) == {"A": 0.5, "B": 0.5, "C": 0.0}
    assert mean_reversion_weights(returns) == {"A": 0.5, "B": 0.0, "C": 0.5}


def test_risk_parity_weights_inverse_volatility() -> None:
    weights = risk_parity_weights(
        {"A": 0.0, "B": 0.0, "C": 0.0}, {"A": 0.01, "B": 0.02, "C": 0.04}
    )
    assert weights == pytest.approx({"A": 4 / 7, "B": 2 / 7, "C": 1 / 7})


def test_risk_parity_excludes_zero_volatility_symbols() -> None:
    weights = risk_parity_weights(
        {"A": 0.0, "B": 0.0, "C": 0.0}, {"A": 0.01, "B": 0.0, "C": 0.02}
    )
    assert weights["B"] == 0.0
    assert weights["A"] + weights["C"] == pytest.approx(1.0)


def test_risk_parity_all_zero_volatility_fails_closed() -> None:
    with pytest.raises(ValueError, match="zero train volatility"):
        risk_parity_weights({"A": 0.0, "B": 0.0}, {"A": 0.0, "B": 0.0})


# --- walk-forward backtester -------------------------------------------------

def test_walk_forward_window_structure() -> None:
    result = run_walk_forward(
        fixture_series(), strategy="momentum", window_spec=SPEC, costs=COSTS
    )
    assert [window.index for window in result.windows] == [0, 1, 2]
    assert [window.n_trades for window in result.windows] == [2, 0, 0]
    assert result.windows[0].turnover == pytest.approx(1.0)  # entry from flat
    assert result.windows[0].cost == pytest.approx(COSTS.rate())
    assert len(result.equity_curve) == 30  # 3 windows x 10 test bars


def test_walk_forward_insufficient_bars_fails_closed() -> None:
    series = {symbol: fixture_bars(symbol, 35) for symbol in SYMBOLS}
    with pytest.raises(ValueError, match="cannot host"):
        run_walk_forward(series, strategy="momentum", window_spec=SPEC, costs=COSTS)


def test_walk_forward_misaligned_series_fails_closed() -> None:
    series = fixture_series()
    series["BBB"] = [
        bar.model_copy(update={"timestamp": bar.timestamp + timedelta(days=1)})
        for bar in series["BBB"]
    ]
    with pytest.raises(ValueError, match="misaligned"):
        run_walk_forward(series, strategy="momentum", window_spec=SPEC, costs=COSTS)


def test_walk_forward_mixed_lengths_fail_closed() -> None:
    series = fixture_series()
    series["CCC"] = series["CCC"][:-5]
    with pytest.raises(ValueError, match="differ in length"):
        run_walk_forward(series, strategy="momentum", window_spec=SPEC, costs=COSTS)


def test_walk_forward_unknown_strategy_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown strategy"):
        run_walk_forward(fixture_series(), strategy="pairs", window_spec=SPEC, costs=COSTS)


def test_costs_reduce_returns_and_are_charged_once() -> None:
    costly = run_walk_forward(fixture_series(), strategy="momentum", window_spec=SPEC, costs=COSTS)
    free = run_walk_forward(
        fixture_series(), strategy="momentum", window_spec=SPEC, costs=ZERO_COSTS
    )
    assert costly.metrics["total_cost"] > 0
    assert free.metrics["total_cost"] == 0
    assert costly.metrics["total_return"] < free.metrics["total_return"]
    # cost is charged once per window, on one-way turnover
    expected = COSTS.rate() * sum(window.turnover for window in costly.windows)
    assert costly.metrics["total_cost"] == pytest.approx(expected)


def test_metrics_schema_is_fixed() -> None:
    result = run_walk_forward(
        fixture_series(), strategy="risk_parity", window_spec=SPEC, costs=COSTS
    )
    assert set(result.metrics) == {
        "total_return",
        "annualized_return",
        "sharpe",
        "max_drawdown",
        "win_rate",
        "n_windows",
        "avg_turnover",
        "total_cost",
    }
    assert result.metrics["n_windows"] == 3
    expected_wins = sum(1 for window in result.windows if window.window_return > 0)
    assert result.metrics["win_rate"] == pytest.approx(expected_wins / 3)
    assert 0 < result.metrics["win_rate"] <= 1


def test_sharpe_is_none_when_returns_are_flat() -> None:
    result = run_walk_forward(
        {"A": flat_series("A")}, strategy="momentum", window_spec=SPEC, costs=ZERO_COSTS
    )
    assert result.metrics["sharpe"] is None
    assert result.metrics["total_return"] == 0.0


# --- end-to-end report runner -------------------------------------------------

@pytest.fixture
def roots(tmp_path) -> tuple:
    lake_root = tmp_path / "lake"
    registry_root = tmp_path / "reports"
    pinned_lake(lake_root)
    return lake_root, registry_root


def run_report(registry: ReportRegistry, strategy: str = "momentum"):
    return run_baseline_report(
        dataset="equities",
        revision=1,
        strategy=strategy,
        interval="1h",
        universe=UNIVERSE,
        window_spec=SPEC,
        costs=COSTS,
        commit=COMMIT,
        registry=registry,
    )


@pytest.mark.parametrize("strategy", ["momentum", "mean_reversion", "risk_parity"])
def test_report_runs_end_to_end(roots, strategy: str) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)

    report = run_report(registry, strategy)

    assert len(report.id) == 16
    assert report.strategy == strategy
    assert report.revision == 1
    assert report.metrics["n_windows"] == 3
    assert len(report.windows) == 3
    assert registry.get(report.id) == report
    for name in ("report.json", "equity_curve.csv", "trades.csv"):
        assert (registry_root / report.id / name).exists()


def test_report_artifacts_are_well_formed(roots) -> None:
    lake_root, registry_root = roots
    report = run_report(ReportRegistry(root=registry_root, lake_root=lake_root))
    lines = (registry_root / report.id / "equity_curve.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert lines[0] == "timestamp,equity,window_index"
    assert len(lines) == 31  # header + 30 days
    trade_lines = (registry_root / report.id / "trades.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert trade_lines[0] == "timestamp,symbol,weight_before,weight_after,cost"
    assert len(trade_lines) == 3  # first window: two entries plus header


def test_report_runner_refuses_revision_mismatch(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    from quantmesh.data.manifest import ManifestWriter

    ManifestWriter(lake_root).generate("equities", source="fixture", license="test")
    with pytest.raises(ValueError, match="revision"):
        run_report(registry)


def test_report_runner_refuses_empty_member(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    universe = [
        UniverseMember(venue=Venue.MOOMOO, symbol="MISSING"),
        *UNIVERSE,
    ]
    with pytest.raises(ValueError, match="MISSING"):
        run_baseline_report(
            dataset="equities",
            revision=1,
            strategy="momentum",
            interval="1h",
            universe=universe,
            window_spec=SPEC,
            costs=COSTS,
            commit=COMMIT,
            registry=registry,
        )


def test_report_runner_refuses_duplicate_member(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    with pytest.raises(ValueError, match="more than once"):
        run_baseline_report(
            dataset="equities",
            revision=1,
            strategy="momentum",
            interval="1h",
            universe=[UNIVERSE[0], UNIVERSE[0]],
            window_spec=SPEC,
            costs=COSTS,
            commit=COMMIT,
            registry=registry,
        )


def test_report_runner_refuses_empty_universe(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    with pytest.raises(ValueError, match="must not be empty"):
        run_baseline_report(
            dataset="equities",
            revision=1,
            strategy="momentum",
            interval="1h",
            universe=[],
            window_spec=SPEC,
            costs=COSTS,
            commit=COMMIT,
            registry=registry,
        )


def test_report_runner_refuses_symbol_on_multiple_venues(roots) -> None:
    """The backtester keys bars by symbol; a cross-venue duplicate would
    silently overwrite one venue's series, so it fails closed instead."""
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    with pytest.raises(ValueError, match="more than one venue"):
        run_baseline_report(
            dataset="equities",
            revision=1,
            strategy="momentum",
            interval="1h",
            universe=[UNIVERSE[0], UniverseMember(venue=Venue.HYPERLIQUID, symbol="AAA")],
            window_spec=SPEC,
            costs=COSTS,
            commit=COMMIT,
            registry=registry,
        )


def test_report_runner_refuses_unknown_strategy(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    with pytest.raises(ValueError, match="unknown strategy"):
        run_baseline_report(
            dataset="equities",
            revision=1,
            strategy="pairs",
            interval="1h",
            universe=UNIVERSE,
            window_spec=SPEC,
            costs=COSTS,
            commit=COMMIT,
            registry=registry,
        )


def test_reproducibility_regenerates_identical_reports(tmp_path) -> None:
    """The Phase C acceptance: identical pinned setup -> identical output."""
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_registry = None
    for root in (first_root, second_root):
        pinned_lake(root / "lake")
        registry = ReportRegistry(root=root / "reports", lake_root=root / "lake")
        run_report(registry)
        if first_registry is None:
            first_registry = registry
    first_report = first_registry.all()[0]
    second_report = ReportRegistry(
        root=second_root / "reports", lake_root=second_root / "lake"
    ).get(first_report.id)
    assert first_report.id == second_report.id
    assert first_report.metrics == second_report.metrics
    assert first_report.windows == second_report.windows
    for name in ("report.json", "equity_curve.csv", "trades.csv"):
        first_bytes = (first_root / "reports" / first_report.id / name).read_bytes()
        second_bytes = (second_root / "reports" / second_report.id / name).read_bytes()
        assert first_bytes == second_bytes, f"{name} differs between runs"
    # created_at is bookkeeping and must not leak into the artifact
    import json

    document = json.loads(
        (first_root / "reports" / first_report.id / "report.json").read_text(encoding="utf-8")
    )
    assert "created_at" not in document


def test_rerun_into_same_registry_is_refused(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    run_report(registry)
    with pytest.raises(ValueError, match="already recorded"):
        run_report(registry)
