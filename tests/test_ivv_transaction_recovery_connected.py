"""Offline native-metadata/SDK seams; no real input acceptance or financial trial."""

import json
from pathlib import Path

import pytest
from test_ivv_capture_contract import SCHEDULE, facts
from test_ivv_recovery_capture import connected_recovery_capture

from quantmesh.data.objects import ObjectRef, ObjectStore
from quantmesh.research import ivv_admission as gate
from quantmesh.research import ivv_recovery as recovery
from quantmesh.research import native_daily_real as daily


def test_actual_capture_seal_objects_pass_product_verifier(tmp_path, monkeypatch):
    value = connected_recovery_capture(tmp_path, monkeypatch)
    originals = [(p, p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()]
    store = ObjectStore(tmp_path / "product-objects")
    for path, raw in originals:
        media = "application/json" if path.suffix == ".json" else "application/octet-stream"
        store.put_bytes(media, raw)

    def archive(path):
        return store.put_bytes("application/json", Path(path).read_bytes())

    policy = archive(value["policy_ref"]["path"])
    capture_go = archive(value["go_ref"]["path"])
    parent = archive(value["parent_ref"]["path"])
    raw = archive(value["root"] / "capture-manifest.json")
    # Private authority is an unavailable external dependency in committed tests,
    # modeled at the same boundary as the issuer fixture. Every capture/policy/
    # normal-close object below still uses the real content-addressed reader.
    authorization = ObjectRef(
        digest=recovery.AUTHORITY, byte_length=4118, media_type="application/json"
    )
    load = gate._load

    def read_with_authored_private_authority(objects, ref):
        if ref == authorization:
            return {"authored_private_authority_control": True}
        return load(objects, ref)

    monkeypatch.setattr(gate, "_load", read_with_authored_private_authority)
    proofs = gate.TrustedIVVProofs(
        scope_ref=policy,
        capture_policy_ref=policy,
        recovery_policy_ref=policy,
        effect_ref=authorization,
        execution_ref=authorization,
        authorization_ref=authorization,
        go_ref=capture_go,
        acceptance_ref=capture_go,  # Unused by this capture-only verifier.
        windows_policy_ref=capture_go,
        expected_go_sha256=capture_go.digest,
        expected_acceptance_sha256=capture_go.digest,
        expected_policy_sha256=policy.digest,
        expected_authorization_sha256=authorization.digest,
    )
    actual_raw = json.loads(store.get_bytes(raw))
    rec = actual_raw["recovery"]
    refs, usage = gate._recovery_capture_objects(
        store,
        {
            "capture_refs": [raw.model_dump()],
            "capture_go_refs": [capture_go.model_dump()],
            "parent_close_refs": [parent.model_dump()],
            "capture_epoch": rec["batch_id"] + "/" + rec["connection_attempt_id"],
        },
        proofs,
        recovery.validate_policy(json.loads(store.get_bytes(policy))),
    )
    assert parent in refs and raw in refs
    assert usage == [
        {
            "capture_ref": raw.model_dump(),
            "contexts": 1,
            "business_requests": 7,
            "init_connect": 1,
            "keepalive": 0,
        }
    ]
    plain = json.loads((value["root"] / actual_raw["plain_ref"]["path"]).read_bytes())
    declared_facts = facts(value["helper"], plain)
    normalized = value["helper"].normalize_recovery_capture(
        plain, schedule=SCHEDULE, source_facts=declared_facts
    )
    assert len(normalized["bars"]) == 121
    assert normalized["bars"][0]["date"] == "2026-05-08"
    assert normalized["bars"][-1]["date"] == "2026-10-29"
    assert normalized["bars"][0]["close"] == 11.0
    assert normalized["bars"][0]["volume"] == 1000
    staged_ref = gate.stage_ivv_input_set(
        store,
        normalized=normalized,
        source_facts={
            "currency": "USD",
            "volume_unit": "shares",
            "historical_trade_venues": declared_facts["volume_venue"],
            "action_coverage": "complete_cash_ex_pay_no_splits",
            "pit_status": "unknown",
            "revision_note": "authored SDK/OS controls, no real input acceptance",
        },
        capture_ref=raw,
        exposure_ref=raw,
        trial_ledger_ref=raw,
    )
    staged = json.loads(store.get_bytes(staged_ref))
    semantic = {k: staged["facts"][k] for k in recovery.SEMANTIC_FIELDS}
    candidate = value["task"].build_input_manifest(
        recovery,
        semantic,
        [[raw.model_dump(), capture_go.model_dump(), parent.model_dump()]],
        store.put_bytes("application/json", daily.canonical(declared_facts)).model_dump(),
        lambda ref: store.get_bytes(ObjectRef.model_validate(ref)),
    )
    assert candidate["capture_epoch"] == "ivv-recovery-batch-01/connection-000001"
    assert candidate["asof_pit"]["status"] == "unknown"
    assert "review_refs" not in staged["facts"] and "grant_ref" not in staged
    study_root = tmp_path / "no-study"
    monkeypatch.setattr(recovery, "STUDY_ROOT", str(study_root))
    with pytest.raises(daily.NativeError, match="ivv_not_admitted"):
        gate.bind_reviewed_ivv_input(
            store, input_set_ref=staged_ref, proofs=proofs, output_root=study_root
        )
    assert not study_root.exists()
