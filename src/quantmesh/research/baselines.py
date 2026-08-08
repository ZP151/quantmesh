"""Transparent baseline strategies and the walk-forward backtester (issue #27).

The three baselines are pure functions of bars: momentum (long the top
half of the universe by train-period return), mean-reversion (long the
bottom half), and risk-parity (inverse train volatility, zero-volatility
symbols excluded). Nothing here imports a random generator — the
pipeline is deterministic end to end, so the same pinned dataset yields
byte-identical reports (ADR-0005 decisions 6 and 7).

``run_walk_forward`` is a dependency-free backtester over aligned bar
series: weights come from train bars only (no lookahead), the shared
``CostModel`` is charged on one-way turnover at each rebalance, and the
report metrics are aggregated over the disjoint test segments. The
orchestrating ``run_baseline_report`` pins everything through the lake's
manifest gate, writes deterministic artifacts, and records the report.
"""

import csv
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.research.reports import (
    MODEL_STRATEGIES,
    CostModel,
    Parameter,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    WindowResult,
    artifact_paths,
    current_commit,
    report_id,
)

_BARS_PER_YEAR = 252.0
_SECONDS_PER_DAY = 86400.0


def momentum_weights(train_returns: dict[str, float]) -> dict[str, float]:
    """Long-only, equal weight on the top half of the universe by return."""
    ranked = sorted(train_returns, key=lambda symbol: (train_returns[symbol], symbol))
    top = ranked[len(ranked) // 2 :]
    weight = 1.0 / len(top)
    return {symbol: (weight if symbol in top else 0.0) for symbol in ranked}


def mean_reversion_weights(train_returns: dict[str, float]) -> dict[str, float]:
    """Long-only, equal weight on the bottom half of the universe by return."""
    ranked = sorted(train_returns, key=lambda symbol: (train_returns[symbol], symbol))
    bottom = ranked[: len(ranked) // 2 + len(ranked) % 2]
    weight = 1.0 / len(bottom)
    return {symbol: (weight if symbol in bottom else 0.0) for symbol in ranked}


def risk_parity_weights(
    train_returns: dict[str, float], train_vols: dict[str, float]
) -> dict[str, float]:
    """Inverse-volatility weights; zero-volatility symbols are excluded.

    Fails closed when every symbol has zero train volatility — inverse
    risk is then undefined, and a weight vector would be fabricated.
    """
    inverse = {
        symbol: 1.0 / train_vols[symbol]
        for symbol in train_returns
        if train_vols[symbol] > 0
    }
    if not inverse:
        raise ValueError("every symbol has zero train volatility; risk-parity is undefined")
    total = sum(inverse.values())
    return {symbol: inverse.get(symbol, 0.0) / total for symbol in train_returns}


def low_volatility_weights(train_vols: dict[str, float]) -> dict[str, float]:
    """Long-only, equal weight on the bottom half of the universe by
    train-window realized volatility (issue #32, Phase D).

    The M5 volatility baseline: hold the quietest names. Unlike
    risk-parity the weights are rank-based and long-only, and
    zero-volatility symbols are the signal, not an undefined input.
    """
    ranked = sorted(train_vols, key=lambda symbol: (train_vols[symbol], symbol))
    bottom = ranked[: len(ranked) // 2 + len(ranked) % 2]
    weight = 1.0 / len(bottom)
    return {symbol: (weight if symbol in bottom else 0.0) for symbol in ranked}


def signal_top_half_weights(train_signals: dict[str, float]) -> dict[str, float]:
    """Long-only, equal weight on the top half of the universe by a
    train-window mean signal (issues #32 Phase D, #40 Phase B).

    The shared rank rule for signal-driven strategies: sort by the
    signal (symbol name as the tiebreaker), hold the top half equal
    weight, and pay the rest zero. Identical code used to live inside
    ``book_imbalance_weights``; the M7 pipelines weight by their mean
    train-window prediction under the same rule.
    """
    ranked = sorted(train_signals, key=lambda symbol: (train_signals[symbol], symbol))
    top = ranked[len(ranked) // 2 :]
    weight = 1.0 / len(top)
    return {symbol: (weight if symbol in top else 0.0) for symbol in ranked}


def book_imbalance_weights(train_signals: dict[str, float]) -> dict[str, float]:
    """Long-only, equal weight on the top half of the universe by
    train-window mean order-book imbalance (issue #32, Phase D).

    The M5 imbalance baseline: hold the names whose depth is most
    buy-side pressured. The signal values are the per-bar mean imbalance
    series from ``quantmesh.hyperliquid.signal``; weights are rank-based
    like momentum, but over the signal, not the return.
    """
    return signal_top_half_weights(train_signals)


@dataclass(frozen=True)
class BacktestResult:
    """Outputs of ``run_walk_forward``, fed into a ``StrategyReport``."""

    metrics: dict[str, Parameter]
    windows: list[WindowResult]
    equity_curve: list[tuple[datetime, float, int]]
    trades: list[tuple[datetime, str, float, float, float]]


def run_walk_forward(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    strategy: str,
    window_spec: WalkForwardSpec,
    costs: CostModel,
    signals_by_symbol: dict[str, list[float]] | None = None,
    window_signal_provider: Callable[[int, int], dict[str, float]] | None = None,
) -> BacktestResult:
    """Backtest one strategy over aligned bar series, cost-aware.

    ``bars_by_symbol`` maps symbols to bars that share one timestamp
    grid; misaligned series fail closed rather than being silently
    shifted. Weights are computed from each window's train segment and
    held through the test segment (rebalanced once per window). The
    equity curve concatenates the disjoint test segments in order, so
    the report's aggregate metrics cover every evaluation day exactly
    once (ADR-0005 decision 3).

    ``signals_by_symbol`` carries one canonical signal value per bar,
    aligned 1:1 with the bars (issue #32, Phase D: the per-bar mean
    order-book imbalance series). The ``book_imbalance`` strategy
    requires it and weights by each train window's mean signal; the
    other strategies ignore it. A signal series that does not match the
    bar grid (length or symbol set) fails closed — a shifted signal
    would silently backtest a different hypothesis.

    ``window_signal_provider`` (issue #40, Phase B) is how the M7
    pipeline strategies backtest: called per window with the grid
    positions ``(train_start, test_start)``, it must fit the pipeline on
    the train segment only and return one mean train-window signal per
    symbol, from which the weights follow by the shared top-half rule
    (``signal_top_half_weights``). The train slice covers bars
    ``[train_start, test_start - 1]``, so the pipeline never sees a test
    bar. A pipeline strategy without a provider fails closed — a weight
    vector would otherwise be fabricated.
    """
    grid = _aligned_grid(bars_by_symbol)
    if signals_by_symbol is not None:
        _validate_signals(signals_by_symbol, bars_by_symbol)
    closes = {symbol: [bar.close for bar in bars] for symbol, bars in bars_by_symbol.items()}
    returns = {symbol: _daily_returns(closes[symbol]) for symbol in closes}
    rate = costs.rate()

    windows: list[WindowResult] = []
    equity: list[tuple[datetime, float, int]] = []
    trades: list[tuple[datetime, str, float, float, float]] = []
    previous: dict[str, float] = {}
    cumulative = 1.0
    daily_returns: list[float] = []

    for index, test_start in enumerate(window_spec.test_starts(len(grid))):
        train_start = test_start - window_spec.train_bars
        window_returns = {
            symbol: closes[symbol][test_start - 1] / closes[symbol][train_start] - 1.0
            for symbol in closes
        }
        window_vols = {
            symbol: _population_std(returns[symbol][train_start + 1 : test_start])
            for symbol in returns
        }
        if strategy == "momentum":
            weights = momentum_weights(window_returns)
        elif strategy == "mean_reversion":
            weights = mean_reversion_weights(window_returns)
        elif strategy == "risk_parity":
            weights = risk_parity_weights(window_returns, window_vols)
        elif strategy == "low_volatility":
            weights = low_volatility_weights(window_vols)
        elif strategy == "book_imbalance":
            if signals_by_symbol is None:
                raise ValueError(
                    "strategy 'book_imbalance' needs signals_by_symbol; a "
                    "weight vector without the signal series would be fabricated"
                )
            weights = book_imbalance_weights(
                {
                    symbol: _mean(signals_by_symbol[symbol][train_start:test_start])
                    for symbol in signals_by_symbol
                }
            )
        elif strategy in MODEL_STRATEGIES:
            if window_signal_provider is None:
                raise ValueError(
                    f"strategy {strategy!r} needs a window_signal_provider; a "
                    "weight vector without a per-window model fit would be fabricated"
                )
            weights = signal_top_half_weights(window_signal_provider(train_start, test_start))
        else:
            raise ValueError(f"unknown strategy {strategy!r}")

        turnover = sum(
            abs(weights.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in weights
        )
        window_cost = rate * turnover
        n_trades = 0
        for symbol in weights:
            old = previous.get(symbol, 0.0)
            new = weights[symbol]
            if new != old:
                n_trades += 1
                trades.append(
                    (grid[test_start], symbol, old, new, rate * abs(new - old))
                )
        previous = dict(weights)

        window_daily: list[float] = []
        for day, timestamp in enumerate(grid[test_start : test_start + window_spec.test_bars]):
            day_return = sum(
                weights[symbol] * returns[symbol][test_start + day] for symbol in weights
            )
            if day == 0:
                day_return -= window_cost  # cost is charged once, at the rebalance
            window_daily.append(day_return)
            daily_returns.append(day_return)
            cumulative *= 1.0 + day_return
            equity.append((timestamp, cumulative, index))

        windows.append(
            WindowResult(
                index=index,
                train_end=grid[test_start - 1],
                test_start=grid[test_start],
                test_end=grid[test_start + window_spec.test_bars - 1],
                window_return=math.prod(1.0 + value for value in window_daily) - 1.0,
                turnover=turnover,
                cost=window_cost,
                n_trades=n_trades,
            )
        )

    metrics = _aggregate_metrics(daily_returns, windows, interval_of(bars_by_symbol))
    return BacktestResult(metrics=metrics, windows=windows, equity_curve=equity, trades=trades)


def interval_of(bars_by_symbol: dict[str, list[Bar]]) -> str:
    intervals = {bar.interval for bars in bars_by_symbol.values() for bar in bars}
    if len(intervals) != 1:
        raise ValueError(f"bars carry mixed intervals {sorted(intervals)}")
    return intervals.pop()


def run_baseline_report(
    *,
    dataset: str,
    revision: int,
    strategy: str,
    interval: str,
    universe: list[UniverseMember],
    window_spec: WalkForwardSpec,
    costs: CostModel,
    signals_by_symbol: dict[str, list[float]] | None = None,
    commit: str | None = None,
    registry: ReportRegistry | None = None,
) -> StrategyReport:
    """Produce, persist, and record one baseline report (ADR-0005).

    The pin is validated through the lake's manifest gate before any
    computation; bars are read per universe member (empty series fail
    closed); the report ID is the hash of the setup; artifacts are
    written byte-stable under ``reports_root/<id>/`` and the record is
    appended to the registry. ``commit`` defaults to the current git
    HEAD.

    ``signals_by_symbol`` (issue #32, Phase D) carries the canonical
    per-bar signal series for signal-driven strategies; its digest
    folds into the report id so the identity covers the signal inputs.
    """
    registry = registry if registry is not None else ReportRegistry()
    if commit is None:
        commit = current_commit()
    members = validate_universe(universe)
    dataset_handle = registry.resolve_pin(dataset, revision)
    bars_by_symbol: dict[str, list[Bar]] = {}
    for member in members:
        bars = dataset_handle.read_bars(
            interval=interval, venue=member.venue, symbol=member.symbol
        )
        if not bars:
            raise ValueError(
                f"universe member {member.venue.value}.{member.symbol} has no "
                f"{interval} bars in dataset {dataset!r}"
            )
        bars_by_symbol[member.symbol] = bars

    signals_digest = (
        _signals_digest(signals_by_symbol) if signals_by_symbol is not None else None
    )
    result = run_walk_forward(
        bars_by_symbol,
        strategy=strategy,
        window_spec=window_spec,
        costs=costs,
        signals_by_symbol=signals_by_symbol,
    )
    report = StrategyReport(
        id=report_id(
            dataset=dataset,
            revision=revision,
            commit=commit,
            strategy=strategy,
            interval=interval,
            universe=members,
            window_spec=window_spec,
            costs=costs,
            signals_digest=signals_digest,
        ),
        dataset=dataset,
        revision=revision,
        commit=commit,
        strategy=strategy,
        interval=interval,
        universe=members,
        window_spec=window_spec,
        costs=costs,
        signals_digest=signals_digest,
        created_at=datetime.now(UTC),
        metrics=result.metrics,
        windows=result.windows,
    )
    write_artifacts(registry.root, report, result)
    registry.record(report)
    return report


def validate_universe(universe: list[UniverseMember]) -> list[UniverseMember]:
    """Universe rules shared with the baseline and pipeline harnesses."""
    if not universe:
        raise ValueError("universe must not be empty")
    seen: set[tuple[str, str]] = set()
    for member in universe:
        key = (member.venue.value, member.symbol)
        if key in seen:
            raise ValueError(f"universe lists {key} more than once")
        seen.add(key)
    symbols = {member.symbol for member in universe}
    if len(symbols) != len(universe):
        raise ValueError(
            "universe lists a symbol on more than one venue; the backtester "
            "keys bars by symbol and would silently overwrite one venue's bars"
        )
    return universe


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot mean an empty signal segment; the window is empty")
    return sum(values) / len(values)


def _validate_signals(
    signals_by_symbol: dict[str, list[float]],
    bars_by_symbol: dict[str, list[Bar]],
) -> None:
    """A signal series must cover exactly the bar grid (issue #32, Phase D)."""
    if set(signals_by_symbol) != set(bars_by_symbol):
        raise ValueError(
            "signal series and bar series disagree on the universe: "
            f"{sorted(signals_by_symbol)} != {sorted(bars_by_symbol)}"
        )
    for symbol, signals in signals_by_symbol.items():
        if len(signals) != len(bars_by_symbol[symbol]):
            raise ValueError(
                f"signal series for {symbol!r} has {len(signals)} values but the "
                f"bar series has {len(bars_by_symbol[symbol])}; a shifted signal "
                "would silently backtest a different hypothesis"
            )


def _signals_digest(signals_by_symbol: dict[str, list[float]]) -> str:
    """Deterministic digest of the signal inputs, folded into the report id.

    The id stays a setup-only hash (ADR-0005 decision 2): the signal
    series are inputs, not results, so the digest covers them.
    """
    canonical = json.dumps(
        {symbol: values for symbol, values in sorted(signals_by_symbol.items())},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"baseline-signals\0{canonical}".encode()).hexdigest()[:16]


def _aligned_grid(bars_by_symbol: dict[str, list[Bar]]) -> list[datetime]:
    if not bars_by_symbol:
        raise ValueError("no bar series to backtest")
    lengths = {len(bars) for bars in bars_by_symbol.values()}
    if len(lengths) != 1:
        raise ValueError(f"bar series differ in length {sorted(lengths)}; align them first")
    grid = [bar.timestamp for bar in next(iter(bars_by_symbol.values()))]
    for symbol, bars in bars_by_symbol.items():
        for index, bar in enumerate(bars):
            if bar.timestamp != grid[index]:
                raise ValueError(
                    f"series {symbol!r} is misaligned at position {index}: "
                    f"{bar.timestamp} != {grid[index]}"
                )
    return grid


def _daily_returns(closes: list[float]) -> list[float]:
    """Close-to-close simple returns; position 0 is a 0.0 placeholder."""
    return [0.0] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


def _population_std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _aggregate_metrics(
    daily_returns: list[float],
    windows: list[WindowResult],
    interval: str,
) -> dict[str, Parameter]:
    total = math.prod(1.0 + value for value in daily_returns) - 1.0
    seconds_per_bar = interval_to_timedelta(interval).total_seconds()
    bars_per_year = _BARS_PER_YEAR * (_SECONDS_PER_DAY / seconds_per_bar)
    if len(daily_returns) and (1.0 + total) > 0.0:
        annualized = (1.0 + total) ** (bars_per_year / len(daily_returns)) - 1.0
    else:
        annualized = None  # a collapse is reported through total_return, not logarithms
    mean = sum(daily_returns) / len(daily_returns)
    std = _population_std(daily_returns)
    sharpe = mean / std * math.sqrt(bars_per_year) if std > 0 else None
    return {
        "total_return": total,
        "annualized_return": annualized,
        "sharpe": sharpe,
        "max_drawdown": _max_drawdown(daily_returns),
        "win_rate": sum(1 for window in windows if window.window_return > 0) / len(windows),
        "n_windows": len(windows),
        "avg_turnover": sum(window.turnover for window in windows) / len(windows),
        "total_cost": sum(window.cost for window in windows),
    }


def _max_drawdown(daily_returns: list[float]) -> float:
    peak = 1.0
    equity = 1.0
    worst = 0.0
    for value in daily_returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def write_artifacts(root: Path, report: StrategyReport, result: BacktestResult) -> None:
    """Write the report's artifacts byte-stable (ADR-0005 decision 7).

    Public since issue #40 (Phase B): ``run_pipeline_report`` records
    pipeline reports through the same artifact writer.

    ``report.json`` excludes ``created_at`` — bookkeeping, not setup or
    results — so regenerating a report produces identical bytes.
    """
    paths = artifact_paths(root, report)
    directory = paths["report.json"].parent
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        paths["report.json"],
        # mode="json" turns datetimes into ISO strings; created_at is
        # bookkeeping, not setup or results, so it never reaches the file.
        json.dumps(
            report.model_dump(mode="json", exclude={"created_at"}), indent=2, sort_keys=True
        ),
    )
    rows = [
        [timestamp.isoformat(), f"{equity:.10f}", index]
        for timestamp, equity, index in result.equity_curve
    ]
    _atomic_csv(paths["equity_curve.csv"], ["timestamp", "equity", "window_index"], rows)
    rows = [
        [timestamp.isoformat(), symbol, f"{before:.6f}", f"{after:.6f}", f"{cost:.8f}"]
        for timestamp, symbol, before, after, cost in result.trades
    ]
    _atomic_csv(
        paths["trades.csv"],
        ["timestamp", "symbol", "weight_before", "weight_after", "cost"],
        rows,
    )


def _atomic_text(path: Path, text: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".artifact.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _atomic_csv(path: Path, header: list[str], rows: list[list]) -> None:
    """Write a CSV atomically; the handle is closed before the replace,
    which Windows requires for a file-in-place rename."""
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".artifact.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
