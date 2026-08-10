"""The local feed surface: stream + latest-state + connector health +
the prediction comparison board (iteration 0015 Phases C and E,
ADR-0014 decision 4).

The browser connects only to the local server: venue URLs, transports
and supervisors live server-side; the SPA receives normalized
``MarketUpdate`` JSON over WebSocket (preferred) or SSE (fallback),
plus the latest-state, connector-health and prediction snapshots over
REST. Double-mounted like the demo router — one registration serves
the root contract (``/live/*``) and the SPA surface (``/api/live/*``).
Without an attached feed the handlers answer 404 ("no live feed is
attached"), so the workstation is unchanged when no live watchlist is
configured; without an attached prediction board the comparison
handler answers 404 ("no prediction board is attached") the same way.

Subscription is eager (in the handler, before the response is
streamed): an SSE or WebSocket client that publishes before reading
still receives the update, because its queue was registered on connect
— determinism the drills rely on.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect

from quantmesh.live.feed import LiveFeed
from quantmesh.live.prediction import PredictionBoard

_HEARTBEAT_SECONDS = 15.0  # SSE comment heartbeat; keeps idle streams alive
_REPLAY_LIMIT_MAX = 10_000  # upper bound per replay request


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

    @router.get("/live/prediction")
    def live_prediction(request: Request) -> list[dict[str, object]]:
        """The prediction comparison surface (Phase E): per pair, per
        venue the implied probability (mid), bid/ask, spread bps, touch
        depth, book liquidity and the feed's freshness label, plus the
        cross-venue probability difference — a pure fold of the feed's
        latest state at one explicit clock, so the labels and the
        numbers in one response always agree."""
        board = getattr(request.app.state, "prediction", None)
        if not isinstance(board, PredictionBoard):
            raise HTTPException(
                status_code=404, detail="no prediction board is attached"
            )
        feed = _feed(request)
        now = datetime.now(UTC)
        return board.render(feed.latest_state(now=now), now)

    @router.get("/live/replay/windows")
    def live_replay_windows(request: Request) -> dict[str, object]:
        """The recorded replay extent (iteration 0019 slice 4): the
        earliest/latest ``received_at``, row count and venues of the
        attached replay lake. A feed without a lake, or a lake that
        holds nothing yet, answers 404 with an honest reason — there is
        no fabricated window."""
        feed = _feed(request)
        extent = feed.replay_extent()
        if extent is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "no replay lake is attached"
                    if not feed.lake_attached
                    else "the replay lake holds no recorded updates yet"
                ),
            )
        return {"source": "lake", **extent}

    @router.get("/live/replay")
    def live_replay(
        request: Request,
        start: str | None = Query(default=None, description="ISO-8601 window start"),
        end: str | None = Query(default=None, description="ISO-8601 window end"),
        limit: int = Query(default=5000, ge=1, le=_REPLAY_LIMIT_MAX),
    ) -> dict[str, object]:
        """Replay a recorded window from the local lake in append
        (``local_seq``) order. ``start``/``end`` bound the window on
        ``received_at``; both must be timezone-aware ISO instants.
        Every returned update keeps its venue, provenance, event time,
        receive time, sequence and gap marks — the replay surface is the
        same evidence contract the live surface uses, labeled as
        replayed, never folded into the live cache."""
        feed = _feed(request)
        if not feed.lake_attached:
            raise HTTPException(status_code=404, detail="no replay lake is attached")
        if (start is None) != (end is None):
            raise HTTPException(
                status_code=422, detail="start and end must be provided together"
            )
        start_dt = end_dt = None
        if start is not None:
            try:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            except ValueError as error:
                raise HTTPException(
                    status_code=422, detail="start and end must be ISO-8601 timestamps"
                ) from error
            if start_dt.tzinfo is None or end_dt.tzinfo is None:
                raise HTTPException(
                    status_code=422,
                    detail="start and end must be timezone-aware timestamps",
                )
            if start_dt >= end_dt:
                raise HTTPException(
                    status_code=422, detail="start must precede end"
                )
        updates = feed.replay_window(start=start_dt, end=end_dt, limit=limit)
        return {
            "source": "lake",
            "window": {
                "start": start_dt.isoformat() if start_dt is not None else None,
                "end": end_dt.isoformat() if end_dt is not None else None,
                "count": len(updates),
            },
            "updates": [update.model_dump(mode="json") for update in updates],
        }

    @router.get("/live/price-trail")
    def live_price_trail(
        request: Request,
        symbols: str = Query(description="Comma-separated instrument symbols"),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        feed = _feed(request)
        if not feed.lake_attached:
            raise HTTPException(status_code=404, detail="no replay lake is attached")
        syms = [s.strip() for s in symbols.split(",") if s.strip()]
        if not syms:
            raise HTTPException(status_code=422, detail="at least one symbol is required")
        return {"trail": feed.price_trail(syms, limit=limit)}

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
