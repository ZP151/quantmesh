"""Broker/paper reconciliation tests (issue #28, Phase D, ADR-0006).

The reconciliation service is the guarded bridge between the broker's
simulated account and the internal order journal: identity comes only
from the journal, broker-ahead is progress, broker-behind is drift, and
nothing is ever adopted except matched/pending pairs without blocking
findings. The disconnect/reconnect drill at the bottom replays the
full lost-ack lifecycle deterministically.
"""

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Side,
    Venue,
)
from quantmesh.domain.orders import Fill, Order, OrderEventType, OrderStateMachine
from quantmesh.execution import OrderJournal
from quantmesh.moomoo import (
    ExecutionSnapshot,
    FindingKind,
    MoomooExecutionAdapter,
    OpenDUnavailableError,
    ReconcileTolerance,
    ReconciliationReport,
    Severity,
    SimulatedFixtureTransport,
    apply_reconciliation,
    run_reconciliation,
)

INSTRUMENT = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    metadata={"market": "US"},
)
CREATED_AT = datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC)
T0 = datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 8, 13, 30, 1, tzinfo=UTC)


def make_request(**overrides: object) -> OrderRequest:
    values: dict[str, object] = {
        "instrument": INSTRUMENT,
        "side": Side.BUY,
        "quantity": 100.0,
        "limit_price": 210.0,
        "client_order_id": "QM-1",
    }
    values.update(overrides)
    return OrderRequest(**values)


def make_order(order_id: str = "order-1", **overrides: object) -> Order:
    values: dict[str, object] = {
        "order_id": order_id,
        "instrument": INSTRUMENT,
        "side": Side.BUY,
        "quantity": 100.0,
        "order_type": "limit",
        "limit_price": 210.0,
        "created_at": CREATED_AT,
        "client_order_id": "QM-1",
    }
    values.update(overrides)
    return Order(**values)


def fill_order(
    order: Order, qty: float, price: float, *, broker_fill_id: str, fee: float
) -> Order:
    return OrderStateMachine.apply(
        order,
        OrderEventType.FILL,
        fill=Fill(
            timestamp=T1,
            quantity=qty,
            price=price,
            broker_fill_id=broker_fill_id,
            fee=fee,
        ),
        timestamp=T1,
    )


def _vt(value: str) -> datetime:
    """Fixture venue-local wall clock (US = Eastern) → aware UTC."""
    return (
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .astimezone(UTC)
    )


def broker_order(**overrides: object) -> dict:
    values: dict[str, object] = {
        "order_id": "B-1",
        "code": "US.AAPL",
        "qty": 100,
        "price": 210.0,
        "dealt_qty": 100,
        "dealt_avg_price": 210.0,
        "order_status": "FILLED_ALL",
        "trd_side": "BUY",
        "create_time": "2026-08-08 09:30:00",
        "updated_time": "2026-08-08 09:30:01",
        "remark": "QM-1",
    }
    values.update(overrides)
    return values


def broker_deal(**overrides: object) -> dict:
    values: dict[str, object] = {
        "deal_id": "D-1",
        "order_id": "B-1",
        "code": "US.AAPL",
        "qty": 100,
        "price": 210.0,
        "trd_side": "BUY",
        "create_time": "2026-08-08 09:30:01",
        "fee": 0.5,
    }
    values.update(overrides)
    return values


def snapshot(**overrides: object) -> ExecutionSnapshot:
    """A model-valid snapshot; wall-clock strings go through the same
    venue-local → UTC conversion the wire path applies."""
    values: dict[str, object] = {
        "orders": [broker_order()],
        "deals": [broker_deal()],
        "positions": [{"code": "US.AAPL", "qty": 100}],
    }
    values.update(overrides)
    orders = []
    for row in values["orders"]:
        row = dict(row)
        for key in ("create_time", "updated_time"):
            if isinstance(row.get(key), str):
                row[key] = _vt(row[key])
        orders.append(row)
    deals = []
    for row in values["deals"]:
        row = dict(row)
        if isinstance(row.get("create_time"), str):
            row["create_time"] = _vt(row["create_time"])
        deals.append(row)
    return ExecutionSnapshot(orders=orders, deals=deals, positions=values["positions"])


def reconcile(
    snap: ExecutionSnapshot, journal: OrderJournal, **tolerance: object
) -> ReconciliationReport:
    return run_reconciliation(snap, journal, ReconcileTolerance(**tolerance))


def journal_of(*orders: Order, tmp_path: Path) -> OrderJournal:
    journal = OrderJournal(root=tmp_path / "orders")
    for order in orders:
        journal.record(order)
    return journal


# --- classification: clean pairs ---------------------------------------------------

def test_matched_terminal_pair_is_clean(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(), journal)

    assert report.counts == {"matched": 1, "pending": 0, "missing": 0, "divergent": 0}
    assert report.findings == []


def test_broker_ahead_is_pending_progress(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(positions=[]), journal)

    assert report.counts == {"matched": 0, "pending": 1, "missing": 0, "divergent": 0}
    assert report.findings == []


def test_journal_ahead_of_broker_is_divergent(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)
    snap = snapshot(orders=[broker_order(order_status="SUBMITTED")], deals=[])

    report = reconcile(snap, journal)

    assert report.counts["divergent"] == 1
    assert any(f.kind is FindingKind.STATUS for f in report.findings)


def test_missing_broker_order_is_flagged(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(order_id="B-9", remark="nobody")]), journal)

    # "missing" counts both directions: broker orders without a journal
    # counterpart and journal orders the broker has not confirmed.
    assert report.counts["missing"] == 2
    assert any(
        outcome.broker_order_id == "B-9" and outcome.status == "missing"
        for outcome in report.outcomes
    )
    assert "order-1" in report.missing_internal


def test_unadopted_journal_order_is_listed_as_missing_internal(tmp_path: Path) -> None:
    journal = journal_of(make_order(), tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[]), journal)

    assert report.missing_internal == ["order-1"]


# --- classification: identity -------------------------------------------------------

def test_ambiguous_mapping_is_divergent(tmp_path: Path) -> None:
    order_a = make_order("order-a", broker_order_id="B-1", client_order_id="QM-X")
    order_b = make_order("order-b", client_order_id="QM-1")
    journal = journal_of(order_a, order_b, tmp_path=tmp_path)

    report = reconcile(snapshot(), journal)

    assert report.counts["divergent"] == 1
    assert any(
        f.kind is FindingKind.MAPPING and f.severity is Severity.ERROR
        for f in report.findings
    )


def test_remark_recovery_is_noted_not_silent(tmp_path: Path) -> None:
    journal = journal_of(make_order(), tmp_path=tmp_path)

    report = reconcile(snapshot(), journal)

    outcome = report.outcomes[0]
    assert outcome.status == "pending"
    assert outcome.recovered_via_remark is True
    assert any(
        f.kind is FindingKind.MAPPING and f.severity is Severity.WARNING
        for f in outcome.findings
    )


# --- classification: status ----------------------------------------------------------

@pytest.mark.parametrize("status", ["TIMEOUT", "DISABLED", "DELETED", "FILL_CANCELLED"])
def test_unmappable_statuses_fail_closed(status: str, tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(order_status=status)]), journal)

    assert report.counts["divergent"] == 1
    assert any(f.kind is FindingKind.STATUS and f.observed == status for f in report.findings)


def test_status_drift_broker_behind_is_divergent(tmp_path: Path) -> None:
    order = OrderStateMachine.apply(make_order(broker_order_id="B-1"), OrderEventType.ACCEPTED)
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(order_status="UNSUBMITTED")]), journal)

    assert report.counts["divergent"] == 1
    assert any(f.kind is FindingKind.STATUS for f in report.findings)


# --- classification: quantities, prices, fees, times ----------------------------------

def test_quantity_drift_is_a_finding(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(qty=90)]), journal)

    assert any(f.kind is FindingKind.QUANTITY for f in report.findings)


def test_journal_fills_beyond_broker_dealt_qty_is_drift(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(dealt_qty=50)]), journal)

    assert any(f.kind is FindingKind.QUANTITY for f in report.findings)


def test_limit_price_drift_is_a_finding(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(price=215.0)]), journal)

    assert any(f.kind is FindingKind.PRICE for f in report.findings)


def test_execution_price_drift_is_a_finding(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(dealt_avg_price=209.0)]), journal)

    assert any(f.kind is FindingKind.PRICE for f in report.findings)


def test_fee_drift_is_a_finding(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(deals=[broker_deal(fee=9.0)]), journal)

    assert any(f.kind is FindingKind.FEE for f in report.findings)


def test_fee_less_deals_are_missing_data(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(deals=[broker_deal(fee=None)]), journal)

    assert any(f.kind is FindingKind.MISSING_DATA for f in report.findings)


def test_journal_fees_without_broker_deals_fail_closed(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(deals=[]), journal)

    assert any(f.kind is FindingKind.FEE for f in report.findings)


def test_revoked_fill_is_a_finding(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(deals=[]), journal)

    assert any(f.kind is FindingKind.REVOKED_FILL for f in report.findings)


def test_unhealthy_deal_is_not_adoptable(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(deals=[broker_deal(status="CANCELLED")]), journal)

    assert any(f.kind is FindingKind.REVOKED_FILL for f in report.findings)


def test_creation_time_drift_is_a_finding(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(orders=[broker_order(create_time="2026-08-08 09:45:00")]), journal)

    assert any(f.kind is FindingKind.TIMESTAMP for f in report.findings)


# --- classification: positions ---------------------------------------------------------

def test_unexplained_broker_position_is_a_finding(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    report = reconcile(snapshot(positions=[{"code": "US.AAPL", "qty": 500}]), journal)

    assert any(f.kind is FindingKind.POSITION for f in report.position_findings)


def test_journal_position_without_broker_position_is_a_finding(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)

    report = reconcile(snapshot(positions=[]), journal)

    assert any(f.kind is FindingKind.POSITION for f in report.position_findings)


def test_position_drift_respects_tolerance(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)
    snap = snapshot(positions=[{"code": "US.AAPL", "qty": 99}])

    strict = reconcile(snap, journal)
    lenient = reconcile(snap, journal, position_qty_bps=200)

    assert any(f.kind is FindingKind.POSITION for f in strict.findings)
    assert lenient.findings == []


# --- tolerances -------------------------------------------------------------------------

def test_declared_tolerances_absorb_drift(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)
    snap = snapshot(
        orders=[broker_order(qty=101, price=211.0)],
        deals=[broker_deal(fee=0.6)],
        positions=[],
    )

    strict = reconcile(snap, journal)
    lenient = reconcile(snap, journal, qty_bps=200, price_bps=500, fee_abs=1.0)

    assert strict.findings
    assert lenient.findings == []


def test_reports_are_byte_reproducible(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)

    first = reconcile(snapshot(), journal)
    second = reconcile(snapshot(), journal)

    assert first.model_dump_json() == second.model_dump_json()


# --- adoption -----------------------------------------------------------------------------

def test_apply_refuses_divergent_and_missing(tmp_path: Path) -> None:
    order_a = make_order("order-a", broker_order_id="B-1", client_order_id="QM-X")
    order_b = make_order("order-b", client_order_id="QM-1")
    journal = journal_of(order_a, order_b, tmp_path=tmp_path)
    snap = snapshot(orders=[broker_order(), broker_order(order_id="B-9", remark="ghost")])

    result = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    assert result.updated == {}
    assert sorted(result.refused) == ["B-9", "order-a"]


def test_apply_imports_pending_progress_and_re_stamps_recovered_ids(tmp_path: Path) -> None:
    journal = journal_of(make_order(), tmp_path=tmp_path)
    snap = snapshot(orders=[broker_order(order_status="SUBMITTED")], deals=[], positions=[])

    result = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    updated = journal.get("order-1")
    assert "order-1" in result.updated
    assert updated.broker_order_id == "B-1"
    assert updated.status.value == "accepted"


def test_apply_adopts_fills_to_terminal_filled(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)
    snap = snapshot()

    apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    updated = journal.get("order-1")
    assert updated.status.value == "filled"
    assert updated.filled_quantity == 100.0
    assert updated.fills[0].broker_fill_id == "D-1"
    assert updated.fills[0].fee == 0.5


def test_apply_refuses_fee_less_deals(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)
    snap = snapshot(deals=[broker_deal(fee=None)])

    result = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    assert result.updated == {}
    assert result.refused == ["order-1"]


def test_apply_refuses_filled_without_completed_fills(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)
    snap = snapshot(orders=[broker_order(dealt_qty=40)], deals=[broker_deal(qty=40)])

    result = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    assert result.updated == {}
    assert result.refused == ["order-1"]
    assert any("FILLED" in note for note in result.notes)


def test_apply_adopts_canceled_terminal_event(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)
    snap = snapshot(
        orders=[broker_order(order_status="CANCELLED_ALL")], deals=[], positions=[]
    )

    result = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    updated = journal.get("order-1")
    assert updated.status.value == "canceled"
    assert updated.events[-1].event_type is OrderEventType.CANCELED
    assert "order-1" in result.updated


def test_apply_adopts_rejected_with_broker_message(tmp_path: Path) -> None:
    journal = journal_of(make_order(broker_order_id="B-1"), tmp_path=tmp_path)
    snap = snapshot(
        orders=[broker_order(order_status="FAILED", last_err_msg="insufficient balance")],
        deals=[],
        positions=[],
    )

    apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    updated = journal.get("order-1")
    assert updated.status.value == "rejected"
    assert updated.events[-1].reason == "insufficient balance"


def test_apply_second_run_on_matched_pair_changes_nothing(tmp_path: Path) -> None:
    order = fill_order(
        make_order(broker_order_id="B-1"), 100, 210.0, broker_fill_id="D-1", fee=0.5
    )
    journal = journal_of(order, tmp_path=tmp_path)
    snap = snapshot()

    first = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)
    second = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)

    assert first.refused == []
    assert second.refused == []
    assert journal.get("order-1").status.value == "filled"
    assert [f.broker_fill_id for f in journal.get("order-1").fills] == ["D-1"]


# --- the disconnect/reconnect drill ------------------------------------------------------

def test_lost_ack_drill_recovers_via_remark_and_converges(tmp_path: Path) -> None:
    script = [
        {
            "now": "2026-08-08T13:30:00+00:00",
            "orders": [],
            "deals": [],
            "positions": [],
            "lost_acks": ["B-1"],
        },
        {
            "now": "2026-08-08T13:31:00+00:00",
            "orders": [broker_order(order_status="SUBMITTED")],
            "deals": [],
            "positions": [],
        },
        {
            "now": "2026-08-08T13:32:00+00:00",
            "orders": [broker_order()],
            "deals": [broker_deal()],
            "positions": [{"code": "US.AAPL", "qty": 100}],
        },
    ]
    transport = SimulatedFixtureTransport(script)
    adapter = MoomooExecutionAdapter(transport)
    journal = OrderJournal(root=tmp_path / "orders")

    # The placement ack is lost; the order is recorded anyway — exactly
    # the state the remark channel must recover.
    with pytest.raises(OpenDUnavailableError, match="acknowledgement never arrived"):
        adapter.place(make_request(), order_id="order-1", created_at=T0)
    journal.record(Order.from_request(make_request(), order_id="order-1", created_at=T0))

    # Phase 2: the broker confirms the order; remark recovery maps it and
    # adoption imports ACCEPTED plus the broker id.
    transport.advance_to(script[1]["now"])
    snap = transport.snapshot()
    phase2 = run_reconciliation(snap, journal)
    assert phase2.counts["pending"] == 1
    assert phase2.outcomes[0].recovered_via_remark is True
    applied = apply_reconciliation(phase2, journal, snap)
    assert applied.refused == []
    assert journal.get("order-1").broker_order_id == "B-1"

    # Phase 3: the fill lands; adoption imports it and the order fills.
    transport.advance_to(script[2]["now"])
    snap = transport.snapshot()
    applied = apply_reconciliation(run_reconciliation(snap, journal), journal, snap)
    assert applied.refused == []
    order = journal.get("order-1")
    assert order.status.value == "filled"
    assert order.filled_quantity == 100.0
    assert [(f.broker_fill_id, f.fee) for f in order.fills] == [("D-1", 0.5)]

    # Final run: the pair is matched with no findings.
    final = run_reconciliation(transport.snapshot(), journal)
    assert final.counts == {"matched": 1, "pending": 0, "missing": 0, "divergent": 0}
    assert final.findings == []
