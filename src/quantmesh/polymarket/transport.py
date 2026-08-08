"""Polymarket transport boundary (M6, issue #34, Phase A).

``PolyRestTransport`` is the injected boundary every live path goes
through; ``SdkPolyTransport`` implements it over the vendored
``py-clob-client-v2`` for the CLOB surface and over httpx (a core
dependency) for Gamma discovery. The SDK client is constructed
**keyless** (``key=None`` — the pinned constructor's signer is None
then, verified in the vendored source) and lazily: unit tests never
import the SDK, and nothing constructs the client implicitly. The
Gamma and CLOB base URLs are pinned by settings
(``QUANTMESH_POLYMARKET_*``); a caller that wants to override them
does so explicitly at construction — there is no default-key path and
no order surface anywhere in this boundary.
"""

from abc import ABC, abstractmethod

from quantmesh.polymarket.errors import (
    PolymarketSDKMissingError,
    PolymarketUnavailableError,
)
from quantmesh.settings import settings

__all__ = [
    "PolyRestTransport",
    "SdkPolyTransport",
    "GAMMA_API_URL",
    "CLOB_API_URL",
]

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# The CLOB's mainnet chain id (Polygon); the keyless public-data
# surface does not depend on it, but the SDK client requires it.
POLYGON_CHAIN_ID = 137


class PolyRestTransport(ABC):
    """The read-only public surface: Gamma discovery + CLOB data.

    Every method returns the raw wire payload; parsing is the
    ``quantmesh.polymarket.wire`` parsers' job. Implementations raise
    ``PolymarketUnavailableError`` on unreachable/refused requests and
    let the wire parsers surface protocol violations.
    """

    @abstractmethod
    def gamma_events(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> object:
        """``GET /events`` discovery page (bounded by limit/offset)."""

    @abstractmethod
    def clob_book(self, token_id: str) -> object:
        """``GET /book?token_id=`` — the token's order book."""

    @abstractmethod
    def clob_market(self, condition_id: str) -> object:
        """``GET /markets/{condition_id}`` — the market object."""

    @abstractmethod
    def clob_prices_history(
        self,
        market: str,
        *,
        start_ts: int,
        end_ts: int,
        fidelity: int | None = None,
    ) -> object:
        """``GET /prices-history`` — bounded price series (ms range)."""

    @abstractmethod
    def clob_fee_rate(self, token_id: str) -> object:
        """``GET /fee-rate?token_id=`` — the token's base fee in bps."""

    @abstractmethod
    def clob_tick_size(self, token_id: str) -> object:
        """``GET /tick-size?token_id=`` — the token's minimum tick size."""


class SdkPolyTransport(PolyRestTransport):
    """Live transport over the vendored SDK (CLOB) and httpx (Gamma).

    Explicit construction only. The SDK's ``ClobClient`` is created
    with ``key=None`` so its signer is None (verified in the vendored
    source); the signing surface is never reached because no order
    path exists anywhere in M6. The SDK is imported lazily and
    import-guarded — a missing vendored submodule raises
    ``PolymarketSDKMissingError``, never an ImportError.
    """

    def __init__(
        self,
        *,
        gamma_url: str | None = None,
        clob_url: str | None = None,
        request_timeout_s: float | None = None,
        chain_id: int = POLYGON_CHAIN_ID,
    ) -> None:
        self._gamma_url = gamma_url or settings.polymarket_gamma_url
        self._clob_url = clob_url or settings.polymarket_clob_url
        self._request_timeout_s = (
            request_timeout_s
            if request_timeout_s is not None
            else settings.polymarket_request_timeout_s
        )
        self._chain_id = chain_id
        self._client = None

    # -- lazy SDK boundary ---------------------------------------------------

    def _sdk(self):
        if self._client is not None:
            return self._client
        try:
            from py_clob_client_v2.client import ClobClient
        except ImportError as error:
            raise PolymarketSDKMissingError(
                "the vendored py-clob-client-v2 is not importable"
            ) from error
        try:
            self._client = ClobClient(
                host=self._clob_url, chain_id=self._chain_id, key=None
            )
        except Exception as error:
            raise PolymarketUnavailableError(
                f"keyless CLOB client construction failed: {error}"
            ) from error
        return self._client

    def _clob_call(self, name: str, *args: object, **kwargs: object) -> object:
        client = self._sdk()
        try:
            return getattr(client, name)(*args, **kwargs)
        except Exception as error:
            raise PolymarketUnavailableError(f"CLOB {name} failed: {error}") from error

    # -- Gamma via httpx ------------------------------------------------------

    def gamma_events(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> object:
        params = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        import httpx

        try:
            response = httpx.get(
                f"{self._gamma_url}/events",
                params=params,
                timeout=self._request_timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise PolymarketUnavailableError(f"Gamma /events failed: {error}") from error
        return response.json()

    # -- CLOB via the vendored SDK --------------------------------------------

    def clob_book(self, token_id: str) -> object:
        return self._clob_call("get_order_book", token_id)

    def clob_market(self, condition_id: str) -> object:
        return self._clob_call("get_market", condition_id)

    def clob_prices_history(
        self,
        market: str,
        *,
        start_ts: int,
        end_ts: int,
        fidelity: int | None = None,
    ) -> object:
        # The server refuses ranges without an interval ("invalid
        # filters" 400, recorded live); the SDK's own params require
        # an interval or both timestamps. We always send the bounded
        # range plus the 1m interval used in the recorded probe.
        from py_clob_client_v2.clob_types import PricesHistoryParams

        params = PricesHistoryParams(
            market=market,
            start_ts=start_ts,
            end_ts=end_ts,
            fidelity=fidelity,
            interval="1m",
        )
        return self._clob_call("get_prices_history", params)

    def _raw_get(self, path: str, token_id: str) -> object:
        import httpx

        try:
            response = httpx.get(
                f"{self._clob_url}{path}",
                params={"token_id": token_id},
                timeout=self._request_timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise PolymarketUnavailableError(f"CLOB {path} failed: {error}") from error
        return response.json()

    def clob_fee_rate(self, token_id: str) -> object:
        # Read the raw ``{"base_fee": ...}`` wire ourselves instead of
        # the SDK's ``get_fee_rate_bps`` (which collapses to an int and
        # defaults a missing fee to 0 — a fail-open this adapter does
        # not replicate); the SDK's endpoint is the pinned authority,
        # the raw wire keeps our own fail-closed parser in charge.
        return self._raw_get("/fee-rate", token_id)

    def clob_tick_size(self, token_id: str) -> object:
        return self._raw_get("/tick-size", token_id)
