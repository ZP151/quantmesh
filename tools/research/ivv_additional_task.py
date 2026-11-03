"""Fixed identities and durable counters for the independent additional IVV task."""

import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from pathlib import Path
from typing import NamedTuple


class Profile(NamedTuple):
    capture_scope_id: str
    capture_effect_sha256: str
    capture_once_key: str
    research_scope_id: str
    research_effect_sha256: str
    authorization_sha256: str
    job_id: str


APPROVED = Profile(
    "53badf05a10d955cc0826dccc592d1807bfbcfec8abcd4f9e3a194857e3d1858",
    "a6681407439408a9d01baecedb3026f16f8e9513d601b2edd56910b0228eee17",
    "189ac10caf73ef7fd31fa01fb4691bb4b00f19a371cc7792330df60bc6d7ac2c",
    "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a",
    "03cade7368127b1ed36425ff9f7334892aba51fbbf516376a65b4da992dabbda",
    "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832",
    "1d05c58d-b536-4b64-b2c3-89e4217cc4ad",
)
TASK = "ivv-additional-20261103-01"
FAMILY = ".dev-additional-task.v1"
MODE = "DEV_ADDITIONAL_TRUSTED_ENVIRONMENT"
DESCRIPTOR = "06f192d60c76a95e91f150e4e4b867218f243759996442abeb58290f7faf6a25"
DESCRIPTOR_FILE = "76944da09e615b0fec9c60a6ed7ea78d7fa364543684b4d4e5832618860dfa12"
POLICY = "c784651ae76033a3a3695fad97d19d7721d7de5c28dc4a901408f101c6ae1e55"
WINDOWS = "22f6cb798c94c436759f4ff85d16b6101010ae5e550e5e7d4dc155c71ca54179"
ROOT = Path("/var/lib/quantmesh-ivv-additional")
TASK_ROOT = ROOT / "tasks/20261103-01"
PEER = "ubuntu@quantmesh-staging-8gb.tail99d23c.ts.net"
UNIT = "qm-ivv-additional-20261103-01.service"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _key():
    return {
        "task_id": TASK,
        "descriptor_sha256": DESCRIPTOR,
        "capture_scope_id": APPROVED.capture_scope_id,
        "capture_effect_sha256": APPROVED.capture_effect_sha256,
    }


def provenance():
    data = APPROVED._asdict()
    del data["job_id"]
    return {
        **data,
        "additional_task_id": TASK,
        "diagnostic_mode": MODE,
        "descriptor_sha256": DESCRIPTOR,
        "policy_sha256": POLICY,
        "capture_budget": {
            "contexts": 1,
            "business_requests": 7,
            "carrier_submissions": 1,
            "init_connect": 1,
            "keepalive": 96,
        },
        "legacy_capture_charge": {"contexts": 1, "business_requests": 7},
        "historical_actual_cumulative": "UNKNOWN",
        "channel_assurance": "UNVERIFIED_TRUSTED_EXTERNAL",
        "hard_limit_enforced": False,
        "provider_tail_max": "UNKNOWN",
    }


def authenticate(approval, descriptor, capture_policy, windows_policy):
    for raw, size, sha in (
        (approval, 7912, APPROVED.authorization_sha256),
        (descriptor, 3300, DESCRIPTOR_FILE),
        (capture_policy, 1547, POLICY),
        (windows_policy, 949, WINDOWS),
    ):
        _need(
            type(raw) is bytes and len(raw) == size and _sha(raw) == sha, "ADDITIONAL_AUTHORITY_PIN"
        )
    event = json.loads(approval)
    spec = json.loads(descriptor)
    _need(
        _sha(_canonical(spec)) == event["approved_descriptor_sha256"] == DESCRIPTOR
        and event["descriptor_file"]["sha256"] == DESCRIPTOR_FILE
        and event["decision"] == "APPROVED_WHOLE_PACKAGE"
        and spec["task_id"] == event["task_id"] == TASK
        and event["approved_identity"]
        == {k: v for k, v in APPROVED._asdict().items() if k != "authorization_sha256"}
        and event["approved_capture"] == spec["capture"]
        and event["approved_research"] == spec["research"]
        and event["approved_selection"] == spec["selection"]
        and _sha(_canonical(_key())) == APPROVED.capture_once_key,
        "ADDITIONAL_AUTHORITY_BINDING",
    )
    return APPROVED


def _remote_ledger():
    ledger = ROOT / "once"
    _need(sys.platform == "linux" and ledger.resolve(strict=True) == ledger, "ONCE_ROOT")
    for path in (ledger, *ledger.parents):
        info = path.lstat()
        _need(
            stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            "ONCE_ROOT_OWNERSHIP",
        )
    return ledger


def _sync_windows_directory(path):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE

    class Info(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("created", wintypes.FILETIME),
            ("accessed", wintypes.FILETIME),
            ("modified", wintypes.FILETIME),
            ("volume", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    kernel.GetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.POINTER(Info))
    kernel.FlushFileBuffers.argtypes = kernel.CloseHandle.argtypes = (wintypes.HANDLE,)

    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def open_directory(access):
        # Exclude delete sharing while held. Do not follow a final reparse point.
        handle = create(str(path), access, 3, None, 3, 0x02000000 | 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def stamp(handle):
        info = Info()
        check(kernel.GetFileInformationByHandle(handle, ctypes.byref(info)))
        _need(info.attributes & 0x10 and not info.attributes & 0x400, "LOCAL_DIRECTORY_REPARSE")
        return (info.volume, info.index_high, info.index_low)

    def named_stamp():
        named = open_directory(0x80)
        try:
            return stamp(named)
        finally:
            check(kernel.CloseHandle(named))

    held = open_directory(0x40000000)
    try:
        before = stamp(held)
        _need(before == named_stamp(), "LOCAL_DIRECTORY_CHANGED")
        check(kernel.FlushFileBuffers(held))
        _need(before == stamp(held) == named_stamp(), "LOCAL_DIRECTORY_CHANGED")
    finally:
        check(kernel.CloseHandle(held))


def _sync_directory(path):
    if os.name == "nt":
        return _sync_windows_directory(path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        held = os.fstat(fd)
        _need(
            stat.S_ISDIR(held.st_mode) and os.path.samestat(held, path.lstat()),
            "CLAIM_DIRECTORY_CHANGED",
        )
        os.fsync(fd)
        _need(os.path.samestat(held, path.lstat()), "CLAIM_DIRECTORY_CHANGED")
    finally:
        os.close(fd)


def _claim(path, value):
    raw = _canonical(value)
    directory = path.parent.lstat()
    fd = os.open(
        path,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        held = os.fstat(fd)
        _need(
            stat.S_ISREG(held.st_mode)
            and held.st_nlink == 1
            and os.path.samestat(held, path.lstat())
            and os.path.samestat(directory, path.parent.lstat()),
            "CLAIM_INODE_CHANGED",
        )
        view = memoryview(raw)
        while view:
            n = os.write(fd, view)
            _need(n > 0, "CLAIM_SHORT_WRITE")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync_directory(path.parent)
    _need(
        os.path.samestat(held, path.lstat())
        and os.path.samestat(directory, path.parent.lstat())
        and path.read_bytes() == raw
        and os.path.samestat(held, path.lstat()),
        "CLAIM_READBACK",
    )


def reserve_context():
    """Caller has admitted the held permit. An ambiguous write or flush stays spent."""
    _claim(_remote_ledger() / APPROVED.capture_once_key, _key())


def _local_root():
    root = Path(
        "C:/Users/15492/.codex-clean/worktrees/0038-security-runtime-alignment/QuantMesh"
        "/output/ivv-additional-capture-20261103-01"
    )
    _need(os.name == "nt" and root.resolve(strict=True) == root, "LOCAL_CLAIM_ROOT")
    for parent in (root, *root.parents):
        info = parent.lstat()
        _need(
            stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400,
            "LOCAL_DIRECTORY_REPARSE",
        )
    return root


def _auth_receipt(start, end, *, peer, command, rc, job_empty, terminal_closed, drained):
    _need(
        all(type(t) in (float, int) and math.isfinite(t) for t in (start, end))
        and 0 <= start <= end <= start + 300
        and peer == PEER
        and command == "/usr/bin/true"
        and type(rc) is int
        and rc == 0
        and job_empty is terminal_closed is drained is True,
        "AUTH_NORMAL_CLOSE",
    )
    return {
        "state": "AUTH_READY",
        "start": start,
        "end": end,
        "peer": peer,
        "command": command,
        "rc": rc,
        "job_empty": job_empty,
        "terminal_closed": terminal_closed,
        "drained": drained,
        "sdk_contexts": 0,
        "business_requests": 0,
        "program_input_bytes": 0,
        "authorization_sha256": APPROVED.authorization_sha256,
        "capture_once_key": APPROVED.capture_once_key,
    }


class _Preparation(NamedTuple):
    pid: int
    receipt_sha256: str


_preparation = None


def prepare_auth_once(owned_transport):
    """Parent-only adapter. The reviewed transport owns Job/SSH and private RAM handoff."""
    root = _local_root()
    start = time.monotonic()
    _claim(
        root / "auth-attempt.json",
        {
            "authorization_sha256": APPROVED.authorization_sha256,
            "capture_once_key": APPROVED.capture_once_key,
            "start": start,
        },
    )
    result = owned_transport(PEER, "/usr/bin/true", b"\n", 300)
    end = time.monotonic()
    actual = {
        "returncode": 0,
        "timeout": False,
        "cap_refusal": False,
        "failure_stage": None,
        "cleanup_errors": [],
        "input_bytes_written": 1,
        "input_complete": True,
        "stdout_original_bytes": 0,
        "stdout_count_complete": True,
        "stderr_count_complete": True,
        "job_closed": True,
        "job_active_zero": True,
        "local_process_terminal": True,
        "drain_complete": True,
        "job_memory_limit": 134217728,
        "job_active_process_limit": 8,
        "automatic_retry": False,
        "local_transport_timeout_s": 300,
        "timeout_includes_drain": True,
    }
    _need(
        type(result) is dict
        and _canonical({k: result.get(k) for k in actual}) == _canonical(actual)
        and set(actual) <= result.keys(),
        "AUTH_TRANSPORT",
    )
    ready = _auth_receipt(
        start,
        end,
        peer=PEER,
        command="/usr/bin/true",
        rc=result["returncode"],
        job_empty=result["job_active_zero"],
        terminal_closed=result["local_process_terminal"],
        drained=result["drain_complete"],
    )
    _claim(root / "auth-ready.json", ready)
    global _preparation
    _preparation = _Preparation(os.getpid(), _sha(_canonical(ready)))
    return _preparation


def claim_carrier(witness, catalog_sha256, carrier_sha256):
    _need(
        witness is not None and witness is _preparation and witness.pid == os.getpid(),
        "AUTH_PREPARATION_OWNER",
    )
    root = _local_root()
    path = root / "auth-ready.json"
    info = path.lstat()
    _need(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and 0 < info.st_size <= 4096
        and not getattr(info, "st_file_attributes", 0) & 0x400,
        "AUTH_READY_METADATA",
    )
    with path.open("rb") as source:
        held = os.fstat(source.fileno())
        _need(os.path.samestat(info, held), "AUTH_READY_CHANGED")
        raw = source.read(4097)
        _need(
            len(raw) == info.st_size
            and os.path.samestat(held, path.lstat())
            and os.fstat(source.fileno()).st_mtime_ns == held.st_mtime_ns,
            "AUTH_READY_CHANGED",
        )

    _need(_sha(raw) == witness.receipt_sha256, "AUTH_READY_CHANGED")
    ready = json.loads(raw)
    expected = _auth_receipt(
        **{
            k: ready[k]
            for k in (
                "start",
                "end",
                "peer",
                "command",
                "rc",
                "job_empty",
                "terminal_closed",
                "drained",
            )
        }
    )
    _need(raw == _canonical(expected) and 0 <= time.monotonic() - ready["end"] <= 60, "AUTH_STALE")
    _need(
        all(
            type(x) is str and re.fullmatch(r"[0-9a-f]{64}", x) and x != "0" * 64
            for x in (catalog_sha256, carrier_sha256)
        ),
        "CARRIER_PINS",
    )
    _claim(
        root / "transport-claim.json",
        {
            "authorization_sha256": APPROVED.authorization_sha256,
            "capture_once_key": APPROVED.capture_once_key,
            "auth_ready_sha256": _sha(raw),
            "catalog_sha256": catalog_sha256,
            "carrier_sha256": carrier_sha256,
            "local_transport_seconds": 510,
            "remote_transport_seconds": 500,
            "logical_state": "SPENT",
        },
    )

    _need(0 <= time.monotonic() - ready["end"] <= 60, "AUTH_STALE_AFTER_CLAIM")


def submit_carrier_once(witness, *, catalog_sha256, carrier_sha256, packet, owned_transport):
    """Issue one verified program submission through the parent's pinned transport."""
    _need(
        type(packet) is bytes
        and 0 < len(packet) <= 16 * 1024 * 1024
        and _sha(packet) == carrier_sha256,
        "CARRIER_PACKET_PIN",
    )
    claim_carrier(witness, catalog_sha256, carrier_sha256)
    return owned_transport(PEER, packet, 500, 510)
