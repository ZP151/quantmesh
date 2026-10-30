"""Default-off private history profile; kernel facts are not caller booleans.

The trusted controller owns full-content/generation/no-writer proofs. This module
checks its root-owned admission and current actor/unit/tmpfs/guard identities.
It creates no mount, process, database, credentials or operational permission.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

MIB = 1024 * 1024
MAX_ADMISSION = 32768
APPROVAL = "b737f446acfc4c5e1479ec05083c7c46467f30648057fda66f431253f0ea70e1"
DESIGN = "a2119e8331b869f33a94fbaf509ce3e5ea8dc51df29ea95cef67905feaacb746"
KEY_SHA = "7644c851644b387fce7a8b173b89c74e43fcd91e422ac9a14dd9d69aa3ed1ecd"


def _nonzero(value):
    if value == "0" * 64:
        raise ValueError()
    return value


Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$"), AfterValidator(_nonzero)]
Positive = Annotated[int, Field(gt=0)]
Nonnegative = Annotated[int, Field(ge=0)]


class HistoryRamAuxRejected(ValueError):
    def __init__(self):
        super().__init__("history_ram_aux_unavailable")


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _Actor(_Record):
    pid: Positive
    start_ticks: Positive
    uid: Positive
    cgroup: str


class _Unit(_Record):
    cgroup: str
    receipt_sha256: Digest


class _Aux(_Record):
    path: str
    mount_id: Positive
    device: Nonnegative
    inode: Positive


class _Guard(_Actor):
    receipt_sha256: Digest


class _InputFile(_Record):
    path: str
    device: Nonnegative
    inode: Positive
    byte_length: Nonnegative
    mtime_ns: Positive
    ctime_ns: Positive
    sha256: Digest


class _Snapshot(_Record):
    root: str
    files: Annotated[tuple[_InputFile, ...], Field(strict=False, min_length=2, max_length=8)]
    content_manifest_sha256: Digest
    generation_receipt_sha256: Digest
    no_writer_receipt_sha256: Digest
    dependency_receipt_sha256: Digest
    cut: Literal["2026-10-23T23:44:01Z"]
    selected_keys: Literal[111]
    fields: Literal[17]
    key_sha256: Literal[KEY_SHA]

    @field_validator("selected_keys", "fields", mode="before")
    @classmethod
    def exact_integer(cls, value):
        if type(value) is not int:
            raise ValueError()
        return value


class _Runtime(_Record):
    python_version: str
    duckdb_version: Literal["1.5.5"]
    python_executable_sha256: Digest
    duckdb_module_sha256: Digest
    duckdb_extension_sha256: Digest
    buffer_source_sha256: Digest
    profile_source_sha256: Digest
    catalog_sha256: Digest


class _Admission(_Record):
    schema_id: Literal["qm.history-ram-aux.admission.v1"]
    profile: Literal["isolated-ram-aux-v1"]
    approval_sha256: Literal[APPROVAL]
    design_sha256: Literal[DESIGN]
    authority_sha256: Literal["c8b1be862f4f8d939c007f42bc2a819811b9cfb567d45eca96ed395f376b4ab0"]
    nonce: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
    issued_monotonic: Annotated[float, Field(allow_inf_nan=False, ge=0)]
    expires_monotonic: Annotated[float, Field(allow_inf_nan=False, gt=0)]
    actor: _Actor
    unit: _Unit
    aux: _Aux
    guard: _Guard
    snapshot: _Snapshot
    runtime: _Runtime
    controller_receipt_sha256: Digest

    @model_validator(mode="after")
    def bound(self):
        if self.guard.pid == self.actor.pid or self.guard.uid != self.actor.uid:
            raise ValueError()
        if not 0 < self.expires_monotonic - self.issued_monotonic <= 540:
            raise ValueError()
        if not all(
            _valid_cgroup(c) for c in (self.unit.cgroup, self.actor.cgroup, self.guard.cgroup)
        ):
            raise ValueError()
        names = [f.path for f in self.snapshot.files]
        if len(names) != len(set(names)) or not {
            "live/updates.duckdb",
            "live/updates.duckdb.wal",
        }.issubset(names):
            raise ValueError()
        for name in names:
            if not re.fullmatch(r"live/updates\.duckdb(?:\.wal(?:\.[a-zA-Z0-9_-]+)?)?", name):
                raise ValueError()
        raw = _canonical([f.model_dump() for f in self.snapshot.files])
        if hashlib.sha256(raw).hexdigest() != self.snapshot.content_manifest_sha256:
            raise ValueError()
        return self


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _decode_admission(raw: bytes) -> _Admission:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    try:
        if type(raw) is not bytes or len(raw) > MAX_ADMISSION:
            raise ValueError()
        value = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        return _Admission.model_validate(value)
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise HistoryRamAuxRejected() from None


def _mount_entry(text: str, target: str) -> dict:
    matches = []
    for line in text.splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        a, b = left.split(), right.split()
        if len(a) < 6 or len(b) < 3:
            continue
        path = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), a[4])
        if path != target:
            continue
        options = set(a[5].split(",")) | set(b[2].split(","))
        if (
            a[3] != "/"
            or b[0] != "tmpfs"
            or not {"rw", "nosuid", "nodev", "noexec", "noswap"}.issubset(options)
        ):
            raise HistoryRamAuxRejected()
        sizes = [o[5:] for o in options if o.startswith("size=")]
        if len(sizes) != 1 or sizes[0] not in {"262144k", "268435456", "256m"}:
            raise HistoryRamAuxRejected()
        matches.append(dict(id=int(a[0]), device=a[2], path=path))
    if len(matches) != 1:
        raise HistoryRamAuxRejected()
    return matches[0]


def _whole_read_lock(text: str, pid: int, major: int, minor: int, inode: int) -> bool:
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 8 or fields[1:4] != ["POSIX", "ADVISORY", "READ"]:
            continue
        try:
            device = fields[5].split(":")
            if (
                int(fields[4]) == pid
                and (int(device[0], 16), int(device[1], 16), int(device[2]))
                == (major, minor, inode)
                and fields[6:] == ["0", "EOF"]
            ):
                return True
        except (ValueError, IndexError):
            continue
    return False


def _valid_cgroup(value):
    return bool(
        re.fullmatch(r"/[A-Za-z0-9_.@:-]+(?:/[A-Za-z0-9_.@:-]+)*", value)
    ) and ".." not in value.split("/")


def _read_text(path, maximum=1024 * 1024):
    with open(path, "rb") as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise HistoryRamAuxRejected()
    return raw.decode("utf-8", errors="strict")


def _plain_path(path):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise HistoryRamAuxRejected()
    for current in (path, *path.parents):
        if stat.S_ISLNK(current.lstat().st_mode):
            raise HistoryRamAuxRejected()
    return path


def _hash_readonly(path):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size > 256 * MIB
        or not os.statvfs(path).f_flag & os.ST_RDONLY
    ):
        raise HistoryRamAuxRejected()
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if before != path.stat():
        raise HistoryRamAuxRejected()
    return digest


class _Kernel:
    """Production OS adapter; startup accepts no caller-supplied adapter."""

    def platform(self):
        return sys.platform

    def now(self):
        return time.monotonic()

    def current(self):
        return (os.getpid(), os.getuid(), os.geteuid())

    def process(self, pid):
        base = Path("/proc") / str(pid)
        tail = _read_text(base / "stat", 8192).rpartition(") ")[2].split()
        if len(tail) < 20 or tail[0] in {"Z", "X", "x"}:
            raise HistoryRamAuxRejected()
        match = re.search(
            r"^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$",
            _read_text(base / "status", 65536),
            re.MULTILINE,
        )
        if match is None or len(set(match.groups())) != 1:
            raise HistoryRamAuxRejected()
        groups = _read_text(base / "cgroup", 8192).splitlines()
        if len(groups) != 1 or not groups[0].startswith("0::"):
            raise HistoryRamAuxRejected()
        return dict(
            start_ticks=int(tail[19]),
            uid=int(match[1]),
            cgroup=groups[0][3:],
            oom_score_adj=int(_read_text(base / "oom_score_adj", 32)),
        )

    def unit(self, cgroup):
        base = Path("/sys/fs/cgroup") / cgroup.lstrip("/")
        return {
            name: _read_text(base / name, 128).strip()
            for name in ("memory.max", "memory.swap.max", "memory.oom.group", "cpu.max")
        }

    def available(self):
        match = re.search(
            r"^MemAvailable:\s+(\d+) kB$", _read_text("/proc/meminfo", 65536), re.MULTILINE
        )
        if match is None:
            raise HistoryRamAuxRejected()
        return int(match[1]) * 1024

    def aux(self, name):
        path = _plain_path(name)
        mount = _mount_entry(_read_text("/proc/self/mountinfo"), str(path))
        info, vfs = path.stat(), os.statvfs(path)
        if not stat.S_ISDIR(info.st_mode) or vfs.f_flag & os.ST_RDONLY:
            raise HistoryRamAuxRejected()
        with os.scandir(path) as entries:
            empty = next(entries, None) is None
        return dict(
            path=str(path),
            mount_id=mount["id"],
            device=info.st_dev,
            inode=info.st_ino,
            uid=info.st_uid,
            mode=stat.S_IMODE(info.st_mode),
            bytes=vfs.f_blocks * vfs.f_frsize,
            empty=empty,
        )

    def file(self, root, name):
        path = _plain_path(root / name)
        info = path.stat()
        return dict(
            path=name,
            device=info.st_dev,
            inode=info.st_ino,
            byte_length=info.st_size,
            mtime_ns=info.st_mtime_ns,
            ctime_ns=info.st_ctime_ns,
            regular=stat.S_ISREG(info.st_mode),
            readonly=bool(os.statvfs(path).f_flag & os.ST_RDONLY),
        )

    def lock(self, pid, device, inode):
        return _whole_read_lock(
            _read_text("/proc/locks"), pid, os.major(device), os.minor(device), inode
        )

    def runtime(self):
        import _duckdb
        import duckdb

        from quantmesh.live import buffer

        return dict(
            python_version=platform.python_version(),
            duckdb_version=duckdb.__version__,
            python_executable_sha256=_hash_readonly(sys.executable),
            duckdb_module_sha256=_hash_readonly(duckdb.__file__),
            duckdb_extension_sha256=_hash_readonly(_duckdb.__file__),
            buffer_source_sha256=_hash_readonly(buffer.__file__),
            profile_source_sha256=_hash_readonly(__file__),
        )


def _check_live(a: _Admission, root: Path, kernel: _Kernel, *, initial=False):
    try:
        if kernel.platform() != "linux" or kernel.current() != (
            a.actor.pid,
            a.actor.uid,
            a.actor.uid,
        ):
            raise ValueError()
        now = kernel.now()
        if not a.issued_monotonic <= now < a.expires_monotonic:
            raise ValueError()
        root = _plain_path(root)
        aux = _plain_path(a.aux.path)
        if (
            root != Path(a.snapshot.root)
            or root == aux
            or root in aux.parents
            or aux in root.parents
        ):
            raise ValueError()
        for person in (a.actor, a.guard):
            fact = kernel.process(person.pid)
            if fact != dict(
                start_ticks=person.start_ticks,
                uid=person.uid,
                cgroup=person.cgroup,
                oom_score_adj=1000,
            ):
                raise ValueError()
        leaf = a.actor.cgroup
        if a.guard.cgroup != leaf or not (
            leaf == a.unit.cgroup or leaf.startswith(a.unit.cgroup + "/")
        ):
            raise ValueError()
        limits = kernel.unit(a.unit.cgroup)
        if (limits["memory.max"], limits["memory.swap.max"], limits["memory.oom.group"]) != (
            str(2 * 1024**3),
            "0",
            "1",
        ):
            raise ValueError()
        cpu = limits["cpu.max"].split()
        if (
            len(cpu) != 2
            or not all(x.isdecimal() for x in cpu)
            or int(cpu[0]) <= 0
            or int(cpu[0]) * 2 != int(cpu[1])
        ):
            raise ValueError()
        if kernel.available() < (4 if initial else 2) * 1024**3:
            raise ValueError()
        observed_aux = kernel.aux(a.aux.path)
        expected_aux = a.aux.model_dump() | dict(uid=a.actor.uid, mode=0o700, bytes=256 * MIB)
        if any(observed_aux.get(k) != v for k, v in expected_aux.items()) or (
            initial and observed_aux.get("empty") is not True
        ):
            raise ValueError()
        for item in a.snapshot.files:
            fact = kernel.file(root, item.path)
            expected = item.model_dump(exclude={"sha256"}) | dict(regular=True, readonly=True)
            if fact != expected:
                raise ValueError()
        db = next(f for f in a.snapshot.files if f.path == "live/updates.duckdb")
        if kernel.lock(a.guard.pid, db.device, db.inode) is not True:
            raise ValueError()
        if kernel.runtime() != a.runtime.model_dump(exclude={"catalog_sha256"}):
            raise ValueError()
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise HistoryRamAuxRejected() from None


def _get_fd_flags(fd):
    import fcntl

    return fcntl.fcntl(fd, fcntl.F_GETFL)


def _validate_fd_stat(info, flags):
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o444
        or not 0 < info.st_size <= MAX_ADMISSION
        or flags & getattr(os, "O_ACCMODE", 3) != os.O_RDONLY
        or flags & getattr(os, "O_PATH", 0)
    ):
        raise HistoryRamAuxRejected()
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_nlink,
        flags,
    )


def _fd_stamp(fd):
    return _validate_fd_stat(os.fstat(fd), _get_fd_flags(fd))


def _read_admission_fd(fd):
    before = _fd_stamp(fd)
    raw = os.pread(fd, MAX_ADMISSION + 1, 0)
    if before != _fd_stamp(fd) or len(raw) != before[2]:
        raise HistoryRamAuxRejected()
    return raw, before


_CAPABILITY_KEY = object()


class _HistoryRamAuxCapability:
    __slots__ = ("_admission", "_root", "_fd", "_stamp", "_kernel", "_used", "_closed", "_lock")

    def __init__(self, key, admission, root, fd, stamp, kernel):
        if key is not _CAPABILITY_KEY:
            raise HistoryRamAuxRejected()
        self._admission, self._root, self._fd, self._stamp = admission, root, fd, stamp
        self._kernel, self._used, self._closed = kernel, False, False
        self._lock = threading.RLock()

    def check(self):
        with self._lock:
            try:
                if self._closed or _fd_stamp(self._fd) != self._stamp:
                    raise HistoryRamAuxRejected()
                _check_live(self._admission, self._root, self._kernel)
            except (OSError, ValueError, TypeError):
                self._closed = True
                raise HistoryRamAuxRejected() from None

    def _claim(self, root):
        with self._lock:
            if self._used or self._closed or Path(root) != self._root:
                raise HistoryRamAuxRejected()
            self._used = True
            try:
                self.check()
            except BaseException:
                self.close()
                raise
            return {
                "memory_limit": "1GiB",
                "threads": 1,
                "max_temp_directory_size": "256MiB",
                "temp_directory": self._admission.aux.path,
            }

    def _scope(
        self,
        *,
        venue,
        instrument,
        kinds,
        start,
        end,
        data_time_start,
        data_time_end,
        through_local_seq,
        limit,
        tail,
    ):
        cut = datetime(2026, 10, 23, 23, 44, 1, tzinfo=UTC)
        if (
            venue != "hyperliquid"
            or instrument != "BTC"
            or kinds != {"candle", "status"}
            or start != cut - timedelta(days=1)
            or data_time_start != start
            or end != cut
            or data_time_end != cut
            or through_local_seq is not None
            or type(limit) is not int
            or limit != 10000
            or tail is not True
        ):
            raise HistoryRamAuxRejected()

    def close(self):
        with self._lock:
            self._closed = True
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None


def admit_history_ram_aux(
    root: Path, *, admission_fd: int, expected_sha256: str
) -> _HistoryRamAuxCapability:
    """Trusted startup only: expected SHA comes from independent root receipt.

    Caller opens the fixed root-owned admission artifact without following links
    and validates the separate root expected-SHA receipt's THIS run bindings.
    Source duplicates the passed FD; it never closes/advances the caller's FD.
    No HTTP/config booleans or externally supplied verifier enter this API.
    """
    owned = None
    try:
        kernel = _Kernel()
        if kernel.platform() != "linux" or type(admission_fd) is not int or admission_fd < 0:
            raise ValueError()
        if (
            type(expected_sha256) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or expected_sha256 == "0" * 64
        ):
            raise ValueError()
        owned = os.dup(admission_fd)
        os.set_inheritable(owned, False)
        raw, stamp = _read_admission_fd(owned)
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError()
        a = _decode_admission(raw)
        root = _plain_path(root)
        _check_live(a, root, kernel, initial=True)
        result = _HistoryRamAuxCapability(_CAPABILITY_KEY, a, root, owned, stamp, kernel)
        owned = None
        return result
    except (OSError, ValueError, TypeError, ImportError, AttributeError, RecursionError):
        raise HistoryRamAuxRejected() from None
    finally:
        if owned is not None:
            os.close(owned)
