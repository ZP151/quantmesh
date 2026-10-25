"""Offline controlled candles in actual stores, not real market qualification."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from quantmesh.api import workstation
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.feed import LiveFeed
from tests.test_live_history import _candle

AT = datetime(2026, 10, 25, 16, 0, tzinfo=UTC)


def readonly_feed(root):
    with LiveBuffer(root, retention_days=0) as writer:
        writer.append_many(
            [
                _candle(AT - timedelta(minutes=3), sequence=100, close=100, interval="1m"),
                _candle(AT - timedelta(minutes=2), sequence=101, close=101, interval="1m"),
            ]
        )
    return LiveFeed(lake=LiveBuffer(root, read_only=True))


def readonly_app(root):
    feed = readonly_feed(root)
    try:
        app = workstation.create_workstation_app(
            account=PaperAccount(cash=0),
            live_feed=feed,
            workspace_clock=lambda: AT,
            market_data_only=True,
        )
    except BaseException:
        feed.replay_buffer.close()
        raise
    return app, feed


def test_optin_health_and_formal_history_without_unrelated_services(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unrelated store/service initialized")

    for name in (
        "WatchlistStore",
        "PaperAccountStore",
        "DecisionInboxService",
        "DecisionSessionService",
        "SnapshotCatalog",
        "ReplayService",
    ):
        monkeypatch.setattr(workstation, name, forbidden)
    app, feed = readonly_app(tmp_path)
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["runtime_mode"] == "live" and health["market_data_only"] is True
        assert health["paper_mode"] is True and health["live_trading"] is False
        assert health["market_data_acquisition"] == {
            "state": "stopped",
            "reason": "bounded_cache_read_only",
        }
        response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200
        assert response.json()["primary"]["source"] == "hyperliquid-live-replay"
        assert response.json()["primary"]["coverage"]["rows"] == 2
        assert str(tmp_path) not in response.text
        workspace = client.get("/api/instruments/hyperliquid/BTC/workspace?range=1d")
        assert workspace.status_code == 200
        assert datetime.fromisoformat(workspace.json()["generated_at"]) == AT
    assert feed.replay_buffer._closed


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/kill-switch"),
        ("POST", "/watchlist/add"),
        ("POST", "/api/research/spy-replay/jobs"),
        ("POST", "/api/decision-packets"),
        ("POST", "/api/paper/controls/resume"),
        ("DELETE", "/api/watchlist"),
        ("PUT", "/api/account"),
        ("PATCH", "/api/health"),
    ],
)
def test_all_mutators_and_legacy_aliases_are_forbidden(tmp_path, method, path):
    app, _ = readonly_app(tmp_path)
    with TestClient(app) as client:
        response = client.request(method, path, content=b"not even JSON")
        assert response.status_code == 403
        assert response.json() == {"detail": "market_data_read_only"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/account",
        "/api/research/jobs",
        "/api/instruments/hyperliquid/ETH/history?range=1d",
        "/api/instruments/hyperliquid/BTC/history?range=5d",
        "/api/instruments/hyperliquid/BTC/workspace?range=1d&forecast_id=private",
        "/api/instruments/hyperliquid/BTC/history?range=1d&range=1d",
        "/api/live/replay",
        "/openapi.json",
    ],
)
def test_get_identity_and_query_cannot_expand_scope(tmp_path, path):
    app, _ = readonly_app(tmp_path)
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 403
        assert response.json() == {"detail": "market_data_read_only"}


def test_asgi_denial_does_not_receive_body_and_denies_other_websocket_paths(tmp_path):
    app, feed = readonly_app(tmp_path)

    async def exercise():
        async def receive():
            pytest.fail("denied scope must not read a body or message")

        for scope in [
            dict(type="http", method="POST", path="/api/health", query_string=b""),
            dict(type="websocket", path="/api/decision-packets", query_string=b""),
            dict(type="websocket", path="/api/live/ws", query_string=b"coin=ETH"),
        ]:
            sent = []

            async def send(message):
                sent.append(message)

            await app(scope, receive, send)
            if scope["type"] == "http":
                assert sent[0]["status"] == 403
            else:
                assert sent == [
                    dict(type="websocket.close", code=1008, reason="market_data_read_only")
                ]

    try:
        asyncio.run(exercise())
    finally:
        feed.replay_buffer.close()


def test_head_options_and_ordinary_health_are_compatible(tmp_path):
    app, _ = readonly_app(tmp_path)
    with TestClient(app) as client:
        response = client.head("/api/health")
        assert response.status_code == 200 and response.content == b""
        assert client.options("/api/health").status_code == 204
        assert client.options("/api/account").status_code == 403
        assert client.head("/api/live/stream").status_code == 403
    with TestClient(workstation.create_workstation_app(account=PaperAccount(cash=1))) as client:
        health = client.get("/api/health").json()
        assert "market_data_only" not in health and "market_data_acquisition" not in health


def test_cli_enters_mode_before_account_model_research_or_public_client_construction(
    tmp_path, monkeypatch
):
    import uvicorn

    feed = readonly_feed(tmp_path)
    reader = feed.replay_buffer
    monkeypatch.setattr(LiveBuffer, "from_bounded_config", classmethod(lambda cls, *args: reader))
    monkeypatch.setattr(workstation.settings, "live_cache_root", tmp_path)
    monkeypatch.setattr(workstation.settings, "live_cache_budget_file", tmp_path / "budget.json")
    monkeypatch.setattr(workstation.settings, "model_name", "MUST_NOT_INITIALIZE")

    def forbidden(*args, **kwargs):
        pytest.fail("forbidden CLI initialization")

    for name in (
        "TrustedDataCatalog",
        "PaperAccountFile",
        "OrderJournal",
        "HttpModelTransport",
        "ModelGateway",
        "DecisionPacketStore",
        "PriceForecastRegistry",
    ):
        monkeypatch.setattr(workstation, name, forbidden)

    def serve(app, **kwargs):
        with TestClient(app) as client:
            assert client.get("/api/health").json()["market_data_only"] is True
            assert client.post("/api/research/jobs", json={}).status_code == 403

    monkeypatch.setattr(uvicorn, "run", serve)
    try:
        workstation.main(["--live", "--market-data-only", "--port", "8877"])
    finally:
        reader.close()
    assert reader._closed


@pytest.mark.parametrize(
    "args",
    [
        ["--market-data-only"],
        ["--live", "--market-data-only", "--demo"],
        ["--live", "--market-data-only", "--spy-replay-root", "private"],
        ["--live", "--market-data-only", "--market-data-recovery-bars", "6"],
    ],
)
def test_cli_invalid_mode_never_opens_cache_or_store(args, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration initialized a store")

    monkeypatch.setattr(workstation, "TrustedDataCatalog", forbidden)
    monkeypatch.setattr(LiveBuffer, "from_bounded_config", forbidden)
    with pytest.raises(SystemExit) as error:
        workstation.main(args)
    assert error.value.code == 2


def test_cli_real_trading_setting_refuses_before_cache(monkeypatch):
    monkeypatch.setattr(workstation.settings, "allow_live_trading", True)
    monkeypatch.setattr(LiveBuffer, "from_bounded_config", lambda *a: pytest.fail("cache opened"))
    with pytest.raises(SystemExit) as error:
        workstation.main(["--live", "--market-data-only"])
    assert error.value.code == 2


def test_cli_failed_bind_before_lifespan_closes_exact_owned_cache(tmp_path, monkeypatch):
    import uvicorn

    reader = readonly_feed(tmp_path).replay_buffer
    closed = []
    real_close = reader.close

    def close():
        closed.append(reader)
        real_close()

    monkeypatch.setattr(reader, "close", close)
    monkeypatch.setattr(LiveBuffer, "from_bounded_config", classmethod(lambda cls, *args: reader))
    monkeypatch.setattr(workstation.settings, "live_cache_root", tmp_path)
    monkeypatch.setattr(workstation.settings, "live_cache_budget_file", tmp_path / "budget.json")

    def fail_before_lifespan(app, **kwargs):
        assert not app.state.market_data_started
        raise OSError("controlled bind failure")

    monkeypatch.setattr(uvicorn, "run", fail_before_lifespan)
    with pytest.raises(OSError, match="controlled bind failure"):
        workstation.main(["--live", "--market-data-only"])
    assert reader._closed and closed == [reader]


def test_failed_owned_task_surfaces_fixed_error_and_still_closes(tmp_path, monkeypatch):
    app, feed = readonly_app(tmp_path)

    async def fail():
        raise RuntimeError("PRIVATE source failure")

    monkeypatch.setattr(feed, "run", fail)
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.json()["market_data_acquisition"] == dict(
            state="failed", reason="feed_failed"
        )
        assert "PRIVATE" not in response.text
    assert feed.replay_buffer._closed


def test_cancelled_shutdown_joins_actual_close_then_preserves_cancellation(tmp_path, monkeypatch):
    from threading import Event

    app, feed = readonly_app(tmp_path)
    entered, release = Event(), Event()
    real_close = feed.replay_buffer.close

    def close():
        entered.set()
        assert release.wait(2)
        real_close()

    monkeypatch.setattr(feed.replay_buffer, "close", close)

    async def exercise():
        manager = app.router.lifespan_context(app)
        await manager.__aenter__()
        task = asyncio.create_task(manager.__aexit__(None, None, None))
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not getattr(feed.replay_buffer, "_closed", False)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert feed.replay_buffer._closed

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        real_close()


def test_public_receipt_adapter_preserves_transport_receipt_and_real_request_clock():
    from types import SimpleNamespace

    from quantmesh.api.market_data_only import ObservedPublicInfoRecoverySource

    calls, returned = [], []

    class Transport:
        def candles(self, symbol, interval, *, start, end):
            calls.append((symbol, interval, start, end))
            response = SimpleNamespace(
                payload=[{"opaque": "controlled row"}], received_at=datetime.now(UTC)
            )
            returned.append(response)
            return response

    before = datetime.now(UTC)
    observation = ObservedPublicInfoRecoverySource(Transport()).observe_candles(
        "BTC", "1m", start=AT, end=AT + timedelta(minutes=1) - timedelta(milliseconds=1)
    )
    assert observation.rows is returned[0].payload
    assert observation.received_at is returned[0].received_at
    assert before <= observation.requested_at <= observation.received_at <= datetime.now(UTC)
    assert calls == [("BTC", "1m", AT, AT + timedelta(minutes=1) - timedelta(milliseconds=1))]
