"""Kalshi market-data adapter (M6, issue #35, Phase B).

Read-only, keyless, public-endpoints-only: trade-api v2 at
``https://api.elections.kalshi.com`` (the migration host is refused at
construction). No order path, no credentials, no signing surface
exists in this package.
"""

from quantmesh.kalshi.market_data import (
    KalshiFixtureProvider,
    KalshiLiveProvider,
    KalshiMarketDataAdapter,
)
from quantmesh.kalshi.transport import HttpxKalshiTransport, KalshiRestTransport

__all__ = [
    "KalshiFixtureProvider",
    "KalshiLiveProvider",
    "KalshiMarketDataAdapter",
    "KalshiRestTransport",
    "HttpxKalshiTransport",
]
