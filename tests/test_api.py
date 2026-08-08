"""Paper account API observability (issue #6)."""

from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from quantmesh.api.app import create_app
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.execution.accounting import FeeModel, PaperAccount, RiskLimits
from quantmesh.execution.matcher import PaperMatcher

INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
POSITION_KEY = "internal:AAPL"
NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
MARKS = {POSITION_KEY: 95.0}


def make_request(side: Side, quantity: float, limit_price: float | None = None) -> OrderRequest:
    return OrderRequest(
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
    )


def make_quote(*, bid: float = 99.0, ask: float = 100.0) -> Quote:
    return Quote(instrument=INSTRUMENT, timestamp=NOW, bid=bid, ask=ask, volume=100)


def sample_account() -> PaperAccount:
    """Buy 10 @ 100, sell 4 @ 110, leave a non-crossed limit buy working."""
    account = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    account = account.submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account
    account = account.submit(
        make_request(Side.SELL, 4), make_quote(bid=110.0, ask=111.0), now=NOW
    ).account
    account = account.submit(
        make_request(Side.BUY, 10, limit_price=99.0), make_quote(), now=NOW
    ).account
    return account


def client(account: PaperAccount | None = None) -> TestClient:
    return TestClient(create_app(account=account or sample_account(), marks=dict(MARKS)))


def test_account_summary_matches_account_state() -> None:
    account = sample_account()
    response = client(account).get("/account")

    assert response.status_code == 200
    body = response.json()
    assert body["cash"] == account.cash
    assert body["starting_cash"] == account.starting_cash
    assert body["total_fees"] == account.total_fees
    assert body["kill_switch"] is account.kill_switch
    assert body["order_sequence"] == account.order_sequence


def test_positions_include_unrealized_pnl() -> None:
    response = client().get("/positions")

    assert response.status_code == 200
    positions = response.json()
    assert len(positions) == 1
    position = positions[0]
    assert position["key"] == POSITION_KEY
    assert position["quantity"] == 6
    assert position["average_cost"] == 100.0
    assert position["unrealized_pnl"] == pytest.approx(-30.0)


def test_orders_list_orders_with_event_histories() -> None:
    response = client().get("/orders")

    assert response.status_code == 200
    orders = response.json()
    assert [order["order_id"] for order in orders] == ["paper-1", "paper-2", "paper-3"]
    filled = orders[0]
    assert filled["status"] == "filled"
    assert filled["filled_quantity"] == 10
    assert filled["average_fill_price"] == 100.0
    assert [event["event_type"] for event in filled["events"]] == ["accepted", "fill"]


def test_order_by_id_returns_the_order() -> None:
    response = client().get("/orders/paper-2")

    assert response.status_code == 200
    assert response.json()["order_id"] == "paper-2"
    assert response.json()["side"] == "sell"


def test_unknown_order_is_404() -> None:
    response = client().get("/orders/nope")

    assert response.status_code == 404


def test_pnl_reflects_marks_and_account_state() -> None:
    response = client().get("/pnl")

    assert response.status_code == 200
    body = response.json()
    assert body["starting_cash"] == 10_000.0
    assert body["realized_pnl"] == pytest.approx(39.56)
    assert body["unrealized_pnl"] == pytest.approx(-30.0)
    assert body["equity"] == pytest.approx(10_008.56)
    assert body["total_pnl"] == pytest.approx(8.56)
    assert body["marks"] == MARKS
    assert body["missing_marks"] == []


def test_kill_switch_status_is_observable() -> None:
    account = sample_account().model_copy(update={"kill_switch": True})

    response = client(account).get("/kill-switch")

    assert response.status_code == 200
    assert response.json() == {"kill_switch": True, "kill_switches": {}}


def test_pnl_names_positions_without_marks() -> None:
    hold_only = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    ).submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account
    test_client = TestClient(create_app(account=hold_only, marks={}))

    body = test_client.get("/pnl").json()

    # Equity-based numbers exclude the unmarked position, but never
    # silently: the missing mark is named.
    assert body["missing_marks"] == [POSITION_KEY]
    assert body["equity"] == pytest.approx(hold_only.cash)


def test_position_without_a_mark_reports_null_unrealized() -> None:
    hold_only = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    ).submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account
    test_client = TestClient(create_app(account=hold_only, marks={}))

    position = test_client.get("/positions").json()[0]

    assert position["unrealized_pnl"] is None


def test_rejected_order_serializes_reason_and_null_fill_fields() -> None:
    limited = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
        risk_limits=RiskLimits(max_order_quantity=10),
    )
    account = limited.submit(make_request(Side.BUY, 15), make_quote(), now=NOW).account
    test_client = TestClient(create_app(account=account))

    order = test_client.get("/orders/paper-1").json()

    assert order["status"] == "rejected"
    event = order["events"][0]
    assert event["event_type"] == "rejected"
    assert "exceeds limit" in event["reason"]
    assert event["quantity"] is None
    assert event["price"] is None


def test_order_placement_is_not_exposed() -> None:
    response = client().post("/orders")

    assert response.status_code == 405


def test_marks_update_is_reflected() -> None:
    hold_only = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    ).submit(make_request(Side.BUY, 10), make_quote(), now=NOW).account
    app = create_app(account=hold_only, marks={})
    test_client = TestClient(app)

    app.state.marks[POSITION_KEY] = 100.0
    response = test_client.get("/pnl")

    # Buy-and-hold at entry price: only the entry fee is visible.
    assert response.json()["total_pnl"] == pytest.approx(-1.0)


def _api_routes(app) -> list[APIRoute]:
    """Every APIRoute on the app, including those under included
    routers (FastAPI >= 0.14x registers an include as a lazy
    `_IncludedRouter` entry instead of flattening the routes; the
    inner routes live on its `original_router`)."""
    flattened = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            flattened.append(route)
        elif hasattr(route, "original_router"):
            flattened.extend(
                item
                for item in route.original_router.routes
                if isinstance(item, APIRoute)
            )
    return flattened


def test_api_is_read_only() -> None:
    app = create_app(account=sample_account())
    methods = {
        method
        for route in _api_routes(app)
        for method in route.methods
    }

    assert methods == {"GET"}


def test_factory_app_serves_health() -> None:
    response = client().get("/health")

    assert response.status_code == 200
    assert response.json()["paper_mode"] is True
