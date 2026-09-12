"""Closed-candle observations retain revisions without weakening replay identity."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import HistoryRange
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.live.buffer import LiveBuffer, LiveIdentityConflictError
from quantmesh.live.contract import ContinuityState, MarketUpdate, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, ScriptedHyperliquidTransport

OPEN = datetime(2026, 9, 12, 14, 22, tzinfo=UTC)
FIRST_RECEIPT = OPEN + timedelta(minutes=1, microseconds=33_701)
REVISION_RECEIPT = OPEN + timedelta(minutes=1, microseconds=538_628)


def _candle(volume="26.45105", opened=OPEN):
    opened_ms = int(opened.timestamp() * 1000)
    return {
        "channel": "candle",
        "data": {
            "t": opened_ms,
            "T": opened_ms + 59_999,
            "s": "BTC",
            "i": "1m",
            "o": "77357",
            "h": "77377",
            "l": "77357",
            "c": "77362",
            "v": volume,
            "n": 1,
        },
    }


def _quote(coin):
    return {
        "channel": "bbo",
        "data": {
            "coin": coin,
            "time": int(REVISION_RECEIPT.timestamp() * 1000),
            "bbo": [{"px": "100", "sz": "1", "n": 1}, {"px": "101", "sz": "1", "n": 1}],
        },
    }


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
    """Use recorded receipt times while retaining the real supervisor/feed pumps."""

    def dispatch(self, packet, now):
        frame, received = packet
        return [
            update.model_copy(update={"received_at": received})
            for update in super().dispatch(frame, received)
        ]


async def _wait_until(predicate, task):
    async with asyncio.timeout(3):
        while not predicate():
            assert not task.done(), repr(task.exception())
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_recorded_closed_revision_keeps_real_pump_and_all_quotes_running(tmp_path):
    with LiveBuffer(tmp_path) as buffer:
        transport = _QueueTransport()
        supervisor = _RecordedClockSupervisor(transport)
        supervisor.subscribe(["BTC", "ETH", "SOL"])
        feed = LiveFeed(lake=buffer)
        feed.attach(supervisor)
        subscriber = feed.subscribe()
        task = asyncio.create_task(feed.run())
        try:
            await transport.frames.put((_candle(), FIRST_RECEIPT))
            await _wait_until(lambda: len(buffer.replay(kinds=["candle"])) == 1, task)
            await transport.frames.put((_candle("26.45336"), REVISION_RECEIPT))
            await _wait_until(lambda: len(buffer.replay(kinds=["candle"])) == 2, task)
            # A later receipt of identical contents is not another observation.
            await transport.frames.put(
                (_candle("26.45336"), REVISION_RECEIPT + timedelta(seconds=1))
            )
            for coin in ("BTC", "ETH", "SOL"):
                await transport.frames.put((_quote(coin), REVISION_RECEIPT + timedelta(seconds=2)))
            await _wait_until(lambda: len(buffer.replay(kinds=["quote"])) == 3, task)
            assert not task.done()
            candles = buffer.replay(kinds=["candle"])
            assert [row.payload["volume"] for row in candles] == [26.45105, 26.45336]
            assert [row.received_at for row in candles] == [FIRST_RECEIPT, REVISION_RECEIPT]
            assert all(row.payload["final"] is True for row in candles)
            assert {row.sequence for row in candles} == {int(OPEN.timestamp() * 1000)}
            delivered = [subscriber.get_nowait() for _ in range(subscriber.qsize())]
            assert [row.source_event_id for row in delivered if row.kind is UpdateKind.CANDLE] == [
                row.source_event_id for row in candles
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


def _supervisor(rest=None):
    supervisor = HyperliquidVenueSupervisor(ScriptedHyperliquidTransport([]), rest=rest)
    supervisor.subscribe(["BTC"])
    return supervisor


def _observed(supervisor, frame, received):
    [row] = supervisor.dispatch(frame, received)
    return row.model_copy(update={"received_at": received})


def _legacy_id(opened):
    encoded = json.dumps(
        [int(opened.timestamp() * 1000), "BTC", "1m", "final", None], separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_closed_rest_and_websocket_observation_identity_and_recovery_parity(tmp_path):
    class Rest:
        def candles(self, coin, interval, *, start, end):
            assert (coin, interval, start, end) == ("BTC", "1m", OPEN, OPEN)
            return [_candle("26.45336")["data"]]

        def l2_book(self, coin, *, at):
            raise RuntimeError("book unavailable in this candle-only fixture")

    supervisor = _supervisor(Rest())
    previous = _observed(supervisor, _candle(opened=OPEN - timedelta(minutes=1)), OPEN)
    with LiveBuffer(tmp_path) as buffer:
        buffer.append(previous)
        supervisor.on_persisted([previous])
        supervisor.on_disconnect(OPEN + timedelta(seconds=1))
        recovered = [
            row for row in supervisor.resync(REVISION_RECEIPT) if row.kind is UpdateKind.CANDLE
        ]
        assert len(recovered) == 1
        [rest_row] = recovered
        ws_row = _observed(_supervisor(), _candle("26.45336"), REVISION_RECEIPT)
        assert rest_row.source_event_id == ws_row.source_event_id
        assert rest_row.content_digest == ws_row.content_digest
        assert rest_row.continuity is ContinuityState.RECOVERED
        assert rest_row.continuity_evidence.last_durable_source_event_id == previous.source_event_id
        assert (
            rest_row.continuity_evidence.first_recovered_source_event_id == rest_row.source_event_id
        )
        assert buffer.append(rest_row).inserted is True
        assert buffer.append(ws_row).inserted is False
        assert buffer.quarantined() == []


def test_legacy_reopen_retains_evidence_accepts_revision_and_coalesces_history(tmp_path):
    supervisor = _supervisor()
    previous_open = OPEN - timedelta(minutes=1)
    previous = _observed(supervisor, _candle(opened=previous_open), OPEN).model_copy(
        update={"source_event_id": _legacy_id(previous_open)}
    )
    first = _observed(supervisor, _candle(), FIRST_RECEIPT).model_copy(
        update={"source_event_id": _legacy_id(OPEN)}
    )
    with LiveBuffer(tmp_path) as buffer:
        buffer.append_many([previous, first])

    with LiveBuffer(tmp_path) as buffer:
        feed = LiveFeed(lake=buffer)
        restored = _supervisor()
        feed.attach(restored)
        restored.on_disconnect(REVISION_RECEIPT)
        # Recovery evidence must still refer to the retained pre-upgrade ID.
        resumed = _observed(restored, _candle("26.45336"), REVISION_RECEIPT)
        assert resumed.continuity_evidence.last_durable_source_event_id == first.source_event_id
        assert restored._last_candle_open["BTC"] == OPEN

        # A fresh connected observation models normal same-minute delivery.
        new_first = _observed(supervisor, _candle(), FIRST_RECEIPT)
        revision = _observed(supervisor, _candle("26.45336"), REVISION_RECEIPT)
        assert len(feed.ingest([new_first, revision])) == 2
        assert feed.ingest([revision]) == []
        rows = buffer.replay(kinds=["candle"])
        assert [row.source_event_id for row in rows[:2]] == [
            previous.source_event_id,
            first.source_event_id,
        ]
        assert len(rows) == 4
        series = LiveHistoryService(None, feed).history(
            Venue.HYPERLIQUID,
            "BTC",
            HistoryRange.ONE_DAY,
            as_of=REVISION_RECEIPT + timedelta(seconds=1),
        )
        assert [bar.timestamp for bar in series.bars] == [previous_open, OPEN]
        assert [bar.volume for bar in series.bars] == [26.45105, 26.45336]
        assert series.coverage.rows == 2
        assert buffer.quarantined() == []

        conflict = MarketUpdate.model_validate(
            {
                **revision.model_dump(),
                "payload": {**revision.payload, "volume": 99.0},
                "content_digest": None,
            }
        )
        with pytest.raises(LiveIdentityConflictError):
            feed.ingest([conflict])
        assert len(buffer.quarantined()) == 1
        assert len(buffer.replay(kinds=["candle"])) == 4


def test_provisional_identity_is_unchanged():
    row = _observed(_supervisor(), _candle(), OPEN + timedelta(seconds=10))
    expected = hashlib.sha256(
        json.dumps(
            [
                int(OPEN.timestamp() * 1000),
                "BTC",
                "1m",
                "provisional",
                [77357.0, 77377.0, 77357.0, 77362.0, 26.45105],
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert row.source_event_id == expected
    assert row.payload["final"] is False
