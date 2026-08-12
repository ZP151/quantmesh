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
    CoverageSnapshot,
    DatasetBinding,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    InstrumentSnapshot,
    LiveTailLineage,
)
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.live.contract import Provenance

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
    calendar: str | None = None,
) -> DatasetBinding:
    return DatasetBinding(
        dataset_id=dataset_id,
        interval=interval,
        venue=venue,
        symbol=symbol,
        calendar=calendar or ("XNYS" if venue is Venue.MOOMOO else "24/7"),
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

    assert series.instrument.model_dump(mode="json") == NVDA.model_dump(mode="json")
    assert series.dataset_id == "equities"
    assert series.dataset_revision == 7
    assert series.source == "operator-import"
    assert series.license == "operator-supplied"
    assert series.generated_at == GENERATED_AT
    assert series.interval == "1d"
    assert series.calendar == "XNYS"
    assert series.adjustment == "unadjusted"
    assert series.coverage.model_dump() == coverage("NVDA").model_dump()
    assert series.gaps == ()
    assert series.duplicates == ()
    assert series.limitations == (
        "Gap detection requires a session calendar and was not run for XNYS.",
    )
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
        manifest(coverage("NVDA", interval="5m", start=start, end=NOW, rows=2)),
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


@pytest.mark.parametrize("intervals", [("60m", "1h"), ("1h", "60m")])
def test_history_rejects_equal_duration_binding_aliases_as_ambiguous(
    intervals: tuple[str, str],
) -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        HistoryService(
            [binding(interval=interval) for interval in intervals],
            dataset_loader=lambda _: None,
            now=lambda: NOW,
        )


def test_history_treats_one_equivalent_interval_alias_as_preferred() -> None:
    rows = [
        bar(timestamp=NOW - timedelta(hours=1), interval="60m"),
        bar(interval="60m"),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", interval="60m")),
        {("60m", Venue.MOOMOO, "NVDA"): rows},
    )
    service = fake_service([binding(interval="60m")], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.ONE_MONTH)

    assert series.interval == "60m"
    assert series.resolution_fallback is None


@pytest.mark.parametrize(
    ("requested", "preferred", "coarser", "finer"),
    [
        (HistoryRange.ONE_DAY, "5m", "30m", "1m"),
        (HistoryRange.FIVE_DAYS, "30m", "1h", "5m"),
        (HistoryRange.ONE_MONTH, "1h", "1d", "30m"),
        (HistoryRange.THREE_MONTHS, "1d", "1w", "1h"),
        (HistoryRange.SIX_MONTHS, "1d", "1w", "1h"),
        (HistoryRange.ONE_YEAR, "1d", "1w", "1h"),
    ],
)
def test_all_ranges_use_nearest_coarser_fallback_and_never_finer(
    requested: HistoryRange,
    preferred: str,
    coarser: str,
    finer: str,
) -> None:
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", interval=coarser)),
        {(coarser, Venue.MOOMOO, "NVDA"): [bar(interval=coarser)]},
    )
    fallback_service = fake_service(
        [binding(interval=coarser)], {"equities": dataset}
    )

    selected = fallback_service.history(Venue.MOOMOO, "NVDA", requested)

    assert selected.interval == coarser
    assert selected.resolution_fallback == f"{preferred}->{coarser}"
    finer_service = HistoryService(
        [binding(interval=finer)],
        dataset_loader=lambda _: pytest.fail("must not load finer data"),
        now=lambda: NOW,
    )
    with pytest.raises(ValueError, match="preferred or coarser"):
        finer_service.history(Venue.MOOMOO, "NVDA", requested)


def test_dataset_binding_rejects_unknown_interval() -> None:
    with pytest.raises(ValidationError, match="unsupported interval"):
        binding(interval="1q")


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

    with pytest.raises(HistoryUnavailableError, match="unknown venue/symbol"):
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


@pytest.mark.parametrize("offset", [timedelta(days=-11), timedelta(days=-1)])
def test_history_refuses_rows_outside_manifest_coverage(offset: timedelta) -> None:
    declared = coverage(
        "NVDA",
        start=NOW - timedelta(days=10),
        end=NOW - timedelta(days=5),
        rows=6,
    )
    dataset = FakeDataset(
        "equities",
        manifest(declared),
        {("1d", Venue.MOOMOO, "NVDA"): [bar(timestamp=NOW + offset)]},
        ignore_window=True,
    )
    service = fake_service([binding()], {"equities": dataset})

    with pytest.raises(ValueError, match="manifest coverage"):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


def test_history_normalizes_manifest_coverage_before_binding_rows() -> None:
    eastern = timezone(timedelta(hours=-4))
    declared_start = (NOW - timedelta(days=1)).astimezone(eastern)
    declared_end = NOW.astimezone(eastern)
    declared = coverage(
        "NVDA",
        start=declared_start,
        end=declared_end,
        rows=2,
    )
    dataset = FakeDataset(
        "equities",
        manifest(declared),
        {
            ("1d", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=NOW - timedelta(days=1)),
                bar(timestamp=NOW),
            ]
        },
    )
    service = fake_service([binding()], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)

    assert series.coverage.start == NOW - timedelta(days=1)
    assert series.coverage.end == NOW
    assert series.coverage.start.tzinfo is UTC
    assert series.coverage.end.tzinfo is UTC


def test_history_refuses_full_coverage_row_count_or_boundary_drift() -> None:
    declared = coverage(
        "NVDA",
        start=NOW - timedelta(days=2),
        end=NOW,
        rows=3,
    )
    dataset = FakeDataset(
        "equities",
        manifest(declared),
        {
            ("1d", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=NOW - timedelta(days=2)),
                bar(timestamp=NOW),
            ]
        },
    )
    service = fake_service([binding()], {"equities": dataset})

    with pytest.raises(ValueError, match="row count"):
        service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)


@pytest.mark.parametrize("drift", ["start", "end"])
def test_history_refuses_full_coverage_extent_drift(drift: str) -> None:
    declared_start = NOW - timedelta(days=3)
    declared_end = NOW
    timestamps = [declared_start, NOW - timedelta(days=1), declared_end]
    if drift == "start":
        timestamps[0] = declared_start + timedelta(hours=1)
    else:
        timestamps[-1] = declared_end - timedelta(hours=1)
    dataset = FakeDataset(
        "equities",
        manifest(
            coverage(
                "NVDA",
                start=declared_start,
                end=declared_end,
                rows=3,
            )
        ),
        {
            ("1d", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=timestamp) for timestamp in timestamps
            ]
        },
    )
    service = fake_service([binding()], {"equities": dataset})

    with pytest.raises(ValueError, match="coverage extent"):
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
    service = fake_service([binding(calendar="24/7")], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)

    assert series.gaps == (NOW - timedelta(days=2), NOW - timedelta(days=1))
    assert series.duplicates == ()


def test_history_does_not_report_market_closures_as_data_gaps() -> None:
    friday = datetime(2026, 8, 7, 16, 0, tzinfo=UTC)
    monday = datetime(2026, 8, 10, 16, 0, tzinfo=UTC)
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA", start=friday, end=monday, rows=2)),
        {
            ("1d", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=friday),
                bar(timestamp=monday),
            ]
        },
    )
    service = HistoryService(
        [binding(calendar="XNYS")],
        dataset_loader=lambda _: dataset,
        now=lambda: monday,
    )

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)

    assert series.gaps == ()
    assert series.limitations == (
        "Gap detection requires a session calendar and was not run for XNYS.",
    )


def test_history_does_not_report_equity_overnight_as_intraday_gaps() -> None:
    first_close = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
    next_open = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)
    dataset = FakeDataset(
        "equities",
        manifest(
            coverage(
                "NVDA",
                interval="30m",
                start=first_close,
                end=next_open,
                rows=2,
            )
        ),
        {
            ("30m", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=first_close, interval="30m"),
                bar(timestamp=next_open, interval="30m"),
            ]
        },
    )
    service = HistoryService(
        [binding(interval="30m", calendar="XNYS")],
        dataset_loader=lambda _: dataset,
        now=lambda: next_open,
    )

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.FIVE_DAYS)

    assert series.gaps == ()
    assert series.limitations


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

    assert comparison.keys == ("moomoo:NVDA", "moomoo:AAPL")
    assert [point.timestamp for point in comparison.points] == [t1, t3]
    assert comparison.points[0].values == {"moomoo:NVDA": 100.0, "moomoo:AAPL": 100.0}
    assert comparison.points[1].values == {"moomoo:NVDA": 120.0, "moomoo:AAPL": 120.0}
    assert t2 not in [point.timestamp for point in comparison.points]
    assert comparison.limitations == (
        "Gap detection requires a session calendar and was not run for XNYS.",
    )


def test_comparison_selects_the_coarsest_shared_resolution_without_resampling() -> None:
    daily_times = [NOW - timedelta(days=1), NOW]
    hourly_times = [NOW - timedelta(hours=2), NOW - timedelta(hours=1)]
    dataset = FakeDataset(
        "equities",
        manifest(
            coverage(
                "NVDA",
                interval="1h",
                start=hourly_times[0],
                end=hourly_times[-1],
                rows=2,
            ),
            coverage(
                "NVDA",
                start=daily_times[0],
                end=daily_times[-1],
                rows=2,
            ),
            coverage(
                "AAPL",
                start=daily_times[0],
                end=daily_times[-1],
                rows=2,
            ),
        ),
        {
            ("1h", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=timestamp, interval="1h", close=100 + index)
                for index, timestamp in enumerate(hourly_times)
            ],
            ("1d", Venue.MOOMOO, "NVDA"): [
                bar(timestamp=timestamp, close=100 + index * 10)
                for index, timestamp in enumerate(daily_times)
            ],
            ("1d", Venue.MOOMOO, "AAPL"): [
                bar(AAPL, timestamp=timestamp, close=50 + index * 5)
                for index, timestamp in enumerate(daily_times)
            ],
        },
    )
    service = fake_service(
        [binding(interval="1h"), binding(), binding("AAPL")],
        {"equities": dataset},
    )

    comparison = service.compare(
        primary=(Venue.MOOMOO, "NVDA"),
        peers=[(Venue.MOOMOO, "AAPL")],
        range=HistoryRange.ONE_MONTH,
    )

    assert [point.timestamp for point in comparison.points] == daily_times
    assert [call["interval"] for call in dataset.calls] == ["1d", "1d"]
    assert comparison.points[-1].values["moomoo:NVDA"] == pytest.approx(110.0)
    assert comparison.points[-1].values["moomoo:AAPL"] == pytest.approx(110.0)


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
    service = fake_service([binding(), binding("AAPL")], {"equities": dataset})
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
    monkeypatch.setattr(HistoryService, "history", lambda *args, **kwargs: invalid)
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

    assert comparison.keys == (
        "moomoo:NVDA",
        "hyperliquid:BTC-PERP",
        "moomoo:AAPL",
    )
    payload = comparison.model_dump_json()
    assert ComparisonSeries.model_validate_json(payload, strict=True).model_dump_json() == payload
    assert tuple(json.loads(payload)["points"][0]["values"]) == comparison.keys


def test_history_and_comparison_responses_are_structurally_immutable() -> None:
    nvda = [bar(timestamp=NOW - timedelta(days=1)), bar()]
    aapl = [
        bar(AAPL, timestamp=NOW - timedelta(days=1), close=50),
        bar(AAPL, close=55),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(coverage("NVDA"), coverage("AAPL")),
        {
            ("1d", Venue.MOOMOO, "NVDA"): nvda,
            ("1d", Venue.MOOMOO, "AAPL"): aapl,
        },
    )
    service = fake_service([binding(), binding("AAPL")], {"equities": dataset})

    history = service.history(Venue.MOOMOO, "NVDA", HistoryRange.ONE_YEAR)
    comparison = service.compare(
        primary=(Venue.MOOMOO, "NVDA"),
        peers=[(Venue.MOOMOO, "AAPL")],
        range=HistoryRange.ONE_YEAR,
    )

    with pytest.raises(ValidationError):
        history.instrument.symbol = "MUTATED"
    with pytest.raises(TypeError):
        history.instrument.metadata["source"] = "mutated"
    with pytest.raises(AttributeError):
        history.bars.clear()
    with pytest.raises(AttributeError):
        history.gaps.append(NOW)
    with pytest.raises(AttributeError):
        history.duplicates.append(NOW)
    with pytest.raises(AttributeError):
        history.limitations.append("mutated")
    with pytest.raises(ValidationError):
        history.coverage.rows = 1
    with pytest.raises(AttributeError):
        comparison.points.clear()
    with pytest.raises(AttributeError):
        comparison.keys.clear()
    with pytest.raises(AttributeError):
        comparison.limitations.append("mutated")
    with pytest.raises(TypeError):
        comparison.points[0].values[comparison.keys[0]] = 0.0


def test_history_detaches_reader_owned_instrument_coverage_and_lists() -> None:
    source_instrument = Instrument(
        symbol="NVDA",
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        metadata={"sector": "technology"},
    )
    source_coverage = coverage(
        "NVDA",
        start=NOW - timedelta(days=1),
        end=NOW,
        rows=2,
    )
    source_rows = [
        bar(source_instrument, timestamp=NOW - timedelta(days=1)),
        bar(source_instrument, timestamp=NOW),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(source_coverage),
        {("1d", Venue.MOOMOO, "NVDA"): source_rows},
    )
    service = fake_service([binding()], {"equities": dataset})

    series = service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)
    source_instrument.symbol = "MUTATED"
    source_instrument.metadata["sector"] = "mutated"
    source_coverage.rows = 99
    source_rows[0].close = 999.0
    dataset.manifest.coverage.clear()
    source_rows.clear()

    assert series.instrument.symbol == "NVDA"
    assert series.instrument.metadata == {"sector": "technology"}
    assert series.bars[0].instrument.symbol == "NVDA"
    assert series.bars[0].close == 100.0
    assert series.coverage.rows == 2
    assert len(series.bars) == 2

    source_values = {"moomoo:NVDA": 100.0}
    point = ComparisonPoint(timestamp=NOW, values=source_values)
    source_values["moomoo:NVDA"] = 0.0
    assert point.values["moomoo:NVDA"] == 100.0


def test_public_response_dump_keeps_json_arrays_objects_and_strict_round_trip() -> None:
    nvda = [bar(timestamp=NOW - timedelta(days=1)), bar()]
    aapl = [
        bar(AAPL, timestamp=NOW - timedelta(days=1), close=50),
        bar(AAPL, close=55),
    ]
    dataset = FakeDataset(
        "equities",
        manifest(
            coverage("NVDA", start=NOW - timedelta(days=1), end=NOW, rows=2),
            coverage("AAPL", start=NOW - timedelta(days=1), end=NOW, rows=2),
        ),
        {
            ("1d", Venue.MOOMOO, "NVDA"): nvda,
            ("1d", Venue.MOOMOO, "AAPL"): aapl,
        },
    )
    service = fake_service([binding(), binding("AAPL")], {"equities": dataset})
    history = service.history(Venue.MOOMOO, "NVDA", HistoryRange.ONE_YEAR)
    comparison = service.compare(
        primary=(Venue.MOOMOO, "NVDA"),
        peers=[(Venue.MOOMOO, "AAPL")],
        range=HistoryRange.ONE_YEAR,
    )

    history_payload = history.model_dump(mode="json")
    comparison_payload = comparison.model_dump(mode="json")
    assert isinstance(history_payload["bars"], list)
    assert isinstance(history_payload["gaps"], list)
    assert isinstance(history_payload["instrument"]["metadata"], dict)
    assert isinstance(history_payload["coverage"], dict)
    assert history_payload["coverage_scope"] == "historical-only"
    assert isinstance(comparison_payload["keys"], list)
    assert isinstance(comparison_payload["points"], list)
    assert isinstance(comparison_payload["points"][0]["values"], dict)
    assert HistoricalSeries.model_validate_json(
        history.model_dump_json(), strict=True
    ).model_dump_json() == history.model_dump_json()
    assert ComparisonSeries.model_validate_json(
        comparison.model_dump_json(), strict=True
    ).model_dump_json() == comparison.model_dump_json()


def test_live_tail_lineage_is_strict_frozen_and_round_trips() -> None:
    lineage = LiveTailLineage(
        source="moomoo",
        venue=Venue.MOOMOO,
        instrument="NVDA",
        provenance=Provenance.DELAYED,
        data_time=NOW,
        received_at=NOW + timedelta(seconds=2),
        interval="1d",
        sequence=42,
        predecessor_sequence=41,
        predecessor_data_time=NOW - timedelta(days=1),
        sequence_gap=False,
        continuity_proven=True,
        freshness_label="delayed",
        age_ms=3_000,
    )
    live_bar = HistoricalBar(
        instrument=NVDA,
        timestamp=NOW,
        interval="1d",
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=1_000.0,
        is_live_tail=True,
        live_lineage=lineage,
    )

    payload = live_bar.model_dump_json()
    restored = HistoricalBar.model_validate_json(payload, strict=True)
    assert restored.model_dump_json() == payload
    assert restored.live_lineage is not None
    assert restored.live_lineage.provenance is Provenance.DELAYED
    assert restored.live_lineage.predecessor_sequence == 41
    with pytest.raises(ValidationError):
        restored.live_lineage.age_ms = 1


def test_live_tail_flag_and_lineage_identity_must_match_exactly() -> None:
    lineage = LiveTailLineage(
        source="moomoo",
        venue=Venue.MOOMOO,
        instrument="NVDA",
        provenance=Provenance.REAL,
        data_time=NOW,
        received_at=NOW,
        interval="1d",
        sequence=2,
        predecessor_sequence=1,
        predecessor_data_time=NOW - timedelta(days=1),
        sequence_gap=False,
        continuity_proven=True,
        freshness_label="real",
        age_ms=0,
    )
    base = {
        "instrument": NVDA,
        "timestamp": NOW,
        "interval": "1d",
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1_000.0,
    }

    with pytest.raises(ValidationError, match="if and only if"):
        HistoricalBar(**base, is_live_tail=True)
    with pytest.raises(ValidationError, match="if and only if"):
        HistoricalBar(**base, is_live_tail=False, live_lineage=lineage)
    with pytest.raises(ValidationError, match="must match"):
        HistoricalBar(
            **base,
            is_live_tail=True,
            live_lineage=lineage.model_copy(update={"instrument": "AAPL"}),
        )
    invalid_proof = lineage.model_dump()
    invalid_proof["data_time"] = NOW + timedelta(days=2)
    with pytest.raises(ValidationError, match="same or exactly one interval"):
        LiveTailLineage(**invalid_proof)


def _series_with_live_tail() -> HistoricalSeries:
    live_time = NOW + timedelta(days=1)
    as_of = live_time + timedelta(milliseconds=1_500)
    lineage = LiveTailLineage(
        source="moomoo",
        venue=Venue.MOOMOO,
        instrument="NVDA",
        provenance=Provenance.REAL,
        data_time=live_time,
        received_at=live_time,
        interval="1d",
        sequence=2,
        predecessor_sequence=1,
        predecessor_data_time=NOW,
        sequence_gap=False,
        continuity_proven=True,
        freshness_label="real",
        age_ms=1_500,
    )
    return HistoricalSeries(
        instrument=NVDA,
        range=HistoryRange.SIX_MONTHS,
        as_of=as_of,
        bars=(
            HistoricalBar(
                instrument=NVDA,
                timestamp=NOW - timedelta(days=1),
                interval="1d",
                open=99.0,
                high=102.0,
                low=98.0,
                close=100.0,
                volume=1_000.0,
            ),
            HistoricalBar(
                instrument=NVDA,
                timestamp=NOW,
                interval="1d",
                open=100.0,
                high=103.0,
                low=99.0,
                close=101.0,
                volume=1_100.0,
            ),
            HistoricalBar(
                instrument=NVDA,
                timestamp=live_time,
                interval="1d",
                open=101.0,
                high=104.0,
                low=100.0,
                close=103.0,
                volume=1_200.0,
                is_live_tail=True,
                live_lineage=lineage,
            ),
        ),
        dataset_id="equities",
        dataset_revision=7,
        source="operator-import",
        license="operator-supplied",
        generated_at=NOW - timedelta(days=2),
        interval="1d",
        calendar="XNYS",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval="1d",
            venue=Venue.MOOMOO,
            symbol="NVDA",
            start=NOW - timedelta(days=1),
            end=NOW,
            rows=2,
        ),
        limitations=(
            "manifest coverage is historical-only; the live-tail bar is excluded",
        ),
    )


@pytest.mark.parametrize("forged_age", [0, 999_999])
def test_series_strict_json_rejects_forged_live_lineage_age(forged_age: int) -> None:
    payload = json.loads(_series_with_live_tail().model_dump_json())
    payload["bars"][-1]["live_lineage"]["age_ms"] = forged_age

    with pytest.raises(ValidationError, match="age_ms must exactly equal"):
        HistoricalSeries.model_validate_json(json.dumps(payload), strict=True)


def test_series_strict_json_rejects_live_receipt_after_as_of() -> None:
    payload = json.loads(_series_with_live_tail().model_dump_json())
    as_of = datetime.fromisoformat(payload["as_of"])
    payload["bars"][-1]["live_lineage"]["received_at"] = (
        as_of + timedelta(seconds=1)
    ).isoformat()
    payload["bars"][-1]["live_lineage"]["age_ms"] = 0

    with pytest.raises(ValidationError, match="received_at must not exceed series as_of"):
        HistoricalSeries.model_validate_json(json.dumps(payload), strict=True)


def test_series_strict_json_rejects_live_tail_in_the_middle() -> None:
    payload = json.loads(_series_with_live_tail().model_dump_json())
    payload["bars"] = [payload["bars"][0], payload["bars"][2], payload["bars"][1]]

    with pytest.raises(ValidationError, match="live-tail bar must be final"):
        HistoricalSeries.model_validate_json(json.dumps(payload), strict=True)


def test_series_strict_json_rejects_multiple_live_tails() -> None:
    payload = json.loads(_series_with_live_tail().model_dump_json())
    as_of = datetime.fromisoformat(payload["as_of"])
    second = payload["bars"][1]
    lineage = dict(payload["bars"][-1]["live_lineage"])
    lineage.update(
        {
            "data_time": second["timestamp"],
            "received_at": second["timestamp"],
            "sequence": 1,
            "predecessor_sequence": 0,
            "predecessor_data_time": payload["bars"][0]["timestamp"],
            "age_ms": int(
                (
                    as_of - datetime.fromisoformat(second["timestamp"])
                ).total_seconds()
                * 1000
            ),
        }
    )
    second["is_live_tail"] = True
    second["live_lineage"] = lineage

    with pytest.raises(ValidationError, match="at most one live-tail bar"):
        HistoricalSeries.model_validate_json(json.dumps(payload), strict=True)


def test_series_strict_json_rejects_historical_bar_outside_manifest_coverage() -> None:
    payload = json.loads(_series_with_live_tail().model_dump_json())
    coverage_start = datetime.fromisoformat(payload["coverage"]["start"])
    payload["bars"][0]["timestamp"] = (
        coverage_start - timedelta(days=1)
    ).isoformat()

    with pytest.raises(ValidationError, match="historical bars must remain inside"):
        HistoricalSeries.model_validate_json(json.dumps(payload), strict=True)


def test_series_live_tail_exact_age_and_outside_coverage_round_trip() -> None:
    series = _series_with_live_tail()
    payload = series.model_dump_json()

    restored = HistoricalSeries.model_validate_json(payload, strict=True)

    assert restored.model_dump_json() == payload
    assert restored.bars[-1].timestamp > restored.coverage.end
    assert restored.bars[-1].live_lineage is not None
    assert restored.bars[-1].live_lineage.age_ms == 1_500


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
        (
            InstrumentSnapshot,
            {
                "symbol": 123,
                "venue": Venue.MOOMOO,
                "instrument_type": InstrumentType.EQUITY,
                "currency": "USD",
                "metadata": {},
            },
        ),
        (
            CoverageSnapshot,
            {
                "interval": "1d",
                "venue": Venue.MOOMOO,
                "symbol": "NVDA",
                "start": NOW - timedelta(days=1),
                "end": NOW,
                "rows": True,
            },
        ),
    ],
)
def test_public_contracts_reject_extra_coercive_or_nonfinite_state(model, payload) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload, strict=True)
