"""Local Moomoo OpenD connectivity boundary (issue #25, Phase A).

``MoomooOpenDClient`` is the fixture-first contract every Moomoo-facing
capability goes through: probing capabilities, then (later phases)
market data and simulated orders. The client is constructed with an
injected transport, so unit tests run with neither OpenD nor the vendor
SDK; the default ``SdkTransport`` imports the vendored ``py-moomoo-api``
lazily and is inert until an operator explicitly probes.

Safety invariants (AGENTS.md, iteration 0006):

- Probing is strictly read-only capability discovery. It never
  requests, persists, or logs account data, never reads or stores a
  password, never unlocks the trade session, and never places anything.
- The vendor SDK is reached only through this boundary; nothing else in
  QuantMesh imports it.
- Error classification is typed: ``OpenDUnavailableError`` (down or
  unreachable), ``OpenDAuthRequiredError`` (the trade session is locked
  and an unlock is a human-only action), ``OpenDSdkMissingError`` (the
  vendored SDK is not importable), ``OpenDProtocolError`` (a response
  cannot be trusted).
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from quantmesh.settings import Settings


class OpenDError(RuntimeError):
    """Base class for typed OpenD boundary failures."""


class OpenDUnavailableError(OpenDError):
    """OpenD is down, unreachable, or timed out."""


class OpenDAuthRequiredError(OpenDError):
    """The operation needs an unlocked trade session; that is human-only."""


class OpenDSdkMissingError(OpenDError):
    """The vendored py-moomoo-api SDK is not importable."""


class OpenDProtocolError(OpenDError):
    """The probe payload cannot be trusted — fail closed."""


@dataclass(frozen=True)
class OpenDCapabilities:
    """What a local OpenD instance can serve, per the probe.

    ``auth_required`` is the locked-session state: while an account is
    locked, ``order`` and ``order_query`` are forced to ``False`` no
    matter what the transport reports — a locked session must never look
    tradable.
    """

    quote: bool
    history_kline: bool
    order: bool
    order_query: bool
    auth_required: bool = False


_REQUIRED_PROBE_KEYS = ("quote", "history_kline", "order", "order_query", "auth_required")


@runtime_checkable
class OpenDTransport(Protocol):
    """Injected transport behind the client boundary.

    Tests provide stub transports; the default is ``SdkTransport`` over
    a real local OpenD. Extra keys in a probe payload are tolerated
    (the vendored SDK grows fields), but missing or mistyped keys are a
    ``OpenDProtocolError``.
    """

    def probe(self) -> dict: ...
    def close(self) -> None: ...


class SdkTransport:
    """Transport over a real local OpenD via the vendored py-moomoo-api.

    The SDK import is deferred to ``probe``, so constructing the client
    never requires the SDK and fixture-only consumers never touch it.
    The probe is deliberately defensive: every SDK interaction is
    wrapped, and failures are classified rather than leaked. Exact SDK
    behavior (context names, error codes) varies by vendored version and
    is validated at the Phase E operator gate with a human-provided
    simulated-account OpenD; until then this transport is exercised only
    by the typed-missing-SDK test.
    """

    def __init__(
        self, *, host: str, port: int, connect_timeout_s: float, request_timeout_s: float
    ) -> None:
        self._host = host
        self._port = port
        self._connect_timeout_s = connect_timeout_s
        self._request_timeout_s = request_timeout_s

    def probe(self) -> dict:
        try:
            from moomoo import (  # type: ignore[import-not-found]
                OpenQuoteContext,
                OpenSecTradeContext,
            )
        except ImportError as error:
            raise OpenDSdkMissingError(
                "py-moomoo-api is not importable — add vendor/components/py-moomoo-api "
                "to the environment or pip-install it"
            ) from error
        report = {
            "quote": False,
            "history_kline": False,
            "order": False,
            "order_query": False,
            "auth_required": False,
        }
        try:
            quote = OpenQuoteContext(host=self._host, port=self._port)
            report["quote"] = True
            report["history_kline"] = True
            quote.close()
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        try:
            order = OpenSecTradeContext(filter_trdmarket=1, host=self._host, port=self._port)
            report["order"] = True
            report["order_query"] = True
            order.close()
        except Exception as error:  # noqa: BLE001 - classify, never leak
            classified = self._classify(error)
            if isinstance(classified, OpenDAuthRequiredError):
                # A locked trade session is reportable state, not a probe
                # failure: quote capabilities still answer, and the client
                # forces order/order_query to False when auth_required.
                report["auth_required"] = True
            else:
                raise classified from error
        return report

    def close(self) -> None:
        """Nothing to release; SDK contexts are closed per probe."""

    def _classify(self, error: Exception) -> OpenDError:
        """Classify an SDK failure into the typed boundary errors.

        The heuristic keys on the SDK's own error language (unlock,
        auth, password) because the vendored SDK's error codes vary by
        version; the Phase E operator gate validates this against a real
        simulated-account OpenD. Anything else is availability.
        """
        message = f"{error}".lower()
        if "unlock" in message or "auth" in message or "password" in message:
            return OpenDAuthRequiredError(f"OpenD trade session is locked: {error}")
        return OpenDUnavailableError(
            f"OpenD at {self._host}:{self._port} is unavailable: {error}"
        )


class MoomooOpenDClient:
    """Fixture-first boundary to a local Moomoo OpenD instance.

    Construct with an injected transport for tests, or via
    ``from_settings`` for the real ``SdkTransport``. Nothing here
    touches the network or the SDK until ``probe`` is called.
    """

    def __init__(self, transport: OpenDTransport) -> None:
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> "MoomooOpenDClient":
        return cls(
            SdkTransport(
                host=settings.moomoo_opend_host,
                port=settings.moomoo_opend_port,
                connect_timeout_s=settings.moomoo_opend_connect_timeout_s,
                request_timeout_s=settings.moomoo_opend_request_timeout_s,
            )
        )

    def probe(self) -> OpenDCapabilities:
        """Read-only capability discovery; see module docstring for safety."""
        payload = self._transport.probe()
        if not isinstance(payload, dict):
            kind = type(payload).__name__
            raise OpenDProtocolError(f"probe payload must be a mapping, got {kind}")
        for key in _REQUIRED_PROBE_KEYS:
            if key not in payload:
                raise OpenDProtocolError(f"probe payload is missing {key!r}")
            if not isinstance(payload[key], bool):
                raise OpenDProtocolError(f"probe payload key {key!r} must be bool")
        caps = OpenDCapabilities(
            quote=payload["quote"],
            history_kline=payload["history_kline"],
            order=payload["order"],
            order_query=payload["order_query"],
            auth_required=payload["auth_required"],
        )
        if caps.auth_required:
            # A locked session must never look tradable.
            return OpenDCapabilities(
                quote=caps.quote,
                history_kline=caps.history_kline,
                order=False,
                order_query=False,
                auth_required=True,
            )
        return caps

    def close(self) -> None:
        self._transport.close()
