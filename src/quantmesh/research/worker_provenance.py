"""Source-bound preflight for the fixed Linux research Worker entry.

This module reports verified source bytes only. It does not attest an image,
kernel, native extension, container or Engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
import types
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = Path("/opt/quantmesh")
ENTRY_PATH = SOURCE_ROOT / "worker_entry.py"
OBSERVER_PATH = SOURCE_ROOT / "quantmesh/research/worker_provenance.py"
BUILD_PATH = SOURCE_ROOT / "quantmesh/research/worker_build.py"
MANIFEST_PATH = SOURCE_ROOT / "manifest.json"
INVENTORY_PATH = SOURCE_ROOT / "inventory.json"
BINDING_PATH = Path("/inputs/parent-binding.json")
MAX_BINDING_BYTES = 16 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_INVENTORY_FILES = 20_000
MAX_SOURCE_NODES = 20_000
MAX_SOURCE_WALK_SECONDS = 30.0
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class SourcePreflightRejected(ValueError):
    """Sanitized refusal; paths and source contents are never included."""


@dataclass(frozen=True, slots=True)
class SourceObservation:
    binding_sha256: str
    manifest_sha256: str
    inventory_sha256: str
    entry_sha256: str
    observer_sha256: str
    source_root: str
    search_paths: tuple[str, ...]


def _fail() -> None:
    raise SourcePreflightRejected("worker entry rejected") from None


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read(path: Path, limit: int, *, allow_empty: bool = False) -> tuple[bytes, tuple]:
    """Read through held no-follow directory descriptors and verify each name."""
    fds: list[int] = []
    try:
        parts = path.parts
        if not path.is_absolute() or not parts or parts[0] != "/" or ".." in parts:
            _fail()
        # Root is a traversal anchor; actual directory/file reads stay checked.
        current = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(current)
        directories: list[tuple[int, str, tuple[int, ...]]] = []
        for name in parts[1:-1]:
            following = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            fds.append(following)
            info = os.fstat(following)
            named = os.stat(name, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _signature(info) != _signature(named):
                _fail()
            directories.append((current, name, _signature(info)))
            current = following
        filename = parts[-1]
        fd = os.open(
            filename,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=current,
        )
        fds.append(fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size < int(not allow_empty)
            or before.st_size > limit
        ):
            _fail()
        content = bytearray()
        while len(content) <= limit:
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(filename, dir_fd=current, follow_symlinks=False)
        if (
            _signature(before) != _signature(after)
            or _signature(after) != _signature(named)
            or len(content) != before.st_size
        ):
            _fail()
        for parent_fd, name, expected in directories:
            held = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if _signature(held) != expected:
                _fail()
        identity = _signature(after)
        return bytes(content), identity
    except (OSError, ValueError, TypeError, RecursionError):
        _fail()
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass


def _directory_exists(path: Path) -> bool:
    descriptors: list[int] = []
    try:
        if not path.is_absolute() or ".." in path.parts:
            return False
        current = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(current)
        for name in path.parts[1:]:
            following = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(following)
            info = os.fstat(following)
            named = os.stat(name, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _signature(info) != _signature(named):
                return False
            current = following
        return True
    except OSError:
        return False
    finally:
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                pass


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            _fail()
        result[key] = value
    return result


def _json(raw: bytes) -> dict:
    value = json.loads(raw, object_pairs_hook=_pairs)
    if type(value) is not dict:
        _fail()
    return value


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def _verified_builder(
    path: Path, raw: bytes, name: str = "quantmesh_worker_build_pinned"
) -> Iterator[types.ModuleType]:
    """Compile a fresh, currently verified builder and remove only our module."""
    if name in sys.modules:
        _fail()
    current, _ = _read(path, MAX_SOURCE_BYTES)
    if current != raw:
        _fail()
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    module.__spec__ = None
    sys.modules[name] = module
    try:
        exec(compile(current, str(path), "exec", dont_inherit=True), module.__dict__)
        if sys.modules.get(name) is not module:
            _fail()
        yield module
    finally:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        else:
            # A substituted or removed entry is not ours to clean up.
            _fail()


def _source_set(source_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    total = 0
    package = source_root / "quantmesh"
    if MAX_SOURCE_NODES < 1 or MAX_SOURCE_WALK_SECONDS <= 0:
        _fail()
    deadline = time.monotonic() + MAX_SOURCE_WALK_SECONDS
    nodes = 1  # The package root itself is part of the bounded namespace.
    descriptors: list[int] = []

    def check_deadline() -> None:
        if time.monotonic() >= deadline:
            _fail()

    def open_directory(path: Path) -> int:
        parts = path.parts
        if not path.is_absolute() or not parts or parts[0] != "/" or ".." in parts:
            _fail()
        current = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(current)
        for name in parts[1:]:
            check_deadline()
            following = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(following)
            held = os.fstat(following)
            named = os.stat(name, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(held.st_mode) or _signature(held) != _signature(named):
                _fail()
            current = following
        return current

    def scan_directory(directory_fd: int, directory_path: Path) -> None:
        nonlocal nodes, total
        before = os.fstat(directory_fd)
        if not stat.S_ISDIR(before.st_mode):
            _fail()
        try:
            # scandir duplicates a supplied descriptor internally and leaves the
            # caller's held descriptor open. An extra caller-side dup leaks.
            with os.scandir(directory_fd) as entries:
                for entry in entries:
                    check_deadline()
                    nodes += 1
                    if nodes > MAX_SOURCE_NODES:
                        _fail()
                    name = entry.name
                    if not name or name in {".", ".."} or "/" in name or "\0" in name:
                        _fail()
                    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if stat.S_ISLNK(named.st_mode):
                        _fail()
                    path = directory_path / name
                    if stat.S_ISDIR(named.st_mode):
                        child_fd = os.open(
                            name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory_fd,
                        )
                        try:
                            child = os.fstat(child_fd)
                            opened_name = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                            if (
                                not stat.S_ISDIR(child.st_mode)
                                or _signature(child) != _signature(opened_name)
                                or _signature(child) != _signature(named)
                            ):
                                _fail()
                            scan_directory(child_fd, path)
                            current_name = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                            if _signature(current_name) != _signature(child):
                                _fail()
                        finally:
                            os.close(child_fd)
                        continue
                    if not stat.S_ISREG(named.st_mode) or named.st_nlink != 1:
                        _fail()
                    if path.suffix == ".py":
                        raw, identity = _read(path, MAX_SOURCE_BYTES)
                        if identity != _signature(named):
                            _fail()
                        total += len(raw)
                        if total > MAX_SOURCE_TOTAL_BYTES:
                            _fail()
                        relative = path.relative_to(source_root).as_posix()
                        result[relative] = _hash(raw)
                    check_deadline()
        finally:
            after = os.fstat(directory_fd)
            if _signature(before) != _signature(after):
                _fail()

    try:
        root_fd = open_directory(package)
        scan_directory(root_fd, package)
        for parent_fd, name, identity in zip(
            descriptors[:-1], package.parts[1:], descriptors[1:], strict=True
        ):
            if _signature(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != _signature(
                os.fstat(identity)
            ):
                _fail()
    except SourcePreflightRejected:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        _fail()
    finally:
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                pass
    if not result:
        _fail()
    return result


def _assert_source_associations(
    source_root: Path, declared: object, inventory_files: object
) -> dict[str, str]:
    """Require every current package source to match both sealed declarations."""
    current = _source_set(source_root)
    if type(declared) is not dict or declared != current or type(inventory_files) is not dict:
        _fail()
    if any(
        inventory_files.get(str(source_root / name)) != digest for name, digest in current.items()
    ):
        _fail()
    return current


def _preflight(
    *,
    binding_raw: bytes,
    expected_binding_sha256: str,
    entry_raw: bytes,
    observer_raw: bytes,
    source_root: Path = SOURCE_ROOT,
    entry_path: Path = ENTRY_PATH,
    observer_path: Path = OBSERVER_PATH,
    build_path: Path = BUILD_PATH,
    manifest_path: Path = MANIFEST_PATH,
    inventory_path: Path = INVENTORY_PATH,
    binding_path: Path = BINDING_PATH,
) -> SourceObservation:
    """Verify fixed source associations; internal path parameters ease fixture tests."""
    try:
        if (
            not _DIGEST.fullmatch(expected_binding_sha256)
            or len(binding_raw) > MAX_BINDING_BYTES
            or _hash(binding_raw) != expected_binding_sha256
        ):
            _fail()
        binding_value = _json(binding_raw)
        canonical = json.dumps(
            binding_value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        if binding_raw != canonical:
            _fail()
        fields = (
            "schema",
            "engine_id",
            "image_id",
            "image_config_sha256",
            "container_id",
            "owner_nonce",
            "manifest_sha256",
            "inventory_sha256",
            "dependency_lock_sha256",
            "python_executable_sha256",
            "entry_sha256",
            "observer_sha256",
            "expected_prefix",
            "python_version",
            "kernel_profile_sha256",
        )
        schema = binding_value.get("schema")
        expected_fields = set(fields) | ({"execution_profile"} if schema == 2 else set())
        if set(binding_value) != expected_fields or type(schema) is not int or schema not in (1, 2):
            _fail()
        manifest_digest = binding_value["manifest_sha256"]
        inventory_digest = binding_value["inventory_sha256"]
        entry_digest = binding_value["entry_sha256"]
        observer_digest = binding_value["observer_sha256"]
        if any(
            not isinstance(value, str) or not _DIGEST.fullmatch(value)
            for value in (manifest_digest, inventory_digest, entry_digest, observer_digest)
        ):
            _fail()
        if (
            binding_value["expected_prefix"] != "/usr/local"
            or binding_value["python_version"] != "3.12.15"
        ):
            _fail()
        current_entry, _ = _read(entry_path, MAX_SOURCE_BYTES)
        current_observer, _ = _read(observer_path, MAX_SOURCE_BYTES)
        if (
            current_entry != entry_raw
            or current_observer != observer_raw
            or _hash(entry_raw) != entry_digest
            or _hash(observer_raw) != observer_digest
        ):
            _fail()
        manifest_raw, _ = _read(manifest_path, MAX_METADATA_BYTES)
        inventory_raw, _ = _read(inventory_path, MAX_METADATA_BYTES)
        if _hash(manifest_raw) != manifest_digest or _hash(inventory_raw) != inventory_digest:
            _fail()
        manifest = _json(manifest_raw)
        inventory = _json(inventory_raw)
        if set(manifest) != {
            "schema_version",
            "source_commit",
            "source_root",
            "prefix",
            "python_executable",
            "lock_path",
            "inventory_path",
            "inventory_sha256",
            "source_files",
            "library_paths",
            "notice_paths",
        }:
            _fail()
        if (
            type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or manifest["source_root"] != str(source_root)
            or manifest["prefix"] != "/usr/local"
            or manifest["python_executable"] != "/usr/local/bin/python3"
            or manifest["inventory_path"] != str(inventory_path)
            or manifest["inventory_sha256"] != inventory_digest
            or not isinstance(manifest["source_commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"]) is None
        ):
            _fail()
        if set(inventory) != {"roots", "files", "symlinks"}:
            _fail()
        files = inventory["files"]
        if (
            type(files) is not dict
            or not files
            or len(files) > MAX_INVENTORY_FILES
            or type(inventory["roots"]) is not list
            or str(source_root) not in inventory["roots"]
            or "/usr/local" not in inventory["roots"]
        ):
            _fail()
        source_files = manifest["source_files"]
        current_sources = _assert_source_associations(source_root, source_files, files)
        if (
            type(manifest["library_paths"]) is not list
            or not manifest["library_paths"]
            or type(manifest["notice_paths"]) is not list
            or not manifest["notice_paths"]
        ):
            _fail()
        for path in (entry_path, observer_path, build_path, manifest_path, inventory_path):
            if path in {manifest_path, inventory_path}:
                continue
            raw, _ = _read(path, MAX_SOURCE_BYTES if path.suffix == ".py" else MAX_METADATA_BYTES)
            pinned = files.get(str(path))
            if path == entry_path:
                pinned = entry_digest
            elif path == observer_path:
                pinned = observer_digest
            if not isinstance(pinned, str) or _hash(raw) != pinned:
                _fail()
        build_raw, _ = _read(build_path, MAX_SOURCE_BYTES)
        build_digest = files.get(str(build_path))
        if not isinstance(build_digest, str) or _hash(build_raw) != build_digest:
            _fail()
        with _verified_builder(build_path, build_raw) as builder:
            contract = builder.parse_parent_binding(
                binding_raw, expected_sha256=expected_binding_sha256
            )
            if (
                contract.manifest_sha256 != manifest_digest
                or contract.inventory_sha256 != inventory_digest
                or contract.entry_sha256 != entry_digest
                or contract.observer_sha256 != observer_digest
            ):
                _fail()
            # The immutable parsed inventory is shared by all membership checks.
            # Rebuilding its Path set per library/notice makes real image
            # preflight quadratic, before the unchanged full byte verifier.
            inventory_paths = {Path(name) for name in files}
            if (
                not isinstance(manifest["lock_path"], str)
                or builder._path(manifest["lock_path"]) not in inventory_paths
                or any(
                    type(manifest[key]) is not list
                    or not manifest[key]
                    or len(set(manifest[key])) != len(manifest[key])
                    or any(
                        not isinstance(path, str) or builder._path(path) not in inventory_paths
                        for path in manifest[key]
                    )
                    for key in ("library_paths", "notice_paths")
                )
            ):
                _fail()
            # Reuse the integrated exact-membership and metadata-byte verifier only
            # after its source bytes and every package source have been independently pinned.
            admitted = builder._inventory(
                inventory_path,
                inventory_digest,
                manifest_path=manifest_path,
                manifest_expected=manifest_digest,
            )
            if any(
                admitted.get(str(source_root / name)) != digest
                for name, digest in current_sources.items()
            ):
                _fail()
            if _assert_source_associations(source_root, source_files, files) != current_sources:
                _fail()
            if (
                _read(manifest_path, MAX_METADATA_BYTES)[0] != manifest_raw
                or _read(inventory_path, MAX_METADATA_BYTES)[0] != inventory_raw
                or _read(entry_path, MAX_SOURCE_BYTES)[0] != entry_raw
                or _read(observer_path, MAX_SOURCE_BYTES)[0] != observer_raw
                or _read(build_path, MAX_SOURCE_BYTES)[0] != build_raw
            ):
                _fail()
        prefix = Path(manifest["prefix"])
        site_packages = prefix / "lib/python3.12/site-packages"
        if not _directory_exists(site_packages):
            _fail()
        search_paths = (str(source_root), str(site_packages))
        return SourceObservation(
            expected_binding_sha256,
            manifest_digest,
            inventory_digest,
            entry_digest,
            observer_digest,
            str(source_root),
            search_paths,
        )
    except SourcePreflightRejected:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        _fail()


def preflight(
    *, binding_raw: bytes, expected_binding_sha256: str, entry_raw: bytes, observer_raw: bytes
) -> SourceObservation:
    """Validate the canonical source closure and return source-only observation."""
    if (
        SOURCE_ROOT != Path("/opt/quantmesh")
        or ENTRY_PATH != Path("/opt/quantmesh/worker_entry.py")
        or OBSERVER_PATH != Path("/opt/quantmesh/quantmesh/research/worker_provenance.py")
        or BUILD_PATH != Path("/opt/quantmesh/quantmesh/research/worker_build.py")
        or MANIFEST_PATH != Path("/opt/quantmesh/manifest.json")
        or INVENTORY_PATH != Path("/opt/quantmesh/inventory.json")
        or BINDING_PATH != Path("/inputs/parent-binding.json")
    ):
        _fail()
    return _preflight(
        binding_raw=binding_raw,
        expected_binding_sha256=expected_binding_sha256,
        entry_raw=entry_raw,
        observer_raw=observer_raw,
    )


def revalidate(
    observation: SourceObservation, *, binding_raw: bytes, entry_raw: bytes, observer_raw: bytes
) -> None:
    """Re-read every source association and require the same sealed snapshot."""
    current = _preflight(
        binding_raw=binding_raw,
        expected_binding_sha256=observation.binding_sha256,
        entry_raw=entry_raw,
        observer_raw=observer_raw,
    )
    if current != observation:
        _fail()


def measure_runtime_before_import(observation: SourceObservation) -> dict:
    """Actual strict measurement before project/native imports, never a receipt flag."""
    revalidate(
        observation,
        binding_raw=_read(BINDING_PATH, MAX_BINDING_BYTES)[0],
        entry_raw=_read(ENTRY_PATH, MAX_SOURCE_BYTES)[0],
        observer_raw=_read(OBSERVER_PATH, MAX_SOURCE_BYTES)[0],
    )
    raw = _read(BUILD_PATH, MAX_SOURCE_BYTES)[0]
    with _verified_builder(BUILD_PATH, raw) as builder:
        return builder.measure_worker_runtime(
            MANIFEST_PATH, manifest_sha256=observation.manifest_sha256
        )
