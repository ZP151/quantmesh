"""Live feed hub: venue supervisors → replay lake → latest-state cache →
browser (iteration 0015 Phase C, ADR-0014 decision 4).

``LiveFeed`` owns the server side of the feed surface:

- *ingest* — every update a supervisor drains is appended to the replay
  lake and folded into the latest-state cache (one entry per venue +
  instrument + kind). ``ingest`` is a pure function of its inputs, so
  drills drive the whole surface without the network.
- *fan-out* — one bounded queue per subscriber (a WebSocket or SSE
  client); a slow client drops oldest, never stalls the feed. The pump
  is the only asyncio path: it runs the attached supervisors' own
  reconnect pumps, drains their outboxes, and ticks their freshness
  monitors on a cadence so quiet venues still surface lagging/stale
  STATUS transitions.
- *queries* — ``latest_state`` renders the per-instrument surface with
  provenance+age labels (real/delayed/stale/synthetic/unavailable) and
  ``statuses`` the per-venue connector health, both derived from the
  cache the supervisors fill.

The browser connects only to the local server; venue URLs and clients
live server-side only (ADR-0014 decision 4). Without an attached feed
the workstation runs unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.supervisor import VenueSupervisor

_POLL_SECONDS = 0.05  # supervisor outbox poll cadence (drain loop)
_TICK_SECONDS = 1.0  # freshness tick cadence (quiet venues still transition)
_MAX_SUBSCRIBER_QUEUE = 256  # per-client bound; overflow drops oldest

FRESH = "real"
DELAYED = "delayed"
STALE = "stale"
SYNTHETIC = "synthetic"
UNAVAILABLE = "unavailable"

_LIVE_STATES = ("connected", "lagging")  # a venue is "connected" while either holds


def label(update: MarketUpdate, now: datetime, *, lag: timedelta) -> str:
    """The cockpit state label for one update (ADR-0014 decision 6).

    Provenance is the base label; a real update past its freshness lag
    is stale. (``lag`` bounds the supervisor's freshness machine; the
    connector-health endpoint carries the finer lagging/stale split.)
    """
    if update.provenance is Provenance.UNAVAILABLE:
        return UNAVAILABLE
    if update.provenance is Provenance.SYNTHETIC:
        return SYNTHETIC
    if update.provenance is Provenance.DELAYED:
        return DELAYED
    if now - update.received_at > lag:
        return STALE
    return FRESH


def _age_ms(now: datetime, received_at: datetime) -> int:
    return max(0, int((now - received_at).total_seconds() * 1000))


def _view(update: MarketUpdate, now: datetime, *, lag: timedelta) -> dict[str, object]:
    """One kind's JSON view: the update plus its provenance+age label."""
    return {
        "kind": update.kind.value,
        "provenance": update.provenance.value,
        "data_time": update.data_time.isoformat(),
        "received_at": update.received_at.isoformat(),
        "age_ms": _age_ms(now, update.received_at),
        "sequence": update.sequence,
        "sequence_gap": update.sequence_gap,
        "label": label(update, now, lag=lag),
        "payload": update.payload,
    }


class LiveFeed:
    """Hub between venue supervisors and the browser feed surface."""

    def __init__(
        self,
        *,
        lake: LiveBuffer | None = None,
        lag: timedelta = timedelta(seconds=30),
        stale: timedelta = timedelta(seconds=90),
        queue_size: int = _MAX_SUBSCRIBER_QUEUE,
    ) -> None:
        if not (timedelta(0) < lag < stale):
            raise ValueError("require 0 < lag < stale")
        self.lag = lag
        self.stale = stale
        self._lake = lake
        self._queue_size = queue_size
        self._latest: dict[tuple[str, str, str], MarketUpdate] = {}
        self._supervisors: list[VenueSupervisor] = []
        self._subscribers: set[asyncio.Queue[MarketUpdate]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- deterministic surface (drills) -------------------------------------

    def attach(self, supervisor: VenueSupervisor) -> None:
        """Register a supervisor; the pump runs it and drains its outbox."""
        self._supervisors.append(supervisor)

    def ingest(self, updates: list[MarketUpdate]) -> None:
        """Cache + replay lake; the wall-clock-free path every drill drives."""
        for update in updates:
            self._latest[(update.venue.value, update.instrument, update.kind.value)] = update
            if self._lake is not None:
                self._lake.append(update)

    async def publish(self, update: MarketUpdate) -> None:
        """Ingest and fan out to every subscriber (server-loop path)."""
        self.ingest([update])
        await self._deliver(update)

    def publish_threadsafe(self, update: MarketUpdate) -> None:
        """Publish from another thread (TestClient drills): ingested
        synchronously, delivered on the server loop once the pump runs."""
        self.ingest([update])
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._schedule_deliver, update)

    def _schedule_deliver(self, update: MarketUpdate) -> None:
        if self._loop is not None:
            self._loop.create_task(self._deliver(update))

    # -- queries ------------------------------------------------------------

    def latest_state(self, *, now: datetime | None = None) -> dict[str, object]:
        """One entry per instrument: the latest update per kind plus the
        newest update's provenance/age label (the watchlist badge)."""
        now = now if now is not None else datetime.now(UTC)
        instruments: dict[str, dict[str, object]] = {}
        newest: dict[str, MarketUpdate] = {}
        for (venue, instrument, kind), update in sorted(self._latest.items()):
            entry = instruments.setdefault(instrument, {"venue": venue})
            kinds = entry.setdefault("kinds", {})  # type: ignore[assignment]
            kinds[kind] = _view(update, now, lag=self.lag)  # type: ignore[index]
            if instrument not in newest or update.received_at > newest[instrument].received_at:
                newest[instrument] = update
        for instrument, update in newest.items():
            instruments[instrument]["label"] = label(update, now, lag=self.lag)
        return {"generated_at": now.isoformat(), "instruments": instruments}

    def statuses(self, *, now: datetime | None = None) -> dict[str, object]:
        """Per-venue connector health: the latest STATUS per source, with
        ``unavailable`` defaults for watchlist instruments that have not
        reported yet (a freshly opened socket is not a status update)."""
        now = now if now is not None else datetime.now(UTC)
        sources: dict[str, dict[str, dict[str, object]]] = {}
        for (venue, instrument, kind), update in self._latest.items():
            if kind != UpdateKind.STATUS.value or update.state is None:
                continue
            sources.setdefault(venue, {})[instrument] = {
                "instrument": instrument,
                "state": update.state.value,
                "note": update.state_note,
                "data_time": update.data_time.isoformat(),
                "received_at": update.received_at.isoformat(),
                "age_ms": _age_ms(now, update.received_at),
            }
        for supervisor in self._supervisors:
            for instrument in supervisor.watchlist:
                entry = sources.setdefault(supervisor.venue.value, {}).setdefault(
                    instrument,
                    {
                        "instrument": instrument,
                        "state": "unavailable",
                        "note": "no status update received yet",
                        "data_time": None,
                        "received_at": None,
                        "age_ms": None,
                    },
                )
                entry["state"] = str(entry["state"])
        venues = [
            {
                "venue": venue,
                "connected": any(
                    str(source["state"]) in _LIVE_STATES for source in sources_map.values()
                ),
                "sources": [sources_map[key] for key in sorted(sources_map)],
            }
            for venue, sources_map in sorted(sources.items())
        ]
        return {"generated_at": now.isoformat(), "venues": venues}

    # -- replay (iteration 0019 slice 4) --------------------------------------

    @property
    def lake_attached(self) -> bool:
        """Whether the feed persists to a replay lake (the ``--live``
        workstation always does; a feed built without a lake cannot
        replay anything)."""
        return self._lake is not None

    def replay_window(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
    ) -> list[MarketUpdate]:
        """Replay appended updates in local_seq order (oldest first)
        within an optional received_at window. Raises ``ValueError``
        when no lake is attached or the window is malformed."""
        if self._lake is None:
            raise ValueError("no replay lake is attached")
        return self._lake.replay(start=start, end=end, limit=limit)

    def replay_extent(self) -> dict[str, object] | None:
        """The recorded extent of the attached lake: earliest/latest
        received_at, row count and distinct venues — the metadata the
        replay window workflow renders before replaying. ``None`` when
        the lake holds nothing or no lake is attached."""
        if self._lake is None:
            return None
        rows = self._lake.extent()
        if rows["count"] == 0:
            return None
        return rows

    # -- fan-out ------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[MarketUpdate]:
        """A bounded per-client queue; overflow drops oldest for that
        client so one slow subscriber never stalls the feed. The
        latest-state endpoint remains the client's reconciliation truth."""
        queue: asyncio.Queue[MarketUpdate] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[MarketUpdate]) -> None:
        self._subscribers.discard(queue)

    async def _deliver(self, update: MarketUpdate) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()  # drop-oldest, bounded per client
            queue.put_nowait(update)

    # -- live pump (drill-gated, never unit-tested against the network) ------

    async def run(self) -> None:
        """Start the attached supervisors and pump their outboxes to the
        lake, the cache and the subscribers; ticks freshness so quiet
        venues still surface lagging/stale transitions. Only the app
        lifespan starts this; shutdown cancels it (and with it every
        supervisor pump, whose reconnect loops never exit on their own).
        """
        self._loop = asyncio.get_running_loop()
        tasks = [asyncio.create_task(supervisor.run()) for supervisor in self._supervisors]
        tasks.append(asyncio.create_task(self._drain_loop()))
        tasks.append(asyncio.create_task(self._tick_loop()))
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            # inside a cancelled task every await raises CancelledError;
            # swallow it so the cleanup gather still runs to completion
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _drain_loop(self) -> None:
        while True:
            for supervisor in self._supervisors:
                for update in supervisor.drain():
                    await self.publish(update)
            await asyncio.sleep(_POLL_SECONDS)

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(_TICK_SECONDS)
            now = datetime.now(UTC)
            for supervisor in self._supervisors:
                supervisor.on_tick(now)
                for update in supervisor.drain():
                    await self.publish(update)
