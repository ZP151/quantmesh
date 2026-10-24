"""Real workstation HTTP with owned files; original ZIP inspection remains intact."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.research.local_csv_snapshots import MAX_CSV_BYTES, MAX_REQUEST_BYTES
from quantmesh.research.realdata_snapshots import SnapshotCatalog
from tests.test_local_csv_snapshots import CSV, NOW, request
from tests.test_realdata_snapshots import package

PREFIX = "/api/research/data-snapshots/local-csv"


def client(root, configured=True):
    app = create_workstation_app(
        account=PaperAccount(cash=100000),
        host="127.0.0.1",
        research_snapshots_root=root if configured else None,
    )
    if configured:
        app.state.research_snapshots = SnapshotCatalog(root, clock=lambda: NOW)
    return TestClient(app)


def test_configured_and_unconfigured_are_explicit(tmp_path):
    assert client(tmp_path, False).get(PREFIX).json() == {"detail": "snapshot_runtime_unavailable"}
    assert client(tmp_path, False).post(PREFIX, json=request()).status_code == 503
    response = client(tmp_path).get(PREFIX)
    assert response.status_code == 200
    assert response.json() == {"schema_version": 1, "snapshots": []}
    assert response.headers["cache-control"] == "private, no-store"


def test_actual_import_get_reference_download_reopen_and_old_zip_compatibility(tmp_path):
    http = client(tmp_path)
    response = http.post(PREFIX, json=request())
    assert response.status_code == 201, response.text
    report = response.json()
    snapshot_id = report["snapshot_id"]
    assert report["coverage"]["rows"] == 2
    assert report["qualification"]["structural_status"] == "PASS"
    assert report["qualification"]["status"] == "INSUFFICIENT"
    assert http.get(f"{PREFIX}/{snapshot_id}").json() == report
    reference = http.get(f"{PREFIX}/{snapshot_id}/reference")
    assert reference.status_code == 200
    assert reference.json()["runner_status"] == "blocked_unqualified_input"
    assert reference.json()["dataset_ref"] == report["dataset_ref"]
    assert reference.json()["dataset_ref"]["permission_class"] == "local_research"
    assert report["next_action"]["submission_allowed"] is False
    originals = {}
    for suffix in ("original.csv", "report", "reference.json"):
        download = http.get(f"{PREFIX}/{snapshot_id}/{suffix}")
        assert download.status_code == 200
        assert hashlib.sha256(download.content).hexdigest() == download.headers["x-content-sha256"]
        assert download.headers["cache-control"] == "private, no-store"
        assert "attachment" in download.headers["content-disposition"]
        originals[suffix] = download.content
    assert originals["original.csv"] == CSV.encode()
    assert hashlib.sha256(originals["report"]).hexdigest() == report["report_digest"]
    assert json.loads(originals["reference.json"]) == reference.json()
    reopened = client(tmp_path)
    assert reopened.get(f"{PREFIX}/{snapshot_id}").json() == report
    assert reopened.post(PREFIX, json=request()).json() == report
    assert len(reopened.get(PREFIX).json()["snapshots"]) == 1
    old = reopened.post(
        "/api/research/data-snapshots",
        content=package(),
        headers={"content-type": "application/zip"},
    )
    assert old.status_code == 201
    assert old.json()["symbol"] == "SPY"
    assert len(reopened.get("/api/research/data-snapshots").json()["snapshots"]) == 1
    assert len(reopened.get(PREFIX).json()["snapshots"]) == 1


def test_semantic_reject_is_retained_not_http_parse_error(tmp_path):
    http = client(tmp_path)
    invalid_csv = CSV.replace("100,102,99,101,1000", "100,98,99,101,1000")
    response = http.post(PREFIX, json=request(csv_text=invalid_csv))
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["qualification"]["status"] == "REJECT"
    assert report["dataset_ref"] is None
    assert (
        next(c for c in report["checks"] if c["code"] == "bar_values")["locations"][0]["row"] == 2
    )
    assert (
        http.get(f"{PREFIX}/{report['snapshot_id']}/original.csv").content == invalid_csv.encode()
    )
    assert http.get(f"{PREFIX}/{report['snapshot_id']}/reference").json()["normalized_csv"] is None


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"value":NaN}',
        b"[]",
        b"bad-json",
        b'{"csv_text":"timestamp_utc,open,high,low,close,volume\\n"}',
    ],
)
def test_fixed_invalid_json_and_metadata_errors(tmp_path, payload):
    response = client(tmp_path).post(
        PREFIX, content=payload, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "local_csv_invalid"}


def test_csv_header_and_shape_errors_are_fixed_422(tmp_path):
    for csv_text in ("date,open,high,low,close,volume\n2026-10-15,1,2,1,2,10\n", CSV + "1,2\n"):
        response = client(tmp_path).post(PREFIX, json=request(csv_text=csv_text))
        assert response.status_code == 422
        assert response.json() == {"detail": "local_csv_invalid"}


def test_original_origin_guard_and_content_types_are_preserved(tmp_path):
    http = client(tmp_path)
    assert (
        http.post(PREFIX, json=request(), headers={"origin": "https://foreign.invalid"}).status_code
        == 403
    )
    response = http.post(PREFIX, content=b"arbitrary", headers={"content-type": "application/zip"})
    assert response.status_code == 415
    assert response.json() == {"detail": "local_csv_content_type"}


def test_declared_and_streamed_limits_are_not_validation_details(tmp_path):
    http = client(tmp_path)
    response = http.post(
        PREFIX,
        content=b"{}",
        headers={"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 1)},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "local_csv_too_large"}

    def chunks():
        yield b" " * (MAX_REQUEST_BYTES // 2)
        yield b" " * (MAX_REQUEST_BYTES // 2 + 1)

    streamed = http.post(PREFIX, content=chunks(), headers={"content-type": "application/json"})
    assert streamed.status_code == 413
    assert streamed.json() == {"detail": "local_csv_too_large"}
    invalid_length = http.post(
        PREFIX,
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "not-a-number"},
    )
    assert invalid_length.status_code == 422


@pytest.mark.parametrize(
    "csv_text",
    ["x" * (MAX_CSV_BYTES + 1), "é" * (MAX_CSV_BYTES // 2 + 1)],
    ids=["ascii", "multibyte"],
)
def test_ascii_and_multibyte_csv_size_errors_are_both_413(tmp_path, csv_text):
    payload = request(csv_text=csv_text)
    assert len(json.dumps(payload, ensure_ascii=False).encode()) < MAX_REQUEST_BYTES
    response = client(tmp_path).post(PREFIX, json=payload)
    assert response.status_code == 413
    assert response.json() == {"detail": "local_csv_too_large"}
    assert not (tmp_path / "local-csv" / "snapshots").exists()


def test_invalid_unknown_and_corrupted_are_distinct_without_sensitive_values(tmp_path):
    http = client(tmp_path)
    assert http.get(f"{PREFIX}/{'1' * 64}").status_code == 404
    assert http.get(f"{PREFIX}/invalid-id").json() == {"detail": "local_csv_unknown"}
    report = http.post(PREFIX, json=request()).json()
    digest = report["lineage"]["original_sha256"]
    target = (
        tmp_path / "local-csv" / ".trusted-data-v2" / "objects" / "sha256" / digest[:2] / digest
    )
    target.write_bytes(b"private injected content")
    for suffix in ("", "/report", "/original.csv", "/reference", "/reference.json"):
        response = http.get(f"{PREFIX}/{report['snapshot_id']}{suffix}")
        assert response.status_code == 409
        assert response.json() == {"detail": "local_csv_integrity_failed"}


def test_openapi_has_actual_typed_request_and_report_reference_responses(tmp_path):
    schema = client(tmp_path).app.openapi()
    post = schema["paths"][PREFIX]["post"]
    assert post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/LocalCsvRequest"
    )
    assert post["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/LocalCsvReport"
    )
    assert schema["paths"][PREFIX + "/{snapshot_id}/reference"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("/LocalCsvReference")
