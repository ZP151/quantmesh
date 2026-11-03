"""Tests for the single approved additional task. Never operate the actual counter."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
C = "53badf05a10d955cc0826dccc592d1807bfbcfec8abcd4f9e3a194857e3d1858"
R = "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a"
A = "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832"
E = "a6681407439408a9d01baecedb3026f16f8e9513d601b2edd56910b0228eee17"
K = "189ac10caf73ef7fd31fa01fb4691bb4b00f19a371cc7792330df60bc6d7ac2c"


def additional():
    path = BASE / "tools/research/ivv_additional_task.py"
    assert path.is_file(), "additional task admission and once guard missing"
    spec = importlib.util.spec_from_file_location("additional_ivv_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_inputs():
    root = BASE.parent / "contracts"
    if not (root / "AUTHORIZATION.json").is_file():
        pytest.skip("PRIVATE_APPROVAL_FIXTURE_UNAVAILABLE")
    return tuple(
        (root / (name + ".json")).read_bytes()
        for name in ("AUTHORIZATION", "DESCRIPTOR", "CAPTURE-POLICY", "WINDOWS-POLICY")
    )


def test_additional_approved_authority_rejects_old_or_mutated_identity():
    m = additional()
    approval, descriptor, policy, windows = private_inputs()
    profile = m.authenticate(approval, descriptor, policy, windows)
    assert profile.capture_scope_id == C and profile.research_scope_id == R
    assert profile.capture_effect_sha256 == E and profile.authorization_sha256 == A
    assert profile.capture_once_key == K
    for index, before, after in (
        (2, A.encode(), b"3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452"),
        (0, E.encode(), b"37e4667460e66026ba6f281116ceeb6bb525f9aebc1b10d432405a410a139e45"),
        (0, C.encode(), R.encode()),
        (2, R.encode(), C.encode()),
        (3, R.encode(), C.encode()),
    ):
        args = [approval, descriptor, policy, windows]
        assert before in args[index]
        args[index] = args[index].replace(before, after)
        with pytest.raises(ValueError):
            m.authenticate(*args)


def test_additional_carrier_claim_requires_recent_auth_and_is_exclusive(tmp_path, monkeypatch):
    m = additional()
    monkeypatch.setattr(m, "_local_root", lambda: tmp_path)
    flushed = []
    monkeypatch.setattr(m, "_sync_directory", flushed.append)
    catalog = "6" * 64
    carrier = "7" * 64
    with pytest.raises(ValueError):
        m.claim_carrier(None, catalog, carrier)
    assert not (tmp_path / "transport-claim.json").exists()
    times = iter((100, 390))
    monkeypatch.setattr(m.time, "monotonic", lambda: next(times))
    witness = m.prepare_auth_once(lambda *args: _success())
    reopened = additional()
    monkeypatch.setattr(reopened, "_local_root", lambda: tmp_path)
    with pytest.raises(ValueError):
        reopened.claim_carrier(witness, catalog, carrier)
    monkeypatch.setattr(m.time, "monotonic", lambda: 451)
    with pytest.raises(ValueError):
        m.claim_carrier(witness, catalog, carrier)
    assert not (tmp_path / "transport-claim.json").exists()
    monkeypatch.setattr(m.time, "monotonic", lambda: 450)
    m.claim_carrier(witness, catalog, carrier)
    claim = tmp_path / "transport-claim.json"
    assert json.loads(claim.read_bytes())["capture_once_key"] == K
    assert flushed == [tmp_path] * 3
    for outcome in ("zero", "partial", "unknown"):
        with pytest.raises(FileExistsError):
            m.claim_carrier(witness, catalog, carrier)
    assert json.loads(claim.read_bytes())["authorization_sha256"] == A


def test_additional_uncertain_context_fsync_remains_spent(tmp_path, monkeypatch):
    m = additional()
    monkeypatch.setattr(m, "_remote_ledger", lambda: tmp_path)

    def uncertain(path):
        assert path == tmp_path
        raise OSError("directory flush uncertain")

    monkeypatch.setattr(m, "_sync_directory", uncertain)
    with pytest.raises(OSError, match="uncertain"):
        m.reserve_context()
    original = (tmp_path / K).read_bytes()
    assert hashlib.sha256(original).hexdigest() == K
    with pytest.raises(FileExistsError):
        m.reserve_context()
    assert (tmp_path / K).read_bytes() == original


def test_connected_additional_capture_keeps_C_R_and_normal_parent_seal(tmp_path, monkeypatch):
    from test_ivv_trusted_runner import connected_additional_capture

    raw, intent, parent, go = connected_additional_capture(tmp_path, monkeypatch)
    for obj in (raw, intent, parent, go):
        assert obj["scope_id"] == obj["capture_scope_id"] == C
        assert obj["research_scope_id"] == R and obj["capture_effect_sha256"] == E
        assert obj["authorization_sha256"] == A and obj["capture_once_key"] == K
    assert raw["counts"]["application_sends"] == 7 and raw["counts"]["contexts"] == 1
    assert parent["state"] == "NORMAL_EXIT" and len(parent["evidence_refs"]) == 8
    assert go["job_id"] == "1d05c58d-b536-4b64-b2c3-89e4217cc4ad"
    assert go["numeric_runtime_sha256"] == "8" * 64


def test_portable_connected_additional_capture(tmp_path, monkeypatch):
    from test_ivv_trusted_runner import connected_additional_capture

    raw, intent, parent, go = connected_additional_capture(tmp_path, monkeypatch, private=False)
    assert go["scope_id"] == raw["scope_id"] == C and go["research_scope_id"] == R
    assert len(parent["evidence_refs"]) == 8 and parent["termination"] == "NORMAL"


@pytest.mark.parametrize("fault", ["source", "context_fsync"])
def test_connected_additional_refuses_drift_before_sdk(tmp_path, monkeypatch, fault):
    from test_ivv_trusted_runner import connected_additional_capture

    with pytest.raises((OSError, ValueError), match="CONTROL_DIGEST|directory flush uncertain"):
        connected_additional_capture(tmp_path, monkeypatch, private=False, fault=fault)
    marker = tmp_path / "additional-once" / K
    assert marker.exists() is (fault == "context_fsync")
    assert not (tmp_path / "child/capture").exists()


def _success():
    return dict(
        returncode=0,
        timeout=False,
        cap_refusal=False,
        failure_stage=None,
        cleanup_errors=[],
        input_bytes_written=1,
        input_complete=True,
        stdout_original_bytes=0,
        stdout_count_complete=True,
        stderr_count_complete=True,
        job_closed=True,
        job_active_zero=True,
        local_process_terminal=True,
        drain_complete=True,
        job_memory_limit=134217728,
        job_active_process_limit=8,
        automatic_retry=False,
        local_transport_timeout_s=300,
        timeout_includes_drain=True,
    )


@pytest.mark.parametrize("failure", [None, "job_active_zero", "input_complete", "drain_complete"])
def test_auth_preparation_is_exclusive_and_bound_to_normal_real_transport_result(
    tmp_path, monkeypatch, failure
):
    m = additional()
    monkeypatch.setattr(m, "_local_root", lambda: tmp_path)
    monkeypatch.setattr(m, "_sync_directory", lambda path: None)
    calls = []

    def execute(peer, command, payload, seconds):
        assert (peer, command, payload, seconds) == (
            "ubuntu@quantmesh-staging-8gb.tail99d23c.ts.net",
            "/usr/bin/true",
            b"\n",
            300,
        )
        calls.append(1)
        result = _success()
        if failure:
            result[failure] = False
        return result

    assert callable(getattr(m, "prepare_auth_once", None)), "auth-only one-shot preparation missing"
    if failure:
        with pytest.raises(ValueError, match="AUTH_TRANSPORT"):
            m.prepare_auth_once(execute)
    else:
        m.prepare_auth_once(execute)
    assert (tmp_path / "auth-ready.json").exists() is (failure is None)
    assert not (tmp_path / "transport-claim.json").exists()
    with pytest.raises(FileExistsError):
        m.prepare_auth_once(execute)
    assert calls == [1]


def test_native_directory_flush_uses_owned_directory(tmp_path):
    m = additional()
    assert callable(getattr(m, "_sync_windows_directory", None)), (
        "Windows held-directory flush missing"
    )
    m._sync_directory(tmp_path)


def test_additional_runner_clock_starts_before_bootstrap(monkeypatch):
    from test_ivv_trusted_runner import runner

    r = runner()
    now = [10]
    marks = []
    monkeypatch.setattr(r.time, "monotonic", lambda: now[0])

    def bootstrap(ref, *, additional):
        assert additional is True
        now[0] = 150
        return {}, {}, None, None, None, None

    def seed(*args, **kw):
        marks.append(kw.get("started"))
        raise ValueError("stop before kernel")

    monkeypatch.setattr(r, "_bootstrap", bootstrap)
    monkeypatch.setattr(r, "_seed", seed)
    with pytest.raises(ValueError, match="stop before kernel"):
        r.run_additional_once({})
    assert marks == [10]


@pytest.mark.parametrize("controllers", ["memory pids", "memory pids cpu"])
def test_additional_unit_enables_only_its_own_delegated_controllers(monkeypatch, controllers):
    from test_ivv_trusted_runner import owned_scope, runner

    r = runner()
    name = "qm-ivv-additional-20261103-01.service"
    _, k = owned_scope(r, monkeypatch, create=False, unit=name)
    root = "/sys/fs/cgroup/system.slice/" + name
    k.nodes[root + "/cgroup.controllers"]["content"] = controllers
    if "cpu" not in controllers:
        with pytest.raises(ValueError, match="CONTROLLERS_UNAVAILABLE"):
            r._Scope(k.stack, additional=True)
        assert not k.writes
    else:
        scoped = r._Scope(k.stack, additional=True)
        assert (root + "/cgroup.subtree_control", b"+cpu +memory +pids") in k.writes
        assert scoped.manager == "manager" and scoped.leaf is not None
        assert all(path.startswith(root + "/") for path, data in k.writes)


@pytest.mark.parametrize("delivered", [0, 4, None])
def test_claimed_carrier_zero_partial_or_unknown_never_reenters_transport(
    tmp_path, monkeypatch, delivered
):
    m = additional()
    monkeypatch.setattr(m, "_local_root", lambda: tmp_path)
    witness = m.prepare_auth_once(lambda *args: _success())
    packet = b"bounded constructed carrier"
    calls = []

    def transport(peer, body, remote_seconds, local_seconds):
        assert (tmp_path / "transport-claim.json").is_file()
        assert body == packet and remote_seconds == 500 and local_seconds == 510
        calls.append(peer)
        if delivered is None:
            raise OSError("delivery uncertain")
        return {"input_bytes_written": delivered}

    assert hasattr(m, "submit_carrier_once"), "missing claimed submission boundary"
    kwargs = dict(
        catalog_sha256="6" * 64,
        carrier_sha256=hashlib.sha256(packet).hexdigest(),
        packet=packet,
        owned_transport=transport,
    )
    if delivered is None:
        with pytest.raises(OSError, match="delivery uncertain"):
            m.submit_carrier_once(witness, **kwargs)
    else:
        assert m.submit_carrier_once(witness, **kwargs) == {"input_bytes_written": delivered}
    with pytest.raises(FileExistsError):
        m.submit_carrier_once(witness, **kwargs)
    assert len(calls) == 1


def test_additional_normalization_preserves_capture_identity_and_old_entry_rejects_it():
    from test_ivv_capture_contract import SCHEDULE, facts, leaf, originals

    m = leaf()
    data = originals()
    old = m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))
    data["scope_id"] = C
    result = m.normalize_additional_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))
    assert result["bars"] == old["bars"] and result["schedule"] == old["schedule"]
    assert result["capture_evidence_sha256"] != old["capture_evidence_sha256"]
    with pytest.raises(ValueError, match="capture_identity"):
        m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))
    data["scope_id"] = R
    with pytest.raises(ValueError, match="capture_identity"):
        m.normalize_additional_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))


def test_additional_startup_pins_actual_private_approval_bytes(tmp_path, monkeypatch):
    from test_ivv_trusted_runner import check_bootstrap

    check_bootstrap(tmp_path, monkeypatch, False, additional=additional())


def test_stale_or_malformed_additional_go_fields_rejected():
    from test_ivv_trusted_runner import runner

    m = additional()
    r = runner()
    fields = dict(
        job_id=m.APPROVED.job_id,
        windows_policy_sha256=m.WINDOWS,
        output_root_digest="1" * 64,
        code={
            "kernel_version": "native-daily-v2",
            "kernel_sha256": "1" * 64,
            "policy_sha256": "2" * 64,
            "adapter_sha256": "3" * 64,
            "legacy_packaged_ancestor": "4" * 64,
        },
        adapter_sha256="5" * 64,
        gate_sha256="6" * 64,
        numeric_runtime_sha256="7" * 64,
        runtime={"python": "3.13", "calendar": "edition / version", "numpy": "2", "pandas": "3"},
    )
    assert hasattr(r, "_validate_windows_fields"), (
        "closed validated Windows startup projection missing"
    )
    r._validate_windows_fields(fields, m)
    for key, bad in (
        ("code", {}),
        ("runtime", False),
        ("job_id", "wrong"),
        ("numeric_runtime_sha256", None),
    ):
        with pytest.raises(ValueError):
            r._validate_windows_fields({**fields, key: bad}, m)
    with pytest.raises(ValueError):
        r._validate_windows_fields(
            {k: v for k, v in fields.items() if k != "numeric_runtime_sha256"}, m
        )


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("namespace", "CHILD_NAMESPACE_SHARED"),
        ("event", "RESOURCE_LIMIT_EVENT"),
        ("close", "CHILD_CAPTURE_FAILED"),
    ],
)
def test_additional_parent_native_failures_never_issue_normal_seal(
    tmp_path, monkeypatch, fault, code
):
    from test_ivv_trusted_runner import connected_additional_capture

    with pytest.raises(ValueError, match=code):
        connected_additional_capture(tmp_path, monkeypatch, private=False, fault=fault)
    assert not (tmp_path / "parent-close.json").exists()


def test_additional_cli_bad_arity_stays_in_new_task(monkeypatch):
    from test_ivv_trusted_runner import runner

    r = runner()
    failed = []
    monkeypatch.setattr(r, "put", lambda path, body: failed.append((path, body)))
    monkeypatch.setattr(r, "run_once", lambda ref: pytest.fail("additional invoked legacy runner"))
    assert r.main(["--additional-task"]) == 1
    assert (
        str(failed[0][0])
        .replace(chr(92), "/")
        .endswith("/quantmesh-ivv-additional/tasks/20261103-01/parent/runner-failure.json")
    )


@pytest.mark.parametrize("flush", ["file", "directory"])
def test_claim_fsync_uncertainty_never_submits_or_reopens(tmp_path, monkeypatch, flush):
    m = additional()
    monkeypatch.setattr(m, "_local_root", lambda: tmp_path)
    witness = m.prepare_auth_once(lambda *args: _success())

    def uncertain(*args):
        raise OSError("flush failed")

    if flush == "file":
        monkeypatch.setattr(m.os, "fsync", uncertain)
    else:
        monkeypatch.setattr(m, "_sync_directory", uncertain)
    packet = b"bounded packet"
    kw = dict(
        catalog_sha256="5" * 64,
        carrier_sha256=hashlib.sha256(packet).hexdigest(),
        packet=packet,
        owned_transport=lambda *args: pytest.fail("transport before durable unique claim"),
    )
    with pytest.raises(OSError, match="flush failed"):
        m.submit_carrier_once(witness, **kw)
    assert (tmp_path / "transport-claim.json").is_file()
    with pytest.raises(FileExistsError):
        m.submit_carrier_once(witness, **kw)


def window_controls(private):
    """Reconstruct the published selection from the repository's fixed 121-session fixture."""
    from datetime import datetime, timedelta

    from test_ivv_capture_contract import DATES, SCHEDULE

    from quantmesh.research.ivv_admission import WINDOW

    full = {
        "schema": "qm.ivv.fixed-window.v1",
        "calendar": "exchange-calendars:4.13.2:XNYS",
        "timezone": "America/New_York",
        "ceiling_date": "2026-10-29",
        "selector": "last121_completed_regular_sessions_on_or_before_ceiling",
        "count": 121,
        "warmup_count": 100,
        "observation_count": 21,
        "start": "2026-05-08",
        "warmup_end": "2026-09-30",
        "observation_start": "2026-10-01",
        "end": "2026-10-29",
        "terminal": "precommitted_last_observation_OPEN_no_final_close_signal",
        "sample_role": "development_only_retrospective",
        "date_list_sha256": "50e126ad528c49c458517407fda23ca4dcd6205d663ea4b44d49836e183f016a",
        "sessions_csv_sha256": "0a5c0949ff0f5b4743f1509671a5d7f91aca83fe232464b50cee8520ea4288ba",
        "availability": "close+30min_declared_research_assumption_not_vendor_PIT_proof",
    }
    full["sessions"] = [
        {
            "index": i,
            "date": row["date"],
            "role": "warmup" if i < 100 else "observation",
            "open_utc": row["open"],
            "close_utc": row["close"],
            "declared_available_at_utc": (
                datetime.fromisoformat(row["close"]) + timedelta(minutes=30)
            ).isoformat(),
            "terminal_open": i == 120,
        }
        for i, row in enumerate(SCHEDULE)
    ]

    def canonical(v):
        return json.dumps(v, sort_keys=True, separators=(",", ":")).encode()

    controls = {
        "WINDOW.json": json.dumps(full, separators=(",", ":")).encode() + b"\r\n",
        "INPUT-WINDOW.json": canonical(WINDOW),
        "SCHEDULE.json": canonical(SCHEDULE),
        "DATES.txt": ("\n".join(DATES) + "\n").encode(),
    }
    if private:
        root = BASE.parent / "contracts"
        exact = {name: (root / name).read_bytes() for name in controls}
        assert controls == exact
        return exact
    return controls


def test_additional_free_gate_uses_registered_remote_hold_and_preserves_legacy_floor(
    tmp_path, monkeypatch
):
    from test_ivv_dev_diagnostic import kernel_fixture

    _, m, _, _, _, _ = kernel_fixture(tmp_path, monkeypatch)
    actor = m._native_actor()
    from types import SimpleNamespace

    boundary = 53687091200 + 18 * 1024 * 1024
    monkeypatch.setattr(
        m.os, "statvfs", lambda path: SimpleNamespace(f_bavail=boundary, f_frsize=1)
    )
    m._native_recheck(actor, tmp_path, additional=True)
    with pytest.raises(ValueError, match="fresh_capture_capacity"):
        m._native_recheck(actor, tmp_path)
    boundary -= 1
    with pytest.raises(ValueError, match="fresh_capture_capacity"):
        m._native_recheck(actor, tmp_path, additional=True)
    boundary = 53687091200
    m._native_recheck(actor, tmp_path, additional=True, live=True)
