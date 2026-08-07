"""Simulated Moomoo execution adapter tests (issue #28, Phase D).

The adapter is explicit-construction-only and its transports are
fixture-first: everything here runs on ``SimulatedFixtureTransport`` or
wire parsers directly — no OpenD, no vendor SDK. The live
``SdkTradeTransport`` is tested only for its fail-closed refusal
surfaces, which do not need the SDK installed.
"""

import builtins
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Side,
    Venue,
)
from quantmesh.domain.orders import Order, OrderType
from quantmesh.moomoo import (
    ExecutionSnapshot,
    MoomooExecutionAdapter,
    OpenDProtocolError,
    OpenDUnavailableError,
    SdkTradeTransport,
    SimulatedFixtureTransport,
)

INSTRUMENT = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
    metadata={"market": "US"},
)
CREATED_AT = datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC)

# Fixture phases, in scripted order (see the drill test in
# test_moomoo_reconciliation for the full lost-ack lifecycle).
FILLED_ORDER = {
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


# --- fixture script validation -------------------------------------------------

def test_empty_script_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "drill.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="no phases"):
        SimulatedFixtureTransport(path)


def test_phase_without_now_is_refused() -> None:
    with pytest.raises(ValueError, match="'now'"):
        SimulatedFixtureTransport([{"orders": []}])


def test_naive_now_is_refused() -> None:
    with pytest.raises(OpenDProtocolError, match="unparseable broker time"):
        SimulatedFixtureTransport([{"now": "2026-08-08 09:30:00"}])


def test_phase_with_non_list_rows_is_refused() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        SimulatedFixtureTransport([{"now": "2026-08-08T09:30:00+00:00", "orders": {}}])


def test_bad_json_fails_with_line_attribution(tmp_path: Path) -> None:
    path = tmp_path / "drill.jsonl"
    path.write_text('{"now": "2026-08-08T09:30:00+00:00"}\nnot json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 2 is not valid JSON"):
        SimulatedFixtureTransport(path)


def test_missing_script_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        SimulatedFixtureTransport(tmp_path / "nope.jsonl")


# --- phase selection and time ---------------------------------------------------

def _transport(script: list[dict]) -> SimulatedFixtureTransport:
    return SimulatedFixtureTransport(script)


def test_state_is_the_latest_phase_at_or_before_now() -> None:
    transport = _transport(
        [
            {"now": "2026-08-08T13:30:00+00:00", "orders": []},
            {"now": "2026-08-08T13:31:00+00:00", "orders": [FILLED_ORDER]},
        ]
    )

    assert transport.snapshot().orders == []
    transport.advance_to(datetime(2026, 8, 8, 13, 31, 0, tzinfo=UTC))
    assert [order.order_id for order in transport.snapshot().orders] == ["B-1"]


def test_advance_to_requires_aware_time() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])

    with pytest.raises(ValueError, match="timezone-aware"):
        transport.advance_to(datetime(2026, 8, 8, 13, 31, 0))


def test_time_cannot_move_backwards() -> None:
    transport = _transport(
        [
            {"now": "2026-08-08T13:30:00+00:00"},
            {"now": "2026-08-08T13:31:00+00:00"},
        ]
    )
    transport.advance_to(datetime(2026, 8, 8, 13, 31, 0, tzinfo=UTC))

    with pytest.raises(ValueError, match="backwards"):
        transport.advance_to(datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC))


def test_place_assigns_broker_ids_deterministically() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])

    first = transport.place(
        code="US.AAPL", side=Side.BUY, quantity=1.0, price=1.0, remark="a",
        order_type=OrderType.LIMIT,
    )
    second = transport.place(
        code="US.AAPL", side=Side.BUY, quantity=1.0, price=1.0, remark="b",
        order_type=OrderType.LIMIT,
    )

    assert (first, second) == ("B-1", "B-2")


def test_lost_ack_withholds_the_reply_but_records_the_order() -> None:
    transport = _transport(
        [
            {"now": "2026-08-08T13:30:00+00:00", "lost_acks": ["B-1"]},
            {"now": "2026-08-08T13:31:00+00:00", "orders": [FILLED_ORDER]},
        ]
    )

    with pytest.raises(OpenDUnavailableError, match="acknowledgement never arrived"):
        transport.place(
            code="US.AAPL", side=Side.BUY, quantity=1.0, price=1.0, remark="a",
            order_type=OrderType.LIMIT,
        )

    transport.advance_to(datetime(2026, 8, 8, 13, 31, 0, tzinfo=UTC))
    assert [order.order_id for order in transport.snapshot().orders] == ["B-1"]


def test_cancel_of_unknown_order_is_refused() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])

    with pytest.raises(ValueError, match="broker has no order 'B-9'"):
        transport.cancel("B-9")


# --- wire parsing ----------------------------------------------------------------

def test_snapshot_converts_venue_local_times_to_utc() -> None:
    transport = _transport(
        [{"now": "2026-08-08T13:31:00+00:00", "orders": [FILLED_ORDER]}]
    )

    order = transport.snapshot().orders[0]

    assert order.create_time == datetime(2026, 8, 8, 13, 30, 0, tzinfo=UTC)
    assert order.updated_time == datetime(2026, 8, 8, 13, 30, 1, tzinfo=UTC)


def test_snapshot_rejects_codes_without_market_prefix() -> None:
    bad = {**FILLED_ORDER, "code": "AAPL"}
    transport = _transport([{"now": "2026-08-08T13:31:00+00:00", "orders": [bad]}])

    with pytest.raises(OpenDProtocolError, match="timezone metadata for market 'AAPL'"):
        transport.snapshot()


def test_snapshot_rejects_unknown_sides() -> None:
    bad = {**FILLED_ORDER, "trd_side": "HODL"}
    transport = _transport([{"now": "2026-08-08T13:31:00+00:00", "orders": [bad]}])

    with pytest.raises(OpenDProtocolError, match="unknown broker side"):
        transport.snapshot()


def test_snapshot_rejects_unparseable_times() -> None:
    bad = {**FILLED_ORDER, "create_time": "yesterday-ish"}
    transport = _transport([{"now": "2026-08-08T13:31:00+00:00", "orders": [bad]}])

    with pytest.raises(OpenDProtocolError, match="unparseable broker time"):
        transport.snapshot()


def test_snapshot_parses_deals_and_positions_through_the_same_wire() -> None:
    transport = _transport(
        [
            {
                "now": "2026-08-08T13:31:00+00:00",
                "orders": [FILLED_ORDER],
                "deals": [
                    {
                        "deal_id": "D-1",
                        "order_id": "B-1",
                        "code": "US.AAPL",
                        "qty": 100,
                        "price": 210.0,
                        "trd_side": "BUY",
                        "create_time": "2026-08-08 09:30:01",
                        "fee": 0.5,
                    }
                ],
                "positions": [{"code": "US.AAPL", "qty": 100}],
            }
        ]
    )

    snapshot = transport.snapshot()
    assert snapshot.deals[0].deal_id == "D-1"
    assert snapshot.deals[0].fee == 0.5
    assert snapshot.positions[0].qty == 100


# --- adapter ---------------------------------------------------------------------

def test_place_stamps_the_broker_order_id() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])
    adapter = MoomooExecutionAdapter(transport)

    order = adapter.place(make_request(), order_id="order-1", created_at=CREATED_AT)

    assert order.order_id == "order-1"
    assert order.broker_order_id == "B-1"
    assert order.status.value == "pending"


def test_place_derives_limit_or_market_type_from_the_request() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])
    adapter = MoomooExecutionAdapter(transport)

    limit = adapter.place(make_request(), order_id="o-1", created_at=CREATED_AT)
    market = adapter.place(
        make_request(limit_price=None), order_id="o-2", created_at=CREATED_AT
    )

    assert limit.order_type is OrderType.LIMIT
    assert market.order_type is OrderType.MARKET


def test_place_refuses_a_remark_over_the_broker_limit() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])
    adapter = MoomooExecutionAdapter(transport)

    with pytest.raises(ValueError, match="64-byte limit"):
        adapter.place(
            make_request(client_order_id="x" * 65), order_id="o-1", created_at=CREATED_AT
        )


def test_place_requires_market_metadata_fail_closed() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])
    adapter = MoomooExecutionAdapter(transport)
    instrument = Instrument(
        symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY
    )

    with pytest.raises(ValueError, match="metadata 'market'"):
        adapter.place(
            make_request(instrument=instrument), order_id="o-1", created_at=CREATED_AT
        )


def test_cancel_without_a_broker_id_is_refused() -> None:
    transport = _transport([{"now": "2026-08-08T13:30:00+00:00"}])
    adapter = MoomooExecutionAdapter(transport)
    order = Order.from_request(make_request(), order_id="o-1", created_at=CREATED_AT)

    with pytest.raises(ValueError, match="has no broker order id"):
        adapter.cancel(order)


def test_cancel_and_refresh_pass_through_to_the_transport() -> None:
    transport = _transport([{"now": "2026-08-08T13:31:00+00:00", "orders": [FILLED_ORDER]}])
    adapter = MoomooExecutionAdapter(transport)
    order = Order.from_request(make_request(), order_id="o-1", created_at=CREATED_AT)
    order = order.model_copy(update={"broker_order_id": "B-1"})

    adapter.cancel(order)
    snapshot = adapter.refresh()

    assert isinstance(snapshot, ExecutionSnapshot)
    assert snapshot.orders[0].order_id == "B-1"


# --- live transport refusal surfaces (never touches the SDK) ----------------------

def test_sdk_transport_refuses_when_the_sdk_cannot_be_imported(monkeypatch) -> None:
    real_import = builtins.__import__

    def no_moomoo(name, *args, **kwargs):
        if name == "moomoo" or name.startswith("moomoo."):
            raise ImportError("vendored SDK not installed in this venv")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_moomoo)
    transport = SdkTradeTransport("127.0.0.1", 11111, connect_timeout_s=1.0)

    with pytest.raises(OpenDProtocolError, match="not importable"):
        transport.snapshot()
