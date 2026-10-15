"""Explicit external-runtime acceptance; never installs vn.py into core dependencies."""

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.api.vnpy_fixture import create_vnpy_fixture_router
from quantmesh.research.vnpy_fixture import FixtureManager


def test_actual_official_engine_two_strategies_repeat_and_costs(tmp_path):
    runtime = os.environ.get("QUANTMESH_VNPY_PYTHON")
    fixture = os.environ.get("QUANTMESH_VNPY_FIXTURE")
    if not runtime or not fixture:
        pytest.skip("explicit external native runtime required")
    root = Path(os.environ.get("QUANTMESH_VNPY_EVIDENCE", str(tmp_path)))
    manager = FixtureManager(Path(runtime), Path(fixture), root)
    app = FastAPI()
    app.include_router(create_vnpy_fixture_router(manager), prefix="/api")
    reports = []
    prefix = "/api/research/vnpy-fixture/jobs"
    try:
        with TestClient(app) as client:
            for request in [
                {},
                {},
                {"costs": {"fee_bps": 10, "half_spread_price": 0.01, "slippage_price": 0.01}},
                {"strategy_id": "AtrRsiStrategy"},
            ]:
                response = client.post(
                    prefix, json=request, headers={"Idempotency-Key": str(uuid4())}
                )
                assert response.status_code == 202, response.text
                job = response.json()
                deadline = time.monotonic() + 125
                while job["state"] in {"queued", "running"} and time.monotonic() < deadline:
                    time.sleep(0.1)
                    job = client.get(prefix + "/" + job["job_id"]).json()
                assert job["state"] == "succeeded", job
                envelope = client.get(prefix + "/" + job["job_id"] + "/report").json()
                assert hashlib.sha256(envelope["text"].encode()).hexdigest() == envelope["sha256"]
                report = json.loads(envelope["text"])
                assert report["lifecycle"]["replay_bars"] == 1950
                assert report["lifecycle"]["warmup_bars"] == 2340
                assert len(report["daily"]) == 5
                assert report["lifecycle"]["on_init"] == 1
                assert report["lifecycle"]["on_start"] == 1
                assert report["lifecycle"]["on_stop"] == 1
                reports.append(envelope)
        assert reports[0]["sha256"] == reports[1]["sha256"]
        baseline, cost2, atr = [json.loads(reports[index]["text"]) for index in (0, 2, 3)]
        assert len(baseline["trades"]) == 31
        assert baseline["statistics"]["end_balance"] == pytest.approx(100045.48285)
        assert cost2["statistics"]["end_balance"] < baseline["statistics"]["end_balance"]
        assert cost2["request_digest"] != baseline["request_digest"]
        assert atr["request"]["strategy_id"] == "AtrRsiStrategy"
        (root / "native-acceptance.json").write_text(
            json.dumps(
                {
                    "reports": [
                        {"sha256": r["sha256"], "request_digest": r["request_digest"]}
                        for r in reports
                    ],
                    "repeat_identical": True,
                    "doubled_costs_adverse": True,
                    "baseline_end_balance": baseline["statistics"]["end_balance"],
                    "double_cost_end_balance": cost2["statistics"]["end_balance"],
                    "atr_trades": len(atr["trades"]),
                },
                indent=2,
            )
        )
    finally:
        manager.close()
