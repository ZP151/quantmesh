"""Moomoo venue adapters (issues #25/#26, Phases A and B).

Diagnostics and connectivity boundary for a local Moomoo OpenD
instance, market-data mapping (wire payloads → canonical models), and
the explicit-construction-only provider. Everything here is
fixture-first and testable without OpenD or the vendor SDK; the real
transport is inert until an operator explicitly reaches for it (the
``quantmesh-moomoo probe`` command, or a hand-built provider with an
``SdkTransport``).
"""

from quantmesh.moomoo.execution import (
    BrokerDeal,
    BrokerOrder,
    BrokerPosition,
    ExecutionSnapshot,
    MoomooExecutionAdapter,
    SdkTradeTransport,
    SimulatedFixtureTransport,
)
from quantmesh.moomoo.market_data import MoomooDataAdapter, market_tz, sdk_code
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDError,
    OpenDProtocolError,
    OpenDSdkMissingError,
    OpenDTransport,
    OpenDUnavailableError,
    SdkTransport,
)
from quantmesh.moomoo.provider import MoomooOpenDProvider
from quantmesh.moomoo.reconciliation import (
    AdoptionResult,
    FindingKind,
    OrderOutcome,
    ReconcileTolerance,
    ReconciliationFinding,
    ReconciliationReport,
    Severity,
    apply_reconciliation,
    run_reconciliation,
)

__all__ = [
    "AdoptionResult",
    "BrokerDeal",
    "BrokerOrder",
    "BrokerPosition",
    "ExecutionSnapshot",
    "FindingKind",
    "MoomooDataAdapter",
    "MoomooExecutionAdapter",
    "MoomooOpenDClient",
    "MoomooOpenDProvider",
    "OpenDAuthRequiredError",
    "OpenDCapabilities",
    "OpenDError",
    "OpenDProtocolError",
    "OpenDSdkMissingError",
    "OpenDTransport",
    "OpenDUnavailableError",
    "OrderOutcome",
    "ReconciliationFinding",
    "ReconciliationReport",
    "ReconcileTolerance",
    "SdkTradeTransport",
    "SdkTransport",
    "Severity",
    "SimulatedFixtureTransport",
    "apply_reconciliation",
    "market_tz",
    "run_reconciliation",
    "sdk_code",
]
