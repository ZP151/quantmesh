"""Private, reference-bound IVV admission; no market access or grant minting.

Expected GO/acceptance pins come from trusted operator configuration. They are
not browser request fields. Content-addressed data is never its own authority.
"""

import csv
import io
import math
from dataclasses import replace
from pathlib import Path

from quantmesh.research import native_daily_real as daily

SCOPE_ID = "e28541ddae3d7b567e23e2963cc454995aa01c420bd567d8eb8aace6b6354f07"
SOURCE_ID = "moomoo_opend"
SOURCE_USE = "private_diagnostic_internal_once_external_retention_unknown"
WINDOW_SHA = "38f7822357ce458d4fe1d974821e7fda89deb3a31208c68dcea6abb85b04eaf4"
WINDOW = {
    "warmup_start": "2026-05-08",
    "score_start": "2026-10-01",
    "score_end": "2026-10-29",
    "warmup": 100,
    "observations": 21,
}
ORIGINAL_PINS = {
    "scope": "fc2e0942cf1bcd39ddee0bb2a6e327c8ed28e5f1391a38f938777f8a31122971",
    "effect": "37e4667460e66026ba6f281116ceeb6bb525f9aebc1b10d432405a410a139e45",
    "execution": "0f523db13273e7325cad752e529eece44168a17903275d0047adf1e93b50efa3",
}
REVIEWER = "01a14f1c-b716-77f3-9339-416d56fc65fa"
INPUT_CHECKS = (
    "raw_prices",
    "shares_unit",
    "historical_venues",
    "complete_actions",
    "all121_ex_pay",
    "no_splits",
    "normal_close",
    "originals_complete",
    "source_provenance",
    "parent_seal_verified",
)
_REAL_AUTHORITY = object()
TRUSTED_AUTH = "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452"
TRUSTED_SUFFIX = ".dev-trusted-environment.v1"
ADDITIONAL_AUTH = "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832"
ADDITIONAL_DESCRIPTOR = "76944da09e615b0fec9c60a6ed7ea78d7fa364543684b4d4e5832618860dfa12"
ADDITIONAL_SUFFIX = ".dev-additional-task.v1"
ADDITIONAL_POLICY = "c784651ae76033a3a3695fad97d19d7721d7de5c28dc4a901408f101c6ae1e55"
ADDITIONAL_DESCRIPTOR_OBJECT = "06f192d60c76a95e91f150e4e4b867218f243759996442abeb58290f7faf6a25"
ADDITIONAL_JOB_ID = "1d05c58d-b536-4b64-b2c3-89e4217cc4ad"
ADDITIONAL_PROVENANCE = {
    "additional_task_id": "ivv-additional-20261103-01",
    "authorization_sha256": "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832",
    "capture_budget": {
        "business_requests": 7,
        "carrier_submissions": 1,
        "contexts": 1,
        "init_connect": 1,
        "keepalive": 96,
    },
    "capture_effect_sha256": "a6681407439408a9d01baecedb3026f16f8e9513d601b2edd56910b0228eee17",
    "capture_once_key": "189ac10caf73ef7fd31fa01fb4691bb4b00f19a371cc7792330df60bc6d7ac2c",
    "capture_scope_id": "53badf05a10d955cc0826dccc592d1807bfbcfec8abcd4f9e3a194857e3d1858",
    "channel_assurance": "UNVERIFIED_TRUSTED_EXTERNAL",
    "descriptor_sha256": "06f192d60c76a95e91f150e4e4b867218f243759996442abeb58290f7faf6a25",
    "diagnostic_mode": "DEV_ADDITIONAL_TRUSTED_ENVIRONMENT",
    "hard_limit_enforced": False,
    "historical_actual_cumulative": "UNKNOWN",
    "legacy_capture_charge": {"business_requests": 7, "contexts": 1},
    "provider_tail_max": "UNKNOWN",
    "research_effect_sha256": "03cade7368127b1ed36425ff9f7334892aba51fbbf516376a65b4da992dabbda",
    "research_scope_id": "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a",
}
ADDITIONAL_RESEARCH_SCOPE = "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a"
ADDITIONAL_STUDY_ROOT = (
    "C:/Users/15492/.codex-clean/worktrees/latest-bootstrap/QuantMesh/output/"
    "ivv-additional-study-20261103-01"
)


def prepare_runtime(root, basis, store):
    from quantmesh.research.ivv_runtime import IVVRuntime

    return IVVRuntime(root, basis, store)


class TrustedIVVProofs(daily.Contract):
    """Trusted startup refs/pins, never accepted by the public request model."""

    scope_ref: daily.ObjectRef
    effect_ref: daily.ObjectRef
    execution_ref: daily.ObjectRef
    go_ref: daily.ObjectRef
    acceptance_ref: daily.ObjectRef
    windows_policy_ref: daily.ObjectRef
    expected_go_sha256: daily.Digest
    expected_acceptance_sha256: daily.Digest
    capture_policy_ref: daily.ObjectRef | None = None
    authorization_ref: daily.ObjectRef | None = None
    expected_policy_sha256: daily.Digest | None = None
    expected_authorization_sha256: daily.Digest | None = None
    recovery_policy_ref: daily.ObjectRef | None = None


def _schema(proofs, kind):
    dev = proofs.capture_policy_ref is not None
    values = (
        proofs.capture_policy_ref,
        proofs.authorization_ref,
        proofs.expected_policy_sha256,
        proofs.expected_authorization_sha256,
    )
    _require(all(v is not None for v in values) if dev else all(v is None for v in values))
    from quantmesh.research import ivv_recovery as recovery

    if proofs.recovery_policy_ref is not None:
        _require(proofs.scope_ref == proofs.capture_policy_ref == proofs.recovery_policy_ref)
        _require(proofs.recovery_policy_ref.digest == proofs.expected_policy_sha256)
        _require(proofs.authorization_ref == proofs.effect_ref == proofs.execution_ref)
        _require(proofs.expected_authorization_sha256 == proofs.authorization_ref.digest)
        _require(proofs.expected_authorization_sha256 == recovery.AUTHORITY)
        return "qm.ivv." + kind + recovery.FAMILY
    _require(proofs.expected_authorization_sha256 != recovery.AUTHORITY)
    if dev and proofs.expected_authorization_sha256 == ADDITIONAL_AUTH:
        # These slots hold immutable file digests, never logical effect IDs.
        _require(proofs.scope_ref.digest == ADDITIONAL_DESCRIPTOR)
        _require(
            proofs.effect_ref.digest
            == proofs.execution_ref.digest
            == proofs.authorization_ref.digest
            == ADDITIONAL_AUTH
        )
        return "qm.ivv." + kind + ADDITIONAL_SUFFIX
    if dev and proofs.expected_authorization_sha256 == TRUSTED_AUTH:
        return "qm.ivv." + kind + TRUSTED_SUFFIX
    return "qm.ivv." + kind + (".dev-diagnostic.v1" if dev else ".v1")


def _dev_binding(proofs, value, *, policy=None):
    if proofs.capture_policy_ref is None:
        return {}
    if proofs.recovery_policy_ref is not None:
        from quantmesh.research import ivv_recovery as recovery

        _schema(proofs, "provenance")
        _require(policy is not None)
        expected = {
            **recovery.policy_provenance(policy),
            "policy_sha256": proofs.expected_policy_sha256,
        }
        _require(
            all(daily.canonical(value.get(k)) == daily.canonical(v) for k, v in expected.items())
        )
        return expected
    if proofs.expected_authorization_sha256 == ADDITIONAL_AUTH:
        _schema(proofs, "provenance")
        expected = {**ADDITIONAL_PROVENANCE, "policy_sha256": ADDITIONAL_POLICY}
        _require(proofs.expected_policy_sha256 == ADDITIONAL_POLICY)
        _require(proofs.capture_policy_ref.digest == ADDITIONAL_POLICY)
        _require(
            all(daily.canonical(value.get(k)) == daily.canonical(v) for k, v in expected.items())
        )
        return expected
    expected = {
        "policy_sha256": proofs.expected_policy_sha256,
        "authorization_sha256": proofs.expected_authorization_sha256,
        "diagnostic_mode": "DEV_DIAGNOSTIC",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
    }
    if proofs.expected_authorization_sha256 == TRUSTED_AUTH:
        expected.update(
            diagnostic_mode="DEV_TRUSTED_ENVIRONMENT",
            channel_assurance="UNVERIFIED_TRUSTED_EXTERNAL",
        )
    _require(all(value.get(k) == v for k, v in expected.items()))
    _require(value.get("hard_limit_enforced") is False)
    return expected


def _verify_dev_policy(store, proofs, go, acceptance, reviews):
    if proofs.capture_policy_ref is None:
        return {}
    _require(proofs.capture_policy_ref.digest == proofs.expected_policy_sha256)
    _require(proofs.authorization_ref.digest == proofs.expected_authorization_sha256)
    _require(
        proofs.capture_policy_ref.digest in reviews and proofs.authorization_ref.digest in reviews
    )
    _load(store, proofs.authorization_ref)
    policy = _load(store, proofs.capture_policy_ref)
    if proofs.expected_authorization_sha256 == ADDITIONAL_AUTH:
        _require(proofs.expected_policy_sha256 == ADDITIONAL_POLICY)
        _require(policy["schema_id"] == _schema(proofs, "capture-policy"))
        # The policy does not embed its own file digest.
        _dev_binding(proofs, {**policy, "policy_sha256": proofs.expected_policy_sha256})
        _require(policy["scope_id"] == ADDITIONAL_PROVENANCE["capture_scope_id"])
        _require(policy["execution_sha256"] == proofs.execution_ref.digest)
        _require(policy["effect_id"] == go["capture_effect_id"])
        _dev_binding(proofs, acceptance)
        return _dev_binding(proofs, go)
    expected = {
        "schema_id": "qm.ivv.capture-policy.dev-diagnostic.v1",
        "scope_id": SCOPE_ID,
        "execution_sha256": proofs.execution_ref.digest,
        "effect_id": go["capture_effect_id"],
        "authorization_sha256": proofs.expected_authorization_sha256,
        "diagnostic_mode": "DEV_DIAGNOSTIC",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
        "legacy_loaded_guard_provenance": "UNKNOWN",
        "exceptions": ["provider_32MiB_fullRO_sixRW", "legacy_loaded_guard_provenance"],
        "thresholds": {"G": 10500000000, "P": 4500000000, "free": 53687091200},
    }
    if proofs.expected_authorization_sha256 == TRUSTED_AUTH:
        expected.update(
            schema_id=_schema(proofs, "capture-policy"),
            diagnostic_mode="DEV_TRUSTED_ENVIRONMENT",
            channel_assurance="UNVERIFIED_TRUSTED_EXTERNAL",
        )
        expected["exceptions"].append("external_provider_terminal_ipc_socket_environment")
    _require(policy == expected and policy["hard_limit_enforced"] is False)
    _dev_binding(proofs, acceptance)
    return _dev_binding(proofs, go)


def input_set_digest(package):
    """The review signs facts/inputs, excluding its own future reference."""
    value = dict(package)
    value.pop("review_refs", None)
    return daily.digest(daily.canonical(value))


def _load(store, ref):
    reference = daily.ObjectRef.model_validate(ref)
    if reference.media_type != "application/json":
        raise ValueError("proof_media")
    value = daily._loads(daily.NativeDailyService._from_store(store, reference))
    if not isinstance(value, dict):
        raise ValueError("proof_object")
    return value


def _require(condition):
    if not condition:
        raise ValueError("ivv_proof")


def _capture_refs(raw):
    """Read original bytes by hash, never follow paths named by a remote child."""
    refs = []

    def local(value, media="application/json"):
        name = value["path"]
        _require(
            isinstance(name, str)
            and name not in (".", "..")
            and Path(name).name == name
            and "/" not in name
            and "\\" not in name
        )
        ref = daily.ObjectRef(digest=value["sha256"], byte_length=value["bytes"], media_type=media)
        _require(1 <= ref.byte_length <= daily.MAX_OBJECT)
        refs.append(ref)
        return ref

    for key in ("intent_ref", "metadata_ref", "plain_ref", "request_ref"):
        local(raw[key])
    _require(set(raw["responses"]) == {"rehab", "dividends", "splits", "history"})
    for response in raw["responses"].values():
        _require(response["encoding"] == "SDK_PROTOBUF_REENCODING_NOT_NETWORK_FRAME")
        sdk = local(response["sdk_ref"], "application/octet-stream")
        fields = local(response["fields_ref"])
        _require(sdk.byte_length + fields.byte_length <= daily.MAX_OBJECT)
    return refs


def _capture_close(store, raw_ref, acceptance, go, proofs, *, capture_go_ref=None):
    raw = _load(store, raw_ref)
    recovered = proofs.recovery_policy_ref is not None
    policy = _recovery_policy(store, proofs) if recovered else None

    def check_binding(value):
        return _dev_binding(proofs, value, policy=policy)

    additional = proofs.expected_authorization_sha256 == ADDITIONAL_AUTH
    capture_scope = ADDITIONAL_PROVENANCE["capture_scope_id"] if additional else SCOPE_ID
    approval = (
        ADDITIONAL_PROVENANCE["capture_effect_sha256"] if additional else proofs.effect_ref.digest
    )
    if recovered:
        from quantmesh.research import ivv_recovery as recovery

        capture_scope = recovery.capture_scope_id()
        approval = recovery.capture_effect()
    _require(
        raw["schema_id"] == _schema(proofs, "capture") and raw["state"] == "CAPTURED_UNREVIEWED"
    )
    _require(raw["scope_id"] == capture_scope and raw["symbol"] == "US.IVV")
    _require(
        raw["window_digest"] == go["input_window_digest"]
        and raw["full_window_sha256"] == WINDOW_SHA
    )
    _require(raw["requires_parent_close_receipt"] is True and raw["synthetic"] is False)
    _require(raw["primary_failure"] is None and raw["close_failure"] is None)
    _require(
        all(
            raw["normal_close"].get(k) is True
            for k in ("context_closed", "callbacks_stopped", "data_socket_closed")
        )
    )
    check_binding(raw)
    binding = raw["source_binding"]
    check_binding(binding)
    _require(binding["root_go_sha256"] == (capture_go_ref or proofs.go_ref).digest)
    _require(
        binding["approval_sha256"] == approval
        and binding["execution_sha256"] == proofs.execution_ref.digest
    )
    _require(
        binding["catalog_sha256"] == go["catalog_sha256"]
        and binding["capture_helper_sha256"] == go["capture_helper_sha256"]
    )
    parent_ref = daily.ObjectRef.model_validate(acceptance["parent_close_ref"])
    parent = _load(store, parent_ref)
    _require(parent["schema_id"] == _schema(proofs, "capture-parent-close"))
    check_binding(parent)
    _require(parent["state"] == "NORMAL_EXIT" and parent["termination"] == "NORMAL")
    expected = {
        "scope_id": capture_scope,
        "effect_id": raw["effect_id"],
        "capture_manifest_sha256": raw_ref.digest,
        "intent_sha256": raw["intent_ref"]["sha256"],
        "catalog_sha256": binding["catalog_sha256"],
        "helper_sha256": binding["capture_helper_sha256"],
        "root_permit_sha256": binding["root_permit_sha256"],
        "capture_actor": binding["actor"],
    }
    _require(all(parent.get(k) == value for k, value in expected.items()))
    _require(raw["effect_id"] == go["capture_effect_id"])
    for key in ("helper_exit_code", "active_owned_processes"):
        _require(type(parent[key]) is int and parent[key] == 0)
    _require(
        parent["owned_fds_closed"] is True
        and parent["force_killed"] is False
        and parent["resource_limit_event"] is False
    )
    elapsed = parent["elapsed_seconds"]
    _require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 480)
    _require(isinstance(parent["executor_actor"], dict) and bool(parent["executor_actor"]))
    evidence = [daily.ObjectRef.model_validate(r) for r in acceptance["parent_evidence_refs"]]
    _require(1 <= len(evidence) <= 8 and len(evidence) == len(parent["evidence_refs"]))
    _require([r.digest for r in evidence] == [r["sha256"] for r in parent["evidence_refs"]])
    if recovered or proofs.expected_authorization_sha256 in (TRUSTED_AUTH, ADDITIONAL_AUTH):
        _require(len(evidence) == len({r.digest for r in evidence}) == 8)
        _require(
            [r.digest for r in evidence[:5]]
            == [
                binding["plan_sha256"],
                binding["root_permit_sha256"],
                binding["provider_evidence_ref"]["sha256"],
                binding["catalog_sha256"],
                binding["sdk_pins_sha256"],
            ]
        )
        plan, permit, provider = (_load(store, ref) for ref in evidence[:3])
        for obj, kind in (
            (plan, "capture-plan"),
            (permit, "root-permit"),
            (provider, "provider-evidence"),
        ):
            _require(obj.get("schema_id") == _schema(proofs, kind))
        _require(plan["policy_ref"]["sha256"] == proofs.expected_policy_sha256)
        check_binding(permit)
        check_binding(provider)
        _require(permit["actor"] == parent["capture_actor"] == go["capture_actor"])
        _require(permit["root_go_sha256"] == (capture_go_ref or proofs.go_ref).digest)
        _require(provider["provider_actor"] == binding["provider_actor"])
        _require(
            [r.digest for r in evidence[5:]]
            == [
                parent["configuration_sha256"],
                parent["monitor_sha256"],
                parent["kernel_close_sha256"],
            ]
        )
    refs = [parent_ref, *evidence, *_capture_refs(raw)]
    for ref in refs:
        daily.NativeDailyService._from_store(store, ref)
    if proofs.capture_policy_ref is not None:
        intent_ref = raw["intent_ref"]
        intent = _load(
            store,
            daily.ObjectRef(
                digest=intent_ref["sha256"],
                byte_length=intent_ref["bytes"],
                media_type="application/json",
            ),
        )
        _require(intent["schema_id"] == _schema(proofs, "capture-intent"))
        check_binding(intent)
        _require(intent["scope_id"] == capture_scope and intent["effect_id"] == raw["effect_id"])
        _require(
            intent["execution_sha256"] == proofs.execution_ref.digest
            and intent["approval_sha256"] == approval
        )
        _require(intent["state"] == "ATTEMPTED" and intent["synthetic"] is False)
    return parent_ref, refs


def _capture_usage(raw_ref, counts):
    """Accepted originals need actual counts; nominal charge is not observation."""
    controls = counts["control_sends"]
    _require(set(controls) == {"1001", "1004"})
    _require(type(counts["contexts"]) is int and counts["contexts"] == 1)
    _require(type(counts["application_sends"]) is int and counts["application_sends"] == 7)
    _require(type(controls["1001"]) is int and 0 <= controls["1001"] <= 1)
    _require(type(controls["1004"]) is int and 0 <= controls["1004"] <= 96)
    return {
        "capture_usage_ref": raw_ref.model_dump(),
        "capture_usage": {
            "logical_state": "SPENT",
            "actual_contexts": counts["contexts"],
            "actual_business_requests": counts["application_sends"],
            "actual_init_connect": controls["1001"],
            "actual_keepalive": controls["1004"],
        },
    }


def _recovery_policy(store, proofs):
    from quantmesh.research import ivv_recovery as recovery

    _schema(proofs, "recovery-policy")
    policy = recovery.validate_policy(_load(store, proofs.recovery_policy_ref))
    _require(policy["authority_sha256"] == proofs.expected_authorization_sha256)
    _require(daily.digest(daily.canonical(policy)) == proofs.expected_policy_sha256)
    _require(proofs.recovery_policy_ref.byte_length == len(daily.canonical(policy)))
    _load(store, proofs.authorization_ref)
    return policy


def verify_recovery_windows_policy(store, proofs, identity):
    """Check the pinned projection of a trusted policy, not an OS admission."""
    from quantmesh.research import ivv_recovery as recovery

    proofs = TrustedIVVProofs.model_validate(proofs)
    policy = _recovery_policy(store, proofs)
    identity = recovery.validate_identity(identity)
    expected = {
        "schema_id": "qm.ivv.windows-policy" + recovery.FAMILY,
        "logical_task_id": recovery.LOGICAL_TASK_ID,
        "recovery_identity": identity,
        "policy_sha256": proofs.recovery_policy_ref.digest,
        "planning_scope_id": identity["business_key"],
        "planning_job_uuid": recovery.logical_job_id(identity),
        "full_execution_approval_sha256": proofs.authorization_ref.digest,
        "research_effect_sha256": recovery.research_effect(identity),
        "windows_controls": {
            "job_wide_committed_memory_max": policy["actor"]["windows_job_commit_bytes"],
            "affinity_cores": policy["actor"]["windows_affinity_cores"],
            "absolute_seconds": policy["actor"]["numeric_seconds"],
            "owned_study_artifacts": policy["storage"]["study"],
            "paging": "ORDINARY_WINDOWS_OS_MANAGED_ALLOWED",
        },
        "shared_pagefile_growth": "UNKNOWN_NOT_OWNED_ARTIFACTS",
    }
    _require(daily.canonical(_load(store, proofs.windows_policy_ref)) == daily.canonical(expected))
    return policy


def _stored_reference(store, digest, media="application/json"):
    """A digest selects an already held store object, not a remote filename."""
    ref = daily.ObjectRef(digest=digest, byte_length=1, media_type=media)
    path = store.path_for(ref)
    store._reject_symlink_components(path)
    length = path.stat().st_size
    _require(path.is_file() and 1 <= length <= daily.MAX_OBJECT)
    ref = ref.model_copy(update={"byte_length": length})
    daily.NativeDailyService._from_store(store, ref)
    return ref


def _parent_evidence(store, parent_ref):
    """Resolve authenticated digest names within ObjectStore, never child paths."""
    parent = _load(store, parent_ref)
    refs = []
    for item in parent["evidence_refs"]:
        ref = _stored_reference(store, item["sha256"])
        length = ref.byte_length
        if "bytes" in item:
            _require(type(item["bytes"]) is int and item["bytes"] == length)
        refs.append(ref)
    return refs


def _recovery_capture_objects(store, input_manifest, proofs, policy):
    from quantmesh.research import ivv_recovery as recovery

    arrays = [input_manifest[k] for k in ("capture_refs", "capture_go_refs", "parent_close_refs")]
    _require(all(isinstance(a, list) for a in arrays))
    _require(1 <= len(arrays[0]) <= 8 and all(len(a) == len(arrays[0]) for a in arrays))
    epoch = input_manifest["capture_epoch"]
    _require(isinstance(epoch, str) and 1 <= len(epoch) <= 160)
    all_refs, actual_usage = [], []
    for raw_value, go_value, parent_value in zip(*arrays, strict=True):
        raw_ref, go_ref, parent_ref = (
            daily.ObjectRef.model_validate(r) for r in (raw_value, go_value, parent_value)
        )
        raw, capture_go = _load(store, raw_ref), _load(store, go_ref)
        _require(capture_go["schema_id"] == _schema(proofs, "root-go"))
        historical_policy_ref = _stored_reference(store, capture_go["policy_sha256"])
        capture_proofs = proofs.model_copy(
            update={
                "scope_ref": historical_policy_ref,
                "capture_policy_ref": historical_policy_ref,
                "recovery_policy_ref": historical_policy_ref,
                "expected_policy_sha256": historical_policy_ref.digest,
            }
        )
        capture_policy = _recovery_policy(store, capture_proofs)
        _dev_binding(capture_proofs, capture_go, policy=capture_policy)
        expected = {
            "decision": "GO_BOUNDED_CAPTURE_RECOVERY",
            "scope_id": recovery.capture_scope_id(),
            "capture_scope_id": recovery.capture_scope_id(),
            "capture_effect_id": recovery.LOGICAL_TASK_ID + "-capture",
            "approval_sha256": recovery.capture_effect(),
            "execution_sha256": proofs.execution_ref.digest,
        }
        _require(all(capture_go.get(k) == v for k, v in expected.items()))
        rec = raw["recovery"]
        _require(
            set(rec)
            == {
                "logical_task_id",
                "batch_id",
                "connection_attempt_id",
                "policy_sha256",
                "request_journal_ref",
                "history_actual",
            }
        )
        common = {
            "logical_task_id": recovery.LOGICAL_TASK_ID,
            "batch_id": capture_policy["batch"]["batch_id"],
            "connection_attempt_id": rec["connection_attempt_id"],
            "policy_sha256": historical_policy_ref.digest,
        }
        _require(all(rec.get(k) == v for k, v in common.items()))
        _require(
            isinstance(rec["connection_attempt_id"], str) and bool(rec["connection_attempt_id"])
        )
        _require(epoch == rec["batch_id"] + "/" + rec["connection_attempt_id"])
        _require(rec["history_actual"] == "UNKNOWN")
        _require(all(capture_go["recovery"].get(k) == v for k, v in common.items()))
        journal_ref = daily.ObjectRef.model_validate(rec["request_journal_ref"])
        _load(store, journal_ref)
        evidence = _parent_evidence(store, parent_ref)
        accepted = {
            "parent_close_ref": parent_ref.model_dump(),
            "parent_evidence_refs": [r.model_dump() for r in evidence],
        }
        _, refs = _capture_close(
            store, raw_ref, accepted, capture_go, capture_proofs, capture_go_ref=go_ref
        )
        parent = _load(store, parent_ref)
        if "recovery" in parent:
            _require(all(parent["recovery"].get(k) == v for k, v in common.items()))
        counts = raw["counts"]
        controls = counts["control_sends"]
        _require(type(counts["contexts"]) is int and counts["contexts"] == 1)
        _require(
            type(counts["application_sends"]) is int
            and 7 <= counts["application_sends"] <= capture_policy["batch"]["business_requests"]
        )
        _require(type(counts["history_sends"]) is int and counts["history_sends"] == 1)
        _require(set(controls) == {"1001", "1004"})
        _require(
            type(controls["1001"]) is int
            and 0 <= controls["1001"] <= capture_policy["batch"]["init_connect"]
        )
        _require(
            type(controls["1004"]) is int
            and 0 <= controls["1004"] <= capture_policy["batch"]["keepalive"]
        )
        actual_usage.append(
            {
                "capture_ref": raw_ref.model_dump(),
                "contexts": counts["contexts"],
                "business_requests": counts["application_sends"],
                "init_connect": controls["1001"],
                "keepalive": controls["1004"],
            }
        )
        all_refs.extend(
            [
                raw_ref,
                go_ref,
                historical_policy_ref,
                capture_proofs.authorization_ref,
                journal_ref,
                *refs,
            ]
        )
    return all_refs, actual_usage


def _verify_recovery(store, package_ref, proofs, *, executing):
    from quantmesh.research import ivv_recovery as recovery
    from quantmesh.research import ivv_runtime
    from quantmesh.research import native_daily_candidate as native

    policy = _recovery_policy(store, proofs)
    _require(proofs.go_ref.digest == proofs.expected_go_sha256)
    _require(proofs.acceptance_ref.digest == proofs.expected_acceptance_sha256)
    go, accepted = _load(store, proofs.go_ref), _load(store, proofs.acceptance_ref)
    _require(
        go["schema_id"] == _schema(proofs, "root-go")
        and go["decision"] == "GO_RECOVERABLE_AFTER_INPUT_ACCEPTANCE"
    )
    _require(
        accepted["schema_id"] == _schema(proofs, "input-acceptance")
        and accepted["decision"] == "ACCEPT_FOR_DECLARED_RECOVERABLE_RESEARCH"
    )
    provenance = _dev_binding(proofs, go, policy=policy)
    _dev_binding(proofs, accepted, policy=policy)
    identity = recovery.validate_identity(go["recovery_identity"])
    _require(identity == accepted["recovery_identity"])
    package = _load(store, package_ref)
    manifest = daily.RealInput.model_validate(package)
    _require(manifest.evidence_kind == "reviewed_real" and manifest.instrument == "US.IVV")
    _require(manifest.source_id == SOURCE_ID and manifest.source_use == SOURCE_USE)
    _require(manifest.window.model_dump(mode="json") == WINDOW)
    _require(manifest.calendar_version == "exchange-calendars:4.13.2:XNYS")
    _require(manifest.sample_role == "development_only_retrospective")
    semantic = {k: package[k] for k in recovery.SEMANTIC_FIELDS}
    _require(identity["input_version"] == recovery.semantic_input_version(semantic))
    _require(identity["math_cost_spec"] == policy["math_cost_spec"] == recovery.MATH_COST_SPEC)
    refs = {r.digest for r in manifest.review_refs}
    for key in (
        "scope_ref",
        "effect_ref",
        "execution_ref",
        "go_ref",
        "acceptance_ref",
        "windows_policy_ref",
        "recovery_policy_ref",
    ):
        _require(getattr(proofs, key).digest in refs)
    input_ref = daily.ObjectRef.model_validate(go["input_manifest_ref"])
    _require(go["input_manifest_ref"] == accepted["input_manifest_ref"])
    input_manifest = _load(store, input_ref)
    _require(
        set(input_manifest)
        == {
            "schema_id",
            "logical_task_id",
            "semantic",
            "capture_epoch",
            "capture_refs",
            "capture_go_refs",
            "source_facts_ref",
            "parent_close_refs",
            "asof_pit",
        }
    )
    _require(input_manifest["schema_id"] == _schema(proofs, "input-manifest"))
    _require(input_manifest["logical_task_id"] == recovery.LOGICAL_TASK_ID)
    _require(daily.canonical(input_manifest["semantic"]) == daily.canonical(semantic))
    _require(accepted["source_facts_ref"] == input_manifest["source_facts_ref"])
    _require(
        [daily.ObjectRef.model_validate(r) for r in input_manifest["capture_refs"]]
        == manifest.source_asset_refs
    )
    pit = input_manifest["asof_pit"]
    _require(set(pit) == {"status", "provider_asof", "provider_version", "basis_refs"})
    _require(pit["status"] == manifest.pit_status and pit["status"] in {"known", "unknown"})
    for k in ("provider_asof", "provider_version"):
        _require(
            pit[k] is None
            or (
                isinstance(pit[k], str)
                and bool(pit[k].strip())
                and pit[k] != input_manifest["capture_epoch"]
            )
        )
    basis_refs = [daily.ObjectRef.model_validate(r) for r in pit["basis_refs"]]
    if pit["status"] == "known":
        _require(bool(basis_refs) and pit["provider_version"] is not None)
    if pit["provider_asof"] is not None or pit["provider_version"] is not None:
        _require(bool(basis_refs))
    for ref in basis_refs:
        daily.NativeDailyService._from_store(store, ref)
    verify_recovery_windows_policy(store, proofs, identity)
    effect = recovery.research_effect(identity)
    expected = {
        "scope_id": identity["business_key"],
        "research_scope_id": identity["business_key"],
        "research_effect_sha256": effect,
        "approval_sha256": effect,
        "execution_sha256": proofs.execution_ref.digest,
        "job_id": recovery.logical_job_id(identity),
        "capture_scope_id": recovery.capture_scope_id(),
        "capture_effect_id": recovery.LOGICAL_TASK_ID + "-capture",
        "capture_policy_sha256": proofs.recovery_policy_ref.digest,
        "windows_policy_sha256": proofs.windows_policy_ref.digest,
        "output_root_digest": daily._root_pin(recovery.STUDY_ROOT),
        "input_window_digest": daily.digest(daily.canonical(WINDOW)),
        "full_window_sha256": WINDOW_SHA,
    }
    _require(all(go.get(k) == v for k, v in expected.items()))
    _require(all(go["controls"].get(k) is True for k in ("released", "resource_bounds")))
    _require(go["controls"].get("provider_log_cache_bounds") is False)
    recovery.validate_attempt_policy(go["attempt_policy"], policy)
    if executing:
        _require(go["code"] == native._code())
        _require(go["adapter_sha256"] == daily.digest(Path(daily.__file__).read_bytes()))
        _require(go["gate_sha256"] == daily.digest(Path(__file__).read_bytes()))
        _require(
            go["numeric_runtime_sha256"] == daily.digest(Path(ivv_runtime.__file__).read_bytes())
        )
        _require(go["runtime"] == daily.runtime_versions())
        _require(
            identity["math_cost_spec"]
            == daily.digest(daily.canonical(daily._accounting_contract()))
        )
    _require(
        accepted["scope_id"] == identity["business_key"]
        and accepted["capture_scope_id"] == recovery.capture_scope_id()
    )
    _require(
        accepted["reviewer"] == REVIEWER
        and accepted["input_set_digest"] == input_set_digest(package)
    )
    _require(all(accepted["checks"].get(k) is True for k in INPUT_CHECKS))
    _require(
        accepted["financial_qualification"] == "INSUFFICIENT"
        and accepted["paper_allowed"] is False
        and accepted["live_allowed"] is False
    )
    source = _load(store, input_manifest["source_facts_ref"])
    _require(source["schema_id"] == "qm.ivv.source-facts.v1")
    for k in ("currency", "volume_unit", "historical_trade_venues", "action_coverage"):
        _require(source[k] == package[k])
    _require(isinstance(source["basis"], str) and bool(source["basis"].strip()))
    exposure, ledger = _load(store, manifest.exposure_ref), _load(store, manifest.trial_ledger_ref)
    _require(exposure["scope_id"] == identity["business_key"] and exposure["unseen_oos"] is False)
    _require(exposure["sample_role"] == manifest.sample_role)
    _require(
        ledger["scope_id"] == identity["business_key"]
        and ledger["trial_id"] == "qm-ivv-trial-" + identity["business_key"]
    )
    _require(type(ledger["max_trials"]) is int and ledger["max_trials"] == 1)
    _require(
        ledger["state"] in {"REGISTERED", "UNRESERVED"}
    )  # Registration, not proof of unused execution.
    _, usage = _recovery_capture_objects(store, input_manifest, proofs, policy)
    return {
        **provenance,
        "scope_id": identity["business_key"],
        "scope_trial_key": identity["business_key"],
        "job_id": recovery.logical_job_id(identity),
        "output_root_digest": go["output_root_digest"],
        "proofs": proofs.model_dump(mode="json", exclude_none=True),
        "source_facts_ref": input_manifest["source_facts_ref"],
        "capture_ref": input_manifest["capture_refs"][0],
        "parent_close_ref": input_manifest["parent_close_refs"][0],
        "source_use": SOURCE_USE,
        "provider_permission_verified": False,
        "external_API_retention_applicability": "UNKNOWN",
        "recovery_identity": identity,
        "attempt_policy": go["attempt_policy"],
        "recovery_provenance": {
            "input_manifest_ref": input_ref.model_dump(),
            "capture_attempt_refs": input_manifest["capture_refs"],
        },
        "capture_usage": usage,
    }


def _verify_additional_originals(store, proofs):
    """Authenticate immutable new authority files without minting a registration."""
    _require(proofs.expected_authorization_sha256 == ADDITIONAL_AUTH)
    _schema(proofs, "registration")
    descriptor = _load(store, proofs.scope_ref)
    _require(daily.digest(daily.canonical(descriptor)) == ADDITIONAL_DESCRIPTOR_OBJECT)
    _load(store, proofs.effect_ref)
    _load(store, proofs.execution_ref)


def _verify(store, package_ref, proofs, *, executing):
    from quantmesh.research import native_daily_candidate as native

    proofs = TrustedIVVProofs.model_validate(proofs)
    if proofs.recovery_policy_ref is not None:
        return _verify_recovery(store, package_ref, proofs, executing=executing)
    additional = proofs.expected_authorization_sha256 == ADDITIONAL_AUTH
    _schema(proofs, "registration")
    scope_id = ADDITIONAL_RESEARCH_SCOPE if additional else SCOPE_ID
    from quantmesh.research.ivv_runtime import ADDITIONAL_WINDOWS_POLICY_SHA, WINDOWS_POLICY_SHA

    if additional:
        _verify_additional_originals(store, proofs)
        fixed = {"input_window_digest": daily.digest(daily.canonical(WINDOW))}
        expected_policy = ADDITIONAL_WINDOWS_POLICY_SHA
    else:
        originals = {}
        for key in ORIGINAL_PINS:
            ref = getattr(proofs, key + "_ref")
            _require(ref.digest == ORIGINAL_PINS[key])
            originals[key] = _load(store, ref)
        _require(originals["scope"]["selection"]["asset"] == "US.IVV")
        _require(originals["effect"]["scope_approval_sha256"] == proofs.scope_ref.digest)
        _require(originals["effect"]["paper_live"] is False)
        _require(originals["execution"]["approval_sha256"] == proofs.effect_ref.digest)
        fixed = originals["execution"]["fixed_scope"]
        _require(fixed["asset"] == "US.IVV" and fixed["scope_id"] == SCOPE_ID)
        _require(fixed["input_window_digest"] == daily.digest(daily.canonical(WINDOW)))
        expected_policy = WINDOWS_POLICY_SHA
    policy = _load(store, proofs.windows_policy_ref)
    _require(proofs.windows_policy_ref.digest == expected_policy)
    _require(policy["planning_scope_id"] == scope_id)
    _require(policy["full_execution_approval_sha256"] == proofs.effect_ref.digest)
    if additional:
        _require(
            policy["research_effect_sha256"] == ADDITIONAL_PROVENANCE["research_effect_sha256"]
        )
    _require(proofs.go_ref.digest == proofs.expected_go_sha256)
    _require(proofs.acceptance_ref.digest == proofs.expected_acceptance_sha256)
    go, acceptance = _load(store, proofs.go_ref), _load(store, proofs.acceptance_ref)
    package = _load(store, package_ref)
    manifest = daily.RealInput.model_validate(package)
    _require(manifest.evidence_kind == "reviewed_real")
    _require(manifest.instrument == "US.IVV" and manifest.source_id == SOURCE_ID)
    _require(manifest.source_use == SOURCE_USE)
    _require(manifest.window.model_dump(mode="json") == WINDOW)
    _require(manifest.sample_role == "development_only_retrospective")
    _require(manifest.calendar_version == "exchange-calendars:4.13.2:XNYS")
    reviews = {ref.digest for ref in manifest.review_refs}
    _require(
        all(
            getattr(proofs, name).digest in reviews
            for name in (
                "scope_ref",
                "effect_ref",
                "execution_ref",
                "go_ref",
                "acceptance_ref",
                "windows_policy_ref",
            )
        )
    )
    _require(go["schema_id"] == _schema(proofs, "root-go"))
    provenance = _verify_dev_policy(store, proofs, go, acceptance, reviews)
    _require(go["decision"] == "GO_ONCE_AFTER_INPUT_ACCEPTANCE")
    _require(
        go["scope_id"] == (ADDITIONAL_PROVENANCE["capture_scope_id"] if additional else scope_id)
    )
    if additional:
        _require(go["research_scope_id"] == scope_id)
        _require(go["research_effect_sha256"] == ADDITIONAL_PROVENANCE["research_effect_sha256"])
        _require(go["approval_sha256"] == ADDITIONAL_PROVENANCE["capture_effect_sha256"])
        _require(go["job_id"] == ADDITIONAL_JOB_ID)
        _require(go["output_root_digest"] == daily._root_pin(ADDITIONAL_STUDY_ROOT))
    _require(go["execution_sha256"] == proofs.execution_ref.digest)
    _require(go["input_window_digest"] == fixed["input_window_digest"])
    _require(go["full_window_sha256"] == WINDOW_SHA)
    _require(type(go["max_trials"]) is int and go["max_trials"] == 1)
    _require(type(go["max_capture_intents"]) is int and go["max_capture_intents"] == 1)
    _require(
        all(
            go["controls"].get(key) is True
            for key in (
                ("released", "resource_bounds")
                if proofs.capture_policy_ref is not None
                else ("released", "resource_bounds", "provider_log_cache_bounds")
            )
        )
    )
    if proofs.capture_policy_ref is not None:
        _require(go["controls"].get("provider_log_cache_bounds") is False)
    daily._uuid(go["job_id"])
    _require(policy["planning_job_uuid"] == go["job_id"])
    _require(go["windows_policy_sha256"] == proofs.windows_policy_ref.digest)
    if executing:
        if additional:
            from quantmesh.research import ivv_runtime

            _require(
                go["numeric_runtime_sha256"]
                == daily.digest(Path(ivv_runtime.__file__).read_bytes())
            )
        _require(go["code"] == native._code())
        _require(go["adapter_sha256"] == daily.digest(Path(daily.__file__).read_bytes()))
        _require(go["gate_sha256"] == daily.digest(Path(__file__).read_bytes()))
        _require(go["runtime"] == daily.runtime_versions())
    _require(acceptance["schema_id"] == _schema(proofs, "input-acceptance"))
    _require(acceptance["decision"] == "ACCEPT_FOR_ONE_DECLARED_RETROSPECTIVE_RESEARCH")
    _require(acceptance["reviewer"] == REVIEWER and acceptance["scope_id"] == scope_id)
    if additional:
        _require(acceptance["capture_scope_id"] == ADDITIONAL_PROVENANCE["capture_scope_id"])
    _require(acceptance["input_set_digest"] == input_set_digest(package))
    _require(all(acceptance["checks"].get(key) is True for key in INPUT_CHECKS))
    _require(acceptance["financial_qualification"] == "INSUFFICIENT")
    _require(acceptance["paper_allowed"] is False and acceptance["live_allowed"] is False)
    raw_ref = daily.ObjectRef.model_validate(acceptance["capture_ref"])
    _require(raw_ref in manifest.source_asset_refs)
    parent_ref, _ = _capture_close(store, raw_ref, acceptance, go, proofs)
    source = _load(store, acceptance["source_facts_ref"])
    _require(source["schema_id"] == "qm.ivv.source-facts.v1")
    _require(
        source["currency"] == manifest.currency and source["volume_unit"] == manifest.volume_unit
    )
    _require(source["historical_trade_venues"] == manifest.historical_trade_venues)
    _require(source["action_coverage"] == manifest.action_coverage)
    _require(isinstance(source["basis"], str) and bool(source["basis"].strip()))
    exposure, ledger = _load(store, manifest.exposure_ref), _load(store, manifest.trial_ledger_ref)
    _require(exposure["scope_id"] == scope_id and exposure["unseen_oos"] is False)
    _require(exposure["sample_role"] == manifest.sample_role)
    _require(ledger["scope_id"] == scope_id and ledger["trial_id"] == "qm-ivv-trial-" + scope_id)
    _require(type(ledger["max_trials"]) is int and ledger["max_trials"] == 1)
    _require(ledger["state"] == "UNRESERVED")
    if additional:
        raw = _load(store, raw_ref)
        provenance.update(_capture_usage(raw_ref, raw["counts"]))
    return {
        **provenance,
        "scope_id": scope_id,
        "scope_trial_key": daily.digest(
            daily.canonical(
                {
                    "execution": proofs.execution_ref.digest,
                    "scope": scope_id,
                    "trial": 1,
                }
            )
        ),
        "job_id": go["job_id"],
        "output_root_digest": go["output_root_digest"],
        "proofs": proofs.model_dump(mode="json", exclude_none=True),
        "source_facts_ref": acceptance["source_facts_ref"],
        "capture_ref": raw_ref.model_dump(),
        "parent_close_ref": parent_ref.model_dump(),
        "source_use": SOURCE_USE,
        "provider_permission_verified": False,
        "external_API_retention_applicability": "UNKNOWN",
    }


def register_ivv_input(store, *, package_ref, grant_ref, approved_scope_ref, authority_ref, proofs):
    """One operator-configured real registration, after independent acceptance."""
    try:
        evidence = _verify(store, package_ref, proofs, executing=True)
        scope = _load(store, approved_scope_ref)
        _require(scope["output_root_digest"] == evidence["output_root_digest"])
        registration = daily.register_bound_input(
            store,
            package_ref=package_ref,
            grant_ref=grant_ref,
            approved_scope_ref=approved_scope_ref,
            authority_ref=authority_ref,
        )
        record = {
            "schema_id": _schema(TrustedIVVProofs.model_validate(proofs), "registration"),
            **evidence,
        }
        binding = store.put_bytes("application/json", daily.canonical(record))
        recovery = (
            {k: evidence[k] for k in ("recovery_identity", "attempt_policy", "recovery_provenance")}
            if "recovery_identity" in evidence
            else None
        )
        return replace(
            registration, _authority=_REAL_AUTHORITY, real_binding=binding, recovery=recovery
        )
    except (KeyError, TypeError, ValueError, OSError, RecursionError):
        raise daily.NativeError("ivv_not_admitted") from None


def verify_saved_binding(store, package_ref, binding_ref, *, executing):
    """Cold reads validate stored authority bytes, not today's runtime/calendar."""
    record = _load(store, binding_ref)
    _require(
        record.pop("schema_id")
        == _schema(TrustedIVVProofs.model_validate(record["proofs"]), "registration")
    )
    checked = _verify(store, package_ref, record["proofs"], executing=executing)
    _require(record == checked)
    return checked


def binding_objects(store, binding_ref):
    record = _load(store, binding_ref)
    proofs = TrustedIVVProofs.model_validate(record["proofs"])
    if proofs.recovery_policy_ref is not None:
        input_ref = daily.ObjectRef.model_validate(
            record["recovery_provenance"]["input_manifest_ref"]
        )
        manifest = _load(store, input_ref)
        capture_refs, _ = _recovery_capture_objects(
            store, manifest, proofs, _recovery_policy(store, proofs)
        )
        refs = [
            binding_ref,
            input_ref,
            *[
                getattr(proofs, k)
                for k in (
                    "scope_ref",
                    "effect_ref",
                    "execution_ref",
                    "authorization_ref",
                    "capture_policy_ref",
                    "recovery_policy_ref",
                    "go_ref",
                    "acceptance_ref",
                    "windows_policy_ref",
                )
            ],
            daily.ObjectRef.model_validate(manifest["source_facts_ref"]),
            *capture_refs,
            *[daily.ObjectRef.model_validate(r) for r in manifest["asof_pit"]["basis_refs"]],
        ]
        unique = {r.digest: r for r in refs}
        return [(r, daily.NativeDailyService._from_store(store, r)) for r in unique.values()]
    _, capture_refs = _capture_close(
        store,
        daily.ObjectRef.model_validate(record["capture_ref"]),
        _load(store, proofs.acceptance_ref),
        _load(store, proofs.go_ref),
        proofs,
    )
    refs = [
        binding_ref,
        *[
            getattr(proofs, key)
            for key in (
                "scope_ref",
                "effect_ref",
                "execution_ref",
                "go_ref",
                "acceptance_ref",
                "windows_policy_ref",
            )
        ],
        daily.ObjectRef.model_validate(record["source_facts_ref"]),
        *capture_refs,
    ]
    if proofs.capture_policy_ref is not None:
        refs.extend((proofs.capture_policy_ref, proofs.authorization_ref))
    return [(ref, daily.NativeDailyService._from_store(store, ref)) for ref in refs]


def _put(store, value):
    raw = daily.canonical(value)
    _require(0 < len(raw) <= daily.MAX_OBJECT)
    return store.put_bytes("application/json", raw)


def stage_ivv_input_set(
    store, *, normalized, source_facts, capture_ref, exposure_ref, trial_ledger_ref
):
    """Publish an unreviewed input-set, never a grant or a runnable package."""
    try:
        _require(normalized["status"] == "NORMALIZED_UNREVIEWED")
        _require(len(normalized["bars"]) == 121 and len(normalized["schedule"]) == 121)
        text = io.StringIO(newline="")
        names = ["date", "open", "high", "low", "close", "volume", "dividend"]
        writer = csv.DictWriter(text, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in normalized["bars"]:
            _require(set(row) == set(names))
            writer.writerow(row)
        bars = text.getvalue().encode()
        _require(len(bars) <= daily.MAX_OBJECT)
        inputs = {
            "bars": store.put_bytes("text/csv", bars).model_dump(),
            "distributions": _put(store, normalized["distributions"]).model_dump(),
            "schedule": _put(store, normalized["schedule"]).model_dump(),
        }
        _require(source_facts["currency"] == "USD" and source_facts["volume_unit"] == "shares")
        _require(source_facts["action_coverage"] == "complete_cash_ex_pay_no_splits")
        _require(bool(source_facts["historical_trade_venues"].strip()))
        facts = {
            "schema_id": "qm.native-daily.real-input.v1",
            "candidate": daily.CANDIDATE,
            "evidence_kind": "reviewed_real",
            "inputs": inputs,
            "instrument": "US.IVV",
            "source_id": SOURCE_ID,
            "source_use": SOURCE_USE,
            "currency": "USD",
            "price_adjustment": "raw",
            "volume_unit": "shares",
            "historical_trade_venues": source_facts["historical_trade_venues"],
            "action_coverage": source_facts["action_coverage"],
            "calendar_id": "XNYS",
            "calendar_timezone": "America/New_York",
            "calendar_version": "exchange-calendars:4.13.2:XNYS",
            "availability_assumption": "completed_close_plus30min_assumed",
            "pit_status": source_facts["pit_status"],
            "revision_note": source_facts["revision_note"],
            "source_asset_refs": [daily.ObjectRef.model_validate(capture_ref).model_dump()],
            "window": WINDOW,
            "sample_role": "development_only_retrospective",
            "exposure_ref": daily.ObjectRef.model_validate(exposure_ref).model_dump(),
            "trial_ledger_ref": daily.ObjectRef.model_validate(trial_ledger_ref).model_dump(),
        }
        # The facts describe the target manifest. Without review refs this is
        # deliberately NOT a RealInput or a trusted registration.
        return _put(
            store,
            {
                "schema_id": "qm.ivv.unreviewed-input-set.v1",
                "facts": facts,
                "input_set_digest": input_set_digest(facts),
            },
        )
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        raise daily.NativeError("ivv_not_admitted") from None


def bind_reviewed_ivv_input(store, *, input_set_ref, proofs, output_root):
    """Bind already accepted facts to existing internal scope/grant contracts."""
    try:
        staged = _load(store, input_set_ref)
        _require(staged["schema_id"] == "qm.ivv.unreviewed-input-set.v1")
        _require(staged["input_set_digest"] == input_set_digest(staged["facts"]))
        proofs = TrustedIVVProofs.model_validate(proofs)
        facts = dict(staged["facts"])
        _require("review_refs" not in facts)
        facts["review_refs"] = [
            getattr(proofs, key).model_dump()
            for key in (
                "acceptance_ref",
                "scope_ref",
                "effect_ref",
                "execution_ref",
                "go_ref",
                "windows_policy_ref",
            )
        ]
        facts["review_refs"].extend(
            ref.model_dump()
            for ref in (proofs.capture_policy_ref, proofs.authorization_ref)
            if ref is not None
        )
        if proofs.recovery_policy_ref is not None:
            facts["review_refs"].append(proofs.recovery_policy_ref.model_dump())
        facts["review_refs"] = list({r["digest"]: r for r in facts["review_refs"]}.values())
        package_ref = _put(store, facts)
        checked = _verify(store, package_ref, proofs, executing=True)
        _require(checked["output_root_digest"] == daily._root_pin(output_root))
        manifest = daily.RealInput.model_validate(facts)
        scope = {
            "schema_id": "qm.native-daily.research-scope.v1",
            "candidate": daily.CANDIDATE,
            "package_ref": package_ref.model_dump(),
            "source_id": manifest.source_id,
            "source_use": manifest.source_use,
            "instrument": manifest.instrument,
            "window_digest": daily.digest(daily.canonical(facts["window"])),
            "sample_role": manifest.sample_role,
            "exposure_ref": facts["exposure_ref"],
            "trial_ledger_ref": facts["trial_ledger_ref"],
            "output_root_digest": checked["output_root_digest"],
        }
        scope_ref = _put(store, scope)
        authority_ref = _put(
            store,
            {
                "schema_id": "qm.native-daily.scope-authority.v1",
                "candidate": daily.CANDIDATE,
                "approved_scope_ref": scope_ref.model_dump(),
                "review_refs": facts["review_refs"],
                "decision": "APPROVED_DECLARED_RESEARCH",
            },
        )
        grant_ref = _put(
            store,
            {
                **scope,
                "schema_id": "qm.native-daily.bound-grant.v1",
                "approved_scope_ref": scope_ref.model_dump(),
                "authority_ref": authority_ref.model_dump(),
                "max_trials": 1,
            },
        )
        return register_ivv_input(
            store,
            package_ref=package_ref,
            grant_ref=grant_ref,
            approved_scope_ref=scope_ref,
            authority_ref=authority_ref,
            proofs=proofs,
        )
    except (KeyError, TypeError, ValueError, OSError, RecursionError):
        raise daily.NativeError("ivv_not_admitted") from None
