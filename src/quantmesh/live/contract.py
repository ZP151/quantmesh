"""Owned normalized live-market event contract (iteration 0015, ADR-0014).

Every venue supervisor normalizes its frames into a single
``MarketUpdate`` shape so downstream consumers — the UI, the replay
lake and the quote fence — never need venue knowledge. The contract is
fail-closed: unknown kinds, naive timestamps, malformed payloads and
inconsistent quotes are rejected at the boundary instead of being
silently tolerated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Venue


class Provenance(StrEnum):
    """How truthful a value is. ``real`` and ``delayed`` come from the
    venue itself; ``synthetic`` is labeled generated data (the demo
    seed, or the connector fallback); ``unavailable`` means nothing is
    being delivered."""

    REAL = "real"
    DELAYED = "delayed"
    SYNTHETIC = "synthetic"
    UNAVAILABLE = "unavailable"


class UpdateKind(StrEnum):
    QUOTE = "quote"
    TRADE = "trade"
    CANDLE = "candle"
    L2_SNAPSHOT = "l2_snapshot"
    L2_DELTA = "l2_delta"
    METRICS = "metrics"
    STATUS = "status"


class SourceState(StrEnum):
    """Per-source connection/freshness state (ADR-0014, decision 6)."""

    CONNECTED = "connected"
    LAGGING = "lagging"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    UNAVAILABLE = "unavailable"


def _require_aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _positive_price(value: Any) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"price must be numeric, got {value!r}") from error
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    return price


def _non_negative(value: Any, name: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric, got {value!r}") from error
    if amount < 0:
        raise ValueError(f"{name} must be non-negative, got {amount}")
    return amount


def _require_number(payload: dict[str, Any], key: str) -> float:
    if key not in payload:
        raise ValueError(f"{key} missing from payload")
    return _non_negative(payload[key], key)


def _validate_quote(payload: dict[str, Any]) -> None:
    bid = _require_number(payload, "bid")
    ask = _require_number(payload, "ask")
    if ask < bid:
        raise ValueError(f"ask {ask} below bid {bid}")
    for key in ("bid_size", "ask_size"):
        if key in payload:
            _non_negative(payload[key], key)


def _validate_trade(payload: dict[str, Any]) -> None:
    _positive_price(payload.get("price"))
    if payload.get("size") is None:
        raise ValueError("size missing from trade payload")
    _non_negative(payload["size"], "size")
    side = payload.get("side")
    if side not in ("buy", "sell"):
        raise ValueError(f"trade side must be 'buy' or 'sell', got {side!r}")


def _validate_candle(payload: dict[str, Any]) -> None:
    open_ = _require_number(payload, "open")
    high = _require_number(payload, "high")
    low = _require_number(payload, "low")
    close = _require_number(payload, "close")
    _non_negative(payload.get("volume", 0), "volume")
    if high < max(open_, close) or low > min(open_, close):
        raise ValueError("candle high/low inconsistent with open/close")


def _validate_l2(payload: dict[str, Any], require_levels: bool) -> None:
    side = payload.get("side")
    if side not in ("bid", "ask"):
        raise ValueError(f"l2 side must be 'bid' or 'ask', got {side!r}")
    levels = payload.get("levels")
    if require_levels and not levels:
        raise ValueError("l2 payload has no levels")
    if levels is not None:
        previous = None
        direction: int | None = None
        for entry in levels:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise ValueError(f"l2 level must be [price, size], got {entry!r}")
            price = _positive_price(entry[0])
            _non_negative(entry[1], "level size")
            if previous is not None:
                if price == previous:
                    raise ValueError("l2 levels must not repeat prices")
                step = 1 if price > previous else -1
                if direction is None:
                    direction = step
                elif step != direction:
                    raise ValueError("l2 levels must be strictly monotonic in price")
            previous = price


class MarketUpdate(BaseModel):
    """One normalized update from a venue stream (ADR-0014, decision 1).

    ``sequence`` is the venue's own monotonic sequence when it provides
    one; ``sequence_gap`` is set by the supervisor when continuity
    between consecutive updates for the same instrument + kind could
    not be proven (reconnect, dropped frame, backpressure overflow).
    ``data_time`` is the venue timestamp, ``received_at`` the local
    receipt time — their difference is the visible latency.
    """

    venue: Venue
    instrument: str = Field(min_length=1)
    kind: UpdateKind
    provenance: Provenance
    data_time: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sequence: int | None = Field(default=None, ge=0)
    sequence_gap: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    state: SourceState | None = None
    state_note: str | None = None

    @model_validator(mode="after")
    def timestamps_are_aware(self) -> MarketUpdate:
        _require_aware(self.data_time, "data_time")
        _require_aware(self.received_at, "received_at")
        return self

    @model_validator(mode="after")
    def payload_matches_kind(self) -> MarketUpdate:
        if self.kind is UpdateKind.QUOTE:
            _validate_quote(self.payload)
        elif self.kind is UpdateKind.TRADE:
            _validate_trade(self.payload)
        elif self.kind is UpdateKind.CANDLE:
            _validate_candle(self.payload)
        elif self.kind is UpdateKind.L2_SNAPSHOT:
            _validate_l2(self.payload, require_levels=True)
        elif self.kind is UpdateKind.L2_DELTA:
            _validate_l2(self.payload, require_levels=False)
        elif self.kind is UpdateKind.METRICS:
            for key, value in self.payload.items():
                if not isinstance(value, (int, float)):
                    raise ValueError(
                        f"metrics payload values must be numeric, got {key}={value!r}"
                    )
        elif self.kind is UpdateKind.STATUS:
            if self.state is None:
                raise ValueError("status updates require a state")
            if self.payload:
                raise ValueError("status updates carry no payload")
        return self

    @model_validator(mode="after")
    def status_fields_only_for_status(self) -> MarketUpdate:
        if self.kind is not UpdateKind.STATUS and (
            self.state is not None or self.state_note is not None
        ):
            raise ValueError("state fields are only valid on status updates")
        return self
