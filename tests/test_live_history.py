"""Live workstation history assembly and shared live-tail composition."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.data.lake import Lake
from quantmesh.data.manifest import DatasetClass, ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.live_history import discover_history_bindings
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)
from quantmesh.live.feed import LiveFeed


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


def test_live_only_history_fails_closed_when_only_finer_interval_exists(
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
