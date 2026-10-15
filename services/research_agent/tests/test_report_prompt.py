"""Captured synthetic report compatibility; no provider or native admission claim."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from qm_research_agent.orchestrator import approved
from test_agent import gateway, runner
from test_research_jobs import request_for

from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import ArtifactRef

CAPTURE = Path(__file__).parent / "fixtures" / "registered-fixture-report.json"
CAPTURE_SHA = "173f770ee5d2b25ea6042b3a46fe240a92068b6911498abc47a737db143c5beb"


def published_profile(local, mutate=None):
    store, lake, clock = local
    job = store.submit(
        "operator",
        "profile",
        request_for(
            lake,
            analysis_requested=True,
            universe=[{"venue": "moomoo", "symbol": symbol} for symbol in ("AAA", "BBB", "CCC")],
        ),
    )
    captured = CAPTURE.read_bytes()
    assert hashlib.sha256(captured).hexdigest() == CAPTURE_SHA
    envelope = json.loads(captured)
    # Rebind only lineage to this isolated test job, preserving the actual report schema.
    envelope["request_digest"] = job.request_digest
    envelope["implementation_digest"] = job.implementation_digest
    envelope["result"]["commit"] = job.implementation_digest
    envelope["result"]["evidence"]["request_digest"] = job.request_digest
    if mutate is not None:
        mutate(envelope)
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    ref = ArtifactRef(
        artifact_id=digest,
        kind="report",
        sha256=digest,
        byte_size=len(raw),
        object_key=f"{job.job_id}/{digest}.json",
    )
    path = store.artifact_root / ref.object_key
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    lease = store.claim("fixture-worker", clock[0])
    assert store.finish(job.job_id, "fixture-worker", lease.attempt, "succeeded", [ref], None)
    return store.get("operator", job.job_id), ref, raw


def test_captured_report_has_safe_prompt_view_without_mutating_artifact(local):
    store, _, _ = local
    job, ref, raw = published_profile(local)
    with pytest.raises(ValueError, match="unapproved report field"):
        approved(json.loads(raw))  # The shared secret/order filter stays strict.
    request, digest = runner(store).prompt(job, ref)
    prompt = json.loads(request.messages[1].content)
    evidence = prompt["report"]["result"]["evidence"]
    original = json.loads(raw)["result"]["evidence"]
    assert prompt["artifact_id"] == ref.artifact_id and len(digest) == 64
    assert evidence["profile"] == {
        "id": "registered-fixture",
        "version": 1,
        "digest": original["execution_profile_digest"],
    }
    assert not any(name.startswith("execution_profile_") for name in evidence)
    assert evidence["fixture_only"] is True
    assert evidence["opaque_native_cache_state"] == "unverified"
    assert prompt["report"]["result"]["metrics"] == json.loads(raw)["result"]["metrics"]
    approved(prompt)
    assert (store.artifact_root / ref.object_key).read_bytes() == raw


def test_captured_report_advisory_archive_replays_without_second_effect(local):
    store, lake, clock = local
    job, ref, _ = published_profile(local)
    model, transport = gateway(ref)
    lease = store.claim_analysis("first", clock[0])
    original = runner(store).run_analysis(job, ref, model, lease=lease)
    assert original.state == "succeeded" and original.citations == [ref]
    archived = (store.artifact_root / original.output_artifact.object_key).read_bytes()
    clock[0] += timedelta(seconds=61)
    reopened = SQLiteJobStore(store.path, lake_root=lake, clock=lambda: clock[0])
    next_lease = reopened.claim_analysis("after-restart", clock[0])
    replayed = runner(reopened).run_analysis(job, ref, model, lease=next_lease)
    assert replayed == original and len(transport.seen_bodies) == 1
    assert (reopened.artifact_root / replayed.output_artifact.object_key).read_bytes() == archived
    assert reopened.finish_analysis(next_lease, replayed)
    assert reopened.get("operator", job.job_id).state == "succeeded"


@pytest.mark.parametrize("field", ["api_key", "order", "broker", "execution_endpoint"])
def test_forbidden_report_fields_never_get_projected(local, field):
    job, ref, _ = published_profile(
        local, lambda envelope: envelope["result"]["evidence"].update({field: "injected"})
    )
    assert_refused_without_effect(local, job, ref)


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_profile_id", "unregistered"),
        ("execution_profile_id", "sk-PUBLIC_FIXTURE_REJECTION_ONLY"),
        ("execution_profile_version", True),
        ("execution_profile_version", 2),
        ("execution_profile_digest", "not-a-sha256"),
        ("fixture_only", False),
        ("opaque_native_cache_state", "verified"),
        ("profile", {"id": "collision"}),
    ],
)
def test_profile_projection_refuses_invalid_values_without_effect(local, field, value):
    job, ref, _ = published_profile(
        local, lambda envelope: envelope["result"]["evidence"].update({field: value})
    )
    assert_refused_without_effect(local, job, ref)


def test_partial_profile_metadata_refuses_without_effect(local):
    job, ref, _ = published_profile(
        local, lambda envelope: envelope["result"]["evidence"].pop("execution_profile_digest")
    )
    assert_refused_without_effect(local, job, ref)


def test_profile_field_outside_report_evidence_is_still_forbidden(local):
    job, ref, _ = published_profile(
        local, lambda envelope: envelope["result"].update(execution_profile_id="registered-fixture")
    )
    assert_refused_without_effect(local, job, ref)


def assert_refused_without_effect(local, job, ref):
    store, _, clock = local
    model, transport = gateway(ref)
    engine = runner(store)
    lease = store.claim_analysis("refuse", clock[0])
    record = engine.run_analysis(job, ref, model, lease=lease)
    assert record.state == "failed" and record.error_code == "artifact_invalid"
    assert record.provider is None and not transport.seen_bodies
    assert engine.effects.read(job.job_id, ref.sha256) is None
    assert store.get("operator", job.job_id).state == "succeeded"
