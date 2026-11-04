"""Authored offline transactions; no actual accepted input, SDK or financial trial."""

import json
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
