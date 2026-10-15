"""Opt-in Linux private-terminal fixture; never a vendor/login authority.

Admission inspects inherited descriptors without consuming terminal bytes.
Only the synthetic fixture observer reads its newly created PTY master.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_CODES = {
    "invalid_uid",
    "invalid_descriptor",
    "unsupported_native",
    "not_terminal",
    "wrong_owner",
    "nonprivate_mode",
    "echo_enabled",
    "terminal_mismatch",
    "descriptor_changed",
    "inspection_unavailable",
    "process_identity_unavailable",
    "missing_handle",
    "registration_interrupted",
    "cleanup_incomplete",
    "deadline",
    "child_protocol",
    "fixture_failed",
    "output_limit",
    "descriptor_access",
}
_FALSE_FLAGS = {
    "production_release_qualified": False,
    "source_host_private_input_verified": False,
    "private_input_verified": False,
    "sdk_wire_verified": False,
    "server_startup_verified": False,
    "operator_authenticated": False,
    "installation_approved": False,
    "market_verified": False,
    "authentication": {"private_input_verified": False},
}


class TerminalQualificationError(RuntimeError):
    """Fixed nonsecret qualification failure."""

    def __init__(self, code: str, *, cleanup: dict | None = None):
        self.code = code if code in _CODES else "fixture_failed"
        self.cleanup = cleanup or {}
        super().__init__(self.code)


def _native() -> None:
    if sys.platform != "linux" or not hasattr(os, "pidfd_open"):
        raise TerminalQualificationError("unsupported_native")


def _signature(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_rdev, info.st_uid, info.st_mode


def inspect_private_terminal(
    stdin_fd: int, stdout_fd: int, stderr_fd: int, *, expected_uid: int
) -> dict:
    """Inspect one private terminal via retained duplicates, then recheck originals.

    This is a point-in-time admission, not secrecy from root/same-UID observers.
    The launcher must pass the retained device and re-admit immediately at release.
    No path discovery, transcript or terminal read is performed.
    """
    if type(expected_uid) is not int or expected_uid < 0:
        raise TerminalQualificationError("invalid_uid")
    fds = (stdin_fd, stdout_fd, stderr_fd)
    if any(type(fd) is not int or fd < 0 for fd in fds):
        raise TerminalQualificationError("invalid_descriptor")
    _native()
    import fcntl
    import termios

    duplicates = []
    try:
        try:
            before = [os.fstat(fd) for fd in fds]
            for fd in fds:
                duplicates.append(os.dup(fd))
        except OSError:
            raise TerminalQualificationError("invalid_descriptor") from None
        for position, (fd, held, original) in enumerate(zip(fds, duplicates, before, strict=True)):
            if _signature(os.fstat(held)) != _signature(original):
                raise TerminalQualificationError("descriptor_changed")
            if not stat.S_ISCHR(original.st_mode) or not os.isatty(held):
                raise TerminalQualificationError("not_terminal")
            # Recheck before reporting policy errors if a concurrent replacement occurred.
            if _signature(os.fstat(fd)) != _signature(original):
                raise TerminalQualificationError("descriptor_changed")
            if original.st_uid != expected_uid:
                raise TerminalQualificationError("wrong_owner")
            if stat.S_IMODE(original.st_mode) != 0o600:
                raise TerminalQualificationError("nonprivate_mode")
            access = fcntl.fcntl(held, fcntl.F_GETFL) & os.O_ACCMODE
            if access == (os.O_WRONLY if position == 0 else os.O_RDONLY):
                raise TerminalQualificationError("descriptor_access")
        if len({_signature(info) for info in before}) != 1:
            raise TerminalQualificationError("terminal_mismatch")
        attributes = [termios.tcgetattr(fd) for fd in duplicates]
        if any(attrs[3] & (termios.ECHO | termios.ECHONL) for attrs in attributes):
            raise TerminalQualificationError("echo_enabled")
        if any(
            _signature(os.fstat(fd)) != _signature(info)
            or _signature(os.fstat(held)) != _signature(info)
            or termios.tcgetattr(held) != attrs
            for fd, held, info, attrs in zip(fds, duplicates, before, attributes, strict=True)
        ):
            raise TerminalQualificationError("descriptor_changed")
        return {
            "descriptors": [
                {"fd": fd, "device": info.st_dev, "inode": info.st_ino, "rdev": info.st_rdev}
                for fd, info in zip(fds, before, strict=True)
            ],
            "owner_uid": expected_uid,
            "mode": 0o600,
            "echo": False,
            "echonl": False,
        }
    except (OSError, termios.error):
        raise TerminalQualificationError("inspection_unavailable") from None
    finally:
        for fd in duplicates:
            os.close(fd)


@dataclass
class _Deadline:
    started: float = 0.0

    def __post_init__(self):
        self.started = time.monotonic()

    def remaining(self, *, cleanup: bool = False) -> float:
        remaining = self.started + (89 if cleanup else 80) - time.monotonic()
        if remaining <= 0:
            raise TerminalQualificationError("deadline")
        return remaining


# Fixed synthetic helper, no arbitrary command/path/marker accepted on CLI.
# Each child independently expires even when registration fails or the parent dies.
_HELPER = r"""
import fcntl, hashlib, os, select, signal, stat, sys, termios
gate, report, role = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
signal.pthread_sigmask(signal.SIG_SETMASK, [])
signal.alarm(int(sys.argv[4]))
try:
    if not select.select([gate], [], [], 2)[0] or os.read(gate, 1) != b'R':
        sys.exit(40)
    if role != 'sibling':
        infos = [os.fstat(fd) for fd in (0, 1, 2)]
        if any(not stat.S_ISCHR(s.st_mode) or s.st_uid != os.getuid()
               or stat.S_IMODE(s.st_mode) != 0o600 for s in infos):
            sys.exit(41)
        if len({(s.st_dev, s.st_ino, s.st_rdev) for s in infos}) != 1:
            sys.exit(42)
        if any(termios.tcgetattr(fd)[3] & (termios.ECHO | termios.ECHONL)
               for fd in (0, 1, 2)):
            sys.exit(43)
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.write(report, b'R')
    if role == 'input':
        data = os.read(0, 128)
        os.write(report, len(data).to_bytes(2, 'big') + hashlib.sha256(data).digest())
        os.write(1, b'ACK\n')
    elif role == 'blocked':
        os.read(0, 1)
    elif role == 'output_growth':
        while True:
            os.write(1, b'.' * 1024)
    elif role == 'sibling':
        select.select([gate], [], [], 80)
    else:
        sys.exit(44)
except Exception:
    sys.exit(45)
"""


def _identity(proc: subprocess.Popen, pidfd: int) -> dict:
    """Read only newly owned child's kernel identity, never cmdline/environment."""
    if select.select([pidfd], [], [], 0)[0]:
        raise TerminalQualificationError("process_identity_unavailable")
    try:
        directory = os.open(f"/proc/{proc.pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(directory)
            fd = os.open("stat", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                data = os.read(fd, 4096)
            finally:
                os.close(fd)
        finally:
            os.close(directory)
        fields = data.rpartition(b")")[2].split()
        if info.st_uid != os.getuid() or int(data.split(b"(", 1)[0]) != proc.pid:
            raise ValueError
        result = {
            "pid": proc.pid,
            "start_ticks": int(fields[19]),
            "uid": info.st_uid,
            "proc_device": info.st_dev,
            "proc_inode": info.st_ino,
        }
        if select.select([pidfd], [], [], 0)[0] or proc.poll() is not None:
            raise ValueError
        return result
    except (OSError, ValueError, IndexError):
        raise TerminalQualificationError("process_identity_unavailable") from None


def _pipe_read(fd: int, count: int, deadline: _Deadline) -> bytes:
    data = bytearray()
    until = time.monotonic() + min(3, deadline.remaining())
    while len(data) < count:
        seconds = until - time.monotonic()
        if seconds <= 0 or not select.select([fd], [], [], seconds)[0]:
            raise TerminalQualificationError("child_protocol")
        part = os.read(fd, count - len(data))
        if not part:
            raise TerminalQualificationError("child_protocol")
        data.extend(part)
    return bytes(data)


@dataclass
class _OwnedChild:
    proc: subprocess.Popen
    pidfd: int
    gate: int
    report: int
    identity: dict
    admission: dict | None
    deadline: _Deadline
    released: bool = False
    terminal: bool = False

    def alive(self) -> bool:
        return not select.select([self.pidfd], [], [], 0)[0] and self.proc.poll() is None

    def release(self, slave: int | None = None) -> None:
        if not self.alive() or _identity(self.proc, self.pidfd) != self.identity:
            raise TerminalQualificationError("process_identity_unavailable")
        self.deadline.remaining()
        if self.admission is not None:
            proof = inspect_private_terminal(slave, slave, slave, expected_uid=os.getuid())
            if proof != self.admission:
                raise TerminalQualificationError("descriptor_changed")
        os.write(self.gate, b"R")
        self.released = True
        if _pipe_read(self.report, 1, self.deadline) != b"R":
            raise TerminalQualificationError("child_protocol")

    def wait(self) -> int:
        try:
            code = self.proc.wait(timeout=min(4, self.deadline.remaining(cleanup=True)))
        except subprocess.TimeoutExpired:
            raise TerminalQualificationError("cleanup_incomplete") from None
        self.terminal = bool(select.select([self.pidfd], [], [], 0)[0])
        if not self.terminal:
            raise TerminalQualificationError("cleanup_incomplete")
        return code

    def stop(self) -> int:
        if self.alive():
            signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
        return self.wait()

    def close(self) -> None:
        try:
            self.stop()
        finally:
            for fd in (self.gate, self.report, self.pidfd):
                os.close(fd)


def _spawn(
    root: Path, role: str, slave: int | None, deadline: _Deadline, *, failure: str | None = None
) -> _OwnedChild:
    """Hold input behind a gate; interrupted registration closes it before waiting.

    The two fixed faults qualify the real post-Popen window and a kernel-refused
    pidfd_open. No unregistered child is signalled by PID or PGID.
    """
    _native()
    deadline.remaining()
    if role not in {"input", "blocked", "output_growth", "sibling"}:
        raise TerminalQualificationError("fixture_failed")
    proof = (
        None
        if slave is None
        else inspect_private_terminal(slave, slave, slave, expected_uid=os.getuid())
    )
    descriptors = {}
    proc = None
    pidfd = None
    previous_mask = None
    launch_attempted = False
    try:
        gate_read, gate_write = os.pipe()
        descriptors.update(gate_read=gate_read, gate_write=gate_write)
        report_read, report_write = os.pipe()
        descriptors.update(report_read=report_read, report_write=report_write)
        lifetime = min(85, int(deadline.remaining(cleanup=True)))
        if lifetime < 1:
            raise TerminalQualificationError("deadline")
        # SIGINT cannot unwind Popen after it creates a child but before it returns.
        # Restore inside the guarded region so a pending signal still closes the gate.
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
        launch_attempted = True
        proc = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                _HELPER,
                str(gate_read),
                str(report_write),
                role,
                str(lifetime),
            ],
            stdin=slave if slave is not None else subprocess.DEVNULL,
            stdout=slave if slave is not None else subprocess.DEVNULL,
            stderr=slave if slave is not None else subprocess.DEVNULL,
            cwd=root,
            env={"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root)},
            pass_fds=(gate_read, report_write),
            start_new_session=True,
        )
        if failure == "registration_interrupted":
            signal.raise_signal(signal.SIGINT)
        # Invalid flags cause a genuine kernel EINVAL, rather than a fake missing handle.
        pidfd = os.pidfd_open(proc.pid, 1 if failure == "missing_handle" else 0)
        identity = _identity(proc, pidfd)
        restoring = previous_mask
        previous_mask = None
        signal.pthread_sigmask(signal.SIG_SETMASK, restoring)
        return _OwnedChild(proc, pidfd, gate_write, report_read, identity, proof, deadline)
    except BaseException as error:
        for name in ("gate_write", "report_read"):
            if name in descriptors:
                os.close(descriptors.pop(name))
        terminal = not launch_attempted
        code = None
        if proc is not None:
            try:
                # Closing the gate independently exits the retained direct child.
                code = proc.wait(timeout=min(4, deadline.remaining(cleanup=True)))
                terminal = code is not None
            except (subprocess.TimeoutExpired, TerminalQualificationError):
                terminal = False
        if pidfd is not None:
            terminal = terminal and bool(select.select([pidfd], [], [], 0)[0])
            os.close(pidfd)
        cleanup = {"terminal": terminal, "released": False, "returncode": code}
        if not terminal:
            raise TerminalQualificationError("cleanup_incomplete", cleanup=cleanup) from None
        category = (
            "registration_interrupted"
            if isinstance(error, KeyboardInterrupt)
            else (
                "missing_handle" if failure == "missing_handle" else "process_identity_unavailable"
            )
        )
        raise TerminalQualificationError(category, cleanup=cleanup) from None
    finally:
        for name in ("gate_read", "report_write"):
            if name in descriptors:
                os.close(descriptors.pop(name))
        if previous_mask is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


@contextmanager
def _private_pty():
    import pty
    import termios

    master, slave = pty.openpty()
    handles = [master]
    try:
        os.fchmod(slave, 0o600)
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        os.set_blocking(master, False)
        attrs[1] &= ~termios.OPOST
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        yield handles, slave
    finally:
        # Retain exact descriptor ownership; never probe or close a reused number.
        for fd in handles:
            os.close(fd)
        os.close(slave)


def _observe_synthetic(master: int, deadline: _Deadline, *, growth: bool = False) -> bytes:
    """Fixture-only bounded observer; the returned bytes never enter receipts/logs."""
    data = bytearray()
    until = time.monotonic() + min(1, deadline.remaining())
    while len(data) < 4096:
        seconds = until - time.monotonic()
        if seconds <= 0 or not select.select([master], [], [], seconds)[0]:
            break
        try:
            chunk = os.read(master, min(1024, 4096 - len(data)))
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        data.extend(chunk)
        if not growth and b"ACK" in data:
            break
    return bytes(data)


def run_owned_fixture() -> dict:
    """Create only a fresh 0700 local root/PTY and fixed synthetic children."""
    _native()
    deadline = _Deadline()
    root = Path(tempfile.mkdtemp(prefix="quantmesh-private-terminal-", dir="/var/tmp"))
    children = []
    receipt = {
        "status": "failed",
        "scope": "OWNED_LOCAL_PRIVATE_TERMINAL_FIXTURE",
        **_FALSE_FLAGS,
        "root": str(root),
        "owner_uid": os.getuid(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cases": {},
    }
    error = None
    try:
        os.chmod(root, 0o700)
        receipt["owned_root_mode"] = stat.S_IMODE(root.stat().st_mode)
        sibling = _spawn(root, "sibling", None, deadline)
        children.append(sibling)
        sibling.release()
        receipt["sibling_identity"] = sibling.identity
        with _private_pty() as (handles, slave):
            master = handles[0]
            child = _spawn(root, "input", slave, deadline)
            children.append(child)
            receipt["terminal_admission"] = child.admission
            child.release(slave)
            marker = secrets.token_hex(32).encode("ascii") + b"\n"
            os.write(master, marker)
            report = _pipe_read(child.report, 34, deadline)
            child.wait()
            observed = _observe_synthetic(master, deadline)
            receipt["input"] = {
                "accepted_bytes": int.from_bytes(report[:2], "big"),
                "digest_matched": report[2:] == hashlib.sha256(marker).digest(),
                "marker_not_echoed": marker.rstrip(b"\n") not in observed,
                "observed_bytes": len(observed),
                "terminal": child.terminal,
            }
            # Raw bytes and marker are ephemeral; hashes of the marker are not archived.
            if (
                receipt["input"]["accepted_bytes"] != 65
                or not receipt["input"]["digest_matched"]
                or not receipt["input"]["marker_not_echoed"]
                or observed not in (b"ACK\n", b"ACK\r\n")
                or child.proc.returncode != 0
                or not sibling.alive()
            ):
                raise TerminalQualificationError("fixture_failed")
            del marker, observed, report
        for name in (
            "disconnect",
            "blocked",
            "output_growth",
            "gate_timeout",
            "missing_handle",
            "registration_interrupted",
        ):
            with _private_pty() as (handles, slave):
                if name in {"missing_handle", "registration_interrupted"}:
                    try:
                        _spawn(root, "blocked", slave, deadline, failure=name)
                    except TerminalQualificationError as caught:
                        if caught.code != name or not caught.cleanup.get("terminal"):
                            raise
                        case = dict(caught.cleanup)
                    else:
                        raise TerminalQualificationError("fixture_failed")
                else:
                    role = "output_growth" if name == "output_growth" else "blocked"
                    child = _spawn(root, role, slave, deadline)
                    children.append(child)
                    if name != "gate_timeout":
                        child.release(slave)
                    observed_count = 0
                    if name == "disconnect":
                        os.close(handles[0])
                        handles.clear()
                        code = child.wait()
                        if code != -signal.SIGHUP:
                            raise TerminalQualificationError("fixture_failed")
                    elif name == "gate_timeout":
                        code = child.wait()
                        if code != 40:
                            raise TerminalQualificationError("fixture_failed")
                    else:
                        if name == "output_growth":
                            observed_count = len(
                                _observe_synthetic(handles[0], deadline, growth=True)
                            )
                            if observed_count != 4096:
                                raise TerminalQualificationError("fixture_failed")
                        code = child.stop()
                    case = {
                        "terminal": child.terminal,
                        "released": child.released,
                        "returncode": code,
                        "observed_bytes": observed_count,
                        "identity": child.identity,
                    }
                case["sibling_survived"] = sibling.alive()
                if not case["sibling_survived"]:
                    raise TerminalQualificationError("fixture_failed")
                receipt["cases"][name] = case
    except BaseException as caught:
        error = (
            caught
            if isinstance(caught, TerminalQualificationError)
            else (TerminalQualificationError("fixture_failed"))
        )
    finally:
        cleanup_ok = True
        for child in reversed(children):
            try:
                child.close()
            except (OSError, TerminalQualificationError):
                cleanup_ok = False
        receipt["all_owned_children_terminal"] = cleanup_ok and all(c.terminal for c in children)
        try:
            root.rmdir()
            receipt["owned_root_removed"] = True
        except OSError:
            receipt["owned_root_removed"] = False
            cleanup_ok = False
        receipt["elapsed_seconds"] = round(time.monotonic() - deadline.started, 6)
        if not cleanup_ok or receipt["elapsed_seconds"] > 90:
            error = TerminalQualificationError("cleanup_incomplete")
    if error is not None:
        receipt["error_code"] = error.code
        return receipt
    receipt["status"] = "passed"
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owned-fixture", action="store_true")
    args = parser.parse_args(argv)
    if not args.owned_fixture:
        receipt = {"status": "pending", "scope": "PREFLIGHT_NO_EFFECT", **_FALSE_FLAGS}
    else:
        try:
            receipt = run_owned_fixture()
        except TerminalQualificationError as error:
            receipt = {"status": "pending", "error_code": error.code, **_FALSE_FLAGS}
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
