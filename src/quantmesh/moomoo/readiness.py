"""Read-only Moomoo/OpenD quote and history readiness checks.

The readiness boundary deliberately stops at market-data entitlement.  It
never opens a trade context, unlocks an account, or treats order capability as
evidence that a symbol can serve trusted research data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.market_data import MoomooDataAdapter, market_zone
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDError,
    OpenDProtocolError,
    OpenDSdkMissingError,
)

__all__ = ["ReadinessReport", "SymbolReadiness", "run_readiness"]


class ReadinessClient(Protocol):
    """The read-only portion of :class:`MoomooOpenDClient`."""

    def probe_market_data(self) -> OpenDCapabilities: ...

    def stock_quote(self, codes: list[str]) -> dict: ...

    def history_kline(
        self,
        code: str,
        *,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        autype: str = "None",
    ) -> dict: ...


@dataclass(frozen=True)
class SymbolReadiness:
    """Read-only status for one market-qualified symbol."""

    code: str
    status: str
    quote_status: str
    history_status: str
    quote_detail: str | None = None
    history_detail: str | None = None
    history_rows: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "status": self.status,
            "quote_status": self.quote_status,
            "history_status": self.history_status,
            "quote_detail": self.quote_detail,
            "history_detail": self.history_detail,
            "history_rows": self.history_rows,
        }


@dataclass(frozen=True)
class ReadinessReport:
    """A serializable report for the quote/history readiness gate."""

    status: str
    capabilities: OpenDCapabilities
    symbols: tuple[SymbolReadiness, ...]
    interval: str
    order_checked: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "interval": self.interval,
            "order_checked": self.order_checked,
            "capabilities": {
                "quote": self.capabilities.quote,
                "history_kline": self.capabilities.history_kline,
                "order": self.capabilities.order,
                "order_query": self.capabilities.order_query,
                "auth_required": self.capabilities.auth_required,
            },
            "symbols": [symbol.as_dict() for symbol in self.symbols],
        }


def run_readiness(
    client: ReadinessClient | MoomooOpenDClient,
    codes: list[str],
    *,
    interval: str = "1d",
) -> ReadinessReport:
    """Probe quote/history entitlement for every market-qualified ``code``.

    The client is probed exactly once.  Only its quote and historical-kline
    methods are called, and each symbol is classified independently so one
    entitlement failure does not hide another symbol's result.
    """

    if not codes:
        raise ValueError("codes must contain at least one market-qualified symbol")
    if not isinstance(interval, str) or not interval:
        raise ValueError("interval must be a non-empty string")

    interval_to_timedelta(interval)
    for code in codes:
        _instrument_for_code(code)
    capabilities = client.probe_market_data()
    adapter = MoomooDataAdapter()
    results = tuple(
        _probe_symbol(client, adapter, code, capabilities, interval) for code in codes
    )
    return ReadinessReport(
        status=_aggregate_status({symbol.status for symbol in results}),
        capabilities=capabilities,
        symbols=results,
        interval=interval,
    )


def _probe_symbol(
    client: ReadinessClient,
    adapter: MoomooDataAdapter,
    code: str,
    capabilities: OpenDCapabilities,
    interval: str,
) -> SymbolReadiness:
    instrument = _instrument_for_code(code)
    if capabilities.quote:
        quote_status, quote_detail = _probe_quote(client, adapter, instrument, code)
    else:
        quote_status, quote_detail = "skipped", "OpenD quote capability is disabled"
    if capabilities.history_kline:
        history_status, history_detail, history_rows = _probe_history(
            client, adapter, instrument, code, interval
        )
    else:
        history_status, history_detail, history_rows = (
            "skipped",
            "OpenD history_kline capability is disabled",
            0,
        )

    return SymbolReadiness(
        code=code,
        status=_aggregate_status({quote_status, history_status}),
        quote_status=quote_status,
        history_status=history_status,
        quote_detail=quote_detail,
        history_detail=history_detail,
        history_rows=history_rows,
    )


def _probe_quote(
    client: ReadinessClient,
    adapter: MoomooDataAdapter,
    instrument: Instrument,
    code: str,
) -> tuple[str, str | None]:
    try:
        payload = client.stock_quote([code])
        _assert_payload_code(payload, code)
        adapter.stock_quote_to_quote(instrument, payload)
    except (OpenDError, NotImplementedError) as error:
        return readiness_failure(error)
    return "ready", None


def _probe_history(
    client: ReadinessClient,
    adapter: MoomooDataAdapter,
    instrument: Instrument,
    code: str,
    interval: str,
) -> tuple[str, str | None, int]:
    try:
        payload = client.history_kline(code, interval=interval)
        _assert_payload_code(payload, code)
        if isinstance(payload, dict) and (
            payload.get("interval") != interval or payload.get("autype") != "None"
        ):
            raise OpenDProtocolError("history interval or adjustment differs from request")
        bars = adapter.history_kline_to_bars(instrument, payload)
    except (OpenDError, NotImplementedError) as error:
        status, detail = readiness_failure(error)
        return status, detail, 0
    if not bars:
        return "unavailable", "OpenD returned no history rows", 0
    return "ready", None, len(bars)


def _instrument_for_code(code: str) -> Instrument:
    if not isinstance(code, str):
        raise ValueError("codes must contain strings")
    market, separator, symbol = code.partition(".")
    if not separator or not market or not symbol:
        raise ValueError(f"code {code!r} must be market-qualified, e.g. 'US.AAPL'")
    try:
        market_zone(market)
    except ValueError as error:
        raise ValueError(str(error)) from error
    currency = {"US": "USD", "HK": "HKD", "CN": "CNY"}[market]
    return Instrument(
        symbol=symbol,
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency=currency,
        metadata={"market": market},
    )


def _assert_payload_code(payload: object, code: str) -> None:
    """Reject a valid-looking response that belongs to another market."""
    if not isinstance(payload, dict):
        return
    top_code = payload.get("code")
    if top_code is not None and top_code != code:
        raise OpenDProtocolError(
            f"payload code {top_code!r} does not match requested code {code!r}"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows):
        if isinstance(row, dict) and row.get("code") is not None and row["code"] != code:
            raise OpenDProtocolError(
                f"payload row {index} code {row['code']!r} does not match requested code {code!r}"
            )


def readiness_failure(error: Exception) -> tuple[str, str]:
    """Allowlisted operator diagnostics; never serialize vendor/payload text."""
    if isinstance(error, OpenDProtocolError):
        return "protocol_error", "OpenD returned an invalid or mismatched market-data payload"
    if isinstance(error, OpenDSdkMissingError):
        return "sdk_missing", "An audited compatible Moomoo SDK is required"
    if isinstance(error, OpenDAuthRequiredError):
        return "auth_required", "OpenD rejected market-data authentication; no unlock attempted"
    return "unavailable", "OpenD market data unavailable; check connection, subscription and rights"


def _aggregate_status(statuses: set[str]) -> str:
    # Typed failures must survive even if another symbol/surface succeeds.
    for failure in ("protocol_error", "sdk_missing", "auth_required"):
        if failure in statuses:
            return failure
    if statuses == {"ready"}:
        return "ready"
    if statuses & {"ready", "partial"}:
        return "partial"
    return "unavailable"
