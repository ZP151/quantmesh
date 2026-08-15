"""Hyperliquid broker/paper reconciliation service (issue #30, Phase B).

The Moomoo engine's discipline (ADR-0006) carries over; the wire shapes
differ, so the engine stays venue-local while the contract types are
shared (``quantmesh.execution.reconciliation``):

- Identity comes only from the journal: ``broker_order_id`` (the venue
  ack) and the cloid channel — the venue's ``cloid`` echo of the journal's
  ``client_order_id``, the Hyperliquid remark channel. A venue row whose
  channels disagree, or an internal order claimed by two venue rows, is
  ambiguous → divergent. A cloid-only match is a *recovered* mapping and
  is noted, never silent (the placement ack was lost).
- The venue's surface reports only resting orders (``open_orders`` rows)
  and fill rows (``user_fills``) — there is no order-status endpoint in
  the pinned SDK. Order status is therefore derived: ``open`` while the
  venue lists the order, ``inactive`` once the surface is silent and only
  fills remain. ``inactive`` is interpreted with journal context:
  fills totalling the order quantity → FILLED; a journal already
  CANCELED/REJECTED → that status; otherwise the venue's silence means
  the order is no longer live → CANCELED. The venue never *reports*
  filled/canceled/rejected statuses on its surface — those enter the
  journal from venue acks (per-order place errors → REJECTED, cancel
  acks → CANCELED) — and a terminal journal order the venue no longer
  lists is classified matched: a confirmed ack plus a silent surface is
  venue truth, not a lost order. The explicit
  ``HYPERLIQUID_STATUS_TO_DOMAIN`` table declares the venue vocabulary;
  a surface status outside it fails closed as a status finding.
- The broker may be ahead of the journal — unadopted fills and the
  derived statuses that come with them are *progress* a clean run can
  import — but never behind: a journal that shows more fills or a later
  status than the venue is divergent.
- Quantities, prices, fees, timestamps, and positions compare against
  the run's declared tolerances (exact by default). An ``inactive`` row
  no longer declares its original size, so the order-quantity compare is
  skipped there and fills carry the comparison. Fees that cannot be
  verified — a fill row without a fee — are missing-data findings.

``apply_reconciliation`` imports broker-confirmed progress (fills,
status transitions, the recovered oid) into the journal **only** for
pairs classified matched or pending, and only through
``OrderStateMachine``; divergent and missing pairs are refused, never
adopted. A fee-less fill, a fill without venue identity (the parser
already refuses those), or a terminal state that does not follow from
the fills is a refusal with a note. Matched terminal journal orders the
venue no longer lists are skipped silently — their ack is the record,
there is nothing left to import. Nothing is ever canceled, modified, or
reversed by reconciliation.
"""

import math
from datetime import UTC, datetime

from quantmesh.domain.models import Venue
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderStatus,
)
from quantmesh.execution.journal import OrderJournal
from quantmesh.execution.reconciliation import (
    AdoptionResult,
    FindingKind,
    OrderOutcome,
    ReconcileTolerance,
    ReconciliationFinding,
    ReconciliationReport,
    Severity,
    compare_fees,
    compare_fill_ids,
    compare_positions,
    compare_prices,
    compare_quantities,
    dedupe_by_id,
    finding,
    is_terminal,
)
from quantmesh.hyperliquid.exchange import (
    BrokerFill,
    BrokerOrder,
    ExecutionSnapshot,
)

__all__ = [
    "HYPERLIQUID_STATUS_TO_DOMAIN",
    "apply_reconciliation",
    "run_reconciliation",
]

# Surface status → QuantMesh domain status (issue #30, Phase B).
# The venue's surface only ever yields "open" (the order has remaining
# size) and "inactive" (fills-only rows, derived with journal context
# below); the filled/partially_filled/canceled/rejected entries are the
# venue's *ack* vocabulary, declared here so the table is the complete
# per-venue contract. Any surface status outside this table — or any
# ack status the venue should not have sent — fails closed as a status
# finding instead of being guessed.
HYPERLIQUID_STATUS_TO_DOMAIN: dict[str, OrderStatus] = {
    "open": OrderStatus.ACCEPTED,
    "filled": OrderStatus.FILLED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "canceled": OrderStatus.CANCELED,
    "rejected": OrderStatus.REJECTED,
}


def run_reconciliation(
    snapshot: ExecutionSnapshot,
    journal: OrderJournal,
    tolerance: ReconcileTolerance | None = None,
) -> ReconciliationReport:
    """Classify every venue order against the journal; pure and
    deterministic (ADR-0006). The journal is read once; the report never
    writes anything."""
    tolerance = tolerance or ReconcileTolerance()
    internal = journal.all()
    outcomes: list[OrderOutcome] = []
    missing_internal: list[str] = []

    # Identity channels, journal-derived only (ADR-0006 decision 1).
    # The oid channel is str(oid) — the adapter stamps broker_order_id
    # from the venue ack — and the cloid channel carries the raw
    # client_order_id (the venue echoes "0x"+client_order_id).
    by_broker_id = {
        order.broker_order_id: order
        for order in internal
        if order.broker_order_id is not None
    }
    by_cloid: dict[str, Order] = {}
    for order in internal:
        if order.client_order_id is not None:
            by_cloid[order.client_order_id] = order

    for broker_order in dedupe_by_id(snapshot.orders, lambda o: o.oid):
        by_id = by_broker_id.get(str(broker_order.oid))
        by_note = _by_cloid(broker_order, by_cloid)

        if by_id is not None and by_note is not None and by_id is not by_note:
            outcomes.append(
                OrderOutcome(
                    broker_order_id=str(broker_order.oid),
                    internal_order_id=by_id.order_id,
                    status="divergent",
                    findings=[
                        finding(
                            FindingKind.MAPPING,
                            Severity.ERROR,
                            f"venue order {broker_order.oid} maps to "
                            f"{by_id.order_id!r} by oid but {by_note.order_id!r} "
                            "by cloid; the mapping is ambiguous",
                            order_id=by_id.order_id,
                        )
                    ],
                )
            )
            continue

        internal_order = by_id if by_id is not None else by_note
        if internal_order is None:
            outcomes.append(
                OrderOutcome(
                    broker_order_id=str(broker_order.oid),
                    status="missing",
                    findings=[
                        finding(
                            FindingKind.MAPPING,
                            Severity.ERROR,
                            f"venue order {broker_order.oid} has no journal "
                            "counterpart (no oid and no cloid link)",
                        )
                    ],
                )
            )
            continue

        outcomes.append(
            _compare(
                broker_order,
                internal_order,
                snapshot.fills,
                tolerance,
                recovered=by_id is None,
            )
        )

    claimed = {
        outcome.internal_order_id for outcome in outcomes if outcome.internal_order_id
    }
    for order in internal:
        if order.order_id in claimed:
            continue
        if is_terminal(order.status):
            # Ack-terminal unclaimed: the venue surface is silent after a
            # confirmed terminal ack — canceled orders leave the surface,
            # rejected orders never entered it, and old fills age out of
            # userFills. The ack is the record; silence is venue truth,
            # not a lost order. When the order never received a venue
            # order id the silence is still worth noting: the terminal
            # state rests on the ack alone (MAPPING/WARNING, non-blocking).
            findings = []
            if order.broker_order_id is None:
                findings.append(
                    finding(
                        FindingKind.MAPPING,
                        Severity.WARNING,
                        f"order {order.order_id} is {order.status.value} by venue "
                        "ack but never received a venue order id; the venue "
                        "surface is silent and the ack is the record",
                        order_id=order.order_id,
                    )
                )
            outcomes.append(
                OrderOutcome(
                    broker_order_id=order.broker_order_id,
                    internal_order_id=order.order_id,
                    status="matched",
                    findings=findings,
                )
            )
        else:
            missing_internal.append(order.order_id)

    broker_by_symbol: dict[str, float] = {}
    for position in snapshot.positions:
        broker_by_symbol[position.coin] = (
            broker_by_symbol.get(position.coin, 0.0) + position.size
        )
    position_findings = compare_positions(
        broker_by_symbol=broker_by_symbol,
        internal=internal,
        venue=Venue.HYPERLIQUID,
        noun="venue",
        tolerance=tolerance,
    )

    return ReconciliationReport(
        tolerance=tolerance,
        outcomes=outcomes,
        missing_internal=missing_internal,
        position_findings=position_findings,
    )


def apply_reconciliation(
    report: ReconciliationReport,
    journal: OrderJournal,
    snapshot: ExecutionSnapshot,
) -> AdoptionResult:
    """Import broker-confirmed progress for clean pairs (ADR-0006 d. 5).

    Only pairs the run classified matched or pending — with no findings
    other than the recovered-mapping note — are adopted; divergent and
    missing orders are refused. Adoption appends venue fills (stamped
    with ``broker_fill_id`` and fee) and terminal status transitions
    through ``OrderStateMachine``; a transition the machine refuses or a
    fee-less fill is a refusal with a note. Matched terminal orders the
    venue no longer lists are skipped silently — there is nothing left
    to import. Nothing is ever canceled, modified, or reversed.
    """
    result = AdoptionResult()
    snapshot_orders = {str(order.oid): order for order in snapshot.orders}
    for outcome in report.outcomes:
        ref = outcome.internal_order_id or outcome.broker_order_id or "?"
        if outcome.status not in ("matched", "pending"):
            result.refused.append(ref)
            continue
        blocking = [
            finding
            for finding in outcome.findings
            if not (
                finding.kind is FindingKind.MAPPING
                and finding.severity is Severity.WARNING
            )
        ]
        if blocking:
            result.refused.append(ref)
            continue
        if outcome.internal_order_id is None:
            result.refused.append(ref)
            continue
        try:
            order = journal.get(outcome.internal_order_id)
        except ValueError:
            result.refused.append(outcome.internal_order_id)
            continue
        broker_order = None
        if outcome.broker_order_id is not None:
            broker_order = snapshot_orders.get(outcome.broker_order_id)
        if broker_order is None:
            # Ack-terminal skip: a terminal journal order the venue no
            # longer lists (or never listed) has nothing to import; its
            # ack is the record. A live order the venue lost sight of was
            # classified missing/divergent and was refused above.
            if is_terminal(order.status):
                continue
            result.refused.append(outcome.internal_order_id)
            continue
        updated, notes = _adopt_progress(order, broker_order, snapshot, outcome)
        if updated is None:
            result.refused.append(outcome.internal_order_id)
            result.notes.extend(notes)
            continue
        result.updated[updated.order_id] = journal.update(updated)
        result.notes.extend(notes)
    return result


# --- classification internals -------------------------------------------------

def _compare(
    broker: BrokerOrder,
    order: Order,
    fills: list[BrokerFill],
    tolerance: ReconcileTolerance,
    *,
    recovered: bool,
) -> OrderOutcome:
    findings: list[ReconciliationFinding] = []
    if recovered:
        findings.append(
            finding(
                FindingKind.MAPPING,
                Severity.WARNING,
                f"mapping for venue order {broker.oid} recovered via the cloid "
                "channel (the placement acknowledgement was lost); the venue "
                "order id will be re-stamped at adoption",
                order_id=order.order_id,
            )
        )

    broker_status = _surface_status(broker, order)
    if broker_status is None:
        findings.append(
            finding(
                FindingKind.STATUS,
                Severity.ERROR,
                f"venue status {broker.status!r} has no honest domain meaning",
                order_id=order.order_id,
                observed=broker.status,
                expected=order.status.value,
            )
        )
    else:
        _compare_status(broker_status, order, findings, broker)

    findings.extend(
        compare_quantities(
            broker_qty=broker.quantity if broker.declares_quantity else None,
            broker_filled_qty=broker.filled_quantity,
            order=order,
            tolerance=tolerance,
            noun="venue",
            fmt=lambda value: f"{value:g}",
        )
    )
    findings.extend(
        compare_prices(
            broker_limit_price=broker.limit_price,
            broker_average_price=broker.average_price,
            order=order,
            tolerance=tolerance,
            noun="venue",
        )
    )
    order_fills = [fill for fill in fills if fill.oid == broker.oid]
    findings.extend(
        compare_fees(
            broker_fees=[fill.fee for fill in order_fills if fill.fee is not None],
            row_count=len(order_fills),
            row_noun="fills",
            noun="venue",
            order=order,
            tolerance=tolerance,
        )
    )
    venue_ids = {fill.fill_id for fill in order_fills}
    findings.extend(
        compare_fill_ids(
            broker_fill_ids=venue_ids,
            row_noun="fill",
            noun="venue",
            order=order,
        )
    )

    # The recovered-mapping note is non-blocking by contract (the apply
    # path whitelists MAPPING/WARNING); only genuinely blocking findings
    # make the pair divergent. "matched" means terminal agreement on both
    # sides; a terminal broker ahead of a live journal is pending progress.
    blocking = [
        finding
        for finding in findings
        if not (
            finding.kind is FindingKind.MAPPING and finding.severity is Severity.WARNING
        )
    ]
    if blocking:
        status = "divergent"
    elif (
        broker_status is not None
        and is_terminal(order.status)
        and is_terminal(broker_status)
        and broker_status == order.status
    ):
        status = "matched"
    else:
        status = "pending"
    return OrderOutcome(
        broker_order_id=str(broker.oid),
        internal_order_id=order.order_id,
        status=status,
        findings=findings,
        recovered_via_remark=recovered,
    )


def _surface_status(broker: BrokerOrder, order: Order) -> OrderStatus | None:
    """The venue surface → one domain status.

    ``open`` maps through the declared table. ``inactive`` is not a
    venue status — it is the derived marker for fills-only rows — and
    gets its meaning from journal context: fills totalling the order
    quantity → FILLED; a journal already CANCELED/REJECTED → that
    status; otherwise the venue's silence means the order is no longer
    live → CANCELED.
    """
    if broker.status == "inactive":
        if math.isclose(broker.filled_quantity, order.quantity):
            return OrderStatus.FILLED
        if order.status in (OrderStatus.CANCELED, OrderStatus.REJECTED):
            return order.status
        return OrderStatus.CANCELED
    return HYPERLIQUID_STATUS_TO_DOMAIN.get(broker.status)


def _compare_status(
    broker_status: OrderStatus,
    order: Order,
    findings: list[ReconciliationFinding],
    broker: BrokerOrder,
) -> None:
    if broker_status == order.status:
        return
    if _is_progress(broker_status, order.status):
        return  # the broker is ahead; adoption imports the progress
    findings.append(
        finding(
            FindingKind.STATUS,
            Severity.ERROR,
            f"status drift: venue {broker.status} vs journal {order.status.value}",
            order_id=order.order_id,
            observed=broker.status,
            expected=order.status.value,
        )
    )


# --- adoption internals -------------------------------------------------------

def _adopt_progress(
    order: Order,
    broker: BrokerOrder,
    snapshot: ExecutionSnapshot,
    outcome: OrderOutcome,
) -> tuple[Order | None, list[str]]:
    notes: list[str] = []
    fills = [fill for fill in snapshot.fills if fill.oid == broker.oid]

    def evidence_time():
        """The venue's latest evidence for the order, for event stamps."""
        if fills:
            return max(fill.timestamp for fill in fills)
        if broker.created is not None:
            return broker.created
        return datetime.now(UTC)  # defensive; unreachable for real rows

    known = {fill.broker_fill_id for fill in order.fills if fill.broker_fill_id}
    for fill in fills:
        if fill.fill_id in known:
            continue
        if fill.fee is None:
            return None, [f"{order.order_id}: fill {fill.fill_id} has no fee"]
        try:
            order = OrderStateMachine.apply(
                order,
                OrderEventType.FILL,
                fill=Fill(
                    timestamp=fill.timestamp,
                    quantity=fill.quantity,
                    price=fill.price,
                    broker_fill_id=fill.fill_id,
                    fee=fill.fee,
                ),
                timestamp=fill.timestamp,
            )
        except ValueError as error:
            return None, [f"{order.order_id}: fill {fill.fill_id} refused: {error}"]
        notes.append(
            f"{order.order_id}: adopted fill {fill.fill_id} "
            f"({fill.quantity:g} @ {fill.price:g})"
        )

    broker_status = _surface_status(broker, order)
    if broker_status is None:
        return None, [f"{order.order_id}: venue status {broker.status!r} is unmappable"]
    # FILLED is only ever reached through fills; a derived FILLED that
    # the adopted fills do not complete is refused by the post-check
    # below. CANCELED/REJECTED are genuine terminal events.
    if broker_status in (OrderStatus.CANCELED, OrderStatus.REJECTED) and not is_terminal(
        order.status
    ):
        event = {
            OrderStatus.CANCELED: OrderEventType.CANCELED,
            OrderStatus.REJECTED: OrderEventType.REJECTED,
        }[broker_status]
        try:
            order = OrderStateMachine.apply(
                order,
                event,
                reason=broker.status if event is OrderEventType.REJECTED else None,
                timestamp=evidence_time(),
            )
        except ValueError as error:
            return None, [f"{order.order_id}: {broker_status.value} refused: {error}"]
        notes.append(f"{order.order_id}: adopted {broker_status.value}")

    if broker_status is OrderStatus.ACCEPTED and order.status is OrderStatus.PENDING:
        try:
            order = OrderStateMachine.apply(
                order,
                OrderEventType.ACCEPTED,
                timestamp=broker.created or evidence_time(),
            )
        except ValueError as error:
            return None, [f"{order.order_id}: accepted refused: {error}"]
        notes.append(f"{order.order_id}: adopted accepted")

    if broker_status == OrderStatus.FILLED and order.status is not OrderStatus.FILLED:
        return None, [
            f"{order.order_id}: venue reports FILLED but fills total "
            f"{order.filled_quantity:g} of {order.quantity:g}"
        ]
    if broker_status == OrderStatus.ACCEPTED and order.status not in (
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
    ):
        return None, [
            f"{order.order_id}: venue reports an open order but the journal is "
            f"{order.status.value}"
        ]
    if broker_status in (OrderStatus.CANCELED, OrderStatus.REJECTED) and order.status not in (
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
    ):
        return None, [
            f"{order.order_id}: venue reports {broker.status} but the journal is "
            f"{order.status.value}"
        ]
    if broker_status == OrderStatus.PARTIALLY_FILLED and order.status not in (
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.ACCEPTED,
        OrderStatus.FILLED,
    ):
        return None, [
            f"{order.order_id}: venue reports a partial fill but the journal is "
            f"{order.status.value}"
        ]

    if outcome.recovered_via_remark and order.broker_order_id is None:
        order = order.model_copy(update={"broker_order_id": str(broker.oid)})
        notes.append(f"{order.order_id}: re-stamped venue order id {broker.oid}")
    return order, notes


# --- small helpers -------------------------------------------------------------

def _by_cloid(broker: BrokerOrder, by_cloid: dict[str, Order]) -> Order | None:
    if broker.cloid is None:
        return None
    return by_cloid.get(broker.cloid.removeprefix("0x"))


def _is_progress(broker: OrderStatus, internal: OrderStatus) -> bool:
    """Broker-ahead is progress (adoptable); broker-behind is drift.

    The venue's "open" row means the order has remaining size — it is
    compatible with a journal that already shows partial fills (the
    venue reports those fills separately), unlike Moomoo's explicit
    per-order statuses.
    """
    if broker == internal:
        return True
    if is_terminal(broker):
        return not is_terminal(internal)
    if broker is OrderStatus.PARTIALLY_FILLED:
        return internal in (OrderStatus.PENDING, OrderStatus.ACCEPTED)
    if broker is OrderStatus.ACCEPTED:
        return internal in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED)
    return False
