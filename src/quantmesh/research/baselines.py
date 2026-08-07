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
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.research.reports import (
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
) -> BacktestResult:
    """Backtest one strategy over aligned bar series, cost-aware.

    ``bars_by_symbol`` maps symbols to bars that share one timestamp
    grid; misaligned series fail closed rather than being silently
    shifted. Weights are computed from each window's train segment and
    held through the test segment (rebalanced once per window). The
    equity curve concatenates the disjoint test segments in order, so
    the report's aggregate metrics cover every evaluation day exactly
    once (ADR-0005 decision 3).
    """
    grid = _aligned_grid(bars_by_symbol)
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
    """
    registry = registry if registry is not None else ReportRegistry()
    if commit is None:
        commit = current_commit()
    members = _validate_universe(universe)
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

    result = run_walk_forward(
        bars_by_symbol, strategy=strategy, window_spec=window_spec, costs=costs
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
        ),
        dataset=dataset,
        revision=revision,
        commit=commit,
        strategy=strategy,
        interval=interval,
        universe=members,
        window_spec=window_spec,
        costs=costs,
        created_at=datetime.now(UTC),
        metrics=result.metrics,
        windows=result.windows,
    )
    _write_artifacts(registry.root, report, result)
    registry.record(report)
    return report


def _validate_universe(universe: list[UniverseMember]) -> list[UniverseMember]:
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


def _write_artifacts(root: Path, report: StrategyReport, result: BacktestResult) -> None:
    """Write the report's artifacts byte-stable (ADR-0005 decision 7).

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
