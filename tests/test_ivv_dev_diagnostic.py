"""Fictional offline DEV controls; never original authority or native qualification."""

import contextlib
import copy
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_ivv_capture_contract import DATES, Clock, ScriptedBackend, contract, leaf


def dev_module():
    path = Path(__file__).resolve().parents[1] / "tools/research/ivv_dev_diagnostic.py"
    assert path.exists(), "explicit DEV issuer/contract is missing"
    spec = importlib.util.spec_from_file_location("ivv_dev_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dev_plan(m):
    plan = contract(m)
    plan["schema_id"] = "qm.ivv.capture-plan.dev-diagnostic.v1"
    plan["_verified_binding"] = {
        "policy_sha256": "1" * 64,
        "authorization_sha256": "2" * 64,
        "diagnostic_mode": "DEV_DIAGNOSTIC",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
    }
    return plan


def test_dev_shared_core_preserves_version_and_seven_ordered_sends(tmp_path):
    m = leaf()
    plan = dev_plan(m)
    root = tmp_path / "capture"
    clock = Clock()
    result = m._run_capture(
        plan,
        root,
        backend_factory=lambda observer, writer, plan, clock: ScriptedBackend(
            m, observer, writer, clock, root
        ),
        clock=clock,
        sync_dir=lambda path: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["schema_id"] == "qm.ivv.capture.dev-diagnostic.v1"
    assert result["state"] == "CAPTURED_UNREVIEWED"
    intent = json.loads((root / "capture-intent.json").read_bytes())
    assert intent["schema_id"] == "qm.ivv.capture-intent.dev-diagnostic.v1"
    for value in (intent, result):
        assert value["policy_sha256"] == "1" * 64
        assert value["authorization_sha256"] == "2" * 64
        assert value["hard_limit_enforced"] is False
        assert value["provider_tail_max"] == "UNKNOWN"
    requests = json.loads((root / "requests.json").read_bytes())
    assert requests["sent"] == [
        "state",
        "quota",
        "basic",
        "rehab",
        "dividends",
        "splits",
        "history",
    ]
    assert result["counts"]["application_sends"] == 7


def policy(m):
    return {
        "schema_id": "qm.ivv.capture-policy.dev-diagnostic.v1",
        "scope_id": m.SCOPE,
        "execution_sha256": m.EXECUTION,
        "effect_id": "owned-synthetic-vector",
        "authorization_sha256": "2" * 64,
        "diagnostic_mode": "DEV_DIAGNOSTIC",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
        "legacy_loaded_guard_provenance": "UNKNOWN",
        "exceptions": ["provider_32MiB_fullRO_sixRW", "legacy_loaded_guard_provenance"],
        "thresholds": {"G": 10500000000, "P": 4500000000, "free": 53687091200},
    }


@pytest.mark.parametrize("mutation", [None, "hard", "authorization", "schema", "extra"])
def test_closed_dev_policy_rejects_false_guarantees_and_version_mix(mutation):
    d, m = dev_module(), leaf()
    value = policy(m)
    if mutation == "hard":
        value["hard_limit_enforced"] = True
    elif mutation == "authorization":
        value["authorization_sha256"] = "3" * 64
    elif mutation == "schema":
        value["schema_id"] = "qm.ivv.capture-policy.v1"
    elif mutation == "extra":
        value["bypass"] = True
    if mutation is None:
        d.validate_policy(m, value, contract(m), "2" * 64)
    else:
        with pytest.raises(m.CaptureRejected):
            d.validate_policy(m, value, contract(m), "2" * 64)


def test_once_effect_remains_spent_across_policy_helper_and_output(tmp_path, monkeypatch):
    m = leaf()
    monkeypatch.setattr(m, "SCOPE", "fictional-once-scope")
    monkeypatch.setattr(m, "APPROVAL", "0" * 64)
    monkeypatch.setattr(m, "EXECUTION", "e" * 64)
    assert hasattr(m, "_reserve_once"), "canonical cross-policy once reservation is missing"
    monkeypatch.setattr(m, "ONCE_LEDGER", tmp_path / "ledger")
    m.ONCE_LEDGER.mkdir()
    plan = contract(m)
    order = []
    m._reserve_once(plan, sync_dir=lambda path: order.append("directory"))
    assert order == ["directory"]
    plan.update(schema_id="qm.ivv.capture-plan.dev-diagnostic.v1", capture_helper_sha256="f" * 64)
    plan["receipt_root"] = str(tmp_path / "another")
    with pytest.raises(m.CaptureRejected, match="spent_capture_effect"):
        m._reserve_once(plan, sync_dir=lambda path: None)
    markers = list(m.ONCE_LEDGER.iterdir())
    assert len(markers) == 1
    marker = json.loads(markers[0].read_bytes())
    assert set(marker) == {"scope_id", "execution_sha256", "effect_sha256"}
    assert marker["effect_sha256"] == m.APPROVAL
    assert hashlib.sha256(m._canonical(marker)).hexdigest() == markers[0].name


def test_public_dev_entry_refuses_without_trusted_held_authority(tmp_path):
    m = leaf()
    assert hasattr(m, "capture_dev_once"), "explicit DEV entry is missing"
    with pytest.raises((m.CaptureRejected, TypeError, OSError)):
        m.capture_dev_once(tmp_path / "plan", tmp_path / "capture")
    assert not (tmp_path / "capture").exists()


def kernel_fixture(tmp_path, monkeypatch):
    """Real files/hash/issuer/admission; replace only unavailable Linux syscalls/provider."""
    d, m = dev_module(), leaf()
    monkeypatch.setattr(m, "SCOPE", "fictional-dev-scope")
    monkeypatch.setattr(m, "EXECUTION", "e" * 64)
    monkeypatch.setattr(m, "APPROVAL", "a" * 64)
    root = tmp_path / "capture"

    def put(name, value, raw=False):
        body = value if raw else m._canonical(value)
        target = tmp_path / name
        target.write_bytes(body)
        return {"path": str(target), "sha256": hashlib.sha256(body).hexdigest()}

    refs = {}
    for key, constant in (
        ("input_window_ref", "WINDOW"),
        ("window_ref", "FULL_WINDOW"),
        ("schedule_ref", "SCHEDULE_SHA"),
    ):
        refs[key] = put(key, {"fictional": key})
        monkeypatch.setattr(m, constant, refs[key]["sha256"])
    refs["dates_ref"] = put("dates", ("\n".join(DATES) + "\n").encode(), raw=True)
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    pins = []
    for index in range(12):
        body = ("# fictional readonly source " + str(index)).encode()
        name = str(index) + ".py"
        (sdk / name).write_bytes(body)
        pins.append({"relative_path": name, "LF_sha256": hashlib.sha256(body).hexdigest()})
    pins_ref = put("pins", {"pins": pins})
    authorization_ref = put("authorization", {"fictional_human": "DEV software only"})
    plan = contract(m)
    plan.update(
        schema_id="qm.ivv.capture-plan.dev-diagnostic.v1",
        receipt_root=str(root),
        sdk_root=str(sdk),
        sdk_pins_ref=pins_ref,
        sdk_pins_sha256=pins_ref["sha256"],
        **refs,
    )
    value = policy(m)
    value["authorization_sha256"] = authorization_ref["sha256"]
    policy_ref = put("policy", value)
    provenance = {
        "policy_sha256": policy_ref["sha256"],
        "authorization_sha256": authorization_ref["sha256"],
        "diagnostic_mode": "DEV_DIAGNOSTIC",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
    }
    actor = {
        "pid": 123,
        "uid": 997,
        "start_ticks": 321,
        "exe_sha256": "5" * 64,
        "machine_identity_sha256": "6" * 64,
    }
    evidence = {
        "schema_id": "qm.ivv.provider-evidence.dev-diagnostic.v1",
        "state": "DEV_DIAGNOSTIC",
        "scope_id": m.SCOPE,
        "execution_sha256": m.EXECUTION,
        "effect_id": plan["effect_id"],
        "provider_actor": actor,
        "endpoint": plan["endpoint"],
        **provenance,
        "identity_binding_sha256": "7" * 64,
        "channels_binding_sha256": "8" * 64,
        "configuration_binding_sha256": "9" * 64,
    }
    evidence_ref = put("provider", evidence)
    helper_sha = hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
    issuer_sha = hashlib.sha256(Path(d.__file__).read_bytes()).hexdigest()
    catalog_ref = put(
        "catalog", {"capture_helper_sha256": helper_sha, "dev_issuer_sha256": issuer_sha}
    )
    plan.update(
        policy_ref=policy_ref,
        provider_evidence_ref=evidence_ref,
        capture_helper_sha256=helper_sha,
        catalog_sha256=catalog_ref["sha256"],
    )
    assert len(plan) == 22
    plan_ref = put("plan", plan)
    capture_actor = {
        "pid": os.getpid(),
        "uid": 0,
        "start_ticks": 12345,
        "cgroup": "/system.slice/fictional.service",
    }
    go = {
        "schema_id": "qm.ivv.root-go.dev-diagnostic.v1",
        "decision": "GO_ONCE_AFTER_INPUT_ACCEPTANCE",
        **provenance,
        "scope_id": m.SCOPE,
        "execution_sha256": m.EXECUTION,
        "approval_sha256": m.APPROVAL,
        "capture_effect_id": plan["effect_id"],
        "plan_sha256": plan_ref["sha256"],
        "max_capture_intents": 1,
        "max_trials": 1,
        "capture_actor": capture_actor,
        "budget": {"G": 1000, "P": 1000},
        "provider_evidence_sha256": evidence_ref["sha256"],
        "catalog_sha256": catalog_ref["sha256"],
        "capture_helper_sha256": helper_sha,
        "dev_issuer_sha256": issuer_sha,
        "input_window_digest": m.WINDOW,
        "full_window_sha256": m.FULL_WINDOW,
    }
    go_ref = put("go", go)
    snapshot = {
        **evidence,
        "resource_values": {
            "memory.max": "1073741824",
            "memory.swap.max": "0",
            "cpu.max": "50000 100000",
            "pids.max": "128",
        },
        "sample": {"incremental_bytes": 0, "G": 1000, "P": 1000, "free": 100000000000},
        "sampled_monotonic": 0,
    }
    monkeypatch.setattr(d, "_read_native_provider", lambda plan, evidence: copy.deepcopy(snapshot))
    monkeypatch.setattr(d, "_capture", lambda: m)
    monkeypatch.setattr(m, "_dev_contract", lambda: d, raising=False)
    # Linux kernel metadata/control fixture; no production authority is qualified.
    original_stat, original_fstat, original_read = os.stat, os.fstat, os.read
    original_open, original_close = os.open, os.close
    opened = {}

    def opened_file(path, *args, **kwargs):
        fd = original_open(path, *args, **kwargs)
        opened[fd] = path
        return fd

    def close_file(fd):
        opened.pop(fd, None)
        return original_close(fd)

    def stamp(info):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        values.update(
            st_uid=0,
            st_nlink=1,
            st_mode=(stat.S_IFDIR | 0o700)
            if stat.S_ISDIR(info.st_mode)
            else (stat.S_IFREG | 0o444),
        )
        return SimpleNamespace(**values)

    monkeypatch.setattr(os, "stat", lambda *args, **kw: stamp(original_stat(*args, **kw)))
    monkeypatch.setattr(os, "open", opened_file)
    monkeypatch.setattr(os, "close", close_file)
    # Windows Python versions differ in handle-vs-path timestamp precision.
    # The Linux fixture returns the same named/held inode metadata.
    monkeypatch.setattr(
        os,
        "fstat",
        lambda fd: stamp(original_stat(opened[fd]) if fd in opened else original_fstat(fd)),
    )
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "fchmod", lambda fd, mode: None, raising=False)
    monkeypatch.setattr(os, "ST_RDONLY", 1, raising=False)
    for name, value in (("O_NOFOLLOW", 0), ("O_CLOEXEC", 0), ("O_ACCMODE", 3), ("O_PATH", 2097152)):
        monkeypatch.setattr(os, name, value, raising=False)

    def pread(fd, count, offset):
        old = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            return original_read(fd, count)
        finally:
            os.lseek(fd, old, os.SEEK_SET)

    monkeypatch.setattr(os, "pread", pread, raising=False)
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(F_GETFL=3, fcntl=lambda fd, cmd: 0))
    monkeypatch.setattr(
        os,
        "statvfs",
        lambda path: SimpleNamespace(f_flag=1, f_bavail=100000000000, f_frsize=1),
        raising=False,
    )
    old_bytes, old_text = Path.read_bytes, Path.read_text

    def read_bytes(path):
        if path.as_posix() == "/proc/self/stat":
            return (str(os.getpid()) + " (fixture) " + " ".join(["0"] * 19 + ["12345"])).encode()
        return old_bytes(path)

    def read_text(path, *args, **kwargs):
        if path.as_posix() == "/proc/self/cgroup":
            return "0::/system.slice/fictional.service"
        if path.as_posix().startswith("/sys/fs/cgroup/"):
            return {
                "memory.max": "536870912",
                "memory.swap.max": "0",
                "cpu.max": "50000 100000",
                "pids.max": "32",
            }[path.name]
        return old_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(m.time, "monotonic", lambda: 0)
    monkeypatch.setattr(m, "_sync_dir", lambda path: None)
    monkeypatch.setattr(sys, "platform", "linux")
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    monkeypatch.setattr(m, "ONCE_LEDGER", ledger)
    kwargs = dict(
        go_ref=go_ref,
        authorization_ref=authorization_ref,
        catalog_ref=catalog_ref,
        expected_policy_sha256=policy_ref["sha256"],
        expected_authorization_sha256=authorization_ref["sha256"],
        expected_go_sha256=go_ref["sha256"],
        permit_path=tmp_path / "permit",
    )
    return d, m, plan_ref, root, kwargs, snapshot


def test_actual_issuer_held_admission_and_public_dev_capture(tmp_path, monkeypatch):
    # Load Windows numerical packages before emulating Linux kernel calls.
    importlib.import_module("quantmesh.research.ivv_admission")
    d, m, plan_ref, root, kwargs, snapshot = kernel_fixture(tmp_path, monkeypatch)
    assert hasattr(m, "capture_dev_once"), "DEV public admission seam missing"
    fd, digest = d.issue_dev_permit(plan_ref, root, **kwargs)
    startup = {key: value for key, value in kwargs.items() if key.startswith("expected_")}
    events, names = [], {}
    old_open, old_fsync = os.open, os.fsync

    def opened(path, *args, **kwargs):
        number = old_open(path, *args, **kwargs)
        names[number] = Path(path)
        return number

    def flushed(number):
        old_fsync(number)
        events.append(("file", names[number]))

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "fsync", flushed)
    monkeypatch.setattr(m, "_sync_dir", lambda path: events.append(("directory", Path(path))))

    class NativeClock(Clock):
        def phase(self, until):
            return contextlib.nullcontext()

    class Backend(ScriptedBackend):
        def open(self):
            # Reaching the real shared observer is permitted only after both durable writes.
            assert len(list(m.ONCE_LEDGER.iterdir())) == 1
            assert (root / "capture-intent.json").exists()
            marker = next(m.ONCE_LEDGER.iterdir())
            assert events[:5] == [
                ("file", marker),
                ("directory", m.ONCE_LEDGER),
                ("directory", root.parent),
                ("file", root / "capture-intent.json"),
                ("directory", root),
            ]
            self.o.context_created()
            self.o.initializing()

    monkeypatch.setattr(m, "_NativeClock", NativeClock)
    monkeypatch.setattr(m, "_OfficialBackend", lambda o, w, p, c: Backend(m, o, w, c, root))
    try:
        with pytest.raises(m.CaptureRejected):
            m._admit(plan_ref["path"], root, fd, digest)
        result = m.capture_dev_once(
            plan_ref["path"], root, permit_fd=fd, expected_sha256=digest, **startup
        )
        assert result["state"] == "CAPTURED_UNREVIEWED"
        assert result["schema_id"] == "qm.ivv.capture.dev-diagnostic.v1"
        assert result["counts"]["application_sends"] == 7
        assert result["counts"]["contexts"] == 1
        assert result["counts"]["initializations"] == 1
        assert result["requires_parent_close_receipt"] is True
        _consume_real_capture_artifacts(m, root, result, kwargs, tmp_path, monkeypatch)
        assert os.fstat(fd).st_size > 0
        with pytest.raises(m.CaptureRejected, match="spent_capture_effect"):
            m.capture_dev_once(
                plan_ref["path"], root, permit_fd=fd, expected_sha256=digest, **startup
            )
    finally:
        os.close(fd)


def _consume_real_capture_artifacts(m, root, result, kwargs, tmp_path, monkeypatch):
    """Actual helper artifact bytes through the existing consumer's parent gate.

    Parent exit is an authored independent observation in this software model,
    never an assertion that the helper has observed its own subsequent exit.
    """
    from quantmesh.data.objects import ObjectStore
    from quantmesh.research import ivv_admission as v
    from quantmesh.research import native_daily_real as daily

    monkeypatch.setattr(v, "SCOPE_ID", m.SCOPE)
    monkeypatch.setattr(v, "WINDOW_SHA", m.FULL_WINDOW)
    store = ObjectStore(tmp_path / "capture-objects")

    def put(value):
        return store.put_bytes("application/json", daily.canonical(value))

    for path in root.iterdir():
        store.put_bytes(
            "application/octet-stream" if path.suffix == ".pb" else "application/json",
            path.read_bytes(),
        )
    raw_ref = store.put_bytes("application/json", (root / "capture-manifest.json").read_bytes())
    go = json.loads(Path(kwargs["go_ref"]["path"]).read_bytes())
    proofs = SimpleNamespace(
        capture_policy_ref=SimpleNamespace(digest=kwargs["expected_policy_sha256"]),
        authorization_ref=SimpleNamespace(digest=kwargs["expected_authorization_sha256"]),
        expected_policy_sha256=kwargs["expected_policy_sha256"],
        expected_authorization_sha256=kwargs["expected_authorization_sha256"],
        go_ref=SimpleNamespace(digest=kwargs["expected_go_sha256"]),
        effect_ref=SimpleNamespace(digest=m.APPROVAL),
        execution_ref=SimpleNamespace(digest=m.EXECUTION),
    )
    evidence = put({"authored_parent_process_observation": "software-only"})
    provenance = {
        key: result[key]
        for key in (
            "policy_sha256",
            "authorization_sha256",
            "diagnostic_mode",
            "hard_limit_enforced",
            "provider_tail_max",
        )
    }
    parent = {
        "schema_id": "qm.ivv.capture-parent-close.dev-diagnostic.v1",
        **provenance,
        "scope_id": m.SCOPE,
        "state": "NORMAL_EXIT",
        "termination": "NORMAL",
        "effect_id": result["effect_id"],
        "capture_manifest_sha256": raw_ref.digest,
        "intent_sha256": result["intent_ref"]["sha256"],
        "catalog_sha256": go["catalog_sha256"],
        "helper_sha256": go["capture_helper_sha256"],
        "root_permit_sha256": result["source_binding"]["root_permit_sha256"],
        "capture_actor": result["source_binding"]["actor"],
        "executor_actor": {"pid": os.getpid() + 1, "software_only": True},
        "helper_exit_code": 0,
        "active_owned_processes": 0,
        "owned_fds_closed": True,
        "force_killed": False,
        "resource_limit_event": False,
        "elapsed_seconds": 1,
        "evidence_refs": [{"path": "/fictional-parent/evidence", "sha256": evidence.digest}],
    }
    accepted = {
        "parent_close_ref": put(parent).model_dump(),
        "parent_evidence_refs": [evidence.model_dump()],
    }
    parent_ref, objects = v._capture_close(store, raw_ref, accepted, go, proofs)
    assert parent_ref.digest == accepted["parent_close_ref"]["digest"]
    assert result["intent_ref"]["sha256"] in {ref.digest for ref in objects}
    for change in (
        {"schema_id": "qm.ivv.capture-parent-close.v1"},
        {"policy_sha256": "f" * 64},
        {"authorization_sha256": "f" * 64},
        {"active_owned_processes": 1},
        {"helper_exit_code": 1},
        {"owned_fds_closed": False},
    ):
        rejected = {**accepted, "parent_close_ref": put({**parent, **change}).model_dump()}
        with pytest.raises(ValueError):
            v._capture_close(store, raw_ref, rejected, go, proofs)
    old_intent = json.loads((root / "capture-intent.json").read_bytes())
    stale_intent = put({**old_intent, "schema_id": "qm.ivv.capture-intent.v1"})
    stale_raw = {
        **result,
        "intent_ref": {
            "path": "capture-intent.json",
            "sha256": stale_intent.digest,
            "bytes": stale_intent.byte_length,
        },
    }
    stale_raw_ref = put(stale_raw)
    stale_parent = put(
        {
            **parent,
            "capture_manifest_sha256": stale_raw_ref.digest,
            "intent_sha256": stale_intent.digest,
        }
    )
    with pytest.raises(ValueError):
        v._capture_close(
            store,
            stale_raw_ref,
            {**accepted, "parent_close_ref": stale_parent.model_dump()},
            go,
            proofs,
        )


def test_monitor_failure_retains_primary_manifest_without_sdk(tmp_path):
    m = leaf()
    plan = dev_plan(m)

    def changed():
        raise m.CaptureRejected("dev_monitor_threshold")

    plan["_live_verifier"] = changed

    def factory(*args):
        pytest.fail("SDK constructed after failed monitor")

    root = tmp_path / "failure"
    result = m._run_capture(
        plan,
        root,
        backend_factory=factory,
        clock=Clock(),
        sync_dir=lambda path: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["state"] == "FAILED_CAPTURE_REQUIRES_PARENT_SEAL"
    assert result["primary_failure"]["code"] == "dev_monitor_threshold"
    assert json.loads((root / "capture-manifest.json").read_bytes()) == result


@pytest.mark.parametrize(
    "change", ["strict_go", "wrong_auth", "policy", "actor", "evidence", "readonly", "channels"]
)
def test_issuer_refuses_untrusted_or_changed_material_before_permit(tmp_path, monkeypatch, change):
    d, m, plan_ref, root, kwargs, snapshot = kernel_fixture(tmp_path, monkeypatch)
    if change == "strict_go":
        path = Path(kwargs["go_ref"]["path"])
        go = json.loads(path.read_bytes())
        go["schema_id"] = "qm.ivv.root-go.v1"
        raw = m._canonical(go)
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        kwargs["go_ref"]["sha256"] = kwargs["expected_go_sha256"] = digest
    elif change == "wrong_auth":
        kwargs["expected_authorization_sha256"] = "f" * 64
    elif change == "policy":
        kwargs["expected_policy_sha256"] = "f" * 64
    elif change == "actor":
        snapshot["provider_actor"]["pid"] += 1
    elif change == "evidence":
        (tmp_path / "provider").write_bytes(b"{}")
    elif change == "readonly":
        monkeypatch.setattr(
            os, "statvfs", lambda path: SimpleNamespace(f_flag=0, f_bavail=100000000000, f_frsize=1)
        )
    else:
        snapshot["channels_binding_sha256"] = "f" * 64
    with pytest.raises(m.CaptureRejected):
        d.issue_dev_permit(plan_ref, root, **kwargs)
    assert not Path(kwargs["permit_path"]).exists()
    assert not root.exists()


@pytest.mark.parametrize("mode", ["writable", "opath", "linked", "inode", "changed_evidence"])
def test_held_permit_rechecks_flags_inode_and_provider_bytes(tmp_path, monkeypatch, mode):
    d, m, plan_ref, root, kwargs, snapshot = kernel_fixture(tmp_path, monkeypatch)
    fd, digest = d.issue_dev_permit(plan_ref, root, **kwargs)
    startup = {key: value for key, value in kwargs.items() if key.startswith("expected_")}
    try:
        admitted, dates, permit = d.admit_dev(m, plan_ref["path"], root, fd, digest, **startup)
        if mode in ("writable", "opath"):
            sys.modules["fcntl"].fcntl = lambda fd, cmd: (
                os.O_WRONLY if mode == "writable" else os.O_PATH
            )
        elif mode in ("linked", "inode"):
            old = os.fstat

            def changed(fd):
                value = old(fd)
                if mode == "linked":
                    value.st_nlink = 2
                else:
                    value.st_ino += 1
                return value

            monkeypatch.setattr(os, "fstat", changed)
        else:
            (tmp_path / "provider").write_bytes(b"{}")
        with pytest.raises(m.CaptureRejected):
            admitted["_live_verifier"]()
        assert not root.exists()
    finally:
        os.close(fd)


@pytest.mark.parametrize("failure", ["file", "directory"])
def test_uncertain_once_fsync_stays_spent(tmp_path, monkeypatch, failure):
    m = leaf()
    monkeypatch.setattr(m, "SCOPE", "fictional-once-scope")
    monkeypatch.setattr(m, "APPROVAL", "0" * 64)
    monkeypatch.setattr(m, "EXECUTION", "e" * 64)
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    monkeypatch.setattr(m, "ONCE_LEDGER", ledger)

    def fail(*args):
        raise OSError("authored fsync uncertainty")

    if failure == "file":
        monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        m._reserve_once(contract(m), sync_dir=fail)
    with pytest.raises(m.CaptureRejected, match="spent_capture_effect"):
        m._reserve_once(dev_plan(m), sync_dir=lambda path: None)


def test_attempt_label_cannot_renew_the_original_authorized_effect(tmp_path, monkeypatch):
    m = leaf()
    monkeypatch.setattr(m, "SCOPE", "fictional-once-scope")
    monkeypatch.setattr(m, "APPROVAL", "0" * 64)
    monkeypatch.setattr(m, "EXECUTION", "e" * 64)
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    monkeypatch.setattr(m, "ONCE_LEDGER", ledger)
    m._reserve_once(contract(m), sync_dir=lambda path: None)
    other = dev_plan(m)
    other.update(
        effect_id="another-attempt-label",
        capture_helper_sha256="f" * 64,
        receipt_root=str(tmp_path / "different-output"),
    )
    with pytest.raises(m.CaptureRejected, match="spent_capture_effect"):
        m._reserve_once(other, sync_dir=lambda path: None)
