import json
import time
from decimal import Decimal

from conftest import succeeded
from fastapi.testclient import TestClient
from pydantic import SecretStr
from qm_research_agent.app import create_app
from qm_research_agent.budgets import EffectLedger
from qm_research_agent.orchestrator import AdvisoryRunner, ApprovedRemoteGateway
from test_research_jobs import request_for

from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import ScriptedModelTransport


def test_unsupported_budget_blocks_before_effect(local, monkeypatch):
    import qm_research_agent.orchestrator as orchestrator

    # Force unsupported execution capability; real state/ledger must reject
    # before any provider reservation, invocation or fabricated metadata.
    monkeypatch.setattr(orchestrator, "supported_budget", lambda budget: False)
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    transport = ScriptedModelTransport([])
    gateway = ModelGateway(transport, model_name="scripted-fixture")
    lease = store.claim_analysis("first", clock[0])
    effects = EffectLedger(store)
    engine = AdvisoryRunner(
        store, effects, provider="scripted", price=Decimal("0"), price_version="v1"
    )
    result = engine.run_analysis(job, ref, gateway, lease=lease)
    assert result.error_code == "model_unavailable"
    assert result.provider is None and effects.read(job.job_id, ref.sha256) is None
    assert not transport.seen_bodies


class SlowScriptedTransport(ScriptedModelTransport):
    def complete(self, body):
        time.sleep(3)
        return super().complete(body)


class AmbiguousTransport(ScriptedModelTransport):
    def complete(self, body):
        if not self.seen_bodies:
            self.seen_bodies.append(body)
            raise TimeoutError("fixture unknown effect")
        return super().complete(body)


def test_validation_response_never_echoes_injected_secret(local):
    store, lake, _ = local
    client = TestClient(
        create_app(store, operator_id="operator", token=SecretStr("fixture-private-token"))
    )
    headers = {"Authorization": "Bearer fixture-private-token", "Idempotency-Key": "key"}
    body = request_for(lake).model_dump(mode="json")
    body["api_key"] = "PRIVATE-SECRET-SHOULD-NOT-ECHO"
    response = client.post("/v1/jobs", headers=headers, json=body)
    assert response.status_code == 422
    assert "PRIVATE-SECRET-SHOULD-NOT-ECHO" not in response.text


def test_unknown_effect_survives_changed_configuration(local):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    transport = AmbiguousTransport(
        [
            {
                "content": json.dumps(
                    {
                        "verdict": "inconclusive",
                        "summary": "scripted fixture",
                        "citations": [ref.artifact_id],
                    }
                )
            }
        ]
    )
    gateway = ModelGateway(transport, model_name="scripted-fixture")
    lease = store.claim_analysis("first", clock[0])
    engine = AdvisoryRunner(
        store, EffectLedger(store), provider="scripted", price=Decimal("0"), price_version="v1"
    )
    assert engine.run_analysis(job, ref, gateway, lease=lease).error_code == "unknown_effect"
    engine.price_version = "v2"
    result = engine.run_analysis(job, ref, gateway, lease=lease)
    assert result.error_code == "unknown_effect"
    assert len(transport.seen_bodies) == 1


def test_remote_egress_construction_rejects_unapproved_endpoint():
    import pytest

    with pytest.raises(ValueError):
        ApprovedRemoteGateway(
            base_url="https://unapproved.example",
            model="fixture",
            key=SecretStr(""),
            allowed_origins=frozenset({"https://approved.example"}),
            remote_consent=True,
        )


def test_analysis_deadline_stops_owned_effect_without_recall(local):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    job = job.model_copy(
        update={
            "request": job.request.model_copy(
                update={"budget": job.request.budget.model_copy(update={"timeout_seconds": 1})}
            )
        }
    )
    transport = SlowScriptedTransport(
        [
            {
                "content": json.dumps(
                    {
                        "verdict": "inconclusive",
                        "summary": "scripted",
                        "citations": [ref.artifact_id],
                    }
                )
            }
        ]
    )
    gateway = ModelGateway(transport, model_name="scripted-fixture")
    lease = store.claim_analysis("first", clock[0])
    engine = AdvisoryRunner(
        store, EffectLedger(store), provider="scripted", price=Decimal("0"), price_version="v1"
    )
    started = time.monotonic()
    result = engine.run_analysis(job, ref, gateway, lease=lease)
    assert result.error_code == "unknown_effect"
    assert time.monotonic() - started < 2.5
    assert engine.run_analysis(job, ref, gateway, lease=lease).error_code == "unknown_effect"
    assert len(transport.seen_bodies) == 1
