"""Offline facade boundaries: durable identity, private transport and verified bytes."""

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_research_jobs import request_for

from quantmesh.api.research_jobs import create_research_jobs_router
from quantmesh.research.job_options import job_options
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import StoreUnavailable
from quantmesh.research.service_client import LocalResearchClient, ResearchServiceClient
from tests.research_fixtures import pinned_lake

pytest_plugins = ("test_research_job_artifacts",)


@pytest.fixture
def local(tmp_path):
    lake = tmp_path / "worker-lake"
    pinned_lake(lake)
    store = SQLiteJobStore(tmp_path / "jobs.sqlite", lake_root=lake)
    return (
        store,
        lake,
        LocalResearchClient(
            store, operator_id="local", lake_root=lake, configured_dataset_ids=("equities",)
        ),
    )


def api(client):
    app = FastAPI()
    app.include_router(create_research_jobs_router(client))
    return TestClient(app)


def test_submit_idempotency_409_and_unavailable_503(local):
    store, lake, client = local
    body = request_for(lake).model_dump(mode="json")
    headers = {"Idempotency-Key": "fixed-key"}
    with api(client) as app:
        first = app.post("/research/jobs", json=body, headers=headers)
        assert first.status_code == 200
        assert app.post("/research/jobs", json=body, headers=headers).json() == first.json()
        assert (
            app.post(
                "/research/jobs", json={**body, "analysis_requested": True}, headers=headers
            ).status_code
            == 409
        )
        job_id = first.json()["job_id"]
        assert app.get(f"/research/jobs/{job_id}").json()["state"] == "queued"
        assert app.post(f"/research/jobs/{job_id}/cancel").json()["state"] == "cancelled"
        assert app.get("/research/job-options").json()["status"] == "configured"
    reopened = SQLiteJobStore(store.path, lake_root=lake)
    assert reopened.get("local", job_id).state == "cancelled"
    with api(None) as app:
        assert app.post("/research/jobs", json=body, headers=headers).status_code == 503
        assert app.get("/research/job-options").status_code == 503


def test_unqualified_configuration_cannot_submit(local):
    store, lake, _ = local
    client = LocalResearchClient(
        store, operator_id="local", lake_root=lake, configured_dataset_ids=()
    )
    with api(client) as app:
        assert app.get("/research/job-options").json()["datasets"] == []
        assert (
            app.post(
                "/research/jobs",
                json=request_for(lake).model_dump(mode="json"),
                headers={"Idempotency-Key": "key"},
            ).status_code
            == 422
        )


def remote(handler):
    return ResearchServiceClient(
        endpoint="https://research.example.ts.net",
        allowed_endpoints=("https://research.example.ts.net",),
        operator_id="local",
        token=SecretStr("private-test-secret-123"),
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize("fault", ["schema", "operator", "request_digest", "id", "key", "config"])
def test_unknown_schema_and_source_identity_reject(local, fault):
    store, lake, _ = local
    request = request_for(lake)
    job = store.submit("local", "key", request)
    data = job.model_dump(mode="json")
    if fault == "schema":
        data["request"]["schema_version"] = 2
    elif fault == "operator":
        data["operator_id"] = "other"
    elif fault == "id":
        data["job_id"] = "different"
    elif fault == "key":
        data["idempotency_key"] = "other"
    elif fault == "config":
        data["request"]["analysis_requested"] = True
    else:
        data["request_digest"] = "a" * 64
    with remote(lambda _: httpx.Response(200, json=data)) as client:
        with pytest.raises(StoreUnavailable):
            if fault == "id":
                client.get(job.job_id)
            else:
                client.submit(request, "key")


def test_transport_maps_options_jobs_and_cancel_without_retry(local):
    store, lake, _ = local
    job = store.submit("local", "key", request_for(lake))
    paths = []

    def handler(request):
        paths.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer private-test-secret-123"
        if request.url.path == "/v1/options":
            return httpx.Response(
                200, json=job_options(lake, ("equities",)).model_dump(mode="json")
            )
        return httpx.Response(200, json=job.model_dump(mode="json"))

    with remote(handler) as client:
        assert client.options().status == "configured"
        client.submit(job.request, "key")
        client.get(job.job_id)
        client.cancel(job.job_id)
    assert paths == [
        ("GET", "/v1/options"),
        ("POST", "/v1/jobs"),
        ("GET", f"/v1/jobs/{job.job_id}"),
        ("POST", f"/v1/jobs/{job.job_id}/cancel"),
    ]


@pytest.mark.parametrize("status", [302, 500, 503])
def test_errors_do_not_echo_credentials_or_follow_redirects(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://public.example"},
            json={"detail": "private-test-secret-123 postgres://credentials"},
        )

    with remote(handler) as client, api(client) as app:
        response = app.get("/research/job-options")
        assert response.status_code == 503
        assert response.json() == {"detail": "service_unavailable"}
        assert len(calls) == 1


def test_bounded_json_and_options_schema_reject():
    for content in (b" " * (1024 * 1024 + 1), json.dumps({"schema_version": 2}).encode()):
        with remote(lambda _: httpx.Response(200, content=content)) as client:
            with pytest.raises(StoreUnavailable):
                client.options()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://research.example.ts.net",
        "https://public.example",
        "https://user:secret@research.example.ts.net",
        "https://research.example.ts.net/path",
    ],
)
def test_only_fixed_private_tls_origin(endpoint):
    with pytest.raises(ValueError, match="private endpoint"):
        ResearchServiceClient(
            endpoint=endpoint,
            allowed_endpoints=(endpoint,),
            operator_id="local",
            token=SecretStr("private-test-secret-123"),
        )


def test_api_validation_never_echoes_secret(local):
    with api(local[2]) as app:
        response = app.post(
            "/research/jobs",
            json={"secret": "private-test-secret-123"},
            headers={"Idempotency-Key": "key"},
        )
        assert response.status_code == 422
        assert "private-test-secret-123" not in response.text


def test_local_options_must_use_authoritative_worker_root(local, tmp_path):
    store, _, _ = local
    with pytest.raises(ValueError, match="worker_inputs_mismatch"):
        LocalResearchClient(
            store,
            operator_id="local",
            lake_root=tmp_path / "other",
            configured_dataset_ids=("equities",),
        )


def test_historical_report_and_same_key_replay_survive_engine_upgrade(result, monkeypatch):
    from quantmesh.research import service_client, strategy_registry
    from quantmesh.research.job_artifacts import canonical_result, publish_result

    store, job, report = result
    claimed = store.claim("owned", job.created_at)
    ref = publish_result(job, canonical_result(report), store.artifact_root)
    assert store.finish(job.job_id, "owned", claimed.attempt, "succeeded", [ref], None)
    old_registry = strategy_registry.get_strategy

    def upgraded(name, version):
        return old_registry(name, version).model_copy(update={"implementation_digest": "a" * 64})

    monkeypatch.setattr(strategy_registry, "get_strategy", upgraded)
    monkeypatch.setattr(service_client, "get_strategy", upgraded, raising=False)
    client = LocalResearchClient(
        store, operator_id="local", lake_root=store.lake_root, configured_dataset_ids=("equities",)
    )
    completed = client.get(job.job_id)
    assert completed.implementation_digest == job.implementation_digest
    assert client.submit(job.request, job.idempotency_key).job_id == job.job_id
    assert (
        client.artifact(job.job_id, ref.artifact_id)
        == (store.artifact_root / ref.object_key).read_bytes()
    )
    with remote(lambda _: httpx.Response(200, json=completed.model_dump(mode="json"))) as service:
        assert service.get(job.job_id).implementation_digest == job.implementation_digest


def test_remote_conflict_stays_409(local):
    with remote(lambda _: httpx.Response(409, json={"detail": "secret"})) as client:
        with api(client) as app:
            response = app.post(
                "/research/jobs",
                json=request_for(local[1]).model_dump(mode="json"),
                headers={"Idempotency-Key": "key"},
            )
            assert response.status_code == 409


def test_local_and_remote_immutable_report_reload(result):
    from quantmesh.research.job_artifacts import canonical_result, publish_result

    store, job, report = result
    claimed = store.claim("owned", job.created_at)
    ref = publish_result(job, canonical_result(report), store.artifact_root)
    assert store.finish(job.job_id, "owned", claimed.attempt, "succeeded", [ref], None)
    completed = store.get("local", job.job_id)
    raw = (store.artifact_root / ref.object_key).read_bytes()
    client = LocalResearchClient(
        store, operator_id="local", lake_root=store.lake_root, configured_dataset_ids=("equities",)
    )
    assert client.artifact(job.job_id, ref.artifact_id) == raw

    def handler(request):
        return (
            httpx.Response(200, content=raw)
            if "/artifacts/" in request.url.path
            else httpx.Response(200, json=completed.model_dump(mode="json"))
        )

    with remote(handler) as service:
        assert service.artifact(job.job_id, ref.artifact_id) == raw
    (store.artifact_root / ref.object_key).write_bytes(b"changed")
    with api(client) as app:
        assert (
            app.get(f"/research/jobs/{job.job_id}/artifacts/{ref.artifact_id}").status_code == 409
        )


@pytest.mark.parametrize("fault", ["digest", "size", "schema", "config", "oversize"])
def test_artifact_identity_schema_and_bounds_reject(result, fault):
    import hashlib

    from quantmesh.research.job_artifacts import canonical_result, publish_result
    from quantmesh.research.service_client import ARTIFACT_LIMIT, ArtifactInvalid

    store, job, report = result
    ref = publish_result(job, canonical_result(report), store.artifact_root)
    raw = (store.artifact_root / ref.object_key).read_bytes()
    record = job.model_dump(mode="json")
    record.update(state="succeeded", artifacts=[ref.model_dump(mode="json")])
    if fault in ("schema", "config"):
        envelope = json.loads(raw)
        envelope["schema_version" if fault == "schema" else "request_digest"] = (
            2 if fault == "schema" else "a" * 64
        )
        raw = json.dumps(envelope).encode()
        digest = hashlib.sha256(raw).hexdigest()
        record["artifacts"][0].update(
            artifact_id=digest,
            sha256=digest,
            byte_size=len(raw),
            object_key=f"{job.job_id}/{digest}.json",
        )
    elif fault == "size":
        record["artifacts"][0]["byte_size"] += 1
    elif fault == "oversize":
        raw = b"x" * (ARTIFACT_LIMIT + 1)
    else:
        raw = b"x" * len(raw)
    artifact_id = record["artifacts"][0]["artifact_id"]

    def handler(request):
        return (
            httpx.Response(200, content=raw)
            if "/artifacts/" in request.url.path
            else httpx.Response(200, json=record)
        )

    with remote(handler) as service:
        with pytest.raises((ArtifactInvalid, StoreUnavailable)):
            service.artifact(job.job_id, artifact_id)
