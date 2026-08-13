"""Moomoo OpenD provider: client + adapter as the canonical Provider surface (issue #26, Phase B).

Explicit construction only. ``ProviderMode.LIVE`` means the fixture-only
``ProviderRegistry`` refuses this provider (AGENTS.md), so no registered
or default path can reach OpenD: an operator constructs it by hand with
the transport they chose — a fixture stub in tests, ``SdkTransport`` in
an operator script. With a wire fixture transport the provider serves
canonical ``Bar``/``TradeEvent`` models, and those land in the lake
through the M3 machinery, which is exactly the Phase B acceptance:
fixture data through Lake, manifests and quality gates before any live
OpenD read.
"""

from dataclasses import dataclass
from datetime import datetime

from quantmesh.data.providers.base import Provider, ProviderMode
from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, Venue
from quantmesh.moomoo.market_data import MoomooDataAdapter, market_tz, sdk_code
from quantmesh.moomoo.opend import MoomooOpenDClient, OpenDProtocolError

# Raw (unadjusted) prices are the Phase B default; anything else must be
# an explicit request.
_DEFAULT_AUTYPE = "None"


@dataclass(frozen=True)
class MoomooRawBundle:
    """Unadjusted bars plus strict-JSON read-only source payloads."""

    bars: tuple[Bar, ...]
    history_pages: tuple[dict, ...]
    adjustment_factors: dict
    stock_split_pages: tuple[dict, ...]
    dividends: dict


class MoomooOpenDProvider(Provider):
    """Canonical Provider surface over a MoomooOpenDClient (Phase B)."""

    venue = Venue.MOOMOO
    mode = ProviderMode.LIVE  # never registered; explicit construction only

    def __init__(self, client: MoomooOpenDClient, adapter: MoomooDataAdapter | None = None) -> None:
        self._client = client
        self._adapter = adapter if adapter is not None else MoomooDataAdapter()

    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        _require_aware(start, "start")
        _require_aware(end, "end")
        pages = self._history_pages(instrument, interval=interval, start=start, end=end)
        return [
            bar
            for bar in self._adapter.history_pages_to_bars(instrument, pages)
            if _within(bar.timestamp, start, end)
        ]

    def fetch_raw_bundle(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MoomooRawBundle:
        """Fetch unadjusted pages and source actions without deriving adjustments."""
        _require_aware(start, "start")
        _require_aware(end, "end")
        code = sdk_code(instrument)
        pages = self._history_pages(instrument, interval=interval, start=start, end=end)
        if any(page.get("_legacy_single_page") is True for page in pages):
            raise OpenDProtocolError(
                "legacy single-page history cannot qualify as a complete raw bundle"
            )
        bars = tuple(
            bar
            for bar in self._adapter.history_pages_to_bars(instrument, pages)
            if _within(bar.timestamp, start, end)
        )
        return MoomooRawBundle(
            bars=bars,
            history_pages=tuple(pages),
            adjustment_factors=self._client.adjustment_factors(code),
            stock_split_pages=tuple(self._client.stock_splits(code)),
            dividends=self._client.dividends(code),
        )

    def _history_pages(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None,
        end: datetime | None,
    ) -> list[dict]:
        _require_aware(start, "start")
        _require_aware(end, "end")
        if start is not None and end is not None and start > end:
            raise ValueError("start must not be after end")
        code = sdk_code(instrument)
        tz = market_tz(code)
        return self._client.history_pages(
            code,
            interval=interval,
            start=_iso_date(start, tz),
            end=_iso_date(end, tz),
            autype=_DEFAULT_AUTYPE,
        )

    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        _require_aware(start, "start")
        _require_aware(end, "end")
        code = sdk_code(instrument)
        payload = self._client.rt_ticker(code)
        return [
            trade
            for trade in self._adapter.ticker_to_trades(instrument, payload)
            if _within(trade.timestamp, start, end)
        ]

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        raise NotImplementedError(
            "OpenD order books are out of scope for Phase B (issue #26); "
            "execution reconciliation is Phase D"
        )

    def close(self) -> None:
        self._client.close()


def _require_aware(timestamp: datetime | None, name: str) -> None:
    if timestamp is not None and timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _within(timestamp: datetime, start: datetime | None, end: datetime | None) -> bool:
    """Inclusive range membership, matching the lake's range semantics."""
    if start is not None and timestamp < start:
        return False
    if end is not None and timestamp > end:
        return False
    return True


def _iso_date(value: datetime | None, tz) -> str | None:
    """SDK date bounds are venue-local dates; convert UTC instants.

    The returned bars are still filtered by the caller's UTC range, so a
    window that starts before the venue date boundary only widens the
    request, never the result.
    """
    if value is None:
        return None
    return value.astimezone(tz).date().isoformat()
