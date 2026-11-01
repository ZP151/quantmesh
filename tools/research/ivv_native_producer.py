"""Feasibility-only original IVV provider check; no issuer, SDK or mutation API.

Pure mount symbols below are copied unchanged from this repository's
private_storage.py at ca0856e (SHA256 2d494084...0577d6); no upstream code.
"""

import argparse
import hashlib
import json
import os
import re
import select
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import PurePosixPath


class StorageDenied(ValueError):
    """The fixed private storage contract has not been established."""


def _need(condition, reason):
    if not condition:
        raise StorageDenied(reason)


@dataclass(frozen=True)
class Mount:
    identifier: int
    parent: int
    device: tuple
    root: str
    target: str
    options: frozenset
    optional: tuple
    filesystem: str
    superoptions: dict


def _kernel_path(raw):
    _need(re.fullmatch("(?:[^\\\\]|\\\\(?:040|011|012|134))*", raw) is not None, "mount_escape")
    value = re.sub("\\\\([0-7]{3})", lambda m: chr(int(m[1], 8)), raw)
    _need(
        value.startswith("/") and "\x00" not in value and (str(PurePosixPath(value)) == value),
        "mount_path",
    )
    _need(".." not in PurePosixPath(value).parts, "mount_path")
    return value


def _options(raw):
    result = {}
    for option in raw.split(","):
        key, sep, value = option.partition("=")
        _need(key and key not in result and (not sep or value), "mount_options")
        result[key] = value if sep else None
    return result


def parse_mountinfo(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= 262144, "mountinfo_bound")
    try:
        lines = raw.decode("utf-8", errors="strict").splitlines()
        _need(0 < len(lines) <= 1024, "mountinfo_bound")
        result, identifiers = ([], set())
        for line in lines:
            _need(line.count(" - ") == 1, "mountinfo_shape")
            front, back = line.split(" - ")
            head, tail = (front.split(" "), back.split(" "))
            _need(len(head) >= 6 and len(tail) == 3 and all(head) and all(tail), "mountinfo_shape")
            _need(all(re.fullmatch("[0-9]+", x) for x in head[:2]), "mountinfo_number")
            identifier, parent = (int(head[0]), int(head[1]))
            _need(
                0 < identifier < 2**64 and 0 < parent < 2**64 and (identifier not in identifiers),
                "mountinfo_number",
            )
            identifiers.add(identifier)
            _need(re.fullmatch("[0-9]+:[0-9]+", head[2]) is not None, "mountinfo_device")
            device = tuple(int(x) for x in head[2].split(":"))
            _need(all(x < 2**32 for x in device), "mountinfo_device")
            options = frozenset(head[5].split(","))
            _need(("rw" in options) != ("ro" in options), "mountinfo_mode")
            _need(
                all(
                    re.fullmatch(
                        "(?:(?:shared|master|propagate_from):[0-9]+|unbindable|idmapped)", x
                    )
                    for x in head[6:]
                ),
                "mountinfo_optional",
            )
            result.append(
                Mount(
                    identifier,
                    parent,
                    device,
                    _kernel_path(head[3]),
                    _kernel_path(head[4]),
                    options,
                    tuple(head[6:]),
                    tail[0],
                    _options(tail[2]),
                )
            )
        return tuple(result)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, StorageDenied):
            raise
        raise StorageDenied("mountinfo_shape") from None


def _visible_mounts(mounts):
    by_id = {m.identifier: m for m in mounts}
    groups = {}
    for mount in mounts:
        groups.setdefault(mount.target, []).append(mount)
    visible = {}
    for target in sorted(groups, key=lambda p: len(PurePosixPath(p).parts)):
        nearest = next(
            (visible[str(p)] for p in PurePosixPath(target).parents if str(p) in visible), None
        )
        _need(target == "/" or nearest is not None, "mount_parent")
        candidates = []
        for mount in groups[target]:
            ancestor, visited, hidden = (by_id.get(mount.parent), {mount.identifier}, False)
            while ancestor is not None:
                _need(ancestor.identifier not in visited, "mount_cycle")
                visited.add(ancestor.identifier)
                if ancestor.target != target:
                    _need(PurePosixPath(target).is_relative_to(ancestor.target), "mount_parent")
                    if ancestor != nearest:
                        hidden = True
                    break
                ancestor = by_id.get(ancestor.parent)
            _need(ancestor is not None or target == "/", "mount_parent")
            if not hidden:
                candidates.append(mount)
        if not candidates:
            continue
        identifiers = {m.identifier for m in candidates}
        leaves = identifiers - {m.parent for m in candidates}
        _need(len(leaves) == 1, "mount_ambiguity")
        top = by_id[next(iter(leaves))]
        chain, cursor = (set(), top)
        while cursor.identifier in identifiers:
            _need(cursor.identifier not in chain, "mount_cycle")
            chain.add(cursor.identifier)
            cursor = by_id.get(cursor.parent)
            if cursor is None:
                break
        _need(chain == identifiers, "mount_ambiguity")
        visible[target] = top
    return visible


class FeasibilityRejected(ValueError):
    """A fixed native feasibility predicate was not established."""


NONCE = "eabdda557bc641fdbda60ecd993fb2a0"
UNIT = "quantmesh-opend-console@" + NONCE + ".service"
RUNTIME = "/run/quantmesh-opend-console-" + NONCE
MACHINE = "a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191"
INVOCATION = "759f2f9421764604882bef10b67c88fa"
PROCESSES = {
    705646: (276886996, 1, "TMUX"),
    705651: (276887118, 705646, "PYTHON"),
    705711: (276887299, 705651, "VENDOR"),
}


def _require(value, code):
    if not value:
        raise FeasibilityRejected(code)


def _check_identity(value):
    _require(
        value.get("machine") == MACHINE
        and value.get("unit") == UNIT
        and value.get("invocation") == INVOCATION
        and value.get("main_pid") == 705646
        and value.get("active") == "active"
        and value.get("substate") == "running"
        and value.get("vendor_loopback11112") is True,
        "PROVIDER_IDENTITY",
    )
    rows = value.get("processes", [])
    _require(len(rows) == 3 and {x.get("pid") for x in rows} == set(PROCESSES), "PROVIDER_IDENTITY")
    for row in rows:
        start, parent, role = PROCESSES[row["pid"]]
        _require(
            row.get("start") == start
            and row.get("ppid") == parent
            and row.get("role") == role
            and row.get("uids") == [997] * 4
            and row.get("exe_verified") is True
            and row.get("mnt") == 4026532217
            and row.get("net") == 4026531833
            and row.get("cgroup_unit") == UNIT
            and row.get("caps") == 0
            and row.get("nnp") == 1,
            "PROVIDER_IDENTITY",
        )


WRITES = (
    "/var/lib/quantmesh-opend",
    "/var/lib/quantmesh-opend-stage",
    RUNTIME,
    "/tmp",
    "/var/tmp",
    "/dev/shm",
)
IMAGE = "/srv/quantmesh-opend-private-storage-20261031/provider.ext4"
IMAGE_BYTES = 33554432
PSEUDO_FILESYSTEMS = {
    "proc": "/proc",
    "sysfs": "/sys",
    "devtmpfs": "/dev",
    "devpts": "/dev/pts",
    "cgroup2": "/sys/fs/cgroup",
    "cgroup": "/sys/fs/cgroup",
    "mqueue": "/dev/mqueue",
    "securityfs": "/sys/kernel/security",
    "debugfs": "/sys/kernel/debug",
    "tracefs": "/sys/kernel/tracing",
    "pstore": "/sys/fs/pstore",
    "bpf": "/sys/fs/bpf",
    "configfs": "/sys/kernel/config",
    "fusectl": "/sys/fs/fuse/connections",
    "efivarfs": "/sys/firmware/efi/efivars",
}


def _mapping(visible, path, fs, root=None, device=None, writable=False):
    m = visible.get(path)
    _require(
        m is not None
        and m.filesystem == fs
        and (root is None or m.root == root)
        and (device is None or m.device == device)
        and ("rw" if writable else "ro") in m.options
        and (not writable or "rw" in m.superoptions),
        "WRITE_ROLE_MAPPING",
    )
    return m


def _directory(info, device, root=False):
    _require(
        info.get("kind") == "DIR"
        and info.get("device") == device
        and info.get("uid") == (0 if root else 997)
        and info.get("gid") == (0 if root else 987)
        and info.get("mode") == 0o700
        and type(info.get("inode")) is int
        and info["inode"] > 0,
        "DIRECTORY_IDENTITY",
    )


def _check_backing(actual, device):
    image = actual.get("image", {})
    loop = actual.get("loop", {})
    _require(
        image.get("kind") == "REG"
        and image.get("uid") == image.get("gid") == 0
        and image.get("mode") == 0o600
        and image.get("nlink") == 1
        and image.get("size") == IMAGE_BYTES
        and type(image.get("inode")) is int
        and image["inode"] == 1843320
        and image.get("device") == 66305,
        "UNTRUSTED_FINITE_BACKING",
    )
    parents = actual.get("ancestors", [])
    _require(
        parents
        and all(
            x.get("uid") == 0 and type(x.get("mode")) is int and not x["mode"] & 0o022
            for x in parents
        ),
        "UNTRUSTED_FINITE_BACKING",
    )
    _require(
        device[0] == 7
        and loop.get("device") == device
        and loop.get("backing_file") == IMAGE
        and loop.get("offset") == 0
        and loop.get("sizelimit") in (0, IMAGE_BYTES)
        and loop.get("size_sectors") * 512 == IMAGE_BYTES
        and loop.get("read_only") == 0
        and loop.get("block_uid") == 0
        and loop.get("block_gid") != 987
        and type(loop.get("block_mode")) is int
        and not loop["block_mode"] & 0o006,
        "UNTRUSTED_FINITE_BACKING",
    )


def _check_channels(value, visible, device):
    by_id = {m.identifier: m for m in visible.values()}
    for fd in value["fds"]:
        kind = fd.get("kind")
        mount = by_id.get(fd.get("mount_id"))
        if kind in ("SOCKET", "FIFO"):
            continue
        if (
            kind == "CHAR"
            and mount is not None
            and mount.filesystem in ("devpts", "devtmpfs", "tmpfs")
            and mount.target in ("/dev", "/dev/pts")
        ):
            continue
        _require(kind in ("REG", "DIR") and mount is not None, "WRITABLE_CHANNEL_UNPROVEN")
        if kind == "DIR" or fd.get("access") in (1, 2):
            _require(
                fd.get("device") == device or "ro" in mount.options, "WRITABLE_CHANNEL_UNPROVEN"
            )
    for mapping in value["maps"]:
        if mapping.get("inode") == 0 or not mapping.get("shared") or not mapping.get("writable"):
            continue
        _require(mapping.get("device") == device, "WRITABLE_CHANNEL_UNPROVEN")


def _storage(reader, visible):
    home = visible.get(WRITES[0])
    _require(
        home is not None and home.filesystem == "overlay" and "rw" in home.options,
        "HOME_NOT_FINITE",
    )
    upper = home.superoptions.get("upperdir", "")
    match = re.fullmatch(r"(/run/quantmesh-opend-storage-[a-f0-9]{32})/fs/home-upper", upper)
    _require(match is not None, "HOME_NOT_FINITE")
    pool = match.group(1)
    for m in visible.values():
        _require(
            not any(x.startswith(("shared:", "master:", "propagate_from:")) for x in m.optional),
            "PROPAGATION_NOT_PRIVATE",
        )
        canonical = PSEUDO_FILESYSTEMS.get(m.filesystem) == m.target and m.root == "/"
        _require("rw" not in m.options or m.target in WRITES or canonical, "WRITABLE_ESCAPE")
    runtime = _mapping(visible, RUNTIME, "ext4", "/runtime", writable=True)
    device = runtime.device
    _require(device[0] == 7, "WRITE_ROLE_MAPPING")
    _mapping(visible, pool + "/fs", "ext4", "/", device)
    pool_info = reader.path_info("provider", pool)
    _directory(pool_info, pool_info["device"], True)
    _directory(reader.path_info("provider", pool + "/fs"), device, True)
    for name, target in (("home", WRITES[0]), ("state", WRITES[1])):
        m = _mapping(visible, target, "overlay", "/", writable=True)
        expected = {
            "lowerdir": pool + "/lower-" + name,
            "upperdir": pool + "/fs/" + name + "-upper",
            "workdir": pool + "/fs/" + name + "-work",
        }
        _require(
            all(m.superoptions.get(k) == v for k, v in expected.items())
            and "volatile" not in m.superoptions,
            "WRITE_ROLE_MAPPING",
        )
        _directory(reader.path_info("provider", target), m.device)
        lower = _mapping(visible, pool + "/lower-" + name, "ext4")
        actual = reader.path_info("provider", pool + "/lower-" + name)
        original = reader.path_info("host", target)
        _directory(actual, lower.device)
        _require(
            actual["device"] == original["device"] and actual["inode"] == original["inode"],
            "LOWER_IDENTITY",
        )
        for suffix in ("-upper", "-work"):
            _directory(reader.path_info("provider", pool + "/fs/" + name + suffix), device)
    for target, root in (
        (RUNTIME, "/runtime"),
        ("/tmp", "/tmp"),
        ("/var/tmp", "/vartmp"),
        ("/dev/shm", "/shm"),
    ):
        _mapping(visible, target, "ext4", root, device, True)
        _directory(reader.path_info("provider", target), device)
    _check_backing(reader.backing(device, pool), device)
    _check_channels(reader.channels(), visible, device)
    return {"write_roles": 6, "backing_bytes": IMAGE_BYTES, "writable_escape": False}


def check_existing_provider(reader=None):
    """Closed feasibility result; injected OS test seams never count as native proof."""
    native = reader is None
    result = {
        "state": "INSUFFICIENT_NATIVE_EVIDENCE",
        "storage_feasible": False,
        "full_readiness": False,
        "native_observation": native,
        "first_failure": None,
        "cleanup": [],
        "owned_fds_closed": False,
        "SDK": 0,
        "permit": 0,
        "intent": 0,
        "service_actions": 0,
    }
    if reader is None:
        reader = PosixReader()
    try:
        _check_identity(reader.identity())
        result["provider_identity_verified"] = True
        result["endpoint_matches_fixed"] = True
        visible = _visible_mounts(parse_mountinfo(reader.mountinfo()))
        result["storage"] = _storage(reader, visible)
        reader.finish()
        result.update(state="FEASIBILITY_ONLY", storage_feasible=True)
    except FeasibilityRejected as exc:
        result["first_failure"] = {
            "code": str(exc),
            "class": "UNPROVEN"
            if str(exc) in ("WRITABLE_CHANNEL_UNPROVEN", "MANAGER_UNAVAILABLE")
            else "REJECTED",
        }
    except StorageDenied:
        result["first_failure"] = {"code": "MOUNT_GRAPH_UNPROVEN", "class": "UNPROVEN"}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        result["first_failure"] = {"code": "NATIVE_EVIDENCE_UNAVAILABLE", "class": "UNPROVEN"}
    finally:
        try:
            reader.close()
            result["owned_fds_closed"] = True
        except OSError:
            result["cleanup"].append("OWNED_FD_CLOSE_UNPROVEN")
            result.update(state="INSUFFICIENT_NATIVE_EVIDENCE", storage_feasible=False)
            if result["first_failure"] is None:
                result["first_failure"] = {"code": "OWNED_FD_CLOSE_UNPROVEN", "class": "UNPROVEN"}
    return result


class PosixReader:
    """Fixed-subject read-only Linux metadata collector. Raw values stay in RAM."""

    def __init__(self):
        self.deadline = time.monotonic() + 25
        self.fds = []
        self.close_failed = False
        self.processes = {}
        self.paths = []
        self.sysfs = []
        self.raw_mounts = None
        self.channel_snapshot = None
        self.groups = set()

    def tick(self):
        _require(time.monotonic() < self.deadline, "READ_DEADLINE")

    def keep(self, fd):
        self.fds.append(fd)
        return fd

    def directory(self, path, parent=None, magic=False):
        self.tick()
        flags = os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC
        if not magic:
            flags |= os.O_NOFOLLOW
        return self.keep(os.open(path, flags, dir_fd=parent))

    def read(self, parent, name, bound=16384):
        self.tick()
        fd = self.keep(os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent))
        raw = bytearray()
        while len(raw) <= bound:
            self.tick()
            part = os.read(fd, min(8192, bound + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        _require(len(raw) <= bound, "READ_BOUND")
        self.release(fd)
        return bytes(raw)

    def release(self, fd):
        # A failed close is not retried: the kernel may already have released it.
        self.fds.remove(fd)
        try:
            os.close(fd)
        except OSError:
            self.close_failed = True
            raise

    @staticmethod
    def parse_stat(raw, pid):
        left, sep, tail = raw.rpartition(b") ")
        _require(sep and left.startswith(str(pid).encode() + b" ("), "PROCESS_METADATA")
        values = tail.split()
        _require(
            len(values) >= 20 and values[1].isdigit() and values[19].isdigit(), "PROCESS_METADATA"
        )
        return {"pid": pid, "ppid": int(values[1]), "start": int(values[19])}

    @staticmethod
    def parse_status(raw, pid):
        keys = {
            "Pid",
            "Uid",
            "Gid",
            "Groups",
            "CapInh",
            "CapPrm",
            "CapEff",
            "CapBnd",
            "CapAmb",
            "NoNewPrivs",
        }
        fields = {}
        for line in raw.decode("ascii").splitlines():
            key, sep, value = line.partition(":")
            if key in keys:
                _require(sep and key not in fields, "PROCESS_METADATA")
                fields[key] = value.split()
        _require(set(fields) == keys and fields["Pid"] == [str(pid)], "PROCESS_METADATA")
        _require(
            all(
                len(fields[k]) == 4 and all(x.isdigit() for x in fields[k]) for k in ("Uid", "Gid")
            ),
            "PROCESS_METADATA",
        )
        _require(
            len(fields["Groups"]) <= 64 and all(x.isdigit() for x in fields["Groups"]),
            "PROCESS_METADATA",
        )
        _require(
            all(
                len(fields[k]) == 1 and re.fullmatch("[a-fA-F0-9]{1,16}", fields[k][0])
                for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
            ),
            "PROCESS_METADATA",
        )
        _require(
            len(fields["NoNewPrivs"]) == 1 and fields["NoNewPrivs"][0] in ("0", "1"),
            "PROCESS_METADATA",
        )
        return {
            "uids": [int(x) for x in fields["Uid"]],
            "gids": [int(x) for x in fields["Gid"]],
            "groups": [int(x) for x in fields["Groups"]],
            "caps": sum(
                int(fields[k][0], 16) for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
            ),
            "nnp": int(fields["NoNewPrivs"][0]),
        }

    @staticmethod
    def parse_fdinfo(raw):
        values = {}
        for line in raw.decode("ascii").splitlines():
            key, sep, value = line.partition(":")
            if key in ("flags", "mnt_id"):
                _require(sep and key not in values, "FD_METADATA")
                values[key] = value.strip()
        _require(
            set(values) == {"flags", "mnt_id"}
            and re.fullmatch("[0-7]+", values["flags"])
            and values["mnt_id"].isdigit(),
            "FD_METADATA",
        )
        return int(values["flags"], 8) & 3, int(values["mnt_id"])

    @staticmethod
    def parse_maps(raw):
        rows = raw.splitlines()
        _require(len(rows) <= 4096, "MAPS_BOUND")
        result = []
        for row in rows:
            fields = row.split(None, 5)
            _require(
                len(fields) >= 5
                and re.fullmatch(b"[a-f0-9]+-[a-f0-9]+", fields[0])
                and re.fullmatch(b"[r-][w-][x-][sp]", fields[1])
                and re.fullmatch(b"[a-f0-9]+:[a-f0-9]+", fields[3])
                and fields[4].isdigit(),
                "MAPS_METADATA",
            )
            result.append(
                {
                    "device": tuple(int(x, 16) for x in fields[3].split(b":")),
                    "inode": int(fields[4]),
                    "shared": fields[1][3:] == b"s",
                    "writable": fields[1][1:2] == b"w",
                }
            )
        return result

    @staticmethod
    def fixed_endpoint(raw, inodes):
        rows = raw.splitlines()
        _require(0 < len(rows) <= 4096, "TCP_BOUND")
        found = False
        for row in rows[1:]:
            fields = row.split()
            _require(len(fields) >= 10 and fields[9].isdigit(), "TCP_METADATA")
            if int(fields[9]) in inodes:
                found |= fields[1] == b"0100007F:2B68" and fields[3] == b"0A"
        return found

    @staticmethod
    def stamp(s):
        return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink)

    @staticmethod
    def info(s):
        kind = next(
            (
                name
                for test, name in (
                    (stat.S_ISREG, "REG"),
                    (stat.S_ISDIR, "DIR"),
                    (stat.S_ISSOCK, "SOCKET"),
                    (stat.S_ISFIFO, "FIFO"),
                    (stat.S_ISCHR, "CHAR"),
                    (stat.S_ISBLK, "BLOCK"),
                )
                if test(s.st_mode)
            ),
            "OTHER",
        )
        return {
            "kind": kind,
            "uid": s.st_uid,
            "gid": s.st_gid,
            "mode": stat.S_IMODE(s.st_mode),
            "nlink": s.st_nlink,
            "size": s.st_size,
            "device": (os.major(s.st_dev), os.minor(s.st_dev)),
            "inode": s.st_ino,
        }

    def manager(self):
        self.tick()
        command = [
            "/usr/bin/systemctl",
            "show",
            "--no-pager",
            "--property=Id,ActiveState,SubState,MainPID,InvocationID,ControlGroup",
            "--",
            UNIT,
        ]
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            close_fds=True,
        )
        data = bytearray()
        try:
            os.set_blocking(child.stdout.fileno(), False)
            limit = min(self.deadline, time.monotonic() + 2)
            while True:
                left = limit - time.monotonic()
                _require(left > 0, "MANAGER_UNAVAILABLE")
                ready, _, _ = select.select([child.stdout], [], [], left)
                _require(ready, "MANAGER_UNAVAILABLE")
                part = os.read(child.stdout.fileno(), 8193 - len(data))
                if not part:
                    break
                data.extend(part)
                _require(len(data) <= 8192, "MANAGER_UNAVAILABLE")
            _require(
                child.wait(timeout=max(0.001, limit - time.monotonic())) == 0, "MANAGER_UNAVAILABLE"
            )
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)
            child.stdout.close()
        fields = {}
        for line in data.decode("ascii").splitlines():
            key, sep, value = line.partition("=")
            _require(sep and key not in fields, "MANAGER_UNAVAILABLE")
            fields[key] = value
        _require(
            set(fields)
            == {"Id", "ActiveState", "SubState", "MainPID", "InvocationID", "ControlGroup"},
            "MANAGER_UNAVAILABLE",
        )
        _require(
            fields["MainPID"].isdigit()
            and fields["ControlGroup"].startswith("/system.slice/")
            and fields["ControlGroup"].endswith("/" + UNIT),
            "PROVIDER_IDENTITY",
        )
        return fields

    def executable(self, d, role):
        path, digest = {
            "TMUX": (
                "/usr/bin/tmux",
                "034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd",
            ),
            "PYTHON": ("/usr/bin/python3.12", None),
            "VENDOR": (
                "/opt/quantmesh/opend/10.10.7008/OpenD",
                "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601",
            ),
        }[role]
        fd = self.keep(os.open("exe", os.O_PATH | os.O_CLOEXEC, dir_fd=d))
        before = os.fstat(fd)
        published = os.stat(path, follow_symlinks=False)
        _require(
            stat.S_ISREG(published.st_mode)
            and published.st_uid == 0
            and not published.st_mode & 0o022
            and self.stamp(before) == self.stamp(published),
            "EXECUTABLE_IDENTITY",
        )
        if digest:
            public = self.keep(os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW))
            initial = os.fstat(public)
            h = hashlib.sha256()
            size = 0
            while True:
                self.tick()
                part = os.read(public, 65536)
                if not part:
                    break
                size += len(part)
                _require(size <= 67108864, "EXECUTABLE_IDENTITY")
                h.update(part)
            after = os.fstat(public)
            _require(
                self.stamp(initial) == self.stamp(before)
                and (initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns)
                == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and h.hexdigest() == digest,
                "EXECUTABLE_IDENTITY",
            )
            self.release(public)
        _require(self.stamp(os.stat("exe", dir_fd=d)) == self.stamp(before), "EXECUTABLE_IDENTITY")
        return fd, self.stamp(before)

    def process(self, pid, d):
        row = self.parse_stat(self.read(d, "stat"), pid)
        row.update(self.parse_status(self.read(d, "status"), pid))
        cg = self.read(d, "cgroup", 4096)
        _require(
            cg == b"0::" + self.manager_fields["ControlGroup"].encode() + b"\n", "PROVIDER_IDENTITY"
        )
        row["cgroup_unit"] = UNIT
        for key in ("mnt", "net"):
            link = os.readlink("ns/" + key, dir_fd=d)
            match = re.fullmatch(key + r":\[([0-9]+)\]", link)
            _require(match is not None, "NAMESPACE_IDENTITY")
            row[key] = int(match[1])
        return row

    def socket_inodes(self, d):
        directory = self.keep(
            os.open("fd", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        )
        names = sorted(os.listdir(directory), key=int)
        _require(len(names) <= 256 and all(x.isdigit() for x in names), "FD_BOUND")
        result = set()
        for name in names:
            self.tick()
            before = os.stat(name, dir_fd=directory)
            if not stat.S_ISSOCK(before.st_mode):
                continue
            link = os.readlink(name, dir_fd=directory)
            match = re.fullmatch(r"socket:\[([0-9]+)\]", link)
            _require(
                match is not None
                and int(match[1]) == before.st_ino
                and self.stamp(before) == self.stamp(os.stat(name, dir_fd=directory)),
                "FD_RACE",
            )
            result.add(int(match[1]))
        self.release(directory)
        return result

    @staticmethod
    def verify_machine(raw):
        _require(hashlib.sha256(raw).hexdigest() == MACHINE, "HOST_CONTEXT")
        return True

    def identity(self):
        _require(sys.platform == "linux" and os.geteuid() == 0, "HOST_CONTEXT")
        etc = self.directory("/etc")
        machine = self.read(etc, "machine-id", 128)
        self.verify_machine(machine)
        self.manager_fields = self.manager()
        rows = []
        proc = self.directory("/proc")
        for pid, (_, _, role) in PROCESSES.items():
            d = self.directory(str(pid), proc)
            row = self.process(pid, d)
            exe, stamp = self.executable(d, role)
            row.update(role=role, exe_verified=True)
            self.processes[pid] = (d, self.stamp(os.fstat(d)), row.copy(), exe, stamp)
            self.groups.update(row["groups"])
            self.groups.update(row["gids"])
            rows.append(row)
        self.root = self.directory("root", self.processes[705711][0], magic=True)
        inodes = self.socket_inodes(self.processes[705711][0])
        endpoint = self.fixed_endpoint(
            self.read(self.processes[705711][0], "net/tcp", 262144), inodes
        )
        return {
            "machine": MACHINE,
            "unit": self.manager_fields["Id"],
            "invocation": self.manager_fields["InvocationID"],
            "active": self.manager_fields["ActiveState"],
            "substate": self.manager_fields["SubState"],
            "main_pid": int(self.manager_fields["MainPID"]),
            "processes": rows,
            "vendor_loopback11112": endpoint,
        }

    def mountinfo(self):
        raw = self.read(self.processes[705711][0], "mountinfo", 262144)
        if self.raw_mounts is None:
            self.raw_mounts = raw
        return raw

    def held_path(self, path, root=None):
        _require(
            path.startswith("/")
            and str(PurePosixPath(path)) == path
            and ".." not in PurePosixPath(path).parts,
            "PATH_METADATA",
        )
        current = self.directory("/") if root is None else root
        for part in PurePosixPath(path).parts[1:]:
            current = self.keep(
                os.open(part, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current)
            )
            _require(not stat.S_ISLNK(os.fstat(current).st_mode), "PATH_METADATA")
        return current

    def path_info(self, scope, path):
        _require(scope in ("host", "provider"), "PATH_METADATA")
        _require(
            path in WRITES
            or re.fullmatch(
                r"/run/quantmesh-opend-storage-[a-f0-9]{32}(?:/fs(?:/(?:home|state)-(?:upper|work))?|/lower-(?:home|state))?",
                path,
            ),
            "PATH_METADATA",
        )
        fd = self.held_path(path, self.root if scope == "provider" else None)
        s = os.fstat(fd)
        self.paths.append((scope, path, fd, self.stamp(s)))
        return self.info(s)

    def backing(self, device, pool):
        _require(device[0] == 7 and 0 <= device[1] < 1048576, "UNTRUSTED_FINITE_BACKING")
        image = self.held_path(IMAGE)
        s = os.fstat(image)
        info = self.info(s)
        info["device"] = s.st_dev
        self.paths.append(("host", IMAGE, image, self.stamp(s)))
        ancestors = []
        for path in ("/", "/srv", "/srv/quantmesh-opend-private-storage-20261031"):
            fd = self.held_path(path)
            st = os.fstat(fd)
            _require(stat.S_ISDIR(st.st_mode), "UNTRUSTED_FINITE_BACKING")
            ancestors.append({"uid": st.st_uid, "mode": stat.S_IMODE(st.st_mode)})
            self.paths.append(("host", path, fd, self.stamp(st)))
        block = self.held_path("/dev/loop" + str(device[1]))
        b = os.fstat(block)
        _require(
            stat.S_ISBLK(b.st_mode) and (os.major(b.st_rdev), os.minor(b.st_rdev)) == device,
            "UNTRUSTED_FINITE_BACKING",
        )
        _require(
            not (b.st_gid in self.groups and b.st_mode & 0o060) and not b.st_mode & 0o006,
            "UNTRUSTED_FINITE_BACKING",
        )
        self.paths.append(("host", "/dev/loop" + str(device[1]), block, self.stamp(b)))
        loop = {
            "device": device,
            "block_uid": b.st_uid,
            "block_gid": b.st_gid,
            "block_mode": stat.S_IMODE(b.st_mode),
        }
        base = self.directory("/sys/block/loop" + str(device[1]), magic=True)
        for name, key in (
            ("loop/backing_file", "backing_file"),
            ("loop/offset", "offset"),
            ("loop/sizelimit", "sizelimit"),
            ("size", "size_sectors"),
            ("ro", "read_only"),
        ):
            raw = self.read(base, name, 4096).strip()
            self.sysfs.append((base, name, raw))
            if key == "backing_file":
                loop[key] = raw.decode("utf8")
            else:
                _require(raw.isdigit(), "UNTRUSTED_FINITE_BACKING")
                loop[key] = int(raw)
        return {"image": info, "ancestors": ancestors, "loop": loop}

    def channels(self):
        result = {"fds": [], "maps": []}
        for pid, (d, _, _, _, _) in self.processes.items():
            directory = self.keep(
                os.open("fd", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
            )
            names = sorted(os.listdir(directory), key=int)
            _require(len(names) <= 256 and all(x.isdigit() for x in names), "FD_BOUND")
            for name in names:
                self.tick()
                s = os.stat(name, dir_fd=directory)
                access, mount = self.parse_fdinfo(self.read(d, "fdinfo/" + name, 4096))
                after = os.stat(name, dir_fd=directory)
                _require(self.stamp(s) == self.stamp(after), "FD_RACE")
                info = self.info(s)
                info.update(access=access, mount_id=mount)
                result["fds"].append(info)
            _require(set(names) == set(os.listdir(directory)), "FD_RACE")
            self.release(directory)
            result["maps"].extend(self.parse_maps(self.read(d, "maps", 262144)))
        if self.channel_snapshot is None:
            self.channel_snapshot = result
        return result

    def verify_channels(self):
        _require(
            self.channel_snapshot is not None and self.channels() == self.channel_snapshot,
            "CHANNEL_RACE",
        )

    def finish(self):
        self.verify_channels()
        _require(
            self.fixed_endpoint(
                self.read(self.processes[705711][0], "net/tcp", 262144),
                self.socket_inodes(self.processes[705711][0]),
            ),
            "ENDPOINT_RACE",
        )
        _require(self.manager() == self.manager_fields, "PROVIDER_RACE")
        _require(self.mountinfo() == self.raw_mounts, "MOUNT_RACE")
        for pid, (d, stamp, row, exe, exe_stamp) in self.processes.items():
            _require(
                self.stamp(os.fstat(d)) == stamp
                and self.stamp(os.stat("/proc/" + str(pid))) == stamp
                and self.process(pid, d)
                == {k: v for k, v in row.items() if k not in ("role", "exe_verified")}
                and self.stamp(os.stat("exe", dir_fd=d)) == exe_stamp
                and self.stamp(os.fstat(exe)) == exe_stamp,
                "PROVIDER_RACE",
            )
        for scope, path, fd, stamp in self.paths:
            current = self.held_path(path, self.root if scope == "provider" else None)
            _require(
                self.stamp(os.fstat(fd)) == stamp and self.stamp(os.fstat(current)) == stamp,
                "PATH_RACE",
            )
        for d, name, raw in self.sysfs:
            _require(self.read(d, name, 4096).strip() == raw, "BACKING_RACE")

    def close(self):
        errors = []
        while self.fds:
            fd = self.fds.pop()
            try:
                os.close(fd)
            except OSError:
                errors.append(True)
        if errors or self.close_failed:
            raise OSError("owned descriptor close not established")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only fixed-provider feasibility; never SDK admission"
    )
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    result = check_existing_provider()
    wire = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(wire) > 16384:
        # All ordinary fields are closed and tiny; this is never a partial PASS.
        wire = (
            b'{"state":"INSUFFICIENT_NATIVE_EVIDENCE","storage_feasible":false,'
            b'"full_readiness":false,"first_failure":{"code":"OUTPUT_BOUND",'
            b'"class":"UNPROVEN"},"SDK":0,"permit":0,"intent":0,"service_actions":0}\n'
        )
    sys.stdout.buffer.write(wire)
    return 0 if result["storage_feasible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
