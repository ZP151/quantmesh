"""Small synthetic controls for the release-only pytest profiler."""

import json
import sys
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest

from tools import ci_profile_plugin


def test_profile_call_restores_calendar_and_keeps_distinct_argument_digests() -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            return (calendar_id, start, end, policy)

    original = Calendar.sessions
    with ci_profile_plugin.profile_call(Calendar) as capture:
        calendar = Calendar()
        for _ in range(2):
            assert calendar.sessions("XNYS", date(2025, 1, 2), date(2025, 1, 3), policy="regular")
        assert calendar.sessions("XNYS", date(2025, 1, 3), date(2025, 1, 3), policy="regular")

    assert Calendar.sessions is original
    summary = capture.summary("synthetic")
    assert summary["calendar_calls"] == 3
    assert summary["calendar_unique_arguments"] == 2
    assert sorted(row["calls"] for row in summary["calendar_arguments"]) == [1, 2]
    assert all(len(row["sha256"]) == 64 for row in summary["calendar_arguments"])
    assert "2025" not in json.dumps(summary)
    assert summary["functions"]


def test_profile_call_restores_calendar_when_test_raises() -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            raise RuntimeError("original failure")

    original = Calendar.sessions
    with pytest.raises(RuntimeError, match="original failure"):
        with ci_profile_plugin.profile_call(Calendar) as capture:
            Calendar().sessions("XNYS", date(2025, 1, 2), date(2025, 1, 2), policy="regular")

    assert Calendar.sessions is original
    assert capture.summary("synthetic")["calendar_calls"] == 1


def test_profile_summary_is_bounded_and_redacts_function_paths() -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            return None

    with ci_profile_plugin.profile_call(Calendar) as capture:
        for day in range(1, 20):
            Calendar().sessions("XNYS", date(2025, 1, day), date(2025, 1, day), policy="regular")

    summary = capture.summary("synthetic")
    assert len(summary["calendar_arguments"]) <= ci_profile_plugin.MAX_ROWS
    assert len(summary["functions"]) <= ci_profile_plugin.MAX_ROWS
    assert summary["calendar_unique_arguments"] == 19
    assert "C:\\" not in json.dumps(summary)
    assert "/Users/" not in json.dumps(summary)


def test_release_profiler_targets_only_fixed_nodes() -> None:
    assert ci_profile_plugin.TARGETS == frozenset(
        {
            "tests/test_packet_reviews.py::test_risk_refusal_and_operator_invoked_watch_coverage_remain_exact",
            "tests/test_decision_session_e2e.py::test_nvda_aapl_refresh_is_bounded_and_exact_results_survive_reconstruction",
        }
    )


def test_hook_emits_one_bounded_line_for_selected_call(monkeypatch) -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            return (start, end)

    fake_module = ModuleType("quantmesh.data.calendars")
    fake_module.CalendarService = Calendar
    fake_module.XNYS_REGULAR_VERSION = "pinned-xnys"
    fake_module.CONTINUOUS_UTC_VERSION = "pinned-continuous"
    monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)
    lines = []
    reporter = SimpleNamespace(write_line=lines.append)
    manager = SimpleNamespace(
        get_plugin=lambda name: reporter if name == "terminalreporter" else None
    )
    item = SimpleNamespace(
        nodeid=next(iter(ci_profile_plugin.TARGETS)),
        config=SimpleNamespace(pluginmanager=manager),
    )

    call = ci_profile_plugin.pytest_runtest_call(item)
    next(call)
    assert Calendar().sessions("XNYS", date(2025, 1, 2), date(2025, 1, 2), policy="regular")
    with pytest.raises(StopIteration):
        next(call)

    assert len(lines) == 1
    assert lines[0].startswith("CI_PROFILE ")
    summary = json.loads(lines[0].removeprefix("CI_PROFILE "))
    assert summary["nodeid"] == item.nodeid
    assert summary["calendar_calls"] == 1
