"""Read-only Moomoo/OpenD quote and history readiness checks.

The readiness boundary deliberately stops at market-data entitlement.  It
never opens a trade context, unlocks an account, or treats order capability as
evidence that a symbol can serve trusted research data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.market_data import MoomooDataAdapter, market_zone
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDCapabilities,
    OpenDError,
    OpenDProtocolError,
)

__all__ = ["ReadinessReport", "SymbolReadiness", "run_readiness"]


class ReadinessClient(Protocol):
    """The read-only portion of :class:`MoomooOpenDClient`."""

    def probe(self) -> OpenDCapabilities: ...

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

    capabilities = client.probe()
    adapter = MoomooDataAdapter()
    results = tuple(
        _probe_symbol(client, adapter, code, capabilities, interval) for code in codes
    )
    if all(symbol.status == "protocol_error" for symbol in results):
        status = "protocol_error"
    elif all(symbol.status == "ready" for symbol in results):
        status = "ready"
    elif any(symbol.status in {"ready", "partial"} for symbol in results):
        status = "partial"
    else:
        status = "unavailable"
    return ReadinessReport(
        status=status,
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

    statuses = {quote_status, history_status}
    if "protocol_error" in statuses:
        status = "protocol_error"
    elif quote_status == "ready" and history_status == "ready":
        status = "ready"
    elif "ready" in statuses:
        status = "partial"
    else:
        status = "unavailable"
    return SymbolReadiness(
        code=code,
        status=status,
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
        adapter.stock_quote_to_quote(instrument, payload)
    except OpenDProtocolError as error:
        return "protocol_error", str(error)
    except (OpenDError, NotImplementedError) as error:
        return "unavailable", _error_detail(error)
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
        bars = adapter.history_kline_to_bars(instrument, payload)
    except OpenDProtocolError as error:
        return "protocol_error", str(error), 0
    except (OpenDError, NotImplementedError) as error:
        return "unavailable", _error_detail(error), 0
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


def _error_detail(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"
