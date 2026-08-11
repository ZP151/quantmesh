from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.contracts import (
    CoverageSnapshot,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    PriceForecastArtifact,
)
from quantmesh.instruments.forecast import (
    PriceForecastRegistry,
    rolling_oos_forecasts,
    run_price_forecast,
)

MODEL_VERSION = "drift-conformal-v1"
NVDA = Instrument(
    symbol="NVDA",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)
BTC = Instrument(
    symbol="BTC-PERP",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
    currency="USD",
)


def _dates(count: int, *, crypto: bool = False) -> list[datetime]:
    value = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
    result: list[datetime] = []
    while len(result) < count:
        if crypto or value.weekday() < 5:
            result.append(value)
        value += timedelta(days=1)
    return result


def _series(
    count: int = 420,
    *,
    instrument: Instrument = NVDA,
    generated_at: datetime | None = None,
    gaps: tuple[datetime, ...] = (),
    duplicates: tuple[datetime, ...] = (),
) -> HistoricalSeries:
    crypto = instrument.venue is Venue.HYPERLIQUID
    dates = _dates(count, crypto=crypto)
    prices = [
        100.0
        * math.exp(0.0008 * index + 0.018 * math.sin(index / 9.0) + 0.007 * math.cos(index / 4.0))
        for index in range(count)
    ]
    bars = tuple(
        HistoricalBar(
            instrument=instrument,
            timestamp=timestamp,
            interval="1d",
            open=price * 0.998,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=1_000_000 + index,
        )
        for index, (timestamp, price) in enumerate(zip(dates, prices, strict=True))
    )
    stamp = generated_at or dates[-1]
    return HistoricalSeries(
        instrument=instrument,
        range=HistoryRange.ONE_YEAR,
        as_of=stamp,
        bars=bars,
        dataset_id="forecast-fixture",
        dataset_revision=7,
        source="operator-import",
        license="operator-supplied",
        generated_at=dates[-1],
        interval="1d",
        calendar="24/7" if crypto else "XNYS",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval="1d",
            venue=instrument.venue,
            symbol=instrument.symbol,
            start=dates[0],
            end=dates[-1],
            rows=count,
        ),
        gaps=gaps,
        duplicates=duplicates,
    )


def test_forecast_has_three_horizons_quantiles_and_lineage() -> None:
    series = _series()

    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)

    assert [path.sessions for path in artifact.paths] == [7, 30, 126]
    assert all(len(path.points) == path.sessions for path in artifact.paths)
    assert all(
        point.p025 <= point.p10 <= point.p25 <= point.p50 <= point.p75 <= point.p90 <= point.p975
        for path in artifact.paths
        for point in path.points
    )
    assert artifact.dataset_id == series.dataset_id
    assert artifact.dataset_revision == series.dataset_revision
    assert artifact.source == series.source
    assert artifact.train_start == series.bars[0].timestamp
    assert artifact.train_end == series.bars[-1].timestamp
    assert artifact.model_version == MODEL_VERSION
    assert artifact.benchmark_name == "last-price-random-walk"
    assert artifact.eligible == (artifact.blockers == ())
    assert set(artifact.artifact_hashes) == {"report.json", "paths.csv", "oos.csv"}
    assert all(len(value) == 64 for value in artifact.artifact_hashes.values())


def test_artifact_is_deeply_frozen_and_self_consistent() -> None:
    artifact = run_price_forecast(
        _series(), generated_at=_series().as_of, model_version=MODEL_VERSION
    )

    with pytest.raises(Exception):
        artifact.blockers += ("changed",)
    with pytest.raises(Exception):
        artifact.artifact_hashes["report.json"] = "0" * 64
    assert PriceForecastArtifact.model_validate_json(artifact.model_dump_json()) == artifact


def test_future_flip_does_not_change_earlier_oos_predictions() -> None:
    bars = _series().bars
    original = rolling_oos_forecasts(bars, horizon=30)
    cutoff = len(bars) - 30
    changed = tuple(
        bar
        if index < cutoff
        else bar.model_copy(
            update={
                "open": bar.open * 4,
                "high": bar.high * 4,
                "low": bar.low * 4,
                "close": bar.close * 4,
            }
        )
        for index, bar in enumerate(bars)
    )
    flipped = rolling_oos_forecasts(changed, horizon=30)

    unaffected = [row for row in original if row.target_at < bars[cutoff].timestamp]
    assert flipped[: len(unaffected)] == tuple(unaffected)


def test_first_oos_origin_uses_exactly_252_preceding_returns() -> None:
    bars = _series().bars
    rows = rolling_oos_forecasts(bars, horizon=7)
    closes = [bar.close for bar in bars]
    expected_drift = sorted(math.log(closes[index] / closes[index - 1]) for index in range(1, 253))
    midpoint = len(expected_drift) // 2
    expected_median = (expected_drift[midpoint - 1] + expected_drift[midpoint]) / 2

    assert rows[0].origin_at == bars[252].timestamp
    assert rows[0].predicted == pytest.approx(bars[252].close * math.exp(expected_median * 7))


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (314, "history has 314 sessions; at least 315 are required"),
        (315, "126-session horizon has 0 residuals; at least 12 are required"),
    ],
)
def test_insufficient_history_is_reported_as_an_ineligible_artifact(
    count: int, expected: str
) -> None:
    series = _series(count)

    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)

    assert artifact.eligible is False
    assert expected in artifact.blockers
    assert [metric.residual_count for metric in artifact.metrics] == [
        max(0, count - 252 - horizon) for horizon in (7, 30, 126)
    ]


def test_gap_duplicate_and_stale_artifact_each_fail_closed() -> None:
    baseline = _series()
    gap = baseline.bars[100].timestamp
    broken = baseline.model_copy(update={"gaps": (gap,), "duplicates": (gap,)})
    stale_at = baseline.bars[-1].timestamp + timedelta(days=5)
    stale = baseline.model_copy(update={"as_of": stale_at})

    quality = run_price_forecast(broken, generated_at=broken.as_of, model_version=MODEL_VERSION)
    old = run_price_forecast(stale, generated_at=stale_at, model_version=MODEL_VERSION)

    assert any("gap" in blocker for blocker in quality.blockers)
    assert any("duplicate" in blocker for blocker in quality.blockers)
    assert any("one session" in blocker for blocker in old.blockers)


def test_weekday_gap_is_detected_even_when_history_service_could_not_check_calendar() -> None:
    baseline = _series()
    bars = baseline.bars[:80] + baseline.bars[81:]
    coverage = baseline.coverage.model_copy(update={"rows": len(bars), "end": bars[-1].timestamp})
    series = baseline.model_copy(update={"bars": bars, "coverage": coverage})

    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)

    assert any("unexplained weekday gap" in blocker for blocker in artifact.blockers)


def test_live_tail_and_non_daily_inputs_are_refused_not_relabelled() -> None:
    baseline = _series()
    live = baseline.bars[-1].model_copy(update={"is_live_tail": True})
    object.__setattr__(live, "live_lineage", object())
    contaminated = baseline.model_copy(update={"bars": baseline.bars[:-1] + (live,)})

    with pytest.raises(ValueError, match="live-tail"):
        run_price_forecast(
            contaminated,
            generated_at=contaminated.as_of,
            model_version=MODEL_VERSION,
        )


def test_crypto_future_path_uses_every_calendar_day_and_equity_skips_weekends() -> None:
    crypto = _series(instrument=BTC)
    equity = _series()

    crypto_artifact = run_price_forecast(
        crypto, generated_at=crypto.as_of, model_version=MODEL_VERSION
    )
    equity_artifact = run_price_forecast(
        equity, generated_at=equity.as_of, model_version=MODEL_VERSION
    )

    crypto_dates = [point.timestamp for point in crypto_artifact.paths[0].points]
    equity_dates = [point.timestamp for point in equity_artifact.paths[0].points]
    assert all(
        (right - left) == timedelta(days=1) for left, right in zip(crypto_dates, crypto_dates[1:])
    )
    assert all(item.weekday() < 5 for item in equity_dates)


def _write_matching_lake(root: Path, series: HistoricalSeries) -> None:
    lake = Lake(root)
    lake.write_bars(
        series.dataset_id,
        [
            Bar(
                instrument=bar.instrument,
                timestamp=bar.timestamp,
                interval=bar.interval,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in series.bars
        ],
    )
    ManifestWriter(root).generate(
        series.dataset_id,
        source=series.source,
        license=series.license,
        revision=series.dataset_revision,
        generated_at=series.generated_at,
    )


def test_registry_writes_byte_stable_artifacts_and_re_resolves_dataset_pin(
    tmp_path: Path,
) -> None:
    series = _series()
    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)
    lake_root = tmp_path / "lake"
    _write_matching_lake(lake_root, series)
    first = PriceForecastRegistry(tmp_path / "one", lake_root=lake_root)
    second = PriceForecastRegistry(tmp_path / "two", lake_root=lake_root)

    first.record(artifact)
    second.record(artifact)

    assert first.get(artifact.id) == artifact
    for name in ("report.json", "paths.csv", "oos.csv"):
        assert (tmp_path / "one" / artifact.id / name).read_bytes() == (
            tmp_path / "two" / artifact.id / name
        ).read_bytes()
    assert first.resolve_pin(artifact).manifest.revision == 7
    with pytest.raises(ValueError, match="already recorded"):
        first.record(artifact)


@pytest.mark.parametrize("name", ["report.json", "paths.csv", "oos.csv"])
def test_registry_rejects_missing_or_tampered_artifact_file(tmp_path: Path, name: str) -> None:
    series = _series()
    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)
    lake_root = tmp_path / "lake"
    _write_matching_lake(lake_root, series)
    registry = PriceForecastRegistry(tmp_path / "registry", lake_root=lake_root)
    registry.record(artifact)
    path = tmp_path / "registry" / artifact.id / name
    if name == "report.json":
        path.write_text("{}\n", encoding="utf-8")
    else:
        path.unlink()

    with pytest.raises(ValueError, match=name):
        registry.get(artifact.id)


def test_registry_refuses_a_manifest_revision_that_moved(tmp_path: Path) -> None:
    series = _series()
    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)
    lake_root = tmp_path / "lake"
    _write_matching_lake(lake_root, series)
    registry = PriceForecastRegistry(tmp_path / "registry", lake_root=lake_root)
    registry.record(artifact)
    manifest_path = lake_root / series.dataset_id / "manifest.json"
    payload = manifest_path.read_text(encoding="utf-8").replace('"revision": 7', '"revision": 8')
    manifest_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="pin asks for revision 7"):
        registry.resolve_pin(artifact)


def test_generated_at_and_model_version_are_part_of_identity() -> None:
    series = _series()
    original = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)
    later = run_price_forecast(
        series,
        generated_at=series.as_of + timedelta(hours=1),
        model_version=MODEL_VERSION,
    )
    changed_model = run_price_forecast(
        series, generated_at=series.as_of, model_version="drift-conformal-v2"
    )

    assert len({original.id, later.id, changed_model.id}) == 3
