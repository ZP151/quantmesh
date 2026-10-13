"""Durable fixture baseline and owned worker fault/recovery acceptance."""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_research_jobs import request_for

from quantmesh.research.baselines import run_baseline_report
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.reports import ReportRegistry
from tests.research_fixtures import pinned_lake


@pytest.fixture
def setup(tmp_path):
    if os.name != "nt":
        pytest.skip(
            "owned baseline execution requires Windows Job Objects; Linux rejects explicitly"
        )
    lake = tmp_path / "lake"
    pinned_lake(lake)
    store = SQLiteJobStore(tmp_path / "jobs.sqlite", lake_root=lake)
    return store, lake


def test_pinned_baseline_matches_existing_engine(setup, tmp_path):
    from quantmesh.research.job_runner import run_next_job

    store, lake = setup
    request = request_for(lake)
    submitted = store.submit("local", "baseline", request)
    done = run_next_job(store, "worker", lake, store.artifact_root)
    assert done.job_id == submitted.job_id and done.state == "succeeded"
    reopened = SQLiteJobStore(store.path, lake_root=lake).get("local", submitted.job_id)
    assert reopened == done
    envelope = json.loads((store.artifact_root / done.artifacts[0].object_key).read_bytes())
    expected = run_baseline_report(
        dataset="equities",
        revision=request.dataset.revision,
        strategy=request.strategy_id,
        interval=request.interval,
        universe=request.universe,
        window_spec=request.window_spec,
        costs=request.costs,
        commit=done.implementation_digest,
        registry=ReportRegistry(tmp_path / "expected", lake_root=lake),
    ).model_dump(mode="json")
    assert envelope["result"]["metrics"] == expected["metrics"]
    assert envelope["result"]["windows"] == expected["windows"]
    assert envelope["result"]["evidence"]["request_digest"] == submitted.request_digest
    assert run_next_job(store, "worker", lake, store.artifact_root) is None


@pytest.mark.parametrize("fault", ["manifest", "shard", "v2", "rights", "engine"])
def test_changed_inputs_reject_before_execution(setup, fault, monkeypatch):
    from quantmesh.research import job_runner

    store, lake = setup
    submitted = store.submit("local", "changed", request_for(lake))
    path = lake / "equities" / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if fault == "engine":
        original = job_runner.get_strategy
        monkeypatch.setattr(
            job_runner,
            "get_strategy",
            lambda *a: original(*a).model_copy(update={"implementation_digest": "a" * 64}),
        )
    elif fault == "shard":
        shard = next((lake / "equities").rglob("*.parquet"))
        shard.write_bytes(shard.read_bytes() + b"changed")
    else:
        manifest.update(
            {"schema_version": 2}
            if fault == "v2"
            else {"license": "unknown"}
            if fault == "rights"
            else {"revision": 99}
        )
        path.write_text(json.dumps(manifest))
    done = job_runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert done.job_id == submitted.job_id and done.state == "failed"
    assert done.error_code == ("worker_failed" if fault == "engine" else "dataset_rejected")
    assert done.artifacts == []


def test_two_attempts_have_identical_canonical_bytes_with_separate_receipts(setup):
    from quantmesh.research.job_runner import run_next_job

    store, lake = setup
    request = request_for(lake)
    first = store.submit("local", "first", request)
    second = store.submit("local", "second", request)
    a = run_next_job(store, "one", lake, store.artifact_root)
    b = run_next_job(store, "two", lake, store.artifact_root)
    assert [a.job_id, b.job_id] == [first.job_id, second.job_id]
    assert a.state == b.state == "succeeded"
    assert a.artifacts[0].sha256 == b.artifacts[0].sha256
    receipts = [
        json.loads(next((store.artifact_root / j.job_id).rglob("receipt.json")).read_bytes())
        for j in (a, b)
    ]
    assert receipts[0]["report"]["created_at"] != receipts[1]["report"]["created_at"]
    assert receipts[0]["runtime"] == receipts[1]["runtime"]


@pytest.mark.parametrize("fault", ["expired", "reclaimed", "cancelled"])
def test_old_attempt_and_cancel_cannot_publish(setup, monkeypatch, fault):
    from quantmesh.research import job_runner

    store, lake = setup
    job = store.submit("local", "fenced", request_for(lake))
    publish = job_runner.publish_result

    def revoke_after_upload(claimed, raw, root):
        ref = publish(claimed, raw, root)
        if fault == "cancelled":
            store.request_cancel("local", job.job_id)
        else:
            future = datetime.now(UTC) + timedelta(seconds=61)
            store._clock = lambda: future
            if fault == "reclaimed":
                replacement = store.claim("new-owner", future)
                assert replacement.attempt == 2
        return ref

    monkeypatch.setattr(job_runner, "publish_result", revoke_after_upload)
    result = job_runner.run_next_job(store, "old-owner", lake, store.artifact_root)
    assert result.state != "succeeded" and result.artifacts == []
    assert list((store.artifact_root / job.job_id).glob("*.json"))


def test_crash_after_object_upload_leaves_no_success(setup, monkeypatch):
    from quantmesh.research import job_runner

    store, lake = setup
    job = store.submit("local", "crash", request_for(lake))
    publish = job_runner.publish_result

    def crash(claimed, raw, root):
        publish(claimed, raw, root)
        raise SystemExit(23)

    monkeypatch.setattr(job_runner, "publish_result", crash)
    with pytest.raises(SystemExit):
        job_runner.run_next_job(store, "crashed", lake, store.artifact_root)
    reopened = SQLiteJobStore(store.path, lake_root=lake).get("local", job.job_id)
    assert reopened.state == "running" and reopened.artifacts == []


def test_timeout_kills_only_owned_worker(setup, monkeypatch, tmp_path):
    from quantmesh.research import job_runner

    store, lake = setup
    marker = tmp_path / "owned-pid.json"
    request = request_for(lake, budget={"timeout_seconds": 2})
    store.submit("local", "timeout", request)
    # A controlled worker tree, deliberately blocked before baseline. Real sibling is unrelated.
    boot = (
        "import sys,time,subprocess,json,os,pathlib; sys.stdin.readline(); "
        "p=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(120)']); "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]));time.sleep(120)"
    )
    monkeypatch.setattr(
        job_runner, "_child_command", lambda _: [sys.executable, "-B", "-c", boot, str(marker)]
    )
    sibling = subprocess.Popen([sys.executable, "-B", "-c", "import time;time.sleep(120)"])
    try:
        start = time.monotonic()
        result = job_runner.run_next_job(store, "timeout-worker", lake, store.artifact_root)
        assert result.state == "failed" and result.error_code == "timeout"
        assert time.monotonic() - start < 8
        assert sibling.poll() is None
        pids = json.loads(marker.read_bytes())
        if os.name == "nt":
            import ctypes

            for pid in pids:
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    status = ctypes.c_ulong()
                    assert ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(status))
                    ctypes.windll.kernel32.CloseHandle(handle)
                    assert status.value != 259
        else:
            for pid in pids:
                status_path = Path(f"/proc/{pid}/stat")
                assert not status_path.exists() or status_path.read_text().split()[2] == "Z"
    finally:
        sibling.terminate()
        sibling.wait(timeout=5)


def test_active_child_is_stopped_on_cancellation(setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from quantmesh.research import job_runner

    store, lake = setup
    job = store.submit("local", "cancel", request_for(lake))
    real_child = job_runner._OwnedChild
    children = []

    def launch(*args):
        child = real_child(*args)
        children.append(child)
        return child

    monkeypatch.setattr(job_runner, "_OwnedChild", launch)
    monkeypatch.setattr(
        job_runner,
        "_child_command",
        lambda _: [
            sys.executable,
            "-B",
            "-c",
            "import sys,time;sys.stdin.readline();time.sleep(120)",
        ],
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            job_runner.run_next_job, store, "cancel-worker", lake, store.artifact_root
        )
        deadline = time.monotonic() + 10
        while not children and time.monotonic() < deadline:
            time.sleep(0.05)
        assert children
        store.request_cancel("local", job.job_id)
        assert future.result(timeout=5).state == "cancelled"
    assert children[0].process.poll() is not None


def test_fractional_cpu_is_explicitly_unsupported(setup):
    from quantmesh.research.job_runner import run_next_job

    store, lake = setup
    job = store.submit("local", "unsupported", request_for(lake, budget={"cpu_limit": 0.5}))
    result = run_next_job(store, "worker", lake, store.artifact_root)
    assert result.state == "failed" and result.artifacts == []
    assert not list((store.artifact_root / job.job_id).rglob("receipt.json"))


@pytest.mark.skipif(os.name != "nt", reason="Windows native Job Object witness")
def test_windows_launcher_cannot_escape_before_assignment(tmp_path, monkeypatch):
    import ctypes

    from quantmesh.research import job_runner
    from quantmesh.research.jobs import RunBudget

    marker = tmp_path / "boot-pid.txt"
    popen = subprocess.Popen

    def slow_parent(*args, **kwargs):
        process = popen(*args, **kwargs)
        time.sleep(0.4)  # Deterministically let the venv launcher create Python before assignment.
        return process

    monkeypatch.setattr(job_runner.subprocess, "Popen", slow_parent)
    command = [
        sys.executable,
        "-B",
        "-c",
        "import sys,os,pathlib,time;"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));sys.stdin.readline();time.sleep(120)",
        str(marker),
    ]
    child = job_runner._OwnedChild(command, RunBudget(), tmp_path)
    handle = None
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        handle = kernel.OpenProcess(0x1000 | 1, False, int(marker.read_text()))
        assert handle
        child.close()
        status = ctypes.c_ulong()
        assert kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(status))
        assert status.value != 259  # The actual interpreter is in the owned job, not escaped.
    finally:
        if handle:
            kernel.TerminateProcess(ctypes.c_void_p(handle), 1)
            kernel.CloseHandle(ctypes.c_void_p(handle))
        if not child.log.closed:
            child.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows hard memory/affinity witness")
def test_windows_memory_and_one_cpu_limits_are_real(tmp_path):
    from quantmesh.research.job_runner import _OwnedChild
    from quantmesh.research.jobs import RunBudget

    command = [
        sys.executable,
        "-B",
        "-c",
        "import sys,ctypes;sys.stdin.readline();"
        "k=ctypes.windll.kernel32;a=ctypes.c_size_t();b=ctypes.c_size_t();"
        "k.GetProcessAffinityMask(ctypes.c_void_p(-1),ctypes.byref(a),ctypes.byref(b));"
        "assert a.value.bit_count()==1;"
        "exec('try:\\n x=bytearray(256*1024*1024)\\nexcept MemoryError:\\n sys.exit(78)');"
        "sys.exit(79)",
    ]
    child = _OwnedChild(command, RunBudget(memory_mib=64), tmp_path)
    try:
        assert child.process.wait(timeout=5) == 78
    finally:
        child.close()


@pytest.mark.parametrize("operation", ["affinity", "limits", "assign"])
@pytest.mark.skipif(os.name != "nt", reason="Windows ownership failure witness")
def test_failed_windows_setup_reaps_direct_child(tmp_path, monkeypatch, operation):
    import ctypes

    from quantmesh.research import job_runner
    from quantmesh.research.jobs import RunBudget

    processes = []
    popen = subprocess.Popen

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(job_runner.subprocess, "Popen", capture)
    method = {
        "affinity": "GetProcessAffinityMask",
        "limits": "SetInformationJobObject",
        "assign": "AssignProcessToJobObject",
    }[operation]
    monkeypatch.setattr(ctypes.windll.kernel32, method, lambda *args: 0)
    try:
        with pytest.raises(job_runner.UnsupportedLimits):
            job_runner._OwnedChild(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    "import sys,time;sys.stdin.readline();time.sleep(120)",
                ],
                RunBudget(),
                tmp_path,
            )
        assert processes and processes[0].poll() is not None
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def test_linux_without_crash_safe_limits_is_explicitly_rejected(tmp_path, monkeypatch):
    from quantmesh.research import job_runner
    from quantmesh.research.jobs import RunBudget

    monkeypatch.setattr(job_runner.sys, "platform", "linux")
    with pytest.raises(job_runner.UnsupportedLimits):
        child = job_runner._OwnedChild(
            [sys.executable, "-B", "-c", "print('unsafe')"], RunBudget(), tmp_path
        )
        child.close()


def test_boot_eof_does_not_authorize_baseline(tmp_path):
    from quantmesh.research.job_runner import _child_command

    result = subprocess.run(_child_command(tmp_path), input=b"", capture_output=True, timeout=8)
    assert result.returncode == 3 and result.stderr == b""


def test_runtime_digest_binds_python_build(monkeypatch):
    from quantmesh.research import job_runner

    first = job_runner.runtime_fingerprint()
    monkeypatch.setattr(job_runner.sys, "version", sys.version + " different-build")
    second = job_runner.runtime_fingerprint()
    assert first["build_digest"] == second["build_digest"]
    assert first["dependency_digest"] != second["dependency_digest"]


def test_child_command_disables_bytecode_before_boot(tmp_path):
    from quantmesh.research.job_runner import _child_command

    assert _child_command(tmp_path)[1] == "-B"


def test_owned_child_poll_uses_actual_popen_exit():
    from types import SimpleNamespace

    from quantmesh.research.job_runner import _OwnedChild

    child = object.__new__(_OwnedChild)
    child.process = SimpleNamespace(poll=lambda: 7, returncode=0)
    assert child.poll() == 7
    child.pulse()  # Windows ownership requires no pulse channel.


@pytest.fixture
def child_receipt_fixture(tmp_path):
    from quantmesh.research.job_artifacts import _canonical, canonical_result

    lake = tmp_path / "lake"
    pinned_lake(lake)
    store = SQLiteJobStore(tmp_path / "queue.sqlite", lake_root=lake)
    request = request_for(lake)
    store.submit("local", "receipt", request)
    job = store.claim("owner", datetime.now(UTC))
    report = run_baseline_report(
        dataset="equities",
        revision=request.dataset.revision,
        strategy=request.strategy_id,
        interval=request.interval,
        universe=request.universe,
        window_spec=request.window_spec,
        costs=request.costs,
        commit=job.implementation_digest,
        registry=ReportRegistry(tmp_path / "direct", lake_root=lake),
    )
    runtime = dict(build_digest="a" * 64, dependency_digest="b" * 64)
    report.evidence.update(
        runtime,
        request_digest=job.request_digest,
        manifest_digest=request.dataset.manifest_digest,
        export_digest=request.dataset.export_digest,
    )
    output = tmp_path / "output"
    output.mkdir()
    raw = canonical_result(report)
    receipt = dict(
        report=report.model_dump(mode="json"), runtime=runtime, attempt=job.attempt, owner="owner"
    )
    (output / "result.json").write_bytes(raw)
    (output / "receipt.json").write_bytes(_canonical(receipt))
    return job, runtime, output, receipt, raw


def test_child_receipt_accepts_canonical_bound_result(child_receipt_fixture):
    from quantmesh.research import job_runner

    job, runtime, output, _, raw = child_receipt_fixture
    assert job_runner._validated_child_result(job, "owner", runtime, output) == raw


@pytest.mark.parametrize("fault", ["owner", "attempt", "runtime", "symlink", "large"])
def test_child_receipt_rejects_wrong_identity_or_file(child_receipt_fixture, fault, monkeypatch):
    from quantmesh.research import job_runner
    from quantmesh.research.job_artifacts import _canonical

    job, runtime, output, receipt, _ = child_receipt_fixture
    path = output / "receipt.json"
    if fault in {"owner", "attempt", "runtime"}:
        receipt[fault] = {"injected": "host"} if fault == "runtime" else "other"
        path.write_bytes(_canonical(receipt))
    elif fault == "large":
        monkeypatch.setattr(job_runner, "_MAX_OUTPUT_BYTES", 10)
    else:
        target = output / "saved.json"
        path.rename(target)
        try:
            path.symlink_to(target.name)
        except OSError:
            pytest.skip("OS does not permit fixture symlinks")
    with pytest.raises(ValueError):
        job_runner._validated_child_result(job, "owner", runtime, output)


@pytest.mark.skipif(os.name != "nt", reason="Windows abrupt-owner tree witness")
def test_owner_death_kills_tree_and_preserves_sibling(tmp_path):
    import ctypes

    from quantmesh.research.job_runner import _OwnedChild
    from quantmesh.research.jobs import RunBudget

    marker = tmp_path / "tree.json"
    tree = (
        "import sys,time,subprocess,json,os,pathlib;sys.stdin.readline();"
        "p=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(120)']);"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]));time.sleep(120)"
    )
    script = (
        "import sys,os,time;sys.stdin.readline();from pathlib import Path;"
        "from quantmesh.research.job_runner import _OwnedChild;"
        "from quantmesh.research.jobs import RunBudget;"
        "child=_OwnedChild([sys.executable,'-B','-c',sys.argv[2],sys.argv[1]],RunBudget(),Path(sys.argv[3]));"
        "exec('while not Path(sys.argv[1]).exists():\\n time.sleep(.02)');os._exit(24)"
    )
    inner_dir = tmp_path / "inner"
    inner_dir.mkdir()
    sibling = subprocess.Popen([sys.executable, "-B", "-c", "import time;time.sleep(120)"])
    owner = _OwnedChild(
        [sys.executable, "-B", "-c", script, str(marker), tree, str(inner_dir)],
        RunBudget(),
        tmp_path,
    )
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    try:
        assert owner.process.wait(timeout=12) == 24
        assert sibling.poll() is None
        for pid in json.loads(marker.read_bytes()):
            handle = kernel.OpenProcess(0x1000, False, pid)
            if handle:
                try:
                    status = ctypes.c_ulong()
                    assert kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(status))
                    assert status.value != 259
                finally:
                    kernel.CloseHandle(ctypes.c_void_p(handle))
    finally:
        owner.close()
        sibling.terminate()
        sibling.wait(timeout=5)


def test_owned_worker_crash_recovers_within_ninety_seconds(setup, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from quantmesh.research import job_runner
    from quantmesh.research.job_runner import run_next_job

    store, lake = setup
    sibling = store.submit("local", "active-sibling", request_for(lake))
    real_command = job_runner._child_command
    children = []
    real_child = job_runner._OwnedChild

    def command(attempt):
        if json.loads((attempt / "job.json").read_bytes())["job_id"] == sibling.job_id:
            return [
                sys.executable,
                "-B",
                "-c",
                "import sys,time;sys.stdin.readline();time.sleep(120)",
            ]
        return real_command(attempt)

    def launch(*args):
        child = real_child(*args)
        children.append(child)
        return child

    monkeypatch.setattr(job_runner, "_child_command", command)
    monkeypatch.setattr(job_runner, "_OwnedChild", launch)
    pool = ThreadPoolExecutor(max_workers=1)
    sibling_future = pool.submit(run_next_job, store, "sibling-worker", lake, store.artifact_root)
    deadline = time.monotonic() + 10
    while not children and time.monotonic() < deadline:
        time.sleep(0.05)
    assert children and not sibling_future.done()
    try:
        _recover_under_load(store, lake, tmp_path, sibling, children[0])
    finally:
        store.request_cancel("local", sibling.job_id)
        assert sibling_future.result(timeout=5).state == "cancelled"
        pool.shutdown(wait=True)


def _recover_under_load(store, lake, tmp_path, sibling, sibling_child):
    from quantmesh.research.job_runner import _OwnedChild, run_next_job
    from quantmesh.research.jobs import RunBudget

    job = store.submit("local", "recovery", request_for(lake))
    # Actual separate owned worker exits after upload, before durable finish.
    script = (
        "import sys;sys.stdin.readline();from pathlib import Path;"
        "from quantmesh.research import job_runner as r;"
        "from quantmesh.research.job_store import SQLiteJobStore;"
        "publish=r.publish_result;"
        "exec('def crash(j,b,p):\\n publish(j,b,p)\\n raise SystemExit(23)');"
        "r.publish_result=crash;"
        "s=SQLiteJobStore(Path(sys.argv[1]),lake_root=Path(sys.argv[2]));"
        "r.run_next_job(s,'dead-worker',Path(sys.argv[2]),s.artifact_root)"
    )
    directory = tmp_path / "owner"
    directory.mkdir()
    child = _OwnedChild(
        [sys.executable, "-B", "-c", script, str(store.path), str(lake)], RunBudget(), directory
    )
    try:
        assert child.process.wait(timeout=20) == 23
    finally:
        child.close()
    crashed = store.get("local", job.job_id)
    assert crashed.state == "running" and crashed.artifacts == []
    assert store.get("local", sibling.job_id).state == "running"
    assert store.claim("third-worker", datetime.now(UTC)) is None
    start = time.monotonic()
    while datetime.now(UTC) <= crashed.lease_expires_at:
        time.sleep(0.1)
    done = run_next_job(
        SQLiteJobStore(store.path, lake_root=lake), "recovered", lake, store.artifact_root
    )
    elapsed = time.monotonic() - start
    assert elapsed < 90 and done.attempt == 2 and done.state == "succeeded"
    assert sibling_child.process.poll() is None
    assert store.get("local", sibling.job_id).state == "running"
    artifacts = list((store.artifact_root / job.job_id).glob("*.json"))
    assert len(artifacts) == len(done.artifacts) == 1
    evidence = dict(
        recovery_seconds=elapsed,
        lease_seconds=60,
        heartbeat_seconds=15,
        attempts=done.attempt,
        active_job_load=2,
        sibling_survived=True,
        artifact_digest=done.artifacts[0].sha256,
        fixture_only=True,
    )
    (tmp_path / "recovery-evidence.json").write_text(json.dumps(evidence))
