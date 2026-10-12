from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.domain.models import Venue
from quantmesh.live.api import live_router
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
from quantmesh.live.feed import LiveFeed
from tests.test_live_session_freshness import dt


def stock_feed(*, delay=None):
    feed = LiveFeed(provider_delays={Venue.MOOMOO: delay})
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="AAPL",
                kind=UpdateKind.CANDLE,
                provenance=Provenance.REAL,
                data_time=dt("2026-10-09T19:59Z"),
                received_at=dt("2026-10-09T20:00:02Z"),
                payload={
                    "interval": "1m",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 10,
                    "final": True,
                    "provider_end": "2026-10-09T20:00:00+00:00",
                },
            ),
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="AAPL",
                kind=UpdateKind.STATUS,
                provenance=Provenance.REAL,
                data_time=dt("2026-10-09T20:00Z"),
                received_at=dt("2026-10-09T20:00Z"),
                payload={},
                state=SourceState.STALE,
            ),
        ]
    )
    return feed


def test_unknown_vendor_latency_is_explicit_across_live_consumers():
    feed = stock_feed()
    now = dt("2026-10-12T13:37Z")
    row = feed.latest_state(now=now)["instruments"]["moomoo:AAPL"]
    status = feed.statuses(now=now)["venues"][0]["sources"][0]
    assert "session_freshness" in row, "live state lacks the shared policy"
    assert row["session_freshness"] == status["session_freshness"]
    assert row["session_freshness"]["data_state"] == "unknown"
    assert row["session_freshness"]["market_state"] == "open"


@pytest.mark.parametrize(
    "now,delay,state",
    [
        ("2026-10-11T12:00Z", 0, "latest_session"),
        ("2026-10-11T12:00Z", None, "latest_session"),
        ("2026-10-12T13:37Z", 0, "delayed"),
        ("2026-10-12T13:37Z", 900, "fresh"),
    ],
)
def test_state_status_and_api_share_policy_without_renewing_quote_authority(
    monkeypatch,
    now,
    delay,
    state,
):
    feed = stock_feed(delay=delay)
    assert hasattr(feed, "provider_delays"), "no explicit provider-delay admission"
    clock = dt(now)

    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=UTC):
            return clock

    monkeypatch.setattr("quantmesh.live.feed.datetime", FrozenClock)
    app = FastAPI()
    app.state.live = feed
    app.include_router(live_router(), prefix="/api")
    with TestClient(app) as client:
        row = client.get("/api/live/state").json()["instruments"]["moomoo:AAPL"]
        status = client.get("/api/live/status").json()["venues"][0]["sources"][0]
    assert row["session_freshness"] == status["session_freshness"]
    assert row["session_freshness"]["data_state"] == state
    assert row["kinds"]["candle"]["session_freshness"] == row["session_freshness"]
    assert row["kinds"]["candle"]["age_ms"] > 30_000
    assert row["kinds"]["candle"]["provenance"] == "real"
    assert status["state"] == "stale"  # connector lifecycle evidence remains distinct
    snapshot = feed.snapshot_exact(Venue.MOOMOO, "AAPL", UpdateKind.CANDLE, as_of=clock)
    assert snapshot.freshness_label == "stale"


def test_partial_candle_preserves_previous_completed_session_coverage():
    feed = stock_feed(delay=0)
    now = dt("2026-10-12T13:37:20Z")
    complete = MarketUpdate(
        venue=Venue.MOOMOO,
        instrument="AAPL",
        kind=UpdateKind.CANDLE,
        provenance=Provenance.REAL,
        data_time=dt("2026-10-12T13:36Z"),
        received_at=dt("2026-10-12T13:37:01Z"),
        payload={
            "interval": "1m",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10,
            "final": True,
            "provider_end": "2026-10-12T13:37:00+00:00",
        },
    )
    partial = complete.model_copy(
        update={
            "data_time": dt("2026-10-12T13:37Z"),
            "received_at": now,
            "payload": {
                **complete.payload,
                "final": False,
                "provider_end": "2026-10-12T13:38:00+00:00",
            },
        }
    )
    feed.ingest([complete, partial])
    row = feed.latest_state(now=now)["instruments"]["moomoo:AAPL"]
    assert row["session_freshness"]["data_state"] == "fresh"
    assert row["session_freshness"]["last_source_at"] == "2026-10-12T13:37:00Z"
    assert (
        feed.statuses(now=now)["venues"][0]["sources"][0]["session_freshness"]
        == (row["session_freshness"])
    )


def test_candle_without_verified_end_metadata_cannot_certify_coverage():
    feed = LiveFeed(provider_delays={Venue.MOOMOO: 0})
    candle = stock_feed().snapshot_exact(
        Venue.MOOMOO,
        "AAPL",
        UpdateKind.CANDLE,
        as_of=dt("2026-10-12T13:37:21Z"),
    )
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="AAPL",
                kind=UpdateKind.CANDLE,
                provenance=Provenance.REAL,
                data_time=dt("2026-10-12T13:37Z"),
                received_at=dt("2026-10-12T13:37:21Z"),
                payload={
                    key: value for key, value in candle.payload.items() if key != "provider_end"
                },
            )
        ]
    )
    result = feed.latest_state(now=dt("2026-10-12T13:37:21Z"))["instruments"]["moomoo:AAPL"]
    assert result["session_freshness"]["data_state"] != "fresh"
