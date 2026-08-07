import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.data.providers import (
    HyperliquidFixtureProvider,
    MoomooFixtureProvider,
    ProviderMode,
    ProviderRegistry,
)
from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, InstrumentType, Side, Venue

BTC = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
AAPL = Instrument(
    symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
)
MSFT = Instrument(
    symbol="MSFT", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
)

T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def test_fixture_bars_are_canonical_and_in_provider_order() -> None:
    bars = HyperliquidFixtureProvider().fetch_bars(BTC, interval="1m")

    assert len(bars) == 3
    assert all(isinstance(b, Bar) for b in bars)
    assert all(b.timestamp.tzinfo is UTC for b in bars)
    assert [b.timestamp for b in bars] == [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]
    assert bars[0].close == 104.0
    assert bars[0].volume == 12.5
    assert bars[0].interval == "1m"
    assert bars[0].instrument == BTC


def test_fixture_bars_filter_by_inclusive_range() -> None:
    provider = HyperliquidFixtureProvider()

    bars = provider.fetch_bars(BTC, interval="1m", start=T0 + timedelta(minutes=1))

    assert [b.timestamp for b in bars] == [T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]
    window = provider.fetch_bars(
        BTC, interval="1m", start=T0 + timedelta(minutes=1), end=T0 + timedelta(minutes=1)
    )
    assert [b.timestamp for b in window] == [T0 + timedelta(minutes=1)]


def test_fixture_bars_reject_naive_bounds() -> None:
    provider = HyperliquidFixtureProvider()

    with pytest.raises(ValueError, match="aware"):
        provider.fetch_bars(BTC, interval="1m", start=datetime(2026, 8, 7, 12, 0))


def test_fixture_bars_reject_wrong_interval() -> None:
    with pytest.raises(ValueError, match="fixture provides"):
        HyperliquidFixtureProvider().fetch_bars(BTC, interval="5m")


def test_fixture_order_books_are_canonical() -> None:
    books = HyperliquidFixtureProvider().fetch_order_books(BTC)

    assert len(books) == 2
    assert all(isinstance(b, OrderBook) for b in books)
    assert [b.timestamp for b in books] == [T0, T0 + timedelta(minutes=1)]
    assert [level.price for level in books[0].bids] == [104.5, 104.0, 103.8]
    assert [level.price for level in books[0].asks] == [104.6, 105.0, 105.2]


def test_fixture_trades_map_sides_and_sequences() -> None:
    trades = HyperliquidFixtureProvider().fetch_trades(BTC)

    assert len(trades) == 3
    assert all(isinstance(t, TradeEvent) for t in trades)
    assert [t.aggressor_side for t in trades] == [Side.BUY, Side.SELL, Side.BUY]
    assert [t.venue_sequence for t in trades] == [1001, 1002, 1003]
    assert trades[0].price == 104.0
    assert trades[0].quantity == 0.01


def test_moomoo_fixture_bars_check_symbol_and_interval() -> None:
    provider = MoomooFixtureProvider()

    bars = provider.fetch_bars(AAPL, interval="1m")
    assert len(bars) == 3
    assert all(b.instrument == AAPL for b in bars)

    with pytest.raises(ValueError, match="fixture covers"):
        provider.fetch_bars(MSFT, interval="1m")
    with pytest.raises(ValueError, match="fixture provides"):
        provider.fetch_bars(AAPL, interval="5m")


def test_moomoo_fixture_books_and_trades() -> None:
    provider = MoomooFixtureProvider()

    books = provider.fetch_order_books(AAPL)
    assert len(books) == 1
    assert [level.price for level in books[0].bids] == [204.0, 203.5]

    trades = provider.fetch_trades(AAPL)
    assert len(trades) == 2
    assert [t.aggressor_side for t in trades] == [Side.BUY, Side.SELL]
    assert [t.venue_sequence for t in trades] == [5001, 5002]


def test_missing_fixture_fails_closed(tmp_path: Path) -> None:
    provider = HyperliquidFixtureProvider(fixture_dir=tmp_path)

    with pytest.raises(ValueError, match="fixture"):
        provider.fetch_bars(BTC, interval="1m")


def test_registry_roundtrip_and_missing_venue() -> None:
    registry = ProviderRegistry([HyperliquidFixtureProvider()])

    assert Venue.HYPERLIQUID in registry
    assert registry.venues() == frozenset({Venue.HYPERLIQUID})
    assert registry.get(Venue.HYPERLIQUID).fetch_bars(BTC, interval="1m")

    with pytest.raises(ValueError, match="no provider"):
        registry.get(Venue.MOOMOO)


def test_registry_rejects_duplicate_venue() -> None:
    with pytest.raises(ValueError, match="already registered"):
        ProviderRegistry([HyperliquidFixtureProvider(), HyperliquidFixtureProvider()])


@pytest.mark.parametrize("mode", [ProviderMode.SANDBOX, ProviderMode.LIVE])
def test_registry_rejects_non_fixture_modes(mode: ProviderMode) -> None:
    forced_mode = mode

    class NonFixtureHyperliquid(HyperliquidFixtureProvider):
        mode = forced_mode

    with pytest.raises(ValueError, match="fixture-only"):
        ProviderRegistry([NonFixtureHyperliquid()])


def test_registry_rejects_provider_without_venue() -> None:
    class Anonymous(HyperliquidFixtureProvider):
        venue = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="no valid venue"):
        ProviderRegistry([Anonymous()])


def _write_fixture(tmp_path: Path, name: str, rows: list[dict]) -> None:
    (tmp_path / name).write_text(json.dumps(rows), encoding="utf-8")


def test_fixture_rejects_instrument_from_another_venue() -> None:
    with pytest.raises(ValueError, match="cannot serve"):
        HyperliquidFixtureProvider().fetch_bars(AAPL, interval="1m")


def test_naive_fixture_timestamp_fails_closed(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        "hyperliquid_bars.json",
        [
            {
                "t": "2026-08-07T12:00:00",
                "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 3.0, "i": "1m",
            },
        ],
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        HyperliquidFixtureProvider(fixture_dir=tmp_path).fetch_bars(BTC, interval="1m")


def test_fixture_timestamps_normalize_offsets(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        "hyperliquid_bars.json",
        [
            {
                "t": "2026-08-07T14:00:00+02:00",
                "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 3.0, "i": "1m",
            },
        ],
    )

    bars = HyperliquidFixtureProvider(fixture_dir=tmp_path).fetch_bars(BTC, interval="1m")
    assert bars[0].timestamp == T0


def test_empty_fixture_fails_closed(tmp_path: Path) -> None:
    _write_fixture(tmp_path, "hyperliquid_bars.json", [])

    with pytest.raises(ValueError, match="no rows"):
        HyperliquidFixtureProvider(fixture_dir=tmp_path).fetch_bars(BTC, interval="1m")


def test_fixture_trades_reject_unknown_side(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        "hyperliquid_trades.json",
        [{"t": "2026-08-07T12:00:00Z", "px": 104.0, "sz": 0.01, "side": "X", "seq": 1001}],
    )

    with pytest.raises(ValueError, match="unknown trade side"):
        HyperliquidFixtureProvider(fixture_dir=tmp_path).fetch_trades(BTC)


def test_fixture_bars_reject_mixed_intervals(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        "hyperliquid_bars.json",
        [
            {
                "t": "2026-08-07T12:00:00Z",
                "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 12.5, "i": "1m",
            },
            {
                "t": "2026-08-07T12:01:00Z",
                "o": 104.0, "h": 107.0, "l": 103.0, "c": 106.5, "v": 9.25, "i": "5m",
            },
        ],
    )

    with pytest.raises(ValueError, match="fixture provides"):
        HyperliquidFixtureProvider(fixture_dir=tmp_path).fetch_bars(BTC, interval="1m")


def test_moomoo_books_and_trades_check_symbol() -> None:
    provider = MoomooFixtureProvider()

    with pytest.raises(ValueError, match="fixture covers"):
        provider.fetch_order_books(MSFT)
    with pytest.raises(ValueError, match="fixture covers"):
        provider.fetch_trades(MSFT)


def test_books_and_trades_filter_by_inclusive_range() -> None:
    provider = HyperliquidFixtureProvider()

    books = provider.fetch_order_books(BTC, start=T0 + timedelta(minutes=1))
    assert [b.timestamp for b in books] == [T0 + timedelta(minutes=1)]
    trades = provider.fetch_trades(
        BTC, start=T0 + timedelta(seconds=30), end=T0 + timedelta(minutes=1)
    )
    assert [t.timestamp for t in trades] == [
        T0 + timedelta(seconds=30),
        T0 + timedelta(minutes=1),
    ]


def test_provider_isolation_lake_bytes_are_provider_agnostic(tmp_path: Path) -> None:
    """M3 exit criterion: a consumer cannot see which provider produced data."""
    registry = ProviderRegistry([HyperliquidFixtureProvider(), MoomooFixtureProvider()])
    lake = Lake(tmp_path)
    bars = (
        registry.get(Venue.HYPERLIQUID).fetch_bars(BTC, interval="1m")
        + registry.get(Venue.MOOMOO).fetch_bars(AAPL, interval="1m")
    )

    lake.write_bars("iso", bars)
    ManifestWriter(tmp_path).generate("iso", source="ingestion", license="fixture-only")
    dataset = lake.dataset("iso")

    # The consumer reads identical canonical shapes from both venues.
    all_bars = dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    all_bars += dataset.read_bars(interval="1m", venue=Venue.MOOMOO, symbol="AAPL")
    assert len(all_bars) == 6
    assert all(isinstance(b, Bar) for b in all_bars)

    # Shard columns are exactly the canonical lake schema — nothing vendor-specific.
    shards = list(tmp_path.glob("iso/*/*/*/*/shard-0000.parquet"))
    with duckdb.connect() as con:
        columns = set()
        for shard in shards:
            describe = con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{shard.as_posix()}')"
            ).fetchall()
            columns.update(row[0] for row in describe)
    assert columns == {
        "timestamp", "open", "high", "low", "close", "volume",
        "instrument_type", "currency",
    }

    # The manifest carries only canonical coverage fields — no provider identity.
    for entry in dataset.manifest.coverage:
        assert set(entry.model_dump()) == {"interval", "venue", "symbol", "start", "end", "rows"}
