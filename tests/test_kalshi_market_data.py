"""Kalshi adapter and provider discipline (issue #35, Phase B).

Fixture-first: the recorded wire fixtures run through the real
parsers. Registry discipline: the fixture provider registers, the
live provider is refused. Keyless and host-pinned: the live transport
refuses any base URL that is not the recorded public host, and the
migration host is refused with its own recorded story. Every number
below (0.42/0.69, sizes, bars, resolutions) was recorded live on
2026-08-08 (ADR-0008 decision 2).
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.providers import ProviderRegistry
from quantmesh.data.providers.base import ProviderMode
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Side, Venue
from quantmesh.events.models import EventVenue, MarketQuote
from quantmesh.kalshi.errors import KalshiProtocolError, KalshiUnavailableError
from quantmesh.kalshi.market_data import (
    FIXTURE_DIR,
    INTERVAL_TO_PERIOD,
    KalshiFixtureProvider,
    KalshiLiveProvider,
    KalshiMarketDataAdapter,
)
from quantmesh.kalshi.transport import (
    KALSHI_MIGRATION_HOST,
    KALSHI_PINNED_HOST,
    HttpxKalshiTransport,
    KalshiRestTransport,
)
from quantmesh.kalshi.wire import parse_candlesticks, parse_trades

FED_TICKER = "KXFED-27APR-T3.50"

CANONICAL = (
    Path(__file__).parent.parent / "src" / "quantmesh" / "data" / "providers" / "fixtures"
)


def _load(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _canonical(name: str) -> list:
    return json.loads((CANONICAL / name).read_text(encoding="utf-8"))


def _instrument(symbol: str = FED_TICKER) -> Instrument:
    return Instrument(
        symbol=symbol, venue=Venue.KALSHI, instrument_type=InstrumentType.EVENT_CONTRACT
    )


class ScriptedKalshiTransport(KalshiRestTransport):
    """Fixture-backed transport for live-provider drills (no network)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def events(self, *, limit: int | None = None, offset: int | None = None) -> object:
        self.calls.append("events")
        return _load("events.json")

    def event(self, ticker: str) -> object:
        self.calls.append("event")
        return _load("event_mars.json")

    def markets(self, *, event_ticker: str, limit: int | None = None) -> object:
        self.calls.append("markets")
        return _load("markets_mars.json")

    def market(self, ticker: str) -> object:
        self.calls.append("market")
        return _load("market_fed.json")

    def orderbook(self, ticker: str) -> object:
        self.calls.append("orderbook")
        return _load("orderbook.json")

    def trades(
        self,
        ticker: str,
        *,
        limit: int | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> object:
        self.calls.append("trades")
        return _load("trades.json")

    def candlesticks(
        self,
        ticker: str,
        *,
        series_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> object:
        self.calls.append("candlesticks")
        return _load("candles.json")

    def series(self, series_ticker: str) -> object:
        self.calls.append("series")
        return _load("series.json")


# -- registry discipline -------------------------------------------------------


def test_fixture_provider_registers_in_the_registry() -> None:
    registry = ProviderRegistry([KalshiFixtureProvider()])
    assert Venue.KALSHI in registry.venues()
    assert registry.get(Venue.KALSHI).mode is ProviderMode.FIXTURE


def test_live_provider_is_refused_by_the_registry() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match="fixture-only"):
        registry.register(KalshiLiveProvider(ScriptedKalshiTransport()))


def test_live_provider_is_explicitly_live() -> None:
    provider = KalshiLiveProvider(ScriptedKalshiTransport())
    assert provider.mode is ProviderMode.LIVE


# -- discovery -----------------------------------------------------------------


def test_discovery_yields_the_recorded_event_markets() -> None:
    provider = KalshiFixtureProvider()
    markets = provider.events()
    assert len(markets) == 3  # Mars (active), Fed (liquid), one settled
    for market in markets:
        assert market.venue is EventVenue.KALSHI
        assert market.expiry_at.tzinfo is not None
        assert market.outcome_id("Yes") == "yes"
        assert market.outcome_id("No") == "no"
        assert len(market.resolution_rule.fingerprint) == 64
    resolved = [m for m in markets if m.resolution]
    assert len(resolved) == 1
    assert resolved[0].resolution == ["No"]
    assert resolved[0].resolved_at is not None and resolved[0].resolved_at.tzinfo is not None
    fed = [m for m in markets if m.venue_market_id == FED_TICKER]
    assert len(fed) == 1
    assert "federal funds rate" in fed[0].title
    assert fed[0].resolution == []  # active, no result yet


def test_fixture_resolution_reads_the_venue_reported_result() -> None:
    assert KalshiFixtureProvider().resolution() == ["No"]


def test_non_binary_markets_are_refused() -> None:
    payload = json.loads((FIXTURE_DIR / "market_fed.json").read_text(encoding="utf-8"))
    payload["market"]["market_type"] = "multicategorical"
    with pytest.raises(KalshiProtocolError, match="only binary"):
        KalshiMarketDataAdapter().events({"markets": [payload["market"]]})


# -- quotes --------------------------------------------------------------------


def test_market_quote_matches_the_recorded_best_levels() -> None:
    provider = KalshiFixtureProvider()
    quote: MarketQuote = provider.market_quote(FED_TICKER)
    assert quote.symbol == FED_TICKER
    # Recorded live: the best YES bid is the max of the yes ladder
    # (0.42) and the best YES ask derives from the best NO bid
    # (1 - 0.31 = 0.69) — cross-checked against the market object's
    # own yes_bid/yes_ask at the same instant.
    assert quote.best_bid == 0.42
    assert quote.best_ask == 0.69
    assert quote.last_trade_price == 0.77  # the venue reports it
    assert quote.tick_size == 0.01
    assert quote.bid_depth == pytest.approx(
        sum(float(level[1]) for level in _load("orderbook.json")["orderbook_fp"]["yes_dollars"])
    )
    assert quote.ask_depth == pytest.approx(
        sum(float(level[1]) for level in _load("orderbook.json")["orderbook_fp"]["no_dollars"])
    )
    assert quote.min_order_size is None  # not reported by the wire
    assert quote.taker_fee_bps == 0.0  # no bps surface; Phase C reads the quadratic fee
    assert quote.timestamp.tzinfo is not None


def test_market_quote_refuses_a_ticker_mismatch() -> None:
    provider = KalshiFixtureProvider()
    with pytest.raises(KalshiProtocolError, match="does not match"):
        provider.market_quote("KXELONMARS-99")


def test_order_book_canonicalizes_to_best_first_derived_asks() -> None:
    provider = KalshiFixtureProvider()
    book = provider.fetch_order_books(_instrument())[0]
    bid_prices = [level.price for level in book.bids]
    ask_prices = [level.price for level in book.asks]
    assert bid_prices == sorted(bid_prices, reverse=True)  # strictly descending
    assert ask_prices == sorted(ask_prices)  # strictly ascending
    assert bid_prices[0] == 0.42 and book.bids[0].quantity == 6.0
    assert ask_prices[0] == 0.69 and book.asks[0].quantity == 4.0
    # Recorded ladder sizes: 12 YES bids, 13 NO bids (the mirror of the
    # NO ladder keeps every level; nothing was at $1.00 to skip).
    assert len(book.bids) == 12
    assert len(book.asks) == 13


def test_order_book_skips_a_derived_ask_at_zero() -> None:
    # A NO bid at $1.00 mirrors to a YES ask at $0.00 — no tradeable
    # depth; the adapter must drop it rather than emit a zero-priced
    # level. Recorded contract: both ladders ascend worst-first.
    payload = json.loads((FIXTURE_DIR / "orderbook.json").read_text(encoding="utf-8"))
    payload["orderbook_fp"]["no_dollars"].append(["1.0000", "5"])
    book = KalshiMarketDataAdapter().order_book(
        payload, _load("market_fed.json"), _instrument()
    )
    assert len(book.bids) == 12
    assert len(book.asks) == 13  # 14 NO bids, one skipped
    assert all(level.price > 0 for level in book.asks)


def test_order_book_refuses_a_wrong_instrument_symbol() -> None:
    provider = KalshiFixtureProvider()
    with pytest.raises(KalshiProtocolError, match="does not match"):
        provider.fetch_order_books(_instrument(symbol="KXELONMARS-99"))


def test_order_book_refuses_a_wrong_venue_instrument() -> None:
    provider = KalshiFixtureProvider()
    instrument = Instrument(
        symbol=FED_TICKER, venue=Venue.MOOMOO, instrument_type=InstrumentType.EVENT_CONTRACT
    )
    with pytest.raises(ValueError, match="cannot serve"):
        provider.fetch_order_books(instrument)


# -- bars and trades -----------------------------------------------------------


def test_bars_derive_from_the_recorded_traded_candles() -> None:
    provider = KalshiFixtureProvider()
    bars = provider.fetch_bars(_instrument(), interval="1h")
    wire = parse_candlesticks(_load("candles.json"))
    traded = [c for c in wire if c.volume_fp > 0]
    assert len(traded) == 10
    assert len(bars) == len(traded)
    assert all(isinstance(bar, Bar) for bar in bars)
    assert all(bar.interval == "1h" and bar.volume > 0 for bar in bars)
    assert all(
        bars[i].timestamp <= bars[i + 1].timestamp for i in range(len(bars) - 1)
    )
    # bar-open = period end - one hour (the M3 convention)
    assert bars[0].timestamp == traded[0].end_period_ts - timedelta(hours=1)
    assert bars[0].open == traded[0].price.open_dollars
    assert bars[0].close == traded[0].price.close_dollars
    assert bars[0].volume == traded[0].volume_fp


def test_zero_volume_periods_produce_no_bars() -> None:
    # 230 recorded rows, only 10 traded: the idle periods are skipped,
    # never fabricated into a bar from the bid/ask series.
    provider = KalshiFixtureProvider()
    bars = provider.fetch_bars(_instrument(), interval="1h")
    assert len(bars) == 10


def test_unknown_intervals_are_refused_everywhere() -> None:
    provider = KalshiFixtureProvider()
    with pytest.raises(ValueError, match="recorded Kalshi candles fixture is 1h"):
        provider.fetch_bars(_instrument(), interval="1d")
    with pytest.raises(ValueError, match="unsupported interval"):
        KalshiMarketDataAdapter().bars(
            _load("candles.json"), _instrument(), interval="5m"
        )
    assert INTERVAL_TO_PERIOD == {"1m": 1, "1h": 60, "1d": 1440}


def test_trades_map_the_recorded_rows_with_aggressor_sides() -> None:
    provider = KalshiFixtureProvider()
    events = provider.fetch_trades(_instrument())
    wire = parse_trades(_load("trades.json"))
    assert len(events) == len(wire) == 5
    for event, row in zip(events, wire):
        assert event.venue_sequence is None  # trade_id is a uuid, not a sequence
        assert event.quantity == row.count_fp
        assert event.timestamp.tzinfo is not None
        if row.taker_side == "yes":
            assert event.price == row.yes_price_dollars
            assert event.aggressor_side is Side.BUY  # bought YES contracts
        else:
            assert event.price == row.no_price_dollars
            assert event.aggressor_side is Side.SELL  # bought NO contracts


def test_trades_refuse_a_symbol_mismatch() -> None:
    provider = KalshiFixtureProvider()
    with pytest.raises(KalshiProtocolError, match="does not match"):
        provider.fetch_trades(_instrument(symbol="KXELONMARS-99"))


def test_fixture_trades_respect_an_explicit_bounds_filter() -> None:
    provider = KalshiFixtureProvider()
    # The 5 recorded rows: four at 2026-08-02T00:44Z, one at
    # 2026-08-05T04:04Z; a window around the burst keeps four.
    within = provider.fetch_trades(
        _instrument(),
        start=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        end=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
    )
    assert len(within) == 4
    outside = provider.fetch_trades(
        _instrument(),
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert outside == []
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.fetch_trades(
            _instrument(), start=datetime(2026, 8, 2), end=datetime(2026, 8, 5, tzinfo=UTC)
        )


# -- market summaries (canonical listing surface) ------------------------------


def test_market_summaries_cover_the_three_recorded_markets() -> None:
    rows = KalshiFixtureProvider().market_summaries()
    assert len(rows) == 3
    assert {row["ticker"] for row in rows} == {
        "KXELONMARS-99",
        FED_TICKER,
        rows[2]["ticker"],  # the settled market
    }
    fed = [row for row in rows if row["ticker"] == FED_TICKER][0]
    assert fed["status"] == "active"
    assert fed["market_type"] == "binary"
    assert fed["result"] == ""
    assert fed["expiry_at"].startswith("2027")
    assert fed["last_price"] == 0.77
    settled = [row for row in rows if row["status"] == "finalized"][0]
    assert settled["result"] == "no"


# -- canonical M3-shape fixtures (data/providers/fixtures) ---------------------


def test_canonical_events_fixture_matches_the_provider_output() -> None:
    rows = _canonical("kalshi_events.json")
    assert len(rows) == 3
    for row in rows:
        assert row["venue"] == "kalshi"
        assert [o["venue_outcome_id"] for o in row["outcomes"]] == ["yes", "no"]
        assert len(row["resolution_rule"]["fingerprint"]) == 64
    resolved = [row for row in rows if row["resolution"]]
    assert len(resolved) == 1
    assert resolved[0]["resolution"] == ["No"]
    assert resolved[0]["resolved_at"] is not None


def test_canonical_markets_fixture_matches_the_listing_surface() -> None:
    rows = _canonical("kalshi_markets.json")
    assert len(rows) == 3
    assert {row["ticker"] for row in rows} == {
        row["venue_market_id"] for row in _canonical("kalshi_events.json")
    }
    for row in rows:
        assert set(row) == {
            "ticker",
            "event_ticker",
            "title",
            "status",
            "market_type",
            "result",
            "expiry_at",
            "last_price",
            "volume",
            "open_interest",
        }


def test_canonical_books_fixture_matches_the_wire_derived_book() -> None:
    rows = _canonical("kalshi_books.json")
    assert len(rows) == 1
    row = rows[0]
    book = KalshiFixtureProvider().fetch_order_books(_instrument())[0]
    assert row["symbol"] == book.instrument.symbol == FED_TICKER
    assert row["datetime"] == book.timestamp.isoformat()
    assert row["bid_levels"] == [[level.price, level.quantity] for level in book.bids]
    assert row["ask_levels"] == [[level.price, level.quantity] for level in book.asks]


def test_canonical_trades_fixture_matches_the_wire_derived_trades() -> None:
    rows = _canonical("kalshi_trades.json")
    assert len(rows) == 5
    events = KalshiFixtureProvider().fetch_trades(_instrument())
    for row, event in zip(rows, events):
        assert row["t"] == event.timestamp.isoformat()
        assert row["px"] == event.price
        assert row["sz"] == event.quantity
        assert row["side"] == event.aggressor_side.value.upper()
        assert row["seq"] is None  # the canonical null sequence


# -- live provider drill -------------------------------------------------------


def test_live_events_require_an_explicit_limit() -> None:
    provider = KalshiLiveProvider(ScriptedKalshiTransport())
    with pytest.raises(ValueError, match="positive limit"):
        provider.events(limit=0)
    transport = ScriptedKalshiTransport()
    markets = KalshiLiveProvider(transport).events(limit=5)
    assert len(markets) == 3
    assert transport.calls == ["events", "markets", "markets", "markets"]


def test_live_quote_and_resolution_drill_through_the_real_parsers() -> None:
    transport = ScriptedKalshiTransport()
    provider = KalshiLiveProvider(transport)
    quote = provider.market_quote(FED_TICKER)
    assert quote.best_bid == 0.42 and quote.best_ask == 0.69
    assert provider.resolution(FED_TICKER) == []  # the fixture market is active
    assert transport.calls == ["orderbook", "market", "market"]


def test_live_trades_require_a_bounded_aware_range() -> None:
    provider = KalshiLiveProvider(ScriptedKalshiTransport())
    with pytest.raises(ValueError, match="explicit aware start and end"):
        provider.fetch_trades(_instrument())
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.fetch_trades(
            _instrument(),
            start=datetime(2026, 7, 1),
            end=datetime(2026, 8, 8, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="start before end"):
        provider.fetch_trades(
            _instrument(),
            start=datetime(2026, 8, 8, tzinfo=UTC),
            end=datetime(2026, 7, 1, tzinfo=UTC),
        )
    transport = ScriptedKalshiTransport()
    events = KalshiLiveProvider(transport).fetch_trades(
        _instrument(),
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 8, 8, tzinfo=UTC),
    )
    assert len(events) == 5
    assert transport.calls == ["trades"]


def test_live_bars_resolve_the_series_chain() -> None:
    # Bars need the series ticker, which lives on the event, not the
    # market: the drill must hit market → event → candlesticks.
    transport = ScriptedKalshiTransport()
    bars = KalshiLiveProvider(transport).fetch_bars(
        _instrument(),
        interval="1h",
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 8, 8, tzinfo=UTC),
    )
    assert len(bars) == 10
    assert transport.calls == ["market", "event", "candlesticks"]


def test_live_bars_require_interval_and_bounds_before_any_call() -> None:
    provider = KalshiLiveProvider(ScriptedKalshiTransport())
    with pytest.raises(ValueError, match="unsupported interval"):
        provider.fetch_bars(
            _instrument(),
            interval="5m",
            start=datetime(2026, 7, 1, tzinfo=UTC),
            end=datetime(2026, 8, 8, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="explicit aware start and end"):
        provider.fetch_bars(_instrument(), interval="1h")


# -- host pinning and typed transport failures ---------------------------------


def test_construction_refuses_any_host_but_the_pinned_one() -> None:
    with pytest.raises(ValueError, match="migration host"):
        HttpxKalshiTransport(base_url=f"https://{KALSHI_MIGRATION_HOST}/trade-api/v2")
    with pytest.raises(ValueError, match="not the pinned public host"):
        HttpxKalshiTransport(base_url="https://api.kalshi.com/trade-api/v2")
    with pytest.raises(ValueError, match="must be https"):
        HttpxKalshiTransport(base_url=f"http://{KALSHI_PINNED_HOST}/trade-api/v2")
    transport = HttpxKalshiTransport()
    assert KALSHI_PINNED_HOST in transport._base  # settings default is pinned


class _FakeResponse:
    def __init__(self, status_code: int, body: object, text: str = "") -> None:
        self.status_code = status_code
        self._body = body
        self._text = text

    def json(self) -> object:
        if isinstance(self._body, dict):
            return self._body
        raise ValueError("not JSON")

    @property
    def text(self) -> str:
        return self._text or repr(self._body)


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    def get(self, url, params=None):  # noqa: ANN001
        return self.response


def test_transport_turns_the_recorded_error_shapes_into_typed_refusals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = HttpxKalshiTransport()
    # {"error": {"code", "message"}} — the 404 shape.
    monkeypatch.setattr(
        transport,
        "_client",
        lambda: _FakeClient(
            _FakeResponse(404, {"error": {"code": "not_found", "message": "market not found"}})
        ),
    )
    with pytest.raises(KalshiProtocolError, match="market not found"):
        transport.market("KXX")
    # {"msg": ...} — the parameter-validation shape.
    monkeypatch.setattr(
        transport,
        "_client",
        lambda: _FakeClient(
            _FakeResponse(400, {"msg": "Parameter validation failed for GetMarketCandlesticks"})
        ),
    )
    with pytest.raises(KalshiProtocolError, match="Parameter validation failed"):
        transport.candlesticks("KXX", series_ticker="KXS", start_ts=1, end_ts=2, period_interval=1)


def test_transport_non_json_bodies_become_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = HttpxKalshiTransport()
    # The recorded migration-host 401 is plain text — unreachable, not
    # a protocol shape.
    monkeypatch.setattr(
        transport,
        "_client",
        lambda: _FakeClient(_FakeResponse(401, None, "API has been moved")),
    )
    with pytest.raises(KalshiUnavailableError, match="API has been moved"):
        transport.market("KXX")


def test_transport_network_failures_become_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def get(self, url, params=None):  # noqa: ANN001
            raise ConnectionError("refused")

    transport = HttpxKalshiTransport()
    monkeypatch.setattr(transport, "_client", lambda: Boom())
    with pytest.raises(KalshiUnavailableError, match="refused"):
        transport.market("KXX")
