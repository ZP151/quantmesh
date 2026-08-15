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

from quantmesh.domain.models import Side, Venue
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

    position_findings = _compare_positions(snapshot.positions, internal, tolerance)

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

    _compare_quantities(broker, order, tolerance, findings)
    _compare_prices(broker, order, tolerance, findings)
    _compare_fees(broker, fills, order, tolerance, findings)
    _compare_fill_ids(broker, fills, order, findings)

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


def _compare_quantities(
    broker: BrokerOrder,
    order: Order,
    tolerance: ReconcileTolerance,
    findings: list[ReconciliationFinding],
) -> None:
    qty_tol = tolerance.qty_bps / 10_000.0
    if broker.declares_quantity:
        diff = broker.quantity - order.quantity
        if abs(diff) / order.quantity > qty_tol:
            findings.append(
                finding(
                    FindingKind.QUANTITY,
                    Severity.ERROR,
                    f"order quantity drift: venue {broker.quantity:g} vs journal "
                    f"{order.quantity:g}",
                    order_id=order.order_id,
                    observed=f"{broker.quantity:g}",
                    expected=f"{order.quantity:g}",
                )
            )
    # The fill side: the broker may be ahead (unadopted fills) but never
    # behind (the journal cannot hold fills the broker does not know).
    fill_diff = broker.filled_quantity - order.filled_quantity
    if fill_diff < -qty_tol * order.quantity:
        findings.append(
            finding(
                FindingKind.QUANTITY,
                Severity.ERROR,
                f"journal shows more fills than the venue: venue "
                f"{broker.filled_quantity:g} vs journal {order.filled_quantity:g}",
                order_id=order.order_id,
                observed=f"{broker.filled_quantity:g}",
                expected=f"{order.filled_quantity:g}",
            )
        )


def _compare_prices(
    broker: BrokerOrder,
    order: Order,
    tolerance: ReconcileTolerance,
    findings: list[ReconciliationFinding],
) -> None:
    price_tol = tolerance.price_bps / 10_000.0
    if order.limit_price is not None and broker.limit_price is not None:
        if abs(broker.limit_price - order.limit_price) / order.limit_price > price_tol:
            findings.append(
                finding(
                    FindingKind.PRICE,
                    Severity.ERROR,
                    f"limit price drift: venue {broker.limit_price} vs journal "
                    f"{order.limit_price}",
                    order_id=order.order_id,
                    observed=f"{broker.limit_price}",
                    expected=f"{order.limit_price}",
                )
            )
    broker_avg = broker.average_price
    journal_avg = order.average_fill_price
    if broker_avg is not None and journal_avg is not None:
        if abs(broker_avg - journal_avg) / journal_avg > price_tol:
            findings.append(
                finding(
                    FindingKind.PRICE,
                    Severity.ERROR,
                    f"execution price drift: venue avg {broker_avg} vs journal avg "
                    f"{journal_avg}",
                    order_id=order.order_id,
                    observed=f"{broker_avg}",
                    expected=f"{journal_avg}",
                )
            )


def _compare_fees(
    broker: BrokerOrder,
    fills: list[BrokerFill],
    order: Order,
    tolerance: ReconcileTolerance,
    findings: list[ReconciliationFinding],
) -> None:
    order_fills = [fill for fill in fills if fill.oid == broker.oid]
    broker_fees = [fill.fee for fill in order_fills if fill.fee is not None]
    journal_fees = [fill.fee for fill in order.fills if fill.fee is not None]
    if not order_fills and not journal_fees:
        return  # no execution on either side: no fee to compare
    if not order_fills:
        findings.append(
            finding(
                FindingKind.FEE,
                Severity.ERROR,
                "journal holds fills but the venue reports no fills for this order",
                order_id=order.order_id,
            )
        )
        return
    if len(broker_fees) != len(order_fills):
        findings.append(
            finding(
                FindingKind.MISSING_DATA,
                Severity.ERROR,
                f"the venue reports {len(order_fills)} fills but fee data for "
                f"{len(order_fills) - len(broker_fees)} of them; fees cannot be "
                "verified",
                order_id=order.order_id,
            )
        )
        return
    if journal_fees:
        if not broker_fees:
            findings.append(
                finding(
                    FindingKind.MISSING_DATA,
                    Severity.ERROR,
                    "journal holds fees but the venue reports none; cannot compare",
                    order_id=order.order_id,
                )
            )
            return
        broker_total = sum(broker_fees)
        journal_total = sum(journal_fees)
        if abs(broker_total - journal_total) > tolerance.fee_abs:
            findings.append(
                finding(
                    FindingKind.FEE,
                    Severity.ERROR,
                    f"fee drift: venue {broker_total} vs journal {journal_total}",
                    order_id=order.order_id,
                    observed=f"{broker_total}",
                    expected=f"{journal_total}",
                )
            )


def _compare_fill_ids(
    broker: BrokerOrder,
    fills: list[BrokerFill],
    order: Order,
    findings: list[ReconciliationFinding],
) -> None:
    """Fill↔fill identity: a stamped fill whose venue row vanished is a
    finding (ADR-0006 decision 4). The venue only reports executed
    fills, so there is no unhealthy-fill status to check."""
    venue_ids = {fill.fill_id for fill in fills if fill.oid == broker.oid}
    for fill in order.fills:
        if fill.broker_fill_id is not None and fill.broker_fill_id not in venue_ids:
            findings.append(
                finding(
                    FindingKind.REVOKED_FILL,
                    Severity.ERROR,
                    f"fill {fill.broker_fill_id} is stamped on the journal but the "
                    "venue no longer reports that fill",
                    order_id=order.order_id,
                    observed=fill.broker_fill_id,
                )
            )


def _compare_positions(
    positions,
    internal: list[Order],
    tolerance: ReconcileTolerance,
) -> list[ReconciliationFinding]:
    """Account-level position deltas per symbol (ADR-0006 d. 3).

    Venue sizes are signed (``szi``: positive long, negative short) and
    the journal net is filled quantity signed by side, so the comparison
    needs no direction guessing.
    """
    pos_tol = tolerance.position_qty_bps / 10_000.0
    findings: list[ReconciliationFinding] = []
    broker_by_symbol: dict[str, float] = {}
    for position in positions:
        broker_by_symbol[position.coin] = (
            broker_by_symbol.get(position.coin, 0.0) + position.size
        )
    internal_by_symbol: dict[str, float] = {}
    for order in internal:
        if order.instrument.venue is not Venue.HYPERLIQUID:
            continue
        sign = 1.0 if order.side is Side.BUY else -1.0
        total = sum(fill.quantity for fill in order.fills)
        internal_by_symbol[order.instrument.symbol] = (
            internal_by_symbol.get(order.instrument.symbol, 0.0) + sign * total
        )
    for symbol in sorted(set(broker_by_symbol) | set(internal_by_symbol)):
        broker_qty = broker_by_symbol.get(symbol, 0.0)
        internal_qty = internal_by_symbol.get(symbol, 0.0)
        if broker_qty == 0.0 and internal_qty == 0.0:
            continue
        if broker_qty == 0.0:
            findings.append(
                finding(
                    FindingKind.POSITION,
                    Severity.ERROR,
                    f"journal net position {internal_qty:g} for {symbol} has no "
                    "venue position",
                    observed=f"{internal_qty:g}",
                    expected="0",
                )
            )
            continue
        if internal_qty == 0.0:
            findings.append(
                finding(
                    FindingKind.POSITION,
                    Severity.ERROR,
                    f"venue position {broker_qty:g} for {symbol} is unexplained by "
                    "the journal",
                    observed=f"{broker_qty:g}",
                    expected="0",
                )
            )
            continue
        delta = abs(broker_qty - internal_qty) / max(1.0, abs(internal_qty))
        if delta > pos_tol:
            findings.append(
                finding(
                    FindingKind.POSITION,
                    Severity.ERROR,
                    f"position drift for {symbol}: venue {broker_qty:g} vs journal "
                    f"{internal_qty:g}",
                    observed=f"{broker_qty:g}",
                    expected=f"{internal_qty:g}",
                )
            )
    return findings


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
