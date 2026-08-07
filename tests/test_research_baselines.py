"""Baseline strategies, walk-forward backtester, and end-to-end reports (issue #27).

The backtester is deterministic by construction — no random generator
anywhere — and fail closed: misaligned series, insufficient bars, and
undefined risk-parity inputs are errors, not silent adjustments. The
end-to-end runner pins the dataset through the lake's manifest gate and
produces artifacts whose bytes are reproducible.
"""

import math
from datetime import timedelta

import pytest
from research_fixtures import START, SYMBOLS, fixture_bars, pinned_lake

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.market_data import Bar, DepthLevel, OrderBook
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.signal import imbalance_by_bar
from quantmesh.research.baselines import (
    book_imbalance_weights,
    low_volatility_weights,
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
    report_id,
)

COMMIT = "b" * 40
UNIVERSE = [
    UniverseMember(venue=Venue.MOOMOO, symbol=symbol) for symbol in SYMBOLS
]
SPEC = WalkForwardSpec(train_bars=30, test_bars=10, step_bars=10)
COSTS = CostModel(fee_bps=5, half_spread_bps=5, slippage_bps=2)
ZERO_COSTS = CostModel(fee_bps=0, half_spread_bps=0, slippage_bps=0)

# Per-symbol bid-side bias for the Phase D book fixtures: AAA is
# bid-heavy (+1/3 imbalance), BBB balanced (0), CCC ask-heavy (−1/3).
BIAS = {"AAA": 2.0, "BBB": 1.0, "CCC": 0.5}
UNIVERSE_CRYPTO = [
    UniverseMember(venue=Venue.HYPERLIQUID, symbol=symbol) for symbol in SYMBOLS
]


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


# --- Phase D: M5 crypto baselines (issue #32) ----------------------------------


def test_low_volatility_weights_long_quietest_bottom_half() -> None:
    assert low_volatility_weights({"A": 0.2, "B": 0.1, "C": 0.3}) == {
        "A": 0.5,
        "B": 0.5,
        "C": 0.0,
    }
    assert low_volatility_weights({"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}) == {
        "A": 0.0,
        "B": 0.0,
        "C": 0.5,
        "D": 0.5,
    }


def test_low_volatility_includes_zero_volatility_symbols() -> None:
    # Unlike risk-parity, zero train volatility is the signal, not an
    # undefined input.
    assert low_volatility_weights({"A": 0.0, "B": 0.1}) == {"A": 1.0, "B": 0.0}


def test_book_imbalance_weights_long_signal_top_half() -> None:
    assert book_imbalance_weights({"A": 0.3, "B": -0.1, "C": 0.0}) == {
        "A": 0.5,
        "B": 0.0,
        "C": 0.5,
    }


def test_baseline_weight_ties_break_on_symbol() -> None:
    assert low_volatility_weights({"A": 0.1, "B": 0.1, "C": 0.1}) == {
        "A": 0.5,
        "B": 0.5,
        "C": 0.0,
    }
    assert book_imbalance_weights({"A": 0.0, "B": 0.0, "C": 0.0}) == {
        "A": 0.0,
        "B": 0.5,
        "C": 0.5,
    }


def test_book_imbalance_without_signals_fails_closed() -> None:
    with pytest.raises(ValueError, match="needs signals_by_symbol"):
        run_walk_forward(
            fixture_series(),
            strategy="book_imbalance",
            window_spec=SPEC,
            costs=ZERO_COSTS,
        )


def test_signal_series_must_match_the_bar_grid() -> None:
    series = fixture_series(60)
    with pytest.raises(ValueError, match="shifted signal"):
        run_walk_forward(
            series,
            strategy="book_imbalance",
            window_spec=SPEC,
            costs=ZERO_COSTS,
            signals_by_symbol={symbol: [0.0] * 59 for symbol in SYMBOLS},
        )


def test_signal_series_must_match_the_universe() -> None:
    series = fixture_series(60)
    signals = {symbol: [0.0] * 60 for symbol in SYMBOLS}
    signals["ZZZ"] = [0.0] * 60
    with pytest.raises(ValueError, match="disagree on the universe"):
        run_walk_forward(
            series,
            strategy="book_imbalance",
            window_spec=SPEC,
            costs=ZERO_COSTS,
            signals_by_symbol=signals,
        )


def test_book_imbalance_weights_use_train_window_signals_only() -> None:
    """No lookahead: window 1 trains on AAA (+), BBB (0), CCC (−) — the
    test segment holds AAA/BBB even though window 2's train signals turn
    against AAA and window 3 rotates to BBB/CCC."""
    series = fixture_series(60)
    signals = {symbol: [0.0] * 60 for symbol in SYMBOLS}
    for index in range(60):
        signals["AAA"][index] = 0.5 if index < 30 else -0.5
        signals["CCC"][index] = -0.5 if index < 30 else 0.5
    result = run_walk_forward(
        series,
        strategy="book_imbalance",
        window_spec=SPEC,
        costs=ZERO_COSTS,
        signals_by_symbol=signals,
    )
    assert {(symbol, after) for _, symbol, _, after, _ in result.trades[:2]} == {
        ("AAA", 0.5),
        ("BBB", 0.5),
    }
    assert result.windows[0].n_trades == 2  # the initial rebalance
    assert result.windows[1].n_trades == 0  # weights held through window 2
    assert result.windows[2].n_trades == 2  # window 3 rotates to BBB/CCC


def test_low_volatility_report_runs_end_to_end(roots) -> None:
    lake_root, registry_root = roots
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)
    report = run_report(registry, "low_volatility")
    assert report.strategy == "low_volatility"
    assert report.metrics["n_windows"] == 3
    assert registry.get(report.id) == report


def crypto_bars(symbol: str, n: int = 60) -> list[Bar]:
    """HYPERLIQUID-venue bars over the same closed-form shapes."""
    base, drift, amplitude = SYMBOLS[symbol]
    instrument = Instrument(
        symbol=symbol,
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    return [
        Bar(
            instrument=instrument,
            timestamp=START + timedelta(hours=index),
            interval="1h",
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000.0,
        )
        for index in range(n)
        for price in [
            base * (1.0 + drift * index / n + amplitude * math.sin(2 * math.pi * index / 14))
        ]
    ]


def crypto_books(symbol: str, n: int = 60) -> list[OrderBook]:
    """Two snapshots per bar window; the bid side scales by the bias."""
    bars = crypto_bars(symbol, n)
    bias = BIAS[symbol]
    books = []
    for bar in bars:
        for offset_minutes in (15, 45):
            books.append(
                OrderBook(
                    instrument=bar.instrument,
                    timestamp=bar.timestamp + timedelta(minutes=offset_minutes),
                    bids=[DepthLevel(price=bar.close * 0.999, quantity=10.0 * bias)],
                    asks=[DepthLevel(price=bar.close * 1.001, quantity=10.0)],
                )
            )
    return books


def crypto_lake(root, *, name: str = "crypto") -> None:  # noqa: ANN001
    lake = Lake(root)
    for symbol in SYMBOLS:
        lake.write_bars(name, crypto_bars(symbol))
    ManifestWriter(root).generate(name, source="fixture", license="test")


def crypto_signals() -> dict[str, list[float]]:
    return {
        symbol: imbalance_by_bar(crypto_books(symbol), crypto_bars(symbol))
        for symbol in SYMBOLS
    }


def run_crypto_report(
    registry: ReportRegistry, *, signals: dict[str, list[float]] | None = None
):
    return run_baseline_report(
        dataset="crypto",
        revision=1,
        strategy="book_imbalance",
        interval="1h",
        universe=UNIVERSE_CRYPTO,
        window_spec=SPEC,
        costs=COSTS,
        signals_by_symbol=signals,
        commit=COMMIT,
        registry=registry,
    )


def test_book_imbalance_report_runs_end_to_end(tmp_path) -> None:
    lake_root = tmp_path / "lake"
    registry_root = tmp_path / "reports"
    crypto_lake(lake_root)
    registry = ReportRegistry(root=registry_root, lake_root=lake_root)

    report = run_crypto_report(registry, signals=crypto_signals())

    assert report.strategy == "book_imbalance"
    assert report.metrics["n_windows"] == 3
    assert len(report.windows) == 3
    assert registry.get(report.id) == report
    for name in ("report.json", "equity_curve.csv", "trades.csv"):
        assert (registry_root / report.id / name).exists()


def test_signal_reports_are_byte_reproducible(tmp_path) -> None:
    """The Phase D acceptance: identical pinned setup + signals -> identical bytes."""
    first_id = None
    for root in (tmp_path / "first", tmp_path / "second"):
        crypto_lake(root / "lake")
        registry = ReportRegistry(root=root / "reports", lake_root=root / "lake")
        report = run_crypto_report(registry, signals=crypto_signals())
        if first_id is None:
            first_id = report.id
        else:
            assert report.id == first_id
            for name in ("report.json", "equity_curve.csv", "trades.csv"):
                first_bytes = (tmp_path / "first" / "reports" / first_id / name).read_bytes()
                second_bytes = (root / "reports" / report.id / name).read_bytes()
                assert first_bytes == second_bytes, f"{name} differs between runs"


def test_signal_inputs_are_part_of_the_report_identity(tmp_path) -> None:
    """Different signal series, same dataset pin -> different report ids."""
    ids = []
    for bias in (2.0, 1.0):
        lake_root = tmp_path / f"lake-{bias}"
        registry = ReportRegistry(
            root=tmp_path / f"reports-{bias}", lake_root=lake_root
        )
        crypto_lake(lake_root)
        signals = crypto_signals()
        if bias == 1.0:  # make every symbol balanced
            signals = {
                symbol: [0.0] * 60 for symbol in SYMBOLS
            }
        ids.append(run_crypto_report(registry, signals=signals).id)
    assert ids[0] != ids[1]


def test_report_id_includes_the_signals_digest() -> None:
    plain = report_id(
        dataset="crypto",
        revision=1,
        commit=COMMIT,
        strategy="book_imbalance",
        interval="1h",
        universe=UNIVERSE_CRYPTO,
        window_spec=SPEC,
        costs=COSTS,
    )
    with_signals = report_id(
        dataset="crypto",
        revision=1,
        commit=COMMIT,
        strategy="book_imbalance",
        interval="1h",
        universe=UNIVERSE_CRYPTO,
        window_spec=SPEC,
        costs=COSTS,
        signals_digest="a" * 16,
    )
    assert plain != with_signals
    # None keeps the legacy identity: existing reports do not change.
    assert report_id(
        dataset="crypto",
        revision=1,
        commit=COMMIT,
        strategy="book_imbalance",
        interval="1h",
        universe=UNIVERSE_CRYPTO,
        window_spec=SPEC,
        costs=COSTS,
        signals_digest=None,
    ) == plain
