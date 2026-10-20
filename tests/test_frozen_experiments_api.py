"""Frozen evidence API/CLI contracts, using only synthetic package bytes."""

import hashlib
import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.research.realdata_snapshots import SnapshotCatalog
from tests.test_frozen_experiments import backend, package
from tests.test_realdata_snapshots import package as snapshot_package


@pytest.fixture
def source(tmp_path):
    snapshots = SnapshotCatalog(tmp_path / "snapshots")
    payload = snapshot_package()
    snapshots.import_archive(payload)
    return snapshots, payload


def api(catalog=None):
    assert importlib.util.find_spec("quantmesh.api.frozen_experiments") is not None, (
        "frozen experiment routes are not implemented"
    )
    mod = importlib.import_module("quantmesh.api.frozen_experiments")
    app = FastAPI()
    app.state.frozen_experiments = catalog
    app.include_router(mod.create_frozen_experiments_router(), prefix="/api")
    return TestClient(app)


def test_default_off_and_fixed_errors():
    client = api()
    response = client.get("/api/research/frozen-experiments")
    assert response.status_code == 503
    assert response.json()["detail"] == "frozen_experiment_runtime_unavailable"


def test_import_get_download_exact_originals_and_allowlist(tmp_path, source):
    snapshots, snapshot = source
    client = api(backend().FrozenExperimentCatalog(tmp_path / "experiments", snapshots))
    payload = package(snapshot)
    root = "/api/research/frozen-experiments"
    response = client.post(root, content=payload, headers={"Content-Type": "application/zip"})
    assert response.status_code == 201
    report = response.json()
    package_id = report["package_id"]
    assert client.get(f"{root}/{package_id}").json() == report
    assert client.get(root).json()["experiments"] == [report]
    response = client.get(f"{root}/{package_id}/artifacts/archive")
    assert response.content == payload
    assert response.headers["X-Content-SHA256"] == hashlib.sha256(payload).hexdigest()
    assert "attachment" in response.headers["Content-Disposition"]
    for item in report["downloads"]:
        response = client.get(f"{root}/{package_id}/artifacts/{item['kind']}")
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == item["sha256"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get(f"{root}/{package_id}/artifacts/engine.py").status_code == 404
    assert client.get(f"{root}/invalid").status_code == 404


def test_origin_content_type_stream_and_missing_snapshot(tmp_path, source):
    snapshots, snapshot = source
    mod = backend()
    client = api(mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots))
    root = "/api/research/frozen-experiments"
    assert (
        client.post(
            root,
            content=b"x",
            headers={"Origin": "https://evil.test", "Content-Type": "application/zip"},
        ).status_code
        == 403
    )
    assert client.post(root, content=b"x").status_code == 415
    assert (
        client.post(root, content=b"x", headers={"Content-Type": "application/zip"}).json()[
            "detail"
        ]
        == "frozen_experiment_invalid"
    )
    assert (
        client.post(
            root,
            content=(b"x" * 1024 * 1024 for _ in range(9)),
            headers={"Content-Type": "application/zip"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            root,
            content=b"x",
            headers={"Content-Type": "application/zip", "Content-Length": "99999999"},
        ).status_code
        == 413
    )
    response = client.post(
        root,
        content=package(snapshot, change_manifest=lambda m: m.update(snapshot_id="a" * 64)),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "frozen_experiment_snapshot_required"


def test_workstation_default_exposes_unavailable_route(tmp_path):
    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount

    app = create_workstation_app(account=PaperAccount(cash=100000), host="127.0.0.1")
    assert TestClient(app).get("/api/research/frozen-experiments").status_code == 503


@pytest.mark.parametrize(
    "args",
    [
        ["--frozen-experiments-root", "experiments"],
        [
            "--demo",
            "--demo-root",
            "demo",
            "--research-snapshots-root",
            "snapshots",
            "--frozen-experiments-root",
            "demo/experiments",
        ],
    ],
)
def test_cli_rejects_dependent_or_resettable_config_before_demo(args, monkeypatch, capsys):
    from quantmesh.api import workstation

    def forbidden(*_args, **_kwargs):
        raise AssertionError("expensive demo assembly reached")

    monkeypatch.setattr(workstation, "build_demo_workspace", forbidden, raising=False)
    with pytest.raises(SystemExit) as error:
        workstation.main(args)
    assert error.value.code == 2
    assert "unrecognized arguments" not in capsys.readouterr().err


def test_constructor_requires_p1_root_before_assembly():
    from quantmesh.api.workstation import WorkstationConfigError, create_workstation_app

    with pytest.raises(WorkstationConfigError, match="snapshot"):
        create_workstation_app(account=None, frozen_experiments_root=Path("experiments"))


def test_cli_enables_both_catalogs_with_existing_flags(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from quantmesh.api.workstation import main

    served = []
    monkeypatch.setitem(
        sys.modules, "uvicorn", SimpleNamespace(run=lambda app, **kw: served.append(app))
    )
    main(
        [
            "--research-snapshots-root",
            str(tmp_path / "snapshots"),
            "--frozen-experiments-root",
            str(tmp_path / "experiments"),
            "--port",
            "8866",
        ]
    )
    assert TestClient(served[0]).get("/api/research/frozen-experiments").json() == {
        "schema_version": 1,
        "experiments": [],
    }
    assert TestClient(served[0]).get("/api/research/data-snapshots").status_code == 200
