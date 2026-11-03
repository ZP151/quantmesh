"""Authored identity checks only; no actual capture, registration or trial."""

import pytest

from quantmesh.research import ivv_admission as gate
from quantmesh.research import native_daily_real as daily

AUTH = "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832"
DESCRIPTOR = "76944da09e615b0fec9c60a6ed7ea78d7fa364543684b4d4e5832618860dfa12"


def ref(value):
    return daily.ObjectRef(digest=value, byte_length=1, media_type="application/json")


def proofs():
    return gate.TrustedIVVProofs(
        scope_ref=ref(DESCRIPTOR),
        effect_ref=ref(AUTH),
        execution_ref=ref(AUTH),
        go_ref=ref("a" * 64),
        acceptance_ref=ref("b" * 64),
        windows_policy_ref=ref("c" * 64),
        expected_go_sha256="a" * 64,
        expected_acceptance_sha256="b" * 64,
        capture_policy_ref=ref("d" * 64),
        authorization_ref=ref(AUTH),
        expected_policy_sha256="d" * 64,
        expected_authorization_sha256=AUTH,
    )


@pytest.mark.parametrize("kind", ["root-go", "capture", "registration", "input-acceptance"])
def test_new_authority_is_explicit_family_not_legacy_dev(kind):
    assert gate._schema(proofs(), kind) == "qm.ivv." + kind + ".dev-additional-task.v1"


@pytest.mark.parametrize("field", ["scope_ref", "effect_ref", "execution_ref", "authorization_ref"])
def test_additional_family_rejects_cross_task_proof_slots(field):
    wrong = proofs().model_copy(update={field: ref("e" * 64)})
    with pytest.raises(ValueError, match="ivv_proof"):
        gate._schema(wrong, "root-go")


RESEARCH_SCOPE = "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a"
STUDY = (
    "C:/Users/15492/.codex-clean/worktrees/latest-bootstrap/QuantMesh/output/"
    "ivv-additional-study-20261103-01"
)


def test_new_startup_routes_only_new_fixed_scope_and_root(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path

    namespace = runpy.run_path(
        str(Path(__file__).parents[1] / "tools/research/open_ivv_workstation.py")
    )
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    calls = []
    sentinel = object()
    monkeypatch.setattr(
        gate, "bind_reviewed_ivv_input", lambda *a, **kw: calls.append(kw) or sentinel
    )
    monkeypatch.setattr(daily, "NativeDailyService", lambda root, registered: (root, registered))
    value = {
        "schema_id": "qm.ivv.startup.dev-additional-task.v1",
        "scope_id": RESEARCH_SCOPE,
        "inputs_root": str(inputs),
        "study_root": STUDY,
        "input_set_ref": ref("f" * 64).model_dump(),
        "proofs": proofs().model_dump(mode="json"),
    }
    path = tmp_path / "config.json"

    def call(config):
        raw = daily.canonical(config)
        path.write_bytes(raw)
        return namespace["service_from_config"](path, daily.digest(raw))

    assert call(value) == (Path(STUDY), (sentinel,))
    assert len(calls) == 1 and calls[0]["proofs"] == proofs()
    for changed in (
        {"schema_id": "qm.ivv.startup.v1"},
        {"scope_id": gate.SCOPE_ID},
        {"study_root": str(tmp_path / "alias")},
        {
            "proofs": proofs()
            .model_copy(update={"expected_authorization_sha256": gate.TRUSTED_AUTH})
            .model_dump(mode="json")
        },
    ):
        with pytest.raises(ValueError, match="ivv_"):
            call({**value, **changed})
    assert len(calls) == 1
    assert not (tmp_path / "alias").exists()


@pytest.mark.parametrize("mode", ["strict", "legacy-dev", "legacy-trusted"])
def test_legacy_family_dispatch_is_preserved(mode):
    value = proofs()
    if mode == "strict":
        value = value.model_copy(
            update={
                k: None
                for k in (
                    "capture_policy_ref",
                    "authorization_ref",
                    "expected_policy_sha256",
                    "expected_authorization_sha256",
                )
            }
        )
        suffix = ".v1"
    else:
        auth = gate.TRUSTED_AUTH if mode == "legacy-trusted" else "e" * 64
        value = value.model_copy(
            update={"authorization_ref": ref(auth), "expected_authorization_sha256": auth}
        )
        suffix = gate.TRUSTED_SUFFIX if mode == "legacy-trusted" else ".dev-diagnostic.v1"
    assert gate._schema(value, "capture") == "qm.ivv.capture" + suffix


def test_additional_provenance_is_verified_and_not_downcast():
    value = {
        "policy_sha256": "c784651ae76033a3a3695fad97d19d7721d7de5c28dc4a901408f101c6ae1e55",
        "authorization_sha256": AUTH,
        "diagnostic_mode": "DEV_ADDITIONAL_TRUSTED_ENVIRONMENT",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
        "channel_assurance": "UNVERIFIED_TRUSTED_EXTERNAL",
        "additional_task_id": "ivv-additional-20261103-01",
        "descriptor_sha256": "06f192d60c76a95e91f150e4e4b867218f243759996442abeb58290f7faf6a25",
        "capture_scope_id": "53badf05a10d955cc0826dccc592d1807bfbcfec8abcd4f9e3a194857e3d1858",
        "research_scope_id": RESEARCH_SCOPE,
        "capture_effect_sha256": "a6681407439408a9d01baecedb3026f16f8e9513d601b2edd56910b0228eee17",
        "research_effect_sha256": (
            "03cade7368127b1ed36425ff9f7334892aba51fbbf516376a65b4da992dabbda"
        ),
        "capture_once_key": "189ac10caf73ef7fd31fa01fb4691bb4b00f19a371cc7792330df60bc6d7ac2c",
        "legacy_capture_charge": {"contexts": 1, "business_requests": 7},
        "historical_actual_cumulative": "UNKNOWN",
        "capture_budget": {
            "carrier_submissions": 1,
            "contexts": 1,
            "business_requests": 7,
            "init_connect": 1,
            "keepalive": 96,
        },
    }
    p = proofs().model_copy(
        update={
            "expected_policy_sha256": value["policy_sha256"],
            "capture_policy_ref": ref(value["policy_sha256"]),
        }
    )
    assert gate._dev_binding(p, value) == value
    for key in value:
        wrong = dict(value)
        wrong.pop(key)
        with pytest.raises(ValueError, match="ivv_proof"):
            gate._dev_binding(p, wrong)


def test_additional_windows_runtime_accepts_only_new_policy_and_normal_budget(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from quantmesh.data.objects import ObjectStore

    from quantmesh.research import ivv_runtime as runtime

    monkeypatch.setattr(runtime, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(runtime, "sys", SimpleNamespace(platform="win32"))
    from pathlib import Path

    store = ObjectStore(tmp_path / "objects")

    def put(v):
        return store.put_bytes("application/json", daily.canonical(v))

    policy = {
        "planning_scope_id": RESEARCH_SCOPE,
        "planning_job_uuid": "1d05c58d-b536-4b64-b2c3-89e4217cc4ad",
        "full_execution_approval_sha256": AUTH,
        "research_effect_sha256": (
            "03cade7368127b1ed36425ff9f7334892aba51fbbf516376a65b4da992dabbda"
        ),
        "windows_controls": {
            "job_wide_committed_memory_max": 536870912,
            "affinity_cores": 1,
            "absolute_seconds": 80,
            "paging": "ORDINARY_WINDOWS_OS_MANAGED_ALLOWED",
            "owned_study_artifacts": 8388608,
        },
    }
    policy_ref = put(policy)
    monkeypatch.setattr(runtime, "ADDITIONAL_WINDOWS_POLICY_SHA", policy_ref.digest, raising=False)
    go = put(
        {
            "windows_policy_sha256": policy_ref.digest,
            "numeric_runtime_sha256": daily.digest(Path(runtime.__file__).read_bytes()),
        }
    )
    basis = {
        "scope_id": RESEARCH_SCOPE,
        "job_id": policy["planning_job_uuid"],
        "proofs": proofs()
        .model_copy(update={"windows_policy_ref": policy_ref, "go_ref": go})
        .model_dump(mode="json"),
    }
    owner = runtime.IVVRuntime(tmp_path / "study", basis, store)
    owner.close()
    assert not (tmp_path / "study").exists()
    for key, value in [
        ("planning_scope_id", gate.SCOPE_ID),
        ("planning_job_uuid", "3602f0f7-b888-5df0-9bc4-f8ab84850c39"),
        ("research_effect_sha256", "f" * 64),
    ]:
        wrong = put({**policy, key: value})
        altered = {**basis, "proofs": {**basis["proofs"], "windows_policy_ref": wrong.model_dump()}}
        with pytest.raises(ValueError, match="windows_runtime_authority"):
            runtime.IVVRuntime(tmp_path / "study", altered, store)


def additional_registration(tmp_path, monkeypatch):
    """Entirely authored identity, proofs and bars in a temporary control root."""
    import json
    from pathlib import Path

    from test_ivv_admission import scripted_registration

    from quantmesh.research import ivv_runtime as runtime

    v, m, store, study, job_id, old = scripted_registration(tmp_path, monkeypatch, dev=True)

    def load(r):
        return json.loads(store.get_bytes(m.ObjectRef.model_validate(r)))

    def put(o):
        return store.put_bytes("application/json", m.canonical(o))

    descriptor = put({"authored_descriptor": True})
    authority = put({"authored_authority": True})
    common = {
        **v.ADDITIONAL_PROVENANCE,
        "additional_task_id": "authored-additional-task",
        "authorization_sha256": authority.digest,
        "descriptor_sha256": descriptor.digest,
        "capture_scope_id": "1" * 64,
        "research_scope_id": "2" * 64,
        "capture_effect_sha256": "3" * 64,
        "research_effect_sha256": "4" * 64,
        "capture_once_key": "5" * 64,
    }
    for name, value in {
        "ADDITIONAL_AUTH": authority.digest,
        "ADDITIONAL_DESCRIPTOR": descriptor.digest,
        "ADDITIONAL_DESCRIPTOR_OBJECT": descriptor.digest,
        "ADDITIONAL_PROVENANCE": common,
        "ADDITIONAL_RESEARCH_SCOPE": "2" * 64,
        "ADDITIONAL_STUDY_ROOT": str(study),
        "ADDITIONAL_JOB_ID": job_id,
    }.items():
        monkeypatch.setattr(v, name, value)
    suffix = ".dev-additional-task.v1"

    def schema(kind):
        return "qm.ivv." + kind + suffix

    policy = put(
        {
            **common,
            "schema_id": schema("capture-policy"),
            "scope_id": "1" * 64,
            "execution_sha256": authority.digest,
            "effect_id": "authored-additional-task",
            "legacy_loaded_guard_provenance": "UNKNOWN",
            "exceptions": [
                "provider_32MiB_fullRO_sixRW",
                "legacy_loaded_guard_provenance",
                "external_provider_terminal_ipc_socket_environment",
            ],
            "thresholds": {"G": 10500000000, "P": 4500000000, "free": 53687091200},
        }
    )
    monkeypatch.setattr(v, "ADDITIONAL_POLICY", policy.digest)
    provenance = {**common, "policy_sha256": policy.digest}
    windows = put(
        {
            "planning_scope_id": "2" * 64,
            "planning_job_uuid": job_id,
            "full_execution_approval_sha256": authority.digest,
            "research_effect_sha256": "4" * 64,
        }
    )
    monkeypatch.setattr(runtime, "ADDITIONAL_WINDOWS_POLICY_SHA", windows.digest)
    oldproof = old["proofs"]
    go_body = load(oldproof.go_ref)
    catalog = put({"catalog": "authored"})
    sdk = put({"sdk": "authored"})
    go_body.update(
        provenance,
        schema_id=schema("root-go"),
        scope_id="1" * 64,
        approval_sha256="3" * 64,
        execution_sha256=authority.digest,
        windows_policy_sha256=windows.digest,
        capture_effect_id="authored-additional-task",
        catalog_sha256=catalog.digest,
        numeric_runtime_sha256=m.digest(Path(runtime.__file__).read_bytes()),
    )
    actor = {"pid": 123, "uid": 1000, "start_ticks": 456, "cgroup": "/authored"}
    go_body["capture_actor"] = actor
    go = put(go_body)
    intent = put(
        {
            **provenance,
            "schema_id": schema("capture-intent"),
            "scope_id": "1" * 64,
            "effect_id": "authored-additional-task",
            "state": "ATTEMPTED",
            "synthetic": False,
            "execution_sha256": authority.digest,
            "approval_sha256": "3" * 64,
        }
    )
    local = {"path": "intent.json", "sha256": intent.digest, "bytes": intent.byte_length}
    provider_actor = {"pid": 234, "uid": 1000, "start_ticks": 567, "cgroup": "/authored-provider"}
    plan = put({"schema_id": schema("capture-plan"), "policy_ref": {"sha256": policy.digest}})
    permit = put(
        {
            **provenance,
            "schema_id": schema("root-permit"),
            "actor": actor,
            "root_go_sha256": go.digest,
        }
    )
    provider = put(
        {**provenance, "schema_id": schema("provider-evidence"), "provider_actor": provider_actor}
    )
    evidence = [
        plan,
        permit,
        provider,
        catalog,
        sdk,
        *[put({"authored": k}) for k in ("configuration", "monitor", "kernel_close")],
    ]
    accepted = load(oldproof.acceptance_ref)
    raw_body = load(accepted["capture_ref"])
    raw_body.update(
        provenance,
        schema_id=schema("capture"),
        scope_id="1" * 64,
        effect_id="authored-additional-task",
        intent_ref=local,
        counts={"contexts": 1, "application_sends": 7, "control_sends": {"1001": 1, "1004": 2}},
    )
    binding = raw_body["source_binding"]
    binding.update(
        provenance,
        actor=actor,
        root_go_sha256=go.digest,
        approval_sha256="3" * 64,
        execution_sha256=authority.digest,
        catalog_sha256=catalog.digest,
        root_permit_sha256=permit.digest,
        plan_sha256=plan.digest,
        sdk_pins_sha256=sdk.digest,
        provider_actor=provider_actor,
        provider_evidence_ref={"sha256": provider.digest},
    )
    raw = put(raw_body)
    parent_body = load(accepted["parent_close_ref"])
    parent_body.update(
        provenance,
        capture_actor=actor,
        schema_id=schema("capture-parent-close"),
        scope_id="1" * 64,
        effect_id="authored-additional-task",
        capture_manifest_sha256=raw.digest,
        intent_sha256=intent.digest,
        catalog_sha256=catalog.digest,
        root_permit_sha256=permit.digest,
        evidence_refs=[{"path": "authored.json", "sha256": r.digest} for r in evidence],
        configuration_sha256=evidence[5].digest,
        monitor_sha256=evidence[6].digest,
        kernel_close_sha256=evidence[7].digest,
    )
    parent = put(parent_body)
    package = load(old["package_ref"])
    exposure = put({**load(package["exposure_ref"]), "scope_id": "2" * 64})
    ledger = put(
        {
            **load(package["trial_ledger_ref"]),
            "scope_id": "2" * 64,
            "trial_id": "qm-ivv-trial-" + "2" * 64,
        }
    )
    package.update(
        source_asset_refs=[raw.model_dump()],
        exposure_ref=exposure.model_dump(),
        trial_ledger_ref=ledger.model_dump(),
    )
    accepted.update(
        provenance,
        schema_id=schema("input-acceptance"),
        scope_id="2" * 64,
        capture_scope_id="1" * 64,
        input_set_digest=v.input_set_digest(package),
        capture_ref=raw.model_dump(),
        parent_close_ref=parent.model_dump(),
        parent_evidence_refs=[r.model_dump() for r in evidence],
    )
    acceptance = put(accepted)
    p = v.TrustedIVVProofs(
        scope_ref=descriptor,
        effect_ref=authority,
        execution_ref=authority,
        authorization_ref=authority,
        capture_policy_ref=policy,
        go_ref=go,
        acceptance_ref=acceptance,
        windows_policy_ref=windows,
        expected_go_sha256=go.digest,
        expected_acceptance_sha256=acceptance.digest,
        expected_policy_sha256=policy.digest,
        expected_authorization_sha256=authority.digest,
    )
    package["review_refs"] = [
        r.model_dump() for r in (descriptor, authority, go, acceptance, windows, policy)
    ]
    package_ref = put(package)
    scope = {
        **load(old["approved_scope_ref"]),
        "package_ref": package_ref.model_dump(),
        "exposure_ref": exposure.model_dump(),
        "trial_ledger_ref": ledger.model_dump(),
    }
    scope_ref = put(scope)
    auth_ref = put(
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
            "authority_ref": auth_ref.model_dump(),
            "max_trials": 1,
        }
    )
    return (
        v,
        m,
        store,
        study,
        job_id,
        dict(
            package_ref=package_ref,
            grant_ref=grant,
            approved_scope_ref=scope_ref,
            authority_ref=auth_ref,
            proofs=p,
        ),
    )


def test_additional_registration_authenticates_separate_scopes_and_archives_originals(
    tmp_path, monkeypatch
):
    v, m, store, study, job_id, kwargs = additional_registration(tmp_path, monkeypatch)
    v._verify(store, kwargs["package_ref"], kwargs["proofs"], executing=True)
    registration = v.register_ivv_input(store, **kwargs)
    value = v.verify_saved_binding(
        store, kwargs["package_ref"], registration.real_binding, executing=False
    )
    assert value["scope_id"] == "2" * 64 and value["capture_scope_id"] == "1" * 64
    assert value["capture_usage_ref"] == value["capture_ref"]
    assert value["capture_usage"] == {
        "logical_state": "SPENT",
        "actual_contexts": 1,
        "actual_business_requests": 7,
        "actual_init_connect": 1,
        "actual_keepalive": 2,
    }
    assert value["scope_trial_key"] == m.digest(
        m.canonical(
            {"execution": kwargs["proofs"].execution_ref.digest, "scope": "2" * 64, "trial": 1}
        )
    )
    archive = {ref.digest for ref, body in v.binding_objects(store, registration.real_binding)}
    for name in (
        "scope_ref",
        "effect_ref",
        "execution_ref",
        "authorization_ref",
        "capture_policy_ref",
        "windows_policy_ref",
    ):
        assert getattr(kwargs["proofs"], name).digest in archive
    assert not study.exists()
    import json
    from uuid import uuid4

    from quantmesh.research import native_daily_candidate as native

    service = m.NativeDailyService(study, registered=(registration,))
    computed = []
    original_compute = service._compute

    def observed(registration, job):
        persisted = service._records()
        assert len(persisted) == 1
        assert persisted[0].state == "running"
        assert persisted[0].scope_trial_key == value["scope_trial_key"]
        assert persisted[0].consumed_grant == registration.request.grant_ref.digest
        computed.append(1)
        return original_compute(registration, job)

    monkeypatch.setattr(service, "_compute", observed)
    try:
        job, created = service.submit(registration.request, job_id)
        assert created and job["state"] == "succeeded" and computed == [1]
        decision = m.NativeDecisionRequest(
            request_digest=job["request_digest"],
            admission_digest=job["admission"]["digest"],
            report_digest=job["report"]["digest"],
            disposition="reject",
            reason="Authored additional software control, no financial evidence",
        )
        service.decide(job_id, decision, str(uuid4()))
        originals = {k: service.artifact(job_id, k) for k in ("admission", "report", "decision")}
        assert json.loads(originals["report"])["use_basis"] == value
        assert service.submit(registration.request, job_id)[1] is False
    finally:
        service.close()

    def forbidden(*a, **kw):
        pytest.fail("cold read must not calculate")

    monkeypatch.setattr(native, "_calculate_matrix", forbidden)
    monkeypatch.setattr(native, "CalendarService", forbidden)
    monkeypatch.setattr(v, "prepare_runtime", forbidden)
    cold = m.NativeDailyService(study)
    try:
        assert cold.read(job_id)["state"] == "succeeded"
        assert {k: cold.artifact(job_id, k) for k in originals} == originals
        assert cold.submit(registration.request, job_id)[1] is False
        assert computed == [1]
    finally:
        cold.close()


def test_additional_usage_requires_original_integer_counts_not_nominal_charge():
    good = {"contexts": 1, "application_sends": 7, "control_sends": {"1001": 1, "1004": 96}}
    raw_ref = ref("f" * 64)
    checked = gate._capture_usage(raw_ref, good)
    assert checked["capture_usage_ref"] == raw_ref.model_dump()
    assert checked["capture_usage"]["logical_state"] == "SPENT"
    for bad in (
        {},
        {**good, "contexts": True},
        {**good, "contexts": 0},
        {**good, "application_sends": 8},
        {**good, "application_sends": "7"},
        {**good, "control_sends": {"1001": 1, "1004": 97}},
        {**good, "control_sends": {"1001": True, "1004": 0}},
        {**good, "control_sends": {"1001": 1, "1004": 0, "9999": 1}},
    ):
        with pytest.raises((ValueError, KeyError, TypeError)):
            gate._capture_usage(raw_ref, bad)


def test_additional_go_and_acceptance_content_rejected_before_capture_or_runtime(
    tmp_path, monkeypatch
):
    import json
    from uuid import uuid4

    v, m, store, study, job_id, kwargs = additional_registration(tmp_path, monkeypatch)
    p = kwargs["proofs"]

    def load(r):
        return json.loads(store.get_bytes(m.ObjectRef.model_validate(r)))

    def put(v):
        return store.put_bytes("application/json", m.canonical(v))

    original_package = load(kwargs["package_ref"])

    def forbidden(*a, **kw):
        pytest.fail("bad pre-capture authority reached capture/runtime")

    monkeypatch.setattr(v, "_capture_close", forbidden)
    monkeypatch.setattr(v, "prepare_runtime", forbidden)
    changes = [
        ("go_ref", field, value)
        for field, value in (
            ("numeric_runtime_sha256", "f" * 64),
            ("scope_id", "2" * 64),
            ("approval_sha256", p.effect_ref.digest),
            ("research_effect_sha256", p.effect_ref.digest),
            ("job_id", str(uuid4())),
            ("output_root_digest", "f" * 64),
            ("schema_id", "qm.ivv.root-go.dev-trusted-environment.v1"),
        )
    ]
    changes += [
        ("acceptance_ref", field, value)
        for field, value in (
            ("scope_id", "1" * 64),
            ("capture_scope_id", "2" * 64),
            (
                "checks",
                {
                    k: k not in ("shares_unit", "historical_venues", "all121_ex_pay")
                    for k in v.INPUT_CHECKS
                },
            ),
            ("financial_qualification", "QUALIFIED"),
        )
    ]
    for name, field, value in changes:
        body = load(getattr(p, name))
        body[field] = value
        changed = put(body)
        package = {
            **original_package,
            "review_refs": [
                changed.model_dump() if r["digest"] == getattr(p, name).digest else r
                for r in original_package["review_refs"]
            ],
        }
        proof = p.model_copy(
            update={
                name: changed,
                "expected_go_sha256"
                if name == "go_ref"
                else "expected_acceptance_sha256": changed.digest,
            }
        )
        with pytest.raises(ValueError, match="ivv_proof"):
            v._verify(store, put(package), proof, executing=True)
    assert not study.exists()


def test_private_actual_authority_bytes_and_proof_slots(tmp_path):
    """Private byte witness only; not full input acceptance or a research trial."""
    import os
    from pathlib import Path

    from quantmesh.data.objects import ObjectStore

    location = os.environ.get("QM_IVV_ADDITIONAL_PRIVATE_CONTRACTS")
    if not location:
        pytest.skip("PRIVATE_APPROVAL_FIXTURE_UNAVAILABLE")
    root = Path(location)
    store = ObjectStore(tmp_path / "private-control-objects")

    def original(name, pin, length):
        raw = (root / name).read_bytes()
        assert len(raw) == length and daily.digest(raw) == pin
        return store.put_bytes("application/json", raw)

    a = original("AUTHORIZATION.json", AUTH, 7912)
    d = original("DESCRIPTOR.json", DESCRIPTOR, 3300)
    policy = original(
        "CAPTURE-POLICY.json",
        "c784651ae76033a3a3695fad97d19d7721d7de5c28dc4a901408f101c6ae1e55",
        1547,
    )
    windows = original(
        "WINDOWS-POLICY.json",
        "22f6cb798c94c436759f4ff85d16b6101010ae5e550e5e7d4dc155c71ca54179",
        949,
    )
    p = proofs().model_copy(
        update={
            "scope_ref": d,
            "effect_ref": a,
            "execution_ref": a,
            "authorization_ref": a,
            "capture_policy_ref": policy,
            "expected_policy_sha256": policy.digest,
            "windows_policy_ref": windows,
        }
    )
    gate._verify_additional_originals(store, p)
    provenance = {**gate.ADDITIONAL_PROVENANCE, "policy_sha256": policy.digest}
    checked = gate._verify_dev_policy(
        store,
        p,
        {**provenance, "capture_effect_id": "ivv-additional-20261103-01"},
        provenance,
        {policy.digest, a.digest},
    )
    assert checked == provenance
    assert not (tmp_path / "study").exists()
