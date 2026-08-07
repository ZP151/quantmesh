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

from quantmesh.domain.market_data import interval_to_timedelta
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

# The SDK's adjustment markers (``AuType``); "None" is raw (unadjusted).
_AUTYPE_KEYS = ("None", "qfq", "hfq")

# Canonical interval → SDK ``KLType``. Month/quarter/year klines have no
# canonical timedelta representation and are refused at the transport.
_KL_MAP = {
    "1m": "K_1M",
    "3m": "K_3M",
    "5m": "K_5M",
    "15m": "K_15M",
    "30m": "K_30M",
    "60m": "K_60M",
    "1d": "K_DAY",
    "1w": "K_WEEK",
}


@runtime_checkable
class OpenDTransport(Protocol):
    """Injected transport behind the client boundary.

    Tests provide stub transports; the default is ``SdkTransport`` over
    a real local OpenD. Extra keys in a probe payload are tolerated
    (the vendored SDK grows fields), but missing or mistyped keys are a
    ``OpenDProtocolError``.

    Market-data methods (ADR-0004 extension, Phase B) return pandas-free
    dict payloads whose contract the adapter validates: klines carry
    ``code``/``interval``/``autype``/``rows`` (rows with venue-local
    ``time_key`` and OHLCV), tickers ``code``/``rows`` (venue-local
    ``time``, ``price``, ``volume``, optional ``sequence``/``direction``),
    quotes ``rows`` (per-row ``code``, ``data_date``, ``last_price``).
    A transport that does not serve a surface inherits a
    ``NotImplementedError`` default, so a probe-only transport is still
    a valid ``OpenDTransport``.
    """

    def probe(self) -> dict: ...

    def history_kline(
        self, code: str, *, interval: str, start: str | None, end: str | None, autype: str
    ) -> dict:
        raise NotImplementedError("this transport does not serve historical klines")

    def rt_ticker(self, code: str, *, num: int) -> dict:
        raise NotImplementedError("this transport does not serve real-time tickers")

    def stock_quote(self, codes: list[str]) -> dict:
        raise NotImplementedError("this transport does not serve stock quotes")

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

    def _open_quote_ctx(self):
        """Lazy SDK import + context creation, failures classified."""
        try:
            from moomoo import OpenQuoteContext  # type: ignore[import-not-found]
        except ImportError as error:
            raise OpenDSdkMissingError(
                "py-moomoo-api is not importable — add vendor/components/py-moomoo-api "
                "to the environment or pip-install it"
            ) from error
        try:
            return OpenQuoteContext(host=self._host, port=self._port)
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error

    def probe(self) -> dict:
        try:
            from moomoo import OpenSecTradeContext  # type: ignore[import-not-found]
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
        quote = self._open_quote_ctx()
        quote.close()
        report["quote"] = True
        report["history_kline"] = True
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

    def history_kline(
        self, code: str, *, interval: str, start: str | None, end: str | None, autype: str
    ) -> dict:
        """Historical klines as a pandas-free payload (ADR-0004 extension)."""
        context = self._open_quote_ctx()
        try:
            ret, table, _page = context.request_history_kline(
                code, start=start, end=end, ktype=self._kltype(interval), autype=autype
            )
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        finally:
            context.close()
        if ret != 0:
            message = table if isinstance(table, str) else f"request_history_kline returned {ret}"
            raise self._classify(RuntimeError(message))
        return {
            "code": code,
            "interval": interval,
            "autype": autype,
            "rows": [dict(record) for record in table.to_dict("records")],
        }

    def rt_ticker(self, code: str, *, num: int) -> dict:
        """Recent real-time tickers as a pandas-free payload."""
        context = self._open_quote_ctx()
        try:
            ret, table = context.get_rt_ticker(code, num=num)
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        finally:
            context.close()
        if ret != 0:
            message = table if isinstance(table, str) else f"get_rt_ticker returned {ret}"
            raise self._classify(RuntimeError(message))
        rows = [
            {
                "time": record.get("time"),
                "sequence": record.get("sequence"),
                "price": record.get("price"),
                "volume": record.get("volume"),
                "turnover": record.get("turnover"),
                "direction": record.get("ticker_direction"),
                "type": record.get("type"),
            }
            for record in table.to_dict("records")
        ]
        return {"code": code, "rows": rows}

    def stock_quote(self, codes: list[str]) -> dict:
        """Stock quotes as a pandas-free payload; rows carry their own code."""
        context = self._open_quote_ctx()
        try:
            ret, table = context.get_stock_quote(codes)
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        finally:
            context.close()
        if ret != 0:
            message = table if isinstance(table, str) else f"get_stock_quote returned {ret}"
            raise self._classify(RuntimeError(message))
        keep = (
            "code",
            "data_date",
            "data_time",
            "last_price",
            "open_price",
            "high_price",
            "low_price",
            "prev_close_price",
            "volume",
            "turnover",
        )
        rows = [{key: record.get(key) for key in keep} for record in table.to_dict("records")]
        return {"rows": rows}

    def _kltype(self, interval: str) -> str:
        try:
            return _KL_MAP[interval]
        except KeyError as error:
            raise ValueError(
                f"interval {interval!r} has no KLType mapping "
                f"(supported: {', '.join(_KL_MAP)})"
            ) from error

    def close(self) -> None:
        """Nothing to release; SDK contexts are closed per request."""

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

    def history_kline(
        self,
        code: str,
        *,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        autype: str = "None",
    ) -> dict:
        """Historical klines for ``code`` as a wire payload (Phase B).

        ``interval`` is a canonical compact interval (``"1d"``, ``"5m"``);
        ``autype`` is the SDK adjustment marker, raw (``"None"``) by
        default. Request validation fails fast before any transport call;
        mapping the returned payload to canonical models is the adapter's
        job.
        """
        interval_to_timedelta(interval)
        if autype not in _AUTYPE_KEYS:
            raise ValueError(f"unknown autype {autype!r} (expected one of {_AUTYPE_KEYS})")
        return self._transport.history_kline(
            code, interval=interval, start=start, end=end, autype=autype
        )

    def rt_ticker(self, code: str, *, num: int = 500) -> dict:
        """Recent real-time tickers for ``code`` as a wire payload (Phase B)."""
        if not isinstance(num, int) or not 1 <= num <= 1000:
            raise ValueError(f"num must be an integer in [1, 1000], got {num!r}")
        return self._transport.rt_ticker(code, num=num)

    def stock_quote(self, codes: list[str]) -> dict:
        """Stock quotes for ``codes`` as a wire payload (Phase B)."""
        if (
            not isinstance(codes, list)
            or not codes
            or not all(isinstance(code, str) for code in codes)
        ):
            raise ValueError("codes must be a non-empty list of strings")
        return self._transport.stock_quote(codes)

    def close(self) -> None:
        self._transport.close()
