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
from uuid import uuid4

import pytest
from test_ivv_capture_contract import DATES, SCHEDULE, Clock, ScriptedBackend, contract, leaf


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


def _registration_authorities(tmp_path, monkeypatch):
    """Fictional immutable originals prepared before Linux kernel emulation."""
    from quantmesh.research import ivv_admission as v
    from quantmesh.research import ivv_runtime, native_daily_candidate
    from quantmesh.research import native_daily_real as daily

    scope_id, job_id = "fictional-connected-dev-scope", str(uuid4())
    scope = daily.canonical({"selection": {"asset": "US.IVV"}, "software_only": True})
    effect = daily.canonical(
        {"scope_approval_sha256": daily.digest(scope), "paper_live": False, "software_only": True}
    )
    execution = daily.canonical(
        {
            "approval_sha256": daily.digest(effect),
            "fixed_scope": {
                "asset": "US.IVV",
                "scope_id": scope_id,
                "input_window_digest": daily.digest(daily.canonical(v.WINDOW)),
            },
            "software_only": True,
        }
    )
    originals = {"scope": scope, "effect": effect, "execution": execution}
    pins = {key: daily.digest(body) for key, body in originals.items()}
    windows_policy = daily.canonical(
        {
            "planning_scope_id": scope_id,
            "planning_job_uuid": job_id,
            "full_execution_approval_sha256": pins["effect"],
            "software_only": True,
        }
    )
    monkeypatch.setattr(v, "SCOPE_ID", scope_id)
    monkeypatch.setattr(v, "ORIGINAL_PINS", pins)
    monkeypatch.setattr(v, "SOURCE_ID", "scripted_software_control")
    monkeypatch.setattr(ivv_runtime, "WINDOWS_POLICY_SHA", daily.digest(windows_policy))
    output_root = tmp_path / "uncreated-numerical-study"
    return {
        "scope_id": scope_id,
        "original_pins": pins,
        "originals": originals,
        "windows_policy": windows_policy,
        "window": v.WINDOW,
        "output_root": output_root,
        "go_fields": {
            "job_id": job_id,
            "output_root_digest": daily._root_pin(output_root),
            "windows_policy_sha256": daily.digest(windows_policy),
            "code": native_daily_candidate._code(),
            "adapter_sha256": daily.digest(Path(daily.__file__).read_bytes()),
            "gate_sha256": daily.digest(Path(v.__file__).read_bytes()),
            "runtime": daily.runtime_versions(),
            "controls": {
                "released": True,
                "resource_bounds": True,
                "provider_log_cache_bounds": False,
            },
        },
    }


def kernel_fixture(tmp_path, monkeypatch, *, registration=None):
    """Real files/hash/issuer/admission; replace only unavailable Linux syscalls/provider."""
    d, m = dev_module(), leaf()
    monkeypatch.setattr(m, "SCOPE", "fictional-dev-scope")
    monkeypatch.setattr(m, "EXECUTION", "e" * 64)
    monkeypatch.setattr(m, "APPROVAL", "a" * 64)
    if registration is not None:
        monkeypatch.setattr(m, "SCOPE", registration["scope_id"])
        monkeypatch.setattr(m, "APPROVAL", registration["original_pins"]["effect"])
        monkeypatch.setattr(m, "EXECUTION", registration["original_pins"]["execution"])
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
        value = {"fictional": key}
        if registration is not None:
            value = {"input_window_ref": registration["window"], "schedule_ref": SCHEDULE}.get(
                key, value
            )
        refs[key] = put(key, value)
        monkeypatch.setattr(m, constant, refs[key]["sha256"])
    if registration is not None:
        for name, body in registration["originals"].items():
            put("original-" + name, body, raw=True)
        put("windows-policy", registration["windows_policy"], raw=True)
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
    if registration is not None:
        go.update(registration["go_fields"])
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
    registration = _registration_authorities(tmp_path, monkeypatch)
    d, m, plan_ref, root, kwargs, snapshot = kernel_fixture(
        tmp_path, monkeypatch, registration=registration
    )
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
        capture_originals = {path.name: path.read_bytes() for path in root.iterdir()}
        authority_originals = {
            name: (tmp_path / name).read_bytes() for name in ("go", "policy", "authorization")
        }
        _consume_real_capture_artifacts(
            m, root, result, kwargs, tmp_path, monkeypatch, registration
        )
        assert {path.name: path.read_bytes() for path in root.iterdir()} == capture_originals
        assert {
            name: (tmp_path / name).read_bytes() for name in authority_originals
        } == authority_originals
        assert os.fstat(fd).st_size > 0
        with pytest.raises(m.CaptureRejected, match="spent_capture_effect"):
            m.capture_dev_once(
                plan_ref["path"], root, permit_fd=fd, expected_sha256=digest, **startup
            )
    finally:
        os.close(fd)


def _consume_real_capture_artifacts(m, root, result, kwargs, tmp_path, monkeypatch, registration):
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

    def original(name):
        return store.put_bytes("application/json", (tmp_path / name).read_bytes())

    source_facts = {
        "schema_id": "qm.ivv.source-facts.v1",
        "currency": "USD",
        "volume_unit": "shares",
        "historical_trade_venues": "fictional independent reviewer venue basis",
        "action_coverage": "complete_cash_ex_pay_no_splits",
        "pit_status": "unknown",
        "revision_note": "constructed software evidence; no real provider qualification",
        "basis": "fictional independent H1/H2/H3 reviewer facts; never inferred from login",
    }
    source_ref = put(source_facts)
    plain = json.loads((root / "plain.json").read_bytes())
    normalized = m.normalize_capture(
        plain,
        schedule=SCHEDULE,
        source_facts={
            "capture_evidence_sha256": m.capture_evidence_digest(plain),
            "price_currency": "USD",
            "volume_unit": "shares",
            "volume_venue": source_facts["historical_trade_venues"],
            "coverage_start": DATES[0],
            "coverage_end": DATES[-1],
            "evidence_refs": [source_ref.digest],
        },
    )
    exposure = put(
        {"scope_id": m.SCOPE, "sample_role": "development_only_retrospective", "unseen_oos": False}
    )
    trial_ledger = put(
        {
            "scope_id": m.SCOPE,
            "trial_id": "qm-ivv-trial-" + m.SCOPE,
            "max_trials": 1,
            "state": "UNRESERVED",
        }
    )
    staged_ref = v.stage_ivv_input_set(
        store,
        normalized=normalized,
        source_facts=source_facts,
        capture_ref=raw_ref,
        exposure_ref=exposure,
        trial_ledger_ref=trial_ledger,
    )
    accepted.update(
        {
            "schema_id": "qm.ivv.input-acceptance.dev-diagnostic.v1",
            **provenance,
            "decision": "ACCEPT_FOR_ONE_DECLARED_RETROSPECTIVE_RESEARCH",
            "reviewer": v.REVIEWER,
            "scope_id": m.SCOPE,
            "input_set_digest": v._load(store, staged_ref)["input_set_digest"],
            "capture_ref": raw_ref.model_dump(),
            "source_facts_ref": source_ref.model_dump(),
            "checks": {name: True for name in v.INPUT_CHECKS},
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
            "test_control": "fictional independent review",
        }
    )
    acceptance_ref = put(accepted)
    proofs = v.TrustedIVVProofs(
        scope_ref=original("original-scope"),
        effect_ref=original("original-effect"),
        execution_ref=original("original-execution"),
        windows_policy_ref=original("windows-policy"),
        go_ref=original("go"),
        capture_policy_ref=original("policy"),
        authorization_ref=original("authorization"),
        expected_go_sha256=kwargs["expected_go_sha256"],
        expected_policy_sha256=kwargs["expected_policy_sha256"],
        expected_authorization_sha256=kwargs["expected_authorization_sha256"],
        acceptance_ref=acceptance_ref,
        expected_acceptance_sha256=acceptance_ref.digest,
    )
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

    from quantmesh.research import native_daily_candidate as native

    def no_calculation(*args, **kwargs):
        pytest.fail("registration/cold reads must never compute or reserve a trial")

    monkeypatch.setattr(native, "_calculate_matrix", no_calculation)
    output_root = registration["output_root"]
    try:
        registered = v.bind_reviewed_ivv_input(
            store, input_set_ref=staged_ref, proofs=proofs, output_root=output_root
        )
    except daily.NativeError as error:
        raise AssertionError(
            "connected capture must reach real registration"
        ) from error.__context__
    package = v._load(store, registered.package_ref)
    assert raw_ref.model_dump() in package["source_asset_refs"]
    assert (
        proofs.go_ref.digest
        == kwargs["expected_go_sha256"]
        == result["source_binding"]["root_go_sha256"]
    )
    assert proofs.capture_policy_ref.digest == result["policy_sha256"]
    assert proofs.authorization_ref.digest == result["authorization_sha256"]
    checked = v.verify_saved_binding(
        store, registered.package_ref, registered.real_binding, executing=False
    )
    assert checked["capture_ref"] == raw_ref.model_dump()
    assert checked["job_id"] == go["job_id"]
    assert checked["scope_trial_key"] == daily.digest(
        daily.canonical({"execution": m.EXECUTION, "scope": m.SCOPE, "trial": 1})
    )
    archived = {ref.digest: body for ref, body in v.binding_objects(store, registered.real_binding)}
    for ref, path in (
        (proofs.go_ref, tmp_path / "go"),
        (proofs.capture_policy_ref, tmp_path / "policy"),
        (proofs.authorization_ref, tmp_path / "authorization"),
    ):
        assert archived[ref.digest] == path.read_bytes()
    assert archived[result["intent_ref"]["sha256"]] == (root / "capture-intent.json").read_bytes()
    assert (
        daily.NativeDailyService._from_store(store, raw_ref)
        == (root / "capture-manifest.json").read_bytes()
    )
    assert v._load(store, trial_ledger)["state"] == "UNRESERVED"
    assert not output_root.exists()
    for change in (
        {"checks": {**accepted["checks"], "shares_unit": False}},
        {"checks": {**accepted["checks"], "complete_actions": False}},
        {"checks": {**accepted["checks"], "raw_prices": False}},
        {"authorization_sha256": "f" * 64},
        {"parent_close_ref": put({**parent, "helper_exit_code": 1}).model_dump()},
    ):
        rejected_ref = put({**accepted, **change})
        rejected_proofs = proofs.model_copy(
            update={
                "acceptance_ref": rejected_ref,
                "expected_acceptance_sha256": rejected_ref.digest,
            }
        )
        with pytest.raises(daily.NativeError, match="ivv_not_admitted"):
            v.bind_reviewed_ivv_input(
                store, input_set_ref=staged_ref, proofs=rejected_proofs, output_root=output_root
            )
    assert not output_root.exists()
    with pytest.raises(daily.NativeError, match="ivv_not_admitted"):
        v.bind_reviewed_ivv_input(
            store,
            input_set_ref=staged_ref,
            proofs=proofs.model_copy(update={"authorization_ref": None}),
            output_root=output_root,
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
