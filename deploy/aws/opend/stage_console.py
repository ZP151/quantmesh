"""Pinned expiring stage or explicit single-operator persistent private console.

Only --start (or the fixed service pane) can release the pinned vendor. Default
preflight has no effects; --owned-fixture uses synthetic children only. No path,
command, endpoint, vendor home or credential is accepted from the CLI.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import select
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MACHINE_SHA = "a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191"
TMUX_SHA = "034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd"
HELPER_SHA = "c18a81701ce432cb93e1ac2243b31add34f3ec10944dc381b92ff8e1d0133b63"
VALIDATOR_SHA = "53fb2821b21dc695a2934dd20d6822f69714e960585e371181d20d0b81441736"
PROFILE_SHA = "0e0b15be83e2b7b435d4e6dbb94f2cbd9c7833e681c4af517e361f5b80b40e17"
UNIT_SHA = "e108294e59e624d17b0f75034930c9ae3fe1f3d3353c44a90586069e1e0cfdac"
PERSISTENT_UNIT_SHA = "b23d91ec4d5b377d57d8a0cae1971974d4268f1faa3a5fed06dc0d0add867890"
CONFIG_SHA = "d6c9c112004bd0866dacc5d0e4fae4d715fcd6db250cd68cae859f787583bffb"
VENDOR_SHA = "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601"
BASE = Path("/opt/quantmesh/opend")
LAUNCHER = BASE / "stage_console.py"
PERMIT = Path("/etc/quantmesh/opend/staging-window.json")
PERSISTENT_PERMIT = Path("/etc/quantmesh/opend/persistent-session.json")
RECOVERY_PERMIT = Path("/etc/quantmesh/opend/persistent-recovery.json")
PRIVATE_STORAGE_NONCE = "c8f0d0de4ca641a491fca6df24c66ceb"
PRIVATE_STORAGE_DROPIN = Path(
    "/etc/systemd/system/quantmesh-opend-console@"
    + PRIVATE_STORAGE_NONCE
    + ".service.d/30-private-storage.conf"
)
PRIVATE_STORAGE_DROPIN_SHA = "db13077f5bec4ee8815de41234406503275fa9b492a57b2959e914ac4428e294"
PRIVATE_STORAGE_SHA = "6e8177e51abb2b8381881ac6d2cac237c00d353efc734292f2730d2d68b3e518"
RECOVERY_SHA = "761f5078f906d734d17bdeab6369bffd09578be5602d161682cb10470d0aee9d"
PROFILE = Path("/etc/quantmesh/opend/gateway-profile.json")
CONFIG = Path("/etc/quantmesh/opend/OpenD.xml")
VENDOR = BASE / "10.10.7008/OpenD"
STATE = Path("/var/lib/quantmesh-opend-stage")
FALSE_FLAGS = dict.fromkeys(
    (
        "production_release_qualified",
        "source_host_private_input_verified",
        "private_input_verified",
        "sdk_wire_verified",
        "server_startup_verified",
        "operator_authenticated",
        "installation_approved",
        "market_verified",
    ),
    False,
)
FIELDS = set(
    "schema_version purpose nonce approved_build launcher_sha256 tmux_version tmux_sha256 "
    "machine_sha256 gateway_uid gateway_gid not_before expires_at max_seconds human_reviewers "
    "safety_owner ci_conclusion operator_window_approved new_device_approved "
    "market_right_transfer_approved".split()
)
CODES = {
    "permit_denied",
    "protected_path",
    "pin_drift",
    "unsupported_native",
    "identity_denied",
    "backend_denied",
    "terminal_denied",
    "duplicate_nonce",
    "registration_interrupted",
    "missing_handle",
    "cleanup_incomplete",
    "deadline",
    "fixture_failed",
    "context_denied",
    "recovery_denied",
    "duplicate_recovery",
    "claim_changed",
    "storage_denied",
}


class StageDenied(RuntimeError):
    """Fixed safe category only, never include input or an underlying exception."""

    def __init__(self, code="permit_denied", *, cleanup=None):
        self.code = code if code in CODES else "context_denied"
        self.cleanup = cleanup or {}
        super().__init__(self.code)


@dataclass(frozen=True)
class StagingWindow:
    claims: dict

    @property
    def nonce(self):
        return self.claims["nonce"]

    @property
    def expires(self):
        return _utc(self.claims["expires_at"])

    @property
    def persistent(self):
        return self.claims.get("schema_version") == 2


@dataclass(frozen=True)
class RecoveryWindow:
    control: object

    @property
    def claims(self):
        return self.control.claims

    @property
    def nonce(self):
        return self.control.nonce

    @property
    def expires(self):
        return _utc(self.claims["expires_at"])

    @property
    def persistent(self):
        return True


def _utc(value):
    if type(value) is not str:
        raise StageDenied()
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
            raise ValueError
        return result
    except (ValueError, AttributeError):
        raise StageDenied() from None


def validate_staging_window(window, *, now, identity, hashes):
    c = window.claims
    if type(c) is not dict or set(c) != (
        FIELDS | {"session_lifetime"} if window.persistent else FIELDS
    ):
        raise StageDenied()
    exact = dict(
        schema_version=2 if window.persistent else 1,
        purpose=(
            "opend_persistent_private_console"
            if window.persistent
            else "opend_initialization_qualification"
        ),
        tmux_version="3.4",
        machine_sha256=MACHINE_SHA,
        tmux_sha256=TMUX_SHA,
        ci_conclusion="success",
        operator_window_approved=True,
        new_device_approved=True,
        market_right_transfer_approved=True,
    )
    if window.persistent:
        exact["session_lifetime"] = "until_operator_stop"
    if any(type(c[k]) is not type(v) or c[k] != v for k, v in exact.items()):
        raise StageDenied()
    for key, length in [("nonce", 32), ("approved_build", 40), ("launcher_sha256", 64)]:
        if type(c[key]) is not str or not re.fullmatch(rf"[0-9a-f]{{{length}}}", c[key]):
            raise StageDenied()
    for key, maximum in [
        ("max_seconds", 900),
        ("gateway_uid", 2**31 - 1),
        ("gateway_gid", 2**31 - 1),
    ]:
        if type(c[key]) is not int or not 1 <= c[key] <= maximum:
            raise StageDenied()
    reviewers = c["human_reviewers"]
    if (
        type(reviewers) is not list
        or len(reviewers) != (1 if window.persistent else 2)
        or any(
            type(r) is not str or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,80}", r) for r in reviewers
        )
        or len(set(reviewers)) != len(reviewers)
        or (window.persistent and reviewers != ["Operator"])
        or type(c["safety_owner"]) is not str
        or c["safety_owner"] not in reviewers
    ):
        raise StageDenied()
    start, end = _utc(c["not_before"]), window.expires
    if now.tzinfo is None or not start <= now < end or not 0 < (end - start).total_seconds() <= 900:
        raise StageDenied()
    if any(c[k] != identity.get(k) for k in ("machine_sha256", "gateway_uid", "gateway_gid")):
        raise StageDenied("identity_denied")
    if any(c[k] != hashes.get(k) for k in ("launcher_sha256", "tmux_sha256")):
        raise StageDenied("pin_drift")


def _native(*, live=False):
    if (
        sys.platform != "linux"
        or platform.machine() != "x86_64"
        or not hasattr(os, "pidfd_open")
        or not hasattr(signal, "pidfd_send_signal")
        or threading.active_count() != 1
        or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL
    ):
        raise StageDenied("unsupported_native")
    if live and (
        sys.version_info[:2] != (3, 12)
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or Path(__file__) != LAUNCHER
        or len(list(Path("/proc/self/task").iterdir())) != 1
    ):
        raise StageDenied("unsupported_native")


@contextmanager
def _protected_fd(path):
    """Walk immutable root-owned directories by FD; deny symlinks/hardlinks."""
    fds = []
    try:
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts:
            raise StageDenied("protected_path")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(fd)
        for part in path.parts[1:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            fds.append(fd)
        if any(os.fstat(d).st_uid != 0 or os.fstat(d).st_mode & 0o022 for d in fds):
            raise StageDenied("protected_path")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        fds.append(fd)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or info.st_mode & 0o6022
        ):
            raise StageDenied("protected_path")
        yield fd
    except OSError:
        raise StageDenied("protected_path") from None
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _bytes(path, digest=None, *, maximum=65536):
    with _protected_fd(path) as fd:
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        if len(data) > maximum:
            raise StageDenied("protected_path")
        result = bytes(data)
        if digest is not None and hashlib.sha256(result).hexdigest() != digest:
            raise StageDenied("pin_drift")
        return result


def _digest_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(fd), "rb") as stream:
        result = hashlib.file_digest(stream, "sha256").hexdigest()
    os.lseek(fd, 0, os.SEEK_SET)
    return result


def _digest(path):
    with _protected_fd(path) as fd:
        return _digest_fd(fd)


def _json(data):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise StageDenied()
            result[k] = v
        return result

    try:
        return json.loads(data, object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise StageDenied() from None


def load_staging_window(path=None, *, persistent=False):
    if path is None:
        path = PERSISTENT_PERMIT if persistent else PERMIT
    return StagingWindow(_json(_bytes(path)))


def select_console_window(nonce, *, persistent=False):
    if persistent:
        try:
            RECOVERY_PERMIT.lstat()
        except FileNotFoundError:
            pass
        else:
            module = _module(BASE / "same_unit_recovery.py", RECOVERY_SHA)
            return RecoveryWindow(module.load(sys.modules[__name__], nonce))
    return load_staging_window(persistent=True) if persistent else load_staging_window()


def reload_console_window(window):
    if isinstance(window, RecoveryWindow):
        module = _module(BASE / "same_unit_recovery.py", RECOVERY_SHA)
        return RecoveryWindow(module.load(sys.modules[__name__], window.nonce))
    return load_staging_window(persistent=True) if window.persistent else load_staging_window()


def _module(path, digest):
    # Compile only verified source bytes. No import loader, pycache or search path.
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(_bytes(path, digest), str(path), "exec"), module.__dict__)
    return module


def _admit(window):
    _native(live=True)
    import grp
    import pwd

    try:
        account = pwd.getpwnam("quantmesh-opend")
        group = grp.getgrnam("quantmesh-opend")
    except KeyError:
        raise StageDenied("identity_denied") from None
    if (
        account.pw_uid != os.getuid()
        or account.pw_uid != os.geteuid()
        or group.gr_gid != os.getgid()
        or group.gr_gid != os.getegid()
        or any(g != group.gr_gid for g in os.getgroups())
    ):
        raise StageDenied("identity_denied")
    identity = dict(
        machine_sha256=hashlib.sha256(_bytes(Path("/etc/machine-id"))).hexdigest(),
        gateway_uid=account.pw_uid,
        gateway_gid=group.gr_gid,
    )
    hashes = dict(launcher_sha256=_digest(LAUNCHER), tmux_sha256=_digest(Path("/usr/bin/tmux")))
    if isinstance(window, RecoveryWindow):
        if _digest(BASE / "same_unit_recovery.py") != RECOVERY_SHA:
            raise StageDenied("pin_drift")
        window.control.validate(
            now=datetime.now(UTC),
            identity=identity,
            hashes={**hashes, "vendor_sha256": _digest(VENDOR)},
        )
        if window.nonce == PRIVATE_STORAGE_NONCE:
            storage = _module(BASE / "private_storage.py", PRIVATE_STORAGE_SHA)
            try:
                storage.validate_live(window.claims)
            except storage.StorageDenied:
                raise StageDenied("storage_denied") from None
    else:
        validate_staging_window(window, now=datetime.now(UTC), identity=identity, hashes=hashes)
    validator = _module(BASE / "validate_profile.py", VALIDATOR_SHA)
    profile = _json(_bytes(PROFILE, PROFILE_SHA))
    configuration = _bytes(CONFIG, CONFIG_SHA)
    try:
        validator.validate_profile(profile, config_bytes=configuration)
    except (ValueError, KeyError, TypeError):
        raise StageDenied("pin_drift") from None
    if (
        profile["qualification"]["state"] != "blocked"
        or any(
            profile["qualification"][k] is not False
            for k in ("install_allowed", "operator_approved", "server_startup_verified")
        )
        or profile["sdk"]["wire_compatibility_verified"] is not False
        or profile["authentication"]["private_input_verified"] is not False
        or _digest(VENDOR) != VENDOR_SHA
    ):
        raise StageDenied("pin_drift")
    # Only the reviewed credential-free XML is read, never vendor state/config/logs.
    helper = _module(BASE / "qualify_opend_private_terminal.py", HELPER_SHA)
    _vendor_tree(BASE / "10.10.7008")
    with _owned_dir(Path("/var/lib/quantmesh-opend")):
        pass
    return profile, helper


def _vendor_tree(path):
    # Inspect pristine immutable installation metadata, never mutable vendor state.
    # Symlinks/capability binaries require a coordinator ruling; do not weaken this guard.
    with _directory(path) as root:
        for _, directories, files, directory in os.fwalk(".", dir_fd=root, follow_symlinks=False):
            for name in directories + files:
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if (
                    info.st_uid != 0
                    or info.st_mode & 0o6022
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
                ):
                    raise StageDenied("protected_path")
        with _protected_fd(VENDOR) as executable:
            if "security.capability" in os.listxattr(executable):
                raise StageDenied("protected_path")


def _paths(window):
    prefix = "quantmesh-opend-console-" if window.persistent else "quantmesh-opend-stage-"
    return Path("/run") / (prefix + window.nonce)


def _unit(window):
    prefix = "quantmesh-opend-console@" if window.persistent else "quantmesh-opend-stage@"
    return prefix + window.nonce + ".service"


def _owned_dir(path):
    return _directory(path, private=True)


@contextmanager
def _directory(path, *, private=False):
    fds = []
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(fd)
        for index, part in enumerate(path.parts[1:]):
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise StageDenied("protected_path")
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            fds.append(fd)
        info = os.fstat(fd)
        if private:
            if (
                info.st_uid != os.getuid()
                or info.st_gid != os.getgid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise StageDenied("protected_path")
        elif info.st_uid != 0 or info.st_mode & 0o022:
            raise StageDenied("protected_path")
        yield fd
    except OSError:
        raise StageDenied("protected_path") from None
    finally:
        for fd in reversed(fds):
            os.close(fd)


MANAGER_FIXED = dict(
    Type="exec",
    User="quantmesh-opend",
    Group="quantmesh-opend",
    KillMode="control-group",
    Restart="no",
    RuntimeMaxUSec="15min",
    TimeoutStopUSec="15s",
    RuntimeRandomizedExtraUSec="0",
    StandardInput="null",
    StandardOutput="null",
    StandardError="null",
    RuntimeDirectoryMode="0700",
    UMask="0077",
    NoNewPrivileges="yes",
    CapabilityBoundingSet="",
    AmbientCapabilities="",
    DropInPaths="",
    FragmentPath="/etc/systemd/system/quantmesh-opend-stage@.service",
)


def _manager_contract(window):
    if not window.persistent:
        return MANAGER_FIXED
    contract = {
        **MANAGER_FIXED,
        "RuntimeMaxUSec": "infinity",
        "FragmentPath": "/etc/systemd/system/quantmesh-opend-console@.service",
        "MemoryMax": "1073741824",
        "MemoryHigh": "805306368",
        "MemorySwapMax": "0",
        "CPUQuotaPerSecUSec": "500ms",
        "TasksMax": "128",
    }
    if isinstance(window, RecoveryWindow) and window.nonce == PRIVATE_STORAGE_NONCE:
        contract.update(
            DropInPaths=PRIVATE_STORAGE_DROPIN.as_posix(),
            PrivateMounts="yes",
            PrivateTmp="no",
            StateDirectory="",
            RuntimeDirectoryPreserve="yes",
            ProtectSystem="strict",
            ReadWritePaths=(
                "/var/lib/quantmesh-opend /var/lib/quantmesh-opend-stage "
                "/run/quantmesh-opend-console-" + PRIVATE_STORAGE_NONCE + " /tmp /var/tmp /dev/shm"
            ),
        )
    return contract


def _validate_manager(window, properties, *, preparing=False):
    if any(properties.get(k) != v for k, v in _manager_contract(window).items()):
        raise StageDenied("backend_denied")
    if (
        properties.get("Id") != _unit(window)
        or properties.get("RuntimeDirectory") != _paths(window).name
        or properties.get("ActiveState") not in {"active", "activating"}
    ):
        raise StageDenied("backend_denied")
    cg = properties.get("ControlGroup", "")
    if (
        not cg.startswith("/system.slice/")
        or not cg.endswith("/" + _unit(window))
        or ".." in cg.split("/")
    ):
        raise StageDenied("backend_denied")
    if not preparing and not re.fullmatch(r"[1-9][0-9]*", properties.get("MainPID", "")):
        raise StageDenied("backend_denied")


def _command(argv):
    # Only internally fixed manager/metadata commands, never terminal/journal data.
    with _protected_fd(Path(argv[0])):
        pass
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            timeout=2,
        )
        if result.returncode or len(result.stdout) > 16384:
            raise StageDenied("backend_denied")
        return result.stdout.decode("ascii").strip()
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise StageDenied("backend_denied") from None


def _manager(window, *, preparing=False):
    contract = _manager_contract(window)
    _bytes(Path(contract["FragmentPath"]), PERSISTENT_UNIT_SHA if window.persistent else UNIT_SHA)
    if isinstance(window, RecoveryWindow) and window.nonce == PRIVATE_STORAGE_NONCE:
        _bytes(PRIVATE_STORAGE_DROPIN, PRIVATE_STORAGE_DROPIN_SHA)
    names = list(contract) + [
        "Id",
        "MainPID",
        "ActiveState",
        "ControlGroup",
        "RuntimeDirectory",
    ]
    output = _command(
        ["/usr/bin/systemctl", "show", "--no-pager", "--property=" + ",".join(names), _unit(window)]
    )
    properties = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key in properties:
            raise StageDenied("backend_denied")
        properties[key] = value
    _validate_manager(window, properties, preparing=preparing)
    return properties


def _cgroup(pid):
    # Kernel-owned process metadata only; no cmdline, environment or journal.
    text = Path(f"/proc/{pid}/cgroup").read_text()
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].startswith("0::/"):
        raise StageDenied("backend_denied")
    return lines[0][3:]


def _tmux_config(window):
    return (
        b"set-option -g history-limit 0\n"
        # tmux 3.4 minimum is 1. Disable every creation mechanism, not an invalid 0.
        b"set-option -s buffer-limit 1\n"
        b"set-option -s message-limit 0\n"
        b"set-option -s prompt-history-limit 0\n"
        b"set-option -s history-file ''\n"
        b"set-option -s set-clipboard off\n"
        b"set-option -s copy-command ''\n"
        b"set-option -g update-environment ''\n"
        b"set-option -s exit-unattached off\n"
        b"set-option -g status off\n"
        b"set-option -g remain-on-exit off\n"
        b"unbind-key -a\n"
        b"unbind-key -a -T root\n"
        b"set-option -g prefix None\n"
    )


def _pane_command(window):
    return [
        "/usr/bin/tmux",
        "-N",
        "-S",
        str(_paths(window) / "socket"),
        "new-session",
        "-d",
        "-s",
        "opend",
        "/usr/bin/python3",
        "-I",
        "-S",
        "-B",
        str(LAUNCHER),
        "--pane",
        "--nonce",
        window.nonce,
        *(["--persistent"] if window.persistent else []),
    ]


def _create_pane(window):
    _unclaimed(window)
    until = time.monotonic() + 5
    while True:
        with _owned_dir(_paths(window)) as directory:
            try:
                os.stat("socket", dir_fd=directory, follow_symlinks=False)
                break
            except FileNotFoundError:
                pass
        if time.monotonic() >= until:
            raise StageDenied("backend_denied")
        select.select([], [], [], 0.02)
    context = _backend_context(window, pane=False)
    try:
        _command(_pane_command(window))
    finally:
        os.close(context["backend_pidfd"])
    return dict(status="admitted", scope="FIXED_PRIVATE_PANE_CREATED", **FALSE_FLAGS)


def _runtime_config(window):
    with _owned_dir(_paths(window)) as directory:
        fd = os.open("tmux.conf", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if (
                info.st_uid != os.getuid()
                or info.st_nlink != 1
                or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or os.read(fd, 8192) != _tmux_config(window)
            ):
                raise StageDenied("backend_denied")
        finally:
            os.close(fd)


def _claim(window, directory):
    try:
        fd = os.open(
            window.nonce,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
    except FileExistsError:
        raise StageDenied("duplicate_nonce") from None
    try:
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        os.fsync(directory)
    finally:
        os.close(fd)


def _unclaimed(window):
    if isinstance(window, RecoveryWindow):
        window.control.check_available()
        return
    with _owned_dir(STATE) as directory:
        try:
            os.stat(window.nonce, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return
    raise StageDenied("duplicate_nonce")


def _prepare(window):
    _unclaimed(window)
    properties = _manager(window, preparing=True)
    if _cgroup("self") != properties["ControlGroup"]:
        raise StageDenied("backend_denied")
    with _owned_dir(_paths(window)) as directory:
        fd = os.open(
            "tmux.conf",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            os.fchmod(fd, 0o600)
            data = _tmux_config(window)
            if os.write(fd, data) != len(data):
                raise StageDenied("backend_denied")
            os.fsync(fd)
        finally:
            os.close(fd)
    return dict(status="admitted", scope="FIXED_RUNTIME_PREPARED", **FALSE_FLAGS)


def _same_manager(a, b):
    # Type=exec's activation transition is allowed; all authority properties stay exact.
    return {k: v for k, v in a.items() if k != "ActiveState"} == {
        k: v for k, v in b.items() if k != "ActiveState"
    }


def _backend_context(window, *, pane):
    _, helper = _admit(window)
    properties = _manager(window)
    pid = int(properties["MainPID"])
    handle = os.pidfd_open(pid)
    try:
        if (
            select.select([handle], [], [], 0)[0]
            or (pane and os.getppid() != pid)
            or _cgroup("self") != properties["ControlGroup"]
            or _cgroup(pid) != properties["ControlGroup"]
            or os.readlink(f"/proc/{pid}/exe") != "/usr/bin/tmux"
        ):
            raise StageDenied("backend_denied")
        # This one kernel symlink is tied to the retained pidfd, never a user path.
        actual = os.open(f"/proc/{pid}/exe", os.O_RDONLY)
        try:
            with _protected_fd(Path("/usr/bin/tmux")) as pinned:
                a, b = os.fstat(actual), os.fstat(pinned)
                if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) or _digest_fd(actual) != TMUX_SHA:
                    raise StageDenied("backend_denied")
        finally:
            os.close(actual)
        _runtime_config(window)
        socket = _paths(window) / "socket"
        with _owned_dir(_paths(window)) as directory:
            info = os.stat("socket", dir_fd=directory, follow_symlinks=False)
            if (
                not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                raise StageDenied("backend_denied")
        if not pane:
            if select.select([handle], [], [], 0)[0] or not _same_manager(
                _manager(window), properties
            ):
                raise StageDenied("backend_denied")
            return dict(manager=properties, backend_pidfd=handle)
        if os.environ.get("TMUX") != f"{socket},{pid},0" or os.environ.get("TMUX_PANE") != "%0":
            raise StageDenied("backend_denied")
        metadata = _command(
            [
                "/usr/bin/tmux",
                "-N",
                "-S",
                str(socket),
                "display-message",
                "-p",
                "-t",
                "%0",
                "#{pane_pid}|#{pane_tty}|#{pid}|#{socket_path}|#{pane_pipe}|#{history_size}|#{history_limit}",
            ]
        )
        if metadata != f"{os.getpid()}|{os.ttyname(0)}|{pid}|{socket}|0|0|0":
            raise StageDenied("backend_denied")
        proof = helper.inspect_private_terminal(0, 1, 2, expected_uid=os.getuid())
        if select.select([handle], [], [], 0)[0] or not _same_manager(_manager(window), properties):
            raise StageDenied("backend_denied")
        return dict(manager=properties, terminal=proof, backend_pidfd=handle)
    except BaseException:
        os.close(handle)
        raise


def inspect_staging_context(window):
    return _backend_context(window, pane=True)


def start_staging_console(window):
    profile, helper = _admit(window)
    context = inspect_staging_context(window)
    child = None
    registered = []
    held = []
    old_handlers = {}
    deadline = time.monotonic() + min(
        window.claims["max_seconds"], (window.expires - datetime.now(UTC)).total_seconds()
    )
    try:
        _unclaimed(window)
        if not isinstance(window, RecoveryWindow):
            with _owned_dir(STATE) as directory:
                _claim(window, directory)
        for fd in (0, 1, 2):
            held.append(os.dup(fd))
        proof = helper.inspect_private_terminal(*held, expected_uid=os.getuid())
        # FD labels differ on duplicates; compare the device signatures explicitly.
        if [p["rdev"] for p in proof["descriptors"]] != [
            p["rdev"] for p in context["terminal"]["descriptors"]
        ]:
            raise StageDenied("terminal_denied")

        def interrupted(signum, frame):
            raise StageDenied("deadline")

        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            old_handlers[signum] = signal.signal(signum, interrupted)
        with _protected_fd(VENDOR) as executable:
            if _digest_fd(executable) != VENDOR_SHA:
                raise StageDenied("pin_drift")
            child = _spawn_gated(
                tuple(held),
                fixture=False,
                seconds=0
                if window.persistent
                else min(900, math.ceil(deadline - time.monotonic())),
                executable=executable,
                vendor_argv=profile["runtime"]["argv"],
                registry=registered,
                **({"persistent": True} if window.persistent else {}),
            )

            def final_admission():
                latest = reload_console_window(window)
                if latest.claims != window.claims or time.monotonic() >= deadline:
                    raise StageDenied("deadline")
                check = inspect_staging_context(latest)
                try:
                    if (
                        not _same_manager(check["manager"], context["manager"])
                        or check["terminal"] != context["terminal"]
                    ):
                        raise StageDenied("context_denied")
                    if helper.inspect_private_terminal(*held, expected_uid=os.getuid()) != proof:
                        raise StageDenied("terminal_denied")
                    if _cgroup(child.pid) != context["manager"]["ControlGroup"]:
                        raise StageDenied("backend_denied")
                finally:
                    os.close(check["backend_pidfd"])
                # Manager, descriptor and source checks can consume the launch
                # window. Recheck both clocks and the exact permit after them.
                final_permit = reload_console_window(window)
                if (
                    final_permit.claims != window.claims
                    or time.monotonic() >= deadline
                    or datetime.now(UTC) >= window.expires
                ):
                    raise StageDenied("deadline")

            if isinstance(window, RecoveryWindow):
                with window.control.release_lease() as recovery_lease:

                    def release_recovery():
                        recovery_lease.consume()
                        # Persistence may block: revalidate current source/host
                        # and then live authority again before the gate clocks.
                        _admit(window)
                        recovery_lease.check()

                    child.release(
                        final_admission,
                        deadline=deadline,
                        expires=window.expires,
                        before_gate=release_recovery,
                    )
            else:
                child.release(final_admission, deadline=deadline, expires=window.expires)
            while child.alive():
                if window.persistent:
                    # Freshness was checked immediately before release. Once released,
                    # this explicit Operator session lasts until owned stop/exit.
                    if select.select([context["backend_pidfd"]], [], [], 0)[0]:
                        break
                    select.select([child.pidfd, context["backend_pidfd"]], [], [], 0.2)
                    continue
                remaining = min(
                    deadline - time.monotonic(),
                    (window.expires - datetime.now(UTC)).total_seconds(),
                )
                if remaining <= 0 or select.select([context["backend_pidfd"]], [], [], 0)[0]:
                    break
                select.select([child.pidfd, context["backend_pidfd"]], [], [], min(0.2, remaining))
            child.close()
        return dict(
            status="stopped",
            scope="PERSISTENT_PRIVATE_CONSOLE_ONLY" if window.persistent else "EXPIRING_STAGE_ONLY",
            **FALSE_FLAGS,
            child_terminal=child.terminal,
            child_returncode=child.returncode,
        )
    finally:
        try:
            for known in reversed(registered):
                if not known.closed:
                    known.close()
        finally:
            for fd in held:
                os.close(fd)
            for signum, handler in old_handlers.items():
                signal.signal(signum, handler)
            # Ending MainPID invokes the manager's control-group cleanup, including
            # descendants, even when permit expiry is earlier than RuntimeMaxSec.
            _finish_backend(context["backend_pidfd"])


def _stop_backend(handle):
    if not select.select([handle], [], [], 0)[0]:
        signal.pidfd_send_signal(handle, signal.SIGTERM)


def _finish_backend(handle):
    try:
        _stop_backend(handle)
    finally:
        os.close(handle)


def _prctl(option, argument):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(option, argument, 0, 0, 0) != 0:
        raise StageDenied("unsupported_native")


def _identity(pid, handle):
    if select.select([handle], [], [], 0)[0]:
        raise StageDenied("missing_handle")
    info = os.stat(f"/proc/{pid}")
    fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
    if info.st_uid != os.getuid() or int(fields[1]) != os.getpid():
        raise StageDenied("identity_denied")
    return dict(pid=pid, start_ticks=int(fields[19]), uid=info.st_uid)


def _report(fd, count, seconds=2):
    data = bytearray()
    until = time.monotonic() + seconds
    while len(data) < count:
        remaining = until - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise StageDenied("fixture_failed")
        part = os.read(fd, count - len(data))
        if not part:
            raise StageDenied("fixture_failed")
        data.extend(part)
    return bytes(data)


@dataclass
class _Owned:
    pid: int
    pidfd: int
    gate: int
    report: int
    identity: dict
    released: bool = False
    terminal: bool = False
    closed: bool = False
    returncode: int | None = None

    def alive(self):
        return not self.terminal and not select.select([self.pidfd], [], [], 0)[0]

    def release(self, admission=lambda: None, *, deadline=None, expires=None, before_gate=None):
        admission()
        if not self.alive() or _identity(self.pid, self.pidfd) != self.identity:
            raise StageDenied("missing_handle")
        if (deadline is not None and time.monotonic() >= deadline) or (
            expires is not None and datetime.now(UTC) >= expires
        ):
            raise StageDenied("deadline")
        if before_gate is not None:
            # Recovery authority commits after existing PID checks, at this gate.
            # Initial callers keep the original path and perform no extra work.
            before_gate()
            if (deadline is not None and time.monotonic() >= deadline) or (
                expires is not None and datetime.now(UTC) >= expires
            ):
                raise StageDenied("deadline")
        os.write(self.gate, b"R")
        self.released = True
        if _report(self.report, 1) != b"R":
            raise StageDenied("fixture_failed")

    def wait(self, seconds=4):
        if not self.terminal:
            if not select.select([self.pidfd], [], [], seconds)[0]:
                raise StageDenied("cleanup_incomplete")
            pid, status = os.waitpid(self.pid, 0)
            self.terminal = pid == self.pid
            self.returncode = os.waitstatus_to_exitcode(status)
        return self.returncode

    def close(self):
        if self.closed:
            return
        if self.alive():
            signal.pidfd_send_signal(self.pidfd, signal.SIGTERM)
            if not select.select([self.pidfd], [], [], 1)[0]:
                signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
        self.wait()
        for fd in (self.gate, self.report, self.pidfd):
            os.close(fd)
        self.closed = True


def _child(
    gate,
    report,
    terminal_fds,
    seconds,
    parent,
    fixture,
    role,
    executable,
    vendor_argv,
    persistent=False,
):
    """Gated child; terminal descriptors pass directly, with no relay or capture."""
    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
            signal.signal(signum, signal.SIG_DFL)
        _prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG, preserved by ordinary exec.
        if os.getppid() != parent:
            os._exit(40)
        signal.pthread_sigmask(signal.SIG_SETMASK, [])
        if terminal_fds is None:
            fd = os.open("/dev/null", os.O_RDWR)
            for target in (0, 1, 2):
                os.dup2(fd, target)
            if fd > 2:
                os.close(fd)
        else:
            for fd, target in zip(terminal_fds, (0, 1, 2), strict=True):
                os.dup2(fd, target)
        keep = {0, 1, 2, gate, report, executable}
        for entry in Path("/proc/self/fd").iterdir():
            fd = int(entry.name)
            if fd not in keep:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if not select.select([gate], [], [], 2)[0] or os.read(gate, 1) != b"R":
            os._exit(40)
        if fixture and terminal_fds is not None:
            import fcntl
            import termios

            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        signal.setitimer(signal.ITIMER_REAL, 0 if persistent else seconds)
        os.write(report, b"R")
        if not fixture:
            os.close(gate)
            os.close(report)
            os.chdir(BASE / "10.10.7008")
            os.execve(
                executable,
                [str(VENDOR), *vendor_argv],
                {
                    "HOME": "/var/lib/quantmesh-opend",
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "LD_LIBRARY_PATH": str(BASE / "10.10.7008"),
                    "TERM": "xterm-256color",
                },
            )
        elif role == "parent":
            child = _spawn_gated(None, fixture=True, seconds=60)
            child.release()
            os.write(report, str(child.pid).encode().ljust(16, b" "))
            select.select([], [], [], 60)
        else:
            # Synthetic blocked child uses no terminal byte reads or writes.
            select.select([], [], [], 60 if persistent else seconds + 1)
        os._exit(0)
    except BaseException:
        os._exit(41)


def _spawn_gated(
    terminal_fds,
    *,
    fixture,
    seconds,
    role="blocked",
    failure=None,
    executable=None,
    vendor_argv=None,
    registry=None,
    persistent=False,
):
    _native()
    if terminal_fds is not None and type(terminal_fds) is int:
        terminal_fds = (terminal_fds,) * 3
    if (
        role not in {"blocked", "parent"}
        or type(persistent) is not bool
        or not (seconds == 0 if persistent else 0 < seconds <= 900)
    ):
        raise StageDenied("context_denied")
    descriptors = []
    pid = handle = None
    owned = None
    old_mask = None
    try:
        gate_r, gate_w = os.pipe()
        descriptors.extend([gate_r, gate_w])
        report_r, report_w = os.pipe()
        descriptors.extend([report_r, report_w])
        old_mask = signal.pthread_sigmask(
            signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
        )
        parent = os.getpid()
        pid = os.fork()
        if pid == 0:
            _child(
                gate_r,
                report_w,
                terminal_fds,
                seconds,
                parent,
                fixture,
                role,
                executable,
                vendor_argv,
                persistent,
            )
            os._exit(41)
        os.close(gate_r)
        descriptors.remove(gate_r)
        os.close(report_w)
        descriptors.remove(report_w)
        if failure == "registration_interrupted":
            signal.raise_signal(signal.SIGINT)
        handle = os.pidfd_open(pid, 1 if failure == "missing_handle" else 0)
        identity = _identity(pid, handle)
        owned = _Owned(pid, handle, gate_w, report_r, identity)
        if registry is not None:
            registry.append(owned)
        if failure == "registered_then_interrupt":
            signal.raise_signal(signal.SIGINT)
        previous, old_mask = old_mask, None
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        return owned
    except BaseException as error:
        for fd in descriptors:
            os.close(fd)
        # Gate EOF/timeout makes an unregistered child exit independently; never signal by PID.
        terminal = pid is None
        code = None
        until = time.monotonic() + 4
        while pid is not None and time.monotonic() < until:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited == pid:
                code = os.waitstatus_to_exitcode(status)
                terminal = True
                break
            select.select([], [], [], 0.01)
        if handle is not None:
            os.close(handle)
        if owned is not None and registry is not None:
            registry.remove(owned)
        category = (
            "registration_interrupted" if isinstance(error, KeyboardInterrupt) else "missing_handle"
        )
        if not terminal:
            category = "cleanup_incomplete"
        raise StageDenied(
            category, cleanup=dict(terminal=terminal, released=False, returncode=code, pid=pid)
        ) from None
    finally:
        if old_mask is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)


@contextmanager
def _fixture_pty():
    import pty
    import termios

    master, slave = pty.openpty()
    try:
        os.fchmod(slave, 0o600)
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        yield master, slave
    finally:
        os.close(master)
        os.close(slave)


def run_owned_fixture():
    _native()
    started = time.monotonic()
    children = []
    root = Path(tempfile.mkdtemp(prefix="quantmesh-opend-stage-", dir="/var/tmp"))
    result = dict(
        status="failed",
        scope="OWNED_LOCAL_STAGING_FIXTURE",
        **FALSE_FLAGS,
        mocked=["root_permit", "systemd_manager", "tmux_backend", "source_host"],
        native=["fork_gate", "pidfd", "waitpid", "private_pty", "expiry", "pdeathsig", "hup"],
        root=str(root),
        owner_uid=os.getuid(),
        cases={},
        python_version=platform.python_version(),
    )
    subreaper = ctypes.c_int()
    _prctl(37, ctypes.byref(subreaper))
    _prctl(36, 1)
    try:
        os.chmod(root, 0o700)
        sibling = _spawn_gated(None, fixture=True, seconds=80)
        children.append(sibling)
        sibling.release()
        result["sibling_identity"] = sibling.identity
        for name in ("expiry", "hup", "blocked", "missing_handle", "registration_interrupted"):
            with _fixture_pty() as (master, slave):
                if name in {"missing_handle", "registration_interrupted"}:
                    try:
                        _spawn_gated(slave, fixture=True, seconds=2, failure=name)
                    except StageDenied as error:
                        if error.code != name or not error.cleanup.get("terminal"):
                            raise
                        case = error.cleanup
                    else:
                        raise StageDenied("fixture_failed")
                else:
                    child = _spawn_gated(
                        slave, fixture=True, seconds=0.25 if name == "expiry" else 60
                    )
                    children.append(child)
                    child.release()
                    if name == "hup":
                        # Drop only the exact fixture master. Context retains no reused FD.
                        os.close(master)
                        replacement = os.open("/dev/null", os.O_RDONLY)
                        if replacement != master:
                            os.dup2(replacement, master)
                            os.close(replacement)
                    if name in {"expiry", "hup"}:
                        expected = -signal.SIGALRM if name == "expiry" else -signal.SIGHUP
                        if child.wait() != expected:
                            raise StageDenied("fixture_failed")
                    else:
                        child.close()
                    case = dict(
                        terminal=child.terminal,
                        released=child.released,
                        returncode=child.returncode,
                        identity=child.identity,
                    )
                case["sibling_survived"] = sibling.alive()
                if not case["sibling_survived"]:
                    raise StageDenied("fixture_failed")
                result["cases"][name] = case
        parent = _spawn_gated(None, fixture=True, seconds=60, role="parent")
        children.append(parent)
        parent.release()
        child_pid = int(_report(parent.report, 16).strip())
        adopted_handle = os.pidfd_open(child_pid)
        try:
            signal.pidfd_send_signal(parent.pidfd, signal.SIGKILL)
            parent.wait()
            if not select.select([adopted_handle], [], [], 4)[0]:
                raise StageDenied("cleanup_incomplete")
            waited, status = os.waitpid(child_pid, 0)
            result["cases"]["parent_loss"] = dict(
                terminal=waited == child_pid,
                returncode=os.waitstatus_to_exitcode(status),
                pid=child_pid,
                sibling_survived=sibling.alive(),
            )
            if (
                waited != child_pid
                or os.waitstatus_to_exitcode(status) != -signal.SIGKILL
                or not sibling.alive()
            ):
                raise StageDenied("fixture_failed")
        finally:
            os.close(adopted_handle)
        result["status"] = "passed"
    except BaseException as error:
        result["error_code"] = error.code if isinstance(error, StageDenied) else "fixture_failed"
    finally:
        cleanup = True
        for child in reversed(children):
            try:
                child.close()
            except BaseException:
                cleanup = False
        result["all_owned_children_terminal"] = cleanup and all(
            child.terminal for child in children
        )
        _prctl(36, subreaper.value)
        try:
            root.rmdir()
            result["owned_root_removed"] = True
        except OSError:
            result["owned_root_removed"] = False
        result["elapsed_seconds"] = round(time.monotonic() - started, 6)
        if not cleanup or not result["owned_root_removed"] or result["elapsed_seconds"] >= 90:
            result.update(status="failed", error_code="cleanup_incomplete")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group()
    for name in ("start", "check-window", "prepare", "create-pane", "pane", "owned-fixture"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument(
        "--nonce",
        type=lambda s: s if re.fullmatch(r"[0-9a-f]{32}", s) else parser.error("invalid nonce"),
    )
    args = parser.parse_args(argv)
    if args.persistent and not (
        args.start or args.check_window or args.prepare or args.create_pane or args.pane
    ):
        parser.error("persistent requires a service mode")
    if args.nonce and not (
        args.start or args.check_window or args.prepare or args.create_pane or args.pane
    ):
        parser.error("nonce requires a staging service mode")
    receipt = dict(status="pending", scope="PREFLIGHT_NO_EFFECT", **FALSE_FLAGS)
    try:
        if args.owned_fixture:
            receipt = run_owned_fixture()
        elif args.start or args.check_window or args.prepare or args.create_pane or args.pane:
            window = select_console_window(args.nonce, persistent=args.persistent)
            if window.persistent != args.persistent:
                raise StageDenied()
            _admit(window)
            if args.nonce != window.nonce:
                raise StageDenied()
            if args.check_window:
                _unclaimed(window)
                receipt = dict(status="admitted", scope="STAGING_WINDOW_ONLY", **FALSE_FLAGS)
            elif args.prepare:
                receipt = _prepare(window)
            elif args.create_pane:
                receipt = _create_pane(window)
            else:
                if args.pane:
                    import termios

                    # Only this service's own pane; never create/discover a terminal.
                    properties = _manager(window)
                    if (
                        os.getppid() != int(properties["MainPID"])
                        or _cgroup("self") != properties["ControlGroup"]
                    ):
                        raise StageDenied("backend_denied")
                    os.fchmod(0, 0o600)
                    attrs = termios.tcgetattr(0)
                    attrs[3] &= ~(termios.ECHO | termios.ECHONL)
                    termios.tcsetattr(0, termios.TCSANOW, attrs)
                receipt = start_staging_console(window)
    except (Exception, KeyboardInterrupt) as error:
        receipt = dict(
            status="pending",
            scope="STAGING_DENIED",
            **FALSE_FLAGS,
            error_code=error.code if isinstance(error, StageDenied) else "context_denied",
        )
    if not args.pane:
        print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] in {"admitted", "passed", "stopped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
