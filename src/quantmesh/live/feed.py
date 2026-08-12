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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import MappingProxyType
from typing import Any

from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
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


@dataclass(frozen=True)
class ExactUpdateSnapshot:
    """Detached point-in-time view of one exact live stream key."""

    venue: Venue
    instrument: str
    kind: UpdateKind
    source: str
    provenance: Provenance
    data_time: datetime
    received_at: datetime
    sequence: int | None
    sequence_gap: bool
    payload: Mapping[str, object]
    continuity_proven: bool
    predecessor_sequence: int | None
    predecessor_data_time: datetime | None
    freshness_label: str | None
    age_ms: int | None


@dataclass(frozen=True)
class _ContinuityProof:
    proven: bool
    predecessor_sequence: int | None
    predecessor_data_time: datetime | None


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _continuity_proof(
    previous: MarketUpdate | None,
    current: MarketUpdate,
) -> _ContinuityProof:
    if previous is None:
        return _ContinuityProof(False, None, None)
    predecessor = _ContinuityProof(False, previous.sequence, previous.data_time)
    if current.kind is not previous.kind:
        return predecessor
    if current.sequence_gap or previous.sequence_gap:
        return predecessor
    if not all(
        _is_aware(value)
        for value in (
            previous.data_time,
            current.data_time,
            previous.received_at,
            current.received_at,
        )
    ):
        return predecessor
    if current.received_at < previous.received_at:
        return predecessor
    if current.kind is not UpdateKind.CANDLE:
        sequence_ordered = (
            type(current.sequence) is int
            and type(previous.sequence) is int
            and current.sequence > previous.sequence
        )
        receipt_ordered = (
            current.sequence is None
            and previous.sequence is None
            and current.received_at > previous.received_at
        )
        if (
            not (sequence_ordered or receipt_ordered)
            or current.data_time < previous.data_time
        ):
            return predecessor
        return _ContinuityProof(True, previous.sequence, previous.data_time)
    if type(current.sequence) is not int or type(previous.sequence) is not int:
        return predecessor
    previous_interval = previous.payload.get("interval")
    current_interval = current.payload.get("interval")
    if not isinstance(previous_interval, str) or current_interval != previous_interval:
        return predecessor
    try:
        duration = interval_to_timedelta(current_interval)
    except ValueError:
        return predecessor
    same_bar = current.data_time == previous.data_time
    next_bar = current.data_time == previous.data_time + duration
    if not (same_bar or next_bar):
        return predecessor
    if same_bar and current.sequence < previous.sequence:
        return predecessor
    if next_bar and current.sequence <= previous.sequence:
        return predecessor
    return _ContinuityProof(True, previous.sequence, previous.data_time)


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
        self._lock = RLock()
        self._latest: dict[tuple[str, str, str], MarketUpdate] = {}
        self._continuity: dict[tuple[str, str, str], _ContinuityProof] = {}
        self._continuity_barriers: set[tuple[str, str, str]] = set()
        self._supervisors: list[VenueSupervisor] = []
        self._subscribers: set[asyncio.Queue[MarketUpdate]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def replay_buffer(self) -> LiveBuffer | None:
        """The attached local replay authority, when persistence is enabled."""
        return self._lake

    # -- deterministic surface (drills) -------------------------------------

    def attach(self, supervisor: VenueSupervisor) -> None:
        """Register a supervisor; the pump runs it and drains its outbox."""
        with self._lock:
            self._supervisors.append(supervisor)

    def ingest(self, updates: list[MarketUpdate]) -> None:
        """Cache + replay lake; the wall-clock-free path every drill drives."""
        for update in updates:
            cached = update.model_copy(deep=True)
            key = (cached.venue.value, cached.instrument, cached.kind.value)
            with self._lock:
                proof = _continuity_proof(self._latest.get(key), cached)
                barrier_consumed = key in self._continuity_barriers
                if barrier_consumed:
                    proof = _ContinuityProof(
                        False,
                        proof.predecessor_sequence,
                        proof.predecessor_data_time,
                    )
                if self._lake is not None:
                    self._lake.append(cached)
                self._continuity[key] = proof
                self._latest[key] = cached
                if barrier_consumed:
                    self._continuity_barriers.discard(key)
                if cached.kind is UpdateKind.STATUS and cached.state in (
                    SourceState.DISCONNECTED,
                    SourceState.UNAVAILABLE,
                ):
                    affected = [
                        stream_key
                        for stream_key in self._latest
                        if stream_key[:2] == key[:2]
                        and stream_key[2] != UpdateKind.STATUS.value
                    ]
                    for stream_key in affected:
                        previous = self._latest[stream_key]
                        self._continuity[stream_key] = _ContinuityProof(
                            False,
                            previous.sequence,
                            previous.data_time,
                        )
                        self._continuity_barriers.add(stream_key)

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

    def snapshot_exact(
        self,
        venue: Venue,
        instrument: str,
        kind: UpdateKind,
        *,
        as_of: datetime,
    ) -> ExactUpdateSnapshot | None:
        """Return a detached snapshot for one venue/instrument/kind key."""
        with self._lock:
            key = (venue.value, instrument, kind.value)
            update = self._latest.get(key)
            if update is None:
                return None
            copied = update.model_copy(deep=True)
            proof = self._continuity[key]
        try:
            freshness_label = label(copied, as_of, lag=self.lag)
            age_ms = _age_ms(as_of, copied.received_at)
        except (TypeError, ValueError):
            freshness_label = None
            age_ms = None
        return ExactUpdateSnapshot(
            venue=copied.venue,
            instrument=copied.instrument,
            kind=copied.kind,
            source=copied.venue.value,
            provenance=copied.provenance,
            data_time=copied.data_time,
            received_at=copied.received_at,
            sequence=copied.sequence,
            sequence_gap=copied.sequence_gap,
            payload=_freeze(copied.payload),
            continuity_proven=proof.proven,
            predecessor_sequence=proof.predecessor_sequence,
            predecessor_data_time=proof.predecessor_data_time,
            freshness_label=freshness_label,
            age_ms=age_ms,
        )

    def latest_state(self, *, now: datetime | None = None) -> dict[str, object]:
        """One entry per venue/instrument identity with latest views by kind.

        The canonical ``venue:instrument`` key keeps equal symbols from
        different venues independent through the wire and frontend state.
        """
        now = now if now is not None else datetime.now(UTC)
        instruments: dict[str, dict[str, object]] = {}
        newest: dict[str, MarketUpdate] = {}
        with self._lock:
            latest = [
                (key, update.model_copy(deep=True))
                for key, update in sorted(self._latest.items())
            ]
        for (venue, instrument, kind), update in latest:
            identity = f"{venue}:{instrument}"
            entry = instruments.setdefault(identity, {"venue": venue, "instrument": instrument})
            kinds = entry.setdefault("kinds", {})  # type: ignore[assignment]
            kinds[kind] = _view(update, now, lag=self.lag)  # type: ignore[index]
            if identity not in newest or update.received_at > newest[identity].received_at:
                newest[identity] = update
        for identity, update in newest.items():
            instruments[identity]["label"] = label(update, now, lag=self.lag)
        return {"generated_at": now.isoformat(), "instruments": instruments}

    def statuses(self, *, now: datetime | None = None) -> dict[str, object]:
        """Per-venue connector health: the latest STATUS per source, with
        ``unavailable`` defaults for watchlist instruments that have not
        reported yet (a freshly opened socket is not a status update)."""
        now = now if now is not None else datetime.now(UTC)
        sources: dict[str, dict[str, dict[str, object]]] = {}
        with self._lock:
            latest = [
                (key, update.model_copy(deep=True))
                for key, update in self._latest.items()
            ]
            supervisors = [
                (supervisor.venue, tuple(supervisor.watchlist))
                for supervisor in self._supervisors
            ]
        for (venue, instrument, kind), update in latest:
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
        for venue, watchlist in supervisors:
            for instrument in watchlist:
                entry = sources.setdefault(venue.value, {}).setdefault(
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

    def price_trail(
        self, identities: list[tuple[str, str]], limit: int = 20
    ) -> dict[str, list[float]]:
        if self._lake is None:
            raise ValueError("no replay lake is attached")
        return self._lake.price_trail(identities, limit=limit)

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
