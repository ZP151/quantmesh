"""Private, bounded immutable memfd copies for one fixture shard."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows has no fcntl module.
    fcntl = None

from quantmesh.research._fixture_handles import DirectoryHandles, UnsupportedSnapshotProfile
from quantmesh.research._fixture_parquet_guard import validate_file_envelope
from quantmesh.research.fixture_snapshot import BUFFER_BYTES, MAX_SHARD_BYTES, _identity
from quantmesh.research.jobs import DatasetRejected

_FLAGS = 0x1 | 0x2 | 0x8
_REQUIRED_SEALS = 0x1 | 0x2 | 0x4 | 0x8 | 0x20
_KNOWN_SEALS = _REQUIRED_SEALS | 0x10


@dataclass(frozen=True)
class SealedShard:
    alias: str
    sha256: str
    size: int
    footer_length: int


def _invalid() -> None:
    raise DatasetRejected("fixture_sealed_invalid")


def _check(deadline: float) -> None:
    if time.monotonic() >= deadline:
        _invalid()


def _stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return _identity(info)


def _hash_fd(fd: int, size: int, deadline: float) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        _check(deadline)
        chunk = os.pread(fd, min(BUFFER_BYTES, size - offset), offset)
        if not chunk:
            _invalid()
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _memfd_valid(fd: int, size: int, expected: tuple[int, ...] | None = None) -> None:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 0
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_size != size
        or (expected is not None and _stat_identity(info) != expected)
    ):
        _invalid()
    seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    if seals & _REQUIRED_SEALS != _REQUIRED_SEALS or seals & ~_KNOWN_SEALS:
        _invalid()


@contextmanager
def sealed_shard(
    handles: DirectoryHandles,
    path: Path,
    deadline: float,
    *,
    limit: int = MAX_SHARD_BYTES,
):
    """Copy a held source shard into a sealed anonymous file and yield its alias."""
    if (
        sys.platform != "linux"
        or not hasattr(os, "memfd_create")
        or not hasattr(os, "pread")
        or fcntl is None
        or not hasattr(fcntl, "fcntl")
    ):
        raise UnsupportedSnapshotProfile("fixture_sealed_profile_unsupported")
    if type(limit) is not int or not 1 <= limit <= MAX_SHARD_BYTES:
        _invalid()

    source_fd = None
    sealed_fd = None
    primary_error = None
    try:
        try:
            _check(deadline)
            handles.check()
            source_fd = handles.open_file(path, os.O_RDONLY | os.O_NONBLOCK, "source")
            handles.verify()
            before = os.fstat(source_fd)
            named = handles.file_stat(path, "source")
            identity = _stat_identity(before)
            if (
                identity != _stat_identity(named)
                or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_uid != os.getuid()
                or not 0 < before.st_size <= limit
            ):
                _invalid()
            sealed_fd = os.memfd_create("quantmesh-fixture-shard", _FLAGS)
            source_hash = hashlib.sha256()
            copied = 0
            while copied < before.st_size:
                _check(deadline)
                handles.check()
                chunk = os.read(source_fd, min(BUFFER_BYTES, before.st_size - copied))
                if not chunk:
                    _invalid()
                source_hash.update(chunk)
                cursor = 0
                while cursor < len(chunk):
                    _check(deadline)
                    written = os.write(sealed_fd, chunk[cursor:])
                    if written <= 0:
                        _invalid()
                    cursor += written
                copied += len(chunk)
            if os.read(source_fd, 1):
                _invalid()
            _check(deadline)
            handles.verify()
            after = os.fstat(source_fd)
            named = handles.file_stat(path, "source")
            if (
                _stat_identity(after) != identity
                or _stat_identity(named) != identity
                or copied != before.st_size
            ):
                _invalid()
            first4 = os.pread(sealed_fd, 4, 0)
            last8 = os.pread(sealed_fd, 8, copied - 8)
            footer_length = validate_file_envelope(first4, last8, copied)
            os.fchmod(sealed_fd, 0o400)
            fcntl.fcntl(sealed_fd, fcntl.F_ADD_SEALS, _REQUIRED_SEALS)
            info = os.fstat(sealed_fd)
            memfd_identity = _stat_identity(info)
            _memfd_valid(sealed_fd, copied, memfd_identity)
            digest = source_hash.hexdigest()
            if _hash_fd(sealed_fd, copied, deadline) != digest:
                _invalid()
            owned_source_fd = source_fd
            source_fd = None
            handles.close_file(owned_source_fd)
            result = SealedShard(
                f"/proc/{os.getpid()}/fd/{sealed_fd}", digest, copied, footer_length
            )
        except (DatasetRejected, UnsupportedSnapshotProfile):
            raise
        except (OSError, ValueError, TypeError, OverflowError):
            _invalid()

        # Keep the owned memfd open through the entire consumer context.
        yield result
        try:
            _check(deadline)
            _memfd_valid(sealed_fd, result.size, memfd_identity)
            if _hash_fd(sealed_fd, result.size, deadline) != result.sha256:
                _invalid()
        except (DatasetRejected, UnsupportedSnapshotProfile):
            raise
        except (OSError, ValueError, TypeError, OverflowError):
            _invalid()
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_failed = False
        if source_fd is not None:
            owned_source_fd = source_fd
            source_fd = None
            try:
                handles.close_file(owned_source_fd)
            except Exception:
                cleanup_failed = True
        if sealed_fd is not None:
            owned_sealed_fd = sealed_fd
            sealed_fd = None
            try:
                os.close(owned_sealed_fd)
            except Exception:
                cleanup_failed = True
        if cleanup_failed and primary_error is None:
            _invalid()
