"""Operator-only public snapshots under modeled kernel facts."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from test_ivv_dev_native import native_module
from test_ivv_native_producer import producer

NONCE = "4ae19a7fad3fdaf8e3d23c1a4eb4b3d4"
UNIT = "quantmesh-opend-console@" + NONCE + ".service"
GROUP = "/system.slice/" + UNIT
INV = "4" * 32
AUTH = "0d2965519662b53c448e003f6a8ddcf8d07834d399da2ece4ab2407475f9a945"
VENDOR = "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601"
TEMPLATE = "b23d91ec4d5b377d57d8a0cae1971974d4268f1faa3a5fed06dc0d0add867890"
PROFILE = "0e0b15be83e2b7b435d4e6dbb94f2cbd9c7833e681c4af517e361f5b80b40e17"


def receipt(p):
    launch = dict(
        schema="qm.opend.attributed-launch.v1",
        nonce=NONCE,
        authority_sha256=AUTH,
        control_sha256="2" * 64,
        launcher_sha256="3" * 64,
        unit=UNIT,
        invocation=INV,
        cgroup=GROUP,
        main_pid=3001,
        pane_pid=3002,
        vendor_pid=3003,
        vendor_start=555,
        claim_dev=33,
        claim_ino=350,
    )
    return {
        "schema": "qm.opend.provider-binding.v1",
        "launch": launch,
        "machine_sha256": p.MACHINE,
        "template_sha256": TEMPLATE,
        "vendor_sha256": VENDOR,
        "profile_sha256": PROFILE,
        "processes": {
            role: dict(pid=pid, start=start, ppid=parent, mnt=44, net=55)
            for role, pid, start, parent in [
                ("TMUX", 3001, 501, 1),
                ("PYTHON", 3002, 530, 3001),
                ("VENDOR", 3003, 555, 3002),
            ]
        },
    }


@pytest.mark.parametrize(
    "field,value",
    [
        (("schema",), "qm.opend.operator-login-origin.v1"),
        (("machine_sha256",), "f" * 64),
        (("template_sha256",), "f" * 64),
        (("profile_sha256",), "f" * 64),
        (("vendor_sha256",), "f" * 64),
        (("launch", "authority_sha256"), "f" * 64),
        (("launch", "nonce"), "a" * 32),
        (("launch", "invocation"), "bad"),
        (("launch", "cgroup"), "/system.slice/../" + UNIT),
        (("launch", "vendor_start"), True),
        (("launch", "main_pid"), 1),
        (("processes", "VENDOR", "ppid"), 3001),
        (("processes", "PYTHON", "mnt"), 99),
        (("processes", "VENDOR", "net"), 88),
        (("processes", "PYTHON", "pid"), 3003),
    ],
)
def test_closed_binding_rejects_substitution(field, value):
    p = producer()
    obj = receipt(p)
    node = obj
    for key in field[:-1]:
        node = node[key]
    node[field[-1]] = value
    with pytest.raises(p.FeasibilityRejected):
        p.ProviderExecution.verified_record(obj)


def test_cross_use_is_rejected_before_live_reads():
    import hashlib
    import json

    p, n = producer(), native_module()
    for operator in (False, True):
        obj = receipt(p)
        if operator:
            obj["schema"] = "qm.opend.operator-login-origin.v1"
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        pin = hashlib.sha256(raw).hexdigest()
        validate = p.validate_operator_login_origin if operator else p.validate_provider_binding
        other = p.validate_provider_binding if operator else p.validate_operator_login_origin
        binding = validate(raw, pin)
        with pytest.raises(p.FeasibilityRejected):
            other(raw, pin)
        for malformed in (b" " + raw, raw + b"\n", b"{}"):
            with pytest.raises(p.FeasibilityRejected):
                validate(malformed, pin)
        wrong = n.verified_provider_snapshot if operator else n.verified_operator_login_snapshot
        with pytest.raises(n.NativeUnproven):
            wrong(p, binding)


@pytest.mark.parametrize(
    "fault",
    [None, "invocation", "inactive", "foreign", "fragment", "dropin", "descendant", "cgroup"],
)
def test_held_current_manager_and_exact_membership(monkeypatch, fault):
    p = producer()
    b = p.ProviderExecution.verified_record(receipt(p))
    reader = p.OperatorReader(b)
    attrs = dict(
        Id=UNIT,
        ActiveState="active",
        SubState="running",
        MainPID="3001",
        InvocationID=INV,
        ControlGroup=GROUP,
        FragmentPath="/etc/systemd/system/quantmesh-opend-console@.service",
        DropInPaths="",
    )
    for case, k, v in [
        ("invocation", "InvocationID", "7" * 32),
        ("inactive", "ActiveState", "inactive"),
        ("fragment", "FragmentPath", "/else"),
        ("dropin", "DropInPaths", "override"),
        ("cgroup", "ControlGroup", "/system.slice/other"),
    ]:
        if case == fault:
            attrs[k] = v
    stream = [("\n".join(k + "=" + v for k, v in attrs.items()) + "\n").encode(), b""]

    class Pipe:
        def fileno(self):
            return 10

        def close(self):
            pass

    proc = SimpleNamespace(stdout=Pipe(), wait=lambda **kw: 0, poll=lambda: 0)

    def popen(cmd, **kw):
        assert cmd[-1] == UNIT and cmd[1] == "show"
        assert "FragmentPath,DropInPaths" in cmd[3]
        return proc

    monkeypatch.setattr(p.subprocess, "Popen", popen)
    monkeypatch.setattr(
        p, "os", SimpleNamespace(set_blocking=lambda *args: None, read=lambda *args: stream.pop(0))
    )
    monkeypatch.setattr(p, "select", SimpleNamespace(select=lambda a, *args: (a, [], [])))
    opened = []

    def directory(path):
        assert path == "/sys/fs/cgroup" + GROUP
        opened.append(22)
        return 22

    reader.directory = directory
    reader.read = lambda fd, name, bound: (
        (b"3001\n3002\n999\n" if fault == "foreign" else b"3001\n3002\n3003\n")
        if name == "cgroup.procs"
        else (b"nr_descendants 1\n" if fault == "descendant" else b"nr_descendants 0\n")
    )
    reader.release = lambda fd: opened.remove(fd)
    if fault:
        with pytest.raises(p.FeasibilityRejected):
            reader.manager()
    else:
        assert reader.manager() == attrs
    assert not opened


@pytest.mark.parametrize("fault", [None, "foreign", "wrong_ip", "ipv6", "duplicate", "missing"])
def test_listener_is_unique_and_vendor_owned(fault):
    p = producer()
    reader = p.OperatorReader(p.ProviderExecution.verified_record(receipt(p)))
    data = b"0: 0100007F:2B68 00000000:0000 0A 0 0 0 0 0 900\n"
    reader.socket_inodes = lambda fd: {901 if fault == "foreign" else 900}
    reader.read = lambda fd, k, bound: (
        b"header\n" + (data if fault == "ipv6" else b"")
        if k.endswith("6")
        else b"header\n"
        + (
            data.replace(b"0100007F", b"00000000")
            if fault == "wrong_ip"
            else b""
            if fault == "missing"
            else data * 2
            if fault == "duplicate"
            else data
        )
    )
    if fault:
        with pytest.raises(p.FeasibilityRejected):
            reader.bound_listener(70)
    else:
        assert reader.bound_listener(70) == 900


@pytest.mark.parametrize("operator", [True, False])
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "gid",
        "supplementary",
        "memory_high",
        "process_drift",
        "current_control",
        "source",
        "finish",
    ],
)
@pytest.mark.parametrize("nonce", [NONCE, "1" * 32, "f" * 32])
def test_current_snapshot_checks_owned_origin_without_prelogin_endpoint_assumption(
    monkeypatch, operator, fault, nonce
):
    p, n = producer(), native_module()
    obj = receipt(p)
    version = "v1" if nonce == NONCE else "v2"
    unit = "quantmesh-opend-console@" + nonce + ".service"
    group = "/system.slice/" + unit
    obj["schema"] = "qm.opend.provider-binding." + version
    obj["launch"].update(
        schema="qm.opend.attributed-launch." + version, nonce=nonce, unit=unit, cgroup=group
    )
    if operator:
        obj["schema"] = "qm.opend.operator-login-origin." + version
    import hashlib
    import json

    def encode(v):
        return json.dumps(v, sort_keys=True, separators=(",", ":")).encode()

    def sha(raw):
        return hashlib.sha256(raw).hexdigest()

    source = b"observed merged launcher"
    control = encode(
        {
            "schema": "qm.opend.operator-restore." + version,
            "authority_sha256": AUTH,
            "claims": {
                "nonce": nonce,
                "launcher_sha256": sha(source),
                "gateway_gid": 987,
                "gateway_uid": 997,
            },
        }
    )
    obj["launch"].update(control_sha256=sha(control), launcher_sha256=sha(source))
    raw = encode(obj)
    validate = p.validate_operator_login_origin if operator else p.validate_provider_binding
    binding = validate(raw, sha(raw))
    assert binding.nonce == nonce
    folder = Path(__file__).resolve().parents[1] / "deploy/aws/opend"
    name = "OPERATOR-LOGIN-ORIGIN.json" if operator else "PROVIDER-BINDING.json"

    def protected(path, limit, *, mode=None):
        directory = (
            "/var/lib/quantmesh-opend-restore-20261105-01"
            if nonce == NONCE
            else "/var/lib/quantmesh-opend-operator-restores/" + nonce
        )
        if path == directory + "/" + name:
            assert mode == 0o444
            return raw
        if path == "/etc/quantmesh/opend/operator-restores/" + nonce + ".json":
            assert mode == 0o444
            return b"{}" if fault == "current_control" else control
        if path.endswith("stage_console.py"):
            return b"changed" if fault == "source" else source
        return (folder / Path(path).name).read_bytes()

    monkeypatch.setattr(n, "_protected_bytes", protected)
    reader = p.OperatorReader(binding)
    monkeypatch.setattr(p, "OperatorReader", lambda kept: reader)
    monkeypatch.setattr(p, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(p, "os", SimpleNamespace(geteuid=lambda: 0, fstat=lambda fd: fd))
    reader.stamp = lambda val: val
    reader.directory = lambda path, *a, **kw: int(path) if path.isdigit() else 2
    reader.verify_machine = lambda raw: None
    observed = {
        "Id": unit,
        "InvocationID": INV,
        "ActiveState": "active",
        "SubState": "running",
        "MainPID": "3001",
        "ControlGroup": group,
    }
    reader.manager = lambda: observed
    names = {row["pid"]: role for role, row in obj["processes"].items()}

    def process(pid, fd):
        role = names[pid]
        row = dict(
            obj["processes"][role],
            groups=[8] if fault == "supplementary" else [987],
            gids=[33 if fault == "gid" else 987] * 4,
            uids=[997] * 4,
            nnp=1,
            caps=0,
            cgroup_unit=unit,
        )
        if fault == "process_drift" and role == "VENDOR":
            row["start"] += 1
        return row

    reader.process = process
    reader.executable = lambda fd, role: (fd + 100, (1, fd))
    resources = {
        "memory.max": b"1073741824",
        "memory.high": b"max" if fault == "memory_high" else b"805306368",
        "memory.swap.max": b"0",
        "cpu.max": b"50000 100000",
        "pids.max": b"128",
    }

    def read(fd, name, bound):
        if name == "machine-id":
            return b"modeled-machine-id"
        if name == "memory.max":
            events.append("resources")
        return resources[name]

    reader.read = read
    reader.release = lambda fd: None
    events = []

    def listener(fd):
        assert fd == 3003 and not operator
        events.append("listener")
        return 918

    reader.bound_listener = listener
    reader.finish = lambda: ["PROVIDER_RACE"] if fault == "finish" else []
    reader.close = lambda: events.append("closed")
    check = n.verified_operator_login_snapshot if operator else n.verified_provider_snapshot
    if fault:
        with pytest.raises((p.FeasibilityRejected, n.NativeUnproven)):
            check(p, binding)
        if fault not in ("source", "current_control"):
            assert events[-1] == "closed"
    else:
        result = check(p, binding)
        assert result["main_pid"] == 3001 and result["invocation"] == INV
        assert ("vendor_loopback11112" in result) is (not operator)
        assert events == (
            ["resources", "closed"] if operator else ["listener", "resources", "closed"]
        )


@pytest.mark.parametrize("operator", [True, False])
def test_exact_deployed_slice(operator):
    import hashlib
    import json

    p = producer()
    doc = receipt(p)
    if operator:
        doc["schema"] = "qm.opend.operator-login-origin.v1"
    validate = p.validate_operator_login_origin if operator else p.validate_provider_binding
    doc["launch"]["cgroup"] = r"/system.slice/system-quantmesh\x2dopend\x2dconsole.slice/" + UNIT

    def parse():
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        return validate(raw, hashlib.sha256(raw).hexdigest())

    assert parse().cgroup == doc["launch"]["cgroup"]
    doc["launch"]["cgroup"] = doc["launch"]["cgroup"].replace(r"\x2d", r"\x2f")
    with pytest.raises(p.FeasibilityRejected):
        parse()


@pytest.mark.parametrize("entry", ["legacy_reader", "growth", "legacy_check"])
def test_collector_entry_does_not_take_operator_binding(entry):
    p, native = producer(), native_module()
    binding = p.ProviderExecution.verified_record(receipt(p))
    with pytest.raises(TypeError):
        if entry == "legacy_reader":
            p.PosixReader(binding)
        elif entry == "growth":
            native.RoleGrowth("/run/foreign")
        else:
            p._check_identity({}, binding)
    assert p.PosixReader().unit == p.UNIT


@pytest.mark.parametrize(
    "fault",
    [
        "reserved_restore",
        "reserved_session",
        "reserved_recovery",
        "path",
        "uppercase",
        "unit",
        "v1_packet",
        "v1_original",
        "other_role",
        "duplicate",
    ],
)
def test_v2_receipt_must_bind_one_new_instance_before_any_path(fault):
    import hashlib
    import json

    p = producer()
    nonce = {
        "reserved_restore": NONCE,
        "reserved_session": p.NONCE,
        "reserved_recovery": "c8f0d0de4ca641a491fca6df24c66ceb",
        "path": "../" + "e" * 29,
        "uppercase": "F" * 32,
    }.get(fault, "b" * 32)
    obj = receipt(p)
    unit = "quantmesh-opend-console@" + nonce + ".service"
    obj["schema"] = "qm.opend.operator-login-origin.v2"
    obj["launch"].update(
        nonce=nonce,
        unit=unit,
        cgroup="/system.slice/" + unit,
        schema="qm.opend.attributed-launch.v2",
    )
    if fault == "unit":
        obj["launch"]["unit"] = UNIT
    elif fault == "v1_packet":
        obj["launch"]["schema"] = "qm.opend.attributed-launch.v1"
    elif fault == "v1_original":
        obj["schema"] = "qm.opend.operator-login-origin.v1"
    elif fault == "other_role":
        obj["schema"] = "qm.opend.provider-binding.v2"
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    if fault == "duplicate":
        raw = b'{"schema":"qm.opend.operator-login-origin.v2",' + raw[1:]
    with pytest.raises(p.FeasibilityRejected):
        p.validate_operator_login_origin(raw, hashlib.sha256(raw).hexdigest())
