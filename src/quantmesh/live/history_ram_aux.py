"""Default-off private history profile; kernel facts are not caller booleans.

The trusted controller owns full-content/generation/no-writer proofs. This module
checks its root-owned admission and current actor/unit/tmpfs/guard identities.
It creates no mount, process, database, credentials or operational permission.
"""

from __future__ import annotations

import errno
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


def _decode_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    if type(raw) is not bytes or len(raw) > MAX_ADMISSION:
        raise ValueError()
    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
    )


def _decode_admission(raw: bytes) -> _Admission:
    try:
        value = _decode_json(raw)
        if isinstance(value, dict) and value.get("schema_id") == "qm.history-ram-aux.admission.v2":
            return _AdmissionV2.model_validate(value)
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

    def boot(self):
        return _read_text("/proc/sys/kernel/random/boot_id", 128).strip()

    def open_parent(self, root, name):
        return _parent_open(root, name)

    def parent(self, root, name, fd):
        return _parent_fact(root, name, fd)

    def absent(self, fd, basename):
        return _absent_at(fd, basename)

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
    __slots__ = (
        "_admission",
        "_root",
        "_fd",
        "_stamp",
        "_kernel",
        "_used",
        "_closed",
        "_lock",
        "_evidence",
        "_reader",
    )

    def __init__(self, key, admission, root, fd, stamp, kernel, evidence=None):
        if key is not _CAPABILITY_KEY:
            raise HistoryRamAuxRejected()
        self._admission, self._root, self._fd, self._stamp = admission, root, fd, stamp
        self._kernel, self._used, self._closed = kernel, False, False
        self._lock = threading.RLock()
        self._evidence = evidence
        self._reader = None

    def _bind_reader(self, reader):
        # Only ABSENT owns additional lifetime evidence. Keep v1/PRESENT behavior.
        if self._evidence is None:
            return
        from quantmesh.live.buffer import LiveBuffer

        with self._lock:
            if (
                self._closed
                or not self._used
                or self._reader is not None
                or type(reader) is not LiveBuffer
                or reader._history_ram_aux is not self
                or reader._con is None
            ):
                raise HistoryRamAuxRejected()
            self._reader = reader

    def check(self):
        with self._lock:
            try:
                if self._closed or _fd_stamp(self._fd) != self._stamp:
                    raise HistoryRamAuxRejected()
                _check_live(self._admission, self._root, self._kernel)
                if self._evidence is not None:
                    self._evidence.check()
                return
            except (OSError, ValueError, TypeError):
                self._closed = True
                close_absent = self._evidence is not None
        # A replay can own the reader lock before taking this capability lock.
        # Never wait for reader.close while holding the capability lock.
        if close_absent:
            self.close()
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
        reader = None
        try:
            with self._lock:
                self._closed = True
                reader = self._reader
                self._close_evidence()
        finally:
            try:
                if reader is not None and not getattr(reader, "_closed", False):
                    reader.close()
            finally:
                # Detachment is not completion. A replay already holding the
                # reentrant reader lock must be able to finish close itself
                # while a monitor's close is waiting outside our lock.
                if reader is not None:
                    with self._lock:
                        if self._reader is reader and getattr(reader, "_closed", False):
                            self._reader = None

    def _close_evidence(self):
        try:
            if self._fd is not None:
                fd, self._fd = self._fd, None
                os.close(fd)
        finally:
            if self._evidence is not None:
                self._evidence.close()


def admit_history_ram_aux(
    root: Path,
    *,
    admission_fd: int,
    expected_sha256: str,
    checkpoint_fd: int | None = None,
    absence_fd: int | None = None,
    epoch_fd: int | None = None,
) -> _HistoryRamAuxCapability:
    """Trusted startup only: expected SHA comes from independent root receipt.

    Caller opens the fixed root-owned admission artifact without following links
    and validates the separate root expected-SHA receipt's THIS run bindings.
    Source duplicates the passed FD; it never closes/advances the caller's FD.
    No HTTP/config booleans or externally supplied verifier enter this API.
    """
    owned = None
    evidence = None
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
        evidence = _prepare_evidence(a, root, kernel, checkpoint_fd, absence_fd, epoch_fd)
        result = _HistoryRamAuxCapability(_CAPABILITY_KEY, a, root, owned, stamp, kernel, evidence)
        owned = None
        evidence = None
        return result
    except (OSError, ValueError, TypeError, ImportError, AttributeError, RecursionError):
        raise HistoryRamAuxRejected() from None
    finally:
        try:
            if owned is not None:
                os.close(owned)
        finally:
            if evidence is not None:
                evidence.close()


APPROVAL_V2 = "1462eae76d7c909e53cc94fc65dfc62ac05a5676f1a8dde95c1353976971730b"
DESIGN_V2 = "e46450c6469b0d05ce3f4d4cf2a7f2feb6b03477013615bb717bbd148624090b"
AUTHORITY_V2 = "281575d1d400ea7439ed5d1865b08e61f4349f5eaf3ace7778b821b020c93fc7"
FiniteTime = Annotated[float, Field(allow_inf_nan=False, ge=0)]
Boot = Annotated[str, Field(pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")]
Epoch = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class _DirectoryPin(_Record):
    path: Literal["live"]
    device: Nonnegative
    inode: Positive
    mount_id: Positive
    mtime_ns: Positive
    ctime_ns: Positive


class _PresentWal(_Record):
    presence: Literal["PRESENT"]
    file: _InputFile


class _AbsentWal(_Record):
    presence: Literal["ABSENT"]
    parent: _DirectoryPin
    basename: Literal["updates.duckdb.wal"]
    checkpoint_receipt_sha256: Digest
    absence_receipt_sha256: Digest
    epoch_receipt_sha256: Digest


class _SnapshotV2(_Record):
    root: str
    db: _InputFile
    wal: Annotated[_PresentWal | _AbsentWal, Field(discriminator="presence")]
    dependency_files: Annotated[tuple[_InputFile, ...], Field(strict=False, max_length=6)]
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

    @property
    def files(self):
        wal = (self.wal.file,) if isinstance(self.wal, _PresentWal) else ()
        return (self.db, *wal, *self.dependency_files)


class _AdmissionV2(_Admission):
    schema_id: Literal["qm.history-ram-aux.admission.v2"]
    profile: Literal["isolated-ram-aux-wal-state-v2"]
    approval_sha256: Literal[APPROVAL_V2]
    design_sha256: Literal[DESIGN_V2]
    authority_sha256: Literal[AUTHORITY_V2]
    snapshot: _SnapshotV2

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
        s = self.snapshot
        if s.db.path != "live/updates.duckdb":
            raise ValueError()
        if isinstance(s.wal, _PresentWal):
            if s.wal.file.path != "live/updates.duckdb.wal":
                raise ValueError()
        elif s.dependency_files:
            # A checkpointed ABSENT input cannot also need a recovery WAL.
            raise ValueError()
        names = [f.path for f in s.files]
        if len(names) != len(set(names)) or any(
            not re.fullmatch(r"live/updates\.duckdb\.wal\.[a-zA-Z0-9_-]+", f.path)
            for f in s.dependency_files
        ):
            raise ValueError()
        raw = _canonical(s.model_dump(mode="json", include={"db", "wal", "dependency_files"}))
        if hashlib.sha256(raw).hexdigest() != s.content_manifest_sha256:
            raise ValueError()
        return self


class _CheckpointReceipt(_Record):
    schema_id: Literal["qm.history-checkpoint.v1"]
    nonce: Epoch
    boot_id: Boot
    db: _InputFile
    runtime: _Runtime
    cut: Literal["2026-10-23T23:44:01Z"]
    completed_monotonic: FiniteTime
    completion: Literal["CHECKPOINT_COMPLETED", "VERIFIED_SEALED_CHECKPOINT"]
    pending_recovery: Literal["NONE"]
    event_receipt_sha256: Digest
    generation_receipt_sha256: Digest
    no_writer_receipt_sha256: Digest
    dependency_receipt_sha256: Digest


class _EpochContext(_Record):
    nonce: Epoch
    boot_id: Boot
    epoch_id: Epoch
    issued_monotonic: FiniteTime
    expires_monotonic: FiniteTime
    parent: _DirectoryPin
    db_sha256: Digest
    generation_receipt_sha256: Digest
    no_writer_receipt_sha256: Digest
    namespace_receipt_sha256: Digest
    checkpoint_receipt_sha256: Digest


class _EpochReceipt(_EpochContext):
    schema_id: Literal["qm.history-absence-epoch.v1"]
    actor: _Actor
    guard: _Guard


class _AbsenceReceipt(_EpochContext):
    schema_id: Literal["qm.history-absence.v1"]
    basename: Literal["updates.duckdb.wal"]
    dependency_receipt_sha256: Digest
    epoch_receipt_sha256: Digest
    enforcement: Literal["ENFORCED_NAMESPACE_EXCLUSION"]


def _receipt(raw, model, expected):
    # Reuse the bounded, duplicate-key-rejecting transport parser.

    if hashlib.sha256(raw).hexdigest() != expected:
        raise HistoryRamAuxRejected()
    return model.model_validate(_decode_json(raw))


def _validate_proofs(a, checkpoint, absence, epoch):
    s, w = a.snapshot, a.snapshot.wal
    if not isinstance(w, _AbsentWal):
        raise HistoryRamAuxRejected()
    cp = _receipt(checkpoint, _CheckpointReceipt, w.checkpoint_receipt_sha256)
    ab = _receipt(absence, _AbsenceReceipt, w.absence_receipt_sha256)
    ep = _receipt(epoch, _EpochReceipt, w.epoch_receipt_sha256)
    if (
        cp.nonce != a.nonce
        or ab.nonce != a.nonce
        or cp.db != s.db
        or cp.runtime != a.runtime
        or cp.cut != s.cut
        or cp.completed_monotonic > a.issued_monotonic
        or cp.boot_id != ab.boot_id
        or ep.boot_id != ab.boot_id
        or ep.actor != a.actor
        or ep.guard != a.guard
        or ab.parent != w.parent
        or ab.basename != w.basename
        or ab.epoch_receipt_sha256 != w.epoch_receipt_sha256
        or ab.checkpoint_receipt_sha256 != w.checkpoint_receipt_sha256
        or ab.db_sha256 != s.db.sha256
        or ab.issued_monotonic != a.issued_monotonic
        or ab.expires_monotonic != a.expires_monotonic
    ):
        raise HistoryRamAuxRejected()
    for key in (
        "generation_receipt_sha256",
        "no_writer_receipt_sha256",
        "dependency_receipt_sha256",
    ):
        if getattr(cp, key) != getattr(s, key) or getattr(ab, key) != getattr(s, key):
            raise HistoryRamAuxRejected()
    if ep.model_dump(include=set(_EpochContext.model_fields)) != ab.model_dump(
        include=set(_EpochContext.model_fields)
    ):
        raise HistoryRamAuxRejected()
    return cp, ab, ep


def encode_history_wal_state_bundle(admission, *, checkpoint=None, absence=None, epoch=None):
    """Serialize completed controller evidence; performs no host work or issuance.

    The trusted controller must already possess real completed event/namespace
    proofs. This adapter cannot attest facts, sign authority or certify a run.
    Epoch unlink revocation and final posthash/close sealing are operational duties.
    """
    try:
        a = _AdmissionV2.model_validate(admission)
        parts = (checkpoint, absence, epoch)
        if isinstance(a.snapshot.wal, _AbsentWal):
            if any(x is None for x in parts):
                raise ValueError()
            raws = tuple(_canonical(x) for x in parts)
            _validate_proofs(a, *raws)
        else:
            if any(x is not None for x in parts):
                raise ValueError()
            raws = (None, None, None)
        admission_raw = _canonical(admission)
        if len(admission_raw) > MAX_ADMISSION:
            raise ValueError()
        return dict(admission=admission_raw, checkpoint=raws[0], absence=raws[1], epoch=raws[2])
    except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
        raise HistoryRamAuxRejected() from None


class _WalEvidence:
    """Owned transport/parent descriptors; unlink permanently revokes the epoch."""

    def __init__(self, admission, root, kernel, owned, stamps, parent_fd, proofs):
        self.admission, self.root, self.kernel = admission, root, kernel
        self.owned, self.stamps, self.parent_fd, self.proofs = owned, stamps, parent_fd, proofs
        self.closed = False

    def check(self):

        if self.closed:
            raise HistoryRamAuxRejected()
        for fd, stamp in zip(self.owned, self.stamps, strict=True):
            if _fd_stamp(fd) != stamp:
                raise HistoryRamAuxRejected()
        w = self.admission.snapshot.wal
        if self.kernel.boot() != self.proofs[1].boot_id:
            raise HistoryRamAuxRejected()
        if (
            self.kernel.parent(self.root, w.parent.path, self.parent_fd)
            != (w.parent.model_dump() | dict(directory=True, readonly=True))
            or self.kernel.absent(self.parent_fd, w.basename) is not True
        ):
            raise HistoryRamAuxRejected()

    def close(self):
        import os

        self.closed = True
        fds, self.owned = self.owned, []
        if self.parent_fd is not None:
            fds.append(self.parent_fd)
            self.parent_fd = None
        error = None
        for fd in fds:
            try:
                os.close(fd)
            except OSError as exc:
                error = error or exc
        if error is not None:
            raise error


def _prepare_evidence(a, root, kernel, checkpoint_fd, absence_fd, epoch_fd):
    import os

    supplied = (checkpoint_fd, absence_fd, epoch_fd)
    absent = isinstance(a, _AdmissionV2) and isinstance(a.snapshot.wal, _AbsentWal)
    if not absent:
        if any(fd is not None for fd in supplied):
            raise HistoryRamAuxRejected()
        return None
    if any(type(fd) is not int or fd < 0 for fd in supplied):
        raise HistoryRamAuxRejected()
    owned, stamps, raws = [], [], []
    parent_fd = None
    result = None
    try:
        for fd in supplied:
            duplicate = os.dup(fd)
            owned.append(duplicate)
            os.set_inheritable(duplicate, False)
            raw, stamp = _read_admission_fd(duplicate)
            raws.append(raw)
            stamps.append(stamp)
        proofs = _validate_proofs(a, *raws)
        parent_fd = kernel.open_parent(root, a.snapshot.wal.parent.path)
        os.set_inheritable(parent_fd, False)
        result = _WalEvidence(a, root, kernel, owned, stamps, parent_fd, proofs)
        result.check()
        return result
    except BaseException:
        if result is not None:
            result.close()
        else:
            temporary = _WalEvidence(a, root, kernel, owned, stamps, parent_fd, ())
            temporary.close()
        raise


def _parent_open(root, name):
    import os

    path = _plain_path(root / name)
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _parent_fact(root, name, fd):
    import os
    import stat
    from pathlib import Path

    path = _plain_path(root / name)
    named, held = path.stat(), os.fstat(fd)

    def stamp(st):
        return (
            st.st_dev,
            st.st_ino,
            st.st_mtime_ns,
            st.st_ctime_ns,
            st.st_mode,
            st.st_nlink,
            st.st_uid,
            st.st_gid,
        )

    if not stat.S_ISDIR(held.st_mode) or stamp(named) != stamp(held):
        raise HistoryRamAuxRejected()
    matches = []
    for line in _read_text("/proc/self/mountinfo").splitlines():
        fields = line.partition(" - ")[0].split()
        if len(fields) < 6:
            continue
        mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4]))
        if mount == path or mount in path.parents:
            matches.append((len(str(mount)), int(fields[0])))
    if not matches:
        raise HistoryRamAuxRejected()
    return dict(
        path=name,
        device=held.st_dev,
        inode=held.st_ino,
        mtime_ns=held.st_mtime_ns,
        ctime_ns=held.st_ctime_ns,
        mount_id=max(matches)[1],
        directory=True,
        readonly=bool(os.statvfs(path).f_flag & os.ST_RDONLY)
        and bool(os.fstatvfs(fd).f_flag & os.ST_RDONLY),
    )


def _absent_at(parent_fd, basename):
    import os

    try:
        os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        if exc.errno != errno.ENOENT:
            raise
    else:
        return False
    # The trusted producer also proves the complete pinned recovery closure.
    # This bounded local check rejects any WAL/recovery name, including links.
    os.lseek(parent_fd, 0, os.SEEK_SET)
    with os.scandir(parent_fd) as entries:
        for count, entry in enumerate(entries, 1):
            if count > 64 or entry.name.startswith(basename):
                return False
    return True
