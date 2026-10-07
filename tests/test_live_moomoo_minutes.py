"""Bounded source-backed equity candle polling, without execution authority."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.live.contract import UpdateKind
from quantmesh.live.feed import LiveFeed, label
from quantmesh.live.moomoo import MoomooVenueSupervisor, MoomooVenueTransport
from quantmesh.moomoo.opend import OpenDCapabilities
from quantmesh.settings import Settings

NOW = datetime(2026, 9, 23, 14, 2, 30, tzinfo=UTC)


def window(labels=("10:01:00", "10:02:00", "10:03:00"), close=101):
    return {
        "code": "US.AAPL",
        "interval": "1m",
        "autype": "None",
        "session": "regular",
        "rows": [
            {
                "code": "US.AAPL",
                "time_key": f"2026-09-23 {t}",
                "open": 100,
                "high": 103,
                "low": 99,
                "close": close,
                "volume": 1000,
            }
            for t in labels
        ],
    }


def supervisor():
    s = MoomooVenueSupervisor(MoomooVenueTransport(None))
    s.subscribe(["AAPL"])
    return s


def test_candle_window_revisions_appends_and_identical_reads_do_not_refresh():
    s = supervisor()
    updates = s.dispatch({"kind": "current_kline", "payload": window()}, NOW)
    assert len(updates) == 3
    assert [u.data_time for u in updates] == [NOW.replace(minute=m, second=0) for m in (0, 1, 2)]
    assert all(u.kind is UpdateKind.CANDLE for u in updates)
    assert [u.sequence for u in updates] == sorted({u.sequence for u in updates})
    assert updates[-1].payload["provider_time_key"] == "2026-09-23 10:03:00"
    assert updates[-1].payload["sequence_origin"] == "local-observation"
    assert updates[-1].payload["license"] == "moomoo-private-market-data"
    assert updates[-1].payload["adjustment"] == "unadjusted"
    assert label(updates[0], NOW, lag=timedelta(seconds=30)) == "stale"
    assert label(updates[-1], NOW, lag=timedelta(seconds=30)) == "real"
    assert (
        s.dispatch({"kind": "current_kline", "payload": window()}, NOW + timedelta(seconds=5)) == []
    )
    revised = window()
    revised["rows"][-1]["close"] = 102
    revision = s.dispatch({"kind": "current_kline", "payload": revised}, NOW + timedelta(seconds=6))
    assert len(revision) == 1 and revision[0].data_time == updates[-1].data_time
    assert revision[0].sequence > updates[-1].sequence
    assert revision[0].payload["close"] == 102
    assert label(revision[0], NOW + timedelta(minutes=2), lag=timedelta(seconds=30)) == "stale"
    next_window = window(("10:02:00", "10:03:00", "10:04:00"))
    next_window["rows"][1]["close"] = 102
    appended = s.dispatch(
        {"kind": "current_kline", "payload": next_window}, NOW + timedelta(minutes=1)
    )
    assert len(appended) == 1 and appended[0].data_time.minute == 3
    feed = LiveFeed()
    feed.ingest([*updates, *revision, *appended])
    snap = feed.snapshot_exact(
        Venue.MOOMOO, "AAPL", UpdateKind.CANDLE, as_of=NOW + timedelta(minutes=1)
    )
    assert snap.continuity_proven
    assert feed.snapshot_exact(Venue.MOOMOO, "AAPL", UpdateKind.QUOTE, as_of=NOW) is None


def test_gap_is_not_filled_and_old_revision_cannot_rewind_latest():
    s = supervisor()
    s.dispatch({"kind": "current_kline", "payload": window()}, NOW)
    changed_old = window()
    changed_old["rows"][0]["close"] = 102
    assert (
        s.dispatch({"kind": "current_kline", "payload": changed_old}, NOW + timedelta(seconds=5))
        == []
    )
    gap = s.dispatch(
        {"kind": "current_kline", "payload": window(("10:07:00", "10:08:00"))},
        NOW + timedelta(minutes=5),
    )
    assert [u.data_time.minute for u in gap] == [6, 7]


def test_reconnect_does_not_reemit_cached_window_but_keeps_continuity_barrier():
    s = supervisor()
    feed = LiveFeed()
    initial = s.dispatch({"kind": "current_kline", "payload": window()}, NOW)
    feed.ingest(initial)
    s.on_disconnect(NOW + timedelta(seconds=1))
    feed.ingest(s.drain())
    assert (
        s.dispatch({"kind": "current_kline", "payload": window()}, NOW + timedelta(seconds=5)) == []
    )
    revised = window()
    revised["rows"][-1]["close"] = 102
    changed = s.dispatch({"kind": "current_kline", "payload": revised}, NOW + timedelta(seconds=6))
    assert len(changed) == 1
    assert changed[0].sequence > initial[-1].sequence
    feed.ingest(changed)
    snapshot = feed.snapshot_exact(
        Venue.MOOMOO, "AAPL", UpdateKind.CANDLE, as_of=NOW + timedelta(seconds=6)
    )
    assert not snapshot.continuity_proven
    appended = s.dispatch(
        {"kind": "current_kline", "payload": window(("10:04:00",))},
        NOW + timedelta(minutes=1),
    )
    assert len(appended) == 1
    assert appended[0].data_time == NOW.replace(minute=3, second=0)


def test_candle_polling_is_opt_in_and_bounded():
    class Client:
        def probe_market_data(self):
            return OpenDCapabilities(True, True, False, False)

        def stock_quote(self, codes):
            return {"rows": []}

        def rt_ticker(self, code, *, num):
            return {"code": code, "rows": []}

        def current_kline(self, code, *, num):
            assert code == "US.AAPL" and num == 390
            return window()

    async def run():
        wire = MoomooVenueTransport(Client(), candle_num=390)
        try:
            wire.connect()
            wire.send({"symbol": "AAPL", "code": "US.AAPL"})
            frames = [await asyncio.wait_for(wire.recv(), 2) for _ in range(3)]
            assert [f["kind"] for f in frames] == ["stock_quote", "rt_ticker", "current_kline"]
        finally:
            wire.close()

    asyncio.run(run())
    assert Settings().moomoo_candle_num == 0
    for invalid in (-1, 391, True):
        with pytest.raises(ValueError):
            MoomooVenueTransport(Client(), candle_num=invalid)


def test_mixed_watchlist_keeps_other_equity_polling_when_minutes_are_enabled():
    class Client:
        def probe_market_data(self):
            return OpenDCapabilities(True, True, False, False)

        def stock_quote(self, codes):
            return {"rows": []}

        def rt_ticker(self, code, *, num):
            return {"code": code, "rows": []}

        def current_kline(self, code, *, num):
            if code != "US.AAPL":
                raise ValueError("current minute scope excludes this code")
            return window()

    async def run():
        wire = MoomooVenueTransport(
            Client(), candle_num=390, poll_interval=timedelta(milliseconds=5)
        )
        try:
            wire.connect()
            for symbol in ("AAPL", "MSFT"):
                wire.send({"symbol": symbol, "code": "US." + symbol})
            frames = [await asyncio.wait_for(wire.recv(), 0.5) for _ in range(5)]
            assert [f["kind"] for f in frames] == [
                "stock_quote",
                "rt_ticker",
                "current_kline",
                "rt_ticker",
                "stock_quote",
            ]
            assert frames[3]["payload"]["code"] == "US.MSFT"
        finally:
            wire.close()

    asyncio.run(run())
