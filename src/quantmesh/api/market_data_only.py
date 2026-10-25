"""Default-off BTC observation surface; HTTP reads, budgeted internal cache writes."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from fastapi.responses import JSONResponse, Response

from quantmesh.api.app import create_app
from quantmesh.hyperliquid.public_info import PublicInfoRecoverySource
from quantmesh.instruments.api import instrument_router
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.instruments.workspace import InstrumentWorkspaceService
from quantmesh.live.api import live_router
from quantmesh.live.feed import LiveFeed

READ_ONLY_CODE = "market_data_read_only"
OBSERVATION_LIMITATION = (
    "Minute-end public REST snapshot observations only; interim WebSocket candles are not "
    "archived. Provider finality and historical PIT are unknown; coverage is partial."
)
_STREAM = {"/live/stream", "/api/live/stream"}
_WS = {"/live/ws", "/api/live/ws"}
_READS = {
    "/health",
    "/api/health",
    "/kill-switch",
    "/api/kill-switch",
    "/api/markets",
    "/live/state",
    "/api/live/state",
    "/live/status",
    "/api/live/status",
    *_STREAM,
}
_INSTRUMENTS = {
    f"{prefix}/instruments/hyperliquid/BTC/{kind}"
    for prefix in ("", "/api")
    for kind in ("history", "workspace")
}
_CHART = {"/app", "/app/", "/app/instruments/hyperliquid/BTC"}


def _allowed(scope):
    path = scope.get("path", "")
    try:
        pairs = parse_qsl(
            scope.get("query_string", b"").decode("ascii"),
            keep_blank_values=True,
            strict_parsing=True,
        )
    except (UnicodeError, ValueError):
        return False
    if scope["type"] == "websocket":
        return path in _WS and not pairs
    if path in _INSTRUMENTS:
        return pairs == [("range", "1d")]
    if path in _CHART:
        return len(dict(pairs)) == len(pairs) and all(
            (key, value) in {("range", "1d"), ("mode", "line")} for key, value in pairs
        )
    if pairs:
        return False
    if path in _READS or path in {"/app/favicon.svg", "/app/icons.svg"}:
        return True
    return path.startswith("/app/assets/") and all(
        part not in {".", "..", ""} for part in path.removeprefix("/app/assets/").split("/")
    )


class MarketDataOnlyGuard:
    """Outer ASGI policy: denied scopes never receive bodies or invoke handlers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            if _allowed(scope):
                return await self.app(scope, receive, send)
            return await send(dict(type="websocket.close", code=1008, reason=READ_ONLY_CODE))
        if scope["type"] != "http":
            raise RuntimeError("market_data_scope_invalid")
        method = scope["method"]
        if (
            method not in {"GET", "HEAD", "OPTIONS"}
            or not _allowed(scope)
            or (method == "HEAD" and scope["path"] in _STREAM)
        ):
            return await JSONResponse({"detail": READ_ONLY_CODE}, status_code=403)(
                scope, receive, send
            )
        if method == "OPTIONS":
            return await Response(status_code=204, headers={"Allow": "GET, HEAD, OPTIONS"})(
                scope, receive, send
            )
        if method == "HEAD":
            scope = {**scope, "method": "GET"}

            async def head_send(message):
                if message["type"] == "http.response.body":
                    message = {**message, "body": b""}
                await send(message)

            return await self.app(scope, receive, head_send)
        return await self.app(scope, receive, send)


class ObservationHistory(LiveHistoryService):
    def history(self, *args, **kwargs):
        series = super().history(*args, **kwargs)
        return series.model_copy(
            update={"limitations": (*series.limitations, OBSERVATION_LIMITATION)}
        )


class ObservedPublicInfoRecoverySource(PublicInfoRecoverySource):
    """Same existing public transport, preserving its actual response receipt."""

    def observe_candles(self, symbol, interval, *, start, end):
        from quantmesh.live.hyperliquid import CandleObservation

        requested_at = datetime.now(UTC)
        response = self._transport.candles(symbol, interval, start=start, end=end)
        return CandleObservation(
            rows=response.payload, requested_at=requested_at, received_at=response.received_at
        )


def build_market_data_cli_app(*, host, recovery_limit):
    """Called only after CLI validation, before the ordinary --live constructors."""
    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount
    from quantmesh.hyperliquid.public_info import PublicInfoTransport
    from quantmesh.live.buffer import LiveBuffer
    from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, LiveHyperliquidTransport
    from quantmesh.settings import settings

    lake = LiveBuffer.from_bounded_config(settings.live_cache_root, settings.live_cache_budget_file)
    client_close = None
    try:
        feed = LiveFeed(lake=lake)
        if not lake.read_only:
            public = PublicInfoTransport()
            # PublicInfoTransport has no public close surface; this assembly
            # created its direct-network client and owns its lifetime exactly.
            client_close = public._client.close
            source = HyperliquidVenueSupervisor(
                LiveHyperliquidTransport("wss://api.hyperliquid.xyz/ws"),
                rest=ObservedPublicInfoRecoverySource(public),
                candle_only=True,
                candle_recovery_limit=recovery_limit,
            )
            source.subscribe(["BTC"])
            feed.attach(source)
        app = create_workstation_app(
            account=PaperAccount(cash=0), live_feed=feed, market_data_only=True, host=host
        )
        if client_close is not None:
            app.state.market_data_close_callbacks.append(client_close)
        return app
    except BaseException:
        try:
            lake.close()
        finally:
            if client_close is not None:
                client_close()
        raise


async def _join_owned(task):
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled |= bool(asyncio.current_task().cancelling())
            continue
    with contextlib.suppress(asyncio.CancelledError):
        task.result()
    return cancelled


def build_market_data_app(*, account, feed, clock=None):
    # The factory calls this before constructing unrelated services/stores.
    from quantmesh.api.workstation import PageContext, _register_spa_serving, spa_router

    if not isinstance(feed, LiveFeed) or feed.replay_buffer is None:
        raise ValueError("market_data_configuration_invalid")
    lake = feed.replay_buffer
    supervisors = tuple(feed._supervisors)  # owned assembly, never a public subscription surface
    if lake.read_only:
        if supervisors:
            raise ValueError("market_data_configuration_invalid")
    elif (
        lake.write_budget is None
        or len(supervisors) != 1
        or not (
            getattr(supervisors[0], "candle_only", False) and supervisors[0].watchlist == ["BTC"]
        )
    ):
        raise ValueError("market_data_configuration_invalid")
    if account.orders or account.positions:
        raise ValueError("market_data_configuration_invalid")
    app = create_app(account=account)
    selected_clock = clock or (lambda: datetime.now(UTC))
    history = ObservationHistory(None, feed)
    app.state.live, app.state.history, app.state.instrument_clock = feed, history, selected_clock
    app.state.instrument_workspace = InstrumentWorkspaceService(
        history=history,
        forecasts=None,
        account_provider=lambda: account,
        marks_provider=lambda: {},
        live_feed=feed,
        now=selected_clock,
    )
    app.state.page_context = PageContext(
        account=account, marks={}, markets={"hyperliquid": {"BTC": None}}, watchlist=None
    )
    app.include_router(spa_router(), prefix="/api")
    for router in (instrument_router(), live_router()):
        app.include_router(router)
        app.include_router(
            router, prefix="/api", generate_unique_id_function=lambda r: f"api_{r.name}"
        )
    _register_spa_serving(app)
    app.add_middleware(MarketDataOnlyGuard)
    app.state.market_data_only = True
    state = {"state": "starting", "reason": None}
    app.state.market_data_started = app.state.market_data_closed = False
    app.state.market_data_close_callbacks = []

    def status():
        result = dict(state)
        if result["state"] == "running" and supervisors:
            result["reason"] = getattr(supervisors[0], "observation_issue", None)
        return result

    app.state.market_data_status = status

    def close():
        if app.state.market_data_closed:
            return
        try:
            lake.close()
        finally:
            for callback in app.state.market_data_close_callbacks:
                callback()
        app.state.market_data_closed = True

    def dispose_unstarted():
        if not app.state.market_data_started:
            close()

    app.state.market_data_dispose_unstarted = dispose_unstarted

    @asynccontextmanager
    async def lifespan(app):
        app.state.market_data_started = True
        state.update(
            state="stopped" if lake.read_only else "running",
            reason="bounded_cache_read_only" if lake.read_only else None,
        )
        task = asyncio.create_task(feed.run())

        def completed(task):
            if not task.cancelled() and task.exception() is not None:
                state.update(state="failed", reason="feed_failed")
            elif lake.read_only:
                return
            elif feed.capacity_exhausted:
                state.update(
                    state="capacity_stopped",
                    reason=feed.capacity_stop_error or "capacity_exhausted",
                )
            elif task.cancelled():
                state.update(state="stopped", reason="shutdown")
            else:
                task.exception()  # consume; raw exceptions never become API metadata
                state.update(state="failed", reason="feed_failed")

        task.add_done_callback(completed)
        try:
            await asyncio.sleep(0)
            yield
        finally:
            task.cancel()
            cancelled = False
            try:
                cancelled |= await _join_owned(task)
            except Exception:
                state.update(state="failed", reason="feed_failed")
                logging.getLogger(__name__).error("Market data acquisition: feed_failed")
            closer = asyncio.create_task(asyncio.to_thread(close))
            try:
                cancelled |= await _join_owned(closer)
            except Exception:
                state.update(state="failed", reason="cache_close_failed")
                raise RuntimeError("market_data_cache_close_failed") from None
            if cancelled:
                raise asyncio.CancelledError

    app.router.lifespan_context = lifespan
    return app
