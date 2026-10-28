"""Tiny stored synthetic engineering observations through the normal factory."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import WorkstationConfigError, create_workstation_app
from quantmesh.data.manifest import DatasetManifest, SeriesCoverage
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.contracts import DatasetBinding, HistoryRange
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.live.buffer import _SCHEMA, LiveBuffer
from quantmesh.live.contract import MarketUpdate, UpdateKind
from quantmesh.live.feed import LiveFeed
from tests.test_history_inspection import AT, candle


@pytest.fixture(scope="module")
def saved_archive(tmp_path_factory):
    root = tmp_path_factory.mktemp("saved-history-profile")
    path = root / "live/updates.duckdb"
    path.parent.mkdir()
    events = [candle(3, 100), candle(2, 101), candle(1, 102)]
    events.append(
        MarketUpdate(
            venue="hyperliquid",
            instrument="GLOBAL",
            kind="quote",
            provenance="real",
            data_time=AT,
            received_at=AT,
            payload={"bid": 100, "ask": 101},
        )
    )
    events.extend([event.model_copy(update={"instrument": "GAP"}) for event in events[:3]])
    events.insert(
        6,
        MarketUpdate(
            venue="hyperliquid",
            instrument="GAP",
            kind="status",
            provenance="real",
            data_time=AT - timedelta(minutes=1, seconds=5),
            received_at=AT - timedelta(minutes=1, seconds=5),
            state="disconnected",
            payload={},
        ),
    )
    # Legacy stored identity conflict is intentionally rejected by the unchanged history rules.
    events.extend(
        [
            candle(2, 200, close=100).model_copy(
                update={"instrument": "CONFLICT", "source_event_id": "same"}
            ),
            candle(1, 201, close=101).model_copy(
                update={"instrument": "CONFLICT", "source_event_id": "same"}
            ),
        ]
    )
    rows = []
    for seq, event in enumerate(events, 1):
        rows.append(
            (
                seq,
                event.venue.value,
                event.instrument,
                event.kind.value,
                event.provenance.value,
                event.data_time,
                event.received_at,
                event.sequence,
                event.sequence_gap,
                event.continuity.value,
                event.source_event_id,
                None,
                event.snapshot_epoch,
                None,
                event.state.value if event.state else None,
                event.state_note,
                json.dumps(event.payload),
            )
        )
    with duckdb.connect(str(path)) as connection:
        connection.execute(_SCHEMA)
        connection.execute("INSERT INTO live_schema_metadata VALUES ('market_updates',2)")
        connection.executemany(
            "INSERT INTO market_updates VALUES (" + ",".join("?" for _ in range(17)) + ")", rows
        )
        connection.execute("CHECKPOINT")
    return root


def history_app(reader):
    feed = LiveFeed(lake=reader, history_only=True)
    service = LiveHistoryService(None, feed)
    account = PaperAccount(cash=0, kill_switch=True)
    app = create_workstation_app(account=account, history=service, host="127.0.0.1")
    return app, feed, service, account


def get(client, symbol="BTC", at=AT.isoformat(), **extra):
    return client.get(
        f"/api/instruments/hyperliquid/{symbol}/history-inspection", params={"at": at, **extra}
    )


def test_real_saved_range_without_global_cache_bootstrap(saved_archive, monkeypatch):
    path = saved_archive / "live/updates.duckdb"
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    with LiveBuffer(saved_archive, read_only=True) as reader:
        monkeypatch.setattr(
            reader, "latest", lambda **kw: pytest.fail("unrequested global bootstrap")
        )
        replay = reader.replay
        calls = []

        def observed(**kw):
            calls.append(kw)
            return replay(**kw)

        monkeypatch.setattr(reader, "replay", observed)
        app, feed, service, account = history_app(reader)
        assert feed.replay_buffer is reader and app.state.history is service
        assert not hasattr(app.state, "live") and calls == []
        settings = reader._con.execute(
            "SELECT current_setting('memory_limit'),current_setting('threads'),"
            "current_setting('max_temp_directory_size')"
        ).fetchone()
        assert settings == ("128.0 MiB", 1, "0 bytes")
        account_before = account.model_dump_json()
        clock_before = app.state.instrument_clock()
        with TestClient(app) as client:
            response = get(client)
            assert response.status_code == 200, response.text
            value = response.json()
            assert len(value["primary"]["bars"]) == 3
            assert value["source_time"] == "2026-10-23T23:43:00Z"
            assert value["source_received_at"] == "2026-10-23T23:43:30Z"
            assert value["window_end"] == AT.isoformat().replace("+00:00", "Z")
            assert clock_before <= datetime.fromisoformat(value["observed_at"]) <= datetime.now(UTC)
            assert value["stale"] is True and value["stale_after_seconds"] == 120
            assert value["primary"]["coverage"]["rows"] == 3
            for bar in value["primary"]["bars"]:
                assert [bar[key] for key in ("open", "high", "low", "close", "volume")] == [
                    100,
                    101,
                    99,
                    100,
                    10,
                ]
            assert all(not bar["is_live_tail"] for bar in value["primary"]["bars"])
            assert (
                client.get("/api/instruments/hyperliquid/BTC/history?range=1d").status_code == 404
            )
            assert (
                client.post(
                    "/api/instruments/hyperliquid/BTC/history-inspection",
                    params={"at": AT.isoformat()},
                ).status_code
                == 405
            )
        assert (
            account.model_dump_json() == account_before
            and app.state.instrument_clock() >= clock_before
        )
        assert len(calls) == 1
        assert calls[0] == dict(
            venue="hyperliquid",
            instrument="BTC",
            kinds={"candle", "status"},
            start=AT - timedelta(days=1),
            end=AT,
            data_time_start=AT - timedelta(days=1),
            data_time_end=AT,
            limit=10000,
            tail=True,
        )
    assert before == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)


def test_default_feed_still_hydrates_complete_global_latest(saved_archive, monkeypatch):
    with LiveBuffer(saved_archive, read_only=True) as reader:
        original = reader.latest
        calls = []

        def observed(**kw):
            calls.append(kw)
            return original(**kw)

        monkeypatch.setattr(reader, "latest", observed)
        feed = LiveFeed(lake=reader)
        assert calls == [{}]
        assert (
            feed.snapshot_exact(Venue.HYPERLIQUID, "GLOBAL", UpdateKind.QUOTE, as_of=AT) is not None
        )


@pytest.mark.parametrize(
    "at,extra",
    [("2999-01-01T00:00:00Z", {}), ("2026-10-23T23:44:01", {}), (AT.isoformat(), {"range": "5d"})],
)
def test_invalid_selection_refuses_before_any_replay(saved_archive, monkeypatch, at, extra):
    with LiveBuffer(saved_archive, read_only=True) as reader:
        app, *_ = history_app(reader)
        monkeypatch.setattr(reader, "replay", lambda **kw: pytest.fail("read before validation"))
        with TestClient(app) as client:
            assert get(client, at=at, **extra).status_code == 422


@pytest.mark.parametrize("symbol", ["MISSING", "GAP", "CONFLICT"])
def test_missing_gap_and_identity_conflict_do_not_become_history(saved_archive, symbol):
    with LiveBuffer(saved_archive, read_only=True) as reader:
        app, *_ = history_app(reader)
        with TestClient(app) as client:
            assert get(client, symbol=symbol).status_code == 404


@pytest.mark.parametrize("error", [ValueError, duckdb.IOException, duckdb.OutOfMemoryException])
def test_read_failure_is_explicit_unavailable(saved_archive, monkeypatch, error):
    with LiveBuffer(saved_archive, read_only=True) as reader:
        app, *_ = history_app(reader)

        def fail(**kw):
            raise error("modeled stored read refusal")

        monkeypatch.setattr(reader, "replay", fail)
        with TestClient(app) as client:
            assert get(client).status_code == 404


def test_history_profile_cannot_become_live_or_mutate(saved_archive):
    with LiveBuffer(saved_archive, read_only=True) as reader:
        _, feed, service, _ = history_app(reader)
        actions = [
            lambda: feed.attach(object()),
            lambda: feed.ingest([candle(1, 1)]),
            lambda: feed.publish_threadsafe(candle(1, 1)),
            lambda: asyncio.run(feed.publish(candle(1, 1))),
            lambda: asyncio.run(feed.run()),
            lambda: feed.subscribe(),
            lambda: feed.prune_if_due(AT),
            lambda: feed.latest_state(),
            lambda: feed.statuses(),
            lambda: feed.session_coverage(Venue.HYPERLIQUID, "BTC"),
            lambda: feed.snapshot_exact(Venue.HYPERLIQUID, "BTC", UpdateKind.CANDLE, as_of=AT),
        ]
        for action in actions:
            with pytest.raises(RuntimeError, match="historical"):
                action()
        with pytest.raises(RuntimeError, match="historical"):
            feed.capture_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                clock=lambda: pytest.fail("historical profile sampled current clock"),
            )
        with pytest.raises(HistoryUnavailableError, match="historical"):
            service.history(Venue.HYPERLIQUID, "BTC", HistoryRange.ONE_DAY, as_of=AT)
        with pytest.raises(HistoryUnavailableError, match="historical"):
            service.compare(
                primary=(Venue.HYPERLIQUID, "BTC"), peers=[], range=HistoryRange.ONE_DAY
            )
        with pytest.raises(WorkstationConfigError, match="historical"):
            create_workstation_app(account=PaperAccount(cash=0), live_feed=feed, host="127.0.0.1")


def test_history_profile_requires_readable_readonly_lake(saved_archive, tmp_path_factory):
    with pytest.raises(ValueError, match="read.only"):
        LiveFeed(history_only=True)
    with LiveBuffer(saved_archive, read_only=True) as reader:
        reader.read_unavailable = True
        with pytest.raises(ValueError, match="read.only"):
            LiveFeed(lake=reader, history_only=True)
    with LiveBuffer(
        tmp_path_factory.mktemp("writable-profile-refusal"), retention_days=0
    ) as writer:
        with pytest.raises(ValueError, match="read.only"):
            LiveFeed(lake=writer, history_only=True)
    with pytest.raises(ValueError, match="boolean"):
        LiveFeed(history_only=1)


def test_real_manifest_priority_retains_unknown_receipt(saved_archive, monkeypatch):
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    rows = [
        Bar(
            instrument=instrument,
            timestamp=AT.replace(second=0) - timedelta(minutes=i),
            interval="5m",
            open=99,
            high=100,
            low=98,
            close=99,
            volume=1,
        )
        for i in (10, 5)
    ]

    class Dataset:
        name = "synthetic-profile-manifest"
        manifest = DatasetManifest(
            revision=1,
            dataset=name,
            source="SYNTHETIC ENGINEERING FIXTURE",
            license="engineering-only",
            generated_at=AT,
            coverage=[
                SeriesCoverage(
                    interval="5m",
                    venue=Venue.HYPERLIQUID,
                    symbol="BTC",
                    start=rows[0].timestamp,
                    end=rows[-1].timestamp,
                    rows=2,
                )
            ],
        )

        def read_bars(self, **kwargs):
            return rows

    dataset = Dataset()
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
    with LiveBuffer(saved_archive, read_only=True) as reader:
        feed = LiveFeed(lake=reader, history_only=True)
        service = LiveHistoryService(historical, feed)
        monkeypatch.setattr(
            reader, "replay", lambda **kw: pytest.fail("manifest must remain first")
        )
        app = create_workstation_app(
            account=PaperAccount(cash=0), history=service, host="127.0.0.1"
        )
        with TestClient(app) as client:
            response = get(client)
            assert response.status_code == 200, response.text
            assert len(response.json()["primary"]["bars"]) == 2
            assert response.json()["source_received_at"] is None
