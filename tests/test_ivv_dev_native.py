"""Native socket attribution with literal read-only procfs and syscall records."""

import importlib.util
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest


def native_module():
    path = Path(__file__).resolve().parents[1] / "tools/research/ivv_dev_native.py"
    spec = importlib.util.spec_from_file_location("qm_native_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNTIME = "/run/quantmesh-opend-console-eabdda557bc641fdbda60ecd993fb2a0"
TCP = b"header\n 0: 0100007F:2B68 00000000:0000 0A 0:0 00:0 0 997 0 111000\n"
UNIX = (
    b"header\n0000: 00000002 00000000 00010000 0001 01 5965500 " + RUNTIME.encode() + b"/socket\n"
)


@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "owner_read_write",
        "unknown",
        "extra",
        "domain",
        "connected",
        "parent",
        "socket_dac",
        "wrong_link",
        "fdinfo_inode",
        "fd_race",
        "table_race",
        "outside",
    ],
)
def test_initial_sockfs_inventory(monkeypatch, mode):
    m = native_module()
    tmux, python, vendor = 12, 11, 13
    fd_names = {tmux: {"9": 5965500}, python: {}, vendor: {"6": 111000}}
    if mode == "extra":
        fd_names[vendor]["7"] = 222222
    if mode == "outside":
        fd_names[python]["4"] = fd_names[vendor].pop("6")
    tables = {"net/tcp": TCP, "net/unix": UNIX}
    if mode == "unknown":
        tables["net/tcp"] = TCP.replace(b"111000", b"111001")
    if mode == "domain":
        tables["net/unix"] = UNIX.replace(b"0001 01", b"0002 01")
    if mode == "connected":
        tables["net/unix"] = UNIX.replace(b"0001 01", b"0001 03")

    def st(perm, inode):
        return SimpleNamespace(
            st_mode=perm, st_dev=3, st_ino=inode, st_nlink=1, st_uid=997, st_gid=987, st_rdev=0
        )

    handles = {}
    procfd = {}
    socket_handles = {}
    opened = set()

    def acquire(table, value):
        handle = 100 + len(handles)
        handles[handle] = value
        table[handle] = value
        opened.add(handle)
        return handle

    def os_open(path, flags, *, dir_fd):
        if path == "fd":
            assert dir_fd in fd_names and flags == 7
            return acquire(procfd, dir_fd)
        assert flags == 10  # O_PATH, CLOEXEC. Dereference the proc fd magic link.
        return acquire(socket_handles, fd_names[procfd[dir_fd]][path])

    def readlink(path):
        assert path.startswith("/proc/self/fd/")
        handle = int(path.split("/")[-1])
        assert handle in opened
        return f"socket:[{socket_handles[handle] + (mode == 'wrong_link')}]"

    def fstat(handle):
        if handle == 16:
            return st(stat.S_IFDIR | (0o750 if mode == "parent" else 0o700), 700)
        if handle == 17:
            perm = {"socket_dac": 0o770, "owner_read_write": 0o600}.get(mode, 0o700)
            return st(stat.S_IFSOCK | perm, 901)
        return st(stat.S_IFSOCK | 0o777, socket_handles[handle])

    class Reader:
        processes = {705646: (tmux,), 705651: (python,), 705711: (vendor,)}
        root = 10
        reads = 0

        def read(self, parent, path, maximum):
            if path.startswith("fdinfo/"):
                inode = fd_names[parent][path.split("/")[-1]]
                return (
                    f"flags:\t02\nmnt_id:\t90\nino:\t{inode + (mode == 'fdinfo_inode')}\n".encode()
                )
            assert parent == vendor
            if path == "net/tcp":
                self.reads += 1
                if self.reads > 1 and mode == "table_race":
                    return TCP.replace(b"111000", b"111001")
            return tables[path]

        def tick(self):
            pass

        def held_path(self, path, root):
            assert root == self.root
            fd = {RUNTIME: 16, RUNTIME + "/socket": 17}[path]
            opened.add(fd)
            return fd

        def keep(self, fd):
            return fd

        def release(self, fd):
            opened.remove(fd)

    def proc_stat(name, *, dir_fd):
        inode = fd_names[procfd[dir_fd]][name]
        return st(stat.S_IFSOCK | 0o777, inode + (mode == "fd_race"))

    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            O_PATH=8,
            O_CLOEXEC=2,
            O_DIRECTORY=4,
            O_NOFOLLOW=1,
            O_RDONLY=0,
            open=os_open,
            fstat=fstat,
            readlink=readlink,
            stat=proc_stat,
            listdir=lambda fd: list(fd_names[procfd[fd]]),
        ),
    )
    if mode in ("valid", "owner_read_write"):
        assert m.initial_socket_roles(Reader()) == {
            "TMUX_LISTENER": 5965500,
            "VENDOR_LISTENER": 111000,
        }
    else:
        with pytest.raises(m.NativeUnproven):
            m.initial_socket_roles(Reader())
    assert not opened


@pytest.mark.parametrize(
    "case",
    ["grow", "rename_race", "slow", "entry_limit", "symlink", "highwater_limit", "shared_alias"],
)
def test_metadata_sample_uses_inode_high_water(monkeypatch, case):
    m = native_module()
    from types import SimpleNamespace as NS

    R = (
        "/var/lib/quantmesh-opend",
        "/var/lib/quantmesh-opend-stage",
        RUNTIME,
        "/tmp",
        "/var/tmp",
        "/dev/shm",
    )
    directories = {name: pos + 20 for pos, name in enumerate(R)}
    held = set()
    state = {"size": 512, "stamp": 3, "clock": 0, "many": False}

    def st(mode, inode, size=0, stamp=3):
        return NS(
            st_dev=5,
            st_ino=inode,
            st_mode=mode,
            st_nlink=1,
            st_uid=997,
            st_gid=987,
            st_size=size,
            st_blocks=(size + 511) // 512,
            st_ctime_ns=stamp,
            st_mtime_ns=stamp,
        )

    def fstat(fd):
        return st(stat.S_IFDIR | 0o700, fd % 100, stamp=state["stamp"])

    def open_dir(path, flags, *, dir_fd):
        assert path == "." and flags == 7
        held.add(dir_fd + 100)
        return dir_fd + 100

    def scandir(fd):
        names = ["opaque-name"] if fd == 120 or (fd == 121 and case == "shared_alias") else []
        if state["many"] and fd == 120:
            names = map(str, range(16385))

        class Cursor:
            def __enter__(self):
                return (NS(name=name) for name in names)

            def __exit__(self, *args):
                pass

        return Cursor()

    def file_stat(path, *, dir_fd, follow_symlinks):
        assert not follow_symlinks
        if case == "rename_race" and state["size"] > 512:
            state["stamp"] += 1
        if case == "slow" and state["size"] > 512:
            state["clock"] = 3
        kind = stat.S_IFLNK if case == "symlink" else stat.S_IFREG
        return st(kind | 0o600, 501, state["size"])

    class Reader:
        root = 10

        def held_path(self, path, root):
            assert root == 10
            fd = directories[path]
            held.add(fd)
            return fd

        def keep(self, fd):
            return fd

        def release(self, fd):
            held.remove(fd)

    monkeypatch.setattr(
        m,
        "os",
        NS(
            open=open_dir,
            fstat=fstat,
            scandir=scandir,
            stat=file_stat,
            O_RDONLY=0,
            O_NOFOLLOW=1,
            O_CLOEXEC=2,
            O_DIRECTORY=4,
        ),
    )
    series = m.RoleGrowth()
    monkeypatch.setattr(m.time, "monotonic", lambda: state["clock"])
    reader = Reader()

    def sample():
        return series.sample(reader)

    try:
        if case == "symlink":
            with pytest.raises(m.NativeUnproven, match="ROLE_SYMLINK"):
                sample()
            return
        assert sample() == 0
        state["size"] = 512 + (33554432 if case == "highwater_limit" else 1024)
        state["many"] = case == "entry_limit"
        if case in ("grow", "shared_alias"):
            assert sample() == 1024
            state["size"] = 512
            assert sample() == 1024
        else:
            with pytest.raises(m.NativeUnproven):
                sample()
    finally:
        assert not held


@pytest.mark.parametrize(
    "mode", ["normal", "signal_exit", "resources", "descendant", "stalled", "message", "late"]
)
def test_parent_observes_kernel_and_owned_watchdog(monkeypatch, mode):
    m = native_module()
    from types import SimpleNamespace as NS

    now = [2.0]
    waited = []
    events = [b"R", b"S", b"C", b""]

    def waitpid(child, options):
        assert child == 789 and options == 1
        waited.append(child)
        if mode == "stalled" or events:
            return (0, 0)
        return (child, 9 if mode == "signal_exit" else 0)

    def read(fd, size):
        assert fd == 33 and size == 1
        x = events.pop(0)
        return b"X" if mode == "message" else x

    def ready(r, w, x, timeout):
        now[0] += 8 if mode == "stalled" else 0.1
        if mode == "late":
            now[0] = 482
        return (r if mode != "stalled" else [], [], [])

    def kernel(name):
        values = {
            "cgroup.events": b"populated 0\nfrozen 0\n",
            "pids.events": b"max 0\n",
            "memory.events": b"low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n",
        }
        if mode == "descendant":
            values["cgroup.events"] = b"populated 1\nfrozen 0\n"
        if mode == "resources":
            values["memory.events"] = values["memory.events"].replace(b"oom_kill 0", b"oom_kill 1")
        return values[name]

    handles = {"cgroup.events": 21, "pids.events": 22, "memory.events": 23}
    monkeypatch.setattr(
        m,
        "os",
        NS(
            waitpid=waitpid,
            WNOHANG=1,
            read=read,
            pread=lambda fd, size, offset: kernel({v: k for k, v in handles.items()}[fd]),
            WIFEXITED=lambda s: s == 0,
            WEXITSTATUS=lambda s: 0,
        ),
    )
    monkeypatch.setattr(m, "select", NS(select=ready))
    monkeypatch.setattr(m.time, "monotonic", lambda: now[0])
    if mode == "normal":
        value = m._await_owned_exit(789, 33, handles, 1.0)
        assert value["helper_exit_code"] == value["active_owned_processes"] == 0
        assert value["watchdog_eof"] and not value["force_killed"]
    else:
        with pytest.raises(m.NativeUnproven):
            m._await_owned_exit(789, 33, handles, 1.0)


@pytest.mark.parametrize(
    "case", ["valid", "sdk_default_changed", "client_version", "encrypt", "alias", "second_ctor"]
)
def test_original_client_config_projection(case):
    m = native_module()
    call = (
        "moomoo.OpenQuoteContext(host='127.0.0.1', port=11112, "
        "is_encrypt=False, is_async_connect=True)"
    )
    source = (
        b"class OpenQuoteContext(OpenContextBase):\n def __init__(self, "
        b"host='127.0.0.1', port=11111, is_encrypt=None, is_async_connect=False, "
        b"security_firm=SecurityFirm.NONE, ai_type=0): pass\n"
    )
    if case == "sdk_default_changed":
        source = source.replace(b"SecurityFirm.NONE", b"SecurityFirm.FUTUSG")
    if case == "encrypt":
        call = call.replace("is_encrypt=False", "is_encrypt=True")
    if case == "alias":
        call = call.replace("host='127.0.0.1'", "host=get_host()")
    if case == "second_ctor":
        call += "\n" + call
    expected = {"host": "127.0.0.1", "port": 11112, "is_encrypt": False, "security_firm": "NONE"}
    if case == "valid":
        assert m._quote_settings(call.encode(), source, "10.10.7008") == expected
    else:
        with pytest.raises(m.NativeUnproven):
            m._quote_settings(
                call.encode(), source, "10.10.7009" if case == "client_version" else "10.10.7008"
            )


@pytest.mark.parametrize(
    "case",
    [
        "paired",
        "wrong_tty",
        "wrong_session",
        "wrong_index",
        "cohort",
        "extra_master",
        "extra_slave",
        "cross_mount",
        "wrong_fs",
    ],
)
def test_kernel_pty_pair(case):
    m = native_module()

    def make_stat(pid, session, tty):
        return f"{pid} (has ) char) S 1 1 {session} {tty} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 100".encode()

    rows = {
        705646: make_stat(705646, 705646, 0),
        705651: make_stat(705651, 705651, 34823),
        705711: make_stat(705711, 705651, 34823),
    }
    if case == "wrong_session":
        rows[705711] = make_stat(705711, 22, 34823)
    if case == "wrong_tty":
        rows[705711] = make_stat(705711, 705651, 34822)
    ptys = [
        (705646, 80, (0, 23), (5, 2), b"tty-index:\t7\n"),
        (705651, 80, (0, 23), (136, 7), b""),
        (705711, 80, (0, 23), (136, 7), b""),
    ]
    if case == "wrong_index":
        ptys[0] = (*ptys[0][:4], b"tty-index:\t5\n")
    if case == "extra_master":
        ptys.append(ptys[0])
    if case == "extra_slave":
        ptys.append((705646, 80, (0, 23), (136, 7), b""))
    if case == "cross_mount":
        ptys[2] = (705711, 81, (0, 23), (136, 7), b"")
    if case == "cohort":
        rows[777] = make_stat(777, 705651, 34823)
    mounts = {
        80: SimpleNamespace(
            filesystem="ext4" if case == "wrong_fs" else "devpts",
            device=(0, 23),
            target="/dev/pts",
            root="/",
        )
    }
    if case == "paired":
        assert m._paired_pty(ptys, rows, mounts) == (80, (0, 23), 7)
    else:
        with pytest.raises(m.NativeUnproven):
            m._paired_pty(ptys, rows, mounts)


@pytest.mark.parametrize(
    "case", ["clean", "untrusted_dir", "links", "symlink", "write", "race", "oversize", "short"]
)
def test_fixed_control_origin(monkeypatch, case):
    m = native_module()
    held = set()

    def op(path, flags, *, dir_fd=None):
        fd = {
            ("/", None): 1,
            ("etc", 1): 2,
            ("quantmesh", 2): 3,
            ("opend", 3): 4,
            ("OpenD.xml", 4): 5,
        }[path, dir_fd]
        assert flags & 8 and flags & 2
        held.add(fd)
        return fd

    def st(fd):
        mode = stat.S_IFDIR | (0o777 if case == "untrusted_dir" and fd == 2 else 0o755)
        if fd == 5:
            mode = (stat.S_IFLNK if case == "symlink" else stat.S_IFREG) | (
                0o666 if case == "write" else 0o444
            )
        return SimpleNamespace(
            st_uid=0,
            st_gid=0,
            st_mode=mode,
            st_dev=1,
            st_ino=fd,
            st_size=5 if case == "oversize" else 4,
            st_mtime_ns=2,
            st_ctime_ns=2,
            st_nlink=2 if case == "links" and fd == 5 else 1,
        )

    def named(path, *, dir_fd, follow_symlinks):
        assert not follow_symlinks
        info = st({"etc": 2, "quantmesh": 3, "opend": 4, "OpenD.xml": 5}[path])
        if case == "race":
            info.st_ino += 1
        return info

    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            O_NOFOLLOW=8,
            O_CLOEXEC=2,
            O_DIRECTORY=4,
            O_RDONLY=0,
            O_NONBLOCK=16,
            open=op,
            fstat=st,
            stat=named,
            close=held.remove,
            pread=lambda fd, count, offset: b"ABC" if case == "short" else b"ABCD",
        ),
    )
    if case == "clean":
        assert m._protected_bytes("/etc/quantmesh/opend/OpenD.xml", 4) == b"ABCD"
    else:
        with pytest.raises(m.NativeUnproven):
            m._protected_bytes("/etc/quantmesh/opend/OpenD.xml", 4)
    assert not held


@pytest.mark.parametrize(
    "case", ["valid", "encrypt_xml", "writable_sdk", "sdk_origin", "wrong_client", "wrong_firm"]
)
def test_trusted_settings_joins_original_receipt_and_current_public_bytes(monkeypatch, case):
    m = native_module()
    import hashlib
    import json

    def digest(body):
        return hashlib.sha256(body).hexdigest()

    sdk_root = (
        "/opt/quantmesh/releases/69515b79d2bc67303bfef9dee660dbca9bef41e3/"
        ".venv/lib/python3.12/site-packages"
    )
    nonce = "a" * 32
    hist = "/opt/quantmesh/l90-20261023-183245/"
    public = "/opt/quantmesh/opend-console-evidence/" + nonce
    client = (
        b"moomoo.OpenQuoteContext(host='127.0.0.1',port=11112,"
        b"is_encrypt=False,is_async_connect=True)"
    )
    sdk = b"class OpenQuoteContext:\n def __init__(self, security_firm=SecurityFirm.NONE): pass"
    validator = (
        b"def validate_profile(p):\n assert p == {}\n"
        b"def reviewed_configuration(): return b'<public/>'"
    )
    raw = json.dumps(
        {
            "unit": f"qm-opend-sdk-{nonce}.service",
            "sdk_projection": {"sdk_version": "10.10.7008"},
            "result_directory": public,
            "helper_sha256": digest(client),
        }
    ).encode()
    seal = json.dumps({"raw_result_sha256": digest(raw), "child_terminal": True}).encode()
    paths = {
        hist + "cb2-vb2-sdk-exact-stdout.json": raw,
        hist + "cb2-vb2-sdk-provenance.json": seal,
        public + "/sdk-probe.py": client,
        "/opt/quantmesh/opend/validate_profile.py": validator,
        "/etc/quantmesh/opend/OpenD.xml": b"<encrypted/>"
        if case == "encrypt_xml"
        else b"<public/>",
        "/etc/quantmesh/opend/gateway-profile.json": b"{}",
        sdk_root + "/moomoo/quote/open_quote_context.py": sdk,
    }
    for name, body in (
        ("_HISTORICAL_RAW", raw),
        ("_HISTORICAL_BINDING", seal),
        ("_CLIENT_SHA", client),
        ("_SDK_SHA", sdk),
        ("_VALIDATOR_SHA", validator),
    ):
        monkeypatch.setattr(m, name, digest(body))
    if case == "wrong_client":
        paths[public + "/sdk-probe.py"] = b"changed"
    monkeypatch.setattr(m, "_protected_bytes", lambda path, maximum: paths[path])
    monkeypatch.setattr(m, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            getuid=lambda: 0,
            geteuid=lambda: 0,
            ST_RDONLY=1,
            statvfs=lambda path: SimpleNamespace(f_flag=0 if case == "writable_sdk" else 1),
        ),
    )
    endpoint = {"host": "127.0.0.1", "port": 11112, "is_encrypt": False, "security_firm": "NONE"}
    plan = {
        "sdk_root": "/unreviewed" if case == "sdk_origin" else sdk_root,
        "endpoint": dict(endpoint, security_firm="FUTUSG") if case == "wrong_firm" else endpoint,
    }
    if case == "valid":
        ep, binding = m._trusted_configuration(plan)
        assert ep == endpoint and len(binding) == 64
    else:
        with pytest.raises(m.NativeUnproven):
            m._trusted_configuration(plan)


@pytest.mark.parametrize("case", ["good", "drift", "writable", "alias", "missing"])
def test_released_native_source_is_verified_before_compilation(tmp_path, monkeypatch, case):
    import hashlib

    native_module()
    from test_ivv_dev_diagnostic import dev_module

    d = dev_module()
    # The emitted fixture source never signs anything. A stale pycache must not participate.
    origin = tmp_path / "ivv_dev_diagnostic.py"
    monkeypatch.setattr(d, "__file__", str(origin))
    name = "ivv_native_producer.py"
    source = tmp_path / name
    source.write_bytes(b"FROZEN = 123\n")
    raw = source.read_bytes()

    def fileinfo(path):
        return SimpleNamespace(f_flag=0 if case == "writable" else 1)

    monkeypatch.setattr(d.os, "statvfs", fileinfo, raising=False)
    monkeypatch.setattr(d.os, "ST_RDONLY", 1, raising=False)
    if case == "alias":
        name = "../ivv_native_producer.py"
    pin = hashlib.sha256(raw).hexdigest()
    if case == "drift":
        source.write_bytes(b"FROZEN = 456\n")
    if case == "missing":
        pin = None
    if case == "good":
        assert d._released_module(name, pin).FROZEN == 123
    else:
        with pytest.raises((RuntimeError, ValueError)):
            d._released_module(name, pin)


def test_unprepared_or_forked_actor_cannot_supply_provider_evidence():
    from test_ivv_dev_diagnostic import dev_module

    d = dev_module()
    with pytest.raises(RuntimeError, match="DEV_NATIVE_SESSION_ABSENT"):
        d._read_native_provider({"scope_id": "fictional"}, {"provider_actor": {"pid": 12}})


def test_constructed_cohort_pair_cannot_seal_external_holders():
    m = native_module()
    with pytest.raises(m.NativeUnproven, match="^PTY_EXTERNAL_HOLDER_UNPROVEN$"):
        m._require_holder_closure((80, (0, 23), 7))


@pytest.mark.parametrize(
    "case", ["coherent", "fifo", "outside_reg", "shared_map", "extra_socket", "limits"]
)
def test_real_six_role_and_retained_kernel_acquisition_reaches_precise_boundary(monkeypatch, case):
    import contextlib
    import os

    from test_ivv_native_producer import MetadataOS, producer

    m, p = native_module(), producer()
    io = MetadataOS(os)
    io.O_DIRECTORY = 0x10000
    io.O_NOFOLLOW = 0x20000
    io.O_CLOEXEC = 0x80000

    def add(path, mode, **kw):
        io.add(path, mode, **kw)
        io.items[path].st_blocks = 0

    def directory(path, **kw):
        add(path, stat.S_IFDIR | 0o700, **kw)

    def raw(path, body):
        add(path, stat.S_IFREG | 0o444)
        io.data[path] = body

    for name in (
        "/root",
        "/root/var",
        "/root/var/lib",
        "/root/var/tmp",
        "/root/tmp",
        "/root/dev",
        "/root/dev/shm",
        "/root/run",
        "/root/var/lib/quantmesh-opend",
        "/root/var/lib/quantmesh-opend-stage",
        "/proc",
        "/sys/fs",
        "/sys/fs/cgroup",
        "/sys/fs/cgroup/system.slice",
    ):
        directory(name)
    directory("/root" + RUNTIME, uid=997, gid=987)
    add("/root" + RUNTIME + "/socket", stat.S_IFSOCK | 0o700, uid=997, gid=987, ino=901)
    add("/root/var/lib/quantmesh-opend/opaque", stat.S_IFREG | 0o600, uid=997, ino=400, size=77)
    cg = "/sys/fs/cgroup/system.slice/" + p.UNIT
    directory(cg)
    for name, value in {
        "memory.max": "1" if case == "limits" else "1073741824",
        "pids.max": "128",
        "cpu.max": "50000 100000",
        "memory.swap.max": "0",
    }.items():
        raw(cg + "/" + name, value.encode() + b"\n")
    for pid in (705646, 705651, 705711):
        base = f"/proc/{pid}"
        for name in ("", "/fd", "/fdinfo", "/net"):
            directory(base + name)
        sess, tty = (705646, 0) if pid == 705646 else (705651, 34823)
        raw(
            base + "/stat", f"{pid} (a) S 1 1 {sess} {tty} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 100".encode()
        )
        raw(
            base + "/maps",
            b"1-2 rw-s 0000 103:01 777\n" if case == "shared_map" else b"1-2 rw-p 0000 00:00 0\n",
        )

    def fd(pid, n, mode, ino, dev, mount, rdev=0, tail=""):
        base = f"/proc/{pid}"
        add(f"{base}/fd/{n}", mode, uid=997, gid=987, dev=dev, ino=ino, rdev=rdev)
        raw(f"{base}/fdinfo/{n}", f"ino: {ino}\nmnt_id: {mount}\nflags: 02\n{tail}".encode())

    fd(705646, 9, stat.S_IFSOCK, 5965500, 9, 90)
    fd(705711, 6, stat.S_IFSOCK, 111000, 9, 90)
    fd(705646, 7, stat.S_IFCHR, 2, 23, 80, 1282, "tty-index: 7\n")
    fd(705651, 1, stat.S_IFCHR, 10, 23, 80, 34823)
    fd(705711, 1, stat.S_IFCHR, 10, 23, 80, 34823)
    fd(705711, 4, stat.S_IFREG, 400 if case != "outside_reg" else 499, 66305, 1)
    io.items["/proc/705711/fd/4"].st_size = 77
    if case == "fifo":
        fd(705711, 8, stat.S_IFIFO, 71, 9, 92)
    if case == "extra_socket":
        for n in range(8, 12):
            fd(705711, n, stat.S_IFSOCK, 72 + n, 9, 92)
    raw("/proc/705711/net/tcp", TCP)
    raw("/proc/705711/net/unix", UNIX)
    raw(
        "/proc/705711/mountinfo",
        b"1 99 259:1 / / rw - ext4 /dev/root rw\n80 1 0:23 / /dev/pts rw - devpts devpts rw\n",
    )
    io.readlink = lambda path: (
        f"socket:[{io.fstat(int(path.removeprefix('/proc/self/fd/'))).st_ino}]"
    )
    io.scandir = lambda handle: contextlib.nullcontext(
        iter(SimpleNamespace(name=n) for n in io.listdir(handle))
    )
    io.statvfs = lambda path: SimpleNamespace(f_bavail=100000000000, f_frsize=1)
    io.makedev = lambda major, minor: (major << 8) | minor
    monkeypatch.setattr(m, "os", io)
    monkeypatch.setattr(p, "os", io)
    reader = p.PosixReader()
    reader.root = reader.directory("/root")
    reader.processes = {pid: (reader.directory(f"/proc/{pid}"),) for pid in p.PROCESSES}
    reader.manager_fields = {"ControlGroup": "/system.slice/" + p.UNIT}
    reasons = {
        "coherent": "PTY_EXTERNAL_HOLDER_UNPROVEN",
        "fifo": "UNSUPPORTED_CHANNEL",
        "outside_reg": "OUTSIDE_RETAINED_FILE",
        "shared_map": "UNPROVEN_SHARED_MAPPING",
        "extra_socket": "UNPROVEN_SOCKET",
        "limits": "PROVIDER_RESOURCES",
    }
    try:
        with pytest.raises(m.NativeUnproven, match="^" + reasons[case] + "$"):
            m._fresh_provider(
                reader,
                p,
                {"started_monotonic": m.time.monotonic(), "receipt_root": "/owned/result"},
                {"G": 12345, "P": 2000},
                m.RoleGrowth(),
            )
    finally:
        reader.close()
    assert not io.handles


def test_unclassified_pty_initial_preflight_preserves_primary_and_cleanup():
    from test_ivv_native_producer import producer

    m, p = native_module(), producer()

    class Reader:
        def identity(self):
            raise p.FeasibilityRejected("PROVIDER_IDENTITY")

        def finish(self):
            return ["PROVIDER_RACE"]

        def close(self):
            raise OSError("PRIVATE_SENTINEL")

    p.PosixReader = Reader
    with pytest.raises(
        m.NativeUnproven, match="^PROVIDER_IDENTITY\\+PROVIDER_RACE\\+NATIVE_CLOSE_UNPROVEN$"
    ):
        m.prepare_provider({}, p, {})


def test_kernel_close_requires_preheld_event_descriptions(monkeypatch):
    m = native_module()
    held = {"cgroup.events": 21, "pids.events": 22, "memory.events": 23}
    reads = {
        21: b"populated 0\nfrozen 0\n",
        22: b"max 0\n",
        23: b"low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n",
    }
    monkeypatch.setattr(m, "os", SimpleNamespace(pread=lambda f, n, o: reads[f]))
    assert m._observe_empty(held) is None
    del reads[21]
    with pytest.raises(m.NativeUnproven):
        m._observe_empty(held)


def test_snapshot_never_crosses_owner_lifetime_and_expiry(monkeypatch):
    m = native_module()
    sess = object.__new__(m.NativeSession)
    sess.owner = 911
    sess.last = {"sampled_monotonic": 2.0, "sample": {"incremental_bytes": 1}}
    sess.failure = None
    sess.closed = False
    import threading

    sess.lock = threading.Lock()
    monkeypatch.setattr(m, "os", SimpleNamespace(getpid=lambda: 911))
    monkeypatch.setattr(m.time, "monotonic", lambda: 3.0)
    snapshot = sess.snapshot()
    snapshot["sample"]["incremental_bytes"] = 100
    assert sess.snapshot()["sample"]["incremental_bytes"] == 1
    monkeypatch.setattr(m.time, "monotonic", lambda: 8.0)
    with pytest.raises(m.NativeUnproven, match="STALE"):
        sess.snapshot()
    monkeypatch.setattr(m, "os", SimpleNamespace(getpid=lambda: 912))
    with pytest.raises(m.NativeUnproven, match="OWNER"):
        sess.snapshot()


@pytest.mark.parametrize("case", ["bound", "populated", "drift", "foreign_parent"])
def test_controller_creates_only_fixed_cgroup_and_preholds_kernel_files(monkeypatch, case):
    m = native_module()
    opened = {}
    closed = []
    values = {
        "cgroup.events": b"populated 0\nfrozen 0\n",
        "pids.events": b"max 0\n",
        "memory.events": b"low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n",
    }
    if case == "populated":
        values["cgroup.events"] = b"populated 1\nfrozen 0\n"

    def op(name, flags, *, dir_fd=None):
        if dir_fd is None:
            assert name == "/sys/fs/cgroup/system.slice"
        elif dir_fd == 100:
            assert name == "quantmesh-ivv-dev-e285.scope"
        else:
            assert dir_fd == 101 and "/" not in name
        n = 100 + len(opened)
        opened[n] = name
        return n

    def write(fd, data):
        values[opened[fd]] = data
        return len(data)

    def pread(fd, n, o):
        key = opened[fd]
        if case == "drift" and key == "memory.max":
            return b"max\n"
        return values[key]

    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            O_RDONLY=0,
            O_DIRECTORY=4,
            O_CLOEXEC=2,
            O_NOFOLLOW=1,
            O_RDWR=8,
            O_WRONLY=16,
            open=op,
            close=closed.append,
            write=write,
            pread=pread,
            fstat=lambda f: SimpleNamespace(
                st_uid=1 if case == "foreign_parent" and f == 100 else 0,
                st_mode=stat.S_IFDIR | 0o755,
            ),
            mkdir=lambda name, mode, dir_fd: None,
            rmdir=lambda name, dir_fd: None,
        ),
    )
    if case == "bound":
        with m._owned_group() as held:
            assert values["pids.max"] == b"32" and values["memory.max"] == b"536870912"
            assert set(held) >= {
                "pids.events",
                "memory.events",
                "cgroup.events",
                "cgroup.procs",
                "cgroup.kill",
            }
            assert all(held[n] not in closed for n in held)
    else:
        with pytest.raises(m.NativeUnproven), m._owned_group():
            pass
    assert len(closed) == len(set(closed)) == len(opened)
