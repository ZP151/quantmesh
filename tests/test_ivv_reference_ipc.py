"""Actual closed supervisor/channel seam; modeled kernel reads, no SDK or transport."""

import io
import stat
import struct
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
import test_ivv_reference_condition as fixture


@pytest.mark.parametrize("fault", [None, "foreign", "pair", "lease", "extra", "reference_mode"])
def test_parent_existing_observe_authenticates_conditional_may(monkeypatch, fault):
    original_open = Path.open
    case = fixture.ConditionOwner()
    try:
        r, book, value, pair_sha, native, producer, read = case.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        attempt = book.begin(
            value["method_sha256"],
            now=101,
            reference_transition=ref,
            pre_dispatch=fixture.dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        original = dict(
            schema="qm.ivv.executable-origin.v1",
            method="EXACT_PATH",
            phase="INITIAL",
            python_sha256="b" * 64,
            namespace_inode=44,
            kernel_mount_readonly="UNKNOWN",
        )
        requested = dict(ref)
        if fault == "pair":
            requested["pair_sha256"] = "0" * 64
        packet = dict(
            op="observe",
            executable_origin=dict(original, phase="SESSION"),
            reference_transition=requested,
        )
        if fault == "extra":
            packet["extra"] = True
        packets = [dict(op="ready", executable_origin=original), packet]
        replies = []

        class Observed(Exception):
            pass

        class Socket:
            type = 5

            def fileno(self):
                return 99

            def setsockopt(self, *args):
                pass

            def settimeout(self, *args):
                pass

            def send(self, raw):
                reply = r.json.loads(raw)
                replies.append(reply)
                if "reference_transition" in reply:
                    raise Observed
                return len(raw)

            def recvmsg(self, *args):
                packet = packets.pop(0)
                sender = 999 if fault == "foreign" and packet["op"] == "observe" else 502
                return r.raw_json(packet), [(1, 2, struct.pack("3i", sender, 0, 0))], 0, None

        monkeypatch.setattr(
            r,
            "os",
            NS(
                **{
                    **vars(r.os),
                    "fstat": lambda fd: NS(st_dev=1, st_ino=99, st_mode=stat.S_IFSOCK, st_uid=0),
                }
            ),
        )
        monkeypatch.setattr(
            r,
            "socket",
            NS(
                SOL_SOCKET=1,
                SO_PASSCRED=3,
                SOCK_SEQPACKET=5,
                SCM_CREDENTIALS=2,
                CMSG_SPACE=lambda n: n,
            ),
        )
        channel = r._Channel(Socket())
        scope = NS(
            pid=502,
            pidfd=100,
            check_pid=lambda: None,
            check_resources=lambda: None,
            verify_manager=lambda: None,
        )
        checks = []
        monitor = NS(
            next=105,
            last={},
            sample=lambda: None,
            peer=lambda pid: None,
            verify_network=lambda scope: checks.append("network"),
        )
        monkeypatch.setattr(r, "_Provider", lambda *a, **k: monitor)
        monkeypatch.setattr(r, "_child_kernel", lambda *a, **k: {"namespace_inode": 44})
        monkeypatch.setattr(r, "_authorize", lambda *a: ({}, {}))
        monkeypatch.setattr(r, "select", NS(select=lambda *a: ([channel.s], [], [])))
        if fault == "lease":
            case.fixture_stack.enter_context(
                patch.object(r.Path, "open", lambda *a, **k: io.BytesIO(b"pos:\t0\n"))
            )
        values = dict(
            _recovery_mode=attempt,
            _recovery_ledger=book,
            _recovery_method=value["method_sha256"],
            catalog_ref=dict(python_sha256="b" * 64, provider_binding={}),
        )
        plan = dict(started_monotonic=100, reference_pair_ref=dict(sha256=pair_sha))
        if fault == "reference_mode":
            plan["reference_init_ref"] = {}
        with pytest.raises(Observed if fault is None else ValueError):
            r._supervise(
                scope, channel, 700, ({"budget_ref": {}}, values, None, None, None, None), plan
            )
        assert (len([v for v in replies if "reference_transition" in v]) == 1) == (fault is None)
        assert attempt + ".may.json" not in book.rows
        if fault is None:
            assert checks == ["network", "network"]
            assert replies[-1]["reference_transition"]["pair_sha256"] == pair_sha
    finally:
        case.doCleanups()
        assert Path.open is original_open
