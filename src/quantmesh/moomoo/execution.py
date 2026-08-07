"""Simulated-only Moomoo order/status/fill adapter (issue #28, Phase D).

The broker's simulated account is a real fill source — its deals are
facts — so this adapter is the only surface that talks to it. It is
explicit-construction-only: the caller supplies a transport, there is
no registry entry, no default transport, and nothing reachable from a
bare import. ``place`` pins the SDK trade environment to
``TrdEnv.SIMULATE`` and refuses anything else before it reaches the
wire (ADR-0006 decision 6). Unit tests and fixture drills run entirely
on ``SimulatedFixtureTransport``; the vendored SDK is reached only
through the lazy ``SdkTradeTransport`` constructed by an explicit
operator command (Phase E gate).

Wire models mirror the vendored SDK's order/deal/position columns
(order_list_query, deal_list_query, position_list_query) with venue-local
wall-clock times converted to UTC by market-prefix zone (ADR-0004), so a
``BrokerOrder`` is comparable to journal state without guessing.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Side
from quantmesh.domain.orders import Order, OrderType
from quantmesh.moomoo.market_data import market_zone, sdk_code
from quantmesh.moomoo.opend import (
    OpenDProtocolError,
    OpenDUnavailableError,
)

# SDK venue-local time formats (the OpenD trade responses use
# "YYYY-MM-DD HH:MM:SS" wall-clock strings; fixtures may use ISO 8601).
_BROKER_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
)


class BrokerOrder(BaseModel):
    """One broker-side order (SDK order_list_query columns, ADR-0006)."""

    order_id: str
    code: str
    qty: float = Field(gt=0)
    price: float | None = Field(default=None, ge=0)
    dealt_qty: float = Field(default=0, ge=0)
    dealt_avg_price: float | None = Field(default=None, ge=0)
    order_status: str
    trd_side: str
    create_time: datetime
    updated_time: datetime | None = None
    remark: str | None = None
    currency: str | None = None
    last_err_msg: str | None = None

    @model_validator(mode="after")
    def times_are_aware(self) -> "BrokerOrder":
        if self.create_time.tzinfo is None:
            raise ValueError("create_time must be timezone-aware")
        if self.updated_time is not None and self.updated_time.tzinfo is None:
            raise ValueError("updated_time must be timezone-aware")
        # The side is validated at the wire boundary, not lazily: an
        # untyped row must never sit silently in a snapshot.
        _side_of(self.trd_side, self.code)
        return self

    @property
    def symbol(self) -> str:
        return _symbol_of(self.code)

    @property
    def side(self) -> Side:
        return _side_of(self.trd_side, self.code)

    @property
    def filled_quantity(self) -> float:
        return max(self.dealt_qty, 0.0)


class BrokerDeal(BaseModel):
    """One broker fill (SDK deal_list_query columns; fee venue-reported)."""

    deal_id: str
    order_id: str
    code: str
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    trd_side: str
    create_time: datetime
    status: str = "OK"
    fee: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def time_is_aware(self) -> "BrokerDeal":
        if self.create_time.tzinfo is None:
            raise ValueError("create_time must be timezone-aware")
        _side_of(self.trd_side, self.code)
        return self

    @property
    def symbol(self) -> str:
        return _symbol_of(self.code)

    @property
    def side(self) -> Side:
        return _side_of(self.trd_side, self.code)


class BrokerPosition(BaseModel):
    """One broker account position (SDK position_list_query columns)."""

    code: str
    qty: float = Field(ge=0)

    @property
    def symbol(self) -> str:
        return _symbol_of(self.code)


class ExecutionSnapshot(BaseModel):
    """The broker-side state a reconciliation run compares against."""

    orders: list[BrokerOrder] = Field(default_factory=list)
    deals: list[BrokerDeal] = Field(default_factory=list)
    positions: list[BrokerPosition] = Field(default_factory=list)


@runtime_checkable
class TradeTransport(Protocol):
    """Broker trade surface; implementations are never default-constructed."""

    def place(
        self,
        *,
        code: str,
        side: Side,
        quantity: float,
        price: float | None,
        remark: str,
        order_type: OrderType,
    ) -> str:
        """Submit to the SIMULATED account; returns the broker order id."""

    def cancel(self, order_id: str) -> None:
        """Cancel a broker order; ack is a later snapshot's business."""

    def snapshot(self) -> ExecutionSnapshot:
        """Current broker orders, deals, and positions."""


class SimulatedFixtureTransport:
    """Deterministic broker simulator replaying a fixture script.

    The script is JSONL, one phase per line:

    ``{"now": "2026-08-08T09:30:00+00:00", "orders": [...], "deals": [...],
    "positions": [...], "lost_acks": ["B-2"]}``

    ``now`` is required, aware, and strictly increasing. The transport's
    state at time *t* is the phase with the latest ``now <= t`` — pure
    declaration, never mutated. ``place`` assigns the next broker id
    (``B-1``, ``B-2``, …) deterministically; if that id is listed in the
    current phase's ``lost_acks`` the broker records the order but the
    acknowledgement is withheld (``OpenDUnavailableError``) — the
    disconnect gap that reconciliation's remark channel recovers. Deals
    and post-placement order states are declared in later phases with the
    assigned id, so a replay is a pure function of the script plus the
    scripted operations.
    """

    def __init__(self, script: Path | str | list[dict]) -> None:
        if isinstance(script, str):
            script = Path(script)
        phases = _load_jsonl(script) if isinstance(script, Path) else script
        if not phases:
            raise ValueError("fixture script has no phases")
        self._phases = [_validate_phase(phase, index) for index, phase in enumerate(phases)]
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
        code: str,
        side: Side,
        quantity: float,
        price: float | None,
        remark: str,
        order_type: OrderType,
    ) -> str:
        self._placed += 1
        order_id = f"B-{self._placed}"
        if order_id in self._phase()["lost_acks"]:
            raise OpenDUnavailableError(
                f"connection lost; the broker recorded {order_id} but the "
                "acknowledgement never arrived"
            )
        return order_id

    def cancel(self, order_id: str) -> None:
        known = {order["order_id"] for order in self._phase()["orders"]}
        if order_id not in known:
            raise ValueError(f"broker has no order {order_id!r} at {self._now}")

    def snapshot(self) -> ExecutionSnapshot:
        # Rows go through the same wire parsers as the live SDK path, so
        # venue-local wall-clock times convert to UTC the same way.
        return ExecutionSnapshot(
            orders=[_broker_order(row) for row in self._phase()["orders"]],
            deals=[_broker_deal(row) for row in self._phase()["deals"]],
            positions=[_broker_position(row) for row in self._phase()["positions"]],
        )

    def _phase(self) -> dict:
        current = self._phases[0]
        for phase in self._phases:
            if phase["now"] <= self._now:
                current = phase
            else:
                break
        return current


class SdkTradeTransport:
    """Lazy transport over the vendored SDK's US trade context.

    Constructed only by an explicit operator command; unit tests never
    import the SDK. Every call pins ``trd_env=TrdEnv.SIMULATE`` — a
    non-simulated environment is refused before anything reaches the
    wire, and this transport's API does not even expose the choice.
    """

    def __init__(self, host: str, port: int, *, connect_timeout_s: float) -> None:
        self._host = host
        self._port = port
        self._connect_timeout_s = connect_timeout_s
        self._context = None
        self._env = None

    def _ensure_context(self):
        if self._context is not None:
            return self._context
        try:
            from moomoo import ModifyOrderOp, OpenUSTradeContext, TrdEnv, TrdSide
            from moomoo.common.constant import OrderType as SdkOrderType
        except ImportError as error:
            raise OpenDProtocolError(
                "the vendored py-moomoo-api SDK is not importable"
            ) from error
        self._env = TrdEnv.SIMULATE
        self._trd_side = TrdSide
        self._modify = ModifyOrderOp
        self._order_type = SdkOrderType
        self._context = OpenUSTradeContext(host=self._host, port=self._port)
        return self._context

    # The environment is fixed at construction; there is deliberately no
    # parameter a caller could flip to REAL.
    def _check_env(self) -> None:
        self._ensure_context()
        if self._env is None or self._env.value != "SIMULATE":
            raise OpenDProtocolError(
                "refusing to trade in a non-simulated environment"
            )

    def place(
        self,
        *,
        code: str,
        side: Side,
        quantity: float,
        price: float | None,
        remark: str,
        order_type: OrderType,
    ) -> str:
        context = self._ensure_context()
        self._check_env()
        sdk_side = self._trd_side.BUY if side is Side.BUY else self._trd_side.SELL
        sdk_type = (
            self._order_type.NORMAL if order_type is OrderType.MARKET else self._order_type.LIMIT
        )
        sdk_price = 0.0 if price is None else float(price)
        ret_code, msg, order_id = context.place_order(
            sdk_price,
            float(quantity),
            code,
            sdk_side,
            order_type=sdk_type,
            trd_env=self._env,
            remark=remark,
        )
        if ret_code != 0:
            raise OpenDUnavailableError(f"broker refused the order: {msg}")
        return str(order_id)

    def cancel(self, order_id: str) -> None:
        context = self._ensure_context()
        self._check_env()
        ret_code, msg = context.modify_order(
            self._modify.CANCEL, order_id, 0, 0, trd_env=self._env
        )
        if ret_code != 0:
            raise OpenDUnavailableError(f"broker refused the cancel: {msg}")

    def snapshot(self) -> ExecutionSnapshot:
        context = self._ensure_context()
        self._check_env()
        ret_code, order_rows = context.order_list_query(trd_env=self._env)
        if ret_code != 0:
            raise OpenDUnavailableError("order_list_query failed")
        ret_code, deal_rows = context.deal_list_query(trd_env=self._env)
        if ret_code != 0:
            raise OpenDUnavailableError("deal_list_query failed")
        ret_code, position_rows = context.position_list_query(trd_env=self._env)
        if ret_code != 0:
            raise OpenDUnavailableError("position_list_query failed")
        return ExecutionSnapshot(
            orders=[_broker_order(row) for row in _rows(order_rows)],
            deals=[_broker_deal(row) for row in _rows(deal_rows)],
            positions=[_broker_position(row) for row in _rows(position_rows)],
        )


def _rows(table: object) -> list[dict]:
    """SDK responses come back as pandas DataFrames; tolerate any
    record-shaped iterable."""
    if table is None:
        return []
    if hasattr(table, "to_dict"):
        return [dict(row) for row in table.to_dict("records")]
    return [dict(row) for row in table]


class MoomooExecutionAdapter:
    """Simulated-only order surface; explicit construction only (ADR-0006).

    ``place`` builds the domain order, submits it through the injected
    transport (whose every implementation is simulated-only), and stamps
    the broker order id. On a lost acknowledgement the transport raises
    ``OpenDUnavailableError`` and no broker id is stamped — the caller
    (the drill harness) records the order anyway, which is exactly the
    state the remark channel recovers on the next reconciliation.
    """

    def __init__(self, transport: TradeTransport) -> None:
        self.transport = transport

    def place(
        self,
        request,
        *,
        order_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Order:
        order_id = order_id or uuid.uuid4().hex
        created_at = created_at or datetime.now(UTC)
        remark = request.client_order_id or order_id
        if len(remark.encode("utf-8")) > 64:
            raise ValueError(f"remark exceeds the broker's 64-byte limit: {remark!r}")
        broker_order_id = self.transport.place(
            code=sdk_code(request.instrument),
            side=request.side,
            quantity=request.quantity,
            price=request.limit_price,
            remark=remark,
            order_type=(
                OrderType.LIMIT if request.limit_price is not None else OrderType.MARKET
            ),
        )
        order = Order.from_request(request, order_id=order_id, created_at=created_at)
        return order.model_copy(update={"broker_order_id": broker_order_id})

    def cancel(self, order: Order) -> None:
        if order.broker_order_id is None:
            raise ValueError(
                f"order {order.order_id!r} has no broker order id; cancel is impossible"
            )
        self.transport.cancel(order.broker_order_id)

    def refresh(self) -> ExecutionSnapshot:
        return self.transport.snapshot()


# --- parsing helpers ---------------------------------------------------------

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
    # The four state keys are optional but always complete after
    # validation, so readers can index them directly.
    for key in ("orders", "deals", "positions", "lost_acks"):
        if key in phase and not isinstance(phase[key], list):
            raise ValueError(f"fixture phase {index} {key!r} must be a list")
        phase.setdefault(key, [])
    phase["now"] = _parse_broker_time(now, None)
    return phase


def _parse_broker_time(value: str, market: str | None) -> datetime:
    """Venue-local wall clock or ISO instant → aware UTC; never guess."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise OpenDProtocolError("broker time must be timezone-aware")
        return value.astimezone(UTC)
    if not isinstance(value, str):
        raise OpenDProtocolError(f"broker time must be a string, got {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC)
    except ValueError:
        pass
    if market is not None:
        for fmt in _BROKER_TIME_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            try:
                return parsed.replace(tzinfo=market_zone(market)).astimezone(UTC)
            except ValueError as error:
                raise OpenDProtocolError(
                    f"no timezone metadata for market {market!r}"
                ) from error
    raise OpenDProtocolError(f"unparseable broker time {value!r}")


def _symbol_of(code: object) -> str:
    if not isinstance(code, str) or "." not in code:
        raise OpenDProtocolError(f"broker code {code!r} has no market prefix")
    return code.split(".", 1)[1]


def _side_of(marker: object, code: object) -> Side:
    if not isinstance(marker, str):
        raise OpenDProtocolError(f"broker side for {code!r} must be a string")
    upper = marker.upper()
    if upper in ("BUY", "BUY_ALL"):
        return Side.BUY
    if upper in ("SELL", "SELL_ALL"):
        return Side.SELL
    raise OpenDProtocolError(f"unknown broker side {marker!r} for {code!r}")


def _broker_order(row: dict) -> BrokerOrder:
    code = row.get("code")
    market = code.split(".", 1)[0] if isinstance(code, str) else None
    create = _parse_broker_time(row.get("create_time"), market)
    updated = (
        _parse_broker_time(row["updated_time"], market)
        if row.get("updated_time")
        else None
    )
    return BrokerOrder(
        order_id=str(row["order_id"]),
        code=code,
        qty=float(row["qty"]),
        price=_opt_float(row.get("price")),
        dealt_qty=float(row.get("dealt_qty") or 0.0),
        dealt_avg_price=_opt_float(row.get("dealt_avg_price")),
        order_status=str(row.get("order_status") or ""),
        trd_side=str(row.get("trd_side") or ""),
        create_time=create,
        updated_time=updated,
        remark=row.get("remark") or None,
        currency=row.get("currency") or None,
        last_err_msg=row.get("last_err_msg") or None,
    )


def _broker_deal(row: dict) -> BrokerDeal:
    code = row.get("code")
    market = code.split(".", 1)[0] if isinstance(code, str) else None
    return BrokerDeal(
        deal_id=str(row["deal_id"]),
        order_id=str(row["order_id"]),
        code=code,
        qty=float(row["qty"]),
        price=float(row["price"]),
        trd_side=str(row.get("trd_side") or ""),
        create_time=_parse_broker_time(row.get("create_time"), market),
        status=str(row.get("status") or "OK"),
        fee=_opt_float(row.get("fee")),
    )


def _broker_position(row: dict) -> BrokerPosition:
    return BrokerPosition(
        code=str(row["code"]),
        qty=float(row.get("qty") or 0.0),
    )


def _opt_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
