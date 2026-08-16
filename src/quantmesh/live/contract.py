"""Owned normalized live-market event contract (iteration 0015, ADR-0014).

Every venue supervisor normalizes its frames into a single
``MarketUpdate`` shape so downstream consumers — the UI, the replay
lake and the quote fence — never need venue knowledge. The contract is
fail-closed: unknown kinds, naive timestamps, malformed payloads and
inconsistent quotes are rejected at the boundary instead of being
silently tolerated.
"""

from __future__ import annotations

import hashlib
import json
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


class ContinuityState(StrEnum):
    """What is provable about the event stream around this update."""

    COMPLETE = "complete"
    KNOWN_GAP = "known-gap"
    UNKNOWN_AFTER_DISCONNECT = "unknown-after-disconnect"
    RECOVERED = "recovered"
    UNRECOVERABLE = "unrecoverable"


class ContinuityEvidence(BaseModel):
    """Structured boundary evidence for one disrupted provider channel."""

    channel: str = Field(min_length=1)
    disconnected_at: datetime
    last_durable_source_event_id: str | None = None
    first_recovered_source_event_id: str = Field(min_length=1)
    recovered_at: datetime
    recovery_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def timestamps_are_ordered_and_aware(self) -> ContinuityEvidence:
        _require_aware(self.disconnected_at, "disconnected_at")
        _require_aware(self.recovered_at, "recovered_at")
        if self.recovered_at < self.disconnected_at:
            raise ValueError("recovered_at precedes disconnected_at")
        return self


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
    continuity: ContinuityState = ContinuityState.COMPLETE
    source_event_id: str | None = Field(default=None, min_length=1)
    content_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    snapshot_epoch: str | None = Field(default=None, min_length=1)
    continuity_evidence: ContinuityEvidence | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    state: SourceState | None = None
    state_note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_gap_and_continuity_agree(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        has_gap = "sequence_gap" in data
        has_continuity = "continuity" in data
        if has_gap and has_continuity:
            continuity = ContinuityState(data["continuity"])
            expected_gap = continuity is not ContinuityState.COMPLETE
            if bool(data["sequence_gap"]) is not expected_gap:
                raise ValueError("sequence_gap contradicts continuity")
        elif has_gap:
            data["continuity"] = (
                ContinuityState.KNOWN_GAP
                if bool(data["sequence_gap"])
                else ContinuityState.COMPLETE
            )
        elif has_continuity:
            data["sequence_gap"] = (
                ContinuityState(data["continuity"]) is not ContinuityState.COMPLETE
            )
        return data

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

    @model_validator(mode="after")
    def continuity_and_identity_are_canonical(self) -> MarketUpdate:
        if self.sequence_gap != (self.continuity is not ContinuityState.COMPLETE):
            raise ValueError("sequence_gap contradicts continuity")
        if self.continuity is ContinuityState.COMPLETE and self.continuity_evidence:
            raise ValueError("complete continuity cannot carry disruption evidence")

        if self.kind is UpdateKind.L2_SNAPSHOT:
            if self.snapshot_epoch is None:
                self.snapshot_epoch = _digest(
                    [
                        self.venue.value,
                        self.instrument,
                        self.data_time.astimezone(UTC).isoformat(),
                    ]
                )
        elif self.snapshot_epoch is not None:
            raise ValueError("snapshot_epoch is only valid on L2 snapshots")

        expected_digest = _digest(
            {
                "venue": self.venue.value,
                "instrument": self.instrument,
                "kind": self.kind.value,
                "provenance": self.provenance.value,
                "data_time": self.data_time.astimezone(UTC).isoformat(),
                "sequence": self.sequence,
                "snapshot_epoch": self.snapshot_epoch,
                "state": self.state.value if self.state is not None else None,
                "state_note": self.state_note,
                "payload": self.payload,
            }
        )
        if self.content_digest is not None and self.content_digest != expected_digest:
            raise ValueError("content_digest disagrees with normalized event content")
        self.content_digest = expected_digest
        if self.source_event_id is None:
            self.source_event_id = f"derived:{expected_digest}"
        return self


def _digest(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
