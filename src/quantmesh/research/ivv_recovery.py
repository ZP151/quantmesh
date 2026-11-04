"""Closed IVV recovery identity/policy contract; no storage or authority issuer.

Validation here is structural. Actual protected source/authority/policy provenance,
native admission and independent real-input acceptance remain caller obligations.
"""

import copy
import hashlib
import json
import math
import re
import uuid

FAMILY = ".dev-transaction-recovery.v1"
MODE = "DEV_TRANSACTION_RECOVERY"
AUTHORITY = "6db1254cdf428a17952ae764b10d597435067dc151219c39b3c4fc18c1853dfd"
LOGICAL_TASK_ID = "ivv-trend-staged-20261029"
STUDY_ROOT = (
    "C:/Users/15492/.codex-clean/worktrees/0038-security-runtime-alignment/QuantMesh"
    "/output/ivv-transaction-recovery-20261104-01/study"
)
MATH_COST_SPEC = "7e0c785311bdae85828898bcc63b7a88d724da9bab4f844eb35673c923c34fea"
MIB = 1048576
IDENTITY_FIELDS = frozenset(("logical_task_id", "experiment_id", "input_version", "math_cost_spec"))
SEMANTIC_FIELDS = frozenset(
    (
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
)
_SELECTION = {
    "symbol": "US.IVV",
    "first": "2026-05-08",
    "last": "2026-10-29",
    "sessions": 121,
    "warmup": 100,
    "observations": 21,
    "window_sha256": "38f7822357ce458d4fe1d974821e7fda89deb3a31208c68dcea6abb85b04eaf4",
}
_ACTOR = {
    "memory_bytes": 536870912,
    "swap_bytes": 0,
    "cpu_percent": 50,
    "tasks_max": 32,
    "context_runtime_seconds": 480,
    "writer_bytes": 7 * MIB,
    "sdk_log_bytes": MIB,
    "windows_job_commit_bytes": 536870912,
    "windows_affinity_cores": 1,
    "numeric_seconds": 80,
}
_ASSURANCE = {
    "channel": "UNVERIFIED_TRUSTED_EXTERNAL",
    "provider_hard_limit_enforced": False,
    "provider_tail_max": "UNKNOWN",
    "historical_actual_cumulative": "UNKNOWN",
}
_READ_ONLY_PROTOCOLS = (1002, 3104, 3202, 3105, 3234, 3236, 3103)
DEFAULT_POLICY = {
    "schema_id": "qm.ivv.recovery-policy.v1",
    "authority_sha256": AUTHORITY,
    "logical_task_id": LOGICAL_TASK_ID,
    "math_cost_spec": MATH_COST_SPEC,
    "selection": dict(_SELECTION),
    "batch": {
        "batch_id": "ivv-recovery-batch-01",
        "wall_seconds": 1800,
        "contexts": 3,
        "business_requests": 32,
        "max_business_per_second": 1,
        "init_connect": 3,
        "keepalive": 288,
        "max_numerical_attempts": 3,
    },
    "actor": dict(_ACTOR),
    "storage": {
        "software": 16 * MIB,
        "capture_local": 48 * MIB,
        "capture_remote": 48 * MIB,
        "input_review": 4 * MIB,
        "study": 8 * MIB,
        "closeout_local": 2 * MIB,
        "closeout_remote": 2 * MIB,
    },
    "thresholds": {
        "G": 12884901888,
        "P": 6442450944,
        "free": 53687091200,
        "guard_G": 10604343386,
        "guard_P": 4566270990,
        "all_parent_stress": 4622894094,
    },
    "read_only_protocols": list(_READ_ONLY_PROTOCOLS),
    "assurance": dict(_ASSURANCE),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _need(ok, code):
    if not ok:
        raise ValueError(code)


def _closed(value, keys, code):
    _need(type(value) is dict and set(value) == set(keys), code)


def _sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive(value):
    return type(value) is int and value > 0


def _fixed(value, expected, code):
    _closed(value, expected, code)
    _need(all(type(value[k]) is type(v) and value[k] == v for k, v in expected.items()), code)


def _name(value):
    return type(value) is str and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", value) is not None


def _reference(value):
    _closed(value, ("algorithm", "digest", "media_type", "byte_length"), "recovery_reference")
    _need(
        value["algorithm"] == "sha256"
        and _sha(value["digest"])
        and type(value["media_type"]) is str
        and bool(value["media_type"].strip())
        and _positive(value["byte_length"])
        and value["byte_length"] <= MIB,
        "recovery_reference",
    )
    return value


def business_key(identity):
    _need(
        type(identity) is dict
        and set(identity) in (IDENTITY_FIELDS, IDENTITY_FIELDS | {"business_key"}),
        "recovery_identity",
    )
    _need(
        identity["logical_task_id"] == LOGICAL_TASK_ID
        and _name(identity["experiment_id"])
        and _sha(identity["input_version"])
        and _sha(identity["math_cost_spec"]),
        "recovery_identity",
    )
    key = digest(canonical({name: identity[name] for name in IDENTITY_FIELDS}))
    _need("business_key" not in identity or identity["business_key"] == key, "recovery_key")
    return key


def validate_identity(identity):
    key = business_key(identity)
    return {**{name: identity[name] for name in IDENTITY_FIELDS}, "business_key": key}


def logical_job_id(identity):
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, "urn:quantmesh:ivv-recovery:v1:" + business_key(identity))
    )


def research_effect(identity):
    return digest(
        canonical({"business_key": business_key(identity), "purpose": "declared_ivv_research"})
    )


def capture_scope_id():
    return digest(
        canonical({"logical_task_id": LOGICAL_TASK_ID, "purpose": "readonly_ivv_capture"})
    )


def semantic_input_version(semantic):
    _closed(semantic, SEMANTIC_FIELDS, "recovery_semantic_fields")
    _closed(semantic["inputs"], ("bars", "distributions", "schedule"), "recovery_semantic_inputs")
    for ref in semantic["inputs"].values():
        _reference(ref)
    _need(type(semantic["window"]) is dict and bool(semantic["window"]), "recovery_semantic_window")
    _need(
        all(
            type(semantic[name]) is str and bool(semantic[name].strip())
            for name in SEMANTIC_FIELDS - {"inputs", "window"}
        ),
        "recovery_semantic_fact",
    )
    return digest(canonical(semantic))


def validate_policy(policy):
    _closed(policy, DEFAULT_POLICY, "recovery_policy_fields")
    _need(
        policy["schema_id"] == "qm.ivv.recovery-policy.v1"
        and _sha(policy["authority_sha256"])
        and policy["logical_task_id"] == LOGICAL_TASK_ID
        and policy["math_cost_spec"] == MATH_COST_SPEC,
        "recovery_policy_identity",
    )
    _fixed(policy["selection"], _SELECTION, "recovery_fixed_scope")
    _fixed(policy["actor"], _ACTOR, "recovery_fixed_scope")
    _fixed(policy["assurance"], _ASSURANCE, "recovery_assurance")
    protocols = policy["read_only_protocols"]
    _need(
        type(protocols) is list
        and all(type(p) is int for p in protocols)
        and tuple(protocols) == _READ_ONLY_PROTOCOLS,
        "recovery_protocols",
    )
    batch = policy["batch"]
    _closed(batch, DEFAULT_POLICY["batch"], "recovery_batch_fields")
    _need(_name(batch["batch_id"]), "recovery_batch_identity")
    _need(
        all(_positive(batch[k]) for k in set(batch) - {"batch_id", "max_business_per_second"}),
        "recovery_batch_budget",
    )
    rate = batch["max_business_per_second"]
    _need(type(rate) in (int, float) and math.isfinite(rate) and rate > 0, "recovery_batch_rate")
    _need(
        batch["init_connect"] == batch["contexts"] and batch["keepalive"] <= 96 * batch["contexts"],
        "recovery_control_budget",
    )
    storage = policy["storage"]
    _closed(storage, DEFAULT_POLICY["storage"], "recovery_storage_fields")
    _need(all(_positive(v) for v in storage.values()), "recovery_storage")
    _need(
        storage["capture_local"] >= 16 * MIB * batch["contexts"]
        and storage["capture_remote"] >= 16 * MIB * batch["contexts"]
        and storage["study"] >= MIB * batch["max_numerical_attempts"],
        "recovery_unfunded_attempts",
    )
    limits = policy["thresholds"]
    _closed(limits, DEFAULT_POLICY["thresholds"], "recovery_threshold_fields")
    _need(all(_positive(v) for v in limits.values()), "recovery_thresholds")
    _need(
        limits["free"] >= 53687091200
        and limits["guard_G"] <= limits["G"]
        and limits["guard_P"] <= limits["P"]
        and limits["all_parent_stress"] <= limits["P"],
        "recovery_capacity",
    )
    # JSON roundtrip declines non-finite/non-JSON nested values and removes aliases.
    return json.loads(canonical(policy))


def attempt_policy(policy, policy_ref):
    checked = validate_policy(policy)
    _reference(policy_ref)
    raw = canonical(checked)
    _need(
        policy_ref["media_type"] == "application/json"
        and policy_ref["digest"] == digest(raw)
        and policy_ref["byte_length"] == len(raw),
        "recovery_policy_reference",
    )
    return {
        "policy_ref": dict(policy_ref),
        "batch_id": checked["batch"]["batch_id"],
        "max_numerical_attempts": checked["batch"]["max_numerical_attempts"],
    }


def validate_attempt_policy(value, policy):
    _closed(value, ("policy_ref", "batch_id", "max_numerical_attempts"), "recovery_attempt_policy")
    expected = attempt_policy(policy, value["policy_ref"])
    _need(
        type(value["max_numerical_attempts"]) is int and value == expected,
        "recovery_attempt_policy",
    )
    return expected


def policy_provenance(policy):
    checked = validate_policy(policy)
    return {
        "diagnostic_mode": MODE,
        "logical_task_id": checked["logical_task_id"],
        "authorization_sha256": checked["authority_sha256"],
        "math_cost_spec": checked["math_cost_spec"],
        "batch_id": checked["batch"]["batch_id"],
        "capture_budget": copy.deepcopy(checked["batch"]),
        **copy.deepcopy(checked["assurance"]),
    }
