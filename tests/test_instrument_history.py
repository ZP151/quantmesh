from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import DatasetManifest, ManifestWriter, SeriesCoverage
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.contracts import (
    ComparisonPoint,
    ComparisonSeries,
    DatasetBinding,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
)
from quantmesh.instruments.history import HistoryService

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)
NVDA = Instrument(
    symbol="NVDA",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)
AAPL = Instrument(
    symbol="AAPL",
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


def bar(
    instrument: Instrument = NVDA,
    *,
    timestamp: datetime = NOW,
    interval: str = "1d",
    close: float = 100.0,
) -> Bar:
    return Bar(
        instrument=instrument,
        timestamp=timestamp,
        interval=interval,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=1_000.0,
    )


def binding(
    symbol: str = "NVDA",
    *,
    dataset_id: str = "equities",
    interval: str = "1d",
    venue: Venue = Venue.MOOMOO,
) -> DatasetBinding:
    return DatasetBinding(
        dataset_id=dataset_id,
        interval=interval,
        venue=venue,
        symbol=symbol,
        calendar="XNYS" if venue is Venue.MOOMOO else "24/7",
        adjustment="unadjusted",
    )


def manifest(
    *coverages: SeriesCoverage,
    dataset_id: str = "equities",
    revision: int = 7,
) -> DatasetManifest:
    return DatasetManifest(
        dataset=dataset_id,
        source="operator-import",
        license="operator-supplied",
        revision=revision,
        generated_at=GENERATED_AT,
        coverage=list(coverages),
    )


class FakeDataset:
    def __init__(
        self,
        name: str,
        dataset_manifest: DatasetManifest,
        rows: dict[tuple[str, Venue, str], list[Any]],
        *,
        ignore_window: bool = False,
    ) -> None:
        self.name = name
        self.manifest = dataset_manifest
        self._rows = rows
        self._ignore_window = ignore_window
        self.calls: list[dict[str, Any]] = []

    def read_bars(
        self,
        *,
        interval: str,
        venue: Venue,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Any]:
        self.calls.append(
            {
                "interval": interval,
                "venue": venue,
                "symbol": symbol,
                "start": start,
                "end": end,
            }
        )
        result = list(self._rows.get((interval, venue, symbol), []))
        if self._ignore_window:
            return result
        return [
            row
            for row in result
            if (start is None or row.timestamp >= start) and (end is None or row.timestamp <= end)
        ]


def coverage(
    symbol: str,
    *,
    interval: str = "1d",
    venue: Venue = Venue.MOOMOO,
    start: datetime = NOW - timedelta(days=400),
    end: datetime = NOW,
    rows: int = 401,
) -> SeriesCoverage:
    return SeriesCoverage(
        interval=interval,
        venue=venue,
        symbol=symbol,
        start=start,
        end=end,
        rows=rows,
    )


def fake_service(
    bindings: list[DatasetBinding],
    datasets: dict[str, FakeDataset],
) -> HistoryService:
    return HistoryService(bindings, dataset_loader=datasets.__getitem__, now=lambda: NOW)


def test_history_ranges_are_the_public_wire_values() -> None:
    assert [item.value for item in HistoryRange] == ["1d", "5d", "1m", "3m", "6m", "1y"]
    assert HistoryRange.SIX_MONTHS.value == "6m"
    assert HistoryRange.ONE_YEAR.value == "1y"


def test_history_is_manifest_gated_venue_aware_chronological_and_provenanced() -> None:
    rows = [
        bar(timestamp=NOW - timedelta(days=2), close=100),
        bar(timestamp=NOW - timedelta(days=1), close=102),
        bar(timestamp=NOW, close=101),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA")),
        {("1d", Venue.MOOMOO, "NVDA"): rows},
    )
    service = fake_service([binding()], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)

    assert series.instrument == NVDA
    assert series.dataset_id == "equities"
    assert series.dataset_revision == 7
    assert series.source == "operator-import"
    assert series.license == "operator-supplied"
    assert series.generated_at == GENERATED_AT
    assert series.interval == "1d"
    assert series.calendar == "XNYS"
    assert series.adjustment == "unadjusted"
    assert series.coverage == coverage("NVDA")
    assert series.gaps == []
    assert series.duplicates == []
    assert series.limitations == []
    assert series.resolution_fallback is None
    assert [item.timestamp for item in series.bars] == [row.timestamp for row in rows]
    assert all(item.is_live_tail is False for item in series.bars)
    assert all(item.adjusted_close is None for item in series.bars)
    assert dataset.calls == [
        {
            "interval": "1d",
            "venue": Venue.MOOMOO,
            "symbol": "NVDA",
            "start": NOW - timedelta(days=186),
            "end": NOW,
        }
    ]


def test_history_uses_explicit_as_of_inclusively_and_normalizes_to_utc() -> None:
    eastern = timezone(timedelta(hours=-4))
    as_of = datetime(2026, 8, 12, 12, 0, tzinfo=eastern)
    start = as_of.astimezone(UTC) - timedelta(days=1)
    rows = [
        bar(timestamp=start.astimezone(eastern), interval="5m", close=99),
        bar(timestamp=as_of, interval="5m", close=101),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", interval="5m", start=start, end=NOW)),
        {("5m", Venue.MOOMOO, "NVDA"): rows},
    )
    service = fake_service([binding(interval="5m")], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.ONE_DAY, as_of=as_of)

    assert series.as_of == NOW
    assert [item.timestamp for item in series.bars] == [start, NOW]
    assert all(item.timestamp.tzinfo is UTC for item in series.bars)


@pytest.mark.parametrize(
    ("requested", "preferred"),
    [
        (HistoryRange.ONE_DAY, "5m"),
        (HistoryRange.FIVE_DAYS, "30m"),
        (HistoryRange.ONE_MONTH, "1h"),
        (HistoryRange.THREE_MONTHS, "1d"),
        (HistoryRange.SIX_MONTHS, "1d"),
        (HistoryRange.ONE_YEAR, "1d"),
    ],
)
def test_range_selects_the_planned_preferred_interval(
    requested: HistoryRange, preferred: str
) -> None:
    row = bar(timestamp=NOW, interval=preferred)
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", interval=preferred)),
        {(preferred, Venue.MOOMOO, "NVDA"): [row]},
    )
    service = fake_service([binding(interval=preferred)], {"equities": dataset})

    assert service.history(Venue.MOOMOO, "NVDA", requested).interval == preferred


def test_history_uses_only_the_nearest_coarser_fallback_and_records_it() -> None:
    rows_30m = [
        bar(timestamp=NOW - timedelta(minutes=30), interval="30m"),
        bar(timestamp=NOW, interval="30m"),
    ]
    rows_1h = [bar(timestamp=NOW, interval="1h")]
    dataset = FakeDataset(
        "equities",
        manifest(
            coverage("NVDA", interval="30m"),
            coverage("NVDA", interval="1h"),
        ),
        {
            ("30m", Venue.MOOMOO, "NVDA"): rows_30m,
            ("1h", Venue.MOOMOO, "NVDA"): rows_1h,
        },
    )
    service = fake_service(
        [binding(interval="1h"), binding(interval="30m")], {"equities": dataset}
    )

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.ONE_DAY)

    assert series.interval == "30m"
    assert series.resolution_fallback == "5m->30m"
    assert dataset.calls[0]["interval"] == "30m"


def test_history_never_falls_back_to_a_finer_interval() -> None:
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", interval="5m")),
        {("5m", Venue.MOOMOO, "NVDA"): [bar(interval="5m")]},
    )
    service = fake_service([binding(interval="5m")], {"equities": dataset})

    with pytest.raises(ValueError, match="preferred or coarser"):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.ONE_MONTH)


def test_history_refuses_ambiguous_same_resolution_bindings() -> None:
    bindings = [binding(dataset_id="one"), binding(dataset_id="two")]

    with pytest.raises(ValueError, match="ambiguous"):
        HistoryService(bindings, dataset_loader=lambda _: None, now=lambda: NOW)


@pytest.mark.parametrize(
    ("venue", "symbol"),
    [(Venue.HYPERLIQUID, "NVDA"), (Venue.MOOMOO, "UNKNOWN")],
)
def test_history_refuses_unknown_venue_or_symbol(venue: Venue, symbol: str) -> None:
    service = HistoryService(
        [binding()], dataset_loader=lambda _: pytest.fail("must not load"), now=lambda: NOW
    )

    with pytest.raises(ValueError, match="unknown venue/symbol"):
        service.history(venue, symbol, HistoryRange.SIX_MONTHS)


def test_history_reopens_the_dataset_and_refuses_a_stale_manifest(tmp_path) -> None:
    lake = Lake(tmp_path)
    lake.write_bars("equities", [bar(timestamp=NOW - timedelta(days=1))])
    ManifestWriter(tmp_path).generate(
        "equities",
        source="fixture",
        license="fixture-only",
        generated_at=GENERATED_AT,
    )
    service = HistoryService(
        [binding()], dataset_loader=lake.dataset, now=lambda: NOW
    )
    assert service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS).bars

    lake.write_bars("equities", [bar(timestamp=NOW)])

    with pytest.raises(ValueError, match="manifest is stale"):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


def test_history_refuses_manifest_without_the_bound_coverage() -> None:
    dataset = FakeDataset("equities", manifest(coverage("AAPL")), {})
    service = fake_service([binding()], {"equities": dataset})

    with pytest.raises(ValueError, match="manifest coverage"):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


def test_history_refuses_loader_identity_or_manifest_identity_drift() -> None:
    wrong_name = FakeDataset(
        "other",
        manifest(coverage("NVDA"), dataset_id="equities"),
        {("1d", Venue.MOOMOO, "NVDA"): [bar()]},
    )
    wrong_manifest = FakeDataset(
        "equities",
        manifest(coverage("NVDA"), dataset_id="other"),
        {("1d", Venue.MOOMOO, "NVDA"): [bar()]},
    )

    with pytest.raises(ValueError, match="dataset identity"):
        fake_service([binding()], {"equities": wrong_name}).history(
            Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS
        )
    with pytest.raises(ValueError, match="manifest identity"):
        fake_service([binding()], {"equities": wrong_manifest}).history(
            Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS
        )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "empty requested window"),
        (
            [
                bar(timestamp=NOW),
                bar(timestamp=NOW - timedelta(days=1)),
            ],
            "non-monotonic",
        ),
        ([bar(timestamp=NOW), bar(timestamp=NOW)], "duplicate timestamp"),
        ([bar(instrument=AAPL, timestamp=NOW)], "mixed instrument"),
    ],
)
def test_history_fails_closed_on_invalid_rows(rows: list[Bar], message: str) -> None:
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA")),
        {("1d", Venue.MOOMOO, "NVDA"): rows},
    )
    service = fake_service([binding()], {"equities": dataset})

    with pytest.raises(ValueError, match=message):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


def test_history_refuses_future_leakage_even_when_a_reader_ignores_the_window() -> None:
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", end=NOW + timedelta(days=1))),
        {("1d", Venue.MOOMOO, "NVDA"): [bar(timestamp=NOW + timedelta(seconds=1))]},
        ignore_window=True,
    )
    service = fake_service([binding()], {"equities": dataset})

    with pytest.raises(ValueError, match="future leakage"):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


def test_history_refuses_live_tail_or_forecast_rows() -> None:
    live = SimpleNamespace(**bar().__dict__, is_live_tail=True)
    forecast = SimpleNamespace(**bar().__dict__, is_forecast=True)
    for tagged, message in [(live, "live-tail"), (forecast, "forecast")]:
        dataset = FakeDataset(
            "equities",
            manifest(coverage("NVDA")),
            {("1d", Venue.MOOMOO, "NVDA"): [tagged]},
        )
        service = fake_service([binding()], {"equities": dataset})

        with pytest.raises(ValueError, match=message):
            service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


def test_history_records_real_interval_gaps_but_does_not_invent_duplicates() -> None:
    rows = [
        bar(timestamp=NOW - timedelta(days=3)),
        bar(timestamp=NOW),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA")),
        {("1d", Venue.MOOMOO, "NVDA"): rows},
    )
    service = fake_service([binding()], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)

    assert series.gaps == [NOW - timedelta(days=2), NOW - timedelta(days=1)]
    assert series.duplicates == []


def test_comparison_rebases_only_the_shared_observed_window_without_forward_fill() -> None:
    t0, t1, t2, t3 = [NOW - timedelta(days=value) for value in (3, 2, 1, 0)]
    nvda_rows = [
        bar(timestamp=t0, close=90),
        bar(timestamp=t1, close=100),
        bar(timestamp=t3, close=120),
    ]
    aapl_rows = [
        bar(AAPL, timestamp=t1, close=50),
        bar(AAPL, timestamp=t2, close=55),
        bar(AAPL, timestamp=t3, close=60),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA"), coverage("AAPL")),
        {
            ("1d", Venue.MOOMOO, "NVDA"): nvda_rows,
            ("1d", Venue.MOOMOO, "AAPL"): aapl_rows,
        },
    )
    service = fake_service([binding(), binding("AAPL")], {"equities": dataset})

    comparison = service.compare(
        primary=(Venue.MOOMOO, "NVDA"),
        peers=[(Venue.MOOMOO, "AAPL")],
        range=HistoryRange.ONE_YEAR,
    )

    assert comparison.keys == ["moomoo:NVDA", "moomoo:AAPL"]
    assert [point.timestamp for point in comparison.points] == [t1, t3]
    assert comparison.points[0].values == {"moomoo:NVDA": 100.0, "moomoo:AAPL": 100.0}
    assert comparison.points[1].values == {"moomoo:NVDA": 120.0, "moomoo:AAPL": 120.0}
    assert t2 not in [point.timestamp for point in comparison.points]


def test_comparison_refuses_fewer_than_two_shared_points() -> None:
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA"), coverage("AAPL")),
        {
            ("1d", Venue.MOOMOO, "NVDA"): [bar(timestamp=NOW)],
            ("1d", Venue.MOOMOO, "AAPL"): [bar(AAPL, timestamp=NOW)],
        },
    )
    service = fake_service([binding(), binding("AAPL")], {"equities": dataset})

    with pytest.raises(ValueError, match="at least two shared observed points"):
        service.compare(
            primary=(Venue.MOOMOO, "NVDA"),
            peers=[(Venue.MOOMOO, "AAPL")],
            range=HistoryRange.ONE_YEAR,
        )


def test_comparison_refuses_duplicate_keys_and_invalid_base_values(monkeypatch) -> None:
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA")),
        {("1d", Venue.MOOMOO, "NVDA"): [bar(timestamp=NOW - timedelta(days=1)), bar()]},
    )
    service = fake_service([binding()], {"equities": dataset})
    with pytest.raises(ValueError, match="duplicate comparison instrument"):
        service.compare(
            primary=(Venue.MOOMOO, "NVDA"),
            peers=[(Venue.MOOMOO, "NVDA")],
            range=HistoryRange.ONE_YEAR,
        )

    invalid = HistoricalSeries.model_construct(
        instrument=NVDA,
        range=HistoryRange.ONE_YEAR,
        as_of=NOW,
        bars=[
            HistoricalBar.model_construct(
                instrument=NVDA,
                timestamp=NOW - timedelta(days=1),
                interval="1d",
                open=1.0,
                high=1.0,
                low=1.0,
                close=0.0,
                volume=0.0,
                adjusted_close=None,
                is_live_tail=False,
            ),
            HistoricalBar.model_construct(
                instrument=NVDA,
                timestamp=NOW,
                interval="1d",
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=0.0,
                adjusted_close=None,
                is_live_tail=False,
            ),
        ],
        dataset_id="equities",
        dataset_revision=1,
        source="s",
        license="l",
        generated_at=GENERATED_AT,
        interval="1d",
        calendar="XNYS",
        adjustment="unadjusted",
        coverage=coverage("NVDA"),
        gaps=[],
        duplicates=[],
        limitations=[],
        resolution_fallback=None,
    )
    monkeypatch.setattr(service, "history", lambda *args, **kwargs: invalid)
    with pytest.raises(ValueError, match="finite and positive"):
        service.compare(
            primary=(Venue.MOOMOO, "NVDA"),
            peers=[(Venue.MOOMOO, "AAPL")],
            range=HistoryRange.ONE_YEAR,
        )


def test_comparison_has_deterministic_key_order_and_stable_serialization() -> None:
    nvda = [bar(timestamp=NOW - timedelta(days=1), close=100), bar(close=110)]
    aapl = [bar(AAPL, timestamp=NOW - timedelta(days=1), close=50), bar(AAPL, close=55)]
    btc = [bar(BTC, timestamp=NOW - timedelta(days=1), close=200), bar(BTC, close=180)]
    dataset = FakeDataset(
        "equities",
        manifest(
            coverage("NVDA"),
            coverage("AAPL"),
            coverage("BTC-PERP", venue=Venue.HYPERLIQUID),
        ),
        {
            ("1d", Venue.MOOMOO, "NVDA"): nvda,
            ("1d", Venue.MOOMOO, "AAPL"): aapl,
            ("1d", Venue.HYPERLIQUID, "BTC-PERP"): btc,
        },
    )
    service = fake_service(
        [binding(), binding("AAPL"), binding("BTC-PERP", venue=Venue.HYPERLIQUID)],
        {"equities": dataset},
    )

    comparison = service.compare(
        primary=(Venue.MOOMOO, "NVDA"),
        peers=[(Venue.HYPERLIQUID, "BTC-PERP"), (Venue.MOOMOO, "AAPL")],
        range=HistoryRange.ONE_YEAR,
    )

    assert comparison.keys == ["moomoo:NVDA", "hyperliquid:BTC-PERP", "moomoo:AAPL"]
    payload = comparison.model_dump_json()
    assert ComparisonSeries.model_validate_json(payload, strict=True).model_dump_json() == payload
    assert list(json.loads(payload)["points"][0]["values"]) == comparison.keys


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            DatasetBinding,
            {
                "dataset_id": "ds",
                "interval": "1d",
                "venue": "moomoo",
                "symbol": "NVDA",
                "calendar": "XNYS",
                "adjustment": "unadjusted",
                "extra": 1,
            },
        ),
        (
            HistoricalBar,
            {
                "instrument": NVDA,
                "timestamp": NOW,
                "interval": "1d",
                "open": "1",
                "high": 2.0,
                "low": 1.0,
                "close": 1.5,
                "volume": 1.0,
                "adjusted_close": None,
                "is_live_tail": False,
            },
        ),
        (ComparisonPoint, {"timestamp": NOW, "values": {"moomoo:NVDA": float("nan")}}),
    ],
)
def test_public_contracts_reject_extra_coercive_or_nonfinite_state(model, payload) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload, strict=True)
