"""Live workstation history assembly and shared live-tail composition."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.data.lake import Lake
from quantmesh.data.manifest import DatasetClass, ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.history import HistoryService
from quantmesh.instruments.live_history import discover_history_bindings
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, ScriptedHyperliquidTransport


def _candle(
    timestamp: datetime,
    *,
    sequence: int,
    close: float,
    interval: str = "5m",
    received_at: datetime | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue="hyperliquid",
        instrument="BTC",
        kind=UpdateKind.CANDLE,
        provenance=Provenance.REAL,
        data_time=timestamp,
        received_at=received_at or timestamp + timedelta(milliseconds=1),
        sequence=sequence,
        sequence_gap=False,
        payload={
            "interval": interval,
            "open": close - 0.2,
            "high": close + 0.4,
            "low": close - 0.5,
            "close": close,
            "volume": 10.0,
        },
    )


def test_live_only_workstation_serves_one_shared_continuity_checked_series(
    tmp_path: Path,
) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest(
        [
            _candle(anchor - timedelta(minutes=5), sequence=100, close=100.0),
            _candle(anchor, sequence=101, close=101.0),
        ]
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor + timedelta(milliseconds=1),
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        history = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        workspace = client.get("/api/instruments/hyperliquid/BTC/workspace?range=1d")

    assert history.status_code == 200
    assert workspace.status_code == 200
    history_primary = history.json()["primary"]
    workspace_history = workspace.json()["history"]
    assert history_primary["source"] == "hyperliquid-live-replay"
    assert workspace_history["source"] == "hyperliquid-live-replay"
    assert history_primary["interval"] == "5m"
    assert history_primary["resolution_fallback"] is None
    assert (
        history_primary["bars"][-1]["live_lineage"]
        == (workspace_history["bars"][-1]["live_lineage"])
    )
    assert history_primary["bars"][-1]["is_live_tail"] is True
    assert any("local live replay" in item for item in workspace_history["limitations"])
    buffer.close()


def test_live_only_history_selects_nearest_coarser_interval_and_reports_fallback(
    tmp_path: Path,
) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest(
        [
            _candle(
                anchor - timedelta(minutes=1),
                sequence=100,
                close=100.0,
                interval="1m",
            ),
            _candle(anchor, sequence=101, close=101.0, interval="1m"),
            _candle(
                anchor - timedelta(minutes=30),
                sequence=200,
                close=300.0,
                interval="30m",
            ),
            _candle(anchor, sequence=201, close=301.0, interval="30m"),
        ]
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor + timedelta(milliseconds=1),
        host="127.0.0.1",
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")

        assert response.status_code == 200, response.text
        primary = response.json()["primary"]
        assert primary["interval"] == "30m"
        assert primary["resolution_fallback"] == "5m->30m"
        assert [bar["close"] for bar in primary["bars"]] == [300.0, 301.0]
    finally:
        buffer.close()


@pytest.mark.parametrize("selected_range", ["5d", "1m", "3m", "6m", "1y"])
def test_live_only_history_fails_closed_for_unsupported_ranges(
    tmp_path: Path,
    selected_range: str,
) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest(
        [
            _candle(
                anchor - timedelta(minutes=1),
                sequence=100,
                close=100.0,
                interval="1m",
            ),
            _candle(anchor, sequence=101, close=101.0, interval="1m"),
        ]
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor + timedelta(milliseconds=1),
        host="127.0.0.1",
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/instruments/hyperliquid/BTC/history?range={selected_range}"
            )

        assert response.status_code == 404
        assert "no replay candles" in response.json()["detail"]
    finally:
        buffer.close()


def test_live_replay_disconnect_barrier_refuses_to_bridge_candles(tmp_path: Path) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest([_candle(anchor - timedelta(minutes=5), sequence=100, close=100.0)])
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.HYPERLIQUID,
                instrument="BTC",
                kind=UpdateKind.STATUS,
                provenance=Provenance.UNAVAILABLE,
                data_time=anchor - timedelta(seconds=30),
                received_at=anchor - timedelta(seconds=30),
                sequence=100,
                sequence_gap=False,
                state=SourceState.DISCONNECTED,
                state_note="scripted reconnect barrier",
                payload={},
            ),
            _candle(anchor, sequence=101, close=101.0),
        ]
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor + timedelta(milliseconds=1),
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")

    assert response.status_code == 404
    assert "continuity is not proven" in response.json()["detail"]
    buffer.close()


def test_live_replay_range_excludes_recently_received_old_backfill(tmp_path: Path) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest(
        [
            _candle(
                anchor - timedelta(days=14, minutes=1),
                sequence=100,
                close=100.0,
                received_at=anchor - timedelta(seconds=2),
            ),
            _candle(
                anchor - timedelta(days=14),
                sequence=101,
                close=101.0,
                received_at=anchor - timedelta(seconds=1),
            ),
        ]
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor,
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")

    assert response.status_code == 404
    assert "no replay candles" in response.json()["detail"]
    buffer.close()


def test_live_replay_range_includes_market_data_at_lower_bound(tmp_path: Path) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    lower_bound = anchor - timedelta(days=1)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest(
        [
            _candle(
                lower_bound,
                sequence=100,
                close=100.0,
                received_at=anchor - timedelta(seconds=2),
            ),
            _candle(
                lower_bound + timedelta(minutes=5),
                sequence=101,
                close=101.0,
                received_at=anchor - timedelta(seconds=1),
            ),
        ]
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor,
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")

    assert response.status_code == 200
    timestamps = [item["timestamp"] for item in response.json()["primary"]["bars"]]
    assert datetime.fromisoformat(timestamps[0].replace("Z", "+00:00")) == lower_bound
    buffer.close()


def test_live_replay_range_filters_data_time_before_tail_limit(tmp_path: Path) -> None:
    anchor = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    buffer = LiveBuffer(tmp_path / "lake")
    feed = LiveFeed(lake=buffer)
    feed.ingest(
        [
            _candle(
                anchor - timedelta(minutes=5),
                sequence=100,
                close=100.0,
                received_at=anchor - timedelta(seconds=2),
            ),
            _candle(
                anchor,
                sequence=101,
                close=101.0,
                received_at=anchor - timedelta(seconds=1),
            ),
        ]
    )
    # Use one bulk fixture write so this cardinality regression remains fast.
    # The assertion still exercises the public workstation history API.
    buffer._con.execute(
        "INSERT INTO market_updates "
        "(local_seq, venue, instrument, kind, provenance, data_time, received_at, "
        "sequence, sequence_gap, state, state_note, payload_json) "
        "SELECT index + 3, 'hyperliquid', 'BTC', 'status', 'unavailable', "
        "CASE WHEN index % 2 = 0 THEN ? ELSE ? END, ?, "
        "index + 102, FALSE, 'stale', 'out-of-range data-time distraction', '{}' "
        "FROM range(10001) AS generated(index)",
        [
            anchor - timedelta(days=1, seconds=1),
            anchor + timedelta(microseconds=1),
            anchor - timedelta(milliseconds=1),
        ],
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        workspace_clock=lambda: anchor,
        host="127.0.0.1",
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")

        assert response.status_code == 200, response.text
        assert [bar["close"] for bar in response.json()["primary"]["bars"]] == [
            100.0,
            101.0,
        ]
    finally:
        buffer.close()


def test_live_binding_discovery_uses_structured_dataset_class(tmp_path: Path) -> None:
    instrument = Instrument(
        symbol="NVDA",
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )
    lake = Lake(tmp_path)
    datasets = (
        ("observed", "demo contest feed", DatasetClass.OBSERVED),
        ("synthetic", "generated-data", DatasetClass.SYNTHETIC),
        ("legacy", "operator-import", None),
    )
    for dataset, source, data_class in datasets:
        lake.write_bars(
            dataset,
            [
                Bar(
                    instrument=instrument,
                    timestamp=datetime(2026, 8, 11, tzinfo=UTC),
                    interval="1d",
                    open=100.0,
                    high=102.0,
                    low=99.0,
                    close=101.0,
                    volume=1_000.0,
                )
            ],
        )
        ManifestWriter(tmp_path).generate(
            dataset,
            source=source,
            license="operator-supplied",
            data_class=data_class,
        )

    bindings = discover_history_bindings(tmp_path)

    assert [binding.dataset_id for binding in bindings] == ["observed"]


# Real subscription shape and source-derived candle identity; only the local
# receipt clock is fixed so API/replay assertions remain deterministic.
def _production_candle(symbol: str, opened: datetime, received: datetime, close: float):
    supervisor = HyperliquidVenueSupervisor(ScriptedHyperliquidTransport([]))
    supervisor.subscribe([symbol])
    opened_ms = int(opened.timestamp() * 1000)
    [update] = supervisor.dispatch(
        {
            "channel": "candle",
            "data": {
                "t": opened_ms,
                "T": opened_ms + 59_999,
                "s": symbol,
                "i": "1m",
                "o": "100",
                "h": "110",
                "l": "90",
                "c": str(close),
                "v": "10",
                "n": 3,
            },
        },
        received,
    )
    return update.model_copy(update={"received_at": received})


def _history_pair(feed: LiveFeed, now: datetime, symbol: str = "BTC"):
    app = create_workstation_app(
        account=PaperAccount(cash=100_000),
        live_feed=feed,
        workspace_clock=lambda: now,
        host="127.0.0.1",
    )
    with TestClient(app) as client:
        history = client.get(f"/api/instruments/hyperliquid/{symbol}/history?range=1d")
        workspace = client.get(f"/api/instruments/hyperliquid/{symbol}/workspace?range=1d")
    return history, workspace


@pytest.mark.parametrize("interval,minutes", [("5m", 5), ("30m", 30)])
@pytest.mark.parametrize("state", ["single", "gapped", "invalid", "valid"])
def test_minute_replay_fallback_requires_usable_preferred_candidate(
    tmp_path: Path, interval, minutes, state
):
    anchor = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        candidates = []
        if state != "single":
            candidates.append(
                _candle(
                    anchor - timedelta(minutes=minutes * (2 if state == "gapped" else 1)),
                    sequence=200,
                    close=300,
                    interval=interval,
                )
            )
        latest = _candle(anchor, sequence=201, close=301, interval=interval)
        if state == "invalid":
            # Zero OHLC is storable, but cannot become positive-price history.
            latest = MarketUpdate.model_validate(
                {
                    **latest.model_dump(),
                    "content_digest": None,
                    "payload": {**latest.payload, "open": 0, "high": 0, "low": 0, "close": 0},
                }
            )
        candidates.append(latest)
        feed.ingest(candidates)
        feed.ingest(
            [
                _production_candle("BTC", anchor - timedelta(minutes=1), anchor, 100),
                _production_candle("BTC", anchor, anchor + timedelta(seconds=1), 101),
            ]
        )
        history, workspace = _history_pair(feed, anchor + timedelta(seconds=2))
        assert history.status_code == workspace.status_code == 200
        primary = history.json()["primary"]
        assert primary == workspace.json()["history"]
        if state == "valid":
            assert primary["interval"] == interval
            assert [bar["close"] for bar in primary["bars"]] == [300, 301]
            assert primary["resolution_fallback"] == (None if interval == "5m" else "5m->30m")
        else:
            assert primary["interval"] == "1m"
            assert primary["resolution_fallback"] == "5m->1m"
            assert [bar["close"] for bar in primary["bars"]] == [100, 101]
            assert primary["coverage"]["rows"] == 2


@pytest.mark.parametrize("endpoint", ["history", "workspace"])
def test_minute_replay_live_append_after_replay_capture_keeps_exact_coverage(
    tmp_path: Path, monkeypatch, endpoint
):
    anchor = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    now = anchor + timedelta(minutes=2, seconds=2)
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [
                _production_candle("BTC", anchor, anchor + timedelta(seconds=1), 100),
                _production_candle(
                    "BTC",
                    anchor + timedelta(minutes=1),
                    anchor + timedelta(minutes=1, seconds=1),
                    101,
                ),
            ]
        )
        replay = buffer.replay

        def capture_then_advance(**kwargs):
            captured = replay(**kwargs)
            feed.ingest(
                [
                    _production_candle(
                        "BTC", anchor + timedelta(minutes=2), now - timedelta(seconds=1), 103
                    )
                ]
            )
            return captured

        monkeypatch.setattr(buffer, "replay", capture_then_advance)
        app = create_workstation_app(
            account=PaperAccount(cash=100_000),
            live_feed=feed,
            workspace_clock=lambda: now,
            host="127.0.0.1",
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/api/instruments/hyperliquid/BTC/{endpoint}?range=1d")
        assert response.status_code == 200, response.text
        series = response.json()["primary" if endpoint == "history" else "history"]
        assert [bar["close"] for bar in series["bars"]] == [100, 101, 103]
        assert series["coverage"]["rows"] == 3
        assert series["coverage"]["end"] == series["bars"][-1]["timestamp"]
        assert series["bars"][-1]["is_live_tail"] is True
        lineage_received_at = datetime.fromisoformat(
            series["bars"][-1]["live_lineage"]["received_at"].replace("Z", "+00:00")
        )
        assert lineage_received_at == now - timedelta(seconds=1)
        assert datetime.fromisoformat(series["generated_at"].replace("Z", "+00:00")) >= (
            lineage_received_at
        )
        assert not any("manifest coverage" in value for value in series["limitations"])


@pytest.mark.parametrize("symbol", ["BTC", "ETH", "SOL"])
def test_production_minute_candles_revise_append_and_survive_reopen(tmp_path: Path, symbol):
    anchor = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    root = tmp_path / "replay"
    with LiveBuffer(root) as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [
                _production_candle(symbol, anchor - timedelta(minutes=1), anchor, 100),
                _production_candle(symbol, anchor, anchor + timedelta(seconds=1), 101),
            ]
        )
        history, workspace = _history_pair(feed, anchor + timedelta(seconds=2), symbol)
        assert history.status_code == 200, history.text
        assert workspace.status_code == 200, workspace.text
        first = history.json()["primary"]
        assert first == workspace.json()["history"]
        assert first["interval"] == "1m"
        assert first["resolution_fallback"] == "5m->1m"
        assert first["source"] == "hyperliquid-live-replay"
        assert first["calendar"] == "24/7"
        assert first["manifest_id"] is None
        assert first["coverage"]["rows"] == 2
        assert [bar["close"] for bar in first["bars"]] == [100, 101]

        feed.ingest([_production_candle(symbol, anchor, anchor + timedelta(seconds=10), 102)])
        history, workspace = _history_pair(feed, anchor + timedelta(seconds=11), symbol)
        revised = history.json()["primary"]
        assert revised == workspace.json()["history"]
        assert [bar["close"] for bar in revised["bars"]] == [100, 102]
        assert revised["coverage"]["rows"] == 2
        tail = revised["bars"][-1]
        assert tail["is_live_tail"] is True
        assert tail["live_lineage"]["sequence"] == int(anchor.timestamp() * 1000)
        assert (
            datetime.fromisoformat(tail["live_lineage"]["data_time"].replace("Z", "+00:00"))
            == anchor
        )

        next_open = anchor + timedelta(minutes=1)
        feed.ingest([_production_candle(symbol, next_open, next_open + timedelta(seconds=1), 103)])
        history, workspace = _history_pair(feed, next_open + timedelta(seconds=2), symbol)
        appended = history.json()["primary"]
        assert appended == workspace.json()["history"]
        assert [bar["close"] for bar in appended["bars"]] == [100, 102, 103]
        assert appended["coverage"]["rows"] == 3
        assert any("local live replay" in value for value in appended["limitations"])

    with LiveBuffer(root) as reopened:
        history, workspace = _history_pair(
            LiveFeed(lake=reopened), next_open + timedelta(seconds=3), symbol
        )
        assert history.status_code == 200, history.text
        assert workspace.status_code == 200, workspace.text
        replayed = history.json()["primary"]
        assert replayed == workspace.json()["history"]
        assert replayed["coverage"] == appended["coverage"]
        assert [bar["close"] for bar in replayed["bars"]] == [100, 102, 103]
        # A reopened cache has no predecessor proof yet, so it cannot claim a live tail.
        assert replayed["bars"][-1]["is_live_tail"] is False


@pytest.mark.parametrize("venue", [Venue.MOOMOO, Venue.POLYMARKET, Venue.KALSHI])
def test_minute_replay_fallback_does_not_expand_other_venues(tmp_path: Path, venue):
    anchor = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        for index in [0, 1]:
            update = _candle(
                anchor + timedelta(minutes=index), sequence=index, close=100, interval="1m"
            )
            feed.ingest(
                [
                    MarketUpdate(
                        **{
                            **update.model_dump(),
                            "venue": venue,
                            "source_event_id": None,
                            "content_digest": None,
                        }
                    )
                ]
            )
        app = create_workstation_app(
            account=PaperAccount(cash=100_000),
            live_feed=feed,
            workspace_clock=lambda: anchor + timedelta(minutes=1, seconds=1),
            host="127.0.0.1",
        )
        with TestClient(app) as client:
            response = client.get(f"/api/instruments/{venue.value}/BTC/history?range=1d")
        assert response.status_code == 404
        assert "preferred or a coarser resolution" in response.json()["detail"]


@pytest.mark.parametrize("state", ["empty", "single", "missing-minute", "disconnected"])
def test_minute_replay_collecting_and_gaps_never_fabricate_continuity(tmp_path: Path, state):
    anchor = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    with LiveBuffer(tmp_path / "replay") as buffer:
        feed = LiveFeed(lake=buffer)
        if state != "empty":
            feed.ingest([_production_candle("BTC", anchor, anchor + timedelta(seconds=1), 100)])
        if state == "disconnected":
            feed.ingest(
                [
                    MarketUpdate(
                        venue=Venue.HYPERLIQUID,
                        instrument="BTC",
                        kind=UpdateKind.STATUS,
                        provenance=Provenance.UNAVAILABLE,
                        data_time=anchor + timedelta(seconds=30),
                        received_at=anchor + timedelta(seconds=30),
                        state=SourceState.DISCONNECTED,
                        payload={},
                    )
                ]
            )
        if state in {"missing-minute", "disconnected"}:
            second = anchor + timedelta(minutes=2 if state == "missing-minute" else 1)
            feed.ingest([_production_candle("BTC", second, second + timedelta(seconds=1), 101)])
        history, workspace = _history_pair(feed, anchor + timedelta(minutes=3))
        assert history.status_code == workspace.status_code == 404
        expected = "no replay candles" if state == "empty" else "continuity is not proven"
        assert expected in history.json()["detail"]
        assert expected in workspace.json()["detail"]
        if state in {"missing-minute", "disconnected"}:
            recovered = second + timedelta(minutes=1)
            feed.ingest(
                [_production_candle("BTC", recovered, recovered + timedelta(seconds=1), 102)]
            )
            history, workspace = _history_pair(feed, recovered + timedelta(seconds=2))
            assert history.status_code == workspace.status_code == 200
            primary = history.json()["primary"]
            assert [bar["close"] for bar in primary["bars"]] == [101, 102]
            assert primary["coverage"]["rows"] == 2
            assert (
                datetime.fromisoformat(primary["coverage"]["start"].replace("Z", "+00:00"))
                == second
            )


@pytest.mark.parametrize("live_interval", ["1m", "5m"])
def test_minute_replay_fallback_does_not_replace_manifest_history(tmp_path: Path, live_interval):
    anchor = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    root = tmp_path / "lake"
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    lake = Lake(root)
    lake.write_bars(
        "observed-btc",
        [
            Bar(
                instrument=instrument,
                timestamp=anchor - timedelta(minutes=5),
                interval="5m",
                open=90,
                high=92,
                low=89,
                close=91,
                volume=10,
            )
        ],
    )
    ManifestWriter(root).generate(
        "observed-btc",
        source="operator-import",
        license="operator-supplied",
        data_class=DatasetClass.OBSERVED,
        generated_at=anchor - timedelta(hours=1),
    )
    historical = HistoryService(discover_history_bindings(root), dataset_loader=lake.dataset)
    with LiveBuffer(root) as buffer:
        feed = LiveFeed(lake=buffer)
        feed.ingest(
            [
                _production_candle("BTC", anchor - timedelta(minutes=1), anchor, 100),
                _production_candle("BTC", anchor, anchor + timedelta(seconds=1), 101),
            ]
        )
        if live_interval == "5m":
            feed.ingest(
                [
                    _candle(anchor - timedelta(minutes=5), sequence=200, close=100),
                    _candle(anchor, sequence=201, close=101),
                ]
            )
        app = create_workstation_app(
            account=PaperAccount(cash=100_000),
            live_feed=feed,
            history=historical,
            workspace_clock=lambda: anchor + timedelta(seconds=2),
            host="127.0.0.1",
        )
        with TestClient(app) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200, response.text
        primary = response.json()["primary"]
        assert primary["dataset_id"] == "observed-btc"
        assert primary["source"] == "operator-import"
        assert primary["resolution_fallback"] is None
        assert primary["interval"] == "5m"
        assert [bar["close"] for bar in primary["bars"]] == (
            [91, 101] if live_interval == "5m" else [91]
        )
        assert datetime.fromisoformat(primary["generated_at"].replace("Z", "+00:00")) == (
            anchor - timedelta(hours=1)
        )
        assert primary["coverage"]["rows"] == 1
        if live_interval == "5m":
            assert primary["bars"][-1]["is_live_tail"] is True
