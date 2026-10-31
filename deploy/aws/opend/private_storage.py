"""Fixed c8 disk-image metadata admission; no credential or image-payload reads."""

import hashlib
import json
import os
import re
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath

IMAGE_BYTES = 33554432
NONCE = "c8f0d0de4ca641a491fca6df24c66ceb"
STORAGE_ROOT = "/srv/quantmesh-opend-private-storage-20261031"
PROVIDER_IMAGE = STORAGE_ROOT + "/provider.ext4"
FIXTURE_IMAGE = STORAGE_ROOT + "/fixture.ext4"
POOL = "/run/quantmesh-opend-storage-" + NONCE
HOME = "/var/lib/quantmesh-opend"
STATE = "/var/lib/quantmesh-opend-stage"
RUNTIME = "/run/quantmesh-opend-console-" + NONCE
IMAGE_ALIAS = "/etc/quantmesh/opend/private-storage-image"
PROFILE = "/etc/quantmesh/opend/private-storage.json"
WRITES = (HOME, STATE, RUNTIME, "/tmp", "/var/tmp", "/dev/shm")
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
PROFILE_FIELDS = {
    "schema_version",
    "purpose",
    "nonce",
    "image_bytes",
    "backing_file",
    "image_identity",
    "device",
    "fsid",
    "runtime_inode",
    "lower_device",
    "lower_roots",
}
IMAGE_FIELDS = {"device", "inode", "uid", "gid", "mode", "nlink", "size"}


class StorageDenied(ValueError):
    """The fixed private storage contract has not been established."""


def _need(condition, reason):
    if not condition:
        raise StorageDenied(reason)


def _uint(value, *, positive=False):
    return type(value) is int and (0 < value if positive else 0 <= value) and value < 2**64


def _device(value):
    return type(value) is list and len(value) == 2 and all(_uint(v) for v in value)


def _path(value):
    return (
        type(value) is str
        and value.startswith("/")
        and len(value) <= 4096
        and all(part and part not in {".", ".."} for part in value[1:].split("/"))
        and not any(c.isspace() or c in "\\\x00" for c in value)
    )


def validate_profile(profile):
    _need(type(profile) is dict and set(profile) == PROFILE_FIELDS, "profile_shape")
    _need(
        type(profile["schema_version"]) is int and profile["schema_version"] == 1, "profile_schema"
    )
    _need(
        profile["purpose"] == "opend_c8_private_storage" and profile["nonce"] == NONCE,
        "profile_identity",
    )
    _need(
        type(profile["image_bytes"]) is int and profile["image_bytes"] == IMAGE_BYTES, "image_size"
    )
    _need(
        type(profile["backing_file"]) is str
        and profile["backing_file"] in {PROVIDER_IMAGE, FIXTURE_IMAGE},
        "image_path",
    )
    identity = profile["image_identity"]
    _need(type(identity) is dict and set(identity) == IMAGE_FIELDS, "image_identity")
    _need(all(_uint(v) for v in identity.values()) and identity["inode"] > 0, "image_identity")
    _need(
        identity["uid"] == identity["gid"] == 0
        and identity["mode"] == 0o600
        and identity["nlink"] == 1
        and identity["size"] == IMAGE_BYTES,
        "image_identity",
    )
    _need(_device(profile["device"]) and profile["device"][0] == 7, "image_device")
    _need(profile["device"][1] < 2**20, "image_device")
    _need(_device(profile["lower_device"]), "lower_device")
    _need(
        _uint(profile["fsid"], positive=True) and _uint(profile["runtime_inode"], positive=True),
        "filesystem_identity",
    )
    roots = profile["lower_roots"]
    _need(type(roots) is dict and set(roots) == {"home", "state"}, "lower_roots")
    _need(all(_path(p) for p in roots.values()), "lower_roots")


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
    _need(re.fullmatch(r"(?:[^\\]|\\(?:040|011|012|134))*", raw) is not None, "mount_escape")
    value = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), raw)
    _need(
        value.startswith("/") and "\x00" not in value and str(PurePosixPath(value)) == value,
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
        result, identifiers = [], set()
        for line in lines:
            _need(line.count(" - ") == 1, "mountinfo_shape")
            front, back = line.split(" - ")
            head, tail = front.split(" "), back.split(" ")
            _need(len(head) >= 6 and len(tail) == 3 and all(head) and all(tail), "mountinfo_shape")
            _need(all(re.fullmatch(r"[0-9]+", x) for x in head[:2]), "mountinfo_number")
            identifier, parent = int(head[0]), int(head[1])
            _need(
                0 < identifier < 2**64 and 0 < parent < 2**64 and identifier not in identifiers,
                "mountinfo_number",
            )
            identifiers.add(identifier)
            _need(re.fullmatch(r"[0-9]+:[0-9]+", head[2]) is not None, "mountinfo_device")
            device = tuple(int(x) for x in head[2].split(":"))
            _need(all(x < 2**32 for x in device), "mountinfo_device")
            options = frozenset(head[5].split(","))
            _need(("rw" in options) != ("ro" in options), "mountinfo_mode")
            _need(
                all(
                    re.fullmatch(
                        r"(?:(?:shared|master|propagate_from):[0-9]+|unbindable|idmapped)", x
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
        # A deeper visible pathname prefix covers children of older mount-tree ancestors.
        nearest = next(
            (visible[str(p)] for p in PurePosixPath(target).parents if str(p) in visible),
            None,
        )
        _need(target == "/" or nearest is not None, "mount_parent")
        candidates = []
        for mount in groups[target]:
            ancestor, visited, hidden = by_id.get(mount.parent), {mount.identifier}, False
            while ancestor is not None:
                _need(ancestor.identifier not in visited, "mount_cycle")
                visited.add(ancestor.identifier)
                if ancestor.target != target:
                    _need(PurePosixPath(target).is_relative_to(ancestor.target), "mount_parent")
                    if ancestor != nearest:
                        hidden = True
                    # The selected ancestor already established its own ancestry.
                    # Older covered mounts above it must not hide its new children.
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
        chain, cursor = set(), top
        while cursor.identifier in identifiers:
            _need(cursor.identifier not in chain, "mount_cycle")
            chain.add(cursor.identifier)
            cursor = by_id.get(cursor.parent)
            if cursor is None:
                break
        _need(chain == identifiers, "mount_ambiguity")
        visible[target] = top
    return visible


def _mapping(visible, target, *, filesystem, root, device=None, writable=False):
    _need(target in visible, "missing_mount")
    mount = visible[target]
    _need(mount.filesystem == filesystem and mount.root == root, "mount_mapping")
    _need(device is None or mount.device == tuple(device), "mount_device")
    _need(("rw" if writable else "ro") in mount.options, "mount_mode")
    _need(not any(x.startswith("shared:") for x in mount.optional), "shared_mount")
    if writable:
        _need("rw" in mount.superoptions, "filesystem_readonly")
    return mount


def _validate_mounts(profile, snapshot):
    _need(snapshot["mountinfo"] == snapshot["mountinfo_after"], "mount_drift")
    visible = _visible_mounts(parse_mountinfo(snapshot["mountinfo"]))
    _mapping(visible, POOL + "/fs", filesystem="ext4", root="/", device=profile["device"])
    for name, target in (("home", HOME), ("state", STATE)):
        _mapping(
            visible,
            POOL + "/lower-" + name,
            filesystem="ext4",
            root=profile["lower_roots"][name],
            device=profile["lower_device"],
        )
        mount = _mapping(visible, target, filesystem="overlay", root="/", writable=True)
        expected = {
            "lowerdir": POOL + "/lower-" + name,
            "upperdir": POOL + "/fs/" + name + "-upper",
            "workdir": POOL + "/fs/" + name + "-work",
        }
        _need(all(mount.superoptions.get(k) == v for k, v in expected.items()), "overlay_mapping")
        _need("volatile" not in mount.superoptions, "volatile_overlay")
    _mapping(
        visible,
        STATE + "/" + NONCE,
        filesystem="ext4",
        root=profile["lower_roots"]["state"] + "/" + NONCE,
        device=profile["lower_device"],
    )
    _need(_device(snapshot["image_device"]), "image_device")
    _mapping(
        visible,
        IMAGE_ALIAS,
        filesystem="ext4",
        root=profile["backing_file"],
        device=snapshot["image_device"],
    )
    for target, root in (
        (RUNTIME, "/runtime"),
        ("/tmp", "/tmp"),
        ("/var/tmp", "/vartmp"),
        ("/dev/shm", "/shm"),
    ):
        _mapping(
            visible, target, filesystem="ext4", root=root, device=profile["device"], writable=True
        )
    for mount in visible.values():
        if "rw" in mount.options:
            canonical_kernel_mount = (
                PSEUDO_FILESYSTEMS.get(mount.filesystem) == mount.target and mount.root == "/"
            )
            _need(mount.target in WRITES or canonical_kernel_mount, "writable_escape")


def validate_snapshot(profile, snapshot):
    validate_profile(profile)
    _need(
        type(snapshot) is dict
        and set(snapshot)
        == {"mountinfo", "mountinfo_after", "image_identity", "image_device", "loop", "runtime"},
        "snapshot_shape",
    )
    _need(snapshot["image_identity"] == profile["image_identity"], "image_identity")
    loop = snapshot["loop"]
    _need(
        type(loop) is dict
        and set(loop) == {"backing_file", "offset", "sizelimit", "size_sectors", "read_only"},
        "loop_shape",
    )
    _need(loop["backing_file"] == profile["backing_file"], "loop_backing")
    _need(all(_uint(v) for k, v in loop.items() if k != "backing_file"), "loop_shape")
    _need(
        loop["offset"] == loop["read_only"] == 0 and loop["sizelimit"] == IMAGE_BYTES, "loop_extent"
    )
    _need(loop["size_sectors"] * 512 == IMAGE_BYTES, "loop_extent")
    runtime = snapshot["runtime"]
    _need(
        type(runtime) is dict
        and set(runtime) == {"device", "inode", "uid", "gid", "mode", "fsid", "blocks", "frsize"},
        "runtime_shape",
    )
    _need(all(_uint(v) for k, v in runtime.items() if k != "device"), "runtime_shape")
    _need(
        runtime["device"] == profile["device"]
        and runtime["fsid"] == profile["fsid"]
        and runtime["inode"] == profile["runtime_inode"],
        "runtime_identity",
    )
    _need(
        runtime["uid"] == 997 and runtime["gid"] == 987 and runtime["mode"] == 0o700,
        "runtime_owner",
    )
    _need(runtime["frsize"] in {1024, 2048, 4096, 8192, 16384, 32768, 65536}, "filesystem_geometry")
    _need(0 < runtime["blocks"] * runtime["frsize"] <= IMAGE_BYTES, "filesystem_geometry")
    _validate_mounts(profile, snapshot)


def _read_fixed(path, maximum):
    with open(path, "rb") as source:
        raw = source.read(maximum + 1)
    _need(len(raw) <= maximum, "kernel_read_bound")
    return raw


def _scalar(path):
    raw = _read_fixed(path, 32).strip()
    _need(re.fullmatch(rb"[0-9]{1,20}", raw) is not None, "kernel_scalar")
    value = int(raw)
    _need(_uint(value), "kernel_scalar")
    return value


def _image_identity(info):
    _need(stat.S_ISREG(info.st_mode), "image_type")
    return dict(
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.S_IMODE(info.st_mode),
        nlink=info.st_nlink,
        size=info.st_size,
    )


def _runtime_identity(info):
    _need(stat.S_ISDIR(info.st_mode), "runtime_type")
    return dict(
        device=[os.major(info.st_dev), os.minor(info.st_dev)],
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.S_IMODE(info.st_mode),
    )


def _loop_metadata(profile):
    prefix = "/sys/block/loop" + str(profile["device"][1])
    return dict(
        backing_file=_read_fixed(prefix + "/loop/backing_file", 4096)
        .decode("utf-8")
        .removesuffix("\n"),
        offset=_scalar(prefix + "/loop/offset"),
        sizelimit=_scalar(prefix + "/loop/sizelimit"),
        size_sectors=_scalar(prefix + "/size"),
        read_only=_scalar(prefix + "/ro"),
    )


def capture_live(profile):
    """Read only fixed kernel metadata and image/runtime stat; no payload open."""
    validate_profile(profile)
    try:
        mounts = _read_fixed("/proc/self/mountinfo", 262144)
        image_info = os.stat(IMAGE_ALIAS, follow_symlinks=False)
        image = _image_identity(image_info)
        loop = _loop_metadata(profile)
        runtime = _runtime_identity(os.stat(RUNTIME, follow_symlinks=False))
        geometry = os.statvfs(RUNTIME)
        _need(
            _runtime_identity(os.stat(RUNTIME, follow_symlinks=False)) == runtime, "runtime_drift"
        )
        runtime.update(fsid=geometry.f_fsid, blocks=geometry.f_blocks, frsize=geometry.f_frsize)
        _need(_image_identity(os.stat(IMAGE_ALIAS, follow_symlinks=False)) == image, "image_drift")
        mounts_after = _read_fixed("/proc/self/mountinfo", 262144)
        _need(_loop_metadata(profile) == loop, "loop_drift")
        return dict(
            mountinfo=mounts,
            mountinfo_after=mounts_after,
            image_identity=image,
            image_device=[os.major(image_info.st_dev), os.minor(image_info.st_dev)],
            loop=loop,
            runtime=runtime,
        )
    except StorageDenied:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        raise StorageDenied("storage_metadata_read") from None


def _file_stamp(info):
    return (_image_identity(info), info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _protected_profile():
    """Keep fixed root parents and the public root0444 file held throughout."""
    with ExitStack() as stack:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directory = os.open("/", directory_flags)
        stack.callback(os.close, directory)
        for part in ("etc", "quantmesh", "opend"):
            info = os.fstat(directory)
            _need(
                stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "profile_parent",
            )
            directory = os.open(part, directory_flags, dir_fd=directory)
            stack.callback(os.close, directory)
        info = os.fstat(directory)
        _need(
            stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            "profile_parent",
        )
        fd = os.open(
            "private-storage.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=directory,
        )
        stack.callback(os.close, fd)
        info = os.fstat(fd)
        identity = _file_stamp(info)
        _need(
            info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o444
            and info.st_nlink == 1
            and 0 < info.st_size <= 16384,
            "profile_file",
        )
        chunks = bytearray()
        while len(chunks) <= 16384:
            chunk = os.read(fd, min(4096, 16385 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        _need(
            len(chunks) == info.st_size and _file_stamp(os.fstat(fd)) == identity,
            "profile_file_drift",
        )
        yield fd, bytes(chunks), identity


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "duplicate_profile_key")
        result[key] = value
    return result


def validate_live(claims):
    """Production-only c8 gate; synthetic common inspection is not authority."""
    _need(type(claims) is dict, "storage_control")
    _need(
        type(claims.get("schema_version")) is int and claims["schema_version"] == 4,
        "storage_control",
    )
    _need(
        claims.get("nonce") == NONCE
        and claims.get("gateway_uid") == 997
        and claims.get("gateway_gid") == 987,
        "storage_control",
    )
    digest = claims.get("storage_profile_sha256")
    _need(
        type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "storage_control"
    )
    try:
        with _protected_profile() as (fd, raw, identity):
            _need(hashlib.sha256(raw).hexdigest() == digest, "storage_profile_digest")
            profile = json.loads(raw, object_pairs_hook=_unique_pairs)
            validate_profile(profile)
            _need(profile["backing_file"] == PROVIDER_IMAGE, "production_image_required")
            validate_snapshot(profile, capture_live(profile))
            with _protected_profile() as (_, current, current_identity):
                _need(current == raw and current_identity == identity, "storage_profile_drift")
            _need(_file_stamp(os.fstat(fd)) == identity, "storage_profile_drift")
    except StorageDenied:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        raise StorageDenied("storage_profile_read") from None
