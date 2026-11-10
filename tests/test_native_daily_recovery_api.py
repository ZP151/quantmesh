"""Actual HTTP serialization of authored recovery records; no numerical execution."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.api.native_daily_real import create_native_daily_router
from quantmesh.research import native_daily_real as daily
from tests.test_ivv_transaction_recovery_product import transaction_registration

PREFIX = "/api/research/native-daily/jobs"


def client(service):
    app = FastAPI()
    app.state.native_daily = service
    app.include_router(create_native_daily_router(), prefix="/api")
    return TestClient(app)


def stop_before_numerical_execution(*args):
    raise RuntimeError("authored transport-only stop")


@pytest.mark.parametrize("operation", ["submit", "read", "decision"])
def test_recovery_summary_survives_actual_http_response_validation(
    tmp_path, monkeypatch, operation
):
    _, root, key, registration = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registration,))
    monkeypatch.setattr(service, "_compute", stop_before_numerical_execution)
    try:
        if operation != "submit":
            public, _ = service.submit(registration.request, key)
        with client(service) as http:
            if operation == "submit":
                response = http.post(
                    PREFIX,
                    json=registration.request.model_dump(mode="json"),
                    headers={"Idempotency-Key": key},
                )
            elif operation == "read":
                response = http.get(f"{PREFIX}/{key}")
            else:
                response = http.post(
                    f"{PREFIX}/{key}/decision",
                    json={
                        "request_digest": public["request_digest"],
                        "admission_digest": public["admission"]["digest"],
                        "report_digest": None,
                        "disposition": "watch",
                        "reason": "Authored failed engineering attempt; no financial qualification",
                    },
                    headers={"Idempotency-Key": str(uuid4())},
                )
            assert response.status_code == (200 if operation == "read" else 201), response.text
            value = response.json()
            assert value == service.read(key)
            assert value["recovery_status"] == {
                "business_key": registration.recovery["recovery_identity"]["business_key"],
                "experiment_id": "declared-trend-staged-v1",
                "registered_attempts": 1,
                "last_attempt_state": "failed",
                "request_digest_history": [value["request_digest"]],
            }
            assert "transaction" not in value and "real_binding" not in value
            assert value["financial_qualification"] == "INSUFFICIENT"
            assert value["paper_allowed"] is value["live_allowed"] is False
    finally:
        service.close()


def test_legacy_response_keeps_null_artifact_fields_and_omits_recovery_summary(tmp_path):
    service = daily.NativeDailyService(tmp_path / "legacy")
    try:
        key = str(uuid4())
        with client(service) as http:
            response = http.post(PREFIX, json={}, headers={"Idempotency-Key": key})
            assert response.status_code == 201
            assert response.json() == service.read(key)
            assert response.json()["report"] is response.json()["decision"] is None
            assert "recovery_status" not in response.json()
    finally:
        service.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("business_key", "not-a-digest"),
        ("experiment_id", "../private-path"),
        ("registered_attempts", True),
        ("last_attempt_state", "qualified"),
        ("request_digest_history", ["not-a-digest"]),
        ("private_proof", "must-not-be-public"),
    ],
)
def test_invalid_or_private_recovery_summary_is_not_silently_filtered(
    tmp_path, monkeypatch, field, value
):
    _, root, key, registration = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registration,))
    monkeypatch.setattr(service, "_compute", stop_before_numerical_execution)
    try:
        public, _ = service.submit(registration.request, key)
        public["recovery_status"][field] = value
        monkeypatch.setattr(service, "read", lambda job_id: public)
        with client(service) as http:
            response = http.get(f"{PREFIX}/{key}")
        assert response.status_code == 503
        assert response.json() == {"detail": "service_unavailable"}
        assert "private" not in response.text
    finally:
        service.close()
