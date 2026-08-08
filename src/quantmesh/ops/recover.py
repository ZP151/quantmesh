"""Journal replay and recovery drills (M10 Phase B, issue #59).

``recover`` reads the M2 order journal with the fail-closed discipline
(all refusals collected with line attribution — never a partial
replay), replays the recorded orders into a fresh account by pure
event application (no risk gate, no matcher — the already-executed
history re-books exactly as it ran), verifies every order's event
history re-applies cleanly through the state machine (no orphaned
fills, no fabricated state), and reconciles the result against a
surviving account snapshot with the ADR-0006 identity/tolerance
discipline (order identity, filled quantity, average fill price,
position surface). ``quantmesh ops recover`` is the drill surface:
exit 0 only when the replay is clean — any refusal, event
inconsistency or ERROR finding exits 1 with the findings named.

The account snapshot target is a ``PaperAccount`` JSON dump (the M1
surface serializes the same model); the operator declares the account
configuration (starting cash, fee bps) that the journal itself does
not record. Replay with the same configuration produces the same
state — that equality, plus the reconciliation report, is the drill
evidence that journal replay causes no duplicate or orphaned orders.
"""

import math
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from quantmesh.domain.models import Side
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderStatus,
)
from quantmesh.execution.accounting import (
    DEFAULT_FEE_BPS,
    FeeModel,
    PaperAccount,
    position_key,
)
from quantmesh.execution.journal import JOURNAL_FILE
from quantmesh.execution.reconciliation import (
    FindingKind,
    OrderOutcome,
    ReconcileTolerance,
    ReconciliationFinding,
    ReconciliationReport,
    Severity,
)
from quantmesh.settings import settings


class RecoveryReport(BaseModel):
    """One recovery drill outcome: refusals, the replayed account and
    the reconciliation report. ``clean`` is False on any refusal or any
    ERROR finding — the drill exits 1 and nothing is silently accepted."""

    refusals: list[str] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    account: PaperAccount | None = None
    report: ReconciliationReport | None = None

    @property
    def clean(self) -> bool:
        if self.refusals or self.report is None:
            return False
        if self.report.counts["missing"]:
            return False
        return not any(
            finding.severity is Severity.ERROR for finding in self.report.findings
        )


def read_journal_lines(root: Path | None) -> tuple[list[Order], list[str]]:
    """Read the order journal fail-closed, collecting every refusal
    with line attribution instead of stopping at the first.

    The discipline is OrderJournal's own, applied diagnostically so a
    recovery drill reports ALL corrupt lines: a partial append or a
    truncated tail (crash mid-write) is refused with its line number,
    never partially replayed. A missing root or file is an empty
    journal — replaying nothing is a valid, clean outcome.
    """
    journal_root = root if root is not None else settings.orders_dir
    path = journal_root / JOURNAL_FILE
    if not journal_root.exists():
        return [], []
    if not journal_root.is_dir():
        return [], [f"order journal root {journal_root} is not a directory"]
    if not path.exists():
        return [], []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return [], [f"order journal {path} is unreadable: {error}"]

    orders: list[Order] = []
    refusals: list[str] = []
    seen: dict[str, int] = {}
    seen_keys: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            order = Order.model_validate_json(line)
        except ValidationError:
            refusals.append(f"order journal {path} line {line_number} is invalid")
            continue
        if order.order_id in seen:
            refusals.append(
                f"order journal {path} lines {seen[order.order_id]} and "
                f"{line_number} share an order id"
            )
            continue
        if order.idempotency_key is not None:
            if order.idempotency_key in seen_keys:
                refusals.append(
                    f"order journal {path} lines {seen_keys[order.idempotency_key]} "
                    f"and {line_number} share an idempotency key"
                )
                continue
            seen_keys[order.idempotency_key] = line_number
        seen[order.order_id] = line_number
        orders.append(order)
    return orders, refusals


def verify_event_history(order: Order) -> list[str]:
    """Re-apply the recorded event history through the state machine
    and compare with the recorded state: no orphaned fills, no
    fabricated state, no illegal transition. A hand-edited or corrupt-
    but-parseable journal order is named, never silently replayed."""
    rebuilt = order.model_copy(
        update={"status": OrderStatus.PENDING, "filled_quantity": 0.0, "events": []}
    )
    try:
        for event in order.events:
            if event.event_type is OrderEventType.FILL:
                fill = Fill(
                    timestamp=event.timestamp,
                    quantity=event.quantity,
                    price=event.price,
                    broker_fill_id=event.broker_fill_id,
                    fee=event.fee,
                )
                rebuilt = OrderStateMachine.apply(
                    rebuilt,
                    event.event_type,
                    fill=fill,
                    reason=event.reason,
                    timestamp=event.timestamp,
                )
            else:
                rebuilt = OrderStateMachine.apply(
                    rebuilt,
                    event.event_type,
                    reason=event.reason,
                    timestamp=event.timestamp,
                )
    except ValueError as error:
        return [f"order {order.order_id!r} event history is invalid: {error}"]
    problems: list[str] = []
    if rebuilt.status is not order.status:
        problems.append(
            f"order {order.order_id!r} state {order.status.value!r} disagrees "
            f"with its event history ({rebuilt.status.value!r})"
        )
    if not math.isclose(rebuilt.filled_quantity, order.filled_quantity):
        problems.append(
            f"order {order.order_id!r} filled_quantity {order.filled_quantity} "
            f"disagrees with its event history ({rebuilt.filled_quantity})"
        )
    if len(rebuilt.events) != len(order.events):
        problems.append(
            f"order {order.order_id!r} event count {len(order.events)} "
            f"disagrees with a clean replay ({len(rebuilt.events)})"
        )
    return problems


def replay_orders(
    orders: Sequence[Order], *, cash: float, fee_bps: float = DEFAULT_FEE_BPS
) -> PaperAccount:
    """Fold the journal into a fresh account by event application only.

    The risk gate, the matcher and the kill switch are NOT re-run: the
    orders were already gated and matched, and a recovery that re-gated
    them could diverge from what actually happened. Each order replays
    as recorded (an ACCEPTED order with no fills stays unacknowledged —
    the operator's runbook decision, never a fabricated fill), and its
    fill events re-book cash, positions and fees exactly as the kernel
    booked them the first time.
    """
    account = PaperAccount(cash=cash, fee_model=FeeModel(fee_bps=fee_bps))
    orders_map: dict[str, Order] = {}
    for order in orders:
        for event in order.events:
            if event.event_type is OrderEventType.FILL:
                fill = Fill(
                    timestamp=event.timestamp,
                    quantity=event.quantity,
                    price=event.price,
                    broker_fill_id=event.broker_fill_id,
                    fee=event.fee,
                )
                account = account.apply_fill(order, fill)
        orders_map[order.order_id] = order
    return account.model_copy(
        update={"orders": orders_map, "order_sequence": len(orders_map)}
    )


def _journal_positions(orders: Sequence[Order]) -> dict[str, float]:
    """Net position per instrument implied by the journal's fill
    events — the reconciliation target for the account position
    surface (zero positions are dropped, mirroring the kernel's
    close-pop)."""
    positions: dict[str, float] = {}
    for order in orders:
        key = position_key(order.instrument)
        sign = 1.0 if order.side is Side.BUY else -1.0
        for fill in order.fills:
            positions[key] = positions.get(key, 0.0) + sign * fill.quantity
    return {key: value for key, value in positions.items() if not math.isclose(value, 0)}


def _within_bps(observed: float, expected: float, bps: float) -> bool:
    if expected == 0:
        return math.isclose(observed, 0)
    return abs(observed - expected) / abs(expected) <= bps / 10_000


def reconcile_recovered(
    orders: Sequence[Order],
    account: PaperAccount,
    tolerance: ReconcileTolerance | None = None,
) -> ReconciliationReport:
    """Reconcile the journal against an account with the ADR-0006
    discipline: every journal order matched by identity with filled
    quantity, average fill price and status compared under the declared
    tolerances; account orders with no journal record are orphaned
    (divergent); the position surface is compared with the
    position_qty tolerance; event-history inconsistencies are named.

    Against a replay of the same journal every outcome is matched with
    zero findings — that exact report is the drill evidence. Against a
    surviving account snapshot it is the ADR-0006 comparison: a
    divergence on either side is a finding, never silently accepted.
    """
    limits = tolerance or ReconcileTolerance()
    journal_ids = {order.order_id for order in orders}
    outcomes: list[OrderOutcome] = []
    missing_internal: list[str] = []
    for order in orders:
        findings = [
            ReconciliationFinding(
                kind=FindingKind.STATUS,
                severity=Severity.ERROR,
                message=problem,
                order_id=order.order_id,
            )
            for problem in verify_event_history(order)
        ]
        live = account.orders.get(order.order_id)
        if live is None:
            missing_internal.append(order.order_id)
            continue
        if live.status is not order.status:
            findings.append(
                ReconciliationFinding(
                    kind=FindingKind.STATUS,
                    severity=Severity.ERROR,
                    message=(
                        f"order {order.order_id!r} status "
                        f"{live.status.value!r} disagrees with the journal "
                        f"({order.status.value!r})"
                    ),
                    order_id=order.order_id,
                    observed=live.status.value,
                    expected=order.status.value,
                )
            )
        if not _within_bps(live.filled_quantity, order.filled_quantity, limits.qty_bps):
            findings.append(
                ReconciliationFinding(
                    kind=FindingKind.QUANTITY,
                    severity=Severity.ERROR,
                    message=(
                        f"order {order.order_id!r} filled quantity "
                        f"{live.filled_quantity} disagrees with the journal "
                        f"({order.filled_quantity})"
                    ),
                    order_id=order.order_id,
                    observed=str(live.filled_quantity),
                    expected=str(order.filled_quantity),
                )
            )
        observed_price = live.average_fill_price
        expected_price = order.average_fill_price
        if (
            observed_price is not None
            and expected_price is not None
            and not _within_bps(observed_price, expected_price, limits.price_bps)
        ):
            findings.append(
                ReconciliationFinding(
                    kind=FindingKind.PRICE,
                    severity=Severity.ERROR,
                    message=(
                        f"order {order.order_id!r} average fill price "
                        f"{observed_price} disagrees with the journal "
                        f"({expected_price})"
                    ),
                    order_id=order.order_id,
                    observed=str(observed_price),
                    expected=str(expected_price),
                )
            )
        outcomes.append(
            OrderOutcome(
                internal_order_id=order.order_id,
                status="divergent" if findings else "matched",
                findings=findings,
            )
        )

    # Account orders the journal does not record are orphaned — a replay
    # cannot have produced them, so a snapshot carrying them is divergent.
    for order_id in sorted(account.orders):
        if order_id not in journal_ids:
            outcomes.append(
                OrderOutcome(
                    internal_order_id=order_id,
                    status="divergent",
                    findings=[
                        ReconciliationFinding(
                            kind=FindingKind.STATUS,
                            severity=Severity.ERROR,
                            message=(
                                f"account order {order_id!r} has no journal "
                                f"record (orphaned)"
                            ),
                            order_id=order_id,
                        )
                    ],
                )
            )

    position_findings: list[ReconciliationFinding] = []
    expected_positions = _journal_positions(orders)
    for key in sorted(set(expected_positions) | set(account.positions)):
        expected = expected_positions.get(key)
        observed = account.positions.get(key)
        if expected is None or observed is None:
            side = "account" if observed is not None else "journal"
            quantity = observed if observed is not None else expected
            position_findings.append(
                ReconciliationFinding(
                    kind=FindingKind.POSITION,
                    severity=Severity.ERROR,
                    message=(
                        f"position {key!r} ({quantity} {side}) has no "
                        f"counterpart on the other surface"
                    ),
                    observed=str(observed),
                    expected=str(expected),
                )
            )
        elif not _within_bps(
            observed.quantity, expected, limits.position_qty_bps
        ):
            position_findings.append(
                ReconciliationFinding(
                    kind=FindingKind.POSITION,
                    severity=Severity.ERROR,
                    message=(
                        f"position {key!r} quantity {observed.quantity} "
                        f"disagrees with the journal ({expected})"
                    ),
                    observed=str(observed.quantity),
                    expected=str(expected),
                )
            )
    return ReconciliationReport(
        tolerance=limits,
        outcomes=outcomes,
        missing_internal=missing_internal,
        position_findings=position_findings,
    )


def recover(
    root: Path | None,
    *,
    cash: float,
    fee_bps: float = DEFAULT_FEE_BPS,
    tolerance: ReconcileTolerance | None = None,
    against: Path | None = None,
) -> RecoveryReport:
    """Run one recovery drill: read fail-closed, replay, reconcile.

    The report is ``clean`` only when every journal line read, the
    events re-applied and the reconciliation is without refusals or
    ERROR findings — a corrupt journal (partial append, truncated
    tail), an un-bookable replay or a divergent snapshot all exit 1
    with the attribution named.
    """
    orders, refusals = read_journal_lines(root)
    account: PaperAccount | None = None
    report: ReconciliationReport | None = None
    if not refusals:
        try:
            account = replay_orders(orders, cash=cash, fee_bps=fee_bps)
        except ValueError as error:
            refusals.append(f"replay refused: {error}")
    if not refusals and account is not None:
        target = account
        if against is not None:
            try:
                target = PaperAccount.model_validate_json(
                    against.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, ValidationError) as error:
                refusals.append(f"account snapshot {against} is unreadable: {error}")
        if not refusals:
            report = reconcile_recovered(orders, target, tolerance)
    return RecoveryReport(
        refusals=refusals,
        orders=orders,
        account=account if not refusals else None,
        report=report,
    )
