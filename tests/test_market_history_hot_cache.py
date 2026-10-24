"""Approved B uses tiny synthetic observations in actual DuckDB, never the host lake."""

import asyncio
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live import buffer as buffer_module
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import ContinuityState, MarketUpdate, SourceState, UpdateKind
from quantmesh.live.feed import LiveFeed
from tests.test_live_history import _candle

AT = datetime(2026, 10, 24, 0, 10, tzinfo=UTC)


def candles():
    return [
        _candle(AT - timedelta(minutes=10 - i * 5), sequence=100 + i, close=100.0 + i)
        for i in range(3)
    ]


def seed(root, updates):
    with LiveBuffer(root, retention_days=0) as buffer:
        buffer.append_many(updates)


def history_client(feed, archive):
    return TestClient(
        create_workstation_app(
            account=PaperAccount(cash=100_000.0),
            live_feed=feed,
            history_archive_root=archive,
            workspace_clock=lambda: AT + timedelta(seconds=1),
            host="127.0.0.1",
        )
    )


def test_archive_read_only_never_mutates_original_or_allows_writes(tmp_path):
    root = tmp_path / "archive"
    seed(root, candles()[:2])
    path = root / "live/updates.duckdb"
    original, mtime = path.read_bytes(), path.stat().st_mtime_ns
    with LiveBuffer(root, read_only=True) as archive:
        assert len(archive.replay()) == 2
        with pytest.raises(ValueError, match="read.only"):
            archive.append(candles()[2])
        with pytest.raises(ValueError, match="read.only"):
            archive.prune()
    assert path.read_bytes() == original and path.stat().st_mtime_ns == mtime
    assert not path.with_suffix(".duckdb.wal").exists()


def test_read_only_missing_archive_is_not_created(tmp_path):
    root = tmp_path / "absent"
    with pytest.raises(ValueError, match="archive"):
        LiveBuffer(root, read_only=True)
    assert not root.exists()


def test_read_only_incompatible_schema_does_not_migrate(tmp_path):
    root = tmp_path / "old"
    path = root / "live/updates.duckdb"
    path.parent.mkdir(parents=True)
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE market_updates(local_seq BIGINT)")
    original = path.read_bytes()
    with pytest.raises(ValueError, match="archive"):
        LiveBuffer(root, read_only=True)
    assert path.read_bytes() == original


def test_existing_history_url_reads_archive_and_hot_with_independent_local_seq(tmp_path):
    root = tmp_path / "archive"
    seed(root, candles()[:2])
    original = (root / "live/updates.duckdb").read_bytes()
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        feed = LiveFeed(lake=hot)
        feed.ingest(candles()[2:])  # hot local_seq=1, archive local_seq=1,2
        with history_client(feed, root) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200, response.text
        primary = response.json()["primary"]
        assert [bar["close"] for bar in primary["bars"]] == [100.0, 101.0, 102.0]
        assert primary["source"] == "hyperliquid-live-replay"
        assert any("archive" in limitation.lower() for limitation in primary["limitations"])
    assert (root / "live/updates.duckdb").read_bytes() == original


def test_bad_archive_is_explicit_unavailable_even_when_hot_alone_is_valid(tmp_path):
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        feed = LiveFeed(lake=hot)
        feed.ingest(candles())
        with history_client(feed, tmp_path / "absent") as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 404
        assert "archive" in response.json()["detail"].lower()


@pytest.mark.parametrize("conflict", [False, True])
def test_cross_store_event_digest_dedup_or_conflict(tmp_path, conflict):
    root = tmp_path / "archive"
    rows = candles()
    seed(root, rows[:2])
    duplicate = rows[1]
    if conflict:
        duplicate = _candle(duplicate.data_time, sequence=101, close=999.0).model_copy(
            update={"source_event_id": duplicate.source_event_id, "content_digest": None}
        )
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        feed = LiveFeed(lake=hot)
        feed.ingest([duplicate, rows[2]])
        with history_client(feed, root) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        if conflict:
            assert response.status_code == 404
            assert "conflict" in response.json()["detail"].lower()
        else:
            assert response.status_code == 200, response.text
            assert len(response.json()["primary"]["bars"]) == 3


def budget_spec(root, *, operations=3):
    return {
        "schema_version": 1,
        "root": str(root.resolve()),
        "ledger_sha256": "a" * 64,
        "peak_bound_sha256": "b" * 64,
        "leaf_remaining_bytes": operations * 8_000_000 + 1_000_000,
        "global_reserved_bytes": operations * 8_000_000 + 1_000_000,
        "peak_operation_bytes": 8_000_000,
        "close_failure_reserve_bytes": 1_000_000,
        "max_batch_bytes": 65536,
        "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }


def test_hot_budget_consumes_reservations_before_io_without_restart_refund(tmp_path):
    root = tmp_path / "hot"
    spec = budget_spec(root)
    budget = buffer_module.HotCacheBudget(root, spec)
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:
        hot.append(candles()[0])
    # Startup + append consumed two complete peak reservations, not actual small growth.
    reopened = buffer_module.HotCacheBudget(root, spec)
    with LiveBuffer(root, retention_days=0, write_budget=reopened) as hot:
        with pytest.raises(buffer_module.LiveCapacityExceeded):
            hot.append(candles()[1])
        assert len(hot.replay()) == 1
    assert len(list(root.glob("budget-intent-*.json"))) == 3


def test_hot_budget_failure_keeps_charge_and_atomic_book_validation(tmp_path, monkeypatch):
    root = tmp_path / "hot"
    budget = buffer_module.HotCacheBudget(root, budget_spec(root, operations=2))
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:

        def fail(update, seq):
            raise OSError("synthetic write failure")

        monkeypatch.setattr(hot, "_insert_update", fail)
        with pytest.raises(OSError):
            hot.append(candles()[0])
        with pytest.raises(buffer_module.LiveCapacityExceeded):
            hot.append(candles()[0])
        assert hot.replay() == []
    assert len(list(root.glob("budget-intent-*.json"))) == 2


def test_hot_budget_refuses_unknown_peak_or_wrong_root_before_materialization(tmp_path):
    root = tmp_path / "hot"
    for key, value in [("peak_bound_sha256", "0" * 64), ("root", str(tmp_path))]:
        spec = budget_spec(root)
        spec[key] = value
        with pytest.raises(ValueError, match="budget"):
            buffer_module.HotCacheBudget(root, spec)
        assert not root.exists()


def test_hot_budget_never_enables_retention_or_replenishes_existing_data(tmp_path):
    root = tmp_path / "hot"
    seed(root, candles())
    with pytest.raises(ValueError, match="budget"):
        buffer_module.HotCacheBudget(root, budget_spec(root))
    fresh = tmp_path / "fresh"
    budget = buffer_module.HotCacheBudget(fresh, budget_spec(fresh))
    with pytest.raises(ValueError, match="retention"):
        LiveBuffer(fresh, retention_days=7, write_budget=budget)


def test_capacity_stop_joins_providers_and_keeps_original_history_url(tmp_path):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    root = tmp_path / "hot"
    budget = buffer_module.HotCacheBudget(root, budget_spec(root, operations=3))
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:
        feed = LiveFeed(lake=hot)
        feed.ingest(candles()[2:])
        supervisor = ScriptedSupervisor([])
        feed.attach(supervisor)
        subscriber = feed.subscribe()

        async def scenario():
            pump = asyncio.create_task(feed.run())
            await asyncio.sleep(0)
            budget.expires = datetime.now(UTC) - timedelta(seconds=1)
            with pytest.raises(buffer_module.LiveCapacityExceeded):
                await feed.publish(candles()[2])
            await asyncio.wait_for(pump, 2)
            assert feed.capacity_exhausted and feed._stopped
            assert subscriber.empty()
            assert len(hot.replay()) == 1

        asyncio.run(scenario())
        with history_client(feed, archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200, response.text
        assert len(response.json()["primary"]["bars"]) == 3


def test_exhausted_hot_reopens_read_only_without_consuming_new_budget(tmp_path):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=2)
    with LiveBuffer(
        root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)
    ) as hot:
        hot.append_many(candles())
    budget = buffer_module.HotCacheBudget(root, spec)
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert hot.read_only
        feed = LiveFeed(lake=hot)
        asyncio.run(feed.run())  # no supervisor starts when no further write is authorized
        assert feed.capacity_exhausted
        assert len(hot.replay()) == 3
    assert len(list(root.glob("budget-intent-*.json"))) == 2


def test_settings_refuse_half_configured_or_aliased_hot_root(tmp_path):
    from quantmesh.settings import Settings

    with pytest.raises(ValueError, match="hot"):
        Settings(live_cache_root=tmp_path)
    with pytest.raises(ValueError, match="hot"):
        Settings(
            live_cache_root=tmp_path,
            live_cache_budget_file=tmp_path / "budget.json",
            lake_root=tmp_path,
        )


def test_duplicate_identity_cannot_hide_new_unknown_continuity(tmp_path):
    archive = tmp_path / "archive"
    rows = candles()
    seed(archive, rows[:2])
    unknown = rows[1].model_copy(
        update={
            "continuity": ContinuityState.UNKNOWN_AFTER_DISCONNECT,
            "sequence_gap": True,
        }
    )
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        feed = LiveFeed(lake=hot)
        feed.ingest([unknown, rows[2]])
        with history_client(feed, archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 404
        assert "conflict" in response.json()["detail"].lower()


def test_capacity_refusal_is_durable_and_does_not_auto_rearm(tmp_path):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=1)
    with LiveBuffer(
        root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)
    ) as hot:
        with pytest.raises(buffer_module.LiveCapacityExceeded):
            hot.append(candles()[0])
        stop = (root / "budget-stop.json").read_bytes()
    assert b"capacity_exhausted" in stop
    budget = buffer_module.HotCacheBudget(root, spec)
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert hot.read_only
    assert (root / "budget-stop.json").read_bytes() == stop


def test_final_admitted_commit_is_delivered_then_stops_without_next_write(tmp_path):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    root = tmp_path / "hot"
    budget = buffer_module.HotCacheBudget(root, budget_spec(root, operations=2))
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:
        feed = LiveFeed(lake=hot)
        supervisor = ScriptedSupervisor([])
        feed.attach(supervisor)
        subscriber = feed.subscribe()

        async def scenario():
            pump = asyncio.create_task(feed.run())
            await asyncio.sleep(0)
            await feed.publish(candles()[0])
            await asyncio.wait_for(pump, 2)
            assert feed.capacity_exhausted and feed._stopped
            assert subscriber.get_nowait().source_event_id == candles()[0].source_event_id
            assert subscriber.empty()
            assert len(hot.replay()) == 1

        asyncio.run(scenario())


def test_archive_and_bounded_hot_cannot_spill_into_unbudgeted_disk(tmp_path):
    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    with LiveBuffer(archive, read_only=True) as reader:
        assert (
            reader._con.execute("SELECT current_setting('max_temp_directory_size')").fetchone()[0]
            == "0 bytes"
        )
    root = tmp_path / "hot"
    budget = buffer_module.HotCacheBudget(root, budget_spec(root))
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:
        assert (
            hot._con.execute("SELECT current_setting('max_temp_directory_size')").fetchone()[0]
            == "0 bytes"
        )


def test_budget_syncs_parent_directory_before_storage_dispatch(tmp_path, monkeypatch):
    import os
    import stat

    if not hasattr(os, "O_DIRECTORY"):
        pytest.skip("Directory fsync proof belongs to native POSIX release CI")
    synced = []
    original = os.fsync

    def sync(fd):
        synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        original(fd)

    monkeypatch.setattr(buffer_module.os, "fsync", sync)
    root = tmp_path / "hot"
    budget = buffer_module.HotCacheBudget(root, budget_spec(root))
    synced.clear()
    with LiveBuffer(root, retention_days=0, write_budget=budget):
        assert True in synced


@pytest.mark.parametrize("fault", ["status", "future_received", "future_market", "unknown"])
def test_merged_replay_preserves_status_time_and_unknown_barriers(tmp_path, fault):
    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    row = candles()[2]
    updates = []
    if fault == "status":
        updates.append(
            MarketUpdate(
                venue="hyperliquid",
                instrument="BTC",
                kind=UpdateKind.STATUS,
                provenance="unavailable",
                state=SourceState.DISCONNECTED,
                data_time=AT - timedelta(minutes=1),
                received_at=AT - timedelta(minutes=1),
            )
        )
    elif fault == "future_received":
        row = row.model_copy(update={"received_at": AT + timedelta(hours=1)})
    elif fault == "future_market":
        row = _candle(AT + timedelta(minutes=5), sequence=102, close=102.0, received_at=AT)
    else:
        row = row.model_copy(
            update={"continuity": ContinuityState.UNKNOWN_AFTER_DISCONNECT, "sequence_gap": True}
        )
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        feed = LiveFeed(lake=hot)
        feed.ingest([*updates, row])
        with history_client(feed, archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        if fault in {"status", "unknown"}:
            assert response.status_code == 404
        else:
            assert response.status_code == 200, response.text
            assert [bar["close"] for bar in response.json()["primary"]["bars"]] == [100, 101]


def test_existing_archive_wal_is_never_checkpointed_or_removed_by_reader(tmp_path):
    import subprocess
    import sys

    root = tmp_path / "archive"
    code = """
import os, sys
from pathlib import Path
from tests.test_market_history_hot_cache import candles
from quantmesh.live.buffer import LiveBuffer
buffer = LiveBuffer(Path(sys.argv[1]), retention_days=0)
buffer.append_many(candles()[:2])
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(root)], check=True, timeout=15)
    path = root / "live/updates.duckdb"
    wal = path.with_suffix(".duckdb.wal")
    assert wal.exists()
    original = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (path, wal)}
    try:
        with LiveBuffer(root, read_only=True) as reader:
            assert len(reader.replay()) == 2
    except ValueError as error:
        assert "archive" in str(error)
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (path, wal)} == original


def test_manifest_history_stays_first_even_if_archive_is_unavailable(tmp_path):
    from quantmesh.data.lake import Lake
    from quantmesh.data.manifest import DatasetClass, ManifestWriter
    from quantmesh.domain.market_data import Bar
    from quantmesh.domain.models import Instrument, InstrumentType, Venue
    from quantmesh.instruments.history import HistoryService
    from quantmesh.instruments.live_history import discover_history_bindings

    root = tmp_path / "manifest"
    lake = Lake(root)
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    lake.write_bars(
        "observed-btc",
        [
            Bar(
                instrument=instrument,
                timestamp=AT,
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
        generated_at=AT - timedelta(hours=1),
    )
    history = HistoryService(discover_history_bindings(root), dataset_loader=lake.dataset)
    with LiveBuffer(tmp_path / "hot", retention_days=0) as hot:
        app = create_workstation_app(
            account=PaperAccount(cash=100_000),
            live_feed=LiveFeed(lake=hot),
            history=history,
            history_archive_root=tmp_path / "missing",
            workspace_clock=lambda: AT + timedelta(seconds=1),
            host="127.0.0.1",
        )
        with TestClient(app) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200, response.text
        assert response.json()["primary"]["dataset_id"] == "observed-btc"


def test_main_binds_only_new_hot_writer_and_keeps_archive_for_same_api(tmp_path, monkeypatch):
    import json
    import sys
    import types
    from pathlib import Path

    from quantmesh.api import workstation
    from quantmesh.settings import settings

    for name in type(settings).model_fields:
        if isinstance(getattr(settings, name), Path):
            monkeypatch.setattr(settings, name, tmp_path / name)
    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    original = (archive / "live/updates.duckdb").read_bytes()
    root = tmp_path / "hot"
    spec_path = tmp_path / "capacity.json"
    spec_path.write_text(json.dumps(budget_spec(root)), encoding="utf-8")
    for name, value in {
        "lake_root": archive,
        "live_cache_root": root,
        "live_cache_budget_file": spec_path,
        "live_watchlist": "BTC",
        "prediction_watchlist": "",
        "moomoo_watchlist": "",
    }.items():
        monkeypatch.setattr(settings, name, value)
    captured = []
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        types.SimpleNamespace(run=lambda app, **kwargs: captured.append(app)),
    )
    workstation.main(["--live"])
    app = captured[0]
    hot = app.state.live.replay_buffer
    try:
        assert hot.root == root and hot.retention == timedelta(0)
        assert hot.write_budget is not None
        assert app.state.history._archive_root == archive
        assert app.state.instrument_workspace._history is app.state.history
    finally:
        hot.close()
    assert (archive / "live/updates.duckdb").read_bytes() == original


def test_budget_intent_types_cannot_reset_or_mask_reserved_attempts(tmp_path):
    import json

    root = tmp_path / "hot"
    spec = budget_spec(root)
    with LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)):
        pass
    intent = root / "budget-intent-000001.json"
    record = json.loads(intent.read_bytes())
    record["attempt"] = True  # Python dict equality treats True as1; evidence must not.
    intent.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="budget"):
        buffer_module.HotCacheBudget(root, spec)
