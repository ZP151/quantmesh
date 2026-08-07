"""Moomoo (equity) fixture adapter (issue #17).

Serves bundled fixture payloads shaped like Moomoo's wire format
(``symbol``/``interval``/``datetime`` keys) and normalizes them into
canonical domain models. Equity fixtures are symbol-scoped: requesting a
symbol the fixture does not cover fails closed instead of returning an
empty series that would look like "no data".
"""

from datetime import datetime

from quantmesh.data.providers.base import FixtureProvider
from quantmesh.domain.market_data import Bar, DepthLevel, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, Venue


class MoomooFixtureProvider(FixtureProvider):
    """Moomoo adapter serving bundled fixture payloads (M3)."""

    venue = Venue.MOOMOO

    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        self._require_venue(instrument)
        rows = self._load_rows("moomoo_bars.json")

        def parse(row: dict) -> Bar:
            if row["symbol"] != instrument.symbol:
                raise ValueError(f"fixture covers {row['symbol']}, requested {instrument.symbol!r}")
            if row["interval"] != interval:
                raise ValueError(f"fixture provides {row['interval']} bars, requested {interval!r}")
            return Bar(
                instrument=instrument,
                timestamp=self._utc(row["datetime"]),
                interval=interval,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

        return self._filtered(self._map_rows("moomoo_bars.json", rows, parse), start, end)

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        rows = self._load_rows("moomoo_books.json")

        def parse(row: dict) -> OrderBook:
            if row["symbol"] != instrument.symbol:
                raise ValueError(f"fixture covers {row['symbol']}, requested {instrument.symbol!r}")
            return OrderBook(
                instrument=instrument,
                timestamp=self._utc(row["datetime"]),
                bids=[
                    DepthLevel(price=level[0], quantity=level[1])
                    for level in row["bid_levels"]
                ],
                asks=[
                    DepthLevel(price=level[0], quantity=level[1])
                    for level in row["ask_levels"]
                ],
            )

        return self._filtered(self._map_rows("moomoo_books.json", rows, parse), start, end)

    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        self._require_venue(instrument)
        rows = self._load_rows("moomoo_trades.json")

        def parse(row: dict) -> TradeEvent:
            if row["symbol"] != instrument.symbol:
                raise ValueError(f"fixture covers {row['symbol']}, requested {instrument.symbol!r}")
            return TradeEvent(
                instrument=instrument,
                timestamp=self._utc(row["datetime"]),
                price=row["price"],
                quantity=row["quantity"],
                aggressor_side=self._side(row["side"]),
                venue_sequence=row["seq"],
            )

        return self._filtered(self._map_rows("moomoo_trades.json", rows, parse), start, end)
