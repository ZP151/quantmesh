"""Linearizable in-process authority for the immutable paper account."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from pydantic import ValidationError

from quantmesh._fs import atomic_replace
from quantmesh.domain.orders import Order, validate_order_replay
from quantmesh.execution.accounting import PaperAccount

PAPER_ACCOUNT_FILE = "paper-account.json"


class PaperAccountPersistenceError(ValueError):
    """The local paper-account snapshot is absent, corrupt or unwritable."""


class PaperAccountFile:
    """Atomic local snapshot used to preserve the paper kernel across restarts."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.path = self.root / PAPER_ACCOUNT_FILE

    def load_or_create(self, initial: PaperAccount) -> PaperAccount:
        if not self.path.exists():
            self.save(initial)
            return initial
        if not self.path.is_file():
            raise PaperAccountPersistenceError(f"paper account snapshot is not a file: {self.path}")
        try:
            return PaperAccount.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValidationError) as error:
            raise PaperAccountPersistenceError(
                f"paper account snapshot is unreadable or invalid: {self.path}"
            ) from error

    def save(self, account: PaperAccount) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        try:
            temporary.write_text(account.model_dump_json(indent=2), encoding="utf-8")
            atomic_replace(temporary, self.path)
        except OSError as error:
            raise PaperAccountPersistenceError(
                f"paper account snapshot could not be written: {self.path}"
            ) from error


def recover_account_from_journal(
    account: PaperAccount,
    orders: Sequence[Order],
) -> PaperAccount:
    """Rebuild account aggregates and adopt a journal-only trailing suffix.

    This closes the crash window between durable journal append and atomic
    account publication. The surviving snapshot must be the exact derived
    state of an ordered journal prefix. Policy and kill-switch configuration
    survive recovery, but unverifiable funding and conflicting state fail
    closed instead of being trusted.
    """
    journal_orders: dict[str, Order] = {}
    journal_order_ids: list[str] = []
    previous_created_at = None
    for order in orders:
        try:
            validate_order_replay(order)
        except ValueError as error:
            raise PaperAccountPersistenceError(
                f"order journal derived state is invalid for {order.order_id!r}"
            ) from error
        if order.order_id in journal_orders:
            raise PaperAccountPersistenceError(
                f"order journal contains duplicate order id {order.order_id!r}"
            )
        if previous_created_at is not None and order.created_at < previous_created_at:
            raise PaperAccountPersistenceError(
                f"order journal creation time regresses at {order.order_id!r}"
            )
        journal_orders[order.order_id] = order
        journal_order_ids.append(order.order_id)
        previous_created_at = order.created_at

    for key, order in account.orders.items():
        if key != order.order_id:
            raise PaperAccountPersistenceError(
                f"paper account order map key {key!r} does not match order id {order.order_id!r}"
            )
        try:
            validate_order_replay(order)
        except ValueError as error:
            raise PaperAccountPersistenceError(
                f"paper account order {order.order_id!r} has invalid derived state"
            ) from error
        journal_order = journal_orders.get(order.order_id)
        if journal_order is None:
            raise PaperAccountPersistenceError(
                f"paper account order {order.order_id!r} is absent from the order journal"
            )
        if order != journal_order:
            raise PaperAccountPersistenceError(
                f"paper account and journal disagree on order {order.order_id!r}"
            )

    account_order_ids = list(account.orders)
    if account_order_ids != journal_order_ids[: len(account_order_ids)]:
        raise PaperAccountPersistenceError(
            "paper account orders are not an exact ordered prefix of the order journal"
        )
    if account.starting_cash is None:
        raise PaperAccountPersistenceError("paper account starting_cash is unavailable")
    if account.total_funding != 0:
        raise PaperAccountPersistenceError(
            "paper account total_funding is unverifiable without a durable funding journal"
        )

    recovered = PaperAccount(
        cash=account.starting_cash,
        starting_cash=account.starting_cash,
        fee_model=account.fee_model,
        risk_limits=account.risk_limits,
        matcher=account.matcher,
        kill_switch=account.kill_switch,
        kill_switches=dict(account.kill_switches),
    )

    prefix_length = len(account_order_ids)
    if prefix_length == 0:
        _validate_account_aggregate(account, recovered)

    for sequence, order in enumerate(orders, start=1):
        for fill in order.fills:
            try:
                recovered = recovered.apply_fill(order, fill)
            except ValueError as error:
                raise PaperAccountPersistenceError(
                    f"order journal fills cannot reconstruct order {order.order_id!r}"
                ) from error
        order_map = dict(recovered.orders)
        order_map[order.order_id] = order
        recovered = recovered.model_copy(
            update={
                "orders": order_map,
                "order_sequence": sequence,
            }
        )
        if sequence == prefix_length:
            _validate_account_aggregate(account, recovered)
    return recovered


def _validate_account_aggregate(
    account: PaperAccount,
    reconstructed: PaperAccount,
) -> None:
    for field in (
        "cash",
        "positions",
        "total_fees",
        "total_funding",
        "realized_pnl",
        "orders",
        "order_sequence",
    ):
        if getattr(account, field) != getattr(reconstructed, field):
            raise PaperAccountPersistenceError(
                f"paper account aggregate {field} disagrees with journal reconstruction"
            )


class PaperAccountStore:
    """Own one account revision and serialize every mutation.

    ``PaperAccount`` is immutable, but a read-compute-replace sequence is not.
    This store keeps proposal submission, kill-switch changes, persistence and
    reset installation under one re-entrant boundary so stale revisions cannot
    overwrite newer safety state.
    """

    def __init__(
        self,
        account: PaperAccount,
        *,
        publish: Callable[[PaperAccount], None] | None = None,
    ) -> None:
        self._account = account
        self._publish = publish
        self._lock = RLock()

    def get(self) -> PaperAccount:
        with self._lock:
            return self._account

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            yield

    def replace(self, account: PaperAccount) -> PaperAccount:
        with self._lock:
            if self._publish is not None:
                self._publish(account)
            self._account = account
            return account

    def update(self, transform: Callable[[PaperAccount], PaperAccount]) -> PaperAccount:
        with self._lock:
            return self.replace(transform(self._account))
