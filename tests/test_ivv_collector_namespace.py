"""READY verification must not move periodic provider samples or admit a foreign loopback."""

import json
import stat
import sys
import types
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace as NS

import pytest
from test_ivv_provider_binding import AUTH, INV
from test_ivv_provider_binding import receipt as legacy_receipt

NONCE = "b" * 32
UNIT = "quantmesh-opend-console@" + NONCE + ".service"


def receipt(p):
    obj = legacy_receipt(p)
    obj["schema"] = "qm.opend.provider-binding.v2"
    obj["launch"].update(
        nonce=NONCE,
        unit=UNIT,
        cgroup="/system.slice/" + UNIT,
        schema="qm.opend.attributed-launch.v2",
    )
    return obj


def module(name):
    source = Path(__file__).resolve().parents[1] / "tools/research" / (name + ".py")
    m = types.ModuleType("collector_test_" + name)
    m.__file__ = str(source)
    sys.modules[m.__name__] = m
    exec(compile(source.read_bytes(), m.__file__, "exec"), m.__dict__)
    return m


class ClockTest(unittest.TestCase):
    def run_clock(self, *, fault=None):
        r, p = module("ivv_trusted_runner"), module("ivv_native_producer")
        doc = receipt(p)
        closed = []
        now = [0.0]
        growth, resources, namespaces, sent, pending = [], [], [], [], []
        scope = NS(
            pid=77,
            pidfd=12,
            check_pid=lambda: None,
            check_resources=lambda: None,
            verify_manager=lambda: None,
        )
        row = dict(pid=3003, uids=[997] * 4, start=555)

        def ns_stat(fd):
            return NS(
                st_dev=3 if fd == 111 and fault == "device" else 4,
                st_ino=56 if fd == 111 and fault == "different" else 55,
            )

        kernel = NS(
            O_RDONLY=0,
            O_CLOEXEC=1,
            open=lambda n, flags, dir_fd: 100 + dir_fd,
            fstat=ns_stat,
            stat=lambda n, dir_fd: (
                NS(st_dev=4, st_ino=54)
                if fault == "renamed" and dir_fd == 12
                else ns_stat(dir_fd + 100)
            ),
        )

        def acquire(b):
            held = []

            def retain(fd):
                held.append(fd)
                return fd

            def close():
                if held:
                    closed.append(tuple(held))
                    if fault == "close":
                        raise OSError("modeled close uncertainty")
                    if fault == "deadline":
                        now[0] += 2.0

            reader = NS(
                binding=b,
                vendor_pid=3003,
                processes={3003: (12, None, row)},
                directory=lambda s, *a: 11 if s == "77" else 3,
                keep=retain,
                finish=lambda: ["PROVIDER_RACE"] if held and fault == "drift" else [],
                close=close,
                socket_inodes=lambda fd: {900},
                read=lambda *a: b"hdr\n0: 0100007F:2B68 00000000:0000 0A 0 0 0 0 0 900\n",
            )
            return reader

        p.OperatorReader = acquire

        def grow(reader):
            growth.append(now[0])
            return int(now[0])

        def controls(reader):
            resources.append(now[0])
            return {"observed": now[0]}

        native = NS(
            RestoredRoleGrowth=lambda producer, binding: NS(sample=grow),
            _operator_sources=lambda *a: 987,
            _operator_identity=lambda *a: {"machine": p.MACHINE},
            _provider_controls=controls,
            trusted_quote_configuration=lambda plan: ({}, "a" * 64),
        )
        r.time = NS(monotonic=lambda: now[0])

        def open_namespace(name, flags, dir_fd):
            if dir_fd == 12:
                namespaces.append(now[0])
            return 100 + dir_fd

        kernel.open = open_namespace
        kernel.statvfs = lambda path: NS(f_bavail=1 << 30, f_frsize=4096)
        r.os = kernel
        r.read_ref = lambda ref, path: b'{"G":1,"P":1}'
        r._child_kernel = lambda *a, **kw: {"namespace_inode": 44}
        r._accept_executable_origin = lambda *a, **kw: {}
        r._Provider.peer = lambda self, pid: (901, 900)

        verify = r._Provider.verify_network

        def verify_unchanged(monitor, owned):
            before = {key: value for key, value in vars(monitor).items()}
            periodic = (list(growth), list(resources))
            verify(monitor, owned)
            self.assertEqual(vars(monitor), before)
            self.assertEqual((growth, resources), periodic)

        r._Provider.verify_network = verify_unchanged

        def authorize(context, plan, owned, monitor):
            self.assertEqual(namespaces, [1.0])
            self.assertEqual(closed, [(112, 111)])
            self.assertTrue(monitor.first)
            pending.append(monitor.next)
            return ({}, {}, {}, {})

        r._authorize = authorize
        events = [(1.0, "ready"), (6.25, "observe")]

        def wait(reads, writes, errors, timeout):
            arrival, _ = events[0]
            wake = min(arrival, now[0] + timeout)
            now[0] = wake
            return ([11] if wake == arrival else [], [], [])

        r.select = NS(select=wait)

        class Observed(Exception):
            pass

        def send(packet):
            sent.append(packet)
            if "snapshot" in packet:
                raise Observed()

        channel = NS(
            s=11, recv=lambda pid: {"op": events.pop(0)[1], "executable_origin": {}}, send=send
        )
        values = {"_recovery_mode": "connection-000006", "catalog_ref": {"provider_binding": doc}}
        context = ({"budget_ref": {}}, values, None, None, native, p)
        wanted = OSError if fault == "close" else r.Refused if fault else Observed
        with self.assertRaises(wanted):
            r._supervise(scope, channel, 700, context, {"started_monotonic": 0})
        if fault:
            self.assertEqual(closed, [(112, 111)])
            self.assertEqual((namespaces, pending, sent), ([1.0], [], [{"op": "enter"}]))
            return
        self.assertEqual([m.get("op") for m in sent], ["enter", "go", None])
        snapshot = sent[-1]["snapshot"]
        observed = dict(
            deadline_at_go=pending[0],
            sample_times=growth,
            resource_times=resources,
            snapshot_time=snapshot["sampled_monotonic"],
            age=now[0] - snapshot["sampled_monotonic"],
            growth=snapshot["sample"]["incremental_bytes"],
            resource=snapshot["resource_values"]["observed"],
        )
        print("successful GO/served snapshot", json.dumps(observed, sort_keys=True), flush=True)
        self.assertEqual(
            observed,
            dict(
                deadline_at_go=5.0,
                sample_times=[0.0, 5.0],
                resource_times=[0.0, 5.0],
                snapshot_time=5.0,
                age=1.25,
                growth=5,
                resource=5.0,
            ),
        )

    def test_different_namespace_stops_before_grant(self):
        self.run_clock(fault="different")

    def test_successful_go_keeps_original_sample_deadline(self):
        self.run_clock()

    def test_changed_device_or_uncertain_closure_never_grants(self):
        for fault in ("device", "renamed", "close", "drift", "deadline"):
            with self.subTest(fault=fault):
                self.run_clock(fault=fault)


def test_only_restored_runtime_growth_path_changes():
    n, p = module("ivv_dev_native"), module("ivv_native_producer")
    assert n.RoleGrowth._role_paths == n._ROLE_PATHS
    for nonce in ("b" * 32, "c" * 32, p.RESTORE_NONCE):
        obj = receipt(p) if nonce != p.RESTORE_NONCE else legacy_receipt(p)
        if nonce != p.RESTORE_NONCE:
            unit = "quantmesh-opend-console@" + nonce + ".service"
            obj["launch"].update(nonce=nonce, unit=unit, cgroup="/system.slice/" + unit)
        binding = p.ProviderExecution.verified_record(obj)
        assert n.RestoredRoleGrowth(p, binding)._role_paths == tuple(
            "/run/quantmesh-opend-console-" + nonce if path == n._RUNTIME else path
            for path in n._ROLE_PATHS
        )
    with pytest.raises(TypeError):
        n.RoleGrowth("arbitrary")
    with pytest.raises(n.NativeUnproven):
        n.RestoredRoleGrowth(p, NS(nonce="../../foreign"))


def test_actual_monitor_accepts_attributed_restored_cohort(monkeypatch):
    p, r = module("ivv_native_producer"), module("ivv_trusted_runner")
    obj = receipt(p)
    public = b"reviewed source"
    obj["launch"]["launcher_sha256"] = r.digest(public)
    control = r.raw_json(
        {
            "schema": "qm.opend.operator-restore.v2",
            "authority_sha256": AUTH,
            "claims": {
                "nonce": NONCE,
                "launcher_sha256": r.digest(public),
                "gateway_uid": 997,
                "gateway_gid": 987,
            },
        }
    )
    obj["launch"]["control_sha256"] = r.digest(control)
    rows = [
        dict(
            **v,
            role=k,
            uids=[997] * 4,
            gids=[987] * 4,
            groups=[987],
            exe_verified=True,
            cgroup_unit=UNIT,
            caps=0,
            nnp=1,
        )
        for k, v in obj["processes"].items()
    ]
    observed = dict(
        machine=p.MACHINE,
        unit=UNIT,
        invocation=INV,
        main_pid=3001,
        active="active",
        substate="running",
        vendor_loopback11112=True,
        processes=rows,
    )
    reader = NS(
        identity=lambda: observed,
        processes={3003: (5, None, rows[2])},
        socket_inodes=lambda fd: {900},
        read=lambda *args: b"hdr\n0: 0100007F:2B68 00000000:0000 0A 0 0 0 0 0 900\n",
        close=lambda: None,
        finish=lambda: [],
    )
    monkeypatch.setattr(p, "OperatorReader", lambda *a: reader)
    native = module("ivv_dev_native")
    deploy = Path(__file__).resolve().parents[1] / "deploy/aws/opend"

    def original(path, limit, *, mode=None):
        if path.endswith(NONCE + ".json") or path.endswith("PROVIDER-BINDING.json"):
            assert mode == 0o444
            return control if path.endswith(NONCE + ".json") else r.raw_json(obj)
        return public if path.endswith(".py") else (deploy / Path(path).name).read_bytes()

    monkeypatch.setattr(native, "_protected_bytes", original)
    monkeypatch.setattr(
        native, "RestoredRoleGrowth", lambda producer, binding: NS(sample=lambda reader: 0)
    )
    monkeypatch.setattr(native, "trusted_quote_configuration", lambda plan: ({}, "a" * 64))
    monkeypatch.setattr(native, "_provider_controls", lambda reader: {})
    monitor = r._Provider(
        native,
        p,
        None,
        {"started_monotonic": r.time.monotonic()},
        {},
        additional="connection-000006",
        binding=obj,
    )

    def read(ref, path, *args):
        if path.name == "budget.json":
            return b'{"G":1,"P":1}'
        raw = control if path.name == NONCE + ".json" else r.raw_json(obj)
        assert ref["sha256"] == r.digest(raw)
        return raw

    monkeypatch.setattr(r, "read_ref", read)
    monkeypatch.setattr(
        r.os, "statvfs", lambda p: NS(f_bavail=1 << 30, f_frsize=4096), raising=False
    )
    assert monitor.sample()["provider_actor"]["pid"] == 3003

    class Proc(PurePosixPath):
        def iterdir(self):
            assert str(self) == "/proc/77/fd"
            return [NS(stat=lambda: NS(st_mode=stat.S_IFSOCK, st_ino=901))]

        def read_bytes(self):
            assert str(self) == "/proc/77/net/tcp"
            return (
                b"header\n0: 0100007F:9000 0100007F:2B68 01 0 0 0 0 0 901\n"
                b"1: 0100007F:2B68 0100007F:9000 01 0 0 0 0 0 900\n"
            )

    monkeypatch.setattr(r, "Path", Proc)
    assert monitor.peer(77) == (901, 900)
    reader.socket_inodes = lambda fd: {988}
    with pytest.raises(r.Refused, match="CAPTURE_PEER_NOT_PROVIDER_OWNED"):
        monitor.peer(77)
    observed["invocation"] = "0" * 32
    with pytest.raises(p.FeasibilityRejected, match="PROVIDER_IDENTITY"):
        monitor.peer(77)
