"""Calendar-version compatibility through forecast and immutable replay seams."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from test_price_forecast import MODEL_VERSION, _binding, _series, _write_matching_lake

from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.demo.generators import analytical_history
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.seeder import _seed_price_forecasts
from quantmesh.instruments.contracts import HistoricalBar
from quantmesh.instruments.forecast import (
    PriceForecastRegistry,
    run_price_forecast,
    validate_price_forecast_artifact,
)


def _xnys_series(end: datetime, count: int = 20):
    dates = CalendarService().expected_bar_opens(
        "XNYS",
        end - timedelta(days=count * 2 + 20),
        end + timedelta(seconds=1),
        interval="1d",
        policy=SessionPolicy.REGULAR,
    )[-count:]
    base = _series(count)
    bars = tuple(
        bar.model_copy(update={"timestamp": stamp})
        for bar, stamp in zip(base.bars, dates, strict=True)
    )
    return base.model_copy(
        update={
            "bars": bars,
            "as_of": end,
            "generated_at": dates[-1],
            "coverage": base.coverage.model_copy(update={"start": dates[0], "end": dates[-1]}),
        }
    )


def _portable_evidence_digest(value):
    # Golden evidence was captured from a78ff0a before XNYS dispatch. Native
    # libm results differ by a few ULPs on Windows/Linux; normalize only floats
    # to ten significant digits with a ten-decimal-place floor for near-zero
    # residuals (relative error <= 5e-10 plus absolute error <= 5e-11). IDs, timestamps,
    # counts, eligibility and every other nonnumeric field remain exact.
    # Actual registry bytes are checked separately without normalization.
    def normalize(item):
        if isinstance(item, float):
            rounded = round(float(format(item, ".10g")), 10)
            return 0.0 if rounded == 0 else rounded
        if isinstance(item, dict):
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        return item

    encoded = json.dumps(normalize(value), sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_legacy_forecast_retains_pre_xnys_bytes_and_identity(tmp_path):
    series = _series()
    artifact = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)
    assert artifact.id == "forecast-88c268f0e7d9107203cc653a"
    # Native payload digests necessarily follow the native floating-point bytes.
    # Pin all underlying report/path/OOS evidence, not platform-specific digests.
    assert _portable_evidence_digest(
        artifact.model_dump(mode="json", exclude={"artifact_hashes"})
    ) == ("7bfd0b70e3f77b09ec25e9afbbad8bb907e8855a0506ced14f425c35432824eb")
    assert validate_price_forecast_artifact(artifact) == artifact
    lake = tmp_path / "lake"
    _write_matching_lake(lake, series)
    root = tmp_path / "registry"
    registry = PriceForecastRegistry(root, lake_root=lake, bindings=(_binding(series),))
    registry.record(artifact)
    saved = {name: (root / artifact.id / name).read_bytes() for name in artifact.artifact_hashes}
    restarted = PriceForecastRegistry(root, lake_root=lake, bindings=(_binding(series),))
    replayed = restarted.get(artifact.id)
    assert json.dumps(replayed.model_dump(mode="json"), sort_keys=True) == json.dumps(
        artifact.model_dump(mode="json"), sort_keys=True
    )
    assert dict(replayed.artifact_hashes) == dict(artifact.artifact_hashes)
    for name, content in saved.items():
        assert (root / artifact.id / name).read_bytes() == content
        if name != "report.json":
            assert hashlib.sha256(content).hexdigest() == artifact.artifact_hashes[name]


def test_xnys_age_skips_christmas_weekend_and_counts_missing_sessions():
    series = _xnys_series(datetime(2026, 12, 24, 5, tzinfo=UTC))
    holiday = run_price_forecast(
        series,
        generated_at=datetime(2026, 12, 27, 22, tzinfo=UTC),
        model_version="drift-conformal-xnys-v2",
        session_calendar="XNYS",
    )
    assert holiday.age_sessions == 0
    after_two_sessions = run_price_forecast(
        series,
        generated_at=datetime(2026, 12, 29, 22, tzinfo=UTC),
        model_version="drift-conformal-xnys-v2",
        session_calendar="XNYS",
    )
    assert after_two_sessions.age_sessions == 2
    assert "artifact age is 2 sessions; it exceeds one session" in after_two_sessions.blockers
    missing = series.model_copy(update={"bars": series.bars[:4] + series.bars[5:]})
    artifact = run_price_forecast(
        missing,
        generated_at=series.as_of,
        model_version="drift-conformal-xnys-v2",
        session_calendar="XNYS",
    )
    assert artifact.gap_count == 1
    assert "history contains 1 unexplained XNYS session gap(s)" in artifact.blockers


def test_xnys_config_fails_closed_for_unsupported_calendar_and_off_grid_history():
    series = _xnys_series(datetime(2026, 12, 24, 5, tzinfo=UTC))
    with pytest.raises(ValueError, match="unsupported forecast session calendar"):
        run_price_forecast(
            series, generated_at=series.as_of, model_version="v2", session_calendar="XHKG"
        )
    with pytest.raises(ValueError, match="requires an XNYS equity"):
        run_price_forecast(
            series.model_copy(update={"calendar": "XHKG"}),
            generated_at=series.as_of,
            model_version="v2",
            session_calendar="XNYS",
        )
    off_grid = series.model_copy(
        update={
            "bars": tuple(
                bar.model_copy(update={"timestamp": bar.timestamp - timedelta(hours=1)})
                for bar in series.bars
            )
        }
    )
    with pytest.raises(ValueError, match="outside the daily session grid"):
        run_price_forecast(
            off_grid, generated_at=series.as_of, model_version="v2", session_calendar="XNYS"
        )


def test_registry_restarts_and_replays_both_calendar_configurations(tmp_path):
    series = _xnys_series(datetime(2026, 12, 24, 5, tzinfo=UTC))
    lake = tmp_path / "lake"
    _write_matching_lake(lake, series)
    root = tmp_path / "registry"
    artifacts = tuple(
        run_price_forecast(
            series,
            generated_at=series.as_of,
            model_version="same-declared-version",
            session_calendar=selection,
        )
        for selection in ("legacy", "XNYS")
    )
    registry = PriceForecastRegistry(root, lake_root=lake, bindings=(_binding(series),))
    for artifact in artifacts:
        registry.record(artifact)
    reports = {
        artifact.id: (root / artifact.id / "report.json").read_bytes() for artifact in artifacts
    }
    restarted = PriceForecastRegistry(root, lake_root=lake, bindings=(_binding(series),))
    for artifact in artifacts:
        assert restarted.get(artifact.id) == artifact
        assert (root / artifact.id / "report.json").read_bytes() == reports[artifact.id]


def test_xnys_internal_validator_refuses_changed_projection_dates_and_age():
    series = _xnys_series(datetime(2026, 12, 24, 5, tzinfo=UTC))
    artifact = run_price_forecast(
        series,
        generated_at=series.as_of,
        model_version="v2",
        session_calendar="XNYS",
    )
    first_path = artifact.paths[0]
    wrong_first = first_path.points[0].model_copy(
        update={
            "timestamp": datetime(2026, 12, 25, 5, tzinfo=UTC),
        }
    )
    wrong_path = first_path.model_copy(update={"points": (wrong_first, *first_path.points[1:])})
    with pytest.raises(ValueError, match="XNYS projection dates"):
        validate_price_forecast_artifact(
            artifact.model_copy(update={"paths": (wrong_path, *artifact.paths[1:])})
        )
    with pytest.raises(ValueError, match="XNYS age"):
        validate_price_forecast_artifact(artifact.model_copy(update={"age_sessions": 1}))


@pytest.mark.parametrize("symbol", ["AAPL", "NVDA"])
def test_demo_xnys_history_has_650_coherent_completed_sessions(symbol):
    scenario = DemoScenario(anchor=datetime(2026, 12, 25, 12, tzinfo=UTC))
    spec = next(spec for spec in scenario.equities if spec.symbol == symbol)
    rows = analytical_history(scenario, spec, target_close=123.0, session_calendar="XNYS")
    daily = rows["1d"]
    assert len(daily) == 650
    assert daily[-1]["close"] == pytest.approx(123.0)
    assert daily[-1]["timestamp"] == datetime(2026, 12, 24, 5, tzinfo=UTC)
    calendar = CalendarService()
    for interval, observed in rows.items():
        expected = calendar.expected_bar_opens(
            "XNYS",
            observed[0]["timestamp"],
            scenario.anchor,
            interval=interval,
            policy=SessionPolicy.REGULAR,
        )
        assert tuple(row["timestamp"] for row in observed) == expected
    assert rows == analytical_history(scenario, spec, target_close=123.0, session_calendar="XNYS")
    base = _xnys_series(daily[-1]["timestamp"], count=650)
    instrument = base.instrument.model_copy(update={"symbol": symbol})
    series = base.model_copy(
        update={
            "instrument": instrument,
            "source": "demo-synthetic",
            "coverage": base.coverage.model_copy(update={"symbol": symbol}),
            "bars": tuple(HistoricalBar(instrument=instrument, **row) for row in daily),
        }
    )
    artifact = run_price_forecast(
        series,
        generated_at=scenario.anchor,
        model_version="demo-drift-conformal-xnys-v2",
        session_calendar="XNYS",
    )
    assert artifact.history_sessions == 650
    assert artifact.eligible
    assert artifact.gap_count == artifact.age_sessions == 0


def test_legacy_demo_generator_keeps_original_bytes():
    scenario = DemoScenario()
    history = analytical_history(scenario, scenario.equities[0])
    assert _portable_evidence_digest(history) == (
        "c4d23358a523219215ce1fc56129d7eb610b2d7110f013345d85c6f6f574967d"
    )
    assert json.dumps(history, sort_keys=True, default=str) == json.dumps(
        analytical_history(scenario, scenario.equities[0]), sort_keys=True, default=str
    )


def test_scoped_demo_seeder_labels_and_reopens_xnys_forecasts(tmp_path):
    # Only the two forecast datasets are needed; avoid the full demo/account seeder.
    scenario = DemoScenario(anchor=datetime(2026, 12, 25, 12, tzinfo=UTC))
    lake = tmp_path / "lake"
    bindings = []
    for symbol in ("AAPL", "NVDA"):
        series = _xnys_series(datetime(2026, 12, 24, 5, tzinfo=UTC))
        instrument = series.instrument.model_copy(update={"symbol": symbol})
        series = series.model_copy(
            update={
                "instrument": instrument,
                "bars": tuple(
                    bar.model_copy(update={"instrument": instrument}) for bar in series.bars
                ),
                "coverage": series.coverage.model_copy(update={"symbol": symbol}),
                "dataset_id": f"demo-moomoo-{symbol.lower()}",
                "source": "demo-synthetic",
                "license": "QuantMesh deterministic demo",
            }
        )
        _write_matching_lake(lake, series)
        bindings.append(_binding(series))
    registry = _seed_price_forecasts(scenario, tmp_path, lake, tuple(bindings))
    artifacts = registry.all()
    assert {artifact.instrument.symbol for artifact in artifacts} == {"AAPL", "NVDA"}
    for artifact in artifacts:
        assert artifact.source == "demo-synthetic"
        assert artifact.model_version == "demo-drift-conformal-xnys-v2"
        assert artifact.gap_count == artifact.age_sessions == 0
        assert artifact.paths[0].points[0].timestamp == datetime(2026, 12, 28, 5, tzinfo=UTC)
        assert registry.get(artifact.id) == artifact


@pytest.mark.parametrize(
    ("end", "first", "seventh"),
    [
        ("2026-12-24T05:00:00+00:00", "2026-12-28T05:00:00+00:00", "2027-01-06T05:00:00+00:00"),
        ("2026-03-06T05:00:00+00:00", "2026-03-09T04:00:00+00:00", "2026-03-17T04:00:00+00:00"),
    ],
)
def test_xnys_forecast_uses_holidays_and_ny_daily_grid_across_dst(end, first, seventh):
    series = _xnys_series(datetime.fromisoformat(end))
    artifact = run_price_forecast(
        series,
        generated_at=series.as_of,
        model_version="drift-conformal-xnys-v2",
        session_calendar="XNYS",
    )
    legacy = run_price_forecast(series, generated_at=series.as_of, model_version=MODEL_VERSION)
    assert artifact.config_digest != legacy.config_digest
    assert artifact.paths[0].points[0].timestamp == datetime.fromisoformat(first)
    assert artifact.paths[0].points[-1].timestamp == datetime.fromisoformat(seventh)
    assert artifact.gap_count == 0
    assert artifact.age_sessions == 0
    assert "exchange-calendars:4.13.2:XNYS" in " ".join(artifact.limitations)
    assert validate_price_forecast_artifact(artifact) == artifact
