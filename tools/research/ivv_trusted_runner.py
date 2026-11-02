"""Original, one-effect Linux IVV trusted-external-environment parent and capture child.

Invoke the protected release with its installed interpreter, -I -S -B, and the
independently pinned digest of the staged startup reference file. No arbitrary
PID, cgroup, control descriptor, executable, callback or shell command is input.
"""

import contextlib
import ctypes
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import time
import types
from pathlib import Path, PurePosixPath

BASE = Path("/var/lib/quantmesh/ivv-trusted-environment")
CONTROL = BASE / "parent"
CHILD = BASE / "child"
RECEIPT = CHILD / "capture"
LEDGER = Path("/var/lib/quantmesh/ivv-capture-once")
RELEASE = Path(__file__).parent
SDK = Path(
    "/opt/quantmesh/releases/69515b79d2bc67303bfef9dee660dbca9bef41e3/.venv/lib/python3.12/site-packages"
)
FAMILY = ".dev-trusted-environment.v1"
AUTH = "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452"
ASSURANCE = "UNVERIFIED_TRUSTED_EXTERNAL"
CG = Path("/sys/fs/cgroup")
LIMITS = {
    "memory.max": "536870912",
    "memory.swap.max": "0",
    "cpu.max": "50000 100000",
    "pids.max": "32",
}
SOURCES = {
    "capture_helper_sha256": "capture_opend_ivv_daily.py",
    "dev_issuer_sha256": "ivv_dev_diagnostic.py",
    "dev_native_sha256": "ivv_dev_native.py",
    "native_producer_sha256": "ivv_native_producer.py",
    "trusted_runner_sha256": "ivv_trusted_runner.py",
}


class Refused(ValueError):
    pass


class _Handles(contextlib.ExitStack):
    """Close every retained handle; never let a later close erase earlier facts."""

    def __init__(self):
        super().__init__()
        self.errors = []

    def callback(self, callback, *args, **kwargs):
        def close():
            try:
                callback(*args, **kwargs)
            except BaseException as error:
                self.errors.append("CLOSE_" + reason(error))

        return super().callback(close)


def need(ok, code):
    if not ok:
        raise Refused(code)


def reason(e):
    if (
        isinstance(e, (ValueError, RuntimeError))
        and len(e.args) == 1
        and isinstance(e.args[0], str)
        and re.fullmatch(r"[A-Za-z0-9_+]{1,256}", e.args[0])
    ):
        return e.args[0]
    return type(e).__name__


def raw_json(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid


def _file_stamp(info):
    return (*identity(info), info.st_nlink, info.st_size, info.st_ctime_ns, info.st_mtime_ns)


def _close_fd(fd):
    primary = sys.exc_info()[1]
    try:
        os.close(fd)
    except BaseException as error:
        raise Refused(
            (reason(primary) + "+" if primary else "") + "FD_CLOSE_" + reason(error)
        ) from None


def protected(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path, "CONTROL_PATH_ALIAS")
    for parent in (path, *path.parents):
        s = parent.lstat()
        need(s.st_uid == 0 and not s.st_mode & 0o022, "CONTROL_OWNERSHIP")


def read_ref(ref, path, maximum=32768, readonly=False):
    need(
        type(ref) is dict
        and set(ref) == {"path", "sha256"}
        and ref["path"] == str(path)
        and isinstance(ref["sha256"], str)
        and re.fullmatch("[0-9a-f]{64}", ref["sha256"]),
        "CONTROL_REF",
    )
    protected(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        need(
            stat.S_ISREG(s.st_mode)
            and s.st_nlink == 1
            and s.st_uid == 0
            and (not (s.st_mode & 0o022) if readonly else stat.S_IMODE(s.st_mode) == 0o444)
            and 0 < s.st_size <= maximum,
            "CONTROL_METADATA",
        )
        if readonly:
            need(os.fstatvfs(fd).f_flag & os.ST_RDONLY, "SOURCE_WRITABLE")
        raw = os.pread(fd, s.st_size + 1, 0)
        need(len(raw) == s.st_size and _file_stamp(s) == _file_stamp(os.fstat(fd)), "CONTROL_RACE")
        need(
            _file_stamp(s) == _file_stamp(os.stat(path, follow_symlinks=False))
            and digest(raw) == ref["sha256"],
            "CONTROL_DIGEST",
        )
        return raw
    finally:
        _close_fd(fd)


def put(path, obj):
    raw = raw_json(obj)
    need(0 < len(raw) <= 32768, "CONTROL_SIZE")
    protected(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(raw)
            out.flush()
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    finally:
        _close_fd(fd)
    _sync_dir(path.parent)
    return {"path": str(path), "sha256": digest(raw)}


def _sync_dir(path):
    d = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(d)
    finally:
        _close_fd(d)


def _libcall(name, *args):
    libc = ctypes.CDLL(None, use_errno=True)
    if getattr(libc, name)(*args) != 0:
        raise OSError(ctypes.get_errno(), name)


def _private_mounts():
    protected(RELEASE)
    old = os.stat("/proc/self/ns/mnt").st_ino
    _libcall("unshare", 0x00020000)
    _libcall("mount", None, b"/", None, ctypes.c_ulong(0x40000 | 0x4000), None)
    new = os.stat("/proc/self/ns/mnt").st_ino
    need(new != old, "NAMESPACE_NOT_PRIVATE")
    return new


class _MountAttr(ctypes.Structure):
    _fields_ = [(k, ctypes.c_uint64) for k in ("set", "clear", "propagation", "userns")]


def _attr(path, readonly, recursive):
    need(os.uname().machine in ("x86_64", "aarch64"), "MOUNT_ABI")
    a = _MountAttr(int(readonly), int(not readonly), 0, 0)
    _libcall(
        "syscall",
        442,
        -100,
        os.fsencode(path),
        0x8000 if recursive else 0,
        ctypes.byref(a),
        ctypes.sizeof(a),
    )


def _bind(path):
    protected(path)
    _libcall(
        "mount", os.fsencode(path), os.fsencode(path), None, ctypes.c_ulong(4096 | 16384), None
    )


def _bootstrap(startup_ref):
    need(sys.platform == "linux" and os.getuid() == os.geteuid() == 0, "LINUX_ROOT")
    need(
        sys.flags.isolated
        and sys.flags.no_site
        and sys.dont_write_bytecode
        and not any(k == "moomoo" or k.startswith("moomoo.") for k in sys.modules),
        "ISOLATED_INTERPRETER",
    )
    startup = json.loads(read_ref(startup_ref, CONTROL / "startup.json", 8192))
    names = {
        "catalog_ref": "release-catalog.json",
        "seed_ref": "plan-seed.json",
        "budget_ref": "budget.json",
        "authorization_ref": "authorization.json",
        "go_fields_ref": "windows-go-fields.json",
    }
    need(set(startup) == set(names), "STARTUP_REFS")
    _private_mounts()
    for path in (RELEASE, SDK, Path("/usr/lib"), Path("/usr/bin")):
        _bind(path)
        _attr(path, True, True)
    values = {
        k: json.loads(read_ref(startup[k], (RELEASE if k == "catalog_ref" else CONTROL) / v))
        for k, v in names.items()
    }
    need(startup["authorization_ref"]["sha256"] == AUTH, "AUTHORIZATION_PIN")
    catalog = values["catalog_ref"]
    need(set(SOURCES) <= set(catalog), "CATALOG_SOURCES")
    for key, filename in SOURCES.items():
        path = RELEASE / filename
        raw = read_ref({"path": str(path), "sha256": catalog[key]}, path, 262144, True)
        if key == "dev_issuer_sha256":
            issuer = types.ModuleType("_qm_trusted_issuer")
            issuer.__file__ = str(path)
            exec(compile(raw, str(path), "exec"), issuer.__dict__)
    helper = issuer._capture()
    native, producer = issuer._native_sources(helper, catalog)
    need(
        helper._CAPTURE_HELPER_SHA256 == catalog["capture_helper_sha256"]
        if hasattr(helper, "_CAPTURE_HELPER_SHA256")
        else issuer._CAPTURE_HELPER_SHA256 == catalog["capture_helper_sha256"],
        "HELPER_CATALOG",
    )
    return startup, values, issuer, helper, native, producer


def _kread(fd, name, bound=8192):
    f = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
    try:
        return _fdread(f, bound)
    finally:
        _close_fd(f)


def _fdread(fd, bound=8192):
    data = os.pread(fd, bound + 1, 0)
    need(len(data) <= bound, "KERNEL_BOUND")
    return data.decode("ascii").strip()


def _events(fd):
    pairs = [line.split() for line in _fdread(fd).splitlines()]
    need(all(len(row) == 2 and row[1].isdigit() for row in pairs), "RESOURCE_EVENT_SHAPE")
    out = {k: int(v) for k, v in pairs}
    need(bool(out) and len(out) == len(pairs), "RESOURCE_EVENT_SHAPE")
    return out


def _process(pid):
    p = Path("/proc") / str(pid)
    raw = (p / "stat").read_bytes()
    head, sep, tail = raw.rpartition(b") ")
    fields = tail.split()
    need(sep and head.startswith(str(pid).encode() + b" (") and len(fields) >= 20, "PID_STAT")
    group = (p / "cgroup").read_text().strip()
    need(
        re.fullmatch(r"0::/system\.slice/[A-Za-z0-9_@.:-]+\.service/[A-Za-z0-9_-]+", group),
        "OWNED_CGROUP_PATH",
    )
    return (
        {"pid": pid, "start_ticks": int(fields[19]), "uid": p.stat().st_uid, "cgroup": group[3:]},
        int(fields[1]),
    )


def _cgroup_mount():
    lines = Path("/proc/self/mountinfo").read_text().splitlines()
    visible = [line.split() for line in lines if line.split()[4] == str(CG)]
    need(len(visible) == 1, "CGROUP_MOUNT")
    row = visible[0]
    need(row[3] == "/" and row[row.index("-") + 1] == "cgroup2", "CGROUP2_MOUNT")
    return int(row[0])


def _mount_id(fd):
    raw = Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
    return int(next(line.split()[1] for line in raw if line.startswith("mnt_id:")))


def _manager_fields(unit):
    fields = (
        "Id",
        "MainPID",
        "InvocationID",
        "ControlGroup",
        "KillMode",
        "SendSIGKILL",
        "Delegate",
        "DelegateSubgroup",
        "ActiveState",
        "SubState",
    )
    child = subprocess.Popen(
        ["/usr/bin/systemctl", "show", "--no-pager", "--property=" + ",".join(fields), "--", unit],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        close_fds=True,
    )
    data = bytearray()
    deadline = time.monotonic() + 2
    try:
        os.set_blocking(child.stdout.fileno(), False)
        while True:
            left = deadline - time.monotonic()
            need(left > 0, "OWN_MANAGER_TIMEOUT")
            ready, _, _ = select.select([child.stdout], [], [], left)
            need(ready, "OWN_MANAGER_TIMEOUT")
            part = os.read(child.stdout.fileno(), 8193 - len(data))
            if not part:
                break
            data.extend(part)
            need(len(data) <= 8192, "OWN_MANAGER_BOUND")
        need(child.wait(timeout=max(0.001, deadline - time.monotonic())) == 0, "OWN_MANAGER_QUERY")
        rows = [line.partition("=") for line in data.decode("ascii").splitlines()]
        result = {k: v for k, sep, v in rows if sep}
        need(len(result) == len(rows) and set(result) == set(fields), "OWN_MANAGER_SHAPE")
        return result
    finally:
        primary = sys.exc_info()[1]
        errors = []
        try:
            if child.poll() is None:
                child.kill()  # this Popen-created query child only
                child.wait(timeout=2)
        except BaseException as error:
            errors.append("OWN_MANAGER_REAP_" + reason(error))
        try:
            child.stdout.close()
        except BaseException as error:
            errors.append("OWN_MANAGER_CLOSE_" + reason(error))
        if errors:
            raise Refused("+".join(([reason(primary)] if primary else []) + errors)) from None


def _manager_contract(parent):
    path = PurePosixPath(parent["cgroup"])
    unit = path.parent.name
    fields = _manager_fields(unit)
    need(
        fields.get("Id") == unit
        and fields.get("MainPID") == str(parent["pid"])
        and fields.get("ControlGroup") == str(path.parent)
        and re.fullmatch("[0-9a-f]{32}", fields.get("InvocationID", ""))
        and fields.get("KillMode") == "process"
        and fields.get("SendSIGKILL") == "no"
        and fields.get("Delegate") == "yes"
        and fields.get("DelegateSubgroup") == path.name
        and fields.get("ActiveState") == "active"
        and fields.get("SubState") == "running",
        "OWN_MANAGER_CONTRACT",
    )
    return fields


class _Scope:
    """Handles are created internally and retained until the final resource observation."""

    def __init__(self, stack):
        self.stack = stack
        self.pid = None
        self.pidfd = None
        self.child = None
        self.reaped = False
        self.moved = False
        self.leaf = None
        self.mount = _cgroup_mount()
        self.parent, _ = _process(os.getpid())
        self.manager_contract = _manager_contract(self.parent)
        self.manager = Path(self.parent["cgroup"]).name
        self.unitpath = CG / self.parent["cgroup"].strip("/")
        self.unitpath = self.unitpath.parent
        self.group = self.open_dir(self.unitpath)
        self.man = self.open_dir(self.manager, self.group)
        need(
            _kread(self.man, "cgroup.procs") == str(os.getpid())
            and _kread(self.group, "cgroup.procs") == ""
            and self.dirs(self.group) == {self.manager},
            "UNIT_NOT_EXCLUSIVE",
        )
        self.controls(self.group)
        self.total_events = self.event_files(self.group)
        self.name = "ivv-owned-" + str(os.getpid()) + "-" + str(self.parent["start_ticks"])
        # mkdir must win exclusively before any cleanup or write is registered.
        self.verify_unit()
        os.mkdir(self.name, 0o700, dir_fd=self.group)
        self.leaf = self.open_dir(self.name, self.group)
        self.check_leaf()
        for k, v in LIMITS.items():
            self.write(k, v)
        self.controls(self.leaf)
        self.leaf_events = self.event_files(self.leaf)
        self.pop = self.open_file("cgroup.events", self.leaf)
        self.events = [*self.total_events, *self.leaf_events]
        self.initial = [_events(fd) for fd in self.events]

    def open_file(self, name, where, flags=None):
        fd = os.open(
            name,
            (os.O_RDONLY if flags is None else flags) | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=where,
        )
        self.stack.callback(os.close, fd)
        need(_mount_id(fd) == self.mount, "CGROUP_FD_MOUNT")
        return fd

    def open_dir(self, name, where=None):
        return self.open_file(name, where, os.O_RDONLY | os.O_DIRECTORY)

    @staticmethod
    def dirs(fd):
        with os.scandir(fd) as stream:
            return {e.name for e in stream if e.is_dir(follow_symlinks=False)}

    def event_files(self, fd):
        return [
            self.open_file(name, fd)
            for name in ("memory.events", "pids.events", "memory.swap.events")
        ]

    @staticmethod
    def controls(fd):
        need({k: _kread(fd, k, 128) for k in LIMITS} == LIMITS, "TOTAL_OR_CHILD_LIMIT")

    def verify_unit(self):
        need(
            _cgroup_mount() == self.mount
            and identity(os.stat(self.unitpath, follow_symlinks=False))
            == identity(os.fstat(self.group))
            and _process(os.getpid())[0] == self.parent
            and identity(os.stat(self.manager, dir_fd=self.group, follow_symlinks=False))
            == identity(os.fstat(self.man)),
            "UNIT_CHANGED",
        )
        self.controls(self.group)

    def verify_manager(self):
        need(_manager_contract(self.parent) == self.manager_contract, "OWN_MANAGER_DRIFT")

    def check_leaf(self):
        self.verify_unit()
        need(
            self.leaf is not None
            and identity(os.stat(self.name, dir_fd=self.group, follow_symlinks=False))
            == identity(os.fstat(self.leaf))
            and self.dirs(self.group) == {self.manager, self.name}
            and not self.dirs(self.man)
            and not self.dirs(self.leaf),
            "CGROUP_REPLACED",
        )

    def write(self, name, value):
        self.check_leaf()
        fd = os.open(name, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.leaf)
        try:
            need(
                _mount_id(fd) == self.mount and os.write(fd, value.encode()) == len(value),
                "CGROUP_WRITE",
            )
        finally:
            _close_fd(fd)

    def bind(self, pid):
        self.pid = pid
        self.pidfd = os.pidfd_open(pid)
        self.stack.callback(os.close, self.pidfd)
        actor, ppid = _process(pid)
        need(
            ppid == os.getpid() and actor["uid"] == 0 and actor["cgroup"] == self.parent["cgroup"],
            "FORK_BIND",
        )
        self.child = actor
        self.check_pid()
        self.write("cgroup.procs", str(pid))
        self.moved = True
        self.child = {
            **actor,
            "cgroup": str(PurePosixPath(self.parent["cgroup"]).parent / self.name),
        }
        self.check_pid()

    def check_pid(self):
        need(
            self.pid and self.pid > 0 and not self.reaped and self.pidfd is not None, "NO_OWNED_PID"
        )
        info = Path(f"/proc/self/fdinfo/{self.pidfd}").read_text().splitlines()
        need(
            [line.split()[1] for line in info if line.startswith("Pid:")] == [str(self.pid)],
            "PIDFD_SWAPPED",
        )
        actual, ppid = _process(self.pid)
        need(actual == self.child and ppid == os.getpid(), "CHILD_PID_CHANGED")

    def check_resources(self):
        self.check_leaf()
        self.controls(self.leaf)
        need([_events(fd) for fd in self.events] == self.initial, "RESOURCE_LIMIT_EVENT")

    def check_final_resources(self):
        # The empty removed leaf cannot accrue events. Its FDs stay retained;
        # the enclosing TOTAL counters still cover all final parent work.
        need(self.reaped and self.leaf is None, "FINAL_CHILD_NOT_REMOVED")
        self.verify_unit()
        need(
            self.dirs(self.group) == {self.manager}
            and not self.dirs(self.man)
            and _kread(self.man, "cgroup.procs") == str(os.getpid()),
            "FINAL_UNIT_NOT_EMPTY",
        )
        need(
            [_events(fd) for fd in self.total_events] == self.initial[: len(self.total_events)],
            "RESOURCE_LIMIT_EVENT",
        )

    def reap(self):
        self.check_pid()
        info = os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG)
        if info is None:
            return None
        self.reaped = True
        need(info.si_pid == self.pid and info.si_code == os.CLD_EXITED, "ABNORMAL_CHILD_EXIT")
        return info.si_status

    def empty(self):
        self.check_leaf()
        need(
            _events(self.pop).get("populated") == 0 and not _kread(self.leaf, "cgroup.procs"),
            "CGROUP_NOT_EMPTY",
        )

    def remove(self):
        self.empty()
        os.rmdir(self.name, dir_fd=self.group)

    def abort(self):
        errors = []
        try:
            if self.pid and not self.reaped:
                self.check_pid()
                signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                poll = select.poll()
                poll.register(self.pidfd, select.POLLIN)
                need(poll.poll(2000), "FORCED_WAIT_UNKNOWN")
                status = os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG)
                need(status and status.si_pid == self.pid, "FORCED_REAP_UNKNOWN")
                self.reaped = True
        except BaseException as e:
            errors.append(reason(e))
        try:
            if self.leaf is not None:
                self.check_leaf()
                # Only the fork-derived, start/PPID/pidfd-bound child is signal
                # authority. A leaf inode does not prove that every process
                # subsequently placed there is ours. Unknown members stay
                # untouched and make recursive empty/removal fail closed.
                self.remove()
        except BaseException as e:
            errors.append(reason(e))
        return errors


class _Channel:
    def __init__(self, s):
        self.s = s
        self.origin = identity(os.fstat(s.fileno()))
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        self.s.settimeout(20)

    def check(self):
        need(
            identity(os.fstat(self.s.fileno())) == self.origin
            and self.s.type == socket.SOCK_SEQPACKET,
            "CONTROL_FD_SWAPPED",
        )

    def send(self, obj):
        self.check()
        raw = raw_json(obj)
        need(0 < len(raw) <= 8192 and self.s.send(raw) == len(raw), "CONTROL_SEND")

    def recv(self, sender):
        import struct

        self.check()
        data, anc, flags, _ = self.s.recvmsg(8192, socket.CMSG_SPACE(12))
        if not data and not anc and flags == 0:
            raise Refused("CONTROL_EOF")
        need(
            data
            and flags == 0
            and len(anc) == 1
            and anc[0][:2] == (socket.SOL_SOCKET, socket.SCM_CREDENTIALS)
            and len(anc[0][2]) == 12
            and struct.unpack("3i", anc[0][2]) == (sender, 0, 0),
            "CONTROL_SENDER",
        )
        return json.loads(data)


def _fds():
    # The listdir implementation opens a transient descriptor itself.
    result = set()
    for n in os.listdir("/proc/self/fd"):
        try:
            os.fstat(int(n))
        except OSError as e:
            if e.errno == 9:
                continue
            raise
        result.add(int(n))
    return result


def _stdio():
    for fd in (0, 1, 2):
        s = os.fstat(fd)
        need(stat.S_ISCHR(s.st_mode) and s.st_rdev == os.makedev(1, 3), "UNEXPECTED_STDIO")


def _landlock():
    """Restrict reads, writes and exec, including access through proc magic links."""
    libc = ctypes.CDLL(None, use_errno=True)

    def call(number, *args):
        ret = libc.syscall(number, *args)
        if ret < 0:
            raise OSError(ctypes.get_errno(), "landlock")
        return ret

    need(call(444, None, 0, 1) >= 5, "LANDLOCK_ABI")
    # ABI5 covers every file modification right including IOCTL_DEV. Deny
    # new exec entirely, and expose only public runtime/source/control bytes;
    # readonly host mounts alone would still expose HOME/key/env payloads.
    rights = (1 << 16) - 1
    attr = ctypes.c_uint64(rights)
    rules = call(444, ctypes.byref(attr), 8, 0)
    try:
        read = (1 << 2) | (1 << 3)
        actor, _ = _process(os.getpid())
        need(PurePosixPath(actor["cgroup"]).name.startswith("ivv-owned-"), "LANDLOCK_OWNED_CGROUP")
        paths = [
            (Path("/usr"), read),
            (RELEASE, read),
            (SDK, read),
            (CONTROL, read),
            (CHILD, read | (1 << 1) | (1 << 7) | (1 << 8) | (1 << 14)),
            (LEDGER, read | (1 << 1) | (1 << 8)),
            (CG / actor["cgroup"].lstrip("/"), read),
        ]
        paths.extend(
            (Path("/proc") / str(os.getpid()) / name, 1 << 2)
            for name in ("stat", "status", "cgroup", "mountinfo")
        )
        paths.extend(
            (Path(name), 1 << 2)
            for name in ("/proc/sys/kernel/cap_last_cap", "/etc/ld.so.cache", "/etc/localtime")
        )
        for path, bits in paths:
            path = Path(path).resolve(strict=True)
            directory = stat.S_ISDIR(path.stat().st_mode)
            need(directory or not bits & (1 << 3), "LANDLOCK_READ_ORIGIN")
            fd = os.open(
                path,
                os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0),
            )
            try:

                class Rule(ctypes.Structure):
                    _pack_ = 1
                    _fields_ = [("access", ctypes.c_uint64), ("fd", ctypes.c_int32)]

                rule = Rule(bits, fd)
                call(445, rules, 1, ctypes.byref(rule), 0)
            finally:
                _close_fd(fd)
        _libcall("prctl", 38, 1, 0, 0, 0)
        call(446, rules, 0)
    finally:
        _close_fd(rules)


def _drop_caps():
    _libcall("prctl", 28, 0xF, 0, 0, 0)  # lock NOROOT and NO_SETUID_FIXUP
    for cap in range(int(Path("/proc/sys/kernel/cap_last_cap").read_text()) + 1):
        _libcall("prctl", 24, cap, 0, 0, 0)
    header = (ctypes.c_uint32 * 2)(0x20080522, 0)
    data = (ctypes.c_uint32 * 6)()
    _libcall("capset", ctypes.byref(header), ctypes.byref(data))
    fields = dict(
        row.split(":", 1)
        for row in Path("/proc/self/status").read_text().splitlines()
        if ":" in row
    )
    need(
        all(int(fields[k], 16) == 0 for k in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb"))
        and fields["NoNewPrivs"].strip() == "1",
        "CHILD_PRIVILEGES",
    )


def _writable_mounts(producer):
    raw = Path("/proc/self/mountinfo").read_bytes()
    mounts = producer._visible_mounts(producer.parse_mountinfo(raw))
    need(
        {m.target for m in mounts.values() if "rw" in m.options} == {str(CHILD), str(LEDGER)},
        "CHILD_WRITE_MOUNTS",
    )


def _child_namespace(channel, producer):
    for fd in _fds() - {channel.s.fileno(), 0, 1, 2}:
        os.close(fd)
    null = os.open("/dev/null", os.O_RDWR | os.O_NOFOLLOW)
    try:
        for fd in (0, 1, 2):
            os.dup2(null, fd, inheritable=False)
    finally:
        _close_fd(null)
    _stdio()
    channel.check()
    need(_fds() == {0, 1, 2, channel.s.fileno()}, "INHERITED_FD")
    ns = _private_mounts()
    for path in (CHILD, LEDGER):
        _bind(path)
    _attr(Path("/"), True, True)
    for path in (CHILD, LEDGER):
        _attr(path, False, False)
    _writable_mounts(producer)
    _landlock()
    _drop_caps()
    return ns


def _runtime(plan, helper, ns, catalog, producer):
    need(os.stat("/proc/self/ns/mnt").st_ino == ns, "OWN_NAMESPACE_DRIFT")
    _writable_mounts(producer)
    need(
        plan["sdk_root"] == str(SDK)
        and sys.version_info[:2] == (3, 12)
        and Path("/proc/self/exe").resolve() == Path("/usr/bin/python3.12"),
        "RUNTIME_ORIGIN",
    )
    home = os.environ.get("HOME")
    need(home and Path(home).is_absolute(), "HOME_NOT_READY")
    log = Path(home) / ".com.moomoo.OpenD" / "Log"
    need(
        log.resolve(strict=True) == log
        and stat.S_ISDIR(log.stat().st_mode)
        and os.statvfs(log).f_flag & os.ST_RDONLY,
        "HOME_LOG_PREREQUISITE",
    )
    for key, name in SOURCES.items():
        path = RELEASE / name
        read_ref({"path": str(path), "sha256": catalog[key]}, path, 262144, True)
    for path in sys.path:
        if Path(path).exists():
            resolved = Path(path).resolve(strict=True)
            need(
                resolved.is_relative_to("/usr/lib/python3.12") or resolved == SDK,
                "PYTHON_SEARCH_PATH",
            )
            protected(resolved)
            need(os.statvfs(resolved).f_flag & os.ST_RDONLY, "PYTHON_SEARCH_WRITABLE")
    need(Path(sys.executable).resolve() == Path("/usr/bin/python3.12"), "PYTHON_EXECUTABLE")
    exe = Path("/usr/bin/python3.12")
    read_ref({"path": str(exe), "sha256": catalog["python_sha256"]}, exe, 32 * 1024 * 1024, True)
    source_pins = json.loads(read_ref(plan["sdk_pins_ref"], CONTROL / "sdk-pins.json"))
    rows = source_pins["pins"]
    need(type(rows) is list and 12 <= len(rows) <= 128, "SDK_PINS_COUNT")
    names = set()
    for r in rows:
        rel = (
            r.get("relative_path")
            or str(r.get("path", "")).replace(chr(92), "/").split("/site-packages/")[-1]
        )
        need(
            re.fullmatch(r"(?:moomoo|google/protobuf|google/_upb)/[A-Za-z0-9_./-]+\.(?:py|so)", rel)
            and ".." not in Path(rel).parts
            and rel not in names,
            "SDK_PIN_ROLE",
        )
        names.add(rel)
        path = SDK / rel
        protected(path)
        need(
            path.resolve(strict=True) == path
            and os.statvfs(path).f_flag & os.ST_RDONLY
            and digest(path.read_bytes().replace(b"\r\n", b"\n")) == r["LF_sha256"],
            "SDK_PIN_DRIFT",
        )
    need(
        any("/pb/" in n or "_pb2.py" in n for n in names)
        and "moomoo/quote/open_quote_context.py" in names,
        "PROTO_AND_QUOTE_ORIGIN",
    )
    # PathFinder performs no package import. Production imports only after once.
    spec = importlib.machinery.PathFinder.find_spec("moomoo", sys.path)
    need(spec and Path(spec.origin) == SDK / "moomoo/__init__.py", "SDK_IMPORT_ORIGIN")
    return {
        "namespace_inode": ns,
        "sdk_pins_sha256": plan["sdk_pins_sha256"],
        "python_sha256": catalog["python_sha256"],
    }


def _environment():
    # HOME is our own public path prerequisite. Do not enumerate, copy, hash or
    # export any other inherited environment value before discarding it.
    home = os.environ.get("HOME")
    need(isinstance(home, str) and Path(home).is_absolute(), "HOME_NOT_READY")
    log = Path(home) / ".com.moomoo.OpenD" / "Log"
    protected(log)
    need(
        log.resolve(strict=True) == log
        and stat.S_ISDIR(log.stat().st_mode)
        and os.statvfs(log).f_flag & os.ST_RDONLY,
        "HOME_LOG_PREREQUISITE",
    )
    os.environ.clear()
    os.environ.update({"HOME": home, "PATH": "/usr/bin:/bin", "LC_ALL": "C"})


class _Provider:
    """Single independently sampled provider, with monotonic per-inode growth."""

    def __init__(self, native, producer, helper, plan, budget_ref):
        self.native = native
        self.producer = producer
        self.helper = helper
        self.plan = plan
        self.budget_ref = budget_ref
        self.series = native.RoleGrowth()
        self.first = None
        self.last = None
        self.next = 0
        self.peak = 0

    def sample(self):
        start = time.monotonic()
        reader = self.producer.PosixReader()
        reader.deadline = min(start + 2, self.plan["started_monotonic"] + 480)
        try:
            identity_doc = reader.identity()
            self.producer._check_identity(identity_doc)
            vendor = reader.processes[705711][0]

            def listeners():
                inodes = reader.socket_inodes(vendor)
                rows = reader.read(vendor, "net/tcp", 262144).splitlines()[1:]
                return sorted(
                    int(row.split()[9])
                    for row in rows
                    if len(row.split()) >= 10
                    and row.split()[1] == b"0100007F:2B68"
                    and row.split()[3] == b"0A"
                    and int(row.split()[9]) in inodes
                )

            listener = listeners()
            need(len(listener) == 1, "OWNED_LISTENER")
            endpoint, configuration = self.native.trusted_quote_configuration(self.plan)
            increment = self.series.sample(reader)
            resources = self.native._provider_controls(reader)
            budget = json.loads(read_ref(self.budget_ref, CONTROL / "budget.json"))
            need(
                set(budget) == {"G", "P"}
                and all(type(v) is int and v > 0 for v in budget.values()),
                "BUDGET_SHAPE",
            )
            fs = os.statvfs(CHILD)
            sample = {
                "incremental_bytes": increment,
                "G": budget["G"] + increment,
                "P": budget["P"] + increment,
                "free": fs.f_bavail * fs.f_frsize,
            }
            need(
                sample["G"] <= 10500000000
                and sample["P"] <= 4500000000
                and sample["free"] >= 53687091200,
                "MONITOR_THRESHOLD",
            )
            need(not reader.finish() and listener == listeners(), "PROVIDER_DRIFT")
            row = reader.processes[705711][2]
            actual = {
                "provider_actor": {
                    "pid": row["pid"],
                    "uid": row["uids"][0],
                    "start_ticks": row["start"],
                    "exe_sha256": (
                        "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601"
                    ),
                    "machine_identity_sha256": identity_doc["machine"],
                },
                "endpoint": endpoint,
                "identity_binding_sha256": digest(raw_json(identity_doc)),
                "configuration_binding_sha256": configuration,
                "listener_binding_sha256": digest(raw_json(listener)),
            }
            need(self.first is None or self.first == actual, "PROVIDER_DRIFT")
            self.first = actual
            self.last = {
                **actual,
                "resource_values": resources,
                "sample": sample,
                "sampled_monotonic": time.monotonic(),
            }
            self.peak = max(self.peak, increment)
        finally:
            primary = sys.exc_info()[1]
            try:
                reader.close()
            except BaseException as e:
                raise Refused((reason(primary) + "+" if primary else "") + reason(e)) from None
        need(time.monotonic() - start < 2, "PROVIDER_SAMPLE_DEADLINE")
        self.next = (self.next or start) + 5
        return self.last


def _child_kernel(scope, producer, endpoint, initial):
    scope.check_pid()
    path = Path("/proc") / str(scope.pid)
    ns = (path / "ns/mnt").stat().st_ino
    need(ns != os.stat("/proc/self/ns/mnt").st_ino, "CHILD_NAMESPACE_SHARED")
    raw = (path / "mountinfo").read_bytes()
    visible = producer._visible_mounts(producer.parse_mountinfo(raw))
    need(
        {m.target for m in visible.values() if "rw" in m.options} == {str(CHILD), str(LEDGER)},
        "CHILD_WRITE_MOUNTS",
    )
    status = (path / "status").read_text().splitlines()
    fields = dict(line.split(":", 1) for line in status if ":" in line)
    need(
        fields["NoNewPrivs"].strip() == "1"
        and all(
            int(fields[k], 16) == 0 for k in ("CapEff", "CapBnd", "CapAmb", "CapInh", "CapPrm")
        ),
        "CHILD_PRIVILEGES",
    )
    need(
        identity((path / "exe").stat()) == identity(Path("/proc/self/exe").stat()),
        "CHILD_EXECUTABLE",
    )
    if initial:
        fdpath = path / "fd"
        objects = {int(e.name): e.stat() for e in fdpath.iterdir()}
        need(
            len(objects) == 4
            and all(
                stat.S_ISCHR(objects[k].st_mode) and objects[k].st_rdev == os.makedev(1, 3)
                for k in (0, 1, 2)
            )
            and [s.st_ino for s in objects.values() if stat.S_ISSOCK(s.st_mode)] == [endpoint],
            "CHILD_FD_CLOSURE",
        )
    scope.check_pid()
    return {"namespace_inode": ns, "mountinfo_sha256": digest(raw), "capture_actor": scope.child}


def _owned_peer(pid):
    def sockets(path):
        out = set()
        for entry in path.iterdir():
            try:
                s = entry.stat()
            except FileNotFoundError:
                continue
            if stat.S_ISSOCK(s.st_mode):
                out.add(s.st_ino)
        return out

    rows = (Path("/proc") / str(pid) / "net/tcp").read_bytes().splitlines()
    need(len(rows) <= 4096, "PEER_TABLE_BOUND")
    child = sockets(Path("/proc") / str(pid) / "fd")
    vendor = sockets(Path("/proc/705711/fd"))
    table = [line.split() for line in rows[1:]]
    pairs = []
    for row in table:
        need(len(row) >= 10 and row[9].isdigit(), "PEER_TABLE")
        if int(row[9]) in child and row[3] == b"01":
            need(
                row[2] == b"0100007F:2B68" and row[1].startswith(b"0100007F:"),
                "FOREIGN_CAPTURE_PEER",
            )
            peers = [
                r
                for r in table
                if r[1:3] == [row[2], row[1]] and r[3] == b"01" and int(r[9]) in vendor
            ]
            need(len(peers) == 1, "CAPTURE_PEER_NOT_PROVIDER_OWNED")
            pairs.append((int(row[9]), int(peers[0][9])))
    need(len(pairs) <= 1, "SECOND_CAPTURE_PEER")
    return pairs[0] if pairs else None


def _seed(values, startup, helper, issuer):
    plan = dict(values["seed_ref"])
    helper._validate_production_plan_keys(plan, schema="qm.ivv.capture-plan" + FAMILY)
    plan["started_monotonic"] = time.monotonic()
    helper._validate_fixed_plan(plan, schema="qm.ivv.capture-plan" + FAMILY)
    need(
        plan["sdk_root"] == str(SDK)
        and plan["receipt_root"] == str(RECEIPT)
        and plan["catalog_sha256"] == startup["catalog_ref"]["sha256"]
        and plan["capture_helper_sha256"] == values["catalog_ref"]["capture_helper_sha256"],
        "FIXED_PLAN_PATH",
    )
    need(
        plan["provider_evidence_ref"]
        == {"path": str(CONTROL / "provider.json"), "sha256": "0" * 64},
        "PROVIDER_PENDING",
    )
    for key, name in (
        ("dates_ref", "dates.txt"),
        ("input_window_ref", "input-window.json"),
        ("window_ref", "window.json"),
        ("schedule_ref", "schedule.json"),
        ("sdk_pins_ref", "sdk-pins.json"),
        ("policy_ref", "policy.json"),
    ):
        read_ref(plan[key], CONTROL / name)
    policy = json.loads(read_ref(plan["policy_ref"], CONTROL / "policy.json"))
    issuer.validate_trusted_policy(helper, policy, plan, AUTH)
    extra = values["go_fields_ref"]
    need(
        set(extra)
        == {
            "job_id",
            "windows_policy_sha256",
            "output_root_digest",
            "code",
            "adapter_sha256",
            "gate_sha256",
            "runtime",
        },
        "WINDOWS_GO_FIELDS",
    )
    for path in (CONTROL, CHILD, LEDGER):
        protected(path)
        need(stat.S_IMODE(path.stat().st_mode) == 0o700, "PRIVATE_CONTROL_DIRECTORY")
    need(not any(CHILD.iterdir()), "OUTPUT_ALREADY_USED")
    return plan


class _ChildSession:
    def __init__(self, channel, parent, check):
        import threading

        self.channel = channel
        self.parent = parent
        self.owner = os.getpid()
        self.check = check
        self.lock = threading.Lock()

    def snapshot(self):
        need(os.getpid() == self.owner, "SESSION_OWNER")
        with self.lock:
            self.check()
            self.channel.send({"op": "observe"})
            return self.channel.recv(self.parent)["snapshot"]

    def before_effect(self):
        self.snapshot()


def _child(channel, parent, context, plan):
    startup, values, issuer, m, native, producer = context
    _bind_parent(parent)
    need(channel.recv(parent) == {"op": "enter"}, "CHILD_GATE")
    ns = _child_namespace(channel, producer)
    _environment()
    if str(SDK) not in sys.path:
        sys.path.append(str(SDK))

    def runtime():
        return _runtime(plan, m, ns, values["catalog_ref"], producer)

    runtime()
    # Validate all immutable material, actor limits and available space before parent GO.
    actor = m._native_actor()
    m._admit_material(
        plan, None, RECEIPT, {**plan, "actor": actor, "budget": values["budget_ref"]}, None, None
    )
    channel.send({"op": "ready"})
    grant = channel.recv(parent)
    need(set(grant) == {"op", "plan_ref", "go_ref"} and grant["op"] == "go", "CHILD_GO_GATE")
    final = m._strict_json(read_ref(grant["plan_ref"], CONTROL / "plan.json"))
    need(
        {k: v for k, v in final.items() if k != "provider_evidence_ref"}
        == {k: v for k, v in plan.items() if k != "provider_evidence_ref"},
        "PARENT_PLAN_CHANGED",
    )
    evidence = m._strict_json(read_ref(final["provider_evidence_ref"], CONTROL / "provider.json"))
    state = types.ModuleType("_qm_live_ivv_native_" + str(os.getpid()))
    state.session = _ChildSession(channel, parent, runtime)
    state.helper = m
    state.trusted_issuer = issuer
    state.plan = m._canonical({k: v for k, v in final.items() if k != "provider_evidence_ref"})
    state.evidence = m._canonical(evidence)
    need(state.__name__ not in sys.modules, "NATIVE_BUSY")
    sys.modules[state.__name__] = state
    try:
        pins = {
            "expected_policy_sha256": final["policy_ref"]["sha256"],
            "expected_authorization_sha256": AUTH,
            "expected_go_sha256": grant["go_ref"]["sha256"],
        }
        go = m._strict_json(read_ref(grant["go_ref"], CONTROL / "go.json"))
        need(
            go["capture_actor"] == actor
            and go["trusted_runner_sha256"] == values["catalog_ref"]["trusted_runner_sha256"],
            "CHILD_GO_ACTOR",
        )
        fd, sha = issuer._issue_family(
            m,
            FAMILY,
            grant["plan_ref"],
            RECEIPT,
            go_ref=grant["go_ref"],
            authorization_ref=startup["authorization_ref"],
            catalog_ref=startup["catalog_ref"],
            permit_path=CHILD / "permit.json",
            **pins,
        )
        try:
            result = m.capture_trusted_once(
                grant["plan_ref"]["path"], RECEIPT, permit_fd=fd, expected_sha256=sha, **pins
            )
        finally:
            _close_fd(fd)
        need(result["state"] == "CAPTURED_UNREVIEWED", "CHILD_CAPTURE_FAILED")
        channel.send(
            {
                "op": "terminal",
                "permit_sha256": sha,
                "manifest_sha256": digest((RECEIPT / "capture-manifest.json").read_bytes()),
            }
        )
    finally:
        del sys.modules[state.__name__]


def _bind_parent(parent):
    # The death signal is attached to the actual forking thread, not an input
    # PID to be signalled. Recheck PPID after installing it to close the fork /
    # parent-exit race. It remains installed through capability drop and exit.
    _libcall("prctl", 1, signal.SIGKILL, 0, 0, 0)
    need(os.getppid() == parent, "PARENT_LOST")


def _authorize(context, plan, scope, monitor):
    startup, values, issuer, m, native, producer = context
    prov = {
        "policy_sha256": plan["policy_ref"]["sha256"],
        "authorization_sha256": AUTH,
        "diagnostic_mode": "DEV_TRUSTED_ENVIRONMENT",
        "channel_assurance": ASSURANCE,
        "provider_tail_max": "UNKNOWN",
        "hard_limit_enforced": False,
    }
    actual = monitor.first
    evidence = {
        "schema_id": "qm.ivv.provider-evidence" + FAMILY,
        "state": "DEV_TRUSTED_ENVIRONMENT",
        **{k: plan[k] for k in ("scope_id", "execution_sha256", "effect_id")},
        **prov,
        **actual,
    }
    plan = {**plan, "provider_evidence_ref": put(CONTROL / "provider.json", evidence)}
    plan_ref = put(CONTROL / "plan.json", plan)
    go = {
        "schema_id": "qm.ivv.root-go" + FAMILY,
        "decision": "GO_ONCE_AFTER_INPUT_ACCEPTANCE",
        **prov,
        **values["go_fields_ref"],
        "scope_id": plan["scope_id"],
        "execution_sha256": plan["execution_sha256"],
        "approval_sha256": plan["approval_sha256"],
        "capture_effect_id": plan["effect_id"],
        "max_capture_intents": 1,
        "max_trials": 1,
        "capture_actor": scope.child,
        "budget": values["budget_ref"],
        "plan_sha256": plan_ref["sha256"],
        "provider_evidence_sha256": plan["provider_evidence_ref"]["sha256"],
        "catalog_sha256": plan["catalog_sha256"],
        "input_window_digest": plan["input_window_digest"],
        "full_window_sha256": plan["full_window_sha256"],
        "controls": {"released": True, "resource_bounds": True, "provider_log_cache_bounds": False},
        **{k: values["catalog_ref"][k] for k in SOURCES},
    }
    return plan_ref, put(CONTROL / "go.json", go), plan, prov


def _manifest(ref, path):
    # Capture originals are private 0600, different from readonly Root controls.
    protected(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        need(
            stat.S_ISREG(s.st_mode)
            and s.st_uid == 0
            and s.st_nlink == 1
            and stat.S_IMODE(s.st_mode) == 0o600
            and 0 < s.st_size <= 1024 * 1024,
            "CAPTURE_RECEIPT_METADATA",
        )
        raw = os.pread(fd, s.st_size + 1, 0)
        need(
            len(raw) == s.st_size
            and digest(raw) == ref
            and _file_stamp(s) == _file_stamp(os.fstat(fd)) == _file_stamp(path.stat()),
            "CAPTURE_RECEIPT_DIGEST",
        )
        return json.loads(raw)
    finally:
        _close_fd(fd)


def _seal(context, grant, scope, monitor, kernel, terminal, peer, elapsed):
    startup, values, issuer, m, native, producer = context
    plan_ref, go_ref, plan, prov = grant
    raw = _manifest(terminal["manifest_sha256"], RECEIPT / "capture-manifest.json")
    binding = raw["source_binding"]
    need(
        raw["schema_id"] == "qm.ivv.capture" + FAMILY
        and raw["state"] == "CAPTURED_UNREVIEWED"
        and raw["synthetic"] is False
        and raw["primary_failure"] is None
        and raw["close_failure"] is None
        and raw["normal_close"]
        == {"data_socket_closed": True, "context_closed": True, "callbacks_stopped": True}
        and all(v is True for v in raw["normal_close"].values())
        and raw["counts"]["application_sends"] == 7
        and binding["actor"] == scope.child
        and binding["root_go_sha256"] == go_ref["sha256"]
        and binding["root_permit_sha256"] == terminal["permit_sha256"]
        and binding["plan_sha256"] == plan_ref["sha256"]
        and m._dev_provenance(raw, FAMILY) == prov
        and peer is not None,
        "CAPTURE_TERMINAL_EVIDENCE",
    )
    intent = _manifest(raw["intent_ref"]["sha256"], RECEIPT / "capture-intent.json")
    need(
        intent["schema_id"] == "qm.ivv.capture-intent" + FAMILY
        and intent["state"] == "ATTEMPTED"
        and m._dev_provenance(intent, FAMILY) == prov,
        "CAPTURE_INTENT",
    )
    permit_ref = {"path": str(CHILD / "permit.json"), "sha256": terminal["permit_sha256"]}
    permit = json.loads(read_ref(permit_ref, CHILD / "permit.json"))
    need(
        permit["actor"] == scope.child and permit["root_go_sha256"] == go_ref["sha256"],
        "SEAL_PERMIT_BINDING",
    )
    config_ref = put(
        CONTROL / "configuration.json",
        {
            "endpoint": monitor.first["endpoint"],
            "configuration_binding_sha256": monitor.first["configuration_binding_sha256"],
            "channel_assurance": ASSURANCE,
        },
    )
    monitor_ref = put(
        CONTROL / "monitor.json",
        {
            "samples": monitor.series.samples,
            "growth_highwater": monitor.peak,
            "last": monitor.last["sample"],
            "peer_inode_pair": list(peer),
            "provider_tail_max": "UNKNOWN",
        },
    )
    close_ref = put(
        CONTROL / "kernel-close.json",
        {
            **kernel,
            "child_reaped": True,
            "recursive_populated": 0,
            "resource_events": scope.initial,
            "control_eof": True,
            "parent_actor": scope.parent,
        },
    )
    refs = [
        plan_ref,
        permit_ref,
        plan["provider_evidence_ref"],
        startup["catalog_ref"],
        plan["sdk_pins_ref"],
        config_ref,
        monitor_ref,
        close_ref,
    ]
    for ref in refs:
        m._read_root_ref(ref, maximum=32768, exact_mode=True)
    return {
        "schema_id": "qm.ivv.capture-parent-close" + FAMILY,
        **prov,
        "state": "NORMAL_EXIT",
        "termination": "NORMAL",
        "scope_id": plan["scope_id"],
        "effect_id": plan["effect_id"],
        "capture_manifest_sha256": terminal["manifest_sha256"],
        "intent_sha256": raw["intent_ref"]["sha256"],
        "catalog_sha256": binding["catalog_sha256"],
        "helper_sha256": binding["capture_helper_sha256"],
        "root_permit_sha256": terminal["permit_sha256"],
        "capture_actor": scope.child,
        "executor_actor": scope.parent,
        "helper_exit_code": 0,
        "active_owned_processes": 0,
        "owned_fds_closed": True,
        "resource_limit_event": False,
        "force_killed": False,
        "elapsed_seconds": elapsed,
        "evidence_refs": refs,
        "configuration_sha256": config_ref["sha256"],
        "monitor_sha256": monitor_ref["sha256"],
        "kernel_close_sha256": close_ref["sha256"],
    }


def _supervise(scope, channel, endpoint, context, plan):
    startup, values, issuer, m, native, producer = context
    monitor = _Provider(native, producer, m, plan, startup["budget_ref"])
    start = plan["started_monotonic"]
    kernel = grant = terminal = peer = None
    scope.check_pid()
    channel.send({"op": "enter"})
    while True:
        now = time.monotonic()
        # The shared capture enforces context close <=390. Receipt fsync and
        # terminal IPC may follow it; actual child exit has its own420 limit.
        deadline = start + (420 if grant is not None else 180)
        need(now < deadline, "OWNED_CHILD_DEADLINE")
        scope.check_resources()
        if now >= monitor.next:
            scope.verify_manager()
            monitor.sample()
        until = min(deadline, monitor.next)
        ready, _, _ = select.select(
            [channel.s, scope.pidfd], [], [], max(0, until - time.monotonic())
        )
        exit_observed = time.monotonic() - start if scope.pidfd in ready else None
        if channel.s in ready:
            try:
                packet = channel.recv(scope.pid)
            except Refused as error:
                if not terminal or reason(error) != "CONTROL_EOF":
                    raise
                # EOF is verified again after actual wait/recursive empty below.
                packet = None
            if packet == {"op": "ready"} and grant is None:
                kernel = _child_kernel(scope, producer, endpoint, True)
                need(time.monotonic() - start < 180, "ROOT_GO_EXPIRED")
                grant = _authorize(context, plan, scope, monitor)
                scope.check_pid()
                channel.send({"op": "go", "plan_ref": grant[0], "go_ref": grant[1]})
            elif packet == {"op": "observe"} and grant and not terminal:
                need(
                    _child_kernel(scope, producer, endpoint, False) == kernel,
                    "CHILD_NAMESPACE_DRIFT",
                )
                pair = _owned_peer(scope.pid)
                if pair:
                    need(peer is None or pair == peer, "CAPTURE_PEER_CHANGED")
                    peer = pair
                channel.send({"snapshot": monitor.last})
            elif packet and packet.get("op") == "terminal" and grant and not terminal:
                need(
                    set(packet) == {"op", "permit_sha256", "manifest_sha256"}
                    and all(m._digest(packet[k]) for k in ("permit_sha256", "manifest_sha256")),
                    "TERMINAL_PACKET",
                )
                terminal = packet
            elif packet is not None:
                raise Refused(
                    packet.get("code", "CHILD_PROTOCOL")
                    if packet.get("op") == "failed"
                    and re.fullmatch("[A-Za-z0-9_+]{1,256}", packet.get("code", ""))
                    else "CHILD_PROTOCOL"
                )
        if scope.pidfd in ready:
            rc = scope.reap()
            exited = exit_observed
            need(exited <= 420, "CHILD_EXIT_DEADLINE")
            need(rc == 0 and grant and kernel, "CHILD_TERMINAL_MISSING")
            # select may have checked the channel before the child's final
            # send and the pidfd after its exit. Authenticate queued terminal
            # and EOF after the actual wait, independent of readiness order.
            for _ in range(3):
                need(time.monotonic() - start <= 480, "FINAL_SEAL_DEADLINE")
                try:
                    packet = channel.recv(scope.pid)
                except Refused as error:
                    if reason(error) != "CONTROL_EOF":
                        raise
                    break
                need(
                    terminal is None
                    and type(packet) is dict
                    and set(packet) == {"op", "permit_sha256", "manifest_sha256"}
                    and packet["op"] == "terminal"
                    and all(m._digest(packet[k]) for k in ("permit_sha256", "manifest_sha256")),
                    "CHILD_TERMINAL_PROTOCOL",
                )
                terminal = packet
            else:
                raise Refused("CONTROL_NOT_CLOSED")
            need(terminal, "CHILD_TERMINAL_MISSING")
            scope.empty()
            scope.check_resources()
            scope.verify_manager()
            monitor.sample()
            channel.check()
            break
    elapsed = time.monotonic() - start
    need(elapsed <= 480, "FINAL_SEAL_DEADLINE")
    return _seal(
        context,
        grant,
        scope,
        monitor,
        {**kernel, "child_exit_observed_seconds": exited},
        terminal,
        peer,
        elapsed,
    )


def _commit_close(ref):
    source = CONTROL / "parent-close.pending.json"
    read_ref(ref, source)
    _libcall(
        "renameat2", -100, os.fsencode(source), -100, os.fsencode(CONTROL / "parent-close.json"), 1
    )
    _sync_dir(CONTROL)


def _reject_close(ref, committed):
    source = CONTROL / ("parent-close.json" if committed else "parent-close.pending.json")
    try:
        read_ref({"path": str(source), "sha256": ref["sha256"]}, source)
    except FileNotFoundError:
        source = CONTROL / ("parent-close.pending.json" if committed else "parent-close.json")
        read_ref({"path": str(source), "sha256": ref["sha256"]}, source)
    _libcall(
        "renameat2",
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(CONTROL / "parent-close.rejected.json"),
        1,
    )
    _sync_dir(CONTROL)


def run_once(startup_ref):
    context = _bootstrap(startup_ref)
    startup, values, issuer, helper, native, producer = context
    plan = _seed(values, startup, helper, issuer)
    _stdio()
    need(
        _fds() == {0, 1, 2} and len(list(Path("/proc/self/task").iterdir())) == 1,
        "PARENT_FD_THREAD_CLOSURE",
    )
    os.umask(0o077)
    primary = None
    pending = None
    committed = False
    with _Handles() as stack:
        scope = _Scope.__new__(_Scope)
        try:
            scope.__init__(stack)
            a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
            stack.callback(a.close)
            stack.callback(b.close)
            parent_side, child_side = _Channel(a), _Channel(b)
            endpoint = child_side.origin[1]
            parent = os.getpid()
            pid = os.fork()
            if pid == 0:
                rc = 1
                try:
                    a.close()
                    _child(child_side, parent, context, plan)
                    rc = 0
                except BaseException as error:
                    with contextlib.suppress(OSError, ValueError):
                        child_side.send({"op": "failed", "code": reason(error)})
                finally:
                    os._exit(rc)
            b.close()
            scope.bind(pid)
            result = _supervise(scope, parent_side, endpoint, context, plan)
            scope.check_resources()
            scope.remove()
            scope.leaf = None
            elapsed = time.monotonic() - plan["started_monotonic"]
            need(elapsed <= 480, "FINAL_SEAL_DEADLINE")
            result["elapsed_seconds"] = elapsed
            # Keep all resource/event handles through JSON/file+directory
            # fsync and normal publication. No partial file is normal authority.
            pending = put(CONTROL / "parent-close.pending.json", result)
            scope.check_final_resources()
            need(time.monotonic() - plan["started_monotonic"] <= 480, "FINAL_SEAL_DEADLINE")
            committed = True
            _commit_close(pending)
            scope.check_final_resources()
            need(time.monotonic() - plan["started_monotonic"] <= 480, "FINAL_SEAL_DEADLINE")
        except BaseException as error:
            failures = scope.abort()
            primary = [reason(error), *failures]
    if time.monotonic() - plan["started_monotonic"] > 480:
        primary = [*(primary or []), "FINAL_SEAL_DEADLINE"]
    if primary or stack.errors:
        failures = [*(primary or []), *stack.errors]
        if pending is not None:
            try:
                _reject_close(pending, committed)
            except BaseException as error:
                failures.append("SEAL_RETIRE_" + reason(error))
        raise Refused("+".join(failures)) from None
    return result


def main(argv):
    try:
        need(len(argv) == 1, "STARTUP_DIGEST_REQUIRED")
        run_once({"path": str(CONTROL / "startup.json"), "sha256": argv[0]})
        return 0
    except BaseException as e:
        # Even when preflight failed, never overwrite an earlier attempt.
        with contextlib.suppress(OSError, ValueError):
            put(CONTROL / "runner-failure.json", {"state": "STOP", "reason": reason(e)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
