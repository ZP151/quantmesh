"""Offline workstation lifecycle; never a real-data or financial qualification."""

import importlib
import json
from uuid import uuid4

import pytest


def implementation():
    try:
        return importlib.import_module("quantmesh.research.native_daily_real")
    except ModuleNotFoundError:
        pytest.fail("fixed candidate workstation admission is not implemented")


def test_missing_input_persists_insufficient_and_cold_reopens_without_compute(tmp_path):
    m = implementation()
    root = tmp_path / "study"
    key = str(uuid4())
    service = m.NativeDailyService(root)
    job, created = service.submit(m.NativeRequest(), key)
    assert created and job["job_id"] == key
    assert job["state"] == "not_run" and job["report"] is None
    assert job["admission_status"] == "INSUFFICIENT"
    assert job["trial_consumed"] is False
    admission = service.artifact(key, "admission")
    assert json.loads(admission)["reasons"] == ["package_missing", "candidate_grant_missing"]
    decision = m.NativeDecisionRequest(
        request_digest=job["request_digest"],
        admission_digest=job["admission"]["digest"],
        report_digest=None,
        disposition="watch",
        reason="Await a separately approved package",
    )
    saved, fresh = service.decide(key, decision, str(uuid4()))
    assert fresh and saved["decision"] is not None
    original = service.artifact(key, "decision")
    service.close()
    reopened = m.NativeDailyService(root)
    assert reopened.read(key)["state"] == "not_run"
    assert reopened.artifact(key, "admission") == admission
    assert reopened.artifact(key, "decision") == original
    assert reopened.read(key)["trial_consumed"] is False
    reopened.close()


def test_same_id_is_idempotent_and_changed_body_conflicts(tmp_path):
    m = implementation()
    service = m.NativeDailyService(tmp_path / "study")
    try:
        key = str(uuid4())
        request = m.NativeRequest()
        first, _ = service.submit(request, key)
        second, created = service.submit(request, key)
        assert not created and first == second
        forged = {"digest": "a" * 64, "byte_length": 1, "media_type": "application/json"}
        with pytest.raises(m.NativeError, match="idempotency_conflict"):
            service.submit(m.NativeRequest(package_ref=forged), key)
        other, _ = service.submit(m.NativeRequest(package_ref=forged), str(uuid4()))
        assert other["state"] == "not_run"
        assert not other["trial_consumed"]
    finally:
        service.close()


def test_admission_tampering_fails_closed(tmp_path):
    m = implementation()
    service = m.NativeDailyService(tmp_path / "study")
    try:
        job, _ = service.submit(m.NativeRequest(), str(uuid4()))
        path = service.objects.path_for(m.ObjectRef.model_validate(job["admission"]))
        path.write_bytes(b"{}")
        with pytest.raises(m.NativeError, match="artifact_invalid"):
            service.read(job["job_id"])
    finally:
        service.close()


def test_request_cannot_supply_paths_or_qualification_flags():
    m = implementation()
    with pytest.raises(ValueError):
        m.NativeRequest(package_path="private.csv", qualified=True)


def test_ordinary_workstation_api_saves_and_downloads_missing_input(tmp_path):
    m = implementation()
    from fastapi.testclient import TestClient

    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount

    service = m.NativeDailyService(tmp_path / "study")
    app = create_workstation_app(
        account=PaperAccount(cash=100000), native_daily_service=service, host="127.0.0.1"
    )
    key = str(uuid4())
    with TestClient(app) as client:
        options = client.get("/api/research/native-daily/options").json()
        assert options["configured"] and not options["real_input_enabled"]
        response = client.post(
            "/api/research/native-daily/jobs", json={}, headers={"Idempotency-Key": key}
        )
        assert response.status_code == 201
        job = response.json()
        assert job["state"] == "not_run" and not job["trial_consumed"]
        raw = client.get(f"/api/research/native-daily/jobs/{key}/artifact?kind=admission")
        assert raw.status_code == 200
        assert (
            m.digest(raw.content) == job["admission"]["digest"] == raw.headers["X-Content-SHA256"]
        )
        repeat = client.post(
            "/api/research/native-daily/jobs", json={}, headers={"Idempotency-Key": key}
        )
        assert repeat.status_code == 200 and repeat.json() == job


@pytest.mark.parametrize(
    "payload,headers",
    [
        ('{"candidate":"other","candidate":"doublema_daily_overlay_candidate_v1"}', {}),
        ('{"padding":"' + "x" * 8192 + '"}', {}),
        ("{}", {"Origin": "https://untrusted.example"}),
    ],
)
def test_api_write_guards_do_not_create_intents(tmp_path, payload, headers):
    m = implementation()
    from fastapi.testclient import TestClient

    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount

    service = m.NativeDailyService(tmp_path / "study")
    app = create_workstation_app(account=PaperAccount(cash=100000), native_daily_service=service)
    with TestClient(app) as client:
        response = client.post(
            "/api/research/native-daily/jobs",
            content=payload,
            headers={
                "Idempotency-Key": str(uuid4()),
                "Content-Type": "application/json",
                **headers,
            },
        )
        assert response.status_code in (403, 422)
        assert not service._store.path.exists()


def test_registered_substitute_uses_one_ten_arm_cashbook_and_cold_reopens(tmp_path, monkeypatch):
    m = implementation()
    from quantmesh.data.objects import ObjectStore
    from quantmesh.research import spy_replay_engine as engine

    root = tmp_path / "study"
    registered = m.engineering_registration(ObjectStore(tmp_path / "inputs"), output_root=root)
    service = m.NativeDailyService(root, registered=(registered,))
    calls = []
    original = engine.run_cashbook

    def counted(*args, **kwargs):
        calls.append(kwargs["cost_bps"])
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "run_cashbook", counted)
    key = str(uuid4())
    job, fresh = service.submit(registered.request, key)
    assert fresh and job["state"] == "succeeded" and job["trial_consumed"]
    assert calls == [5] * 5 + [10] * 5
    raw = service.artifact(key, "report")
    report = json.loads(raw)
    assert report["evidence_kind"] == "engineering_fixture"
    assert report["financial_qualification"] == "INSUFFICIENT"
    assert not report["paper_allowed"] and not report["live_allowed"]
    assert list(
        report["calculation"]["base5"]["TO"]["trades"][i]["quantity"] for i in range(4)
    ) == [333, 33, -33, -333]
    assert report["calculation"]["base5"]["TO"]["metrics"]["friction_usd"] == pytest.approx(63.4725)
    repeated, created = service.submit(registered.request, key)
    assert not created and repeated == job and len(calls) == 10
    denied, _ = service.submit(registered.request, str(uuid4()))
    assert denied["state"] == "not_run" and not denied["trial_consumed"]
    assert "trial_already_reserved" in denied["admission_reasons"]
    assert len(calls) == 10
    decision, _ = service.decide(
        key,
        m.NativeDecisionRequest(
            request_digest=job["request_digest"],
            admission_digest=job["admission"]["digest"],
            report_digest=job["report"]["digest"],
            disposition="reject",
            reason="Engineering only",
        ),
        str(uuid4()),
    )
    decision_raw = service.artifact(key, "decision")
    service.close()
    monkeypatch.setattr(
        engine, "run_cashbook", lambda *a, **k: pytest.fail("cold read recalculated")
    )
    cold = m.NativeDailyService(root)
    assert cold.read(key)["state"] == "succeeded"
    assert cold.read(key)["decision"] == decision["decision"]
    assert cold.artifact(key, "report") == raw
    assert cold.artifact(key, "decision") == decision_raw
    cold.close()


def test_registration_is_bound_to_candidate_grant_and_output_root(tmp_path):
    m = implementation()
    from dataclasses import replace

    from quantmesh.data.objects import ObjectStore

    registration = m.engineering_registration(
        ObjectStore(tmp_path / "inputs"), output_root=tmp_path / "study"
    )
    invalid = replace(registration, grant_ref=registration.package_ref)
    service = m.NativeDailyService(tmp_path / "study", registered=(invalid,))
    job, _ = service.submit(invalid.request, str(uuid4()))
    assert job["state"] == "not_run" and not job["trial_consumed"]
    service.close()
    moved = m.NativeDailyService(tmp_path / "other-root", registered=(registration,))
    job, _ = moved.submit(registration.request, str(uuid4()))
    assert job["state"] == "not_run" and not job["trial_consumed"]
    moved.close()


def test_interrupted_reserved_trial_is_not_refunded_or_recomputed(tmp_path, monkeypatch):
    m = implementation()
    from quantmesh.data.objects import ObjectStore

    root = tmp_path / "study"
    registration = m.engineering_registration(ObjectStore(tmp_path / "inputs"), output_root=root)
    service = m.NativeDailyService(root, registered=(registration,))
    key = str(uuid4())

    def lost_process(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(service, "_compute", lost_process)
    with pytest.raises(KeyboardInterrupt):
        service.submit(registration.request, key)
    service.close()
    cold = m.NativeDailyService(root, registered=(registration,))
    assert cold.read(key)["state"] == "interrupted"
    assert cold.read(key)["trial_consumed"]
    same, created = cold.submit(registration.request, key)
    assert not created and same["state"] == "interrupted"
    changed, _ = cold.submit(registration.request, str(uuid4()))
    assert changed["state"] == "not_run" and not changed["trial_consumed"]
    cold.close()


def test_standard_launcher_enables_storage_and_refuses_resettable_demo_root(tmp_path, monkeypatch):
    m = implementation()
    import uvicorn
    from fastapi.testclient import TestClient

    from quantmesh.api import workstation

    seen = []

    def serve(application, **kwargs):
        with TestClient(application) as client:
            seen.append(client.get("/api/research/native-daily/options").json())

    monkeypatch.setattr(uvicorn, "run", serve)
    root = tmp_path / "study"
    workstation.main(["--native-daily-root", str(root)])
    assert seen[0]["configured"] and not seen[0]["real_input_enabled"]
    reopened = m.NativeDailyService(root)
    reopened.close()
    with pytest.raises(SystemExit):
        workstation.main(
            [
                "--demo",
                "--demo-root",
                str(tmp_path / "demo"),
                "--native-daily-root",
                str(tmp_path / "demo" / "study"),
            ]
        )
    assert len(seen) == 1


def bound_input_fixture(m, root, *, evidence_kind="engineering_fixture", **changes):
    """Author supplied substitute for the real-shaped adapter; no actual source/grant."""
    from quantmesh.data.objects import ObjectStore

    store = ObjectStore(root / "inputs")
    legacy = m.engineering_registration(store, output_root=root / "study")
    old = json.loads(store.get_bytes(legacy.package_ref))
    schedule = json.loads(store.get_bytes(m.ObjectRef.model_validate(old["inputs"]["schedule"])))
    # A distinct authored price tape proves this adapter is not locked to _V1_INPUTS.
    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(store.get_bytes(m.ObjectRef.model_validate(old["inputs"]["bars"])).decode())
        )
    )
    changed_bars = io.StringIO(newline="")
    writer = csv.DictWriter(changed_bars, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        for price in ("open", "high", "low", "close"):
            row[price] = str(float(row[price]) + 0.25)
        writer.writerow(row)
    changed_ref = store.put_bytes("text/csv", changed_bars.getvalue().encode())
    assert changed_ref.digest != old["inputs"]["bars"]["digest"]
    old["inputs"]["bars"] = changed_ref.model_dump()

    def put(value):
        return store.put_bytes("application/json", m.canonical(value))

    review = put({"kind": "offline_substitute_review", "not_actual_market_or_human_grant": True})
    exposure = put({"kind": "offline_exposure_control", "sample_role": "engineering_control"})
    ledger = put({"kind": "offline_trial_control", "no_empirical_trial": True})
    window = {
        "warmup_start": schedule[0]["date"],
        "score_start": schedule[100]["date"],
        "score_end": schedule[-1]["date"],
        "warmup": 100,
        "observations": 21,
    }
    value = {
        "schema_id": "qm.native-daily.real-input.v1",
        "candidate": m.CANDIDATE,
        "evidence_kind": evidence_kind,
        "inputs": old["inputs"],
        "instrument": "ENGINEERING.CONTROL",
        "source_id": "author_offline_control",
        "source_use": "offline_engineering_only",
        "currency": "USD",
        "price_adjustment": "raw",
        "volume_unit": "shares",
        "historical_trade_venues": "constructed; no market coverage assertion",
        "action_coverage": "complete_cash_ex_pay_no_splits",
        "calendar_id": "XNYS",
        "calendar_timezone": "America/New_York",
        "calendar_version": "offline_control",
        "availability_assumption": "completed_close_plus30min_assumed",
        "pit_status": "unknown",
        "revision_note": "constructed fixture, no real PIT claim",
        "review_refs": [review.model_dump()],
        "source_asset_refs": [review.model_dump()],
        "window": window,
        "sample_role": "engineering_control",
        "exposure_ref": exposure.model_dump(),
        "trial_ledger_ref": ledger.model_dump(),
        **changes,
    }
    manifest = m.RealInput.model_validate(value)
    package = put(manifest.model_dump(mode="json"))
    scope = {
        "schema_id": "qm.native-daily.research-scope.v1",
        "candidate": m.CANDIDATE,
        "package_ref": package.model_dump(),
        "source_id": manifest.source_id,
        "source_use": manifest.source_use,
        "instrument": manifest.instrument,
        "window_digest": m.digest(m.canonical(window)),
        "sample_role": manifest.sample_role,
        "exposure_ref": exposure.model_dump(),
        "trial_ledger_ref": ledger.model_dump(),
        "output_root_digest": m._root_pin(root / "study"),
    }
    scope_ref = put(scope)
    authority = put(
        {
            "schema_id": "qm.native-daily.scope-authority.v1",
            "candidate": m.CANDIDATE,
            "approved_scope_ref": scope_ref.model_dump(),
            "review_refs": [review.model_dump()],
            "decision": "APPROVED_OFFLINE_ENGINEERING"
            if evidence_kind == "engineering_fixture"
            else "APPROVED_DECLARED_RESEARCH",
        }
    )
    grant = put(
        {
            "schema_id": "qm.native-daily.bound-grant.v1",
            **{k: v for k, v in scope.items() if k != "schema_id"},
            "approved_scope_ref": scope_ref.model_dump(),
            "authority_ref": authority.model_dump(),
            "max_trials": 1,
        }
    )
    return m.register_bound_input(
        store,
        package_ref=package,
        grant_ref=grant,
        approved_scope_ref=scope_ref,
        authority_ref=authority,
    )


def test_real_shaped_adapter_and_scoped_grant_use_substitute_without_v1_pins(tmp_path):
    m = implementation()
    registration = bound_input_fixture(m, tmp_path)
    service = m.NativeDailyService(tmp_path / "study", registered=(registration,))
    try:
        job, _ = service.submit(registration.request, str(uuid4()))
        assert job["state"] == "succeeded" and job["trial_consumed"]
        report = json.loads(service.artifact(job["job_id"], "report"))
        assert report["input_facts"]["pit_status"] == "unknown"
        assert report["input_facts"]["source_id"] == "author_offline_control"
        assert report["input_facts"]["window"]["observations"] == 21
    finally:
        service.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"volume_unit": "unknown"},
        {"price_adjustment": "adjusted"},
        {"historical_trade_venues": ""},
        {"review_refs": []},
        {"action_coverage": "unknown"},
        {"calendar_timezone": "UTC"},
    ],
)
def test_real_input_facts_must_bind_the_existing_units_actions_and_calendar(tmp_path, changes):
    m = implementation()
    with pytest.raises(ValueError):
        bound_input_fixture(m, tmp_path, **changes)


def test_reviewed_real_contract_does_not_enable_an_actual_trial(tmp_path):
    m = implementation()
    registration = bound_input_fixture(m, tmp_path, evidence_kind="reviewed_real")
    service = m.NativeDailyService(tmp_path / "study", registered=(registration,))
    try:
        job, _ = service.submit(registration.request, str(uuid4()))
        assert job["state"] == "not_run" and not job["trial_consumed"]
        assert "real_execution_not_enabled" in job["admission_reasons"]
    finally:
        service.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "different-source"),
        ("instrument", "DIFFERENT.CONTROL"),
        ("window_digest", "f" * 64),
        ("sample_role", "different-sample-role"),
        ("exposure_ref", None),
        ("trial_ledger_ref", None),
        ("candidate", "legacy-SPY"),
    ],
)
def test_bound_grant_cannot_change_source_asset_window_role_or_exposure(tmp_path, field, value):
    m = implementation()
    registration = bound_input_fixture(m, tmp_path)
    grant = json.loads(registration.store.get_bytes(registration.grant_ref))
    grant[field] = value
    changed = registration.store.put_bytes("application/json", m.canonical(grant))
    forged = m.register_bound_input(
        registration.store,
        package_ref=registration.package_ref,
        grant_ref=changed,
        approved_scope_ref=registration.approved_scope_ref,
        authority_ref=registration.authority_ref,
    )
    service = m.NativeDailyService(tmp_path / "study", registered=(forged,))
    try:
        job, _ = service.submit(forged.request, str(uuid4()))
        assert job["state"] == "not_run" and not job["trial_consumed"]
        assert job["report"] is None
    finally:
        service.close()


def test_bound_report_cold_reader_does_not_use_calendar_or_calculator(tmp_path, monkeypatch):
    m = implementation()
    from quantmesh.research import native_daily_candidate as native

    registration = bound_input_fixture(m, tmp_path)
    service = m.NativeDailyService(tmp_path / "study", registered=(registration,))
    key = str(uuid4())
    job, _ = service.submit(registration.request, key)
    assert job["state"] == "succeeded"
    original = service.artifact(key, "report")
    service.close()
    monkeypatch.setattr(
        native, "_calculate_matrix", lambda *a: pytest.fail("recomputed on cold read")
    )
    monkeypatch.setattr(
        native, "CalendarService", lambda: pytest.fail("regenerated calendar on cold read")
    )
    cold = m.NativeDailyService(tmp_path / "study")
    assert cold.artifact(key, "report") == original
    assert cold.read(key)["state"] == "succeeded"
    cold.close()


def test_bound_protocol_binds_runtime_and_refuses_drift_before_trial(tmp_path, monkeypatch):
    m = implementation()
    registration = bound_input_fixture(m, tmp_path)
    protocol = json.loads(registration.store.get_bytes(registration.protocol_ref))
    assert protocol["runtime"] == m.runtime_versions()
    assert set(protocol["runtime"]) == {"python", "pandas", "numpy", "calendar"}
    changed = {**protocol["runtime"], "pandas": "different-runtime-control"}
    monkeypatch.setattr(m, "runtime_versions", lambda: changed)
    service = m.NativeDailyService(tmp_path / "study", registered=(registration,))
    job, _ = service.submit(registration.request, str(uuid4()))
    assert job["state"] == "not_run" and not job["trial_consumed"]
    rebound = m.register_bound_input(
        registration.store,
        package_ref=registration.package_ref,
        grant_ref=registration.grant_ref,
        approved_scope_ref=registration.approved_scope_ref,
        authority_ref=registration.authority_ref,
    )
    assert rebound.protocol_ref.digest != registration.protocol_ref.digest
    service.close()


def test_cold_generic_report_keeps_archived_runtime_after_environment_change(tmp_path, monkeypatch):
    m = implementation()
    registration = bound_input_fixture(m, tmp_path)
    service = m.NativeDailyService(tmp_path / "study", registered=(registration,))
    job, _ = service.submit(registration.request, str(uuid4()))
    assert job["state"] == "succeeded"
    original = service.artifact(job["job_id"], "report")
    protocol = registration.store.get_bytes(registration.protocol_ref)
    service.close()
    monkeypatch.setattr(
        m, "runtime_versions", lambda: pytest.fail("cold reader consulted current runtime")
    )
    cold = m.NativeDailyService(tmp_path / "study")
    assert cold.artifact(job["job_id"], "report") == original
    assert cold.objects.get_bytes(registration.protocol_ref) == protocol
    cold.close()


def test_runtime_unknown_draft_protocol_is_read_only_and_not_backfilled(tmp_path):
    m = implementation()
    from dataclasses import replace

    registration = bound_input_fixture(m, tmp_path)
    protocol = json.loads(registration.store.get_bytes(registration.protocol_ref))
    del protocol["runtime"]
    protocol["schema_id"] = "qm.native-daily.real-protocol.v2"
    original = m.canonical(protocol)
    reference = registration.store.put_bytes("application/json", original)
    draft = replace(registration, protocol_ref=reference)
    service = m.NativeDailyService(tmp_path / "study", registered=(draft,))
    try:
        facts, _ = service._binding(draft.request, registration.store, executing=False)
        assert facts["schema_id"] == "qm.native-daily.real-input.v1"
        job, _ = service.submit(draft.request, str(uuid4()))
        assert job["state"] == "not_run" and not job["trial_consumed"]
        assert registration.store.get_bytes(reference) == original
    finally:
        service.close()
