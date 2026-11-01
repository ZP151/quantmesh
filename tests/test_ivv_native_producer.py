"""Independent literal kernel metadata fixtures; no SDK/application/native execution."""

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools/research/ivv_native_producer.py"


def producer():
    if not MODULE.exists():
        raise AssertionError("provider feasibility check is not implemented")
    spec = importlib.util.spec_from_file_location("ivv_native_producer_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


NONCE = "eabdda557bc641fdbda60ecd993fb2a0"
UNIT = "quantmesh-opend-console@" + NONCE + ".service"
RUNTIME = "/run/quantmesh-opend-console-" + NONCE
UNBOUNDED = (
    """1 99 259:1 / / ro - ext4 /dev/root rw
2 1 259:1 /var/lib/quantmesh-opend /var/lib/quantmesh-opend rw - ext4 /dev/root rw
3 1 259:1 /var/lib/quantmesh-opend-stage /var/lib/quantmesh-opend-stage rw - ext4 /dev/root rw
4 1 259:1 /runtime """
    + RUNTIME
    + """ rw - ext4 /dev/root rw
5 1 259:1 /tmp /tmp rw - ext4 /dev/root rw
6 1 259:1 /vartmp /var/tmp rw - ext4 /dev/root rw
7 1 259:1 /shm /dev/shm rw - ext4 /dev/root rw
"""
).encode()


class NativeFixture:
    """The OS boundary returns hand-written facts, never a precomputed verdict."""

    def __init__(self, mounts=UNBOUNDED):
        self.mounts = mounts
        self.closed = False

    def identity(self):
        return {
            "machine": "a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191",
            "unit": UNIT,
            "invocation": "759f2f9421764604882bef10b67c88fa",
            "active": "active",
            "substate": "running",
            "main_pid": 705646,
            "processes": [
                {
                    "pid": 705646,
                    "start": 276886996,
                    "uids": [997] * 4,
                    "ppid": 1,
                    "role": "TMUX",
                    "exe_verified": True,
                    "mnt": 4026532217,
                    "net": 4026531833,
                    "cgroup_unit": UNIT,
                    "caps": 0,
                    "nnp": 1,
                },
                {
                    "pid": 705651,
                    "start": 276887118,
                    "uids": [997] * 4,
                    "ppid": 705646,
                    "role": "PYTHON",
                    "exe_verified": True,
                    "mnt": 4026532217,
                    "net": 4026531833,
                    "cgroup_unit": UNIT,
                    "caps": 0,
                    "nnp": 1,
                },
                {
                    "pid": 705711,
                    "start": 276887299,
                    "uids": [997] * 4,
                    "ppid": 705651,
                    "role": "VENDOR",
                    "exe_verified": True,
                    "mnt": 4026532217,
                    "net": 4026531833,
                    "cgroup_unit": UNIT,
                    "caps": 0,
                    "nnp": 1,
                },
            ],
            "vendor_loopback11112": True,
        }

    def mountinfo(self):
        return self.mounts

    def close(self):
        self.closed = True


POOL = "/run/quantmesh-opend-storage-0123456789abcdef0123456789abcdef"
FINITE = (
    """1 99 259:1 / / ro - ext4 /dev/root rw
2 1 0:5 / /dev rw - devtmpfs devtmpfs rw
3 1 0:6 / /proc rw - proc proc rw
10 1 7:17 / """
    + POOL
    + """/fs ro - ext4 /dev/loop17 rw
11 1 259:1 /var/lib/quantmesh-opend """
    + POOL
    + """/lower-home ro - ext4 /dev/root rw
12 1 259:1 /var/lib/quantmesh-opend-stage """
    + POOL
    + """/lower-state ro - ext4 /dev/root rw
20 1 0:77 / /var/lib/quantmesh-opend rw - overlay overlay rw,lowerdir="""
    + POOL
    + """/lower-home,upperdir="""
    + POOL
    + """/fs/home-upper,workdir="""
    + POOL
    + """/fs/home-work
21 1 0:78 / /var/lib/quantmesh-opend-stage rw - overlay overlay rw,lowerdir="""
    + POOL
    + """/lower-state,upperdir="""
    + POOL
    + """/fs/state-upper,workdir="""
    + POOL
    + """/fs/state-work
22 1 7:17 /runtime """
    + RUNTIME
    + """ rw - ext4 /dev/loop17 rw
23 1 7:17 /tmp /tmp rw - ext4 /dev/loop17 rw
24 1 7:17 /vartmp /var/tmp rw - ext4 /dev/loop17 rw
25 2 7:17 /shm /dev/shm rw - ext4 /dev/loop17 rw
"""
).encode()


class FiniteFixture(NativeFixture):
    def __init__(self):
        super().__init__(FINITE)
        self.image = {
            "kind": "REG",
            "uid": 0,
            "gid": 0,
            "mode": 0o600,
            "nlink": 1,
            "size": 33554432,
            "device": 66305,
            "inode": 1843320,
        }
        self.loop = {
            "backing_file": "/srv/quantmesh-opend-private-storage-20261031/provider.ext4",
            "offset": 0,
            "sizelimit": 0,
            "size_sectors": 65536,
            "read_only": 0,
            "device": (7, 17),
            "block_uid": 0,
            "block_gid": 6,
            "block_mode": 0o660,
        }
        self.channel_data = {
            "fds": [{"kind": "REG", "device": (7, 17), "mount_id": 22, "access": 2}],
            "maps": [
                {"device": (7, 17), "inode": 7, "shared": True, "writable": True},
                {"device": (0, 0), "inode": 0, "shared": True, "writable": True},
            ],
        }
        self.finished = False

    def backing(self, device, pool):
        if device != (7, 17) or pool != POOL:
            raise AssertionError("unexpected native backing selection")
        return {
            "image": self.image,
            "loop": self.loop,
            "ancestors": [{"uid": 0, "mode": 0o755}, {"uid": 0, "mode": 0o700}],
        }

    def path_info(self, scope, path):
        device = (7, 17)
        inode = 100
        uid = 997
        if path == POOL:
            device = (259, 1)
            uid = 0
        elif path == POOL + "/fs":
            uid = 0
        elif scope == "host" and path == "/var/lib/quantmesh-opend":
            device = (259, 1)
            inode = 101
        elif scope == "host" and path == "/var/lib/quantmesh-opend-stage":
            device = (259, 1)
            inode = 102
        elif path == POOL + "/lower-home":
            device = (259, 1)
            inode = 101
        elif path == POOL + "/lower-state":
            device = (259, 1)
            inode = 102
        elif path == "/var/lib/quantmesh-opend":
            device = (0, 77)
        elif path == "/var/lib/quantmesh-opend-stage":
            device = (0, 78)
        elif path not in (
            RUNTIME,
            "/tmp",
            "/var/tmp",
            "/dev/shm",
            POOL + "/fs/home-upper",
            POOL + "/fs/home-work",
            POOL + "/fs/state-upper",
            POOL + "/fs/state-work",
        ):
            raise AssertionError("unexpected metadata path")
        return {
            "kind": "DIR",
            "uid": uid,
            "gid": 0 if uid == 0 else 987,
            "mode": 0o700,
            "device": device,
            "inode": inode,
        }

    def channels(self):
        return self.channel_data

    def finish(self):
        self.finished = True


class CheckProviderTests(unittest.TestCase):
    def test_host_filesystem_home_is_not_a_finite_provider_enforcer(self):
        reader = NativeFixture()
        result = producer().check_existing_provider(reader)
        self.assertFalse(result["storage_feasible"])
        self.assertEqual(result["first_failure"]["code"], "HOME_NOT_FINITE")
        self.assertFalse(result["full_readiness"])
        self.assertTrue(reader.closed)
        self.assertNotIn("/dev/root", repr(result))

    def test_changed_invocation_does_not_reach_storage_admission(self):
        reader = NativeFixture()
        actual = reader.identity()
        actual["invocation"] = "0" * 32
        reader.identity = lambda: actual
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "PROVIDER_IDENTITY")
        self.assertTrue(reader.closed)

    def test_real_effective_saved_or_fs_uid_drift_is_rejected(self):
        reader = NativeFixture()
        actual = reader.identity()
        actual["processes"][2]["uids"] = [997, 997, 997, 0]
        reader.identity = lambda: actual
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "PROVIDER_IDENTITY")
        self.assertFalse(result["storage_feasible"])

    def test_real_finite_backing_and_six_roles_are_only_feasibility(self):
        reader = FiniteFixture()
        result = producer().check_existing_provider(reader)
        self.assertTrue(result["storage_feasible"])
        self.assertEqual(result["state"], "FEASIBILITY_ONLY")
        self.assertFalse(result["full_readiness"])
        self.assertFalse(result["native_observation"])
        self.assertTrue(reader.finished)
        self.assertTrue(reader.closed)

    def test_readonly_parent_does_not_hide_new_writable_child(self):
        reader = FiniteFixture()
        reader.mounts += b"40 1 259:1 /PRIVATE_SENTINEL /run/new-child rw - ext4 /dev/root rw\n"
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "WRITABLE_ESCAPE")
        self.assertNotIn("PRIVATE_SENTINEL", repr(result))
        self.assertFalse(reader.finished)

    def test_six_writable_bindings_cannot_claim_different_backing(self):
        reader = FiniteFixture()
        reader.mounts = reader.mounts.replace(b"7:17 /vartmp", b"259:1 /vartmp")
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "WRITE_ROLE_MAPPING")
        self.assertFalse(result["storage_feasible"])

    def test_root_owned_image_claim_does_not_replace_regular_finite_object(self):
        reader = FiniteFixture()
        reader.image["kind"] = "DIR"
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "UNTRUSTED_FINITE_BACKING")
        self.assertFalse(result["storage_feasible"])

    def test_existing_writable_file_outside_device_is_insufficient(self):
        reader = FiniteFixture()
        reader.channel_data["fds"][0]["device"] = (259, 1)
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "WRITABLE_CHANNEL_UNPROVEN")
        self.assertFalse(result["storage_feasible"])

    def test_post_read_race_is_not_a_positive_or_private_error_message(self):
        reader = FiniteFixture()

        def changed():
            raise OSError(5, "PRIVATE_SENTINEL")

        reader.finish = changed
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "NATIVE_EVIDENCE_UNAVAILABLE")
        self.assertNotIn("PRIVATE_SENTINEL", repr(result))
        self.assertTrue(reader.closed)


class KernelReaderTests(unittest.TestCase):
    def test_status_uses_four_uids_not_proc_directory_owner(self):
        m = producer()
        raw = (
            b"Name:\tredacted\nPid:\t705711\nUid:\t997 997 997 997\nGid:\t987 987 "
            b"987 987\nGroups:\t987\nCapInh:\t0000\nCapPrm:\t0000\nCapEff:\t0000\n"
            b"CapBnd:\t0000\nCapAmb:\t0000\nNoNewPrivs:\t1\n"
        )
        actual = m.PosixReader.parse_status(raw, 705711)
        self.assertEqual(actual["uids"], [997] * 4)
        self.assertEqual(actual["gids"], [987] * 4)
        self.assertEqual(actual["groups"], [987])
        self.assertNotIn("redacted", repr(actual))
        for changed in (
            raw.replace(b"705711", b"1"),
            raw + b"Uid: 0 0 0 0\n",
            raw.replace(b"997 997 997 997", b"997 997 997"),
        ):
            with self.assertRaises(m.FeasibilityRejected):
                m.PosixReader.parse_status(changed, 705711)

    def test_stat_handles_comm_parentheses_and_zero_start_without_retaining_name(self):
        m = producer()
        fields = ["S", "1"] + ["0"] * 17 + ["0"]
        result = m.PosixReader.parse_stat(
            ("705711 (PRIVATE ) SENTINEL) " + " ".join(fields)).encode(), 705711
        )
        self.assertEqual(result, {"pid": 705711, "ppid": 1, "start": 0})
        self.assertNotIn("SENTINEL", repr(result))

    def test_exact_ipv4_endpoint_selected_socket_only(self):
        m = producer()
        header = (
            b"  sl local_address rem_address st tx_queue rx_queue tr tm->when "
            b"retrnsmt uid timeout inode\n"
        )
        row = (
            b" 0: 0100007F:2B68 00000000:0000 0A 00000000:00000000 00:00000000 "
            b"00000000 997 0 12345\n"
        )
        self.assertTrue(m.PosixReader.fixed_endpoint(header + row, {12345}))
        self.assertFalse(m.PosixReader.fixed_endpoint(header + row, {99}))
        self.assertFalse(
            m.PosixReader.fixed_endpoint(header + row.replace(b"0100007F", b"0200007F"), {12345})
        )
        self.assertFalse(m.PosixReader.fixed_endpoint(header + row.replace(b"0A", b"01"), {12345}))

    def test_shared_file_mapping_is_not_confused_with_anonymous_memory(self):
        m = producer()
        raw = (
            b"0001-0002 rw-s 00000000 07:11 7 /PRIVATE_SENTINEL\n0003-0004 rw-s "
            b"00000000 00:00 0 /dev/zero (deleted)\n"
        )
        result = m.PosixReader.parse_maps(raw)
        self.assertEqual(
            result,
            [
                {"device": (7, 17), "inode": 7, "shared": True, "writable": True},
                {"device": (0, 0), "inode": 0, "shared": True, "writable": True},
            ],
        )
        self.assertNotIn("PRIVATE_SENTINEL", repr(result))

    def test_fdinfo_requires_unique_mount_and_access_flags(self):
        m = producer()
        self.assertEqual(
            m.PosixReader.parse_fdinfo(b"pos: 0\nflags: 0100002\nmnt_id: 22\nino: 7\n"), (2, 22)
        )
        for raw in (b"flags: 2\n", b"flags: 2\nmnt_id: 22\nmnt_id: 23\n"):
            with self.assertRaises(m.FeasibilityRejected):
                m.PosixReader.parse_fdinfo(raw)


class MetadataOS:
    """Finite syscall seam; image/executable payloads are deliberately absent."""

    def __init__(self, real):
        from types import SimpleNamespace

        self.real = real
        self.next = 100
        self.handles = {}
        self.flags = {}
        self.closed = []
        self.failclose = set()
        self.data = {}
        self.items = {}
        self.SimpleNamespace = SimpleNamespace
        for key in ("O_PATH", "O_DIRECTORY", "O_CLOEXEC", "O_NOFOLLOW", "O_RDONLY"):
            setattr(self, key, getattr(real, key, {"O_PATH": 0x200000}.get(key, 0)))
        for path in (
            "/",
            "/srv",
            "/srv/quantmesh-opend-private-storage-20261031",
            "/dev",
            "/sys",
            "/sys/block",
            "/sys/block/loop17",
        ):
            self.add(path, 0o040755)
        self.add(
            "/srv/quantmesh-opend-private-storage-20261031/provider.ext4",
            0o100600,
            size=33554432,
            dev=66305,
            ino=1843320,
        )
        self.add("/dev/loop17", 0o060660, gid=6, rdev=(7 << 8) | 17)
        self.data.update(
            {
                "/sys/block/loop17/loop/backing_file": (
                    b"/srv/quantmesh-opend-private-storage-20261031/provider.ext4\n"
                ),
                "/sys/block/loop17/loop/offset": b"0\n",
                "/sys/block/loop17/loop/sizelimit": b"0\n",
                "/sys/block/loop17/size": b"65536\n",
                "/sys/block/loop17/ro": b"0\n",
            }
        )
        for path in self.data:
            self.add(path, 0o100444)

    def add(self, path, mode, uid=0, gid=0, dev=66305, ino=None, size=0, rdev=0):
        self.items[path] = self.SimpleNamespace(
            st_mode=mode,
            st_uid=uid,
            st_gid=gid,
            st_dev=dev,
            st_ino=ino or len(self.items) + 1,
            st_size=size,
            st_nlink=1,
            st_rdev=rdev,
            st_mtime_ns=1,
            st_ctime_ns=1,
        )

    def open(self, path, flags, dir_fd=None):
        from posixpath import normpath

        full = normpath(
            path if path.startswith("/") else self.handles[dir_fd][0].rstrip("/") + "/" + path
        )
        if full not in self.items:
            raise FileNotFoundError("PRIVATE_SENTINEL")
        self.next += 1
        self.handles[self.next] = [full, 0]
        self.flags[self.next] = flags
        return self.next

    def fstat(self, fd):
        return self.items[self.handles[fd][0]]

    def stat(self, path, dir_fd=None, follow_symlinks=True):
        from posixpath import normpath

        return self.items[
            normpath(
                path if path.startswith("/") else self.handles[dir_fd][0].rstrip("/") + "/" + path
            )
        ]

    def read(self, fd, count):
        path, pos = self.handles[fd]
        if path not in self.data:
            raise AssertionError("payload read forbidden")
        result = self.data[path][pos : pos + count]
        self.handles[fd][1] += len(result)
        return result

    def close(self, fd):
        self.closed.append(fd)
        if fd in self.failclose:
            raise OSError(5, "PRIVATE_SENTINEL")
        del self.handles[fd]

    def listdir(self, fd):
        if self.flags[fd] & self.O_PATH:
            raise OSError(9, "O_PATH cannot enumerate")
        path = self.handles[fd][0] + "/"
        return [
            p[len(path) :] for p in self.items if p.startswith(path) and "/" not in p[len(path) :]
        ]

    def major(self, dev):
        return (dev >> 8) & 0xFFF

    def minor(self, dev):
        return (dev & 255) | ((dev >> 12) & 0xFFFFFF00)


class SyscallBoundaryTests(unittest.TestCase):
    def test_actual_backing_reader_uses_geometry_without_image_payload(self):
        import os
        from unittest.mock import patch

        m = producer()
        fake = MetadataOS(os)
        r = m.PosixReader()
        with patch.object(m, "os", fake):
            actual = r.backing((7, 17), POOL)
            m._check_backing(actual, (7, 17))
            self.assertEqual(actual["image"]["inode"], 1843320)
            r.close()
        self.assertEqual(fake.handles, {})

    def test_actual_backing_reader_rejects_wrong_geometry_and_provider_block_access(self):
        import os
        from unittest.mock import patch

        for group, scalar in ((6, b"65535\n"), (987, b"65536\n")):
            m = producer()
            fake = MetadataOS(os)
            fake.data["/sys/block/loop17/size"] = scalar
            fake.items["/dev/loop17"].st_gid = group
            r = m.PosixReader()
            r.groups = {group}
            with patch.object(m, "os", fake):
                with self.assertRaises(m.FeasibilityRejected):
                    m._check_backing(r.backing((7, 17), POOL), (7, 17))
                r.close()
            self.assertEqual(fake.handles, {})

    def test_actual_reader_bound_closes_every_owned_descriptor(self):
        import os
        from unittest.mock import patch

        m = producer()
        fake = MetadataOS(os)
        fake.data["/sys/block/loop17/size"] = b"9" * 4097
        r = m.PosixReader()
        with patch.object(m, "os", fake):
            with self.assertRaises(m.FeasibilityRejected):
                r.backing((7, 17), POOL)
            r.close()
        self.assertEqual(fake.handles, {})

    def test_failed_intermediate_close_cannot_be_reported_as_all_closed(self):
        import os
        from unittest.mock import patch

        m = producer()
        fake = MetadataOS(os)
        r = m.PosixReader()
        with patch.object(m, "os", fake):
            fd = r.directory("/sys/block/loop17")
            fake.failclose.add(fd)
            with self.assertRaises(OSError):
                r.release(fd)
            with self.assertRaises(OSError):
                r.close()

    def test_actual_socket_scan_uses_enumerable_directory_not_opath(self):
        import os
        from unittest.mock import patch

        m = producer()
        fake = MetadataOS(os)
        fake.add("/proc", 0o040555)
        fake.add("/proc/705711", 0o040555)
        fake.add("/proc/705711/fd", 0o040500)
        r = m.PosixReader()
        with patch.object(m, "os", fake):
            d = r.directory("/proc/705711")
            self.assertEqual(r.socket_inodes(d), set())
            r.close()
        self.assertEqual(fake.handles, {})


class LifetimeTests(unittest.TestCase):
    def test_fd_and_mapping_channels_are_revalidated_after_collection(self):
        import os
        from unittest.mock import patch

        m = producer()
        fake = MetadataOS(os)
        for path in ("/proc", "/proc/705711", "/proc/705711/fd", "/proc/705711/fdinfo"):
            fake.add(path, 0o040500)
        fake.add("/proc/705711/fd/4", 0o100600, dev=(7 << 8) | 17, ino=9)
        fake.add("/proc/705711/fdinfo/4", 0o100400)
        fake.data["/proc/705711/fdinfo/4"] = b"flags: 2\nmnt_id: 22\n"
        fake.add("/proc/705711/maps", 0o100400)
        fake.data["/proc/705711/maps"] = b"0001-0002 rw-s 00000000 07:11 9 /PRIVATE_SENTINEL\n"
        r = m.PosixReader()
        with patch.object(m, "os", fake):
            d = r.directory("/proc/705711")
            r.processes = {705711: (d, None, None, None, None)}
            r.channels()
            fake.items["/proc/705711/fd/4"].st_dev = 66305
            with self.assertRaises(m.FeasibilityRejected):
                r.verify_channels()
            r.close()
        self.assertEqual(fake.handles, {})

    def test_deadline_is_checked_before_metadata_open(self):
        import os
        from unittest.mock import patch

        m = producer()
        fake = MetadataOS(os)
        r = m.PosixReader()
        r.deadline = 0
        with patch.object(m, "os", fake):
            with self.assertRaises(m.FeasibilityRejected):
                r.directory("/proc")
            self.assertEqual(fake.handles, {})
            r.close()

    def test_malformed_parent_graph_cannot_be_hidden_as_no_escape(self):
        reader = FiniteFixture()
        reader.mounts = reader.mounts.replace(b"25 2 ", b"25 999 ")
        result = producer().check_existing_provider(reader)
        self.assertEqual(result["first_failure"]["code"], "MOUNT_GRAPH_UNPROVEN")
        self.assertFalse(result["storage_feasible"])

    def test_close_failure_never_keeps_positive_feasibility(self):
        reader = FiniteFixture()

        def failed():
            raise OSError(5, "PRIVATE_SENTINEL")

        reader.close = failed
        result = producer().check_existing_provider(reader)
        self.assertFalse(result["storage_feasible"])
        self.assertFalse(result["owned_fds_closed"])
        self.assertEqual(result["cleanup"], ["OWNED_FD_CLOSE_UNPROVEN"])
        self.assertNotIn("PRIVATE_SENTINEL", repr(result))


class ClosedOutcomeTests(unittest.TestCase):
    def test_known_image_cannot_be_substituted_by_another_root_owned_inode(self):
        r = FiniteFixture()
        r.image["inode"] = 1843321
        actual = producer().check_existing_provider(r)
        self.assertFalse(actual["storage_feasible"])
        self.assertEqual(actual["first_failure"]["code"], "UNTRUSTED_FINITE_BACKING")

    def test_emitter_is_one_json_frame_and_all_qualification_stays_false(self):
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch

        m = producer()
        result = m.check_existing_provider(FiniteFixture())
        out = io.BytesIO()
        with (
            patch.object(m, "check_existing_provider", return_value=result),
            patch.object(m.sys, "stdout", SimpleNamespace(buffer=out)),
        ):
            self.assertEqual(m.main(["--check"]), 0)
        raw = out.getvalue()
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertEqual(json.loads(raw), result)
        self.assertFalse(result["full_readiness"])
        self.assertFalse(result["native_observation"])
        self.assertEqual(
            [result[k] for k in ("SDK", "permit", "intent", "service_actions")], [0] * 4
        )


class HostBindingTests(unittest.TestCase):
    def test_machine_digest_uses_exact_public_bytes_including_newline(self):
        import hashlib
        from unittest.mock import patch

        m = producer()
        raw = b"fixed-public-test-machine\n"
        with patch.object(m, "MACHINE", hashlib.sha256(raw).hexdigest()):
            self.assertTrue(m.PosixReader.verify_machine(raw))
            with self.assertRaises(m.FeasibilityRejected):
                m.PosixReader.verify_machine(raw.rstrip())


if __name__ == "__main__":
    unittest.main()
