"""The local feed surface: stream + latest-state + connector health
(iteration 0015 Phase C, ADR-0014 decision 4).

The browser connects only to the local server: venue URLs, transports
and supervisors live server-side; the SPA receives normalized
``MarketUpdate`` JSON over WebSocket (preferred) or SSE (fallback),
plus the latest-state and connector-health snapshots over REST.
Double-mounted like the demo router — one registration serves the root
contract (``/live/*``) and the SPA surface (``/api/live/*``). Without an
attached feed the handlers answer 404 ("no live feed is attached"), so
the workstation is unchanged when no live watchlist is configured.

Subscription is eager (in the handler, before the response is
streamed): an SSE or WebSocket client that publishes before reading
still receives the update, because its queue was registered on connect
— determinism the drills rely on.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect

from quantmesh.live.feed import LiveFeed

_HEARTBEAT_SECONDS = 15.0  # SSE comment heartbeat; keeps idle streams alive


def _feed(request: Request) -> LiveFeed:
    feed = getattr(request.app.state, "live", None)
    if not isinstance(feed, LiveFeed):
        raise HTTPException(status_code=404, detail="no live feed is attached")
    return feed


def live_router() -> APIRouter:
    """The /live surface; handlers read ``request.app.state.live`` so
    both mounts share the same feed handle."""
    router = APIRouter()

    @router.get("/live/state")
    def live_state(request: Request) -> dict[str, object]:
        """The latest update per venue+instrument+kind, with the
        provenance+age label the watchlist badges on."""
        return _feed(request).latest_state()

    @router.get("/live/status")
    def live_status(request: Request) -> dict[str, object]:
        """Per-venue connector health from the supervisors' STATUS
        transitions (connected/lagging/stale/disconnected/unavailable)."""
        return _feed(request).statuses()

    @router.get("/live/stream")
    async def live_stream(request: Request) -> StreamingResponse:
        """SSE fallback: one ``data:`` event per normalized update,
        with a heartbeat comment every 15 s."""
        feed = _feed(request)
        queue = feed.subscribe()
        return StreamingResponse(_events(queue, feed), media_type="text/event-stream")

    @router.websocket("/live/ws")
    async def live_ws(websocket: WebSocket) -> None:
        """WebSocket stream: one JSON ``MarketUpdate`` per message."""
        feed = getattr(websocket.app.state, "live", None)
        if not isinstance(feed, LiveFeed):
            await websocket.close(code=1011, reason="no live feed is attached")
            return
        await websocket.accept()
        queue = feed.subscribe()
        try:
            while True:
                update = await queue.get()
                await websocket.send_json(update.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass  # a closed client is an unsubscription, never an error
        finally:
            feed.unsubscribe(queue)

    return router


async def _events(queue: asyncio.Queue, feed: LiveFeed) -> AsyncGenerator[str, None]:
    """The SSE body: drain the subscriber queue into ``data:`` events.
    The queue was registered by the handler before the response started
    streaming, so nothing published between connect and first read is
    lost; ``finally`` releases the subscription when the client goes."""
    try:
        yield "retry: 2000\n\n"
        while True:
            try:
                update = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {update.model_dump_json()}\n\n"
    finally:
        feed.unsubscribe(queue)
