"""Venue-exact, fail-closed marks for live paper-account valuation."""

from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from quantmesh.api import workstation
from quantmesh.api.workstation import create_workstation_app
from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Quote, Side, Venue
from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.marks import live_mark_snapshot

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)


def _account_with_btc() -> PaperAccount:
    account = PaperAccount(cash=100_000.0)
    quote = Quote(
        instrument=BTC,
        timestamp=NOW,
        bid=100.0,
        ask=101.0,
        volume=10.0,
    )
    return account.submit(
        OrderRequest(instrument=BTC, side=Side.BUY, quantity=1.0),
        quote,
        now=NOW,
    ).account


def _quote(sequence: int, *, received_at: datetime, bid: float, ask: float) -> MarketUpdate:
    return MarketUpdate(
        venue=Venue.HYPERLIQUID,
        instrument="BTC",
        kind=UpdateKind.QUOTE,
        provenance=Provenance.REAL,
        data_time=received_at,
        received_at=received_at,
        sequence=sequence,
        payload={"bid": bid, "ask": ask, "bid_size": 2.0, "ask_size": 3.0},
    )


def test_healthy_exact_live_quote_marks_account_equity() -> None:
    account = _account_with_btc()
    feed = LiveFeed()
    feed.ingest(
        [
            _quote(1, received_at=NOW, bid=100.0, ask=101.0),
            _quote(2, received_at=NOW + timedelta(seconds=1), bid=102.0, ask=103.0),
        ]
    )

    snapshot = live_mark_snapshot(
        account,
        base_marks={},
        feed=feed,
        as_of=NOW + timedelta(seconds=2),
    )

    key = position_key(BTC)
    assert snapshot.marks[key] == 102.5
    assert snapshot.statuses[key]["status"] == "available"
    assert snapshot.statuses[key]["provenance"] == "real"
    assert account.equity(snapshot.marks) == pytest.approx(account.cash + 102.5)


def test_stale_or_unproven_live_quote_removes_static_mark_and_names_reason() -> None:
    account = _account_with_btc()
    key = position_key(BTC)
    feed = LiveFeed()
    feed.ingest([_quote(1, received_at=NOW, bid=100.0, ask=101.0)])

    unproven = live_mark_snapshot(account, base_marks={key: 999.0}, feed=feed, as_of=NOW)
    assert key not in unproven.marks
    assert unproven.statuses[key]["status"] == "unavailable"
    assert "continuity is unproven" in str(unproven.statuses[key]["reason"])

    feed.ingest([_quote(2, received_at=NOW + timedelta(seconds=1), bid=101.0, ask=102.0)])
    stale = live_mark_snapshot(
        account,
        base_marks={key: 999.0},
        feed=feed,
        as_of=NOW + timedelta(seconds=32),
    )
    assert key not in stale.marks
    assert stale.statuses[key]["status"] == "stale"
    assert "old" in str(stale.statuses[key]["reason"])


def test_live_workstation_pnl_uses_the_same_exact_quote_mark() -> None:
    account = _account_with_btc()
    feed = LiveFeed()
    feed.ingest(
        [
            _quote(1, received_at=NOW, bid=100.0, ask=101.0),
            _quote(2, received_at=NOW + timedelta(seconds=1), bid=102.0, ask=103.0),
        ]
    )
    app = create_workstation_app(
        account=account,
        live_feed=feed,
        workspace_clock=lambda: NOW + timedelta(seconds=2),
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        payload = client.get("/api/pnl").json()

    key = position_key(BTC)
    assert payload["marks"][key] == 102.5
    assert payload["equity"] == pytest.approx(account.cash + 102.5)
    assert payload["missing_marks"] == []
    assert payload["mark_statuses"][key]["status"] == "available"


def test_missing_live_mark_makes_equity_and_total_pnl_explicitly_incomplete() -> None:
    account = _account_with_btc()
    key = position_key(BTC)
    feed = LiveFeed()
    feed.ingest([_quote(1, received_at=NOW, bid=100.0, ask=101.0)])
    app = create_workstation_app(
        account=account,
        marks={key: 999.0},
        live_feed=feed,
        workspace_clock=lambda: NOW,
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        pnl = client.get("/api/pnl").json()
        positions = client.get("/api/positions").json()

    assert pnl["valuation_complete"] is False
    assert pnl["valuation_reason"] == f"missing valid marks for held positions: {key}"
    assert pnl["equity"] is None
    assert pnl["total_pnl"] is None
    assert pnl["unrealized_pnl"] is None
    assert pnl["missing_marks"] == [key]
    assert positions[0]["mark_status"]["status"] == "unavailable"
    assert "continuity is unproven" in positions[0]["mark_status"]["reason"]


def test_account_revision_and_marks_are_returned_as_one_immutable_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = _account_with_btc()
    feed = LiveFeed()
    feed.ingest(
        [
            _quote(1, received_at=NOW, bid=100.0, ask=101.0),
            _quote(2, received_at=NOW + timedelta(seconds=1), bid=102.0, ask=103.0),
        ]
    )
    entered = Event()
    release = Event()
    original = workstation.live_mark_snapshot

    def paused_snapshot(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(workstation, "live_mark_snapshot", paused_snapshot)
    app = create_workstation_app(
        account=account,
        live_feed=feed,
        workspace_clock=lambda: NOW + timedelta(seconds=2),
        host="127.0.0.1",
    )
    result: list[list[dict[str, object]]] = []
    with TestClient(app) as client:
        request = Thread(
            target=lambda: result.append(client.get("/api/positions").json()),
            daemon=True,
        )
        request.start()
        assert entered.wait(timeout=10)
        app.state.account_store.replace(account.model_copy(update={"positions": {}}))
        release.set()
        request.join(timeout=10)

    assert len(result) == 1
    assert [row["key"] for row in result[0]] == [position_key(BTC)]
    assert result[0][0]["mark_status"]["status"] == "available"
