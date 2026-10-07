from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import HistoricalSeries, HistoryRange
from quantmesh.instruments.history import HistoryUnavailableError
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed
from tests.test_instrument_workspace_api import NOW, _harness, _quote_feed

ANCHOR = datetime(2026, 10, 8, 14, 0, tzinfo=UTC)


def _candle(at, sequence, *, symbol="AAPL", close=100, received_at=None, **metadata):
    return MarketUpdate(
        venue=Venue.MOOMOO,
        instrument=symbol,
        kind=UpdateKind.CANDLE,
        provenance=Provenance.REAL,
        data_time=at,
        received_at=received_at or at + timedelta(seconds=5),
        sequence=sequence,
        payload={
            "interval": "1m",
            "open": 99,
            "high": 105,
            "low": 98,
            "close": close,
            "volume": 10,
            "license": "moomoo-private-market-data",
            "session": "regular",
            "adjustment": "unadjusted",
            "sequence_origin": "local-observation",
            "provider_time_key": (at + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "provider_end": (at + timedelta(minutes=1)).isoformat(),
            **metadata,
        },
    )


def _history(feed, at=ANCHOR + timedelta(minutes=1, seconds=6), symbol="AAPL"):
    return LiveHistoryService(None, feed).history(
        Venue.MOOMOO, symbol, HistoryRange.ONE_DAY, as_of=at
    )


@pytest.mark.parametrize("symbol", ["AAPL", "NVDA"])
def test_private_equity_minute_replay_keeps_exact_coverage_and_revisions(tmp_path: Path, symbol):
    root = tmp_path / "replay"
    with LiveBuffer(root) as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [
                _candle(ANCHOR, 1, symbol=symbol),
                _candle(ANCHOR + timedelta(minutes=1), 2, symbol=symbol),
            ]
        )
        series = _history(feed, symbol=symbol)
        assert series.resolution_fallback == "5m->1m"
        assert series.license == "moomoo-private-market-data"
        assert series.calendar == "XNYS"
        assert series.coverage.rows == 2
        assert any("regular-session" in detail for detail in series.limitations)
        assert any("local observation" in detail for detail in series.limitations)
        feed.ingest(
            [
                _candle(
                    ANCHOR + timedelta(minutes=1),
                    3,
                    symbol=symbol,
                    close=102,
                    received_at=ANCHOR + timedelta(minutes=1, seconds=10),
                )
            ]
        )
        revised = _history(feed, ANCHOR + timedelta(minutes=1, seconds=11), symbol)
        assert [bar.close for bar in revised.bars] == [100, 102]
        feed.ingest([_candle(ANCHOR + timedelta(minutes=2), 4, symbol=symbol, close=103)])
        appended = _history(feed, ANCHOR + timedelta(minutes=2, seconds=6), symbol)
        assert appended.coverage.rows == 3
        assert appended.coverage.end == appended.bars[-1].timestamp
    with LiveBuffer(root) as buffer:
        series = _history(LiveFeed(lake=buffer), ANCHOR + timedelta(minutes=3), symbol)
        assert [bar.close for bar in series.bars] == [100, 102, 103]
        assert not series.bars[-1].is_live_tail


@pytest.mark.parametrize(
    "metadata",
    [
        {"license": "venue-public-market-data"},
        {"session": "extended"},
        {"adjustment": "split-adjusted"},
        {"sequence_origin": "exchange"},
        {"provider_end": "bad"},
    ],
)
def test_private_minute_replay_rejects_mismatched_supplier_metadata(tmp_path, metadata):
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [_candle(ANCHOR, 1, **metadata), _candle(ANCHOR + timedelta(minutes=1), 2, **metadata)]
        )
        with pytest.raises(HistoryUnavailableError):
            _history(feed)


@pytest.mark.parametrize(
    "changes",
    [
        {"license": "venue-public-market-data"},
        {"source": "operator-import"},
        {"dataset_id": "imported-equity"},
        {"range": HistoryRange.FIVE_DAYS},
        {"calendar": "24/7"},
        {"adjustment": "split-adjusted"},
    ],
)
def test_private_minute_fallback_contract_is_exactly_bound(tmp_path, changes):
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest([_candle(ANCHOR, 1), _candle(ANCHOR + timedelta(minutes=1), 2)])
        data = _history(feed).model_dump()
        data.update(changes)
        with pytest.raises(ValueError):
            HistoricalSeries.model_validate(data)


def test_private_replay_keeps_gap_and_fresh_receipt_does_not_make_closed_candle_live(tmp_path):
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [
                _candle(ANCHOR, 1),
                _candle(ANCHOR + timedelta(minutes=1), 2),
                _candle(ANCHOR + timedelta(minutes=3), 3),
                _candle(ANCHOR + timedelta(minutes=4), 4),
            ]
        )
        now = ANCHOR + timedelta(minutes=10)
        series = _history(feed, now)
        assert [bar.timestamp for bar in series.bars] == [
            ANCHOR + timedelta(minutes=3),
            ANCHOR + timedelta(minutes=4),
        ]
        assert not series.bars[-1].is_live_tail
        assert series.coverage.rows == 2
        # A freshly delivered cached provider window cannot certify live data.
        feed.ingest([_candle(ANCHOR + timedelta(minutes=4), 5, received_at=now)])
        assert not _history(feed, now + timedelta(seconds=1)).bars[-1].is_live_tail


def test_workspace_metrics_last_is_display_only_and_blocks_paper(tmp_path):
    feed = LiveFeed()
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="NVDA",
                kind=UpdateKind.METRICS,
                provenance=Provenance.REAL,
                data_time=NOW - timedelta(seconds=2),
                received_at=NOW - timedelta(seconds=1),
                sequence=1,
                payload={"last": 105.5},
            )
        ]
    )
    harness = _harness(tmp_path, live=feed)
    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
    assert response.status_code == 200, response.text
    live = response.json()["live"]
    assert live["status"] == "degraded"
    assert live["last"] == 105.5
    assert live["bid"] is None and live["ask"] is None
    assert live["source"] == "moomoo"
    assert live["data_time"] == (NOW - timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
    assert live["received_at"] == (NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    assert live["age_ms"] == 1000
    assert "not an executable quote" in live["reason"]
    assert not response.json()["proposal"]["allowed"]
    assert feed.snapshot_exact(Venue.MOOMOO, "NVDA", UpdateKind.QUOTE, as_of=NOW) is None


def test_workspace_quote_retains_priority_over_metrics_last(tmp_path):
    feed = _quote_feed()
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="NVDA",
                kind=UpdateKind.METRICS,
                provenance=Provenance.REAL,
                data_time=NOW,
                received_at=NOW,
                sequence=10,
                payload={"last": 900},
            )
        ]
    )
    harness = _harness(tmp_path, live=feed)
    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
    assert response.json()["live"]["status"] == "available"
    assert response.json()["live"]["last"] == 105


def test_workspace_metrics_fallback_is_captured_before_competing_ingest(tmp_path, monkeypatch):
    feed = LiveFeed()
    earlier = MarketUpdate(
        venue=Venue.MOOMOO,
        instrument="NVDA",
        kind=UpdateKind.METRICS,
        provenance=Provenance.REAL,
        data_time=NOW - timedelta(seconds=2),
        received_at=NOW - timedelta(seconds=1),
        sequence=1,
        payload={"last": 105.5},
    )
    feed.ingest([earlier])
    capture = feed.capture_exact

    def capture_then_ingest(*args, **kwargs):
        captured = capture(*args, **kwargs)
        feed.ingest(
            [
                earlier.model_copy(
                    update={
                        "sequence": 2,
                        "data_time": NOW + timedelta(seconds=1),
                        "received_at": NOW + timedelta(seconds=1),
                        "payload": {"last": 900},
                    }
                )
            ]
        )
        return captured

    monkeypatch.setattr(feed, "capture_exact", capture_then_ingest)
    harness = _harness(tmp_path, live=feed)
    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
    body = response.json()
    assert body["generated_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert body["live"]["last"] == 105.5
    assert body["live"]["received_at"] == earlier.received_at.isoformat().replace("+00:00", "Z")
    assert feed.snapshot_exact(Venue.MOOMOO, "NVDA", UpdateKind.METRICS, as_of=NOW).sequence == 2


def test_metrics_payload_cannot_invent_workspace_bidask_depth(tmp_path):
    feed = LiveFeed()
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="NVDA",
                kind=UpdateKind.METRICS,
                provenance=Provenance.REAL,
                data_time=NOW,
                received_at=NOW,
                sequence=10,
                payload={"last": 105.5, "bid": 105, "ask": 106, "bid_size": 100, "ask_size": 100},
            )
        ]
    )
    harness = _harness(tmp_path, live=feed)
    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
    live = response.json()["live"]
    assert live["bid"] is None and live["ask"] is None
    assert live["last"] == 105.5
    assert live["status"] == "degraded"


@pytest.mark.parametrize("payload", [{"last": True}, {"last": -1}, {}])
def test_invalid_metrics_last_retains_typed_absence(tmp_path, payload):
    feed = LiveFeed()
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="NVDA",
                kind=UpdateKind.METRICS,
                provenance=Provenance.REAL,
                data_time=NOW,
                received_at=NOW,
                sequence=1,
                payload=payload,
            )
        ]
    )
    harness = _harness(tmp_path, live=feed)
    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
    assert response.json()["live"]["last"] is None
    assert response.json()["live"]["status"] != "available"


def test_just_closed_private_tail_age_is_bound_to_provider_end(tmp_path):
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [
                _candle(ANCHOR, 1),
                _candle(
                    ANCHOR + timedelta(minutes=1),
                    2,
                    received_at=ANCHOR + timedelta(minutes=2, seconds=2),
                ),
            ]
        )
        series = _history(feed, ANCHOR + timedelta(minutes=2, seconds=3))
        lineage = series.bars[-1].live_lineage
        assert lineage is not None
        assert lineage.age_ms == 3000
        assert lineage.freshness_time == ANCHOR + timedelta(minutes=2)
        assert lineage.provider_end == ANCHOR + timedelta(minutes=2)
        assert lineage.sequence_origin == "local-observation"
        data = series.model_dump()
        data["bars"][-1]["live_lineage"]["age_ms"] = 1000
        with pytest.raises(ValueError, match="freshness clock"):
            HistoricalSeries.model_validate(data)


def test_private_tail_append_after_replay_capture_rebuilds_exact_coverage(tmp_path, monkeypatch):
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest([_candle(ANCHOR, 1), _candle(ANCHOR + timedelta(minutes=1), 2)])
        original_replay = buffer.replay

        def capture_then_append(**kwargs):
            captured = original_replay(**kwargs)
            feed.ingest([_candle(ANCHOR + timedelta(minutes=2), 3, close=103)])
            return captured

        monkeypatch.setattr(buffer, "replay", capture_then_append)
        series = _history(feed, ANCHOR + timedelta(minutes=2, seconds=6))
        assert [bar.close for bar in series.bars] == [100, 100, 103]
        assert series.coverage.rows == 3
        assert series.coverage.end == ANCHOR + timedelta(minutes=2)
        assert series.bars[-1].is_live_tail


def test_private_minute_session_gap_starts_new_observed_segment(tmp_path):
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        last_session = ANCHOR - timedelta(days=1)
        feed.ingest(
            [
                _candle(last_session, 1),
                _candle(last_session + timedelta(minutes=1), 2),
                _candle(ANCHOR, 3),
                _candle(ANCHOR + timedelta(minutes=1), 4),
            ]
        )
        series = _history(feed)
        assert [bar.timestamp for bar in series.bars] == [ANCHOR, ANCHOR + timedelta(minutes=1)]
        assert series.coverage.rows == 2
