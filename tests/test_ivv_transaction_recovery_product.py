"""Authored offline transactions; no actual accepted input, SDK or financial trial."""

import json
import sys
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

import pytest

from quantmesh.data.objects import ObjectStore
from quantmesh.research import native_daily_real as daily

SEMANTIC_KEYS = (
    "candidate",
    "inputs",
    "instrument",
    "source_id",
    "source_use",
    "currency",
    "price_adjustment",
    "volume_unit",
    "historical_trade_venues",
    "action_coverage",
    "calendar_id",
    "calendar_timezone",
    "calendar_version",
    "availability_assumption",
    "pit_status",
    "revision_note",
    "window",
    "sample_role",
)


def authored_policy(store, batch, maximum, authority=None):
    import copy

    from quantmesh.research import ivv_recovery as recovery

    body = copy.deepcopy(recovery.DEFAULT_POLICY)
    body["batch"].update(batch_id=batch, max_numerical_attempts=maximum)
    if authority is not None:
        body["authority_sha256"] = authority
    return store.put_bytes("application/json", daily.canonical(body))


def transaction_registration(tmp_path):
    store = ObjectStore(tmp_path / "inputs")
    root = tmp_path / "study"
    registered = daily.engineering_registration(store, output_root=root)
    package = json.loads(store.get_bytes(registered.package_ref))
    identity = {
        "logical_task_id": "ivv-trend-staged-20261029",
        "experiment_id": "declared-trend-staged-v1",
        "input_version": daily.digest(
            daily.canonical({"authored_legacy_engineering_inputs": package["inputs"]})
        ),
        "math_cost_spec": daily.digest(daily.canonical(daily._accounting_contract())),
    }
    identity["business_key"] = daily.digest(daily.canonical(identity))
    policy = authored_policy(store, "authored-a", 3)
    meta = {
        "recovery_identity": identity,
        "attempt_policy": {
            "policy_ref": policy.model_dump(),
            "batch_id": "authored-a",
            "max_numerical_attempts": 3,
        },
        "recovery_provenance": {
            "input_manifest_ref": registered.package_ref.model_dump(),
            "capture_attempt_refs": [registered.package_ref.model_dump()],
        },
    }
    key = str(uuid5(NAMESPACE_URL, "urn:quantmesh:ivv-recovery:v1:" + identity["business_key"]))
    return store, root, key, replace(registered, recovery=meta)


def test_interrupted_execution_recovers_across_authority_metadata_without_new_identity(
    tmp_path, monkeypatch
):
    store, root, key, registered = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registered,))

    def interrupt(*args):
        raise KeyboardInterrupt("authored interruption")

    monkeypatch.setattr(service, "_compute", interrupt)
    with pytest.raises(KeyboardInterrupt):
        service.submit(registered.request, key)
    service.close()
    second_policy = authored_policy(store, "authored-b", 3, "b" * 64)
    refreshed = replace(
        registered,
        recovery={
            **registered.recovery,
            "attempt_policy": {
                **registered.recovery["attempt_policy"],
                "policy_ref": second_policy.model_dump(),
                "batch_id": "authored-b",
            },
        },
    )
    service = daily.NativeDailyService(root, registered=(refreshed,))
    calls = []
    original = service._compute

    def counted(registration, job):
        saved = service._records()[0]
        assert (
            len(saved.transaction.attempts) == 2
            and saved.transaction.attempts[-1].state == "running"
        )
        calls.append(1)
        return original(registration, job)

    monkeypatch.setattr(service, "_compute", counted)
    try:
        job, created = service.submit(refreshed.request, key)
        assert job["state"] == "succeeded" and not created and calls == [1]
        saved = service._records()[0]
        assert [a.state for a in saved.transaction.attempts] == ["interrupted", "committed"]
        assert saved.transaction.identity == registered.recovery["recovery_identity"]
        assert len({a.attempt_id for a in saved.transaction.attempts}) == 2
        assert service.submit(refreshed.request, key)[1] is False and calls == [1]
    finally:
        service.close()


def test_concurrent_submit_claims_one_compute_attempt(tmp_path, monkeypatch):
    import threading

    store, root, key, registered = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registered,))
    entered = threading.Event()
    release = threading.Event()
    calls = []
    out = []
    original = service._compute

    def parked(registration, job):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return original(registration, job)

    monkeypatch.setattr(service, "_compute", parked)

    def run():
        try:
            out.append(service.submit(registered.request, key))
        except BaseException as e:
            out.append(e)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        duplicate, created = service.submit(registered.request, key)
        assert duplicate["state"] == "running" and not created
        assert len(service._records()[0].transaction.attempts) == 1 and calls == [1]
    finally:
        release.set()
        thread.join(10)
        service.close()
    assert not thread.is_alive() and len(out) == 1 and not isinstance(out[0], BaseException)
    assert out[0][0]["state"] == "succeeded" and calls == [1]


def test_prepared_report_and_decision_ack_loss_restart_publish_originals_without_compute(
    tmp_path, monkeypatch
):
    from uuid import uuid4

    from quantmesh.research import native_daily_candidate as native

    store, root, key, registered = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registered,))
    original = service._store.write
    crashed = []

    def lose_ack(records):
        records = list(records)
        original(records)
        if records[0].transaction.prepared_report is not None and not crashed:
            crashed.append(1)
            raise KeyboardInterrupt("authored prepared-result acknowledgement loss")

    monkeypatch.setattr(service._store, "write", lose_ack)
    with pytest.raises(KeyboardInterrupt):
        service.submit(registered.request, key)
    prepared = service._records()[0]
    report = service._object(prepared.transaction.prepared_report)
    admission = service.artifact(key, "admission")
    service.close()

    def forbidden(*a, **kw):
        pytest.fail("committed/prepared recovery must not calculate")

    monkeypatch.setattr(native, "_calculate_matrix", forbidden)
    monkeypatch.setattr(native, "CalendarService", forbidden)
    cold = daily.NativeDailyService(root)
    job = cold.read(key)
    assert job["state"] == "succeeded" and cold.artifact(key, "report") == report
    assert cold.artifact(key, "admission") == admission
    assert cold.submit(registered.request, key)[1] is False
    request = daily.NativeDecisionRequest(
        request_digest=job["request_digest"],
        admission_digest=job["admission"]["digest"],
        report_digest=job["report"]["digest"],
        disposition="reject",
        reason="Authored recovery control; no financial evidence",
    )
    decision_key = str(uuid4())
    write = cold._store.write

    def decision_ack_loss(records):
        records = list(records)
        write(records)
        if records[0].decision is not None:
            raise KeyboardInterrupt("authored decision acknowledgement loss")

    monkeypatch.setattr(cold._store, "write", decision_ack_loss)
    with pytest.raises(KeyboardInterrupt):
        cold.decide(key, request, decision_key)
    decision = cold.artifact(key, "decision")
    cold.close()
    reopened = daily.NativeDailyService(root)
    try:
        assert reopened.decide(key, request, decision_key)[1] is False
        assert [reopened.artifact(key, k) for k in ("admission", "report", "decision")] == [
            admission,
            report,
            decision,
        ]
        assert len(reopened._records()[0].transaction.attempts) == 1
    finally:
        reopened.close()


def test_prepared_recovery_rejects_contradictory_archived_state(tmp_path, monkeypatch):
    """A prepared blob cannot turn a failed or inconsistent archive into success."""
    import copy

    _, root, key, registered = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registered,))
    write = service._store.write

    def stop_after_prepare(records):
        records = list(records)
        write(records)
        if records[0].transaction.prepared_report is not None:
            raise KeyboardInterrupt("authored crash after durable prepared report")

    monkeypatch.setattr(service._store, "write", stop_after_prepare)
    with pytest.raises(KeyboardInterrupt):
        service.submit(registered.request, key)
    ledger = root / "jobs.jsonl"
    original = json.loads(ledger.read_bytes())
    service.close()

    def forbidden(*args, **kwargs):
        pytest.fail("invalid archive must not compute or publish")

    monkeypatch.setattr(daily.NativeDailyService, "_compute", forbidden)
    mutations = [
        ("job", "state", "failed"),
        ("job", "state", "interrupted"),
        ("job", "completed_at", "2026-11-04T00:00:00+00:00"),
        ("attempt", "failure_code", "COMPUTE_FAILED"),
        ("attempt", "completed_at", "2026-11-04T00:00:00+00:00"),
    ]
    for target, field, value in mutations:
        changed = copy.deepcopy(original)
        record = changed if target == "job" else changed["transaction"]["attempts"][-1]
        record[field] = value
        raw = daily.canonical(changed) + b"\n"
        ledger.write_bytes(raw)
        with pytest.raises(daily.NativeError, match="artifact_invalid"):
            reopened = daily.NativeDailyService(root)
            reopened.close()
        assert ledger.read_bytes() == raw


def test_policy_expansion_is_counted_and_additional_experiment_is_explicit(tmp_path, monkeypatch):
    store, root, key, registered = transaction_registration(tmp_path)
    limited_policy = authored_policy(store, "authored-a", 1)
    limited = replace(
        registered,
        recovery={
            **registered.recovery,
            "attempt_policy": {
                **registered.recovery["attempt_policy"],
                "max_numerical_attempts": 1,
                "policy_ref": limited_policy.model_dump(),
            },
        },
    )
    service = daily.NativeDailyService(root, registered=(limited,))

    def failure(*a, **kw):
        raise ValueError("authored failed calculation")

    monkeypatch.setattr(service, "_compute", failure)
    assert service.submit(limited.request, key)[0]["state"] == "failed"
    with pytest.raises(daily.NativeError, match="study_not_admitted"):
        service.submit(limited.request, key)
    assert len(service._records()[0].transaction.attempts) == 1
    service.close()
    policy = authored_policy(store, "expanded", 2)
    expanded = replace(
        registered,
        recovery={
            **registered.recovery,
            "attempt_policy": {
                **registered.recovery["attempt_policy"],
                "max_numerical_attempts": 2,
                "policy_ref": policy.model_dump(),
                "batch_id": "expanded",
            },
        },
    )
    service = daily.NativeDailyService(root, registered=(expanded,))
    try:
        assert service.submit(expanded.request, key)[0]["state"] == "succeeded"
        assert len(service._records()[0].transaction.attempts) == 2
        original = service.artifact(key, "report")
        body = json.loads(store.get_bytes(registered.grant_ref))
        extra_grant = store.put_bytes("application/json", json.dumps(body, indent=1).encode())
        protocol = json.loads(store.get_bytes(registered.protocol_ref))
        protocol["grant_ref"] = extra_grant.model_dump()
        extra_protocol = store.put_bytes("application/json", daily.canonical(protocol))
        identity = {**registered.recovery["recovery_identity"], "input_version": "e" * 64}
        identity["business_key"] = daily.digest(
            daily.canonical({k: v for k, v in identity.items() if k != "business_key"})
        )
        changed = replace(
            registered,
            grant_ref=extra_grant,
            protocol_ref=extra_protocol,
            recovery={**expanded.recovery, "recovery_identity": identity},
        )
        service._registered = (expanded, changed)
        changed_id = str(
            uuid5(NAMESPACE_URL, "urn:quantmesh:ivv-recovery:v1:" + identity["business_key"])
        )
        with pytest.raises(daily.NativeError, match="idempotency_conflict"):
            service.submit(changed.request, changed_id)
        identity = {
            **registered.recovery["recovery_identity"],
            "experiment_id": "declared-trend-staged-v2",
        }
        identity["business_key"] = daily.digest(
            daily.canonical({k: v for k, v in identity.items() if k != "business_key"})
        )
        additional = replace(
            registered,
            grant_ref=extra_grant,
            protocol_ref=extra_protocol,
            recovery={**expanded.recovery, "recovery_identity": identity},
        )
        service._registered = (expanded, additional)
        extra_id = str(
            uuid5(NAMESPACE_URL, "urn:quantmesh:ivv-recovery:v1:" + identity["business_key"])
        )
        # A new experiment is not a refund of the logical task's cumulative budget.
        with pytest.raises(daily.NativeError, match="study_not_admitted"):
            service.submit(additional.request, extra_id)
        third_policy = authored_policy(store, "expanded-again", 3)
        additional = replace(
            additional,
            recovery={
                **additional.recovery,
                "attempt_policy": {
                    "policy_ref": third_policy.model_dump(),
                    "batch_id": "expanded-again",
                    "max_numerical_attempts": 3,
                },
            },
        )
        service._registered = (expanded, additional)
        assert service.submit(additional.request, extra_id)[0]["state"] == "succeeded"
        jobs = service._records()
        assert len(jobs) == 2 and sum(len(j.transaction.attempts) for j in jobs) == 3
        assert service.artifact(key, "report") == original
        assert all(
            json.loads(service.artifact(j.job_id, "report"))["financial_qualification"]
            == "INSUFFICIENT"
            for j in jobs
        )
    finally:
        service.close()


def test_recovery_numeric_preflight_uses_attempt_namespace_after_legacy_refusals(
    tmp_path, monkeypatch
):
    import threading
    from uuid import uuid4

    from quantmesh.research import ivv_runtime as runtime

    for n in range(4):
        (tmp_path / f"numeric-{n}").mkdir()
    seen = []

    class Child:
        def __init__(self, command, budget, directory):
            seen.append(directory)

        def poll(self):
            return None

        def close(self):
            pass

    monkeypatch.setattr(runtime, "_OwnedChild", Child)
    monkeypatch.setattr(runtime, "_readback", lambda child: {"authored_control": True})
    for n in range(5):
        owner = runtime.IVVRuntime.__new__(runtime.IVVRuntime)
        owner.recovery_attempt_id = str(uuid4())
        owner.directory = tmp_path / ("numeric-" + owner.recovery_attempt_id)
        owner.child = owner.started = owner.timer = None
        owner.closed = False
        owner._lock = threading.RLock()
        try:
            assert owner.check()
        finally:
            owner.close()
    assert len(set(seen)) == 5
    assert all((tmp_path / f"numeric-{n}").is_dir() for n in range(4))


def recovery_proofs():
    from quantmesh.research import ivv_admission as gate
    from quantmesh.research import ivv_recovery as recovery

    def ref(digest, length=1):
        return daily.ObjectRef(digest=digest, byte_length=length, media_type="application/json")

    raw = daily.canonical(recovery.DEFAULT_POLICY)
    policy = ref(daily.digest(raw), len(raw))
    authority = ref(recovery.AUTHORITY, 4118)
    return gate.TrustedIVVProofs(
        scope_ref=policy,
        effect_ref=authority,
        execution_ref=authority,
        authorization_ref=authority,
        capture_policy_ref=policy,
        recovery_policy_ref=policy,
        windows_policy_ref=ref("e" * 64),
        go_ref=ref("a" * 64),
        acceptance_ref=ref("b" * 64),
        expected_go_sha256="a" * 64,
        expected_acceptance_sha256="b" * 64,
        expected_policy_sha256=policy.digest,
        expected_authorization_sha256=authority.digest,
    )


def test_recovery_proof_family_rejects_legacy_or_mixed_slots():
    from quantmesh.research import ivv_admission as gate

    p = recovery_proofs()
    assert gate._schema(p, "registration") == "qm.ivv.registration.dev-transaction-recovery.v1"
    for name in (
        "scope_ref",
        "effect_ref",
        "execution_ref",
        "authorization_ref",
        "capture_policy_ref",
    ):
        wrong = p.model_copy(
            update={
                name: daily.ObjectRef(digest="c" * 64, byte_length=1, media_type="application/json")
            }
        )
        with pytest.raises(ValueError):
            gate._schema(wrong, "registration")
    with pytest.raises(ValueError):
        gate._schema(p.model_copy(update={"recovery_policy_ref": None}), "registration")


def reviewed_recovery_registration(tmp_path, monkeypatch, *, historical_capture=False):
    """Authored complete proof graph; never actual captured or accepted market data."""
    import copy

    from test_ivv_additional_consumer import additional_registration

    from quantmesh.research import ivv_recovery as recovery

    gate, m, store, root, old_id, old = additional_registration(tmp_path, monkeypatch)

    def load(ref):
        return json.loads(store.get_bytes(m.ObjectRef.model_validate(ref)))

    def put(obj):
        return store.put_bytes("application/json", m.canonical(obj))

    authority = old["proofs"].authorization_ref
    monkeypatch.setattr(recovery, "AUTHORITY", authority.digest)
    monkeypatch.setattr(recovery, "STUDY_ROOT", str(root))
    policy_body = copy.deepcopy(recovery.DEFAULT_POLICY)
    policy_body["authority_sha256"] = authority.digest
    policy = put(policy_body)
    prov = {**recovery.policy_provenance(policy_body), "policy_sha256": policy.digest}
    cap_authority, cap_policy, cap_body, cap_prov = authority, policy, policy_body, prov
    if historical_capture:
        # The capture policy changes under the same actual human anchor.
        cap_authority = authority
        cap_body = copy.deepcopy(policy_body)
        cap_body["authority_sha256"] = cap_authority.digest
        cap_body["batch"]["batch_id"] = "prior-capture-batch"
        cap_body["storage"]["software"] = 16 * 1024 * 1024
        cap_policy = put(cap_body)
        cap_prov = {**recovery.policy_provenance(cap_body), "policy_sha256": cap_policy.digest}

    def clean(value, *, capture=False):
        value = dict(value)
        for key in gate.ADDITIONAL_PROVENANCE:
            value.pop(key, None)
        value.update(cap_prov if capture else prov)
        return value

    package = load(old["package_ref"])
    semantic = {k: package[k] for k in recovery.SEMANTIC_FIELDS}
    identity = recovery.validate_identity(
        {
            "logical_task_id": recovery.LOGICAL_TASK_ID,
            "experiment_id": "declared-trend-staged-v1",
            "input_version": recovery.semantic_input_version(semantic),
            "math_cost_spec": recovery.MATH_COST_SPEC,
        }
    )
    key = recovery.logical_job_id(identity)
    accepted = load(old["proofs"].acceptance_ref)
    base_raw = load(accepted["capture_ref"])
    old_parent = load(accepted["parent_close_ref"])
    old_go = load(old["proofs"].go_ref)
    source_facts = daily.ObjectRef.model_validate(accepted["source_facts_ref"])
    conn = "authored-connection-01"
    rec = {
        "logical_task_id": recovery.LOGICAL_TASK_ID,
        "batch_id": cap_body["batch"]["batch_id"],
        "connection_attempt_id": conn,
        "policy_sha256": cap_policy.digest,
    }
    capture_go = clean(old_go, capture=True)
    for k in (
        "job_id",
        "output_root_digest",
        "windows_policy_sha256",
        "code",
        "adapter_sha256",
        "gate_sha256",
        "numeric_runtime_sha256",
        "runtime",
        "max_trials",
        "max_capture_intents",
    ):
        capture_go.pop(k, None)
    capture_go.update(
        schema_id="qm.ivv.root-go" + recovery.FAMILY,
        decision="GO_BOUNDED_CAPTURE_RECOVERY",
        scope_id=recovery.capture_scope_id(),
        capture_scope_id=recovery.capture_scope_id(),
        capture_effect_id=recovery.LOGICAL_TASK_ID + "-capture",
        approval_sha256=recovery.capture_effect(),
        execution_sha256=cap_authority.digest,
        recovery=rec,
    )
    capture_go_ref = put(capture_go)
    evidence = [daily.ObjectRef.model_validate(r) for r in accepted["parent_evidence_refs"]]
    plan = load(evidence[0])
    plan.update(
        schema_id="qm.ivv.capture-plan" + recovery.FAMILY, policy_ref={"sha256": cap_policy.digest}
    )
    evidence[0] = put(plan)
    permit = clean(load(evidence[1]), capture=True)
    permit.update(
        schema_id="qm.ivv.root-permit" + recovery.FAMILY, root_go_sha256=capture_go_ref.digest
    )
    evidence[1] = put(permit)
    provider = clean(load(evidence[2]), capture=True)
    provider.update(schema_id="qm.ivv.provider-evidence" + recovery.FAMILY)
    evidence[2] = put(provider)
    journal = put(
        {
            "logical_task_id": recovery.LOGICAL_TASK_ID,
            "connection_attempt_id": conn,
            "batch_id": cap_body["batch"]["batch_id"],
            "policy_sha256": cap_policy.digest,
            "history_actual": "UNKNOWN",
        }
    )
    intent = clean(
        load(
            daily.ObjectRef(
                digest=base_raw["intent_ref"]["sha256"],
                byte_length=base_raw["intent_ref"]["bytes"],
                media_type="application/json",
            )
        ),
        capture=True,
    )
    intent.update(
        schema_id="qm.ivv.capture-intent" + recovery.FAMILY,
        scope_id=recovery.capture_scope_id(),
        effect_id=recovery.LOGICAL_TASK_ID + "-capture",
        approval_sha256=recovery.capture_effect(),
        execution_sha256=cap_authority.digest,
    )
    intent_ref = put(intent)
    raw = clean(base_raw, capture=True)
    raw.update(
        schema_id="qm.ivv.capture" + recovery.FAMILY,
        scope_id=recovery.capture_scope_id(),
        effect_id=recovery.LOGICAL_TASK_ID + "-capture",
        intent_ref={
            "path": "intent.json",
            "sha256": intent_ref.digest,
            "bytes": intent_ref.byte_length,
        },
        recovery={**rec, "request_journal_ref": journal.model_dump(), "history_actual": "UNKNOWN"},
    )
    raw["counts"].update(initializations=1, history_sends=1)
    binding = clean(raw["source_binding"], capture=True)
    binding.update(
        root_go_sha256=capture_go_ref.digest,
        approval_sha256=recovery.capture_effect(),
        execution_sha256=cap_authority.digest,
        plan_sha256=evidence[0].digest,
        root_permit_sha256=evidence[1].digest,
        provider_evidence_ref={"sha256": evidence[2].digest},
    )
    raw["source_binding"] = binding
    raw_ref = put(raw)
    parent = clean(old_parent, capture=True)
    parent.update(
        schema_id="qm.ivv.capture-parent-close" + recovery.FAMILY,
        scope_id=recovery.capture_scope_id(),
        effect_id=recovery.LOGICAL_TASK_ID + "-capture",
        capture_manifest_sha256=raw_ref.digest,
        intent_sha256=intent_ref.digest,
        root_permit_sha256=evidence[1].digest,
        evidence_refs=[
            {"path": "authored.json", "sha256": r.digest, "bytes": r.byte_length} for r in evidence
        ],
        recovery=rec,
    )
    parent_ref = put(parent)
    manifest = put(
        {
            "schema_id": "qm.ivv.input-manifest" + recovery.FAMILY,
            "logical_task_id": recovery.LOGICAL_TASK_ID,
            "semantic": semantic,
            "capture_epoch": rec["batch_id"] + "/" + conn,
            "capture_refs": [raw_ref.model_dump()],
            "capture_go_refs": [capture_go_ref.model_dump()],
            "source_facts_ref": source_facts.model_dump(),
            "parent_close_refs": [parent_ref.model_dump()],
            "asof_pit": {
                "status": "unknown",
                "provider_asof": None,
                "provider_version": None,
                "basis_refs": [],
            },
        }
    )
    windows = put(
        {
            "schema_id": "qm.ivv.windows-policy" + recovery.FAMILY,
            "logical_task_id": recovery.LOGICAL_TASK_ID,
            "recovery_identity": identity,
            "policy_sha256": policy.digest,
            "planning_scope_id": identity["business_key"],
            "planning_job_uuid": key,
            "full_execution_approval_sha256": authority.digest,
            "research_effect_sha256": recovery.research_effect(identity),
            "windows_controls": {
                "job_wide_committed_memory_max": 536870912,
                "affinity_cores": 1,
                "absolute_seconds": 80,
                "owned_study_artifacts": 8388608,
                "paging": "ORDINARY_WINDOWS_OS_MANAGED_ALLOWED",
            },
            "shared_pagefile_growth": "UNKNOWN_NOT_OWNED_ARTIFACTS",
        }
    )
    study = clean(old_go)
    study.update(
        schema_id="qm.ivv.root-go" + recovery.FAMILY,
        decision="GO_RECOVERABLE_AFTER_INPUT_ACCEPTANCE",
        recovery_identity=identity,
        attempt_policy=recovery.attempt_policy(policy_body, policy.model_dump()),
        input_manifest_ref=manifest.model_dump(),
        scope_id=identity["business_key"],
        research_scope_id=identity["business_key"],
        research_effect_sha256=recovery.research_effect(identity),
        approval_sha256=recovery.research_effect(identity),
        execution_sha256=authority.digest,
        job_id=key,
        capture_scope_id=recovery.capture_scope_id(),
        capture_effect_id=recovery.LOGICAL_TASK_ID + "-capture",
        capture_policy_sha256=policy.digest,
        windows_policy_sha256=windows.digest,
    )
    study.pop("max_capture_intents", None)
    study_ref = put(study)
    exposure = put({**load(package["exposure_ref"]), "scope_id": identity["business_key"]})
    ledger = put(
        {
            **load(package["trial_ledger_ref"]),
            "scope_id": identity["business_key"],
            "trial_id": "qm-ivv-trial-" + identity["business_key"],
            "state": "REGISTERED",
        }
    )
    package.update(
        source_asset_refs=[raw_ref.model_dump()],
        exposure_ref=exposure.model_dump(),
        trial_ledger_ref=ledger.model_dump(),
    )
    accepted = clean(accepted)
    accepted.update(
        schema_id="qm.ivv.input-acceptance" + recovery.FAMILY,
        decision="ACCEPT_FOR_DECLARED_RECOVERABLE_RESEARCH",
        recovery_identity=identity,
        input_manifest_ref=manifest.model_dump(),
        scope_id=identity["business_key"],
        capture_scope_id=recovery.capture_scope_id(),
        input_set_digest=gate.input_set_digest(package),
        capture_ref=raw_ref.model_dump(),
        parent_close_ref=parent_ref.model_dump(),
        parent_evidence_refs=[r.model_dump() for r in evidence],
    )
    accept_ref = put(accepted)
    package["review_refs"] = [
        r.model_dump() for r in (policy, authority, study_ref, accept_ref, windows)
    ]
    package_ref = put(package)
    proof = gate.TrustedIVVProofs(
        scope_ref=policy,
        effect_ref=authority,
        execution_ref=authority,
        authorization_ref=authority,
        capture_policy_ref=policy,
        recovery_policy_ref=policy,
        windows_policy_ref=windows,
        go_ref=study_ref,
        acceptance_ref=accept_ref,
        expected_go_sha256=study_ref.digest,
        expected_acceptance_sha256=accept_ref.digest,
        expected_policy_sha256=policy.digest,
        expected_authorization_sha256=authority.digest,
    )
    scope = load(old["approved_scope_ref"])
    scope.update(
        package_ref=package_ref.model_dump(),
        exposure_ref=exposure.model_dump(),
        trial_ledger_ref=ledger.model_dump(),
    )
    scope_ref = put(scope)
    scope_authority = put(
        {
            **load(old["authority_ref"]),
            "approved_scope_ref": scope_ref.model_dump(),
            "review_refs": package["review_refs"],
        }
    )
    grant = put(
        {
            **scope,
            "schema_id": "qm.native-daily.bound-grant.v1",
            "approved_scope_ref": scope_ref.model_dump(),
            "authority_ref": scope_authority.model_dump(),
            "max_trials": 1,
        }
    )
    return (
        gate,
        store,
        root,
        key,
        dict(
            package_ref=package_ref,
            grant_ref=grant,
            approved_scope_ref=scope_ref,
            authority_ref=scope_authority,
            proofs=proof,
        ),
    )


def test_reviewed_recovery_proofs_bind_two_go_roles_and_archive_without_calculation(
    tmp_path, monkeypatch
):
    gate, store, root, key, kwargs = reviewed_recovery_registration(tmp_path, monkeypatch)
    checked = gate._verify(store, kwargs["package_ref"], kwargs["proofs"], executing=True)
    assert checked["scope_trial_key"] == checked["recovery_identity"]["business_key"]
    assert checked["job_id"] == key
    registration = gate.register_ivv_input(store, **kwargs)
    assert registration.recovery["recovery_identity"] == checked["recovery_identity"]
    cold = gate.verify_saved_binding(
        store, kwargs["package_ref"], registration.real_binding, executing=False
    )
    assert cold == checked
    archived = {r.digest for r, b in gate.binding_objects(store, registration.real_binding)}
    assert kwargs["proofs"].recovery_policy_ref.digest in archived
    assert checked["recovery_provenance"]["input_manifest_ref"]["digest"] in archived
    assert not root.exists()


def test_complete_manifest_survives_capture_policy_version_change(tmp_path, monkeypatch):
    gate, store, root, key, kwargs = reviewed_recovery_registration(
        tmp_path, monkeypatch, historical_capture=True
    )
    result = gate._verify(store, kwargs["package_ref"], kwargs["proofs"], executing=True)
    assert result["recovery_identity"]["business_key"] == result["scope_trial_key"]
    manifest = gate._load(store, result["recovery_provenance"]["input_manifest_ref"])
    capture_go = gate._load(store, manifest["capture_go_refs"][0])
    assert capture_go["authorization_sha256"] == kwargs["proofs"].authorization_ref.digest
    assert capture_go["policy_sha256"] != kwargs["proofs"].recovery_policy_ref.digest
    registration = gate.register_ivv_input(store, **kwargs)
    archived = {r.digest for r, b in gate.binding_objects(store, registration.real_binding)}
    assert (
        capture_go["policy_sha256"] in archived and capture_go["authorization_sha256"] in archived
    )
    assert not root.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows constructor platform contract")
def test_recovery_windows_constructor_uses_verified_policy_and_attempt(tmp_path, monkeypatch):
    from uuid import uuid4

    from quantmesh.research import ivv_runtime as runtime

    gate, store, root, key, kwargs = reviewed_recovery_registration(tmp_path, monkeypatch)
    proofs = kwargs["proofs"]
    basis = {
        "proofs": proofs.model_dump(mode="json"),
        "scope_id": gate._load(store, proofs.go_ref)["scope_id"],
        "job_id": key,
        "recovery_identity": gate._load(store, proofs.go_ref)["recovery_identity"],
        "compute_attempt_id": str(uuid4()),
    }
    owner = runtime.IVVRuntime(root, basis, store)
    assert owner.directory == root / ("numeric-" + basis["compute_attempt_id"])
    assert owner.artifact_limit == 8388608
    assert not root.exists()  # Validation does not launch or reserve a child.
    for change in ({"compute_attempt_id": None}, {"job_id": str(uuid4())}, {"scope_id": "f" * 64}):
        with pytest.raises(ValueError):
            runtime.IVVRuntime(root, {**basis, **change}, store)
    windows = gate._load(store, proofs.windows_policy_ref)
    windows["windows_controls"]["affinity_cores"] = True
    bad = store.put_bytes("application/json", daily.canonical(windows))
    altered = proofs.model_copy(update={"windows_policy_ref": bad})
    with pytest.raises(ValueError):
        runtime.IVVRuntime(root, {**basis, "proofs": altered.model_dump(mode="json")}, store)


def test_capacity_growth_is_explicit_and_strict(tmp_path):
    from quantmesh.research import ivv_runtime as runtime

    (tmp_path / "retained").write_bytes(b"x" * 64)
    runtime.ensure_capacity(tmp_path, 64, limit=128)
    for reserved, limit in ((65, 128), (0, True), (True, 128), (-1, 128)):
        with pytest.raises(ValueError):
            runtime.ensure_capacity(tmp_path, reserved, limit=limit)


def test_preclaim_refusal_closes_started_runtime_without_reserving_trial(tmp_path, monkeypatch):
    store, root, key, registered = transaction_registration(tmp_path)
    registered = replace(registered, real_binding=registered.package_ref)
    service = daily.NativeDailyService(root, registered=(registered,))
    closed = []

    class Owner:
        def close(self):
            closed.append(True)

    def admitted(*args, **kwargs):
        service._real_runtimes[registered.real_binding.digest] = Owner()
        return registered, []

    monkeypatch.setattr(service, "_admit", admitted)
    monkeypatch.setattr(
        service,
        "_binding",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("authored preclaim refusal")),
    )
    try:
        with pytest.raises(ValueError, match="authored preclaim refusal"):
            service.submit(registered.request, key)
        assert closed == [True]
        assert service._real_runtimes == {}
        assert service._records() == []
    finally:
        service.close()


def test_public_recovery_status_preserves_request_history_without_private_proofs(
    tmp_path, monkeypatch
):
    store, root, key, registered = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registered,))
    monkeypatch.setattr(
        service, "_compute", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    with pytest.raises(KeyboardInterrupt):
        service.submit(registered.request, key)
    service.close()
    reopened = daily.NativeDailyService(root, registered=(registered,))
    try:
        public = reopened.read(key)
        assert public["recovery_status"] == {
            "business_key": registered.recovery["recovery_identity"]["business_key"],
            "experiment_id": "declared-trend-staged-v1",
            "registered_attempts": 1,
            "last_attempt_state": "interrupted",
            "request_digest_history": [public["request_digest"]],
        }
        assert "transaction" not in public and "real_binding" not in public
        assert "policy_ref" not in public["recovery_status"]
    finally:
        reopened.close()


def test_study_capacity_uses_registered_policy_growth_and_keeps_legacy_limit(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    store, root, key, registered = transaction_registration(tmp_path)
    policy = json.loads(
        store.get_bytes(
            daily.ObjectRef.model_validate(registered.recovery["attempt_policy"]["policy_ref"])
        )
    )
    policy["storage"]["study"] = 12 * 1024 * 1024
    larger = store.put_bytes("application/json", daily.canonical(policy))
    grown = replace(
        registered,
        recovery={
            **registered.recovery,
            "attempt_policy": {
                **registered.recovery["attempt_policy"],
                "policy_ref": larger.model_dump(),
            },
        },
    )
    service = daily.NativeDailyService(root, registered=(grown,))
    original = Path.rglob
    retained = SimpleNamespace(
        is_file=lambda: True, stat=lambda: SimpleNamespace(st_size=8 * 1024 * 1024)
    )
    monkeypatch.setattr(
        Path,
        "rglob",
        lambda self, pattern: iter([retained]) if self == root else original(self, pattern),
    )
    try:
        assert service._put(b"authored") == service.objects.put_bytes(
            "application/json", b"authored"
        )
        service._registered = (replace(registered, recovery=None),)
        with pytest.raises(daily.NativeError, match="capacity_exceeded"):
            service._put(b"legacy retains eight MiB")
    finally:
        service.close()


def test_recovery_manifest_and_windows_mutations_reject_with_fresh_reference_bindings(
    tmp_path, monkeypatch
):
    import copy

    gate, store, root, key, kwargs = reviewed_recovery_registration(tmp_path, monkeypatch)
    proofs = kwargs["proofs"]

    def load(ref):
        return gate._load(store, ref)

    def put(value):
        return store.put_bytes("application/json", daily.canonical(value))

    original_go, original_accept = load(proofs.go_ref), load(proofs.acceptance_ref)
    original_manifest = load(original_go["input_manifest_ref"])
    original_package = load(kwargs["package_ref"])
    # Rebuild every affected content reference. These fail content checks, not
    # merely an obsolete digest in an unrelated enclosing proof.
    variants = []
    bad = copy.deepcopy(original_manifest)
    bad["capture_epoch"] = "wrong-batch/wrong-connection"
    variants.append(bad)
    bad = copy.deepcopy(original_manifest)
    bad["capture_go_refs"] = [proofs.go_ref.model_dump()]
    variants.append(bad)
    bad = copy.deepcopy(original_manifest)
    bad["asof_pit"]["provider_version"] = "claimed-without-original"
    variants.append(bad)
    bad = copy.deepcopy(original_manifest)
    bad["source_facts_ref"] = kwargs["package_ref"].model_dump()
    variants.append(bad)
    bad = copy.deepcopy(original_manifest)
    bad["semantic"]["currency"] = "EUR"
    variants.append(bad)
    for manifest in variants:
        manifest_ref = put(manifest)
        go = {**original_go, "input_manifest_ref": manifest_ref.model_dump()}
        accepted = {**original_accept, "input_manifest_ref": manifest_ref.model_dump()}
        go_ref, accept_ref = put(go), put(accepted)
        altered = proofs.model_copy(
            update={
                "go_ref": go_ref,
                "acceptance_ref": accept_ref,
                "expected_go_sha256": go_ref.digest,
                "expected_acceptance_sha256": accept_ref.digest,
            }
        )
        package = {
            **original_package,
            "review_refs": [
                r.model_dump()
                for r in (
                    proofs.recovery_policy_ref,
                    proofs.authorization_ref,
                    go_ref,
                    accept_ref,
                    proofs.windows_policy_ref,
                )
            ],
        }
        with pytest.raises((ValueError, KeyError, TypeError)):
            gate._verify(store, put(package), altered, executing=True)
    assert not root.exists()


def test_reviewed_recovery_report_and_decision_reopen_originals_without_calculation(
    tmp_path, monkeypatch
):
    from uuid import uuid4

    from quantmesh.research import native_daily_candidate as native

    gate, store, root, key, kwargs = reviewed_recovery_registration(
        tmp_path, monkeypatch, historical_capture=True
    )
    registration = gate.register_ivv_input(store, **kwargs)
    service = daily.NativeDailyService(root, registered=(registration,))
    observed = []
    compute = service._compute

    def counted(reg, job):
        pending = service._records()[0]
        assert pending.transaction.attempts[-1].state == "running"
        observed.append(pending.transaction.attempts[-1].attempt_id)
        return compute(reg, job)

    monkeypatch.setattr(service, "_compute", counted)
    try:
        job, created = service.submit(registration.request, key)
        assert created and job["state"] == "succeeded" and len(observed) == 1
        assert job["recovery_status"]["last_attempt_state"] == "committed"
        decision = daily.NativeDecisionRequest(
            request_digest=job["request_digest"],
            admission_digest=job["admission"]["digest"],
            report_digest=job["report"]["digest"],
            disposition="reject",
            reason="Authored software control; no accepted real market input",
        )
        service.decide(key, decision, str(uuid4()))
        originals = {
            kind: service.artifact(key, kind) for kind in ("admission", "report", "decision")
        }
        report = json.loads(originals["report"])
        assert report["financial_qualification"] == "INSUFFICIENT"
        assert (
            report["use_basis"]["recovery_identity"] == registration.recovery["recovery_identity"]
        )
    finally:
        service.close()

    def forbidden(*args, **kwargs):
        pytest.fail("cold recovery must not calculate, regenerate calendars or create runtime")

    monkeypatch.setattr(native, "_calculate_matrix", forbidden)
    monkeypatch.setattr(native, "CalendarService", forbidden)
    monkeypatch.setattr(gate, "prepare_runtime", forbidden)
    cold = daily.NativeDailyService(root)
    try:
        assert cold.read(key)["state"] == "succeeded"
        assert {kind: cold.artifact(key, kind) for kind in originals} == originals
        assert cold.submit(registration.request, key)[1] is False
        assert len(observed) == 1
    finally:
        cold.close()
