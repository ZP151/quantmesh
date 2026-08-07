"""Testnet-only Hyperliquid exchange surface (M5, issue #30, Phase B).

The venue's trade surface is reached through the pinned SDK's
``Exchange`` class exactly like the market-data boundary (ADR-0007):
lazy and import-guarded (unit tests never import the SDK), testnet
pinned, mainnet refused before the wire. Signing stays inside the SDK;
this module only injects the key material through an in-memory signer
that is never persisted, logged, or reported.

The client-order-id channel replaces the Moomoo remark channel: a client
order id is exactly 32 lowercase hex characters and becomes the venue's
``cloid`` (``0x`` + 32 hex). Identity is journal-first — the id is
recorded in the journal before the wire, and an id already mapped
refuses submission — so after a lost acknowledgement the mapping is
recovered from the venue's own cloid echo and a reconnect never
re-submits (the Phase B extension of ADR-0007).

Wire contracts are derived from the pinned SDK source: ``order`` /
``market_open`` responses (``{"status": "ok"|"err", "response":
{"data": {"statuses": [{"resting"|"filled": {...}} | {"error": "..."}]}}``),
``cancel`` / ``cancel_by_cloid`` acks (``["success" | {"error": "..."}]``),
``openOrders`` rows, ``userFills`` rows (``tid``/``hash`` identity, fee
when the venue reports one), and ``userState`` asset positions with
signed ``szi``. The snapshot builds one ``BrokerOrder`` per venue order:
``open`` while the venue lists it, ``inactive`` once the venue's surface
is silent and only fills remain — the reconciliation derives the honest
terminal meaning from fills and journal state (never guessing).
"""

import json
import math
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import OrderRequest, Side, Venue
from quantmesh.domain.orders import (
    Order,
    OrderEventType,
    OrderStateMachine,
    OrderType,
)
from quantmesh.execution.journal import OrderJournal
from quantmesh.hyperliquid.errors import (
    HyperliquidError,
    HyperliquidProtocolError,
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.rest import TESTNET_API_URL
from quantmesh.hyperliquid.wire import ms_to_utc

__all__ = [
    "BrokerFill",
    "BrokerOrder",
    "BrokerPosition",
    "CancelAck",
    "ExchangeTransport",
    "ExecutionSnapshot",
    "HyperliquidExecutionAdapter",
    "HyperliquidSigner",
    "InMemorySigner",
    "PlaceAck",
    "ScriptedExchangeTransport",
    "SdkExchangeTransport",
    "build_snapshot",
    "parse_cancel_ack",
    "parse_fill",
    "parse_open_order",
    "parse_place_ack",
    "parse_position",
    "signer_from_env",
    "to_cloid",
]

# --- wire models ---------------------------------------------------------------


class BrokerOrder(BaseModel):
    """One venue-side order, derived from the venue's surface.

    ``status`` is ``"open"`` while the venue lists the order (with its
    declared ``sz``) and ``"inactive"`` once the venue's surface is
    silent and only fill rows remain — the original order size is then
    unknown, so ``declares_quantity`` is False and the reconciliation
    compares fills instead of order sizes.
    """

    oid: int
    coin: str
    side: Side
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, ge=0)
    created: datetime | None = None
    cloid: str | None = None
    status: str
    filled_quantity: float = Field(default=0, ge=0)
    average_price: float | None = Field(default=None, ge=0)
    fees: list[float] = Field(default_factory=list)
    declares_quantity: bool = True


class BrokerFill(BaseModel):
    """One venue-reported fill (a ``userFills`` row).

    ``fill_id`` is the venue's own identity for the fill — ``tid`` when
    present, else the transaction ``hash`` — and is stamped on the
    journal fill at adoption (ADR-0006 decision 4). ``fee`` is the
    venue-reported execution fee when the venue reports one; adoption
    refuses a fee-less fill (M4 discipline).
    """

    fill_id: str
    oid: int
    coin: str
    side: Side
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    timestamp: datetime
    fee: float | None = Field(default=None, ge=0)
    cloid: str | None = None

    @model_validator(mode="after")
    def side_is_concrete(self) -> "BrokerFill":
        _require_side(self.side, f"fill {self.fill_id}")
        return self


class BrokerPosition(BaseModel):
    """One venue account position (a ``userState`` asset position).

    ``size`` is the signed ``szi`` — positive for a long, negative for
    a short — so the account-level position comparison needs no side
    guessing.
    """

    coin: str
    size: float
    entry_price: float | None = Field(default=None, ge=0)
    liquidation_price: float | None = Field(default=None, ge=0)
    leverage: int | None = Field(default=None, ge=1)
    unrealized_pnl: float | None = None


class ExecutionSnapshot(BaseModel):
    """The venue-side state a reconciliation run compares against."""

    orders: list[BrokerOrder] = Field(default_factory=list)
    fills: list[BrokerFill] = Field(default_factory=list)
    positions: list[BrokerPosition] = Field(default_factory=list)


class PlaceAck(BaseModel):
    """The venue's answer to one ``place``.

    ``status`` is ``"resting"`` (on the book), ``"filled"`` (executed
    immediately — the fills arrive through the snapshot), or ``"error"``
    (the venue refused the order; ``message`` carries the reason).
    """

    oid: int | None = None
    status: str
    message: str | None = None


class CancelAck(BaseModel):
    """The venue's answer to one cancel: ``"success"`` or ``"error"``."""

    status: str
    message: str | None = None


# --- signer --------------------------------------------------------------------

@runtime_checkable
class HyperliquidSigner(Protocol):
    """In-memory testnet signer: key material never leaves memory."""

    private_key: bytes


@dataclass(frozen=True)
class InMemorySigner:
    """A testnet private key held in memory only (ADR-0007 Phase B/E).

    Constructed from exactly 32 key bytes; the address is derived lazily
    inside the SDK boundary, so no key or address material ever appears
    in the journal, fixtures, reports, or logs.
    """

    private_key: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.private_key, bytes) or len(self.private_key) != 32:
            raise ValueError(
                "a Hyperliquid signer private key must be exactly 32 bytes "
                f"(got {type(self.private_key).__name__})"
            )


def signer_from_env(env_name: str = "QUANTMESH_HYPERLIQUID_PRIVATE_KEY") -> InMemorySigner:
    """Build an in-memory signer from an env var (the Phase E operator path).

    The env value is a 64-hex-character (optionally ``0x``-prefixed)
    private key. Missing, malformed, or wrong-length values fail closed;
    nothing is written anywhere.
    """
    raw = os.environ.get(env_name)
    if not raw:
        raise HyperliquidUnavailableError(
            f"no testnet signer: {env_name} is not set"
        )
    value = raw.removeprefix("0x")
    try:
        key = bytes.fromhex(value)
    except ValueError as error:
        raise HyperliquidProtocolError(
            f"{env_name} must hold a hex private key, not {value!r}"
        ) from error
    if len(key) != 32:
        raise HyperliquidProtocolError(
            f"{env_name} must hold a 64-hex-character private key "
            f"(got {len(value)} hex characters)"
        )
    return InMemorySigner(key)


# --- transport boundary ----------------------------------------------------------

@runtime_checkable
class ExchangeTransport(Protocol):
    """Venue trade surface; implementations are never default-constructed."""

    def place(
        self,
        *,
        coin: str,
        side: Side,
        quantity: float,
        limit_price: float | None,
        order_type: OrderType,
        reduce_only: bool,
        cloid: str,
    ) -> PlaceAck:
        """Submit to the TESTNET account; returns the venue ack."""

    def cancel(self, *, coin: str, oid: int | None, cloid: str | None) -> CancelAck:
        """Cancel by venue order id or client order id (cloid)."""

    def snapshot(self) -> ExecutionSnapshot:
        """Current venue orders, fills, and positions."""


class ScriptedExchangeTransport:
    """Deterministic testnet stub replaying a fixture phase script.

    The script is JSONL, one phase per line:

    ``{"now": "2025-08-07T21:00:00+00:00", "open_orders": [...],
    "fills": [...], "positions": [...], "lost_acks": [1001]}``

    ``now`` is required, aware, and strictly increasing. The transport's
    state at time *t* is the phase with the latest ``now <= t`` — pure
    declaration, never mutated. ``place`` assigns the next venue order id
    deterministically (``1001``, ``1002``, …); if that id is listed in the
    current phase's ``lost_acks`` the venue records the order but the
    acknowledgement is withheld (``HyperliquidUnavailableError``) — the
    disconnect gap the reconciliation's cloid channel recovers. Filled and
    canceled states are declared in later phases, so a replay is a pure
    function of the script plus the scripted operations. Only limit
    orders are scriptable; market orders fail closed.
    """

    def __init__(self, script: Path | str | list[dict]) -> None:
        if isinstance(script, str):
            script = Path(script)
        phases = _load_jsonl(script) if isinstance(script, Path) else script
        if not phases:
            raise ValueError("fixture script has no phases")
        self._phases = [_validate_phase(phase, index) for index, phase in enumerate(phases)]
        for previous, current in zip(self._phases, self._phases[1:]):
            if current["now"] <= previous["now"]:
                raise ValueError(
                    f"fixture phase {current!r} does not advance the clock"
                )
        self._now = self._phases[0]["now"]
        self._placed = 0

    @property
    def now(self) -> datetime:
        return self._now

    @property
    def end(self) -> datetime:
        """The script's final phase instant — the default replay target."""
        return self._phases[-1]["now"]

    def advance_to(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("advance_to requires a timezone-aware time")
        if now < self._now:
            raise ValueError(f"cannot move time backwards ({now} < {self._now})")
        self._now = now

    def place(
        self,
        *,
        coin: str,
        side: Side,
        quantity: float,
        limit_price: float | None,
        order_type: OrderType,
        reduce_only: bool,
        cloid: str,
    ) -> PlaceAck:
        if order_type is not OrderType.LIMIT:
            raise HyperliquidProtocolError(
                "the scripted transport places limit orders only"
            )
        self._placed += 1
        oid = 1000 + self._placed
        if oid in self._phase()["lost_acks"]:
            raise HyperliquidUnavailableError(
                f"connection lost; the venue recorded order {oid} but the "
                "acknowledgement never arrived"
            )
        return PlaceAck(oid=oid, status="resting")

    def cancel(self, *, coin: str, oid: int | None, cloid: str | None) -> CancelAck:
        known = self._phase()["open_orders"]
        by_oid = oid is not None and any(row.get("oid") == oid for row in known)
        by_cloid = (
            cloid is not None
            and any(row.get("cloid") == to_cloid(cloid) for row in known)
        )
        if not by_oid and not by_cloid:
            return CancelAck(
                status="error",
                message=(
                    f"no open order matching oid {oid} or cloid {cloid!r} "
                    f"at {self._now}"
                ),
            )
        return CancelAck(status="success")

    def snapshot(self) -> ExecutionSnapshot:
        # Rows go through the same wire parsers as the live SDK path, so
        # a fixture failure is a parser failure (ADR-0007 decision 5).
        phase = self._phase()
        return build_snapshot(
            open_orders=phase["open_orders"],
            fills=phase["fills"],
            positions=phase["positions"],
        )

    def _phase(self) -> dict:
        current = self._phases[0]
        for phase in self._phases:
            if phase["now"] <= self._now:
                current = phase
            else:
                break
        return current


class SdkExchangeTransport:
    """Lazy testnet exchange transport over the vendored SDK.

    Explicit construction with an injected in-memory signer; testnet
    pinned and mainnet refused at construction (ADR-0007 decision 2).
    The SDK — including the ``eth_account`` signer it builds from the
    injected key — is imported only on first use, so unit tests never
    import it. Any SDK exception becomes ``HyperliquidUnavailableError``;
    a missing SDK becomes ``HyperliquidSDKMissingError``.
    """

    def __init__(
        self,
        signer: HyperliquidSigner,
        *,
        base_url: str | None = None,
        request_timeout_s: float = 10.0,
    ) -> None:
        if base_url is not None and base_url != TESTNET_API_URL:
            raise HyperliquidProtocolError(
                f"refusing base URL {base_url!r}: only the testnet endpoint "
                f"{TESTNET_API_URL} is reachable from this adapter"
            )
        self._signer = signer
        self._base_url = base_url or TESTNET_API_URL
        self._request_timeout_s = request_timeout_s
        self._exchange = None
        self._cloid_type = None

    # -- lazy SDK boundary ---------------------------------------------------

    def _sdk(self):
        if self._exchange is not None:
            return self._exchange
        try:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils.types import Cloid
        except ImportError as error:
            raise HyperliquidSDKMissingError(
                "the vendored hyperliquid-python-sdk is not importable"
            ) from error
        self._cloid_type = Cloid
        try:
            account = Account.from_key(self._signer.private_key)
            self._exchange = Exchange(
                account, base_url=self._base_url, timeout=self._request_timeout_s
            )
        except Exception as error:
            raise HyperliquidUnavailableError(
                f"testnet exchange handshake failed: {error}"
            ) from error
        return self._exchange

    def _sdk_cloid(self, client_order_id: str) -> object:
        return self._cloid_type(to_cloid(client_order_id))

    def _call(self, name: str, *args: object, **kwargs: object) -> object:
        try:
            return getattr(self._sdk(), name)(*args, **kwargs)
        except HyperliquidError:
            raise
        except Exception as error:
            raise HyperliquidUnavailableError(f"{name} failed: {error}") from error

    # -- ExchangeTransport surface ---------------------------------------------

    def place(
        self,
        *,
        coin: str,
        side: Side,
        quantity: float,
        limit_price: float | None,
        order_type: OrderType,
        reduce_only: bool,
        cloid: str,
    ) -> PlaceAck:
        is_buy = side is Side.BUY
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise ValueError("a limit order needs a limit price")
            payload = self._call(
                "order",
                coin,
                is_buy,
                quantity,
                limit_price,
                {"limit": {"tif": "Gtc"}},
                reduce_only,
                self._sdk_cloid(cloid),
            )
        elif order_type is OrderType.MARKET:
            if reduce_only:
                # The venue's market_open path hard-codes reduce_only=False
                # in the pinned SDK; a reduce-only market order must not be
                # silently re-typed as a fresh position (Phase C handles
                # position closing with reduce-only LIMIT orders).
                raise ValueError(
                    "the venue's market-open path cannot carry reduce_only"
                )
            payload = self._call(
                "market_open", coin, is_buy, quantity, cloid=self._sdk_cloid(cloid)
            )
        else:  # pragma: no cover - the domain enum has two members
            raise ValueError(f"unknown order type {order_type!r}")
        return parse_place_ack(payload, sent_cloid=cloid)

    def cancel(self, *, coin: str, oid: int | None, cloid: str | None) -> CancelAck:
        if oid is not None:
            payload = self._call("cancel", coin, oid)
        elif cloid is not None:
            payload = self._call("cancel_by_cloid", coin, self._sdk_cloid(cloid))
        else:
            raise ValueError("cancel needs an oid or a cloid")
        return parse_cancel_ack(payload)

    def snapshot(self) -> ExecutionSnapshot:
        exchange = self._sdk()
        address = exchange.wallet.address
        info = exchange.info
        try:
            open_rows = info.open_orders(address)
            fill_rows = info.user_fills(address)
            state = info.user_state(address)
        except HyperliquidError:
            raise
        except Exception as error:
            raise HyperliquidUnavailableError(f"snapshot failed: {error}") from error
        if not isinstance(open_rows, list):
            raise HyperliquidProtocolError(
                f"openOrders must be a list, got {type(open_rows).__name__}"
            )
        if not isinstance(fill_rows, list):
            raise HyperliquidProtocolError(
                f"userFills must be a list, got {type(fill_rows).__name__}"
            )
        positions = state.get("assetPositions") if isinstance(state, dict) else None
        if not isinstance(positions, list):
            raise HyperliquidProtocolError(
                "userState must be an object with an assetPositions list, "
                f"got {type(state).__name__}"
            )
        position_payloads = []
        for index, row in enumerate(positions):
            if not isinstance(row, dict) or not isinstance(row.get("position"), dict):
                raise HyperliquidProtocolError(
                    f"assetPositions[{index}] must be an object with a position object"
                )
            position_payloads.append(row["position"])
        return build_snapshot(
            open_orders=open_rows,
            fills=fill_rows,
            positions=position_payloads,
        )


# --- adapter -------------------------------------------------------------------

class HyperliquidExecutionAdapter:
    """Journal-first testnet execution surface (ADR-0007 Phase B).

    Explicit construction: transport and journal are injected; nothing
    is default-constructed. ``place`` records the order in the journal
    BEFORE the wire: the client order id (the venue cloid seed) is
    journal-owned before submission, and an id already mapped refuses
    submission — re-derive-on-reconnect never re-submits. A lost
    acknowledgement leaves the order recorded as PENDING; reconciliation
    recovers the mapping from the venue's cloid echo and re-stamps the
    oid. ``cancel`` applies the venue-confirmed cancel through the state
    machine — the venue's surface forgets canceled orders, so the ack is
    the only honest terminal record.
    """

    def __init__(self, transport: ExchangeTransport, journal: OrderJournal) -> None:
        self.transport = transport
        self.journal = journal

    def place(
        self,
        request: OrderRequest,
        *,
        order_id: str | None = None,
        created_at: datetime | None = None,
        client_order_id: str | None = None,
        reduce_only: bool = False,
    ) -> Order:
        if request.instrument.venue is not Venue.HYPERLIQUID:
            raise ValueError(
                f"instrument {request.instrument.symbol!r} is not a Hyperliquid "
                "instrument"
            )
        order_id = order_id or uuid.uuid4().hex
        created_at = created_at or datetime.now(UTC)
        client_order_id = client_order_id or request.client_order_id or uuid.uuid4().hex
        to_cloid(client_order_id)  # validates the 32-hex shape up front
        order = Order.from_request(request, order_id=order_id, created_at=created_at)
        order = order.model_copy(update={"client_order_id": client_order_id})

        # Journal-first: the client id is journal-owned before the wire,
        # and a client id already mapped refuses submission.
        if any(
            recorded.client_order_id == client_order_id
            for recorded in self.journal.all()
        ):
            raise ValueError(
                f"client order id {client_order_id!r} is already mapped; "
                "refusing to re-submit"
            )
        self.journal.record(order)

        try:
            ack = self.transport.place(
                coin=order.instrument.symbol,
                side=order.side,
                quantity=order.quantity,
                limit_price=order.limit_price,
                order_type=order.order_type,
                reduce_only=reduce_only,
                cloid=client_order_id,
            )
        except HyperliquidError:
            # The order stays PENDING and unacknowledged in the journal;
            # the reconnect path re-derives its mapping from the venue.
            raise
        if ack.status == "error":
            order = OrderStateMachine.apply(
                order,
                OrderEventType.REJECTED,
                reason=ack.message,
                timestamp=created_at,
            )
        else:
            order = OrderStateMachine.apply(
                order, OrderEventType.ACCEPTED, timestamp=created_at
            )
            if ack.oid is not None:
                order = order.model_copy(update={"broker_order_id": str(ack.oid)})
        return self.journal.update(order)

    def cancel(self, order: Order, *, at: datetime | None = None) -> Order:
        oid = None if order.broker_order_id is None else int(order.broker_order_id)
        cloid = order.client_order_id
        if oid is None and cloid is None:
            raise ValueError(
                f"order {order.order_id!r} has no venue identity; cancel is impossible"
            )
        ack = self.transport.cancel(
            coin=order.instrument.symbol,
            oid=oid,
            cloid=cloid,
        )
        if ack.status == "error":
            raise HyperliquidProtocolError(
                f"the venue refused the cancel: {ack.message}"
            )
        order = OrderStateMachine.apply(
            order,
            OrderEventType.CANCELED,
            timestamp=at or datetime.now(UTC),
        )
        return self.journal.update(order)

    def refresh(self) -> ExecutionSnapshot:
        return self.transport.snapshot()


# --- parsing helpers ------------------------------------------------------------

def to_cloid(client_order_id: str) -> str:
    """client order id → venue cloid: exactly 32 lowercase hex characters.

    The cloid channel is the Hyperliquid remark channel (ADR-0007 Phase
    B), and the venue's shape is fixed — anything else fails closed
    before the wire.
    """
    if (
        not isinstance(client_order_id, str)
        or len(client_order_id) != 32
        or any(char not in "0123456789abcdef" for char in client_order_id)
    ):
        raise ValueError(
            "a Hyperliquid client order id must be exactly 32 lowercase hex "
            f"characters (got {client_order_id!r})"
        )
    return "0x" + client_order_id


def parse_open_order(row: object) -> BrokerOrder:
    """One ``openOrders`` row → ``BrokerOrder`` (status ``"open"``)."""
    if not isinstance(row, dict):
        raise HyperliquidProtocolError("an openOrders row must be an object")
    coin = row.get("coin")
    if not isinstance(coin, str) or not coin:
        raise HyperliquidProtocolError("an openOrders row needs a 'coin' string")
    oid = row.get("oid")
    if isinstance(oid, bool) or not isinstance(oid, int):
        raise HyperliquidProtocolError(f"order {oid!r} must have an integer oid")
    sz = _positive_float(row, "sz")
    limit_px = _opt_finite_float(row.get("limitPx"), "limitPx")
    timestamp = row.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise HyperliquidProtocolError(
            f"order {oid} needs an integer 'timestamp' in milliseconds"
        )
    return BrokerOrder(
        oid=oid,
        coin=coin,
        side=_side_of(row.get("side"), f"order {oid}"),
        quantity=sz,
        limit_price=limit_px,
        created=ms_to_utc(timestamp),
        cloid=_opt_cloid(row.get("cloid"), f"order {oid}"),
        status="open",
    )


def parse_fill(row: object) -> BrokerFill:
    """One ``userFills`` row → ``BrokerFill``.

    ``tid`` is the venue's per-fill sequence; a row without ``tid`` must
    carry a transaction ``hash`` — a fill without venue identity cannot
    be stamped on the journal (ADR-0006 decision 4).
    """
    if not isinstance(row, dict):
        raise HyperliquidProtocolError("a userFills row must be an object")
    coin = row.get("coin")
    if not isinstance(coin, str) or not coin:
        raise HyperliquidProtocolError("a userFills row needs a 'coin' string")
    oid = row.get("oid")
    if isinstance(oid, bool) or not isinstance(oid, int):
        raise HyperliquidProtocolError("a userFills row needs an integer 'oid'")
    tid = row.get("tid")
    if tid is not None and (isinstance(tid, bool) or not isinstance(tid, int)):
        raise HyperliquidProtocolError(
            f"fill for order {oid} has a non-integer 'tid'"
        )
    fill_hash = row.get("hash")
    if fill_hash is not None and not isinstance(fill_hash, str):
        raise HyperliquidProtocolError(f"fill for order {oid} has a non-string 'hash'")
    if tid is None and not fill_hash:
        raise HyperliquidProtocolError(
            f"fill for order {oid} has no identity: neither 'tid' nor 'hash'"
        )
    px = _positive_float(row, "px")
    sz = _positive_float(row, "sz")
    time = row.get("time")
    if isinstance(time, bool) or not isinstance(time, int):
        raise HyperliquidProtocolError(
            f"fill for order {oid} needs an integer 'time' in milliseconds"
        )
    return BrokerFill(
        fill_id=str(tid) if tid is not None else fill_hash,
        oid=oid,
        coin=coin,
        side=_side_of(row.get("side"), f"fill for order {oid}"),
        quantity=sz,
        price=px,
        timestamp=ms_to_utc(time),
        fee=_opt_finite_float(row.get("fee"), f"fee for fill of order {oid}"),
        cloid=_opt_cloid(row.get("cloid"), f"fill for order {oid}"),
    )


def parse_position(payload: object) -> BrokerPosition:
    """One ``userState`` asset position → ``BrokerPosition`` (signed size)."""
    if not isinstance(payload, dict):
        raise HyperliquidProtocolError("an asset position must be an object")
    coin = payload.get("coin")
    if not isinstance(coin, str) or not coin:
        raise HyperliquidProtocolError("an asset position needs a 'coin' string")
    szi = _finite_float(payload.get("szi"), f"position {coin}")
    leverage = payload.get("leverage")
    leverage_value = None
    if leverage is not None:
        if (
            not isinstance(leverage, dict)
            or not isinstance(leverage.get("type"), str)
            or isinstance(leverage.get("value"), bool)
            or not isinstance(leverage.get("value"), int)
        ):
            raise HyperliquidProtocolError(
                f"position {coin} has a malformed 'leverage' object"
            )
        leverage_value = leverage["value"]
    return BrokerPosition(
        coin=coin,
        size=szi,
        entry_price=_opt_finite_float(payload.get("entryPx"), f"entryPx of {coin}"),
        liquidation_price=_opt_finite_float(
            payload.get("liquidationPx"), f"liquidationPx of {coin}"
        ),
        leverage=leverage_value,
        unrealized_pnl=_opt_finite_float(
            payload.get("unrealizedPnl"), f"unrealizedPnl of {coin}"
        ),
    )


def build_snapshot(
    *,
    open_orders: list[dict],
    fills: list[dict],
    positions: list[dict],
) -> ExecutionSnapshot:
    """Merge raw venue rows into one deterministic snapshot.

    One ``BrokerOrder`` per venue oid: ``open`` while the venue lists it
    (fills merged into it), ``inactive`` once only fill rows remain —
    the venue no longer reports the order size, so ``declares_quantity``
    is False. Fill rows for the same oid must agree on coin and side.
    """
    open_rows = [parse_open_order(row) for row in open_orders]
    fill_rows = [parse_fill(row) for row in fills]
    open_by_oid = {order.oid: order for order in open_rows}
    fills_by_oid: dict[int, list[BrokerFill]] = {}
    for fill in fill_rows:
        fills_by_oid.setdefault(fill.oid, []).append(fill)

    orders = []
    for oid in sorted(set(open_by_oid) | set(fills_by_oid)):
        fills_for = fills_by_oid.get(oid, [])
        if fills_for:
            reference = fills_for[0]
            if any(
                fill.coin != reference.coin or fill.side is not reference.side
                for fill in fills_for[1:]
            ):
                raise HyperliquidProtocolError(
                    f"fill rows for order {oid} disagree on coin or side"
                )
        if oid in open_by_oid:
            order = open_by_oid[oid]
            if fills_for:
                order = order.model_copy(
                    update={
                        "filled_quantity": sum(f.quantity for f in fills_for),
                        "average_price": _average_price(fills_for),
                        "fees": [f.fee for f in fills_for if f.fee is not None],
                    }
                )
        else:
            filled = sum(f.quantity for f in fills_for)
            order = BrokerOrder(
                oid=oid,
                coin=fills_for[0].coin,
                side=fills_for[0].side,
                quantity=filled,
                limit_price=None,
                created=None,
                cloid=next(
                    (f.cloid for f in fills_for if f.cloid is not None), None
                ),
                status="inactive",
                filled_quantity=filled,
                average_price=_average_price(fills_for),
                fees=[f.fee for f in fills_for if f.fee is not None],
                declares_quantity=False,
            )
        orders.append(order)

    return ExecutionSnapshot(
        orders=orders,
        fills=fill_rows,
        positions=[parse_position(payload) for payload in positions],
    )


def parse_place_ack(payload: object, *, sent_cloid: str) -> PlaceAck:
    """The ``order``/``market_open`` response → ``PlaceAck``.

    A top-level ``"err"`` means the whole action was refused — that
    raises: the order never reached the venue. A per-order ``"error"``
    is the venue rejecting the order itself; the adapter records it as a
    journal rejection. The venue's cloid echo, when present, must match
    the cloid that was sent — a mismatch is an identity violation.
    """
    if not isinstance(payload, dict):
        raise HyperliquidProtocolError(
            f"a place response must be an object, got {type(payload).__name__}"
        )
    status = payload.get("status")
    if status == "err":
        raise HyperliquidProtocolError(
            f"the venue refused the action: {payload.get('response')}"
        )
    if status != "ok":
        raise HyperliquidProtocolError(
            f"a place response needs status 'ok' or 'err', got {status!r}"
        )
    statuses = _response_statuses(payload, "place")
    if len(statuses) != 1:
        raise HyperliquidProtocolError(
            f"a single order must produce exactly one status, got {len(statuses)}"
        )
    entry = statuses[0]
    if not isinstance(entry, dict):
        raise HyperliquidProtocolError(
            f"a place status must be an object, got {type(entry).__name__}"
        )
    if "error" in entry:
        message = entry["error"]
        if not isinstance(message, str):
            raise HyperliquidProtocolError("a place error status needs a string message")
        return PlaceAck(status="error", message=message)
    for kind in ("resting", "filled"):
        if kind in entry:
            inner = entry[kind]
            if not isinstance(inner, dict):
                raise HyperliquidProtocolError(
                    f"a {kind!r} status must be an object"
                )
            oid = inner.get("oid")
            if isinstance(oid, bool) or not isinstance(oid, int):
                raise HyperliquidProtocolError(
                    f"a {kind!r} status needs an integer oid"
                )
            echo = inner.get("cloid")
            if echo is not None:
                if not isinstance(echo, str) or echo != to_cloid(sent_cloid):
                    raise HyperliquidProtocolError(
                        f"cloid echo mismatch: sent {to_cloid(sent_cloid)!r}, "
                        f"echoed {echo!r}"
                    )
            if kind == "filled":
                for key in ("totalSz", "avgPx"):
                    if key in inner:
                        _positive_float(inner, key)
            return PlaceAck(oid=oid, status=kind)
    raise HyperliquidProtocolError(
        f"unknown place status {list(entry)!r}; expected resting, filled, or error"
    )


def parse_cancel_ack(payload: object) -> CancelAck:
    """The ``cancel``/``cancel_by_cloid`` response → ``CancelAck``."""
    if not isinstance(payload, dict):
        raise HyperliquidProtocolError(
            f"a cancel response must be an object, got {type(payload).__name__}"
        )
    status = payload.get("status")
    if status == "err":
        raise HyperliquidProtocolError(
            f"the venue refused the cancel action: {payload.get('response')}"
        )
    if status != "ok":
        raise HyperliquidProtocolError(
            f"a cancel response needs status 'ok' or 'err', got {status!r}"
        )
    statuses = _response_statuses(payload, "cancel")
    if len(statuses) != 1:
        raise HyperliquidProtocolError(
            f"a single cancel must produce exactly one status, got {len(statuses)}"
        )
    entry = statuses[0]
    if entry == "success":
        return CancelAck(status="success")
    if isinstance(entry, dict) and isinstance(entry.get("error"), str):
        return CancelAck(status="error", message=entry["error"])
    raise HyperliquidProtocolError(
        f"a cancel status must be 'success' or an error object, got {entry!r}"
    )


# --- small helpers ----------------------------------------------------------------

def _response_statuses(payload: dict, surface: str) -> list:
    response = payload.get("response")
    if not isinstance(response, dict):
        raise HyperliquidProtocolError(
            f"a {surface} response needs a 'response' object, got "
            f"{type(response).__name__}"
        )
    data = response.get("data")
    if not isinstance(data, dict):
        raise HyperliquidProtocolError(
            f"a {surface} response needs a 'response.data' object, got "
            f"{type(data).__name__}"
        )
    statuses = data.get("statuses")
    if not isinstance(statuses, list):
        raise HyperliquidProtocolError(
            f"a {surface} response needs a 'response.data.statuses' list, got "
            f"{type(statuses).__name__}"
        )
    return statuses


def _positive_float(row: dict, key: str) -> float:
    value = _finite_float(row.get(key), f"'{key}'")
    if value <= 0:
        raise HyperliquidProtocolError(f"'{key}' must be positive, got {value:g}")
    return value


def _finite_float(value: object, where: str) -> float:
    if isinstance(value, bool) or value is None:
        raise HyperliquidProtocolError(f"{where} must be numeric, got {value!r}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise HyperliquidProtocolError(
            f"{where} must be numeric, got {value!r}"
        ) from error
    if not math.isfinite(parsed):
        raise HyperliquidProtocolError(f"{where} must be finite, got {value!r}")
    return parsed


def _opt_finite_float(value: object, where: str) -> float | None:
    if value is None:
        return None
    return _finite_float(value, where)


def _side_of(marker: object, where: str) -> Side:
    if marker == "A":
        return Side.BUY
    if marker == "B":
        return Side.SELL
    raise HyperliquidProtocolError(f"{where} has unknown side marker {marker!r}")


def _require_side(side: Side, where: str) -> None:
    if side is not Side.BUY and side is not Side.SELL:
        raise HyperliquidProtocolError(f"{where} has an unknown side {side!r}")


def _opt_cloid(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 34 or not value.startswith("0x"):
        raise HyperliquidProtocolError(f"{where} has a malformed cloid {value!r}")
    if any(char not in "0123456789abcdef" for char in value[2:]):
        raise HyperliquidProtocolError(f"{where} has a malformed cloid {value!r}")
    return value


def _average_price(fills: list[BrokerFill]) -> float | None:
    if not fills:
        return None
    notional = sum(fill.quantity * fill.price for fill in fills)
    return notional / sum(fill.quantity for fill in fills)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise ValueError(f"fixture script {path} does not exist")
    phases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            phases.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"fixture script {path} line {line_number} is not valid JSON"
            ) from error
    return phases


def _validate_phase(phase: dict, index: int) -> dict:
    if not isinstance(phase, dict):
        raise ValueError(f"fixture phase {index} must be an object")
    now = phase.get("now")
    if not isinstance(now, str):
        raise ValueError(f"fixture phase {index} needs an ISO 'now' string")
    try:
        parsed_now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"fixture phase {index} has an unparseable 'now' {now!r}"
        ) from error
    if parsed_now.tzinfo is None:
        raise ValueError(f"fixture phase {index} 'now' must be timezone-aware")
    # The four state keys are optional but always complete after
    # validation, so readers can index them directly.
    for key in ("open_orders", "fills", "positions", "lost_acks"):
        if key in phase and not isinstance(phase[key], list):
            raise ValueError(f"fixture phase {index} {key!r} must be a list")
        phase.setdefault(key, [])
    for oid in phase["lost_acks"]:
        if isinstance(oid, bool) or not isinstance(oid, int):
            raise ValueError(
                f"fixture phase {index} lost_acks entries must be integer oids"
            )
    phase["now"] = parsed_now
    return phase


