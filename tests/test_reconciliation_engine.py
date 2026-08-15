"""Shared reconciliation engine seam (iteration 0024, issue #114).

The venue-neutral comparison and helper functions in
``quantmesh.execution.reconciliation`` are tested directly here, independent of
any venue binding, so drift / missing-data / revoked-fill / position behavior
lives at one seam. The Moomoo and Hyperliquid bindings both call these.
"""

from __future__ import annotations

from datetime import UTC, datetime

from quantmesh.domain.models import Instrument, InstrumentType, Side, Venue
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderStatus,
)
from quantmesh.execution.reconciliation import (
    FindingKind,
    ReconcileTolerance,
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

INSTRUMENT = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    metadata={"market": "US"},
)
T0 = datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 8, 13, 30, 1, tzinfo=UTC)


def make_order(**overrides: object) -> Order:
    values: dict[str, object] = {
        "order_id": "order-1",
        "instrument": INSTRUMENT,
        "side": Side.BUY,
        "quantity": 100.0,
        "order_type": "limit",
        "limit_price": 210.0,
        "created_at": T0,
    }
    values.update(overrides)
    return Order(**values)


def filled_order(
    qty: float,
    price: float,
    fee: float = 0.0,
    *,
    broker_fill_id: str | None = None,
) -> Order:
    return OrderStateMachine.apply(
        make_order(),
        OrderEventType.FILL,
        fill=Fill(
            timestamp=T1,
            quantity=qty,
            price=price,
            fee=fee,
            broker_fill_id=broker_fill_id,
        ),
        timestamp=T1,
    )


# --- pure helpers -------------------------------------------------------------


def test_finding_builds_a_typed_finding() -> None:
    result = finding(FindingKind.QUANTITY, Severity.ERROR, "drift", order_id="o-1")
    assert result.kind is FindingKind.QUANTITY
    assert result.severity is Severity.ERROR
    assert result.order_id == "o-1"
    assert result.message == "drift"


def test_dedupe_by_id_keeps_last() -> None:
    items = [(1, "a"), (2, "b"), (1, "c"), (3, "d")]
    assert dedupe_by_id(items, key=lambda v: v[0]) == [(1, "c"), (2, "b"), (3, "d")]


def test_is_terminal() -> None:
    assert is_terminal(OrderStatus.FILLED)
    assert is_terminal(OrderStatus.CANCELED)
    assert not is_terminal(OrderStatus.PENDING)


# --- compare_quantities -------------------------------------------------------


def test_compare_quantities_order_drift() -> None:
    findings = compare_quantities(
        broker_qty=90.0,
        broker_filled_qty=0.0,
        order=make_order(),
        tolerance=ReconcileTolerance(),
        noun="broker",
    )
    assert [f.kind for f in findings] == [FindingKind.QUANTITY]


def test_compare_quantities_skips_undeclared_order_qty() -> None:
    findings = compare_quantities(
        broker_qty=None,
        broker_filled_qty=0.0,
        order=make_order(),
        tolerance=ReconcileTolerance(),
        noun="venue",
    )
    assert findings == []


def test_compare_quantities_journal_ahead_is_drift() -> None:
    order = filled_order(100.0, 210.0, 0.0)
    findings = compare_quantities(
        broker_qty=100.0,
        broker_filled_qty=50.0,
        order=order,
        tolerance=ReconcileTolerance(),
        noun="broker",
    )
    assert [f.kind for f in findings] == [FindingKind.QUANTITY]


# --- compare_prices -----------------------------------------------------------


def test_compare_prices_limit_drift() -> None:
    findings = compare_prices(
        broker_limit_price=215.0,
        broker_average_price=None,
        order=make_order(),
        tolerance=ReconcileTolerance(),
        noun="broker",
    )
    assert [f.kind for f in findings] == [FindingKind.PRICE]


def test_compare_prices_execution_drift() -> None:
    order = filled_order(100.0, 210.0, 0.0)
    findings = compare_prices(
        broker_limit_price=210.0,
        broker_average_price=209.0,
        order=order,
        tolerance=ReconcileTolerance(),
        noun="venue",
    )
    assert [f.kind for f in findings] == [FindingKind.PRICE]


# --- compare_positions --------------------------------------------------------


def test_compare_positions_unexplained_broker_position() -> None:
    findings = compare_positions(
        broker_by_symbol={"AAPL": 100.0},
        internal=[make_order()],  # no fills → journal net 0
        venue=Venue.MOOMOO,
        noun="broker",
        tolerance=ReconcileTolerance(),
    )
    assert [f.kind for f in findings] == [FindingKind.POSITION]


def test_compare_positions_drift_respects_tolerance() -> None:
    order = filled_order(100.0, 210.0, 0.0)
    strict = compare_positions(
        broker_by_symbol={"AAPL": 99.0},
        internal=[order],
        venue=Venue.MOOMOO,
        noun="broker",
        tolerance=ReconcileTolerance(),
    )
    lenient = compare_positions(
        broker_by_symbol={"AAPL": 99.0},
        internal=[order],
        venue=Venue.MOOMOO,
        noun="broker",
        tolerance=ReconcileTolerance(position_qty_bps=200),
    )
    assert [f.kind for f in strict] == [FindingKind.POSITION]
    assert lenient == []


# --- compare_fees / compare_fill_ids -----------------------------------------


def test_compare_fees_drift() -> None:
    order = filled_order(100.0, 210.0, fee=0.5)
    findings = compare_fees(
        broker_fees=[9.0],
        row_count=1,
        row_noun="deals",
        noun="broker",
        order=order,
        tolerance=ReconcileTolerance(),
    )
    assert [f.kind for f in findings] == [FindingKind.FEE]


def test_compare_fees_missing_fee_data() -> None:
    order = filled_order(100.0, 210.0, fee=0.5)
    findings = compare_fees(
        broker_fees=[],
        row_count=1,
        row_noun="fills",
        noun="venue",
        order=order,
        tolerance=ReconcileTolerance(),
    )
    assert [f.kind for f in findings] == [FindingKind.MISSING_DATA]


def test_compare_fill_ids_revoked() -> None:
    order = filled_order(100.0, 210.0, fee=0.0, broker_fill_id="D-1")
    findings = compare_fill_ids(
        broker_fill_ids=set(),
        row_noun="deal",
        noun="broker",
        order=order,
    )
    assert [f.kind for f in findings] == [FindingKind.REVOKED_FILL]
