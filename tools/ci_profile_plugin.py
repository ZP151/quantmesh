"""Bounded pytest failure/progress evidence and profiles for two existing slow nodes.

The cProfile table covers the pytest call thread only. Calendar wall time is
captured across worker threads, so its totals and profiler cumulative times
can overlap; neither should be summed as elapsed time.
"""

import cProfile
import hashlib
import json
import os
import platform
import pstats
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date
from enum import StrEnum
from functools import wraps
from pathlib import Path
from threading import Lock

import pytest

TARGETS = frozenset(
    {
        "tests/test_packet_reviews.py::test_risk_refusal_and_operator_invoked_watch_coverage_remain_exact",
        "tests/test_decision_session_e2e.py::test_nvda_aapl_refresh_is_bounded_and_exact_results_survive_reconstruction",
    }
)
MAX_ROWS = 12
MAX_DIGESTS = 256
MAX_FEEDBACK_EVENTS = 256


def pytest_addoption(parser):
    group = parser.getgroup("ci-feedback")
    group.addoption("--ci-events", help="unique JSONL evidence file for this pytest process")
    group.addoption(
        "--ci-log", default="pytest.log", help="ordinary pytest assertion log reference"
    )
    group.addoption(
        "--ci-contract", action="store_true", help="require release bootstrap collection"
    )


def pytest_configure(config):
    if config.getoption("ci_events"):
        config.pluginmanager.register(_Feedback(config), "quantmesh-ci-feedback")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if config.getoption("ci_contract"):
        from tools.quality_gate import check_contract_collection

        try:
            check_contract_collection(item.nodeid for item in items)
        except ValueError as error:
            raise pytest.UsageError(str(error)) from error


def _file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class _Feedback:
    """Sparse finite metadata; assertions stay in the ordinary captured pytest log."""

    def __init__(self, config):
        self.config = config
        self.path = Path(config.getoption("ci_events"))
        self.log = Path(config.getoption("ci_log")).name
        self.stream = None
        self.completed = 0
        self.collected = 0
        self.events = 0
        self.first_failure = False
        self.failed = False
        self.last_progress = float("-inf")
        self.started = time.monotonic()
        self.durations = dict.fromkeys(("setup", "call", "teardown", "collection"), 0.0)

    def emit(self, event, **fields):
        try:
            row = {
                "schema": "qm.ci.pytest-feedback.v1",
                "event": event,
                "elapsed_seconds": round(time.monotonic() - self.started, 6),
                "log": self.log,
                "artifact": self.path.name,
                **fields,
            }
            encoded = json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n"
            if len(encoded.encode()) > 8192:
                raise ValueError("event bound")
            self.stream.write(encoded)
            self.stream.flush()
            self.events += 1
        except Exception:
            self.failed = True
            # Fixed text cannot leak the diagnostic exception's paths or payload.
            sys.stderr.write("CI_FEEDBACK_ERROR: evidence write failed\n")

    def pytest_sessionstart(self, session):
        try:
            self.stream = self.path.open("x", encoding="utf-8", newline="\n")
            root = Path(__file__).resolve().parents[1]

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)

            identity = {
                "commit": git("rev-parse", "HEAD").decode().strip(),
                "tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
                "tracked_diff_sha256": hashlib.sha256(git("diff", "--binary", "HEAD")).hexdigest(),
                "plugin_sha256": _file_digest(__file__),
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "platform": sys.platform,
                "pytest_version": pytest.__version__,
                "executable_sha256": _file_digest(sys.executable),
            }
            self.emit("session_started", identity=identity)
        except Exception:
            self.failed = True
            sys.stderr.write("CI_FEEDBACK_ERROR: evidence identity unavailable\n")

    def pytest_collection_finish(self, session):
        nodes = [item.nodeid for item in session.items]
        self.collected = len(nodes)
        sources = sorted(_file_digest(path) for path in {item.path for item in session.items})
        self.emit(
            "collection_finished",
            collected=self.collected,
            collection_sha256=hashlib.sha256("\n".join(nodes).encode()).hexdigest(),
            test_sources_sha256=hashlib.sha256("\n".join(sources).encode()).hexdigest(),
        )

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection(self, session):
        started = time.monotonic()
        yield
        self.durations["collection"] = time.monotonic() - started

    def phase(self, item, phase):
        self.current(item.nodeid, phase, "active")
        now = time.monotonic()
        if now - self.last_progress >= 30 and self.events < MAX_FEEDBACK_EVENTS - 3:
            self.emit(
                "active",
                nodeid=item.nodeid,
                phase=phase,
                completed=self.completed,
                collected=self.collected,
            )
            self.last_progress = now

    def current(self, nodeid, phase, state):
        if self.failed:
            return
        try:
            value = {
                "schema": "qm.ci.pytest-current.v1",
                "nodeid": nodeid,
                "phase": phase,
                "state": state,
                "completed": self.completed,
                "collected": self.collected,
                "artifact": self.path.name,
                "elapsed_seconds": round(time.monotonic() - self.started, 6),
            }
            encoded = json.dumps(value, sort_keys=True, ensure_ascii=True) + "\n"
            if len(encoded.encode()) > 8192:
                raise ValueError("current node bound")
            temporary = self.path.with_suffix(".current.tmp")
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(self.path.with_suffix(".current.json"))
        except Exception:
            self.failed = True
            sys.stderr.write("CI_FEEDBACK_ERROR: current node evidence failed\n")

    def pytest_runtest_setup(self, item):
        self.phase(item, "setup")

    def pytest_runtest_call(self, item):
        self.phase(item, "call")

    def pytest_runtest_teardown(self, item):
        self.phase(item, "teardown")

    def report(self, report, phase):
        duration = getattr(report, "duration", None)
        if duration is not None and phase != "collection":
            self.durations[phase] += duration
        if report.failed and not self.first_failure:
            self.first_failure = True
            crash = getattr(report.longrepr, "reprcrash", None)
            self.emit(
                "first_failure",
                nodeid=report.nodeid,
                phase=phase,
                outcome="failed",
                duration_seconds=round(duration, 6) if duration is not None else None,
                assertion_line=getattr(crash, "lineno", None),
                completed=self.completed,
                collected=self.collected,
            )

    def pytest_runtest_logreport(self, report):
        self.report(report, report.when)
        if report.when == "teardown":
            self.completed += 1
            self.current(report.nodeid, report.when, "completed")

    def pytest_collectreport(self, report):
        self.report(report, "collection")

    def pytest_sessionfinish(self, session, exitstatus):
        self.emit(
            "session_finished",
            exit_code=int(exitstatus),
            completed=self.completed,
            collected=self.collected,
            durations={key: round(value, 6) for key, value in self.durations.items()},
            progress_truncated=self.events >= MAX_FEEDBACK_EVENTS - 3,
            diagnostic_failed=self.failed,
        )
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                self.failed = True
                sys.stderr.write("CI_FEEDBACK_ERROR: evidence close failed\n")
        if self.failed and session.exitstatus == 0:
            session.exitstatus = pytest.ExitCode.INTERNAL_ERROR


def _digest(calendar_id, start, end, policy, versions):
    """Hash only expected immutable calendar inputs; never log their values."""
    if type(calendar_id) is not str or type(start) is not date or type(end) is not date:
        raise TypeError("calendar identity has unexpected types")
    if type(policy) is str:
        policy_value = policy
    elif isinstance(policy, StrEnum):
        policy_value = policy.value
    else:
        raise TypeError("calendar policy has unexpected type")
    identity = (
        calendar_id,
        start.isoformat(),
        end.isoformat(),
        policy_value,
        versions.get(calendar_id, "unknown"),
    )
    encoded = json.dumps(identity, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class _Capture:
    def __init__(self):
        self.profiler = cProfile.Profile()
        self.lock = Lock()
        self.calendar_arguments = Counter()
        self.calendar_calls = 0
        self.calendar_wall_seconds = 0.0
        self.identity_errors = 0
        self.overflow_calls = 0

    def record(self, digest, elapsed):
        with self.lock:
            self.calendar_calls += 1
            self.calendar_wall_seconds += elapsed
            if digest is None:
                self.identity_errors += 1
            elif digest in self.calendar_arguments or len(self.calendar_arguments) < MAX_DIGESTS:
                self.calendar_arguments[digest] += 1
            else:
                self.overflow_calls += 1

    def summary(self, nodeid):
        stats = pstats.Stats(self.profiler).stats
        functions = sorted(stats.items(), key=lambda row: row[1][3], reverse=True)[:MAX_ROWS]
        with self.lock:
            arguments = self.calendar_arguments.most_common(MAX_ROWS)
            return {
                "nodeid": nodeid,
                "scope": "pytest-call-thread-cprofile; calendar-wrapper-all-threads",
                "timing_note": "cumulative times overlap; profiler and wrapper add overhead",
                "functions": [
                    {
                        "function": f"{os.path.basename(key[0])}:{key[1]}:{key[2]}",
                        "calls": value[1],
                        "cumulative_seconds": round(value[3], 6),
                    }
                    for key, value in functions
                ],
                "calendar_calls": self.calendar_calls,
                "calendar_wall_seconds": round(self.calendar_wall_seconds, 6),
                "calendar_unique_arguments": len(self.calendar_arguments),
                "calendar_arguments": [
                    {"sha256": digest, "calls": calls} for digest, calls in arguments
                ],
                "calendar_identity_errors": self.identity_errors,
                "calendar_overflow_calls": self.overflow_calls,
            }


@contextmanager
def profile_call(calendar_class, versions=None):
    """Profile one call phase and restore the original calendar method on exit."""
    capture = _Capture()
    original = calendar_class.sessions
    versions = versions or {}

    @wraps(original)
    def observed(self, calendar_id, start, end, *, policy):
        digest = None
        try:
            digest = _digest(calendar_id, start, end, policy, versions)
        except Exception:  # Diagnostics cannot alter validation or refusal behavior.
            pass
        started = time.perf_counter()
        try:
            return original(self, calendar_id, start, end, policy=policy)
        finally:
            capture.record(digest, time.perf_counter() - started)

    capture.profiler.enable()
    try:
        calendar_class.sessions = observed
        try:
            yield capture
        finally:
            calendar_class.sessions = original
    finally:
        capture.profiler.disable()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.nodeid not in TARGETS:
        yield
        return

    from quantmesh.data.calendars import (
        CONTINUOUS_UTC_VERSION,
        XNYS_REGULAR_VERSION,
        CalendarService,
    )

    versions = {"XNYS": XNYS_REGULAR_VERSION, "24/7": CONTINUOUS_UTC_VERSION}
    with profile_call(CalendarService, versions) as capture:
        yield
    reporter = item.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            "CI_PROFILE " + json.dumps(capture.summary(item.nodeid), sort_keys=True)
        )
