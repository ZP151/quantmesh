"""Read-only byte admission and actual Worker fingerprints, without Git.

An externally pinned manifest identifies measured files, not an OCI certificate.
Image identity, ELF edges, notices and native qualification remain separate gates.
No environment variable, saved runtime tuple or qualification boolean is accepted.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import stat
import sys
import types
from dataclasses import dataclass
from pathlib import Path

LINUX_LOCK_SHA256 = "07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a"
_JSON_LIMIT = 4 * 1024 * 1024
_FILE_LIMIT = 512 * 1024 * 1024
_ENTRY_LIMIT = 20000
_distributions = importlib.metadata.distributions


class WorkerBuildRejected(ValueError):
    """Sanitized source/runtime rejection; never echo a manifest or host path."""


@dataclass(frozen=True, slots=True)
class ParentBindingContract:
    """Parsed structure only; this record does not grant image or Worker admission."""

    schema: int
    engine_id: str
    image_id: str
    image_config_sha256: str
    container_id: str
    owner_nonce: str
    manifest_sha256: str
    inventory_sha256: str
    dependency_lock_sha256: str
    python_executable_sha256: str
    entry_sha256: str
    observer_sha256: str
    expected_prefix: str
    python_version: str
    kernel_profile_sha256: str


_PARENT_BINDING_LIMIT = 16 * 1024
_PARENT_BINDING_KEYS = frozenset(
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
_PARENT_BINDING_DIGESTS = frozenset(
    {
        "image_config_sha256",
        "manifest_sha256",
        "inventory_sha256",
        "dependency_lock_sha256",
        "python_executable_sha256",
        "entry_sha256",
        "observer_sha256",
        "kernel_profile_sha256",
    }
)


def parse_parent_binding(raw: bytes, *, expected_sha256: str) -> ParentBindingContract:
    """Validate bounded canonical parent-binding bytes, without granting authority.

    The caller must obtain ``expected_sha256`` from the trusted parent/argv
    boundary. This function verifies only exact bytes and field relationships;
    it does not verify an Engine, container, image, kernel profile, or runtime.
    """
    try:
        if (
            type(raw) is not bytes
            or not 0 < len(raw) <= _PARENT_BINDING_LIMIT
            or not _sha(expected_sha256)
            or hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_pairs)
        if type(value) is not dict or set(value) != _PARENT_BINDING_KEYS:
            raise ValueError
        if _canonical(value) != raw:
            raise ValueError
        if type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError
        for key in _PARENT_BINDING_KEYS - {"schema"}:
            item = value[key]
            if type(item) is not str or not item or len(item) > 256:
                raise ValueError
            if any(ord(char) < 0x20 or ord(char) == 0x7F for char in item):
                raise ValueError
        if any(not _sha(value[key]) for key in _PARENT_BINDING_DIGESTS):
            raise ValueError
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value["image_id"]):
            raise ValueError
        if not re.fullmatch(r"[0-9a-f]{64}", value["container_id"]):
            raise ValueError
        if not re.fullmatch(r"[0-9a-f]{32}", value["owner_nonce"]):
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value["engine_id"]):
            raise ValueError
        if value["expected_prefix"] != "/usr/local":
            raise ValueError
        if not re.fullmatch(r"3\.12\.\d{1,3}", value["python_version"]):
            raise ValueError
        return ParentBindingContract(**value)
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise WorkerBuildRejected("worker binding rejected") from None


def encode_parent_binding(contract: ParentBindingContract) -> tuple[bytes, str]:
    """Serialize a trusted parent binding, validating it before returning its pin.

    The returned digest must be delivered through the fixed parent-to-controller
    launch channel. Reading the digest back from the binding file would make the
    check self-authenticating and is deliberately not supported here.
    """
    try:
        if type(contract) is not ParentBindingContract:
            raise ValueError
        value = {key: getattr(contract, key) for key in _PARENT_BINDING_KEYS}
        raw = _canonical(value)
        digest = hashlib.sha256(raw).hexdigest()
        parse_parent_binding(raw, expected_sha256=digest)
        return raw, digest
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise WorkerBuildRejected("worker binding rejected") from None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _path(value: object) -> Path:
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError
    for parent in path.parents:
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError
    return path


def _read(path: Path, limit: int, *, allow_empty: bool = False) -> bytes:
    """Read one unchanged regular inode; no links, devices or unbounded input."""
    path = _path(str(path))
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not int(not allow_empty) <= before.st_size <= limit:
            raise ValueError
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 512 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after, named = os.fstat(fd), path.lstat()

        def identity(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        if (
            identity(before) != identity(after)
            or identity(after) != identity(named)
            or len(raw) != before.st_size
        ):
            raise ValueError
        return raw
    finally:
        os.close(fd)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _json(path: Path, expected: str) -> dict:
    if not _sha(expected):
        raise ValueError
    raw = _read(path, _JSON_LIMIT)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError
    data = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(data, dict):
        raise ValueError
    return data


def _inventory(path: Path, expected: str) -> dict[str, str]:
    data = _json(path, expected)
    if set(data) != {"roots", "files", "symlinks"}:
        raise ValueError
    files, links = data["files"], data["symlinks"]
    if (
        not isinstance(files, dict)
        or not isinstance(links, dict)
        or not files
        or len(files) + len(links) > _ENTRY_LIMIT
    ):
        raise ValueError
    if not isinstance(data["roots"], list) or not data["roots"] or len(data["roots"]) > 32:
        raise ValueError
    roots = [_path(p) for p in data["roots"]]
    if len(set(roots)) != len(roots) or any(
        not p.is_dir() or p.is_symlink() or p == Path(p.anchor) for p in roots
    ):
        raise ValueError
    if any(a != b and a.is_relative_to(b) for a in roots for b in roots):
        raise ValueError
    measured = set()
    for root in roots:
        for item in root.rglob("*"):
            if item.is_symlink() or item.is_file():
                measured.add(str(item))
                if len(measured) > _ENTRY_LIMIT:
                    raise ValueError
            elif not item.is_dir():
                raise ValueError
    if measured != set(files) | set(links) or set(files) & set(links):
        raise ValueError
    for name, digest in files.items():
        item = _path(name)
        if not _sha(digest) or item.suffix in {".pyc", ".pyo"}:
            raise ValueError
        if hashlib.sha256(_read(item, _FILE_LIMIT, allow_empty=True)).hexdigest() != digest:
            raise ValueError
    for name, target in links.items():
        item = _path(name)
        if not isinstance(target, str) or not item.is_symlink() or os.readlink(item) != target:
            raise ValueError
        try:
            resolved = item.resolve(strict=True)
        except RuntimeError:
            # Python3.12 reports symlink loops as path-bearing RuntimeError.
            raise ValueError from None
        if not any(resolved.is_relative_to(root) for root in roots) or (
            resolved.is_file() and str(resolved) not in files
        ):
            raise ValueError
    return files


def _interpreter_pin(executable: Path, prefix: Path, files: dict, links: dict) -> tuple:
    """Repin only explicitly inventoried interpreter links and their file bytes."""

    def signature(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
            info.st_uid,
            info.st_gid,
            info.st_nlink,
        )

    current, chain, seen = executable, [], set()
    while current.is_symlink():
        if len(chain) >= 32 or str(current) in seen:
            raise ValueError
        seen.add(str(current))
        before = current.lstat()
        target = os.readlink(current)
        if links.get(str(current)) != target:
            raise ValueError
        chain.append((current, signature(before), target))
        following = Path(target) if Path(target).is_absolute() else current.parent / target
        current = _path(os.path.normpath(str(following)))
        if not current.is_relative_to(prefix):
            raise ValueError
    if str(current) not in files or not current.is_relative_to(prefix):
        raise ValueError
    before = current.lstat()
    digest = hashlib.sha256(_read(current, _FILE_LIMIT)).hexdigest()
    if digest != files[str(current)] or signature(before) != signature(current.lstat()):
        raise ValueError
    for alias, identity, target in chain:
        if signature(alias.lstat()) != identity or os.readlink(alias) != target:
            raise ValueError
    return digest, str(current), signature(before), tuple(chain)


def _pins(path: Path) -> dict[str, str]:
    raw = _read(path, _JSON_LIMIT)
    if hashlib.sha256(raw).hexdigest() != LINUX_LOCK_SHA256:
        raise ValueError
    result = {}
    for line in raw.decode().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==(\S+) --hash=sha256:([0-9a-f]{64})", line)
        if not match:
            raise ValueError
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in result:
            raise ValueError
        result[name] = match[2]
    if len(result) != 81:
        raise ValueError
    return result


def _originless_helper(name: str, module: object, modules: dict, files: dict) -> bool:
    """Bind only the two observed non-native helper shapes, without calling hooks.

    Native Cython caches deliberately remain refused: type slots alone do not
    attest instance/descriptor callback payloads. This is not image admission.
    """
    if name == "cython_runtime":
        if type(module) is not types.ModuleType:
            raise ValueError
        raw = types.ModuleType.__getattribute__(module, "__dict__")
        if any(type(key) is not str for key in raw):
            raise ValueError
        metadata = {"__name__", "__doc__", "__loader__", "__package__", "__spec__"}
        if set(raw) not in (metadata, metadata | {"cline_in_traceback"}):
            raise ValueError
        if type(raw["__name__"]) is not str or raw["__name__"] != name:
            raise ValueError
        if any(raw[key] is not None for key in metadata - {"__name__"}):
            raise ValueError
        if "cline_in_traceback" in raw and type(raw["cline_in_traceback"]) is not bool:
            raise ValueError
        return True
    if name not in {"typing.io", "typing.re"}:
        return False
    if sys.version_info[:2] != (3, 12):
        raise ValueError
    typing = modules.get("typing")
    if type(typing) is not types.ModuleType:
        raise ValueError
    namespace = types.ModuleType.__getattribute__(typing, "__dict__")
    if any(type(key) is not str for key in namespace):
        raise ValueError
    path = _path(namespace["__file__"])
    source = _read(path, _JSON_LIMIT)
    if hashlib.sha256(source).hexdigest() != files.get(str(path)):
        raise ValueError
    suffix = name.split(".")[1]
    meta = namespace["_DeprecatedType"]
    if type(meta) is not type or type(module) is not meta or module is not namespace[suffix]:
        raise ValueError
    meta_raw = type.__getattribute__(meta, "__dict__")
    if (
        set(meta_raw) != {"__module__", "__doc__", "__getattribute__"}
        or type(meta_raw["__module__"]) is not str
        or meta_raw["__module__"] != "typing"
        or meta_raw["__doc__"] is not None
        or type.__getattribute__(meta, "__bases__") != (type,)
    ):
        raise ValueError
    method = meta_raw["__getattribute__"]
    if type(method) is not types.FunctionType or method.__globals__ is not namespace:
        raise ValueError

    # Compile measured bytes without executing them; compare the actual defining
    # function with its code in that source, rather than trusting co_filename.
    def named_code(code, wanted):
        matches = [c for c in code.co_consts if type(c) is types.CodeType and c.co_name == wanted]
        if len(matches) != 1:
            raise ValueError
        return matches[0]

    try:
        expected = named_code(
            named_code(compile(source, str(path), "exec", dont_inherit=True), "_DeprecatedType"),
            "__getattribute__",
        )
    except SyntaxError:
        raise ValueError from None
    if (
        method.__code__ != expected
        or method.__code__.co_filename != str(path)
        or method.__defaults__ is not None
        or method.__kwdefaults__ is not None
        or method.__annotations__
        or not method.__closure__
        or len(method.__closure__) != 1
        or method.__closure__[0].cell_contents is not meta
    ):
        raise ValueError
    members = ("IO", "TextIO", "BinaryIO") if suffix == "io" else ("Pattern", "Match")
    raw = type.__getattribute__(module, "__dict__")
    if (
        set(raw) != set(members) | {"__module__", "__doc__", "__all__", "__dict__", "__weakref__"}
        or type(raw["__module__"]) is not str
        or raw["__module__"] != "typing"
        or type(raw["__doc__"]) is not str
        or type(raw["__all__"]) is not list
        or any(type(member) is not str for member in raw["__all__"])
        or raw["__all__"] != list(members)
        or type.__getattribute__(module, "__bases__") != (object,)
        or type.__getattribute__(module, "__name__") != name
        or any(raw[key] is not namespace[key] for key in members)
    ):
        raise ValueError
    for key in ("__dict__", "__weakref__"):
        descriptor = raw[key]
        if (
            type(descriptor) is not types.GetSetDescriptorType
            or descriptor.__objclass__ is not module
            or descriptor.__name__ != key
        ):
            raise ValueError
    return True


def measure_worker_runtime(manifest_path: Path, *, manifest_sha256: str) -> dict:
    """Validate pinned actual bytes, then collect the unchanged five runtime fields.

    The caller supplies the manifest SHA from independent image admission. This
    function grants no Linux activation or image/native certificate by itself.
    """
    try:
        data = _json(Path(manifest_path), manifest_sha256)
        if set(data) != {
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
            raise ValueError
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError
        if not isinstance(data["source_commit"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", data["source_commit"]
        ):
            raise ValueError
        source, prefix, executable = (
            _path(data[key]) for key in ("source_root", "prefix", "python_executable")
        )
        if (
            sys.platform != "linux"
            or sys.version_info[:2] != (3, 12)
            or platform.machine() != "x86_64"
            or not sys.dont_write_bytecode
            or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"
            or Path(sys.prefix) != prefix
            or Path(sys.executable) != executable
            or not executable.is_relative_to(prefix)
        ):
            raise ValueError
        files = _inventory(_path(data["inventory_path"]), data["inventory_sha256"])
        required = [source, prefix]
        inventory = _json(_path(data["inventory_path"]), data["inventory_sha256"])
        if any(str(root) not in inventory["roots"] for root in required):
            raise ValueError
        roots = [_path(root) for root in inventory["roots"]]
        for key in ("library_paths", "notice_paths"):
            if (
                not isinstance(data[key], list)
                or not data[key]
                or len(set(data[key])) != len(data[key])
            ):
                raise ValueError
            if any(str(_path(p)) not in files for p in data[key]):
                raise ValueError
        if str(_path(data["lock_path"])) not in files:
            raise ValueError
        interpreter = _interpreter_pin(executable, prefix, files, inventory["symlinks"])
        pins = _pins(_path(data["lock_path"]))
        declared = data["source_files"]
        if not isinstance(declared, dict) or not declared:
            raise ValueError
        if any(p.is_symlink() for p in (source / "quantmesh").rglob("*")):
            raise ValueError
        source_files = {
            p.relative_to(source).as_posix(): files[str(p)]
            for p in sorted((source / "quantmesh").rglob("*.py"))
            if not p.is_symlink()
        }
        if source_files != declared:
            raise ValueError
        admitted_source = {str(source / relative) for relative in source_files}
        if str(_path(str(Path(__file__)))) not in admitted_source:
            raise ValueError
        for name, module in tuple(sys.modules.items()):
            if module is None:
                continue
            if name != "quantmesh" and not name.startswith("quantmesh."):
                if _originless_helper(name, module, sys.modules, files):
                    continue
                # Installed RECORDs cannot attest code imported before admission.
                # Bind every active non-QuantMesh file (including stdlib/extensions)
                # to the measured closure, and every package search root. A venv's
                # base stdlib can legitimately live outside its distribution prefix.
                origin = getattr(module, "__file__", None)
                spec_origin = getattr(getattr(module, "__spec__", None), "origin", None)
                if name == "__main__" and origin in admitted_source:
                    # -m / the trusted file entry can alias admitted QuantMesh code.
                    # Inline -c/stdin code is deliberately not an admitted image entry.
                    if spec_origin not in {None, origin} or getattr(module, "__path__", None):
                        raise ValueError
                    continue
                for candidate in (origin, spec_origin):
                    if candidate and candidate not in {"built-in", "frozen"}:
                        path = _path(candidate)
                        if str(path) not in files:
                            raise ValueError
                if origin and spec_origin not in {None, "built-in", "frozen", origin}:
                    raise ValueError
                namespace = getattr(module, "__path__", None)
                if namespace is not None:
                    if not namespace:
                        raise ValueError
                    for candidate in namespace:
                        path = _path(str(candidate))
                        if (
                            not any(path.is_relative_to(root) for root in roots)
                            or not path.is_dir()
                            or path.is_symlink()
                        ):
                            raise ValueError
                elif not origin and spec_origin not in {"built-in", "frozen"}:
                    raise ValueError
                continue
            origin = getattr(module, "__file__", None)
            if origin:
                if str(_path(origin)) not in admitted_source:
                    raise ValueError
            else:
                namespace = getattr(module, "__path__", None)
                if not namespace or any(
                    not _path(str(p)).is_relative_to(source) for p in namespace
                ):
                    raise ValueError
        dependencies, actual = [], {}
        for dist in _distributions():
            metadata_root = _path(os.path.abspath(dist.locate_file("")))
            if not metadata_root.is_relative_to(prefix) or not dist.files:
                raise ValueError
            for entry in dist.files:
                origin = _path(os.path.abspath(dist.locate_file(entry)))
                if origin.suffix == ".pyc" and not origin.exists():
                    continue
                if not origin.is_relative_to(prefix) or str(origin) not in files:
                    raise ValueError
            name = dist.metadata["Name"]
            normalized = re.sub(r"[-_.]+", "-", name).lower()
            if normalized in actual:
                raise ValueError
            actual[normalized] = dist.version
            hashes = {
                key: hashlib.sha256((dist.read_text(key) or "").encode()).hexdigest()
                for key in ("METADATA", "RECORD", "direct_url.json")
            }
            dependencies.append((name, dist.version, hashes))
        if actual != pins:
            raise ValueError
        if _interpreter_pin(executable, prefix, files, inventory["symlinks"]) != interpreter:
            raise ValueError
        executable_digest = interpreter[0]
        dependency = hashlib.sha256(
            _canonical(
                dict(
                    packages=[json.loads(d) for d in sorted({_canonical(d) for d in dependencies})],
                    python_version=sys.version,
                    python_executable_digest=executable_digest,
                    platform=sys.platform,
                    machine=platform.machine(),
                )
            )
        ).hexdigest()
        return dict(
            build_digest=hashlib.sha256(_canonical(sorted(source_files.items()))).hexdigest(),
            dependency_digest=dependency,
            git_commit=data["source_commit"],
            python_version=sys.version,
            python_executable_digest=executable_digest,
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise WorkerBuildRejected("worker build rejected") from None
