"""Hyperliquid provider tests (M5, issue #29, Phase A).

``HyperliquidFixtureProvider`` serves bundled wire-shaped payloads
through the real parsers, so a fixture failure is a parser failure; it
is registry-registerable like every M3 fixture provider. The live
provider is explicit-construction-only: the registry refuses it
(fixture-only gate), bounded ranges are mandatory, and trades fail
closed because Hyperliquid has no public trades REST endpoint. A lake
round trip proves the parsed bars land in the canonical layout with a
gap-free series.
"""

from datetime import UTC, datetime

import pytest

from quantmesh.data.lake import Lake
from quantmesh.data.providers.registry import ProviderRegistry
from quantmesh.domain.market_data import find_gaps
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.market_data import (
    HyperliquidFixtureProvider,
    HyperliquidLiveProvider,
)
from quantmesh.hyperliquid.rest import ScriptedRestTransport

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
    currency="USD",
)

T0 = 1754600400000
STEP_MS = 60_000


def _t(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def test_fixture_bars_parse_through_the_real_parsers() -> None:
    bars = HyperliquidFixtureProvider().fetch_bars(BTC, interval="1m")

    assert len(bars) == 6
    assert [bar.timestamp for bar in bars] == [_t(T0 + i * STEP_MS) for i in range(6)]
    assert bars[0].open == 100.0
    assert bars[0].close == 104.5
    assert find_gaps([bar.timestamp for bar in bars], interval="1m") == []


def test_fixture_bars_filter_inclusively() -> None:
    provider = HyperliquidFixtureProvider()

    bars = provider.fetch_bars(
        BTC, interval="1m", start=_t(T0 + STEP_MS), end=_t(T0 + 3 * STEP_MS)
    )

    assert len(bars) == 3
    assert bars[0].timestamp == _t(T0 + STEP_MS)
    assert bars[-1].timestamp == _t(T0 + 3 * STEP_MS)


def test_fixture_bars_reject_naive_bounds() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        HyperliquidFixtureProvider().fetch_bars(
            BTC, interval="1m", start=datetime(2026, 8, 8)
        )


def test_fixture_book_and_trades_and_funding() -> None:
    provider = HyperliquidFixtureProvider()

    book = provider.fetch_order_books(BTC)[0]
    assert [level.price for level in book.bids] == [107.5, 107.0, 106.5]

    trades = provider.fetch_trades(BTC)
    assert [trade.venue_sequence for trade in trades] == [7, 8, 9]

    rates = provider.funding(BTC)
    assert [rate.coin for rate in rates] == ["BTC", "BTC"]
    assert [rate.rate for rate in rates] == [0.00001, 0.000012]


def test_fixture_provider_refuses_foreign_venues() -> None:
    moomoo = Instrument(
        symbol="AAPL",
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )

    with pytest.raises(ValueError, match="cannot serve"):
        HyperliquidFixtureProvider().fetch_bars(moomoo, interval="1m")


def test_fixture_provider_rejects_an_unrequested_interval() -> None:
    with pytest.raises(HyperliquidProtocolError, match="does not match requested"):
        HyperliquidFixtureProvider().fetch_bars(BTC, interval="5m")


def test_fixture_provider_registers_like_any_m3_provider() -> None:
    registry = ProviderRegistry([HyperliquidFixtureProvider()])

    assert Venue.HYPERLIQUID in registry
    assert registry.get(Venue.HYPERLIQUID).mode.value == "fixture"


def test_live_provider_bars_require_bounded_ranges() -> None:
    provider = HyperliquidLiveProvider(ScriptedRestTransport())

    with pytest.raises(ValueError, match="bounded ranges only"):
        provider.fetch_bars(BTC, interval="1m")
    with pytest.raises(ValueError, match="bounded ranges only"):
        provider.fetch_bars(BTC, interval="1m", start=_t(T0))


def test_live_provider_bars_parse_scripted_rows() -> None:
    import json

    from quantmesh.hyperliquid.market_data import FIXTURE_DIR

    rows = json.loads((FIXTURE_DIR / "wire_candles.json").read_text(encoding="utf-8"))
    transport = ScriptedRestTransport(candles={("BTC", "1m"): rows})
    provider = HyperliquidLiveProvider(transport)

    bars = provider.fetch_bars(BTC, interval="1m", start=_t(T0), end=_t(T0 + 5 * STEP_MS))

    assert len(bars) == 6
    assert bars[-1].timestamp == _t(T0 + 5 * STEP_MS)


def test_live_provider_trades_fail_closed() -> None:
    provider = HyperliquidLiveProvider(ScriptedRestTransport())

    with pytest.raises(HyperliquidProtocolError, match="no public trades REST endpoint"):
        provider.fetch_trades(BTC)


def test_live_provider_funding_history_parses() -> None:
    transport = ScriptedRestTransport(
        funding={
            "BTC": [{"coin": "BTC", "fundingRate": "0.00001", "premium": "0.00002", "time": T0}]
        }
    )
    provider = HyperliquidLiveProvider(transport)

    rates = provider.funding_history(BTC, start=_t(T0), end=_t(T0 + STEP_MS))

    assert [rate.rate for rate in rates] == [0.00001]


def test_live_provider_is_refused_by_the_registry() -> None:
    provider = HyperliquidLiveProvider(ScriptedRestTransport())

    with pytest.raises(ValueError, match="fixture-only"):
        ProviderRegistry().register(provider)


def test_lake_round_trip_is_gap_free(tmp_path) -> None:
    bars = HyperliquidFixtureProvider().fetch_bars(BTC, interval="1m")
    lake = Lake(tmp_path)

    lake.write_bars("bars", bars)
    stored = lake.read_bars(
        "bars", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC"
    )

    assert [bar.timestamp for bar in stored] == [bar.timestamp for bar in bars]
    assert stored[0].instrument == BTC
    assert find_gaps([bar.timestamp for bar in stored], interval="1m") == []
