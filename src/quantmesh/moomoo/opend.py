"""Local Moomoo OpenD connectivity boundary (issue #25, Phase A).

``MoomooOpenDClient`` is the fixture-first contract every Moomoo-facing
capability goes through: probing capabilities, then (later phases)
market data and simulated orders. The client is constructed with an
injected transport, so unit tests run with neither OpenD nor the vendor
SDK; the default ``SdkTransport`` lazily imports a separately installed,
audited compatible ``py-moomoo-api`` runtime and is inert until explicitly used.

Safety invariants (AGENTS.md, iteration 0006):

- Probing is strictly read-only capability discovery. It never
  requests, persists, or logs account data, never reads or stores a
  password, never unlocks the trade session, and never places anything.
- The vendor SDK is reached only through this boundary; nothing else in
  QuantMesh imports it.
- Error classification is typed: ``OpenDUnavailableError`` (down or
  unreachable), ``OpenDAuthRequiredError`` (the trade session is locked
  and an unlock is a human-only action), ``OpenDSdkMissingError`` (the
  compatible SDK is not importable), ``OpenDProtocolError`` (a response
  cannot be trusted).
"""

import base64
import math
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import date, datetime
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
    """An audited compatible py-moomoo-api runtime is not importable."""


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
    (the compatible SDK may grow fields), but missing or mistyped keys are a
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

    def history_kline_page(
        self,
        code: str,
        *,
        interval: str,
        start: str | None,
        end: str | None,
        autype: str,
        max_count: int,
        page_req_key: bytes | None,
    ) -> dict:
        """Compatibility page for transports that only serve one legacy response."""
        return _legacy_history_page(
            self,
            code=code,
            interval=interval,
            start=start,
            end=end,
            autype=autype,
            page_req_key=page_req_key,
        )

    @contextmanager
    def history_session(self) -> Iterator["OpenDTransport"]:
        """Keep one transport lifetime across a complete cursor chain."""
        yield self

    def adjustment_factors(self, code: str) -> dict:
        raise NotImplementedError("this transport does not serve adjustment factors")

    def stock_splits_page(self, code: str, *, next_key: str | None, num: int) -> dict:
        raise NotImplementedError("this transport does not serve stock splits")

    def dividends(self, code: str) -> dict:
        raise NotImplementedError("this transport does not serve dividends")

    def rt_ticker(self, code: str, *, num: int) -> dict:
        raise NotImplementedError("this transport does not serve real-time tickers")

    def stock_quote(self, codes: list[str]) -> dict:
        raise NotImplementedError("this transport does not serve stock quotes")

    def close(self) -> None: ...


class SdkTransport:
    """Transport over local OpenD via an audited compatible py-moomoo-api.

    The SDK import is deferred to ``probe``, so constructing the client
    never requires the SDK and fixture-only consumers never touch it.
    The probe is deliberately defensive: every SDK interaction is
    wrapped, and failures are classified rather than leaked. Exact SDK
    behavior (context names, error codes) varies by installed version and
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
                "py-moomoo-api is not importable — install only a compatible SDK closure "
                "audited under ADR-0004; the vendored 10.02 snapshot is reference-only"
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
                "py-moomoo-api is not importable — install only a compatible SDK closure "
                "audited under ADR-0004; the vendored 10.02 snapshot is reference-only"
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
        """One backwards-compatible first page of historical klines."""
        return self.history_kline_page(
            code,
            interval=interval,
            start=start,
            end=end,
            autype=autype,
            max_count=1000,
            page_req_key=None,
        )

    def history_kline_page(
        self,
        code: str,
        *,
        interval: str,
        start: str | None,
        end: str | None,
        autype: str,
        max_count: int,
        page_req_key: bytes | None,
    ) -> dict:
        """One official ``request_history_kline`` page as plain Python data."""
        context = self._open_quote_ctx()
        try:
            return self._history_kline_page_with_context(
                context,
                code=code,
                interval=interval,
                start=start,
                end=end,
                autype=autype,
                max_count=max_count,
                page_req_key=page_req_key,
            )
        finally:
            context.close()

    @contextmanager
    def history_session(self) -> Iterator["_SdkHistorySession"]:
        """Use one quote context for every opaque cursor in a history chain."""
        context = self._open_quote_ctx()
        try:
            yield _SdkHistorySession(self, context)
        finally:
            context.close()

    def _history_kline_page_with_context(
        self,
        context,
        *,
        code: str,
        interval: str,
        start: str | None,
        end: str | None,
        autype: str,
        max_count: int,
        page_req_key: bytes | None,
    ) -> dict:
        try:
            ret, table, next_page_req_key = _sdk_result(
                context.request_history_kline(
                    code,
                    start=start,
                    end=end,
                    ktype=self._kltype(interval),
                    autype=autype,
                    max_count=max_count,
                    page_req_key=page_req_key,
                ),
                "request_history_kline",
                arity=3,
            )
        except OpenDError:
            raise
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        if ret != 0:
            message = table if isinstance(table, str) else f"request_history_kline returned {ret}"
            raise self._classify(RuntimeError(message))
        return {
            "code": code,
            "interval": interval,
            "autype": autype,
            "request_page_req_key": page_req_key,
            "next_page_req_key": next_page_req_key,
            "rows": _table_records(table, "history"),
        }

    def adjustment_factors(self, code: str) -> dict:
        """Official ``get_rehab`` response without pandas objects."""
        context = self._open_quote_ctx()
        try:
            ret, table = _sdk_result(context.get_rehab(code), "get_rehab", arity=2)
        except OpenDError:
            raise
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        finally:
            context.close()
        if ret != 0:
            message = table if isinstance(table, str) else f"get_rehab returned {ret}"
            raise self._classify(RuntimeError(message))
        return {"code": code, "rows": _table_records(table, "adjustment-factor")}

    def stock_splits_page(self, code: str, *, next_key: str | None, num: int) -> dict:
        """One official stock-split page without pandas objects."""
        context = self._open_quote_ctx()
        try:
            method = _sdk_method(context, "get_corporate_actions_stock_splits", "stock-split")
            ret, payload = _sdk_result(
                method(code, next_key=next_key, num=num),
                "get_corporate_actions_stock_splits",
                arity=2,
            )
        except OpenDError:
            raise
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        finally:
            context.close()
        if ret != 0:
            message = payload if isinstance(payload, str) else f"stock splits returned {ret}"
            raise self._classify(RuntimeError(message))
        if not isinstance(payload, dict):
            raise OpenDProtocolError("stock-split SDK payload must be a mapping")
        missing = [key for key in ("next_key", "split_list") if key not in payload]
        if missing:
            raise OpenDProtocolError(f"stock-split SDK payload is missing {missing}")
        next_cursor = payload["next_key"]
        if not isinstance(next_cursor, str) or not next_cursor:
            raise OpenDProtocolError("stock-split SDK next_key must be a non-empty string")
        return {
            "code": code,
            "request_next_key": next_key,
            "next_key": next_cursor,
            "rows": _mapping_rows(payload["split_list"], "stock-split"),
        }

    def dividends(self, code: str) -> dict:
        """Official corporate-action dividend response as plain Python data."""
        context = self._open_quote_ctx()
        try:
            method = _sdk_method(context, "get_corporate_actions_dividends", "dividend")
            ret, payload = _sdk_result(method(code), "get_corporate_actions_dividends", arity=2)
        except OpenDError:
            raise
        except Exception as error:  # noqa: BLE001 - classify, never leak
            raise self._classify(error) from error
        finally:
            context.close()
        if ret != 0:
            message = payload if isinstance(payload, str) else f"dividends returned {ret}"
            raise self._classify(RuntimeError(message))
        if not isinstance(payload, dict):
            raise OpenDProtocolError("dividend SDK payload must be a mapping")
        if "dividend_list" not in payload:
            raise OpenDProtocolError("dividend SDK payload is missing ['dividend_list']")
        return {
            "code": code,
            "rows": _mapping_rows(payload["dividend_list"], "dividend"),
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
                f"interval {interval!r} has no KLType mapping (supported: {', '.join(_KL_MAP)})"
            ) from error

    def close(self) -> None:
        """Nothing to release; SDK contexts are closed per request."""

    def _classify(self, error: Exception) -> OpenDError:
        """Classify an SDK failure into the typed boundary errors.

        The heuristic keys on the SDK's own error language (unlock,
        auth, password) because compatible SDK error codes vary by
        version; the Phase E operator gate validates this against a real
        simulated-account OpenD. Anything else is availability.
        """
        message = f"{error}".lower()
        if "unlock" in message or "auth" in message or "password" in message:
            return OpenDAuthRequiredError(f"OpenD trade session is locked: {error}")
        return OpenDUnavailableError(f"OpenD at {self._host}:{self._port} is unavailable: {error}")


class _SdkHistorySession:
    """Page facade tied to one SDK quote-context lifetime."""

    def __init__(self, transport: SdkTransport, context) -> None:
        self._transport = transport
        self._context = context

    def history_kline_page(
        self,
        code: str,
        *,
        interval: str,
        start: str | None,
        end: str | None,
        autype: str,
        max_count: int,
        page_req_key: bytes | None,
    ) -> dict:
        return self._transport._history_kline_page_with_context(
            self._context,
            code=code,
            interval=interval,
            start=start,
            end=end,
            autype=autype,
            max_count=max_count,
            page_req_key=page_req_key,
        )


class _LegacyHistorySession:
    """Structural adapter for transports that expose only ``history_kline``."""

    def __init__(self, transport: object) -> None:
        self._transport = transport

    def history_kline_page(
        self,
        code: str,
        *,
        interval: str,
        start: str | None,
        end: str | None,
        autype: str,
        max_count: int,
        page_req_key: bytes | None,
    ) -> dict:
        del max_count
        return _legacy_history_page(
            self._transport,
            code=code,
            interval=interval,
            start=start,
            end=end,
            autype=autype,
            page_req_key=page_req_key,
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

    def history_pages(
        self,
        code: str,
        *,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        autype: str = "None",
        page_size: int = 1000,
        max_pages: int = 100,
        max_rows: int = 100_000,
    ) -> list[dict]:
        """Collect every bounded history page while preserving cursor evidence."""
        interval_to_timedelta(interval)
        if autype not in _AUTYPE_KEYS:
            raise ValueError(f"unknown autype {autype!r} (expected one of {_AUTYPE_KEYS})")
        start_date = _date_bound(start, "start")
        end_date = _date_bound(end, "end")
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start must not be after end")
        _bounded_int(page_size, "page_size", minimum=1, maximum=1000)
        _bounded_int(max_pages, "max_pages", minimum=1)
        _bounded_int(max_rows, "max_rows", minimum=1)
        pages: list[dict] = []
        requested: bytes | None = None
        seen_cursors: set[bytes] = set()
        row_count = 0
        session_factory = getattr(self._transport, "history_session", None)
        page_method = getattr(self._transport, "history_kline_page", None)
        legacy_method = getattr(self._transport, "history_kline", None)
        if callable(session_factory):
            session_context = session_factory()
        elif callable(page_method):
            session_context = nullcontext(self._transport)
        elif callable(legacy_method):
            session_context = nullcontext(_LegacyHistorySession(self._transport))
        else:
            raise OpenDProtocolError("transport exposes no historical-kline method")
        with session_context as session:
            while True:
                page = session.history_kline_page(
                    code,
                    interval=interval,
                    start=start,
                    end=end,
                    autype=autype,
                    max_count=page_size,
                    page_req_key=requested,
                )
                _validate_history_page(
                    page,
                    code=code,
                    interval=interval,
                    autype=autype,
                    requested=requested,
                    start=start_date,
                    end=end_date,
                )
                row_count += len(page["rows"])
                if row_count > max_rows:
                    raise OpenDProtocolError(f"history response exceeds max_rows={max_rows}")
                next_cursor = page["next_page_req_key"]
                if next_cursor is not None and not page["rows"]:
                    raise OpenDProtocolError("history response has an empty nonterminal page")
                pages.append(_history_evidence_page(page))
                if next_cursor is None:
                    return pages
                if len(pages) >= max_pages:
                    raise OpenDProtocolError(f"history response exceeds max_pages={max_pages}")
                if (
                    not isinstance(next_cursor, bytes)
                    or not next_cursor
                    or next_cursor in seen_cursors
                ):
                    raise OpenDProtocolError("history response has a repeated page cursor")
                seen_cursors.add(next_cursor)
                requested = next_cursor

    def adjustment_factors(self, code: str) -> dict:
        """Return raw official adjustment-factor rows without deriving prices."""
        return _plain_mapping(
            _validate_action_payload(
                self._transport.adjustment_factors(code),
                contract="adjustment-factor",
                code=code,
            ),
            "adjustment-factor",
        )

    def stock_splits(
        self,
        code: str,
        *,
        page_size: int = 50,
        max_pages: int = 100,
        max_rows: int = 5_000,
    ) -> list[dict]:
        """Collect every official stock-split page with bounded cursors."""
        _bounded_int(page_size, "page_size", minimum=1, maximum=50)
        _bounded_int(max_pages, "max_pages", minimum=1)
        _bounded_int(max_rows, "max_rows", minimum=1)
        pages: list[dict] = []
        requested: str | None = None
        seen: set[str] = set()
        row_count = 0
        while True:
            page = _plain_mapping(
                _validate_action_payload(
                    self._transport.stock_splits_page(code, next_key=requested, num=page_size),
                    contract="stock-split",
                    code=code,
                    required=("request_next_key", "next_key"),
                ),
                "stock-split",
            )
            if page["request_next_key"] != requested:
                raise OpenDProtocolError("stock-split page request cursor disagrees")
            row_count += len(page["rows"])
            if row_count > max_rows:
                raise OpenDProtocolError(f"stock-split response exceeds max_rows={max_rows}")
            pages.append(page)
            next_key = page["next_key"]
            if next_key == "-1":
                return pages
            if not page["rows"]:
                raise OpenDProtocolError("stock-split response has an empty nonterminal page")
            if len(pages) >= max_pages:
                raise OpenDProtocolError(f"stock-split response exceeds max_pages={max_pages}")
            if not isinstance(next_key, str) or not next_key or next_key in seen:
                raise OpenDProtocolError("stock-split response has a repeated page cursor")
            seen.add(next_key)
            requested = next_key

    def dividends(self, code: str) -> dict:
        """Return raw official dividend rows without parsing distribution text."""
        return _plain_mapping(
            _validate_action_payload(
                self._transport.dividends(code), contract="dividend", code=code
            ),
            "dividend",
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


def _legacy_history_page(
    transport: object,
    *,
    code: str,
    interval: str,
    start: str | None,
    end: str | None,
    autype: str,
    page_req_key: bytes | None,
) -> dict:
    if page_req_key is not None:
        raise OpenDProtocolError("legacy transport cannot continue a paginated response")
    method = getattr(transport, "history_kline", None)
    if not callable(method):
        raise OpenDProtocolError("legacy transport exposes no history_kline method")
    payload = method(code, interval=interval, start=start, end=end, autype=autype)
    if not isinstance(payload, dict):
        return payload
    return {
        **payload,
        "request_page_req_key": None,
        "next_page_req_key": None,
        "_legacy_single_page": True,
    }


def _bounded_int(value: object, name: str, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _table_records(table: object, contract: str) -> list[dict]:
    """Convert one DataFrame-like SDK table without accepting shape drift."""
    to_dict = getattr(table, "to_dict", None)
    if not callable(to_dict):
        raise OpenDProtocolError(f"{contract} SDK table has no records conversion")
    try:
        rows = to_dict("records")
    except Exception as error:  # noqa: BLE001 - malformed SDK value
        raise OpenDProtocolError(f"{contract} SDK table cannot convert to records") from error
    return _mapping_rows(rows, contract)


def _sdk_method(context: object, name: str, contract: str):
    method = getattr(context, name, None)
    if not callable(method):
        raise OpenDProtocolError(
            f"installed Moomoo SDK does not expose {name} required by {contract}"
        )
    return method


def _sdk_result(value: object, contract: str, *, arity: int) -> tuple:
    if not isinstance(value, tuple) or len(value) != arity:
        raise OpenDProtocolError(f"{contract} must return a {arity}-item result tuple")
    status = value[0]
    if type(status) is not int:
        raise OpenDProtocolError(f"{contract} must return an integer status")
    return value


def _mapping_rows(rows: object, contract: str) -> list[dict]:
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise OpenDProtocolError(f"{contract} SDK rows must be a list of mappings")
    return [_plain_mapping(row, contract) for row in rows]


def _plain_mapping(value: dict, contract: str) -> dict:
    normalized = _plain_json(value, contract)
    if not isinstance(normalized, dict):  # defensive; ``value`` is already a dict
        raise OpenDProtocolError(f"{contract} payload is not a mapping")
    return normalized


def _plain_json(value: object, contract: str):
    """Normalize SDK scalars to strict JSON types; NaN means source null."""
    value_type = type(value)
    if value_type.__name__ in {"NAType", "NaTType"} and value_type.__module__.startswith(
        ("pandas", "pandas._libs")
    ):
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            raise OpenDProtocolError(f"{contract} payload contains an infinite float")
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise OpenDProtocolError(f"{contract} payload keys must be strings")
        return {key: _plain_json(item, contract) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item, contract) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        converted = item()
        if converted is not value:
            return _plain_json(converted, contract)
    raise OpenDProtocolError(f"{contract} payload contains non-JSON value {type(value).__name__}")


def _cursor_evidence(cursor: object) -> str | None:
    if cursor is None:
        return None
    if not isinstance(cursor, bytes) or not cursor:
        raise OpenDProtocolError("history response has an invalid page cursor")
    return "base64:" + base64.b64encode(cursor).decode("ascii")


def _history_evidence_page(page: dict) -> dict:
    """Encode opaque SDK cursor bytes losslessly for canonical JSON storage."""
    return _plain_mapping(
        {
            **page,
            "request_page_req_key": _cursor_evidence(page["request_page_req_key"]),
            "next_page_req_key": _cursor_evidence(page["next_page_req_key"]),
        },
        "history",
    )


def _date_bound(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date string") from error


def _validate_history_page(
    payload: object,
    *,
    code: str,
    interval: str,
    autype: str,
    requested: bytes | None,
    start: date | None,
    end: date | None,
) -> None:
    page = _validate_action_payload(
        payload,
        contract="history",
        code=code,
        required=("interval", "autype", "request_page_req_key", "next_page_req_key"),
    )
    if page["interval"] != interval or page["autype"] != autype:
        raise OpenDProtocolError("history page interval/autype echo disagrees")
    if page["request_page_req_key"] != requested:
        raise OpenDProtocolError("history page request cursor disagrees")
    for index, row in enumerate(page["rows"]):
        raw_time = row.get("time_key")
        if not isinstance(raw_time, str):
            raise OpenDProtocolError(f"history row {index} has no string time_key")
        try:
            event_date = date.fromisoformat(raw_time[:10])
        except ValueError as error:
            raise OpenDProtocolError(f"history row {index} has an invalid time_key") from error
        if (start is not None and event_date < start) or (end is not None and event_date > end):
            raise OpenDProtocolError(f"history row {index} is outside requested date bounds")


def _validate_action_payload(
    payload: object,
    *,
    contract: str,
    code: str,
    required: tuple[str, ...] = (),
) -> dict:
    if not isinstance(payload, dict):
        raise OpenDProtocolError(f"{contract} payload is non-mapping ({type(payload).__name__})")
    missing = [key for key in ("code", "rows", *required) if key not in payload]
    if missing:
        raise OpenDProtocolError(f"{contract} payload is missing {missing}")
    if payload["code"] != code:
        raise OpenDProtocolError(f"{contract} payload code disagrees with request")
    if not isinstance(payload["rows"], list) or not all(
        isinstance(row, dict) for row in payload["rows"]
    ):
        raise OpenDProtocolError(f"{contract} payload rows must be mappings")
    return payload
