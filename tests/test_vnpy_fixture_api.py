from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.api.vnpy_fixture import create_vnpy_fixture_router
from quantmesh.research.vnpy_fixture import FixtureManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)
    app = FastAPI()
    app.include_router(create_vnpy_fixture_router(manager), prefix="/api")
    with TestClient(app) as client:
        yield client
    manager.close()


BASE = "/api/research/vnpy-fixture"


def test_options_submit_progress_cancel(client):
    assert len(client.get(BASE + "/options").json()["strategies"]) == 2
    headers = {"Idempotency-Key": str(uuid4())}
    response = client.post(BASE + "/jobs", json={}, headers=headers)
    assert response.status_code == 202
    job = response.json()
    assert job["state"] == "queued"
    assert client.post(BASE + "/jobs", json={}, headers=headers).json() == job
    assert client.get(BASE + "/jobs/" + job["job_id"]).json() == job
    assert client.post(BASE + "/jobs/" + job["job_id"] + "/cancel").json()["state"] == "cancelled"
    assert client.get(BASE + "/jobs/" + job["job_id"] + "/report").status_code == 409


def test_validation_conflict_capacity_and_private_errors(client):
    assert client.post(BASE + "/jobs", json={}).status_code == 422
    assert (
        client.post(BASE + "/jobs", json={}, headers={"Idempotency-Key": "bad"}).status_code == 422
    )
    key = {"Idempotency-Key": str(uuid4())}
    assert client.post(BASE + "/jobs", json={"python": "secret"}, headers=key).status_code == 422
    assert client.post(BASE + "/jobs", json={}, headers=key).status_code == 202
    assert (
        client.post(BASE + "/jobs", json={"strategy_id": "AtrRsiStrategy"}, headers=key).status_code
        == 409
    )
    assert (
        client.post(BASE + "/jobs", json={}, headers={"Idempotency-Key": str(uuid4())}).status_code
        == 409
    )
    missing = client.get(BASE + "/jobs/" + str(uuid4()))
    assert missing.status_code == 404
    assert missing.json() == {"detail": "job_unknown"}


def test_unconfigured_fails_closed():
    app = FastAPI()
    app.include_router(create_vnpy_fixture_router(None), prefix="/api")
    with TestClient(app) as client:
        assert client.get(BASE + "/options").status_code == 503
