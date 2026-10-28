"""R1 regressions: immutable reopen and complete, independently bound children."""

import copy
import json

import pytest

from quantmesh.data.objects import ObjectStore
from quantmesh.research import native_daily_candidate as c


@pytest.fixture(scope="module")
def publication(tmp_path_factory):
    store = ObjectStore(tmp_path_factory.mktemp("archive"))
    value = c.engineering_input()
    ref = c.publish(value, c.freeze_protocol(value), store)
    return store, ref, store.get_bytes(ref)


def test_original_reopen_has_no_current_generator_calendar_or_math_dependency(
    publication, monkeypatch
):
    store, ref, raw = publication

    def forbidden(*args, **kwargs):
        pytest.fail("original reopen invoked current generation/runtime or math")

    monkeypatch.setattr(c, "engineering_input", forbidden)
    monkeypatch.setattr(c, "CalendarService", forbidden)
    monkeypatch.setattr(c, "evaluate", forbidden)
    assert c.read_result(store, ref) == raw


@pytest.mark.parametrize(
    "missing",
    [
        "calculation",
        "scenario",
        "arm",
        "metrics",
        "daily",
        "trace_record",
        "trade_record",
        "metrics_field",
        "numeric_type",
    ],
)
def test_incomplete_matrix_cannot_reopen_as_success(publication, missing):
    store, _, raw = publication
    body = json.loads(raw)
    if missing == "calculation":
        del body["calculation"]
    elif missing == "scenario":
        del body["calculation"]["stress10"]
    elif missing == "arm":
        del body["calculation"]["base5"]["TO"]
    elif missing == "metrics":
        del body["calculation"]["base5"]["TO"]["metrics"]
    elif missing == "daily":
        body["calculation"]["base5"]["TO"]["daily"].pop()
    elif missing == "trace_record":
        del body["calculation"]["base5"]["TO"]["trace"][1]["filled"]
    elif missing == "trade_record":
        del body["calculation"]["base5"]["TO"]["trades"][0]["friction"]
    elif missing == "metrics_field":
        del body["calculation"]["base5"]["TO"]["metrics"]["friction_usd"]
    else:
        body["calculation"]["base5"]["TO"]["metrics"]["terminal_shares"] = False
    ref = store.put_bytes("application/json", c.canonical(body))
    with pytest.raises(c.CandidateError, match="artifact_invalid"):
        c.read_result(store, ref)


def test_children_have_distinct_bound_parent_arm_and_cost_identities(publication):
    _, _, raw = publication
    body = json.loads(raw)
    ids = set()
    for scenario, bps in (("base5", 5), ("stress10", 10)):
        for arm in c.ARMS:
            row = body["calculation"][scenario][arm]
            assert row["binding"]["request_digest"] == body["request_digest"]
            assert row["binding"]["arm"] == arm
            assert row["binding"]["cost_bps"] == bps
            assert row["child_id"] not in ids
            ids.add(row["child_id"])
    assert len(ids) == 10


def test_swapped_cost_children_cannot_reopen_as_correctly_bound(publication):
    store, _, raw = publication
    body = json.loads(raw)
    base = copy.deepcopy(body["calculation"]["base5"]["TO"])
    body["calculation"]["base5"]["TO"] = body["calculation"]["stress10"]["TO"]
    body["calculation"]["stress10"]["TO"] = base
    ref = store.put_bytes("application/json", c.canonical(body))
    with pytest.raises(c.CandidateError, match="artifact_invalid"):
        c.read_result(store, ref)


@pytest.mark.parametrize("change", ["empty", "truncated", "reordered", "other_fill"])
def test_trade_ledger_must_match_metrics_and_recorded_actual_trace_fills(publication, change):
    store, _, raw = publication
    body = json.loads(raw)
    arm = body["calculation"]["base5"]["TO"]
    if change == "empty":
        arm["trades"] = []
    elif change == "truncated":
        arm["trades"].pop()
    elif change == "reordered":
        arm["trades"].reverse()
    else:
        arm["trades"][0]["quantity"] += 1
    ref = store.put_bytes("application/json", c.canonical(body))
    with pytest.raises(c.CandidateError, match="artifact_invalid"):
        c.read_result(store, ref)
