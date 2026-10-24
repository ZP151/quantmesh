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


@pytest.fixture(autouse=True)
def modeled_session_directory_durability_on_windows(monkeypatch):
    """Protocol unit model only: native directory-fsync proof still requires POSIX CI."""
    import os

    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(
            buffer_module.HotCacheBudget,
            "_require_directory_sync",
            lambda self: None,
            raising=False,
        )


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


@pytest.mark.parametrize("hot_unreadable", [False, True])
def test_manifest_history_stays_first_even_if_archive_is_unavailable(tmp_path, hot_unreadable):
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
    if hot_unreadable:
        hot_root, spec_path = unreadable_hot(tmp_path)
        hot = LiveBuffer.from_bounded_config(hot_root, spec_path)
    else:
        hot = LiveBuffer(tmp_path / "hot", retention_days=0)
    with hot:
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


@pytest.mark.parametrize("cause", ["expired", "insufficient", "free_floor", "zero"])
def test_first_start_without_admitted_hot_keeps_archive_http_and_no_providers(
    tmp_path, monkeypatch, caplog, cause
):
    import json
    from collections import namedtuple

    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    original = (archive / "live/updates.duckdb").read_bytes()
    root = tmp_path / "hot"
    spec = budget_spec(root)
    if cause == "expired":
        spec["expires_at_utc"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    elif cause == "insufficient":
        spec["global_reserved_bytes"] = 1_000_000
    elif cause == "zero":
        spec["global_reserved_bytes"] = 0
    else:
        usage = namedtuple("Usage", "total used free")(
            100_000_000_000, 51_000_000_000, 49_000_000_000
        )
        monkeypatch.setattr(buffer_module.shutil, "disk_usage", lambda path: usage)
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    with LiveBuffer.from_bounded_config(root, path) as hot:
        assert hot.read_only
        assert not (root / "live/updates.duckdb").exists()
        feed = LiveFeed(lake=hot)

        class NeverStarts(ScriptedSupervisor):
            async def run(self):
                raise AssertionError("capacity-refused startup started a provider")

        feed.attach(NeverStarts([]))
        with history_client(feed, archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200, response.text
        assert [bar["close"] for bar in response.json()["primary"]["bars"]] == [100, 101]
        assert feed.capacity_exhausted
    assert (archive / "live/updates.duckdb").read_bytes() == original
    assert "hot capacity exhausted" in caplog.text


@pytest.mark.parametrize("failure", ["write", "sync_after_create", "both_receipts"])
def test_postcommit_stop_record_failure_still_delivers_then_stops_and_records_failure(
    tmp_path, monkeypatch, caplog, failure
):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    root = tmp_path / "hot"
    spec = budget_spec(root, operations=2)
    budget = buffer_module.HotCacheBudget(root, spec)
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:
        feed = LiveFeed(lake=hot)
        feed.attach(ScriptedSupervisor([]))
        subscriber = feed.subscribe()
        original_write = budget._write_once

        def fail_stop(path, raw):
            if path.name == "budget-stop.json":
                if failure == "sync_after_create":
                    original_write(path, raw)
                raise OSError("synthetic stop record write failure")
            if path.name == "budget-stop-failure.json" and failure == "both_receipts":
                raise OSError("synthetic terminal receipt failure")
            return original_write(path, raw)

        monkeypatch.setattr(budget, "_write_once", fail_stop)

        async def scenario():
            pump = asyncio.create_task(feed.run())
            await asyncio.sleep(0)
            await feed.publish(candles()[0])
            await asyncio.wait_for(pump, 2)
            assert len(hot.replay()) == len(feed._latest) == 1
            assert subscriber.get_nowait().source_event_id == candles()[0].source_event_id
            assert feed.capacity_exhausted and feed._stopped
            assert feed.capacity_stop_error == "budget_stop_persistence_failed"

        asyncio.run(scenario())
        assert (root / "budget-stop-failure.json").exists() is (failure != "both_receipts")
        assert "budget_stop_persistence_failed" in caplog.text
        assert f"failure_receipt_recorded={failure != 'both_receipts'}" in caplog.text
    # The failure evidence is a permanent stop, even if a future retry could write the stop file.
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as hot:
        assert hot.read_only and len(hot.replay()) == 1


def test_double_stop_write_failure_and_recovered_free_space_cannot_rearm(tmp_path, monkeypatch):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    original_archive = (archive / "live/updates.duckdb").read_bytes()
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    budget = buffer_module.HotCacheBudget(root, spec)
    with LiveBuffer(root, retention_days=0, write_budget=budget) as hot:
        feed = LiveFeed(lake=hot)
        feed.attach(ScriptedSupervisor([]))
        original_headroom, original_write = budget._headroom, budget._write_once

        def fail_terminal(path, raw):
            if path.name in {"budget-stop.json", "budget-stop-failure.json"}:
                raise OSError("terminal writes unavailable before creation")
            original_write(path, raw)

        def committed_then_free_floor(updates):
            receipts = original_append(updates)

            def free_floor(needed):
                raise buffer_module.LiveCapacityExceeded("hot capacity exhausted")

            monkeypatch.setattr(budget, "_headroom", free_floor)
            return receipts

        original_append = hot.append_many
        monkeypatch.setattr(hot, "append_many", committed_then_free_floor)
        monkeypatch.setattr(budget, "_write_once", fail_terminal)

        async def scenario():
            pump = asyncio.create_task(feed.run())
            await asyncio.sleep(0)
            await feed.publish(candles()[0])
            await asyncio.wait_for(pump, 2)
            assert feed.capacity_exhausted and len(hot.replay()) == 1

        asyncio.run(scenario())
        assert not (root / "budget-stop.json").exists()
        assert not (root / "budget-stop-failure.json").exists()
        with history_client(feed, archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200 and len(response.json()["primary"]["bars"]) == 2
        monkeypatch.setattr(budget, "_headroom", original_headroom)
        monkeypatch.setattr(budget, "_write_once", original_write)
    # Fresh instance, free/write availability restored, two operation charges remain.
    assert len(list(root.glob("budget-intent-*.json"))) == 2
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert reopened.read_only, "terminal stop was lost across restart with allowance remaining"
        assert len(reopened.replay()) == 1
        with history_client(LiveFeed(lake=reopened), archive) as client:
            assert (
                client.get("/api/instruments/hyperliquid/BTC/history?range=1d").status_code == 200
            )
    assert len(list(root.glob("budget-intent-*.json"))) == 2
    assert (archive / "live/updates.duckdb").read_bytes() == original_archive


@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_session_marker_must_be_durable_before_any_hot_database_io(tmp_path, monkeypatch, failure):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    budget = buffer_module.HotCacheBudget(root, spec)
    original_write = budget._write_once

    def fail_marker(path, raw):
        if path.name.startswith("budget-session-"):
            if failure == "fsync":
                with path.open("xb") as handle:
                    handle.write(raw)
                raise OSError("session directory fsync unavailable")
            raise OSError("session write unavailable")
        original_write(path, raw)

    monkeypatch.setattr(budget, "_write_once", fail_marker)
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert hot.read_only
        assert not (root / "live").exists()
        assert len(list(root.glob("budget-intent-*.json"))) == 1  # Failed attempt is not refunded.
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert reopened.read_only
    assert len(list(root.glob("budget-intent-*.json"))) == 1


@pytest.mark.parametrize("failure", ["write", "fsync", "publish", "database", "context_exception"])
def test_failed_clean_close_never_authorizes_restart(tmp_path, monkeypatch, failure):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    budget = buffer_module.HotCacheBudget(root, spec)
    hot = LiveBuffer(root, retention_days=0, write_budget=budget)
    hot.append(candles()[0])
    original_write = budget._write_once

    def fail_close(path, raw):
        if path.name.startswith("budget-close-ready-"):
            if failure == "fsync":
                with path.open("xb") as handle:
                    handle.write(raw)
                raise OSError("close receipt directory fsync unavailable")
            raise OSError("close receipt write unavailable")
        original_write(path, raw)

    if failure in {"write", "fsync"}:
        monkeypatch.setattr(budget, "_write_once", fail_close)
        with pytest.raises(OSError):
            hot.close()
    elif failure == "publish":

        def fail_publish(*args):
            raise OSError("atomic close publication unavailable")

        monkeypatch.setattr(buffer_module.os, "link", fail_publish)
        with pytest.raises(OSError):
            hot.close()
    elif failure == "database":
        real_connection = hot._con

        class FailedClose:
            def close(self):
                real_connection.close()
                raise OSError("database close unknown")

        hot._con = FailedClose()
        with pytest.raises(OSError):
            hot.close()
    else:
        hot.__exit__(RuntimeError, RuntimeError("abnormal context"), None)
    assert not list(root.glob("budget-closed-*.json"))
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert reopened.read_only and len(reopened.replay()) == 1
    assert len(list(root.glob("budget-intent-*.json"))) == 2


def test_normal_clean_close_allows_restart_without_refunding_intents(tmp_path):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    with LiveBuffer(
        root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)
    ) as hot:
        hot.append(candles()[0])
    assert len(list(root.glob("budget-closed-*.json"))) == 1
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert not reopened.read_only
        reopened.append(candles()[1])
    assert len(list(root.glob("budget-intent-*.json"))) == 4


@pytest.mark.parametrize("after_commit", [False, True])
def test_crashed_process_leaves_session_read_only_and_archive_http_available(
    tmp_path, after_commit
):
    import json
    import subprocess
    import sys

    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    original = (archive / "live/updates.duckdb").read_bytes()
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                [
                    "import json, os, sys",
                    "from pathlib import Path",
                    "from quantmesh.live.buffer import HotCacheBudget, LiveBuffer",
                    # Protocol model only; production refuses missing directory sync.
                    "if not hasattr(os, 'O_DIRECTORY'):",
                    "    HotCacheBudget._require_directory_sync = lambda self: None",
                    "root = Path(sys.argv[1])",
                    "budget = HotCacheBudget(root, json.loads(sys.argv[2]))",
                    "hot = LiveBuffer(root, retention_days=0, write_budget=budget)",
                    "if sys.argv[3] != 'none':",
                    "    from quantmesh.live.contract import MarketUpdate",
                    "    hot.append(MarketUpdate.model_validate_json(sys.argv[3]))",
                    "os._exit(0)",
                ]
            ),
            str(root),
            json.dumps(spec),
            candles()[2].model_dump_json() if after_commit else "none",
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    attempts = 2 if after_commit else 1
    assert len(list(root.glob("budget-intent-*.json"))) == attempts
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as hot:
        assert hot.read_only
        feed = LiveFeed(lake=hot)
        with history_client(feed, archive) as client:
            assert client.get("/health").status_code == 200
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        if hot.read_unavailable:
            assert response.status_code == 404
            assert "hot" in response.json()["detail"].lower()
        else:
            assert response.status_code == 200
            assert len(response.json()["primary"]["bars"]) == (3 if after_commit else 2)
        with history_client(feed, tmp_path / "missing-archive") as client:
            assert (
                client.get("/api/instruments/hyperliquid/BTC/history?range=1d").status_code == 404
            )
    assert (archive / "live/updates.duckdb").read_bytes() == original
    assert len(list(root.glob("budget-intent-*.json"))) == attempts


@pytest.mark.parametrize("damage", ["partial", "foreign", "missing", "extra", "closed", "ready"])
def test_unknown_session_evidence_never_grants_restart(tmp_path, damage):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    with LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)):
        pass
    marker = root / "budget-session-000001.json"
    if damage == "partial":
        marker.write_bytes(b"{")
    elif damage == "foreign":
        import json

        record = json.loads(marker.read_bytes())
        record["spec_sha256"] = "c" * 64
        marker.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    elif damage == "missing":
        marker.rename(root / "retained-damaged-session.json")
    elif damage == "closed":
        (root / "budget-closed-000001.json").write_bytes(b"{}")
    elif damage == "ready":
        (root / "budget-close-ready-000001.json").rename(root / "retained-close-ready.json")
    else:
        (root / "budget-session-garbage.json").write_bytes(b"{}")
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert reopened.read_only
    assert len(list(root.glob("budget-intent-*.json"))) == 1


def test_normal_shutdown_joins_accepted_commit_before_clean_close(tmp_path):
    from tests.test_live_feed_owned_persistence import CommitGate, ScriptedSupervisor

    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    hot = LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec))
    gate = CommitGate(hot._con, [])
    hot._con = gate
    feed = LiveFeed(lake=hot)
    feed.attach(ScriptedSupervisor([]))

    async def scenario():
        pump = asyncio.create_task(feed.run())
        await asyncio.sleep(0)
        publishing = asyncio.create_task(feed.publish(candles()[0]))
        assert await asyncio.to_thread(gate.entered.wait, 1)
        pump.cancel()
        await asyncio.sleep(0)
        assert not pump.done()
        assert not list(root.glob("budget-closed-*.json"))
        gate.release.set()
        results = await asyncio.gather(publishing, pump, return_exceptions=True)
        assert all(
            result is None or isinstance(result, asyncio.CancelledError) for result in results
        )
        assert hot.write_budget._owners == 0
        assert len(list(root.glob("budget-closed-*.json"))) == 1
        with LiveBuffer(root, read_only=True) as persisted:
            assert len(persisted.replay()) == 1

    try:
        asyncio.run(scenario())
    finally:
        gate.release.set()
        hot.close()
    assert len(list(root.glob("budget-closed-*.json"))) == 1
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert not reopened.read_only and len(reopened.replay()) == 1


def test_close_with_live_owner_cannot_issue_clean_close(tmp_path):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    hot = LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec))
    feed = LiveFeed(lake=hot)
    feed.attach(ScriptedSupervisor([]))

    async def scenario():
        pump = asyncio.create_task(feed.run())
        await asyncio.sleep(0)
        hot.close()
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)

    asyncio.run(scenario())
    assert not list(root.glob("budget-closed-*.json"))
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert reopened.read_only


@pytest.mark.parametrize("gate", ["expiry", "free", "cumulative"])
def test_clean_close_does_not_bypass_original_restart_admission(tmp_path, monkeypatch, gate):
    from collections import namedtuple

    root = tmp_path / "hot"
    spec = budget_spec(root, operations=1 if gate == "cumulative" else 4)
    with LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)):
        pass
    budget = buffer_module.HotCacheBudget(root, spec)
    if gate == "expiry":
        budget.expires = datetime.now(UTC) - timedelta(seconds=1)
    elif gate == "free":
        usage = namedtuple("Usage", "total used free")(
            100_000_000_000, 51_000_000_000, 49_000_000_000
        )
        monkeypatch.setattr(buffer_module.shutil, "disk_usage", lambda path: usage)
    with LiveBuffer.open_bounded_hot(root, budget) as reopened:
        assert reopened.read_only
    assert len(list(root.glob("budget-intent-*.json"))) == 1


def test_header_without_intents_cannot_adopt_unaccounted_database(tmp_path):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    buffer_module.HotCacheBudget(root, spec)  # Header exists, but no storage admission took place.
    seed(root, candles()[:1])
    with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as reopened:
        assert reopened.read_only
        assert len(reopened.replay()) == 1
    assert not list(root.glob("budget-intent-*.json"))


def test_native_session_directory_fsync_failure_precedes_duckdb_io(tmp_path, monkeypatch):
    import os
    import stat

    if not hasattr(os, "O_DIRECTORY"):
        pytest.skip("Native session directory-fsync proof requires POSIX CI")
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    budget = buffer_module.HotCacheBudget(root, spec)
    original_write, original_sync = budget._write_once, os.fsync
    marker_active = False

    def write(path, raw):
        nonlocal marker_active
        marker_active = path.name.startswith("budget-session-")
        try:
            original_write(path, raw)
        finally:
            marker_active = False

    def sync(descriptor):
        if marker_active and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("native directory fsync unavailable")
        return original_sync(descriptor)

    monkeypatch.setattr(budget, "_write_once", write)
    monkeypatch.setattr(buffer_module.os, "fsync", sync)
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert hot.read_only
        assert not (root / "live").exists()
    assert len(list(root.glob("budget-intent-*.json"))) == 1


def test_actual_app_normal_shutdown_closes_session_and_allows_fresh_restart(tmp_path):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    hot = LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec))
    feed = LiveFeed(lake=hot)
    feed.attach(ScriptedSupervisor([]))
    app = create_workstation_app(account=PaperAccount(cash=100_000), live_feed=feed)
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert not list(root.glob("budget-closed-*.json"))
        # Production lifespan must close; no test/manual close before this assertion.
        assert len(list(root.glob("budget-closed-*.json"))) == 1
        with LiveBuffer.open_bounded_hot(root, buffer_module.HotCacheBudget(root, spec)) as fresh:
            assert not fresh.read_only
        assert len(list(root.glob("budget-intent-*.json"))) == 2
    finally:
        hot.close()


def test_recursive_creation_syncs_existing_ancestor_before_database_open(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    root = tmp_path / "new-parent" / "hot"
    synced, descriptors = [], {}
    original_open, original_close, original_sync = os.open, os.close, os.fsync
    directory_flag = getattr(os, "O_DIRECTORY", 1 << 24)
    monkeypatch.setattr(buffer_module.os, "O_DIRECTORY", directory_flag, raising=False)

    def open_directory(path, flags, *args, **kwargs):
        if flags & directory_flag:
            descriptor = 100_000 + len(descriptors)
            descriptors[descriptor] = Path(path)
            return descriptor
        return original_open(path, flags, *args, **kwargs)

    def sync(descriptor):
        if descriptor in descriptors:
            synced.append(descriptors[descriptor])
        else:
            original_sync(descriptor)

    def close(descriptor):
        if descriptor not in descriptors:
            original_close(descriptor)

    # Only directory syscalls are modeled; files, intents and actual DuckDB remain real.
    monkeypatch.setattr(buffer_module.os, "open", open_directory)
    monkeypatch.setattr(buffer_module.os, "fsync", sync)
    monkeypatch.setattr(buffer_module.os, "close", close)
    budget = buffer_module.HotCacheBudget(root, budget_spec(root, operations=4))
    real_connect = buffer_module.duckdb.connect

    def connect(*args, **kwargs):
        assert tmp_path in synced, "new-parent entry was not synced in its existing parent"
        assert synced.index(root) < synced.index(root.parent) < synced.index(tmp_path)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(buffer_module.duckdb, "connect", connect)
    with LiveBuffer(root, retention_days=0, write_budget=budget):
        pass


def unreadable_hot(tmp_path, *, normal_close=False):
    import json

    root = tmp_path / "unknown-hot"
    spec = budget_spec(root, operations=4)
    hot = LiveBuffer(root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec))
    hot.append(candles()[2])
    if normal_close:
        hot.close()
    else:
        hot._con.close()  # Controlled input, not claimed as a real crash reproduction.
    hot.path.rename(hot.path.with_suffix(".retained-duckdb"))
    hot.path.write_bytes(b"controlled invalid formerly admitted hot database")
    path = tmp_path / "unreadable-budget.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return root, path


@pytest.mark.parametrize("damage", ["unreadable", "missing"])
@pytest.mark.parametrize("normal_close", [False, True])
def test_unreadable_admitted_hot_keeps_http_but_never_silent_archive_only_success(
    tmp_path, damage, normal_close
):
    from tests.test_live_feed_owned_persistence import ScriptedSupervisor

    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    original = (archive / "live/updates.duckdb").read_bytes()
    root, path = unreadable_hot(tmp_path, normal_close=normal_close)
    if damage == "missing":
        (root / "live/updates.duckdb").rename(root / "retained-invalid-db")
    with LiveBuffer.from_bounded_config(root, path) as hot:
        feed = LiveFeed(lake=hot)

        class NeverStarts(ScriptedSupervisor):
            async def run(self):
                raise AssertionError("unavailable hot started acquisition")

        feed.attach(NeverStarts([]))
        with history_client(feed, archive) as client:
            assert client.get("/health").status_code == 200
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
            assert response.status_code == 404, "unknown hot was silently replaced by empty success"
            assert "hot" in response.json()["detail"].lower()
        assert feed.capacity_exhausted and not feed._latest
        assert feed.statuses()["venues"][0]["sources"][0]["state"] == "unavailable"
        with pytest.raises(ValueError, match="hot"):
            hot.replay()
    assert (archive / "live/updates.duckdb").read_bytes() == original


def test_partial_crash_accounting_refuses_acquisition_but_retains_readable_history(tmp_path):
    import json

    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    with LiveBuffer(
        root, retention_days=0, write_budget=buffer_module.HotCacheBudget(root, spec)
    ) as hot:
        hot.append(candles()[2])
    intent = root / "budget-intent-000002.json"
    intent.rename(root / "retained-original-intent.json")
    intent.write_bytes(b"{")  # Controlled partial receipt, not a claimed actual crash outcome.
    spec_path = tmp_path / "budget.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    with LiveBuffer.from_bounded_config(root, spec_path) as stopped:
        assert stopped.read_only
        with history_client(LiveFeed(lake=stopped), archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200
        assert [bar["close"] for bar in response.json()["primary"]["bars"]] == [100, 101, 102]
    assert len(list(root.glob("budget-intent-*.json"))) == 2
    assert intent.read_bytes() == b"{"
