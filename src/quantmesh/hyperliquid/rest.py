"""Hyperliquid REST surface (M5, issue #29, Phase A).

The transport boundary is the SDK's ``Info`` class from the pinned
submodule, reached lazily and import-guarded — unit tests never import
the SDK, exactly like the M4 OpenD discipline. The base URL is pinned
to the testnet endpoint the SDK itself declares
(``hyperliquid.utils.constants.TESTNET_API_URL``); any other base URL
is refused before a single request is made (ADR-0007): the product
surface cannot reach mainnet.

``ScriptedRestTransport`` is the deterministic stub the reconnect drills
drive: candles keyed by ``(symbol, interval)`` with time-window
filtering, a per-symbol l2Book snapshot (static dict or callable so a
drill can return a fresh post-disconnect book), and funding rows.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from quantmesh.hyperliquid.errors import (
    HyperliquidError,
    HyperliquidProtocolError,
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)

# Pinned to the vendored submodule's own constants
# (vendor/components/hyperliquid-python-sdk/hyperliquid/utils/constants.py).
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
MAINNET_API_URL = "https://api.hyperliquid.xyz"

__all__ = [
    "TESTNET_API_URL",
    "MAINNET_API_URL",
    "RestTransport",
    "SdkRestTransport",
    "ScriptedRestTransport",
]


def to_ms(instant: datetime) -> int:
    """Aware UTC instant → unix milliseconds; naive times fail closed."""
    if instant.tzinfo is None:
        raise HyperliquidProtocolError("REST times must be timezone-aware")
    return int(instant.timestamp() * 1000)


def from_ms(millis: object) -> datetime:
    """Unix milliseconds → aware UTC (matches ``wire.ms_to_utc``)."""
    return datetime.fromtimestamp(int(millis) / 1000, tz=UTC)


class RestTransport(Protocol):
    """REST surface the adapter and the reconnect logic depend on."""

    def candles(
        self, symbol: str, interval: str, *, start: datetime, end: datetime
    ) -> list[dict]:
        """Raw ``candleSnapshot`` rows for ``symbol`` in ``[start, end]``."""

    def l2_book(self, symbol: str, *, at: datetime | None = None) -> dict:
        """Raw ``l2Book`` payload (``levels`` arrays), optionally at ``at``."""

    def funding_history(self, symbol: str, *, start: datetime, end: datetime) -> list[dict]:
        """Raw ``fundingHistory`` rows for ``symbol`` in ``[start, end]``."""

    def meta(self) -> dict:
        """Raw ``meta`` payload (perp universe)."""

    def spot_meta(self) -> dict:
        """Raw ``spotMeta`` payload."""


class SdkRestTransport:
    """Lazy REST transport over the vendored SDK's ``Info`` (testnet only).

    Explicit construction, testnet pinned: a caller cannot reach
    mainnet through this class, and nothing constructs it implicitly.
    ``Info`` is created with ``skip_ws=True`` — QuantMesh owns the WS
    layer (ADR-0007); the SDK's thread-based manager has no reconnect.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        request_timeout_s: float = 10.0,
    ) -> None:
        if base_url is not None and base_url != TESTNET_API_URL:
            raise HyperliquidProtocolError(
                f"refusing base URL {base_url!r}: only the testnet endpoint "
                f"{TESTNET_API_URL} is reachable from this adapter"
            )
        self._base_url = base_url or TESTNET_API_URL
        self._request_timeout_s = request_timeout_s
        self._info = None

    # -- lazy SDK boundary ---------------------------------------------------

    def _sdk(self):
        if self._info is not None:
            return self._info
        try:
            from hyperliquid.info import Info
        except ImportError as error:
            raise HyperliquidSDKMissingError(
                "the vendored hyperliquid-python-sdk is not importable"
            ) from error
        try:
            self._info = Info(
                base_url=self._base_url,
                skip_ws=True,
                timeout=self._request_timeout_s,
            )
        except Exception as error:
            raise HyperliquidUnavailableError(
                f"testnet metadata handshake failed: {error}"
            ) from error
        return self._info

    def _call(self, name: str, *args: object) -> object:
        info = self._sdk()
        try:
            return getattr(info, name)(*args)
        except HyperliquidError:
            raise
        except Exception as error:
            raise HyperliquidUnavailableError(f"{name} failed: {error}") from error

    # -- RestTransport surface ------------------------------------------------

    def candles(
        self, symbol: str, interval: str, *, start: datetime, end: datetime
    ) -> list[dict]:
        payload = self._call(
            "candles_snapshot", symbol, interval, to_ms(start), to_ms(end)
        )
        if not isinstance(payload, list):
            raise HyperliquidProtocolError(
                f"candles must be a list, got {type(payload).__name__}"
            )
        return payload

    def l2_book(self, symbol: str, *, at: datetime | None = None) -> dict:
        payload = self._call("l2_snapshot", symbol)
        if not isinstance(payload, dict):
            raise HyperliquidProtocolError(
                f"l2Book must be an object, got {type(payload).__name__}"
            )
        return payload

    def funding_history(self, symbol: str, *, start: datetime, end: datetime) -> list[dict]:
        payload = self._call("funding_history", symbol, to_ms(start), to_ms(end))
        if not isinstance(payload, list):
            raise HyperliquidProtocolError(
                f"funding must be a list, got {type(payload).__name__}"
            )
        return payload

    def meta(self) -> dict:
        payload = self._call("meta")
        if not isinstance(payload, dict):
            raise HyperliquidProtocolError(f"meta must be an object, got {type(payload).__name__}")
        return payload

    def spot_meta(self) -> dict:
        payload = self._call("spot_meta")
        if not isinstance(payload, dict):
            raise HyperliquidProtocolError(
                f"spotMeta must be an object, got {type(payload).__name__}"
            )
        return payload


class ScriptedRestTransport:
    """Deterministic REST stub for drills: scripted payloads, honest ranges.

    ``candles`` is keyed by ``(symbol, interval)`` and filtered by the
    requested window; ``l2_book`` returns a stored dict or the result of
    a callable (so a drill can serve a fresh post-disconnect book); the
    ``at`` parameter is handed to the callable, mirroring the live
    transport's query shape. Missing keys raise ``HyperliquidProtocolError``
    so a drill cannot silently fetch nothing.
    """

    def __init__(
        self,
        *,
        candles: dict[tuple[str, str], list[dict]] | None = None,
        l2_books: dict[str, dict | Callable[[datetime], dict]] | None = None,
        funding: dict[str, list[dict]] | None = None,
        meta_payload: dict | None = None,
        spot_meta_payload: dict | None = None,
    ) -> None:
        self._candles = candles or {}
        self._l2_books = l2_books or {}
        self._funding = funding or {}
        self._meta = meta_payload
        self._spot_meta = spot_meta_payload

    def candles(
        self, symbol: str, interval: str, *, start: datetime, end: datetime
    ) -> list[dict]:
        rows = self._candles.get((symbol, interval))
        if rows is None:
            raise HyperliquidProtocolError(
                f"scripted REST has no candles for {(symbol, interval)!r}"
            )
        start_ms, end_ms = to_ms(start), to_ms(end)
        return [row for row in rows if start_ms <= int(row["t"]) <= end_ms]

    def l2_book(self, symbol: str, *, at: datetime | None = None) -> dict:
        entry = self._l2_books.get(symbol)
        if entry is None:
            raise HyperliquidProtocolError(f"scripted REST has no l2Book for {symbol!r}")
        if callable(entry):
            return entry(at)
        return entry

    def funding_history(self, symbol: str, *, start: datetime, end: datetime) -> list[dict]:
        rows = self._funding.get(symbol)
        if rows is None:
            raise HyperliquidProtocolError(f"scripted REST has no funding for {symbol!r}")
        start_ms, end_ms = to_ms(start), to_ms(end)
        return [row for row in rows if start_ms <= int(row["time"]) <= end_ms]

    def meta(self) -> dict:
        if self._meta is None:
            raise HyperliquidProtocolError("scripted REST has no meta payload")
        return self._meta

    def spot_meta(self) -> dict:
        if self._spot_meta is None:
            raise HyperliquidProtocolError("scripted REST has no spotMeta payload")
        return self._spot_meta
