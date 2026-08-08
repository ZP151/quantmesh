"""Kalshi data adapter and providers (M6, issue #35, Phase B).

``KalshiMarketDataAdapter`` is the pure wire→domain mapping (no I/O):
event bundles → ``EventMarket``, orderbook + market object →
``MarketQuote``/``OrderBook``, trades → ``TradeEvent``, candlesticks →
``Bar``. Unlike Polymarket, Kalshi's candlesticks report volume, so
this adapter serves a genuine bar surface, and the venue reports last
trade prices and resolution state inline in the market object.

``KalshiFixtureProvider`` serves the recorded wire fixtures through
the real parsers (a fixture failure is a parser failure) and registers
in the M3 registry (``mode = FIXTURE``). ``KalshiLiveProvider`` is
explicit-construction-only with ``ProviderMode.LIVE`` and an injected
keyless transport; the registry refuses it. No credentials, no order
path, no signing surface exists anywhere in this package.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantmesh.data.providers.base import FixtureProvider, Provider, ProviderMode
from quantmesh.domain.market_data import Bar, DepthLevel, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, Side, Venue
from quantmesh.events.models import EventMarket, EventVenue, MarketQuote, Outcome, ResolutionRule
from quantmesh.kalshi.errors import KalshiProtocolError
from quantmesh.kalshi.transport import KalshiRestTransport
from quantmesh.kalshi.wire import (
    KalshiMarket,
    KalshiMarketStatus,
    parse_candlesticks,
    parse_events,
    parse_market,
    parse_markets,
    parse_orderbook,
    parse_trades,
)

__all__ = [
    "KalshiMarketDataAdapter",
    "KalshiFixtureProvider",
    "KalshiLiveProvider",
    "FIXTURE_DIR",
    "INTERVAL_TO_PERIOD",
]

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# The venue's candlestick periods (minutes) per canonical M3 interval.
INTERVAL_TO_PERIOD = {"1m": 1, "1h": 60, "1d": 1440}

_RESOLVED_STATUSES = (KalshiMarketStatus.SETTLED, KalshiMarketStatus.FINALIZED)
_RESULT_TO_OUTCOME = {"yes": "Yes", "no": "No"}


class KalshiMarketDataAdapter:
    """Pure wire→domain mapping; no I/O, deterministic."""

    # -- event markets ---------------------------------------------------------

    def events(
        self,
        markets_payload: object,
        *,
        event_title: str | None = None,
        category: str | None = None,
    ) -> list[EventMarket]:
        """A markets list → canonical event markets.

        Kalshi reports resolution inline: a settled/finalized market
        with a ``result`` carries its resolution here (unlike
        Polymarket, where resolution enters only through the CLOB
        winner flags). Non-binary markets are refused — Phase C
        probabilities are binary-payoff.
        """
        return [
            self._event_market(market, event_title=event_title, category=category)
            for market in parse_markets(markets_payload)
        ]

    def market(
        self, market_payload: object, *, event_title: str | None = None
    ) -> EventMarket:
        return self._event_market(
            parse_market(market_payload), event_title=event_title, category=None
        )

    @staticmethod
    def _event_market(
        market: KalshiMarket, *, event_title: str | None, category: str | None
    ) -> EventMarket:
        if market.market_type != "binary":
            raise KalshiProtocolError(
                f"market {market.ticker}: only binary markets normalize into "
                f"EventMarket, got {market.market_type!r}"
            )
        rule_text = market.rules_primary.strip() or (event_title or "").strip()
        if not rule_text:
            raise KalshiProtocolError(
                f"market {market.ticker}: no resolution rule text (rules_primary "
                "empty and no event title fallback) to fingerprint"
            )
        resolution = []
        resolved_at = None
        if market.status in _RESOLVED_STATUSES:
            outcome = _RESULT_TO_OUTCOME.get(market.result)
            if outcome is not None:
                resolution = [outcome]
                resolved_at = market.settlement_ts
        return EventMarket(
            venue=EventVenue.KALSHI,
            venue_market_id=market.ticker,
            event_ticker=market.event_ticker,
            title=market.title,
            category=category,
            start_at=market.open_time,
            expiry_at=market.expiration_time,
            outcomes=[
                Outcome(name="Yes", venue_outcome_id="yes"),
                Outcome(name="No", venue_outcome_id="no"),
            ],
            resolution_rule=ResolutionRule.of(rule_text),
            resolution=resolution,
            resolved_at=resolved_at,
        )

    def resolution(self, market_payload: object) -> list[str]:
        """The market object's resolved outcome names (venue-reported)."""
        market = parse_market(market_payload)
        if market.status not in _RESOLVED_STATUSES:
            return []
        outcome = _RESULT_TO_OUTCOME.get(market.result)
        return [outcome] if outcome else []

    # -- quotes and books ------------------------------------------------------

    def market_quote(
        self, book_payload: object, market_payload: object, *, ticker: str
    ) -> MarketQuote:
        """Orderbook + market object → one canonical quote for ``ticker``.

        Best levels are extracted order-agnostically (max of each
        ladder): the recorded wire lists both bid ladders ascending
        worst-first, contradicting the docs' "best to worst" claim.
        The best YES ask is derived from the best NO bid (the docs'
        own rule: a NO bid at price y implies a YES ask at 1 - y).
        The venue reports last trade and its own bid/ask directly;
        the market object's ``updated_time`` is the quote timestamp.
        """
        book = parse_orderbook(book_payload)
        market = parse_market(market_payload)
        if market.ticker != ticker:
            raise KalshiProtocolError(
                f"market ticker {market.ticker!r} does not match requested ticker {ticker!r}"
            )
        if market.updated_time is None:
            raise KalshiProtocolError(
                f"market {ticker}: no updated_time to timestamp the quote"
            )
        if not market.price_ranges:
            raise KalshiProtocolError(f"market {ticker}: no price_ranges for the tick size")
        yes_bids = [level.price for level in book.yes_dollars]
        no_bids = [level.price for level in book.no_dollars]
        return MarketQuote(
            venue=EventVenue.KALSHI,
            symbol=ticker,
            timestamp=market.updated_time,
            best_bid=max(yes_bids) if yes_bids else None,
            best_ask=(1.0 - max(no_bids)) if no_bids else None,
            last_trade_price=market.last_price_dollars,  # the venue reports it
            bid_depth=sum(level.size for level in book.yes_dollars),
            ask_depth=sum(level.size for level in book.no_dollars),
            tick_size=market.price_ranges[0].step,
            min_order_size=None,  # not reported by the wire contract
            taker_fee_bps=0.0,  # no bps fee surface; the series fee is
            # quadratic (fee_type/fee_multiplier) — Phase C interprets it
        )

    def order_book(
        self, book_payload: object, market_payload: object, instrument: Instrument
    ) -> OrderBook:
        """Orderbook + market object → canonical M3 ``OrderBook``.

        Bids are the ``yes_dollars`` ladder reversed to best-first;
        asks are the ``no_dollars`` ladder's mirror image (1 - price,
        same count) reversed to best-first. A derived ask at or below
        zero (a NO bid at $1.00) carries no tradeable depth and is
        skipped; anything else must satisfy the canonical strict
        ordering. The market's ``updated_time`` timestamps the book.
        """
        book = parse_orderbook(book_payload)
        market = parse_market(market_payload)
        if market.ticker != instrument.symbol:
            raise KalshiProtocolError(
                f"market ticker {market.ticker!r} does not match instrument {instrument.symbol!r}"
            )
        if market.updated_time is None:
            raise KalshiProtocolError(
                f"market {instrument.symbol}: no updated_time to timestamp the book"
            )
        bids = [
            DepthLevel(price=level.price, quantity=level.size)
            for level in reversed(book.yes_dollars)
        ]
        asks = [
            DepthLevel(price=1.0 - level.price, quantity=level.size)
            for level in reversed(book.no_dollars)
            if 1.0 - level.price > 0.0
        ]
        return OrderBook(
            instrument=instrument,
            timestamp=market.updated_time,
            bids=bids,
            asks=asks,
        )

    # -- trades ----------------------------------------------------------------

    def trades(self, payload: object, instrument: Instrument) -> list[TradeEvent]:
        """``/markets/trades`` → canonical trades.

        The taker's side names the outcome they bought; buying YES is
        a buy of the contract, buying NO is a sell. Price is the
        taker side's complementary price; size is ``count_fp``.
        """
        trades = []
        for wire in parse_trades(payload):
            if wire.ticker != instrument.symbol:
                raise KalshiProtocolError(
                    f"trade ticker {wire.ticker!r} does not match instrument {instrument.symbol!r}"
                )
            trades.append(
                TradeEvent(
                    instrument=instrument,
                    timestamp=wire.created_time,
                    price=(
                        wire.yes_price_dollars
                        if wire.taker_side == "yes"
                        else wire.no_price_dollars
                    ),
                    quantity=wire.count_fp,
                    aggressor_side=Side.BUY if wire.taker_side == "yes" else Side.SELL,
                    venue_sequence=None,  # trade_id is a uuid, not a sequence
                )
            )
        return trades

    # -- bars ------------------------------------------------------------------

    def bars(self, payload: object, instrument: Instrument, *, interval: str) -> list[Bar]:
        """Candlesticks → canonical M3 bars (bar-open timestamps).

        Kalshi reports volume, so this is a genuine bar surface
        (ADR-0008 decision 4). Only traded periods produce bars: a
        zero-volume row's ``price`` carries no period OHLC (just the
        previous close), so fabricating one from the bid/ask series
        would invent data — the period simply has no bar. A traded
        row's OHLC is the venue's own trade-price bar, re-based from
        the period END to the M3 bar-open convention.
        """
        period_minutes = INTERVAL_TO_PERIOD.get(interval)
        if period_minutes is None:
            raise ValueError(
                f"unsupported interval {interval!r} (Kalshi serves 1m/1h/1d candlesticks)"
            )
        bars = []
        for candle in parse_candlesticks(payload):
            if candle.volume_fp <= 0:
                continue
            price = candle.price
            if price.open_dollars is None:
                # The parser enforces this; the guard keeps the mapping
                # fail-closed even if a future parser path weakens.
                raise KalshiProtocolError(
                    f"traded candlestick at {candle.end_period_ts.isoformat()} "
                    "has no trade OHLC"
                )
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=candle.end_period_ts - timedelta(minutes=period_minutes),
                    interval=interval,
                    open=price.open_dollars,
                    high=price.high_dollars,
                    low=price.low_dollars,
                    close=price.close_dollars,
                    volume=candle.volume_fp,
                )
            )
        return bars

    # -- market summaries (canonical listing surface) --------------------------

    def market_summaries(self, markets_payload: object) -> list[dict]:
        """Compact venue-neutral market listings (canonical fixture rows)."""
        rows = []
        for market in parse_markets(markets_payload):
            rows.append(
                {
                    "ticker": market.ticker,
                    "event_ticker": market.event_ticker,
                    "title": market.title,
                    "status": market.status.value,
                    "market_type": market.market_type,
                    "result": market.result,
                    "expiry_at": market.expiration_time.isoformat(),
                    "last_price": market.last_price_dollars,
                    "volume": market.volume_fp,
                    "open_interest": market.open_interest_fp,
                }
            )
        return rows


class KalshiFixtureProvider(FixtureProvider):
    """Fixture provider serving the recorded wire payloads through the
    real parsers (``fixture_dir`` injectable, default the package's
    ``fixtures/``). Registry-registerable: ``mode`` is FIXTURE and the
    M3 gate holds."""

    venue = Venue.KALSHI
    mode = ProviderMode.FIXTURE

    def __init__(self, fixture_dir: Path | None = None) -> None:
        super().__init__(fixture_dir or FIXTURE_DIR)
        self.adapter = KalshiMarketDataAdapter()

    def _load_payload(self, name: str) -> object:
        path = self._fixture_dir / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"fixture {path} is unreadable or invalid: {error}") from error
        return payload

    def _mars_bundle(self) -> tuple[object, object]:
        bundle = self._load_payload("event_mars.json")
        return bundle["event"], bundle["markets"]

    def events(self) -> list[EventMarket]:
        """The recorded discovery capture through the real parsers:
        the Mars event (1 active market), the Fed event (1 liquid
        market) and the settled cross-category market (resolved No)."""
        mars_event, mars_markets = self._mars_bundle()
        markets = [
            self.adapter._event_market(
                market, event_title=mars_event["title"], category=mars_event["category"]
            )
            for market in parse_markets({"markets": mars_markets})
        ]
        settled = self._load_payload("event_settled.json")
        markets.extend(
            self.adapter.events(
                {"markets": settled["markets"]},
                event_title=settled["event"]["title"],
                category=settled["event"]["category"],
            )
        )
        fed_event = parse_events(self._load_payload("events_fed.json"))[0]
        fed_market = self._load_payload("market_fed.json")
        markets.append(
            self.adapter.market(fed_market, event_title=fed_event.title)
        )
        return markets

    def resolution(self) -> list[str]:
        """The fixture settled market's resolution (venue-reported)."""
        return self.adapter.resolution(self._load_payload("market_settled.json"))

    def market_quote(self, ticker: str) -> MarketQuote:
        """The fixture quote for ``ticker`` (must be the recorded one)."""
        return self.adapter.market_quote(
            self._load_payload("orderbook.json"),
            self._load_payload("market_fed.json"),
            ticker=ticker,
        )

    def market_summaries(self) -> list[dict]:
        """Compact market listings for the canonical fixture: the Mars
        market, the Fed market and the settled market."""
        mars_event, mars_markets = self._mars_bundle()
        rows = self.adapter.market_summaries({"markets": mars_markets})
        rows.extend(
            self.adapter.market_summaries(
                {"markets": [self._load_payload("market_fed.json")["market"]]}
            )
        )
        rows.extend(
            self.adapter.market_summaries(
                {"markets": [self._load_payload("market_settled.json")["market"]]}
            )
        )
        return rows

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        books = [
            self.adapter.order_book(
                self._load_payload("orderbook.json"),
                self._load_payload("market_fed.json"),
                instrument,
            )
        ]
        return self._filtered(books, start, end)

    def fetch_trades(self, instrument: Instrument, *, start=None, end=None) -> list[TradeEvent]:
        self._require_venue(instrument)
        trades = self.adapter.trades(self._load_payload("trades.json"), instrument)
        return self._filtered(trades, start, end)

    def fetch_bars(
        self, instrument: Instrument, *, interval: str, start=None, end=None
    ) -> list[Bar]:
        self._require_venue(instrument)
        if interval != "1h":
            raise ValueError(
                f"the recorded Kalshi candles fixture is 1h; cannot serve {interval!r}"
            )
        bars = self.adapter.bars(self._load_payload("candles.json"), instrument, interval=interval)
        return self._filtered(bars, start, end)


class KalshiLiveProvider(Provider):
    """Live provider over an injected keyless transport; explicit
    construction only. ``mode`` is LIVE and the registry refuses LIVE
    venues (M3 gate), so this class is reachable only by deliberate
    construction. Everything it can do is public read-only data; no
    order path exists."""

    venue = Venue.KALSHI
    mode = ProviderMode.LIVE

    def __init__(self, transport: KalshiRestTransport) -> None:
        self.transport = transport
        self.adapter = KalshiMarketDataAdapter()

    def events(self, *, limit: int, offset: int = 0) -> list[EventMarket]:
        """Bounded discovery: one events page, then each event's markets."""
        if limit <= 0:
            raise ValueError("live Kalshi discovery needs a positive limit")
        result: list[EventMarket] = []
        for event in parse_events(self.transport.events(limit=limit, offset=offset)):
            payload = self.transport.markets(event_ticker=event.event_ticker, limit=limit)
            result.extend(
                self.adapter.events(payload, event_title=event.title, category=event.category)
            )
        return result

    def market_quote(self, ticker: str) -> MarketQuote:
        """One quote: orderbook + market object by ticker."""
        return self.adapter.market_quote(
            self.transport.orderbook(ticker),
            self.transport.market(ticker),
            ticker=ticker,
        )

    def resolution(self, ticker: str) -> list[str]:
        """The live market object's venue-reported resolution."""
        return self.adapter.resolution(self.transport.market(ticker))

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        return [
            self.adapter.order_book(
                self.transport.orderbook(instrument.symbol),
                self.transport.market(instrument.symbol),
                instrument,
            )
        ]

    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        """Bounded trades: an explicit aware range is mandatory (the
        bounded-surface discipline, parity with live history paths)."""
        self._require_venue(instrument)
        if start is None or end is None:
            raise ValueError("live Kalshi trades need an explicit aware start and end")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("live Kalshi trades need timezone-aware bounds")
        if start >= end:
            raise ValueError("live Kalshi trades need start before end")
        payload = self.transport.trades(
            instrument.symbol,
            start_ts=int(start.astimezone(UTC).timestamp()),
            end_ts=int(end.astimezone(UTC).timestamp()),
        )
        return self.adapter.trades(payload, instrument)

    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        """Bounded bars over the candlestick surface.

        The bar route needs the series ticker, which the market
        object does not carry — it is resolved through the market's
        event (market → event → series), two public read-only calls,
        then the bounded candlestick range.
        """
        self._require_venue(instrument)
        if interval not in INTERVAL_TO_PERIOD:
            raise ValueError(
                f"unsupported interval {interval!r} (Kalshi serves 1m/1h/1d candlesticks)"
            )
        if start is None or end is None:
            raise ValueError("live Kalshi bars need an explicit aware start and end")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("live Kalshi bars need timezone-aware bounds")
        if start >= end:
            raise ValueError("live Kalshi bars need start before end")
        market = parse_market(self.transport.market(instrument.symbol))
        event = self.transport.event(market.event_ticker)
        series_ticker = parse_events({"events": [event["event"]]})[0].series_ticker
        payload = self.transport.candlesticks(
            instrument.symbol,
            series_ticker=series_ticker,
            start_ts=int(start.astimezone(UTC).timestamp()),
            end_ts=int(end.astimezone(UTC).timestamp()),
            period_interval=INTERVAL_TO_PERIOD[interval],
        )
        return self.adapter.bars(payload, instrument, interval=interval)
