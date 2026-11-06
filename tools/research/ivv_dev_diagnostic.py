"""Purpose-limited DEV authority. No SDK, provider mutation or self-approval.

Only an independently acquired native session can provide evidence. Current
cohort observations cannot prove exclusive external PTY holder closure.
"""

import hashlib
import os
import stat
import sys
import types
from pathlib import Path

SUFFIX = ".dev-diagnostic.v1"
PROVENANCE_KEYS = (
    "policy_sha256",
    "authorization_sha256",
    "diagnostic_mode",
    "hard_limit_enforced",
    "provider_tail_max",
)


# The independently reviewed helper is fixed for this release. No code from the
# plan, catalog, or helper runs to establish this initial trust anchor.
_CAPTURE_HELPER_SHA256 = "41378389494f144bc98b79660dddd827788d8b8dbd9494028f345f168fe60e7c"


def _capture():
    if sys.platform != "linux" or os.getuid() != 0 or os.geteuid() != 0:
        raise RuntimeError("dev_root_issuer")
    return _released_module("capture_opend_ivv_daily.py", _CAPTURE_HELPER_SHA256)


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


def validate_trusted_policy(m, value, plan, authorization_sha256):
    m._require(authorization_sha256 == m.TRUSTED_AUTH, "trusted_external_authorization")
    expected = dict(value)
    m._require(
        expected.pop("channel_assurance", None) == m.CHANNEL_ASSURANCE
        and expected.get("schema_id") == "qm.ivv.capture-policy" + m.TRUSTED_SUFFIX
        and expected.get("diagnostic_mode") == "DEV_TRUSTED_ENVIRONMENT"
        and expected.get("exceptions")
        == [
            "provider_32MiB_fullRO_sixRW",
            "legacy_loaded_guard_provenance",
            "external_provider_terminal_ipc_socket_environment",
        ],
        "trusted_external_policy",
    )
    expected.update(
        schema_id="qm.ivv.capture-policy" + SUFFIX,
        diagnostic_mode="DEV_DIAGNOSTIC",
        exceptions=expected["exceptions"][:-1],
    )
    validate_policy(m, expected, plan, authorization_sha256)


def _released_module(name, expected):
    """Compile the checked bytes directly. Native authority never executes a .pyc file."""
    if name not in (
        "capture_opend_ivv_daily.py",
        "ivv_dev_native.py",
        "ivv_native_producer.py",
        "ivv_additional_task.py",
        "ivv_recovery.py",
    ):
        raise RuntimeError("DEV_NATIVE_SOURCE_ORIGIN")
    path = Path(__file__).with_name(name)
    if path.resolve(strict=True) != path:
        raise RuntimeError("DEV_NATIVE_SOURCE_ORIGIN")

    def stamp(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_uid,
            info.st_nlink,
            info.st_size,
            info.st_ctime_ns,
            info.st_mtime_ns,
        )

    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not (
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and info.st_nlink == 1
            and not info.st_mode & 0o022
            and 0 < info.st_size <= 262144
            and os.fstatvfs(fd).f_flag & os.ST_RDONLY
            and stamp(info) == stamp(os.stat(path, follow_symlinks=False))
        ):
            raise RuntimeError("DEV_NATIVE_SOURCE_ORIGIN")
        raw = os.pread(fd, info.st_size + 1, 0)
        if not (
            len(raw) == info.st_size
            and hashlib.sha256(raw).hexdigest() == expected
            and os.fstatvfs(fd).f_flag & os.ST_RDONLY
            and stamp(os.fstat(fd)) == stamp(info) == stamp(os.stat(path, follow_symlinks=False))
        ):
            raise RuntimeError("DEV_NATIVE_SOURCE_PIN")
    finally:
        primary = sys.exc_info()[1]
        try:
            os.close(fd)
        except OSError:
            code = (
                str(primary)
                if type(primary) is RuntimeError
                and primary.args in (("DEV_NATIVE_SOURCE_ORIGIN",), ("DEV_NATIVE_SOURCE_PIN",))
                else "DEV_NATIVE_SOURCE_READ"
            )
            reason = code + "+DEV_NATIVE_SOURCE_CLOSE" if primary else "DEV_NATIVE_SOURCE_CLOSE"
            raise RuntimeError(reason) from None
    mod = types.ModuleType("_qm_" + name[:-3] + "_" + expected)
    mod.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), mod.__dict__)
    return mod


def _native_sources(m, catalog, go=None):
    result = {}
    for key, filename in (
        ("dev_native_sha256", "ivv_dev_native.py"),
        ("native_producer_sha256", "ivv_native_producer.py"),
    ):
        expected = catalog.get(key)
        m._require(
            m._digest(expected) and (go is None or go.get(key) == expected),
            "dev_native_source_catalog",
        )
        result[key] = _released_module(filename, expected)
    return result["dev_native_sha256"], result["native_producer_sha256"]


def prepare_native_evidence(plan, *, provenance, budget_ref):
    """Root pre-GO, in the already-bounded actor. A failed collector never registers a session."""
    m = _capture()
    m._require(sys.platform == "linux" and os.getuid() == os.geteuid() == 0, "dev_root_issuer")
    m._validate_production_plan_keys(plan, schema="qm.ivv.capture-plan" + SUFFIX)
    m._validate_fixed_plan(plan, schema="qm.ivv.capture-plan" + SUFFIX)
    m._require(
        m._dev_provenance(provenance) == provenance
        and plan["policy_ref"]["sha256"] == provenance["policy_sha256"],
        "dev_policy_pin",
    )
    policy = m._strict_json(m._read_root_ref(plan["policy_ref"], maximum=32768, exact_mode=True))
    validate_policy(m, policy, plan, provenance["authorization_sha256"])
    catalog_ref = {
        "path": str(Path(__file__).with_name("ivv-dev-catalog.json")),
        "sha256": plan["catalog_sha256"],
    }
    catalog = m._strict_json(m._read_root_ref(catalog_ref, maximum=32768, exact_mode=True))
    for path, key in (
        (Path(__file__), "dev_issuer_sha256"),
        (Path(m.__file__), "capture_helper_sha256"),
    ):
        m._require(
            os.statvfs(path).f_flag & os.ST_RDONLY
            and hashlib.sha256(path.read_bytes()).hexdigest() == catalog.get(key),
            "dev_released_source",
        )
    m._require(
        catalog["capture_helper_sha256"] == plan["capture_helper_sha256"], "dev_released_source"
    )
    native, producer = _native_sources(m, catalog)
    actor = m._native_actor()
    m._native_recheck(actor, Path(plan["receipt_root"]).parent)
    m._require(0 <= m.time.monotonic() - plan["started_monotonic"] < 180, "root_effect_expired")
    m._read_root_ref(budget_ref, maximum=32768, exact_mode=True)
    # No success instance can exist until the native external-holder gate is satisfied.
    session = native.prepare_provider(plan, producer, budget_ref)
    try:
        actual = session.snapshot()
        evidence = {
            "schema_id": "qm.ivv.provider-evidence" + SUFFIX,
            "state": "DEV_DIAGNOSTIC",
            **{k: plan[k] for k in ("scope_id", "execution_sha256", "effect_id")},
            **provenance,
            **{
                k: actual[k]
                for k in (
                    "provider_actor",
                    "endpoint",
                    "identity_binding_sha256",
                    "configuration_binding_sha256",
                    "channels_binding_sha256",
                )
            },
        }
        # The helper loads this module separately. Share only the prepared private instance.
        name = "_qm_live_ivv_native_" + str(os.getpid())
        m._require(name not in sys.modules, "dev_native_session_busy")
        state = types.ModuleType(name)
        state.session = session
        state.helper = m
        state.evidence = m._canonical(evidence)
        state.plan = m._canonical({k: v for k, v in plan.items() if k != "provider_evidence_ref"})
        sys.modules[name] = state
        return session, evidence
    except BaseException:
        session.close()
        raise


def _read_native_provider(plan, evidence):
    """A supplied artifact cannot recreate a live process-private observation session."""
    state = sys.modules.get("_qm_live_ivv_native_" + str(os.getpid()))
    if state is None:
        raise RuntimeError("DEV_NATIVE_SESSION_ABSENT")
    m = state.helper
    original = {
        k: v for k, v in plan.items() if not k.startswith("_") and k != "provider_evidence_ref"
    }
    m._require(
        m._canonical(original) == state.plan and m._canonical(evidence) == state.evidence,
        "dev_native_session_binding",
    )
    return state.session.snapshot()


def native_provider_snapshot(m, plan, evidence):
    """Validate actual collector projection and current monitoring thresholds."""
    actual = _read_native_provider(plan, evidence)
    for key in (
        "provider_actor",
        "endpoint",
        "identity_binding_sha256",
        "listener_binding_sha256"
        if plan["schema_id"]
        in {
            "qm.ivv.capture-plan" + x
            for x in (m.TRUSTED_SUFFIX, m.ADDITIONAL_SUFFIX, m.RECOVERY_SUFFIX)
        }
        else "channels_binding_sha256",
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
    recovery = plan["schema_id"] == "qm.ivv.capture-plan" + m.RECOVERY_SUFFIX
    sample = actual.get("sample", {})
    m._require(
        set(sample) == {"incremental_bytes", "G", "P", "free"}
        and all(type(v) is int and v >= 0 for v in sample.values())
        and sample["incremental_bytes"] < 33554432
        and sample["G"] <= (12884901888 if recovery else 10500000000)
        and sample["P"] <= (6442450944 if recovery else 4500000000)
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
    suffix=SUFFIX,
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
    m._validate_production_plan_keys(plan, schema="qm.ivv.capture-plan" + suffix)
    m._validate_fixed_plan(plan, schema="qm.ivv.capture-plan" + suffix)
    m._require(plan["policy_ref"]["sha256"] == expected_policy_sha256, "dev_policy_pin")
    policy = m._strict_json(m._read_root_ref(plan["policy_ref"], maximum=32768, exact_mode=True))
    recovery = suffix == m.RECOVERY_SUFFIX
    if recovery:
        state = sys.modules.get("_qm_live_ivv_native_" + str(os.getpid()))
        profile = getattr(state, "recovery_profile", None)
        m._require(
            profile is not None
            and expected_authorization_sha256 == m.RECOVERY_AUTH
            and expected_policy_sha256 == profile.policy_sha
            and m._canonical(policy) == profile.policy_bytes
            and plan["recovery"] == profile.binding(),
            "recovery_owned_authority",
        )
    elif suffix == m.ADDITIONAL_SUFFIX:
        state = sys.modules.get("_qm_live_ivv_native_" + str(os.getpid()))
        extra = getattr(state, "additional_task", None)
        m._require(
            extra is not None
            and expected_authorization_sha256 == extra.APPROVED.authorization_sha256
            and expected_policy_sha256 == extra.POLICY,
            "additional_owned_authority",
        )
        m._require(
            hashlib.sha256(m._canonical(policy)).hexdigest() == extra.POLICY, "additional_policy"
        )
    else:
        validator = validate_trusted_policy if suffix == m.TRUSTED_SUFFIX else validate_policy
        validator(m, policy, plan, expected_authorization_sha256)
    # Authorization is independently pinned actual human bytes, never inferred
    # from a decision string supplied by the capture caller.
    m._read_root_ref(authorization_ref, maximum=32768, exact_mode=True)
    go = m._strict_json(m._read_root_ref(go_ref, maximum=32768, exact_mode=True))
    provenance = m._dev_provenance(go, suffix)
    if recovery:
        m._require(
            m._canonical(provenance) == m._canonical(profile.provenance()),
            "recovery_policy_provenance",
        )
    m._require(
        provenance["policy_sha256"] == expected_policy_sha256
        and provenance["authorization_sha256"] == expected_authorization_sha256,
        "dev_go_policy",
    )
    m._require(
        go.get("schema_id") == "qm.ivv.root-go" + suffix
        and go.get("decision")
        == ("GO_BOUNDED_CAPTURE_RECOVERY" if recovery else "GO_ONCE_AFTER_INPUT_ACCEPTANCE")
        and go.get("capture_effect_id") == plan["effect_id"]
        and go.get("scope_id") == plan["scope_id"]
        and go.get("execution_sha256") == plan["execution_sha256"]
        and go.get("approval_sha256") == plan["approval_sha256"]
        and go.get("input_window_digest") == plan["input_window_digest"]
        and go.get("full_window_sha256") == plan["full_window_sha256"]
        and go.get("plan_sha256") == plan_ref["sha256"]
        and (
            recovery
            or (
                type(go.get("max_capture_intents")) is int
                and go["max_capture_intents"] == 1
                and type(go.get("max_trials")) is int
                and go["max_trials"] == 1
            )
        ),
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
    _native_sources(m, catalog, go)
    if recovery:
        m._require(
            go.get("recovery") == profile.binding()
            and go.get("capture_scope_id") == plan["scope_id"]
            and go.get("actor") == go.get("capture_actor")
            and go.get("catalog") == catalog_ref
            and go.get("native_controls") == go.get("controls")
            and not {"job_id", "research_scope_id", "max_trials"} & set(go),
            "recovery_capture_go",
        )
        for key, name in (
            ("additional_task_sha256", "ivv_additional_task.py"),
            ("recovery_contract_sha256", "ivv_recovery.py"),
        ):
            m._require(
                catalog.get(key) == go.get(key) and go.get("source", {}).get(key) == catalog[key],
                "recovery_source_catalog",
            )
            _released_module(name, catalog[key])
    if suffix == m.ADDITIONAL_SUFFIX:
        m._require(
            catalog["additional_task_sha256"] == go.get("additional_task_sha256")
            and go.get("job_id") == extra.APPROVED.job_id
            and go.get("windows_policy_sha256") == extra.WINDOWS
            and m._digest(go.get("numeric_runtime_sha256")),
            "additional_go_binding",
        )
        _released_module("ivv_additional_task.py", catalog["additional_task_sha256"])
    evidence = m._strict_json(
        m._read_root_ref(plan["provider_evidence_ref"], maximum=32768, exact_mode=True)
    )
    m._require(
        evidence.get("schema_id") == "qm.ivv.provider-evidence" + suffix
        and evidence.get("state") == provenance["diagnostic_mode"]
        and evidence.get("scope_id") == plan["scope_id"]
        and evidence.get("execution_sha256") == plan["execution_sha256"]
        and evidence.get("effect_id") == plan["effect_id"]
        and evidence.get("endpoint") == plan["endpoint"]
        and m._dev_provenance(evidence, suffix) == provenance
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
        "listener_binding_sha256"
        if suffix in (m.TRUSTED_SUFFIX, m.ADDITIONAL_SUFFIX, m.RECOVERY_SUFFIX)
        else "channels_binding_sha256",
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
        "schema_id": go["schema_id"].replace("qm.ivv.root-go", "qm.ivv.root-permit", 1),
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
    return _admit_family(
        m,
        plan_path,
        receipt_root,
        fd,
        expected_sha256,
        SUFFIX,
        expected_policy_sha256=expected_policy_sha256,
        expected_authorization_sha256=expected_authorization_sha256,
        expected_go_sha256=expected_go_sha256,
    )


def _admit_family(
    m,
    plan_path,
    receipt_root,
    fd,
    expected_sha256,
    suffix,
    *,
    expected_policy_sha256,
    expected_authorization_sha256,
    expected_go_sha256,
):
    permit = m._read_held_json(fd, expected_sha256)
    m._require(permit.get("schema_id") == "qm.ivv.root-permit" + suffix, "dev_permit_schema")
    plan_ref = {"path": str(plan_path), "sha256": permit["plan_sha256"]}
    plan, go, evidence, provenance = _context(
        m,
        plan_ref,
        receipt_root,
        permit["go_ref"],
        permit["authorization_ref"],
        permit["catalog_ref"],
        suffix=suffix,
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
        m._lifecycle_mark(plan, guard="CONTROL_REFS")
        for ref in (
            plan["policy_ref"],
            plan["provider_evidence_ref"],
            permit["go_ref"],
            permit["authorization_ref"],
            permit["catalog_ref"],
        ):
            m._read_root_ref(ref, maximum=32768, exact_mode=True)
        m._lifecycle_mark(plan, guard="PROVIDER_SESSION")
        native_provider_snapshot(m, plan, evidence)

    plan["_live_verifier"] = live
    plan["_verified_binding"].update(
        provenance,
        provider_evidence_ref=plan["provider_evidence_ref"],
        provider_actor=evidence["provider_actor"],
    )
    live()
    return plan, dates, permit


def issue_dev_permit(plan_ref, receipt_root, **pins):
    return _issue_family(_capture(), SUFFIX, plan_ref, receipt_root, **pins)


def _issue_family(
    m,
    suffix,
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
    m._require(sys.platform == "linux" and os.getuid() == os.geteuid() == 0, "dev_root_issuer")
    plan, go, evidence, provenance = _context(
        m,
        plan_ref,
        receipt_root,
        go_ref,
        authorization_ref,
        catalog_ref,
        suffix=suffix,
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
        _admit_family(
            m,
            plan_ref["path"],
            receipt_root,
            fd,
            digest,
            suffix,
            expected_policy_sha256=expected_policy_sha256,
            expected_authorization_sha256=expected_authorization_sha256,
            expected_go_sha256=expected_go_sha256,
        )
    except BaseException:
        os.close(fd)
        raise
    return fd, digest
