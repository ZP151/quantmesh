"""Fixed IVV numerical child; reuse the existing owned Windows Job Object.

The web viewer survives the numerical child. Ordinary system paging is allowed
by the separately pinned human approval; commit is neither RSS nor swap zero.
No provider imports, arbitrary commands, new environment or engine changes.
"""

import ctypes
import io
import math
import os
import sys
import threading
import time
from pathlib import Path

from quantmesh.research.job_runner import _ExtendedLimits, _OwnedChild
from quantmesh.research.jobs import RunBudget

COMMIT_BYTES = 536870912
ARTIFACT_BYTES = 8388608
WINDOWS_POLICY_SHA = "eba49b57044c1883c185fd3d844a8f645cfd64dc058104c63b820d34c65abb63"


def ensure_capacity(root, reserved):
    used = sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())
    if reserved < 0 or used + reserved > ARTIFACT_BYTES:
        raise ValueError("numeric_artifact_capacity")


def _readback(child):
    """Read kernel limits AND membership; JSON declarations cannot satisfy this."""
    kernel = ctypes.windll.kernel32
    limits = _ExtendedLimits()
    handle = ctypes.c_void_p(child.job_handle)
    if not kernel.QueryInformationJobObject(
        handle, 9, ctypes.byref(limits), ctypes.sizeof(limits), None
    ):
        raise ValueError("job_readback")
    belongs = ctypes.c_int()
    if (
        not kernel.IsProcessInJob(
            ctypes.c_void_p(int(child.process._handle)), handle, ctypes.byref(belongs)
        )
        or not belongs.value
    ):
        raise ValueError("job_membership")
    affinity = limits.basic.affinity
    actual, system = ctypes.c_size_t(), ctypes.c_size_t()
    if (
        not kernel.GetProcessAffinityMask(
            ctypes.c_void_p(int(child.process._handle)), ctypes.byref(actual), ctypes.byref(system)
        )
        or actual.value != affinity
    ):
        raise ValueError("process_affinity")
    if (
        limits.basic.flags & 0x2210 != 0x2210
        or limits.basic.flags & 0x1800  # no breakaway or silent breakaway
        or limits.job_memory != COMMIT_BYTES
        or not affinity
        or affinity & (affinity - 1)
    ):
        raise ValueError("job_limits")
    return {
        "affinity": affinity,
        "process_affinity": actual.value,
        "kernel_flags": limits.basic.flags,
        "job_commit_bytes": limits.job_memory,
        "child_membership_verified": True,
    }


class _Accounting(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_longlong) for name in ("user", "kernel", "period_user", "period_kernel")
    ] + [(name, ctypes.c_ulong) for name in ("faults", "total", "active", "terminated")]


def _active(child):
    info = _Accounting()
    if not ctypes.windll.kernel32.QueryInformationJobObject(
        ctypes.c_void_p(child.job_handle), 1, ctypes.byref(info), ctypes.sizeof(info), None
    ):
        raise ValueError("job_accounting")
    return info.active


def validate_close_receipt(value, code):
    if not isinstance(value, dict):
        raise ValueError("numeric_close")
    affinity = value.get("affinity")
    elapsed = value.get("wall_seconds")
    flags = value.get("kernel_flags")
    if (
        value.get("schema_id") != "qm.ivv.numeric-close.v1"
        or type(value.get("job_commit_bytes")) is not int
        or value["job_commit_bytes"] != COMMIT_BYTES
        or type(affinity) is not int
        or affinity <= 0
        or affinity & (affinity - 1)
        or type(flags) is not int
        or flags & 0x2210 != 0x2210
        or flags & 0x1800
        or type(value.get("process_affinity")) is not int
        or value["process_affinity"] != affinity
        or value.get("child_membership_verified") is not True
        or type(value.get("returncode")) is not int
        or value["returncode"] != 0
        or type(value.get("active_processes")) is not int
        or value["active_processes"] != 0
        or value.get("owned_fds_closed") is not True
        or type(elapsed) not in (int, float)
        or not math.isfinite(elapsed)
        or not 0 <= elapsed <= 80
        or not isinstance(value.get("code"), dict)
        or value["code"] != code
    ):
        raise ValueError("numeric_close")


class IVVRuntime:
    def __init__(self, root, basis, store):
        from quantmesh.research import ivv_admission as gate

        ref = basis["proofs"]["windows_policy_ref"]
        policy = gate._load(store, ref)
        go = gate._load(store, basis["proofs"]["go_ref"])
        if (
            os.name != "nt"
            or sys.platform != "win32"
            or ref["digest"] != WINDOWS_POLICY_SHA
            or policy["planning_scope_id"] != basis["scope_id"]
            or policy["planning_job_uuid"] != basis["job_id"]
            or policy["full_execution_approval_sha256"] != basis["proofs"]["effect_ref"]["digest"]
            or go["windows_policy_sha256"] != WINDOWS_POLICY_SHA
            or go["numeric_runtime_sha256"] != gate.daily.digest(Path(__file__).read_bytes())
        ):
            raise ValueError("windows_runtime_authority")
        controls = policy["windows_controls"]
        if (
            controls["job_wide_committed_memory_max"] != COMMIT_BYTES
            or controls["absolute_seconds"] != 80
            or controls["paging"] != "ORDINARY_WINDOWS_OS_MANAGED_ALLOWED"
            or controls["owned_study_artifacts"] != 8388608
        ):
            raise ValueError("windows_runtime_budget")
        self.directory = Path(root) / "numeric"
        self.child = self.started = self.timer = None
        self.closed = False
        self._lock = threading.RLock()

    def check(self, *, pending_bytes=0):
        if self.closed:
            return False
        # Four MiB cover bounded command/result/report, decision, atomic staging,
        # ledger and metadata. Existing originals are additional, never deleted.
        ensure_capacity(self.directory.parent, pending_bytes + 4 * 1024 * 1024)
        if self.child is not None:
            return self.child.poll() is None and time.monotonic() - self.started < 60
        self.directory.mkdir(exist_ok=False)
        self.started = time.monotonic()
        boot = (
            "import os,sys\nif sys.stdin.readline() != "
            + repr("go\n")
            + ": raise SystemExit(3)\n"
            + "null=os.open(os.devnull,os.O_WRONLY); os.dup2(null,2); os.close(null)\n"
            + "from quantmesh.research.ivv_runtime import _child_main; _child_main(sys.argv[1])"
        )
        try:
            self.child = _OwnedChild(
                [sys.executable, "-B", "-c", boot, str(self.directory)],
                RunBudget(
                    timeout_seconds=80,
                    memory_mib=512,
                    cpu_limit=1,
                    max_model_calls=0,
                    max_estimated_model_usd=0,
                ),
                self.directory,
            )
            self.native_limits = _readback(self.child)
            # Absolute deadline includes parked/pre-reservation time and cleanup.
            self.timer = threading.Timer(max(0, 70 - (time.monotonic() - self.started)), self.close)
            self.timer.daemon = True
            self.timer.start()
            return True
        except BaseException:
            self.close()
            raise

    def calculate(self, bars, events, protocol_digest, code):
        from quantmesh.research import native_daily_real as daily

        if not self.check():
            raise ValueError("numeric_not_ready")
        command = daily.canonical(
            {
                "bars": bars.decode("utf-8"),
                "events": events,
                "protocol_digest": protocol_digest,
                "code": code,
            }
        )
        if len(command) > daily.MAX_OBJECT:
            raise ValueError("numeric_capacity")
        temporary = self.directory / "command.pending"
        temporary.write_bytes(command)
        temporary.replace(self.directory / "command.json")
        try:
            while self.child.poll() is None and time.monotonic() - self.started < 60:
                time.sleep(0.02)
            if self.child.poll() is None:
                raise ValueError("numeric_timeout")
            if self.child.poll() != 0:
                raise ValueError("numeric_failed")
            while _active(self.child) and time.monotonic() - self.started < 70:
                time.sleep(0.02)
            with self._lock:
                if self.closed or _active(self.child) != 0:
                    raise ValueError("numeric_close")
                result = self.directory / "result.json"
                if not 1 <= result.stat().st_size <= daily.MAX_OBJECT:
                    raise ValueError("numeric_capacity")
                matrix = daily._loads(result.read_bytes())
                self.child.process.wait(timeout=0)
                self.child.log.close()
                self.child.process._handle.Close()
                if not ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.child.job_handle)):
                    raise ValueError("numeric_handle_close")
                self.child.job_handle = None
                self.closed = True
                self.timer.cancel()
                receipt = {
                    "schema_id": "qm.ivv.numeric-close.v1",
                    **self.native_limits,
                    "returncode": 0,
                    "active_processes": 0,
                    "owned_fds_closed": True,
                    "wall_seconds": time.monotonic() - self.started,
                    "code": code,
                }
                validate_close_receipt(receipt, code)
                return matrix, receipt
        finally:
            self.close()

    def close(self):
        # _OwnedChild kills only this Job Object and waits at most five seconds.
        lock = getattr(self, "_lock", threading.RLock())
        with lock:
            if self.timer is not None:
                self.timer.cancel()
            if not self.closed:
                self.closed = True
                if self.child is not None:
                    self.child.close()


def _child_main(directory):
    """A fixed command format; there is no module, strategy or callable selector."""
    started = time.monotonic()
    target = Path(directory)
    command = target / "command.json"
    while not command.exists():
        if time.monotonic() - started >= 60:
            raise SystemExit(4)
        time.sleep(0.02)
    if not 1 <= command.stat().st_size <= 1024 * 1024:
        raise SystemExit(5)
    from quantmesh.research import native_daily_candidate as native
    from quantmesh.research import native_daily_real as daily

    value = daily._loads(command.read_bytes())
    if value["code"] != native._code():
        raise SystemExit(6)
    frame = native.pd.read_csv(io.BytesIO(value["bars"].encode()), dtype={"date": str}).set_index(
        "date"
    )
    matrix = native._calculate_matrix(frame, value["events"], value["protocol_digest"])
    raw = daily.canonical(native.engine._plain(matrix))
    if not 1 <= len(raw) <= daily.MAX_OBJECT:
        raise SystemExit(7)
    (target / "result.json").write_bytes(raw)
