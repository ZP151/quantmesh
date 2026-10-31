"""Offline native-fixture safety controls; no Linux mounts or provider actions."""

import ast
import copy
import ctypes
import errno
import hashlib
import importlib.util
import inspect
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "/srv/quantmesh-opend-private-storage-20261031/fixture.ext4"
MACHINE = "a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191"


def module():
    path = ROOT / "deploy/aws/opend/private_storage_fixture.py"
    assert path.exists(), "the finite namespace fixture has not been implemented"
    spec = importlib.util.spec_from_file_location("private_storage_fixture_tests", path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def environment():
    return dict(
        platform="linux",
        architecture="x86_64",
        uid=0,
        euid=0,
        python=[3, 12],
        isolated=True,
        no_site=True,
        no_bytecode=True,
        machine_sha256=MACHINE,
        kernel="7.0.0-1012-aws",
        initial_mnt=1,
        current_mnt=2,
        initial_userns=3,
        current_userns=3,
        cap_sys_admin=True,
        threads=1,
        sigchld_default=True,
    )


@pytest.mark.parametrize(
    "change",
    [
        None,
        "uid",
        "euid",
        "platform",
        "architecture",
        "python",
        "isolated",
        "current_mnt",
        "current_userns",
        "machine_sha256",
        "kernel",
        "cap_sys_admin",
        "threads",
    ],
)
def test_fixture_refuses_an_unproved_root_namespace_before_any_allocation(change):
    fixture = module()
    facts = environment()
    if change:
        facts[change] = {
            "uid": 997,
            "euid": 997,
            "platform": "win32",
            "architecture": "aarch64",
            "python": [3, 13],
            "isolated": False,
            "current_mnt": 1,
            "current_userns": 99,
            "machine_sha256": "0" * 64,
            "kernel": "foreign",
            "cap_sys_admin": False,
            "threads": 2,
        }[change]
        with pytest.raises(fixture.FixtureDenied):
            fixture.validate_environment(facts)
    else:
        assert fixture.validate_environment(facts) is None


def test_existing_fixture_image_is_not_opened_for_formatting_or_replaced(tmp_path, monkeypatch):
    fixture = module()
    history = tmp_path / "fixture.ext4"
    history.write_bytes(b"RETAINED_FAILED_IMAGE")
    opened = []

    def open_image(path, flags, mode=0o777):
        assert str(path) == IMAGE
        opened.append(flags)
        return os.open(history, flags, mode)

    def no_write(*args):
        pytest.fail("an existing image must not be truncated or reformatted")

    fake = SimpleNamespace(
        open=open_image,
        close=os.close,
        ftruncate=no_write,
        posix_fallocate=no_write,
        fsync=no_write,
        fstat=os.fstat,
        O_WRONLY=os.O_WRONLY,
        O_CREAT=os.O_CREAT,
        O_EXCL=os.O_EXCL,
        O_NOFOLLOW=getattr(os, "O_NOFOLLOW", 0),
    )
    monkeypatch.setattr(fixture, "os", fake)
    with pytest.raises(fixture.FixtureDenied):
        fixture.create_image()
    assert opened and opened[0] & os.O_EXCL
    assert history.read_bytes() == b"RETAINED_FAILED_IMAGE"


class KernelAdapter:
    """Stateful external mount/process boundary model, never native evidence."""

    def __init__(self, failure=None):
        self.failure = failure
        self.images, self.mounts, self.loops, self.children = [], [], [], []
        self.cleaned = False
        self.round = 0

    def environment(self):
        value = environment()
        if self.failure == "environment":
            value["current_mnt"] = value["initial_mnt"]
        return value

    def initialize(self):
        self.images.append({"device": 66305, "inode": 44, "size": 33554432})

    def prepare(self):
        self.round += 1
        self.mounts.append("OWNED_PRIVATE_MOUNTS")
        self.loops.append("OWNED_LOOP")
        if self.failure == "prepare":
            raise OSError(5, "modeled mount failure")
        identity = copy.deepcopy(self.images[0])
        if self.failure == "replaced_image" and self.round == 2:
            identity["inode"] = 45
        return {"image_identity": identity, "fsid": 101, "runtime_inode": 11}

    def exercise(self, profile, *, prime):
        self.children.append("OWNED_CHILD")
        if self.failure == ("prime" if prime else "fill"):
            raise OSError(5, "modeled child failure")
        self.children.clear()
        return {
            "phase": "prime" if prime else "fill",
            "marker_inode": 88,
            "marker_created": prime,
            "spent_after_remount": not prime,
            "socket_reachable": prime,
            "six_backings_verified": True,
            "enospc_errno": None if prime else 28,
            "per_target_bytes": [4096] * 6 if prime else [4194304] * 6,
        }

    def unmount(self):
        self.mounts.clear()
        self.loops.clear()

    def verify_lowers(self):
        if self.failure == "lower_changed":
            raise ValueError("modeled lower mismatch")
        return {"home_sha256": "1" * 64, "claim_nine_fields_unchanged": True}

    def cleanup(self):
        self.children.clear()
        self.mounts.clear()
        self.loops.clear()
        self.cleaned = True
        return []


@pytest.mark.parametrize(
    "failure", [None, "environment", "prepare", "prime", "fill", "replaced_image", "lower_changed"]
)
def test_finite_fixture_retains_one_image_and_closes_owned_resources_on_failure(failure):
    fixture = module()
    assert callable(getattr(fixture, "run_fixture", None)), "finite proof lifecycle is absent"
    kernel = KernelAdapter(failure)
    receipt = fixture.run_fixture(kernel)
    assert receipt["status"] == ("passed" if failure is None else "failed")
    assert kernel.cleaned and not kernel.children and not kernel.mounts and not kernel.loops
    assert len(kernel.images) == (0 if failure == "environment" else 1)
    assert receipt["provider_start_or_SDK"] is False
    assert receipt["production_admission"] is False
    if failure is None:
        assert receipt["prime"]["marker_inode"] == receipt["fill"]["marker_inode"] == 88


@pytest.mark.parametrize("failure", [None, "unshare", "readonly"])
def test_unit_like_namespace_cannot_change_mounts_before_successful_unshare(monkeypatch, failure):
    fixture = module()
    assert callable(getattr(fixture, "setup_child", None)), "the nested namespace entry is absent"
    changes, identities = [], []

    class Kernel:
        @staticmethod
        def prctl(*args):
            return 0

        @staticmethod
        def unshare(flags):
            assert flags == 0x20000
            return -1 if failure == "unshare" else 0

        @staticmethod
        def syscall(number, directory, path, flags, attributes, size):
            assert number.value == 442 and directory.value == -100 and size.value == 32
            attr = attributes._obj
            changes.append((path.value.decode(), flags.value, attr.attr_set, attr.attr_clr))
            return -1 if failure == "readonly" else 0

    fake = SimpleNamespace(
        getppid=lambda: 123,
        setgroups=lambda groups: identities.append(("groups", groups)),
        setgid=lambda gid: identities.append(("gid", gid)),
        setuid=lambda uid: identities.append(("uid", uid)),
    )
    monkeypatch.setattr(fixture, "os", fake)
    ctypes.set_errno(1)
    if failure:
        with pytest.raises(fixture.FixtureDenied):
            fixture.setup_child(Kernel(), 123)
        assert not identities
        assert len(changes) == (0 if failure == "unshare" else 1)
    else:
        fixture.setup_child(Kernel(), 123)
        assert changes[0] == ("/", 0x8000, 1, 0)
        assert [row[0] for row in changes[1:]] == [
            "/var/lib/quantmesh-opend",
            "/var/lib/quantmesh-opend-stage",
            "/run/quantmesh-opend-console-c8f0d0de4ca641a491fca6df24c66ceb",
            "/tmp",
            "/var/tmp",
            "/dev/shm",
        ]
        assert all(row[1:] == (0, 0, 1) for row in changes[1:])
        assert identities == [("groups", []), ("gid", 987), ("uid", 997)]


@pytest.mark.parametrize("number", [errno.ENOSPC, errno.EIO, 0])
def test_aggregate_writer_requires_actual_enospc_and_rejects_other_or_zero_writes(
    monkeypatch, number
):
    fixture = module()
    assert callable(getattr(fixture, "fill_files", None)), "bounded aggregate writer is absent"
    total = 0

    def write(fd, data):
        nonlocal total
        if not number:
            return 0
        if total >= 512:
            raise OSError(number, "modeled external filesystem result")
        total += 512
        return 512

    fake = SimpleNamespace(
        fstat=lambda fd: SimpleNamespace(st_size=4096), write=write, fsync=lambda fd: None
    )
    monkeypatch.setattr(fixture, "os", fake)
    if number == errno.ENOSPC:
        receipt = fixture.fill_files([10, 11, 12, 13, 14, 15])
        assert receipt["enospc_errno"] == errno.ENOSPC
        assert receipt["per_target_bytes"] == [4608, 4096, 4096, 4096, 4096, 4096]
    elif number:
        with pytest.raises(OSError) as error:
            fixture.fill_files([10, 11, 12, 13, 14, 15])
        assert error.value.errno == errno.EIO
    else:
        with pytest.raises(fixture.FixtureDenied):
            fixture.fill_files([10, 11, 12, 13, 14, 15])


@pytest.mark.parametrize("failure", [None, "write", "fsync"])
def test_fixture_marker_is_irreversibly_spent_even_when_persistence_fails(
    tmp_path, monkeypatch, failure
):
    fixture = module()
    assert callable(getattr(fixture, "consume_marker", None)), "native marker primitive is absent"
    marker = tmp_path / "synthetic.recovery"
    handles = set()

    def open_file(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is None:
            assert path == "/var/lib/quantmesh-opend-stage"
            handles.add(100000)
            return 100000
        assert dir_fd == 100000 and path.endswith(".recovery")
        fd = os.open(marker, flags | getattr(os, "O_BINARY", 0), mode)
        handles.add(fd)
        return fd

    def close(fd):
        handles.remove(fd)
        if fd != 100000:
            os.close(fd)

    def write(fd, raw):
        if failure == "write":
            raise OSError(errno.ENOSPC, "modeled marker write exhaustion")
        return os.write(fd, raw)

    def sync(fd):
        if failure == "fsync" and fd != 100000:
            raise OSError(errno.ENOSPC, "modeled marker fsync exhaustion")
        if fd != 100000:
            os.fsync(fd)

    def info(value):
        return SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600,
            st_uid=997,
            st_gid=987,
            st_nlink=1,
            st_size=value.st_size,
            st_ino=value.st_ino,
        )

    fake = SimpleNamespace(
        open=open_file,
        close=close,
        write=write,
        fsync=sync,
        fchmod=lambda fd, mode: None,
        fstat=lambda fd: info(os.fstat(fd)),
        stat=lambda name, **kw: info(marker.stat()),
        O_RDONLY=os.O_RDONLY,
        O_WRONLY=os.O_WRONLY,
        O_CREAT=os.O_CREAT,
        O_EXCL=os.O_EXCL,
        O_DIRECTORY=getattr(os, "O_DIRECTORY", 65536),
        O_NOFOLLOW=getattr(os, "O_NOFOLLOW", 0),
    )
    monkeypatch.setattr(fixture, "os", fake)
    if failure:
        with pytest.raises(OSError):
            fixture.consume_marker(prime=True)
    else:
        fixture.consume_marker(prime=True)
    assert marker.exists() and not handles
    assert fixture.consume_marker(prime=False) == marker.stat().st_ino
    with pytest.raises(fixture.FixtureDenied):
        fixture.consume_marker(prime=True)
    assert marker.exists() and not handles


def test_child_source_uses_the_exact_reviewed_guard_and_real_tested_primitives():
    from test_opend_private_storage import layout

    fixture = module()
    assert callable(getattr(fixture, "child_program", None)), "the finite child program is absent"
    profile, _ = layout()
    profile["backing_file"] = IMAGE
    guard_source = (ROOT / "deploy/aws/opend/private_storage.py").read_bytes()
    program = fixture.child_program(profile, prime=True, gate_fd=17, guard_source=guard_source)
    tree = ast.parse(program)
    compile(program, "<synthetic-child>", "exec")
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for function in (fixture.consume_marker, fixture.fill_files):
        expected = ast.parse(inspect.getsource(function)).body[0]
        assert ast.dump(functions[function.__name__], include_attributes=False) == ast.dump(
            expected, include_attributes=False
        )
    assert len(program) <= 65536
    with pytest.raises(fixture.FixtureDenied):
        fixture.child_program(
            profile, prime=True, gate_fd=17, guard_source=guard_source + b"# drift\n"
        )


def test_native_cleanup_does_not_detach_a_loop_with_an_unclosed_owned_mount(monkeypatch):
    fixture = module()
    assert hasattr(fixture, "NativeOps"), "fixed native OS boundary is absent"
    ops = fixture.NativeOps()
    ops.mounts = ["/owned/fs", "/owned/view"]
    ops.loop = "/dev/loop8"
    calls = []

    def command(argv):
        calls.append(argv)
        if argv[0].endswith("umount"):
            raise fixture.FixtureDenied("modeled_busy_mount")
        pytest.fail("a busy owned mount must retain its loop association")

    monkeypatch.setattr(ops, "command", command)
    errors = ops.cleanup()
    assert errors and calls == [["/usr/bin/umount", "/owned/view"]]
    assert ops.mounts == ["/owned/fs", "/owned/view"] and ops.loop == "/dev/loop8"


def test_native_successful_cleanup_closes_only_owned_handles_in_reverse_order(monkeypatch):
    fixture = module()
    assert hasattr(fixture, "NativeOps"), "fixed native OS boundary is absent"
    ops = fixture.NativeOps()
    ops.mounts = ["/owned/fs", "/owned/view"]
    ops.loop = "/dev/loop8"
    calls = []
    monkeypatch.setattr(ops, "command", lambda argv: calls.append(argv) or b"")
    assert ops.cleanup() == []
    assert calls == [
        ["/usr/bin/umount", "/owned/view"],
        ["/usr/bin/umount", "/owned/fs"],
        ["/usr/sbin/losetup", "--detach", "/dev/loop8"],
    ]
    assert not ops.mounts and ops.loop is None


def test_native_child_cleanup_waits_for_the_exact_owned_child_before_unmount(monkeypatch):
    fixture = module()
    assert hasattr(fixture, "NativeOps"), "fixed native OS boundary is absent"
    ops = fixture.NativeOps()
    calls = []
    ops.child = SimpleNamespace(
        poll=lambda: None,
        kill=lambda: calls.append("kill-owned"),
        wait=lambda **kw: calls.append("join-owned"),
        stdin=SimpleNamespace(close=lambda: calls.append("close-in")),
        stdout=SimpleNamespace(close=lambda: calls.append("close-out")),
    )
    ops.mounts = ["/owned/fs"]
    monkeypatch.setattr(ops, "command", lambda argv: calls.append(argv) or b"")
    assert ops.cleanup() == []
    assert calls == [
        "kill-owned",
        "join-owned",
        "close-in",
        "close-out",
        ["/usr/bin/umount", "/owned/fs"],
    ]


def test_termination_during_exercise_reaches_owned_cleanup_and_keeps_the_image(monkeypatch, capsys):
    fixture = module()
    kernel = KernelAdapter()
    handlers = {}

    def install(number, handler):
        previous = handlers.get(number, fixture.signal.SIG_DFL)
        handlers[number] = handler
        return previous

    def interrupted(profile, *, prime):
        kernel.children.append("OWNED_CHILD")
        handlers[fixture.signal.SIGTERM](fixture.signal.SIGTERM, None)

    kernel.exercise = interrupted
    monkeypatch.setattr(fixture, "NativeOps", lambda: kernel)
    monkeypatch.setattr(fixture.sys, "argv", ["fixed-fixture"])
    monkeypatch.setattr(fixture.signal, "signal", install)
    assert fixture.main() == 1
    assert kernel.cleaned and len(kernel.images) == 1 and not kernel.children
    assert "fixture_interrupted" in capsys.readouterr().out
    assert handlers == {
        fixture.signal.SIGTERM: fixture.signal.SIG_DFL,
        fixture.signal.SIGINT: fixture.signal.SIG_DFL,
    }


def test_native_environment_preserves_the_exact_pinned_machine_id_bytes(monkeypatch):
    fixture = module()
    ops = fixture.NativeOps()
    machine_id = b"PUBLIC_SYNTHETIC_MACHINE_ID\n"
    monkeypatch.setattr(
        fixture, "signal", SimpleNamespace(SIGCHLD=17, SIG_DFL=0, getsignal=lambda number: 0)
    )
    monkeypatch.setattr(
        ops,
        "read",
        lambda path, limit: machine_id if path == "/etc/machine-id" else b"CapEff:\t00200000\n",
    )
    monkeypatch.setattr(
        fixture,
        "os",
        SimpleNamespace(
            getuid=lambda: 0,
            geteuid=lambda: 0,
            stat=lambda path: SimpleNamespace(
                st_ino={
                    "/proc/1/ns/mnt": 1,
                    "/proc/self/ns/mnt": 2,
                    "/proc/1/ns/user": 3,
                    "/proc/self/ns/user": 3,
                }[path]
            ),
        ),
    )
    assert ops.environment()["machine_sha256"] == hashlib.sha256(machine_id).hexdigest()
