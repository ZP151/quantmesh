from conftest import publish
from fastapi.testclient import TestClient
from pydantic import SecretStr
from qm_research_agent.app import create_app
from test_research_jobs import request_for


def test_auth_identity_and_artifact_access(local):
    store, lake, _ = local
    app = create_app(
        store,
        operator_id="operator",
        token=SecretStr("fixture-private-token"),
        configured_dataset_ids=("equities",),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer fixture-private-token", "Idempotency-Key": "same"}
    req = request_for(lake).model_dump(mode="json")
    assert client.get("/health").status_code == 401
    assert client.post("/v1/jobs", json=req).status_code == 401
    assert (
        client.post("/v1/jobs", headers=headers, json={**req, "operator_id": "other"}).status_code
        == 422
    )
    response = client.post("/v1/jobs", headers=headers, json=req)
    assert response.status_code == 200
    job = store.get("operator", response.json()["job_id"])
    assert client.post("/v1/jobs", headers=headers, json=req).json()["job_id"] == job.job_id
    changed = {**req, "analysis_requested": True}
    assert client.post("/v1/jobs", headers=headers, json=changed).status_code == 409
    report = publish(store, job)
    url = f"/v1/jobs/{job.job_id}/artifacts/{report.artifact_id}"
    assert (
        client.get(url, headers=headers).content
        == (store.artifact_root / report.object_key).read_bytes()
    )
    (store.artifact_root / report.object_key).write_bytes(b"changed")
    assert client.get(url, headers=headers).status_code == 409
    assert client.get("/v1/jobs/unknown", headers=headers).status_code == 404
    assert (
        client.post(f"/v1/jobs/{job.job_id}/cancel", headers=headers).json()["state"] == "succeeded"
    )
