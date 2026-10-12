"""Options use server-owned fixture inputs and the same private authentication."""

from fastapi.testclient import TestClient
from pydantic import SecretStr
from qm_research_agent.app import create_app
from test_research_jobs import request_for

HEADERS = {"Authorization": "Bearer fixture-private-token"}


def test_options_without_configured_inputs_cannot_enable_submission(local):
    store, _, _ = local
    client = TestClient(
        create_app(store, operator_id="operator", token=SecretStr("fixture-private-token"))
    )
    assert client.get("/v1/options").status_code == 401
    response = client.get("/v1/options", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "no_qualified_inputs"
    assert response.json()["datasets"] == []


def test_options_read_only_the_configured_worker_lake(local):
    store, lake, _ = local
    client = TestClient(
        create_app(
            store,
            operator_id="operator",
            token=SecretStr("fixture-private-token"),
            configured_dataset_ids=("equities",),
        )
    )
    response = client.get("/v1/options", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["status"] == "configured"
    assert body["reason"] is None
    assert {s["strategy_id"] for s in body["strategies"]} == {
        "momentum",
        "mean_reversion",
        "risk_parity",
    }
    assert len(body["datasets"]) == 1
    option = body["datasets"][0]
    assert option["dataset"]["dataset_id"] == "equities"
    assert option["dataset"]["permission_class"] == "fixture"
    assert option["minimum_available_bars"] == 60
    assert option["interval"] == "1h"
    assert {m["symbol"] for m in option["universe"]} == {"AAA", "BBB", "CCC"}
    # A query cannot switch the construction-time input root or dataset list.
    queried = client.get("/v1/options?dataset_id=other&lake_root=other", headers=HEADERS)
    assert queried.json() == body
    # Missing source bytes do not remain a cached, falsely qualified choice.
    (lake / "equities" / "manifest.json").rename(lake / "equities" / "manifest.saved")
    unavailable = client.get("/v1/options", headers=HEADERS)
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["datasets"] == []


def test_service_cannot_submit_an_unconfigured_fixture(local):
    store, lake, _ = local
    client = TestClient(
        create_app(store, operator_id="operator", token=SecretStr("fixture-private-token"))
    )
    response = client.post(
        "/v1/jobs",
        headers={**HEADERS, "Idempotency-Key": "unconfigured"},
        json=request_for(lake).model_dump(mode="json"),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "dataset_rejected"}
    assert store.claim("worker", store._clock()) is None


def test_same_key_replay_survives_disappeared_fixture_inputs(local):
    store, lake, _ = local
    client = TestClient(
        create_app(
            store,
            operator_id="operator",
            token=SecretStr("fixture-private-token"),
            configured_dataset_ids=("equities",),
        )
    )
    request = request_for(lake).model_dump(mode="json")
    headers = {**HEADERS, "Idempotency-Key": "accepted"}
    submitted = client.post("/v1/jobs", headers=headers, json=request)
    assert submitted.status_code == 200
    (lake / "equities" / "manifest.json").rename(lake / "equities" / "manifest.saved")
    assert client.get("/v1/options", headers=HEADERS).json()["status"] == "unavailable"
    replay = client.post("/v1/jobs", headers=headers, json=request)
    assert replay.status_code == 200
    assert replay.json()["job_id"] == submitted.json()["job_id"]
    changed = {**request, "analysis_requested": True}
    assert client.post("/v1/jobs", headers=headers, json=changed).status_code == 409
