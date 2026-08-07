"""Hyperliquid testnet market-data and execution surface (M5).

The package is fixture-first like ``quantmesh.moomoo``: everything
here is testable without the SDK or the network, the live surfaces are
explicit-construction-only, and the testnet endpoint is pinned while
mainnet is refused before the wire (ADR-0007). Phase A ships the
REST/WS market-data surface; Phase B adds the testnet execution
adapters; Phase C the risk pre-submission checks; Phase D the crypto
baselines; Phase E the wallet-isolation tests and operator drill.
"""

from quantmesh.hyperliquid.errors import (
    HyperliquidError,
    HyperliquidProtocolError,
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.market_data import (
    HyperliquidDataAdapter,
    HyperliquidFixtureProvider,
    HyperliquidLiveProvider,
)
from quantmesh.hyperliquid.rest import (
    MAINNET_API_URL,
    TESTNET_API_URL,
    RestTransport,
    ScriptedRestTransport,
    SdkRestTransport,
)
from quantmesh.hyperliquid.stream import (
    GapFinding,
    HyperliquidStream,
    SimulatedStreamTransport,
    StreamSupervisor,
    next_backoff,
    subscription_identifier,
    ws_url_for,
)
from quantmesh.hyperliquid.wire import FundingRate, PerpMeta, SpotPair

__all__ = [
    "FundingRate",
    "GapFinding",
    "HyperliquidDataAdapter",
    "HyperliquidError",
    "HyperliquidFixtureProvider",
    "HyperliquidLiveProvider",
    "HyperliquidProtocolError",
    "HyperliquidSDKMissingError",
    "HyperliquidStream",
    "HyperliquidUnavailableError",
    "MAINNET_API_URL",
    "PerpMeta",
    "RestTransport",
    "ScriptedRestTransport",
    "SdkRestTransport",
    "SimulatedStreamTransport",
    "SpotPair",
    "StreamSupervisor",
    "TESTNET_API_URL",
    "next_backoff",
    "subscription_identifier",
    "ws_url_for",
]
