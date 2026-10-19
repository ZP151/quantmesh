"""Only synthetic bytes exercise the workstation snapshot HTTP/CLI boundary."""

import hashlib
import importlib
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_realdata_snapshots import NOW, backend, package

from quantmesh.api.workstation import create_workstation_app, main
from quantmesh.execution.accounting import PaperAccount

PREFIX = "/api/research/data-snapshots"


def client(tmp_path, configured=True):
    assert importlib.util.find_spec("quantmesh.api.realdata_snapshots") is not None, (
        "P1 snapshot API is not implemented"
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100000),
        host="127.0.0.1",
        research_snapshots_root=tmp_path if configured else None,
    )
    if configured:
        app.state.research_snapshots = backend().SnapshotCatalog(tmp_path, clock=lambda: NOW)
    return TestClient(app)


def test_default_is_unavailable_and_configured_list_is_empty(tmp_path):
    assert client(tmp_path, False).get(PREFIX).status_code == 503
    assert client(tmp_path).get(PREFIX).json() == {"schema_version": 1, "snapshots": []}


def test_http_import_reopen_and_download_hashes(tmp_path):
    http = client(tmp_path)
    archive = package()
    response = http.post(PREFIX, content=archive, headers={"Content-Type": "application/zip"})
    assert response.status_code == 201
    report = response.json()
    snapshot_id = report["snapshot_id"]
    assert http.get(f"{PREFIX}/{snapshot_id}").json() == report
    assert http.get(PREFIX).json()["snapshots"] == [report]
    for suffix, digest, original in (
        ("archive", snapshot_id, archive),
        ("report", report["report_digest"], None),
    ):
        download = http.get(f"{PREFIX}/{snapshot_id}/{suffix}")
        assert download.status_code == 200
        assert hashlib.sha256(download.content).hexdigest() == digest
        assert download.headers["x-content-sha256"] == digest
        assert download.headers["etag"] == f'"{digest}"'
        assert "attachment" in download.headers["content-disposition"]
        if original:
            assert download.content == original
        else:
            assert "report_digest" not in json.loads(download.content)
    assert client(tmp_path).get(f"{PREFIX}/{snapshot_id}").status_code == 200


def test_http_origin_payload_caps_and_safe_malformed_errors(tmp_path):
    http = client(tmp_path)
    archive = package()
    assert (
        http.post(
            PREFIX,
            content=archive,
            headers={"Content-Type": "application/zip", "Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert http.post(PREFIX, content=archive).status_code == 415
    bad = http.post(
        PREFIX, content=b"secret malformed content", headers={"Content-Type": "application/zip"}
    )
    assert bad.status_code == 422
    assert bad.json() == {"detail": "snapshot_invalid"}
    too_big = http.post(
        PREFIX, content=b"x" * (8 * 1024 * 1024 + 1), headers={"Content-Type": "application/zip"}
    )
    assert too_big.status_code == 413
    streamed = http.post(
        PREFIX,
        content=iter([b"x" * (4 * 1024 * 1024)] * 3),
        headers={"Content-Type": "application/zip"},
    )
    assert streamed.status_code == 413
    assert http.get(f"{PREFIX}/{'f' * 64}").status_code == 404
    assert http.get(f"{PREFIX}/bad-id").status_code == 404


def test_corrupted_bytes_are_fixed_safe_conflict(tmp_path):
    http = client(tmp_path)
    report = http.post(
        PREFIX, content=package(), headers={"Content-Type": "application/zip"}
    ).json()
    digest = report["snapshot_id"]
    target = tmp_path / ".trusted-data-v2" / "objects" / "sha256" / digest[:2] / digest
    target.write_bytes(b"secret changed bytes")
    for suffix in ("", "/archive", "/report"):
        response = http.get(f"{PREFIX}/{digest}{suffix}")
        assert response.status_code == 409
        assert response.json() == {"detail": "snapshot_integrity_failed"}


@pytest.mark.parametrize("raw", [b'{"chart":null}', b'{"chart":[]}', b"[]"])
def test_malformed_source_shapes_are_fixed_422(tmp_path, raw):
    from test_realdata_snapshots import YAHOO

    http = client(tmp_path)
    response = http.post(
        PREFIX,
        content=package(mutate=lambda files: files.update({YAHOO: raw})),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "snapshot_invalid"}


def test_malformed_nested_manifest_json_is_fixed_422(tmp_path):
    import io
    import zipfile

    http = client(tmp_path)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package())) as source, zipfile.ZipFile(output, "w") as dest:
        for info in source.infolist():
            value = (
                b"[" * 2000 + b"0" + b"]" * 2000
                if info.filename == "manifest.json"
                else source.read(info)
            )
            dest.writestr(info, value)
    response = http.post(
        PREFIX, content=output.getvalue(), headers={"Content-Type": "application/zip"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "snapshot_invalid"}


def test_ordinary_cli_root_is_independent_opt_in(tmp_path, monkeypatch):
    served = []
    monkeypatch.setitem(
        sys.modules, "uvicorn", SimpleNamespace(run=lambda app, **kw: served.append(app))
    )
    main(["--research-snapshots-root", str(tmp_path), "--port", "8844"])
    assert TestClient(served[0]).get(PREFIX).json() == {"schema_version": 1, "snapshots": []}


def test_cli_refuses_snapshot_root_in_resettable_demo_tree(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **kw: None))
    with pytest.raises(SystemExit) as refused:
        main(
            [
                "--demo",
                "--demo-root",
                str(tmp_path),
                "--research-snapshots-root",
                str(tmp_path / "snapshots"),
            ]
        )
    assert refused.value.code == 2
    assert "must be outside the resettable demo root" in capsys.readouterr().err


def test_cli_retains_existing_vnpy_flags_alongside_snapshot_root(tmp_path, monkeypatch):
    import quantmesh.api.vnpy_fixture as fixture_api
    import quantmesh.research.vnpy_fixture as fixture_engine

    served = []
    attached = []
    monkeypatch.setitem(
        sys.modules, "uvicorn", SimpleNamespace(run=lambda app, **kw: served.append(app))
    )
    manager = object()
    monkeypatch.setattr(fixture_engine, "FixtureManager", lambda *a: manager)
    monkeypatch.setattr(
        fixture_api, "attach_fixture_runtime", lambda app, instance: attached.append(instance)
    )
    main(
        [
            "--research-snapshots-root",
            str(tmp_path / "snapshots"),
            "--vnpy-python",
            str(tmp_path / "python.exe"),
            "--vnpy-fixture",
            str(tmp_path / "fixture.csv"),
            "--vnpy-root",
            str(tmp_path / "vnpy"),
        ]
    )
    assert attached == [manager]
    assert TestClient(served[0]).get(PREFIX).status_code == 200
