"""Private no-follow component handles for fixture I/O; no pathname fallback."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MAX_FDS = 8192
_SUPPORTED = (
    os.name == "posix"
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and {os.open, os.mkdir, os.stat} <= os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.scandir in os.supports_fd
)


class UnsupportedSnapshotProfile(ValueError):
    """The platform has no qualified handle-relative fixture I/O primitive."""


def require_snapshot_profile() -> None:
    if os.name != "posix" or not _SUPPORTED:
        raise UnsupportedSnapshotProfile("fixture_snapshot_profile_unsupported")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


@dataclass
class _Directory:
    fd: int
    parent: Path | None
    name: str
    identity: tuple[int, ...]
    ctime: int
    roles: set[str]


class DirectoryHandles:
    """Hold the component associations and close every acquired descriptor on exit.

    Relative no-follow opens bind I/O to these objects even during namespace
    replacement. Association/owner checks and mutation signals additionally refuse
    changed namespaces; timestamps are not the no-follow primitive.
    """

    def __init__(self, roots: dict[str, Path], check: Callable[[], None] = lambda: None):
        require_snapshot_profile()  # Before any fixture filesystem I/O.
        self.roots = {role: path.absolute() for role, path in roots.items()}
        if any(".." in path.parts for path in self.roots.values()):
            raise ValueError("fixture directory association invalid")
        self.check = check
        self.directories: dict[Path, _Directory] = {}
        self.files: set[int] = set()
        self.scans = 0

    def __enter__(self) -> DirectoryHandles:
        return self

    def __exit__(self, *error) -> None:
        try:
            for fd in tuple(self.files):
                self.close_file(fd)
        finally:
            for directory in reversed(tuple(self.directories.values())):
                os.close(directory.fd)
            self.directories.clear()

    def _guard(self) -> None:
        self.check()
        if len(self.directories) + len(self.files) + self.scans >= MAX_FDS:
            raise ValueError("fixture descriptor bound exceeded")

    def verify(self, *, mutating: Path | None = None) -> None:
        for path, directory in self.directories.items():
            self.check()
            current = os.fstat(directory.fd)
            if _identity(current) != directory.identity:
                raise ValueError("fixture directory identity changed")
            if directory.parent is not None:
                parent = self.directories[directory.parent]
                named = os.stat(directory.name, dir_fd=parent.fd, follow_symlinks=False)
                if _identity(named) != directory.identity:
                    raise ValueError("fixture directory membership changed")
            if path != mutating and current.st_ctime_ns != directory.ctime:
                raise ValueError("fixture directory namespace changed")
            if any(
                not (path.is_relative_to(self.roots[role]) or self.roots[role].is_relative_to(path))
                for role in directory.roles
            ):
                raise ValueError("fixture directory role changed")

    def _refresh_created_parent(self, path: Path) -> None:
        self.verify(mutating=path)
        self.directories[path].ctime = os.fstat(self.directories[path].fd).st_ctime_ns

    def directory(self, path: Path, role: str, *, create: bool = False) -> int:
        path = path.absolute()
        if (
            role not in self.roots
            or not path.is_relative_to(self.roots[role])
            or ".." in path.parts
            or (create and role != "target")
        ):
            raise ValueError("fixture directory role invalid")
        self.verify()
        anchor = Path(path.anchor)
        chain = [anchor, *reversed(path.parents[:-1]), path] if path != anchor else [anchor]
        for current in chain:
            self.check()
            if current in self.directories:
                self.directories[current].roles.add(role)
                continue
            self._guard()
            parent = current.parent if current != anchor else None
            parent_fd = self.directories[parent].fd if parent is not None else None
            name = current.name if parent is not None else str(anchor)
            # Ancestors anchor traversal; only configured roots are enumerated.
            access = (
                getattr(os, "O_PATH", os.O_RDONLY)
                if parent is None and current not in self.roots.values()
                else os.O_RDONLY
            )
            flags = access | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            try:
                fd = os.open(name, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(name, 0o700, dir_fd=parent_fd)
                self._refresh_created_parent(parent)
                fd = os.open(name, flags, dir_fd=parent_fd)
            try:
                info = os.fstat(fd)
                identity = _identity(info)
                if not stat.S_ISDIR(info.st_mode) or any(
                    item.identity[:2] == identity[:2] for item in self.directories.values()
                ):
                    raise ValueError("fixture directory object invalid")
                if (
                    role == "target"
                    and current.is_relative_to(self.roots[role])
                    and info.st_uid != os.geteuid()
                ):
                    raise ValueError("fixture destination owner invalid")
                self.directories[current] = _Directory(
                    fd, parent, name, identity, info.st_ctime_ns, {role}
                )
            except BaseException:
                os.close(fd)
                raise
            self.verify()
        return self.directories[path].fd

    def open_file(self, path: Path, flags: int, role: str) -> int:
        path = path.absolute()
        creating = bool(flags & os.O_CREAT)
        parent = path.parent
        parent_fd = self.directory(parent, role, create=creating)
        self._guard()
        try:
            fd = os.open(
                path.name,
                flags | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_fd,
            )
        except OSError:
            raise ValueError("fixture file open invalid") from None
        self.files.add(fd)
        try:
            if creating:
                self._refresh_created_parent(parent)
            else:
                self.verify()
            return fd
        except BaseException:
            self.close_file(fd)
            raise

    def close_file(self, fd: int) -> None:
        try:
            os.close(fd)
        finally:
            self.files.remove(fd)

    def file_stat(self, path: Path, role: str) -> os.stat_result:
        fd = self.directory(path.parent, role)
        result = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        self.verify()
        return result

    @contextmanager
    def scan(self, path: Path, role: str):
        fd = self.directory(path, role)
        self._guard()  # scandir(fd) may duplicate its descriptor.
        self.scans += 1
        try:
            with os.scandir(fd) as entries:
                yield entries
            self.verify()
        finally:
            self.scans -= 1
