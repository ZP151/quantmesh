"""Standalone fixed runner, executed only inside the external vn.py environment.

Upstream engine/strategies remain installed MIT packages, never copied here.
"""

import csv
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import math
import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo


def main():
    if sys.stdin.readline() != "go\n":
        raise ValueError("ownership gate")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Python 3.12 required")
    root = Path(sys.argv[1]).resolve()
    # Upstream catches strategy callback errors and prints them to stdout.
    # Retain that diagnostic stream in the owned attempt, never send it to APIs.
    sys.stdout = (root / "engine.log").open("w", encoding="utf-8", buffering=1)
    payload = json.loads((root / "input.json").read_bytes())
    identity, request = payload["identity"], payload["request"]
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != identity["runner_sha256"]:
        raise ValueError("runner source drift")
    fixture = Path(payload["fixture"])
    if hashlib.sha256(fixture.read_bytes()).hexdigest() != identity["fixture_sha256"]:
        raise ValueError("fixture drift")
    for name, version in identity["versions"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError("runtime drift")
    (root / ".vntrader").mkdir()
    (root / ".vntrader/vt_setting.json").write_text(
        json.dumps(
            {
                "database.name": "sqlite",
                "database.database": "fixture.db",
                "log.file": False,
            }
        )
    )
    os.chdir(root)
    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.database import DB_TZ, get_database
    from vnpy.trader.object import BarData
    from vnpy_ctastrategy.backtesting import BacktestingEngine

    modules = {"DoubleMaStrategy": "double_ma_strategy", "AtrRsiStrategy": "atr_rsi_strategy"}
    strategy = getattr(
        importlib.import_module(f"vnpy_ctastrategy.strategies.{modules[request['strategy_id']]}"),
        request["strategy_id"],
    )
    for cls, expected in [
        (BacktestingEngine, identity["engine_sha256"]),
        (strategy, identity["strategy_sources"][request["strategy_id"]]),
    ]:
        if hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest() != expected:
            raise ValueError("upstream source drift")

    def progress(stage, completed=0):
        temp = root / "progress.tmp"
        temp.write_text(json.dumps({"stage": stage, "completed_bars": completed}))
        try:
            temp.replace(root / "progress.json")
        except PermissionError:
            # Windows readers can briefly prevent replacement. Progress is
            # observational and must never interrupt native strategy callbacks.
            pass

    progress("loading_data")
    with fixture.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    bars = [
        BarData(
            symbol="SPY",
            exchange=Exchange.SMART,
            datetime=datetime.fromisoformat(row["timestamp"]),
            interval=Interval.MINUTE,
            volume=float(row["volume"]),
            open_price=float(row["open"]),
            high_price=float(row["high"]),
            low_price=float(row["low"]),
            close_price=float(row["close"]),
            gateway_name="SYNTHETIC_FIXTURE",
        )
        for row in rows
    ]
    database = get_database()
    try:
        if not database.save_bar_data(bars):
            raise ValueError("fixture save failed")
        native_loader = database.load_bar_data

        def exchange_loader(symbol, exchange, interval, start, end):
            # Official SQLite adapter stores host-local naive timestamps. Normalize
            # query bounds and returned bars at this adapter boundary only.
            result = native_loader(
                symbol,
                exchange,
                interval,
                start.astimezone(DB_TZ).replace(tzinfo=None),
                end.astimezone(DB_TZ).replace(tzinfo=None),
            )
            for bar in result:
                bar.datetime = bar.datetime.astimezone(ZoneInfo("America/New_York"))
            return result

        database.load_bar_data = exchange_loader
        engine = BacktestingEngine()
        costs = request["costs"]
        engine.set_parameters(
            vt_symbol="SPY.SMART",
            interval=Interval.MINUTE,
            start=datetime.fromisoformat("2013-10-07T00:00:00-04:00"),
            end=datetime.fromisoformat("2013-10-11T23:59:59-04:00"),
            rate=costs["fee_bps"] / 10000,
            slippage=costs["half_spread_price"] + costs["slippage_price"],
            size=1,
            pricetick=0.01,
            capital=100000,
            annual_days=252,
        )
        engine.add_strategy(strategy, request["parameters"])
        lifecycle = {"warmup_bars": 0, "replay_bars": 0}
        for name in ("on_init", "on_start", "on_stop", "on_bar", "on_order", "on_trade"):
            original = getattr(engine.strategy, name)

            def traced(*args, _name=name, _original=original):
                lifecycle[_name] = lifecycle.get(_name, 0) + 1
                if _name == "on_bar":
                    bucket = "replay_bars" if engine.strategy.trading else "warmup_bars"
                    lifecycle[bucket] += 1
                    if bucket == "replay_bars" and lifecycle[bucket] % 100 == 0:
                        progress("replaying", lifecycle[bucket])
                elif _name == "on_init":
                    progress("warmup")
                return _original(*args)

            setattr(engine.strategy, name, traced)
        engine.load_data()
        expected = [row for row in rows if row["timestamp"][:10] >= "2013-10-07"]
        if len(engine.history_data) != 1950 or len(expected) != 1950:
            raise ValueError("replay count mismatch")
        for bar, row in zip(engine.history_data, expected, strict=True):
            actual = [bar.open_price, bar.high_price, bar.low_price, bar.close_price, bar.volume]
            if bar.datetime.isoformat() != row["timestamp"] or actual != [
                float(row[key]) for key in ("open", "high", "low", "close", "volume")
            ]:
                raise ValueError("fixture roundtrip mismatch")
        engine.run_backtesting()
        if lifecycle["replay_bars"] != 1950 or lifecycle.get("on_stop") != 1:
            raise ValueError("native replay did not complete")
        progress("reporting", lifecycle["replay_bars"])
        daily = engine.calculate_result()
        statistics = engine.calculate_statistics()

        def clean(value):
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, dict):
                return {str(key): clean(item) for key, item in value.items()}
            if isinstance(value, list):
                return [clean(item) for item in value]
            if hasattr(value, "isoformat"):
                return value.isoformat()
            if hasattr(value, "item"):
                return clean(value.item())
            if isinstance(value, float) and not math.isfinite(value):
                return None
            return value

        result = {
            "schema_version": 1,
            "request_digest": payload["request_digest"],
            "request": request,
            "identity": identity,
            "statistics": clean(statistics),
            "daily": clean(
                daily.drop(columns=["trades"], errors="ignore")
                .reset_index()
                .to_dict(orient="records")
            ),
            "trades": clean([vars(trade) for trade in engine.get_all_trades()]),
            "lifecycle": lifecycle,
            "semantics": "Native vn.py daily marking; synthetic workflow evidence only. "
            "Half spread and slippage are charged per unit per fill in native slippage. "
            "Null statistics are nonfinite or unavailable. Active jobs do not recover on restart.",
        }
        raw = json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        temp = root / "result.tmp"
        temp.write_bytes(raw)
        temp.replace(root / "result.json")
    finally:
        database.db.close()


if __name__ == "__main__":
    main()
