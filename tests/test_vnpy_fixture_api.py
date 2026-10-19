from contextlib import asynccontextmanager
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


@pytest.fixture
def manager(tmp_path, monkeypatch):
    # Keep the real manager/store behavior; only external admission and child spawn are replaced.
    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)
    yield manager
    manager.close()


def test_standalone_workstation_guards_fixture_writes_before_mutation(manager):
    from quantmesh.api.vnpy_fixture import create_fixture_app

    key = str(uuid4())
    with TestClient(create_fixture_app(manager)) as client:
        headers = {"Idempotency-Key": key, "Origin": "https://attacker.invalid"}
        assert client.post(BASE + "/jobs", json={}, headers=headers).status_code == 403
        headers["Origin"] = "http://127.0.0.1:8765"
        accepted = client.post(BASE + "/jobs", json={}, headers=headers)
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]
        headers["Origin"] = "https://attacker.invalid"
        assert client.post(BASE + f"/jobs/{job_id}/cancel", headers=headers).status_code == 403
        assert client.get(BASE + f"/jobs/{job_id}").json()["state"] == "queued"
        headers["Origin"] = "http://localhost:8765"
        assert (
            client.post(BASE + f"/jobs/{job_id}/cancel", headers=headers).json()["state"]
            == "cancelled"
        )


@pytest.mark.parametrize("failure", [None, "startup", "shutdown"])
def test_attachment_preserves_lifespan_and_closes_manager_on_failure(manager, monkeypatch, failure):
    import quantmesh.api.vnpy_fixture as fixture_api

    events = []
    original_close = manager.close

    def close():
        events.append("fixture-close")
        original_close()

    monkeypatch.setattr(manager, "close", close)

    @asynccontextmanager
    async def lifespan(app):
        events.append("existing-enter")
        if failure == "startup":
            raise RuntimeError("startup failed")
        try:
            yield
        finally:
            events.append("existing-exit")
            if failure == "shutdown":
                raise RuntimeError("shutdown failed")

    app = FastAPI(lifespan=lifespan)
    fixture_api.attach_fixture_runtime(app, manager)

    def visit():
        with TestClient(app) as client:
            assert client.get(BASE + "/options").status_code == 200

    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            visit()
    else:
        visit()
    expected = (
        ["existing-enter", "fixture-close"]
        if failure == "startup"
        else ["existing-enter", "existing-exit", "fixture-close"]
    )
    assert events == expected
    with pytest.raises(ValueError, match="service_closed"):
        from quantmesh.research.vnpy_fixture import FixtureRequest

        manager.submit(FixtureRequest(), str(uuid4()))
