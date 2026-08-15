"""Broker/paper reconciliation service (issue #28, Phase D, ADR-0006).

Every broker order in a snapshot is classified against the journal —
matched, pending, missing, or divergent — and every disagreement beyond
a declared tolerance is a typed finding. The classification rules:

- Identity comes only from the journal: ``broker_order_id`` (the broker
  ack) and ``remark`` (the ``client_order_id``/``order_id`` echo) are
  the two channels; a broker order whose channels disagree, or an
  internal order claimed by two broker orders, is ambiguous → divergent
  (ADR-0006 decision 1). A remark-only match is a *recovered* mapping
  and is noted, never silent.
- The broker may be ahead of the journal — unadopted fills and the
  statuses that come with them are *progress* a clean run can import —
  but never behind: a journal that shows more fills or a later status
  than the broker is divergent.
- Statuses compare through an explicit SDK→domain table; statuses with
  no honest domain meaning (``TIMEOUT``, ``DISABLED``, ``DELETED``,
  ``FILL_CANCELLED``) fail closed as status findings (decision 2).
- Quantities, prices, fees, timestamps, and positions compare against
  the run's declared tolerances; the deterministic simulator's default
  is exact (decision 3). Fees that cannot be verified — fills on one
  side, fee data missing on the other — are missing-data findings, not
  vacuously passed comparisons.

``apply_reconciliation`` imports broker-confirmed progress (fills,
status transitions) into the journal **only** for pairs the run
classified matched or pending, and only through ``OrderStateMachine``;
divergent, missing, and ambiguous pairs are refused, never adopted
(decision 5).
"""

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
from quantmesh.moomoo.execution import (
    BrokerDeal,
    BrokerOrder,
    ExecutionSnapshot,
)

# Broker order status → QuantMesh domain status (ADR-0006 decision 2).
# Pre-submission states map to PENDING, in-flight cancels to their
# fill-based equivalents. Statuses with no honest domain meaning are
# deliberately absent: they fail closed as status findings.
BROKER_STATUS_TO_DOMAIN: dict[str, OrderStatus] = {
    "UNSUBMITTED": OrderStatus.PENDING,
    "WAITING_SUBMIT": OrderStatus.PENDING,
    "SUBMITTING": OrderStatus.PENDING,
    "SUBMITTED": OrderStatus.ACCEPTED,
    "FILLED_PART": OrderStatus.PARTIALLY_FILLED,
    "FILLED_ALL": OrderStatus.FILLED,
    "CANCELLING_PART": OrderStatus.PARTIALLY_FILLED,
    "CANCELLING_ALL": OrderStatus.ACCEPTED,
    "CANCELLED_PART": OrderStatus.CANCELED,
    "CANCELLED_ALL": OrderStatus.CANCELED,
    "SUBMIT_FAILED": OrderStatus.REJECTED,
    "FAILED": OrderStatus.REJECTED,
}

# Only healthy deals are adoptable; a revoked or altered fill (broker
# DealStatus) is a finding, never a fill.
_HEALTHY_DEAL_STATUSES = ("OK",)

# The ADR-0006 contract types (FindingKind, Severity, ReconcileTolerance,
# ReconciliationFinding, OrderOutcome, ReconciliationReport, AdoptionResult)
# live in ``quantmesh.execution.reconciliation`` and are re-exported here,
# so existing importers keep working and the Hyperliquid binding shares
# the same vocabulary.


def run_reconciliation(
    snapshot: ExecutionSnapshot,
    journal: OrderJournal,
    tolerance: ReconcileTolerance | None = None,
) -> ReconciliationReport:
    """Classify every broker order against the journal; pure and
    deterministic (ADR-0006). The journal is read once; the report never
    writes anything."""
    tolerance = tolerance or ReconcileTolerance()
    internal = journal.all()
    outcomes: list[OrderOutcome] = []
    missing_internal: list[str] = []

    # Identity channels, journal-derived only (ADR-0006 decision 1).
    by_broker_id = {
        order.broker_order_id: order
        for order in internal
        if order.broker_order_id is not None
    }
    by_remark: dict[str, Order] = {}
    for order in internal:
        for key in (order.client_order_id, order.order_id):
            if key is not None:
                by_remark[key] = order

    deals = dedupe_by_id(snapshot.deals, lambda d: d.deal_id)

    for broker_order in dedupe_by_id(snapshot.orders, lambda o: o.order_id):
        by_id = by_broker_id.get(broker_order.order_id)
        by_note = _by_remark(broker_order, by_remark)

        if by_id is not None and by_note is not None and by_id is not by_note:
            outcomes.append(
                OrderOutcome(
                    broker_order_id=broker_order.order_id,
                    internal_order_id=by_id.order_id,
                    status="divergent",
                    findings=[
                        finding(
                            FindingKind.MAPPING,
                            Severity.ERROR,
                            f"broker order {broker_order.order_id} maps to "
                            f"{by_id.order_id!r} by broker id but {by_note.order_id!r} "
                            "by remark; the mapping is ambiguous",
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
                    broker_order_id=broker_order.order_id,
                    status="missing",
                    findings=[
                        finding(
                            FindingKind.MAPPING,
                            Severity.ERROR,
                            f"broker order {broker_order.order_id} has no journal "
                            "counterpart (no broker id and no remark link)",
                        )
                    ],
                )
            )
            continue

        outcomes.append(
            _compare(
                broker_order,
                internal_order,
                deals,
                tolerance,
                recovered=by_id is None,
            )
        )

    claimed = {
        outcome.internal_order_id for outcome in outcomes if outcome.internal_order_id
    }
    missing_internal = [
        order.order_id for order in internal if order.order_id not in claimed
    ]

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
    other than the recovered-mapping note — are adopted; divergent,
    missing, and ambiguous orders are refused. Adoption appends broker
    fills (stamped with ``broker_fill_id`` and fee) and terminal status
    transitions through ``OrderStateMachine``; a transition the machine
    refuses, a fee-less deal, or a terminal state that does not follow
    from the fills is a refusal with a note. Nothing is ever canceled,
    modified, or reversed by reconciliation.
    """
    result = AdoptionResult()
    snapshot_orders = {order.order_id: order for order in snapshot.orders}
    for outcome in report.outcomes:
        ref = outcome.internal_order_id or outcome.broker_order_id or "?"
        if outcome.status not in ("matched", "pending"):
            result.refused.append(ref)
            continue
        blocking = [
            finding
            for finding in outcome.findings
            if not (finding.kind is FindingKind.MAPPING and finding.severity is Severity.WARNING)
        ]
        if blocking:
            result.refused.append(ref)
            continue
        if outcome.internal_order_id is None or outcome.broker_order_id is None:
            result.refused.append(ref)
            continue
        try:
            order = journal.get(outcome.internal_order_id)
        except ValueError:
            result.refused.append(outcome.internal_order_id)
            continue
        broker_order = snapshot_orders.get(outcome.broker_order_id)
        if broker_order is None:
            result.refused.append(outcome.internal_order_id)
            continue
        updated, notes = _adopt_progress(
            order, broker_order, snapshot, outcome
        )
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
    deals: list[BrokerDeal],
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
                f"mapping for broker order {broker.order_id} recovered via remark "
                "(the placement acknowledgement was lost); the broker id will be "
                "re-stamped at adoption",
                order_id=order.order_id,
            )
        )

    broker_status = BROKER_STATUS_TO_DOMAIN.get(broker.order_status)
    if broker_status is None:
        findings.append(
            finding(
                FindingKind.STATUS,
                Severity.ERROR,
                f"broker status {broker.order_status!r} has no honest domain meaning",
                order_id=order.order_id,
                observed=broker.order_status,
                expected=order.status.value,
            )
        )
    else:
        _compare_status(broker_status, order, findings, broker)

    _compare_quantities(broker, order, tolerance, findings)
    _compare_prices(broker, order, tolerance, findings)
    _compare_fees(broker, deals, order, tolerance, findings)
    _compare_timestamps(broker, order, tolerance, findings)
    _compare_fill_ids(broker, deals, order, findings)

    # The recovered-mapping note is non-blocking by contract (the apply
    # path whitelists MAPPING/WARNING); only genuinely blocking findings
    # make the pair divergent. "matched" means terminal agreement on both
    # sides; a terminal broker ahead of a live journal is pending progress.
    blocking = [
        finding
        for finding in findings
        if not (finding.kind is FindingKind.MAPPING and finding.severity is Severity.WARNING)
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
        broker_order_id=broker.order_id,
        internal_order_id=order.order_id,
        status=status,
        findings=findings,
        recovered_via_remark=recovered,
    )


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
            f"status drift: broker {broker.order_status} vs journal {order.status.value}",
            order_id=order.order_id,
            observed=broker.order_status,
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
    diff = broker.qty - order.quantity
    if abs(diff) / order.quantity > qty_tol:
        findings.append(
            finding(
                FindingKind.QUANTITY,
                Severity.ERROR,
                f"order quantity drift: broker {broker.qty} vs journal {order.quantity}",
                order_id=order.order_id,
                observed=f"{broker.qty}",
                expected=f"{order.quantity}",
            )
        )
    # The fill side: the broker may be ahead (unadopted fills) but never
    # behind (the journal cannot hold fills the broker does not know).
    fill_diff = broker.dealt_qty - order.filled_quantity
    if fill_diff < -qty_tol * order.quantity:
        findings.append(
            finding(
                FindingKind.QUANTITY,
                Severity.ERROR,
                f"journal shows more fills than the broker: broker {broker.dealt_qty} "
                f"vs journal {order.filled_quantity}",
                order_id=order.order_id,
                observed=f"{broker.dealt_qty}",
                expected=f"{order.filled_quantity}",
            )
        )


def _compare_prices(
    broker: BrokerOrder,
    order: Order,
    tolerance: ReconcileTolerance,
    findings: list[ReconciliationFinding],
) -> None:
    price_tol = tolerance.price_bps / 10_000.0
    if order.limit_price is not None and broker.price is not None:
        if abs(broker.price - order.limit_price) / order.limit_price > price_tol:
            findings.append(
                finding(
                    FindingKind.PRICE,
                    Severity.ERROR,
                    f"limit price drift: broker {broker.price} vs journal "
                    f"{order.limit_price}",
                    order_id=order.order_id,
                    observed=f"{broker.price}",
                    expected=f"{order.limit_price}",
                )
            )
    broker_avg = broker.dealt_avg_price
    journal_avg = order.average_fill_price
    if broker_avg is not None and journal_avg is not None:
        if abs(broker_avg - journal_avg) / journal_avg > price_tol:
            findings.append(
                finding(
                    FindingKind.PRICE,
                    Severity.ERROR,
                    f"execution price drift: broker avg {broker_avg} vs journal avg "
                    f"{journal_avg}",
                    order_id=order.order_id,
                    observed=f"{broker_avg}",
                    expected=f"{journal_avg}",
                )
            )


def _compare_fees(
    broker: BrokerOrder,
    deals: list[BrokerDeal],
    order: Order,
    tolerance: ReconcileTolerance,
    findings: list[ReconciliationFinding],
) -> None:
    order_deals = [deal for deal in deals if deal.order_id == broker.order_id]
    broker_fees = [deal.fee for deal in order_deals if deal.fee is not None]
    journal_fees = [fill.fee for fill in order.fills if fill.fee is not None]
    if not order_deals and not journal_fees:
        return  # no execution on either side: no fee to compare
    if not order_deals:
        findings.append(
            finding(
                FindingKind.FEE,
                Severity.ERROR,
                "journal holds fills but the broker reports no deals for this order",
                order_id=order.order_id,
            )
        )
        return
    if len(broker_fees) != len(order_deals):
        findings.append(
            finding(
                FindingKind.MISSING_DATA,
                Severity.ERROR,
                f"broker reports {len(order_deals)} deals but fee data for "
                f"{len(order_deals) - len(broker_fees)} of them; fees cannot be verified",
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
                    "journal holds fees but the broker reports none; cannot compare",
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
                    f"fee drift: broker {broker_total} vs journal {journal_total}",
                    order_id=order.order_id,
                    observed=f"{broker_total}",
                    expected=f"{journal_total}",
                )
            )


def _compare_timestamps(
    broker: BrokerOrder,
    order: Order,
    tolerance: ReconcileTolerance,
    findings: list[ReconciliationFinding],
) -> None:
    skew = tolerance.time_skew_s
    create_delta = abs((broker.create_time - order.created_at).total_seconds())
    if create_delta > skew:
        findings.append(
            finding(
                FindingKind.TIMESTAMP,
                Severity.ERROR,
                f"creation time drift: broker {broker.create_time} vs journal "
                f"{order.created_at}",
                order_id=order.order_id,
                observed=broker.create_time.isoformat(),
                expected=order.created_at.isoformat(),
            )
        )
    last_event = order.events[-1].timestamp if order.events else None
    if broker.updated_time is not None and last_event is not None:
        update_delta = abs((broker.updated_time - last_event).total_seconds())
        if update_delta > skew:
            findings.append(
                finding(
                    FindingKind.TIMESTAMP,
                    Severity.ERROR,
                    f"update time drift: broker {broker.updated_time} vs journal "
                    f"{last_event}",
                    order_id=order.order_id,
                    observed=broker.updated_time.isoformat(),
                    expected=last_event.isoformat(),
                )
            )


def _compare_fill_ids(
    broker: BrokerOrder,
    deals: list[BrokerDeal],
    order: Order,
    findings: list[ReconciliationFinding],
) -> None:
    """Deal↔fill identity: a stamped fill whose deal vanished, or a
    revoked deal, is a finding (ADR-0006 decision 4)."""
    deal_ids = {deal.deal_id for deal in deals if deal.order_id == broker.order_id}
    for fill in order.fills:
        if fill.broker_fill_id is not None and fill.broker_fill_id not in deal_ids:
            findings.append(
                finding(
                    FindingKind.REVOKED_FILL,
                    Severity.ERROR,
                    f"fill {fill.broker_fill_id} is stamped on the journal but the "
                    "broker no longer reports that deal",
                    order_id=order.order_id,
                    observed=fill.broker_fill_id,
                )
            )
    for deal in deals:
        if deal.order_id != broker.order_id:
            continue
        if deal.status not in _HEALTHY_DEAL_STATUSES:
            findings.append(
                finding(
                    FindingKind.REVOKED_FILL,
                    Severity.ERROR,
                    f"deal {deal.deal_id} has status {deal.status!r} and is not adoptable",
                    order_id=order.order_id,
                    observed=deal.status,
                )
            )


def _compare_positions(
    positions,
    internal: list[Order],
    tolerance: ReconcileTolerance,
) -> list[ReconciliationFinding]:
    """Account-level position deltas per symbol (ADR-0006 d. 3)."""
    pos_tol = tolerance.position_qty_bps / 10_000.0
    findings: list[ReconciliationFinding] = []
    broker_by_symbol: dict[str, float] = {}
    for position in positions:
        broker_by_symbol[position.symbol] = (
            broker_by_symbol.get(position.symbol, 0.0) + position.qty
        )
    internal_by_symbol: dict[str, float] = {}
    for order in internal:
        if order.instrument.venue is not Venue.MOOMOO:
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
                    "broker position",
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
                    f"broker position {broker_qty:g} for {symbol} is unexplained by "
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
                    f"position drift for {symbol}: broker {broker_qty:g} vs journal "
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
    deals = [deal for deal in snapshot.deals if deal.order_id == broker.order_id]
    known = {fill.broker_fill_id for fill in order.fills if fill.broker_fill_id}
    for deal in deals:
        if deal.deal_id in known:
            continue
        if deal.status not in _HEALTHY_DEAL_STATUSES:
            return None, [f"{order.order_id}: deal {deal.deal_id} is {deal.status!r}"]
        if deal.fee is None:
            return None, [f"{order.order_id}: deal {deal.deal_id} has no fee"]
        try:
            order = OrderStateMachine.apply(
                order,
                OrderEventType.FILL,
                fill=Fill(
                    timestamp=deal.create_time,
                    quantity=deal.qty,
                    price=deal.price,
                    broker_fill_id=deal.deal_id,
                    fee=deal.fee,
                ),
                timestamp=deal.create_time,
            )
        except ValueError as error:
            return None, [f"{order.order_id}: fill {deal.deal_id} refused: {error}"]
        notes.append(
            f"{order.order_id}: adopted fill {deal.deal_id} "
            f"({deal.qty:g} @ {deal.price:g})"
        )

    broker_status = BROKER_STATUS_TO_DOMAIN.get(broker.order_status)
    if broker_status is None:
        return None, [f"{order.order_id}: broker status {broker.order_status!r} is unmappable"]
    # FILLED is only ever reached through fills; a broker FILLED that
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
                reason=(
                    broker.last_err_msg if event is OrderEventType.REJECTED else None
                ),
                timestamp=broker.updated_time or broker.create_time,
            )
        except ValueError as error:
            return None, [f"{order.order_id}: {broker_status.value} refused: {error}"]
        notes.append(f"{order.order_id}: adopted {broker_status.value}")

    if broker_status is OrderStatus.ACCEPTED and order.status is OrderStatus.PENDING:
        try:
            order = OrderStateMachine.apply(
                order,
                OrderEventType.ACCEPTED,
                timestamp=broker.updated_time or broker.create_time,
            )
        except ValueError as error:
            return None, [f"{order.order_id}: accepted refused: {error}"]
        notes.append(f"{order.order_id}: adopted accepted")

    if broker_status == OrderStatus.FILLED and order.status is not OrderStatus.FILLED:
        return None, [
            f"{order.order_id}: broker reports FILLED but fills total "
            f"{order.filled_quantity} of {order.quantity}"
        ]
    if (
        broker_status == OrderStatus.PARTIALLY_FILLED
        and order.status is not OrderStatus.PARTIALLY_FILLED
    ):
        return None, [
            f"{order.order_id}: broker reports FILLED_PART but the journal is "
            f"{order.status.value}"
        ]
    if (
        broker_status in (OrderStatus.CANCELED, OrderStatus.REJECTED)
        and order.status is not broker_status
    ):
        return None, [
            f"{order.order_id}: broker reports {broker.order_status} but the journal "
            f"is {order.status.value}"
        ]
    if broker_status == OrderStatus.ACCEPTED and order.status is not OrderStatus.ACCEPTED:
        return None, [
            f"{order.order_id}: broker reports SUBMITTED but the journal is "
            f"{order.status.value}"
        ]

    if outcome.recovered_via_remark and order.broker_order_id is None:
        order = order.model_copy(update={"broker_order_id": broker.order_id})
        notes.append(f"{order.order_id}: re-stamped broker order id {broker.order_id}")
    return order, notes


# --- small helpers -------------------------------------------------------------

def _by_remark(broker: BrokerOrder, by_remark: dict[str, Order]) -> Order | None:
    if broker.remark is None:
        return None
    return by_remark.get(broker.remark)


def _is_progress(broker: OrderStatus, internal: OrderStatus) -> bool:
    """Broker-ahead is progress (adoptable); broker-behind is drift."""
    if broker == internal:
        return True
    if is_terminal(broker):
        return not is_terminal(internal)
    if broker is OrderStatus.PARTIALLY_FILLED:
        return internal in (OrderStatus.PENDING, OrderStatus.ACCEPTED)
    if broker is OrderStatus.ACCEPTED:
        return internal is OrderStatus.PENDING
    return False
