"""Build bounded, byte-sealed metadata for an already materialized source image.

This stdlib-only producer records bytes and source associations. It does not
import QuantMesh, inspect Git, qualify Python/ELF/kernel behavior, or admit an
image or Worker. The catalog must come from the reviewed transport step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path("/opt/quantmesh")
PREFIX = Path("/usr/local")
INVENTORY_ROOTS = (
    SOURCE_ROOT,
    PREFIX,
    Path("/usr/lib/x86_64-linux-gnu"),
    Path("/usr/share/doc"),
)
PYTHON_EXECUTABLE = Path("/usr/local/bin/python3")
LOCK_IMAGE_PATH = SOURCE_ROOT / "requirements.linux-cp312.lock"
LINUX_LOCK_SHA256 = "07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a"
ENTRY_IMAGE_PATH = SOURCE_ROOT / "worker_entry.py"
OBSERVER_IMAGE_PATH = SOURCE_ROOT / "quantmesh/research/worker_provenance.py"
BOOTSTRAP_IMAGE_PATH = SOURCE_ROOT / "linux_bootstrap.py"
LICENSE_IMAGE_PATH = SOURCE_ROOT / "LICENSE"
PACKAGE_ROOT = SOURCE_ROOT / "quantmesh"
INVENTORY_PATH = SOURCE_ROOT / "inventory.json"
MANIFEST_PATH = SOURCE_ROOT / "manifest.json"

_JSON_LIMIT = 4 * 1024 * 1024
_FILE_LIMIT = 512 * 1024 * 1024
_BYTE_LIMIT = 512 * 1024 * 1024
_NODE_LIMIT = 20_000
_DEADLINE_SECONDS = 30.0
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_RECORD_KEYS = {"repository_path", "image_path", "bytes", "sha256"}


class ImageSealRejected(ValueError):
    """Sanitized producer refusal; no metadata is published on preflight errors."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def _fail() -> None:
    raise ImageSealRejected("image metadata refused") from None


def _abs_path(value: object) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 4096
        or any(ord(char) < 32 for char in value)
        or '"' in value
        or "\x00" in value
        or "\\" in value
    ):
        _fail()
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        _fail()
    return path


def _repository_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 4096
        or any(ord(char) < 32 for char in value)
        or '"' in value
        or "\\" in value
        or "\x00" in value
    ):
        _fail()
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail()
    return value


def _sig(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _open_dir(path: Path) -> int:
    """Open every absolute path component without following symlinks."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open("/", flags)
    try:
        current = Path("/")
        for part in path.parts[1:]:
            before = os.stat(part, dir_fd=fd, follow_symlinks=False)
            following = os.open(part, flags, dir_fd=fd)
            after = os.fstat(following)
            if not stat.S_ISDIR(after.st_mode) or _sig(before) != _sig(after):
                os.close(following)
                _fail()
            os.close(fd)
            fd = following
            current /= part
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_regular(
    path: Path,
    limit: int,
    deadline: float,
    byte_state: list[int] | None = None,
    expected_sig: tuple[int, ...] | None = None,
    capture: bool = False,
) -> tuple[bytes | None, str, int]:
    """Read one single-link regular file with held no-follow component FDs."""
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        _fail()
    parent = _open_dir(path.parent)
    held = [parent]
    try:
        before_named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        fd = os.open(
            path.name,
            os.O_RDONLY
            | os.O_NOFOLLOW
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        held.append(fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _sig(before) != _sig(before_named)
            or (expected_sig is not None and _sig(before) != expected_sig)
            or before.st_size < 0
            or before.st_size > limit
        ):
            _fail()
        result = bytearray() if capture else None
        digest = hashlib.sha256()
        size = 0
        while True:
            if time.monotonic() > deadline:
                _fail()
            chunk = os.read(fd, min(64 * 1024, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                _fail()
            digest.update(chunk)
            if result is not None:
                result.extend(chunk)
            if byte_state is not None:
                byte_state[0] += len(chunk)
                if byte_state[0] > _BYTE_LIMIT:
                    _fail()
        after = os.fstat(fd)
        after_named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (
            size != before.st_size
            or _sig(before) != _sig(after)
            or _sig(after) != _sig(after_named)
        ):
            _fail()
        current_parent = _open_dir(path.parent)
        try:
            if _sig(os.fstat(current_parent)) != _sig(os.fstat(parent)):
                _fail()
        finally:
            os.close(current_parent)
        return (bytes(result) if result is not None else None, digest.hexdigest(), size)
    finally:
        for fd in reversed(held):
            os.close(fd)


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _catalog_records(catalog: object) -> tuple[str, list[dict[str, object]]]:
    if not isinstance(catalog, dict):
        _fail()
    commit = catalog.get("source_commit")
    rows = catalog.get("input_records")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        _fail()
    if not isinstance(rows, list) or not rows or len(rows) > _NODE_LIMIT:
        _fail()
    result: list[dict[str, object]] = []
    seen_targets: set[Path] = set()
    repo_to_digest: dict[str, tuple[int, str]] = {}
    input_text_bytes = len(commit.encode("ascii"))
    for row in rows:
        if not isinstance(row, dict) or set(row) != _RECORD_KEYS:
            _fail()
        repository = _repository_path(row["repository_path"])
        target = _abs_path(row["image_path"])
        input_text_bytes += (
            len(repository.encode("utf-8"))
            + len(str(target).encode("utf-8"))
            + len(str(row["bytes"]))
            + len(str(row["sha256"]))
            + 80
        )
        if input_text_bytes > _JSON_LIMIT:
            _fail()
        size, digest = row["bytes"], row["sha256"]
        if type(size) is not int or size < 0 or size > _FILE_LIMIT:
            _fail()
        if not isinstance(digest, str) or not _SHA.fullmatch(digest):
            _fail()
        if target in seen_targets:
            _fail()
        seen_targets.add(target)
        prior = repo_to_digest.setdefault(repository, (size, digest))
        if prior != (size, digest):
            _fail()
        result.append(
            {"repository_path": repository, "image_path": target, "bytes": size, "sha256": digest}
        )
    return commit, result


def _validate_spec(
    catalog: dict, records: list[dict[str, object]]
) -> tuple[list[Path], list[Path], list[Path]]:
    raw_roots = catalog.get("roots")
    raw_libs = catalog.get("library_paths")
    raw_notices = catalog.get("notice_paths")
    if not isinstance(raw_roots, list) or len(raw_roots) != len(INVENTORY_ROOTS):
        _fail()
    roots = [_abs_path(item) for item in raw_roots]
    if tuple(roots) != INVENTORY_ROOTS:
        _fail()
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if _inside(left, right) or _inside(right, left):
                _fail()
    if (
        not isinstance(raw_libs, list)
        or not raw_libs
        or len(raw_libs) > _NODE_LIMIT
        or not isinstance(raw_notices, list)
        or not raw_notices
        or len(raw_notices) > _NODE_LIMIT
    ):
        _fail()
    libraries = [_abs_path(item) for item in raw_libs]
    notices = [_abs_path(item) for item in raw_notices]
    if (
        sum(len(str(path).encode("utf-8")) + 8 for path in roots + libraries + notices)
        > _JSON_LIMIT
    ):
        _fail()
    if len(set(libraries)) != len(libraries) or len(set(notices)) != len(notices):
        _fail()
    if set(libraries) & set(notices):
        _fail()
    for target in libraries + notices:
        if not any(_inside(target, root) for root in roots):
            _fail()

    targets = {row["image_path"] for row in records}
    for fixed_path, repository in (
        (ENTRY_IMAGE_PATH, "deploy/research_worker/worker_entry.py"),
        (OBSERVER_IMAGE_PATH, "src/quantmesh/research/worker_provenance.py"),
        (BOOTSTRAP_IMAGE_PATH, "src/quantmesh/research/linux_bootstrap.py"),
        (PACKAGE_ROOT / "research/linux_bootstrap.py", "src/quantmesh/research/linux_bootstrap.py"),
        (LICENSE_IMAGE_PATH, "LICENSE"),
        (LOCK_IMAGE_PATH, "services/research_agent/requirements.linux-cp312.lock"),
    ):
        if fixed_path not in targets or not any(
            row["image_path"] == fixed_path and row["repository_path"] == repository
            for row in records
        ):
            _fail()
    repository_counts: dict[str, int] = {}
    for row in records:
        target = row["image_path"]
        repository = row["repository_path"]
        repository_counts[repository] = repository_counts.get(repository, 0) + 1
        if not _inside(target, SOURCE_ROOT) or target in {INVENTORY_PATH, MANIFEST_PATH}:
            _fail()
        if repository.startswith("src/quantmesh/"):
            relative = repository.removeprefix("src/")
            if target != SOURCE_ROOT / relative and not (
                repository == "src/quantmesh/research/linux_bootstrap.py"
                and target == BOOTSTRAP_IMAGE_PATH
            ):
                _fail()
        elif (repository, target) not in {
            ("deploy/research_worker/worker_entry.py", ENTRY_IMAGE_PATH),
            ("LICENSE", LICENSE_IMAGE_PATH),
            ("services/research_agent/requirements.linux-cp312.lock", LOCK_IMAGE_PATH),
        }:
            _fail()
    if any(
        count > 1 and path != "src/quantmesh/research/linux_bootstrap.py"
        for path, count in repository_counts.items()
    ):
        _fail()
    return roots, libraries, notices


def _walk(roots: list[Path], deadline: float) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """Stream every selected tree; retain signatures, not directory listings."""
    files: dict[str, str] = {}
    links: dict[str, str] = {}
    all_package_files: set[str] = set()
    nodes = [0]
    bytes_read = [0]
    root_signatures: list[tuple[Path, tuple[int, ...]]] = []

    def count() -> None:
        nodes[0] += 1
        if nodes[0] > _NODE_LIMIT or time.monotonic() > deadline:
            _fail()

    for root in roots:
        count()
        root_fd = _open_dir(root)
        root_info = os.fstat(root_fd)
        root_signatures.append((root, _sig(root_info)))
        stack: list[
            tuple[int, os.ScandirIterator, Path, tuple[int, ...], int | None, str | None]
        ] = []
        try:
            stack.append((root_fd, os.scandir(root_fd), root, _sig(root_info), None, None))
            while stack:
                if time.monotonic() > deadline:
                    _fail()
                dir_fd, iterator, directory, dir_sig, parent_fd, child_name = stack[-1]
                try:
                    entry = next(iterator)
                except StopIteration:
                    iterator.close()
                    if parent_fd is not None and child_name is not None:
                        named = os.stat(child_name, dir_fd=parent_fd, follow_symlinks=False)
                        if _sig(os.fstat(dir_fd)) != dir_sig or _sig(named) != dir_sig:
                            _fail()
                    os.close(dir_fd)
                    stack.pop()
                    continue
                count()
                before = entry.stat(follow_symlinks=False)
                path = directory / entry.name
                key = str(path)
                if stat.S_ISDIR(before.st_mode):
                    flags = (
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                    )
                    child_fd = os.open(entry.name, flags, dir_fd=dir_fd)
                    child_info = os.fstat(child_fd)
                    named = os.stat(entry.name, dir_fd=dir_fd, follow_symlinks=False)
                    if _sig(before) != _sig(child_info) or _sig(named) != _sig(child_info):
                        os.close(child_fd)
                        _fail()
                    stack.append(
                        (child_fd, os.scandir(child_fd), path, _sig(child_info), dir_fd, entry.name)
                    )
                elif stat.S_ISREG(before.st_mode):
                    if before.st_nlink != 1 or before.st_size < 0 or before.st_size > _FILE_LIMIT:
                        _fail()
                    _, digest, _ = _read_regular(
                        path, _FILE_LIMIT, deadline, bytes_read, _sig(before)
                    )
                    files[key] = digest
                    if _inside(path, PACKAGE_ROOT):
                        all_package_files.add(key)
                elif stat.S_ISLNK(before.st_mode):
                    target = os.readlink(entry.name, dir_fd=dir_fd)
                    if not target or "\x00" in target:
                        _fail()
                    after = os.stat(entry.name, dir_fd=dir_fd, follow_symlinks=False)
                    if _sig(before) != _sig(after):
                        _fail()
                    links[key] = target
                else:
                    _fail()
                if len(files) + len(links) > _NODE_LIMIT:
                    _fail()
            # root fd is consumed/closed when its stack frame unwinds.
        except BaseException:
            for _, iterator, _, _, _, _ in reversed(stack):
                iterator.close()
            for fd, _, _, _, _, _ in reversed(stack):
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise
    for path, expected_sig in root_signatures:
        fd = _open_dir(path)
        try:
            if _sig(os.fstat(fd)) != expected_sig:
                _fail()
        finally:
            os.close(fd)
    for name, target in links.items():
        link = Path(name)
        try:
            resolved = link.resolve(strict=True)
        except (OSError, RuntimeError):
            _fail()
        if not any(_inside(resolved, root) for root in roots):
            _fail()
        if resolved.is_file() and str(resolved) not in files:
            _fail()
        if Path(target).is_absolute() and not any(_inside(Path(target), root) for root in roots):
            _fail()
    return files, links, all_package_files


def _publish(path: Path, raw: bytes) -> int:
    parent = _open_dir(path.parent)
    try:
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o644,
            dir_fd=parent,
        )
        inode = os.fstat(fd).st_ino
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fsync(fd)
            info = os.fstat(fd)
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or _sig(info) != _sig(named):
                _fail()
            return info.st_ino
        except BaseException:
            try:
                current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if (
                    current.st_ino == inode
                    and stat.S_ISREG(current.st_mode)
                    and current.st_nlink == 1
                ):
                    os.unlink(path.name, dir_fd=parent)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _remove_own(path: Path, inode: int) -> None:
    parent = _open_dir(path.parent)
    try:
        try:
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if current.st_ino == inode and stat.S_ISREG(current.st_mode) and current.st_nlink == 1:
                os.unlink(path.name, dir_fd=parent)
        except FileNotFoundError:
            pass
    finally:
        os.close(parent)


def _metadata_absent(path: Path) -> bool:
    parent = _open_dir(path.parent)
    try:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            return False
        except FileNotFoundError:
            return True
    finally:
        os.close(parent)


def produce(catalog: dict) -> dict[str, object]:
    """Preflight explicit committed-source pins and publish canonical metadata."""
    try:
        if sys.platform != "linux" or os.name != "posix":
            _fail()
        if set(catalog) != {
            "source_commit",
            "input_records",
            "roots",
            "library_paths",
            "notice_paths",
        }:
            _fail()
        commit, records = _catalog_records(catalog)
        roots, libraries, notices = _validate_spec(catalog, records)
        if len(_canonical(catalog)) > _JSON_LIMIT:
            _fail()
        # Refuse both fixed publication names before any bounded filesystem walk.
        for metadata in (INVENTORY_PATH, MANIFEST_PATH):
            if not _metadata_absent(metadata):
                _fail()
        deadline = time.monotonic() + _DEADLINE_SECONDS
        seen_source: set[Path] = set()
        expected_source_files: dict[str, str] = {}
        for row in records:
            target = row["image_path"]
            if target in seen_source:
                _fail()
            seen_source.add(target)
            _, digest, size = _read_regular(target, min(_FILE_LIMIT, row["bytes"]), deadline)
            if size != row["bytes"] or digest != row["sha256"]:
                _fail()
            if target == LOCK_IMAGE_PATH and row["sha256"] != LINUX_LOCK_SHA256:
                _fail()
            if _inside(target, PACKAGE_ROOT) and target.suffix in {".pyc", ".pyo"}:
                _fail()
            if _inside(target, PACKAGE_ROOT) and target.suffix == ".py":
                expected_source_files[str(target.relative_to(SOURCE_ROOT))] = row["sha256"]
        files, links, package_files = _walk(roots, deadline)
        declared_package = {str(path) for path in seen_source if _inside(path, PACKAGE_ROOT)}
        if package_files != declared_package:
            _fail()
        declared_source = {str(path) for path in seen_source}
        measured_source = {name for name in files if _inside(Path(name), SOURCE_ROOT)}
        if measured_source != declared_source or any(
            _inside(Path(name), SOURCE_ROOT) for name in links
        ):
            _fail()
        if any(str(path) not in files for path in libraries + notices):
            _fail()
        if str(PYTHON_EXECUTABLE) not in files and str(PYTHON_EXECUTABLE) not in links:
            _fail()
        if str(LOCK_IMAGE_PATH) not in files or files[str(LOCK_IMAGE_PATH)] != LINUX_LOCK_SHA256:
            _fail()
        for row in records:
            path = str(row["image_path"])
            if files.get(path) != row["sha256"]:
                _fail()
        inventory = {
            "roots": sorted(str(root) for root in roots),
            "files": dict(sorted(files.items())),
            "symlinks": dict(sorted(links.items())),
        }
        inventory_bytes = _canonical(inventory)
        if not 0 < len(inventory_bytes) <= _JSON_LIMIT:
            _fail()
        manifest = {
            "schema_version": 1,
            "source_commit": commit,
            "source_root": str(SOURCE_ROOT),
            "prefix": str(PREFIX),
            "python_executable": str(PYTHON_EXECUTABLE),
            "lock_path": str(LOCK_IMAGE_PATH),
            "inventory_path": str(INVENTORY_PATH),
            "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "source_files": dict(sorted(expected_source_files.items())),
            "library_paths": sorted(str(path) for path in libraries),
            "notice_paths": sorted(str(path) for path in notices),
        }
        manifest_bytes = _canonical(manifest)
        if not 0 < len(manifest_bytes) <= _JSON_LIMIT:
            _fail()
        created: list[tuple[Path, int]] = []
        try:
            created.append((INVENTORY_PATH, _publish(INVENTORY_PATH, inventory_bytes)))
            created.append((MANIFEST_PATH, _publish(MANIFEST_PATH, manifest_bytes)))
            for path, expected_bytes in (
                (INVENTORY_PATH, inventory_bytes),
                (MANIFEST_PATH, manifest_bytes),
            ):
                _, digest, size = _read_regular(path, _JSON_LIMIT, deadline)
                if (
                    size != len(expected_bytes)
                    or digest != hashlib.sha256(expected_bytes).hexdigest()
                ):
                    _fail()
        except BaseException:
            for path, inode in reversed(created):
                _remove_own(path, inode)
            raise
        return {
            "inventory": inventory,
            "manifest": manifest,
            "inventory_bytes": inventory_bytes,
            "manifest_bytes": manifest_bytes,
            "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        }
    except ImageSealRejected:
        raise
    except (OSError, TypeError, ValueError, OverflowError, RecursionError):
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", help="reviewed committed-source catalog JSON")
    args = parser.parse_args()
    try:
        raw, _, _ = _read_regular(
            Path(args.catalog),
            _JSON_LIMIT,
            time.monotonic() + _DEADLINE_SECONDS,
            capture=True,
        )
        assert raw is not None
        catalog = json.loads(raw, object_pairs_hook=_unique_pairs)
        result = produce(catalog)
    except (ImageSealRejected, json.JSONDecodeError, OSError, TypeError, ValueError):
        print("image metadata refused", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {key: result[key] for key in ("inventory_sha256", "manifest_sha256")}, sort_keys=True
        )
    )
    return 0


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
