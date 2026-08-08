"""Kalshi transport boundary (M6, issue #35, Phase B).

``KalshiRestTransport`` is the injected boundary every live path goes
through; ``HttpxKalshiTransport`` implements it over httpx (a core
dependency) against the pinned public base URL. There is no SDK for
Kalshi and no credentials anywhere: the adapter cannot hold keys by
construction, and the only reachable surface is public read-only data.

The base URL is pinned to ``https://api.elections.kalshi.com``
(settings ``QUANTMESH_KALSHI_*``) and any other host — in particular
the migration host ``trading-api.kalshi.com``, which answers with a
plain-text "API has been moved" 401 (recorded live) — is refused at
construction, parity with the M5 testnet-pin discipline. Non-2xx
responses carry the recorded error shapes (``{"error": {"code",
"message"}}`` and ``{"msg": ...}``) and raise typed refusals with the
server's own message; non-JSON bodies raise ``KalshiUnavailableError``.
"""

from abc import ABC, abstractmethod
from urllib.parse import urlsplit

from quantmesh.kalshi.errors import KalshiProtocolError, KalshiUnavailableError
from quantmesh.kalshi.wire import _require_error_free
from quantmesh.settings import settings

__all__ = [
    "KalshiRestTransport",
    "HttpxKalshiTransport",
    "KALSHI_PINNED_HOST",
    "KALSHI_MIGRATION_HOST",
]

KALSHI_PINNED_HOST = "api.elections.kalshi.com"
KALSHI_MIGRATION_HOST = "trading-api.kalshi.com"


class KalshiRestTransport(ABC):
    """The read-only public surface of trade-api v2.

    Every method returns the raw wire payload; parsing is the
    ``quantmesh.kalshi.wire`` parsers' job. Implementations raise
    ``KalshiUnavailableError`` on unreachable/refused requests and
    typed ``KalshiProtocolError`` on recorded error bodies.
    """

    @abstractmethod
    def events(self, *, limit: int | None = None, offset: int | None = None) -> object:
        """``GET /events`` discovery page."""

    @abstractmethod
    def event(self, ticker: str) -> object:
        """``GET /events/{ticker}`` — the event bundle with its markets."""

    @abstractmethod
    def markets(self, *, event_ticker: str, limit: int | None = None) -> object:
        """``GET /markets`` filtered to one event."""

    @abstractmethod
    def market(self, ticker: str) -> object:
        """``GET /markets/{ticker}`` — the market object."""

    @abstractmethod
    def orderbook(self, ticker: str) -> object:
        """``GET /markets/{ticker}/orderbook`` — the two bid ladders."""

    @abstractmethod
    def trades(
        self,
        ticker: str,
        *,
        limit: int | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> object:
        """``GET /markets/trades?ticker=`` — executed trades."""

    @abstractmethod
    def candlesticks(
        self,
        ticker: str,
        *,
        series_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> object:
        """``GET /series/{series}/markets/{ticker}/candlesticks`` — bars."""

    @abstractmethod
    def series(self, series_ticker: str) -> object:
        """``GET /series/{ticker}`` — the series object."""


class HttpxKalshiTransport(KalshiRestTransport):
    """Live transport over httpx against the pinned public host.

    Explicit construction only; the base URL must resolve to the
    pinned public host or construction fails. No credentials, no
    headers beyond the defaults, no auth surface exists.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_timeout_s: float | None = None,
    ) -> None:
        base = base_url or settings.kalshi_base_url
        parsed = urlsplit(base)
        if parsed.scheme != "https":
            raise ValueError(f"Kalshi base URL must be https, got {base!r}")
        hostname = (parsed.hostname or "").lower()
        if hostname != KALSHI_PINNED_HOST:
            if hostname == KALSHI_MIGRATION_HOST:
                raise ValueError(
                    "trading-api.kalshi.com is the migration host (its API moved to "
                    f"{KALSHI_PINNED_HOST}); refusing at construction"
                )
            raise ValueError(
                f"Kalshi base URL host {hostname!r} is not the pinned public host "
                f"{KALSHI_PINNED_HOST!r}"
            )
        self._base = base.rstrip("/")
        self._request_timeout_s = (
            request_timeout_s
            if request_timeout_s is not None
            else settings.kalshi_request_timeout_s
        )
        self._http = None  # lazily imported; tests never touch the network

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=self._request_timeout_s)
        return self._http

    def _get(self, path: str, **params: object) -> object:
        try:
            response = self._client().get(f"{self._base}{path}", params=params or None)
        except Exception as error:
            raise KalshiUnavailableError(f"Kalshi {path} failed: {error}") from error
        if response.status_code >= 400:
            # Recorded error shapes become typed refusals carrying the
            # server's message; anything else is an unavailable error.
            try:
                body = response.json()
            except ValueError:
                raise KalshiUnavailableError(
                    f"Kalshi {path} refused (HTTP {response.status_code}): {response.text[:120]!r}"
                ) from None
            try:
                _require_error_free(body, f"Kalshi {path}")
            except KalshiProtocolError as error:
                raise KalshiProtocolError(
                    f"Kalshi {path} refused (HTTP {response.status_code}): {error}"
                ) from error
            raise KalshiUnavailableError(
                f"Kalshi {path} refused (HTTP {response.status_code})"
            )
        return response.json()

    # -- public surface ---------------------------------------------------------

    def events(self, *, limit: int | None = None, offset: int | None = None) -> object:
        params: dict[str, object] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self._get("/events", **params)

    def event(self, ticker: str) -> object:
        return self._get(f"/events/{ticker}")

    def markets(self, *, event_ticker: str, limit: int | None = None) -> object:
        params: dict[str, object] = {"event_ticker": event_ticker}
        if limit is not None:
            params["limit"] = limit
        return self._get("/markets", **params)

    def market(self, ticker: str) -> object:
        return self._get(f"/markets/{ticker}")

    def orderbook(self, ticker: str) -> object:
        return self._get(f"/markets/{ticker}/orderbook")

    def trades(
        self,
        ticker: str,
        *,
        limit: int | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> object:
        params: dict[str, object] = {"ticker": ticker}
        if limit is not None:
            params["limit"] = limit
        if start_ts is not None:
            params["min_ts"] = start_ts
        if end_ts is not None:
            params["max_ts"] = end_ts
        return self._get("/markets/trades", **params)

    def candlesticks(
        self,
        ticker: str,
        *,
        series_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> object:
        return self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )

    def series(self, series_ticker: str) -> object:
        return self._get(f"/series/{series_ticker}")
