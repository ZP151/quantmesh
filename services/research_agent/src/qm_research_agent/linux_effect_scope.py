"""Fail-closed aggregate containment for one Linux advisory effect.

Effect scopes are sibling leaves of the systemd-provided ``controller``
subgroup, below the empty delegated service cgroup. This module is Linux-only
and uses only the standard library for cgroup operations.
"""

from __future__ import annotations

import ctypes
import os
import re
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass

from quantmesh.research.jobs import RunBudget

CGROUP_ROOT = "/sys/fs/cgroup"
CGROUP2_SUPER_MAGIC = 0x63677270
_ALLOWED_UNIT = re.compile(
    r"\A(?:quantmesh-research-advisory|quantmesh-advisory-qa-[0-9a-f]{32})\.service\Z"
)
_SAFE_COMPONENT = re.compile(r"\A[A-Za-z0-9_.:@\\x-]+\Z")
_CONTROLLERS = frozenset({"cpu", "memory", "pids"})
_LIMIT_FILES = ("memory.max", "memory.swap.max", "cpu.max", "pids.max")
_MAX_MEMBER_BYTES = 8192
_CLOSE_TIMEOUT_SECONDS = 5.0
_CLOSE_RETRIES = 2


class EffectScopeRejected(RuntimeError):
    """A fixed, sanitized failure at the Linux effect-containment boundary."""

    def __init__(self):
        super().__init__("effect scope unavailable")


def _reject() -> EffectScopeRejected:
    return EffectScopeRejected()


def _validate_unit(unit: str) -> None:
    if not isinstance(unit, str) or not _ALLOWED_UNIT.fullmatch(unit):
        raise _reject()


def _validate_budget(budget: RunBudget) -> None:
    if (
        not isinstance(budget, RunBudget)
        or isinstance(budget.memory_mib, bool)
        or not 1 <= budget.memory_mib <= 2048
        or isinstance(budget.cpu_limit, bool)
        or budget.cpu_limit != 1.0
    ):
        raise _reject()


def _safe_group_path(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise _reject()
    parts = tuple(path[1:].split("/"))
    if any(part in ("", ".", "..") or not _SAFE_COMPONENT.fullmatch(part) for part in parts):
        raise _reject()
    return parts


def _validate_manager_properties(unit: str, properties: dict[str, str], current_pid: int) -> str:
    _validate_unit(unit)
    try:
        delegate_values = properties["DelegateControllers"].split()
        valid = (
            properties["MainPID"] == str(current_pid)
            and properties["KillMode"] == "control-group"
            and properties["Delegate"] == "yes"
            and set(delegate_values) == _CONTROLLERS
            and len(delegate_values) == len(_CONTROLLERS)
            and properties["DelegateSubgroup"] == "controller"
        )
        control_group = properties["ControlGroup"]
    except (AttributeError, KeyError, TypeError):
        raise _reject() from None
    if not valid:
        raise _reject()
    _safe_group_path(control_group)
    return control_group


def _parse_unified_cgroup(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) > 16384:
        raise _reject()
    rows = [line.split(":", 2) for line in raw.splitlines()]
    matches = [parts[2] for parts in rows if len(parts) == 3 and parts[0] == "0" and parts[1] == ""]
    if len(matches) != 1:
        raise _reject()
    path = matches[0]
    _safe_group_path(path)
    return path


def _is_cgroup2_magic(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == CGROUP2_SUPER_MAGIC


def _parse_names(raw: str) -> set[str]:
    if not isinstance(raw, str) or len(raw) > _MAX_MEMBER_BYTES:
        raise _reject()
    names = raw.split()
    if any(not re.fullmatch(r"[a-z_]+", name) for name in names):
        raise _reject()
    return set(names)


def _require_controllers(raw: str) -> set[str]:
    available = _parse_names(raw)
    if not _CONTROLLERS <= available:
        raise _reject()
    return available


def _require_empty_delegated_root(raw_procs: str) -> None:
    if not isinstance(raw_procs, str) or raw_procs.strip():
        raise _reject()


def _read_integer(raw: str) -> int:
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]+", raw.strip()):
        raise _reject()
    try:
        return int(raw.strip())
    except ValueError:
        raise _reject() from None


def _verify_scope_limits(values: dict[str, str], budget: RunBudget) -> None:
    _validate_budget(budget)
    try:
        cpu = values["cpu.max"].split()
        valid = (
            _read_integer(values["memory.max"]) == budget.memory_mib * 1024**2
            and _read_integer(values["memory.swap.max"]) == 0
            and cpu == ["100000", "100000"]
            and _read_integer(values["pids.max"]) == 128
        )
    except (KeyError, AttributeError, TypeError):
        raise _reject() from None
    if not valid:
        raise _reject()


def _run_systemctl(unit: str) -> dict[str, str]:
    _validate_unit(unit)
    properties = "MainPID,KillMode,Delegate,DelegateControllers,DelegateSubgroup,ControlGroup"
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "show", "--no-pager", f"--property={properties}", unit],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=2.0,
            check=False,
            close_fds=True,
            env={"LANG": "C", "PATH": "/usr/bin:/bin"},
        )
        if (
            result.returncode != 0
            or len(result.stdout) > _MAX_MEMBER_BYTES
            or len(result.stderr) > _MAX_MEMBER_BYTES
        ):
            raise _reject()
        text = result.stdout.decode("ascii")
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise _reject() from None
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if (
            not separator
            or key in parsed
            or key
            not in {
                "MainPID",
                "KillMode",
                "Delegate",
                "DelegateControllers",
                "DelegateSubgroup",
                "ControlGroup",
            }
        ):
            raise _reject()
        parsed[key] = value
    return parsed


def _statfs_type(directory_fd: int) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    fstatfs = libc.fstatfs
    fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
    fstatfs.restype = ctypes.c_int
    raw = ctypes.create_string_buffer(256)
    if fstatfs(directory_fd, raw) != 0:
        raise _reject()
    return int(ctypes.cast(raw, ctypes.POINTER(ctypes.c_long))[0])


def _open_directory(path: str, *, parent_fd: int | None = None) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = None
    try:
        fd = os.open(path, flags) if parent_fd is None else os.open(path, flags, dir_fd=parent_fd)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            os.close(fd)
            fd = None
            raise _reject()
        return fd
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise _reject() from None


def _open_absolute_directory(path: str) -> tuple[list[int], list[str]]:
    if not isinstance(path, str) or not path.startswith("/") or ".." in path.split("/"):
        raise _reject()
    components = [part for part in path.split("/") if part]
    descriptors = []
    try:
        current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(current)
        for component in components:
            following = _open_directory(component, parent_fd=current)
            info = os.fstat(following)
            named = os.stat(component, dir_fd=current, follow_symlinks=False)
            if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                os.close(following)
                raise _reject()
            descriptors.append(following)
            current = following
        return descriptors, components
    except BaseException as exc:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise _reject() from None
        raise


def _get_delegate_xattr(directory_fd: int) -> bytes:
    try:
        return os.getxattr(directory_fd, "user.delegate")
    except OSError:
        raise _reject() from None


@dataclass
class _HeldPath:
    descriptors: list[int]
    names: list[str]

    @property
    def fd(self) -> int:
        return self.descriptors[-1]

    @property
    def parent_fd(self) -> int:
        return self.descriptors[-2]

    @property
    def name(self) -> str:
        return self.names[-1]

    @property
    def identity(self) -> tuple[int, int]:
        result = os.fstat(self.fd)
        return result.st_dev, result.st_ino

    def close(self) -> None:
        for descriptor in reversed(self.descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.descriptors.clear()


def _open_beneath(
    root_fd: int,
    components: tuple[str, ...],
    *,
    held_descriptors: list[int] | None = None,
    held_names: list[str] | None = None,
) -> _HeldPath:
    descriptors = [root_fd] if held_descriptors is None else list(held_descriptors)
    names = [] if held_names is None else list(held_names)
    try:
        for component in components:
            parent_fd = descriptors[-1]
            fd = _open_directory(component, parent_fd=parent_fd)
            before = os.fstat(fd)
            named = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
                os.close(fd)
                raise _reject()
            descriptors.append(fd)
            names.append(component)
        return _HeldPath(descriptors, names)
    except BaseException as exc:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise _reject() from None
        raise


def _read_member(directory_fd: int, name: str, maximum: int = _MAX_MEMBER_BYTES) -> str:
    if (
        name
        not in {
            "cgroup.controllers",
            "cgroup.subtree_control",
            *_LIMIT_FILES,
            "cgroup.procs",
            "cgroup.events",
            "cgroup.kill",
            "memory.events",
            "cpu.stat",
            "pids.current",
        }
        or not 1 <= maximum <= _MAX_MEMBER_BYTES
    ):
        raise _reject()
    fd = None
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise _reject()
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(data) > maximum
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise _reject()
        return data.decode("ascii")
    except (OSError, UnicodeError):
        raise _reject() from None
    finally:
        if fd is not None:
            os.close(fd)


def _write_member(directory_fd: int, name: str, value: str) -> None:
    if name not in {*_LIMIT_FILES, "cgroup.subtree_control", "cgroup.procs", "cgroup.kill"}:
        raise _reject()
    data = value.encode("ascii")
    if not data or len(data) > 256:
        raise _reject()
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
        before = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (
            named.st_dev,
            named.st_ino,
        ):
            raise _reject()
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise _reject()
    except OSError:
        raise _reject() from None
    finally:
        if fd is not None:
            os.close(fd)


def _require_writable_kill_file(directory_fd: int) -> None:
    fd = None
    try:
        fd = os.open("cgroup.kill", os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
        opened = os.fstat(fd)
        named = os.stat("cgroup.kill", dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            named.st_dev,
            named.st_ino,
        ):
            raise _reject()
    except OSError:
        raise _reject() from None
    finally:
        if fd is not None:
            os.close(fd)


def _enable_controllers(root_fd: int) -> None:
    # DelegateSubgroup keeps the service process in the separate controller
    # child, so this delegated service root must be empty before domain
    # controllers can be distributed to effect children.
    _require_empty_delegated_root(_read_member(root_fd, "cgroup.procs"))
    available = _require_controllers(_read_member(root_fd, "cgroup.controllers"))
    enabled = _parse_names(_read_member(root_fd, "cgroup.subtree_control"))
    missing = sorted(_CONTROLLERS - enabled)
    if not set(missing) <= available:
        raise _reject()
    if missing:
        _write_member(root_fd, "cgroup.subtree_control", " ".join("+" + name for name in missing))
    if not _CONTROLLERS <= _parse_names(_read_member(root_fd, "cgroup.subtree_control")):
        raise _reject()


def _read_proc_file(pid: int, filename: str, maximum: int = 16384) -> str:
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or filename not in {"stat", "cgroup"}
    ):
        raise _reject()
    fd = None
    try:
        fd = os.open(
            f"/proc/{pid}/{filename}",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, "O_NONBLOCK", 0),
        )
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(4096, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > maximum:
            raise _reject()
        return data.decode("ascii")
    except (OSError, UnicodeError):
        raise _reject() from None
    finally:
        if fd is not None:
            os.close(fd)


def _parse_proc_stat(raw: str) -> tuple[int, int]:
    if not isinstance(raw, str) or len(raw) > 16384:
        raise _reject()
    close_paren = raw.rfind(")")
    if close_paren < 0:
        raise _reject()
    fields = raw[close_paren + 1 :].split()
    try:
        parent_pid = int(fields[1])
        start_time = int(fields[19])
    except (IndexError, ValueError):
        raise _reject() from None
    if parent_pid <= 0 or start_time <= 0:
        raise _reject()
    return parent_pid, start_time


def _validate_owned_child_identity(
    before: tuple[int, int], after: tuple[int, int], current_pid: int
) -> int:
    parent_before, start_before = before
    parent_after, start_after = after
    if (
        parent_before != current_pid
        or parent_after != current_pid
        or start_before <= 0
        or start_after != start_before
    ):
        raise _reject()
    return start_before


def _process_identity(pid: int) -> tuple[int, int]:
    return _parse_proc_stat(_read_proc_file(pid, "stat"))


@dataclass
class _Scope:
    held: _HeldPath
    name: str
    cgroup_path: str
    limits: dict[str, str]
    attached_pid: int | None = None
    attached_start_time: int | None = None
    pidfd: int | None = None
    closed: bool = False
    close_failed: bool = False


class _LinuxEffectCgroup:
    def __init__(self, unit: str, budget: RunBudget):
        _validate_unit(unit)
        _validate_budget(budget)
        if not sys_platform_linux():
            raise _reject()
        properties = _run_systemctl(unit)
        control_group = _validate_manager_properties(unit, properties, os.getpid())
        expected_manager_group = control_group + "/controller"
        if _parse_unified_cgroup(_read_proc_file(os.getpid(), "cgroup")) != expected_manager_group:
            raise _reject()

        root_descriptors, root_names = _open_absolute_directory(CGROUP_ROOT)
        root_fd = root_descriptors[-1]
        try:
            if not _is_cgroup2_magic(_statfs_type(root_fd)):
                raise _reject()
        except BaseException:
            for descriptor in reversed(root_descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise
        try:
            held_root = _open_beneath(
                root_fd,
                _safe_group_path(control_group),
                held_descriptors=root_descriptors,
                held_names=root_names,
            )
            try:
                if _get_delegate_xattr(held_root.fd) != b"1":
                    raise _reject()
                _enable_controllers(held_root.fd)
                self._root = held_root
            except BaseException:
                held_root.close()
                raise
        except BaseException:
            # _open_beneath owns root_fd after it has been called.
            raise
        self._budget = budget
        self._close_failed = False
        try:
            self._scope = self._create_scope(control_group)
        except BaseException:
            self._root.close()
            raise

    def _create_scope(self, delegated_path: str) -> _Scope:
        _ensure_held_name(self._root)
        name = "effect-" + uuid.uuid4().hex
        held = _create_scope_directory(self._root, name)
        limits = {
            "memory.max": str(self._budget.memory_mib * 1024**2),
            "memory.swap.max": "0",
            "cpu.max": "100000 100000",
            "pids.max": "128",
        }
        try:
            _require_writable_kill_file(held.fd)
            for filename, value in limits.items():
                _write_member(held.fd, filename, value)
            readback = {
                filename: _read_member(held.fd, filename).strip() for filename in _LIMIT_FILES
            }
            _verify_scope_limits(readback, self._budget)
        except BaseException:
            # The scope is exact and newly created; it is safe to remove only
            # after confirming it is empty. No recursive cleanup is attempted.
            try:
                _remove_empty_scope(held)
            finally:
                os.close(held.fd)
            raise
        return _Scope(held, name, delegated_path + "/" + name, readback)

    def attach(self, process: subprocess.Popen) -> None:
        scope = self._scope
        if (
            scope.closed
            or scope.close_failed
            or scope.attached_pid is not None
            or not isinstance(process, subprocess.Popen)
            or process.pid is None
            or process.pid <= 0
            or process.poll() is not None
        ):
            raise _reject()
        pid = process.pid
        pidfd = None
        try:
            if not hasattr(os, "pidfd_open"):
                raise _reject()
            pidfd = os.pidfd_open(pid, 0)
            identity_before = _process_identity(pid)
            parent_before, start_before = identity_before
            if parent_before != os.getpid():
                raise _reject()
            scope.attached_pid = pid
            scope.attached_start_time = start_before
            scope.pidfd = pidfd
            _ensure_held_name(scope.held)
            _write_member(scope.held.fd, "cgroup.procs", str(pid))
            identity_after = _process_identity(pid)
            actual_group = _parse_unified_cgroup(_read_proc_file(pid, "cgroup"))
            if (
                process.poll() is not None
                or _validate_owned_child_identity(identity_before, identity_after, os.getpid())
                != start_before
                or actual_group != scope.cgroup_path
            ):
                raise _reject()
        except BaseException:
            # Caller cleanup can kill only this unique child scope.
            if pidfd is not None and scope.pidfd is None:
                os.close(pidfd)
            raise _reject() from None

    def snapshot(self) -> dict:
        scope = self._scope
        if scope.closed or scope.close_failed:
            raise _reject()
        _ensure_held_name(scope.held)
        return {
            "scope": scope.name,
            "identity": {"device": scope.held.identity[0], "inode": scope.held.identity[1]},
            "caps": dict(scope.limits),
            "memory_events": _parse_counter_file(_read_member(scope.held.fd, "memory.events")),
            "cpu_stat": _parse_counter_file(_read_member(scope.held.fd, "cpu.stat")),
            "pids_current": _read_integer(_read_member(scope.held.fd, "pids.current")),
        }

    def close(self) -> None:
        scope = self._scope
        if scope.closed:
            return
        if self._close_failed or scope.close_failed:
            raise _reject()
        for attempt in range(_CLOSE_RETRIES):
            try:
                self._close_once()
                return
            except BaseException:
                if attempt + 1 < _CLOSE_RETRIES:
                    continue
                scope.close_failed = True
                self._close_failed = True
                self._release_owned_fds()
                raise _reject() from None

    def _close_once(self) -> None:
        scope = self._scope
        _ensure_held_name(scope.held)
        if scope.attached_pid is not None:
            _write_member(scope.held.fd, "cgroup.kill", "1")
        deadline = time.monotonic() + _CLOSE_TIMEOUT_SECONDS
        while True:
            events = _parse_key_values(_read_member(scope.held.fd, "cgroup.events"))
            if events.get("populated") == 0:
                break
            if time.monotonic() >= deadline:
                raise _reject()
            time.sleep(0.05)
        _remove_empty_scope(scope.held)
        scope.closed = True
        self._release_owned_fds()

    def _release_owned_fds(self) -> None:
        scope = self._scope
        if scope.pidfd is not None:
            try:
                os.close(scope.pidfd)
            except OSError:
                pass
            scope.pidfd = None
        if scope.held.descriptors:
            leaf_fd = scope.held.descriptors[-1]
            if leaf_fd not in self._root.descriptors:
                try:
                    os.close(leaf_fd)
                except OSError:
                    pass
            scope.held.descriptors.clear()
        self._root.close()


def _parse_key_values(raw: str) -> dict[str, int]:
    if not isinstance(raw, str) or len(raw) > _MAX_MEMBER_BYTES:
        raise _reject()
    result = {}
    for line in raw.splitlines():
        parts = line.split()
        if (
            len(parts) != 2
            or parts[0] in result
            or not re.fullmatch(r"[a-z_]+(?:\.[a-z_]+)*", parts[0])
        ):
            raise _reject()
        result[parts[0]] = _read_integer(parts[1])
    return result


def _parse_counter_file(raw: str) -> dict[str, int]:
    values = _parse_key_values(raw)
    if len(values) > 32 or any(not re.fullmatch(r"[a-z_]+(?:\.[a-z_]+)*", key) for key in values):
        raise _reject()
    return values


def _ensure_held_name(held: _HeldPath) -> None:
    try:
        descriptor = os.fstat(held.fd)
        named = os.stat(held.name, dir_fd=held.parent_fd, follow_symlinks=False)
    except OSError:
        raise _reject() from None
    if not stat.S_ISDIR(descriptor.st_mode) or (descriptor.st_dev, descriptor.st_ino) != (
        named.st_dev,
        named.st_ino,
    ):
        raise _reject()


def _remove_empty_scope(held: _HeldPath) -> None:
    _ensure_held_name(held)
    try:
        os.rmdir(held.name, dir_fd=held.parent_fd)
    except OSError:
        raise _reject() from None


def _remove_created_empty_directory(parent_fd: int, name: str, identity: tuple[int, int]) -> None:
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != identity:
            raise _reject()
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        raise _reject() from None


def _create_scope_directory(root: _HeldPath, name: str) -> _HeldPath:
    if not re.fullmatch(r"effect-[0-9a-f]{32}", name):
        raise _reject()
    parent_fd = root.fd
    created = False
    identity = None
    child_fd = None
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        created = True
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode):
            raise _reject()
        identity = (named.st_dev, named.st_ino)
        child_fd = _open_directory(name, parent_fd=parent_fd)
        opened = os.fstat(child_fd)
        named_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != identity or (
            named_after.st_dev,
            named_after.st_ino,
        ) != identity:
            raise _reject()
        held = _HeldPath([*root.descriptors, child_fd], [*root.names, name])
        child_fd = None
        return held
    except BaseException as exc:
        cleanup_failed = False
        if created and identity is not None:
            try:
                _remove_created_empty_directory(parent_fd, name, identity)
            except EffectScopeRejected:
                cleanup_failed = True
        if child_fd is not None:
            try:
                os.close(child_fd)
            except OSError:
                pass
        if cleanup_failed or isinstance(exc, OSError):
            raise _reject() from None
        raise


def sys_platform_linux() -> bool:
    return os.name == "posix" and os.uname().sysname == "Linux"


class EffectScope:
    """Own one aggregate effect cgroup below a verified delegated subgroup."""

    def __init__(self, unit: str, budget: RunBudget):
        _validate_unit(unit)
        _validate_budget(budget)
        self.unit = unit
        self.budget = budget
        self._controller = _LinuxEffectCgroup(unit, budget)
        self._closed = False

    def attach(self, process: subprocess.Popen) -> None:
        if (
            self._closed
            or not isinstance(process, subprocess.Popen)
            or process.pid is None
            or process.pid <= 0
            or process.poll() is not None
        ):
            raise _reject()
        self._controller.attach(process)

    def snapshot(self) -> dict:
        if self._closed:
            raise _reject()
        return self._controller.snapshot()

    def close(self) -> None:
        if self._closed:
            return
        self._controller.close()
        self._closed = True

    def __enter__(self) -> EffectScope:
        if self._closed:
            raise _reject()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
