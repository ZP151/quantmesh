"""The Phase C SPA JSON surface and the demo paper-order POST.

The SPA consumes one JSON surface; every screen renders through the
exact page providers the RC1 templates use, so the browser and the
legacy screens can never disagree. Under test:

- the read surface: /api/overview, /api/markets, /api/watchlist,
  /api/experiments, /api/promotions, /api/forecasts, /api/risk,
  /api/audit, /api/enablement — each serving the seeded demo contract
  counts, and a typed 404 on a plain M1 app without a workstation
  context
- the JSON kill-switch POST: flips global and per-venue switches and
  replaces the account in app.state, refused cross-origin and for
  unknown venues
- the demo paper-order POST: fills through the seeded provider
  pipeline, records in the journal, updates cash and positions,
  refuses outside the universe / under a kill switch / cross-origin,
  and a reset restores the pristine root
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.app import create_app
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.domain.models import Venue

SCENARIO = DemoScenario()


@pytest.fixture()
def demo_client(tmp_path: Path):
    app = create_demo_app(root=tmp_path / "runtime", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        yield client, app


# ---------------------------------------------------------------------------
# The read surface
# ---------------------------------------------------------------------------


def test_read_surface_serves_the_demo_screens(demo_client) -> None:
    client, _app = demo_client

    overview = client.get("/api/overview").json()
    assert len(overview["venues"]) == 2  # moomoo + hyperliquid
    instruments = overview["venues"][0]["instruments"] + overview["venues"][1]["instruments"]
    assert len(instruments) == 10  # 6 equities + 4 perps
    assert len(overview["watchlist"]) == 4

    markets = client.get("/api/markets").json()
    assert len(markets["instruments"]) == 10

    watchlist = client.get("/api/watchlist").json()
    assert len(watchlist["entries"]) == 4

    experiments = client.get("/api/experiments").json()
    assert experiments["registry_bound"] is True
    assert len(experiments["experiments"]) == SCENARIO.surface_counts["experiments"]

    promotions = client.get("/api/promotions").json()
    assert len(promotions["promotions"]) == SCENARIO.surface_counts["promotions"]
    assert promotions["promotions"][0]["oos"]["resolved"] is True

    forecasts = client.get("/api/forecasts").json()
    assert len(forecasts["reports"]) == SCENARIO.surface_counts["forecasts"]
    assert all(report["artifacts_present"] for report in forecasts["reports"])

    risk = client.get("/api/risk").json()
    assert len(risk["alerts"]) == SCENARIO.surface_counts["alerts"]
    assert risk["paper_limits"]["kill_switch"] is False
    assert risk["alerts_bound"] is True

    audit = client.get("/api/audit").json()
    assert len(audit["entries"]) == (
        SCENARIO.surface_counts["orders"]
        + SCENARIO.surface_counts["mappings"]
        + SCENARIO.surface_counts["decisions"]
    )
    kinds = {entry["kind"] for entry in audit["entries"]}
    assert kinds == {"order", "mapping", "decision"}

    enablement = client.get("/api/enablement").json()
    assert enablement["bound"] is True
    states = {item["venue"]: item["state"] for item in enablement["states"]}
    assert states == {"moomoo": "pending", "hyperliquid": "disabled"}


def test_plain_app_has_no_json_surface() -> None:
    app = create_app(account=None)  # type: ignore[arg-type]
    with TestClient(app) as client:
        for route in ("/api/markets", "/api/risk", "/api/audit", "/api/enablement"):
            assert client.get(route).status_code == 404, route


# ---------------------------------------------------------------------------
# The JSON kill-switch POST
# ---------------------------------------------------------------------------


def test_kill_switch_json_flips_global_and_per_venue(demo_client) -> None:
    client, app = demo_client
    flipped = client.post("/api/kill-switch", json={"action": "engage"})
    assert flipped.status_code == 200
    assert flipped.json()["kill_switch"] is True
    assert app.state.account.kill_switch is True
    assert client.get("/api/risk").json()["paper_limits"]["kill_switch"] is True

    disarmed = client.post("/api/kill-switch", json={"action": "disarm"})
    assert disarmed.status_code == 200
    assert disarmed.json()["kill_switch"] is False
    assert app.state.account.kill_switch is False

    venue_engaged = client.post("/api/kill-switch", json={"action": "engage", "venue": "moomoo"})
    assert venue_engaged.status_code == 200
    assert venue_engaged.json()["kill_switches"]["moomoo"] is True
    assert app.state.account.kill_switches[Venue.MOOMOO] is True
    # The global bit and other venues are untouched.
    assert venue_engaged.json()["kill_switch"] is False

    venue_disarmed = client.post("/api/kill-switch", json={"action": "disarm", "venue": "moomoo"})
    assert venue_disarmed.json()["kill_switches"]["moomoo"] is False


def test_kill_switch_json_refusals(demo_client) -> None:
    client, _app = demo_client
    cross_origin = client.post(
        "/api/kill-switch", json={"action": "engage"}, headers={"Origin": "https://evil.example"}
    )
    assert cross_origin.status_code == 403
    assert client.post("/api/kill-switch", json={"action": "engage", "venue": "not-a-venue"}).status_code == 422


# ---------------------------------------------------------------------------
# The demo paper-order POST (the tracer-bullet submit)
# ---------------------------------------------------------------------------


def test_demo_order_fills_through_the_seeded_pipeline(demo_client) -> None:
    client, app = demo_client
    cash_before = client.get("/api/account").json()["cash"]
    positions_before = client.get("/api/positions").json()

    response = client.post(
        "/api/demo/order", json={"venue": "hyperliquid", "symbol": "SOL-USD", "side": "BUY", "quantity": 10}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "filled"
    assert payload["order"]["side"] == "buy"
    assert payload["account"]["cash"] < cash_before

    # The fresh account replaced app.state: every surface agrees.
    assert app.state.account.cash == payload["account"]["cash"]
    assert len(client.get("/api/positions").json()) == len(positions_before) + 1
    # The order is recorded in the seeded journal (a real append).
    counts = SCENARIO.surface_counts
    audit = client.get("/api/audit").json()
    assert len(audit["entries"]) == counts["orders"] + counts["mappings"] + counts["decisions"] + 1
    assert any(
        entry["kind"] == "order" and entry["order"]["order_id"] == payload["order"]["order_id"]
        for entry in audit["entries"]
    )


def test_demo_order_resting_limit_accepts_without_fill(demo_client) -> None:
    client, _app = demo_client
    positions_before = len(client.get("/api/positions").json())
    response = client.post(
        "/api/demo/order",
        json={"venue": "moomoo", "symbol": "MSFT", "side": "BUY", "quantity": 1, "limit_price": 0.5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "accepted"
    assert payload["order"]["filled_quantity"] == 0
    assert len(client.get("/api/positions").json()) == positions_before


def test_demo_order_idempotency_key_replays(demo_client) -> None:
    client, _app = demo_client
    first = client.post(
        "/api/demo/order",
        json={
            "venue": "moomoo",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 2,
            "idempotency_key": "tracer-bullet-1",
        },
    )
    assert first.status_code == 200
    replay = client.post(
        "/api/demo/order",
        json={
            "venue": "moomoo",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 2,
            "idempotency_key": "tracer-bullet-1",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["order"]["order_id"] == first.json()["order"]["order_id"]
    # No duplicate was recorded.
    assert len(client.get("/api/orders").json()) == 9


def test_demo_order_refusals(demo_client) -> None:
    client, _app = demo_client
    outside = client.post(
        "/api/demo/order", json={"venue": "moomoo", "symbol": "DOES-NOT-EXIST", "side": "BUY", "quantity": 1}
    )
    assert outside.status_code == 404
    cross_origin = client.post(
        "/api/demo/order",
        json={"venue": "moomoo", "symbol": "AAPL", "side": "BUY", "quantity": 1},
        headers={"Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 403
    bad_body = client.post(
        "/api/demo/order", json={"venue": "moomoo", "symbol": "AAPL", "side": "BUY", "quantity": -3}
    )
    assert bad_body.status_code == 422


def test_demo_order_refused_under_a_kill_switch(demo_client) -> None:
    client, _app = demo_client
    client.post("/api/kill-switch", json={"action": "engage"})
    response = client.post(
        "/api/demo/order", json={"venue": "moomoo", "symbol": "AAPL", "side": "BUY", "quantity": 1}
    )
    assert response.status_code == 409
    assert "kill switch" in response.json()["detail"]


def test_reset_restores_the_pristine_root_after_orders(demo_client) -> None:
    client, _app = demo_client
    seeded_cash = client.get("/api/account").json()["cash"]
    client.post(
        "/api/demo/order", json={"venue": "hyperliquid", "symbol": "SOL-USD", "side": "BUY", "quantity": 10}
    )
    client.post(
        "/api/demo/order", json={"venue": "moomoo", "symbol": "AAPL", "side": "BUY", "quantity": 2}
    )
    assert client.get("/api/account").json()["cash"] != seeded_cash

    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200
    assert client.get("/api/account").json()["cash"] == seeded_cash
    assert len(client.get("/api/orders").json()) == 8
    assert len(client.get("/api/positions").json()) == 5


def test_no_demo_order_on_a_plain_app() -> None:
    app = create_app(account=None)  # type: ignore[arg-type]
    with TestClient(app) as client:
        response = client.post(
            "/api/demo/order", json={"venue": "moomoo", "symbol": "AAPL", "side": "BUY", "quantity": 1}
        )
        assert response.status_code == 404
