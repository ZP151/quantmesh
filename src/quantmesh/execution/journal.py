"""Durable order journal: the internal order state reconciliation runs against.

Every order QuantMesh has ever placed is recorded here as a domain
``Order`` snapshot with its full event history. The journal is the
single source of truth for the broker-order mapping (ADR-0006 decision
1): ``broker_order_id`` and ``client_order_id`` live on the recorded
orders, and nothing else may claim them.

Discipline mirrors the experiment and report registries (issue #18,
#27) and now lives in the shared ``JsonlStore`` (ADR-0016): atomic
writes via temp-file + ``os.replace``, fail-closed reads with line
attribution, duplicate order ids and idempotency keys refused on read,
and replay validation on read. Records are rewritten in place by
``update`` — an order's events grow, so its snapshot replaces the old
one — still one atomic replace per write.
"""

from pathlib import Path

from quantmesh.domain.orders import Order, validate_order_replay
from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.settings import settings

JOURNAL_FILE = "journal.jsonl"


class OrderJournal:
    """Append-only store of order snapshots under one journal root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.orders_dir
        self._store = JsonlStore(
            self.root,
            filename=JOURNAL_FILE,
            model=Order,
            label="order journal",
            id_label="order",
            article="an",
            key=lambda order: order.order_id,
            secondary_keys=[("idempotency key", lambda order: order.idempotency_key)],
            extra_validate=validate_order_replay,
        )

    def record(self, order: Order) -> Order:
        """Record a new order; a duplicate order id is refused."""
        return self._store.append(order)

    def update(self, order: Order) -> Order:
        """Replace the snapshot of an existing order in place."""
        return self._store.update(order)

    def get(self, order_id: str) -> Order:
        for order in self._store.read():
            if order.order_id == order_id:
                return order
        raise ValueError(f"no order recorded with id {order_id!r}")

    def all(self) -> list[Order]:
        return self._store.read()
