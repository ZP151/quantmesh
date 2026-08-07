"""Hyperliquid market-data adapter and providers (M5, issue #29, Phase A).

``HyperliquidDataAdapter`` is the pure payload→model mapping: SDK wire
shapes in, canonical domain models out (``Bar``/``OrderBook``/
``TradeEvent``), every row through the fail-closed parsers in ``wire``.

``HyperliquidFixtureProvider`` serves bundled wire-shaped fixtures (the
SDK's native JSON, not hand-canonicalized rows) through the real
parsers, so a fixture failure is a parser failure.

``HyperliquidLiveProvider`` is explicit-construction-only with
``ProviderMode.LIVE`` and an injected REST transport; the registry
refuses LIVE venues (M3 gate, tested), so it is reachable only by an
explicit construction. Public trades have no REST endpoint on
Hyperliquid — the live provider fails closed rather than pretending.
"""

import json
from datetime import datetime
from pathlib import Path

from quantmesh.data.providers.base import FixtureProvider, Provider, ProviderMode
from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.rest import RestTransport
from quantmesh.hyperliquid.wire import (
    FundingRate,
    parse_candle,
    parse_funding,
    parse_l2_book,
    parse_trades,
)

__all__ = [
    "HyperliquidDataAdapter",
    "HyperliquidFixtureProvider",
    "HyperliquidLiveProvider",
    "FIXTURE_DIR",
]

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class HyperliquidDataAdapter:
    """Pure wire→domain mapping; no I/O, no SDK, deterministic."""

    def bars(self, payload: list[dict], instrument: Instrument, *, interval: str) -> list[Bar]:
        return [parse_candle(row, instrument, interval=interval) for row in payload]

    def order_book(self, payload: dict, instrument: Instrument) -> OrderBook:
        return parse_l2_book(payload, instrument)

    def trades(self, payload: list[dict], instrument: Instrument) -> list[TradeEvent]:
        return parse_trades(payload, instrument)

    def funding(self, payload: list[dict]) -> list[FundingRate]:
        return parse_funding(payload)


class HyperliquidFixtureProvider(FixtureProvider):
    """Fixture provider serving wire-shaped payloads through the real parsers.

    ``fixture_dir`` is injectable; the default is the package's
    ``fixtures/`` directory (M5 wire shapes, distinct from the M3
    canonical-shaped fixtures under ``data/providers/fixtures``).
    """

    venue = Venue.HYPERLIQUID
    mode = ProviderMode.FIXTURE

    def __init__(self, fixture_dir: Path | None = None) -> None:
        super().__init__(fixture_dir or FIXTURE_DIR)
        self.adapter = HyperliquidDataAdapter()

    def _load_rows(self, name: str) -> list[dict]:
        path = self._fixture_dir / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"fixture {path} is unreadable or invalid: {error}") from error
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"fixture {path} has no rows")
        return payload

    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        self._require_venue(instrument)
        bars = self.adapter.bars(
            self._load_rows("wire_candles.json"), instrument, interval=interval
        )
        return self._filtered(bars, start, end)

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        path = self._fixture_dir / "wire_l2book.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"fixture {path} is unreadable or invalid: {error}") from error
        books = [self.adapter.order_book(payload, instrument)]
        return self._filtered(books, start, end)

    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        self._require_venue(instrument)
        trades = self.adapter.trades(self._load_rows("wire_trades.json"), instrument)
        return self._filtered(trades, start, end)

    def funding(self, instrument: Instrument) -> list[FundingRate]:
        self._require_venue(instrument)
        return self.adapter.funding(self._load_rows("wire_funding.json"))


class HyperliquidLiveProvider(Provider):
    """Live provider over an injected REST transport; explicit construction only.

    ``mode`` is LIVE and the registry refuses LIVE venues (M3 gate), so
    this class is reachable only by deliberate construction — the M4
    explicit-construction-only discipline. Trades have no public REST
    endpoint on Hyperliquid and fail closed instead of fabricating.
    """

    venue = Venue.HYPERLIQUID
    mode = ProviderMode.LIVE

    def __init__(self, transport: RestTransport) -> None:
        self.transport = transport
        self.adapter = HyperliquidDataAdapter()

    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        self._require_venue(instrument)
        if start is None or end is None:
            raise ValueError(
                "live Hyperliquid bars need explicit start and end (bounded ranges only)"
            )
        rows = self.transport.candles(
            instrument.symbol, interval, start=start, end=end
        )
        return self.adapter.bars(rows, instrument, interval=interval)

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        payload = self.transport.l2_book(instrument.symbol)
        return [self.adapter.order_book(payload, instrument)]

    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        self._require_venue(instrument)
        raise HyperliquidProtocolError(
            "Hyperliquid exposes no public trades REST endpoint; use the stream"
        )

    def funding_history(
        self, instrument: Instrument, *, start: datetime, end: datetime
    ) -> list[FundingRate]:
        self._require_venue(instrument)
        rows = self.transport.funding_history(instrument.symbol, start=start, end=end)
        return self.adapter.funding(rows)
