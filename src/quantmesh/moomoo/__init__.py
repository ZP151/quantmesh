"""Moomoo venue adapters (issues #25/#26, Phases A and B).

Diagnostics and connectivity boundary for a local Moomoo OpenD
instance, market-data mapping (wire payloads → canonical models), and
the explicit-construction-only provider. Everything here is
fixture-first and testable without OpenD or the vendor SDK; the real
transport is inert until an operator explicitly reaches for it (the
``quantmesh-moomoo probe`` command, or a hand-built provider with an
``SdkTransport``).
"""

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

__all__ = [
    "MoomooDataAdapter",
    "MoomooOpenDClient",
    "MoomooOpenDProvider",
    "OpenDAuthRequiredError",
    "OpenDCapabilities",
    "OpenDError",
    "OpenDProtocolError",
    "OpenDSdkMissingError",
    "OpenDTransport",
    "OpenDUnavailableError",
    "SdkTransport",
    "market_tz",
    "sdk_code",
]
