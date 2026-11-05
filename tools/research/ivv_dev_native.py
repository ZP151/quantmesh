"""Linux kernel acquisition for the initial fixed DEV listener graph."""

import ast
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import PurePosixPath


class NativeUnproven(ValueError):
    """Fixed non-sensitive reason. Native proof was not established."""


_RUNTIME = "/run/quantmesh-opend-console-eabdda557bc641fdbda60ecd993fb2a0"
_COHORT = {705646, 705651, 705711}


def _need(value, reason):
    if not value:
        raise NativeUnproven(reason)


class _CleanupFailure(NativeUnproven):
    def __init__(self, code, primary):
        super().__init__(code)
        self.primary = primary


@contextmanager
def _held(reader, fd):
    try:
        yield fd
    finally:
        primary = sys.exc_info()[1]
        try:
            reader.release(fd)
        except OSError:
            raise _CleanupFailure("NATIVE_FD_CLOSE", primary) from None


def _stamp(item):
    return item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid, item.st_nlink


def _tmux_filesystem_endpoint(reader):
    with _held(reader, reader.held_path(_RUNTIME, reader.root)) as parent:
        directory = os.fstat(parent)
        _need(
            stat.S_ISDIR(directory.st_mode)
            and (directory.st_uid, directory.st_gid, stat.S_IMODE(directory.st_mode))
            == (997, 987, 0o700),
            "UNPROVEN_UNIX_PARENT",
        )
        with _held(reader, reader.held_path(_RUNTIME + "/socket", reader.root)) as fd:
            item = os.fstat(fd)
            _need(
                stat.S_ISSOCK(item.st_mode)
                and (item.st_uid, item.st_gid, item.st_nlink) == (997, 987, 1)
                and item.st_mode & 0o077 == 0
                and item.st_dev == directory.st_dev
                and item.st_ino > 0,
                "UNPROVEN_UNIX_ENDPOINT",
            )
            return _stamp(directory), _stamp(item)


def _socket_inventory(reader):
    result = set()
    _need(set(reader.processes) == _COHORT, "UNPROVEN_COHORT")
    for pid, (proc, *_) in reader.processes.items():
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        with _held(reader, reader.keep(os.open("fd", flags, dir_fd=proc))) as directory:
            names = os.listdir(directory)
            _need(len(names) <= 256 and all(n.isascii() and n.isdigit() for n in names), "FD_BOUND")
            for name in names:
                reader.tick()
                # O_PATH holds the kernel object. Only a held, typed socket may be readlinked.
                flags = os.O_PATH | os.O_CLOEXEC
                with _held(reader, reader.keep(os.open(name, flags, dir_fd=directory))) as handle:
                    item = os.fstat(handle)
                    if stat.S_ISSOCK(item.st_mode):
                        fields = reader.read(proc, "fdinfo/" + name, 4096).splitlines()
                        inode = [
                            x.split(b":", 1)[1].strip() for x in fields if x.startswith(b"ino:")
                        ]
                        _need(
                            inode == [str(item.st_ino).encode()]
                            and item.st_ino > 0
                            and os.readlink("/proc/self/fd/" + str(handle))
                            == f"socket:[{item.st_ino}]",
                            "UNPROVEN_SOCKET_INODE",
                        )
                        result.add((pid, name, item.st_ino))
                    _need(_stamp(os.stat(name, dir_fd=directory)) == _stamp(item), "FD_RACE")
            _need(set(os.listdir(directory)) == set(names), "FD_RACE")
    return result


def _classify_initial(reader):
    sockets = _socket_inventory(reader)
    proc = reader.processes[705711][0]
    rows = {}
    for name, column in (("tcp", 9), ("unix", 6)):
        raw = reader.read(proc, "net/" + name, 262144).splitlines()
        _need(0 < len(raw) <= 4096, "SOCKET_TABLE_BOUND")
        for line in raw[1:]:
            fields = line.split(None, 7) if name == "unix" else line.split()
            _need(len(fields) > column and fields[column].isdigit(), "SOCKET_TABLE_UNKNOWN")
            ino = int(fields[column])
            if not any(inode == ino for _, _, inode in sockets):
                continue
            _need(ino not in rows, "UNPROVEN_SOCKET")
            if name == "tcp":
                _need(
                    fields[1:4] == [b"0100007F:2B68", b"00000000:0000", b"0A"]
                    and fields[7] == b"997",
                    "UNPROVEN_TCP",
                )
                rows[ino] = (705711, "VENDOR_LISTENER")
            else:
                _need(
                    len(fields) == 8
                    and fields[2:6] == [b"00000000", b"00010000", b"0001", b"01"]
                    and fields[7] == (_RUNTIME + "/socket").encode(),
                    "UNPROVEN_UNIX",
                )
                rows[ino] = (705646, "TMUX_LISTENER")
    result = {}
    for pid, _, inode in sockets:
        owner, role = rows.get(inode, (None, None))
        _need(pid == owner and role not in result, "UNPROVEN_SOCKET")
        result[role] = inode
    _need(set(result) == {"TMUX_LISTENER", "VENDOR_LISTENER"}, "UNPROVEN_LISTENERS")
    return sockets, result, _tmux_filesystem_endpoint(reader)


def _verified_socket_inventory(reader):
    before = _classify_initial(reader)
    _need(_classify_initial(reader) == before, "SOCKET_TABLE_RACE")
    return before[0], before[1]


def initial_socket_roles(reader):
    """Only the two pre-connect listeners, using held producer-verified proc handles."""
    _, listeners = _verified_socket_inventory(reader)
    return listeners


_ROLE_PATHS = (
    "/var/lib/quantmesh-opend",
    "/var/lib/quantmesh-opend-stage",
    _RUNTIME,
    "/tmp",
    "/var/tmp",
    "/dev/shm",
)


class RoleGrowth:
    """Positive per-inode high water in the fixed roles; samples cannot bound the provider tail."""

    def __init__(self):
        self.baseline = None
        self.peaks = {}
        self.samples = 0
        self.current = frozenset()

    def sample(self, reader):
        deadline = time.monotonic() + 2
        _need(self.samples < 97, "SAMPLE_COUNT")
        self.samples += 1
        entries = 0
        observed = {}

        def tick():
            _need(time.monotonic() < deadline, "SAMPLE_TIMEOUT")

        def measure(item):
            nonlocal entries
            tick()
            entries += 1
            _need(entries <= 16384, "SAMPLE_ENTRY_LIMIT")
            key = (item.st_dev, item.st_ino)
            size = max(item.st_size, item.st_blocks * 512)
            _need(key not in observed or observed[key] == size, "ROLE_ENTRY_RACE")
            observed[key] = size

        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

        def mount_id(fd):
            raw = reader.read(None, f"/proc/self/fdinfo/{fd}", 4096)
            rows = [line[7:].strip() for line in raw.splitlines() if line.startswith(b"mnt_id:")]
            _need(len(rows) == 1 and rows[0].isdigit() and int(rows[0]) > 0, "ROLE_MOUNT_UNKNOWN")
            return int(rows[0])

        def directory(fd, depth, role_mount):
            tick()
            _need(depth <= 64, "SAMPLE_DEPTH")
            before = os.fstat(fd)
            measure(before)
            with os.scandir(fd) as stream:
                for entry in stream:
                    tick()
                    named = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                    _need(not stat.S_ISLNK(named.st_mode), "ROLE_SYMLINK")
                    if stat.S_ISDIR(named.st_mode):
                        with _held(
                            reader, reader.keep(os.open(entry.name, flags, dir_fd=fd))
                        ) as child:
                            _need(_stamp(os.fstat(child)) == _stamp(named), "ROLE_ENTRY_RACE")
                            _need(mount_id(child) == role_mount, "ROLE_MOUNT_CROSSING")
                            directory(child, depth + 1, role_mount)
                    else:
                        _need(
                            stat.S_ISREG(named.st_mode) or stat.S_ISSOCK(named.st_mode),
                            "UNPROVEN_ROLE_ENTRY",
                        )
                        with _held(
                            reader,
                            reader.keep(
                                os.open(
                                    entry.name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd
                                )
                            ),
                        ) as leaf:
                            _need(mount_id(leaf) == role_mount, "ROLE_MOUNT_CROSSING")
                            item = os.fstat(leaf)
                            _need(_stamp(item) == _stamp(named), "ROLE_ENTRY_RACE")
                            measure(item)
                    after = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                    _need(
                        _stamp(after) == _stamp(named)
                        and (after.st_ctime_ns, after.st_size, after.st_blocks)
                        == (named.st_ctime_ns, named.st_size, named.st_blocks),
                        "ROLE_ENTRY_RACE",
                    )
            end = os.fstat(fd)
            _need(
                _stamp(end) == _stamp(before)
                and (before.st_mtime_ns, before.st_ctime_ns) == (end.st_mtime_ns, end.st_ctime_ns),
                "ROLE_TREE_RACE",
            )

        for path in _ROLE_PATHS:
            with _held(reader, reader.held_path(path, reader.root)) as ref:
                with _held(reader, reader.keep(os.open(".", flags, dir_fd=ref))) as fd:
                    role_mount = mount_id(ref)
                    _need(mount_id(fd) == role_mount, "ROLE_MOUNT_CROSSING")
                    directory(fd, 0, role_mount)
            tick()
        self.current = observed
        if self.baseline is None:
            self.baseline = observed
        for key, size in observed.items():
            self.peaks[key] = max(self.peaks.get(key, 0), size - self.baseline.get(key, 0))
        _need(len(self.peaks) <= 16384, "SAMPLE_ENTRY_LIMIT")
        incremental = sum(self.peaks.values())
        _need(incremental < 33554432, "PROVIDER_GROWTH")
        tick()
        return incremental


def _quote_settings(client_code, sdk_code, version):
    """Derive client settings from previously authenticated public code, without SDK import."""
    _need(version == "10.10.7008", "CONFIG_QUOTE_VERSION")
    try:
        calls = [
            node
            for node in ast.walk(ast.parse(client_code))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "OpenQuoteContext"
        ]
        _need(
            len(calls) == 1
            and not calls[0].args
            and isinstance(calls[0].func.value, ast.Name)
            and calls[0].func.value.id == "moomoo",
            "CONFIG_ORIGINAL_CLIENT",
        )
        values = {keyword.arg: ast.literal_eval(keyword.value) for keyword in calls[0].keywords}
        _need(
            values
            == {"host": "127.0.0.1", "port": 11112, "is_encrypt": False, "is_async_connect": True}
            and values["is_encrypt"] is False,
            "CONFIG_ORIGINAL_CLIENT",
        )
        classes = [
            node
            for node in ast.parse(sdk_code).body
            if isinstance(node, ast.ClassDef) and node.name == "OpenQuoteContext"
        ]
        _need(len(classes) == 1, "CONFIG_SDK_CONSTRUCTOR")
        constructors = [
            node
            for node in classes[0].body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        ]
        _need(len(constructors) == 1, "CONFIG_SDK_CONSTRUCTOR")
        params = constructors[0].args
        defaults = dict(
            zip([a.arg for a in params.args][-len(params.defaults) :], params.defaults, strict=True)
        )
        firm = defaults["security_firm"]
        _need(
            isinstance(firm, ast.Attribute)
            and isinstance(firm.value, ast.Name)
            and firm.value.id == "SecurityFirm"
            and firm.attr == "NONE",
            "CONFIG_FIRM_UNKNOWN",
        )
        return {
            "host": values["host"],
            "port": values["port"],
            "is_encrypt": False,
            "security_firm": firm.attr,
        }
    except (KeyError, SyntaxError, TypeError, ValueError) as exc:
        if isinstance(exc, NativeUnproven):
            raise
        raise NativeUnproven("CONFIG_METADATA") from None


def _paired_pty(endpoints, process_stat, mounts):
    """Prove the *cohort* pair. External-holder closure is a separate admission gate."""
    _need(set(process_stat) == _COHORT, "PTY_COHORT")
    sessions = {}
    for pid, raw in process_stat.items():
        left, delimiter, tail = raw.rpartition(b") ")
        values = tail.split()
        _need(
            delimiter
            and left.startswith(str(pid).encode() + b" (")
            and len(values) >= 20
            and all(value.isdigit() for value in values[3:5]),
            "PTY_STAT",
        )
        sessions[pid] = (int(values[3]), int(values[4]))
    master = None
    slaves = set()
    for pid, mount_id, dev, rdev, fdinfo in endpoints:
        mount = mounts.get(mount_id)
        _need(
            mount
            and mount.filesystem == "devpts"
            and mount.target == "/dev/pts"
            and mount.root == "/"
            and mount.device == dev,
            "PTY_FILESYSTEM",
        )
        if rdev == (5, 2):
            indices = [
                line.split(b":", 1)[1].strip()
                for line in fdinfo.splitlines()
                if line.startswith(b"tty-index:")
            ]
            _need(
                pid == 705646
                and master is None
                and len(indices) == 1
                and indices[0].isdigit()
                and int(indices[0]) < 4096
                and sessions[pid] == (705646, 0),
                "PTY_MASTER",
            )
            master = (mount_id, dev, int(indices[0]))
        else:
            major, minor = rdev
            _need(
                136 <= major <= 143
                and 0 <= minor < 256
                and pid in (705651, 705711)
                and sessions[pid] == (705651, major * 256 + minor),
                "PTY_SLAVE",
            )
            slaves.add((mount_id, dev, (major - 136) * 256 + minor))
    _need(master is not None and slaves == {master}, "PTY_PAIR")
    return master


def _protected_bytes(path, maximum, *, mode=None):
    """Only used for the fixed controls and reviewed public code. Never include data in errors."""
    parts = PurePosixPath(path).parts
    _need(
        len(parts) > 1
        and parts[0] == "/"
        and str(PurePosixPath(path)) == path
        and ".." not in parts,
        "CONFIG_CONTROL_PATH",
    )
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    held = []

    def acquire(part, flags, parent=None):
        fd = os.open(part, flags, dir_fd=parent)
        held.append((part, fd, parent))
        return fd

    try:
        parent = acquire("/", flags | os.O_DIRECTORY)
        for part in parts[1:-1]:
            info = os.fstat(parent)
            _need(
                stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "CONFIG_CONTROL_PARENT",
            )
            parent = acquire(part, flags | os.O_DIRECTORY, parent)
        info = os.fstat(parent)
        _need(
            stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            "CONFIG_CONTROL_PARENT",
        )
        fd = acquire(parts[-1], flags | os.O_NONBLOCK, parent)
        info = os.fstat(fd)
        _need(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and info.st_nlink == 1
            and not info.st_mode & 0o6022
            and (mode is None or stat.S_IMODE(info.st_mode) == mode)
            and 0 < info.st_size <= maximum,
            "CONFIG_CONTROL_ORIGIN",
        )
        raw = os.pread(fd, info.st_size + 1, 0)
        after = os.fstat(fd)
        _need(
            len(raw) == info.st_size
            and (info.st_mtime_ns, info.st_ctime_ns, info.st_size)
            == (after.st_mtime_ns, after.st_ctime_ns, after.st_size),
            "CONFIG_CONTROL_RACE",
        )
        for name, handle, parent in held[1:]:
            _need(
                _stamp(os.fstat(handle))
                == _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                "CONFIG_CONTROL_RACE",
            )
        return raw
    finally:
        primary = sys.exc_info()[1]
        failed = False
        for _, handle, _ in reversed(held):
            try:
                os.close(handle)
            except OSError:
                failed = True
        if failed:
            raise _CleanupFailure("CONFIG_CONTROL_CLOSE", primary) from None


_HISTORICAL_ROOT = "/opt/quantmesh/l90-20261023-183245/"
_HISTORICAL_RAW = "d694282872f837a76c3fbaea32d63764a55d1424e99fe3f06cd1a4a663fdd6ab"
_HISTORICAL_BINDING = "d60ac13c669f0f2aef36f2cce7818ef974a390d4496c73caf84abc7e293536db"
_CLIENT_SHA = "72d8c1e9bb5458a05000760b083ab8098da09b2d784708b15088934cce5186f1"
_SDK_SHA = "ef77c2a66941a8ae8079b5d4dc258286e8426561e1f1b33f00f6c1913d3cc558"
_VALIDATOR_SHA = "53fb2821b21dc695a2934dd20d6822f69714e960585e371181d20d0b81441736"


def _trusted_configuration(plan):
    return _project_client(plan, legacy_public_xml=True)


def trusted_quote_configuration(plan):
    return _project_client(plan, legacy_public_xml=False)


def _project_client(plan, *, legacy_public_xml):
    """Project the original client's settings from the reviewed public sources."""
    _need(sys.platform == "linux" and os.getuid() == os.geteuid() == 0, "CONFIG_ROOT")

    def code(path, size, digest, *, readonly=False):
        if readonly:
            _need(os.statvfs(path).f_flag & os.ST_RDONLY, "CONFIG_SDK_WRITABLE")
        body = _protected_bytes(path, size)
        _need(hashlib.sha256(body).hexdigest() == digest, "CONFIG_SOURCE_PIN")
        return body

    source = code("/opt/quantmesh/opend/validate_profile.py", 32768, _VALIDATOR_SHA)
    validator = {"__name__": "_qm_reviewed_profile"}
    exec(compile(source, "<reviewed public profile validator>", "exec"), validator)
    profile = json.loads(_protected_bytes("/etc/quantmesh/opend/gateway-profile.json", 16384))
    # Runtime/argv here are the reviewed noncredential *public profile*, never live proc argv.
    try:
        validator["validate_profile"](profile)
    except (KeyError, TypeError, ValueError):
        raise NativeUnproven("CONFIG_PROFILE_UNKNOWN") from None
    if legacy_public_xml:
        expected = validator["reviewed_configuration"]()
        _need(
            _protected_bytes("/etc/quantmesh/opend/OpenD.xml", len(expected)) == expected,
            "CONFIG_PUBLIC_CONFIGURATION_DRIFT",
        )
    evidence = json.loads(
        code(_HISTORICAL_ROOT + "cb2-vb2-sdk-exact-stdout.json", 16384, _HISTORICAL_RAW)
    )
    seal = json.loads(
        code(_HISTORICAL_ROOT + "cb2-vb2-sdk-provenance.json", 65536, _HISTORICAL_BINDING)
    )
    unit = evidence["unit"]
    _need(
        seal["raw_result_sha256"] == _HISTORICAL_RAW
        and seal["child_terminal"] is True
        and evidence["helper_sha256"] == _CLIENT_SHA
        and re.fullmatch(r"qm-opend-sdk-[0-9a-f]{32}\.service", unit),
        "CONFIG_ORIGINAL_PROVENANCE",
    )
    nonce = unit[len("qm-opend-sdk-") : -len(".service")]
    client_dir = "/opt/quantmesh/opend-console-evidence/" + nonce
    _need(evidence["result_directory"] == client_dir, "CONFIG_ORIGINAL_PROVENANCE")
    client = code(client_dir + "/sdk-probe.py", 8192, _CLIENT_SHA)
    sdk_root = plan["sdk_root"]
    _need(
        sdk_root
        == (
            "/opt/quantmesh/releases/69515b79d2bc67303bfef9dee660dbca9bef41e3/"
            ".venv/lib/python3.12/site-packages"
        ),
        "CONFIG_SDK_ORIGIN",
    )
    sdk = code(sdk_root + "/moomoo/quote/open_quote_context.py", 524288, _SDK_SHA, readonly=True)
    settings = _quote_settings(client, sdk, evidence["sdk_projection"]["sdk_version"])
    _need(settings == plan["endpoint"], "CONFIG_PLAN_MISMATCH")
    # No live config bytes, names or credential-derived digests enter the binding.
    binding = {
        "endpoint": settings,
        "public_validator": _VALIDATOR_SHA,
        "quote_source": _SDK_SHA,
        "original_client": _CLIENT_SHA,
        "original_receipt": _HISTORICAL_BINDING,
    }
    return settings, hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_holder_closure(pair):
    # The approved Linux sources identify this devpts object and the three known holders.
    # They have no object-specific reverse index for descriptors already transferred out.
    _need(pair is not None, "PTY_PAIR")
    raise NativeUnproven("PTY_EXTERNAL_HOLDER_UNPROVEN")


def _retained_channels(reader, producer, current_roles):
    mounts = {
        m.identifier: m
        for m in producer._visible_mounts(producer.parse_mountinfo(reader.mountinfo())).values()
    }
    endpoints = []
    sockets = set()
    process_stats = {}
    for pid, (proc, *_) in reader.processes.items():
        process_stats[pid] = reader.read(proc, "stat", 4096)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        with _held(reader, reader.keep(os.open("fd", flags, dir_fd=proc))) as directory:
            names = os.listdir(directory)
            _need(len(names) <= 256 and all(n.isascii() and n.isdigit() for n in names), "FD_BOUND")
            for name in names:
                reader.tick()
                with _held(
                    reader, reader.keep(os.open(name, os.O_PATH | os.O_CLOEXEC, dir_fd=directory))
                ) as held:
                    obj = os.fstat(held)
                    info = reader.info(obj)
                    raw = reader.read(proc, "fdinfo/" + name, 4096)
                    _, mnt = reader.parse_fdinfo(raw)
                    mount = mounts.get(mnt)
                    kind = info["kind"]
                    if kind == "CHAR":
                        if mount and mount.filesystem == "devpts":
                            endpoints.append((pid, mnt, info["device"], info["rdev"], raw))
                        else:
                            _need(
                                mount
                                and mount.filesystem == "devtmpfs"
                                and mount.target == "/dev"
                                and mount.root == "/"
                                and info["device"] == mount.device
                                and info["rdev"] in {(1, 3), (1, 5), (1, 7), (1, 8), (1, 9)},
                                "UNPROVEN_CHARACTER",
                            )
                    elif kind in ("REG", "DIR"):
                        _need(
                            mount
                            and info["device"] == mount.device
                            and (obj.st_dev, obj.st_ino) in current_roles,
                            "OUTSIDE_RETAINED_FILE",
                        )
                        _need(
                            max(obj.st_size, obj.st_blocks * 512)
                            == current_roles[(obj.st_dev, obj.st_ino)],
                            "ROLE_ENTRY_RACE",
                        )
                    else:
                        _need(kind == "SOCKET", "UNSUPPORTED_CHANNEL")
                        sockets.add((pid, name, obj.st_ino))
                    _need(_stamp(obj) == _stamp(os.stat(name, dir_fd=directory)), "FD_RACE")
            _need(set(os.listdir(directory)) == set(names), "FD_RACE")
        maps = reader.read(proc, "maps", 262144)
        for line, mapping in zip(maps.splitlines(), reader.parse_maps(maps), strict=True):
            if mapping["shared"] and mapping["writable"]:
                key = (os.makedev(*mapping["device"]), mapping["inode"])
                _need(mapping["inode"] > 0 and key in current_roles, "UNPROVEN_SHARED_MAPPING")
                name = "map_files/" + line.split(None, 1)[0].decode("ascii")
                with _held(
                    reader, reader.keep(os.open(name, os.O_PATH | os.O_CLOEXEC, dir_fd=proc))
                ) as fd:
                    item = os.fstat(fd)
                    _need(
                        stat.S_ISREG(item.st_mode)
                        and (item.st_dev, item.st_ino) == key
                        and max(item.st_size, item.st_blocks * 512) == current_roles[key]
                        and _stamp(item) == _stamp(os.stat(name, dir_fd=proc)),
                        "SHARED_MAPPING_RACE",
                    )
    return _paired_pty(endpoints, process_stats, mounts), sockets


def _provider_controls(reader):
    group = reader.manager_fields["ControlGroup"]
    _need(
        re.fullmatch(r"/system\.slice/(?:[A-Za-z0-9_.@\\:-]+/)*[A-Za-z0-9_.@\\:-]+", group)
        and ".." not in group.split("/"),
        "PROVIDER_CGROUP",
    )
    with _held(reader, reader.directory("/sys/fs/cgroup" + group)) as fd:
        if getattr(reader, "binding", None) is not None:
            _need(reader.read(fd, "memory.high", 128).strip() == b"805306368", "PROVIDER_RESOURCES")
        values = {
            k: reader.read(fd, k, 128).decode("ascii").strip()
            for k in ("memory.max", "memory.swap.max", "cpu.max", "pids.max")
        }
    _need(
        values
        == {
            "memory.max": "1073741824",
            "memory.swap.max": "0",
            "cpu.max": "50000 100000",
            "pids.max": "128",
        },
        "PROVIDER_RESOURCES",
    )
    return values


def _operator_sources(producer, binding):
    if type(binding) is producer.ProviderExecution:
        name, verify = "PROVIDER-BINDING.json", producer.validate_provider_binding
    else:
        _need(type(binding) is producer.OperatorLoginOrigin, "PROVIDER_IDENTITY")
        name, verify = "OPERATOR-LOGIN-ORIGIN.json", producer.validate_operator_login_origin
    nonce = binding.nonce
    version = "v1" if nonce == producer.RESTORE_NONCE else "v2"
    directory = (
        "/var/lib/quantmesh-opend-restore-20261105-01"
        if nonce == producer.RESTORE_NONCE
        else "/var/lib/quantmesh-opend-operator-restores/" + nonce
    )
    original = _protected_bytes(directory + "/" + name, 4096, mode=0o444)
    _need(verify(original, binding.receipt_sha) == binding, "PROVIDER_IDENTITY")
    control = _protected_bytes(
        "/etc/quantmesh/opend/operator-restores/" + nonce + ".json",
        8192,
        mode=0o444,
    )
    _need(hashlib.sha256(control).hexdigest() == binding.control_sha, "PROVIDER_IDENTITY")
    permit = json.loads(control)
    _need(
        type(permit) is dict
        and set(permit) == {"schema", "authority_sha256", "claims"}
        and permit["schema"] == "qm.opend.operator-restore." + version
        and permit["authority_sha256"] == producer.RESTORE_AUTHORITY
        and type(permit["claims"]) is dict
        and permit["claims"].get("nonce") == nonce
        and permit["claims"].get("launcher_sha256") == binding.launcher_sha
        and permit["claims"].get("gateway_uid") == 997
        and type(permit["claims"].get("gateway_gid")) is int
        and 0 < permit["claims"]["gateway_gid"] < 2**31,
        "PROVIDER_IDENTITY",
    )
    for path, pin, maximum in (
        ("/opt/quantmesh/opend/stage_console.py", binding.launcher_sha, 262144),
        ("/etc/systemd/system/quantmesh-opend-console@.service", producer.RESTORE_TEMPLATE, 4096),
        ("/etc/quantmesh/opend/gateway-profile.json", producer.RESTORE_PROFILE, 32768),
    ):
        _need(
            hashlib.sha256(_protected_bytes(path, maximum)).hexdigest() == pin, "PROVIDER_IDENTITY"
        )
    return permit["claims"]["gateway_gid"]


def _operator_identity(producer, binding, gid, reader):
    actual = reader.identity()
    producer._check_subject(actual, binding)
    _need(
        all(
            row["gids"] == [gid] * 4 and all(group == gid for group in row["groups"])
            for row in actual["processes"]
        ),
        "PROVIDER_IDENTITY",
    )
    return actual


def verified_provider_snapshot(producer, binding):
    """Read-only kernel witness for the attributed operator. Never start or use an SDK."""
    _need(type(binding) is producer.ProviderExecution, "PROVIDER_IDENTITY")
    return _verified_snapshot(producer, binding)


def verified_operator_login_snapshot(producer, binding):
    """Public process attribution only, before private ordinary login; no endpoint admission."""
    _need(type(binding) is producer.OperatorLoginOrigin, "PROVIDER_IDENTITY")
    return _verified_snapshot(producer, binding)


def _verified_snapshot(producer, binding):
    limit = time.monotonic() + 2
    gid = _operator_sources(producer, binding)
    reader = producer.OperatorReader(binding)
    reader.deadline = limit
    try:
        actual = _operator_identity(producer, binding, gid, reader)
        _provider_controls(reader)
        _need(not reader.finish() and time.monotonic() < limit, "PROVIDER_DRIFT")
        return actual
    finally:
        reader.close()


def _fresh_provider(reader, producer, plan, budget, series):
    _need(tuple(producer.WRITES) == _ROLE_PATHS, "ROLE_CATALOG")
    started = time.monotonic()
    reader.deadline = min(started + 2, plan["started_monotonic"] + 480)
    for variable in ("G", "P"):
        _need(type(budget.get(variable)) is int and budget[variable] > 0, "BUDGET_UNKNOWN")
    incremental = series.sample(reader)
    pair, prior_sockets = _retained_channels(reader, producer, series.current)
    classified, listeners = _verified_socket_inventory(reader)
    final_pair, final_sockets = _retained_channels(reader, producer, series.current)
    _need(pair == final_pair, "PTY_RACE")
    _need(prior_sockets == classified == final_sockets, "SOCKET_TABLE_RACE")
    resources = _provider_controls(reader)
    usage = os.statvfs(str(PurePosixPath(plan["receipt_root"]).parent))
    _need(
        budget["G"] + incremental <= 10500000000
        and budget["P"] + incremental <= 4500000000
        and usage.f_bavail * usage.f_frsize >= 53687091200,
        "MONITOR_THRESHOLD",
    )
    reader.tick()
    _require_holder_closure(pair)
    return (
        listeners,
        resources,
        {
            "incremental_bytes": incremental,
            "G": budget["G"] + incremental,
            "P": budget["P"] + incremental,
            "free": usage.f_bavail * usage.f_frsize,
        },
    )


def _digest_public(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _failure_code(error, producer):
    if isinstance(error, _CleanupFailure) and error.primary is not None:
        return _failure_code(error.primary, producer) + "+" + error.args[0]
    if isinstance(error, (NativeUnproven, producer.FeasibilityRejected)) and error.args:
        value = error.args[0]
        if isinstance(value, str) and re.fullmatch(r"[A-Z_+]{1,256}", value):
            return value
    return "NATIVE_READ_UNPROVEN"


class NativeSession:
    """A same-process, single-subject lifetime with one bounded sampling thread."""

    def __init__(self, plan, producer, budget_ref):
        self.owner = os.getpid()
        self.reader = producer.PosixReader()
        self.producer = producer
        self.plan = copy.deepcopy(plan)
        self.budget_ref = budget_ref
        self.series = RoleGrowth()
        self.closed = False
        self.failure = None
        self.last = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None

    def _release(self):
        self.reader.deadline = min(
            time.monotonic() + 2, self.plan.get("started_monotonic", time.monotonic()) + 480
        )
        errors = []
        try:
            errors.extend(self.reader.finish())
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            errors.append("POSTCHECK_UNPROVEN")
        try:
            self.reader.close()
        except OSError:
            errors.append("NATIVE_CLOSE_UNPROVEN")
        return errors

    def _sample(self):
        raw = _protected_bytes(self.budget_ref["path"], 32768)
        _need(hashlib.sha256(raw).hexdigest() == self.budget_ref["sha256"], "BUDGET_CHANGED")
        budget = json.loads(raw)
        before = time.monotonic()
        reader = self.reader
        marker = len(reader.fds)
        try:
            listeners, limits, sample = _fresh_provider(
                reader, self.producer, self.plan, budget, self.series
            )
            _need(not reader.finish(), "PROVIDER_RACE")
        finally:
            primary = sys.exc_info()[1]
            failed = False
            for fd in reversed(reader.fds[marker:]):
                try:
                    reader.release(fd)
                except OSError:
                    failed = True
            if failed:
                raise _CleanupFailure("NATIVE_FD_CLOSE", primary) from None
        stamp = time.monotonic()
        _need(stamp - before < 2, "SAMPLE_TIMEOUT")
        baseline = _digest_public(
            {"listener_inodes": listeners, "actor": self.actor, "configuration": self.config}
        )
        with self.lock:
            if self.last:
                _need(self.last["channels_binding_sha256"] == baseline, "CHANNEL_BASELINE_RACE")
            self.last = {
                "provider_actor": self.actor,
                "identity_binding_sha256": self.identity,
                "endpoint": self.endpoint,
                "configuration_binding_sha256": self.config,
                "channels_binding_sha256": baseline,
                "resource_values": limits,
                "sample": sample,
                "sampled_monotonic": stamp,
            }

    def begin(self):
        reader = self.reader
        identity = reader.identity()
        self.producer._check_identity(identity)
        self.actor = {
            "pid": 705711,
            "uid": 997,
            "start_ticks": 276887299,
            "exe_sha256": "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601",
            "machine_identity_sha256": identity["machine"],
        }
        self.identity = _digest_public(identity)
        for path in ("/etc/quantmesh/opend/OpenD.xml", "/etc/quantmesh/opend/gateway-profile.json"):
            with _held(reader, reader.held_path(path, reader.root)) as held:
                _need(
                    _stamp(os.fstat(held)) == _stamp(os.stat(path, follow_symlinks=False)),
                    "CONFIG_NAMESPACE",
                )
        self.endpoint, self.config = _trusted_configuration(self.plan)
        reader.tick()
        self._sample()
        # Descriptor 3 is the fixed private write end of the owning parent's watchdog.
        _need(stat.S_ISFIFO(os.fstat(3).st_mode), "OWNED_CONTROL")
        _need(os.write(3, b"RS") == 2, "OWNED_CONTROL")
        self.thread = threading.Thread(target=self._monitor, name="ivv-native-monitor", daemon=True)
        self.thread.start()

    def _monitor(self):
        at = self.last["sampled_monotonic"] + 5
        try:
            while not self.stop.wait(max(0, at - time.monotonic())):
                self._sample()
                _need(os.write(3, b"S") == 1, "OWNED_CONTROL")
                at += 5
        except BaseException as error:
            with self.lock:
                self.failure = _failure_code(error, self.producer)
            os.write(3, b"X")

    def snapshot(self):
        _need(os.getpid() == self.owner and not self.closed, "SESSION_OWNER")
        with self.lock:
            _need(not self.failure, self.failure or "NATIVE_MONITOR_FAILURE")
            _need(
                self.last and 0 <= time.monotonic() - self.last["sampled_monotonic"] <= 5,
                "SAMPLE_STALE",
            )
            return copy.deepcopy(self.last)

    def close(self):
        _need(os.getpid() == self.owner and not self.closed, "SESSION_OWNER")
        self.closed = True
        name = "_qm_live_ivv_native_" + str(self.owner)
        if getattr(sys.modules.get(name), "session", None) is self:
            del sys.modules[name]
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
            _need(not self.thread.is_alive(), "MONITOR_JOIN_UNPROVEN")
        failures = self._release()
        if self.failure:
            failures.insert(0, self.failure)
        if failures:
            raise NativeUnproven("+".join(failures)) from None
        return {"sampler_stopped": True, "reader_closed": True}


def prepare_provider(plan, producer, budget_ref):
    session = NativeSession(plan, producer, budget_ref)
    try:
        session.begin()
    except BaseException as error:
        primary = _failure_code(error, producer)
        try:
            session.close()
        except NativeUnproven as cleanup:
            primary += "+" + str(cleanup)
        raise NativeUnproven(primary) from None
    return session
