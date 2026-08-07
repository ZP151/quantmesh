"""Durable order journal: the internal order state reconciliation runs against.

Every order QuantMesh has ever placed is recorded here as a domain
``Order`` snapshot with its full event history. The journal is the
single source of truth for the broker-order mapping (ADR-0006 decision
1): ``broker_order_id`` and ``client_order_id`` live on the recorded
orders, and nothing else may claim them.

Discipline mirrors the experiment and report registries (issue #18,
#27): atomic writes via temp-file + ``os.replace``, fail-closed reads
with line attribution, duplicate order ids refused on read. Records are
rewritten in place by ``update`` — an order's events grow, so its
snapshot replaces the old one — still one atomic replace per write.
"""

import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from quantmesh.domain.orders import Order
from quantmesh.settings import settings

JOURNAL_FILE = "journal.jsonl"


class OrderJournal:
    """Append-only store of order snapshots under one journal root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.orders_dir

    def record(self, order: Order) -> Order:
        """Record a new order; a duplicate order id is refused."""
        existing = self.all()
        if any(record.order_id == order.order_id for record in existing):
            raise ValueError(f"order {order.order_id!r} already recorded")
        self._write(existing + [order])
        return order

    def update(self, order: Order) -> Order:
        """Replace the snapshot of an existing order in place."""
        existing = self.all()
        if not any(record.order_id == order.order_id for record in existing):
            raise ValueError(f"order {order.order_id!r} is not recorded")
        updated = [order if record.order_id == order.order_id else record for record in existing]
        self._write(updated)
        return order

    def get(self, order_id: str) -> Order:
        for order in self.all():
            if order.order_id == order_id:
                return order
        raise ValueError(f"no order recorded with id {order_id!r}")

    def all(self) -> list[Order]:
        return self._read()

    def _write(self, orders: list[Order]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / JOURNAL_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{JOURNAL_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for order in orders:
                    handle.write(order.model_dump_json())
                    handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[Order]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"order journal root {self.root} is not a directory")
        path = self.root / JOURNAL_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"order journal {path} is unreadable") from error
        orders = []
        seen: dict[str, int] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                order = Order.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(
                    f"order journal {path} line {line_number} is invalid"
                ) from error
            if order.order_id in seen:
                raise ValueError(
                    f"order journal {path} lines {seen[order.order_id]} and "
                    f"{line_number} share an order id"
                )
            seen[order.order_id] = line_number
            orders.append(order)
        return orders
