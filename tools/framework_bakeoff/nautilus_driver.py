"""Offline child-process driver for the pinned NautilusTrader bake-off.

Copyright (C) 2026 QuantMesh contributors.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _same_number(left: object, right: object) -> bool:
    if not isinstance(left, (int, float)) or isinstance(left, bool):
        return False
    if not isinstance(right, (int, float)) or isinstance(right, bool):
        return False
    return abs(float(left) - float(right)) <= 1e-9


def run(input_path: Path, config_path: Path, output_root: Path) -> None:
    """Replay local bars through the pinned low-level engine and compare facts."""
    import pandas as pd
    from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
    from nautilus_trader.backtest.config import BacktestEngineConfig
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import LoggingConfig
    from nautilus_trader.data.config import DataEngineConfig
    from nautilus_trader.model.currencies import BTC, USDC
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
    from nautilus_trader.model.identifiers import (
        ClientOrderId,
        InstrumentId,
        Symbol,
        TraderId,
        Venue,
    )
    from nautilus_trader.model.instruments import CryptoPerpetual
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.persistence.wranglers import BarDataWrangler
    from nautilus_trader.trading.strategy import Strategy

    rows = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
    ]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if len(rows) != 6 or config.get("paper") is not True:
        raise ValueError("driver requires the bounded six-row paper fixture")
    if [row.get("replay_ordinal") for row in rows] != list(range(6)):
        raise ValueError("driver input replay ordinals are not canonical file order")
    if any(
        row.get("venue") != "hyperliquid"
        or row.get("symbol") != "BTC"
        or row.get("interval") != "1m"
        or row.get("sequence_source") != "quantmesh-fixture-order"
        or "sequence" in row
        for row in rows
    ):
        raise ValueError("driver input provenance does not match Hyperliquid BTC 1m")

    intent = config["order_intent"]
    expected = config["quantmesh_expected"]
    venue = Venue("HYPERLIQUID")
    instrument_id = InstrumentId(Symbol("BTC-USD-PERP"), venue)
    instrument = CryptoPerpetual(
        instrument_id=instrument_id,
        raw_symbol=Symbol("BTC"),
        base_currency=BTC,
        quote_currency=USDC,
        settlement_currency=USDC,
        is_inverse=False,
        price_precision=1,
        size_precision=5,
        price_increment=Price.from_str("0.1"),
        size_increment=Quantity.from_str("0.00001"),
        max_quantity=None,
        min_quantity=None,
        max_notional=None,
        min_notional=None,
        max_price=None,
        min_price=None,
        margin_init=Decimal("0.05"),
        margin_maint=Decimal("0.025"),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )
    bar_type = BarType.from_str(
        "BTC-USD-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL"
    )
    frame = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=1),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in rows
        ]
    ).set_index("timestamp")
    bars: list[Bar] = BarDataWrangler(bar_type, instrument).process(frame)

    class BoundedLimitBuy(Strategy):
        def __init__(self) -> None:
            super().__init__()
            self.replay_ordinal = -1
            self.submitted = False
            self.transitions: list[str] = []
            self.native_order_id: str | None = None
            self.native_venue_order_id: str | None = None
            self.native_trade_id: str | None = None
            self.fill_price: float | None = None
            self.fill_quantity: float | None = None

        def on_start(self) -> None:
            self.subscribe_bars(bar_type)

        def on_bar(self, _bar: Bar) -> None:
            self.replay_ordinal += 1
            if not self.submitted and self.replay_ordinal == int(
                intent["submit_after_replay_ordinal"]
            ):
                order = self.order_factory.limit(
                    instrument_id=instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=instrument.make_qty(float(intent["quantity"])),
                    price=instrument.make_price(float(intent["limit_price"])),
                    client_order_id=ClientOrderId(str(intent["order_id"])),
                )
                self.transitions.append("submitted")
                self.native_order_id = str(order.client_order_id)
                self.submit_order(order)
                self.submitted = True

        def on_order_accepted(self, event: object) -> None:
            self.transitions.append("accepted")
            self.native_venue_order_id = str(event.venue_order_id)

        def on_order_filled(self, event: object) -> None:
            self.transitions.append("filled")
            self.native_trade_id = str(event.trade_id)
            self.fill_price = event.last_px.as_double()
            self.fill_quantity = event.last_qty.as_double()

    engine = BacktestEngine(
        BacktestEngineConfig(
            trader_id=TraderId("QM-BACKTEST-001"),
            data_engine=DataEngineConfig(validate_data_sequence=True),
            logging=LoggingConfig(log_level="ERROR", log_colors=False),
        )
    )
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(float(expected["starting_cash"]), USDC)],
        base_currency=USDC,
        default_leverage=Decimal(1),
        use_random_ids=False,
        use_reduce_only=True,
        bar_execution=True,
        trade_execution=True,
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)
    strategy = BoundedLimitBuy()
    engine.add_strategy(strategy)
    engine.run()

    account = engine.cache.account_for_venue(venue)
    if account is None:
        raise RuntimeError("Nautilus backtest did not create a HYPERLIQUID account")
    cash = account.balance_total(USDC).as_double()
    positions = engine.cache.positions_open(instrument_id=instrument_id)
    position_quantity = positions[0].quantity.as_double() if positions else 0.0
    backtest = {
        "account_delta": cash - float(expected["starting_cash"]),
        "cash": cash,
        "fill_price": strategy.fill_price,
        "fill_quantity": strategy.fill_quantity,
        "native_order_id": strategy.native_order_id,
        "native_trade_id": strategy.native_trade_id,
        "native_venue_order_id": strategy.native_venue_order_id,
        "order_id": intent["order_id"],
        "position_quantity": position_quantity,
        "status_transitions": strategy.transitions,
    }

    sandbox_config = SandboxExecutionClientConfig(
        venue="HYPERLIQUID",
        starting_balances=[f"{expected['starting_cash']} USDC"],
        base_currency="USDC",
        oms_type="NETTING",
        account_type="MARGIN",
        bar_execution=True,
        trade_execution=True,
        use_random_ids=False,
        use_reduce_only=True,
    )
    sandbox_limitation = (
        "NautilusTrader 1.231.0 SandboxExecutionClientConfig is a live TradingNode "
        "execution-client configuration and exposes no standalone offline recorded-bar "
        "run method; executing it requires a live-node data client, which this "
        "credential-free comparator does not fabricate"
    )
    sandbox = {
        "account_delta": None,
        "cash": None,
        "config": {
            "account_type": sandbox_config.account_type,
            "bar_execution": sandbox_config.bar_execution,
            "oms_type": sandbox_config.oms_type,
            "trade_execution": sandbox_config.trade_execution,
            "use_random_ids": sandbox_config.use_random_ids,
            "use_reduce_only": sandbox_config.use_reduce_only,
            "venue": sandbox_config.venue,
        },
        "fill_price": None,
        "fill_quantity": None,
        "limitation": sandbox_limitation,
        "order_id": intent["order_id"],
        "position_quantity": None,
        "status_transitions": ["configuration_validated"],
        "supported": False,
    }
    quantmesh = {
        key: expected[key]
        for key in (
            "account_delta",
            "cash",
            "fill_price",
            "fill_quantity",
            "order_id",
            "position_quantity",
            "status_transitions",
        )
    }
    mismatches = []
    for key in (
        "account_delta",
        "cash",
        "fill_price",
        "fill_quantity",
        "position_quantity",
    ):
        if not _same_number(backtest.get(key), quantmesh.get(key)):
            mismatches.append(
                f"backtest {key} {backtest.get(key)!r} != quantmesh {quantmesh.get(key)!r}"
            )
    if backtest["status_transitions"] != quantmesh["status_transitions"]:
        mismatches.append(
            "backtest status_transitions "
            f"{backtest['status_transitions']!r} != quantmesh "
            f"{quantmesh['status_transitions']!r}"
        )
    mismatches.append(sandbox_limitation)

    source = {
        "fixture": "src/quantmesh/hyperliquid/fixtures/wire_candles.json",
        "sequence_source": "quantmesh-fixture-order",
    }
    events = []
    event_ordinals = {"submitted": 0, "accepted": 0, "filled": 1}
    for index, status in enumerate(strategy.transitions, 1):
        row = {
            "event_id": f"backtest-event-{index:03d}",
            "mode": "backtest",
            "order_id": intent["order_id"],
            "paper": True,
            "replay_ordinal": event_ordinals.get(status, strategy.replay_ordinal),
            "source": source,
            "status": status,
            "venue": "hyperliquid",
        }
        if status == "filled":
            row["fill_id"] = intent["fill_id"]
        events.append(row)
    fills = []
    if strategy.fill_price is not None and strategy.fill_quantity is not None:
        fills.append(
            {
                "fill_id": intent["fill_id"],
                "mode": "backtest",
                "native_trade_id": strategy.native_trade_id,
                "order_id": intent["order_id"],
                "paper": True,
                "price": strategy.fill_price,
                "quantity": strategy.fill_quantity,
                "replay_ordinal": 1,
                "source": source,
                "venue": "hyperliquid",
            }
        )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "events.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in events
        ),
        encoding="utf-8",
    )
    _write_json(output_root / "fills.json", fills)
    _write_json(
        output_root / "account.json",
        {
            "comparison": {"mismatches": mismatches},
            "nautilus_backtest": backtest,
            "nautilus_sandbox": sandbox,
            "paper": True,
            "quantmesh": quantmesh,
            "source": source,
            "starting_cash": expected["starting_cash"],
            "venue": "hyperliquid",
        },
    )
    engine.dispose()


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
