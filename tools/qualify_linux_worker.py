"""Test-owned OCI witnesses. Prerequisite-only and missing-native runs exit 2.

Never installs, starts, builds or pulls anything. No baseline/report certificate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Direct execution from a checkout, without a global installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantmesh.research.jobs import RunBudget  # noqa: E402
from quantmesh.research.linux_owned import (  # noqa: E402
    PYTHON_PATH,
    LinuxContainmentError,
    LinuxExecutionProfile,
    LinuxOwnedProcess,
    _safe_path,
    bootstrap_digest,
)

REQUIRED = (
    "normal",
    "nonzero",
    "aggregate_oom",
    "cpu_quota",
    "timeout",
    "owner_loss",
    "cli_loss",
    "hung_attach",
    "cancel",
    "lease_loss",
    "output_limit",
    "reparented_descendant",
    "input_immutable",
    "isolation",
    "sibling_survival",
)
SLEEP = "import time;time.sleep(120)"


def load_profile(path: Path) -> LinuxExecutionProfile:
    doc = json.loads(path.read_text())
    if set(doc) != {"endpoint", "docker_cli", "image_id", "uid", "gid", "fixture_root"}:
        raise LinuxContainmentError("invalid_profile")
    doc["docker_cli"] = Path(doc["docker_cli"])
    doc["fixture_root"] = Path(doc["fixture_root"])
    return LinuxExecutionProfile(**doc)


def _wait(process: LinuxOwnedProcess, sibling: LinuxOwnedProcess, *, pulses=True) -> int:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        sibling.pulse()
        # Do not call poll while running: its host timeout/size rescue is not
        # evidence that PID1 enforced anything. Inspect actual stopped status.
        state = process._inspect()["State"]
        if not state["Running"]:
            process.poll()  # Record host interpretation only after actual termination.
            return int(state["ExitCode"])
        if pulses:
            try:
                process.pulse()
            except LinuxContainmentError:
                state = process._inspect()["State"]
                if not state["Running"]:
                    process.poll()
                    return int(state["ExitCode"])
                raise
        time.sleep(0.5)
    raise LinuxContainmentError("witness_timeout")


def _owner(profile_path: Path, directory: Path) -> int:
    profile = load_profile(profile_path)
    worker = LinuxOwnedProcess(
        profile,
        [PYTHON_PATH, "-c", SLEEP],
        RunBudget(memory_mib=128, timeout_seconds=20),
        directory / "inputs",
        directory / "attempt",
    )
    (directory / "owner.json").write_text(
        json.dumps({"id": worker.container_id, "nonce": worker.nonce})
    )
    worker.pulse()
    # Abrupt owner death: no Python finalizer/close. PID1 must stop independently.
    os._exit(23)


def native_checks(
    profile: LinuxExecutionProfile, output: Path, profile_path: Path, checks: dict
) -> None:
    if not output.is_relative_to(profile.fixture_root):
        raise LinuxContainmentError("output_outside_owned_root")
    inputs = output / "inputs"
    inputs.mkdir()
    source = inputs / "fixture.txt"
    source.write_text("immutable fixture\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    sibling = LinuxOwnedProcess(
        profile,
        [PYTHON_PATH, "-c", SLEEP],
        RunBudget(memory_mib=128, timeout_seconds=120),
        inputs,
        output / "sibling",
    )

    def run(name, script, *, expected=0, memory=128, timeout=20, pulses=True):
        process = LinuxOwnedProcess(
            profile,
            [PYTHON_PATH, "-c", script],
            RunBudget(memory_mib=memory, timeout_seconds=timeout),
            inputs,
            output / name,
        )
        try:
            code = _wait(process, sibling, pulses=pulses)
            checks[name] = {
                "passed": code == expected,
                "actual_exit": code,
                "expected_exit": expected,
                "evidence": dict(process.evidence),
            }
            if sibling.poll() is not None:
                raise LinuxContainmentError("sibling_lost")
            return process
        finally:
            process.close()

    try:
        run("normal", "pass")
        run("nonzero", "raise SystemExit(7)", expected=7)
        # Four simultaneous 32 MiB descendant allocations exceed 96 MiB together.
        oom = run(
            "aggregate_oom",
            """
import subprocess,sys
children=[subprocess.Popen([sys.executable,'-c',
 'import time;x=bytearray(32*1024*1024);time.sleep(8)']) for _ in range(4)]
codes=[p.wait() for p in children]
sys.exit(137 if any(c!=0 for c in codes) else 0)
""",
            memory=96,
            expected=137,
        )
        checks["aggregate_oom"]["passed"] &= bool(oom.evidence["oom_killed"])
        # Actual cgroup CPU use and throttling under four competing descendants.
        cpu = run(
            "cpu_quota",
            """
import json,subprocess,sys,time
from pathlib import Path
def stats():
 return dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())
before=stats();start=time.monotonic()
script='import time;end=time.monotonic()+4\\nwhile time.monotonic()<end: pass'
children=[subprocess.Popen([sys.executable,'-c',script]) for _ in range(4)]
for p in children: p.wait()
after=stats();elapsed=time.monotonic()-start
usage=(int(after['usage_usec'])-int(before['usage_usec']))/1e6
throttled=int(after['nr_throttled'])-int(before['nr_throttled'])
Path('/output/cpu.json').write_text(json.dumps(dict(elapsed=elapsed,usage=usage,
 throttled=throttled)))
sys.exit(0 if usage<=elapsed*1.2 and throttled>0 else 1)
""",
        )
        checks["cpu_quota"]["measurement"] = json.loads((cpu.output / "cpu.json").read_text())
        run("timeout", SLEEP, timeout=2, expected=124)
        run(
            "output_limit",
            "import sys;sys.stdout.write('x'*(18*1024*1024));sys.stdout.flush()",
            expected=125,
        )
        # Double-fork/setsid orphan survives process-group cleanup but cannot survive PID1.
        run(
            "reparented_descendant",
            """
import os,time
if os.fork()==0:
 os.setsid()
 if os.fork()==0:
  time.sleep(120)
 os._exit(0)
time.sleep(.3)
""",
        )
        run(
            "input_immutable",
            """
from pathlib import Path
try: Path('/inputs/fixture.txt').write_text('changed')
except OSError: pass
else: raise SystemExit(1)
""",
        )
        checks["input_immutable"]["passed"] &= (
            hashlib.sha256(source.read_bytes()).hexdigest() == digest
        )
        run(
            "isolation",
            """
import os,socket
from pathlib import Path
assert os.getuid()!=0
assert os.read(0,1)==b''
assert not any(k for k in os.environ if k not in {'PATH','LANG','LC_CTYPE'})
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines()
 if ':' in line)
assert int(status['CapEff'].strip(),16)==0
assert status['NoNewPrivs'].strip()=='1'
assert not Path('/var/run/docker.sock').exists()
assert not Path('/run/docker.sock').exists()
assert not Path('/root/.ssh').exists()
assert not Path('/root/.docker').exists()
assert not Path('/proc/net/route').read_text().splitlines()[1:]
s=socket.socket();s.settimeout(.3)
try: s.connect(('192.0.2.1',9))
except OSError: pass
else: raise SystemExit(1)
""",
        )
        for name in ("cancel", "lease_loss"):
            process = LinuxOwnedProcess(
                profile,
                [PYTHON_PATH, "-c", SLEEP],
                RunBudget(memory_mib=128, timeout_seconds=20),
                inputs,
                output / name,
            )
            process.close()
            # inspect exact removed ID: daemon must refuse, not silently running.
            try:
                profile.invoke(["inspect", process.container_id])
            except LinuxContainmentError:
                removed = True
            else:
                removed = False
            checks[name] = {
                "passed": removed and sibling.poll() is None,
                "evidence": process.evidence,
            }
        process = LinuxOwnedProcess(
            profile,
            [PYTHON_PATH, "-c", SLEEP],
            RunBudget(memory_mib=128, timeout_seconds=20),
            inputs,
            output / "cli_loss",
        )
        process.transport.close()  # Actual CLI connection death, no rm yet.
        try:
            code = _wait(process, sibling, pulses=False)
            checks["cli_loss"] = {
                "passed": code != 0 and process.evidence["elapsed_seconds"] <= 12,
                "evidence": dict(process.evidence),
            }
        finally:
            process.close()
        # Keep stdin open while the attachment itself is suspended. The five-second
        # deadline must expire without EOF, Docker CLI progress or host removal.
        if os.name != "posix":
            raise LinuxContainmentError("hung_attachment_witness_requires_linux_owner")
        process = LinuxOwnedProcess(
            profile,
            [PYTHON_PATH, "-c", SLEEP],
            RunBudget(memory_mib=128, timeout_seconds=20),
            inputs,
            output / "hung_attach",
        )
        try:
            process.pulse()
            last_pulse = time.monotonic()
            os.kill(process.transport.process.pid, signal.SIGSTOP)
            code = _wait(process, sibling, pulses=False)
            elapsed = time.monotonic() - last_pulse
            checks["hung_attach"] = {
                "passed": code == 124 and 4.5 <= elapsed <= 8,
                "since_last_pulse_seconds": elapsed,
                "evidence": dict(process.evidence),
            }
        finally:
            process.close()
        owner_dir = output / "owner_loss"
        owner_dir.mkdir()
        (owner_dir / "inputs").mkdir()
        started = time.monotonic()
        owner = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--internal-owner",
                str(owner_dir),
                "--profile",
                str(profile_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        while owner.poll() is None and time.monotonic() - started < 15:
            sibling.pulse()
            time.sleep(0.5)
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
            raise LinuxContainmentError("owner_fixture_failed")
        identity = json.loads((owner_dir / "owner.json").read_text())
        # Reconstitute exact owned identity only, for observation/cleanup after the crash.
        crashed = object.__new__(LinuxOwnedProcess)
        crashed.profile, crashed.container_id, crashed.nonce = (
            profile,
            identity["id"],
            identity["nonce"],
        )
        crashed.transport, crashed.closed = None, False
        crashed.evidence, crashed.started = {}, started
        crashed.output = owner_dir / "attempt"
        crashed.budget = RunBudget(memory_mib=128, timeout_seconds=20)
        try:
            code = _wait(crashed, sibling, pulses=False)
            checks["owner_loss"] = {
                "passed": owner.returncode == 23
                and code != 0
                and crashed.evidence["elapsed_seconds"] <= 15,
                "evidence": dict(crashed.evidence),
                "owner_exit": owner.returncode,
            }
        finally:
            crashed.close()
        checks["sibling_survival"] = {
            "passed": sibling.poll() is None,
            "evidence": dict(sibling.evidence),
        }
    finally:
        sibling.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-fixtures", action="store_true")
    parser.add_argument("--internal-owner", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.internal_owner:
        return _owner(args.profile, args.internal_owner)
    if args.output is None:
        parser.error("--output is required")
    output = _safe_path(args.output.absolute())
    output.mkdir(parents=False, exist_ok=False)
    result = {
        "status": "pending",
        "native_qualified": False,
        "required_native_checks": list(REQUIRED),
        "checks": {},
        "bootstrap_sha256": bootstrap_digest(),
        "scope": "Task1 containment only",
    }
    code = 2
    try:
        profile = load_profile(args.profile)
        result["runtime"] = profile.prerequisites()
        if args.native_fixtures:
            native_checks(profile, output, args.profile.resolve(), result["checks"])
            passed = all(result["checks"].get(name, {}).get("passed") is True for name in REQUIRED)
            result.update(native_qualified=passed, status="qualified" if passed else "failed")
            code = 0 if passed else 1
        else:
            result["reason"] = "native_witnesses_not_run"
    except (LinuxContainmentError, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        result["reason"] = (
            str(exc) if isinstance(exc, LinuxContainmentError) else "fixture_unavailable"
        )
    (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "native_qualified": result["native_qualified"]}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
