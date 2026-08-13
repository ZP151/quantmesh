"""Pinned public-mainnet Hyperliquid market-data transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from quantmesh.data.capabilities import (
    DataKind,
    EntitlementState,
    HistoryAccess,
    HistoryLimit,
    PaginationPolicy,
    PaginationStyle,
    ProviderAccess,
    ProviderCapability,
    ProviderDescriptor,
    RateLimitPolicy,
)
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue
from quantmesh.hyperliquid.errors import (
    HyperliquidProtocolError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.rest import to_ms

MAINNET_INFO_URL = "https://api.hyperliquid.xyz/info"
_CANDLE_INTERVALS = (
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _candle_capability(interval: str) -> ProviderCapability:
    seconds = interval_to_timedelta(interval).total_seconds() * 4_999
    conservative_days = max(1, int(seconds // 86_400))
    return ProviderCapability(
        access=ProviderAccess.PUBLIC_LIVE,
        data_kind=DataKind.BARS,
        symbols=frozenset({"BTC", "ETH", "SOL"}),
        intervals=frozenset({interval}),
        entitlement=EntitlementState.NOT_REQUIRED,
        history_access=HistoryAccess.BOUNDED,
        history_limit=HistoryLimit(
            max_window_days=conservative_days,
            max_rows=5_000,
            max_pages=1,
        ),
        source_rights_id="hyperliquid-public-market-data",
        terms_version="2026-08-14",
        timezone="UTC",
        calendar="24/7",
        latency_class="realtime",
        rate_limit=RateLimitPolicy(requests=10, per_seconds=60, burst=2),
        pagination=PaginationPolicy(
            style=PaginationStyle.NONE,
            max_page_size=5_000,
        ),
    )


HYPERLIQUID_PUBLIC_DESCRIPTOR = ProviderDescriptor(
    provider_id="hyperliquid-public",
    venue=Venue.HYPERLIQUID,
    provider_version="public-info-v1",
    adapter_schema_version="quantmesh-hyperliquid-public-v1",
    capabilities=tuple(_candle_capability(interval) for interval in _CANDLE_INTERVALS)
    + (
        ProviderCapability(
            access=ProviderAccess.PUBLIC_LIVE,
            data_kind=DataKind.BOOKS,
            symbols=frozenset({"BTC", "ETH", "SOL"}),
            entitlement=EntitlementState.NOT_REQUIRED,
            history_access=HistoryAccess.NONE,
            source_rights_id="hyperliquid-public-market-data",
            terms_version="2026-08-14",
            timezone="UTC",
            calendar="24/7",
            latency_class="realtime",
            rate_limit=RateLimitPolicy(requests=10, per_seconds=60, burst=2),
            pagination=PaginationPolicy(style=PaginationStyle.NONE),
        ),
    ),
)


class _Response(Protocol):
    status_code: int
    content: bytes


class _Client(Protocol):
    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> _Response: ...


class PublicInfoResponse(BaseModel):
    """Exact response bytes plus the strictly decoded public payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    payload: list[dict] | dict
    raw_bytes: bytes
    received_at: datetime

    @field_validator("received_at")
    @classmethod
    def receipt_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("received_at must be UTC")
        return value


class PublicInfoTransport:
    """Data-only `/info` client with no wallet, account or exchange surface."""

    __slots__ = (
        "_client",
        "_clock",
        "_is_direct_network_source",
        "_request_timeout_s",
        "_sealed",
    )

    descriptor = HYPERLIQUID_PUBLIC_DESCRIPTOR

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("PublicInfoTransport is immutable after construction")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        base_url: str = MAINNET_INFO_URL,
        *,
        client: _Client | None = None,
        request_timeout_s: float = 10.0,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if base_url != MAINNET_INFO_URL:
            raise HyperliquidProtocolError(f"public info URL must be pinned to {MAINNET_INFO_URL}")
        if request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be positive")
        self._is_direct_network_source = client is None and clock is _utc_now
        self._client = httpx.Client() if client is None else client
        self._request_timeout_s = request_timeout_s
        self._clock = clock
        self._sealed = True

    def candles(
        self,
        symbol: str,
        interval: str,
        *,
        start: datetime,
        end: datetime,
    ) -> PublicInfoResponse:
        """Fetch one bounded `candleSnapshot` response."""
        request = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": interval,
                "startTime": to_ms(start),
                "endTime": to_ms(end),
            },
        }
        return self._post(request, expected=list)

    def l2_book(self, symbol: str) -> PublicInfoResponse:
        """Fetch one public L2 snapshot without exposing an execution client."""
        return self._post({"type": "l2Book", "coin": symbol}, expected=dict)

    def _post(self, request: dict[str, Any], *, expected: type) -> PublicInfoResponse:
        try:
            response = self._client.post(
                MAINNET_INFO_URL,
                json=request,
                timeout=self._request_timeout_s,
            )
        except (httpx.HTTPError, OSError) as error:
            raise HyperliquidUnavailableError("public info request failed") from error
        if response.status_code != 200:
            raise HyperliquidUnavailableError(f"public info returned HTTP {response.status_code}")
        raw = bytes(response.content)
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HyperliquidProtocolError("public info response is invalid JSON") from error
        if not isinstance(payload, expected):
            raise HyperliquidProtocolError(f"public info payload must be a {expected.__name__}")
        return PublicInfoResponse(
            payload=payload,
            raw_bytes=raw,
            received_at=self._clock(),
        )
