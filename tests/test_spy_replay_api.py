"""Actual API/math/storage paths over trusted synthetic sessions only."""

import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.research.spy_replay import ReplayService
from tests.test_spy_replay import request_for, synthetic_input

BASE = "/api/research/spy-replay"


def app(service=None):
    return create_workstation_app(account=PaperAccount(cash=100000), spy_replay_service=service)


def test_actual_five_endpoint_loop_original_bytes_and_cold_reopen(tmp_path):
    value = synthetic_input()
    key, decision_key = str(uuid4()), str(uuid4())
    service = ReplayService(tmp_path, replay_input=value)
    with TestClient(app(service)) as client:
        options = client.get(BASE).json()
        assert options["configured"] and options["input"]["evidence_kind"] == "engineering_fixture"
        assert options["paper_allowed"] is False
        request = request_for(value).model_dump()
        first = client.post(BASE + "/jobs", json=request, headers={"Idempotency-Key": key})
        assert first.status_code == 201
        job = first.json()
        assert job["state"] == "succeeded" and job["job_id"] == key
        response = client.get(BASE + f"/jobs/{key}/artifact")
        raw = response.content
        assert hashlib.sha256(raw).hexdigest() == job["report"]["digest"]
        assert response.headers["X-Content-SHA256"] == job["report"]["digest"]
        assert (
            response.json()["calculation"]["scenarios"]["base5"]["strategy"]["metrics"][
                "total_return"
            ]
            > 0
        )
        body = dict(
            request_digest=job["request_digest"],
            report_digest=job["report"]["digest"],
            disposition="watch",
            reason="Development follow-up only",
        )
        headers = {"Idempotency-Key": decision_key}
        decided = client.post(BASE + f"/jobs/{key}/decision", json=body, headers=headers)
        assert decided.status_code == 201
        retry = client.post(BASE + f"/jobs/{key}/decision", json=body, headers=headers)
        assert retry.status_code == 200 and retry.json() == decided.json()
        decision_raw = client.get(BASE + f"/jobs/{key}/artifact?kind=decision").content
        assert (
            client.post(BASE + "/jobs", json=request, headers={"Idempotency-Key": key}).json()
            == decided.json()
        )
    # Lifespan actually released the writer lease; new service can reopen.
    cold = ReplayService(tmp_path)
    with TestClient(app(cold)) as client:
        assert client.get(BASE + f"/jobs/{key}").json() == decided.json()
        assert client.get(BASE + f"/jobs/{key}/artifact").content == raw
        assert client.get(BASE + f"/jobs/{key}/artifact?kind=decision").content == decision_raw


@pytest.mark.parametrize(
    "extra",
    [
        dict(fixture=True),
        dict(qualified=True),
        dict(path="private"),
        dict(parameters={"lookback": 1}),
        dict(paper_allowed=True),
    ],
)
def test_public_input_claims_cannot_admit_or_change_math(tmp_path, extra):
    value = synthetic_input()
    service = ReplayService(tmp_path)
    with TestClient(app(service)) as client:
        response = client.post(
            BASE + "/jobs",
            json={**request_for(value).model_dump(), **extra},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422 and response.json() == {"detail": "invalid_request"}
        assert not (tmp_path / "jobs.jsonl").exists()


def test_default_unconfigured_and_real_input_gate_are_separate(tmp_path):
    value = synthetic_input()
    with TestClient(app()) as client:
        assert client.get(BASE).json()["unavailable_reason"] == "not_configured"
        assert (
            client.post(
                BASE + "/jobs",
                json=request_for(value).model_dump(),
                headers={"Idempotency-Key": str(uuid4())},
            ).status_code
            == 503
        )
    with TestClient(app(ReplayService(tmp_path))) as client:
        response = client.post(
            BASE + "/jobs",
            json=request_for(value).model_dump(),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "input_not_qualified"}


def test_origin_guard_conflicts_errors_and_openapi_contract(tmp_path):
    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    with TestClient(app(service)) as client:
        request, key = request_for(value).model_dump(), str(uuid4())
        bad = client.post(
            BASE + "/jobs",
            json=request,
            headers={"Idempotency-Key": key, "Origin": "https://attacker.invalid"},
        )
        assert bad.status_code == 403 and not (tmp_path / "jobs.jsonl").exists()
        assert client.post(BASE + "/jobs", json=request).status_code == 422
        assert client.get(BASE + "/jobs/bad").json() == {"detail": "invalid_request"}
        assert client.get(BASE + f"/jobs/{uuid4()}").status_code == 404
        assert (
            client.post(BASE + "/jobs", json=request, headers={"Idempotency-Key": key}).status_code
            == 201
        )
        changed = {**request, "protocol_digest": "a" * 64}
        assert client.post(
            BASE + "/jobs", json=changed, headers={"Idempotency-Key": key}
        ).json() == {"detail": "idempotency_conflict"}
        schema = client.get("/openapi.json").json()
        assert set(schema["components"]["schemas"]["ReplayRequest"]["properties"]) == {
            "snapshot_digest",
            "protocol_digest",
        }
        assert schema["paths"][BASE + "/jobs"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"] == {"$ref": "#/components/schemas/ReplayRequest"}


def test_cli_opt_in_is_real_and_root_cannot_be_inside_demo(tmp_path, monkeypatch):
    import uvicorn

    from quantmesh.api import workstation

    seen = []

    def serve(application, **kwargs):
        with TestClient(application) as client:
            seen.append(client.get(BASE).json())

    monkeypatch.setattr(uvicorn, "run", serve)
    root = tmp_path / "replay"
    workstation.main(["--spy-replay-root", str(root)])
    assert seen[0]["unavailable_reason"] == "input_not_qualified"
    reopened = ReplayService(root)
    reopened.close()
    with pytest.raises(SystemExit):
        workstation.main(
            [
                "--demo",
                "--demo-root",
                str(tmp_path / "demo"),
                "--spy-replay-root",
                str(tmp_path / "demo/replay"),
            ]
        )
    assert len(seen) == 1


def test_paper_decision_is_rejected_without_any_decision_effect(tmp_path):
    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    with TestClient(app(service)) as client:
        key = str(uuid4())
        job = client.post(
            BASE + "/jobs", json=request_for(value).model_dump(), headers={"Idempotency-Key": key}
        ).json()
        response = client.post(
            BASE + f"/jobs/{key}/decision",
            json={
                "request_digest": job["request_digest"],
                "report_digest": job["report"]["digest"],
                "disposition": "paper_proposal",
                "reason": "Should be refused",
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422
        assert client.get(BASE + f"/jobs/{key}").json()["decision"] is None


@pytest.mark.parametrize("failure", ["startup", "shutdown"])
def test_runtime_attachment_closes_real_service_even_if_original_lifespan_fails(tmp_path, failure):
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    from quantmesh.api.spy_replay import attach_spy_replay_runtime

    @asynccontextmanager
    async def original(application):
        if failure == "startup":
            raise RuntimeError("controlled startup failure")
        yield
        raise RuntimeError("controlled shutdown failure")

    application = FastAPI(lifespan=original)
    service = ReplayService(tmp_path)
    attach_spy_replay_runtime(application, service)
    with pytest.raises(RuntimeError):
        with TestClient(application):
            pass
    reopened = ReplayService(tmp_path)
    reopened.close()


def test_duplicate_json_keys_and_large_requests_are_bounded(tmp_path):
    with TestClient(app(ReplayService(tmp_path))) as client:
        headers = {"Idempotency-Key": str(uuid4()), "Content-Type": "application/json"}
        duplicate = client.post(
            BASE + "/jobs", content='{"snapshot_digest":"a","snapshot_digest":"b"}', headers=headers
        )
        assert duplicate.status_code == 422 and duplicate.json() == {"detail": "invalid_request"}
        large = client.post(BASE + "/jobs", content=b" " * 8193, headers=headers)
        assert large.status_code == 422 and large.json() == {"detail": "invalid_request"}
        assert not (tmp_path / "jobs.jsonl").exists()
