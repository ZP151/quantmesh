"""Versioned binding/one-job tests; calculator is an explicit nonfinancial sentinel."""

import json
from contextlib import closing
from datetime import timedelta
from uuid import uuid4

import pytest

from quantmesh.data.objects import ObjectStore
from quantmesh.research import spy_replay as replay
from tests.test_freeze_opend_spy_daily import AS_OF
from tests.test_spy_policy_exception_freeze import authority as _authority
from tests.test_spy_policy_exception_freeze import frozen_v3, sha
from tools.research import freeze_opend_spy_daily as freezer


@pytest.fixture
def authority(tmp_path, monkeypatch):
    return _authority.__wrapped__(tmp_path, monkeypatch)


def descriptor(authority):
    root, _, binding = authority
    frozen, auth, _, _ = frozen_v3(authority)
    store = ObjectStore(root)
    acceptance = dict(
        schema_version=3,
        status="accepted_for_policy_exception_historical_diagnostic",
        scope="US.SPY/1d/private_research",
        snapshot_digest=frozen["freeze_digest"],
        protocol_digest=frozen["protocol_ref"]["digest"],
        use_document_sha256=binding["policy_document_ref"]["digest"],
        independent_input_review_sha256="e" * 64,
        authorization_sha256=sha(freezer._canonical(auth)),
        post_review_sha256=frozen["members"]["post-review.json"]["digest"],
        policy_exception=binding,
        capture_intent_ref=frozen["capture_intent_ref"],
        reviewed_at_utc=(AS_OF + timedelta(minutes=4)).isoformat(),
    )
    ref = store.put_bytes("application/json", freezer._canonical(acceptance))
    path = root / "operator-descriptor.json"
    path.write_bytes(
        freezer._canonical(
            dict(
                schema_version=3,
                freeze_root=str(root),
                freeze_digest=frozen["freeze_digest"],
                acceptance=ref.model_dump(mode="json"),
            )
        )
    )
    return path, frozen, acceptance


def test_trusted_descriptor_v3_exposes_internal_exception_not_vendor_allow(authority):
    path, _, _ = descriptor(authority)
    value = replay.ReplayInput.from_descriptor(path)
    summary = value.summary().model_dump(mode="json")
    assert summary["evidence_kind"] == "reviewed_opend_policy_exception_once_v3"
    assert summary["policy_exception"]["external_api_storage_applicability"] == "UNKNOWN"
    assert summary["policy_exception"]["job_idempotency_key"] == authority[2]["job_idempotency_key"]


def test_single_job_same_payload_and_cold_proof_no_calculation(authority, tmp_path, monkeypatch):
    path, _, _ = descriptor(authority)
    value = replay.ReplayInput.from_descriptor(path)
    calls = []

    def sentinel(*args):
        calls.append(1)
        return {"controlled_test_seam": "NO_FINANCIAL_COMPUTATION"}

    monkeypatch.setattr(replay.engine, "calculate", sentinel)
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    key = authority[2]["job_idempotency_key"]
    target = tmp_path / "jobs"
    with closing(replay.ReplayService(target, replay_input=value)) as service:
        with pytest.raises(replay.ReplayError, match="invalid_request"):
            service.submit(request, uuid4())
        assert calls == []
        job, created = service.submit(request, key)
        assert created and job.state == "succeeded" and calls == [1]
        assert service.submit(request, key)[1] is False and calls == [1]
        changed = request.model_copy(update={"snapshot_digest": "f" * 64})
        with pytest.raises(replay.ReplayError, match="idempotency_conflict"):
            service.submit(changed, key)
        report = service.artifact(key)
        decoded = json.loads(report)
        assert decoded["schema_version"] == 3
        assert decoded["sample_evidence"]["policy_exception"] == authority[2]
        body = replay.DecisionRequest(
            request_digest=job.request_digest,
            report_digest=job.report.digest,
            disposition="watch",
            reason="Controlled contract test only",
        )
        service.decide(key, body, uuid4())
    # Cold service has no current input or options to backfill from.
    with closing(replay.ReplayService(target)) as cold:
        assert cold.artifact(key) == report and cold.get(key).decision.disposition == "watch"
        assert calls == [1]


def test_acceptance_different_policy_or_missing_review_cannot_qualify(authority):
    path, frozen, acceptance = descriptor(authority)
    acceptance["policy_exception"]["external_api_storage_applicability"] = "VERIFIED"
    ref = ObjectStore(authority[0]).put_bytes("application/json", freezer._canonical(acceptance))
    value = json.loads(path.read_bytes())
    value["acceptance"] = ref.model_dump(mode="json")
    path.write_bytes(freezer._canonical(value))
    with pytest.raises(replay.ReplayError, match="input_not_qualified"):
        replay.ReplayInput.from_descriptor(path)


def test_legacy_report_bytes_stay_read_only_without_exception_backfill(tmp_path, monkeypatch):
    from tests.test_spy_replay import synthetic_input

    monkeypatch.setattr(replay.engine, "calculate", lambda *args: {"engineering_only": True})
    value = synthetic_input()
    key = uuid4()
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    target = tmp_path / "legacy"
    with closing(replay.ReplayService(target, replay_input=value)) as service:
        job, _ = service.submit(request, key)
        before = service.artifact(key)
    with closing(replay.ReplayService(target)) as cold:
        assert cold.artifact(key) == before
        assert "policy_exception" not in json.loads(before)["sample_evidence"]
        assert cold.get(key).report == job.report


def test_failed_once_job_stays_failed_without_new_chance(authority, tmp_path, monkeypatch):
    path, _, _ = descriptor(authority)
    value = replay.ReplayInput.from_descriptor(path)
    calls = []

    def fail(*args):
        calls.append(1)
        raise RuntimeError("controlled calculator refusal; no math")

    monkeypatch.setattr(replay.engine, "calculate", fail)
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    key = authority[2]["job_idempotency_key"]
    with closing(replay.ReplayService(tmp_path / "failed", replay_input=value)) as service:
        assert service.submit(request, key)[0].state == "failed"
        assert service.submit(request, key)[0].state == "failed" and calls == [1]


def test_same_intent_concurrent_submit_returns_one_running_job(authority, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    path, _, _ = descriptor(authority)
    value = replay.ReplayInput.from_descriptor(path)
    entered, release = Event(), Event()
    calls = []

    def held(*args):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return {"controlled_test_seam": True}

    monkeypatch.setattr(replay.engine, "calculate", held)
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    key = authority[2]["job_idempotency_key"]
    with closing(replay.ReplayService(tmp_path / "parallel", replay_input=value)) as service:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(service.submit, request, key)
            try:
                assert entered.wait(4)
                job, created = service.submit(request, key)
                assert job.state == "running" and not created and calls == [1]
            finally:
                release.set()
            assert future.result(5)[0].state == "succeeded" and calls == [1]


def test_cold_missing_original_policy_refuses_without_options_fallback(
    authority, tmp_path, monkeypatch
):
    path, _, _ = descriptor(authority)
    value = replay.ReplayInput.from_descriptor(path)
    monkeypatch.setattr(replay.engine, "calculate", lambda *args: {"controlled_test_seam": True})
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    target = tmp_path / "tampered"
    with closing(replay.ReplayService(target, replay_input=value)) as service:
        service.submit(request, authority[2]["job_idempotency_key"])
        ref = value.policy_exception.policy_document_ref
        original = service.objects.path_for(ref)
    original.write_bytes(b"tampered controlled fixture")
    with pytest.raises(replay.ReplayError, match="artifact_invalid"):
        replay.ReplayService(target)
