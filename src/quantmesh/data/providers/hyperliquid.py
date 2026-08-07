"""Hyperliquid fixture adapter (issue #17).

Serves bundled fixture payloads shaped like Hyperliquid's wire format
(``t``/``o``/``h``/``l``/``c``/``v``/``i`` for bars, ``px``/``sz``/
``seq`` for trades) and normalizes them into canonical domain models.
"""

from datetime import datetime

from quantmesh.data.providers.base import FixtureProvider
from quantmesh.domain.market_data import Bar, DepthLevel, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, Venue


class HyperliquidFixtureProvider(FixtureProvider):
    """Hyperliquid adapter serving bundled fixture payloads (M3)."""

    venue = Venue.HYPERLIQUID

    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        self._require_venue(instrument)
        rows = self._load_rows("hyperliquid_bars.json")

        def parse(row: dict) -> Bar:
            if row["i"] != interval:
                raise ValueError(f"fixture provides {row['i']} bars, requested {interval!r}")
            return Bar(
                instrument=instrument,
                timestamp=self._utc(row["t"]),
                interval=interval,
                open=row["o"],
                high=row["h"],
                low=row["l"],
                close=row["c"],
                volume=row["v"],
            )

        return self._filtered(self._map_rows("hyperliquid_bars.json", rows, parse), start, end)

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        rows = self._load_rows("hyperliquid_books.json")

        def parse(row: dict) -> OrderBook:
            return OrderBook(
                instrument=instrument,
                timestamp=self._utc(row["ts"]),
                bids=[DepthLevel(price=level[0], quantity=level[1]) for level in row["bids"]],
                asks=[DepthLevel(price=level[0], quantity=level[1]) for level in row["asks"]],
            )

        return self._filtered(self._map_rows("hyperliquid_books.json", rows, parse), start, end)

    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        self._require_venue(instrument)
        rows = self._load_rows("hyperliquid_trades.json")

        def parse(row: dict) -> TradeEvent:
            return TradeEvent(
                instrument=instrument,
                timestamp=self._utc(row["t"]),
                price=row["px"],
                quantity=row["sz"],
                aggressor_side=self._side(row["side"]),
                venue_sequence=row["seq"],
            )

        return self._filtered(self._map_rows("hyperliquid_trades.json", rows, parse), start, end)
