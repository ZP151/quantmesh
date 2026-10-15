"""Metadata-only boundary trace. Never persist prompts, responses or credentials."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from ipaddress import ip_address
from pathlib import Path

import pytest

EVENTS: list[dict] = []
REPORTS: list[dict] = []
PATCH = pytest.MonkeyPatch()
CURRENT_NODE = None
COLLECTED: list[str] | None = None


def flush_trace(*, exit_code=None):
    path = os.environ.get("QUANTMESH_EVAL_TRACE")
    if path:
        Path(path).write_text(
            json.dumps(
                {
                    "reports": REPORTS,
                    "events": EVENTS,
                    "exit_code": exit_code,
                    "incomplete": exit_code is None,
                    "collected_nodeids": COLLECTED,
                    "imported_plugin": str(Path(__file__).resolve()),
                    "imported_source": str(Path(sys.modules["quantmesh"].__file__).resolve()),
                    "instrumentation": "ModelGateway completions + ToolRegistry.dispatch",
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def pytest_configure(config):
    import quantmesh
    from quantmesh.ai.gateway import ModelGateway
    from quantmesh.ai.tools import ToolRegistry
    from quantmesh.ai.transport import HttpModelTransport

    expected = os.environ.get("QUANTMESH_EVAL_REPO")
    if expected and not Path(quantmesh.__file__).resolve().is_relative_to(Path(expected) / "src"):
        raise pytest.UsageError("eval imported quantmesh from the wrong checkout")

    def instrument(cls, name, kind):
        original = getattr(cls, name)

        def wrapped(self, *args, **kwargs):
            start = time.perf_counter()
            event = {
                "sequence": len(EVENTS),
                "kind": kind,
                "boundary": cls.__name__,
                "outcome": "ok",
                "nodeid": CURRENT_NODE,
                "method": name,
            }
            if kind == "model":
                event["transport"] = type(self._transport).__name__
            EVENTS.append(event)
            try:
                return original(self, *args, **kwargs)
            except Exception as exc:
                event.update(outcome="error", error_type=type(exc).__name__)
                raise
            finally:
                event["duration_seconds"] = time.perf_counter() - start

        PATCH.setattr(cls, name, wrapped)

    def no_network(*args, **kwargs):
        raise RuntimeError("offline eval forbids network/model HTTP")

    PATCH.setattr(HttpModelTransport, "complete", no_network)
    # Windows asyncio builds its socketpair over loopback. Permit local IPC,
    # refuse external TCP; this is not an arbitrary-code sandbox.
    for name in ("connect", "connect_ex"):
        original = getattr(socket.socket, name)

        def guarded(self, address, _original=original):
            try:
                local = isinstance(address, tuple) and ip_address(address[0]).is_loopback
            except ValueError:
                local = False
            if not local:
                return no_network()
            return _original(self, address)

        PATCH.setattr(socket.socket, name, guarded)
    instrument(ModelGateway, "complete", "model")
    instrument(ModelGateway, "complete_structured", "model")
    instrument(ToolRegistry, "dispatch", "tool")
    if os.environ.get("QUANTMESH_EVAL_INJECT_BAD") == "1":
        # A fault at the independent verifier boundary. Never mutate production bytes.
        def broken_verifier():
            assert False, "injected known-bad verifier must remain a real failure"

        PATCH.setattr(sys.modules[__name__], "_injected_check", broken_verifier)
    flush_trace()


def _injected_check():
    pass


def pytest_runtest_call(item):
    _injected_check()


def pytest_runtest_setup(item):
    global CURRENT_NODE
    CURRENT_NODE = item.nodeid


def pytest_collection_finish(session):
    global COLLECTED
    COLLECTED = [item.nodeid for item in session.items]
    flush_trace()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    from quantmesh.ai.redact import redact_context

    report = (yield).get_result()
    if call.excinfo:
        cleaned, _ = redact_context({"failure": str(call.excinfo.value)[:4000]})
        report.eval_failure = {"type": call.excinfo.typename, "message": cleaned["failure"]}


def pytest_runtest_logreport(report):
    REPORTS.append(
        {
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "duration_seconds": report.duration,
            "location": list(report.location),
            "wasxfail": bool(getattr(report, "wasxfail", False)),
            "failure": getattr(report, "eval_failure", None),
        }
    )
    flush_trace()


def pytest_collectreport(report):
    if report.failed:
        REPORTS.append({"nodeid": report.nodeid, "when": "collection", "outcome": "failed"})
        flush_trace()


def pytest_sessionfinish(session, exitstatus):
    flush_trace(exit_code=int(exitstatus))


def pytest_unconfigure(config):
    PATCH.undo()
