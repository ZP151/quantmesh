"""Polymarket adapter and provider discipline (issue #34, Phase A).

Fixture-first: the recorded wire fixtures run through the real
parsers. Registry discipline: the fixture provider registers, the
live provider is refused. Keyless: the SDK client is constructed with
``key=None`` by construction (proven below with a faked import) and
nothing else reaches it.
"""

import builtins
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.data.providers import ProviderRegistry
from quantmesh.data.providers.base import ProviderMode
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.events.models import EventVenue
from quantmesh.polymarket.errors import (
    PolymarketProtocolError,
    PolymarketSDKMissingError,
    PolymarketUnavailableError,
)
from quantmesh.polymarket.market_data import (
    FIXTURE_DIR,
    PolyFixtureProvider,
    PolyLiveProvider,
)
from quantmesh.polymarket.transport import PolyRestTransport, SdkPolyTransport

FED_YES_TOKEN = "97186030785608128217926542396950266594898339988989015155120280107165449433603"
FED_NO_TOKEN = "81470465080656150088482886298356783621062802919110096763062861781139262816347"
FED_CONDITION = "0x5e464d85eb49f22d876f3ed6168a7db5e2288e9ae1eb91effd2758e994676f86"
NBA_TICKER = (
    "nba-will-the-mavericks-beat-the-grizzlies-by-more-than-"
    "5pt5-points-in-their-december-4-matchup"
)


def _load(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _instrument(symbol: str = FED_YES_TOKEN) -> Instrument:
    return Instrument(
        symbol=symbol, venue=Venue.POLYMARKET, instrument_type=InstrumentType.EVENT_CONTRACT
    )


class ScriptedPolyTransport(PolyRestTransport):
    """Fixture-backed transport for live-provider drills (no network)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _load(self, name: str) -> object:
        return _load(name)

    def gamma_events(self, *, limit=None, offset=None) -> object:  # noqa: ANN001
        self.calls.append("gamma_events")
        return self._load("gamma_active.json")

    def clob_book(self, token_id: str) -> object:
        self.calls.append("clob_book")
        return self._load("clob_book.json")

    def clob_market(self, condition_id: str) -> object:
        self.calls.append("clob_market")
        return self._load("clob_market.json")

    def clob_prices_history(self, market, *, start_ts, end_ts, fidelity=None) -> object:  # noqa: ANN001
        self.calls.append("clob_prices_history")
        return self._load("clob_history.json")

    def clob_fee_rate(self, token_id: str) -> object:
        self.calls.append("clob_fee_rate")
        return self._load("fee_rate.json")

    def clob_tick_size(self, token_id: str) -> object:
        self.calls.append("clob_tick_size")
        return self._load("tick_size.json")


# -- registry discipline -------------------------------------------------------


def test_fixture_provider_registers_in_the_registry() -> None:
    registry = ProviderRegistry([PolyFixtureProvider()])
    assert Venue.POLYMARKET in registry.venues()
    assert registry.get(Venue.POLYMARKET).mode is ProviderMode.FIXTURE


def test_live_provider_is_refused_by_the_registry() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match="fixture-only"):
        registry.register(PolyLiveProvider(ScriptedPolyTransport()))


def test_live_provider_is_explicitly_live() -> None:
    provider = PolyLiveProvider(ScriptedPolyTransport())
    assert provider.mode is ProviderMode.LIVE


# -- discovery -----------------------------------------------------------------


def test_discovery_yields_the_recorded_event_markets() -> None:
    provider = PolyFixtureProvider()
    markets = provider.events()
    assert len(markets) == 6  # 1 resolved NBA + 5 Fed markets
    tickers = {market.event_ticker for market in markets}
    assert tickers == {NBA_TICKER, "fed-decision-in-september-762"}
    fed = [m for m in markets if m.event_ticker == "fed-decision-in-september-762"]
    assert len(fed) == 5
    for market in fed:
        assert market.venue is EventVenue.POLYMARKET
        assert market.expiry_at == datetime(2026, 9, 16, tzinfo=UTC)
        assert market.outcome_id("Yes")  # every Fed market has a YES token id
        assert market.outcome_id("Yes") in {
            outcome.venue_outcome_id for outcome in market.outcomes
        }
        assert market.resolution == []  # Gamma carries no winner flag
        assert market.resolution_rule.fingerprint  # rule text fingerprinted
    nba = [m for m in markets if m.event_ticker == NBA_TICKER]
    assert len(nba) == 1
    assert nba[0].outcome_id("Yes") and nba[0].outcome_id("No")


def test_discovery_resolution_stays_empty_from_gamma() -> None:
    # A closed Gamma event (the 2021 NBA one) still yields no
    # resolution: Gamma carries no winner flag, and resolution enters
    # only through the CLOB market object's winner flags.
    provider = PolyFixtureProvider()
    assert all(market.resolution == [] for market in provider.events())


def test_fixture_resolution_reads_the_clob_winner_flags() -> None:
    provider = PolyFixtureProvider()
    # The Fed fixture market is unresolved: every winner flag is False.
    assert provider.resolution() == []


# -- quotes --------------------------------------------------------------------


def test_market_quote_takes_best_levels_order_agnostically() -> None:
    provider = PolyFixtureProvider()
    quote = provider.market_quote(FED_YES_TOKEN)
    assert quote.symbol == FED_YES_TOKEN
    # The wire lists bids ascending (worst first); the best bid is the
    # max (0.009). The 99-level ask ladder descends from 0.999 to a
    # tight 0.01 bottom quote (recorded live), so the best ask is the
    # min — extracted order-agnostically.
    assert quote.best_bid == 0.009
    assert quote.best_ask == 0.01
    assert quote.bid_depth == pytest.approx(
        sum(float(level["size"]) for level in _load("clob_book.json")["bids"])
    )
    assert quote.tick_size == 0.001
    assert quote.min_order_size == 5
    assert quote.taker_fee_bps == 1000
    assert quote.last_trade_price is None  # the live book omits it
    assert quote.timestamp.tzinfo is not None


def test_market_quote_refuses_a_symbol_mismatch() -> None:
    provider = PolyFixtureProvider()
    with pytest.raises(PolymarketProtocolError, match="does not match"):
        provider.market_quote(FED_NO_TOKEN)


def test_order_book_canonicalizes_to_best_first() -> None:
    provider = PolyFixtureProvider()
    book = provider.fetch_order_books(_instrument())[0]
    bid_prices = [level.price for level in book.bids]
    ask_prices = [level.price for level in book.asks]
    assert bid_prices == sorted(bid_prices, reverse=True)  # strictly descending
    assert ask_prices == sorted(ask_prices)  # strictly ascending
    assert bid_prices[0] == 0.009  # the wire's last (best) bid leads
    assert ask_prices[0] == 0.01  # the wire's last (best) ask leads


def test_order_book_refuses_a_wrong_instrument_symbol() -> None:
    provider = PolyFixtureProvider()
    with pytest.raises(PolymarketProtocolError, match="does not match"):
        provider.fetch_order_books(_instrument(symbol=FED_NO_TOKEN))


def test_order_book_refuses_a_wrong_venue_instrument() -> None:
    provider = PolyFixtureProvider()
    instrument = Instrument(
        symbol=FED_YES_TOKEN, venue=Venue.MOOMOO, instrument_type=InstrumentType.EVENT_CONTRACT
    )
    with pytest.raises(ValueError, match="cannot serve"):
        provider.fetch_order_books(instrument)


def test_bars_and_trades_fail_closed() -> None:
    provider = PolyFixtureProvider()
    with pytest.raises(PolymarketProtocolError, match="no public bar surface"):
        provider.fetch_bars(_instrument(), interval="1m")
    with pytest.raises(PolymarketProtocolError, match="trades-history"):
        provider.fetch_trades(_instrument())


def test_prices_history_serves_the_recorded_series() -> None:
    points = PolyFixtureProvider().prices_history()
    assert len(points) == 707


# -- canonical M3-shape fixtures (data/providers/fixtures) ---------------------


def test_canonical_books_fixture_matches_the_wire_derived_book() -> None:
    # The canonical file is derived from the recorded wire through the
    # real adapter; it must stay consistent with what the adapter
    # produces (a drift shows up here as a shape mismatch).
    rows = json.loads(
        (
            Path(__file__).parent.parent
            / "src"
            / "quantmesh"
            / "data"
            / "providers"
            / "fixtures"
            / "polymarket_books.json"
        ).read_text(encoding="utf-8")
    )
    assert len(rows) == 1
    row = rows[0]
    book = PolyFixtureProvider().fetch_order_books(_instrument())[0]
    assert row["symbol"] == book.instrument.symbol
    assert row["datetime"] == book.timestamp.isoformat()
    assert row["bid_levels"] == [[level.price, level.quantity] for level in book.bids]
    assert row["ask_levels"] == [[level.price, level.quantity] for level in book.asks]


def test_canonical_events_fixture_round_trips_into_event_markets() -> None:
    rows = json.loads(
        (
            Path(__file__).parent.parent
            / "src"
            / "quantmesh"
            / "data"
            / "providers"
            / "fixtures"
            / "polymarket_events.json"
        ).read_text(encoding="utf-8")
    )
    assert len(rows) == 6
    for row in rows:
        assert row["venue"] == "polymarket"
        assert row["resolution"] == []
        assert len(row["outcomes"]) >= 2
        assert len(row["resolution_rule"]["fingerprint"]) == 64


# -- live provider drill -------------------------------------------------------


def test_live_events_require_an_explicit_limit() -> None:
    provider = PolyLiveProvider(ScriptedPolyTransport())
    with pytest.raises(ValueError, match="positive limit"):
        provider.events(limit=0)
    markets = provider.events(limit=5)
    assert len(markets) == 5


def test_live_quote_and_history_drill_through_the_real_parsers() -> None:
    transport = ScriptedPolyTransport()
    provider = PolyLiveProvider(transport)
    quote = provider.market_quote(FED_YES_TOKEN, FED_CONDITION)
    assert quote.best_bid == 0.009
    points = provider.prices_history(
        FED_YES_TOKEN,
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 8, 8, tzinfo=UTC),
    )
    assert len(points) == 707
    assert transport.calls == ["clob_book", "clob_market", "clob_prices_history"]


def test_live_history_requires_a_bounded_aware_range() -> None:
    provider = PolyLiveProvider(ScriptedPolyTransport())
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.prices_history(
            FED_YES_TOKEN, start=datetime(2026, 7, 1), end=datetime(2026, 8, 8, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="start before end"):
        provider.prices_history(
            FED_YES_TOKEN,
            start=datetime(2026, 8, 8, tzinfo=UTC),
            end=datetime(2026, 7, 1, tzinfo=UTC),
        )


def test_live_order_book_drill() -> None:
    provider = PolyLiveProvider(ScriptedPolyTransport())
    book = provider.fetch_order_books(_instrument())[0]
    assert book.bids[0].price == 0.009


# -- SDK transport: keyless construction and typed failures --------------------


class _FakeClobClient:
    """Records construction kwargs to prove the keyless contract."""

    instances: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002
        self.args = args
        self.kwargs = kwargs
        _FakeClobClient.instances.append(kwargs)

    def get_order_book(self, token_id):  # noqa: ANN001
        return _load("clob_book.json")


def _fake_sdk_import(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "py_clob_client_v2.client":
            module = type("fake_client", (), {})()
            module.ClobClient = _FakeClobClient
            return module
        if name == "py_clob_client_v2.clob_types":
            module = type("fake_types", (), {})()
            module.PricesHistoryParams = type("PricesHistoryParams", (), {})
            return module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_sdk_transport_constructs_the_client_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClobClient.instances = []
    _fake_sdk_import(monkeypatch)
    transport = SdkPolyTransport()
    transport.clob_book(FED_YES_TOKEN)
    assert len(_FakeClobClient.instances) == 1
    kwargs = _FakeClobClient.instances[0]
    assert kwargs["key"] is None  # no signer path exists
    assert kwargs["host"] == "https://clob.polymarket.com"
    assert kwargs["chain_id"] == 137


def test_sdk_transport_missing_sdk_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def no_sdk(name, *args, **kwargs):
        if name.startswith("py_clob_client_v2"):
            raise ImportError("vendored SDK not installed in this venv")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sdk)
    transport = SdkPolyTransport()
    with pytest.raises(PolymarketSDKMissingError, match="not importable"):
        transport.clob_book(FED_YES_TOKEN)


def test_sdk_transport_sdk_failures_become_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def get_order_book(self, token_id):  # noqa: ANN001
            raise ConnectionError("refused")

    monkeypatch.setattr(SdkPolyTransport, "_sdk", lambda self: Boom())
    transport = SdkPolyTransport()
    with pytest.raises(PolymarketUnavailableError, match="get_order_book"):
        transport.clob_book(FED_YES_TOKEN)
