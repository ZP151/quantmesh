"""Scripted asyncio fake venue for fixture-first WebSocket tests (ADR-0014).

Phase B drives the venue supervisor against this server; Phase A only
proves the server itself is deterministic: the same plan always
produces the same frames, in the same order, with the same delays and
the same disconnects. A plan is a list of ``(delay, frame)`` steps
where ``frame`` is either a JSON-serializable payload (sent verbatim)
or a control marker:

- ``{"__cmd": "drop"}`` — abort the connection abruptly (a network
  drop; the client sees a closed socket mid-stream).
- ``{"__cmd": "close"}`` — end the session cleanly.

Every connection replays the whole plan from the start, so reconnect
drills observe a deterministic stream on each attempt. The special
``last_frame_received`` hook lets a client signal that it is done;
the handler then finishes its script and closes.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import websockets

_CONTROL_KEYS = {"__cmd"}


@dataclass
class ScriptedVenue:
    """A deterministic scripted venue: serves one or more clients the
    same plan on every connection."""

    plan: list[tuple[float, object]] = field(default_factory=list)
    host: str = "127.0.0.1"
    #: per-connection handshake delay before the first frame (0 = none)
    first_delay: float = 0.0

    async def __aenter__(self) -> ScriptedVenue:
        self._server = await websockets.serve(
            self._handle, self.host, 0, max_size=2**20
        )
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://{self.host}:{port}"
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, socket: websockets.ServerConnection) -> None:
        try:
            if self.first_delay:
                await asyncio.sleep(self.first_delay)
            for delay, frame in self.plan:
                if delay:
                    await asyncio.sleep(delay)
                if isinstance(frame, dict) and set(frame) == _CONTROL_KEYS:
                    if frame["__cmd"] == "drop":
                        await socket.close(code=1006, reason="simulated network drop")
                        return
                    if frame["__cmd"] == "close":
                        await socket.close(code=1000, reason="scripted end")
                        return
                    raise ValueError(f"unknown control frame {frame!r}")
                await socket.send(json.dumps(frame))
        except websockets.ConnectionClosed:
            return  # client went away mid-script: fine for a fixture


async def collect_frames(venue: ScriptedVenue, *, stop_after: int | None = None) -> list[object]:
    """Connect once and collect every data frame the script sends.

    ``stop_after`` limits how many frames to collect before closing the
    client socket (used to prove that the server replays the full plan
    per connection).
    """

    frames: list[object] = []
    async with websockets.connect(venue.url) as socket:
        async for raw in socket:
            frame = json.loads(raw)
            if isinstance(frame, dict) and set(frame) == _CONTROL_KEYS:
                raise AssertionError(f"control frame leaked to client: {frame!r}")
            frames.append(frame)
            if stop_after is not None and len(frames) >= stop_after:
                break
    return frames
