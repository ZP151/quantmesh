"""Fixed-day inspection uses synthetic local stores, never an actual market archive."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.data.manifest import DatasetManifest, SeriesCoverage
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.api import instrument_router
from quantmesh.instruments.contracts import DatasetBinding, HistoryRange
from quantmesh.instruments.history import HistoryService
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
from quantmesh.live.feed import LiveFeed

AT = datetime(2026, 10, 23, 23, 44, 1, tzinfo=UTC)


def candle(minute, sequence, *, received_at=None, close=100.0):
    timestamp = AT.replace(second=0) - timedelta(minutes=minute)
    return MarketUpdate(
        venue="hyperliquid",
        instrument="BTC",
        kind=UpdateKind.CANDLE,
        provenance=Provenance.REAL,
        data_time=timestamp,
        received_at=received_at or timestamp + timedelta(seconds=30),
        sequence=sequence,
        sequence_gap=False,
        payload={
            "interval": "1m",
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 10,
        },
    )


@pytest.fixture
def mounted(tmp_path):
    archive_root = tmp_path / "archive"
    with LiveBuffer(archive_root, retention_days=0) as archive:
        archive.append_many([candle(2, 100), candle(1, 101)])
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        feed = LiveFeed(lake=hot)
        app = FastAPI()
        app.include_router(instrument_router(), prefix="/api")
        app.state.history = LiveHistoryService(None, feed, archive_root=archive_root)
        app.state.instrument_clock = lambda: AT
        with TestClient(app) as client:
            yield client, app, hot, archive_root


def inspect(client, at=AT.isoformat(), venue="hyperliquid", symbol="BTC", **extra):
    return client.get(
        f"/api/instruments/{venue}/{symbol}/history-inspection", params={"at": at, **extra}
    )


def test_old_observations_real_view_time_original_receipt_no_live_join(mounted, monkeypatch):
    client, app, _hot, root = mounted
    path = root / "live" / "updates.duckdb"
    original, mtime = path.read_bytes(), path.stat().st_mtime_ns
    before = datetime.now(UTC)
    calls = []
    app.state.instrument_clock = lambda: calls.append("clock") or AT
    import quantmesh.instruments.live_history as module

    monkeypatch.setattr(module, "join_live_tail", lambda *a, **k: pytest.fail("live join"))
    response = inspect(client)
    assert response.status_code == 200, response.text
    value = response.json()
    assert before <= datetime.fromisoformat(value["observed_at"]) <= datetime.now(UTC)
    assert datetime.fromisoformat(value["window_end"]) == AT
    assert value["source_time"] == "2026-10-23T23:43:00Z"
    assert value["source_received_at"] == "2026-10-23T23:43:30Z"
    assert value["stale"] is True and value["stale_after_seconds"] == 120
    assert len(value["primary"]["bars"]) == 2
    assert all(not bar["is_live_tail"] for bar in value["primary"]["bars"])
    assert calls == []
    assert path.read_bytes() == original and path.stat().st_mtime_ns == mtime


@pytest.mark.parametrize(
    "at", ["2026-10-23T23:44:01", "2026-10-23", "1790000000", "invalid", "2999-01-01T00:00:00Z"]
)
def test_invalid_or_future_dates_refuse_before_replay(mounted, monkeypatch, at):
    client, _app, hot, _root = mounted
    monkeypatch.setattr(hot, "replay", lambda **k: pytest.fail("read before input validation"))
    assert inspect(client, at=at).status_code == 422


def test_at_offsets_normalize_but_duplicate_or_extra_queries_refuse(mounted):
    client, _app, _hot, _root = mounted
    response = inspect(client, at="2026-10-24T07:44:01+08:00")
    assert response.status_code == 200, response.text
    assert response.json()["window_end"] == "2026-10-23T23:44:01Z"
    assert inspect(client, range="5d").status_code == 422
    assert (
        client.get(
            "/api/instruments/hyperliquid/BTC/history-inspection",
            params=[("at", AT.isoformat()), ("at", AT.isoformat())],
        ).status_code
        == 422
    )


@pytest.mark.parametrize("venue,symbol", [("moomoo", "SPY"), ("polymarket", "BTC")])
def test_scope_refuses_without_extending_private_minute_policy(mounted, venue, symbol):
    client, _app, _hot, _root = mounted
    assert inspect(client, venue=venue, symbol=symbol).status_code == 422


def test_last_selected_receipt_is_not_maximum_receipt(mounted):
    client, _app, hot, _root = mounted
    hot.append_many(
        [
            candle(2, 200, received_at=AT - timedelta(seconds=1), close=201),
            candle(1, 201, received_at=AT - timedelta(seconds=20), close=202),
        ]
    )
    value = inspect(client).json()
    assert value["primary"]["bars"][-1]["close"] == 202
    assert value["source_received_at"] == "2026-10-23T23:43:41Z"
    assert value["primary"]["generated_at"] == "2026-10-23T23:44:00Z"


def test_real_gap_and_status_leave_only_final_segment(mounted):
    client, _app, hot, _root = mounted
    hot.append_many(
        [
            MarketUpdate(
                venue="hyperliquid",
                instrument="BTC",
                kind=UpdateKind.STATUS,
                provenance=Provenance.REAL,
                data_time=AT - timedelta(minutes=1),
                received_at=AT - timedelta(seconds=50),
                state=SourceState.DISCONNECTED,
            ),
            candle(12, 300),
            candle(11, 301),
        ]
    )
    value = inspect(client).json()
    assert [bar["timestamp"] for bar in value["primary"]["bars"]] == [
        "2026-10-23T23:32:00Z",
        "2026-10-23T23:33:00Z",
    ]
    assert value["primary"]["coverage"]["rows"] == 2


def test_inherited_dual_time_tail_bounds_and_failure_are_explicit(mounted, monkeypatch):
    client, _app, hot, _root = mounted
    calls = []
    replay = LiveBuffer.replay

    def recording(self, **kwargs):
        calls.append(kwargs)
        return replay(self, **kwargs)

    monkeypatch.setattr(LiveBuffer, "replay", recording)
    assert inspect(client).status_code == 200
    assert len(calls) == 2
    for item in calls:
        assert item["limit"] == 10_000 and item["tail"] is True
        assert item["start"] == item["data_time_start"] == AT - timedelta(days=1)
        assert item["end"] == item["data_time_end"] == AT

    def refused(**kwargs):
        raise RuntimeError("synthetic bounded resource refusal")

    monkeypatch.setattr(hot, "replay", refused)
    response = inspect(client)
    assert response.status_code == 404 and "hot replay unavailable" in response.text


def test_empty_or_missing_archive_does_not_become_hot_only_success(mounted):
    client, app, hot, root = mounted
    assert inspect(client, at="2026-10-22T00:00:00Z").status_code == 404
    hot.append_many([candle(2, 200), candle(1, 201)])
    app.state.history = LiveHistoryService(None, LiveFeed(lake=hot), archive_root=root / "absent")
    response = inspect(client)
    assert response.status_code == 404 and "archive unavailable" in response.text


def test_manifest_precedence_and_unknown_receipt_without_replay(mounted, monkeypatch):
    client, app, hot, _root = mounted
    original = client.get("/api/instruments/hyperliquid/BTC/history?range=1d").json()["primary"]
    series = app.state.history.history(Venue.HYPERLIQUID, "BTC", HistoryRange.ONE_DAY, as_of=AT)
    historical = HistoryService([], dataset_loader=lambda _: pytest.fail("dataset loading"))
    monkeypatch.setattr(historical, "history", lambda *a, **k: series)
    app.state.history = LiveHistoryService(historical, LiveFeed(lake=hot))
    monkeypatch.setattr(hot, "replay", lambda **k: pytest.fail("manifest must win"))
    value = inspect(client).json()
    assert value["source_received_at"] is None
    assert value["primary"] == original


def test_existing_history_json_and_current_clock_unchanged(mounted):
    client, app, _hot, _root = mounted
    url = "/api/instruments/hyperliquid/BTC/history?range=1d"
    before = client.get(url).json()
    assert set(before) == {"primary", "comparison"}
    assert inspect(client).status_code == 200
    assert client.get(url).json() == before
    assert app.state.instrument_clock() == AT
    assert (
        client.post(
            "/api/instruments/hyperliquid/BTC/history-inspection", params={"at": AT.isoformat()}
        ).status_code
        == 405
    )


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("single_row", [False, True])
def test_genuine_manifest_last_segment_minimum_and_original_coverage(mounted, wrapped, single_row):
    client, app, hot, _root = mounted
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    selected_times = (
        ["2026-10-23T23:40:00Z"]
        if single_row
        else [
            "2026-10-23T23:20:00Z",
            "2026-10-23T23:25:00Z",
            "2026-10-23T23:35:00Z",
            "2026-10-23T23:40:00Z",
        ]
    )
    stamps = ["2026-10-01T00:00:00Z", *selected_times, "2026-10-26T00:00:00Z"]
    rows = [
        Bar(
            instrument=instrument,
            timestamp=datetime.fromisoformat(stamp),
            interval="5m",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        )
        for stamp in stamps
    ]

    class SyntheticDataset:
        name = "inspection-synthetic-manifest"
        manifest = DatasetManifest(
            revision=1,
            dataset=name,
            source="SYNTHETIC MANIFEST FIXTURE",
            license="engineering-only",
            generated_at=AT,
            coverage=[
                SeriesCoverage(
                    interval="5m",
                    venue=Venue.HYPERLIQUID,
                    symbol="BTC",
                    start=rows[0].timestamp,
                    end=rows[-1].timestamp,
                    rows=len(rows),
                )
            ],
        )

        def read_bars(self, *, start, end, **kwargs):
            return [row for row in rows if start <= row.timestamp <= end]

    dataset = SyntheticDataset()
    historical = HistoryService(
        [
            DatasetBinding(
                dataset_id=dataset.name,
                interval="5m",
                venue=Venue.HYPERLIQUID,
                symbol="BTC",
                calendar="24/7",
                adjustment="unadjusted",
            )
        ],
        dataset_loader=lambda _: dataset,
    )
    app.state.history = (
        LiveHistoryService(historical, LiveFeed(lake=hot)) if wrapped else historical
    )
    original = client.get("/api/instruments/hyperliquid/BTC/history?range=1d").json()
    assert len(original["primary"]["bars"]) == len(selected_times)
    response = inspect(client)
    if single_row:
        assert response.status_code == 404, response.text
        assert "two" in response.text
    else:
        assert response.status_code == 200, response.text
        value = response.json()
        assert [bar["timestamp"] for bar in value["primary"]["bars"]] == selected_times[-2:]
        assert value["primary"]["coverage"] == original["primary"]["coverage"]
        assert value["source_received_at"] is None
    assert client.get("/api/instruments/hyperliquid/BTC/history?range=1d").json() == original
