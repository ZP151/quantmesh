"""Hyperliquid testnet exchange surface tests (M5, issue #30, Phase B).

``SdkExchangeTransport`` is lazy, import-guarded, testnet-pinned, and
signer-injected: mainnet is refused at construction, the SDK (and the
``eth_account`` key) is only reached on first use, and unit tests stub
the SDK boundary exactly like the Phase A REST tests. ``ScriptedExchangeTransport``
is the deterministic JSONL-phase stub that drives the Phase B drill.
"""

import builtins
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Side, Venue
from quantmesh.domain.orders import OrderStatus, OrderType
from quantmesh.execution.journal import OrderJournal
from quantmesh.hyperliquid.errors import (
    HyperliquidProtocolError,
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.exchange import (
    HyperliquidExecutionAdapter,
    InMemorySigner,
    PlaceAck,
    ScriptedExchangeTransport,
    SdkExchangeTransport,
    build_snapshot,
    parse_cancel_ack,
    parse_fill,
    parse_open_order,
    parse_place_ack,
    parse_position,
    signer_from_env,
    to_cloid,
)
from quantmesh.hyperliquid.market_data import FIXTURE_DIR
from quantmesh.hyperliquid.rest import MAINNET_API_URL, TESTNET_API_URL

T0 = 1754600400000
P1 = datetime.fromtimestamp(T0 / 1000, tz=UTC)
SCRIPT = FIXTURE_DIR / "wire_exchange_script.jsonl"

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)
SELL_1072 = OrderRequest(
    instrument=BTC, side=Side.SELL, quantity=1.0, limit_price=107.2
)
BUY_1074 = OrderRequest(
    instrument=BTC, side=Side.BUY, quantity=1.0, limit_price=107.4
)

CID_1001 = "5e8f2c4d7a1b9e3f6c0d4a2b8e5f7c1d"
CID_1002 = "9d3a6c1e8b2f4570a1c9e3d5b7f2a84c"


class StubCloid:
    def __init__(self, raw: str) -> None:
        self.raw = raw


class StubExchange:
    """The SDK Exchange surface as the tests see it: wallet + actions."""

    def __init__(self, *, info=None) -> None:
        self.wallet = SimpleNamespace(address="0x" + "ab" * 20)
        self.info = info or StubInfo()
        self.calls: list[tuple[str, tuple, dict]] = []
        self.place_payload = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 1001}}]}},
        }
        self.cancel_payload = {
            "status": "ok",
            "response": {"data": {"statuses": ["success"]}},
        }

    def order(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.calls.append(("order", args, kwargs))
        return self.place_payload

    def market_open(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.calls.append(("market_open", args, kwargs))
        return self.place_payload

    def cancel(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.calls.append(("cancel", args, kwargs))
        return self.cancel_payload

    def cancel_by_cloid(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.calls.append(("cancel_by_cloid", args, kwargs))
        return self.cancel_payload


class StubInfo:
    def __init__(self) -> None:
        self.open_rows = []
        self.fill_rows = []
        self.state_payload = {"assetPositions": []}

    def open_orders(self, address, dex: str = ""):  # noqa: ANN001, ANN201
        return self.open_rows

    def user_fills(self, address):  # noqa: ANN001, ANN201
        return self.fill_rows

    def user_state(self, address, dex: str = ""):  # noqa: ANN001, ANN201
        return self.state_payload


def sdk_exchange(
    monkeypatch: pytest.MonkeyPatch, *, stub: StubExchange | None = None
) -> SdkExchangeTransport:
    stub = stub or StubExchange()
    monkeypatch.setattr(SdkExchangeTransport, "_sdk", lambda self: stub)
    transport = SdkExchangeTransport(InMemorySigner(b"\x01" * 32))
    transport._cloid_type = StubCloid
    return transport


# --- signer -----------------------------------------------------------------------


def test_in_memory_signer_requires_exactly_32_bytes() -> None:
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        InMemorySigner(b"\x01" * 31)
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        InMemorySigner(b"\x01" * 33)
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        InMemorySigner("0x" + "ab" * 32)


def test_signer_from_env_missing_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTMESH_HYPERLIQUID_PRIVATE_KEY", raising=False)
    with pytest.raises(HyperliquidUnavailableError, match="not set"):
        signer_from_env()


def test_signer_from_env_rejects_non_hex_and_wrong_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTMESH_HYPERLIQUID_PRIVATE_KEY", "not-hex!")
    with pytest.raises(HyperliquidProtocolError, match="hex private key"):
        signer_from_env()
    monkeypatch.setenv("QUANTMESH_HYPERLIQUID_PRIVATE_KEY", "ab" * 33)
    with pytest.raises(HyperliquidProtocolError, match="64-hex-character"):
        signer_from_env()


def test_signer_from_env_accepts_plain_and_prefixed_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTMESH_HYPERLIQUID_PRIVATE_KEY", "ab" * 32)
    assert signer_from_env().private_key == bytes.fromhex("ab" * 32)
    monkeypatch.setenv("QUANTMESH_HYPERLIQUID_PRIVATE_KEY", "0x" + "cd" * 32)
    assert signer_from_env().private_key == bytes.fromhex("cd" * 32)


# --- construction -----------------------------------------------------------------


def test_sdk_exchange_refuses_a_non_testnet_base_url() -> None:
    with pytest.raises(HyperliquidProtocolError, match="refusing base URL"):
        SdkExchangeTransport(InMemorySigner(b"\x01" * 32), base_url=MAINNET_API_URL)


def test_sdk_exchange_defaults_to_testnet() -> None:
    assert (
        SdkExchangeTransport(InMemorySigner(b"\x01" * 32))._base_url
        == TESTNET_API_URL
    )


def test_sdk_exchange_is_lazy_and_import_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = SdkExchangeTransport(InMemorySigner(b"\x01" * 32))
    real_import = builtins.__import__

    def forbid(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if name in ("hyperliquid", "eth_account"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbid)
    with pytest.raises(HyperliquidSDKMissingError, match="not importable"):
        transport._sdk()


# --- cloid channel ----------------------------------------------------------------


def test_to_cloid_prefixes_exactly_32_lowercase_hex() -> None:
    assert to_cloid(CID_1001) == "0x" + CID_1001


def test_to_cloid_rejects_bad_shapes() -> None:
    for bad in ("a" * 31, "A" * 32, "g" * 32, "0x" + "a" * 32, None, 123):
        with pytest.raises(ValueError, match="32 lowercase hex"):
            to_cloid(bad)  # type: ignore[arg-type]


# --- wire parsers -----------------------------------------------------------------


def test_parse_place_ack_resting() -> None:
    ack = parse_place_ack(
        {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 1001}}]}},
        },
        sent_cloid=CID_1001,
    )
    assert ack.oid == 1001
    assert ack.status == "resting"


def test_parse_place_ack_filled() -> None:
    ack = parse_place_ack(
        {
            "status": "ok",
            "response": {
                "data": {
                    "statuses": [
                        {"filled": {"oid": 1001, "totalSz": "1.0", "avgPx": "107.4"}}
                    ]
                }
            },
        },
        sent_cloid=CID_1001,
    )
    assert ack.oid == 1001
    assert ack.status == "filled"


def test_parse_place_ack_per_order_error() -> None:
    ack = parse_place_ack(
        {
            "status": "ok",
            "response": {"data": {"statuses": [{"error": "Order size too small"}]}},
        },
        sent_cloid=CID_1001,
    )
    assert ack.status == "error"
    assert ack.message == "Order size too small"


def test_parse_place_ack_top_level_err_raises() -> None:
    with pytest.raises(HyperliquidProtocolError, match="refused the action"):
        parse_place_ack({"status": "err", "response": "Rate limited"}, sent_cloid=CID_1001)


def test_parse_place_ack_cloid_echo_mismatch_fails_closed() -> None:
    payload = {
        "status": "ok",
        "response": {
            "data": {
                "statuses": [{"resting": {"oid": 1001, "cloid": "0x" + "f" * 32}}]
            }
        },
    }
    with pytest.raises(HyperliquidProtocolError, match="cloid echo mismatch"):
        parse_place_ack(payload, sent_cloid=CID_1001)


def test_parse_place_ack_bad_shapes_fail_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="must be an object"):
        parse_place_ack(["not", "an", "object"], sent_cloid=CID_1001)
    with pytest.raises(HyperliquidProtocolError, match="statuses"):
        parse_place_ack({"status": "ok", "response": {"data": {}}}, sent_cloid=CID_1001)
    with pytest.raises(HyperliquidProtocolError, match="exactly one status"):
        parse_place_ack(
            {
                "status": "ok",
                "response": {
                    "data": {
                        "statuses": [
                            {"resting": {"oid": 1}},
                            {"resting": {"oid": 2}},
                        ]
                    }
                },
            },
            sent_cloid=CID_1001,
        )
    with pytest.raises(HyperliquidProtocolError, match="unknown place status"):
        parse_place_ack(
            {"status": "ok", "response": {"data": {"statuses": [{"bogus": {}}]}}},
            sent_cloid=CID_1001,
        )


def test_parse_cancel_ack_success_and_error() -> None:
    ok = {"status": "ok", "response": {"data": {"statuses": ["success"]}}}
    assert parse_cancel_ack(ok).status == "success"
    err = {"status": "ok", "response": {"data": {"statuses": [{"error": "no such order"}]}}}
    ack = parse_cancel_ack(err)
    assert ack.status == "error"
    assert ack.message == "no such order"


def test_parse_cancel_ack_top_level_err_raises() -> None:
    with pytest.raises(HyperliquidProtocolError, match="refused the cancel action"):
        parse_cancel_ack({"status": "err", "response": "rejected"})


def test_parse_open_order_row() -> None:
    row = {
        "coin": "BTC",
        "oid": 1001,
        "side": "B",
        "sz": "1.0",
        "limitPx": "107.2",
        "timestamp": T0,
        "cloid": "0x" + CID_1001,
    }
    order = parse_open_order(row)
    assert order.oid == 1001
    assert order.coin == "BTC"
    assert order.side is Side.SELL
    assert order.quantity == 1.0
    assert order.limit_price == 107.2
    assert order.created == P1
    assert order.cloid == "0x" + CID_1001
    assert order.status == "open"
    assert order.declares_quantity


def test_parse_open_order_bad_shapes_fail_closed() -> None:
    base = {"coin": "BTC", "oid": 1001, "side": "A", "sz": "1.0", "timestamp": T0}
    for mutation, match in (
        ({"oid": "1001"}, "integer oid"),
        ({"oid": True}, "integer oid"),
        ({"sz": "-1.0"}, "must be positive"),
        ({"sz": "NaN"}, "must be finite"),
        ({"side": "X"}, "unknown side"),
        ({"timestamp": "now"}, "milliseconds"),
        ({"limitPx": "abc"}, "must be numeric"),
    ):
        with pytest.raises(HyperliquidProtocolError, match=match):
            parse_open_order({**base, **mutation})


def test_parse_fill_row() -> None:
    row = {
        "coin": "BTC",
        "oid": 1002,
        "tid": 92,
        "px": "107.4",
        "sz": "0.6",
        "side": "A",
        "time": T0 + 300_000,
        "fee": "0.07",
    }
    fill = parse_fill(row)
    assert fill.fill_id == "92"
    assert fill.oid == 1002
    assert fill.side is Side.BUY
    assert fill.quantity == 0.6
    assert fill.price == 107.4
    assert fill.fee == 0.07


def test_parse_fill_identity_via_hash_when_tid_missing() -> None:
    row = {
        "coin": "BTC",
        "oid": 1002,
        "hash": "0x" + "9" * 64,
        "px": "107.4",
        "sz": "0.6",
        "side": "A",
        "time": T0 + 300_000,
    }
    assert parse_fill(row).fill_id == "0x" + "9" * 64


def test_parse_fill_without_identity_fails_closed() -> None:
    row = {
        "coin": "BTC",
        "oid": 1002,
        "px": "107.4",
        "sz": "0.6",
        "side": "A",
        "time": T0 + 300_000,
    }
    with pytest.raises(HyperliquidProtocolError, match="no identity"):
        parse_fill(row)


def test_parse_position_row() -> None:
    payload = {
        "coin": "BTC",
        "szi": "-1.0",
        "entryPx": "107.2",
        "leverage": {"type": "cross", "value": 3},
        "liquidationPx": "50.0",
    }
    position = parse_position(payload)
    assert position.coin == "BTC"
    assert position.size == -1.0
    assert position.entry_price == 107.2
    assert position.leverage == 3


def test_parse_position_malformed_leverage_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="leverage"):
        parse_position({"coin": "BTC", "szi": "1.0", "leverage": {"type": 5}})


def test_build_snapshot_merges_open_order_and_fills() -> None:
    snapshot = build_snapshot(
        open_orders=[
            {"coin": "BTC", "oid": 1001, "side": "A", "sz": "1.0", "timestamp": T0}
        ],
        fills=[
            {
                "coin": "BTC",
                "oid": 1001,
                "tid": 1,
                "px": "107.4",
                "sz": "0.6",
                "side": "A",
                "time": T0 + 300_000,
                "fee": "0.07",
            }
        ],
        positions=[],
    )
    (order,) = snapshot.orders
    assert order.status == "open"
    assert order.filled_quantity == 0.6
    assert order.average_price == 107.4
    assert order.fees == [0.07]


def test_build_snapshot_marks_fills_only_rows_inactive() -> None:
    snapshot = build_snapshot(
        open_orders=[],
        fills=[
            {
                "coin": "BTC",
                "oid": 1002,
                "tid": 92,
                "px": "107.4",
                "sz": "0.6",
                "side": "A",
                "time": T0 + 300_000,
                "fee": "0.07",
            },
            {
                "coin": "BTC",
                "oid": 1002,
                "tid": 93,
                "px": "107.5",
                "sz": "0.4",
                "side": "A",
                "time": T0 + 301_000,
                "fee": "0.05",
            },
        ],
        positions=[],
    )
    (order,) = snapshot.orders
    assert order.status == "inactive"
    assert not order.declares_quantity
    assert order.filled_quantity == 1.0
    assert order.average_price == 107.44


def test_build_snapshot_refuses_contradictory_fill_rows() -> None:
    with pytest.raises(HyperliquidProtocolError, match="disagree"):
        build_snapshot(
            open_orders=[],
            fills=[
                {
                    "coin": "BTC",
                    "oid": 1002,
                    "tid": 92,
                    "px": "107.4",
                    "sz": "0.6",
                    "side": "A",
                    "time": T0 + 300_000,
                },
                {
                    "coin": "BTC",
                    "oid": 1002,
                    "tid": 93,
                    "px": "107.4",
                    "sz": "0.4",
                    "side": "B",
                    "time": T0 + 301_000,
                },
            ],
            positions=[],
        )


# --- scripted transport -----------------------------------------------------------


def test_scripted_transport_validates_its_script(tmp_path) -> None:  # noqa: ANN001
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"now": "2025-08-07T21:00:00+00:00"}\n{"now": "2025-08-07T20:00:00+00:00"}\n'
    )
    with pytest.raises(ValueError, match="does not advance"):
        ScriptedExchangeTransport(bad)
    bad.write_text('{"now": "2025-08-07T21:00:00"}\n')
    with pytest.raises(ValueError, match="timezone-aware"):
        ScriptedExchangeTransport(bad)
    bad.write_text("not json\n")
    with pytest.raises(ValueError, match="not valid JSON"):
        ScriptedExchangeTransport(bad)


def test_scripted_transport_lost_ack_withholds_the_acknowledgement() -> None:
    transport = ScriptedExchangeTransport(SCRIPT)
    transport.advance_to(P1)
    with pytest.raises(HyperliquidUnavailableError, match="acknowledgement never arrived"):
        transport.place(
            coin="BTC",
            side=Side.SELL,
            quantity=1.0,
            limit_price=107.2,
            order_type=OrderType.LIMIT,
            reduce_only=False,
            cloid=CID_1001,
        )


def test_scripted_transport_places_and_lists_orders() -> None:
    transport = ScriptedExchangeTransport(SCRIPT)
    transport.advance_to(P1 + timedelta(seconds=120))  # phase p2 lists 1001
    ack = transport.place(
        coin="BTC",
        side=Side.SELL,
        quantity=1.0,
        limit_price=107.2,
        order_type=OrderType.LIMIT,
        reduce_only=False,
        cloid=CID_1001,
    )
    assert ack == PlaceAck(oid=1001, status="resting")
    assert [o.oid for o in transport.snapshot().orders] == [1001]


def test_scripted_transport_cancels_known_orders_and_errors_otherwise() -> None:
    transport = ScriptedExchangeTransport(SCRIPT)
    transport.advance_to(P1 + timedelta(seconds=120))
    assert transport.cancel(coin="BTC", oid=1001, cloid=None).status == "success"
    assert transport.cancel(coin="BTC", oid=None, cloid=CID_1001).status == "success"
    assert transport.cancel(coin="BTC", oid=None, cloid=CID_1002).status == "error"


def test_scripted_transport_limits_to_limit_orders() -> None:
    transport = ScriptedExchangeTransport(SCRIPT)
    with pytest.raises(HyperliquidProtocolError, match="limit orders only"):
        transport.place(
            coin="BTC",
            side=Side.BUY,
            quantity=1.0,
            limit_price=None,
            order_type=OrderType.MARKET,
            reduce_only=False,
            cloid=CID_1001,
        )


# --- SDK transport with stubbed SDK ----------------------------------------------


def test_sdk_place_limit_routes_to_sdk_order(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubExchange()
    transport = sdk_exchange(monkeypatch, stub=stub)

    ack = transport.place(
        coin="BTC",
        side=Side.BUY,
        quantity=1.0,
        limit_price=107.2,
        order_type=OrderType.LIMIT,
        reduce_only=False,
        cloid=CID_1001,
    )

    assert ack.oid == 1001
    assert ack.status == "resting"
    name, args, kwargs = stub.calls[0]
    assert name == "order"
    assert args[:6] == ("BTC", True, 1.0, 107.2, {"limit": {"tif": "Gtc"}}, False)
    assert args[6].raw == "0x" + CID_1001
    assert kwargs == {}


def test_sdk_place_market_routes_to_sdk_market_open(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubExchange()
    transport = sdk_exchange(monkeypatch, stub=stub)

    ack = transport.place(
        coin="BTC",
        side=Side.SELL,
        quantity=1.0,
        limit_price=None,
        order_type=OrderType.MARKET,
        reduce_only=False,
        cloid=CID_1002,
    )

    assert ack.status == "resting"
    name, args, kwargs = stub.calls[0]
    assert name == "market_open"
    assert args == ("BTC", False, 1.0)
    assert set(kwargs) == {"cloid"}
    assert kwargs["cloid"].raw == "0x" + CID_1002


def test_sdk_place_refuses_reduce_only_market_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = sdk_exchange(monkeypatch)
    with pytest.raises(ValueError, match="reduce_only"):
        transport.place(
            coin="BTC",
            side=Side.BUY,
            quantity=1.0,
            limit_price=None,
            order_type=OrderType.MARKET,
            reduce_only=True,
            cloid=CID_1001,
        )


def test_sdk_cancel_by_oid_and_by_cloid(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubExchange()
    transport = sdk_exchange(monkeypatch, stub=stub)
    assert transport.cancel(coin="BTC", oid=1001, cloid=None).status == "success"
    assert stub.calls[0] == ("cancel", ("BTC", 1001), {})
    assert transport.cancel(coin="BTC", oid=None, cloid=CID_1001).status == "success"
    name, args, kwargs = stub.calls[1]
    assert name == "cancel_by_cloid"
    assert args[:1] == ("BTC",)
    assert args[1].raw == "0x" + CID_1001
    assert kwargs == {}


def test_sdk_cancel_needs_an_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = sdk_exchange(monkeypatch)
    with pytest.raises(ValueError, match="an oid or a cloid"):
        transport.cancel(coin="BTC", oid=None, cloid=None)


def test_sdk_snapshot_builds_from_stub_info(monkeypatch: pytest.MonkeyPatch) -> None:
    info = StubInfo()
    info.open_rows = [
        {"coin": "BTC", "oid": 1001, "side": "A", "sz": "1.0", "timestamp": T0}
    ]
    info.fill_rows = [
        {
            "coin": "BTC",
            "oid": 1001,
            "tid": 92,
            "px": "107.4",
            "sz": "0.6",
            "side": "A",
            "time": T0 + 300_000,
        }
    ]
    info.state_payload = {
        "assetPositions": [
            {
                "position": {
                    "coin": "BTC",
                    "szi": "0.6",
                    "leverage": {"type": "cross", "value": 3},
                }
            }
        ]
    }
    transport = sdk_exchange(monkeypatch, stub=StubExchange(info=info))

    snapshot = transport.snapshot()

    (order,) = snapshot.orders
    assert order.filled_quantity == 0.6
    assert [f.fill_id for f in snapshot.fills] == ["92"]
    assert snapshot.positions[0].size == 0.6


def test_sdk_snapshot_fails_closed_on_bad_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    info = StubInfo()
    info.state_payload = {"not": "positions"}
    transport = sdk_exchange(monkeypatch, stub=StubExchange(info=info))
    with pytest.raises(HyperliquidProtocolError, match="assetPositions"):
        transport.snapshot()


def test_sdk_exceptions_become_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubExchange()

    def boom(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise RuntimeError("connection reset")

    stub.order = boom
    transport = sdk_exchange(monkeypatch, stub=stub)
    with pytest.raises(HyperliquidUnavailableError, match="order failed"):
        transport.place(
            coin="BTC",
            side=Side.BUY,
            quantity=1.0,
            limit_price=107.2,
            order_type=OrderType.LIMIT,
            reduce_only=False,
            cloid=CID_1001,
        )


# --- adapter ----------------------------------------------------------------------


def _adapter(transport, tmp_path):  # noqa: ANN001
    journal = OrderJournal(tmp_path)
    return HyperliquidExecutionAdapter(transport, journal), journal


def test_adapter_place_records_journal_first_then_wires(
    monkeypatch: pytest.MonkeyPatch, tmp_path  # noqa: ANN001
) -> None:
    stub = StubExchange()
    transport = sdk_exchange(monkeypatch, stub=stub)
    adapter, journal = _adapter(transport, tmp_path)

    order = adapter.place(
        BUY_1074,
        order_id="ord-1",
        created_at=P1,
        client_order_id=CID_1002,
    )

    assert order.status is OrderStatus.ACCEPTED
    assert order.broker_order_id == "1001"
    assert journal.all()[0].order_id == "ord-1"


def test_adapter_place_lost_ack_leaves_pending_unacknowledged(tmp_path) -> None:  # noqa: ANN001
    transport = ScriptedExchangeTransport(SCRIPT)
    adapter, journal = _adapter(transport, tmp_path)
    transport.advance_to(P1)

    with pytest.raises(HyperliquidUnavailableError, match="acknowledgement never arrived"):
        adapter.place(SELL_1072, order_id="ord-lost", created_at=P1, client_order_id=CID_1001)

    (order,) = journal.all()
    assert order.status is OrderStatus.PENDING
    assert order.broker_order_id is None
    assert order.client_order_id == CID_1001


def test_adapter_place_refuses_reused_client_order_id(tmp_path) -> None:  # noqa: ANN001
    transport = ScriptedExchangeTransport(SCRIPT)
    adapter, _ = _adapter(transport, tmp_path)
    transport.advance_to(P1 + timedelta(seconds=120))
    adapter.place(SELL_1072, order_id="ord-1", created_at=P1, client_order_id=CID_1001)

    with pytest.raises(ValueError, match="already mapped"):
        adapter.place(SELL_1072, order_id="ord-2", created_at=P1, client_order_id=CID_1001)


def test_adapter_place_per_order_error_rejects_with_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path  # noqa: ANN001
) -> None:
    stub = StubExchange()
    stub.place_payload = {
        "status": "ok",
        "response": {"data": {"statuses": [{"error": "Order size too small"}]}},
    }
    transport = sdk_exchange(monkeypatch, stub=stub)
    adapter, _ = _adapter(transport, tmp_path)

    order = adapter.place(BUY_1074, order_id="ord-1", created_at=P1, client_order_id=CID_1002)

    assert order.status is OrderStatus.REJECTED
    assert "Order size too small" in order.events[-1].reason


def test_adapter_place_filled_ack_only_advances_to_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path  # noqa: ANN001
) -> None:
    stub = StubExchange()
    stub.place_payload = {
        "status": "ok",
        "response": {
            "data": {
                "statuses": [
                    {"filled": {"oid": 1001, "totalSz": "1.0", "avgPx": "107.4"}}
                ]
            }
        },
    }
    transport = sdk_exchange(monkeypatch, stub=stub)
    adapter, _ = _adapter(transport, tmp_path)

    order = adapter.place(BUY_1074, order_id="ord-1", created_at=P1, client_order_id=CID_1002)

    # Place-time "filled" acks only advance to ACCEPTED; fills arrive
    # through reconciliation, which stamps them with venue identity.
    assert order.status is OrderStatus.ACCEPTED
    assert order.filled_quantity == 0


def test_adapter_place_refuses_other_venues(tmp_path) -> None:  # noqa: ANN001
    transport = ScriptedExchangeTransport(SCRIPT)
    adapter, _ = _adapter(transport, tmp_path)
    request = OrderRequest(
        instrument=Instrument(
            symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY
        ),
        side=Side.BUY,
        quantity=1.0,
        limit_price=200.0,
    )
    with pytest.raises(ValueError, match="not a Hyperliquid instrument"):
        adapter.place(request, order_id="ord-1", created_at=P1)


def test_adapter_place_validates_client_order_id_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path  # noqa: ANN001
) -> None:
    transport = sdk_exchange(monkeypatch)
    adapter, _ = _adapter(transport, tmp_path)
    with pytest.raises(ValueError, match="32 lowercase hex"):
        adapter.place(BUY_1074, order_id="ord-1", created_at=P1, client_order_id="TOO-LONG")


def test_adapter_cancel_by_oid_and_by_cloid(tmp_path) -> None:  # noqa: ANN001
    transport = ScriptedExchangeTransport(SCRIPT)
    adapter, _ = _adapter(transport, tmp_path)
    transport.advance_to(P1 + timedelta(seconds=120))
    order = adapter.place(SELL_1072, order_id="ord-1", created_at=P1, client_order_id=CID_1001)

    canceled = adapter.cancel(order, at=P1 + timedelta(seconds=180))

    assert canceled.status is OrderStatus.CANCELED
    assert canceled.events[-1].timestamp == P1 + timedelta(seconds=180)


def test_adapter_cancel_by_cloid_when_oid_unknown(tmp_path) -> None:  # noqa: ANN001
    transport = ScriptedExchangeTransport(SCRIPT)
    adapter, _ = _adapter(transport, tmp_path)
    transport.advance_to(P1 + timedelta(seconds=120))
    order = adapter.place(SELL_1072, order_id="ord-1", created_at=P1, client_order_id=CID_1001)
    unacknowledged = order.model_copy(update={"broker_order_id": None})

    canceled = adapter.cancel(unacknowledged, at=P1 + timedelta(seconds=180))

    assert canceled.status is OrderStatus.CANCELED


def test_adapter_cancel_refused_by_venue_raises(tmp_path) -> None:  # noqa: ANN001
    transport = ScriptedExchangeTransport(SCRIPT)
    adapter, _ = _adapter(transport, tmp_path)
    transport.advance_to(P1 + timedelta(seconds=120))
    order = adapter.place(SELL_1072, order_id="ord-1", created_at=P1, client_order_id=CID_1001)
    # At p5 the venue only lists order 1002; canceling 1001 (already
    # forgotten by the venue in later phases) is a venue refusal.
    transport.advance_to(P1 + timedelta(seconds=300))
    with pytest.raises(HyperliquidProtocolError, match="refused the cancel"):
        adapter.cancel(order, at=P1 + timedelta(seconds=300))
