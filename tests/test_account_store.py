"""Paper-account authority and restart-safe local persistence."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Quote, Side, Venue
from quantmesh.execution.account_store import (
    PAPER_ACCOUNT_FILE,
    PaperAccountFile,
    PaperAccountPersistenceError,
    recover_account_from_journal,
)
from quantmesh.execution.accounting import FeeModel, PaperAccount, RiskLimits
from quantmesh.execution.matcher import PaperMatcher


def test_account_file_round_trips_the_complete_immutable_account(tmp_path: Path) -> None:
    snapshots = PaperAccountFile(tmp_path)
    initial = PaperAccount(cash=100_000.0)
    assert snapshots.load_or_create(initial) == initial
    updated = initial.model_copy(update={"kill_switch": True, "order_sequence": 7})

    snapshots.save(updated)

    assert PaperAccountFile(tmp_path).load_or_create(initial) == updated


def test_account_file_refuses_corrupt_existing_state(tmp_path: Path) -> None:
    (tmp_path / PAPER_ACCOUNT_FILE).write_text("not-json", encoding="utf-8")

    with pytest.raises(PaperAccountPersistenceError, match="invalid"):
        PaperAccountFile(tmp_path).load_or_create(PaperAccount(cash=100_000.0))


def test_journal_recovery_closes_the_append_before_snapshot_crash_window() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )

    recovered = recover_account_from_journal(initial, [submitted.order])

    assert recovered.cash == submitted.account.cash
    assert recovered.positions == submitted.account.positions
    assert recovered.orders == submitted.account.orders
    assert recovered.order_sequence == submitted.account.order_sequence


def test_journal_recovery_refuses_state_that_disagrees_with_fill_history() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    inconsistent = submitted.order.model_copy(update={"status": "pending", "filled_quantity": 0.0})

    with pytest.raises(PaperAccountPersistenceError, match="derived state"):
        recover_account_from_journal(initial, [inconsistent])


def test_journal_recovery_refuses_account_order_stored_under_the_wrong_key() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    payload = submitted.account.model_dump(mode="json")
    payload["orders"] = {"wrong-key": submitted.order.model_dump(mode="json")}
    valid_json_account = PaperAccount.model_validate(payload)

    with pytest.raises(PaperAccountPersistenceError, match="map key.*does not match order id"):
        recover_account_from_journal(valid_json_account, [submitted.order])


def test_journal_recovery_refuses_invalid_account_order_derived_state() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    payload = submitted.account.model_dump(mode="json")
    payload["orders"][submitted.order.order_id]["status"] = "pending"
    payload["orders"][submitted.order.order_id]["filled_quantity"] = 0.0
    valid_json_account = PaperAccount.model_validate(payload)

    with pytest.raises(
        PaperAccountPersistenceError,
        match="paper account order.*invalid derived state",
    ):
        recover_account_from_journal(valid_json_account, [submitted.order])


def test_journal_recovery_refuses_account_orders_absent_from_journal() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )

    with pytest.raises(PaperAccountPersistenceError, match="absent from the order journal"):
        recover_account_from_journal(submitted.account, [])


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        pytest.param("cash", 50_000.0, id="cash"),
        pytest.param("total_fees", 123.0, id="total-fees"),
        pytest.param("total_funding", 1.0, id="unverifiable-funding"),
        pytest.param("realized_pnl", 5.0, id="realized-pnl"),
        pytest.param("order_sequence", 2, id="order-sequence"),
    ],
)
def test_journal_recovery_refuses_tampered_account_aggregate_field(
    field: str,
    tampered_value: float | int,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    payload = submitted.account.model_dump(mode="json")
    payload[field] = tampered_value
    valid_json_account = PaperAccount.model_validate(payload)

    with pytest.raises(PaperAccountPersistenceError, match=field):
        recover_account_from_journal(valid_json_account, [submitted.order])


def test_journal_recovery_refuses_tampered_positions() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    payload = submitted.account.model_dump(mode="json")
    payload["positions"]["hyperliquid:BTC"]["quantity"] = 2.0
    valid_json_account = PaperAccount.model_validate(payload)

    with pytest.raises(PaperAccountPersistenceError, match="positions"):
        recover_account_from_journal(valid_json_account, [submitted.order])


def test_journal_recovery_refuses_reordered_account_order_prefix() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    first = initial.submit(
        OrderRequest(
            instrument=instrument,
            side=Side.BUY,
            quantity=1.0,
            client_order_id="first",
        ),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    second = first.account.submit(
        OrderRequest(
            instrument=instrument,
            side=Side.BUY,
            quantity=1.0,
            client_order_id="second",
        ),
        Quote(instrument=instrument, timestamp=now, bid=100.0, ask=101.0, volume=2.0),
        now=now,
    )
    payload = second.account.model_dump(mode="json")
    payload["orders"] = {
        "second": second.order.model_dump(mode="json"),
        "first": first.order.model_dump(mode="json"),
    }
    reordered = PaperAccount.model_validate(payload)

    with pytest.raises(PaperAccountPersistenceError, match="ordered prefix"):
        recover_account_from_journal(reordered, [first.order, second.order])


def test_journal_recovery_refuses_duplicate_journal_order_ids() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    submitted = initial.submit(
        OrderRequest(instrument=instrument, side=Side.BUY, quantity=1.0),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )

    with pytest.raises(PaperAccountPersistenceError, match="duplicate order id"):
        recover_account_from_journal(initial, [submitted.order, submitted.order])


def test_journal_recovery_refuses_regressing_journal_creation_time() -> None:
    first_time = datetime(2026, 8, 12, 0, 0, 1, tzinfo=UTC)
    second_time = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(cash=100_000.0)
    first = initial.submit(
        OrderRequest(
            instrument=instrument,
            side=Side.BUY,
            quantity=1.0,
            client_order_id="first",
        ),
        Quote(
            instrument=instrument,
            timestamp=first_time,
            bid=99.0,
            ask=100.0,
            volume=2.0,
        ),
        now=first_time,
    )
    second = first.account.submit(
        OrderRequest(
            instrument=instrument,
            side=Side.BUY,
            quantity=1.0,
            client_order_id="second",
        ),
        Quote(
            instrument=instrument,
            timestamp=second_time,
            bid=100.0,
            ask=101.0,
            volume=2.0,
        ),
        now=second_time,
    )

    with pytest.raises(PaperAccountPersistenceError, match="creation time regresses"):
        recover_account_from_journal(initial, [first.order, second.order])


def test_journal_recovery_preserves_policy_and_switches_when_adopting_trailing_order() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    initial = PaperAccount(
        cash=100_000.0,
        fee_model=FeeModel(fee_bps=25.0, min_fee=0.25),
        risk_limits=RiskLimits(max_order_quantity=10.0, max_notional=10_000.0),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    first = initial.submit(
        OrderRequest(
            instrument=instrument,
            side=Side.BUY,
            quantity=1.0,
            client_order_id="first",
        ),
        Quote(instrument=instrument, timestamp=now, bid=99.0, ask=100.0, volume=2.0),
        now=now,
    )
    second = first.account.submit(
        OrderRequest(
            instrument=instrument,
            side=Side.BUY,
            quantity=1.0,
            client_order_id="second",
        ),
        Quote(instrument=instrument, timestamp=now, bid=100.0, ask=101.0, volume=2.0),
        now=now,
    )
    surviving_snapshot = first.account.model_copy(
        update={
            "kill_switch": True,
            "kill_switches": {Venue.MOOMOO: True},
        }
    )

    recovered = recover_account_from_journal(
        surviving_snapshot,
        [first.order, second.order],
    )

    assert recovered.cash == second.account.cash
    assert recovered.positions == second.account.positions
    assert recovered.total_fees == second.account.total_fees
    assert recovered.orders == second.account.orders
    assert recovered.order_sequence == 2
    assert recovered.fee_model == initial.fee_model
    assert recovered.risk_limits == initial.risk_limits
    assert recovered.matcher == initial.matcher
    assert recovered.kill_switch is True
    assert recovered.kill_switches == {Venue.MOOMOO: True}
