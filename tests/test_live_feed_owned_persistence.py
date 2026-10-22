"""Owned I/O event-order contract; old latency experiments are frozen in output."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread, get_ident

import pytest

from quantmesh.domain.models import Venue
from quantmesh.live import feed as feed_module
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor

T0 = datetime(2026, 10, 21, tzinfo=UTC)


def quote(number):
    return MarketUpdate(
        venue=Venue.HYPERLIQUID,
        instrument="BTC",
        kind=UpdateKind.QUOTE,
        provenance=Provenance.SYNTHETIC,
        data_time=T0 + timedelta(milliseconds=number),
        received_at=T0 + timedelta(milliseconds=number),
        sequence=number,
        source_event_id=f"owned-quote-{number}",
        payload={"bid": 100 + number, "ask": 101 + number},
    )


class QueueTransport:
    def __init__(self):
        self.frames = asyncio.Queue()

    def connect(self):
        pass

    def close(self):
        pass

    def send(self, message):
        pass

    async def recv(self):
        return await self.frames.get()


class CommitGate:
    """Real commit with a bounded observer-controlled gate, never fake success."""

    def __init__(self, connection, trace):
        self.connection = connection
        self.trace = trace
        self.entered, self.release = Event(), Event()

    def execute(self, query, parameters=None):
        if query == "COMMIT":
            self.trace.append("commit_enter")
            self.entered.set()
            assert self.release.wait(1), "owned observer failed to release finite gate"
            self.trace.append("io_release")
        result = (
            self.connection.execute(query)
            if parameters is None
            else self.connection.execute(query, parameters)
        )
        if query == "COMMIT":
            self.trace.append("commit_return")
        return result

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_pending_append_keeps_cache_read_and_stop_on_owner_loop(tmp_path):
    async def scenario():
        trace, observed = [], []
        with LiveBuffer(tmp_path) as lake:
            lake.append(quote(0))
            transport = QueueTransport()
            supervisor = HyperliquidVenueSupervisor(transport)
            supervisor.subscribe(["BTC"])
            feed = LiveFeed(lake=lake)
            feed.attach(supervisor)
            subscriber = feed.subscribe()
            gate = CommitGate(lake._con, trace)
            lake._con = gate
            # Exact synthetic wire inputs: no warmup, delay pair or latency gate.
            for number in range(1, 33):
                transport.frames.put_nowait(
                    {
                        "channel": "bbo",
                        "data": {
                            "coin": "BTC",
                            "time": int(T0.timestamp() * 1000) + number,
                            "bbo": [
                                {"px": str(100 + number), "sz": "1", "n": 1},
                                {"px": str(101 + number), "sz": "1", "n": 1},
                            ],
                        },
                    }
                )
            loop = asyncio.get_running_loop()
            handled = Event()

            def observe_stop():
                trace.append("stop_observed")
                snapshot = feed.snapshot_exact(Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0)
                observed.append((gate.release.is_set(), snapshot.source_event_id))
                pump.cancel()
                handled.set()

            def observer():
                try:
                    if gate.entered.wait(1):
                        trace.append("stop_intent")
                        loop.call_soon_threadsafe(observe_stop)
                        handled.wait(0.160)  # Finite cleanup; not a performance threshold.
                finally:
                    gate.release.set()

            thread = Thread(target=observer, name="owned-persistence-observer")
            thread.start()
            pump = asyncio.create_task(feed.run())
            try:
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.shield(pump), 3)
            finally:
                gate.release.set()
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(pump, 3)
                thread.join(1)
            assert not thread.is_alive()
            trace.append("stopped")
            persisted = lake.replay(kinds=["quote"])
            print({"trace": trace, "cache_at_stop": observed, "persisted": len(persisted)})
            assert len(persisted) == 33  # A late successful commit is durable truth.
            assert observed == [(False, "owned-quote-0")], "loop/cache waited for real I/O"
            assert trace.index("stop_observed") < trace.index("io_release")
            assert trace.index("commit_return") < trace.index("stopped")
            assert subscriber.empty(), "stopped generation published a late commit"
            assert (
                feed.snapshot_exact(
                    Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0
                ).source_event_id
                == "owned-quote-0"
            )

    asyncio.run(scenario())


class ScriptedSupervisor(HyperliquidVenueSupervisor):
    """Real outbox/cursor operations; the scripted input needs no network pump."""

    def __init__(self, trace):
        super().__init__(QueueTransport())
        self.subscribe(["BTC"])
        self.trace = trace

    async def run(self):
        await asyncio.Future()

    def on_persisted(self, updates):
        super().on_persisted(updates)
        self.trace.extend(("cursor", row.source_event_id) for row in updates)


class OrderedConnection(CommitGate):
    def __init__(self, connection, trace):
        super().__init__(connection, [])
        self.events = trace
        self.identities = []

    def execute(self, query, parameters=None):
        if query == "BEGIN TRANSACTION":
            self.identities = []
        if query.startswith("INSERT INTO market_updates"):
            self.identities.append(parameters[10])
        result = super().execute(query, parameters)
        if query == "COMMIT":
            self.events.extend(("commit", identity) for identity in self.identities)
        return result


async def start_feed(feed):
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0)
    return task


async def stop_feed(task):
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)


def test_commit_cache_cursor_delivery_and_threadsafe_producers_share_order(tmp_path):
    async def scenario():
        trace, errors, active = [], [], []
        owner_thread = get_ident()
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            supervisor = ScriptedSupervisor(trace)
            feed.attach(supervisor)
            supervisor._push_many([quote(1)])
            trace.clear()
            subscriber = feed.subscribe()
            gate = OrderedConnection(lake._con, trace)
            lake._con = gate
            real_append = lake.append_many
            guard = Lock()
            running = 0

            def append(rows):
                nonlocal running
                with guard:
                    running += 1
                    active.append((running, get_ident()))
                try:
                    return real_append(rows)
                finally:
                    with guard:
                        running -= 1

            lake.append_many = append
            real_cache, real_deliver = feed._ingest_cached, feed._deliver

            def cache(row):
                assert get_ident() == owner_thread
                trace.append(("cache", row.source_event_id))
                real_cache(row)

            async def deliver(row):
                assert get_ident() == owner_thread
                trace.append(("delivery", row.source_event_id))
                await real_deliver(row)

            feed._ingest_cached, feed._deliver = cache, deliver
            pump = await start_feed(feed)
            thread_done = Event()

            def producer():
                try:
                    assert feed.publish_threadsafe(quote(2)) is None
                except BaseException as error:
                    errors.append(error)
                finally:
                    thread_done.set()

            thread = Thread(target=producer, name="owned-sync-producer")
            try:
                assert await asyncio.to_thread(gate.entered.wait, 1)
                assert subscriber.empty()
                thread.start()
                third = asyncio.create_task(feed.publish(quote(3)))
                await asyncio.sleep(0)
                assert not thread_done.is_set()
                gate.release.set()
                await asyncio.wait_for(third, 3)
                assert await asyncio.to_thread(thread_done.wait, 1)
                thread.join(1)
                assert errors == []
                expected = [row.source_event_id for row in lake.replay()]
                assert expected[0] == "owned-quote-1"
                assert set(expected) == {"owned-quote-1", "owned-quote-2", "owned-quote-3"}
                for phase in ("commit", "cache", "delivery"):
                    assert [identity for kind, identity in trace if kind == phase] == expected
                assert (
                    trace.index(("cache", "owned-quote-1"))
                    < trace.index(("cursor", "owned-quote-1"))
                    < trace.index(("delivery", "owned-quote-1"))
                )
                assert [subscriber.get_nowait().source_event_id for _ in range(3)] == expected
                await feed.publish(
                    quote(2)
                )  # Real duplicate receipt cannot regress cache/delivery.
                assert subscriber.empty()
                assert (
                    feed.snapshot_exact(
                        Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0
                    ).source_event_id
                    == expected[-1]
                )
                assert max(count for count, _ in active) == 1
                assert all(thread_id != owner_thread for _, thread_id in active)
            finally:
                gate.release.set()
                await stop_feed(pump)
                if thread.ident is not None:
                    thread.join(1)
            assert not thread.is_alive()
            with pytest.raises(RuntimeError, match="stopped"):
                feed.publish_threadsafe(quote(4))
            assert len(lake.replay()) == 3

    asyncio.run(scenario())


class FailWriteConnection:
    def __init__(self, connection, *, second_book=False):
        self.connection = connection
        self.second_book = second_book
        self.book_inserts = 0
        self.error = RuntimeError("owned real transaction failure")

    def execute(self, query, parameters=None):
        if query.startswith("INSERT INTO market_updates") and parameters[3] == "l2_snapshot":
            self.book_inserts += 1
            if self.second_book and self.book_inserts == 2:
                raise self.error
        if not self.second_book and query == "COMMIT":
            raise self.error
        return (
            self.connection.execute(query)
            if parameters is None
            else self.connection.execute(query, parameters)
        )

    def __getattr__(self, name):
        return getattr(self.connection, name)


def book(side):
    return MarketUpdate(
        venue=Venue.HYPERLIQUID,
        instrument="BTC",
        kind=UpdateKind.L2_SNAPSHOT,
        provenance=Provenance.SYNTHETIC,
        data_time=T0,
        received_at=T0,
        source_event_id=f"owned-book:{side}",
        snapshot_epoch="owned-book",
        payload={"side": side, "levels": [[100 if side == "bid" else 101, 1]]},
    )


@pytest.mark.parametrize("entry", ["drain", "tick", "async"])
def test_failed_atomic_book_batch_never_publishes_or_advances_cursor(tmp_path, monkeypatch, entry):
    async def scenario():
        trace = []
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            supervisor = ScriptedSupervisor(trace)
            feed.attach(supervisor)
            subscriber = feed.subscribe()
            failure = FailWriteConnection(lake._con, second_book=True)
            lake._con = failure
            rows = [book("bid"), book("ask")]
            if entry == "drain":
                supervisor._push_many(rows)
            if entry == "tick":
                monkeypatch.setattr(feed_module, "_TICK_SECONDS", 0.001)
                supervisor.on_tick = lambda now: supervisor._push_many(rows)
            pump = await start_feed(feed)
            try:
                if entry == "async":
                    with pytest.raises(RuntimeError) as error:
                        await feed.publish_many(rows)
                else:
                    with pytest.raises(RuntimeError) as error:
                        await asyncio.wait_for(pump, 3)
                assert error.value is failure.error
            finally:
                if not pump.done():
                    await stop_feed(pump)
            assert failure.book_inserts == 2
            assert lake.replay() == [] and lake.statuses() == []
            assert subscriber.empty() and trace == []
            assert supervisor._last_event_id == {}
            assert (
                feed.snapshot_exact(Venue.HYPERLIQUID, "BTC", UpdateKind.L2_SNAPSHOT, as_of=T0)
                is None
            )

    asyncio.run(scenario())


def test_threadsafe_failure_returns_actual_error_and_offline_semantics_remain(tmp_path):
    async def scenario():
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            assert feed.publish_threadsafe(quote(0)) is None  # Before pump: still synchronous.
            assert (
                feed.snapshot_exact(
                    Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0
                ).source_event_id
                == "owned-quote-0"
            )
            subscriber = feed.subscribe()
            failure = FailWriteConnection(lake._con)
            lake._con = failure
            pump = await start_feed(feed)
            try:
                with pytest.raises(RuntimeError) as error:
                    await asyncio.to_thread(feed.publish_threadsafe, quote(1))
                assert error.value is failure.error
                assert [row.source_event_id for row in lake.replay()] == ["owned-quote-0"]
                assert subscriber.empty()
                assert (
                    feed.snapshot_exact(
                        Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0
                    ).source_event_id
                    == "owned-quote-0"
                )
            finally:
                await stop_feed(pump)

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["append", "prune"])
@pytest.mark.parametrize("fails", [False, True])
def test_stop_joins_entered_io_and_cancels_waiting_producer(
    tmp_path, monkeypatch, operation, fails
):
    async def scenario():
        trace, inspected, producer_errors = [], [], []
        entered, release, checked, producer_done = Event(), Event(), Event(), Event()
        error = RuntimeError("late owned I/O failure")
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            supervisor = ScriptedSupervisor([])
            feed.attach(supervisor)
            subscriber = feed.subscribe()
            real_append, real_prune = lake.append_many, lake.prune

            def entered_io(*args):
                trace.append("entered")
                entered.set()
                assert release.wait(1), "finite observer did not release owned work"
                if fails:
                    trace.append("io_failure")
                    raise error
                result = real_append(*args) if operation == "append" else real_prune()
                trace.append("io_return")
                return result

            if operation == "append":
                lake.append_many = entered_io
                supervisor._push_many([quote(1)])
            else:
                monkeypatch.setattr(feed_module, "_TICK_SECONDS", 0.001)
                lake.prune = entered_io
            loop = asyncio.get_running_loop()

            def producer():
                try:
                    feed.publish_threadsafe(quote(2))
                except BaseException as failure:
                    producer_errors.append(failure)
                finally:
                    producer_done.set()

            producer_thread = Thread(target=producer, name="owned-waiting-producer")

            def inspect_shutdown():
                inspected.append((pump.done(), release.is_set()))
                checked.set()

            def request_stop():
                trace.append("stop_observed")
                pump.cancel()
                loop.call_later(0.010, inspect_shutdown)

            def observer():
                try:
                    if entered.wait(1):
                        producer_thread.start()
                        loop.call_soon_threadsafe(request_stop)
                        checked.wait(0.160)
                finally:
                    release.set()

            observer_thread = Thread(target=observer, name="owned-stop-observer")
            observer_thread.start()
            pump = asyncio.create_task(feed.run())
            try:
                if fails:
                    with pytest.raises(RuntimeError) as failure:
                        await asyncio.wait_for(asyncio.shield(pump), 3)
                    assert failure.value is error
                else:
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.wait_for(asyncio.shield(pump), 3)
                trace.append("stopped")
            finally:
                release.set()
                if not pump.done():
                    await stop_feed(pump)
                observer_thread.join(1)
                if producer_thread.ident is not None:
                    assert await asyncio.to_thread(producer_done.wait, 1)
                    producer_thread.join(1)
            assert not observer_thread.is_alive() and not producer_thread.is_alive()
            assert inspected == [(False, False)], "stop completed before real I/O joined"
            terminal = "io_failure" if fails else "io_return"
            assert trace.index("stop_observed") < trace.index(terminal) < trace.index("stopped")
            assert producer_errors, "waiting producer must not silently succeed after stop"
            assert subscriber.empty() and feed._requests == set() and feed._io_task is None
            assert feed.snapshot_exact(Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0) is None
            assert [row.source_event_id for row in lake.replay()] == (
                ["owned-quote-1"] if operation == "append" and not fails else []
            )
            with pytest.raises(RuntimeError, match="stopped"):
                await feed.publish(quote(3))

    asyncio.run(scenario())


def test_queued_publish_freezes_input_before_waiting_for_sequence_gate(tmp_path):
    async def scenario():
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            gate = CommitGate(lake._con, [])
            lake._con = gate
            pump = await start_feed(feed)
            first = asyncio.create_task(feed.publish(quote(1)))
            try:
                assert await asyncio.to_thread(gate.entered.wait, 1)
                batch = [quote(2)]
                second = asyncio.create_task(feed.publish_many(batch))
                await asyncio.sleep(0)
                batch.clear()
                gate.release.set()
                await asyncio.wait_for(asyncio.gather(first, second), 3)
                assert [row.source_event_id for row in lake.replay()] == [
                    "owned-quote-1",
                    "owned-quote-2",
                ], "queued accepted input was still borrowed from the caller"
            finally:
                gate.release.set()
                await stop_feed(pump)

    asyncio.run(scenario())


def test_cancelled_entered_publisher_applies_commit_while_pump_remains_active(tmp_path):
    async def scenario():
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            subscriber = feed.subscribe()
            gate = CommitGate(lake._con, [])
            lake._con = gate
            pump = await start_feed(feed)
            publisher = asyncio.create_task(feed.publish(quote(1)))
            try:
                assert await asyncio.to_thread(gate.entered.wait, 1)
                publisher.cancel()
                await asyncio.sleep(0)
                gate.release.set()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(publisher, 3)
                assert publisher.cancelled()
                assert not pump.done() and feed._accepting
                assert [row.source_event_id for row in lake.replay()] == ["owned-quote-1"]
                snapshot = feed.snapshot_exact(Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0)
                assert snapshot is not None, "successful accepted commit was never applied"
                assert snapshot.source_event_id == "owned-quote-1"
                assert subscriber.get_nowait().source_event_id == "owned-quote-1"
                await feed.publish(quote(1))
                assert subscriber.empty() and len(lake.replay()) == 1
                await feed.publish(quote(2))
                assert subscriber.get_nowait().source_event_id == "owned-quote-2"
                assert feed._requests == set() and feed._io_task is None
            finally:
                gate.release.set()
                await stop_feed(pump)

    asyncio.run(scenario())


def test_cancelled_queued_publisher_never_starts_storage(tmp_path):
    async def scenario():
        with LiveBuffer(tmp_path) as lake:
            feed = LiveFeed(lake=lake)
            subscriber = feed.subscribe()
            gate = CommitGate(lake._con, [])
            lake._con = gate
            pump = await start_feed(feed)
            first = asyncio.create_task(feed.publish(quote(1)))
            try:
                assert await asyncio.to_thread(gate.entered.wait, 1)
                second = asyncio.create_task(feed.publish(quote(2)))
                await asyncio.sleep(0)
                second.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(second, 1)
                assert not first.done() and not pump.done()
                gate.release.set()
                await asyncio.wait_for(first, 3)
                assert [row.source_event_id for row in lake.replay()] == ["owned-quote-1"]
                assert subscriber.get_nowait().source_event_id == "owned-quote-1"
                assert subscriber.empty() and feed._requests == set() and feed._io_task is None
            finally:
                gate.release.set()
                await stop_feed(pump)

    asyncio.run(scenario())
