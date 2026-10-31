"""Fixed c8 public metadata layouts; never mount or read vendor state."""

import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
NONCE = "c8f0d0de4ca641a491fca6df24c66ceb"
POOL = "/run/quantmesh-opend-storage-" + NONCE
HOME = "/var/lib/quantmesh-opend"
STATE = "/var/lib/quantmesh-opend-stage"
RUNTIME = "/run/quantmesh-opend-console-" + NONCE
IMAGE = "/srv/quantmesh-opend-private-storage-20261031/provider.ext4"
ALIAS = "/etc/quantmesh/opend/private-storage-image"


def module():
    path = ROOT / "deploy/aws/opend/private_storage.py"
    assert path.exists(), "fixed finite storage admission is not implemented"
    spec = importlib.util.spec_from_file_location("opend_private_storage_tests", path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def layout():
    profile = {
        "schema_version": 1,
        "purpose": "opend_c8_private_storage",
        "nonce": NONCE,
        "image_bytes": 33554432,
        "backing_file": IMAGE,
        "image_identity": {
            "device": 66305,
            "inode": 900,
            "uid": 0,
            "gid": 0,
            "mode": 0o600,
            "nlink": 1,
            "size": 33554432,
        },
        "device": [7, 8],
        "fsid": 123456,
        "runtime_inode": 11,
        "lower_device": [259, 1],
        "lower_roots": {"home": HOME, "state": STATE},
    }
    raw = (
        "10 1 259:1 / / ro,relatime - ext4 /dev/root rw\n"
        f"11 10 7:8 / {POOL}/fs ro,relatime - ext4 /dev/loop8 rw\n"
        f"12 10 259:1 {HOME} {POOL}/lower-home ro - ext4 /dev/root rw\n"
        f"13 10 259:1 {STATE} {POOL}/lower-state ro - ext4 /dev/root rw\n"
        f"14 10 0:51 / {HOME} rw - overlay overlay rw,lowerdir={POOL}/lower-home,"
        f"upperdir={POOL}/fs/home-upper,workdir={POOL}/fs/home-work\n"
        f"15 10 0:52 / {STATE} rw - overlay overlay rw,lowerdir={POOL}/lower-state,"
        f"upperdir={POOL}/fs/state-upper,workdir={POOL}/fs/state-work\n"
        f"16 15 259:1 {STATE}/{NONCE} {STATE}/{NONCE} ro - ext4 /dev/root rw\n"
        f"17 10 7:8 /runtime {RUNTIME} rw - ext4 /dev/loop8 rw\n"
        "18 10 7:8 /tmp /tmp rw - ext4 /dev/loop8 rw\n"
        "19 10 7:8 /vartmp /var/tmp rw - ext4 /dev/loop8 rw\n"
        "20 23 7:8 /shm /dev/shm rw - ext4 /dev/loop8 rw\n"
        f"21 10 259:1 {IMAGE} {ALIAS} ro - ext4 /dev/root rw\n"
        "22 10 0:2 / /proc rw - proc proc rw\n"
        "23 10 0:3 / /dev rw - devtmpfs udev rw\n"
    ).encode()
    snapshot = {
        "mountinfo": raw,
        "mountinfo_after": raw,
        "image_identity": copy.deepcopy(profile["image_identity"]),
        "image_device": [259, 1],
        "loop": {
            "backing_file": IMAGE,
            "offset": 0,
            "sizelimit": 33554432,
            "size_sectors": 65536,
            "read_only": 0,
        },
        "runtime": {
            "device": [7, 8],
            "inode": 11,
            "uid": 997,
            "gid": 987,
            "mode": 0o700,
            "fsid": 123456,
            "blocks": 30000,
            "frsize": 1024,
        },
    }
    return profile, snapshot


@pytest.mark.parametrize("size", [33554432, 33554433])
def test_only_exact_finite_image_can_admit_the_original_layout(size):
    guard = module()
    profile, snapshot = layout()
    profile["image_bytes"] = size
    if size == 33554432:
        assert guard.validate_snapshot(profile, snapshot) is None
    else:
        with pytest.raises(guard.StorageDenied):
            guard.validate_snapshot(profile, snapshot)


@pytest.mark.parametrize(
    "change",
    [
        "image_replaced",
        "image_writable",
        "image_hardlink",
        "image_smaller",
        "loop_foreign_file",
        "loop_offset",
        "loop_unbounded",
        "loop_larger",
        "loop_readonly",
        "foreign_fsid",
        "foreign_device",
        "unbounded_geometry",
        "foreign_runtime_owner",
        "foreign_nonce",
        "unknown_profile_field",
        "boolean_size",
    ],
)
def test_foreign_or_unbounded_backing_never_admits(change):
    guard = module()
    profile, snapshot = layout()
    if change == "image_replaced":
        snapshot["image_identity"]["inode"] = 901
    elif change == "image_writable":
        profile["image_identity"]["mode"] = snapshot["image_identity"]["mode"] = 0o666
    elif change == "image_hardlink":
        profile["image_identity"]["nlink"] = snapshot["image_identity"]["nlink"] = 2
    elif change == "image_smaller":
        snapshot["image_identity"]["size"] = 33554431
    elif change.startswith("loop_"):
        key, value = {
            "loop_foreign_file": ("backing_file", "/srv/foreign.ext4"),
            "loop_offset": ("offset", 4096),
            "loop_unbounded": ("sizelimit", 0),
            "loop_larger": ("size_sectors", 65537),
            "loop_readonly": ("read_only", 1),
        }[change]
        snapshot["loop"][key] = value
    elif change == "foreign_fsid":
        snapshot["runtime"]["fsid"] = 7654321
    elif change == "foreign_device":
        snapshot["runtime"]["device"] = [7, 9]
    elif change == "unbounded_geometry":
        snapshot["runtime"]["blocks"] = 32769
    elif change == "foreign_runtime_owner":
        snapshot["runtime"]["uid"] = 1000
    elif change == "foreign_nonce":
        profile["nonce"] = "a" * 32
    elif change == "unknown_profile_field":
        profile["qualified"] = True
    elif change == "boolean_size":
        profile["image_bytes"] = True
    with pytest.raises(guard.StorageDenied):
        guard.validate_snapshot(profile, snapshot)


@pytest.mark.parametrize(
    "change",
    [
        "missing_write",
        "wrong_write_device",
        "wrong_write_root",
        "readonly_write",
        "writable_lower",
        "wrong_lower_root",
        "wrong_upper",
        "wrong_work",
        "volatile_overlay",
        "missing_claim",
        "writable_claim",
        "foreign_claim_root",
        "writable_alias",
        "wrong_alias_device",
        "missing_pool",
        "extra_nested_write",
        "extra_tmpfs_write",
        "ambiguous_mount",
        "duplicate_mount_id",
        "shared_write",
        "mount_drift",
    ],
)
def test_only_six_complete_private_mappings_admit(change):
    guard = module()
    profile, snapshot = layout()
    raw = snapshot["mountinfo"]
    if change == "missing_write":
        raw = raw.replace(b"18 10 7:8 /tmp /tmp rw - ext4 /dev/loop8 rw\n", b"")
    elif change == "wrong_write_device":
        raw = raw.replace(b"18 10 7:8", b"18 10 7:9")
    elif change == "wrong_write_root":
        raw = raw.replace(b"/tmp /tmp rw", b"/runtime /tmp rw")
    elif change == "readonly_write":
        raw = raw.replace(b"/tmp /tmp rw", b"/tmp /tmp ro")
    elif change == "writable_lower":
        raw = raw.replace((POOL + "/lower-home ro").encode(), (POOL + "/lower-home rw").encode())
    elif change == "wrong_lower_root":
        raw = raw.replace(
            f"259:1 {HOME} {POOL}/lower-home".encode(), f"259:1 /foreign {POOL}/lower-home".encode()
        )
    elif change == "wrong_upper":
        raw = raw.replace((POOL + "/fs/home-upper").encode(), b"/host/foreign-upper")
    elif change == "wrong_work":
        raw = raw.replace((POOL + "/fs/state-work").encode(), b"/host/foreign-work")
    elif change == "volatile_overlay":
        raw = raw.replace(b"workdir=", b"volatile,workdir=", 1)
    elif change == "missing_claim":
        raw = b"\n".join(line for line in raw.splitlines() if not line.startswith(b"16 ")) + b"\n"
    elif change == "writable_claim":
        raw = raw.replace(
            (STATE + "/" + NONCE + " ro").encode(), (STATE + "/" + NONCE + " rw").encode()
        )
    elif change == "foreign_claim_root":
        raw = raw.replace(f"259:1 {STATE}/{NONCE}".encode(), b"259:1 /foreign-claim")
    elif change == "writable_alias":
        raw = raw.replace((ALIAS + " ro").encode(), (ALIAS + " rw").encode())
    elif change == "wrong_alias_device":
        raw = raw.replace(b"21 10 259:1", b"21 10 8:2")
    elif change == "missing_pool":
        raw = b"\n".join(line for line in raw.splitlines() if not line.startswith(b"11 ")) + b"\n"
    elif change == "extra_nested_write":
        raw += f"40 14 259:1 / {HOME}/escape rw - ext4 /dev/root rw\n".encode()
    elif change == "extra_tmpfs_write":
        raw += b"40 10 0:99 / /run/escape rw - tmpfs tmpfs rw\n"
    elif change == "ambiguous_mount":
        raw += b"40 10 7:8 /tmp /tmp rw - ext4 /dev/loop8 rw\n"
    elif change == "duplicate_mount_id":
        raw += b"18 10 7:8 /tmp /foreign rw - ext4 /dev/loop8 rw\n"
    elif change == "shared_write":
        raw = raw.replace(b"/tmp rw -", b"/tmp rw shared:1 -")
    elif change == "mount_drift":
        snapshot["mountinfo_after"] += b"40 10 0:99 / /escape rw - tmpfs tmpfs rw\n"
    snapshot["mountinfo"] = raw
    if change != "mount_drift":
        snapshot["mountinfo_after"] = raw
    with pytest.raises(guard.StorageDenied):
        guard.validate_snapshot(profile, snapshot)


def test_visible_mount_stack_preserves_valid_host_runtime_bind():
    guard = module()
    profile, snapshot = layout()
    raw = snapshot["mountinfo"] + f"40 17 7:8 /runtime {RUNTIME} rw - ext4 /dev/loop8 rw\n".encode()
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    assert guard.validate_snapshot(profile, snapshot) is None


def test_covered_old_root_children_do_not_create_a_false_writable_escape():
    guard = module()
    profile, snapshot = layout()
    raw = snapshot["mountinfo"].replace(b"10 1 259:1 / / ro", b"10 2 259:1 / / ro")
    raw += b"2 1 259:1 / / rw - ext4 /dev/root rw\n3 2 259:1 /boot /boot rw - ext4 /dev/root rw\n"
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    assert guard.validate_snapshot(profile, snapshot) is None


@pytest.mark.parametrize("old_id,new_id,prefix_id", [(672, 720, 719), (720, 672, 719), (5, 900, 9)])
@pytest.mark.parametrize("reverse_rows", [False, True])
def test_nearer_visible_prefix_hides_old_child_without_mount_id_heuristics(
    old_id, new_id, prefix_id, reverse_rows
):
    guard = module()
    profile, snapshot = layout()
    # Public synthetic path: the observed private target was never retained.
    target = "/proc/sys/opaque-fixture"
    rows = [
        f"{old_id} 22 0:99 / {target} rw - tmpfs tmpfs rw\n",
        f"{prefix_id} 22 0:2 /sys /proc/sys ro - proc proc rw\n",
        f"{new_id} {prefix_id} 0:99 / {target} ro - tmpfs tmpfs rw\n",
    ]
    raw = snapshot["mountinfo"] + "".join(reversed(rows) if reverse_rows else rows).encode()
    visible = guard._visible_mounts(guard.parse_mountinfo(raw))
    assert visible[target].identifier == new_id
    assert "ro" in visible[target].options
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    assert guard.validate_snapshot(profile, snapshot) is None


def test_hidden_child_without_replacement_is_absent_not_a_writable_escape():
    guard = module()
    profile, snapshot = layout()
    target = "/proc/sys/opaque-fixture"
    raw = (
        snapshot["mountinfo"]
        + (
            f"40 22 0:99 / {target} rw - tmpfs tmpfs rw\n"
            "41 22 0:2 /sys /proc/sys ro - proc proc rw\n"
        ).encode()
    )
    visible = guard._visible_mounts(guard.parse_mountinfo(raw))
    assert target not in visible
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    assert guard.validate_snapshot(profile, snapshot) is None


def test_visible_prefix_filter_preserves_true_sibling_ambiguity():
    guard = module()
    raw = (
        b"1 99 259:1 / / ro - ext4 root rw\n"
        b"2 1 0:2 / /proc rw - proc proc rw\n"
        b"3 2 0:2 /sys /proc/sys ro - proc proc rw\n"
        b"4 3 0:99 / /proc/sys/opaque-fixture ro - tmpfs tmpfs rw\n"
        b"5 3 0:99 / /proc/sys/opaque-fixture ro - tmpfs tmpfs rw\n"
    )
    with pytest.raises(guard.StorageDenied, match="^mount_ambiguity$"):
        guard._visible_mounts(guard.parse_mountinfo(raw))


def test_nearer_prefix_preserves_legitimate_same_target_stack():
    guard = module()
    raw = (
        b"1 99 259:1 / / ro - ext4 root rw\n"
        b"2 1 0:2 / /proc rw - proc proc rw\n"
        b"3 2 0:2 /sys /proc/sys ro - proc proc rw\n"
        b"40 3 0:99 / /proc/sys/opaque-fixture ro - tmpfs tmpfs rw\n"
        b"4 40 0:99 / /proc/sys/opaque-fixture ro - tmpfs tmpfs rw\n"
    )
    visible = guard._visible_mounts(guard.parse_mountinfo(raw))
    assert visible["/proc/sys/opaque-fixture"].identifier == 4


def test_nearest_prefix_uses_path_components_not_string_prefixes():
    guard = module()
    raw = (
        b"1 99 259:1 / / ro - ext4 root rw\n"
        b"2 1 0:2 / /proc rw - proc proc rw\n"
        b"3 2 0:2 /sys /proc/sys ro - proc proc rw\n"
        b"4 2 0:99 / /proc/sysctl/opaque-fixture ro - tmpfs tmpfs rw\n"
    )
    visible = guard._visible_mounts(guard.parse_mountinfo(raw))
    assert visible["/proc/sysctl/opaque-fixture"].identifier == 4


@pytest.mark.parametrize(
    "raw,reason",
    [
        (
            "1 99 259:1 / / ro - ext4 root rw\n2 9 0:99 / /escape rw - tmpfs tmpfs rw\n",
            "mount_parent",
        ),
        (
            "1 99 259:1 / / ro - ext4 root rw\n"
            "2 3 0:99 / /escape ro - tmpfs tmpfs rw\n"
            "3 2 0:99 / /escape ro - tmpfs tmpfs rw\n",
            "mount_cycle",
        ),
        (
            "1 99 259:1 / / ro - ext4 root rw\n"
            "2 1 0:99 / /other ro - tmpfs tmpfs rw\n"
            "3 2 0:99 / /escape ro - tmpfs tmpfs rw\n",
            "mount_parent",
        ),
        ("2 99 0:99 / /escape rw - tmpfs tmpfs rw\n", "mount_parent"),
    ],
)
def test_visible_mount_graph_parent_and_cycle_fail_closed(raw, reason):
    guard = module()
    with pytest.raises(guard.StorageDenied, match="^" + reason + "$"):
        guard._visible_mounts(guard.parse_mountinfo(raw.encode()))


def test_mount_namespace_root_may_have_an_unlisted_external_parent():
    guard = module()
    visible = guard._visible_mounts(guard.parse_mountinfo(b"1 99 259:1 / / ro - ext4 root rw\n"))
    assert visible["/"].identifier == 1


def test_visible_writable_child_under_new_prefix_is_still_denied():
    guard = module()
    profile, snapshot = layout()
    raw = snapshot["mountinfo"] + (
        b"40 22 0:2 /sys /proc/sys ro - proc proc rw\n"
        b"41 40 0:99 / /proc/sys/opaque-fixture rw - tmpfs tmpfs rw\n"
    )
    visible = guard._visible_mounts(guard.parse_mountinfo(raw))
    assert visible["/proc/sys/opaque-fixture"].identifier == 41
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    with pytest.raises(guard.StorageDenied, match="^writable_escape$"):
        guard.validate_snapshot(profile, snapshot)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"invalid",
        b"1 2 7:8 / /tmp rw - ext4 x rw\n1 2 7:8 / /tmp rw - ext4 x rw\n",
        b"1 2 7:8 / /tmp\\999 rw - ext4 x rw\n",
        b"1 2 7:8 / /../tmp rw - ext4 x rw\n",
        b"1 2 7:8 / /tmp rw,ro - ext4 x rw\n",
        b"1 2 7:8 / /tmp rw - ext4 x rw,rw\n",
    ],
)
def test_malformed_kernel_mapping_cannot_be_interpreted_as_admission(raw):
    guard = module()
    with pytest.raises(guard.StorageDenied):
        guard.parse_mountinfo(raw)


def test_escaped_foreign_writable_path_still_counts_as_an_escape():
    guard = module()
    profile, snapshot = layout()
    raw = snapshot["mountinfo"] + b"40 10 0:99 / /run/foreign\\040path rw - tmpfs tmpfs rw\n"
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    with pytest.raises(guard.StorageDenied):
        guard.validate_snapshot(profile, snapshot)


def test_unhashable_profile_value_is_a_clean_denial():
    guard = module()
    profile, snapshot = layout()
    profile["backing_file"] = []
    with pytest.raises(guard.StorageDenied):
        guard.validate_snapshot(profile, snapshot)


def test_dropin_declares_only_the_six_writes_and_readonly_image_metadata():
    path = ROOT / "deploy/aws/opend/quantmesh-opend-console-c8-private-storage.conf"
    assert path.exists(), "the original c8 instance needs an explicit bounded mapping"
    text = path.read_text(encoding="utf-8")
    settings = {}
    for line in text.splitlines():
        if line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            settings.setdefault(key, []).append(value)
    assert settings.get("ReadOnlyPaths") == [POOL]
    assert settings["ReadWritePaths"] == ["", f"{HOME} {STATE} {RUNTIME} /tmp /var/tmp /dev/shm"]
    assert settings["BindPaths"] == [
        "",
        " ".join(
            [
                f"{POOL}/view-home:{HOME}",
                f"{POOL}/view-state:{STATE}",
                f"{POOL}/fs/runtime:{RUNTIME}",
                f"{POOL}/fs/tmp:/tmp",
                f"{POOL}/fs/vartmp:/var/tmp",
                f"{POOL}/fs/shm:/dev/shm",
            ]
        ),
    ]
    assert settings["BindReadOnlyPaths"] == [
        "",
        f"{IMAGE}:{ALIAS} {POOL}/lower-state/{NONCE}:{STATE}/{NONCE}",
    ]
    for key, value in {
        "PrivateMounts": "yes",
        "MountFlags": "slave",
        "PrivateTmp": "no",
        "StateDirectory": "",
        "RuntimeDirectoryPreserve": "yes",
    }.items():
        assert settings[key] == [value]
    assert set(settings) == {
        "PrivateMounts",
        "MountFlags",
        "PrivateTmp",
        "StateDirectory",
        "RuntimeDirectoryPreserve",
        "ReadOnlyPaths",
        "ReadWritePaths",
        "BindPaths",
        "BindReadOnlyPaths",
    }


class KernelWorld:
    """Modeled Linux metadata boundary; no native qualification or payload IO."""

    def __init__(self, snapshot, change=None):
        self.snapshot, self.change = snapshot, change
        self.reads, self.stats = [], []
        self.values = {
            "/proc/self/mountinfo": snapshot["mountinfo"],
            "/sys/block/loop8/loop/backing_file": (IMAGE + "\n").encode(),
            "/sys/block/loop8/loop/offset": b"0\n",
            "/sys/block/loop8/loop/sizelimit": b"33554432\n",
            "/sys/block/loop8/size": b"65536\n",
            "/sys/block/loop8/ro": b"0\n",
        }
        self.os = SimpleNamespace(
            stat=self.stat,
            statvfs=self.statvfs,
            major=lambda dev: 259 if dev == 66305 else 7,
            minor=lambda dev: 1 if dev == 66305 else 8,
        )

    def open_file(self, path, mode):
        path = str(path)
        assert mode == "rb" and path in self.values, "credential/image payload read attempted"
        self.reads.append(path)
        value = self.values[path]
        if (
            self.change == "mount_drift"
            and path == "/proc/self/mountinfo"
            and self.reads.count(path) > 1
        ):
            value += b"40 10 0:99 / /escape rw - tmpfs tmpfs rw\n"
        return io.BytesIO(value)

    def stat(self, path, *, follow_symlinks=True):
        path = str(path)
        assert path in {ALIAS, RUNTIME} and follow_symlinks is False
        self.stats.append(path)
        if path == ALIAS:
            d = self.snapshot["image_identity"]
            inode = d["inode"] + int(self.change == "image_drift" and self.stats.count(path) > 1)
            return SimpleNamespace(
                st_dev=d["device"],
                st_ino=inode,
                st_uid=d["uid"],
                st_gid=d["gid"],
                st_mode=stat.S_IFREG | d["mode"],
                st_nlink=d["nlink"],
                st_size=d["size"],
            )
        d = self.snapshot["runtime"]
        return SimpleNamespace(
            st_dev=1800,
            st_ino=d["inode"],
            st_uid=d["uid"],
            st_gid=d["gid"],
            st_mode=stat.S_IFDIR | d["mode"],
            st_nlink=2,
            st_size=4096,
        )

    def statvfs(self, path):
        assert str(path) == RUNTIME
        d = self.snapshot["runtime"]
        return SimpleNamespace(f_blocks=d["blocks"], f_frsize=d["frsize"], f_fsid=d["fsid"])


@pytest.mark.parametrize("change", [None, "image_drift", "mount_drift"])
def test_live_metadata_capture_preserves_the_complete_mapping_and_never_reads_payload(
    monkeypatch, change
):
    guard = module()
    assert callable(getattr(guard, "capture_live", None)), "live kernel mapping is not implemented"
    profile, snapshot = layout()
    world = KernelWorld(snapshot, change)
    monkeypatch.setattr(guard, "os", world.os, raising=False)
    monkeypatch.setattr(guard, "open", world.open_file, raising=False)
    if change:
        with pytest.raises(guard.StorageDenied):
            guard.validate_snapshot(profile, guard.capture_live(profile))
    else:
        assert guard.validate_snapshot(profile, guard.capture_live(profile)) is None
        assert set(world.reads) == set(world.values)
        assert ALIAS in world.stats and RUNTIME in world.stats


@pytest.mark.parametrize(
    "filesystem,target,root,allowed",
    [
        ("devtmpfs", HOME + "/escape", "/foreign-writable", False),
        ("proc", HOME + "/escape", "/", False),
        ("devtmpfs", "/dev", "/foreign-writable", False),
        ("devpts", "/escape", "/", False),
        ("sysfs", "/sys", "/", True),
        ("cgroup2", "/sys/fs/cgroup", "/", True),
        ("devpts", "/dev/pts", "/", True),
    ],
)
def test_writable_kernel_exceptions_are_bound_to_canonical_targets_and_roots(
    filesystem, target, root, allowed
):
    guard = module()
    profile, snapshot = layout()
    parent = 10
    if target.startswith(HOME + "/"):
        parent = 14
    elif target == "/dev/pts":
        parent = 23
    raw = (
        snapshot["mountinfo"]
        + f"40 {parent} 0:99 {root} {target} rw - {filesystem} kernel rw\n".encode()
    )
    if target == "/dev":
        raw = raw.replace(b"23 10 0:3 / /dev rw - devtmpfs udev rw\n", b"")
        # Keep the child attached to the replacement /dev mount.
        raw = raw.replace(b"20 23 7:8 /shm", b"20 40 7:8 /shm")
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    if allowed:
        assert guard.validate_snapshot(profile, snapshot) is None
    else:
        with pytest.raises(guard.StorageDenied, match="^writable_escape$"):
            guard.validate_snapshot(profile, snapshot)


@pytest.mark.parametrize(
    "field,value",
    [
        ("loop/backing_file", b"/srv/foreign.ext4\n"),
        ("loop/offset", b"4096\n"),
        ("loop/sizelimit", b"0\n"),
        ("size", b"65537\n"),
        ("ro", b"1\n"),
    ],
)
def test_loop_drift_inside_capture_is_denied_before_the_snapshot_returns(monkeypatch, field, value):
    guard = module()
    profile, snapshot = layout()
    world = KernelWorld(snapshot)
    original_stat = world.os.stat

    def stat_and_drift(path, **kwargs):
        if str(path) == RUNTIME:
            world.values["/sys/block/loop8/" + field] = value
        return original_stat(path, **kwargs)

    world.os.stat = stat_and_drift
    monkeypatch.setattr(guard, "os", world.os)
    monkeypatch.setattr(guard, "open", world.open_file, raising=False)
    with pytest.raises(guard.StorageDenied):
        guard.validate_snapshot(profile, guard.capture_live(profile))


PROFILE = "/etc/quantmesh/opend/private-storage.json"


class ProfileWorld(KernelWorld):
    """Virtual root/proc filesystem with held-node semantics and real JSON bytes."""

    def __init__(self, profile, snapshot, change=None):
        super().__init__(snapshot, change)
        self.nodes, self.handles, self.opened = {}, {}, []
        for index, path in enumerate(("/", "/etc", "/etc/quantmesh", "/etc/quantmesh/opend")):
            self.nodes[path] = self.node(path, b"", 10 + index, stat.S_IFDIR | 0o755)
        raw = json.dumps(profile, sort_keys=True).encode()
        if change == "duplicate_key":
            raw = raw.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
        self.nodes[PROFILE] = self.node(PROFILE, raw, 1234, stat.S_IFREG | 0o444)
        if change == "profile_mode":
            self.nodes[PROFILE].info.st_mode = stat.S_IFREG | 0o644
        elif change == "profile_owner":
            self.nodes[PROFILE].info.st_uid = 997
        elif change == "profile_nlink":
            self.nodes[PROFILE].info.st_nlink = 2
        elif change == "parent_writable":
            self.nodes["/etc/quantmesh"].info.st_mode = stat.S_IFDIR | 0o777
        for name, default in {
            "O_RDONLY": 0,
            "O_DIRECTORY": 65536,
            "O_NOFOLLOW": 131072,
            "O_CLOEXEC": 524288,
            "O_NONBLOCK": 2048,
        }.items():
            setattr(self.os, name, getattr(os, name, default))
        self.os.open, self.os.close, self.os.fstat = self.fdopen, self.close, self.fstat
        self.os.read, self.os.lseek = self.read, self.seek
        self.os.SEEK_SET = 0
        self.next_fd = 100

    @staticmethod
    def node(path, raw, inode, mode):
        info = SimpleNamespace(
            st_dev=66305,
            st_ino=inode,
            st_uid=0,
            st_gid=0,
            st_mode=mode,
            st_nlink=1,
            st_size=len(raw),
            st_mtime_ns=1,
            st_ctime_ns=2,
        )
        return SimpleNamespace(path=path, data=raw, info=info)

    def fdopen(self, path, flags, *, dir_fd=None):
        path = str(path)
        if dir_fd is not None:
            path = self.handles[dir_fd][0].path.rstrip("/") + "/" + path
        assert path in self.nodes and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT) == 0
        self.next_fd += 1
        self.handles[self.next_fd] = [self.nodes[path], 0]
        self.opened.append(path)
        return self.next_fd

    def close(self, fd):
        del self.handles[fd]

    def fstat(self, fd):
        return self.handles[fd][0].info

    def read(self, fd, size):
        node, offset = self.handles[fd]
        assert node.path == PROFILE, "only the fixed public profile has a readable payload"
        result = node.data[offset : offset + size]
        self.handles[fd][1] += len(result)
        return result

    def seek(self, fd, offset, whence):
        assert offset == whence == 0
        self.handles[fd][1] = 0
        return 0

    def open_file(self, path, mode):
        if self.change == "replace_profile" and str(path) == "/proc/self/mountinfo":
            node = self.nodes[PROFILE]
            self.nodes[PROFILE] = self.node(PROFILE, node.data, 9999, stat.S_IFREG | 0o444)
            self.change = None
        return super().open_file(path, mode)


@pytest.mark.parametrize(
    "change",
    [
        None,
        "wrong_digest",
        "old_control",
        "profile_mode",
        "profile_owner",
        "profile_nlink",
        "parent_writable",
        "replace_profile",
        "fixture_profile",
        "duplicate_key",
    ],
)
def test_production_guard_binds_protected_profile_and_closes_all_owned_fds(monkeypatch, change):
    guard = module()
    assert callable(getattr(guard, "validate_live", None)), (
        "protected live storage admission is absent"
    )
    profile, snapshot = layout()
    if change == "fixture_profile":
        profile["backing_file"] = "/srv/quantmesh-opend-private-storage-20261031/fixture.ext4"
    world = ProfileWorld(profile, snapshot, change)
    claims = {
        "schema_version": 4,
        "nonce": NONCE,
        "gateway_uid": 997,
        "gateway_gid": 987,
        "storage_profile_sha256": hashlib.sha256(world.nodes[PROFILE].data).hexdigest(),
    }
    if change == "wrong_digest":
        claims["storage_profile_sha256"] = "0" * 64
    elif change == "old_control":
        claims["schema_version"] = 3
    monkeypatch.setattr(guard, "os", world.os, raising=False)
    monkeypatch.setattr(guard, "open", world.open_file, raising=False)
    if change:
        with pytest.raises(guard.StorageDenied):
            guard.validate_live(claims)
    else:
        assert guard.validate_live(claims) is None
    assert not world.handles, "the guard must close every owned profile/directory fd"
    if change in {
        "wrong_digest",
        "old_control",
        "profile_mode",
        "profile_owner",
        "profile_nlink",
        "parent_writable",
        "fixture_profile",
        "duplicate_key",
    }:
        assert not world.reads, "bad authority must deny before observing the kernel layout"


@pytest.mark.parametrize(
    "target",
    [
        POOL + "/fs",
        POOL + "/lower-home",
        POOL + "/lower-state",
        HOME,
        STATE,
        STATE + "/" + NONCE,
        ALIAS,
        RUNTIME,
        "/tmp",
        "/var/tmp",
        "/dev/shm",
    ],
)
@pytest.mark.parametrize("propagation", ["master:7", "shared:7"])
def test_each_required_mapping_rejects_shared_but_accepts_slave_metadata(
    monkeypatch, target, propagation
):
    guard = module()
    profile, snapshot = layout()
    lines = snapshot["mountinfo"].decode().splitlines()
    changed = 0
    for i, line in enumerate(lines):
        if line.split()[4] == target:
            lines[i] = line.replace(" - ", " " + propagation + " - ", 1)
            changed += 1
    assert changed == 1
    raw = ("\n".join(lines) + "\n").encode()
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    world = KernelWorld(snapshot)
    monkeypatch.setattr(guard, "os", world.os)
    monkeypatch.setattr(guard, "open", world.open_file, raising=False)
    captured = guard.capture_live(profile)
    if propagation == "shared:7":
        with pytest.raises(guard.StorageDenied, match="^shared_mount$"):
            guard.validate_snapshot(profile, captured)
    else:
        assert guard.validate_snapshot(profile, captured) is None
    assert IMAGE not in world.reads


@pytest.mark.parametrize(
    "change,reason",
    [
        (None, None),
        ("pool_writable", "mount_mode"),
        ("runtime_readonly", "mount_mode"),
        ("alias_replaced", "image_identity"),
        ("claim_writable", "mount_mode"),
        ("visible_child", "writable_escape"),
        ("covered_shared", None),
    ],
)
def test_slave_tags_preserve_modes_identity_claim_and_visible_escape_checks(
    monkeypatch, change, reason
):
    guard = module()
    profile, snapshot = layout()
    raw = snapshot["mountinfo"].replace(b" - ", b" master:7 - ")
    if change == "pool_writable":
        raw = raw.replace((POOL + "/fs ro").encode(), (POOL + "/fs rw").encode())
    elif change == "runtime_readonly":
        raw = raw.replace((RUNTIME + " rw").encode(), (RUNTIME + " ro").encode())
    elif change == "alias_replaced":
        snapshot["image_identity"]["inode"] += 1
    elif change == "claim_writable":
        raw = raw.replace(
            (STATE + "/" + NONCE + " ro").encode(), (STATE + "/" + NONCE + " rw").encode()
        )
    elif change == "visible_child":
        raw += (f"40 14 259:1 / {HOME}/escape rw master:7 - ext4 /dev/root rw\n").encode()
    elif change == "covered_shared":
        raw = raw.replace((RUNTIME + " rw master:7").encode(), (RUNTIME + " rw shared:9").encode())
        raw += (f"40 17 7:8 /runtime {RUNTIME} rw master:7 - ext4 /dev/loop8 rw\n").encode()
    snapshot.update(mountinfo=raw, mountinfo_after=raw)
    world = KernelWorld(snapshot)
    monkeypatch.setattr(guard, "os", world.os)
    monkeypatch.setattr(guard, "open", world.open_file, raising=False)
    captured = guard.capture_live(profile)
    if reason:
        with pytest.raises(guard.StorageDenied, match="^" + reason + "$"):
            guard.validate_snapshot(profile, captured)
    else:
        assert guard.validate_snapshot(profile, captured) is None


def _merged_service_settings(texts):
    # v255 config_parse_bind_paths uses ONE bind_mounts list for both directives.
    # This is a narrow public config model, not a systemd/native qualification.
    list_keys = {"Environment", "ReadOnlyPaths", "ReadWritePaths", "BindPaths", "BindReadOnlyPaths"}
    effective = {}
    for text in texts:
        section = None
        for line in text.splitlines():
            if line.startswith("["):
                section = line
            elif section == "[Service]" and line and not line.startswith("#"):
                key, value = line.split("=", 1)
                value = value.replace("%i", NONCE)
                if key in {"BindPaths", "BindReadOnlyPaths"} and not value:
                    effective["BindPaths"] = []
                    effective["BindReadOnlyPaths"] = []
                elif key in list_keys:
                    if value:
                        effective.setdefault(key, []).extend(value.split())
                    else:
                        effective[key] = []
                else:
                    effective[key] = value
    return effective


@pytest.mark.parametrize("reset", ["BindPaths", "BindReadOnlyPaths"])
def test_either_empty_bind_directive_clears_both_accumulated_bind_kinds(reset):
    settings = _merged_service_settings(
        [
            "[Service]\n"
            "BindPaths=/synthetic/write:/synthetic/target\n"
            "BindReadOnlyPaths=/synthetic/readonly:/synthetic/ro\n" + reset + "=\n"
        ]
    )
    assert settings == {"BindPaths": [], "BindReadOnlyPaths": []}


def test_complete_base_and_c8_dropin_merge_keeps_six_writes_and_slave_propagation():
    # Independently specified effective vector, including shared-list reset semantics.
    effective = _merged_service_settings(
        [
            (ROOT / "deploy/aws/opend" / name).read_text(encoding="utf-8")
            for name in (
                "quantmesh-opend-console@.service",
                "quantmesh-opend-console-c8-private-storage.conf",
            )
        ]
    )
    assert effective == {
        "Type": "exec",
        "User": "quantmesh-opend",
        "Group": "quantmesh-opend",
        "WorkingDirectory": "/opt/quantmesh/opend/10.10.7008",
        "Environment": ["HOME=/var/lib/quantmesh-opend", "PATH=/usr/bin:/bin", "LANG=C.UTF-8"],
        "ExecCondition": (
            "/usr/bin/python3 -I -S -B /opt/quantmesh/opend/stage_console.py "
            "--check-window --nonce "
        )
        + NONCE
        + " --persistent",
        "ExecStartPre": (
            "/usr/bin/python3 -I -S -B /opt/quantmesh/opend/stage_console.py --prepare --nonce "
        )
        + NONCE
        + " --persistent",
        "ExecStart": f"/usr/bin/tmux -D -f {RUNTIME}/tmux.conf -S {RUNTIME}/socket",
        "ExecStartPost": (
            "/usr/bin/python3 -I -S -B /opt/quantmesh/opend/stage_console.py --create-pane --nonce "
        )
        + NONCE
        + " --persistent",
        "StandardInput": "null",
        "StandardOutput": "null",
        "StandardError": "null",
        "RuntimeDirectory": "quantmesh-opend-console-" + NONCE,
        "RuntimeDirectoryMode": "0700",
        "StateDirectory": "",
        "StateDirectoryMode": "0700",
        "UMask": "0077",
        "NoNewPrivileges": "true",
        "ProtectSystem": "strict",
        "ProtectHome": "true",
        "PrivateTmp": "no",
        "PrivateMounts": "yes",
        "MountFlags": "slave",
        "ProtectKernelTunables": "true",
        "ProtectKernelModules": "true",
        "ProtectControlGroups": "true",
        "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet": "",
        "ReadOnlyPaths": [POOL],
        "ReadWritePaths": [HOME, STATE, RUNTIME, "/tmp", "/var/tmp", "/dev/shm"],
        "BindPaths": [
            f"{POOL}/view-home:{HOME}",
            f"{POOL}/view-state:{STATE}",
            f"{POOL}/fs/runtime:{RUNTIME}",
            f"{POOL}/fs/tmp:/tmp",
            f"{POOL}/fs/vartmp:/var/tmp",
            f"{POOL}/fs/shm:/dev/shm",
        ],
        "BindReadOnlyPaths": [f"{IMAGE}:{ALIAS}", f"{POOL}/lower-state/{NONCE}:{STATE}/{NONCE}"],
        "RuntimeDirectoryPreserve": "yes",
        "RuntimeMaxSec": "infinity",
        "MemoryMax": "1G",
        "MemoryHigh": "768M",
        "MemorySwapMax": "0",
        "CPUQuota": "50%",
        "TasksMax": "128",
        "TimeoutStartSec": "15",
        "TimeoutStopSec": "15",
        "KillMode": "control-group",
        "Restart": "no",
    }


def test_nonempty_bind_directives_append_without_erasing_the_other_kind():
    settings = _merged_service_settings(
        [
            "[Service]\n"
            "BindPaths=/synthetic/first:/synthetic/a\n"
            "BindReadOnlyPaths=/synthetic/readonly:/synthetic/b\n"
            "BindPaths=/synthetic/last:/synthetic/c\n"
        ]
    )
    assert settings == {
        "BindPaths": ["/synthetic/first:/synthetic/a", "/synthetic/last:/synthetic/c"],
        "BindReadOnlyPaths": ["/synthetic/readonly:/synthetic/b"],
    }
