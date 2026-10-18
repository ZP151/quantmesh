"""The mounted workstation preserves availability and browser write guards."""

import pytest
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


@pytest.mark.parametrize(
    "flags",
    [
        ["--vnpy-python", "python.exe"],
        ["--vnpy-fixture", "fixture.csv"],
        ["--vnpy-root", "jobs"],
        ["--vnpy-python", "python.exe", "--vnpy-fixture", "fixture.csv"],
        ["--vnpy-python", "python.exe", "--vnpy-root", "jobs"],
        ["--vnpy-fixture", "fixture.csv", "--vnpy-root", "jobs"],
    ],
)
def test_launcher_requires_all_fixture_paths(flags, capsys):
    from quantmesh.api.workstation import main

    with pytest.raises(SystemExit) as raised:
        main(flags)
    assert raised.value.code == 2
    assert (
        "--vnpy-python, --vnpy-fixture and --vnpy-root must be supplied together"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize("demo", [False, True])
def test_launcher_attaches_fixture_to_existing_workstation(tmp_path, monkeypatch, demo):
    from contextlib import asynccontextmanager
    from pathlib import Path
    from uuid import uuid4

    import uvicorn
    from fastapi import FastAPI

    import quantmesh.demo.runtime as demo_runtime
    from quantmesh.api.workstation import main
    from quantmesh.research.vnpy_fixture import FixtureManager

    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    events = []

    @asynccontextmanager
    async def lifespan(app):
        events.append("demo-enter")
        yield
        events.append("demo-exit")

    demo_app = FastAPI(lifespan=lifespan)

    @demo_app.get("/api/demo/status")
    def status():
        return {"seed": 7}

    monkeypatch.setattr(demo_runtime, "create_demo_app", lambda **kwargs: demo_app)

    def serve(app, *, host, port):
        assert host == "127.0.0.1" and port == 8765
        with TestClient(app) as client:
            if demo:
                assert client.get("/api/demo/status").json() == {"seed": 7}
            else:
                assert client.get("/api/markets").status_code == 200
                assert client.get("/api/research/job-options").status_code == 503
            base = "/api/research/vnpy-fixture"
            assert len(client.get(base + "/options").json()["strategies"]) == 2
            headers = {"Idempotency-Key": str(uuid4()), "Origin": "http://localhost:8765"}
            accepted = client.post(base + "/jobs", json={}, headers=headers)
            assert accepted.status_code == 202
            job_id = accepted.json()["job_id"]
            assert client.get(base + f"/jobs/{job_id}").json()["state"] == "queued"
            assert (
                client.post(base + f"/jobs/{job_id}/cancel", headers=headers).json()["state"]
                == "cancelled"
            )
            assert client.get(base + f"/jobs/{job_id}/report").status_code == 409
        events.append("served")

    monkeypatch.setattr(uvicorn, "run", serve)
    flags = [
        "--vnpy-python",
        str(Path("python.exe")),
        "--vnpy-fixture",
        "fixture.csv",
        "--vnpy-root",
        str(tmp_path / "jobs"),
    ]
    if demo:
        flags += ["--demo", "--demo-root", str(tmp_path / "demo")]
    main(flags)
    assert events == (["demo-enter", "demo-exit", "served"] if demo else ["served"])


@pytest.mark.parametrize("subpath", [".", "jobs", "nested/../jobs"])
def test_launcher_rejects_output_in_resettable_demo_before_assembly(
    tmp_path, monkeypatch, capsys, subpath
):
    import quantmesh.demo.runtime as demo_runtime
    from quantmesh.api.workstation import main

    def forbidden(**kwargs):
        pytest.fail("unsafe configuration must fail before demo seeding")

    monkeypatch.setattr(demo_runtime, "create_demo_app", forbidden)
    demo_root = tmp_path / "demo"
    flags = [
        "--demo",
        "--demo-root",
        str(demo_root),
        "--vnpy-python",
        "python.exe",
        "--vnpy-fixture",
        "fixture.csv",
        "--vnpy-root",
        str(demo_root / subpath),
    ]
    with pytest.raises(SystemExit) as raised:
        main(flags)
    assert raised.value.code == 2
    assert "--vnpy-root must be outside the resettable demo root" in capsys.readouterr().err


def test_launcher_without_fixture_flags_remains_unbound(monkeypatch):
    import uvicorn

    from quantmesh.api.workstation import main
    from quantmesh.research.vnpy_fixture import FixtureManager

    def forbidden(*args):
        pytest.fail("ordinary startup must not construct the optional fixture runtime")

    monkeypatch.setattr(FixtureManager, "__init__", forbidden)

    def serve(app, **kwargs):
        with TestClient(app) as client:
            assert client.get("/api/markets").status_code == 200
            assert client.get("/api/research/vnpy-fixture/options").status_code == 404

    monkeypatch.setattr(uvicorn, "run", serve)
    main([])


def test_launcher_rejects_fixture_in_staging_before_assembly(monkeypatch, capsys):
    from quantmesh.api.workstation import main, settings

    monkeypatch.setattr(settings, "environment", "staging")
    with pytest.raises(SystemExit) as raised:
        main(
            ["--vnpy-python", "python.exe", "--vnpy-fixture", "fixture.csv", "--vnpy-root", "jobs"]
        )
    assert raised.value.code == 2
    assert "vn.py fixture requires the local workstation environment" in capsys.readouterr().err


def test_launcher_reports_unavailable_fixture_without_leaking_paths(tmp_path, monkeypatch, capsys):
    import uvicorn

    from quantmesh.api.workstation import main

    def forbidden(*args, **kwargs):
        pytest.fail("an unadmitted runtime must never be served")

    monkeypatch.setattr(uvicorn, "run", forbidden)
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "--vnpy-python",
                "private-python.exe",
                "--vnpy-fixture",
                "private-fixture.csv",
                "--vnpy-root",
                str(tmp_path / "jobs"),
            ]
        )
    assert raised.value.code == 2
    message = capsys.readouterr().err
    assert "vn.py fixture runtime unavailable" in message
    assert "private-python" not in message and "private-fixture" not in message


def test_launcher_checks_default_demo_root_before_seeding(tmp_path, monkeypatch, capsys):
    from quantmesh.api.workstation import main, settings

    monkeypatch.setattr(settings, "demo_root", tmp_path / "default-demo")
    with pytest.raises(SystemExit):
        main(
            [
                "--demo",
                "--vnpy-python",
                "python.exe",
                "--vnpy-fixture",
                "fixture.csv",
                "--vnpy-root",
                str(settings.demo_root / "jobs"),
            ]
        )
    assert "--vnpy-root must be outside the resettable demo root" in capsys.readouterr().err
