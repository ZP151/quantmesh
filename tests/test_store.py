"""SQLite event persistence, replay and reconciliation (issue #5)."""

import sqlite3
from datetime import UTC, datetime

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.domain.orders import OrderStatus
from quantmesh.execution.accounting import FeeModel, PaperAccount, RiskLimits
from quantmesh.execution.matcher import PaperMatcher
from quantmesh.execution.store import EventStore, StoreCorruptionError

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
POSITION_KEY = "internal:AAPL"
NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make_request(
    side: Side,
    quantity: float,
    limit_price: float | None = None,
    client_order_id: str | None = None,
) -> OrderRequest:
    return OrderRequest(
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        client_order_id=client_order_id,
    )


def make_quote(
    *, bid: float | None = 99.0, ask: float | None = 100.0, volume: float | None = 100
) -> Quote:
    return Quote(
        instrument=INSTRUMENT, timestamp=NOW, bid=bid, ask=ask, volume=volume
    )


def base_account() -> PaperAccount:
    return PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )


def sample_account() -> PaperAccount:
    """Buy 10 @ 100, sell 4 @ 110, leave a non-crossed limit buy working."""
    account = base_account()
    account = account.submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account
    account = account.submit(
        make_request(Side.SELL, 4), make_quote(bid=110.0, ask=111.0), now=NOW
    ).account
    account = account.submit(
        make_request(Side.BUY, 10, limit_price=99.0), make_quote(), now=NOW
    ).account
    return account


def open_raw(path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))


def test_save_writes_events_with_monotonic_global_sequences(tmp_path) -> None:
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(sample_account())

    conn = open_raw(path)
    rows = conn.execute("SELECT * FROM events").fetchall()
    sequences = [row[0] for row in rows]
    assert sequences == sorted(sequences)
    assert sequences == list(range(1, len(rows) + 1))
    # Submission order is preserved by the global sequence.
    assert [row[1] for row in rows] == [
        "paper-1", "paper-1", "paper-2", "paper-2", "paper-3",
    ]
    # Per-order sequences are preserved from the domain events.
    first_order_events = [row for row in rows if row[1] == rows[0][1]]
    assert [row[2] for row in first_order_events] == [1, 2]
    conn.close()
    store.close()


def test_restore_rebuilds_identical_state(tmp_path) -> None:
    original = sample_account()
    store = EventStore(tmp_path / "book.sqlite")
    store.save(original)

    restored = store.restore()

    assert restored.divergences == []
    assert restored.account.model_dump() == original.model_dump()
    store.close()


def test_restart_rebuilds_identical_state(tmp_path) -> None:
    path = tmp_path / "book.sqlite"
    original = sample_account()
    EventStore(path).save(original)
    # A fresh store on the same path is the simulated process restart.
    restarted = EventStore(path).restore()

    assert restarted.account.model_dump() == original.model_dump()
    assert restarted.divergences == []


def test_replay_is_deterministic_across_stores(tmp_path) -> None:
    original = sample_account()
    first = EventStore(tmp_path / "a.sqlite")
    second = EventStore(tmp_path / "b.sqlite")
    first.save(original)
    second.save(original)

    assert first.restore().account.model_dump() == second.restore().account.model_dump()


def test_save_is_idempotent(tmp_path) -> None:
    original = sample_account()
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(original)
    store.save(original)

    conn = open_raw(path)
    rows = conn.execute("SELECT * FROM events").fetchall()
    conn.close()
    assert len(rows) == 5  # accepted+fill x2, accepted x1 — no duplicates
    assert store.restore().account.model_dump() == original.model_dump()


def test_restore_on_empty_store_fails_closed(tmp_path) -> None:
    store = EventStore(tmp_path / "book.sqlite")

    with pytest.raises(ValueError, match="no persisted account"):
        store.restore()


def test_reconcile_is_clean_for_pristine_state(tmp_path) -> None:
    original = sample_account()
    store = EventStore(tmp_path / "book.sqlite")
    store.save(original)

    assert store.restore().divergences == []


def test_reconcile_detects_tampered_fill_price(tmp_path) -> None:
    original = sample_account()
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(original)
    order_id = original.orders["paper-1"].order_id
    conn = open_raw(path)
    conn.execute(
        "UPDATE events SET price = 101.0 WHERE order_id = ? AND event_type = 'fill'",
        (order_id,),
    )
    conn.commit()
    conn.close()

    result = store.restore()

    assert result.divergences
    assert any("cash" in d for d in result.divergences)
    assert any("positions" in d for d in result.divergences)


def test_reconcile_detects_deleted_event(tmp_path) -> None:
    original = sample_account()
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(original)
    working_order_id = original.orders["paper-3"].order_id
    conn = open_raw(path)
    conn.execute("DELETE FROM events WHERE order_id = ?", (working_order_id,))
    conn.commit()
    conn.close()

    result = store.restore()

    assert result.divergences
    assert any("orders" in d for d in result.divergences)


def test_reconcile_detects_tampered_order_header(tmp_path) -> None:
    original = sample_account()
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(original)
    working_order_id = original.orders["paper-3"].order_id
    conn = open_raw(path)
    conn.execute("UPDATE orders SET side = 'sell' WHERE order_id = ?", (working_order_id,))
    conn.commit()
    conn.close()

    result = store.restore()

    assert result.divergences
    assert any("orders" in d for d in result.divergences)


def test_reconcile_detects_tampered_config(tmp_path) -> None:
    original = sample_account()
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(original)
    conn = open_raw(path)
    conn.execute("UPDATE account_meta SET kill_switch = 1 WHERE id = 1")
    conn.commit()
    conn.close()

    result = store.restore()

    assert result.divergences
    assert any("config" in d for d in result.divergences)


def test_invalid_transition_tamper_raises_store_corruption(tmp_path) -> None:
    original = sample_account()
    path = tmp_path / "book.sqlite"
    store = EventStore(path)
    store.save(original)
    working_order_id = original.orders["paper-3"].order_id
    conn = open_raw(path)
    conn.execute(
        """
        INSERT INTO events (
            global_sequence, order_id, event_sequence, timestamp,
            event_type, status, quantity, price, reason
        ) VALUES (NULL, ?, 2, ?, 'accepted', 'accepted', NULL, NULL, NULL)
        """,
        (working_order_id, NOW.isoformat()),
    )
    conn.commit()
    conn.close()

    with pytest.raises(StoreCorruptionError, match="corrupt event log"):
        store.restore()


def test_kill_switch_survives_restart(tmp_path) -> None:
    account_ = base_account().model_copy(update={"kill_switch": True})
    path = tmp_path / "book.sqlite"
    EventStore(path).save(account_)

    restored = EventStore(path).restore()

    assert restored.divergences == []
    assert restored.account.kill_switch is True


def test_partially_filled_order_round_trip(tmp_path) -> None:
    account = base_account().submit(
        make_request(Side.BUY, 10), make_quote(volume=4), now=NOW
    ).account
    assert account.orders["paper-1"].status is OrderStatus.PARTIALLY_FILLED
    store = EventStore(tmp_path / "book.sqlite")
    store.save(account)

    restored = store.restore()

    assert restored.divergences == []
    assert restored.account.model_dump() == account.model_dump()


def test_rejected_order_round_trip(tmp_path) -> None:
    limited = base_account().model_copy(
        update={"risk_limits": RiskLimits(max_order_quantity=10)}
    )
    account = limited.submit(make_request(Side.BUY, 15), make_quote(), now=NOW).account
    assert account.orders["paper-1"].status is OrderStatus.REJECTED
    store = EventStore(tmp_path / "book.sqlite")
    store.save(account)

    restored = store.restore()

    assert restored.divergences == []
    assert restored.account.model_dump() == account.model_dump()


def test_fills_replay_in_submission_order(tmp_path) -> None:
    original = sample_account()  # buy before sell; reversed order would raise
    store = EventStore(tmp_path / "book.sqlite")
    store.save(original)

    restored = store.restore()

    assert restored.divergences == []
    position = restored.account.positions[POSITION_KEY]
    assert position.quantity == 6
    assert restored.account.cash == pytest.approx(9_438.56)
    assert restored.account.realized_pnl == pytest.approx(39.56)


def test_restore_keeps_working_orders_working(tmp_path) -> None:
    original = sample_account()
    store = EventStore(tmp_path / "book.sqlite")
    store.save(original)

    working = store.restore().account.orders["paper-3"]

    assert working.status is OrderStatus.ACCEPTED
    assert working.filled_quantity == 0
    assert len(working.events) == 1
