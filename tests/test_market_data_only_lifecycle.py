"""Actual async feed/store/HTTP lifecycle, controlled clocks/wire, not native proof."""

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live import supervisor as supervisor_module
from quantmesh.live.buffer import HotCacheBudget, LiveBuffer
from quantmesh.live.contract import UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import CandleObservation, HyperliquidVenueSupervisor
from tests.test_hyperliquid_candle_only import frame, row

MIB = 1024 * 1024


class Wire:
    def __init__(self):
        self.frames = asyncio.Queue()
        self.sent = []
        self.connected = False

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def send(self, message):
        self.sent.append(message)

    async def recv(self):
        return await self.frames.get()


class ReceiptSource:
    def __init__(self, clock):
        self.clock, self.calls = clock, []

    def observe_candles(self, symbol, interval, *, start, end):
        self.calls.append((symbol, interval, start, end))
        requested = self.clock[0] + timedelta(milliseconds=1)
        return CandleObservation(
            [row(start, 102 + len(self.calls))], requested, requested + timedelta(milliseconds=10)
        )


def eventually(predicate):
    deadline = time.monotonic() + 4
    while not predicate():
        assert time.monotonic() < deadline, "bounded engineering observer timed out"
        time.sleep(0.01)


def run_stream(tmp_path, monkeypatch, allowance):
    if not hasattr(os, "O_DIRECTORY"):
        # Windows models only this directory-fsync primitive; actual DB, intents,
        # close, async ownership and API are exercised. Not a native quota proof.
        monkeypatch.setattr(HotCacheBudget, "_require_directory_sync", lambda self: None)
    clock = [datetime.now(UTC).replace(second=0, microsecond=0)]
    anchor = clock[0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(supervisor_module, "datetime", Clock)
    spec = dict(
        schema_version=1,
        root=str(tmp_path.resolve()),
        ledger_sha256="a" * 64,
        peak_bound_sha256="b" * 64,
        leaf_remaining_bytes=64 * MIB,
        global_reserved_bytes=allowance * MIB,
        peak_operation_bytes=4 * MIB,
        close_failure_reserve_bytes=4 * MIB,
        max_batch_bytes=65536,
        expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    budget = HotCacheBudget(tmp_path, spec)
    lake = LiveBuffer.open_bounded_hot(tmp_path, budget)
    finishes = []
    original_close = budget.close_session

    def counted_finish():
        finishes.append(1)
        original_close()

    monkeypatch.setattr(budget, "close_session", counted_finish)
    feed = LiveFeed(lake=lake)
    wire, rest = Wire(), ReceiptSource(clock)
    source = HyperliquidVenueSupervisor(wire, rest=rest, candle_only=True)
    source.subscribe(["BTC"])
    feed.attach(source)
    app = create_workstation_app(
        account=PaperAccount(cash=0),
        live_feed=feed,
        market_data_only=True,
        workspace_clock=lambda: clock[0] + timedelta(seconds=1),
    )
    with TestClient(app) as client:
        for i in range(30):
            client.portal.call(wire.frames.put_nowait, frame(anchor, 500 + i))
        eventually(lambda: source._sample_current_open == anchor)
        eventually(lambda: len(lake.replay(kinds={"status"})) == 1)
        assert rest.calls == []
        for minute in (1, 2):
            clock[0] = anchor + timedelta(minutes=minute, seconds=2)
            client.portal.call(
                wire.frames.put_nowait, frame(anchor + timedelta(minutes=minute), 900)
            )
            eventually(lambda: len(lake.replay(kinds={"candle"})) == minute)
            eventually(
                lambda: (
                    source._last_candle_open.get("BTC") == anchor + timedelta(minutes=minute - 1)
                )
            )
        if allowance == 20:
            # The final COMMIT precedes provider close and its freshness transition.
            # Compare two views only after that genuine terminal state is settled.
            eventually(
                lambda: (
                    client.get("/api/health").json()["market_data_acquisition"]["state"]
                    == "capacity_stopped"
                )
            )
        response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200, response.text
        primary = response.json()["primary"]
        assert len(primary["bars"]) == 2
        assert primary["bars"][0]["timestamp"] != primary["bars"][1]["timestamp"]
        assert [b["close"] for b in primary["bars"]] == [103, 104]
        assert any("interim WebSocket" in text for text in primary["limitations"])
        workspace = client.get("/api/instruments/hyperliquid/BTC/workspace?range=1d")
        assert workspace.status_code == 200
        assert workspace.json()["history"]["bars"] == primary["bars"]
        assert workspace.json()["proposal"]["allowed"] is False
        assert len(rest.calls) == 2
        rows = lake.replay()
        assert sum(u.kind is UpdateKind.STATUS for u in rows) == 1
        if allowance == 20:
            eventually(
                lambda: (
                    client.get("/api/health").json()["market_data_acquisition"]["state"]
                    == "capacity_stopped"
                )
            )
            assert not getattr(lake, "_closed", False)
            assert (
                client.get("/api/instruments/hyperliquid/BTC/history?range=1d").json()["primary"][
                    "bars"
                ]
                == primary["bars"]
            )
        else:
            assert client.get("/api/health").json()["market_data_acquisition"] == dict(
                state="running", reason=None
            )
    assert lake._closed and not wire.connected
    assert finishes == [1]  # no duplicate durable session finish
    intents = list(tmp_path.glob("budget-intent-*.json"))
    assert len(intents) == 4  # startup + initial real state transition + two data appends
    if allowance == 64:
        assert len(list(tmp_path.glob("budget-closed-*.json"))) == 1
    else:
        assert (tmp_path / "budget-stop.json").exists()
    with LiveBuffer(tmp_path, read_only=True) as cold:
        assert len(cold.replay(kinds={"candle"})) == 2


def test_two_new_minute_observations_and_normal_close_use_four_actual_intents(
    tmp_path, monkeypatch
):
    run_stream(tmp_path, monkeypatch, 64)


def test_real_budget_exhaustion_stops_provider_keeps_http_then_closes(tmp_path, monkeypatch):
    run_stream(tmp_path, monkeypatch, 20)


@pytest.mark.parametrize("phase", ["boundary", "recovery"])
def test_shutdown_during_synchronous_rest_joins_request_before_cache_close(
    tmp_path, monkeypatch, phase
):
    from threading import Event, Thread

    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(HotCacheBudget, "_require_directory_sync", lambda self: None)
    clock = [datetime.now(UTC).replace(second=0, microsecond=0)]
    anchor = clock[0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(supervisor_module, "datetime", Clock)
    spec = dict(
        schema_version=1,
        root=str(tmp_path.resolve()),
        ledger_sha256="a" * 64,
        peak_bound_sha256="b" * 64,
        leaf_remaining_bytes=64 * MIB,
        global_reserved_bytes=64 * MIB,
        peak_operation_bytes=4 * MIB,
        close_failure_reserve_bytes=4 * MIB,
        max_batch_bytes=65536,
        expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    lake = LiveBuffer.open_bounded_hot(tmp_path, HotCacheBudget(tmp_path, spec))
    entered, release, stop_requested, stopped = Event(), Event(), Event(), Event()
    trace, errors = [], []
    original_close = lake.close

    def close():
        if not getattr(lake, "_closed", False):
            trace.append("cache_close")
        original_close()

    monkeypatch.setattr(lake, "close", close)

    class BlockingReceipt(ReceiptSource):
        def observe_candles(self, *args, **kwargs):
            trace.append("rest_enter")
            entered.set()
            assert release.wait(4), "bounded test observer did not release request"
            value = super().observe_candles(*args, **kwargs)
            trace.append("rest_return")
            return value

    class DroppableWire(Wire):
        async def recv(self):
            value = await self.frames.get()
            if value == "DROP":
                raise OSError("controlled socket loss")
            return value

    wire, rest = DroppableWire(), BlockingReceipt(clock)
    source = HyperliquidVenueSupervisor(wire, rest=rest, candle_only=True, candle_recovery_limit=1)
    source.subscribe(["BTC"])
    acknowledged = []
    on_persisted = source.on_persisted

    def record_ack(updates):
        acknowledged.extend(updates)
        on_persisted(updates)

    monkeypatch.setattr(source, "on_persisted", record_ack)
    feed = LiveFeed(lake=lake)
    feed.attach(source)
    app = create_workstation_app(
        account=PaperAccount(cash=0),
        live_feed=feed,
        market_data_only=True,
        workspace_clock=lambda: clock[0],
    )
    client = TestClient(app)
    client.__enter__()

    def stop():
        stop_requested.set()
        try:
            client.__exit__(None, None, None)
        except BaseException as exc:
            errors.append(type(exc).__name__)
        finally:
            stopped.set()

    worker = None
    try:
        client.portal.call(wire.frames.put_nowait, frame(anchor))
        eventually(lambda: source._sample_current_open == anchor)
        clock[0] = anchor + timedelta(minutes=1, seconds=2)
        client.portal.call(
            wire.frames.put_nowait,
            "DROP" if phase == "recovery" else frame(anchor + timedelta(minutes=1)),
        )
        assert entered.wait(3)
        worker = Thread(target=stop)
        worker.start()
        assert stop_requested.wait(1)
        assert not stopped.is_set() and "cache_close" not in trace
        # Synchronous HTTP runs in the owned supervisor task, not an abandoned
        # executor. Shutdown cannot pass it while the response is outstanding.
        release.set()
        worker.join(4)
        assert not worker.is_alive() and errors == []
        assert trace.index("rest_return") < trace.index("cache_close")
        assert lake._closed and not wire.connected
        # Whether cancellation raced before or after admission, only COMMIT may
        # advance the durable cursor; no callback writes after cache closure.
        with LiveBuffer(tmp_path, read_only=True) as cold:
            rows = cold.replay(kinds={"candle"})
        # Cancellation may occur after COMMIT but before admission/acknowledgement.
        # Conservative cursor omission is safe; acknowledgement without COMMIT is not.
        acked = [u for u in acknowledged if u.kind is UpdateKind.CANDLE]
        assert {u.source_event_id for u in acked} <= {u.source_event_id for u in rows}
        eligible = [u for u in acked if u.continuity.value not in {"known_gap", "unrecoverable"}]
        assert ("BTC" in source._last_candle_open) == bool(eligible)
        if eligible:
            assert source._last_candle_open["BTC"] == eligible[-1].data_time
    finally:
        release.set()
        if worker is not None:
            worker.join(4)
        else:
            client.__exit__(None, None, None)
        lake.close()
