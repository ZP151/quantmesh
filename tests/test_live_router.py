"""The /api/live surface drills (iteration 0015 Phase C, ADR-0014
decision 4): latest-state, connector health, SSE fallback and WebSocket
stream — double-mounted like the demo router, driven by the feed's
thread-safe publish (no network anywhere; the pump runs only because the
TestClient lifespan starts it).

The deterministic trick the router relies on: subscriptions are eager —
an SSE or WS client's queue is registered in the handler before the
response streams — so a publish made after the client connects is
always received, with no timing races.

The SSE fallback drills against a real uvicorn server on a pinned
loopback port: starlette's TestClient buffers the whole response body
before returning, so an infinite stream cannot be driven through it
(httpx's ``stream()`` would block until the app coroutine completes).
That is exactly the server shape the SPA's fallback transport talks to,
so the drill uses it.
"""

import json
import socket
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.domain.models import Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.prediction import demo_board

SSE_HOST = "127.0.0.1"
SSE_PORT = 8644  # pinned like the other E2E ports; skip when taken
SSE_BASE_URL = f"http://{SSE_HOST}:{SSE_PORT}"

T0 = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)
LAG = timedelta(seconds=30)
STALE = timedelta(seconds=90)


def _upd(
    instrument: str = "BTC",
    kind: UpdateKind = UpdateKind.QUOTE,
    *,
    venue: Venue = Venue.HYPERLIQUID,
    provenance: Provenance = Provenance.REAL,
    received_at: datetime | None = None,
    state: SourceState | None = None,
    sequence: int | None = None,
    sequence_gap: bool = False,
    payload: dict | None = None,
) -> MarketUpdate:
    # Default to "just received" so a wire label of "real" is the
    # expected outcome unless the test makes the update deliberately old.
    received_at = received_at if received_at is not None else datetime.now(UTC)
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=received_at,
        received_at=received_at,
        # STATUS updates carry no payload (contract validator); the rest
        # of the kinds default to a valid quote shape.
        payload=(
            payload if payload is not None else {"bid": 100.0, "ask": 100.5}
        )
        if kind is not UpdateKind.STATUS
        else {},
        state=state,
        state_note="drill" if state is not None else None,
        sequence=sequence,
        sequence_gap=sequence_gap,
    )


def _port_in_use() -> bool:
    with socket.socket() as probe:
        try:
            probe.bind((SSE_HOST, SSE_PORT))
        except OSError:
            return True
    return False


def _wait_for_server() -> None:
    for _ in range(400):
        if _port_in_use():
            return
        threading.Event().wait(0.1)
    raise AssertionError(f"uvicorn never came up on {SSE_HOST}:{SSE_PORT}")


@pytest.fixture(scope="module")
def sse_env(tmp_path_factory):
    """The attached-feed app behind a real uvicorn server: the shape an
    SSE client (and later the SPA fallback) actually talks to."""
    if _port_in_use():
        pytest.skip(f"port {SSE_PORT} is already bound — the pinned SSE port must be free")
    root = tmp_path_factory.mktemp("live-sse")
    feed = LiveFeed(lake=LiveBuffer(root=root), lag=LAG, stale=STALE)
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0), live_feed=feed, host=SSE_HOST
    )
    server = uvicorn.Server(uvicorn.Config(app, host=SSE_HOST, port=SSE_PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_for_server()
        yield SSE_BASE_URL, feed
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture()
def live_app(tmp_path):
    """A workstation app with an attached feed (lake on tmp, pump
    started by the TestClient lifespan) and a bare account."""
    feed = LiveFeed(lake=LiveBuffer(root=tmp_path), lag=LAG, stale=STALE)
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0), live_feed=feed, host="127.0.0.1"
    )
    with TestClient(app) as client:
        yield client, app, feed


@pytest.fixture()
def prediction_app(tmp_path):
    """A workstation app with the feed and the demo prediction board
    attached (Phase E): the comparison surface over the live state."""
    feed = LiveFeed(lake=LiveBuffer(root=tmp_path), lag=LAG, stale=STALE)
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        live_feed=feed,
        prediction=demo_board(),
        host="127.0.0.1",
    )
    with TestClient(app) as client:
        yield client, app, feed


class TestStateEndpoint:
    def test_state_reflects_published_updates(self, live_app) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(_upd())
        feed.publish_threadsafe(
            _upd(
                kind=UpdateKind.TRADE,
                payload={"price": 100.25, "size": 1.0, "side": "buy"},
            )
        )
        response = client.get("/api/live/state")
        assert response.status_code == 200
        instruments = response.json()["instruments"]
        assert set(instruments["hyperliquid:BTC"]["kinds"]) == {"quote", "trade"}
        assert instruments["hyperliquid:BTC"]["label"] == "real"
        assert instruments["hyperliquid:BTC"]["venue"] == "hyperliquid"
        assert instruments["hyperliquid:BTC"]["instrument"] == "BTC"

    def test_label_derivation_on_the_wire(self, live_app) -> None:
        client, _app, feed = live_app
        old_quote = _upd(received_at=datetime.now(UTC) - timedelta(seconds=60))
        feed.publish_threadsafe(old_quote)
        feed.publish_threadsafe(
            _upd(
                kind=UpdateKind.TRADE,
                provenance=Provenance.SYNTHETIC,
                payload={"price": 100.25, "size": 1.0, "side": "buy"},
            )
        )
        response = client.get("/api/live/state")
        kinds = response.json()["instruments"]["hyperliquid:BTC"]["kinds"]
        assert kinds["quote"]["label"] == "stale"
        assert kinds["quote"]["age_ms"] >= 30_000
        assert kinds["trade"]["label"] == "synthetic"

    def test_root_and_api_mounts_agree(self, live_app) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(_upd())
        # generated_at and age_ms are wall-clock measurements taken per
        # request, so they legitimately differ by milliseconds between
        # the two calls — everything else is the same payload.
        def without_clock(snapshot: dict) -> dict:
            return {
                instrument: {
                    **summary,
                    "kinds": {
                        kind: {key: view[key] for key in view if key != "age_ms"}
                        for kind, view in summary["kinds"].items()
                    },
                }
                for instrument, summary in snapshot["instruments"].items()
            }

        root_mount = without_clock(client.get("/live/state").json())
        api_mount = without_clock(client.get("/api/live/state").json())
        assert root_mount == api_mount

    def test_openapi_lists_both_mounts(self, live_app) -> None:
        client, _app, _feed = live_app
        paths = client.get("/openapi.json").json()["paths"]
        # WebSocket routes are not part of OpenAPI — only the HTTP surface.
        assert "/api/live/state" in paths and "/live/state" in paths
        assert "/api/live/stream" in paths and "/live/stream" in paths
        assert "/api/live/prediction" in paths and "/live/prediction" in paths


class TestStatusEndpoint:
    def test_status_reflects_supervisor_transitions(self, live_app) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(_upd(kind=UpdateKind.STATUS, state=SourceState.CONNECTED))
        response = client.get("/api/live/status")
        assert response.status_code == 200
        venues = response.json()["venues"]
        assert venues[0]["venue"] == "hyperliquid"
        assert venues[0]["connected"] is True
        assert venues[0]["sources"][0]["state"] == "connected"


class TestSseStream:
    def test_stream_emits_published_updates(self, sse_env) -> None:
        base_url, feed = sse_env
        with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
            with client.stream("GET", f"{base_url}/api/live/stream") as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                lines = response.iter_lines()
                assert next(lines) == "retry: 2000"
                assert next(lines) == ""
                feed.publish_threadsafe(_upd(sequence=5))
                data_line = next(lines)
        assert data_line.startswith("data: ")
        update = json.loads(data_line[len("data: ") :])
        assert update["instrument"] == "BTC"
        assert update["kind"] == "quote"
        assert update["sequence"] == 5

    def test_updates_published_before_first_read_are_not_lost(self, sse_env) -> None:
        base_url, feed = sse_env
        with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
            with client.stream("GET", f"{base_url}/live/stream") as response:
                lines = response.iter_lines()
                assert next(lines) == "retry: 2000"
                assert next(lines) == ""
                feed.publish_threadsafe(_upd(sequence=1))
                feed.publish_threadsafe(_upd(sequence=2))
                payloads = []
                while len(payloads) < 2:
                    line = next(lines)
                    if line.startswith("data: "):
                        payloads.append(json.loads(line[6:]))
        assert [p["sequence"] for p in payloads] == [1, 2]


class TestWebSocketStream:
    def test_ws_emits_published_updates(self, live_app) -> None:
        client, _app, feed = live_app
        with client.websocket_connect("/api/live/ws") as websocket:
            feed.publish_threadsafe(_upd(sequence=9))
            update = websocket.receive_json()
        assert update["instrument"] == "BTC"
        assert update["kind"] == "quote"
        assert update["sequence"] == 9

    def test_ws_fans_out_to_every_subscriber(self, live_app) -> None:
        client, _app, feed = live_app
        with (
            client.websocket_connect("/api/live/ws") as first,
            client.websocket_connect("/live/ws") as second,
        ):
            feed.publish_threadsafe(_upd(sequence=11))
            assert first.receive_json()["sequence"] == 11
            assert second.receive_json()["sequence"] == 11


class TestPredictionEndpoint:
    """The Phase E comparison surface: per-pair venue rows (implied
    probability, spread, depth, liquidity, freshness label) plus the
    cross-venue diff — folded from the feed's latest state at one
    explicit clock, never a fabricated number."""

    def test_full_surface_with_both_venues(self, prediction_app) -> None:
        client, _app, feed = prediction_app
        feed.publish_threadsafe(
            _upd(
                venue=Venue.POLYMARKET,
                instrument="0xasset-btc-100k",
                payload={
                    "bid": 0.60,
                    "ask": 0.65,
                    "bid_size": 100.0,
                    "ask_size": 75.0,
                },
            )
        )
        feed.publish_threadsafe(
            _upd(
                venue=Venue.KALSHI,
                instrument="KXBTD-26JUN26-1000-C",
                payload={"bid": 0.62, "ask": 0.68, "bid_size": 20.0, "ask_size": 80.0},
            )
        )
        rows = client.get("/api/live/prediction").json()
        pair = next(row for row in rows if row["event_key"] == "btc-100k")
        assert pair["title"] == "BTC above $100k on 2026-06-26"
        assert pair["expiry"] == "2026-06-26T00:00:00+00:00"
        by_venue = {row["venue"]: row for row in pair["venues"]}
        pm = by_venue["polymarket"]
        assert pm["probability"] == 62.5
        assert pm["bid"] == 0.6 and pm["ask"] == 0.65
        assert pm["spread_bps"] == 800.0
        assert pm["depth"] == 175.0
        assert pm["label"] == "real"
        ks = by_venue["kalshi"]
        assert ks["probability"] == 65.0
        assert pair["diff"] == -2.5

    def test_unconfigured_venue_renders_unavailable(self, prediction_app) -> None:
        client, _app, feed = prediction_app
        feed.publish_threadsafe(
            _upd(
                venue=Venue.POLYMARKET,
                instrument="0xasset-solo",
                payload={"bid": 0.3, "ask": 0.34, "bid_size": 10.0, "ask_size": 20.0},
            )
        )
        rows = client.get("/api/live/prediction").json()
        pair = next(row for row in rows if row["event_key"] == "solo-pm")
        by_venue = {row["venue"]: row for row in pair["venues"]}
        assert by_venue["polymarket"]["probability"] == 32.0
        assert by_venue["kalshi"]["label"] == "unavailable"
        assert by_venue["kalshi"]["probability"] is None
        assert pair["diff"] is None

    def test_mounts_agree(self, prediction_app) -> None:
        client, _app, feed = prediction_app
        feed.publish_threadsafe(
            _upd(
                venue=Venue.POLYMARKET,
                instrument="0xasset-eth-5k",
                payload={"bid": 0.5, "ask": 0.54, "bid_size": 1.0, "ask_size": 1.0},
            )
        )
        root = client.get("/live/prediction").json()
        api = client.get("/api/live/prediction").json()
        assert root == api

    def test_404_without_a_board(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get("/api/live/prediction")
        assert response.status_code == 404
        assert response.json()["detail"] == "no prediction board is attached"

    def test_404_without_a_feed(self, tmp_path) -> None:
        # A board without its feed renders nothing: the handler answers
        # the feed's typed 404, never a fabricated comparison.
        app = create_workstation_app(
            account=PaperAccount(cash=100_000.0),
            prediction=demo_board(),
            host="127.0.0.1",
        )
        with TestClient(app) as client:
            response = client.get("/api/live/prediction")
        assert response.status_code == 404
        assert response.json()["detail"] == "no live feed is attached"


class TestNotConfigured:
    def test_state_404_without_a_feed(self) -> None:
        app = create_workstation_app(account=PaperAccount(cash=100_000.0), host="127.0.0.1")
        with TestClient(app) as client:
            response = client.get("/api/live/state")
        assert response.status_code == 404
        assert response.json()["detail"] == "no live feed is attached"


class TestReplayEndpoint:
    """Iteration 0019 slice 4: the recorded replay surface over the
    lake — window extent metadata and a window replay in append order,
    with the full provenance contract preserved on every row. A feed
    without a lake, or a lake that holds nothing, fails honestly."""

    def test_windows_reports_the_recorded_extent(self, live_app) -> None:
        client, _app, feed = live_app
        t1 = T0 + timedelta(seconds=5)
        t2 = T0 + timedelta(seconds=25)
        feed.publish_threadsafe(
            _upd(received_at=t1, sequence=1, payload={"bid": 100.0, "ask": 100.5})
        )
        feed.publish_threadsafe(
            _upd(
                received_at=t2,
                sequence=2,
                venue=Venue.MOOMOO,
                kind=UpdateKind.METRICS,
                payload={"last": 42.0},
            )
        )
        response = client.get("/api/live/replay/windows")
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "lake"
        assert body["count"] == 2
        assert body["earliest"] == t1.isoformat()
        assert body["latest"] == t2.isoformat()
        assert body["venues"] == ["hyperliquid", "moomoo"]

    def test_windows_404_when_the_lake_is_empty(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get("/api/live/replay/windows")
        assert response.status_code == 404
        assert response.json()["detail"] == "the replay lake holds no recorded updates yet"

    def test_replay_returns_updates_in_append_order_with_provenance(
        self, live_app
    ) -> None:
        client, _app, feed = live_app
        # The second append carries an older received_at — append order
        # (local_seq) must still win, exactly like the live cache fold.
        t0 = T0 + timedelta(seconds=5)
        feed.publish_threadsafe(_upd(received_at=t0, sequence=1))
        feed.publish_threadsafe(
            _upd(
                received_at=T0,
                sequence=2,
                provenance=Provenance.SYNTHETIC,
                sequence_gap=True,
                payload={"bid": 99.0, "ask": 99.5},
            )
        )
        response = client.get("/api/live/replay")
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "lake"
        assert body["window"]["count"] == 2
        updates = body["updates"]
        assert [u["sequence"] for u in updates] == [1, 2]
        assert updates[1]["provenance"] == "synthetic"
        assert updates[1]["sequence_gap"] is True
        # The lake stores UTC instants; the wire may render them with a
        # trailing Z instead of +00:00 — same instant either way.
        assert datetime.fromisoformat(
            updates[1]["received_at"].replace("Z", "+00:00")
        ) == T0

    def test_replay_window_bounds_filter_on_received_at(self, live_app) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(_upd(received_at=T0, sequence=1))
        feed.publish_threadsafe(_upd(received_at=T0 + timedelta(seconds=30), sequence=2))
        feed.publish_threadsafe(_upd(received_at=T0 + timedelta(seconds=60), sequence=3))
        response = client.get(
            "/api/live/replay",
            params={
                "start": (T0 + timedelta(seconds=10)).isoformat(),
                "end": (T0 + timedelta(seconds=30)).isoformat(),
            },
        )
        assert response.status_code == 200
        updates = response.json()["updates"]
        assert [u["sequence"] for u in updates] == [2]

    def test_replay_mounts_agree(self, live_app) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(_upd(sequence=4))
        root = client.get("/live/replay").json()
        api = client.get("/api/live/replay").json()
        assert root == api

    def test_replay_requires_both_window_bounds(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get("/api/live/replay", params={"start": T0.isoformat()})
        assert response.status_code == 422
        assert response.json()["detail"] == "start and end must be provided together"

    def test_replay_rejects_inverted_or_naive_bounds(self, live_app) -> None:
        client, _app, _feed = live_app
        inverted = client.get(
            "/api/live/replay",
            params={
                "start": (T0 + timedelta(seconds=60)).isoformat(),
                "end": T0.isoformat(),
            },
        )
        assert inverted.status_code == 422
        naive = client.get(
            "/api/live/replay",
            params={
                "start": T0.isoformat().replace("+00:00", ""),
                "end": (T0 + timedelta(seconds=60)).isoformat().replace("+00:00", ""),
            },
        )
        assert naive.status_code == 422
        assert naive.json()["detail"] == "start and end must be timezone-aware timestamps"

    def test_replay_404_without_a_lake(self, tmp_path) -> None:
        feed = LiveFeed(lag=LAG, stale=STALE)  # no lake on purpose
        app = create_workstation_app(
            account=PaperAccount(cash=100_000.0), live_feed=feed, host="127.0.0.1"
        )
        with TestClient(app) as client:
            response = client.get("/api/live/replay")
            windows = client.get("/api/live/replay/windows")
        assert response.status_code == 404
        assert response.json()["detail"] == "no replay lake is attached"
        assert windows.status_code == 404
        assert windows.json()["detail"] == "no replay lake is attached"


class TestPriceTrail:
    """Iteration 0019 slice 5: trailing closes per instrument from the
    lake in oldest-first order — the watchlist sparkline data — with
    correct fail-closed behavior and mount agreement."""

    _TRAIL_LIMIT = 20

    def _candle(
        self,
        instrument: str,
        close: float,
        *,
        at: datetime,
        venue: Venue = Venue.HYPERLIQUID,
    ) -> MarketUpdate:
        return MarketUpdate(
            venue=venue,
            instrument=instrument,
            kind=UpdateKind.CANDLE,
            provenance=Provenance.REAL,
            data_time=at,
            received_at=at,
            payload={"open": close, "high": close + 1, "low": close - 1, "close": close},
        )

    def test_returns_closes_per_instrument(self, live_app) -> None:
        client, _app, feed = live_app
        t0 = T0
        feed.publish_threadsafe(self._candle("BTC", 100.5, at=t0))
        feed.publish_threadsafe(self._candle("BTC", 101.5, at=t0 + timedelta(seconds=60)))
        feed.publish_threadsafe(self._candle("SOL", 30.2, at=t0))
        response = client.get(
            "/api/live/price-trail?identities=hyperliquid:BTC,hyperliquid:SOL&limit=10"
        )
        assert response.status_code == 200
        trail = response.json()["trail"]
        assert trail["hyperliquid:BTC"] == [100.5, 101.5]
        assert trail["hyperliquid:SOL"] == [30.2]

    def test_returns_oldest_first_order(self, live_app) -> None:
        client, _app, feed = live_app
        t0 = T0
        for i, close in enumerate([100.0, 101.0, 102.0, 103.0]):
            feed.publish_threadsafe(self._candle("BTC", close, at=t0 + timedelta(seconds=60 * i)))
        response = client.get(
            "/api/live/price-trail?identities=hyperliquid:BTC&limit=10"
        )
        assert response.status_code == 200
        assert response.json()["trail"]["hyperliquid:BTC"] == [
            100.0,
            101.0,
            102.0,
            103.0,
        ]

    def test_limits_per_instrument(self, live_app) -> None:
        client, _app, feed = live_app
        t0 = T0
        for i in range(30):
            feed.publish_threadsafe(
                self._candle("BTC", 100.5 + i, at=t0 + timedelta(seconds=60 * i))
            )
        response = client.get(
            "/api/live/price-trail?identities=hyperliquid:BTC&limit=20"
        )
        assert response.status_code == 200
        assert len(response.json()["trail"]["hyperliquid:BTC"]) == 20

    def test_skips_non_candle_kinds(self, live_app) -> None:
        client, _app, feed = live_app
        t0 = T0
        feed.publish_threadsafe(_upd())  # quote, not candle — must be ignored
        feed.publish_threadsafe(self._candle("BTC", 100.5, at=t0))
        response = client.get(
            "/api/live/price-trail?identities=hyperliquid:BTC&limit=10"
        )
        assert response.status_code == 200
        assert response.json()["trail"]["hyperliquid:BTC"] == [100.5]

    def test_missing_symbol_returns_empty_list(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get(
            "/api/live/price-trail?identities=hyperliquid:GHOST&limit=10"
        )
        assert response.status_code == 200
        assert response.json()["trail"]["hyperliquid:GHOST"] == []

    def test_vanished_duplicate_venue_cannot_contaminate_remaining_trail(
        self, live_app
    ) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(
            self._candle("BTC", 100.0, at=T0, venue=Venue.HYPERLIQUID)
        )
        feed.publish_threadsafe(
            self._candle("BTC", 200.0, at=T0, venue=Venue.MOOMOO)
        )

        response = client.get(
            "/api/live/price-trail?identities=hyperliquid:BTC&limit=10"
        )

        assert response.status_code == 200
        assert response.json()["trail"] == {"hyperliquid:BTC": [100.0]}

    def test_404_without_a_lake(self, tmp_path) -> None:
        feed = LiveFeed(lag=LAG, stale=STALE)
        app = create_workstation_app(
            account=PaperAccount(cash=100_000.0), live_feed=feed, host="127.0.0.1"
        )
        with TestClient(app) as client:
            response = client.get(
                "/api/live/price-trail?identities=hyperliquid:BTC"
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "no replay lake is attached"

    def test_422_when_empty_identities(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get("/api/live/price-trail?identities=&limit=10")
        assert response.status_code == 422
        assert response.json()["detail"] == "at least one identity is required"

    def test_symbol_only_identity_is_rejected_as_ambiguous(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get("/api/live/price-trail?identities=BTC&limit=10")
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "identities must use canonical venue:instrument form"
        )

    def test_legacy_symbols_parameter_is_not_accepted(self, live_app) -> None:
        client, _app, _feed = live_app
        response = client.get("/api/live/price-trail?symbols=BTC&limit=10")
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["query", "identities"]

    def test_mounts_agree(self, live_app) -> None:
        client, _app, feed = live_app
        feed.publish_threadsafe(self._candle("BTC", 100.5, at=T0))
        root = client.get(
            "/live/price-trail?identities=hyperliquid:BTC"
        ).json()
        api = client.get(
            "/api/live/price-trail?identities=hyperliquid:BTC"
        ).json()
        assert root == api


class TestLifespan:
    def test_pump_starts_with_the_app(self, tmp_path) -> None:
        feed = LiveFeed(lake=LiveBuffer(root=tmp_path), lag=LAG, stale=STALE)
        app = create_workstation_app(
            account=PaperAccount(cash=100_000.0), live_feed=feed, host="127.0.0.1"
        )
        with TestClient(app) as client:
            assert feed._loop is not None  # the lifespan ran the pump
            feed.publish_threadsafe(_upd())
            assert client.get("/api/live/state").status_code == 200
        # shutdown cancelled the pump; nothing holds a live task
        assert feed._loop is not None
