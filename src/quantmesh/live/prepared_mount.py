"""Read-only verification of one operator-prepared fixed live filesystem.

Root is the preparation/deployment trust authority. This module never mounts,
opens a raw device/backing, repairs data or issues a capacity approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

CAPACITY = 16_777_216
RECEIPT_BASE = Path("/run/quantmesh-live-prepared")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("prepared mount metadata exceeds bound")
    return raw


def _check_receipt_stat(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != 0
        or value.st_gid != 0
        or stat.S_IMODE(value.st_mode) != 0o444
        or value.st_nlink != 1
        or not 0 < value.st_size <= 16384
    ):
        raise ValueError("prepared receipt ownership unavailable")


def _read_receipt(path: Path) -> bytes:
    if os.name != "posix":
        raise ValueError("prepared mount requires POSIX")
    for parent in path.parents:
        metadata = parent.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or metadata.st_mode & 0o022
        ):
            raise ValueError("prepared receipt parent unavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        _check_receipt_stat(before)
        chunks, remaining = [], 16385
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(raw) != before.st_size:
            raise ValueError("prepared receipt changed")
        _check_receipt_stat(after)
        return raw
    finally:
        os.close(descriptor)


def _directory(value: os.stat_result) -> dict:
    return {
        "dev": value.st_dev,
        "ino": value.st_ino,
        "uid": value.st_uid,
        "gid": value.st_gid,
        "mode": stat.S_IMODE(value.st_mode),
        "kind": "directory" if stat.S_ISDIR(value.st_mode) else "foreign",
    }


def _deployment() -> dict:
    executable = Path(sys.executable).resolve()
    info = executable.stat()
    folder = Path(__file__).parent
    return {
        "buffer_sha256": hashlib.sha256(_bounded(folder / "buffer.py", 262144)).hexdigest(),
        "verifier_sha256": hashlib.sha256(_bounded(Path(__file__), 262144)).hexdigest(),
        "python_executable": str(executable),
        "python_dev": info.st_dev,
        "python_ino": info.st_ino,
        "python_version": sys.version,
        "duckdb_version": duckdb.__version__,
    }


def _mount_id(descriptor: int) -> int:
    lines = _bounded(Path(f"/proc/self/fdinfo/{descriptor}"), 4096).decode().splitlines()
    values = [int(line.split(":", 1)[1]) for line in lines if line.startswith("mnt_id:")]
    if len(values) != 1:
        raise ValueError("mount identity unavailable")
    return values[0]


def _unescape(value: str) -> str:
    for old, new in ((r"\040", " "), (r"\011", "\t"), (r"\012", "\n"), (r"\134", "\\")):
        value = value.replace(old, new)
    return value


def _observe(root: Path) -> dict:
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("prepared mount requires POSIX directory support")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    live_fd = None
    try:
        live_fd = os.open("live", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        root_info, live_info = os.fstat(root_fd), os.fstat(live_fd)
        root_id, live_id = _mount_id(root_fd), _mount_id(live_fd)
        rows = _bounded(Path("/proc/self/mountinfo"), 1048576).decode().splitlines()
        selected = [line.split(" - ") for line in rows if line.split(" ", 1)[0] == str(live_id)]
        if len(selected) != 1 or len(selected[0]) != 2:
            raise ValueError("prepared mount mapping unavailable")
        before, after = selected[0][0].split(), selected[0][1].split()
        major, minor = map(int, before[2].split(":"))
        if (major, minor) != (os.major(live_info.st_dev), os.minor(live_info.st_dev)):
            raise ValueError("prepared mount device mismatch")
        sysfs = Path(f"/sys/dev/block/{major}:{minor}")

        def number(name: str) -> int:
            return int(_bounded(sysfs / name, 4096).strip())

        groups = _bounded(Path("/proc/self/cgroup"), 16384).decode().splitlines()
        cgroup = [line[3:] for line in groups if line.startswith("0::")]
        status = dict(
            line.split(":", 1)
            for line in _bounded(Path("/proc/self/status"), 65536).decode().splitlines()
            if ":" in line
        )
        if (
            len(cgroup) != 1
            or os.getuid() != os.geteuid()
            or os.getuid() <= 0
            or any(int(status[name].strip(), 16) != 0 for name in ("CapEff", "CapPrm", "CapAmb"))
            or status["NoNewPrivs"].strip() != "1"
        ):
            raise ValueError("prepared deployment privileges unavailable")
        lost = os.stat("lost+found", dir_fd=live_fd, follow_symlinks=False)
        fs = os.fstatvfs(live_fd)
        ns = Path("/proc/self/ns/mnt").stat()
        return {
            "root": _directory(root_info),
            "live": _directory(live_info),
            "lost_found": {**_directory(lost), "nlink": lost.st_nlink},
            "app_uid": os.getuid(),
            "app_gid": os.getegid(),
            "boot_id": _bounded(Path("/proc/sys/kernel/random/boot_id"), 128).decode().strip(),
            "unit_cgroup": cgroup[0],
            "deployment": _deployment(),
            "loop": {
                "major": major,
                "minor": minor,
                "offset": number("loop/offset"),
                "sizelimit": number("loop/sizelimit"),
                "capacity": number("size") * 512,
                "backing_path": _bounded(sysfs / "loop/backing_file", 4096).decode().strip(),
            },
            "filesystem": {"frsize": fs.f_frsize, "blocks": fs.f_blocks, "fsid": fs.f_fsid},
            "mount": {
                "filesystem": after[0],
                "root": _unescape(before[3]),
                "point": _unescape(before[4]),
                "options": before[5].split(","),
            },
            "namespace": [ns.st_dev, ns.st_ino],
            "root_mount_id": root_id,
            "live_mount_id": live_id,
            "root_names": sorted(os.listdir(root_fd)),
            "live_names": sorted(os.listdir(live_fd)),
        }
    finally:
        if live_fd is not None:
            os.close(live_fd)
        os.close(root_fd)


def _unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result or type(value) in (bool, float):
            raise ValueError("duplicate or non-strict prepared receipt value")
        result[key] = value
    return result


class PreparedLiveMount:
    def __init__(self, root: Path, core_sha: str, receipt_sha: str) -> None:
        self.root = root
        self.path = RECEIPT_BASE / f"{hashlib.sha256(str(root).encode()).hexdigest()}.json"
        self.receipt_sha = receipt_sha
        raw = _read_receipt(self.path)
        if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != receipt_sha:
            raise ValueError("prepared receipt digest mismatch")
        record = json.loads(raw, object_pairs_hook=_unique)
        if set(record) != {
            "schema_version",
            "core_budget_sha256",
            "deployment_receipt_sha256",
            "expires_at_utc",
            "unit_restart",
            "facts",
            "filesystem_uuid",
            "backing",
            "underlying",
            "lost_found_entries",
        }:
            raise ValueError("prepared receipt schema invalid")
        if type(record["schema_version"]) is not int or record["schema_version"] != 1:
            raise ValueError("prepared receipt schema invalid")
        if record["core_budget_sha256"] != core_sha or record["unit_restart"] != "no":
            raise ValueError("prepared receipt budget/deployment mismatch")
        digest = record["deployment_receipt_sha256"]
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or digest == "0" * 64
        ):
            raise ValueError("prepared deployment receipt missing")
        uuid.UUID(record["filesystem_uuid"])
        self.expires = datetime.fromisoformat(record["expires_at_utc"])
        if self.expires.utcoffset() != timedelta(0):
            raise ValueError("prepared expiry unavailable")
        self.record = record
        view = _observe(root)
        self.identity = {key: view[key] for key in ("namespace", "root_mount_id", "live_mount_id")}
        self._validate(view, fresh=False)

    def _validate(self, view: dict, *, fresh: bool) -> None:
        facts = self.record["facts"]
        actual = {
            key: view[key]
            for key in view
            if key
            not in {"namespace", "root_mount_id", "live_mount_id", "root_names", "live_names"}
        }
        if _canonical(facts) != _canonical(actual) or any(
            _canonical(view[key]) != _canonical(value) for key, value in self.identity.items()
        ):
            raise ValueError("prepared live mapping changed")
        if (
            datetime.now(UTC) > self.expires
            or type(view["app_uid"]) is not int
            or view["app_uid"] <= 0
        ):
            raise ValueError("prepared live unavailable")
        for key in ("root", "live"):
            value = view[key]
            if (
                value["uid"] != 0
                or value["gid"] != view["app_gid"]
                or value["mode"] != 0o1770
                or value["kind"] != "directory"
            ):
                raise ValueError("prepared directory ownership unavailable")
        lost = view["lost_found"]
        if lost["dev"] != view["live"]["dev"]:
            raise ValueError("prepared lost+found is on a foreign filesystem")
        if (lost["uid"], lost["gid"], lost["mode"], lost["kind"], lost["nlink"]) != (
            0,
            0,
            0o700,
            "directory",
            2,
        ):
            raise ValueError("prepared lost+found unavailable")
        if (
            view["root"]["dev"] == view["live"]["dev"]
            or view["root_mount_id"] == view["live_mount_id"]
        ):
            raise ValueError("prepared live is not a separate mount")
        loop, fs, mount = view["loop"], view["filesystem"], view["mount"]
        if (
            loop["offset"] != 0
            or loop["sizelimit"] != CAPACITY
            or loop["capacity"] != CAPACITY
            or not 0 < fs["blocks"] * fs["frsize"] <= CAPACITY
            or mount["filesystem"] != "ext4"
            or mount["root"] != "/"
            or mount["point"] != str(self.root / "live")
            or not {"rw", "nodev", "nosuid", "noexec"}.issubset(mount["options"])
        ):
            raise ValueError("prepared physical mapping unavailable")
        backing, underlying = self.record["backing"], self.record["underlying"]
        if (
            set(backing) != {"dev", "ino", "uid", "mode", "nlink", "size", "allocated", "path"}
            or (backing["uid"], backing["mode"], backing["nlink"], backing["size"])
            != (0, 0o600, 1, CAPACITY)
            or backing["dev"] != view["root"]["dev"]
            or backing["ino"] <= 0
            or backing["allocated"] < CAPACITY
            or backing["path"] != loop["backing_path"]
            or set(underlying) != {"dev", "ino", "uid", "gid", "mode", "kind", "nlink"}
            or (
                underlying["uid"],
                underlying["gid"],
                underlying["mode"],
                underlying["kind"],
                underlying["nlink"],
            )
            != (0, 0, 0o555, "directory", 2)
            or underlying["dev"] != view["root"]["dev"]
            or underlying["ino"] <= 0
            or self.record["lost_found_entries"] != []
        ):
            raise ValueError("prepared root witness unavailable")
        if fresh and (view["root_names"] != ["live"] or view["live_names"] != ["lost+found"]):
            raise ValueError("prepared first mount is not empty")

    def verify(self, *, fresh: bool = False) -> None:
        if hashlib.sha256(_read_receipt(self.path)).hexdigest() != self.receipt_sha:
            raise ValueError("prepared receipt changed")
        self._validate(_observe(self.root), fresh=fresh)
