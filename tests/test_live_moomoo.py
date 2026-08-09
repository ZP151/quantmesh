"""Phase F drills (iteration 0015): the Moomoo OpenD read-only venue
supervisor and its poll transport.

OpenD is request/response, so the wire here is the poll transport
itself — a stub local daemon answers ``probe``/``stock_quote``/
``rt_ticker`` exactly like the M4 client boundary, with the venue's
own wall-clock timestamps. The drills pin:

- the normalized surface: METRICS (last + volume) from the quote
  snapshot, TRADE ticks from ``rt_ticker`` with the venue-reported
  aggressor side and sequence, tick dedup over the overlapping poll
  windows, neutral ticks accepted-but-skipped (no invented side), and
  never a QUOTE (the wire carries no bid/ask — fabricating one is the
  exact thing Phase F forbids);
- fail-closed dispatch: unsubscribed symbols, unknown frame kinds and
  poll failures all raise instead of silence;
- the venue-clock gate: an answer whose own timestamp is outside the
  realtime window (a closed market, a delayed feed) is blocked, so old
  data is never labeled real;
- the honest availability ladder on the live stack: a fresh daemon
  streams real labels; a daemon that stops refreshing its venue clock
  ages the last real numbers to Stale; a poll failure after data
  flowed surfaces DISCONNECTED; a daemon that never answers surfaces
  UNAVAILABLE with no instrument rows — never fabricated real-time.
"""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from quantmesh.domain.models import Venue
from quantmesh.live.contract import Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.moomoo import (
    MoomooProtocolError,
    MoomooVenueSupervisor,
    MoomooVenueTransport,
)
from quantmesh.moomoo.opend import OpenDCapabilities, OpenDUnavailableError

_US_TZ = ZoneInfo("America/New_York")


def _venue_now() -> tuple[str, str]:
    """The stub daemon's wall clock (venue-local, like the SDK)."""
    now = datetime.now(UTC).astimezone(_US_TZ)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")


class _StubOpenD:
    """Canned local OpenD: live wall-clock payloads, with switchable
    probe/poll failures and an optional stale (closed-market) clock."""

    def __init__(
        self,
        *,
        probe_ok: bool = True,
        quote_capability: bool = True,
        quote_fail_after: int | None = None,
        stale_clock: bool = False,
    ) -> None:
        self.probe_ok = probe_ok
        self.quote_capability = quote_capability
        self.quote_fail_after = quote_fail_after
        self.stale_clock = stale_clock
        self.calls = {"probe": 0, "quote": 0, "ticker": 0}
        self.ticker_sequences = {"US.AAPL": 0, "US.NVDA": 0}

    def probe(self) -> OpenDCapabilities:
        self.calls["probe"] += 1
        if not self.probe_ok:
            raise OpenDUnavailableError("OpenD at 127.0.0.1:11111 is unavailable: simulated")
        return OpenDCapabilities(
            quote=self.quote_capability,
            history_kline=True,
            order=False,
            order_query=False,
            auth_required=False,
        )

    def _data_clock(self) -> tuple[str, str]:
        if self.stale_clock:
            return "2020-01-01", "09:30:00"
        return _venue_now()

    def stock_quote(self, codes: list[str]) -> dict:
        self.calls["quote"] += 1
        if self.quote_fail_after is not None and self.calls["quote"] > self.quote_fail_after:
            raise OpenDUnavailableError("OpenD at 127.0.0.1:11111 is unavailable: simulated")
        data_date, data_time = self._data_clock()
        return {
            "rows": [
                {
                    "code": code,
                    "data_date": data_date,
                    "data_time": data_time,
                    "last_price": 190.0 if code == "US.AAPL" else 400.0,
                    "volume": 1_000_000.0,
                }
                for code in codes
            ]
        }

    def rt_ticker(self, code: str, *, num: int) -> dict:
        self.calls["ticker"] += 1
        self.ticker_sequences[code] += 1
        seq = self.ticker_sequences[code]
        price = 190.25 if code == "US.AAPL" else 400.5
        data_date, data_time = self._data_clock()
        rows = []
        # the first poll carries both sides; later polls replay seq 2 so
        # the drills can pin the transport's dedup across windows
        if seq == 1:
            rows.append(
                {
                    "time": f"{data_date} {data_time}",
                    "sequence": 1,
                    "price": price,
                    "volume": 100.0,
                    "direction": "BUY",
                }
            )
            rows.append(
                {
                    "time": f"{data_date} {data_time}",
                    "sequence": 2,
                    "price": price + 0.05,
                    "volume": 50.0,
                    "direction": "SELL",
                }
            )
            rows.append(
                {
                    "time": f"{data_date} {data_time}",
                    "sequence": 3,
                    "price": price,
                    "volume": 25.0,
                    "direction": "NEUTRAL",
                }
            )
        else:
            rows.append(
                {
                    "time": f"{data_date} {data_time}",
                    "sequence": 2,
                    "price": price + 0.05,
                    "volume": 50.0,
                    "direction": "SELL",
                }
            )
        return {"code": code, "rows": rows}


def _supervisor(client: _StubOpenD, *, watchlist: list[str] | None = None):
    supervisor = MoomooVenueSupervisor(MoomooVenueTransport(client))
    supervisor.subscribe(watchlist or ["AAPL", "NVDA"])
    return supervisor


# -- the normalized surface ----------------------------------------------------


def test_specs_derive_market_qualified_codes() -> None:
    supervisor = _supervisor(_StubOpenD())
    specs = supervisor.specs(["AAPL", "NVDA"])
    assert specs == {
        "AAPL": {"symbol": "AAPL", "code": "US.AAPL"},
        "NVDA": {"symbol": "NVDA", "code": "US.NVDA"},
    }
    # an instrument without a known market fails closed at subscribe
    supervisor = MoomooVenueSupervisor(MoomooVenueTransport(_StubOpenD()), market="XX")
    with pytest.raises(ValueError):
        supervisor.subscribe(["AAPL"])


def test_stock_quote_frame_yields_metrics_update() -> None:
    supervisor = _supervisor(_StubOpenD())
    payload = _StubOpenD().stock_quote(["US.AAPL"])
    now = datetime.now(UTC)
    updates = supervisor.dispatch({"kind": "stock_quote", "payload": payload}, now)
    assert len(updates) == 1
    update = updates[0]
    assert update.venue is Venue.MOOMOO
    assert update.instrument == "AAPL"
    assert update.kind is UpdateKind.METRICS
    assert update.provenance is Provenance.REAL
    assert update.payload == {"last": 190.0, "volume": 1_000_000.0}
    # the venue's own data date/time is the honest timestamp
    assert update.data_time.tzinfo is UTC
    assert (now - update.data_time).total_seconds() < 5
    # never a QUOTE: the wire carries no bid/ask
    assert update.kind is not UpdateKind.QUOTE


def test_rt_ticker_frame_yields_trades_with_sides_sequences_and_dedup() -> None:
    supervisor = _supervisor(_StubOpenD())
    now = datetime.now(UTC)
    payload = _StubOpenD().rt_ticker("US.AAPL", num=100)
    updates = supervisor.dispatch({"kind": "rt_ticker", "payload": payload}, now)
    # seq 1 BUY and seq 2 SELL are trades; seq 3 is neutral (no side to
    # claim — accepted, skipped, never invented)
    assert [u.sequence for u in updates] == [1, 2]
    assert [u.payload["side"] for u in updates] == ["buy", "sell"]
    assert [u.payload["price"] for u in updates] == [190.25, 190.30]
    assert [u.payload["size"] for u in updates] == [100.0, 50.0]
    # the next poll's window overlaps: the same venue sequence is not
    # replayed — the tape never shows a tick twice
    again = _StubOpenD().rt_ticker("US.AAPL", num=100)
    again["rows"] = again["rows"][1:]
    assert supervisor.dispatch({"kind": "rt_ticker", "payload": again}, now) == []
    # a fresh sequence still flows
    data_date, data_time = _venue_now()
    again["rows"] = [
        {
            "time": f"{data_date} {data_time}",
            "sequence": 4,
            "price": 191.0,
            "volume": 10.0,
            "direction": "BUY",
        }
    ]
    updates = supervisor.dispatch({"kind": "rt_ticker", "payload": again}, now)
    assert [u.sequence for u in updates] == [4]


def test_stale_venue_clock_emits_nothing() -> None:
    """A daemon answering with an old venue clock (a closed market, or
    a delayed feed) is blocked at dispatch: emitting the snapshot would
    label old data "real". The last real numbers age honestly instead
    (the feed drills below)."""
    supervisor = _supervisor(_StubOpenD(stale_clock=True))
    stale = _StubOpenD(stale_clock=True)
    now = datetime.now(UTC)
    assert (
        supervisor.dispatch(
            {"kind": "stock_quote", "payload": stale.stock_quote(["US.AAPL"])}, now
        )
        == []
    )
    assert (
        supervisor.dispatch(
            {"kind": "rt_ticker", "payload": stale.rt_ticker("US.AAPL", num=100)}, now
        )
        == []
    )


def test_dispatch_fails_closed() -> None:
    supervisor = _supervisor(_StubOpenD(), watchlist=["AAPL"])
    now = datetime.now(UTC)
    with pytest.raises(MoomooProtocolError):
        supervisor.dispatch(
            {"kind": "stock_quote", "payload": _StubOpenD().stock_quote(["US.NVDA"])}, now
        )
    with pytest.raises(MoomooProtocolError):
        supervisor.dispatch({"kind": "mystery", "payload": {}}, now)
    with pytest.raises(MoomooProtocolError):
        supervisor.dispatch({"kind": "poll_error", "message": "boom"}, now)
    with pytest.raises(MoomooProtocolError):
        supervisor.dispatch("not a frame", now)


# -- the poll transport --------------------------------------------------------


def test_connect_probes_and_serves_quote_capability() -> None:
    client = _StubOpenD()
    transport = MoomooVenueTransport(client)

    async def run() -> None:
        transport.connect()
        transport.send({"symbol": "AAPL", "code": "US.AAPL"})
        frame = await asyncio.wait_for(transport.recv(), timeout=5)
        assert frame["kind"] == "stock_quote"
        transport.close()

    asyncio.run(run())
    assert client.calls["probe"] == 1


def test_connect_fails_honestly_when_opend_is_unavailable() -> None:
    transport = MoomooVenueTransport(_StubOpenD(probe_ok=False))

    async def run() -> None:
        with pytest.raises(OpenDUnavailableError):
            transport.connect()

    asyncio.run(run())


def test_connect_refuses_when_quote_capability_is_off() -> None:
    transport = MoomooVenueTransport(_StubOpenD(quote_capability=False))

    async def run() -> None:
        with pytest.raises(MoomooProtocolError):
            transport.connect()

    asyncio.run(run())


def test_poll_failure_becomes_a_poll_error_frame() -> None:
    """A failed poll call is queued as a poll_error frame — the
    supervisor raises on it and the pump disconnects, so a dying daemon
    surfaces through the status model instead of stalling the wire."""
    client = _StubOpenD(quote_fail_after=1)
    transport = MoomooVenueTransport(client, poll_interval=timedelta(seconds=0.05))

    async def run() -> None:
        transport.connect()
        transport.send({"symbol": "AAPL", "code": "US.AAPL"})
        while True:
            frame = await asyncio.wait_for(transport.recv(), timeout=5)
            if frame["kind"] == "poll_error":
                assert "simulated" in str(frame["message"])
                break
        transport.close()

    asyncio.run(run())


# -- the live-stack drills (feed + supervisor on one daemon loop) --------------


def _start_pump(feed: LiveFeed) -> tuple[threading.Thread, asyncio.Task[None]]:
    loop = asyncio.new_event_loop()
    started = threading.Event()
    holder: dict[str, object] = {}

    def runner() -> None:
        asyncio.set_event_loop(loop)
        task = loop.create_task(feed.run())
        holder["task"] = task
        started.set()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    if not started.wait(timeout=5):
        raise AssertionError("the pump never started")
    return thread, cast(asyncio.Task[None], holder["task"])


def _stop_pump(thread, loop, run_task: asyncio.Task[None], transport) -> None:
    loop.call_soon_threadsafe(run_task.cancel)
    loop.call_soon_threadsafe(transport.close)  # cancels the poll task
    thread.join(timeout=5)


def _wait_for(condition, timeout: float = 10.0) -> None:
    deadline = timeout
    while deadline > 0:
        if condition():
            return
        threading.Event().wait(0.05)
        deadline -= 0.05
    raise AssertionError("condition never became true")


def _state(feed: LiveFeed, symbol: str) -> dict:
    return feed.latest_state()["instruments"].get(symbol, {})


def _moomoo_venue(feed: LiveFeed) -> dict:
    return next((v for v in feed.statuses()["venues"] if v["venue"] == "moomoo"), {})


def _source_state(feed: LiveFeed, symbol: str) -> str | None:
    sources = _moomoo_venue(feed).get("sources", [])
    row = next((s for s in sources if s["instrument"] == symbol), {})
    return row.get("state")


def test_live_stack_streams_real_labels_from_a_live_daemon() -> None:
    """The real poll cycle: fresh venue timestamps stream the metrics +
    trade surface with real labels."""
    feed = LiveFeed(lag=timedelta(seconds=2), stale=timedelta(seconds=4))
    client = _StubOpenD()
    transport = MoomooVenueTransport(client, poll_interval=timedelta(seconds=0.1))
    supervisor = MoomooVenueSupervisor(transport)
    supervisor.subscribe(["AAPL"])
    feed.attach(supervisor)
    thread, run_task = _start_pump(feed)
    loop = run_task.get_loop()
    try:
        _wait_for(lambda: _state(feed, "AAPL").get("label") == "real")
        kinds = _state(feed, "AAPL")["kinds"]
        assert kinds["metrics"]["payload"]["last"] == 190.0
        assert kinds["metrics"]["payload"]["volume"] == 1_000_000.0
        # the newest trade is the SELL (seq 2) — the BUY (seq 1) was
        # replaced by the kinds-cache, and the label is real
        _wait_for(
            lambda: _state(feed, "AAPL")
            .get("kinds", {})
            .get("trade", {})
            .get("payload", {})
            .get("side")
            == "sell"
        )
        kinds = _state(feed, "AAPL")["kinds"]
        assert kinds["trade"]["sequence"] == 2
        assert kinds["trade"]["label"] == "real"
        assert _source_state(feed, "AAPL") == "connected"
    finally:
        _stop_pump(thread, loop, run_task, transport)


def test_live_stack_ages_stale_when_the_venue_clock_stops() -> None:
    """The daemon keeps answering but its own clock stopped (a closed
    market, or a delayed feed): the blocked polls stream nothing new,
    so the last real numbers age to Stale — honestly labeled."""
    feed = LiveFeed(lag=timedelta(seconds=2), stale=timedelta(seconds=4))
    client = _StubOpenD()
    transport = MoomooVenueTransport(client, poll_interval=timedelta(seconds=0.1))
    supervisor = MoomooVenueSupervisor(transport)
    supervisor.subscribe(["AAPL"])
    feed.attach(supervisor)
    thread, run_task = _start_pump(feed)
    loop = run_task.get_loop()
    try:
        _wait_for(lambda: _state(feed, "AAPL").get("label") == "real")
        client.stale_clock = True
        _wait_for(lambda: _state(feed, "AAPL").get("label") == "stale")
        kinds = _state(feed, "AAPL")["kinds"]
        # the last real numbers remain visible, honestly labeled stale
        assert kinds["metrics"]["payload"]["last"] == 190.0
        assert kinds["trade"]["label"] == "stale"
    finally:
        _stop_pump(thread, loop, run_task, transport)


def test_live_stack_honest_disconnected_when_the_daemon_dies() -> None:
    """Data flowed, then a poll call failed: the pump disconnects and
    the status model surfaces the watchlist as DISCONNECTED while the
    last real numbers stay visible."""
    feed = LiveFeed(lag=timedelta(seconds=2), stale=timedelta(seconds=4))
    client = _StubOpenD(quote_fail_after=1)
    transport = MoomooVenueTransport(client, poll_interval=timedelta(seconds=0.1))
    supervisor = MoomooVenueSupervisor(transport)
    supervisor.subscribe(["AAPL"])
    feed.attach(supervisor)
    thread, run_task = _start_pump(feed)
    loop = run_task.get_loop()
    try:
        # the first poll's real numbers flow before the daemon dies
        _wait_for(lambda: "metrics" in _state(feed, "AAPL").get("kinds", {}))
        _wait_for(lambda: _source_state(feed, "AAPL") == "disconnected")
        assert _moomoo_venue(feed).get("connected") is False
        # the last real numbers remain visible; the disconnect's STATUS
        # update (provenance unavailable) honestly flips the row label
        row = _state(feed, "AAPL")
        assert row["label"] == "unavailable"
        assert row["kinds"]["metrics"]["payload"]["last"] == 190.0
        assert row["kinds"]["trade"]["payload"]["side"] == "sell"
    finally:
        _stop_pump(thread, loop, run_task, transport)


def test_live_stack_honest_unavailable_when_opend_is_down() -> None:
    """A daemon that never answers surfaces every watchlist instrument
    as UNAVAILABLE with no instrument rows — the honest state model,
    never a fabricated number."""
    feed = LiveFeed(lag=timedelta(seconds=2), stale=timedelta(seconds=4))
    client = _StubOpenD(probe_ok=False)
    transport = MoomooVenueTransport(client, poll_interval=timedelta(seconds=0.05))
    supervisor = MoomooVenueSupervisor(transport)
    supervisor.subscribe(["AAPL", "NVDA"])
    feed.attach(supervisor)
    thread, run_task = _start_pump(feed)
    loop = run_task.get_loop()
    try:
        # wait for the disconnect STATUS updates themselves (the
        # statuses() defaults alone are not the surface)
        _wait_for(lambda: set(feed.latest_state()["instruments"]) == {"AAPL", "NVDA"})
        assert _source_state(feed, "AAPL") == "unavailable"
        assert _source_state(feed, "NVDA") == "unavailable"
        assert _moomoo_venue(feed).get("connected") is False
        # the watchlist rows exist — honestly labeled unavailable, with
        # no metrics/trade surface at all: never a fabricated number
        instruments = feed.latest_state()["instruments"]
        assert set(instruments) == {"AAPL", "NVDA"}
        for row in instruments.values():
            assert row["label"] == "unavailable"
            assert "metrics" not in row["kinds"]
            assert "trade" not in row["kinds"]
    finally:
        _stop_pump(thread, loop, run_task, transport)
