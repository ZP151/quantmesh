"""Fixed-case workstation API: complete parity, bounded inputs and no authority."""

import importlib
import importlib.util
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tools import run_trend_overlay_candidate as cli


def client():
    assert importlib.util.find_spec("quantmesh.api.trend_overlay") is not None, (
        "fixed-case API not implemented"
    )
    module = importlib.import_module("quantmesh.api.trend_overlay")
    app = FastAPI()
    app.include_router(module.trend_overlay_router(), prefix="/api")
    return TestClient(app)


@pytest.mark.parametrize("case", cli.CASES)
def test_all_cases_equal_complete_cli_trace_and_remain_bounded(case):
    response = client().get(f"/api/research/trend-overlay/{case}")
    assert response.status_code == 200
    assert response.json() == cli.build_trace(case)
    assert response.content == cli._canonical(cli.build_trace(case))
    assert len(response.content) < 100_000
    assert response.json()["evidence_kind"] == "synthetic_policy_trace"
    assert not {"returns", "pnl", "paper_allowed", "equity"} & response.json().keys()
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("case", ["arbitrary.csv", "python", "CAMPAIGN", "unknown"])
def test_unregistered_cases_never_return_trace(case):
    response = client().get(f"/api/research/trend-overlay/{case}")
    assert response.status_code == 422
    assert "arms" not in response.json()


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_write_method(method):
    response = getattr(client(), method)("/api/research/trend-overlay/campaign")
    assert response.status_code == 405


def test_query_and_body_are_refused_not_silently_accepted():
    api = client()
    for response in (
        api.get("/api/research/trend-overlay/campaign?input=evil.py"),
        api.request("GET", "/api/research/trend-overlay/campaign", content=b"{}"),
    ):
        assert response.status_code == 400
        assert "arms" not in response.json()


def test_repeat_read_and_full_trace_digest():
    import hashlib

    api = client()
    first = api.get("/api/research/trend-overlay/cash-cap")
    second = api.get("/api/research/trend-overlay/cash-cap")
    assert first.content == second.content
    trace = first.json()
    digest = trace.pop("trace_sha256")
    payload = json.dumps(trace, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert hashlib.sha256(payload.encode()).hexdigest() == digest


def test_normal_workstation_mounts_without_optional_research_runtime():
    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount

    app = create_workstation_app(account=PaperAccount(cash=100_000))
    api = TestClient(app)
    assert api.get("/api/research/trend-overlay/campaign").status_code == 200
    assert api.get("/api/health").json()["live_trading"] is False
