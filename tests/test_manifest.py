import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import (
    MANIFEST_NAME,
    DatasetClass,
    DatasetManifest,
    ManifestWriter,
)
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

BTC = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
AAPL = Instrument(
    symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
)
T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


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


def manifest_path(root: Path, dataset: str) -> Path:
    return root / dataset / MANIFEST_NAME


def test_generate_writes_versioned_manifest(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])

    manifest = ManifestWriter(tmp_path).generate(
        "ds", source="hyperliquid fixture", license="fixture-only"
    )

    assert manifest_path(tmp_path, "ds").exists()
    assert manifest.schema_version == 1
    assert manifest.dataset == "ds"
    assert manifest.source == "hyperliquid fixture"
    assert manifest.license == "fixture-only"
    assert manifest.timezone == "UTC"
    assert manifest.revision == 1
    assert manifest.generated_at.tzinfo is UTC


def test_manifest_roundtrips_through_json(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    manifest = ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    parsed = DatasetManifest.model_validate_json(manifest_path(tmp_path, "ds").read_text())

    assert parsed == manifest


def test_legacy_manifest_without_dataset_class_remains_compatible(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload.pop("data_class", None)
    manifest_path(tmp_path, "ds").write_text(json.dumps(payload), encoding="utf-8")

    parsed = Lake(tmp_path).dataset("ds").manifest

    assert parsed.data_class is None


def test_generate_records_structured_dataset_class(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])

    manifest = ManifestWriter(tmp_path).generate(
        "ds",
        source="operator-import",
        license="operator-supplied",
        data_class=DatasetClass.OBSERVED,
    )

    assert manifest.data_class is DatasetClass.OBSERVED


def test_regenerate_preserves_existing_dataset_class_when_unspecified(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    writer = ManifestWriter(tmp_path)
    writer.generate(
        "ds",
        source="operator-import",
        license="operator-supplied",
        data_class=DatasetClass.OBSERVED,
    )

    regenerated = writer.generate(
        "ds",
        source="operator-import",
        license="operator-supplied",
    )

    assert regenerated.data_class is DatasetClass.OBSERVED


def test_coverage_reflects_lake(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars(
        "ds",
        [
            bar(),
            bar(timestamp=T0 + timedelta(minutes=1)),
            bar(instrument=AAPL),
        ],
    )

    manifest = ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    assert len(manifest.coverage) == 2
    btc = next(c for c in manifest.coverage if c.symbol == "BTC-PERP")
    assert btc.interval == "1m"
    assert btc.venue == Venue.HYPERLIQUID
    assert btc.rows == 2
    assert btc.start == T0
    assert btc.end == T0 + timedelta(minutes=1)
    assert all(c.start.tzinfo is UTC and c.end.tzinfo is UTC for c in manifest.coverage)


def test_generate_bumps_revision_on_regenerate(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    writer = ManifestWriter(tmp_path)

    assert writer.generate("ds", source="s", license="l").revision == 1
    assert writer.generate("ds", source="s", license="l").revision == 2
    assert writer.generate("ds", source="s", license="l").revision == 3


def test_generate_accepts_explicit_revision(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])

    manifest = ManifestWriter(tmp_path).generate("ds", source="s", license="l", revision=7)

    assert manifest.revision == 7


def test_generate_rejects_blank_source_or_license(tmp_path: Path) -> None:
    (tmp_path / "ds").mkdir()
    writer = ManifestWriter(tmp_path)

    with pytest.raises(ValueError, match="source"):
        writer.generate("ds", source="  ", license="l")
    with pytest.raises(ValueError, match="license"):
        writer.generate("ds", source="s", license=" ")


def test_generate_rejects_invalid_dataset_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dataset"):
        ManifestWriter(tmp_path).generate("../evil", source="s", license="l")


def test_generate_fails_closed_on_unreadable_existing_manifest(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    manifest_path(tmp_path, "ds").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable"):
        ManifestWriter(tmp_path).generate("ds", source="s", license="l")


def _payload(tmp_path: Path, dataset: str = "ds") -> dict[str, object]:
    lake = Lake(tmp_path)
    lake.write_bars(dataset, [bar()])
    ManifestWriter(tmp_path).generate(dataset, source="s", license="l")
    return json.loads(manifest_path(tmp_path, dataset).read_text(encoding="utf-8"))


@pytest.mark.parametrize("bad", [2, 0, -1])
def test_validation_rejects_unknown_schema_version(tmp_path: Path, bad: int) -> None:
    payload = _payload(tmp_path)
    payload["schema_version"] = bad

    with pytest.raises(ValidationError, match="schema_version"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_non_utc_timezone(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["timezone"] = "Asia/Singapore"

    with pytest.raises(ValidationError, match="UTC"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_bad_dataset_name(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["dataset"] = "UpPer"

    with pytest.raises(ValidationError, match="dataset"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_naive_generated_at(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["generated_at"] = "2026-08-07T12:00:00"

    with pytest.raises(ValidationError, match="aware"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_naive_coverage_timestamps(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["coverage"][0]["start"] = "2026-08-07T12:00:00"

    with pytest.raises(ValidationError, match="aware"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_coverage_start_after_end(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    entry = payload["coverage"][0]
    entry["end"] = "2026-08-07T11:00:00+00:00"

    with pytest.raises(ValidationError, match="after end"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_duplicate_coverage_entries(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["coverage"].append(dict(payload["coverage"][0]))

    with pytest.raises(ValidationError, match="duplicate"):
        DatasetManifest.model_validate(payload)


def test_validation_rejects_bad_symbol_in_coverage(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["coverage"][0]["symbol"] = "../x"

    with pytest.raises(ValidationError, match="symbol"):
        DatasetManifest.model_validate(payload)


def test_gate_requires_manifest(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])

    with pytest.raises(ValueError, match="manifest"):
        lake.dataset("ds")


def test_gate_opens_generated_dataset(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    dataset = lake.dataset("ds")

    assert dataset.manifest.revision == 1
    assert dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP") == [bar()]
    report = dataset.quality(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    assert report.rows == 1


def test_gate_rejects_stale_manifest_after_data_change(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])

    with pytest.raises(ValueError, match="stale"):
        lake.dataset("ds")


def test_gate_rejects_stale_manifest_after_new_series(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar(instrument=AAPL)])

    with pytest.raises(ValueError, match="stale"):
        lake.dataset("ds")


def test_gate_reopens_after_regenerate(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    writer = ManifestWriter(tmp_path)
    lake.write_bars("ds", [bar()])
    writer.generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    writer.generate("ds", source="s", license="l")

    dataset = lake.dataset("ds")

    assert dataset.manifest.revision == 2
    assert len(dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")) == 2


def test_gate_rejects_manifest_for_another_dataset(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    payload = json.loads(manifest_path(tmp_path, "ds").read_text(encoding="utf-8"))
    payload["dataset"] = "other"
    manifest_path(tmp_path, "ds").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        lake.dataset("ds")


def test_gate_rejects_corrupt_manifest(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    manifest_path(tmp_path, "ds").write_text("{nope", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid"):
        lake.dataset("ds")


def test_gate_rejects_stale_manifest_same_rows_different_range(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars(
        "ds",
        [
            bar(timestamp=T0 + timedelta(minutes=5)),
            bar(timestamp=T0 + timedelta(minutes=6)),
        ],
    )

    with pytest.raises(ValueError, match="stale"):
        lake.dataset("ds")


def test_gate_rejects_stale_after_series_removal(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(instrument=AAPL)])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.shard_file("ds", "1m", Venue.HYPERLIQUID, "BTC-PERP", "2026-08-07").unlink()

    with pytest.raises(ValueError, match="stale"):
        lake.dataset("ds")


def test_microsecond_timestamps_roundtrip_through_gate(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    precise = T0 + timedelta(microseconds=123456)
    lake.write_bars("ds", [bar(timestamp=precise)])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    dataset = lake.dataset("ds")

    assert dataset.read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP") == [
        bar(timestamp=precise)
    ]


def test_generate_default_bumps_after_explicit_revision(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    writer = ManifestWriter(tmp_path)

    assert writer.generate("ds", source="s", license="l", revision=7).revision == 7
    assert writer.generate("ds", source="s", license="l").revision == 8


def test_generate_empty_dataset_writes_empty_coverage(tmp_path: Path) -> None:
    (tmp_path / "ds").mkdir()

    manifest = ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    assert manifest.coverage == []
    dataset = Lake(tmp_path).dataset("ds")
    assert dataset.manifest.revision == 1


def test_generate_rejects_nonexistent_dataset(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        ManifestWriter(tmp_path).generate("ds", source="s", license="l")


def test_generate_skips_stray_files_but_rejects_stray_dirs(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    writer = ManifestWriter(tmp_path)
    writer.generate("ds", source="s", license="l")
    (tmp_path / "ds" / "readme.txt").write_text("notes", encoding="utf-8")

    manifest = writer.generate("ds", source="s", license="l")

    assert len(manifest.coverage) == 1
    (tmp_path / "ds" / "notes").mkdir()
    with pytest.raises(ValueError, match="unsupported interval"):
        writer.generate("ds", source="s", license="l")


def test_generate_rejects_manifest_for_another_dataset(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    payload = json.loads(manifest_path(tmp_path, "ds").read_text(encoding="utf-8"))
    payload["dataset"] = "other"
    manifest_path(tmp_path, "ds").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="is for dataset"):
        ManifestWriter(tmp_path).generate("ds", source="s", license="l")


def test_generate_rejects_invalid_explicit_revision(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    writer = ManifestWriter(tmp_path)

    with pytest.raises(ValueError, match="revision"):
        writer.generate("ds", source="s", license="l", revision=0)
    with pytest.raises(ValueError, match="revision"):
        writer.generate("ds", source="s", license="l", revision=-1)


def test_symlinks_in_lake_layout_are_rejected(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar()])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    day_dir = tmp_path / "ds" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-07"
    link = tmp_path / "ds" / "1m" / "hyperliquid" / "BTC-PERP" / "2026-08-08"
    try:
        os.symlink(day_dir, link)
    except OSError:
        pytest.skip("cannot create symlinks on this machine")

    with pytest.raises(ValueError, match="symlink"):
        ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    with pytest.raises(ValueError, match="symlink"):
        lake.read_bars("ds", interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")


def test_generate_refuses_vanished_series(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(instrument=AAPL)])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    shutil.rmtree(tmp_path / "ds" / "1m" / "moomoo")

    with pytest.raises(ValueError, match="vanished"):
        ManifestWriter(tmp_path).generate("ds", source="s", license="l")


def test_generate_refuses_unrewritten_rows_shrink(tmp_path: Path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar()])  # same day shard rewritten with one bar

    with pytest.raises(ValueError, match="rows shrank"):
        ManifestWriter(tmp_path).generate("ds", source="s", license="l")


def test_generate_allows_rewritten_rows_shrink(tmp_path: Path) -> None:
    """A series rebuilt from an authoritative source may lose rows (retraction)."""
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar()])

    manifest = ManifestWriter(tmp_path).generate(
        "ds",
        source="s",
        license="l",
        rewritten=frozenset({("1m", Venue.HYPERLIQUID, "BTC-PERP")}),
    )

    assert manifest.revision == 2
    assert manifest.coverage[0].rows == 1


def test_generate_refuses_rewritten_start_forward(tmp_path: Path) -> None:
    """A rewritten series whose start moved forward would bless an interior loss."""
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar(timestamp=T0 + timedelta(minutes=1))])

    with pytest.raises(ValueError, match="start moved forward"):
        ManifestWriter(tmp_path).generate(
            "ds",
            source="s",
            license="l",
            rewritten=frozenset({("1m", Venue.HYPERLIQUID, "BTC-PERP")}),
        )


def test_generate_allows_growth_and_new_series(tmp_path: Path) -> None:
    """Growth must keep the full day shard: wholesale replacement means a
    rewrite that omits earlier ticks would move the start forward."""
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars(
        "ds",
        [
            bar(),
            bar(timestamp=T0 + timedelta(minutes=1)),
            bar(timestamp=T0 + timedelta(minutes=2)),
            bar(instrument=AAPL),
        ],
    )

    manifest = ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    assert manifest.revision == 2
    assert {entry.symbol for entry in manifest.coverage} == {"BTC-PERP", "AAPL"}
    btc = next(entry for entry in manifest.coverage if entry.symbol == "BTC-PERP")
    assert btc.rows == 3
    assert btc.start == T0


def test_generate_override_by_removing_manifest(tmp_path: Path) -> None:
    """Removing the manifest is the explicit recovery for deliberate changes."""
    lake = Lake(tmp_path)
    lake.write_bars("ds", [bar(), bar(timestamp=T0 + timedelta(minutes=1))])
    ManifestWriter(tmp_path).generate("ds", source="s", license="l")
    lake.write_bars("ds", [bar()])
    (tmp_path / "ds" / MANIFEST_NAME).unlink()

    manifest = ManifestWriter(tmp_path).generate("ds", source="s", license="l")

    assert manifest.revision == 1
    assert manifest.coverage[0].rows == 1
