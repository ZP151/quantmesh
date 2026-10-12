"""The mounted workstation preserves availability and browser write guards."""

from fastapi.testclient import TestClient
from test_research_jobs import request_for

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.research.job_store import SQLiteJobStore
from tests.research_fixtures import pinned_lake


def test_unbound_research_is_explicitly_unavailable_without_breaking_markets():
    client = TestClient(create_workstation_app(account=PaperAccount(cash=100_000)))
    response = client.get("/api/research/job-options")
    assert response.status_code == 503
    assert response.json() == {"detail": "service_unavailable"}
    assert client.get("/api/markets").status_code == 200


def test_research_mutations_use_the_workstation_origin_guard(tmp_path):
    from quantmesh.research.service_client import LocalResearchClient

    lake = tmp_path / "lake"
    pinned_lake(lake)
    store = SQLiteJobStore(tmp_path / "jobs.sqlite", lake_root=lake)
    authority = LocalResearchClient(
        store, operator_id="operator", lake_root=lake, configured_dataset_ids=("equities",)
    )
    client = TestClient(
        create_workstation_app(account=PaperAccount(cash=100_000), research_jobs_client=authority)
    )
    request = request_for(lake).model_dump(mode="json")
    headers = {"Idempotency-Key": "one", "Origin": "https://127.attacker.invalid"}
    assert client.post("/api/research/jobs", json=request, headers=headers).status_code == 403
    headers["Origin"] = "http://localhost:8000"
    submitted = client.post("/api/research/jobs", json=request, headers=headers)
    assert submitted.status_code == 200
    job_id = submitted.json()["job_id"]
    assert store.get("operator", job_id).state == "queued"
    headers["Origin"] = "https://127.attacker.invalid"
    assert client.post(f"/api/research/jobs/{job_id}/cancel", headers=headers).status_code == 403
    assert store.get("operator", job_id).state == "queued"
    headers["Origin"] = "http://localhost:8000"
    assert client.post(f"/api/research/jobs/{job_id}/cancel", headers=headers).status_code == 200
    assert store.get("operator", job_id).state == "cancelled"
