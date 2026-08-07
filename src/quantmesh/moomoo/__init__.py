"""Moomoo venue adapters (issue #25, Phase A).

Diagnostics and connectivity boundary for a local Moomoo OpenD
instance, plus (later phases) market-data and simulated-order adapters.
Everything here is fixture-first and testable without OpenD or the
vendor SDK; the real transport is inert until an operator explicitly
runs the ``quantmesh-moomoo probe`` command.
"""

from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDError,
    OpenDProtocolError,
    OpenDSdkMissingError,
    OpenDUnavailableError,
)

__all__ = [
    "MoomooOpenDClient",
    "OpenDAuthRequiredError",
    "OpenDCapabilities",
    "OpenDError",
    "OpenDProtocolError",
    "OpenDSdkMissingError",
    "OpenDUnavailableError",
]
