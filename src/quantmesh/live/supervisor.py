"""Generic venue supervisor protocol (iteration 0015 Phase B, ADR-0014 decision 2).

The M5-era ``StreamSupervisor`` proved the deterministic shape: every
transition takes ``now`` explicitly so drills script time without
sleeps, and a scripted transport proves disconnect/gap recovery without
the network. This module generalizes that shape for every venue:

- ``SourceStatusTracker`` — pure per-source freshness machine
  (connected → lagging → stale → disconnected), driven by an explicit
  clock.
- ``BackpressureGate`` — bounded emit buffer; on overflow the oldest
  update is dropped *with explicit gap marking* (never silent loss:
  the drop is reported, and the next update for the same stream
  carries ``sequence_gap`` until continuity is re-established).
- ``VenueSupervisor`` — the state machine every venue implements:
  subscribe on open, dispatch frames into normalized ``MarketUpdate``s,
  REST re-sync on reconnect, freshness ticking, exponential reconnect
  backoff. Transitions accumulate into an outbox drained by the pump
  (or the drills); nothing touches a wall clock in the deterministic
  paths. The asyncio pump (``run``) is the live path only; unit tests
  drive the deterministic transitions with scripted transports,
  exactly like the M5 drills.

All external venues stay read-only; the supervisor only ever consumes
and normalizes.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)


def next_backoff(attempt: int, *, base_s: float = 1.0, max_s: float = 30.0) -> float:
    """Exponential backoff for the reconnect loop, capped and finite."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    return min(base_s * (2**attempt), max_s)


@dataclass(frozen=True)
class GapFinding:
    """One recovery gap discovered on reconnect (reported, not hidden)."""

    key: str
    message: str


class SourceStatusTracker:
    """Per-source freshness state machine (ADR-0014, decision 6).

    ``evaluate`` is a pure function of the explicit clock; the tracker
    only records last-activity instants and reports *transitions* so a
    supervisor can emit STATUS updates exactly when the UI state
    changes. ``lag`` is the delay after which a source is considered
    lagging, ``stale`` the delay after which it is stale; both must be
    positive and ``stale > lag``.
    """

    def __init__(self, lag: timedelta, stale: timedelta) -> None:
        if lag <= timedelta(0) or stale <= lag:
            raise ValueError("require 0 < lag < stale")
        self.lag = lag
        self.stale = stale
        self._last_data_at: dict[str, datetime] = {}
        self._state: dict[str, SourceState] = {}

    def note_activity(self, key: str, now: datetime) -> None:
        """Record that ``key`` delivered data at ``now``."""
        self._last_data_at[key] = now

    def evaluate(self, key: str, now: datetime, *, connected: bool) -> SourceState:
        """The source's state at ``now``: connected/lagging/stale/disconnected.

        A connected source that has not yet delivered data is
        ``connected`` (freshly opened, not yet lagging). A source that
        was never registered reports ``unavailable``; a registered
        source whose socket is down reports ``disconnected``.
        """
        if key not in self._last_data_at:
            return SourceState.UNAVAILABLE if not connected else SourceState.CONNECTED
        if not connected:
            return SourceState.DISCONNECTED
        age = now - self._last_data_at[key]
        if age <= self.lag:
            return SourceState.CONNECTED
        if age <= self.stale:
            return SourceState.LAGGING
        return SourceState.STALE

    def transitions(
        self, keys: list[str], now: datetime, *, connected: bool
    ) -> list[tuple[str, SourceState, str]]:
        """(key, state, note) for every key whose state changed since last call."""
        changes: list[tuple[str, SourceState, str]] = []
        for key in keys:
            state = self.evaluate(key, now, connected=connected)
            if self._state.get(key) != state:
                self._state[key] = state
                changes.append((key, state, f"freshness state -> {state.value}"))
        return changes


class BackpressureGate:
    """Bounded emit buffer with explicit gap marking (ADR-0014, decision 2).

    ``push`` enqueues an update and returns how many updates were
    dropped; ``flush`` hands everything staged to the consumer. When
    the buffer is full (the consumer is slower than the venue) the
    oldest pending update is dropped — never silently: the drop is
    reported, and the *next* update for the same (venue, instrument,
    kind) carries ``sequence_gap=True`` so consumers see the hole
    instead of a seamless tape. Emission is explicit so the bound is
    real: an eager auto-flush would empty the buffer before it could
    ever overflow, turning the drop path into dead code. Deterministic
    and wall-clock-free.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self.maxsize = maxsize
        self._pending: list[MarketUpdate] = []
        self._gap_pending: set[tuple[str, str, str]] = set()

    @staticmethod
    def _key(update: MarketUpdate) -> tuple[str, str, str]:
        return (update.venue.value, update.instrument, update.kind.value)

    def push(self, update: MarketUpdate) -> int:
        """Enqueue one update; returns the number of updates dropped.

        The first update delivered *after* a drop carries the gap mark:
        if the pushed update is on the dropped stream it is marked, else
        the first pending survivor of that stream is, else the key is
        remembered until the stream pushes again.
        """
        key = self._key(update)
        if key in self._gap_pending:
            update = update.model_copy(update={"sequence_gap": True})
            self._gap_pending.discard(key)
        dropped = 0
        if len(self._pending) >= self.maxsize:
            victim = self._pending.pop(0)
            victim_key = self._key(victim)
            dropped = 1
            if victim_key == key:
                update = update.model_copy(update={"sequence_gap": True})
            else:
                for index, survivor in enumerate(self._pending):
                    if self._key(survivor) == victim_key:
                        self._pending[index] = survivor.model_copy(
                            update={"sequence_gap": True}
                        )
                        break
                else:
                    self._gap_pending.add(victim_key)
        self._pending.append(update)
        return dropped

    def flush(self) -> list[MarketUpdate]:
        """Everything still buffered, in order."""
        emitted = self._pending
        self._pending = []
        return emitted


class VenueTransport(Protocol):
    """The wire surface a venue supervisor drives; live and scripted alike."""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def send(self, message: dict) -> None: ...
    async def recv(self) -> object: ...


class VenueSupervisor(ABC):
    """Deterministic multi-venue stream state machine.

    Subclasses implement ``dispatch`` (frames → normalized updates),
    ``resync`` (post-reconnect recovery) and the subscription specs.
    The base owns connection state, freshness tracking, status
    emission, gap findings and the reconnect pump. Emitted updates
    accumulate in an outbox; ``drain`` hands them to the pump or the
    drills. Every transition takes ``now`` explicitly.
    """

    def __init__(
        self,
        transport: VenueTransport,
        *,
        lag: timedelta = timedelta(seconds=30),
        stale: timedelta = timedelta(seconds=90),
        max_buffered: int = 1000,
    ) -> None:
        self._transport = transport
        self._gate = BackpressureGate(max_buffered)
        self._freshness = SourceStatusTracker(lag, stale)
        self.connected = False
        self._gap_pending: list[GapFinding] = []
        self._subscribed: dict[str, dict] = {}
        self._watchlist: list[str] = []

    # -- subclasses own these ------------------------------------------------

    @property
    @abstractmethod
    def venue(self):  # pragma: no cover - trivial accessor
        ...

    @abstractmethod
    def specs(self, watchlist: list[str]) -> dict[str, dict]:
        """identifier -> subscription spec, derived from the watchlist."""

    @abstractmethod
    def dispatch(self, frame: object, now: datetime) -> list[MarketUpdate]:
        """One venue frame → zero or more normalized updates."""

    @abstractmethod
    def resync(self, now: datetime) -> list[MarketUpdate]:
        """Post-reconnect recovery: REST backfill/snapshot, gap findings."""

    # -- shared surface ------------------------------------------------------

    @property
    def watchlist(self) -> list[str]:
        return list(self._watchlist)

    def _push(self, update: MarketUpdate) -> None:
        if self._gate.push(update):
            self._gap_pending.append(
                GapFinding(update.instrument, "backpressure dropped an update")
            )

    def _status(
        self, key: str, state: SourceState, note: str | None, now: datetime
    ) -> MarketUpdate:
        instrument = key.rsplit(":", 1)[-1]
        return MarketUpdate(
            venue=self.venue,
            instrument=instrument,
            kind=UpdateKind.STATUS,
            provenance=Provenance.REAL if self.connected else Provenance.UNAVAILABLE,
            data_time=now,
            state=state,
            state_note=note,
        )

    def drain(self) -> list[MarketUpdate]:
        """Everything staged since the last drain, in order."""
        return self._gate.flush()

    def subscribe(self, watchlist: list[str]) -> None:
        """Configure the watchlist; called before the first ``on_open``."""
        self._watchlist = list(watchlist)
        self._subscribed = self.specs(watchlist)

    def on_open(self, now: datetime, *, reconnected: bool = False) -> list[GapFinding]:
        self._transport.connect()
        self.connected = True
        for spec in self._subscribed.values():
            self._transport.send({"method": "subscribe", "subscription": spec})
        findings: list[GapFinding] = []
        if reconnected:
            for update in self.resync(now):
                self._push(update)
            findings, self._gap_pending = self._gap_pending, []
        for key in self._source_keys():
            self._freshness.note_activity(key, now)
        return findings

    def on_frame(self, frame: object, now: datetime) -> None:
        for update in self.dispatch(frame, now):
            self._push(update)
            self._freshness.note_activity(update.instrument, now)

    def on_disconnect(self, now: datetime) -> list[GapFinding]:
        self.connected = False
        findings, self._gap_pending = self._gap_pending, []
        for key, state, note in self._freshness.transitions(
            self._source_keys(), now, connected=False
        ):
            self._push(self._status(key, state, note, now))
        return findings

    def on_tick(self, now: datetime) -> None:
        """Freshness check at the tick cadence: emits STATUS on transitions."""
        if not self.connected:
            return
        for key, state, note in self._freshness.transitions(
            self._source_keys(), now, connected=True
        ):
            self._push(self._status(key, state, note, now))

    def close(self, now: datetime) -> None:
        self.connected = False
        self._transport.close()

    def _source_keys(self) -> list[str]:
        """Instruments the freshness tracker keys on (watchlist symbols).

        Deriving from the watchlist rather than the subscription
        identifiers keeps the tracker honest for every venue: some
        identifiers embed extra text (``candle:btc,1m``) that is not an
        instrument symbol.
        """
        return sorted(self._watchlist)

    # -- live pump (drill-gated, never unit-tested against the network) -------

    async def run(self) -> None:
        """Connect → pump → backoff → reconnect loop over the wire transport."""
        attempt = 0
        while True:
            try:
                findings = self.on_open(datetime.now(UTC), reconnected=attempt > 0)
                for finding in findings:
                    self._push(
                        self._status(
                            finding.key,
                            SourceState.LAGGING,
                            finding.message,
                            datetime.now(UTC),
                        )
                    )
                while True:
                    frame = await self._transport.recv()
                    now = datetime.now(UTC)
                    self.on_frame(frame, now)
                    self.on_tick(now)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.on_disconnect(datetime.now(UTC))
                attempt += 1
                await asyncio.sleep(next_backoff(attempt - 1))
