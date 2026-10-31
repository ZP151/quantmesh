"""Bounded diagnostics for two slow nodes in the existing release pytest run.

The cProfile table covers the pytest call thread only. Calendar wall time is
captured across worker threads, so its totals and profiler cumulative times
can overlap; neither should be summed as elapsed time.
"""

import cProfile
import hashlib
import json
import os
import pstats
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date
from enum import StrEnum
from functools import wraps
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
