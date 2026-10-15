"""Concrete, fail-closed admission for the fixed Linux research Worker.

Snapshot bytes are evidence inputs, not a qualification receipt. Each call
rebinds them to the configured immutable image, host kernel state and (when
binding a child) the exact live container process.
"""

from __future__ import annotations

import email.parser
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from quantmesh.research.linux_bootstrap import verify_limits
from quantmesh.research.linux_owned import LinuxContainmentError, LinuxExecutionProfile
from quantmesh.research.worker_build import (
    ParentBindingContract,
    encode_parent_binding,
    parse_execution_profile,
    runtime_with_profile,
    validate_registered_job,
)
from quantmesh.research.worker_kernel import build_kernel_policy, verify_mountinfo

_MAX_JSON = 32 * 1024 * 1024
_MAX_POLICY = 1024 * 1024
_MAX_SOURCE_FILES = 20_000
_MAX_PACKAGES = 256
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_APPARMOR_RAW_ABI = "v5"
_CONTENT_ROOT = Path("/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256")
_SNAPSHOTS = {
    "oci_manifest_sha256": ("oci-manifest.json", _MAX_JSON),
    "oci_config_sha256": ("oci-config.json", _MAX_JSON),
    "manifest_sha256": ("manifest.json", _MAX_JSON),
    "inventory_sha256": ("inventory.json", _MAX_JSON),
    "runtime_metadata_sha256": ("runtime-metadata.json", _MAX_JSON),
    "dependency_lock_sha256": ("requirements.lock", _MAX_JSON),
    "apparmor_sha256": ("policy.apparmor", _MAX_POLICY),
    "seccomp_sha256": ("policy.seccomp.json", _MAX_POLICY),
    "compiled_policy_sha256": ("policy.compiled", _MAX_POLICY),
    "elf_map_sha256": ("elf-map.json", _MAX_JSON),
    "docker_default_sha256": ("docker-default.json", _MAX_POLICY),
}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class WorkerAdmissionRejected(LinuxContainmentError):
    """Sanitized refusal; never includes host paths or snapshot contents."""


@dataclass(frozen=True, slots=True)
class WorkerAdmissionPins:
    engine_id: str
    image_id: str
    image_config_sha256: str
    oci_manifest_sha256: str
    oci_config_sha256: str
    source_commit: str
    manifest_sha256: str
    inventory_sha256: str
    runtime_metadata_sha256: str
    dependency_lock_sha256: str
    python_executable_sha256: str
    entry_sha256: str
    observer_sha256: str
    expected_prefix: str
    python_version: str
    apparmor_name: str
    apparmor_sha256: str
    seccomp_sha256: str
    compiled_policy_sha256: str
    docker_default_sha256: str
    elf_map_sha256: str
    kernel_profile_sha256: str

    def __post_init__(self) -> None:
        hashes = (
            self.image_config_sha256,
            self.oci_manifest_sha256,
            self.oci_config_sha256,
            self.manifest_sha256,
            self.inventory_sha256,
            self.runtime_metadata_sha256,
            self.dependency_lock_sha256,
            self.python_executable_sha256,
            self.entry_sha256,
            self.observer_sha256,
            self.apparmor_sha256,
            self.seccomp_sha256,
            self.compiled_policy_sha256,
            self.docker_default_sha256,
            self.elf_map_sha256,
            self.kernel_profile_sha256,
        )
        if (
            not self.engine_id
            or not self.image_id.startswith("sha256:")
            or not _COMMIT.fullmatch(self.source_commit)
            or any(not _HEX.fullmatch(value) for value in hashes)
            or self.image_id != f"sha256:{self.oci_manifest_sha256}"
            or self.oci_config_sha256 != self.image_config_sha256
            or self.expected_prefix != "/usr/local"
            or not self.python_version.startswith("3.12.15 ")
            or not re.fullmatch(
                r"qm-worker-(?:[a-z0-9]|[a-z0-9][a-z0-9-]{0,52}[a-z0-9])", self.apparmor_name
            )
        ):
            raise LinuxContainmentError("worker_admission_failed")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _metadata_text(raw: bytes) -> tuple[str, str]:
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text, _sha(text.encode("utf-8"))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _json(raw: bytes) -> dict:
    value = json.loads(raw, object_pairs_hook=_pairs)
    if type(value) is not dict:
        raise ValueError
    return value


def _read_regular(path: Path, maximum: int, *, snapshot: bool = False) -> bytes:
    """Read a bounded regular file through held, no-follow ancestors."""
    if snapshot:
        raise WorkerAdmissionRejected("worker_admission_failed")
    return _read_absolute_regular(path, maximum)


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_uid,
        info.st_gid,
    )


def _open_absolute_directory(path: Path) -> tuple[int, list[int]]:
    descriptors = []
    try:
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError
        current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(current)
        for part in path.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(following)
            info = os.fstat(following)
            named = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _identity(info) != _identity(named):
                raise ValueError
            current = following
        return current, descriptors
    except (OSError, ValueError, TypeError):
        for fd in reversed(descriptors):
            os.close(fd)
        raise WorkerAdmissionRejected("worker_admission_failed") from None


def _read_snapshot_member(
    directory_fd: int, name: str, maximum: int, *, expected_mode: int = 0o400
) -> bytes:
    fd = None
    try:
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > maximum
            or stat.S_IMODE(before.st_mode) != expected_mode
            or before.st_uid != 1000
        ):
            raise ValueError
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(64 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(data) != before.st_size
            or _same_stat(before) != _same_stat(after)
            or _same_stat(after) != _same_stat(named)
        ):
            raise ValueError
        return bytes(data)
    except (OSError, ValueError, TypeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        if fd is not None:
            os.close(fd)


def _read_kernel_member(directory_fd: int, name: str, maximum: int) -> bytes:
    fd = None
    try:
        if name not in {
            "profiles",
            "name",
            "mode",
            "raw_abi",
            "raw_data",
            "raw_sha256",
            "abi",
            "sha256",
        }:
            raise ValueError
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(64 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(data) > maximum
            or _same_stat(before) != _same_stat(after)
            or _same_stat(after) != _same_stat(named)
        ):
            raise ValueError
        return bytes(data)
    except (OSError, ValueError, TypeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        if fd is not None:
            os.close(fd)


def _is_kernel_namespace_link(info: os.stat_result, target: str) -> bool:
    return bool(
        stat.S_ISLNK(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o444
        and info.st_uid == info.st_gid == 0
        and re.fullmatch(r"apparmorfs:\[[0-9]+\]", target)
    )


def _open_kernel_policy_profiles() -> tuple[int, list[int]]:
    """Enter only AppArmor's kernel-created namespace link at its fixed anchor.

    This link is an actual virtual kernel API, not a filesystem destination.
    All private snapshot, OCI, policy-member and process reads still use held
    no-follow ancestors. Neither job input nor operator configuration picks it.
    """
    anchor = Path("/sys/kernel/security/apparmor")
    anchor_fd, descriptors = _open_absolute_directory(anchor)
    try:
        anchor_before = os.fstat(anchor_fd)
        if anchor_before.st_uid != 0 or anchor_before.st_mode & 0o022:
            raise ValueError
        link = os.stat("policy", dir_fd=anchor_fd, follow_symlinks=False)
        target = os.readlink("policy", dir_fd=anchor_fd)
        if not _is_kernel_namespace_link(link, target):
            raise ValueError
        # Intentionally follow this one immutable-to-worker kernel namespace
        # reference. O_NOFOLLOW on it returns ENOTDIR on the actual host.
        policy_fd = os.open("policy", os.O_RDONLY | os.O_DIRECTORY, dir_fd=anchor_fd)
        descriptors.append(policy_fd)
        policy = os.fstat(policy_fd)
        if not stat.S_ISDIR(policy.st_mode) or policy.st_uid != 0 or policy.st_mode & 0o022:
            raise ValueError
        profiles_fd = os.open(
            "profiles", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=policy_fd
        )
        descriptors.append(profiles_fd)
        profiles = os.fstat(profiles_fd)
        if (
            not stat.S_ISDIR(profiles.st_mode)
            or profiles.st_uid != 0
            or profiles.st_mode & 0o022
            or _identity(profiles)
            != _identity(os.stat("profiles", dir_fd=policy_fd, follow_symlinks=False))
            or _identity(link)
            != _identity(os.stat("policy", dir_fd=anchor_fd, follow_symlinks=False))
            or target != os.readlink("policy", dir_fd=anchor_fd)
            or _identity(anchor_before) != _identity(os.fstat(anchor_fd))
        ):
            raise ValueError
        return profiles_fd, descriptors
    except (OSError, ValueError, TypeError):
        for fd in reversed(descriptors):
            os.close(fd)
        raise WorkerAdmissionRejected("worker_admission_failed") from None


def _kernel_policy_revision(info: os.stat_result, field: str, target: str) -> str:
    members = {"raw_abi": "abi", "raw_data": "raw_data", "raw_sha256": "sha256"}
    if (
        field not in members
        or not stat.S_ISLNK(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o444
        or info.st_uid != 0
        or info.st_gid != 0
    ):
        raise WorkerAdmissionRejected("worker_admission_failed")
    match = re.fullmatch(r"\.\./\.\./raw_data/([0-9]+)/" + members[field], target)
    if match is None:
        raise WorkerAdmissionRejected("worker_admission_failed")
    return match[1]


def _read_kernel_policy_bytes(profile_fd: int, namespace_fd: int) -> tuple[bytes, str, str]:
    """Resolve the three kernel references using held no-follow namespace FDs.

    No relative link is followed. Its numeric revision selects only a directory
    inside the already held kernel namespace's raw_data bank.
    """
    bank_fd = revision_fd = None
    try:
        references = {}
        for name in ("raw_abi", "raw_data", "raw_sha256"):
            info = os.stat(name, dir_fd=profile_fd, follow_symlinks=False)
            target = os.readlink(name, dir_fd=profile_fd)
            references[name] = (info, target, _kernel_policy_revision(info, name, target))
        revisions = {value[2] for value in references.values()}
        if len(revisions) != 1:
            raise ValueError
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        bank_fd = os.open("raw_data", flags, dir_fd=namespace_fd)
        revision_fd = os.open(revisions.pop(), flags, dir_fd=bank_fd)
        for fd in (bank_fd, revision_fd):
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError
        raw = _read_kernel_member(revision_fd, "raw_data", _MAX_POLICY)
        abi = _read_kernel_member(revision_fd, "abi", 32).decode("ascii").strip()
        sha = _read_kernel_member(revision_fd, "sha256", 128).decode("ascii").strip()
        for name, (info, target, _) in references.items():
            if _identity(info) != _identity(
                os.stat(name, dir_fd=profile_fd, follow_symlinks=False)
            ) or target != os.readlink(name, dir_fd=profile_fd):
                raise ValueError
        return raw, abi, sha
    except (OSError, ValueError, TypeError, UnicodeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        for fd in (revision_fd, bank_fd):
            if fd is not None:
                os.close(fd)


def _read_loaded_apparmor(expected_name: str) -> tuple[bytes, str]:
    root_fd, descriptors = _open_kernel_policy_profiles()
    try:
        entries = os.listdir(root_fd)
        if len(entries) > 1024:
            raise ValueError
        matches = [
            value
            for value in entries
            if re.fullmatch(re.escape(expected_name) + r"\.[0-9]+", value)
        ]
        if len(matches) != 1:
            raise ValueError
        profile_fd = os.open(
            matches[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        try:
            profile_info = os.fstat(profile_fd)
            profile_named = os.stat(matches[0], dir_fd=root_fd, follow_symlinks=False)
            profile_entries = set(os.listdir(profile_fd))
            required = {"name", "mode", "raw_abi", "raw_data", "raw_sha256"}
            allowed = required | {"attach", "learning_count", "sha256"}
            if (
                not stat.S_ISDIR(profile_info.st_mode)
                or _identity(profile_info) != _identity(profile_named)
                or not required <= profile_entries
                or not profile_entries <= allowed
            ):
                raise ValueError
            name = _read_kernel_member(profile_fd, "name", 256).decode("ascii").strip()
            mode = _read_kernel_member(profile_fd, "mode", 32).decode("ascii").strip()
            raw_data, raw_abi, raw_sha = _read_kernel_policy_bytes(profile_fd, descriptors[-2])
            if (
                name != expected_name
                or mode != "enforce"
                or not raw_data
                or raw_sha != _sha(raw_data)
                or _identity(profile_info) != _identity(os.fstat(profile_fd))
                or _identity(profile_info)
                != _identity(os.stat(matches[0], dir_fd=root_fd, follow_symlinks=False))
            ):
                raise ValueError
            return raw_data, raw_abi
        finally:
            os.close(profile_fd)
    except (OSError, ValueError, TypeError, UnicodeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _verify_distribution_metadata(snapshot_root: Path, runtime: dict, files: object) -> None:
    if type(files) is not dict or type(runtime.get("rows")) is not list:
        raise ValueError
    root_fd = metadata_fd = None
    root_chain = []
    try:
        root_fd, root_chain = _open_absolute_directory(snapshot_root)
        metadata_fd = os.open(
            "metadata", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        root_info = os.fstat(root_fd)
        metadata_info = os.fstat(metadata_fd)
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_IMODE(root_info.st_mode) != 0o700
            or root_info.st_uid != 1000
            or not stat.S_ISDIR(metadata_info.st_mode)
            or stat.S_IMODE(metadata_info.st_mode) != 0o700
            or metadata_info.st_uid != 1000
        ):
            raise ValueError
        expected_dirs = set()
        rows = runtime["rows"]
        for row in rows:
            directory = row.get("metadata_directory")
            if type(directory) is not str or not directory.startswith(
                "/usr/local/lib/python3.12/site-packages/"
            ):
                raise ValueError
            basename = PurePosixPath(directory).name
            if (
                not basename.endswith(".dist-info")
                or str(PurePosixPath(basename)) != basename
                or basename in {".", ".."}
                or basename in expected_dirs
            ):
                raise ValueError
            expected_dirs.add(basename)
        if set(os.listdir(metadata_fd)) != expected_dirs:
            raise ValueError
        for row in rows:
            basename = PurePosixPath(row["metadata_directory"]).name
            package_fd = os.open(
                basename,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=metadata_fd,
            )
            try:
                package_info = os.fstat(package_fd)
                if (
                    not stat.S_ISDIR(package_info.st_mode)
                    or stat.S_IMODE(package_info.st_mode) != 0o700
                    or package_info.st_uid != 1000
                ):
                    raise ValueError
                entries = set(os.listdir(package_fd))
                if entries not in (
                    {"METADATA", "RECORD"},
                    {"METADATA", "RECORD", "direct_url.json"},
                ):
                    raise ValueError
                if (
                    "direct_url.json" in entries
                    and row["raw_sha256"].get("direct_url.json") is None
                ):
                    raise ValueError
                for key in ("METADATA", "RECORD", "direct_url.json"):
                    if key in entries:
                        raw = _read_snapshot_member(package_fd, key, _MAX_JSON)
                        raw_digest = _sha(raw)
                        text, text_digest = _metadata_text(raw)
                        if (
                            row["raw_sha256"].get(key) != raw_digest
                            or row["text_sha256"].get(key) != text_digest
                            or files.get(f"{row['metadata_directory']}/{key}") != raw_digest
                        ):
                            raise ValueError
                        if key == "METADATA":
                            parsed = email.parser.Parser().parsestr(text, headersonly=True)
                            if parsed.get("Name") != row.get("name") or parsed.get(
                                "Version"
                            ) != row.get("version"):
                                raise ValueError
                    elif key == "direct_url.json":
                        if (
                            row["raw_sha256"].get(key) != _EMPTY_SHA256
                            or row["text_sha256"].get(key) != _EMPTY_SHA256
                            or f"{row['metadata_directory']}/{key}" in files
                        ):
                            raise ValueError
                    else:
                        raise ValueError
            finally:
                os.close(package_fd)
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        if metadata_fd is not None:
            os.close(metadata_fd)
        for fd in reversed(root_chain):
            os.close(fd)


def _same_stat(info: os.stat_result) -> tuple[int, ...]:
    return _identity(info)


def _read_absolute_regular(path: Path, maximum: int) -> bytes:
    descriptors = []
    try:
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError
        current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(current)
        for part in path.parts[1:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(following)
            info = os.fstat(following)
            named = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _same_stat(info) != _same_stat(named):
                raise ValueError
            current = following
        name = path.parts[-1]
        fd = os.open(
            name,
            os.O_RDONLY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=current,
        )
        descriptors.append(fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size < 0
            or before.st_size > maximum
        ):
            raise ValueError
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(64 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=current, follow_symlinks=False)
        if (
            len(data) != before.st_size
            or _same_stat(before) != _same_stat(after)
            or _same_stat(after) != _same_stat(named)
        ):
            raise ValueError
        return bytes(data)
    except (OSError, ValueError, TypeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _runtime_fingerprint(
    manifest: dict,
    inventory: dict,
    runtime_metadata: dict,
    dependency_lock: bytes,
    pins: WorkerAdmissionPins,
) -> dict:
    """Recompute the unchanged worker_build five-field tuple from pinned bytes."""
    if (
        set(manifest)
        != {
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
        }
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
        or manifest.get("source_commit") != pins.source_commit
        or manifest.get("prefix") != pins.expected_prefix
        or manifest.get("python_executable") != "/usr/local/bin/python3"
        or manifest.get("inventory_path") != "/opt/quantmesh/inventory.json"
        or manifest.get("inventory_sha256") != pins.inventory_sha256
        or type(manifest.get("source_files")) is not dict
        or type(inventory.get("files")) is not dict
        or type(inventory.get("symlinks")) is not dict
        or len(manifest["source_files"]) > _MAX_SOURCE_FILES
    ):
        raise ValueError
    files = inventory["files"]
    source_files = manifest["source_files"]
    source_root = manifest["source_root"]
    if (
        set(inventory) != {"roots", "files", "symlinks"}
        or type(files) is not dict
        or type(inventory["roots"]) is not list
        or type(inventory["symlinks"]) is not dict
        or len(files) + len(inventory["symlinks"]) > _MAX_SOURCE_FILES
        or type(manifest["lock_path"]) is not str
        or not manifest["lock_path"].startswith("/")
        or ".." in PurePosixPath(manifest["lock_path"]).parts
        or len(source_files) == 0
        or type(manifest.get("library_paths")) is not list
        or type(manifest.get("notice_paths")) is not list
        or not manifest["library_paths"]
        or not manifest["notice_paths"]
        or any(
            type(path) is not str for path in manifest["library_paths"] + manifest["notice_paths"]
        )
        or len(set(manifest["library_paths"])) != len(manifest["library_paths"])
        or len(set(manifest["notice_paths"])) != len(manifest["notice_paths"])
        or any(
            not path.startswith("/") or ".." in PurePosixPath(path).parts or path not in files
            for path in manifest["library_paths"] + manifest["notice_paths"]
        )
        or set(inventory["roots"])
        != {
            "/opt/quantmesh",
            "/usr/local",
            "/usr/lib/x86_64-linux-gnu",
            "/usr/share/doc",
        }
        or len(inventory["roots"]) != 4
    ):
        raise ValueError
    if (
        type(source_root) is not str
        or source_root != "/opt/quantmesh"
        or any(
            type(k) is not str
            or str(PurePosixPath(k)) != k
            or not k.startswith("quantmesh/")
            or ".." in PurePosixPath(k).parts
            or not _HEX.fullmatch(v)
            for k, v in source_files.items()
        )
        or any(
            files.get(f"{source_root}/{name}") != digest for name, digest in source_files.items()
        )
        or files.get(manifest["lock_path"]) != pins.dependency_lock_sha256
        or manifest["python_executable"] != "/usr/local/bin/python3"
        or inventory["symlinks"].get("/usr/local/bin/python3") != "python3.12"
        or "/usr/local/bin/python3" in files
        or "/usr/local/bin/python3.12" in inventory["symlinks"]
        or files.get("/usr/local/bin/python3.12") != pins.python_executable_sha256
        or _sha(dependency_lock) != pins.dependency_lock_sha256
    ):
        raise ValueError
    inventoried_sources = {
        path.removeprefix(f"{source_root}/"): digest
        for path, digest in files.items()
        if path.startswith(f"{source_root}/quantmesh/") and path.endswith(".py")
    }
    if inventoried_sources != source_files:
        raise ValueError
    if (
        set(runtime_metadata)
        != {"schema_version", "image_id", "python_version", "python_executable_sha256", "rows"}
        or type(runtime_metadata.get("schema_version")) is not int
        or runtime_metadata.get("schema_version") != 1
        or runtime_metadata.get("image_id") != pins.image_id
        or runtime_metadata.get("python_version") != pins.python_version
        or runtime_metadata.get("python_executable_sha256") != pins.python_executable_sha256
        or type(runtime_metadata.get("rows")) is not list
        or not 1 <= len(runtime_metadata["rows"]) <= _MAX_PACKAGES
    ):
        raise ValueError
    rows, names = [], set()
    for row in runtime_metadata["rows"]:
        if type(row) is not dict or set(row) != {
            "name",
            "version",
            "metadata_directory",
            "text_sha256",
            "raw_sha256",
        }:
            raise ValueError
        name, version, directory = row["name"], row["version"], row["metadata_directory"]
        keys = {"METADATA", "RECORD", "direct_url.json"}
        if (
            type(name) is not str
            or not name
            or type(version) is not str
            or not version
            or name in names
            or type(directory) is not str
            or not directory.startswith("/usr/local/lib/python3.12/site-packages/")
            or not directory.endswith(".dist-info")
            or type(row["text_sha256"]) is not dict
            or type(row["raw_sha256"]) is not dict
            or set(row["text_sha256"]) != keys
            or set(row["raw_sha256"]) != keys
        ):
            raise ValueError
        names.add(name)
        hashes = {}
        for key in sorted(keys):
            text_digest, raw_digest = row["text_sha256"][key], row["raw_sha256"][key]
            if not _HEX.fullmatch(text_digest) or not _HEX.fullmatch(raw_digest):
                raise ValueError
            # The inventory supplies the independent raw-byte digest. Missing
            # direct_url.json is represented by SHA256(empty), exactly as read_text.
            installed = files.get(f"{directory}/{key}")
            if installed is None:
                if key != "direct_url.json" or raw_digest != _EMPTY_SHA256:
                    raise ValueError
            elif installed != raw_digest:
                raise ValueError
            hashes[key] = text_digest
        rows.append([name, version, hashes])
    locked = {}
    for line in dependency_lock.decode("utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==(\S+) --hash=sha256:([0-9a-f]{64})", line)
        if match is None:
            raise ValueError
        normalized = re.sub(r"[-_.]+", "-", match[1]).lower()
        if normalized in locked:
            raise ValueError
        locked[normalized] = match[2]
    normalized_rows = {re.sub(r"[-_.]+", "-", row[0]).lower(): row[1] for row in rows}
    if len(locked) != 81 or len(normalized_rows) != len(rows) or normalized_rows != locked:
        raise ValueError
    packages = [json.loads(value) for value in sorted({_canonical(row) for row in rows})]
    dependency = hashlib.sha256(
        _canonical(
            {
                "packages": packages,
                "python_version": pins.python_version,
                "python_executable_digest": pins.python_executable_sha256,
                "platform": "linux",
                "machine": "x86_64",
            }
        )
    ).hexdigest()
    return {
        "build_digest": _sha(_canonical(sorted(source_files.items()))),
        "dependency_digest": dependency,
        "git_commit": pins.source_commit,
        "python_version": pins.python_version,
        "python_executable_digest": pins.python_executable_sha256,
    }


@dataclass(frozen=True, slots=True)
class WorkerImageAdmission:
    """Concrete provider consumed by ``LinuxWorkerExecution``.

    The private snapshot is required to be owned by the pinned operator UID,
    mode 0700 at its root, with mode 0400 single-link regular members.
    """

    pins: WorkerAdmissionPins
    snapshot_root: Path
    execution_profile: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_root", Path(self.snapshot_root))
        if self.execution_profile is not None:
            parse_execution_profile(self.execution_profile)

    def _snapshot(self) -> dict[str, bytes]:
        root_fd = None
        try:
            root_fd, root_chain = _open_absolute_directory(self.snapshot_root)
            root = os.fstat(root_fd)
            named = self.snapshot_root.lstat()
            if (
                not stat.S_ISDIR(root.st_mode)
                or stat.S_IMODE(root.st_mode) != 0o700
                or root.st_uid != 1000
                or _identity(root) != _identity(named)
            ):
                raise ValueError
            root_entries = set(os.listdir(root_fd))
            if root_entries != {
                *[filename for filename, _ in _SNAPSHOTS.values()],
                "metadata",
                "receipt.json",
                "empty-config",
            }:
                raise ValueError
            # This collector receipt is a non-authoritative operational record.
            # Validate its held file but never parse or trust its claims.
            _read_snapshot_member(root_fd, "receipt.json", 64 * 1024, expected_mode=0o600)
            empty_config_fd = os.open(
                "empty-config",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
            try:
                empty_info = os.fstat(empty_config_fd)
                empty_named = os.stat("empty-config", dir_fd=root_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(empty_info.st_mode)
                    or empty_info.st_uid != 1000
                    or stat.S_IMODE(empty_info.st_mode) != 0o700
                    or os.listdir(empty_config_fd)
                    or _identity(empty_info) != _identity(empty_named)
                    or _identity(empty_info) != _identity(os.fstat(empty_config_fd))
                ):
                    raise ValueError
            finally:
                os.close(empty_config_fd)
            metadata_fd = os.open(
                "metadata", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            try:
                metadata_stat = os.fstat(metadata_fd)
                metadata_named = os.stat("metadata", dir_fd=root_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(metadata_stat.st_mode)
                    or stat.S_IMODE(metadata_stat.st_mode) != 0o700
                    or metadata_stat.st_uid != 1000
                    or _identity(metadata_stat) != _identity(metadata_named)
                ):
                    raise ValueError
            finally:
                os.close(metadata_fd)
            data = {}
            for field, (filename, maximum) in _SNAPSHOTS.items():
                raw = _read_snapshot_member(root_fd, filename, maximum)
                if _sha(raw) != getattr(self.pins, field):
                    raise ValueError
                data[filename] = raw
            if _identity(root) != _identity(os.fstat(root_fd)) or _identity(root) != _identity(
                self.snapshot_root.lstat()
            ):
                raise ValueError
            return data
        except (OSError, ValueError, TypeError):
            raise WorkerAdmissionRejected("worker_admission_failed") from None
        finally:
            if root_fd is not None:
                for fd in reversed(root_chain):
                    os.close(fd)

    def _live_image(self, profile: LinuxExecutionProfile) -> None:
        p = self.pins
        try:
            observed = profile.prerequisites()
            if observed.get("engine_id") != p.engine_id or observed.get("image_id") != p.image_id:
                raise ValueError
            doc = json.loads(profile.invoke(["image", "inspect", p.image_id]))[0]
            if doc.get("Id") != p.image_id or doc.get("Os") != "linux":
                raise ValueError
            raw_manifest = _read_absolute_regular(_CONTENT_ROOT / p.oci_manifest_sha256, _MAX_JSON)
            raw_config = _read_absolute_regular(_CONTENT_ROOT / p.oci_config_sha256, _MAX_JSON)
            if (
                _sha(raw_manifest) != p.oci_manifest_sha256
                or _sha(raw_config) != p.oci_config_sha256
            ):
                raise ValueError
            oci = _json(raw_manifest)
            descriptor = oci.get("config")
            if (
                type(descriptor) is not dict
                or descriptor.get("digest") != f"sha256:{p.image_config_sha256}"
                or type(descriptor.get("size")) is not int
                or descriptor.get("size") != len(raw_config)
            ):
                raise ValueError
            config = _json(raw_config)
            image_config = config.get("config")
            rootfs = config.get("rootfs")
            rootfs_layers = rootfs.get("diff_ids") if type(rootfs) is dict else None
            inspect_config = doc.get("Config")
            inspect_layers = doc.get("RootFS", {}).get("Layers")
            fixed_entrypoint = ["/usr/local/bin/python3"]
            fixed_cmd = ["-B", "-I", "-S", "/opt/quantmesh/worker_entry.py"]
            if (
                config.get("architecture") != "amd64"
                or config.get("os") != "linux"
                or type(image_config) is not dict
                or image_config.get("User") != "10001:10001"
                or image_config.get("Entrypoint") != fixed_entrypoint
                or image_config.get("Cmd") != fixed_cmd
                or type(rootfs) is not dict
                or rootfs.get("type") != "layers"
                or type(rootfs_layers) is not list
                or not 1 <= len(rootfs_layers) <= 16
                or any(
                    type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                    for value in rootfs_layers
                )
                or type(inspect_config) is not dict
                or inspect_config.get("User") != "10001:10001"
                or inspect_config.get("Entrypoint") != fixed_entrypoint
                or inspect_config.get("Cmd") != fixed_cmd
                or inspect_layers != rootfs_layers
                or inspect_config != image_config
                or len(rootfs_layers) != len(oci["layers"])
            ):
                raise ValueError
            if not filesafe_json(oci):
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError):
            raise WorkerAdmissionRejected("worker_admission_failed") from None

    def _live_policy(self, profile: LinuxExecutionProfile, data: dict[str, bytes]) -> None:
        try:
            elf_map = _json(data["elf-map.json"])
            if type(elf_map) is not dict:
                raise ValueError
            default = data["docker-default.json"]
            policy = build_kernel_policy(
                elf_map,
                docker_default=default,
                docker_default_sha256=self.pins.docker_default_sha256,
            )
            if (
                policy.name != self.pins.apparmor_name
                or policy.apparmor != data["policy.apparmor"]
                or policy.seccomp != data["policy.seccomp.json"]
                or policy.sha256 != self.pins.kernel_profile_sha256
                or _sha(data["policy.compiled"]) != self.pins.compiled_policy_sha256
            ):
                raise ValueError
            if profile.apparmor_profile != policy.name:
                raise ValueError
            seccomp = _read_absolute_regular(Path(profile.seccomp_path), _MAX_POLICY)
            if seccomp != policy.seccomp:
                raise ValueError
            raw_loaded, raw_abi = _read_loaded_apparmor(policy.name)
            if (
                raw_abi != _APPARMOR_RAW_ABI
                or raw_loaded != data["policy.compiled"]
                or _sha(raw_loaded) != self.pins.compiled_policy_sha256
            ):
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            raise WorkerAdmissionRejected("worker_admission_failed") from None

    def verify(self, profile: LinuxExecutionProfile) -> dict:
        try:
            data = self._snapshot()
            manifest = _json(data["manifest.json"])
            inventory = _json(data["inventory.json"])
            metadata = _json(data["runtime-metadata.json"])
            _verify_distribution_metadata(self.snapshot_root, metadata, inventory.get("files"))
            runtime = _runtime_fingerprint(
                manifest, inventory, metadata, data["requirements.lock"], self.pins
            )
            self._live_image(profile)
            self._live_policy(profile, data)
            return (
                runtime
                if self.execution_profile is None
                else runtime_with_profile(runtime, self.execution_profile)
            )
        except WorkerAdmissionRejected:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            UnicodeError,
            RecursionError,
        ):
            raise WorkerAdmissionRejected("worker_admission_failed") from None

    def prepare_parent_binding(self, process, job, runtime: dict, ready: dict) -> tuple[bytes, str]:
        try:
            if (
                type(process.profile.uid) is not int
                or process.profile.uid != 10001
                or type(process.profile.gid) is not int
                or process.profile.gid != 10001
            ):
                raise ValueError
            current = self.verify(process.profile)
            if self.execution_profile is not None:
                validate_registered_job(job, self.execution_profile)
            if (
                current != runtime
                or type(ready) is not dict
                or set(ready) != {"event", "limits", "bootstrap_sha256"}
                or ready.get("limits") != process.evidence.get("limits")
                or ready.get("bootstrap_sha256") != process.evidence.get("bootstrap_sha256")
            ):
                raise ValueError
            if ready["event"] != "ready" or not _HEX.fullmatch(ready["bootstrap_sha256"]):
                raise ValueError
            verify_limits(ready["limits"], job.request.budget.memory_mib)
            doc = process._inspect(check_parent_binding=False)
            pid = doc["State"]["Pid"]
            if type(pid) is not int or pid <= 1 or doc["Id"] != process.container_id:
                raise ValueError
            before = _proc_identity(pid)
            if (
                before["uids"] != (process.profile.uid,) * 4
                or before["gids"] != (process.profile.gid,) * 4
                or before["nnp"] != 1
                or before["seccomp"] != 2
                or before["cap_eff"] != 0
                or before["apparmor_current"] != f"{self.pins.apparmor_name} (enforce)"
            ):
                raise ValueError
            verify_mountinfo(before["mountinfo"])
            _verify_cgroup(before["cgroup"], job.request.budget.memory_mib)
            after = _proc_identity(pid)
            inspected = process._inspect(check_parent_binding=False)
            if (
                before != after
                or inspected["Id"] != process.container_id
                or inspected["State"]["Pid"] != pid
                or inspected["State"]["Running"] is not True
                or self.verify(process.profile) != current
            ):
                raise ValueError
            binding = ParentBindingContract(
                schema=1 if self.execution_profile is None else 2,
                engine_id=process.evidence["engine_id"],
                image_id=self.pins.image_id,
                image_config_sha256=self.pins.image_config_sha256,
                container_id=process.container_id,
                owner_nonce=process.nonce,
                manifest_sha256=self.pins.manifest_sha256,
                inventory_sha256=self.pins.inventory_sha256,
                dependency_lock_sha256=self.pins.dependency_lock_sha256,
                python_executable_sha256=self.pins.python_executable_sha256,
                entry_sha256=self.pins.entry_sha256,
                observer_sha256=self.pins.observer_sha256,
                expected_prefix=self.pins.expected_prefix,
                python_version=self.pins.python_version.split(" ", 1)[0],
                kernel_profile_sha256=self.pins.kernel_profile_sha256,
                execution_profile=self.execution_profile,
            )
            return encode_parent_binding(binding)
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            UnicodeError,
            RecursionError,
        ):
            raise WorkerAdmissionRejected("parent_binding_failed") from None
        except LinuxContainmentError:
            raise WorkerAdmissionRejected("parent_binding_failed") from None


def filesafe_json(manifest: dict) -> bool:
    """Reject an OCI manifest whose schema or layer list is not finite/exact."""
    return (
        manifest.get("schemaVersion") == 2
        and type(manifest.get("config")) is dict
        and _HEX.fullmatch(str(manifest["config"].get("digest", "")).removeprefix("sha256:"))
        and type(manifest["config"].get("size")) is int
        and manifest["config"]["size"] > 0
        and type(manifest.get("layers")) is list
        and 1 <= len(manifest["layers"]) <= 16
        and all(
            type(layer) is dict
            and _HEX.fullmatch(str(layer.get("digest", "")).removeprefix("sha256:"))
            and type(layer.get("size")) is int
            and layer["size"] > 0
            for layer in manifest["layers"]
        )
    )


def _proc_identity(pid: int) -> dict:
    root = Path("/proc") / str(pid)
    directory_fd, descriptors = _open_absolute_directory(root)
    try:
        directory_before = os.fstat(directory_fd)
        stat_before = _read_proc_member(directory_fd, "stat", 16 * 1024).decode("ascii")
        # Comm may contain spaces/parentheses; fields after the final ')' are stable.
        rest = stat_before.rsplit(")", 1)[1].split()
        if len(rest) < 20:
            raise ValueError
        start = rest[19]
        status = _read_proc_member(directory_fd, "status", 64 * 1024).decode("ascii")
        values = {}
        for line in status.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                values[key] = value.strip()
        uids = tuple(int(value) for value in values["Uid"].split())
        gids = tuple(int(value) for value in values["Gid"].split())
        nnp, seccomp = int(values["NoNewPrivs"]), int(values["Seccomp"])
        cap_eff = int(values["CapEff"], 16)
        cgroup = _read_proc_member(directory_fd, "cgroup", 16 * 1024).decode("ascii")
        mountinfo = _read_proc_member(directory_fd, "mountinfo", 1024 * 1024)
        apparmor_current = _read_proc_attr_current(directory_fd)
        stat_after = _read_proc_member(directory_fd, "stat", 16 * 1024).decode("ascii")
        rest_after = stat_after.rsplit(")", 1)[1].split()
        directory_after = os.fstat(directory_fd)
        if (
            len(rest_after) < 20
            or rest_after[19] != start
            or _identity(directory_before) != _identity(directory_after)
            or _identity(directory_after)
            != _identity(os.stat(str(pid), dir_fd=descriptors[-2], follow_symlinks=False))
        ):
            raise ValueError
        return {
            "identity": (pid, start),
            "uids": uids,
            "gids": gids,
            "nnp": nnp,
            "seccomp": seccomp,
            "cap_eff": cap_eff,
            "cgroup": cgroup,
            "mountinfo": mountinfo,
            "apparmor_current": apparmor_current,
        }
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _read_proc_member(directory_fd: int, name: str, maximum: int, *, cgroup: bool = False) -> bytes:
    fd = None
    try:
        allowed = (
            {"memory.max", "memory.swap.max", "cpu.max", "pids.max"}
            if cgroup
            else {"stat", "status", "cgroup", "mountinfo", "current"}
        )
        if name not in allowed or (cgroup and maximum != 4096):
            raise ValueError
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or (
            cgroup and (before.st_uid != 0 or before.st_nlink != 1 or before.st_size != 0)
        ):
            raise ValueError
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(fd, min(16 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(data) > maximum
            or _same_stat(before) != _same_stat(after)
            or _same_stat(after) != _same_stat(named)
        ):
            raise ValueError
        return bytes(data)
    except (OSError, ValueError, TypeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        if fd is not None:
            os.close(fd)


def _read_proc_attr_current(directory_fd: int) -> str:
    attr_fd = None
    try:
        attr_fd = os.open(
            "attr",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(attr_fd)
        named = os.stat("attr", dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode) or _same_stat(before) != _same_stat(named):
            raise ValueError
        value = _read_proc_member(attr_fd, "current", 4096).decode("ascii").strip()
        after = os.fstat(attr_fd)
        named_after = os.stat("attr", dir_fd=directory_fd, follow_symlinks=False)
        if (
            not value
            or _same_stat(before) != _same_stat(after)
            or _same_stat(after) != _same_stat(named_after)
        ):
            raise ValueError
        return value
    except (OSError, ValueError, TypeError, UnicodeError):
        raise WorkerAdmissionRejected("worker_admission_failed") from None
    finally:
        if attr_fd is not None:
            os.close(attr_fd)


def _verify_cgroup(raw: str, memory_mib: int) -> None:
    lines = [line.split(":", 2) for line in raw.splitlines()]
    matches = [
        parts[2] for parts in lines if len(parts) == 3 and parts[0] == "0" and parts[1] == ""
    ]
    if len(matches) != 1 or not matches[0].startswith("/") or ".." in Path(matches[0]).parts:
        raise ValueError
    base = Path("/sys/fs/cgroup")
    directory = base.joinpath(*Path(matches[0]).parts[1:])
    # cgroupfs reports size zero even when limits contain bytes. Reuse the
    # bounded virtual-file reader on a held, no-follow kernel directory only.
    fd, descriptors = _open_absolute_directory(directory)
    try:
        values = {
            key: _read_proc_member(fd, key, 4096, cgroup=True).decode("ascii").strip()
            for key in ("memory.max", "memory.swap.max", "cpu.max", "pids.max")
        }
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    verify_limits(values, memory_mib)
