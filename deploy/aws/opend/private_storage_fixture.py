"""One retained synthetic c8 filesystem proof; never a provider/start authority.

Run only through the separately released finite native packet, already inside a
private mount namespace. Importing this module performs no native operation.
"""

import ctypes
import errno
import hashlib
import inspect
import json
import os
import platform
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

IMAGE = "/srv/quantmesh-opend-private-storage-20261031/fixture.ext4"
IMAGE_BYTES = 33554432
MACHINE_SHA = "a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191"
NONCE = "c8f0d0de4ca641a491fca6df24c66ceb"
POOL = "/run/quantmesh-opend-storage-" + NONCE
HOME = "/var/lib/quantmesh-opend"
STATE = "/var/lib/quantmesh-opend-stage"
RUNTIME = "/run/quantmesh-opend-console-" + NONCE
WRITES = (HOME, STATE, RUNTIME, "/tmp", "/var/tmp", "/dev/shm")
GUARD_SHA = "d2addaa991a5b22eff531ccb5891add5c4849ca1357f1c7ba83455b4dc907e30"


class FixtureDenied(RuntimeError):
    pass


class ChildFailed(FixtureDenied):
    def __init__(self, diagnostic):
        super().__init__("fixture_child_failed")
        self.diagnostic = diagnostic


def need(condition, reason):
    if not condition:
        raise FixtureDenied(reason)


def validate_environment(facts):
    expected = dict(
        platform="linux",
        architecture="x86_64",
        uid=0,
        euid=0,
        python=[3, 12],
        isolated=True,
        no_site=True,
        no_bytecode=True,
        machine_sha256=MACHINE_SHA,
        kernel="7.0.0-1012-aws",
        cap_sys_admin=True,
        threads=1,
        sigchld_default=True,
    )
    need(
        type(facts) is dict
        and set(facts)
        == set(expected) | {"initial_mnt", "current_mnt", "initial_userns", "current_userns"},
        "fixture_environment_shape",
    )
    need(
        all(type(facts[k]) is type(v) and facts[k] == v for k, v in expected.items()),
        "fixture_environment",
    )
    need(all(type(v) is int for v in facts["python"]), "fixture_environment")
    need(
        all(
            type(facts[k]) is int and facts[k] > 0
            for k in ("initial_mnt", "current_mnt", "initial_userns", "current_userns")
        ),
        "fixture_namespace",
    )
    need(
        facts["initial_mnt"] != facts["current_mnt"]
        and facts["initial_userns"] == facts["current_userns"],
        "fixture_namespace",
    )


def image_identity(info):
    need(stat.S_ISREG(info.st_mode), "fixture_image_type")
    return dict(
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.S_IMODE(info.st_mode),
        nlink=info.st_nlink,
        size=info.st_size,
    )


def create_image():
    try:
        fd = os.open(
            IMAGE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError:
        raise FixtureDenied("fixture_image_already_exists") from None
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, 0, 0)
        os.ftruncate(fd, IMAGE_BYTES)
        os.posix_fallocate(fd, 0, IMAGE_BYTES)
        os.fsync(fd)
        result = image_identity(os.fstat(fd))
        need(
            result["size"] == IMAGE_BYTES
            and result["uid"] == result["gid"] == 0
            and result["mode"] == 0o600
            and result["nlink"] == 1,
            "fixture_image_metadata",
        )
        return result
    finally:
        os.close(fd)


def run_fixture(ops):
    """One image/two mount rounds; ops is the fixed native OS boundary in main."""
    receipt = dict(
        schema_version=1,
        scope="SYNTHETIC_STORAGE_ONLY",
        status="failed",
        primary=None,
        cleanup=[],
        production_admission=False,
        provider_start_or_SDK=False,
    )
    stage = "ENVIRONMENT"
    try:
        facts = ops.environment()
        validate_environment(facts)
        receipt["environment"] = facts
        stage = "CREATE_ONCE"
        ops.initialize()
        stage = "FIRST_LAYOUT"
        first = ops.prepare()
        stage = "PRIME_AND_SOCKET"
        prime = ops.exercise(first, prime=True)
        need(
            prime["marker_created"]
            and prime["socket_reachable"]
            and prime["six_backings_verified"],
            "prime_evidence",
        )
        need(
            len(prime["per_target_bytes"]) == 6
            and all(n >= 4096 for n in prime["per_target_bytes"]),
            "six_prime_writes",
        )
        receipt["prime"] = prime
        stage = "FIRST_NORMAL_UNMOUNT"
        ops.unmount()
        stage = "SAME_IMAGE_REMOUNT"
        second = ops.prepare()
        need(
            all(first[k] == second[k] for k in ("image_identity", "fsid", "runtime_inode")),
            "remount_identity",
        )
        stage = "SPENT_AND_AGGREGATE_ENOSPC"
        fill = ops.exercise(second, prime=False)
        need(
            fill["spent_after_remount"] and fill["marker_inode"] == prime["marker_inode"],
            "remount_spent",
        )
        need(fill["enospc_errno"] == 28 and fill["six_backings_verified"], "aggregate_enospc")
        need(
            len(fill["per_target_bytes"]) == 6 and all(n >= 4096 for n in fill["per_target_bytes"]),
            "six_fill_writes",
        )
        receipt["fill"] = fill
        stage = "LOWER_PRESERVATION"
        receipt["lower"] = ops.verify_lowers()
        stage = "FINAL_NORMAL_UNMOUNT"
        ops.unmount()
        receipt["status"] = "passed"
    except BaseException as exc:
        receipt["primary"] = dict(
            stage=stage,
            type=type(exc).__name__,
            reason=str(exc) if isinstance(exc, FixtureDenied) else None,
            errno=exc.errno if isinstance(exc, OSError) else None,
        )
        if isinstance(exc, ChildFailed):
            receipt["primary"]["child"] = exc.diagnostic
    finally:
        try:
            receipt["cleanup"] = ops.cleanup()
        except BaseException as exc:
            receipt["cleanup"] = [dict(stage="OWNED_CLEANUP", type=type(exc).__name__)]
        if receipt["cleanup"]:
            receipt["status"] = "failed"
    return receipt


class MountAttr(ctypes.Structure):
    # Linux UAPI mount_attr ABI, not an upstream implementation copy.
    _fields_ = [
        ("attr_set", ctypes.c_uint64),
        ("attr_clr", ctypes.c_uint64),
        ("propagation", ctypes.c_uint64),
        ("userns_fd", ctypes.c_uint64),
    ]


def _mount_attribute(libc, path, *, readonly, recursive=False):
    # Linux v7.0 x86_64 syscall table:442; mount.h:32-byte v0 ABI/readonly1.
    attribute = MountAttr(1 if readonly else 0, 0 if readonly else 1, 0, 0)
    result = libc.syscall(
        ctypes.c_long(442),
        ctypes.c_long(-100),
        ctypes.c_char_p(path.encode("ascii")),
        ctypes.c_uint(0x8000 if recursive else 0),
        ctypes.byref(attribute),
        ctypes.c_size_t(ctypes.sizeof(attribute)),
    )
    need(result == 0, "mount_attributes_failed")


def setup_child(libc, parent_pid):
    need(libc.prctl(1, 9, 0, 0, 0) == 0 and os.getppid() == parent_pid, "parent_death_guard")
    need(libc.unshare(0x20000) == 0, "nested_namespace_failed")
    _mount_attribute(libc, "/", readonly=True, recursive=True)
    for path in WRITES:
        _mount_attribute(libc, path, readonly=False)
    os.setgroups([])
    os.setgid(987)
    os.setuid(997)
    need(libc.prctl(38, 1, 0, 0, 0) == 0, "no_new_privileges_failed")
    # Changing IDs clears PDEATHSIG: re-arm and recheck after the final ID change.
    need(libc.prctl(1, 9, 0, 0, 0) == 0 and os.getppid() == parent_pid, "parent_death_guard")


def fill_files(fds):
    """Append/sync owned image-backed files; only actual errno28 proves exhaustion."""
    need(len(fds) == 6 and len(set(fds)) == 6, "six_owned_files_required")
    written = [os.fstat(fd).st_size for fd in fds]
    need(all(type(n) is int and 0 <= n <= IMAGE_BYTES for n in written), "initial_file_size")
    chunk = b"Q" * 1048576
    operation = "write"
    while sum(written) < 2 * IMAGE_BYTES:
        for index, fd in enumerate(fds):
            if sum(written) >= 2 * IMAGE_BYTES:
                break
            try:
                remaining = memoryview(chunk)
                operation = "write"
                while remaining:
                    count = os.write(fd, remaining)
                    need(0 < count <= len(remaining), "fixture_short_write")
                    written[index] += count
                    remaining = remaining[count:]
                operation = "fsync"
                os.fsync(fd)
            except OSError as exc:
                if exc.errno == errno.ENOSPC:
                    return dict(
                        enospc_errno=exc.errno, enospc_operation=operation, per_target_bytes=written
                    )
                raise
    raise FixtureDenied("bounded_enospc_not_observed")


def consume_marker(*, prime):
    """Use the real create-only/fsync primitive; never delete a partial marker."""
    directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = NONCE + ".recovery"
    try:
        try:
            fd = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
        except FileExistsError:
            need(not prime, "fixture_marker_already_spent")
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            need(
                stat.S_ISREG(info.st_mode)
                and info.st_uid == 997
                and info.st_gid == 987
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1
                and 0 <= info.st_size <= 1024,
                "fixture_marker_metadata",
            )
            return info.st_ino
        try:
            need(prime, "marker_missing_after_remount")
            os.fchmod(fd, 0o600)
            pending = memoryview(b"SYNTHETIC_FIXTURE_SPENT_" + NONCE.encode() + b"\n")
            while pending:
                count = os.write(fd, pending)
                need(0 < count <= len(pending), "fixture_marker_short_write")
                pending = pending[count:]
            os.fsync(fd)
            os.fsync(directory)
            return os.fstat(fd).st_ino
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def child_program(profile, *, prime, gate_fd, guard_source):
    """Embed reviewed public code, not a second imitation of the guard/primitives."""
    need(
        type(guard_source) is bytes and hashlib.sha256(guard_source).hexdigest() == GUARD_SHA,
        "fixture_guard_source_drift",
    )
    need(type(prime) is bool and type(gate_fd) is int and gate_fd > 2, "fixture_child_arguments")
    code = "import errno,json,os,socket,stat,sys,types\n"
    code += "class FixtureDenied(RuntimeError): pass\n"
    code += inspect.getsource(need) + "\n"
    code += f"STATE={STATE!r}\nNONCE={NONCE!r}\nIMAGE_BYTES={IMAGE_BYTES!r}\n"
    code += f"WRITES={WRITES!r}\nRUNTIME={RUNTIME!r}\n"
    code += inspect.getsource(consume_marker) + "\n" + inspect.getsource(fill_files) + "\n"
    body = "guard=types.ModuleType('fixture_storage_guard')\n"
    body += "sys.modules[guard.__name__]=guard\n"
    body += f"exec(compile({guard_source!r}, '<reviewed-storage-guard>', 'exec'),guard.__dict__)\n"
    body += f"profile={profile!r}\nprime={prime!r}\ngate_fd={gate_fd!r}\n"
    body += """
stage='IDENTITY'
need(os.getuid()==997 and os.geteuid()==997 and os.getgid()==987 and not os.getgroups(),
     'fixture_child_identity')
with open('/proc/self/status','rb') as stream:
    status=stream.read(16385)
need(len(status)<=16384, 'fixture_status_bound')
fields=dict(line.split(b':',1) for line in status.splitlines() if b':' in line)
need(int(fields[b'CapEff'].strip(),16)==0 and fields[b'NoNewPrivs'].strip()==b'1',
     'fixture_child_privileges')
stage='LAYOUT'
guard.validate_snapshot(profile,guard.capture_live(profile))
stage='MARKER'
marker_view_inode=consume_marker(prime=prime)
fds=[]
listener=None
try:
    stage='PROBES'
    for target in WRITES:
        flags=os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC
        if prime: flags|=os.O_CREAT|os.O_EXCL
        fd=os.open(target+'/.qm-fixture-probe',flags,0o600)
        fds.append(fd)
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==997 and info.st_gid==987
             and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,
             'fixture_probe_metadata')
        if prime:
            need(info.st_size==0 and os.write(fd,b'Q'*4096)==4096,'fixture_prime_write')
            os.fsync(fd)
        else:
            need(info.st_size==4096,'fixture_remount_probe_size')
    if prime:
        stage='SOCKET'
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        listener.settimeout(15)
        listener.bind(RUNTIME+'/.qm-fixture.sock')
        listener.listen(1)
    print(json.dumps(dict(event='READY',marker_view_inode=marker_view_inode,
                          per_target_bytes=[os.fstat(fd).st_size for fd in fds])),flush=True)
    if listener is not None:
        connection,_=listener.accept()
        with connection:
            connection.settimeout(10)
            need(connection.recv(4)==b'PING','fixture_socket_request')
            connection.sendall(b'PONG')
    stage='GATE'
    need(os.read(gate_fd,1)==b'G','fixture_parent_gate')
    os.close(gate_fd)
    if prime:
        result=dict(per_target_bytes=[os.fstat(fd).st_size for fd in fds])
    else:
        stage='FILL'
        result=fill_files(fds)
    stage='FINAL_LAYOUT'
    guard.validate_snapshot(profile,guard.capture_live(profile))
    print(json.dumps(dict(event='DONE',**result)),flush=True)
finally:
    if listener is not None: listener.close()
    for fd in fds: os.close(fd)
"""
    code += "stage='SETUP'\ntry:\n" + textwrap.indent(body, "    ")
    code += """except BaseException as exc:
    reason=str(exc) if type(exc).__name__ in {'FixtureDenied','StorageDenied'} else None
    print(json.dumps(dict(event='FAIL',stage=stage,type=type(exc).__name__,reason=reason,
                          errno=exc.errno if isinstance(exc,OSError) else None)),flush=True)
    raise SystemExit(1)
"""
    need(len(code.encode("utf-8")) <= 65536, "fixture_child_source_bound")
    compile(code, "<synthetic-child>", "exec")
    return code


def decode_event(raw):
    need(len(raw) <= 8192, "fixture_child_output_bound")
    value = json.loads(raw)
    need(type(value) is dict, "fixture_child_receipt")
    if value.get("event") == "FAIL":
        need(set(value) == {"event", "stage", "type", "reason", "errno"}, "child_failure_shape")
        need(
            value["stage"]
            in {
                "SETUP",
                "IDENTITY",
                "LAYOUT",
                "MARKER",
                "PROBES",
                "SOCKET",
                "GATE",
                "FILL",
                "FINAL_LAYOUT",
            },
            "child_failure_shape",
        )
        need(
            type(value["type"]) is str
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value["type"]) is not None,
            "child_failure_shape",
        )
        need(
            value["reason"] is None
            or (
                type(value["reason"]) is str
                and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value["reason"]) is not None
            ),
            "child_failure_shape",
        )
        need(
            value["errno"] is None or (type(value["errno"]) is int and 0 <= value["errno"] < 4096),
            "child_failure_shape",
        )
        raise ChildFailed({key: value[key] for key in ("stage", "type", "reason", "errno")})
    return value


class NativeOps:
    """Fixed, existing tools inside the already verified preparation namespace."""

    def __init__(self):
        self.mounts = []
        self.loop = None
        self.child = None
        self.gate = None
        self.end = time.monotonic() + 195
        self.root = IMAGE.rsplit("/", 1)[0]

    def remaining(self, maximum=15):
        seconds = min(maximum, self.end - time.monotonic())
        need(seconds > 0, "fixture_deadline")
        return seconds

    @staticmethod
    def read(path, limit):
        with open(path, "rb") as stream:
            raw = stream.read(limit + 1)
        need(len(raw) <= limit, "fixture_public_read_bound")
        return raw

    def environment(self):
        status = dict(
            line.split(b":", 1)
            for line in self.read("/proc/self/status", 16384).splitlines()
            if b":" in line
        )
        return dict(
            platform=sys.platform,
            architecture=platform.machine(),
            uid=os.getuid(),
            euid=os.geteuid(),
            python=list(sys.version_info[:2]),
            isolated=bool(sys.flags.isolated),
            no_site=bool(sys.flags.no_site),
            no_bytecode=bool(sys.dont_write_bytecode),
            machine_sha256=hashlib.sha256(self.read("/etc/machine-id", 256)).hexdigest(),
            kernel=platform.release(),
            cap_sys_admin=bool(int(status[b"CapEff"].strip(), 16) & (1 << 21)),
            threads=threading.active_count(),
            sigchld_default=signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
            initial_mnt=os.stat("/proc/1/ns/mnt").st_ino,
            current_mnt=os.stat("/proc/self/ns/mnt").st_ino,
            initial_userns=os.stat("/proc/1/ns/user").st_ino,
            current_userns=os.stat("/proc/self/ns/user").st_ino,
        )

    def command(self, argv):
        need(
            argv[0]
            in {"/usr/bin/mount", "/usr/bin/umount", "/usr/sbin/mke2fs", "/usr/sbin/losetup"},
            "fixture_tool_allowlist",
        )
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={},
            cwd="/",
            timeout=self.remaining(),
        )
        need(len(result.stdout) <= 4096 and result.returncode == 0, "fixture_tool_failed")
        return result.stdout

    def directory(self, path, *, uid=0, gid=0, mode=0o755):
        os.mkdir(path, mode)
        os.chown(path, uid, gid, follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)

    def public_file(self, path, raw, *, uid=0, gid=0, mode=0o600):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        try:
            os.fchown(fd, uid, gid)
            os.fchmod(fd, mode)
            need(os.write(fd, raw) == len(raw), "fixture_setup_short_write")
            os.fsync(fd)
        finally:
            os.close(fd)

    def mount(self, argv, target):
        self.command(["/usr/bin/mount", *argv, target])
        self.mounts.append(target)

    def bind(self, source, target, *, readonly=False):
        self.mount(["--bind", source], target)
        if readonly:
            self.command(["/usr/bin/mount", "-o", "remount,bind,ro", target])

    def initialize(self):
        # No helper/tool/image operation until run_fixture validated environment.
        self.guard_source = self.read(str(Path(__file__).with_name("private_storage.py")), 65536)
        need(
            hashlib.sha256(self.guard_source).hexdigest() == GUARD_SHA, "fixture_guard_source_drift"
        )
        for fixed in ("/", "/srv", "/usr", "/usr/bin", "/usr/sbin"):
            info = os.lstat(fixed)
            need(
                stat.S_ISDIR(info.st_mode)
                and info.st_uid == info.st_gid == 0
                and not info.st_mode & 0o022,
                "fixture_protected_parent",
            )
        for tool in (
            "/usr/bin/mount",
            "/usr/bin/umount",
            "/usr/sbin/mke2fs",
            "/usr/sbin/losetup",
            "/usr/bin/python3.12",
        ):
            info = os.stat(tool)
            need(
                stat.S_ISREG(info.st_mode)
                and info.st_uid == info.st_gid == 0
                and not info.st_mode & 0o022,
                "fixture_protected_tool",
            )
        # Existing purpose root means an attempt already exists: never reset it.
        self.directory(self.root, mode=0o700)
        self.public_file(self.root + "/ATTEMPT", b"ONE_SYNTHETIC_STORAGE_ATTEMPT\n")
        self.identity = create_image()
        self.command(
            [
                "/usr/sbin/mke2fs",
                "-q",
                "-t",
                "ext4",
                "-F",
                "-m",
                "0",
                "-b",
                "1024",
                "-E",
                "lazy_itable_init=0,lazy_journal_init=0",
                IMAGE,
            ]
        )
        self.command(["/usr/bin/mount", "--make-rprivate", "/"])
        for name in ("fake-lib", "fake-run", "fake-etc", "lower-home", "lower-state"):
            self.directory(self.root + "/" + name)
        for name in ("lower-home", "lower-state"):
            os.chown(self.root + "/" + name, 997, 987)
            os.chmod(self.root + "/" + name, 0o700)
        self.public_file(
            self.root + "/lower-home/synthetic", b"PUBLIC_SYNTHETIC_LOWER\n", uid=997, gid=987
        )
        self.public_file(self.root + "/lower-state/" + NONCE, b"", uid=997, gid=987)
        self.lower_before = self.lower_facts()
        for source, target in (
            ("fake-lib", "/var/lib"),
            ("fake-run", "/run"),
            ("fake-etc", "/etc/quantmesh/opend"),
        ):
            need(stat.S_ISDIR(os.lstat(target).st_mode), "fixture_existing_mountpoint")
            self.bind(self.root + "/" + source, target)
        for target in (HOME, STATE, RUNTIME, POOL):
            self.directory(target)
        for suffix in ("fs", "lower-home", "lower-state", "view-home", "view-state"):
            self.directory(POOL + "/" + suffix)
        self.public_file("/etc/quantmesh/opend/private-storage-image", b"")
        self.base_count = len(self.mounts)

    def prepare(self):
        need(
            self.loop is None and len(self.mounts) == self.base_count, "fixture_round_still_mounted"
        )
        need(image_identity(os.lstat(IMAGE)) == self.identity, "fixture_image_drift")
        loop = self.command(
            [
                "/usr/sbin/losetup",
                "--find",
                "--show",
                "--nooverlap",
                "--sizelimit",
                str(IMAGE_BYTES),
                IMAGE,
            ]
        ).strip()
        need(re.fullmatch(rb"/dev/loop[0-9]{1,6}", loop) is not None, "fixture_loop_name")
        self.loop = loop.decode("ascii")
        info = os.stat(self.loop)
        need(stat.S_ISBLK(info.st_mode) and os.major(info.st_rdev) == 7, "fixture_loop_device")
        device = [os.major(info.st_rdev), os.minor(info.st_rdev)]
        self.mount(["-t", "ext4", "-o", "rw,nosuid,nodev", self.loop], POOL + "/fs")
        self.fresh = not os.path.exists(POOL + "/fs/runtime")
        if self.fresh:
            for suffix in (
                "home-upper",
                "home-work",
                "state-upper",
                "state-work",
                "runtime",
                "tmp",
                "vartmp",
                "shm",
            ):
                temporary = suffix in {"tmp", "vartmp", "shm"}
                self.directory(
                    POOL + "/fs/" + suffix,
                    uid=0 if temporary else 997,
                    gid=0 if temporary else 987,
                    mode=0o1777 if temporary else 0o700,
                )
        for name in ("home", "state"):
            self.bind(self.root + "/lower-" + name, POOL + "/lower-" + name, readonly=True)
            options = (
                f"lowerdir={POOL}/lower-{name},upperdir={POOL}/fs/{name}-upper,"
                f"workdir={POOL}/fs/{name}-work"
            )
            self.mount(["-t", "overlay", "overlay", "-o", options], POOL + "/view-" + name)
        self.bind(POOL + "/lower-state/" + NONCE, POOL + "/view-state/" + NONCE, readonly=True)
        # Recursive view bind carries the immutable claim submount into STATE.
        self.mount(["--rbind", POOL + "/view-state"], STATE)
        # rbind creates both mounts; account for both so cleanup is exact reverse.
        self.mounts.append(STATE + "/" + NONCE)
        self.bind(POOL + "/view-home", HOME)
        for source, target in (
            ("runtime", RUNTIME),
            ("tmp", "/tmp"),
            ("vartmp", "/var/tmp"),
            ("shm", "/dev/shm"),
        ):
            self.bind(POOL + "/fs/" + source, target)
        self.bind(IMAGE, "/etc/quantmesh/opend/private-storage-image", readonly=True)
        runtime = os.stat(RUNTIME)
        lower = os.stat(self.root + "/lower-home")
        need(lower.st_dev == os.stat(self.root + "/lower-state").st_dev, "fixture_lower_device")
        return dict(
            schema_version=1,
            purpose="opend_c8_private_storage",
            nonce=NONCE,
            image_bytes=IMAGE_BYTES,
            backing_file=IMAGE,
            image_identity=self.identity,
            device=device,
            fsid=os.statvfs(RUNTIME).f_fsid,
            runtime_inode=runtime.st_ino,
            lower_device=[os.major(lower.st_dev), os.minor(lower.st_dev)],
            lower_roots={name: self.root + "/lower-" + name for name in ("home", "state")},
        )

    def line(self):
        raw = bytearray()
        while len(raw) <= 8192:
            need(
                select.select([self.child.stdout], [], [], self.remaining(40))[0],
                "fixture_child_timeout",
            )
            char = os.read(self.child.stdout.fileno(), 1)
            need(bool(char), "fixture_child_eof")
            if char == b"\n":
                return decode_event(raw)
            raw.extend(char)
        raise FixtureDenied("fixture_child_output_bound")

    def backings(self, profile):
        paths = [
            POOL + "/fs/" + name + "/.qm-fixture-probe"
            for name in ("home-upper", "state-upper", "runtime", "tmp", "vartmp", "shm")
        ]
        for path in paths:
            info = os.lstat(path)
            need(
                stat.S_ISREG(info.st_mode)
                and [os.major(info.st_dev), os.minor(info.st_dev)] == profile["device"]
                and info.st_uid == 997
                and info.st_gid == 987
                and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_size == 4096,
                "fixture_probe_backing",
            )

    def exercise(self, profile, *, prime):
        read_gate, self.gate = os.pipe()
        try:
            program = child_program(
                profile, prime=prime, gate_fd=read_gate, guard_source=self.guard_source
            )
            libc = ctypes.CDLL(None, use_errno=True)
            libc.syscall.restype = ctypes.c_long
            parent = os.getpid()
            self.child = subprocess.Popen(
                ["/usr/bin/python3.12", "-B", "-I", "-S", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={},
                cwd="/",
                pass_fds=(read_gate,),
                preexec_fn=lambda: setup_child(libc, parent),
            )
        finally:
            os.close(read_gate)
        self.child.stdin.write(program.encode("utf-8"))
        self.child.stdin.close()
        ready = self.line()
        need(
            ready.get("event") == "READY" and ready.get("per_target_bytes") == [4096] * 6,
            "fixture_ready",
        )
        self.backings(profile)
        marker_inode = os.lstat(POOL + "/fs/state-upper/" + NONCE + ".recovery").st_ino
        socket_reachable = False
        if prime:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.remaining(10))
                connection.connect(RUNTIME + "/.qm-fixture.sock")
                connection.sendall(b"PING")
                need(connection.recv(4) == b"PONG", "fixture_socket_outside")
                socket_reachable = True
        need(os.write(self.gate, b"G") == 1, "fixture_gate_write")
        os.close(self.gate)
        self.gate = None
        result = self.line()
        need(result.pop("event", None) == "DONE", "fixture_done")
        need(self.child.wait(timeout=self.remaining(40)) == 0, "fixture_child_exit")
        self.close_child()
        return dict(
            **result,
            marker_inode=marker_inode,
            marker_created=prime,
            spent_after_remount=not prime,
            socket_reachable=socket_reachable,
            six_backings_verified=True,
        )

    def lower_facts(self):
        claim = os.lstat(self.root + "/lower-state/" + NONCE)
        return dict(
            home_sha256=hashlib.sha256(
                self.read(self.root + "/lower-home/synthetic", 1024)
            ).hexdigest(),
            claim=[
                claim.st_dev,
                claim.st_ino,
                claim.st_uid,
                claim.st_gid,
                stat.S_IMODE(claim.st_mode),
                claim.st_nlink,
                claim.st_size,
                claim.st_mtime_ns,
                claim.st_ctime_ns,
            ],
        )

    def verify_lowers(self):
        facts = self.lower_facts()
        need(facts == self.lower_before, "fixture_lower_changed")
        return dict(home_sha256=facts["home_sha256"], claim_nine_fields_unchanged=True)

    def close_child(self):
        if self.child is not None:
            if self.child.poll() is None:
                self.child.kill()
            self.child.wait(timeout=8)
            self.child.stdin.close()
            self.child.stdout.close()
            self.child = None
        if self.gate is not None:
            os.close(self.gate)
            self.gate = None

    def unmount(self, *, final=False):
        self.close_child()
        floor = 0 if final else self.base_count
        while len(self.mounts) > floor:
            self.command(["/usr/bin/umount", self.mounts[-1]])
            self.mounts.pop()
        if self.loop is not None:
            self.command(["/usr/sbin/losetup", "--detach", self.loop])
            self.loop = None

    def cleanup(self):
        # Reserve is separate from proof deadline; one normal reverse close only.
        self.end = max(self.end, time.monotonic() + 25)
        try:
            self.unmount(final=True)
            return []
        except BaseException as exc:
            return [
                dict(
                    stage="OWNED_NORMAL_CLOSE",
                    type=type(exc).__name__,
                    mounts_retained=len(self.mounts),
                    loop_retained=self.loop is not None,
                    child_retained=self.child is not None,
                )
            ]


def main():
    if len(sys.argv) != 1:
        return 2

    def interrupted(number, frame):
        raise FixtureDenied("fixture_interrupted")

    previous = {
        number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        receipt = run_fixture(NativeOps())
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    if len(raw.encode("utf-8")) > 32768:
        print('{"status":"failed","primary":"fixture_receipt_bound"}')
        return 1
    print(raw, flush=True)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
