"""Connected software originals; modeled SDK/kernel, never real input acceptance."""

import json
from pathlib import Path

import pytest

from quantmesh.data.objects import ObjectStore
from quantmesh.research import ivv_admission as gate
from quantmesh.research import native_daily_real as daily


@pytest.mark.parametrize("private", [False, True], ids=["portable-close", "private-registration"])
def test_source_originals_cross_product_close_registration_and_cold(tmp_path, monkeypatch, private):
    from test_ivv_additional_task import private_inputs
    from test_ivv_dev_diagnostic import leaf
    from test_ivv_trusted_runner import connected_additional_capture

    if private:
        private_inputs()  # Explicit PRIVATE_APPROVAL_FIXTURE_UNAVAILABLE in clean CI.
    raw, intent, parent, go = connected_additional_capture(tmp_path, monkeypatch, private=private)
    capture = tmp_path / "child/capture"
    store = ObjectStore(tmp_path / "consumer-objects")

    def put(value):
        return store.put_bytes("application/json", daily.canonical(value))

    def original(path):
        path = Path(path)
        return store.put_bytes(
            "application/octet-stream" if path.suffix == ".pb" else "application/json",
            path.read_bytes(),
        )

    for path in capture.iterdir():
        original(path)
    # Closed local mapping, never follow paths supplied by the captured body.
    evidence_names = (
        "plan.json",
        "child/permit.json",
        "provider.json",
        "catalog",
        "sdk-pins.json",
        "configuration.json",
        "monitor.json",
        "kernel-close.json",
    )
    evidence = [original(tmp_path / name) for name in evidence_names]
    assert [r.digest for r in evidence] == [r["sha256"] for r in parent["evidence_refs"]]
    raw_ref = original(capture / "capture-manifest.json")
    go_ref = original(tmp_path / "go.json")
    parent_ref = put(parent)
    provenance = {**gate.ADDITIONAL_PROVENANCE, "policy_sha256": gate.ADDITIONAL_POLICY}
    accepted = {
        **provenance,
        "schema_id": "qm.ivv.input-acceptance.dev-additional-task.v1",
        "scope_id": gate.ADDITIONAL_RESEARCH_SCOPE,
        "capture_scope_id": gate.ADDITIONAL_PROVENANCE["capture_scope_id"],
        "parent_close_ref": parent_ref.model_dump(),
        "parent_evidence_refs": [r.model_dump() for r in evidence],
    }
    # The portable half deliberately makes no claim to possess the private A bytes.
    authority = daily.ObjectRef(
        digest=gate.ADDITIONAL_AUTH, byte_length=7912, media_type="application/json"
    )
    descriptor = daily.ObjectRef(
        digest=gate.ADDITIONAL_DESCRIPTOR, byte_length=3300, media_type="application/json"
    )
    windows = daily.ObjectRef(
        digest="22f6cb798c94c436759f4ff85d16b6101010ae5e550e5e7d4dc155c71ca54179",
        byte_length=949,
        media_type="application/json",
    )
    if private:
        controls = Path(__file__).parents[2] / "contracts"
        authority = original(controls / "AUTHORIZATION.json")
        descriptor = original(controls / "DESCRIPTOR.json")
        windows = original(controls / "WINDOWS-POLICY.json")
    policy = original(tmp_path / "policy.json")
    proofs = gate.TrustedIVVProofs(
        scope_ref=descriptor,
        effect_ref=authority,
        execution_ref=authority,
        authorization_ref=authority,
        capture_policy_ref=policy,
        windows_policy_ref=windows,
        go_ref=go_ref,
        expected_go_sha256=go_ref.digest,
        expected_policy_sha256=policy.digest,
        expected_authorization_sha256=authority.digest,
        acceptance_ref=put(accepted),
        expected_acceptance_sha256=put(accepted).digest,
    )
    checked_parent, objects = gate._capture_close(store, raw_ref, accepted, go, proofs)
    assert checked_parent == parent_ref
    assert intent == json.loads(
        store.get_bytes(next(r for r in objects if r.digest == raw["intent_ref"]["sha256"]))
    )
    assert gate._capture_usage(raw_ref, raw["counts"])["capture_usage"] == {
        "logical_state": "SPENT",
        "actual_contexts": 1,
        "actual_business_requests": 7,
        "actual_init_connect": 1,
        "actual_keepalive": 0,
    }
    for change in (
        {"helper_exit_code": 1},
        {"active_owned_processes": 1},
        {"owned_fds_closed": False},
    ):
        with pytest.raises(ValueError, match="ivv_proof"):
            gate._capture_close(
                store,
                raw_ref,
                {**accepted, "parent_close_ref": put({**parent, **change}).model_dump()},
                go,
                proofs,
            )
    if not private:
        return

    facts = {
        "schema_id": "qm.ivv.source-facts.v1",
        "currency": "USD",
        "volume_unit": "shares",
        "historical_trade_venues": "scripted software venue; not actual provider evidence",
        "action_coverage": "complete_cash_ex_pay_no_splits",
        "pit_status": "unknown",
        "revision_note": "constructed SDK responses, no real market qualification",
        "basis": "authored independent H1/H2/H3 facts for software control only",
    }
    facts_ref = put(facts)
    helper = leaf()
    plain = json.loads((capture / "plain.json").read_bytes())
    schedule = json.loads((controls / "SCHEDULE.json").read_bytes())
    dates = (controls / "DATES.txt").read_text().splitlines()
    normalized = helper.normalize_additional_capture(
        plain,
        schedule=schedule,
        source_facts={
            "capture_evidence_sha256": helper.capture_evidence_digest(plain),
            "price_currency": "USD",
            "volume_unit": "shares",
            "volume_venue": facts["historical_trade_venues"],
            "coverage_start": dates[0],
            "coverage_end": dates[-1],
            "evidence_refs": [facts_ref.digest],
        },
    )
    exposure = put(
        {
            "scope_id": gate.ADDITIONAL_RESEARCH_SCOPE,
            "sample_role": "development_only_retrospective",
            "unseen_oos": False,
        }
    )
    ledger = put(
        {
            "scope_id": gate.ADDITIONAL_RESEARCH_SCOPE,
            "trial_id": "qm-ivv-trial-" + gate.ADDITIONAL_RESEARCH_SCOPE,
            "max_trials": 1,
            "state": "UNRESERVED",
        }
    )
    staged = gate.stage_ivv_input_set(
        store,
        normalized=normalized,
        source_facts=facts,
        capture_ref=raw_ref,
        exposure_ref=exposure,
        trial_ledger_ref=ledger,
    )
    accepted.update(
        decision="ACCEPT_FOR_ONE_DECLARED_RETROSPECTIVE_RESEARCH",
        reviewer=gate.REVIEWER,
        input_set_digest=gate._load(store, staged)["input_set_digest"],
        capture_ref=raw_ref.model_dump(),
        source_facts_ref=facts_ref.model_dump(),
        checks={name: True for name in gate.INPUT_CHECKS},
        financial_qualification="INSUFFICIENT",
        paper_allowed=False,
        live_allowed=False,
    )
    acceptance = put(accepted)
    proofs = proofs.model_copy(
        update={"acceptance_ref": acceptance, "expected_acceptance_sha256": acceptance.digest}
    )
    registered = gate.bind_reviewed_ivv_input(
        store, input_set_ref=staged, proofs=proofs, output_root=gate.ADDITIONAL_STUDY_ROOT
    )
    checked = gate.verify_saved_binding(
        store, registered.package_ref, registered.real_binding, executing=True
    )
    assert checked["scope_id"] == gate.ADDITIONAL_RESEARCH_SCOPE
    assert checked["capture_scope_id"] != checked["scope_id"]
    assert checked["capture_usage_ref"] == checked["capture_ref"] == raw_ref.model_dump()
    # The ordinary service archives both the generic package closure and IVV proofs.
    # Invoke its read-only validator without opening a writer or reserving a trial.
    reader = object.__new__(daily.NativeDailyService)
    reader.root = Path(gate.ADDITIONAL_STUDY_ROOT)
    _, package_objects = reader._bound_binding(registered.request, store, executing=True)
    archived = [*package_objects, *gate.binding_objects(store, registered.real_binding)]
    cold = ObjectStore(tmp_path / "cold-objects")
    for ref, body in archived:
        assert cold.put_bytes(ref.media_type, body) == ref
    assert (
        gate.verify_saved_binding(
            cold, registered.package_ref, registered.real_binding, executing=False
        )
        == checked
    )
    assert gate._load(store, ledger)["state"] == "UNRESERVED"
    assert not (tmp_path / "study").exists()
