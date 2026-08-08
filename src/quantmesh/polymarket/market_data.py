"""Polymarket data adapter and providers (M6, issue #34, Phase A).

``PolyMarketDataAdapter`` is the pure wire→domain mapping (no I/O, no
SDK): Gamma discovery → ``EventMarket``, CLOB book + market object →
``MarketQuote``/``OrderBook``, prices-history → ``PricePoint``.

``PolyFixtureProvider`` serves the recorded wire fixtures through the
real parsers (a fixture failure is a parser failure) and registers in
the M3 registry (``mode = FIXTURE``). Polymarket has no public bar
surface and no public trades-history surface on the pinned contract,
so ``fetch_bars``/``fetch_trades`` fail closed instead of fabricating
bars from the price series or trades from nothing — exactly the
Hyperliquid trades precedent.

``PolyLiveProvider`` is explicit-construction-only with
``ProviderMode.LIVE`` and an injected keyless transport; the registry
refuses it, and its only reachable surface is public read-only data.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.data.providers.base import FixtureProvider, Provider, ProviderMode
from quantmesh.domain.market_data import DepthLevel, OrderBook
from quantmesh.domain.models import Instrument, Venue
from quantmesh.events.models import EventMarket, EventVenue, MarketQuote, Outcome, ResolutionRule
from quantmesh.polymarket.errors import PolymarketProtocolError
from quantmesh.polymarket.transport import PolyRestTransport
from quantmesh.polymarket.wire import (
    PricePoint,
    parse_clob_book,
    parse_clob_market,
    parse_gamma_events,
    parse_prices_history,
)

__all__ = [
    "PolyMarketDataAdapter",
    "PolyFixtureProvider",
    "PolyLiveProvider",
    "FIXTURE_DIR",
]

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class PolyMarketDataAdapter:
    """Pure wire→domain mapping; no I/O, no SDK, deterministic."""

    # -- discovery -------------------------------------------------------------

    def events(self, payload: object) -> list[EventMarket]:
        """Gamma discovery → canonical event markets.

        Only deployed markets enter the result: a Gamma market whose
        ``clobTokenIds`` are empty is pre-deployment (no quoteable
        tokens) and is skipped — the parsers still surface it, the
        adapter filters it. Resolution is deliberately left empty
        here: Gamma carries no winner flag, and resolution enters only
        through the CLOB market object's ``tokens[].winner`` flags
        (``resolution()``), the venue's authoritative resolution state.
        """
        result: list[EventMarket] = []
        for gamma_event in parse_gamma_events(payload):
            for market in gamma_event.markets:
                if not market.clob_token_ids:
                    continue
                outcomes = [
                    Outcome(name=name, venue_outcome_id=token_id)
                    for name, token_id in zip(market.outcomes, market.clob_token_ids, strict=True)
                ]
                result.append(
                    EventMarket(
                        venue=EventVenue.POLYMARKET,
                        venue_market_id=market.condition_id,
                        event_ticker=gamma_event.ticker,
                        title=market.question,
                        category=gamma_event.category,
                        start_at=gamma_event.start_date,
                        expiry_at=market.end_date or gamma_event.end_date,
                        outcomes=outcomes,
                        resolution_rule=ResolutionRule.of(self._rule_text(market, gamma_event)),
                    )
                )
        return result

    @staticmethod
    def _rule_text(market, gamma_event) -> str:
        """The resolution-rule text for ONE market: its own description,
        else the event title — the last honest fallback (never an empty
        fingerprint). Per-market: a multi-market event may state a
        different rule per market, and cross-assigning the first
        market's rule would mislabel the others."""
        if market.description:
            return market.description
        if gamma_event.title:
            return gamma_event.title
        raise PolymarketProtocolError("Gamma event has no rule text to fingerprint")

    # -- CLOB resolution -------------------------------------------------------

    def resolution(self, market_payload: object) -> list[str]:
        """Resolved outcome names from the CLOB market's winner flags.

        Zero winners = unresolved; multiple winners is a genuine split
        resolution (Polymarket 50/50) and is reported as the full list,
        never flattened. Retired markets 404 on this endpoint (recorded
        live) — those raise ``PolymarketProtocolError`` at the parser.
        """
        market = parse_clob_market(market_payload)
        return [token.outcome for token in market.tokens if token.winner]

    # -- quotes ----------------------------------------------------------------

    def market_quote(
        self, book_payload: object, market_payload: object, *, symbol: str
    ) -> MarketQuote:
        """CLOB book + market object → one canonical quote for ``symbol``.

        Best levels are extracted order-agnostically (max bid / min
        ask): the venue's observed level order is worst-first (bids
        ascending, asks descending — recorded live), and this adapter
        does not depend on it. The book's ``asset_id`` must equal the
        requested symbol, or the quote is refused.
        """
        book = parse_clob_book(book_payload)
        market = parse_clob_market(market_payload)
        if book.asset_id != symbol:
            raise PolymarketProtocolError(
                f"book asset_id {book.asset_id!r} does not match requested symbol {symbol!r}"
            )
        bid_prices = [level.price for level in book.bids]
        ask_prices = [level.price for level in book.asks]
        return MarketQuote(
            venue=EventVenue.POLYMARKET,
            symbol=symbol,
            timestamp=book.timestamp,
            best_bid=max(bid_prices) if bid_prices else None,
            best_ask=min(ask_prices) if ask_prices else None,
            last_trade_price=None,  # the live book omits it; nothing to claim
            bid_depth=sum(level.size for level in book.bids),
            ask_depth=sum(level.size for level in book.asks),
            tick_size=market.minimum_tick_size,
            min_order_size=market.minimum_order_size,
            taker_fee_bps=market.taker_base_fee,
        )

    def order_book(self, book_payload: object, instrument: Instrument) -> OrderBook:
        """CLOB book → canonical M3 ``OrderBook`` (best-first levels).

        The wire's worst-first level order is canonicalized to the M3
        best-first convention (bids descending, asks ascending). The
        book's ``asset_id`` must equal the instrument symbol.
        """
        book = parse_clob_book(book_payload)
        if book.asset_id != instrument.symbol:
            raise PolymarketProtocolError(
                f"book asset_id {book.asset_id!r} does not match instrument {instrument.symbol!r}"
            )
        return OrderBook(
            instrument=instrument,
            timestamp=book.timestamp,
            bids=[
                DepthLevel(price=level.price, quantity=level.size)
                for level in reversed(book.bids)
            ],
            asks=[
                DepthLevel(price=level.price, quantity=level.size)
                for level in reversed(book.asks)
            ],
        )

    def prices_history(self, payload: object) -> list[PricePoint]:
        return parse_prices_history(payload)


class PolyFixtureProvider(FixtureProvider):
    """Fixture provider serving recorded wire payloads through the
    real parsers (``fixture_dir`` injectable, default the package's
    ``fixtures/``). Registry-registerable: ``mode`` is FIXTURE and the
    M3 gate holds."""

    venue = Venue.POLYMARKET
    mode = ProviderMode.FIXTURE

    def __init__(self, fixture_dir: Path | None = None) -> None:
        super().__init__(fixture_dir or FIXTURE_DIR)
        self.adapter = PolyMarketDataAdapter()

    def _load_payload(self, name: str) -> object:
        path = self._fixture_dir / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"fixture {path} is unreadable or invalid: {error}") from error
        return payload

    def _discovery_payload(self) -> list:
        events = self._load_payload("gamma_events.json")
        active = self._load_payload("gamma_active.json")
        if not isinstance(events, list) or not isinstance(active, list):
            raise ValueError("discovery fixtures must be lists of events")
        return [*events, *active]

    def events(self) -> list[EventMarket]:
        """The recorded discovery capture (one resolved + one active
        event) through the real parsers."""
        return self.adapter.events(self._discovery_payload())

    def resolution(self) -> list[str]:
        """The fixture CLOB market object's winner outcomes."""
        return self.adapter.resolution(self._load_payload("clob_market.json"))

    def market_quote(self, symbol: str) -> MarketQuote:
        """The fixture quote for ``symbol`` (must be the book's asset id)."""
        return self.adapter.market_quote(
            self._load_payload("clob_book.json"),
            self._load_payload("clob_market.json"),
            symbol=symbol,
        )

    def prices_history(self) -> list[PricePoint]:
        return self.adapter.prices_history(self._load_payload("clob_history.json"))

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        books = [self.adapter.order_book(self._load_payload("clob_book.json"), instrument)]
        return self._filtered(books, start, end)

    def fetch_bars(self, instrument: Instrument, *, interval: str, start=None, end=None):
        self._require_venue(instrument)
        raise PolymarketProtocolError(
            "Polymarket has no public bar surface on the pinned contract; "
            "the CLOB prices-history is a price series, not OHLC bars"
        )

    def fetch_trades(self, instrument: Instrument, *, start=None, end=None):
        self._require_venue(instrument)
        raise PolymarketProtocolError(
            "Polymarket exposes no public trades-history surface on the pinned "
            "contract; prices-history is a price series, not trades"
        )


class PolyLiveProvider(Provider):
    """Live provider over an injected keyless transport; explicit
    construction only. ``mode`` is LIVE and the registry refuses LIVE
    venues (M3 gate), so this class is reachable only by deliberate
    construction. Everything it can do is public read-only data; no
    order path exists."""

    venue = Venue.POLYMARKET
    mode = ProviderMode.LIVE

    def __init__(self, transport: PolyRestTransport) -> None:
        self.transport = transport
        self.adapter = PolyMarketDataAdapter()

    def events(self, *, limit: int, offset: int = 0) -> list[EventMarket]:
        """Bounded discovery: live calls always carry an explicit limit."""
        if limit <= 0:
            raise ValueError("live Polymarket discovery needs a positive limit")
        return self.adapter.events(self.transport.gamma_events(limit=limit, offset=offset))

    def market_quote(self, token_id: str, condition_id: str) -> MarketQuote:
        """One quote: CLOB book by token + market object by condition."""
        return self.adapter.market_quote(
            self.transport.clob_book(token_id),
            self.transport.clob_market(condition_id),
            symbol=token_id,
        )

    def prices_history(
        self, token_id: str, *, start: datetime, end: datetime
    ) -> list[PricePoint]:
        """Bounded price series: explicit aware range only (the server
        itself refuses over-long ranges — recorded live)."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("live prices-history needs timezone-aware start and end")
        if start >= end:
            raise ValueError("live prices-history needs start before end")
        start_ms = int(start.astimezone(UTC).timestamp() * 1000)
        end_ms = int(end.astimezone(UTC).timestamp() * 1000)
        return self.adapter.prices_history(
            self.transport.clob_prices_history(token_id, start_ts=start_ms, end_ts=end_ms)
        )

    def resolution(self, condition_id: str) -> list[str]:
        """Winner outcomes from the live market object."""
        return self.adapter.resolution(self.transport.clob_market(condition_id))

    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        self._require_venue(instrument)
        payload = self.transport.clob_book(instrument.symbol)
        return [self.adapter.order_book(payload, instrument)]

    def fetch_bars(self, instrument: Instrument, *, interval: str, start=None, end=None):
        self._require_venue(instrument)
        raise PolymarketProtocolError(
            "Polymarket has no public bar surface on the pinned contract"
        )

    def fetch_trades(self, instrument: Instrument, *, start=None, end=None):
        self._require_venue(instrument)
        raise PolymarketProtocolError(
            "Polymarket exposes no public trades-history surface on the pinned contract"
        )
