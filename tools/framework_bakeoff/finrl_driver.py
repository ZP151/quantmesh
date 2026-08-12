"""Offline child-process driver for the pinned FinRL-X NVDA bake-off."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import types
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _block_upstream_provider_import() -> None:
    provider_stub = types.ModuleType("src.data.data_fetcher")

    def forbidden_provider(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("market-data providers are forbidden in the isolated bake-off")

    provider_stub.fetch_price_data = forbidden_provider  # type: ignore[attr-defined]
    sys.modules[provider_stub.__name__] = provider_stub


def run(input_path: Path, config_path: Path, output_root: Path) -> None:
    """Run the pinned engine on exported local bytes and write canonical outputs."""
    import numpy as np
    import pandas as pd

    _block_upstream_provider_import()
    from src.backtest.backtest_engine import BacktestConfig, BacktestEngine
    from src.strategies.base_strategy import BaseStrategy, StrategyConfig, StrategyResult

    class NvdaTimingStrategy(BaseStrategy):
        def generate_weights(
            self, data: dict[str, pd.DataFrame], target_date: str | None = None
        ) -> StrategyResult:
            del target_date
            close = data["prices"]["NVDA"]
            fast = close.rolling(20).mean()
            slow = close.rolling(60).mean()
            weights = (fast > slow).astype(float).to_frame("NVDA")
            return StrategyResult("nvda_timing", weights.fillna(0.0))

    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config != {
        "costs_bps": {"fee": 10, "half_spread": 5, "slippage": 2},
        "seed": 20260811,
        "splits": {
            "test": [315, 420],
            "train": [0, 252],
            "validation": [252, 315],
        },
        "symbol": "NVDA",
    }:
        raise ValueError("driver configuration does not match the pinned Task 2 contract")

    np.random.seed(config["seed"])
    frame = pd.read_csv(input_path)
    expected_columns = [
        "date",
        "datadate",
        "tic",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "cshtrd",
    ]
    if frame.columns.tolist() != expected_columns or len(frame) != 420:
        raise ValueError("input.csv does not match the canonical 420-row export")
    if frame["tic"].tolist() != ["NVDA"] * 420:
        raise ValueError("input.csv contains a symbol outside the NVDA fixture")

    fit_end = config["splits"]["validation"][1]
    test_start, test_end = config["splits"]["test"]
    fit = frame.iloc[:fit_end].copy()
    evaluation = frame.iloc[test_start:test_end].copy()
    fit_prices = fit.pivot(index="datadate", columns="tic", values="adj_close")
    fit_prices.index = pd.to_datetime(fit_prices.index)
    strategy = NvdaTimingStrategy(StrategyConfig(name="nvda_timing"))
    generated = strategy.generate_weights({"prices": fit_prices})
    target_weight = float(generated.weights.iloc[-1]["NVDA"])

    evaluation_dates = pd.to_datetime(evaluation["datadate"])
    weights = pd.DataFrame({"NVDA": target_weight}, index=evaluation_dates)
    prices = evaluation.copy()
    prices["datadate"] = pd.to_datetime(prices["datadate"])
    transaction_cost = sum(config["costs_bps"].values()) / 10_000
    backtest_config = BacktestConfig(
        start_date=str(evaluation_dates.min().date()),
        end_date=str(evaluation_dates.max().date()),
        transaction_cost=transaction_cost,
        benchmark_tickers=[],
        integer_positions=False,
    )
    result = BacktestEngine(backtest_config).run_backtest(
        "nvda_timing", prices, weights
    )

    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "weights.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date", "NVDA"])
        writer.writerows(
            (date.strftime("%Y-%m-%d"), format(target_weight, ".1f"))
            for date in evaluation_dates
        )
    _write_json(
        output_root / "backtest.json",
        {
            "costs": {
                "fee_bps": 10,
                "half_spread_bps": 5,
                "slippage_bps": 2,
                "transaction_cost": transaction_cost,
            },
            "evaluation": {
                "end_date": str(evaluation_dates.max().date()),
                "end_index_exclusive": test_end,
                "start_date": str(evaluation_dates.min().date()),
                "start_index": test_start,
            },
            "fit": {
                "end_date": str(pd.to_datetime(fit.iloc[-1]["datadate"]).date()),
                "end_index_exclusive": fit_end,
                "start_date": str(pd.to_datetime(fit.iloc[0]["datadate"]).date()),
                "start_index": 0,
            },
            "strategy": "nvda_timing",
            "upstream_result": _json_value(result.metrics),
        },
    )
    _write_json(
        output_root / "proposal.json",
        {
            "paper": True,
            "symbol": "NVDA",
            "target_weight": target_weight,
            "venue": "moomoo",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    run(args.input, args.config, args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
