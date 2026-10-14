"""Fixed, fail-closed entry for the isolated Linux research Worker."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
import types
from pathlib import Path

_ROOT = Path("/opt/quantmesh")
_ENTRY = _ROOT / "worker_entry.py"
_OBSERVER = _ROOT / "quantmesh/research/worker_provenance.py"
_BINDING = Path("/inputs/parent-binding.json")
_MANIFEST = _ROOT / "manifest.json"
_INVENTORY = _ROOT / "inventory.json"
_REJECT = "worker entry rejected"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_BINDING_KEYS = frozenset(
    {
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
    }
)
_BINDING_DIGESTS = _BINDING_KEYS - {
    "schema",
    "engine_id",
    "image_id",
    "container_id",
    "owner_nonce",
    "expected_prefix",
    "python_version",
}


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


def _read(path: Path, limit: int) -> bytes:
    descriptors: list[int] = []
    try:
        parts = path.parts
        if not path.is_absolute() or not parts or parts[0] != "/" or ".." in parts:
            raise ValueError
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(parent)
        held: list[tuple[int, str, tuple[int, ...]]] = []
        for part in parts[1:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(following)
            info = os.fstat(following)
            named = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _signature(info) != _signature(named):
                raise ValueError
            held.append((parent, part, _signature(info)))
            parent = following
        fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent,
        )
        descriptors.append(fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= limit
        ):
            raise ValueError
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(8192, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (
            _signature(before) != _signature(after)
            or _signature(after) != _signature(named)
            or len(raw) != before.st_size
        ):
            raise ValueError
        for directory_fd, name, identity in held:
            if _signature(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != identity:
                raise ValueError
        return bytes(raw)
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
            raise ValueError
        result[key] = value
    return result


def _runtime_supported() -> bool:
    flags = sys.flags
    return (
        sys.platform == "linux"
        and platform.machine() == "x86_64"
        and sys.version_info[:3] == (3, 12, 15)
        and sys.executable == "/usr/local/bin/python3"
        and sys.prefix == "/usr/local"
        and flags.dont_write_bytecode
        and flags.isolated
        and flags.no_site
        and flags.no_user_site
        and flags.ignore_environment
        and flags.safe_path
    )


def _arguments(argv: list[str]) -> bool:
    return (
        argv
        == [
            "--binding",
            str(_BINDING),
            "--manifest",
            str(_MANIFEST),
            "--inventory",
            str(_INVENTORY),
            "--binding-sha256",
            argv[-1] if argv else "",
        ]
        and len(argv) == 8
        and bool(_DIGEST.fullmatch(argv[-1]))
    )


def _decode_binding(raw: bytes, expected_sha256: str) -> dict:
    if (
        type(raw) is not bytes
        or not 0 < len(raw) <= 16 * 1024
        or not isinstance(expected_sha256, str)
        or not _DIGEST.fullmatch(expected_sha256)
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValueError
    value = json.loads(raw, object_pairs_hook=_pairs)
    if type(value) is not dict or set(value) != _BINDING_KEYS:
        raise ValueError
    if value.get("schema") != 1 or type(value.get("schema")) is not int:
        raise ValueError
    if (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
        != raw
    ):
        raise ValueError
    for key in _BINDING_KEYS - {"schema"}:
        item = value[key]
        if (
            type(item) is not str
            or not item
            or len(item) > 256
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in item)
        ):
            raise ValueError
    if any(not _DIGEST.fullmatch(value[key]) for key in _BINDING_DIGESTS):
        raise ValueError
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", value["image_id"])
        or not re.fullmatch(r"[0-9a-f]{64}", value["container_id"])
        or not re.fullmatch(r"[0-9a-f]{32}", value["owner_nonce"])
        or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value["engine_id"])
        or value["expected_prefix"] != "/usr/local"
        or value["python_version"] != "3.12.15"
    ):
        raise ValueError
    return value


def _execute_child_after_preflight(revalidate, child_main) -> None:
    """Revalidate source immediately before and after the pinned child call."""
    revalidate()
    child_main()
    revalidate()


def _run() -> int:
    if not _runtime_supported() or sys.argv[0] != str(_ENTRY):
        raise ValueError
    if not _arguments(sys.argv[1:]):
        raise ValueError
    expected_sha = sys.argv[-1]
    binding_raw = _read(_BINDING, 16 * 1024)
    binding = _decode_binding(binding_raw, expected_sha)
    entry_raw = _read(_ENTRY, 32 * 1024 * 1024)
    observer_raw = _read(_OBSERVER, 32 * 1024 * 1024)
    if (
        binding.get("entry_sha256") != hashlib.sha256(entry_raw).hexdigest()
        or binding.get("observer_sha256") != hashlib.sha256(observer_raw).hexdigest()
    ):
        raise ValueError
    observer_name = "quantmesh_worker_provenance_pinned"
    if observer_name in sys.modules:
        raise ValueError
    observer = types.ModuleType(observer_name)
    observer.__file__ = str(_OBSERVER)
    observer.__package__ = ""
    observer.__spec__ = None
    sys.modules[observer_name] = observer
    try:
        exec(compile(observer_raw, str(_OBSERVER), "exec", dont_inherit=True), observer.__dict__)
    except BaseException:
        sys.modules.pop(observer_name, None)
        raise
    observation = observer.preflight(
        binding_raw=binding_raw,
        expected_binding_sha256=expected_sha,
        entry_raw=entry_raw,
        observer_raw=observer_raw,
    )
    for path in observation.search_paths:
        if path not in sys.path:
            sys.path.append(path)
    # All source/package associations are now bound. This is the first project
    # import; existing runtime, Reader, result and publication guards stay intact.
    from quantmesh.research.job_runner import _child_main

    def revalidate() -> None:
        observer.revalidate(
            observation,
            binding_raw=_read(_BINDING, 16 * 1024),
            entry_raw=_read(_ENTRY, 32 * 1024 * 1024),
            observer_raw=_read(_OBSERVER, 32 * 1024 * 1024),
        )

    _execute_child_after_preflight(
        revalidate,
        lambda: _child_main(
            "/inputs",
            output_directory="/output",
            build_manifest=_MANIFEST,
            manifest_sha256=observation.manifest_sha256,
        ),
    )
    return 0


def main() -> int:
    try:
        return _run()
    except BaseException:
        sys.stderr.write(_REJECT + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
