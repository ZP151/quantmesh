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
    HyperliquidRiskRefusalError,
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.exchange import (
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    CancelAck,
    ExchangeTransport,
    ExecutionSnapshot,
    HyperliquidExecutionAdapter,
    HyperliquidSigner,
    InMemorySigner,
    PlaceAck,
    ScriptedExchangeTransport,
    SdkExchangeTransport,
    build_snapshot,
    parse_cancel_ack,
    parse_fill,
    parse_open_order,
    parse_place_ack,
    parse_position,
    signer_from_env,
    to_cloid,
)
from quantmesh.hyperliquid.market_data import (
    HyperliquidDataAdapter,
    HyperliquidFixtureProvider,
    HyperliquidLiveProvider,
)
from quantmesh.hyperliquid.reconciliation import (
    HYPERLIQUID_STATUS_TO_DOMAIN,
    apply_reconciliation,
    run_reconciliation,
)
from quantmesh.hyperliquid.rest import (
    MAINNET_API_URL,
    TESTNET_API_URL,
    RestTransport,
    ScriptedRestTransport,
    SdkRestTransport,
)
from quantmesh.hyperliquid.risk import (
    FUNDING_LEDGER_FILE,
    FundingEntry,
    FundingLedger,
    RiskContext,
    RiskContextProvider,
    RiskDecision,
    RiskKind,
    RiskLimits,
    RiskRefusal,
    evaluate_order,
)
from quantmesh.hyperliquid.signal import book_imbalance, imbalance_by_bar
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
    "BrokerFill",
    "BrokerOrder",
    "BrokerPosition",
    "CancelAck",
    "ExchangeTransport",
    "ExecutionSnapshot",
    "FUNDING_LEDGER_FILE",
    "FundingEntry",
    "FundingLedger",
    "FundingRate",
    "GapFinding",
    "HYPERLIQUID_STATUS_TO_DOMAIN",
    "HyperliquidDataAdapter",
    "HyperliquidError",
    "HyperliquidExecutionAdapter",
    "HyperliquidFixtureProvider",
    "HyperliquidLiveProvider",
    "HyperliquidProtocolError",
    "HyperliquidRiskRefusalError",
    "HyperliquidSDKMissingError",
    "HyperliquidSigner",
    "HyperliquidStream",
    "HyperliquidUnavailableError",
    "InMemorySigner",
    "MAINNET_API_URL",
    "PerpMeta",
    "PlaceAck",
    "RestTransport",
    "RiskContext",
    "RiskContextProvider",
    "RiskDecision",
    "RiskKind",
    "RiskLimits",
    "RiskRefusal",
    "ScriptedExchangeTransport",
    "ScriptedRestTransport",
    "SdkExchangeTransport",
    "SdkRestTransport",
    "SimulatedStreamTransport",
    "SpotPair",
    "StreamSupervisor",
    "TESTNET_API_URL",
    "apply_reconciliation",
    "book_imbalance",
    "build_snapshot",
    "evaluate_order",
    "imbalance_by_bar",
    "next_backoff",
    "parse_cancel_ack",
    "parse_fill",
    "parse_open_order",
    "parse_place_ack",
    "parse_position",
    "run_reconciliation",
    "signer_from_env",
    "subscription_identifier",
    "to_cloid",
    "ws_url_for",
]
