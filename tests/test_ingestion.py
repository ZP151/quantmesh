import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.data.ingestion import IngestionJob, Ingestor, coverage_gaps
from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.data.providers import HyperliquidFixtureProvider, ProviderRegistry
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

BTC = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
AAPL = Instrument(
    symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
)
T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def _bar(timestamp: datetime, symbol: str = "BTC-PERP", interval: str = "1m") -> Bar:
    return Bar(
        instrument=Instrument(
            symbol=symbol,
            venue=Venue.HYPERLIQUID,
            instrument_type=InstrumentType.PERPETUAL,
        ),
        timestamp=timestamp,
        interval=interval,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )


def _row(timestamp: datetime, *, open: float = 100.0) -> dict:
    return {
        "t": timestamp.isoformat(),
        "o": open,
        "h": open + 1.0,
        "l": open - 1.0,
        "c": open + 0.5,
        "v": 10.0,
        "i": "1m",
    }


def _write_fixture(fixture_dir: Path, name: str, rows: list[dict]) -> None:
    (fixture_dir / name).write_text(json.dumps(rows), encoding="utf-8")


def _job(dataset: str = "algo", instrument: Instrument = BTC, interval: str = "1m") -> IngestionJob:
    return IngestionJob(dataset=dataset, instrument=instrument, interval=interval)


def _fixture_registry(tmp_path: Path, rows: list[dict]) -> tuple[ProviderRegistry, Path]:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    _write_fixture(fixture_dir, "hyperliquid_bars.json", rows)
    return ProviderRegistry([HyperliquidFixtureProvider(fixture_dir=fixture_dir)]), fixture_dir


def _two_day_dataset(lake_root: Path, dataset: str = "algo") -> None:
    lake = Lake(lake_root)
    day1 = [_bar(T0 + timedelta(minutes=index)) for index in range(3)]
    day2 = [_bar(T0 + timedelta(days=1, minutes=index)) for index in range(3)]
    lake.write_bars(dataset, day1 + day2)
    ManifestWriter(lake_root).generate(dataset, source="fixture", license="test")


def test_ingest_first_run_writes_bars_and_manifest(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    registry, _ = _fixture_registry(tmp_path, [_row(T0 + timedelta(minutes=i)) for i in range(3)])

    manifest = Ingestor(registry, lake_root).ingest(_job())

    assert manifest is not None
    assert manifest.revision == 1
    assert manifest.source == "ingestion"
    assert manifest.license == "fixture-only"
    dataset = Lake(lake_root).dataset("algo")
    bars = dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    assert len(bars) == 3
    assert [b.timestamp for b in bars] == [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]


def test_ingest_is_incremental_and_idempotent(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    rows = [_row(T0 + timedelta(minutes=i)) for i in range(3)]
    registry, fixture_dir = _fixture_registry(tmp_path, rows)
    ingestor = Ingestor(registry, lake_root)

    first = ingestor.ingest(_job())
    assert first is not None and first.revision == 1

    # Nothing new: no write, manifest revision stable.
    assert ingestor.ingest(_job()) is None

    # A new tick arrives; the day window re-fetches the last day and the
    # wholesale day-shard replacement keeps every bar of that day.
    _write_fixture(fixture_dir, "hyperliquid_bars.json", rows + [_row(T0 + timedelta(minutes=3))])
    second = ingestor.ingest(_job())
    assert second is not None and second.revision == 2

    dataset = Lake(lake_root).dataset("algo")
    bars = dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    assert len(bars) == 4
    assert bars[-1].timestamp == T0 + timedelta(minutes=3)


def test_ingest_picks_up_last_day_value_correction(tmp_path: Path) -> None:
    """Same timestamps, changed values: the day shard is rebuilt (ADR-0003)."""
    lake_root = tmp_path / "lake"
    rows = [_row(T0 + timedelta(minutes=i)) for i in range(3)]
    registry, fixture_dir = _fixture_registry(tmp_path, rows)
    ingestor = Ingestor(registry, lake_root)
    assert ingestor.ingest(_job()).revision == 1

    corrected = rows[:]
    corrected[1] = _row(T0 + timedelta(minutes=1), open=250.0)
    _write_fixture(fixture_dir, "hyperliquid_bars.json", corrected)

    second = ingestor.ingest(_job())
    assert second is not None and second.revision == 2
    bars = Lake(lake_root).dataset("algo").read_bars(
        interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP"
    )
    assert bars[1].open == 250.0


def test_ingest_rebuilds_day_shard_on_retraction(tmp_path: Path) -> None:
    """Provider's last day shrank: the day shard is rebuilt, not frozen."""
    lake_root = tmp_path / "lake"
    rows = [_row(T0 + timedelta(minutes=i)) for i in range(3)]
    registry, fixture_dir = _fixture_registry(tmp_path, rows)
    ingestor = Ingestor(registry, lake_root)
    assert ingestor.ingest(_job()).revision == 1

    _write_fixture(fixture_dir, "hyperliquid_bars.json", rows[:2])

    second = ingestor.ingest(_job())
    assert second is not None and second.revision == 2
    bars = Lake(lake_root).dataset("algo").read_bars(
        interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP"
    )
    assert [b.timestamp for b in bars] == [T0, T0 + timedelta(minutes=1)]


def test_ingest_heals_stale_manifest_when_provider_has_nothing_new(tmp_path: Path) -> None:
    """A write that never regenerated its manifest is healed on the next run."""
    lake_root = tmp_path / "lake"
    registry, _ = _fixture_registry(tmp_path, [_row(T0 + timedelta(minutes=i)) for i in range(3)])
    ingestor = Ingestor(registry, lake_root)
    assert ingestor.ingest(_job()).revision == 1

    # Simulate write-without-regeneration: bytes unchanged, the manifest
    # lags the bytes (declares fewer rows than exist).
    manifest_path = lake_root / "algo" / "manifest.json"
    tampered = manifest_path.read_text(encoding="utf-8").replace('"rows": 3', '"rows": 2', 1)
    manifest_path.write_text(tampered, encoding="utf-8")

    healed = ingestor.ingest(_job())
    assert healed is not None and healed.revision == 2
    assert Lake(lake_root).dataset("algo").manifest.revision == 2


def test_ingest_fails_loudly_on_corrupt_shard_until_repaired(tmp_path: Path) -> None:
    """A corrupt unrelated shard breaks regeneration loudly, and the next
    run recovers the dataset once the shard is repaired."""
    lake_root = tmp_path / "lake"
    rows = [_row(T0 + timedelta(minutes=i)) for i in range(3)]
    registry, fixture_dir = _fixture_registry(tmp_path, rows)
    ingestor = Ingestor(registry, lake_root)
    assert ingestor.ingest(_job()).revision == 1

    lake = Lake(lake_root)
    lake.write_bars("algo", [_bar(T0, symbol="ETH-PERP")])
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    shard = (
        lake_root / "algo" / "1m" / "hyperliquid" / "ETH-PERP" / "2026-08-07" / "shard-0000.parquet"
    )
    shard.write_bytes(b"not a parquet file")

    _write_fixture(fixture_dir, "hyperliquid_bars.json", rows + [_row(T0 + timedelta(minutes=3))])
    with pytest.raises(ValueError, match="unreadable"):
        ingestor.ingest(_job())

    # The failure was loud, not a silent no-op; once the corrupt shard is
    # repaired the next run heals the stale manifest and the gate reopens.
    lake.write_bars("algo", [_bar(T0, symbol="ETH-PERP")])
    repaired = ingestor.ingest(_job())
    assert repaired is not None and repaired.revision == 3
    dataset = Lake(lake_root).dataset("algo")
    assert dataset.manifest.revision == 3
    bars = dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    assert len(bars) == 4


def test_dataset_gate_fails_closed_on_corrupt_shard(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    _two_day_dataset(lake_root)
    shard = (
        lake_root / "algo" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-07" / "shard-0000.parquet"
    )
    shard.write_bytes(b"garbage bytes")

    with pytest.raises(ValueError, match="unreadable"):
        Lake(lake_root).dataset("algo")


def test_coverage_gaps_reports_corrupt_shard_fail_closed(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    _two_day_dataset(lake_root)
    shard = (
        lake_root / "algo" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-07" / "shard-0000.parquet"
    )
    shard.write_bytes(b"garbage bytes")

    with pytest.raises(ValueError, match="unreadable"):
        coverage_gaps(lake_root, "algo")


def test_coverage_gaps_interval_grid_no_phantom_days(tmp_path: Path) -> None:
    """Coarse intervals expect ticks on their grid, not every calendar day."""
    lake_root = tmp_path / "lake"
    lake = Lake(lake_root)
    week = [_bar(T0, interval="1w"), _bar(T0 + timedelta(weeks=1), interval="1w")]
    lake.write_bars("algo", week)
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")

    gap = coverage_gaps(lake_root, "algo").series[0]

    assert gap.missing_days == []
    assert gap.unexpected_days == []


def test_coverage_gaps_empty_dataset_fails_closed(tmp_path: Path) -> None:
    """All data gone: even explicit recovery cannot make a report bless it."""
    lake_root = tmp_path / "lake"
    _two_day_dataset(lake_root)
    shutil.rmtree(lake_root / "algo" / "1m")
    # Removing the manifest is the documented override for deliberate
    # changes; regeneration from the empty lake yields an empty manifest,
    # and the coverage report still refuses to call that clean.
    (lake_root / "algo" / "manifest.json").unlink()
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")

    with pytest.raises(ValueError, match="holds no series"):
        coverage_gaps(lake_root, "algo")


def test_ingest_refuses_to_heal_vanished_series(tmp_path: Path) -> None:
    """A no-op run must not heal away a series that vanished from the lake."""
    lake_root = tmp_path / "lake"
    registry, _ = _fixture_registry(tmp_path, [_row(T0 + timedelta(minutes=i)) for i in range(3)])
    ingestor = Ingestor(registry, lake_root)
    assert ingestor.ingest(_job()).revision == 1
    lake = Lake(lake_root)
    lake.write_bars("algo", [_bar(T0, symbol="ETH-PERP")])
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    shutil.rmtree(lake_root / "algo" / "1m" / "hyperliquid" / "ETH-PERP")

    with pytest.raises(ValueError, match="vanished"):
        ingestor.ingest(_job())

    # The evidence is preserved: the report still names the missing series.
    series = {gap.symbol: gap for gap in coverage_gaps(lake_root, "algo").series}
    assert series["ETH-PERP"].observed_rows is None


def test_ingest_refuses_to_bless_interior_day_loss(tmp_path: Path) -> None:
    """A lost interior day is refused even when a new day masks the count."""
    lake_root = tmp_path / "lake"
    rows = []
    for day in range(3):
        rows += [_row(T0 + timedelta(days=day, minutes=index)) for index in range(3)]
    registry, fixture_dir = _fixture_registry(tmp_path, rows)
    ingestor = Ingestor(registry, lake_root)
    assert ingestor.ingest(_job()).revision == 1

    shutil.rmtree(lake_root / "algo" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-07")
    rows += [_row(T0 + timedelta(days=3, minutes=index)) for index in range(3)]
    _write_fixture(fixture_dir, "hyperliquid_bars.json", rows)

    with pytest.raises(ValueError, match="start moved forward"):
        ingestor.ingest(_job())


def test_ingest_rejects_missing_provider(tmp_path: Path) -> None:
    ingestor = Ingestor(ProviderRegistry([HyperliquidFixtureProvider()]), tmp_path / "lake")

    with pytest.raises(ValueError, match="no provider"):
        ingestor.ingest(_job(instrument=AAPL))


def test_job_rejects_bad_dataset_name() -> None:
    with pytest.raises(ValidationError):
        IngestionJob(dataset="Bad Name", instrument=BTC, interval="1m")


def test_job_rejects_bad_interval() -> None:
    with pytest.raises(ValidationError):
        IngestionJob(dataset="algo", instrument=BTC, interval="5x")


def test_job_rejects_bad_cadence() -> None:
    with pytest.raises(ValidationError):
        IngestionJob(dataset="algo", instrument=BTC, interval="1m", cadence="1x")


def test_run_processes_jobs_in_order(tmp_path: Path) -> None:
    registry, _ = _fixture_registry(tmp_path, [_row(T0 + timedelta(minutes=i)) for i in range(3)])
    ingestor = Ingestor(registry, tmp_path / "lake")

    results = ingestor.run([_job(dataset="first"), _job(dataset="second")])

    assert [result.dataset for result in results if result] == ["first", "second"]


def test_run_preserves_noop_slots(tmp_path: Path) -> None:
    registry, _ = _fixture_registry(tmp_path, [_row(T0 + timedelta(minutes=i)) for i in range(3)])
    ingestor = Ingestor(registry, tmp_path / "lake")
    ingestor.ingest(_job(dataset="first"))

    results = ingestor.run([_job(dataset="first"), _job(dataset="second")])

    assert results[0] is None
    assert results[1] is not None and results[1].dataset == "second"


def test_coverage_gaps_clean_dataset_reports_no_gaps(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    _two_day_dataset(lake_root)

    report = coverage_gaps(lake_root, "algo")

    assert report.dataset == "algo"
    assert len(report.series) == 1
    gap = report.series[0]
    assert gap.declared_rows == gap.observed_rows == 6
    assert gap.declared_start == T0
    assert gap.observed_end == T0 + timedelta(days=1, minutes=2)
    assert gap.missing_days == []
    assert gap.unexpected_days == []


def test_coverage_gaps_missing_day_detected(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    _two_day_dataset(lake_root)
    shutil.rmtree(lake_root / "algo" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-08")

    gap = coverage_gaps(lake_root, "algo").series[0]

    assert gap.missing_days == ["2026-08-08"]
    assert gap.declared_rows == 6
    assert gap.observed_rows == 3
    assert gap.observed_end == T0 + timedelta(minutes=2)


def test_coverage_gaps_missing_series_detected(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    lake = Lake(lake_root)
    lake.write_bars("algo", [_bar(T0, symbol="BTC-PERP"), _bar(T0, symbol="ETH-PERP")])
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    shutil.rmtree(lake_root / "algo" / "1m" / "hyperliquid" / "ETH-PERP")

    series = {gap.symbol: gap for gap in coverage_gaps(lake_root, "algo").series}

    assert series["ETH-PERP"].declared_rows == 1
    assert series["ETH-PERP"].observed_rows is None
    assert series["BTC-PERP"].missing_days == []


def test_coverage_gaps_unexpected_series_and_days_detected(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    lake = Lake(lake_root)
    lake.write_bars("algo", [_bar(T0)])
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    # Appended without regenerating the manifest.
    lake.write_bars("algo", [_bar(T0 + timedelta(days=1))])
    lake.write_bars("algo", [_bar(T0, symbol="ETH-PERP")])

    series = {gap.symbol: gap for gap in coverage_gaps(lake_root, "algo").series}

    assert series["BTC-PERP"].unexpected_days == ["2026-08-08"]
    assert series["BTC-PERP"].declared_rows == 1
    assert series["BTC-PERP"].observed_rows == 2
    assert series["ETH-PERP"].declared_rows is None
    assert series["ETH-PERP"].observed_rows == 1
    assert series["ETH-PERP"].unexpected_days == ["2026-08-07"]


def test_coverage_gaps_requires_manifest(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    Lake(lake_root).write_bars("algo", [_bar(T0)])

    with pytest.raises(ValueError, match="no manifest"):
        coverage_gaps(lake_root, "algo")


def test_coverage_gaps_rejects_foreign_manifest(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    lake = Lake(lake_root)
    lake.write_bars("algo", [_bar(T0)])
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    foreign = lake_root / "other"
    foreign.mkdir(parents=True)
    (foreign / "manifest.json").write_text(
        (lake_root / "algo" / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="does not match"):
        coverage_gaps(lake_root, "other")


def test_ingestion_and_detection_roundtrip(tmp_path: Path) -> None:
    """M3 exit criterion: ingested data, then missing observations detected."""
    lake_root = tmp_path / "lake"
    rows = []
    for day in range(3):
        rows += [_row(T0 + timedelta(days=day, minutes=index)) for index in range(3)]
    registry, _ = _fixture_registry(tmp_path, rows)
    ingestor = Ingestor(registry, lake_root)
    ingestor.ingest(_job())
    assert Lake(lake_root).dataset("algo").manifest.revision == 1

    # An interior day vanishes: lake quality sees the gap, the coverage
    # report names the missing day.
    shutil.rmtree(lake_root / "algo" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-08")
    quality = Lake(lake_root).quality(
        "algo", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP"
    )
    assert quality.gaps
    gap = coverage_gaps(lake_root, "algo").series[0]
    assert gap.missing_days == ["2026-08-08"]
    assert gap.observed_rows == 6
    assert gap.declared_rows == 9

    # Regeneration refuses to bless the loss: a manifest must never
    # declare less than it did before (possible data loss).
    with pytest.raises(ValueError, match="refusing to regenerate"):
        ManifestWriter(lake_root).generate("algo", source="fixture", license="test")

    # Restoring the missing day makes the dataset queryable again.
    lake = Lake(lake_root)
    lake.write_bars("algo", [_bar(T0 + timedelta(days=1, minutes=index)) for index in range(3)])
    ManifestWriter(lake_root).generate("algo", source="fixture", license="test")
    assert Lake(lake_root).dataset("algo").manifest.revision == 2
