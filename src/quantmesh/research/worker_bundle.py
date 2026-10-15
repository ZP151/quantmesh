"""Held metadata-only handoff of one private snapshot, never image admission."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from quantmesh.research._fixture_handles import DirectoryHandles, require_snapshot_profile

_MAX_NODES = 4096
_MAX_BYTES = 257 * 1024 * 1024
_MAX_SECONDS = 10.0


class WorkerBundleRejected(ValueError):
    """Sanitized association/privilege refusal before starting any child."""


def _stable(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def _unchanged(info: os.stat_result) -> tuple:
    return (*_stable(info), info.st_mode, info.st_uid, info.st_gid, info.st_ctime_ns)


def handoff_worker_bundle(bundle: Path, uid: int, gid: int) -> None:
    """Change only held owned nodes; never read/decode their contents.

    Partial owned metadata on failure stays retained. The caller must not create
    a container after rejection. The root stays private/writable to the same UID
    or root parent until it writes its exclusive binding; its child bind is RO.
    """
    try:
        require_snapshot_profile()
        bundle = Path(bundle)
        if not bundle.is_absolute() or bundle == Path("/") or ".." in bundle.parts:
            raise ValueError
        actor, group = os.geteuid(), os.getegid()
        if (
            type(uid) is not int
            or type(gid) is not int
            or not 1 <= uid <= 65535
            or not 1 <= gid <= 65535
            or (actor != 0 and (uid != actor or gid != group))
        ):
            raise ValueError
        deadline = time.monotonic() + _MAX_SECONDS
        count, total = 1, 0

        def bounded():
            if time.monotonic() >= deadline or count > _MAX_NODES:
                raise ValueError

        with DirectoryHandles({"source": bundle}, check=bounded) as handles:
            pending, directories, files, members = [bundle], {}, [], {}
            while pending:
                path = pending.pop()
                fd = handles.directory(path, "source")
                info = os.fstat(fd)
                if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (actor, group, 0o700):
                    raise ValueError
                directories[path] = (fd, info)
                bounded()
                names = set()
                with handles.scan(path, "source") as entries:
                    for entry in entries:
                        count += 1
                        bounded()
                        if entry.name in names:
                            raise ValueError
                        names.add(entry.name)
                        current = path / entry.name
                        info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(current)
                        elif stat.S_ISREG(info.st_mode):
                            if info.st_nlink != 1 or (info.st_uid, info.st_gid) != (actor, group):
                                raise ValueError
                            file_fd = handles.open_file(
                                current, os.O_RDONLY | os.O_NONBLOCK, "source"
                            )
                            opened = os.fstat(file_fd)
                            if _unchanged(opened) != _unchanged(info):
                                raise ValueError
                            files.append((current, file_fd, opened))
                            total += opened.st_size
                            if total > _MAX_BYTES:
                                raise ValueError
                            bounded()
                        else:
                            raise ValueError
                members[path] = frozenset(names)

            handles.verify()
            # Entire tree has passed the preflight before the first mutation.
            for path, fd, before in files:
                bounded()
                handles.verify()
                if _unchanged(os.fstat(fd)) != _unchanged(before):
                    raise ValueError
                os.fchown(fd, uid, gid)
                os.fchmod(fd, 0o400)
                current = os.fstat(fd)
                if (
                    _stable(current) != _stable(before)
                    or (current.st_uid, current.st_gid, stat.S_IMODE(current.st_mode))
                    != (uid, gid, 0o400)
                    or _unchanged(handles.file_stat(path, "source")) != _unchanged(current)
                ):
                    raise ValueError

            for path in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                bounded()
                handles.verify()
                fd, before = directories[path]
                if _unchanged(os.fstat(fd)) != _unchanged(before):
                    raise ValueError
                mode = 0o700 if path == bundle else 0o500
                os.fchown(fd, uid, gid)
                os.fchmod(fd, mode)
                current = os.fstat(fd)
                if _stable(current) != _stable(before) or (
                    current.st_uid,
                    current.st_gid,
                    stat.S_IMODE(current.st_mode),
                ) != (uid, gid, mode):
                    raise ValueError
                # Refresh only the explicitly verified planned metadata change;
                # the held directory object and named parent association persist.
                record = handles.directories[path]
                record.identity = current.st_dev, current.st_ino, current.st_mode, uid, gid
                record.ctime = current.st_ctime_ns
                handles.verify()

            for path, names in members.items():
                with handles.scan(path, "source") as entries:
                    if frozenset(entry.name for entry in entries) != names:
                        raise ValueError
            handles.verify()
            for path, fd, before in files:
                current = os.fstat(fd)
                if (
                    _stable(current) != _stable(before)
                    or (current.st_uid, current.st_gid, stat.S_IMODE(current.st_mode))
                    != (uid, gid, 0o400)
                    or _unchanged(handles.file_stat(path, "source")) != _unchanged(current)
                ):
                    raise ValueError
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
        raise WorkerBundleRejected("worker bundle rejected") from None
