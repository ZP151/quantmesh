"""Authored software controls, never the actual IVV scope/intent or a real trial."""

import csv
import importlib
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest


def implementation():
    try:
        return importlib.import_module("quantmesh.research.ivv_admission")
    except ModuleNotFoundError:
        pytest.fail("scoped IVV admission is not implemented")


def scripted_registration(tmp_path, monkeypatch, *, acceptance_change=None):
    """Fictional authority pins/IDs; no production e285 scope can be reserved."""
    v = implementation()
    from quantmesh.data.calendars import CalendarService, SessionPolicy
    from quantmesh.data.objects import ObjectStore
    from quantmesh.research import native_daily_real as m

    store = ObjectStore(tmp_path / "scripted-inputs")
    study = tmp_path / "scripted-study"
    scope_id = "software-control-" + "a" * 40
    monkeypatch.setattr(v, "SCOPE_ID", scope_id)
    monkeypatch.setattr(v, "SOURCE_ID", "scripted_software_control")

    class ScriptedRuntime:
        """No native claims: fictional proofs and output stay in tmp_path only."""

        def check(self):
            return True

        def calculate(self, bars, events, protocol_digest, code):
            from quantmesh.research import native_daily_candidate as native

            frame = native.pd.read_csv(io.BytesIO(bars), dtype={"date": str}).set_index("date")
            return native._calculate_matrix(frame, events, protocol_digest), {
                "schema_id": "qm.ivv.numeric-close.v1",
                "job_commit_bytes": 536870912,
                "affinity": 1,
                "returncode": 0,
                "active_processes": 0,
                "owned_fds_closed": True,
                "wall_seconds": 0.01,
                "code": code,
            }

        def close(self):
            pass

    monkeypatch.setattr(v, "prepare_runtime", lambda *_: ScriptedRuntime(), raising=False)

    def put(value):
        return store.put_bytes("application/json", m.canonical(value))

    scope_original = put({"selection": {"asset": "US.IVV"}, "test_control": True})
    effect_original = put(
        {"scope_approval_sha256": scope_original.digest, "paper_live": False, "test_control": True}
    )
    window = {
        "warmup_start": "2026-05-08",
        "score_start": "2026-10-01",
        "score_end": "2026-10-29",
        "warmup": 100,
        "observations": 21,
    }
    execution_original = put(
        {
            "approval_sha256": effect_original.digest,
            "fixed_scope": {
                "asset": "US.IVV",
                "scope_id": scope_id,
                "input_window_digest": m.digest(m.canonical(window)),
            },
            "test_control": True,
        }
    )
    monkeypatch.setattr(
        v,
        "ORIGINAL_PINS",
        {
            "scope": scope_original.digest,
            "effect": effect_original.digest,
            "execution": execution_original.digest,
        },
    )
    source_fact = put(
        {
            "schema_id": "qm.ivv.source-facts.v1",
            "currency": "USD",
            "volume_unit": "shares",
            "historical_trade_venues": "authored software only",
            "action_coverage": "complete_cash_ex_pay_no_splits",
            "basis": "constructed test evidence; no market or provider assertion",
        }
    )
    raw = put(
        {
            "status": "CAPTURED_UNREVIEWED",
            "scope_id": scope_id,
            "normal_close": True,
            "originals_complete": True,
            "presence_preserved": True,
            "test_control": True,
        }
    )
    exposure = put(
        {
            "scope_id": scope_id,
            "sample_role": "development_only_retrospective",
            "unseen_oos": False,
            "note": "fictional software control",
        }
    )
    ledger = put(
        {
            "scope_id": scope_id,
            "trial_id": "qm-ivv-trial-" + scope_id,
            "max_trials": 1,
            "state": "UNRESERVED",
        }
    )
    from datetime import date

    sessions = CalendarService().sessions(
        "XNYS", date(2026, 5, 8), date(2026, 10, 29), policy=SessionPolicy.REGULAR
    )
    schedule = [
        {
            "date": s.session_date.isoformat(),
            "open": s.open_at.isoformat(),
            "close": s.close_at.isoformat(),
        }
        for s in sessions
    ]
    assert len(schedule) == 121
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["date", "open", "high", "low", "close", "volume", "dividend"])
    for row in schedule:
        writer.writerow([row["date"], 100, 101, 99, 100, 1000000, 0])
    inputs = {
        "bars": store.put_bytes("text/csv", text.getvalue().encode()).model_dump(),
        "distributions": put([]).model_dump(),
        "schedule": put(schedule).model_dump(),
    }
    package = {
        "schema_id": "qm.native-daily.real-input.v1",
        "candidate": m.CANDIDATE,
        "evidence_kind": "reviewed_real",
        "inputs": inputs,
        "instrument": "US.IVV",
        "source_id": v.SOURCE_ID,
        "source_use": v.SOURCE_USE,
        "currency": "USD",
        "price_adjustment": "raw",
        "volume_unit": "shares",
        "historical_trade_venues": "authored software only",
        "action_coverage": "complete_cash_ex_pay_no_splits",
        "calendar_id": "XNYS",
        "calendar_timezone": "America/New_York",
        "calendar_version": "exchange-calendars:4.13.2:XNYS",
        "availability_assumption": "completed_close_plus30min_assumed",
        "pit_status": "unknown",
        "revision_note": "scripted values; no provider/PIT assertion",
        "review_refs": [],
        "source_asset_refs": [raw.model_dump()],
        "window": window,
        "sample_role": "development_only_retrospective",
        "exposure_ref": exposure.model_dump(),
        "trial_ledger_ref": ledger.model_dump(),
    }
    job_id = str(uuid4())
    runtime = importlib.import_module("quantmesh.research.ivv_runtime")
    policy_ref = put(
        {
            "planning_scope_id": scope_id,
            "planning_job_uuid": job_id,
            "full_execution_approval_sha256": effect_original.digest,
            "test_control": True,
        }
    )
    monkeypatch.setattr(runtime, "WINDOWS_POLICY_SHA", policy_ref.digest)
    go = put(
        {
            "schema_id": "qm.ivv.root-go.v1",
            "decision": "GO_ONCE_AFTER_INPUT_ACCEPTANCE",
            "scope_id": scope_id,
            "execution_sha256": execution_original.digest,
            "input_window_digest": m.digest(m.canonical(window)),
            "full_window_sha256": v.WINDOW_SHA,
            "output_root_digest": m._root_pin(study),
            "job_id": job_id,
            "windows_policy_sha256": policy_ref.digest,
            "max_capture_intents": 1,
            "max_trials": 1,
            "code": importlib.import_module("quantmesh.research.native_daily_candidate")._code(),
            "adapter_sha256": m.digest(Path(m.__file__).read_bytes()),
            "gate_sha256": m.digest(Path(v.__file__).read_bytes()),
            "runtime": m.runtime_versions(),
            "controls": {
                "released": True,
                "resource_bounds": True,
                "provider_log_cache_bounds": True,
            },
            "test_control": True,
        }
    )
    accepted = {
        "schema_id": "qm.ivv.input-acceptance.v1",
        "decision": "ACCEPT_FOR_ONE_DECLARED_RETROSPECTIVE_RESEARCH",
        "reviewer": v.REVIEWER,
        "scope_id": scope_id,
        "input_set_digest": v.input_set_digest(package),
        "capture_ref": raw.model_dump(),
        "source_facts_ref": source_fact.model_dump(),
        "checks": {key: True for key in v.INPUT_CHECKS},
        "financial_qualification": "INSUFFICIENT",
        "paper_allowed": False,
        "live_allowed": False,
        "test_control": True,
    }
    if acceptance_change:
        acceptance_change(accepted)
    acceptance = put(accepted)
    package["review_refs"] = [
        acceptance.model_dump(),
        scope_original.model_dump(),
        effect_original.model_dump(),
        execution_original.model_dump(),
        go.model_dump(),
        policy_ref.model_dump(),
    ]
    package_ref = put(package)
    scope = {
        "schema_id": "qm.native-daily.research-scope.v1",
        "candidate": m.CANDIDATE,
        "package_ref": package_ref.model_dump(),
        "source_id": package["source_id"],
        "source_use": package["source_use"],
        "instrument": "US.IVV",
        "window_digest": m.digest(m.canonical(window)),
        "sample_role": package["sample_role"],
        "exposure_ref": exposure.model_dump(),
        "trial_ledger_ref": ledger.model_dump(),
        "output_root_digest": m._root_pin(study),
    }
    scope_ref = put(scope)
    authority_ref = put(
        {
            "schema_id": "qm.native-daily.scope-authority.v1",
            "candidate": m.CANDIDATE,
            "approved_scope_ref": scope_ref.model_dump(),
            "review_refs": package["review_refs"],
            "decision": "APPROVED_DECLARED_RESEARCH",
        }
    )
    grant_ref = put(
        {
            **scope,
            "schema_id": "qm.native-daily.bound-grant.v1",
            "approved_scope_ref": scope_ref.model_dump(),
            "authority_ref": authority_ref.model_dump(),
            "max_trials": 1,
        }
    )
    proofs = v.TrustedIVVProofs(
        windows_policy_ref=policy_ref,
        scope_ref=scope_original,
        effect_ref=effect_original,
        execution_ref=execution_original,
        go_ref=go,
        acceptance_ref=acceptance,
        expected_go_sha256=go.digest,
        expected_acceptance_sha256=acceptance.digest,
    )
    kwargs = dict(
        package_ref=package_ref,
        grant_ref=grant_ref,
        approved_scope_ref=scope_ref,
        authority_ref=authority_ref,
        proofs=proofs,
    )
    return v, m, store, study, job_id, kwargs


def test_wrong_original_pin_refuses_before_registration(tmp_path, monkeypatch):
    v, m, store, _, _, kwargs = scripted_registration(tmp_path, monkeypatch)
    monkeypatch.setattr(v, "ORIGINAL_PINS", {**v.ORIGINAL_PINS, "effect": "f" * 64})
    with pytest.raises(m.NativeError, match="ivv_not_admitted"):
        v.register_ivv_input(store, **kwargs)


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a.update(input_set_digest="0" * 64),
        lambda a: a["checks"].update(normal_close=False),
        lambda a: a["checks"].pop("complete_actions"),
        lambda a: a.update(reviewer="untrusted"),
        lambda a: a.update(scope_id="other"),
    ],
    ids=["input-set", "normal-close", "actions", "reviewer", "scope"],
)
def test_matching_hash_does_not_substitute_for_acceptance_content(tmp_path, monkeypatch, change):
    v, m, store, _, _, kwargs = scripted_registration(
        tmp_path, monkeypatch, acceptance_change=change
    )
    with pytest.raises(m.NativeError, match="ivv_not_admitted"):
        v.register_ivv_input(store, **kwargs)


def test_input_set_has_no_review_reference_cycle(tmp_path, monkeypatch):
    v, m, store, _, _, kwargs = scripted_registration(tmp_path, monkeypatch)
    package = json.loads(store.get_bytes(kwargs["package_ref"]))
    before = v.input_set_digest(package)
    package["review_refs"] = []
    assert v.input_set_digest(package) == before
    package["volume_unit"] = "lots"
    assert v.input_set_digest(package) != before


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_trials", 2),
        ("full_window_sha256", "f" * 64),
        ("output_root_digest", "f" * 64),
        ("runtime", {"python": "different"}),
        (
            "controls",
            {"released": False, "resource_bounds": True, "provider_log_cache_bounds": True},
        ),
    ],
    ids=["trial-limit", "window", "root", "runtime", "release"],
)
def test_trusted_hash_still_requires_correct_go_context(tmp_path, monkeypatch, field, value):
    v, m, store, _, _, kwargs = scripted_registration(tmp_path, monkeypatch)
    proof = kwargs["proofs"]
    go = json.loads(store.get_bytes(proof.go_ref))
    go[field] = value
    changed = store.put_bytes("application/json", m.canonical(go))
    package = json.loads(store.get_bytes(kwargs["package_ref"]))
    package["review_refs"] = [
        changed.model_dump() if r["digest"] == proof.go_ref.digest else r
        for r in package["review_refs"]
    ]
    package_ref = store.put_bytes("application/json", m.canonical(package))
    # The changed proof's expected pin and its review reference are coherent;
    # refusal must come from the wrong context, not a stale digest test mask.
    changed_proof = proof.model_copy(
        update={"go_ref": changed, "expected_go_sha256": changed.digest}
    )
    with pytest.raises(m.NativeError, match="ivv_not_admitted"):
        v.register_ivv_input(
            store, **{**kwargs, "package_ref": package_ref, "proofs": changed_proof}
        )


def test_trusted_scripted_registration_stays_separate_from_default_real(tmp_path, monkeypatch):
    v, m, store, study, job_id, kwargs = scripted_registration(tmp_path, monkeypatch)
    registration = v.register_ivv_input(store, **kwargs)
    default = m.NativeDailyService(tmp_path / "default")
    try:
        job, _ = default.submit(registration.request, str(uuid4()))
        assert job["state"] == "not_run" and not job["trial_consumed"]
    finally:
        default.close()
    service = m.NativeDailyService(study, registered=(registration,))
    try:
        options = service.options()
        assert (
            options["real_input_enabled"]
            and options["packages"][0]["evidence_kind"] == "reviewed_real"
        )
        assert options["packages"][0]["job_id"] == job_id
        job, _ = service.submit(registration.request, job_id)
        assert (
            job["state"] == "succeeded" and job["admission_status"] == "ACCEPTED_DECLARED_RESEARCH"
        )
    finally:
        service.close()


def test_scripted_real_report_decision_and_same_id_cold_read_do_not_recalculate(
    tmp_path, monkeypatch
):
    v, m, store, study, job_id, kwargs = scripted_registration(tmp_path, monkeypatch)
    registration = v.register_ivv_input(store, **kwargs)
    from quantmesh.research import native_daily_candidate as native

    calls = []
    original = native._calculate_matrix

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(native, "_calculate_matrix", counted)
    service = m.NativeDailyService(study, registered=(registration,))
    job, _ = service.submit(registration.request, job_id)
    assert job["state"] == "succeeded" and calls == [1]
    raw = service.artifact(job_id, "report")
    report = json.loads(raw)
    assert report["schema_id"] == "qm.native-daily.real-report.v2"
    assert report["evidence_kind"] == "reviewed_real"
    assert report["use_basis"]["provider_permission_verified"] is False
    assert report["use_basis"]["external_API_retention_applicability"] == "UNKNOWN"
    decision = m.NativeDecisionRequest(
        request_digest=job["request_digest"],
        admission_digest=job["admission"]["digest"],
        report_digest=job["report"]["digest"],
        disposition="reject",
        reason="Scripted software control, not financial evidence",
    )
    service.decide(job_id, decision, str(uuid4()))
    originals = {k: service.artifact(job_id, k) for k in ("admission", "report", "decision")}
    assert service.submit(registration.request, job_id)[1] is False
    service.close()
    monkeypatch.setattr(native, "_calculate_matrix", lambda *_: pytest.fail("cold calculation"))
    monkeypatch.setattr(native, "CalendarService", lambda: pytest.fail("cold calendar"))
    cold = m.NativeDailyService(study)
    try:
        assert cold.read(job_id)["state"] == "succeeded"
        assert {k: cold.artifact(job_id, k) for k in originals} == originals
        assert calls == [1]
    finally:
        cold.close()


def test_new_grant_byte_alias_cannot_obtain_another_scope_trial(tmp_path, monkeypatch):
    v, m, store, study, job_id, kwargs = scripted_registration(tmp_path, monkeypatch)
    registration = v.register_ivv_input(store, **kwargs)
    grant = json.loads(store.get_bytes(kwargs["grant_ref"]))
    alias = store.put_bytes("application/json", json.dumps(grant, indent=1).encode())
    assert alias.digest != kwargs["grant_ref"].digest
    second = v.register_ivv_input(store, **{**kwargs, "grant_ref": alias})
    service = m.NativeDailyService(study, registered=(registration, second))
    try:
        assert service.submit(registration.request, job_id)[0]["state"] == "succeeded"
        refused, _ = service.submit(second.request, str(uuid4()))
        assert refused["state"] == "not_run" and not refused["trial_consumed"]
        assert refused["admission_reasons"] == ["scope_trial_already_reserved"]
        spent = [job for job in service._records() if job.consumed_grant]
        assert len(spent) == 1 and spent[0].scope_trial_key
    finally:
        service.close()


def test_interrupted_scope_trial_is_not_refunded_or_run_after_restart(tmp_path, monkeypatch):
    v, m, store, study, job_id, kwargs = scripted_registration(tmp_path, monkeypatch)
    registration = v.register_ivv_input(store, **kwargs)
    service = m.NativeDailyService(study, registered=(registration,))
    monkeypatch.setattr(service, "_compute", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        service.submit(registration.request, job_id)
    assert service._records()[0].scope_trial_key
    service.close()
    cold = m.NativeDailyService(study, registered=(registration,))
    try:
        assert cold.read(job_id)["state"] == "interrupted"
        same, created = cold.submit(registration.request, job_id)
        assert not created and same["trial_consumed"]
        another, _ = cold.submit(registration.request, str(uuid4()))
        assert not another["trial_consumed"] and another["state"] == "not_run"
    finally:
        cold.close()


def test_unreviewed_input_set_can_be_staged_but_does_not_mint_an_authority(tmp_path, monkeypatch):
    v, m, store, study, _, kwargs = scripted_registration(tmp_path, monkeypatch)
    package = json.loads(store.get_bytes(kwargs["package_ref"]))
    accepted = json.loads(store.get_bytes(kwargs["proofs"].acceptance_ref))
    facts = json.loads(store.get_bytes(m.ObjectRef.model_validate(accepted["source_facts_ref"])))
    facts.update(pit_status="unknown", revision_note="authored software control")
    rows = list(
        csv.DictReader(
            io.StringIO(
                store.get_bytes(m.ObjectRef.model_validate(package["inputs"]["bars"])).decode()
            )
        )
    )
    for row in rows:
        for name in ("open", "high", "low", "close", "volume", "dividend"):
            row[name] = float(row[name])
    normalized = {
        "status": "NORMALIZED_UNREVIEWED",
        "bars": rows,
        "distributions": [],
        "schedule": json.loads(
            store.get_bytes(m.ObjectRef.model_validate(package["inputs"]["schedule"]))
        ),
    }
    staged = v.stage_ivv_input_set(
        store,
        normalized=normalized,
        source_facts=facts,
        capture_ref=m.ObjectRef.model_validate(accepted["capture_ref"]),
        exposure_ref=m.ObjectRef.model_validate(package["exposure_ref"]),
        trial_ledger_ref=m.ObjectRef.model_validate(package["trial_ledger_ref"]),
    )
    saved = json.loads(store.get_bytes(staged))
    assert saved["schema_id"] == "qm.ivv.unreviewed-input-set.v1"
    assert "review_refs" not in saved["facts"]
    assert saved["input_set_digest"] == v.input_set_digest(saved["facts"])
    assert not study.exists()
    assert not any(key in saved for key in ("grant_ref", "authority_ref", "qualified"))


def test_object_binding_after_review_checks_input_set_before_grant(tmp_path, monkeypatch):
    v, m, store, study, _, kwargs = scripted_registration(tmp_path, monkeypatch)
    package = json.loads(store.get_bytes(kwargs["package_ref"]))
    facts = {k: x for k, x in package.items() if k != "review_refs"}
    staged = store.put_bytes(
        "application/json",
        m.canonical(
            {
                "schema_id": "qm.ivv.unreviewed-input-set.v1",
                "facts": facts,
                "input_set_digest": v.input_set_digest(facts),
            }
        ),
    )
    registered = v.bind_reviewed_ivv_input(
        store, input_set_ref=staged, proofs=kwargs["proofs"], output_root=study
    )
    assert registered.request == v.register_ivv_input(store, **kwargs).request
    bad = store.put_bytes(
        "application/json",
        m.canonical(
            {
                "schema_id": "qm.ivv.unreviewed-input-set.v1",
                "facts": {**facts, "volume_unit": "lots"},
                "input_set_digest": v.input_set_digest({**facts, "volume_unit": "lots"}),
            }
        ),
    )
    with pytest.raises(m.NativeError, match="ivv_not_admitted"):
        v.bind_reviewed_ivv_input(
            store, input_set_ref=bad, proofs=kwargs["proofs"], output_root=study
        )


def test_go_booleans_cannot_replace_real_runtime_admission(tmp_path, monkeypatch):
    v, m, store, study, job_id, kwargs = scripted_registration(tmp_path, monkeypatch)
    registration = v.register_ivv_input(store, **kwargs)

    def unsupported(*_):
        raise m.NativeError("study_runtime_not_admitted")

    service = m.NativeDailyService(
        study, registered=(registration,), real_runtime_factory=unsupported
    )
    try:
        job, _ = service.submit(registration.request, job_id)
        assert job["state"] == "not_run" and not job["trial_consumed"]
        assert job["admission_reasons"] == ["study_runtime_not_admitted"]
    finally:
        service.close()
