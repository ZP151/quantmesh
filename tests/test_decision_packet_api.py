from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.demo.seeder import seed_demo_root
from quantmesh.domain.models import Side, Venue
from quantmesh.instruments.contracts import DecisionDisposition, HistoryRange
from quantmesh.instruments.decision_packets import (
    DecisionPacketService,
    DecisionPacketStore,
)
from quantmesh.instruments.proposals import PaperDecisionService

SCENARIO = DemoScenario()


def _draft(client: TestClient, symbol: str = "NVDA") -> dict[str, object]:
    response = client.get(f"/api/instruments/moomoo/{symbol}/workspace?range=6m")
    assert response.status_code == 200
    return response.json()["decision"]["draft"]


def _save(client: TestClient, draft: dict[str, object], symbol: str = "NVDA"):
    return client.post(
        "/api/decision-packets",
        json={
            "venue": "moomoo",
            "symbol": symbol,
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )


def test_workspace_uses_the_bound_packet_service_and_save_refuses_expected_id_drift(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    original = app.state.instrument_workspace

    class RecordingWorkspace:
        def __init__(self) -> None:
            self.calls = 0

        def render(self, *args, **kwargs):
            self.calls += 1
            return original.render(*args, **kwargs)

    recording = RecordingWorkspace()
    app.state.instrument_workspace = recording

    with TestClient(app) as client:
        draft = _draft(client)
        mismatch = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": "packet-" + "f" * 24,
            },
        )

    assert recording.calls == 2
    assert draft["as_of"] == SCENARIO.anchor.isoformat().replace("+00:00", "Z")
    assert mismatch.status_code == 409
    assert "expected" in mismatch.json()["detail"].lower()
    assert app.state.decision_packets.latest(
        Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS
    ) is None


@pytest.mark.parametrize("disposition", ["reject", "watch"])
def test_reject_and_watch_are_exactly_reopenable_and_idempotent(
    tmp_path: Path,
    disposition: str,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft)
        assert saved.status_code == 200
        path = f"/api/decision-packets/{saved.json()['packet_id']}/actions"
        payload = {
            "disposition": disposition,
            "operator_reason": "Wait for the observed entry condition.",
            "side": None,
            "quantity": None,
            "limit_price": None,
        }
        first = client.post(path, json=payload)
        replay = client.post(path, json=payload)
        exact = client.get(
            f"/api/decision-packets/{first.json()['packet']['packet_id']}"
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert first.json()["packet"]["version"] == 2
    assert first.json()["proposal"] is None
    assert exact.status_code == 200
    assert exact.json() == first.json()["packet"]
    assert app.state.paper_decisions.ledger.all() == ()


def test_stale_packet_blocks_paper_without_creating_a_proposal(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    stale_at = SCENARIO.anchor + timedelta(days=3)
    app.state.instrument_workspace._now = lambda: stale_at  # noqa: SLF001

    with TestClient(app) as client:
        draft = _draft(client)
        codes = [item["code"] for item in draft["paper_capability"]["blockers"]]
        saved = _save(client, draft)
        blocked = client.post(
            f"/api/decision-packets/{saved.json()['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert {"history-freshness", "forecast-freshness"}.issubset(codes)
    assert saved.status_code == 200
    assert blocked.status_code == 409
    assert app.state.paper_decisions.ledger.all() == ()


def test_untrusted_packet_blocks_paper_without_creating_a_proposal(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    artifact = next(
        item
        for item in app.state.price_forecasts.all()
        if item.instrument.symbol == "NVDA"
    )
    untrusted = artifact.model_copy(
        update={"eligible": False, "blockers": ("quality evaluation failed",)}
    )

    class UntrustedForecasts:
        @staticmethod
        def all():
            return [untrusted]

    app.state.instrument_workspace._forecasts = UntrustedForecasts()  # noqa: SLF001

    with TestClient(app) as client:
        draft = _draft(client)
        codes = [item["code"] for item in draft["paper_capability"]["blockers"]]
        saved = _save(client, draft)
        blocked = client.post(
            f"/api/decision-packets/{saved.json()['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert "forecast-ineligible" in codes
    assert saved.status_code == 200
    assert blocked.status_code == 409
    assert app.state.paper_decisions.ledger.all() == ()


def test_packet_bound_paper_action_never_confirms_and_risk_refusal_stays_bound(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft).json()
        before_orders = len(app.state.demo.seeded.journal.all())
        action = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        replay = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        result = action.json()
        assert result["proposal"]["status"] == "pending"
        assert len(app.state.demo.seeded.journal.all()) == before_orders

        account_store = app.state.account_store
        account_store.replace(account_store.get().model_copy(update={"kill_switch": True}))
        refused = client.post(
            f"/api/paper/proposals/{result['proposal']['id']}/confirm",
            json={"confirmation_token": result["proposal"]["confirmation_token"]},
        )

    assert action.status_code == 200
    assert replay.json() == result
    assert result["packet"]["proposal_id"] == result["proposal"]["id"]
    assert refused.status_code == 409
    assert refused.json()["proposal"]["status"] == "rejected"
    assert refused.json()["order"]["status"] == "rejected"
    assert result["packet"]["packet_id"] == app.state.decision_packets.latest(
        Venue.MOOMOO,
        "NVDA",
        HistoryRange.SIX_MONTHS,
    ).packet_id


def test_legacy_proposal_route_requires_an_exact_packet_artifact_binding(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft).json()
        aapl = next(
            artifact
            for artifact in app.state.price_forecasts.all()
            if artifact.instrument.symbol == "AAPL"
        )
        bare = client.post(
            "/api/paper/proposals",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "artifact_id": draft["evidence"]["forecast_artifact_id"],
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )
        mismatch = client.post(
            "/api/paper/proposals",
            json={
                "venue": "moomoo",
                "symbol": "AAPL",
                "artifact_id": aapl.id,
                "decision_packet_id": saved["packet_id"],
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert bare.status_code == 409
    assert "decision packet" in bare.json()["detail"].lower()
    assert mismatch.status_code == 409
    assert "artifact" in mismatch.json()["detail"].lower()
    assert app.state.paper_decisions.ledger.all() == ()


def test_clean_demo_restart_reopens_identical_packet_bytes(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        draft = _draft(client)
        saved = _save(client, draft).json()
        action = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json={
                "disposition": "watch",
                "operator_reason": "Wait for a verified breakout.",
                "side": None,
                "quantity": None,
                "limit_price": None,
            },
        ).json()
    packet_path = root / "decisions" / "packets" / "decision-packets.jsonl"
    before = packet_path.read_bytes()

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        reopened = client.get(
            f"/api/decision-packets/{action['packet']['packet_id']}"
        )

    assert reopened.status_code == 200
    assert reopened.json() == action["packet"]
    assert packet_path.read_bytes() == before


def test_advancing_workspace_clock_saves_the_exact_observed_draft_and_reopens_latest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    tick = 0

    def advancing_clock():
        nonlocal tick
        value = SCENARIO.anchor + timedelta(seconds=tick)
        tick += 1
        return value

    app.state.instrument_workspace._now = advancing_clock  # noqa: SLF001
    with TestClient(app) as client:
        observed = _draft(client)
        saved_response = _save(client, observed)

    assert saved_response.status_code == 200
    saved = saved_response.json()
    assert saved["packet_id"] == observed["packet_id"]
    assert saved["as_of"] == observed["as_of"]

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    restarted.app_state_clock = SCENARIO.anchor + timedelta(minutes=5)
    restarted.state.instrument_workspace._now = (  # noqa: SLF001
        lambda: restarted.app_state_clock
    )
    with TestClient(restarted) as client:
        reopened = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")

    assert reopened.status_code == 200
    assert reopened.json()["decision"]["draft"] == saved
    assert reopened.json()["decision"]["latest"] == saved


@pytest.mark.parametrize("disposition", [DecisionDisposition.REJECT, DecisionDisposition.WATCH])
def test_concurrent_nonpaper_actions_append_one_idempotent_child(
    tmp_path: Path,
    disposition: DecisionDisposition,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        parent = _save(client, _draft(client)).json()

    workers = 8
    barrier = threading.Barrier(workers)
    services = tuple(
        DecisionPacketService(
            store=DecisionPacketStore(app.state.decision_packets.root),
            workspace_provider=lambda: app.state.instrument_workspace,
            proposals=app.state.paper_decisions,
        )
        for _ in range(workers)
    )

    def apply(service: DecisionPacketService):
        barrier.wait()
        return service.transition(
            parent["packet_id"],
            disposition=disposition,
            operator_reason="Wait for one exact condition.",
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = tuple(executor.map(apply, services))

    assert len({result.packet.packet_id for result in results}) == 1
    assert len(app.state.decision_packets.all()) == 2
    assert app.state.paper_decisions.ledger.all() == ()


def test_crash_after_proposal_write_retries_without_a_second_proposal(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        parent = _save(client, _draft(client)).json()

    clock_tick = 0

    def proposal_clock():
        nonlocal clock_tick
        value = SCENARIO.anchor + timedelta(microseconds=clock_tick)
        clock_tick += 1
        return value

    app.state.paper_decisions._now = proposal_clock  # noqa: SLF001
    store = app.state.decision_packets
    original_record = store.record
    crashed = False

    def crash_on_child(packet):
        nonlocal crashed
        if packet.version == 2 and not crashed:
            crashed = True
            raise RuntimeError("simulated stop after proposal durability")
        return original_record(packet)

    store.record = crash_on_child
    with pytest.raises(RuntimeError, match="simulated stop"):
        app.state.decision_packet_service.transition(
            parent["packet_id"],
            disposition=DecisionDisposition.PAPER_PROPOSAL,
            side=Side.BUY,
            quantity=1.0,
        )
    store.record = original_record

    recovered = app.state.decision_packet_service.transition(
        parent["packet_id"],
        disposition=DecisionDisposition.PAPER_PROPOSAL,
        side=Side.BUY,
        quantity=1.0,
    )

    assert len(app.state.paper_decisions.ledger.all()) == 1
    assert recovered.proposal == app.state.paper_decisions.ledger.all()[0]
    assert recovered.packet.proposal_id == recovered.proposal.id
    assert len(store.all()) == 2


def test_concurrent_paper_actions_create_one_proposal_and_one_child(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        parent = _save(client, _draft(client)).json()

    workers = 4
    proposal_barrier = threading.Barrier(workers)
    original = app.state.paper_decisions

    class RacingPaperService(PaperDecisionService):
        def propose(self, *args, **kwargs):
            try:
                proposal_barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
            return super().propose(*args, **kwargs)

    racing = RacingPaperService(
        ledger=original.ledger,
        forecast_registry=original._forecast_registry,  # noqa: SLF001
        account_provider=original._account_provider,  # noqa: SLF001
        account_sink=original._account_sink,  # noqa: SLF001
        account_transaction=original._account_transaction,  # noqa: SLF001
        journal=original._journal,  # noqa: SLF001
        snapshot_provider=original._snapshot_provider,  # noqa: SLF001
        quote_fence=original._quote_fence,  # noqa: SLF001
        demo_quote_provider=original._demo_quote_provider,  # noqa: SLF001
        now=original._now,  # noqa: SLF001
    )
    barrier = threading.Barrier(workers)
    services = tuple(
        DecisionPacketService(
            store=DecisionPacketStore(app.state.decision_packets.root),
            workspace_provider=lambda: app.state.instrument_workspace,
            proposals=racing,
        )
        for _ in range(workers)
    )

    def apply(service: DecisionPacketService):
        barrier.wait()
        return service.transition(
            parent["packet_id"],
            disposition=DecisionDisposition.PAPER_PROPOSAL,
            side=Side.BUY,
            quantity=1.0,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = tuple(executor.map(apply, services))

    assert len({result.packet.packet_id for result in results}) == 1
    assert len({result.proposal.id for result in results if result.proposal is not None}) == 1
    assert len(app.state.paper_decisions.ledger.all()) == 1
    assert len(app.state.decision_packets.all()) == 2


def test_saved_packet_that_naturally_expires_refuses_before_proposal_write(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        parent = _save(client, _draft(client)).json()
        app.state.paper_decisions._now = (  # noqa: SLF001
            lambda: SCENARIO.anchor + timedelta(days=3)
        )
        refused = client.post(
            f"/api/decision-packets/{parent['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert refused.status_code == 409
    assert "expired" in refused.json()["detail"].lower()
    assert app.state.paper_decisions.ledger.all() == ()
    assert app.state.decision_packets.latest(
        Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS
    ).packet_id == parent["packet_id"]


def test_partial_packet_bound_configuration_still_refuses_bare_artifact(
    tmp_path: Path,
) -> None:
    seeded = seed_demo_root(tmp_path / "partial")
    app = create_workstation_app(
        account=seeded.account,
        marks=seeded.marks,
        journal=seeded.journal,
        price_forecasts=seeded.price_forecasts,
        proposal_ledger=seeded.proposal_ledger,
        decision_packets=seeded.decision_packets,
        workspace_clock=lambda: seeded.scenario.anchor,
        host="127.0.0.1",
    )
    artifact = next(
        item for item in seeded.price_forecasts.all() if item.instrument.symbol == "NVDA"
    )

    with TestClient(app) as client:
        refused = client.post(
            "/api/paper/proposals",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "artifact_id": artifact.id,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert not hasattr(app.state, "instrument_workspace")
    assert refused.status_code == 409
    assert "decision packet" in refused.json()["detail"].lower()
    assert seeded.proposal_ledger.all() == ()


def test_registry_drift_between_preflight_and_propose_has_zero_external_writes(
    tmp_path: Path,
) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        parent = _save(client, _draft(client)).json()

        original = app.state.paper_decisions._forecast_registry.get(  # noqa: SLF001
            parent["evidence"]["forecast_artifact_id"]
        )
        drifted = original.model_copy(
            update={"model_version": f"{original.model_version}-drift"}
        )

        class DriftingRegistry:
            calls = 0

            def get(self, artifact_id: str):
                assert artifact_id == original.id
                self.calls += 1
                return original if self.calls == 1 else drifted

        registry = DriftingRegistry()
        app.state.paper_decisions._forecast_registry = registry  # noqa: SLF001
        refused = client.post(
            f"/api/decision-packets/{parent['packet_id']}/actions",
            json={
                "disposition": "paper_proposal",
                "operator_reason": None,
                "side": "buy",
                "quantity": 1.0,
                "limit_price": None,
            },
        )

    assert registry.calls == 2
    assert refused.status_code == 409
    assert "forecast" in refused.json()["detail"].lower()
    assert app.state.paper_decisions.ledger.all() == ()
    assert len(app.state.decision_packets.all()) == 1


def test_exact_packet_get_distinguishes_missing_from_corrupt_store(tmp_path: Path) -> None:
    app = create_demo_app(root=tmp_path / "demo", seed=SCENARIO.seed, host="127.0.0.1")
    missing_id = "packet-" + "f" * 24
    with TestClient(app) as client:
        missing = client.get(f"/api/decision-packets/{missing_id}")
        app.state.decision_packets.path.write_text("{broken-json\n", encoding="utf-8")
        corrupt = client.get(f"/api/decision-packets/{missing_id}")

    assert missing.status_code == 404
    assert corrupt.status_code == 409
    assert "invalid" in corrupt.json()["detail"].lower()
