from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.execution.accounting import PaperAccount, RiskLimits, position_key
from quantmesh.execution.journal import OrderJournal
from quantmesh.instruments.contracts import (
    ComparisonPoint,
    ComparisonSeries,
    CoverageSnapshot,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    PriceForecastArtifact,
)
from quantmesh.instruments.forecast import run_price_forecast
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.instruments.proposals import PaperDecisionService, ProposalLedger
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.fence import QuoteFence

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
NVDA = Instrument(
    venue=Venue.MOOMOO,
    symbol="NVDA",
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)


def _session_dates(count: int, *, end: datetime = NOW) -> tuple[datetime, ...]:
    dates: list[datetime] = []
    candidate = end
    while len(dates) < count:
        if candidate.weekday() < 5:
            dates.append(candidate)
        candidate -= timedelta(days=1)
    return tuple(reversed(dates))


def _series(
    venue: Venue,
    symbol: str,
    selected_range: HistoryRange,
    as_of: datetime,
) -> HistoricalSeries:
    instrument = Instrument(
        venue=venue,
        symbol=symbol,
        instrument_type=(
            InstrumentType.PERPETUAL if venue is Venue.HYPERLIQUID else InstrumentType.EQUITY
        ),
        currency="USD",
    )
    dates = (as_of - timedelta(days=2), as_of - timedelta(days=1))
    bars = tuple(
        HistoricalBar(
            instrument=instrument,
            timestamp=timestamp,
            interval="1d",
            open=100.0 + index,
            high=102.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=1_000_000.0 + index,
        )
        for index, timestamp in enumerate(dates)
    )
    return HistoricalSeries(
        instrument=instrument,
        range=selected_range,
        as_of=as_of,
        bars=bars,
        dataset_id="workspace-history",
        dataset_revision=4,
        source="operator-import",
        license="operator-supplied",
        generated_at=dates[-1],
        interval="1d",
        calendar="24/7" if venue is Venue.HYPERLIQUID else "XNYS",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval="1d",
            venue=venue,
            symbol=symbol,
            start=dates[0],
            end=dates[-1],
            rows=2,
        ),
        limitations=("fixture history is intentionally short",),
    )


class RecordingHistoryService(HistoryService):
    """Read-only seam; manifest validation is covered by Task 5 tests."""

    def __init__(self) -> None:
        self.history_as_of: list[datetime] = []
        self.compare_as_of: list[datetime] = []

    def history(
        self,
        venue: Venue,
        symbol: str,
        range: HistoryRange,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalSeries:
        assert as_of is not None
        self.history_as_of.append(as_of)
        if symbol == "MISSING":
            raise HistoryUnavailableError(f"unknown venue/symbol {venue.value}:{symbol}")
        return _series(venue, symbol, range, as_of)

    def compare(
        self,
        *,
        primary: tuple[Venue, str],
        peers: list[tuple[Venue, str]] | tuple[tuple[Venue, str], ...],
        range: HistoryRange,
        as_of: datetime | None = None,
    ) -> ComparisonSeries:
        assert as_of is not None
        self.compare_as_of.append(as_of)
        keys = tuple(f"{venue.value}:{symbol}" for venue, symbol in (primary, *peers))
        return ComparisonSeries(
            range=range,
            as_of=as_of,
            keys=keys,
            points=(
                ComparisonPoint(
                    timestamp=as_of - timedelta(days=2),
                    values={key: 99.0 for key in keys},
                ),
                ComparisonPoint(
                    timestamp=as_of - timedelta(days=1),
                    values={key: 100.0 for key in keys},
                ),
            ),
            limitations=("comparison uses common observed timestamps",),
        )


class ForecastCatalog:
    """A complete read-only registry seam; persistence is tested in Task 7."""

    def __init__(self, artifacts: tuple[PriceForecastArtifact, ...]) -> None:
        self._artifacts = artifacts

    def all(self) -> list[PriceForecastArtifact]:
        return list(self._artifacts)

    def get(self, artifact_id: str) -> PriceForecastArtifact:
        for artifact in self._artifacts:
            if artifact.id == artifact_id:
                return artifact
        raise ValueError(f"no forecast artifact recorded with id {artifact_id!r}")


@lru_cache(maxsize=2)
def _artifact(*, eligible: bool = True) -> PriceForecastArtifact:
    dates = _session_dates(650 if eligible else 420)
    bars = tuple(
        HistoricalBar(
            instrument=NVDA,
            timestamp=timestamp,
            interval="1d",
            open=price * 0.999,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=1_000_000.0,
        )
        for index, timestamp in enumerate(dates)
        for price in [100.0 * math.exp(0.0006 * index + 0.01 * math.sin(index / 7))]
    )
    series = HistoricalSeries(
        instrument=NVDA,
        range=HistoryRange.ONE_YEAR,
        as_of=dates[-1],
        bars=bars,
        dataset_id="workspace-forecast",
        dataset_revision=2,
        source="operator-import",
        license="operator-supplied",
        generated_at=dates[-1],
        interval="1d",
        calendar="XNYS",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval="1d",
            venue=Venue.MOOMOO,
            symbol="NVDA",
            start=dates[0],
            end=dates[-1],
            rows=len(dates),
        ),
    )
    result = run_price_forecast(
        series,
        generated_at=series.as_of,
        model_version="drift-conformal-v1",
    )
    assert result.eligible is eligible
    return result


def _quote_feed(
    *,
    gap: bool = False,
    stale: bool = False,
    future: bool = False,
    missing_depth: bool = False,
) -> LiveFeed:
    feed = LiveFeed()
    received_at = (
        NOW + timedelta(days=1) if future else NOW - timedelta(minutes=2) if stale else NOW
    )
    payload = {
        "bid": 104.9,
        "ask": 105.1,
        "last": 105.0,
        "bid_size": 500.0,
        "ask_size": 600.0,
    }
    if missing_depth:
        payload.pop("bid_size")
        payload.pop("ask_size")
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="NVDA",
                kind=UpdateKind.QUOTE,
                provenance=Provenance.REAL,
                data_time=received_at,
                received_at=received_at,
                sequence=8,
                sequence_gap=gap,
                payload=payload,
            )
        ]
    )
    return feed


def _account_with_position() -> PaperAccount:
    limits = RiskLimits(
        max_order_quantity=25.0,
        max_notional=5_000.0,
        max_position_quantity=50.0,
    )
    account = PaperAccount(cash=100_000.0, risk_limits=limits)
    filled = account.submit(
        OrderRequest(
            instrument=NVDA,
            side=Side.BUY,
            quantity=2.0,
            paper=True,
            idempotency_key="workspace-seed",
        ),
        Quote(
            instrument=NVDA,
            timestamp=NOW - timedelta(days=1),
            bid=99.9,
            ask=100.0,
            last=100.0,
            volume=1_000.0,
        ),
        now=NOW - timedelta(days=1),
    ).account
    return filled.model_copy(update={"kill_switches": {Venue.MOOMOO: True}})


@dataclass
class ApiHarness:
    app: FastAPI
    history: RecordingHistoryService
    catalog: ForecastCatalog
    proposals: PaperDecisionService
    state: dict[str, PaperAccount]
    sink_calls: list[PaperAccount]
    journal: OrderJournal


def _harness(
    tmp_path: Path,
    *,
    artifacts: tuple[PriceForecastArtifact, ...] | None = None,
    account: PaperAccount | None = None,
    live: LiveFeed | None = None,
) -> ApiHarness:
    selected = artifacts if artifacts is not None else (_artifact(),)
    history = RecordingHistoryService()
    catalog = ForecastCatalog(selected)
    state = {"account": account if account is not None else PaperAccount(cash=100_000.0)}
    sink_calls: list[PaperAccount] = []
    journal = OrderJournal(tmp_path / "orders")

    def sink(value: PaperAccount) -> None:
        sink_calls.append(value)
        state["account"] = value

    proposals = PaperDecisionService(
        ledger=ProposalLedger(tmp_path / "proposals"),
        forecast_registry=catalog,
        account_provider=lambda: state["account"],
        account_sink=sink,
        journal=journal,
        snapshot_provider=lambda: {
            "instruments": {
                "NVDA": {
                    "kinds": {
                        "quote": {
                            "kind": "quote",
                            "provenance": "real",
                            "received_at": NOW.isoformat(),
                            "sequence_gap": False,
                            "payload": {
                                "bid": 104.9,
                                "ask": 105.1,
                                "bid_size": 500.0,
                                "ask_size": 600.0,
                            },
                        }
                    }
                }
            }
        },
        quote_fence=QuoteFence(),
        now=lambda: NOW,
    )
    marks = {position_key(NVDA): 105.0}
    app = create_workstation_app(
        account=state["account"],
        marks=marks,
        history=history,
        host="127.0.0.1",
    )
    # Task 9's router reads these owned services. Attaching a feed after app
    # creation avoids starting connector supervisors in focused HTTP tests.
    app.state.price_forecasts = catalog
    app.state.proposal_service = proposals
    app.state.instrument_clock = lambda: NOW
    if live is not None:
        app.state.live = live
    return ApiHarness(app, history, catalog, proposals, state, sink_calls, journal)


def _create_payload(artifact: PriceForecastArtifact | None = None) -> dict[str, object]:
    selected = artifact if artifact is not None else _artifact()
    return {
        "venue": "moomoo",
        "symbol": "NVDA",
        "artifact_id": selected.id,
        "side": "buy",
        "quantity": 1.0,
        "limit_price": None,
    }


def test_workspace_uses_one_clock_for_history_comparison_and_response(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        account=_account_with_position(),
        live=_quote_feed(),
    )

    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m&compare=moomoo:AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["generated_at"] == body["history"]["as_of"]
    assert body["generated_at"] == body["comparison"]["as_of"]
    assert harness.history.history_as_of == harness.history.compare_as_of
    assert harness.history.history_as_of == [datetime.fromisoformat(body["generated_at"])]
    assert body["history"]["instrument"]["venue"] == "moomoo"
    assert body["history"]["instrument"]["symbol"] == "NVDA"
    assert body["comparison"]["keys"] == ["moomoo:NVDA", "moomoo:AAPL"]


@pytest.mark.parametrize(
    ("feed", "expected_status", "reason_fragment"),
    [
        (None, "unavailable", "live"),
        (_quote_feed(gap=True), "degraded", "gap"),
        (_quote_feed(stale=True), "degraded", "stale"),
        (_quote_feed(future=True), "degraded", "future"),
        (_quote_feed(missing_depth=True), "degraded", "depth"),
    ],
)
def test_workspace_keeps_typed_live_absence_and_degradation(
    tmp_path: Path,
    feed: LiveFeed | None,
    expected_status: str,
    reason_fragment: str,
) -> None:
    harness = _harness(tmp_path, live=feed)

    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")

    assert response.status_code == 200
    live = response.json()["live"]
    assert live["status"] == expected_status
    assert reason_fragment in live["reason"].lower()


def test_workspace_exposes_real_live_lineage_without_relabeling_it(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path, live=_quote_feed())

    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")

    assert response.status_code == 200
    live = response.json()["live"]
    assert live == {
        "status": "available",
        "reason": None,
        "source": "moomoo",
        "provenance": "real",
        "label": "real",
        "data_time": NOW.isoformat().replace("+00:00", "Z"),
        "received_at": NOW.isoformat().replace("+00:00", "Z"),
        "age_ms": 0,
        "sequence": 8,
        "sequence_gap": False,
        "bid": 104.9,
        "ask": 105.1,
        "last": 105.0,
    }


@pytest.mark.parametrize("eligible", [True, False])
def test_workspace_summarizes_the_latest_forecast_even_when_ineligible(
    tmp_path: Path,
    eligible: bool,
) -> None:
    artifact = _artifact(eligible=eligible)
    harness = _harness(tmp_path, artifacts=(artifact,))

    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")

    assert response.status_code == 200
    forecast = response.json()["forecast"]
    assert forecast["artifact_id"] == artifact.id
    assert forecast["eligible"] is eligible
    assert forecast["blockers"] == list(artifact.blockers)
    assert [path["sessions"] for path in forecast["paths"]] == [7, 30, 126]
    assert {metric["sessions"] for metric in forecast["metrics"]} == {7, 30, 126}


def test_workspace_never_selects_a_forecast_from_after_its_clock(tmp_path: Path) -> None:
    current = _artifact()
    future = current.model_copy(update={"generated_at": NOW + timedelta(days=1)})
    harness = _harness(tmp_path, artifacts=(current, future))

    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")

    assert response.status_code == 200
    assert response.json()["forecast"]["generated_at"] == current.generated_at.isoformat().replace(
        "+00:00", "Z"
    )


def test_workspace_exposes_position_marks_pnl_risk_switches_and_capability(
    tmp_path: Path,
) -> None:
    account = _account_with_position()
    harness = _harness(tmp_path, account=account, live=_quote_feed())

    with TestClient(harness.app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")

    assert response.status_code == 200
    body = response.json()
    held = account.positions["moomoo:NVDA"]
    assert body["position"] == {
        "quantity": 2.0,
        "average_cost": held.average_cost,
        "realized_pnl": held.realized_pnl,
        "mark": 105.0,
        "unrealized_pnl": (105.0 - held.average_cost) * 2.0,
    }
    assert body["risk"] == {
        "cash": account.cash,
        "equity": account.equity({"moomoo:NVDA": 105.0}),
        "starting_cash": 100_000.0,
        "max_order_quantity": 25.0,
        "max_notional": 5_000.0,
        "max_position_quantity": 50.0,
        "global_kill_switch": False,
        "venue_kill_switch": True,
        "mark_available": True,
    }
    assert body["proposal"]["allowed"] is False
    assert any("kill switch" in blocker for blocker in body["proposal"]["blockers"])


def test_create_proposal_is_preview_only(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    before = harness.state["account"].model_dump()

    with TestClient(harness.app) as client:
        response = client.post("/api/paper/proposals", json=_create_payload())

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["status"] == "pending"
    assert proposal["artifact_id"] == _artifact().id
    assert proposal["instrument"]["venue"] == "moomoo"
    assert proposal["instrument"]["symbol"] == "NVDA"
    assert harness.state["account"].model_dump() == before
    assert harness.sink_calls == []
    assert harness.journal.all() == []
    assert len(harness.proposals.ledger.events(proposal["id"])) == 1


def test_confirm_places_exactly_one_order_and_terminal_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)

    with TestClient(harness.app) as client:
        preview = client.post("/api/paper/proposals", json=_create_payload())
        assert preview.status_code == 200
        proposal = preview.json()
        confirm_path = f"/api/paper/proposals/{proposal['id']}/confirm"
        first = client.post(
            confirm_path,
            json={"confirmation_token": proposal["confirmation_token"]},
        )
        replay = client.post(
            confirm_path,
            json={"confirmation_token": proposal["confirmation_token"]},
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert first.json()["proposal"]["status"] == "confirmed"
    assert len(harness.journal.all()) == 1
    assert len(harness.state["account"].orders) == 1
    assert harness.state["account"].order_sequence == 1
    assert harness.state["account"].positions["moomoo:NVDA"].quantity == 1.0
    assert len(harness.sink_calls) == 1
    assert len(harness.proposals.ledger.events(proposal["id"])) == 2


@pytest.mark.parametrize("field", ["account", "eligible", "risk_result"])
def test_browser_cannot_supply_server_owned_decision_fields(
    tmp_path: Path,
    field: str,
) -> None:
    harness = _harness(tmp_path)
    payload = {**_create_payload(), field: {"approved": True}}

    with TestClient(harness.app) as client:
        response = client.post("/api/paper/proposals", json=payload)

    assert response.status_code == 422
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])
    assert harness.proposals.ledger.all() == ()
    assert harness.journal.all() == []


def test_non_finite_proposal_numbers_are_request_validation_errors(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    payload = _create_payload()
    body = json.dumps(payload).replace('"quantity": 1.0', '"quantity": 1e309')

    with TestClient(harness.app) as client:
        response = client.post(
            "/api/paper/proposals",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert harness.proposals.ledger.all() == ()


def test_proposal_posts_reject_cross_origin_browsers(tmp_path: Path) -> None:
    harness = _harness(tmp_path)

    with TestClient(harness.app) as client:
        create = client.post(
            "/api/paper/proposals",
            json=_create_payload(),
            headers={"Origin": "https://attacker.invalid"},
        )
        local = client.post("/api/paper/proposals", json=_create_payload())
        assert local.status_code == 200
        proposal = local.json()
        confirm = client.post(
            f"/api/paper/proposals/{proposal['id']}/confirm",
            json={"confirmation_token": proposal["confirmation_token"]},
            headers={"Origin": "https://attacker.invalid"},
        )

    assert create.status_code == 403
    assert "cross-origin" in create.json()["detail"]
    assert confirm.status_code == 403
    assert "cross-origin" in confirm.json()["detail"]
    assert harness.journal.all() == []


def test_unknown_workspace_artifact_and_proposal_are_404(tmp_path: Path) -> None:
    harness = _harness(tmp_path)

    with TestClient(harness.app) as client:
        workspace = client.get("/api/instruments/moomoo/MISSING/workspace?range=6m")
        artifact = client.post(
            "/api/paper/proposals",
            json={**_create_payload(), "artifact_id": "forecast-" + "0" * 24},
        )
        proposal = client.post(
            "/api/paper/proposals/proposal-000000000000000000000000/confirm",
            json={"confirmation_token": "0" * 64},
        )

    assert workspace.status_code == 404
    assert "MISSING" in workspace.json()["detail"]
    assert artifact.status_code == 404
    assert "forecast" in artifact.json()["detail"]
    assert proposal.status_code == 404
    assert "proposal" in proposal.json()["detail"]


def test_ineligible_and_refused_confirmations_return_typed_409(tmp_path: Path) -> None:
    artifact = _artifact(eligible=False)
    harness = _harness(tmp_path, artifacts=(artifact,))

    with TestClient(harness.app) as client:
        blocked_response = client.post(
            "/api/paper/proposals",
            json=_create_payload(artifact),
        )
        assert blocked_response.status_code == 200
        blocked = blocked_response.json()
        blocked_confirm = client.post(
            f"/api/paper/proposals/{blocked['id']}/confirm",
            json={"confirmation_token": blocked["confirmation_token"]},
        )

    assert blocked_confirm.status_code == 409
    blocked_evidence = blocked_confirm.json()
    assert blocked_evidence["proposal"]["status"] == "blocked"
    assert blocked_evidence["proposal"]["blockers"] == list(artifact.blockers)
    assert blocked_evidence["order"] is None
    assert blocked_evidence["blocker"]
    assert harness.journal.all() == []

    eligible = _harness(tmp_path / "refused")
    with TestClient(eligible.app) as client:
        pending_response = client.post("/api/paper/proposals", json=_create_payload())
        assert pending_response.status_code == 200
        pending = pending_response.json()
        refused = client.post(
            f"/api/paper/proposals/{pending['id']}/confirm",
            json={"confirmation_token": "wrong-token"},
        )

    assert refused.status_code == 409
    refused_evidence = refused.json()
    assert refused_evidence["proposal"]["status"] == "pending"
    assert refused_evidence["order"] is None
    assert "token" in refused_evidence["blocker"]
    assert eligible.journal.all() == []


def test_kernel_refusal_returns_409_with_order_and_reason(tmp_path: Path) -> None:
    harness = _harness(tmp_path, account=PaperAccount(cash=100_000.0, kill_switch=True))

    with TestClient(harness.app) as client:
        pending_response = client.post("/api/paper/proposals", json=_create_payload())
        assert pending_response.status_code == 200
        pending = pending_response.json()
        refused = client.post(
            f"/api/paper/proposals/{pending['id']}/confirm",
            json={"confirmation_token": pending["confirmation_token"]},
        )

    assert refused.status_code == 409
    evidence = refused.json()
    assert evidence["proposal"]["status"] == "rejected"
    assert evidence["order"]["status"] == "rejected"
    assert evidence["blocker"] == "kill switch enabled"
    assert len(harness.journal.all()) == 1
    assert len(harness.state["account"].orders) == 1


def test_missing_workspace_and_proposal_services_are_typed_404() -> None:
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        host="127.0.0.1",
    )

    with TestClient(app) as client:
        workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
        proposal = client.post("/api/paper/proposals", json=_create_payload())

    assert workspace.status_code == 404
    assert "service" in workspace.json()["detail"]
    assert proposal.status_code == 404
    assert "service" in proposal.json()["detail"]
