"""Hyperliquid reconciliation tests (M5, issue #30, Phase B).

The Moomoo discipline (ADR-0006) with the Hyperliquid surface: order
status is derived — "open" while the venue lists the order, "inactive"
for fills-only rows interpreted with journal context — and identity
recovery runs through the cloid channel (the venue's echo of the
journal's client_order_id). The acceptance drill converges the full
lifecycle to a clean report.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Side, Venue
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderStatus,
)
from quantmesh.execution.journal import OrderJournal
from quantmesh.execution.reconciliation import FindingKind, Severity
from quantmesh.hyperliquid.errors import HyperliquidUnavailableError
from quantmesh.hyperliquid.exchange import (
    BrokerOrder,
    HyperliquidExecutionAdapter,
    ScriptedExchangeTransport,
    build_snapshot,
)
from quantmesh.hyperliquid.market_data import FIXTURE_DIR
from quantmesh.hyperliquid.reconciliation import (
    HYPERLIQUID_STATUS_TO_DOMAIN,
    apply_reconciliation,
    run_reconciliation,
)

T0 = 1754600400000
P1 = datetime.fromtimestamp(T0 / 1000, tz=UTC)
SCRIPT = FIXTURE_DIR / "wire_exchange_script.jsonl"

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)
CID_1001 = "5e8f2c4d7a1b9e3f6c0d4a2b8e5f7c1d"
CID_1002 = "9d3a6c1e8b2f4570a1c9e3d5b7f2a84c"

OPEN_1001 = {
    "coin": "BTC",
    "oid": 1001,
    "side": "B",
    "sz": "1.0",
    "limitPx": "107.2",
    "timestamp": T0,
    "cloid": "0x" + CID_1001,
}
OPEN_1002 = {
    "coin": "BTC",
    "oid": 1002,
    "side": "A",
    "sz": "1.0",
    "limitPx": "107.4",
    "timestamp": T0 + 240_000,
    "cloid": "0x" + CID_1002,
}
FILL_92 = {
    "coin": "BTC",
    "oid": 1002,
    "tid": 92,
    "px": "107.4",
    "sz": "0.6",
    "side": "A",
    "time": T0 + 300_000,
    "fee": "0.07",
    "cloid": "0x" + CID_1002,
}
FILL_93 = {
    "coin": "BTC",
    "oid": 1002,
    "tid": 93,
    "px": "107.5",
    "sz": "0.4",
    "side": "A",
    "time": T0 + 301_000,
    "fee": "0.05",
    "cloid": "0x" + CID_1002,
}


def make_order(
    journal: OrderJournal,
    *,
    order_id: str,
    side: Side = Side.BUY,
    quantity: float = 1.0,
    limit_price: float | None = 107.2,
    client_order_id: str | None = None,
    broker_order_id: str | None = None,
) -> Order:
    order = Order.from_request(
        OrderRequest(
            instrument=BTC,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
        ),
        order_id=order_id,
        created_at=P1,
    )
    order = order.model_copy(
        update={
            "client_order_id": client_order_id or order_id,
            "broker_order_id": broker_order_id,
        }
    )
    journal.record(order)
    return order


def at(journal: OrderJournal, order: Order, event_type: OrderEventType) -> Order:
    updated = OrderStateMachine.apply(
        order, event_type, timestamp=P1 + timedelta(minutes=1)
    )
    return journal.update(updated)


def fill_at(
    journal: OrderJournal,
    order: Order,
    *,
    quantity: float,
    price: float,
    fill_id: str,
    fee: float,
) -> Order:
    fill = Fill(
        timestamp=P1 + timedelta(minutes=1),
        quantity=quantity,
        price=price,
        broker_fill_id=fill_id,
        fee=fee,
    )
    return journal.update(
        OrderStateMachine.apply(
            order, OrderEventType.FILL, fill=fill, timestamp=fill.timestamp
        )
    )


def snapshot(open_orders=(), fills=(), positions=()):  # noqa: ANN001
    return build_snapshot(
        open_orders=list(open_orders),
        fills=list(fills),
        positions=list(positions),
    )


def run(journal: OrderJournal, open_orders=(), fills=(), positions=()):  # noqa: ANN001
    return run_reconciliation(snapshot(open_orders, fills, positions), journal)


# --- status derivation ------------------------------------------------------------


def test_status_table_declares_the_venue_vocabulary() -> None:
    assert HYPERLIQUID_STATUS_TO_DOMAIN["open"] is OrderStatus.ACCEPTED
    assert HYPERLIQUID_STATUS_TO_DOMAIN["filled"] is OrderStatus.FILLED
    assert (
        HYPERLIQUID_STATUS_TO_DOMAIN["partially_filled"]
        is OrderStatus.PARTIALLY_FILLED
    )
    assert HYPERLIQUID_STATUS_TO_DOMAIN["canceled"] is OrderStatus.CANCELED
    assert HYPERLIQUID_STATUS_TO_DOMAIN["rejected"] is OrderStatus.REJECTED


def test_unmappable_surface_status_fails_closed_as_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    at(journal, order, OrderEventType.ACCEPTED)
    weird = BrokerOrder(
        oid=1001,
        coin="BTC",
        side=Side.SELL,
        quantity=1.0,
        limit_price=107.2,
        created=P1,
        cloid="0x" + CID_1001,
        status="weird",
    )
    empty = snapshot()
    report = run_reconciliation(
        empty.model_copy(update={"orders": [weird]}), journal
    )
    (outcome,) = report.outcomes
    assert outcome.status == "divergent"
    (finding,) = outcome.findings
    assert finding.kind is FindingKind.STATUS
    assert finding.severity is Severity.ERROR


def test_open_order_against_live_journal_is_pending_and_clean(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, open_orders=[OPEN_1001])

    (outcome,) = report.outcomes
    assert outcome.status == "pending"
    assert outcome.internal_order_id == "o1"
    assert outcome.findings == []
    assert report.missing_internal == []


def test_fills_complete_inactive_row_derives_filled(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, fills=[FILL_92, FILL_93])

    (outcome,) = report.outcomes
    # fills 0.6 + 0.4 == quantity 1.0 → derived FILLED; the journal is
    # still ACCEPTED, so the venue is ahead: pending, adoptable progress.
    assert outcome.status == "pending"
    assert outcome.findings == []


def test_inactive_row_with_terminal_journal_matches(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)
    order = fill_at(journal, order, quantity=0.4, price=107.5, fill_id="93", fee=0.05)
    assert order.status is OrderStatus.FILLED

    report = run(journal, fills=[FILL_92, FILL_93])

    (outcome,) = report.outcomes
    assert outcome.status == "matched"
    assert outcome.findings == []


def test_inactive_partial_fills_with_live_journal_derive_canceled(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, fills=[FILL_92])  # 0.6 of 1.0, then the venue is silent

    (outcome,) = report.outcomes
    # The venue no longer lists the order and reports no further fills:
    # the order is dead → derived CANCELED → the venue is ahead.
    assert outcome.status == "pending"
    assert outcome.findings == []


def test_journal_filled_ahead_of_inactive_venue_is_drift(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)
    order = fill_at(journal, order, quantity=0.4, price=107.5, fill_id="93", fee=0.05)
    assert order.status is OrderStatus.FILLED

    # The venue only reports the first fill: it is behind the journal.
    report = run(journal, fills=[FILL_92])

    (outcome,) = report.outcomes
    assert outcome.status == "divergent"
    assert any(finding.kind is FindingKind.STATUS for finding in outcome.findings)
    assert any(finding.kind is FindingKind.QUANTITY for finding in outcome.findings)


def test_open_venue_row_against_canceled_journal_is_drift(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    at(journal, order, OrderEventType.ACCEPTED)
    at(journal, order, OrderEventType.CANCELED)

    report = run(journal, open_orders=[OPEN_1001])

    (outcome,) = report.outcomes
    assert outcome.status == "divergent"
    (finding,) = outcome.findings
    assert finding.kind is FindingKind.STATUS


def test_open_venue_row_tolerates_journal_partial_fills(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="1", fee=0.07)
    assert order.status is OrderStatus.PARTIALLY_FILLED

    # The venue still lists the order (remaining size) and reports the fill.
    report = run(
        journal,
        open_orders=[OPEN_1001],
        fills=[{**FILL_92, "oid": 1001, "tid": 1, "side": "B"}],
    )
    (outcome,) = report.outcomes
    assert outcome.status == "pending"
    assert outcome.findings == []


# --- identity channels ------------------------------------------------------------


def test_cloid_channel_recovers_a_lost_ack_mapping(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    # Placed but unacknowledged: no broker id yet.
    make_order(journal, order_id="o1", client_order_id=CID_1001)

    report = run(journal, open_orders=[OPEN_1001])

    (outcome,) = report.outcomes
    assert outcome.status == "pending"
    assert outcome.recovered_via_remark
    (finding,) = outcome.findings
    assert finding.kind is FindingKind.MAPPING
    assert finding.severity is Severity.WARNING


def test_fills_only_rows_recover_identity_via_cloid(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    # The open row aged out of the venue's surface; only the fill rows
    # remain, and they carry the venue's cloid echo.
    make_order(journal, order_id="o2", limit_price=107.4, client_order_id=CID_1002)

    report = run(journal, fills=[FILL_92, FILL_93])

    (outcome,) = report.outcomes
    assert outcome.status == "pending"
    assert outcome.recovered_via_remark
    assert any(
        f.kind is FindingKind.MAPPING and f.severity is Severity.WARNING
        for f in outcome.findings
    )

    result = apply_reconciliation(report, journal, snapshot(fills=[FILL_92, FILL_93]))
    assert journal.get("o2").broker_order_id == "1002"
    assert journal.get("o2").status is OrderStatus.FILLED
    assert any("re-stamped" in note for note in result.notes)


def test_recovered_mapping_re_stamps_the_oid_at_adoption(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    make_order(journal, order_id="o1", client_order_id=CID_1001)

    report = run(journal, open_orders=[OPEN_1001])
    result = apply_reconciliation(report, journal, snapshot(open_orders=[OPEN_1001]))

    assert "o1" in result.updated
    assert journal.get("o1").broker_order_id == "1001"
    assert journal.get("o1").status is OrderStatus.ACCEPTED
    assert any("re-stamped" in note for note in result.notes)


def test_ambiguous_channels_are_divergent(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    make_order(
        journal, order_id="o1", client_order_id=CID_1001, broker_order_id="1001"
    )
    make_order(journal, order_id="o2", client_order_id=CID_1002)

    # The venue row for 1001 carries o1's oid but o2's cloid.
    stolen = {**OPEN_1001, "cloid": "0x" + CID_1002}
    report = run(journal, open_orders=[stolen])

    (outcome,) = report.outcomes
    assert outcome.status == "divergent"
    assert any(
        finding.kind is FindingKind.MAPPING and finding.severity is Severity.ERROR
        for finding in outcome.findings
    )


def test_venue_order_without_journal_counterpart_is_missing(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )

    report = run(journal, open_orders=[OPEN_1001, OPEN_1002])

    (matched,) = [o for o in report.outcomes if o.internal_order_id == "o1"]
    (unknown,) = [o for o in report.outcomes if o.internal_order_id is None]
    assert matched.status == "pending"
    assert unknown.status == "missing"
    assert any(f.kind is FindingKind.MAPPING for f in unknown.findings)


def test_live_journal_order_without_venue_row_is_missing_internal(
    tmp_path,  # noqa: ANN001
) -> None:
    journal = OrderJournal(tmp_path)
    order = make_order(journal, order_id="o1", client_order_id=CID_1001)
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal)

    assert report.missing_internal == ["o1"]
    assert report.counts["missing"] == 1


def test_journal_with_fills_the_venue_forgot_is_missing_internal(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)

    report = run(journal)  # the venue reports nothing at all

    assert report.missing_internal == ["o2"]


def test_ack_terminal_unclaimed_order_is_matched_and_silent(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    # The venue confirmed the cancel (the order id is stamped); its
    # surface is now silent, which is venue truth, not a lost order.
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    at(journal, order, OrderEventType.ACCEPTED)
    at(journal, order, OrderEventType.CANCELED)  # the venue forgot the order

    report = run(journal)

    (outcome,) = report.outcomes
    assert outcome.status == "matched"
    assert outcome.broker_order_id == "1001"
    assert outcome.findings == []


def test_ack_terminal_without_venue_identity_notes_the_silence(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(journal, order_id="o1", client_order_id=CID_1001)
    # A per-order place error rejects the order; the venue never listed it.
    at(journal, order, OrderEventType.REJECTED)

    report = run(journal)

    (outcome,) = report.outcomes
    assert outcome.status == "matched"
    (finding,) = outcome.findings
    assert finding.kind is FindingKind.MAPPING
    assert finding.severity is Severity.WARNING


# --- quantity, price, fee, fill-id comparisons -----------------------------------


def test_order_quantity_drift_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(journal, order_id="o1", client_order_id=CID_1001)
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, open_orders=[{**OPEN_1001, "sz": "0.5"}])

    (outcome,) = report.outcomes
    assert outcome.status == "divergent"
    assert any(finding.kind is FindingKind.QUANTITY for finding in outcome.findings)


def test_inactive_rows_skip_the_order_quantity_compare(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )

    report = run(journal, fills=[FILL_92, FILL_93])

    (outcome,) = report.outcomes
    # The venue no longer declares the original size; only the fills
    # compare, and the venue is ahead.
    assert outcome.findings == []


def test_limit_price_drift_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(journal, order_id="o1", client_order_id=CID_1001)
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, open_orders=[{**OPEN_1001, "limitPx": "105.0"}])

    (outcome,) = report.outcomes
    assert any(finding.kind is FindingKind.PRICE for finding in outcome.findings)


def test_average_price_drift_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)
    order = fill_at(journal, order, quantity=0.4, price=107.5, fill_id="93", fee=0.05)
    assert order.status is OrderStatus.FILLED

    # journal avg 107.44 vs venue avg 108.0
    report = run(journal, fills=[{**FILL_92, "px": "108.0"}, {**FILL_93, "px": "108.0"}])

    (outcome,) = report.outcomes
    assert any(finding.kind is FindingKind.PRICE for finding in outcome.findings)


def test_fill_without_fee_is_missing_data(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )

    fee_less = {k: v for k, v in FILL_92.items() if k != "fee"}
    report = run(journal, fills=[fee_less])

    (outcome,) = report.outcomes
    assert any(
        finding.kind is FindingKind.MISSING_DATA for finding in outcome.findings
    )


def test_fee_drift_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)
    order = fill_at(journal, order, quantity=0.4, price=107.5, fill_id="93", fee=0.05)
    assert order.status is OrderStatus.FILLED

    report = run(journal, fills=[FILL_92, {**FILL_93, "fee": "0.50"}])

    (outcome,) = report.outcomes
    assert any(finding.kind is FindingKind.FEE for finding in outcome.findings)


def test_stamped_fill_the_venue_forgot_is_revoked(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)

    # The venue only reports tid 93 now; the stamped 92 is revoked.
    report = run(journal, fills=[FILL_93])

    (outcome,) = report.outcomes
    assert any(
        finding.kind is FindingKind.REVOKED_FILL for finding in outcome.findings
    )


# --- positions --------------------------------------------------------------------


def test_unexplained_venue_position_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)

    report = run(
        journal,
        positions=[
            {
                "coin": "BTC",
                "szi": "1.0",
                "leverage": {"type": "cross", "value": 3},
            }
        ],
    )

    (finding,) = report.position_findings
    assert finding.kind is FindingKind.POSITION
    assert finding.severity is Severity.ERROR


def test_journal_net_without_venue_position_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)
    order = fill_at(journal, order, quantity=0.4, price=107.5, fill_id="93", fee=0.05)
    assert order.status is OrderStatus.FILLED

    report = run(journal)

    assert any(
        finding.kind is FindingKind.POSITION for finding in report.position_findings
    )


def test_position_drift_beyond_tolerance_is_a_finding(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    order = at(journal, order, OrderEventType.ACCEPTED)
    order = fill_at(journal, order, quantity=0.6, price=107.4, fill_id="92", fee=0.07)

    report = run(
        journal,
        positions=[
            {"coin": "BTC", "szi": "0.7", "leverage": {"type": "cross", "value": 3}}
        ],
    )
    assert any(
        finding.kind is FindingKind.POSITION for finding in report.position_findings
    )


# --- adoption ---------------------------------------------------------------------


def test_adoption_stamps_fills_and_lands_filled(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, fills=[FILL_92, FILL_93])
    result = apply_reconciliation(
        report, journal, snapshot(fills=[FILL_92, FILL_93])
    )

    assert "o2" in result.updated
    updated = journal.get("o2")
    assert updated.status is OrderStatus.FILLED
    assert updated.filled_quantity == 1.0
    assert [(f.broker_fill_id, f.fee) for f in updated.fills] == [
        ("92", 0.07),
        ("93", 0.05),
    ]
    assert updated.fills[0].timestamp == P1 + timedelta(minutes=5)


def test_adoption_is_idempotent(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    snap = snapshot(fills=[FILL_92, FILL_93])
    first = apply_reconciliation(run(journal, fills=[FILL_92, FILL_93]), journal, snap)
    second = apply_reconciliation(
        run(journal, fills=[FILL_92, FILL_93]), journal, snap
    )

    assert "o2" in first.updated
    updated = journal.get("o2")
    assert updated.status is OrderStatus.FILLED
    assert updated.filled_quantity == 1.0
    assert len(updated.fills) == 2
    # A second apply imports nothing new: the journal is untouched.
    assert second.updated["o2"].events == updated.events
    assert second.refused == []


def test_adoption_refuses_a_fee_less_fill(tmp_path) -> None:  # noqa: ANN001
    """The run can classify pending while the apply snapshot lost the fee
    (snapshots are taken per call); adoption refuses the fee-less fill."""
    journal = OrderJournal(tmp_path)
    make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )

    report = run(journal, fills=[FILL_92])
    fee_less = {k: v for k, v in FILL_92.items() if k != "fee"}
    result = apply_reconciliation(report, journal, snapshot(fills=[fee_less]))

    assert result.updated == {}
    assert result.refused == ["o2"]
    assert any("has no fee" in note for note in result.notes)


def test_adoption_refuses_divergent_pairs(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    shrunk = {**OPEN_1001, "sz": "0.5"}
    report = run(journal, open_orders=[shrunk])
    result = apply_reconciliation(report, journal, snapshot(open_orders=[shrunk]))

    assert result.updated == {}
    assert result.refused == ["o1"]


def test_adoption_refuses_an_overfill(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )

    # 0.6 + 0.5 > quantity 1.0: the second fill overfills the order.
    overfill = {**FILL_93, "sz": "0.5"}
    report = run(journal, fills=[FILL_92, overfill])
    result = apply_reconciliation(
        report, journal, snapshot(fills=[FILL_92, overfill])
    )

    assert result.updated == {}
    assert result.refused == ["o2"]
    assert any("refused" in note for note in result.notes)


def test_adoption_skips_ack_terminal_orders_silently(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o1",
        client_order_id=CID_1001,
        broker_order_id="1001",
    )
    at(journal, order, OrderEventType.ACCEPTED)
    at(journal, order, OrderEventType.CANCELED)  # the venue forgot it

    report = run(journal)
    result = apply_reconciliation(report, journal, snapshot())

    assert result.updated == {}
    assert result.refused == []
    assert journal.get("o1").status is OrderStatus.CANCELED


def test_adoption_applies_a_derived_canceled(tmp_path) -> None:  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    order = make_order(
        journal,
        order_id="o2",
        limit_price=107.4,
        client_order_id=CID_1002,
        broker_order_id="1002",
    )
    at(journal, order, OrderEventType.ACCEPTED)

    report = run(journal, fills=[FILL_92])  # partial fills, then venue silence
    apply_reconciliation(report, journal, snapshot(fills=[FILL_92]))

    updated = journal.get("o2")
    assert updated.status is OrderStatus.CANCELED
    assert updated.filled_quantity == 0.6
    # The cancel event is stamped with the venue's latest evidence.
    assert updated.events[-1].timestamp == P1 + timedelta(minutes=5)


# --- acceptance drill -------------------------------------------------------------


def test_acceptance_drill_converges_to_a_clean_report(tmp_path) -> None:  # noqa: ANN001
    """The Phase B drill: lost ack → cloid recovery → cancel → fills →
    positions, converging to 0 findings and 0 refusals."""
    transport = ScriptedExchangeTransport(SCRIPT)
    journal = OrderJournal(tmp_path)
    adapter = HyperliquidExecutionAdapter(transport, journal)

    # p1 21:00:00Z — place 1001; the venue records it but the ack is lost.
    transport.advance_to(P1)
    with pytest.raises(HyperliquidUnavailableError, match="acknowledgement never arrived"):
        adapter.place(
            OrderRequest(
                instrument=BTC, side=Side.SELL, quantity=1.0, limit_price=107.2
            ),
            order_id="ord-1001",
            created_at=P1,
            client_order_id=CID_1001,
        )
    assert journal.get("ord-1001").status is OrderStatus.PENDING

    # p2 21:01:00Z — the venue lists 1001; the cloid channel recovers the
    # mapping (MAPPING/WARNING note, non-blocking) and adoption re-stamps
    # the oid and adopts ACCEPTED.
    transport.advance_to(P1 + timedelta(minutes=1))
    report = run_reconciliation(transport.snapshot(), journal)
    (recovered,) = report.outcomes
    assert recovered.recovered_via_remark
    assert [f.kind for f in recovered.findings] == [FindingKind.MAPPING]
    result = apply_reconciliation(report, journal, transport.snapshot())
    assert journal.get("ord-1001").broker_order_id == "1001"
    assert journal.get("ord-1001").status is OrderStatus.ACCEPTED
    assert any("re-stamped" in note for note in result.notes)

    # p3 21:02:00Z — the order rests; the run is clean. Cancel it by oid.
    transport.advance_to(P1 + timedelta(minutes=2))
    report = run_reconciliation(transport.snapshot(), journal)
    assert report.findings == []
    adapter.cancel(journal.get("ord-1001"), at=P1 + timedelta(minutes=2))
    assert journal.get("ord-1001").status is OrderStatus.CANCELED

    # p4 21:03:00Z — the venue's surface is silent after the cancel; the
    # ack-terminal order is matched, nothing is missing or refused.
    transport.advance_to(P1 + timedelta(minutes=3))
    report = run_reconciliation(transport.snapshot(), journal)
    assert report.counts == {"matched": 1, "pending": 0, "missing": 0, "divergent": 0}
    assert report.findings == []
    result = apply_reconciliation(report, journal, transport.snapshot())
    assert result.updated == {}
    assert result.refused == []

    # p5 21:04:00Z — place 1002; it rests cleanly.
    transport.advance_to(P1 + timedelta(minutes=4))
    adapter.place(
        OrderRequest(
            instrument=BTC, side=Side.BUY, quantity=1.0, limit_price=107.4
        ),
        order_id="ord-1002",
        created_at=P1 + timedelta(minutes=4),
        client_order_id=CID_1002,
    )
    assert journal.get("ord-1002").status is OrderStatus.ACCEPTED
    report = run_reconciliation(transport.snapshot(), journal)
    assert report.findings == []

    # p6 21:06:00Z — fills 0.6 @ 107.4 + 0.4 @ 107.5 and a +1.0 BTC
    # position. The first pass sees the venue ahead (fills and position
    # unexplained); adoption imports them; the second pass is clean.
    transport.advance_to(P1 + timedelta(minutes=6))
    report = run_reconciliation(transport.snapshot(), journal)
    result = apply_reconciliation(report, journal, transport.snapshot())
    assert set(result.updated) == {"ord-1002"}
    assert result.refused == []
    assert journal.get("ord-1002").status is OrderStatus.FILLED

    final = run_reconciliation(transport.snapshot(), journal)
    assert final.counts == {"matched": 2, "pending": 0, "missing": 0, "divergent": 0}
    assert final.findings == []
    assert apply_reconciliation(final, journal, transport.snapshot()).refused == []
