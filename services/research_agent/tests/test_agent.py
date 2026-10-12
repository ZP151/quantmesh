import json
from datetime import timedelta
from decimal import Decimal

import pytest
from conftest import succeeded
from qm_research_agent.budgets import EffectLedger
from qm_research_agent.orchestrator import AdvisoryRunner

from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.research.jobs import RunBudget


def gateway(ref, content=None):
    transport = ScriptedModelTransport(
        [
            {
                "content": json.dumps(
                    content
                    or {
                        "verdict": "inconclusive",
                        "summary": "Scripted fixture: no trading conclusion.",
                        "citations": [ref.artifact_id],
                    }
                ),
                "usage": {"prompt_tokens": 10, "completion_tokens": 12},
            }
        ]
    )
    return ModelGateway(transport, model_name="scripted-fixture"), transport


def runner(store, price=Decimal("0")):
    return AdvisoryRunner(
        store,
        EffectLedger(store),
        provider="scripted",
        price=price,
        price_version="scripted-free-v1",
    )


def test_paid_call_not_repeated_after_checkpoint_resume(local):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    model, transport = gateway(ref)
    engine = runner(store, Decimal("0.2"))
    lease = store.claim_analysis("first", clock[0])
    record = engine.run_analysis(job, ref, model, lease=lease)
    # Crash after the archived effect, before terminal JobStore publication.
    clock[0] += timedelta(seconds=61)
    replacement = store.claim_analysis("replacement", clock[0])
    resumed = runner(store, Decimal("0.2")).run_analysis(job, ref, model, lease=replacement)
    assert resumed == record
    assert len(transport.seen_bodies) == 1
    assert store.finish_analysis(replacement, resumed)
    assert store.get("operator", job.job_id).state == "succeeded"
    assert resumed.provider == "scripted" and resumed.usage.input_tokens == 10


def test_ambiguous_model_timeout_requires_operator_retry(local):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    model, transport = gateway(ref)
    lease = store.claim_analysis("first", clock[0])
    effects = EffectLedger(store)
    digest = ref.sha256
    assert effects.reserve_call(job.job_id, digest, Decimal("0"), job.request.budget, lease)
    # A reserved effect left by a killed process has unknown external outcome.
    clock[0] += timedelta(seconds=61)
    lease = store.claim_analysis("second", clock[0])
    result = runner(store).run_analysis(job, ref, model, lease=lease)
    assert result.state == "unavailable" and result.error_code == "unknown_effect"
    assert result.usage.estimated_model_usd is None
    assert result.output_digest is None and not transport.seen_bodies
    assert store.finish_analysis(lease, result)
    assert store.get("operator", job.job_id).state == "succeeded"


@pytest.mark.parametrize("price", [None, Decimal("1.01"), Decimal("NaN"), Decimal("-1")])
def test_unknown_price_and_budget_exhaustion_block_calls(local, price):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    model, transport = gateway(ref)
    lease = store.claim_analysis("first", clock[0])
    result = runner(store, price).run_analysis(job, ref, model, lease=lease)
    assert result.state == "unavailable" and not transport.seen_bodies
    assert result.provider is None and result.prompt_digest is None


def test_model_failure_preserves_backtest(local):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    model, _ = gateway(ref, {"verdict": "support", "summary": "bad", "citations": ["f" * 64]})
    lease = store.claim_analysis("first", clock[0])
    result = runner(store).run_analysis(job, ref, model, lease=lease)
    assert result.state == "failed"
    assert store.finish_analysis(lease, result)
    assert store.get("operator", job.job_id).state == "succeeded"


@pytest.mark.parametrize("field", ["api_key", "order", "credentials", "base_url"])
def test_secret_and_order_fields_reject(local, field):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    model, transport = gateway(
        ref,
        {"verdict": "support", "summary": "bad", "citations": [ref.artifact_id], field: "injected"},
    )
    lease = store.claim_analysis("first", clock[0])
    result = runner(store).run_analysis(job, ref, model, lease=lease)
    assert result.state == "failed" and result.output_digest is None
    assert len(transport.seen_bodies) == 1


def test_expired_lease_cannot_reserve(local):
    store, lake, clock = local
    job, _ = succeeded(store, lake)
    lease = store.claim_analysis("first", clock[0])
    clock[0] += timedelta(seconds=61)
    assert not EffectLedger(store).reserve_call(
        job.job_id, "a" * 64, Decimal("0"), RunBudget(), lease
    )


def test_response_before_checkpoint_replays_original_invocation_metadata(local, monkeypatch):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    model, transport = gateway(ref)
    first = runner(store, Decimal("0.2"))
    monkeypatch.setattr(first.effects, "checkpoint", lambda *args: False)
    lease = store.claim_analysis("first", clock[0])
    original = first.run_analysis(job, ref, model, lease=lease)
    assert original.state == "succeeded"
    clock[0] += timedelta(seconds=61)
    replacement = store.claim_analysis("new", clock[0])
    changed = runner(store, Decimal("0.7"))
    changed.price_version = "changed-price-v2"
    other_model, other_transport = gateway(ref)
    other_model._model_name = "changed-model"
    replayed = changed.run_analysis(job, ref, other_model, lease=replacement)
    assert replayed == original
    assert len(transport.seen_bodies) == 1 and not other_transport.seen_bodies
