"""Purpose-limited DEV authority. No SDK, provider mutation or self-approval.

The native collector is deliberately fail-closed until the independently
reviewed native integration is installed. Offline kernel models are not proof.
"""

import hashlib
import importlib.util
import os
import stat
import sys
from pathlib import Path

SUFFIX = ".dev-diagnostic.v1"
PROVENANCE_KEYS = (
    "policy_sha256",
    "authorization_sha256",
    "diagnostic_mode",
    "hard_limit_enforced",
    "provider_tail_max",
)


def _capture():
    spec = importlib.util.spec_from_file_location(
        "ivv_dev_capture", Path(__file__).with_name("capture_opend_ivv_daily.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_policy(m, value, plan, authorization_sha256):
    expected = {
        "schema_id": "qm.ivv.capture-policy" + SUFFIX,
        "scope_id": plan["scope_id"],
        "execution_sha256": plan["execution_sha256"],
        "effect_id": plan["effect_id"],
        "authorization_sha256": authorization_sha256,
        "diagnostic_mode": "DEV_DIAGNOSTIC",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
        "legacy_loaded_guard_provenance": "UNKNOWN",
        "exceptions": ["provider_32MiB_fullRO_sixRW", "legacy_loaded_guard_provenance"],
        "thresholds": {"G": 10500000000, "P": 4500000000, "free": 53687091200},
    }
    m._require(
        m._digest(authorization_sha256)
        and value == expected
        and value.get("hard_limit_enforced") is False,
        "dev_policy_contract",
    )


def _read_native_provider(plan, evidence):
    """Task2 must collect actual metadata; never accept a caller JSON proof."""
    raise RuntimeError("DEV_NATIVE_COLLECTOR_NOT_RELEASED")


def native_provider_snapshot(m, plan, evidence):
    """Validate actual collector projection and current monitoring thresholds."""
    actual = _read_native_provider(plan, evidence)
    for key in (
        "provider_actor",
        "endpoint",
        "identity_binding_sha256",
        "channels_binding_sha256",
        "configuration_binding_sha256",
    ):
        m._require(actual.get(key) == evidence.get(key), "dev_native_binding")
    limits = actual.get("resource_values", {})
    m._require(
        limits.get("memory.max") == "1073741824"
        and limits.get("memory.swap.max") == "0"
        and limits.get("cpu.max") == "50000 100000"
        and limits.get("pids.max") == "128",
        "dev_provider_resources",
    )
    sample = actual.get("sample", {})
    m._require(
        set(sample) == {"incremental_bytes", "G", "P", "free"}
        and all(type(v) is int and v >= 0 for v in sample.values())
        and sample["incremental_bytes"] < 33554432
        and sample["G"] <= 10500000000
        and sample["P"] <= 4500000000
        and sample["free"] >= 53687091200,
        "dev_monitor_threshold",
    )
    stamp = actual.get("sampled_monotonic")
    m._require(
        type(stamp) in (int, float) and 0 <= m.time.monotonic() - stamp <= 5, "dev_monitor_stale"
    )
    return actual


def _context(
    m,
    plan_ref,
    receipt_root,
    go_ref,
    authorization_ref,
    catalog_ref,
    *,
    expected_policy_sha256,
    expected_authorization_sha256,
    expected_go_sha256,
):
    m._require(sys.platform == "linux", "native_root_permit_required")
    for digest in (expected_policy_sha256, expected_authorization_sha256, expected_go_sha256):
        m._require(m._digest(digest), "dev_trusted_startup_pin")
    m._require(
        go_ref["sha256"] == expected_go_sha256
        and authorization_ref["sha256"] == expected_authorization_sha256,
        "dev_trusted_startup_pin",
    )
    plan = m._strict_json(m._read_root_ref(plan_ref, maximum=32768, exact_mode=True))
    m._validate_production_plan_keys(plan, schema="qm.ivv.capture-plan" + SUFFIX)
    m._validate_fixed_plan(plan, schema="qm.ivv.capture-plan" + SUFFIX)
    m._require(plan["policy_ref"]["sha256"] == expected_policy_sha256, "dev_policy_pin")
    policy = m._strict_json(m._read_root_ref(plan["policy_ref"], maximum=32768, exact_mode=True))
    validate_policy(m, policy, plan, expected_authorization_sha256)
    # Authorization is independently pinned actual human bytes, never inferred
    # from a decision string supplied by the capture caller.
    m._read_root_ref(authorization_ref, maximum=32768, exact_mode=True)
    go = m._strict_json(m._read_root_ref(go_ref, maximum=32768, exact_mode=True))
    provenance = m._dev_provenance(go)
    m._require(
        provenance["policy_sha256"] == expected_policy_sha256
        and provenance["authorization_sha256"] == expected_authorization_sha256,
        "dev_go_policy",
    )
    m._require(
        go.get("schema_id") == "qm.ivv.root-go" + SUFFIX
        and go.get("decision") == "GO_ONCE_AFTER_INPUT_ACCEPTANCE"
        and go.get("capture_effect_id") == plan["effect_id"]
        and go.get("scope_id") == plan["scope_id"]
        and go.get("execution_sha256") == plan["execution_sha256"]
        and go.get("approval_sha256") == plan["approval_sha256"]
        and go.get("input_window_digest") == plan["input_window_digest"]
        and go.get("full_window_sha256") == plan["full_window_sha256"]
        and go.get("plan_sha256") == plan_ref["sha256"]
        and type(go.get("max_capture_intents")) is int
        and go["max_capture_intents"] == 1
        and type(go.get("max_trials")) is int
        and go["max_trials"] == 1,
        "dev_go_binding",
    )
    m._require(
        catalog_ref["sha256"] == plan["catalog_sha256"] == go.get("catalog_sha256"),
        "dev_catalog_binding",
    )
    catalog = m._strict_json(m._read_root_ref(catalog_ref, maximum=32768, exact_mode=True))
    own_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    m._require(
        catalog.get("capture_helper_sha256")
        == plan["capture_helper_sha256"]
        == go.get("capture_helper_sha256")
        and catalog.get("dev_issuer_sha256") == own_sha == go.get("dev_issuer_sha256")
        and os.statvfs(__file__).f_flag & os.ST_RDONLY,
        "dev_released_source",
    )
    evidence = m._strict_json(
        m._read_root_ref(plan["provider_evidence_ref"], maximum=32768, exact_mode=True)
    )
    m._require(
        evidence.get("schema_id") == "qm.ivv.provider-evidence" + SUFFIX
        and evidence.get("state") == "DEV_DIAGNOSTIC"
        and evidence.get("scope_id") == plan["scope_id"]
        and evidence.get("execution_sha256") == plan["execution_sha256"]
        and evidence.get("effect_id") == plan["effect_id"]
        and evidence.get("endpoint") == plan["endpoint"]
        and m._dev_provenance(evidence) == provenance
        and go.get("provider_evidence_sha256") == plan["provider_evidence_ref"]["sha256"],
        "dev_provider_evidence",
    )
    actor = evidence.get("provider_actor", {})
    m._require(
        set(actor) == {"pid", "uid", "start_ticks", "exe_sha256", "machine_identity_sha256"}
        and all(
            type(actor[k]) is int and actor[k] >= (0 if k == "uid" else 1)
            for k in ("pid", "uid", "start_ticks")
        )
        and m._digest(actor["exe_sha256"])
        and m._digest(actor["machine_identity_sha256"]),
        "dev_provider_actor",
    )
    m._require(plan["endpoint"]["is_encrypt"] is False, "dev_encrypted_config_unsupported")
    for key in (
        "identity_binding_sha256",
        "channels_binding_sha256",
        "configuration_binding_sha256",
    ):
        m._require(m._digest(evidence.get(key)), "dev_evidence_binding")
    native_provider_snapshot(m, plan, evidence)
    m._require(str(receipt_root) == plan["receipt_root"], "approved_receipt_root")
    return plan, go, evidence, provenance


def _permit_value(plan, plan_ref, go, go_ref, authorization_ref, catalog_ref, provenance):
    keys = (
        "scope_id",
        "effect_id",
        "capture_helper_sha256",
        "catalog_sha256",
        "sdk_pins_sha256",
        "input_window_digest",
        "full_window_sha256",
        "started_monotonic",
        "approval_sha256",
        "execution_sha256",
    )
    return {
        "schema_id": "qm.ivv.root-permit" + SUFFIX,
        "state": "ROOT_INTERNAL_GO",
        **{key: plan[key] for key in keys},
        **provenance,
        "plan_sha256": plan_ref["sha256"],
        "root_go_sha256": go_ref["sha256"],
        "go_ref": go_ref,
        "authorization_ref": authorization_ref,
        "catalog_ref": catalog_ref,
        "provider_evidence_ref": plan["provider_evidence_ref"],
        "actor": go["capture_actor"],
        "budget": go["budget"],
    }


def admit_dev(
    m,
    plan_path,
    receipt_root,
    fd,
    expected_sha256,
    *,
    expected_policy_sha256,
    expected_authorization_sha256,
    expected_go_sha256,
):
    permit = m._read_held_json(fd, expected_sha256)
    m._require(permit.get("schema_id") == "qm.ivv.root-permit" + SUFFIX, "dev_permit_schema")
    plan_ref = {"path": str(plan_path), "sha256": permit["plan_sha256"]}
    plan, go, evidence, provenance = _context(
        m,
        plan_ref,
        receipt_root,
        permit["go_ref"],
        permit["authorization_ref"],
        permit["catalog_ref"],
        expected_policy_sha256=expected_policy_sha256,
        expected_authorization_sha256=expected_authorization_sha256,
        expected_go_sha256=expected_go_sha256,
    )
    m._require(
        permit
        == _permit_value(
            plan,
            plan_ref,
            go,
            permit["go_ref"],
            permit["authorization_ref"],
            permit["catalog_ref"],
            provenance,
        ),
        "dev_permit_binding",
    )
    plan, dates, permit = m._admit_material(
        plan, plan_path, receipt_root, permit, fd, expected_sha256
    )
    inherited = plan["_live_verifier"]

    def live():
        inherited()
        for ref in (
            plan["policy_ref"],
            plan["provider_evidence_ref"],
            permit["go_ref"],
            permit["authorization_ref"],
            permit["catalog_ref"],
        ):
            m._read_root_ref(ref, maximum=32768, exact_mode=True)
        native_provider_snapshot(m, plan, evidence)

    plan["_live_verifier"] = live
    plan["_verified_binding"].update(
        provenance,
        provider_evidence_ref=plan["provider_evidence_ref"],
        provider_actor=evidence["provider_actor"],
    )
    live()
    return plan, dates, permit


def issue_dev_permit(
    plan_ref,
    receipt_root,
    *,
    go_ref,
    authorization_ref,
    catalog_ref,
    expected_policy_sha256,
    expected_authorization_sha256,
    expected_go_sha256,
    permit_path,
):
    """Issue inside the actual bounded Root capture actor; caller owns returned FD.

    Creating a permit does not reserve another effect. Capture always reserves
    the same canonical scope/execution/effect marker before constructing SDK.
    """
    m = _capture()
    m._require(
        sys.platform == "linux" and os.getuid() == 0 and os.geteuid() == 0, "dev_root_issuer"
    )
    plan, go, evidence, provenance = _context(
        m,
        plan_ref,
        receipt_root,
        go_ref,
        authorization_ref,
        catalog_ref,
        expected_policy_sha256=expected_policy_sha256,
        expected_authorization_sha256=expected_authorization_sha256,
        expected_go_sha256=expected_go_sha256,
    )
    permit = _permit_value(plan, plan_ref, go, go_ref, authorization_ref, catalog_ref, provenance)
    m._admit_material(plan, plan_ref["path"], receipt_root, permit, None, None)
    path = Path(permit_path)
    m._require(path.is_absolute() and path.parent.resolve() == path.parent, "dev_permit_path")
    for parent in (path.parent, *path.parent.parents):
        info = parent.stat()
        m._require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == 0
            and not stat.S_IMODE(info.st_mode) & 0o022,
            "dev_permit_parent",
        )
    raw = m._canonical(permit)
    m._require(0 < len(raw) <= 32768, "dev_permit_size")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            m._require(count > 0, "dev_permit_write")
            view = view[count:]
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    finally:
        os.close(fd)
    m._sync_dir(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        m._require(m._read_held_json(fd, digest) == permit, "dev_issued_held_binding")
        m._require(m._fd_stamp(os.fstat(fd)) == m._fd_stamp(path.stat()), "dev_issued_inode")
        admit_dev(
            m,
            plan_ref["path"],
            receipt_root,
            fd,
            digest,
            expected_policy_sha256=expected_policy_sha256,
            expected_authorization_sha256=expected_authorization_sha256,
            expected_go_sha256=expected_go_sha256,
        )
    except BaseException:
        os.close(fd)
        raise
    return fd, digest
