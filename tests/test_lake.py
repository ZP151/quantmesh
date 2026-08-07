from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantmesh.data.lake import Lake, LakeQuality
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.settings import Settings

BTC = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
AAPL = Instrument(
    symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
)
T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
DAY1 = "2026-08-07"
DAY2 = "2026-08-08"


def bar(instrument: Instrument = BTC, **overrides: object) -> Bar:
    values: dict[str, object] = {
        "instrument": instrument,
        "timestamp": T0,
        "interval": "1m",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 12.5,
    }
    values.update(overrides)
    return Bar(**values)


def shard(root: Path, dataset: str, interval: str, venue: Venue, symbol: str, day: str) -> Path:
    return root / dataset / interval / venue.value / symbol / day / "shard-0000.parquet"


def test_write_creates_canonical_partition_layout(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    dataset = "fixture-bars"

    lake.write_bars(dataset, [bar()])

    assert shard(tmp_path, dataset, "1m", Venue.HYPERLIQUID, "BTC-PERP", DAY1).exists()


def test_write_partitions_by_venue_symbol_interval_and_date(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    next_day = T0 + timedelta(days=1)
    next_hour = T0 + timedelta(hours=1)

    lake.write_bars(
        "multi",
        [
            bar(timestamp=T0),
            bar(timestamp=next_hour),
            bar(timestamp=next_day),
            bar(instrument=AAPL, timestamp=T0),
        ],
    )

    assert shard(tmp_path, "multi", "1m", Venue.HYPERLIQUID, "BTC-PERP", DAY1).exists()
    assert shard(tmp_path, "multi", "1m", Venue.HYPERLIQUID, "BTC-PERP", DAY2).exists()
    assert shard(tmp_path, "multi", "1m", Venue.MOOMOO, "AAPL", DAY1).exists()
    # Two bars on the same day land in the same shard, not two shards.
    import re

    day_dir = tmp_path / "multi" / "1m" / "hyperliquid" / "BTC-PERP" / DAY1
    shards = [p for p in day_dir.iterdir() if re.fullmatch(r"shard-\d{4}\.parquet", p.name)]
    assert shards == [day_dir / "shard-0000.parquet"]


def test_roundtrip_preserves_bars(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    bars = [
        bar(timestamp=T0),
        bar(timestamp=T0 + timedelta(minutes=1), close=105.0, volume=3.25),
        bar(timestamp=T0 + timedelta(days=1)),
        bar(instrument=AAPL, timestamp=T0, open=200.0, high=205.0, low=199.0, close=204.0),
    ]

    lake.write_bars("rt", bars)
    back = lake.read_bars("rt", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    back_aapl = lake.read_bars("rt", interval="1m", venue=Venue.MOOMOO, symbol="AAPL")

    assert back == [bars[0], bars[1], bars[2]]
    assert back_aapl == [bars[3]]
    assert all(b.timestamp.tzinfo is UTC for b in back)


def test_read_returns_bars_in_stored_order(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    later = T0 + timedelta(minutes=5)
    bars = [bar(timestamp=later), bar(timestamp=T0)]

    lake.write_bars("ordered", bars)

    stored = lake.read_bars(
        "ordered", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP"
    )
    assert [b.timestamp for b in stored] == [later, T0]


def test_read_filters_by_time_range(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    bars = [bar(timestamp=T0 + timedelta(minutes=m)) for m in range(4)]

    lake.write_bars("range", bars)
    window = lake.read_bars(
        "range",
        interval="1m",
        venue=Venue.HYPERLIQUID,
        symbol="BTC-PERP",
        start=T0 + timedelta(minutes=1),
        end=T0 + timedelta(minutes=2),
    )

    assert [b.timestamp for b in window] == [T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]


def test_write_is_deterministic(tmp_path: Path) -> None:
    first = Lake(tmp_path / "a")
    second = Lake(tmp_path / "b")
    bars = [bar(timestamp=T0 + timedelta(minutes=m)) for m in range(3)]

    first.write_bars("det", bars)
    second.write_bars("det", bars)

    a = first.shard_file("det", "1m", Venue.HYPERLIQUID, "BTC-PERP", DAY1)
    b = second.shard_file("det", "1m", Venue.HYPERLIQUID, "BTC-PERP", DAY1)
    assert a.read_bytes() == b.read_bytes()


def test_write_replaces_the_days_shard_wholesale(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("day", [bar(timestamp=T0), bar(timestamp=T0 + timedelta(minutes=1))])
    lake.write_bars(
        "day",
        [
            bar(timestamp=T0),
            bar(timestamp=T0 + timedelta(minutes=1)),
            bar(timestamp=T0 + timedelta(minutes=2)),
        ],
    )

    back = lake.read_bars("day", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert len(back) == 3


def test_read_empty_dataset_returns_empty_list(tmp_path: Path) -> None:
    lake = Lake(tmp_path)

    stored = lake.read_bars(
        "nothing", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP"
    )
    assert stored == []


def test_write_rejects_empty_sequence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one bar"):
        Lake(tmp_path).write_bars("empty", [])


@pytest.mark.parametrize("bad", ["..", "../evil", "a b", "UpPer", "-lead", "trail-"])
def test_write_rejects_invalid_dataset_names(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="dataset"):
        Lake(tmp_path).write_bars(bad, [bar()])


def test_quality_reports_out_of_order_bars(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    later = T0 + timedelta(minutes=3)
    lake.write_bars("q", [bar(timestamp=later), bar(timestamp=T0)])

    report = lake.quality("q", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert report.out_of_order == [(0, 1)]


def test_quality_reports_duplicate_bars(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars(
        "q", [bar(timestamp=T0), bar(timestamp=T0), bar(timestamp=T0 + timedelta(minutes=1))]
    )

    report = lake.quality("q", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert report.duplicates == {T0: [0, 1]}


def test_quality_reports_gaps(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars(
        "q",
        [
            bar(timestamp=T0, interval="5m"),
            bar(timestamp=T0 + timedelta(minutes=10), interval="5m"),
        ],
    )

    report = lake.quality("q", interval="5m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert report.gaps == [T0 + timedelta(minutes=5)]


def test_quality_clean_dataset_reports_nothing(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("q", [bar(timestamp=T0 + timedelta(minutes=m)) for m in range(3)])

    report = lake.quality("q", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert report.rows == 3
    assert report.out_of_order == []
    assert report.duplicates == {}
    assert report.gaps == []
    assert isinstance(report, LakeQuality)


def test_quality_rejects_misaligned_series(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars(
        "q",
        [
            bar(timestamp=T0, interval="5m"),
            bar(timestamp=T0 + timedelta(minutes=7), interval="5m"),
        ],
    )

    with pytest.raises(ValueError, match="aligned"):
        lake.quality("q", interval="5m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")


def test_settings_lake_root_default_and_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    default = Settings().lake_root
    assert default == Path.home() / ".quantmesh" / "data"

    monkeypatch.setenv("QUANTMESH_LAKE_ROOT", str(tmp_path / "env-lake"))
    assert Settings().lake_root == tmp_path / "env-lake"


def test_lake_from_settings_uses_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QUANTMESH_LAKE_ROOT", str(tmp_path / "env-lake"))
    lake = Lake.from_settings(Settings())

    lake.write_bars("cfg", [bar()])
    assert shard(tmp_path / "env-lake", "cfg", "1m", Venue.HYPERLIQUID, "BTC-PERP", DAY1).exists()


@pytest.mark.parametrize("bad", ["..", "../x", "a b", "up/per", "a'b", "-lead"])
def test_write_rejects_invalid_symbols(tmp_path: Path, bad: str) -> None:
    instrument = Instrument(
        symbol=bad, venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
    )

    with pytest.raises(ValueError, match="symbol"):
        Lake(tmp_path).write_bars("sym", [bar(instrument=instrument)])


def test_read_rejects_invalid_symbol_and_interval(tmp_path: Path) -> None:
    lake = Lake(tmp_path)

    with pytest.raises(ValueError, match="symbol"):
        lake.read_bars("s", interval="1m", venue=Venue.HYPERLIQUID, symbol="..")
    with pytest.raises(ValueError):
        lake.read_bars("s", interval="..", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")


def test_read_rejects_naive_range_bounds(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    naive = datetime(2026, 8, 7, 12, 0)

    with pytest.raises(ValueError, match="aware"):
        lake.read_bars("s", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP", start=naive)
    with pytest.raises(ValueError, match="aware"):
        lake.read_bars("s", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP", end=naive)


def test_roundtrip_normalizes_non_utc_aware_timestamps(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    singapore = datetime(2026, 8, 7, 20, 0, tzinfo=timezone(timedelta(hours=8)))

    lake.write_bars("tz", [bar(timestamp=singapore)])
    back = lake.read_bars("tz", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert back == [bar(timestamp=T0)]
    assert all(b.timestamp.tzinfo is UTC for b in back)


def test_quality_on_empty_partition_reports_empty(tmp_path: Path) -> None:
    report = Lake(tmp_path).quality(
        "fresh", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP"
    )

    assert report.rows == 0
    assert report.out_of_order == []
    assert report.duplicates == {}
    assert report.gaps == []


def test_read_range_spans_days(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    bars = [bar(timestamp=T0), bar(timestamp=T0 + timedelta(days=1))]
    lake.write_bars("span", bars)

    window = lake.read_bars(
        "span",
        interval="1m",
        venue=Venue.HYPERLIQUID,
        symbol="BTC-PERP",
        start=T0,
        end=T0 + timedelta(days=1),
    )

    assert [b.timestamp for b in window] == [b.timestamp for b in bars]


def test_roundtrip_through_root_with_apostrophe(tmp_path: Path) -> None:
    lake = Lake(tmp_path / "user's lake")
    bars = [bar(), bar(timestamp=T0 + timedelta(minutes=1))]

    lake.write_bars("quote", bars)
    back = lake.read_bars("quote", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")

    assert back == bars
