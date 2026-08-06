"""Append-only SQLite event store for the paper-trading kernel.

The events table is the single source of truth: orders and the account
are rebuilt by replaying events through the pure order state machine and
fill application — never by trusting derived fields. A snapshot of the
recorded derived state is kept only for reconciliation, so any tampering
with or loss of events surfaces as a divergence instead of silent drift.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from quantmesh.domain.models import Instrument, Side
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderType,
)
from quantmesh.execution.accounting import (
    FeeModel,
    PaperAccount,
    RiskLimits,
)
from quantmesh.execution.matcher import PaperMatcher

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    global_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    quantity REAL,
    price REAL,
    reason TEXT,
    UNIQUE (order_id, event_sequence)
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    created_at TEXT NOT NULL,
    client_order_id TEXT
);
CREATE TABLE IF NOT EXISTS account_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    starting_cash REAL NOT NULL,
    fee_model TEXT NOT NULL,
    risk_limits TEXT NOT NULL,
    matcher TEXT NOT NULL,
    kill_switch INTEGER NOT NULL,
    order_sequence INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS account_snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL,
    total_fees REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    order_sequence INTEGER NOT NULL,
    positions TEXT NOT NULL,
    orders TEXT NOT NULL,
    config TEXT NOT NULL
);
"""


class StoreCorruptionError(ValueError):
    """The persisted event log cannot be replayed; the store is corrupted."""


class RestoreResult(BaseModel):
    """Rebuilt account plus reconciliation divergences against the snapshot."""

    account: PaperAccount
    divergences: list[str] = []


class EventStore:
    """Append-only event persistence with deterministic replay."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(self, account: PaperAccount) -> None:
        """Persist config, then append any missing events, then snapshot."""
        with self._conn:
            self._write_meta(account)
            for order in account.orders.values():
                self._write_order_header(order)
                self._append_events(order)
            self._write_snapshot(account)

    def restore(self) -> RestoreResult:
        """Rebuild the account from events and reconcile against the snapshot."""
        meta = self._load_meta()
        snapshot = self._load_snapshot()
        if meta is None or snapshot is None:
            raise ValueError(
                "no persisted account state to restore; call save() first"
            )
        account = PaperAccount(
            cash=meta["starting_cash"],
            starting_cash=meta["starting_cash"],
            fee_model=meta["fee_model"],
            risk_limits=meta["risk_limits"],
            matcher=meta["matcher"],
            kill_switch=meta["kill_switch"],
        )
        orders = self._rebuild_orders()
        orders_by_id = {order.order_id: order for order in orders}
        events = self._conn.execute(
            "SELECT * FROM events ORDER BY global_sequence"
        ).fetchall()
        for row in events:
            if row["event_type"] != OrderEventType.FILL.value:
                continue
            account = account.apply_fill(
                orders_by_id[row["order_id"]],
                Fill(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    quantity=row["quantity"],
                    price=row["price"],
                ),
            )
        account = account.model_copy(
            update={
                "orders": {order.order_id: order for order in orders},
                "order_sequence": meta["order_sequence"],
            }
        )
        return RestoreResult(
            account=account,
            divergences=self._reconcile(account, orders, snapshot),
        )

    def _write_meta(self, account: PaperAccount) -> None:
        self._conn.execute(
            """
            INSERT INTO account_meta (
                id, starting_cash, fee_model, risk_limits, matcher,
                kill_switch, order_sequence
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                starting_cash = excluded.starting_cash,
                fee_model = excluded.fee_model,
                risk_limits = excluded.risk_limits,
                matcher = excluded.matcher,
                kill_switch = excluded.kill_switch,
                order_sequence = excluded.order_sequence
            """,
            (
                (
                    account.starting_cash
                    if account.starting_cash is not None
                    else account.cash
                ),
                account.fee_model.model_dump_json(),
                account.risk_limits.model_dump_json(),
                account.matcher.model_dump_json(),
                int(account.kill_switch),
                account.order_sequence,
            ),
        )

    def _write_order_header(self, order: Order) -> None:
        self._conn.execute(
            """
            INSERT INTO orders (
                order_id, instrument, side, quantity, order_type,
                limit_price, created_at, client_order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (order_id) DO NOTHING
            """,
            (
                order.order_id,
                order.instrument.model_dump_json(),
                order.side.value,
                order.quantity,
                order.order_type.value,
                order.limit_price,
                order.created_at.isoformat(),
                order.client_order_id,
            ),
        )

    def _append_events(self, order: Order) -> None:
        last = self._conn.execute(
            "SELECT COALESCE(MAX(event_sequence), 0) FROM events WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()[0]
        rows = [
            (
                order.order_id,
                event.sequence,
                event.timestamp.isoformat(),
                event.event_type.value,
                event.status.value,
                event.quantity,
                event.price,
                event.reason,
            )
            for event in order.events
            if event.sequence > last
        ]
        if rows:
            self._conn.executemany(
                """
                INSERT INTO events (
                    global_sequence, order_id, event_sequence, timestamp,
                    event_type, status, quantity, price, reason
                ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _write_snapshot(self, account: PaperAccount) -> None:
        positions = self._positions_fingerprint(account)
        orders = {
            order_id: self._order_fingerprint(order)
            for order_id, order in account.orders.items()
        }
        self._conn.execute(
            """
            INSERT INTO account_snapshot (
                id, cash, total_fees, realized_pnl, order_sequence,
                positions, orders, config
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                cash = excluded.cash,
                total_fees = excluded.total_fees,
                realized_pnl = excluded.realized_pnl,
                order_sequence = excluded.order_sequence,
                positions = excluded.positions,
                orders = excluded.orders,
                config = excluded.config
            """,
            (
                account.cash,
                account.total_fees,
                account.realized_pnl,
                account.order_sequence,
                json.dumps(positions),
                json.dumps(orders),
                json.dumps(self._config_fingerprint(account)),
            ),
        )

    def _load_meta(self) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM account_meta WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "starting_cash": row["starting_cash"],
            "fee_model": FeeModel.model_validate_json(row["fee_model"]),
            "risk_limits": RiskLimits.model_validate_json(row["risk_limits"]),
            "matcher": PaperMatcher.model_validate_json(row["matcher"]),
            "kill_switch": bool(row["kill_switch"]),
            "order_sequence": row["order_sequence"],
        }

    def _load_snapshot(self) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM account_snapshot WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "cash": row["cash"],
            "total_fees": row["total_fees"],
            "realized_pnl": row["realized_pnl"],
            "order_sequence": row["order_sequence"],
            "positions": json.loads(row["positions"]),
            "orders": json.loads(row["orders"]),
            "config": json.loads(row["config"]),
        }

    def _rebuild_orders(self) -> list[Order]:
        events_by_order: dict[str, list[sqlite3.Row]] = {}
        first_sequence: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT * FROM events ORDER BY global_sequence"
        ):
            events_by_order.setdefault(row["order_id"], []).append(row)
            first_sequence.setdefault(row["order_id"], row["global_sequence"])

        orders: list[Order] = []
        for header in self._conn.execute("SELECT * FROM orders"):
            order = Order(
                order_id=header["order_id"],
                instrument=Instrument.model_validate_json(header["instrument"]),
                side=Side(header["side"]),
                quantity=header["quantity"],
                order_type=OrderType(header["order_type"]),
                limit_price=header["limit_price"],
                created_at=datetime.fromisoformat(header["created_at"]),
                client_order_id=header["client_order_id"],
            )
            try:
                for row in events_by_order.get(header["order_id"], []):
                    timestamp = datetime.fromisoformat(row["timestamp"])
                    fill = None
                    if row["event_type"] == OrderEventType.FILL.value:
                        fill = Fill(
                            timestamp=timestamp,
                            quantity=row["quantity"],
                            price=row["price"],
                        )
                    order = OrderStateMachine.apply(
                        order,
                        OrderEventType(row["event_type"]),
                        fill=fill,
                        reason=row["reason"],
                        timestamp=timestamp,
                    )
            except ValueError as exc:
                raise StoreCorruptionError(
                    f"corrupt event log for order {header['order_id']}: {exc}"
                ) from exc
            orders.append(order)

        # Submission order: the first event's global sequence.
        return sorted(
            orders, key=lambda o: first_sequence.get(o.order_id, 2**63 - 1)
        )

    @staticmethod
    def _positions_fingerprint(account: PaperAccount) -> dict:
        return {
            key: position.model_dump(mode="json")
            for key, position in account.positions.items()
        }

    @staticmethod
    def _order_fingerprint(order: Order) -> dict:
        return {
            "side": order.side.value,
            "quantity": order.quantity,
            "order_type": order.order_type.value,
            "limit_price": order.limit_price,
            "created_at": order.created_at.isoformat(),
            "client_order_id": order.client_order_id,
            "instrument": order.instrument.model_dump(mode="json"),
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "events": len(order.events),
        }

    @staticmethod
    def _config_fingerprint(account: PaperAccount) -> dict:
        return {
            "starting_cash": (
                account.starting_cash
                if account.starting_cash is not None
                else account.cash
            ),
            "kill_switch": account.kill_switch,
            "fee_model": account.fee_model.model_dump(mode="json"),
            "risk_limits": account.risk_limits.model_dump(mode="json"),
            "matcher": account.matcher.model_dump(mode="json"),
        }

    def _reconcile(
        self, account: PaperAccount, orders: list[Order], snapshot: dict
    ) -> list[str]:
        divergences: list[str] = []
        checks = [
            ("cash", account.cash, snapshot["cash"]),
            ("total_fees", account.total_fees, snapshot["total_fees"]),
            ("realized_pnl", account.realized_pnl, snapshot["realized_pnl"]),
            ("order_sequence", account.order_sequence, snapshot["order_sequence"]),
        ]
        for name, rebuilt, recorded in checks:
            if rebuilt != recorded:
                divergences.append(
                    f"{name}: rebuilt {rebuilt} != recorded {recorded}"
                )
        rebuilt_positions = self._positions_fingerprint(account)
        if rebuilt_positions != snapshot["positions"]:
            divergences.append(
                f"positions: rebuilt {rebuilt_positions} != recorded {snapshot['positions']}"
            )
        rebuilt_orders = {
            order.order_id: self._order_fingerprint(order) for order in orders
        }
        if rebuilt_orders != snapshot["orders"]:
            divergences.append(
                f"orders: rebuilt {rebuilt_orders} != recorded {snapshot['orders']}"
            )
        rebuilt_config = self._config_fingerprint(account)
        if rebuilt_config != snapshot["config"]:
            divergences.append(
                f"config: rebuilt {rebuilt_config} != recorded {snapshot['config']}"
            )
        return divergences
