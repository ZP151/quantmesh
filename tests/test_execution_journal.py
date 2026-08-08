"""OrderJournal tests (issue #28, Phase D, ADR-0006 decision 1).

The journal is the single source of truth for the broker-order mapping,
so its durability discipline is load-bearing: atomic writes, fail-closed
reads with line attribution, duplicate ids refused.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    Side,
    Venue,
)
from quantmesh.domain.orders import (
    Fill,
    Order,
    OrderEventType,
    OrderStateMachine,
)
from quantmesh.execution import JOURNAL_FILE, OrderJournal

INSTRUMENT = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    metadata={"market": "US"},
)
CREATED_AT = datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC)


def make_order(order_id: str = "o-1", **overrides: object) -> Order:
    values: dict[str, object] = {
        "order_id": order_id,
        "instrument": INSTRUMENT,
        "side": Side.BUY,
        "quantity": 10,
        "order_type": "limit",
        "limit_price": 100.0,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return Order(**values)


def order_fill(quantity: float, price: float) -> Fill:
    return Fill(timestamp=CREATED_AT, quantity=quantity, price=price)


def test_new_journal_is_empty(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")

    assert journal.all() == []


def test_record_then_read_round_trips(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")
    order = make_order()

    journal.record(order)

    assert journal.all() == [order]
    assert journal.get("o-1") == order
    assert (tmp_path / "orders" / JOURNAL_FILE).exists()


def test_duplicate_record_is_refused(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")
    journal.record(make_order("o-1"))

    with pytest.raises(ValueError, match="already recorded"):
        journal.record(make_order("o-1"))


def test_update_replaces_the_snapshot_in_place(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")
    journal.record(make_order())
    accepted = OrderStateMachine.apply(journal.get("o-1"), OrderEventType.ACCEPTED)

    journal.update(accepted)

    recorded = journal.get("o-1")
    assert recorded.status is accepted.status
    assert [event.event_type for event in recorded.events] == [OrderEventType.ACCEPTED]
    assert len(journal.all()) == 1


def test_update_of_unknown_order_is_refused(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")

    with pytest.raises(ValueError, match="not recorded"):
        journal.update(make_order("o-9"))


def test_get_of_unknown_order_raises(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")

    with pytest.raises(ValueError, match="no order recorded"):
        journal.get("o-9")


def test_persistence_across_instances(tmp_path: Path) -> None:
    root = tmp_path / "orders"
    OrderJournal(root=root).record(make_order("o-1"))
    OrderJournal(root=root).record(make_order("o-2"))

    reloaded = OrderJournal(root=root)

    assert sorted(order.order_id for order in reloaded.all()) == ["o-1", "o-2"]


def test_corrupt_line_fails_closed_with_attribution(tmp_path: Path) -> None:
    root = tmp_path / "orders"
    journal = OrderJournal(root=root)
    journal.record(make_order())
    path = root / JOURNAL_FILE
    path.write_text("this is not json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1 is invalid"):
        journal.all()


def test_duplicate_order_ids_fail_closed_with_both_lines(tmp_path: Path) -> None:
    root = tmp_path / "orders"
    journal = OrderJournal(root=root)
    journal.record(make_order("o-1"))
    journal.record(make_order("o-2"))
    path = root / JOURNAL_FILE
    path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")

    with pytest.raises(ValueError, match="lines 1 and 3 share an order id"):
        journal.all()


def test_root_that_is_a_file_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "not-a-dir"
    root.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        OrderJournal(root=root).all()


def test_writes_leave_no_temp_files(tmp_path: Path) -> None:
    root = tmp_path / "orders"
    journal = OrderJournal(root=root)
    journal.record(make_order())
    journal.update(OrderStateMachine.apply(journal.get("o-1"), OrderEventType.ACCEPTED))

    assert [p.name for p in root.iterdir()] == [JOURNAL_FILE]


def test_record_and_update_preserve_full_history(tmp_path: Path) -> None:
    journal = OrderJournal(root=tmp_path / "orders")
    journal.record(make_order())
    journal.update(
        OrderStateMachine.apply(
            journal.get("o-1"),
            OrderEventType.FILL,
            fill=order_fill(10.0, 100.0),
            timestamp=CREATED_AT,
        )
    )

    reloaded = journal.get("o-1")
    assert reloaded.filled_quantity == 10.0
    assert reloaded.status.value == "filled"
    assert reloaded.fills == [order_fill(10.0, 100.0)]
