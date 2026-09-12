"""Locally timed Hyperliquid metrics retain distinct observations and exact replay."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from quantmesh.live.buffer import LiveBuffer, LiveIdentityConflictError
from quantmesh.live.contract import MarketUpdate, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, ScriptedHyperliquidTransport

OBSERVED = datetime(2026, 9, 12, 15, 45, 47, 265680, tzinfo=UTC)
CHANNELS = ("activeAssetCtx", "allMids")


def _frame(channel, changed=False):
    if channel == "allMids":
        return {"channel": channel, "data": {"mids": {"BTC": "77372" if changed else "77371"}}}
    return {
        "channel": channel,
        "data": {
            "coin": "BTC",
            "ctx": {
                "funding": "-0.0000046821",
                "markPx": "77372" if changed else "77371",
                "oraclePx": "77408.3",
                "openInterest": "36310.0256",
            },
        },
    }


def _supervisor():
    supervisor = HyperliquidVenueSupervisor(ScriptedHyperliquidTransport([]))
    supervisor.subscribe(["BTC"])
    return supervisor


def _observed(supervisor, channel, observed=OBSERVED, changed=False):
    [row] = supervisor.dispatch(_frame(channel, changed), observed)
    return row.model_copy(update={"received_at": observed + timedelta(microseconds=39)})


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("batch", [True, False], ids=["same-batch", "persisted-first"])
@pytest.mark.parametrize(
    "microseconds,changed,count",
    [(1, False, 2), (0, True, 2), (1, True, 2), (1000, False, 2), (0, False, 1)],
    ids=[
        "same-payload-distinct-us",
        "changed-payload-same-time",
        "both-change",
        "next-ms",
        "repeat",
    ],
)
def test_metric_observations_survive_real_feed_buffer(
    tmp_path, channel, batch, microseconds, changed, count
):
    supervisor = _supervisor()
    first = _observed(supervisor, channel)
    second = _observed(
        supervisor, channel, OBSERVED + timedelta(microseconds=microseconds), changed
    )
    with LiveBuffer(tmp_path) as buffer:
        feed = LiveFeed(lake=buffer)
        if batch:
            admitted = feed.ingest([first, second])
        else:
            admitted = feed.ingest([first]) + feed.ingest([second])
        assert len(admitted) == count
        assert buffer.quarantined() == []
        rows = buffer.replay(kinds=["metrics"])
        assert [row.model_dump() for row in rows] == [row.model_dump() for row in admitted]
        assert len({row.source_event_id for row in rows}) == count


@pytest.mark.parametrize("channel", CHANNELS)
def test_legacy_reopen_and_exact_receipt_replay_preserve_evidence_and_conflicts(tmp_path, channel):
    supervisor = _supervisor()
    current = _observed(supervisor, channel)
    legacy_id = hashlib.sha256(
        json.dumps(
            [int(OBSERVED.timestamp() * 1000), "BTC", channel], separators=(",", ":")
        ).encode()
    ).hexdigest()
    legacy = current.model_copy(update={"source_event_id": legacy_id})
    with LiveBuffer(tmp_path) as buffer:
        buffer.append(legacy)
        legacy_bytes = buffer.replay(kinds=["metrics"])[0].model_dump_json()
    with LiveBuffer(tmp_path) as buffer:
        feed = LiveFeed(lake=buffer)
        resumed_supervisor = _supervisor()
        feed.attach(resumed_supervisor)
        resumed_supervisor.on_disconnect(OBSERVED)
        resumed = _observed(resumed_supervisor, channel, OBSERVED + timedelta(seconds=1))
        assert resumed.continuity_evidence.last_durable_source_event_id == legacy_id
        assert (
            resumed.continuity_evidence.first_recovered_source_event_id == resumed.source_event_id
        )
        assert current.source_event_id != legacy_id
        assert len(feed.ingest([current])) == 1
        repeat = current.model_copy(
            update={"received_at": current.received_at + timedelta(seconds=2)}
        )
        assert feed.ingest([repeat]) == []
        assert buffer.quarantined() == []
        payload_key = "mid" if channel == "allMids" else "mark_price"
        conflict = MarketUpdate.model_validate(
            {
                **current.model_dump(),
                "payload": {**current.payload, payload_key: 1.0},
                "content_digest": None,
            }
        )
        with pytest.raises(LiveIdentityConflictError):
            feed.ingest([conflict])
        frozen = [row.model_dump_json() for row in buffer.replay(kinds=["metrics"])]
        assert frozen[0] == legacy_bytes
        assert [row.model_dump() for row in buffer.replay(kinds=["metrics"])] == [
            legacy.model_dump(),
            current.model_dump(),
        ]
        assert len(buffer.quarantined()) == 1
    with LiveBuffer(tmp_path) as buffer:
        assert [row.model_dump_json() for row in buffer.replay(kinds=["metrics"])] == frozen
        assert len(buffer.quarantined()) == 1


@pytest.mark.parametrize("channel", CHANNELS)
def test_identity_uses_normalized_payload_and_utc_instant(channel):
    supervisor = _supervisor()
    first = _observed(supervisor, channel)
    frame = _frame(channel)
    payload = frame["data"]["mids" if channel == "allMids" else "ctx"]
    for key, value in list(payload.items()):
        payload[key] = float(value)
    [equivalent] = supervisor.dispatch(frame, OBSERVED.astimezone(timezone(timedelta(hours=8))))
    assert first.source_event_id == equivalent.source_event_id
    assert first.content_digest == equivalent.content_digest


class _QueueTransport:
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


class _RecordedClockSupervisor(HyperliquidVenueSupervisor):
    def dispatch(self, packet, now):
        frame, observed = packet
        return [
            row.model_copy(update={"received_at": observed + timedelta(microseconds=39)})
            for row in super().dispatch(frame, observed)
        ]


async def _wait_until(predicate, task):
    async with asyncio.timeout(3):
        while not predicate():
            assert not task.done(), repr(task.exception())
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_metric_burst_keeps_real_pump_subscribers_and_three_symbol_quotes_running(tmp_path):
    with LiveBuffer(tmp_path) as buffer:
        transport = _QueueTransport()
        supervisor = _RecordedClockSupervisor(transport)
        supervisor.subscribe(["BTC", "ETH", "SOL"])
        feed = LiveFeed(lake=buffer)
        feed.attach(supervisor)
        subscriber = feed.subscribe()
        task = asyncio.create_task(feed.run())
        try:
            for channel in CHANNELS:
                for microseconds, changed in [(0, False), (1, False), (1, True), (1, True)]:
                    await transport.frames.put(
                        (_frame(channel, changed), OBSERVED + timedelta(microseconds=microseconds))
                    )
            await _wait_until(lambda: len(buffer.replay(kinds=["metrics"])) == 6, task)
            quote_time = OBSERVED + timedelta(seconds=1)
            for coin in ("BTC", "ETH", "SOL"):
                await transport.frames.put(
                    (
                        {
                            "channel": "bbo",
                            "data": {
                                "coin": coin,
                                "time": int(quote_time.timestamp() * 1000),
                                "bbo": [
                                    {"px": "100", "sz": "1", "n": 1},
                                    {"px": "101", "sz": "1", "n": 1},
                                ],
                            },
                        },
                        quote_time,
                    )
                )
            await _wait_until(lambda: len(buffer.replay(kinds=["quote"])) == 3, task)
            assert not task.done()
            delivered = [subscriber.get_nowait() for _ in range(subscriber.qsize())]
            metrics = buffer.replay(kinds=["metrics"])
            assert [row.model_dump() for row in delivered if row.kind is UpdateKind.METRICS] == [
                row.model_dump() for row in metrics
            ]
            assert {row.instrument for row in delivered if row.kind is UpdateKind.QUOTE} == {
                "BTC",
                "ETH",
                "SOL",
            }
            assert buffer.quarantined() == []
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            feed.unsubscribe(subscriber)
