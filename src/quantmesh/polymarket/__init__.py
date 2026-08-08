"""Polymarket market-data adapter (M6, issue #34, Phase A).

Read-only, keyless, public-endpoints-only: Gamma discovery via REST,
CLOB books/markets/fee/tick/prices-history via the pinned
``py-clob-client-v2`` keyless surface or the raw wire. No order path,
no credentials, no signing surface exists in this package.
"""

from quantmesh.polymarket.market_data import (
    PolyFixtureProvider,
    PolyLiveProvider,
    PolyMarketDataAdapter,
)
from quantmesh.polymarket.transport import PolyRestTransport, SdkPolyTransport

__all__ = [
    "PolyFixtureProvider",
    "PolyLiveProvider",
    "PolyMarketDataAdapter",
    "PolyRestTransport",
    "SdkPolyTransport",
]
