"""Verified saved-study discovery; synthetic software evidence, never real research."""

import hashlib
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantmesh.api.native_daily_real import create_native_daily_router
from quantmesh.data.objects import ObjectStore
from quantmesh.research import native_daily_real as daily
from tests.test_ivv_transaction_recovery_product import transaction_registration

PREFIX = "/api/research/native-daily/jobs"


def client(service=None):
    app = FastAPI()
    if service is not None:
        app.state.native_daily = service
    app.include_router(create_native_daily_router(), prefix="/api")
    return TestClient(app)


def snapshot(root):
    """The held Windows lease is deliberately not opened or mistaken for an artifact."""
    return {
        str(path.relative_to(root)): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file() and path.name != ".writer.lock"
    }


def forbidden(*args, **kwargs):
    pytest.fail("saved-study discovery invoked a write or execution path")


def forbid_effects(service, monkeypatch):
    for name in ("submit", "decide", "_compute", "_publish_records", "_put"):
        monkeypatch.setattr(service, name, forbidden)
    monkeypatch.setattr(service._store, "write", forbidden)
    monkeypatch.setattr(service.objects, "put_bytes", forbidden)


def test_configured_empty_collection_does_not_create_a_journal(tmp_path, monkeypatch):
    with_service = daily.NativeDailyService(tmp_path / "study")
    try:
        before = snapshot(with_service.root)
        forbid_effects(with_service, monkeypatch)
        with client(with_service) as http:
            response = http.get(PREFIX)
        assert response.status_code == 200, response.text
        assert response.json() == {"jobs": []}
        assert response.headers["cache-control"] == "private, no-store"
        assert not with_service._store.path.exists()
        assert snapshot(with_service.root) == before
    finally:
        with_service.close()


def test_unconfigured_service_is_unavailable_not_empty():
    with client() as http:
        response = http.get(PREFIX)
    assert response.status_code == 503, response.text
    assert response.json() == {"detail": "service_unavailable"}


def test_original_creation_order_and_uuid_ties_are_stable_and_read_only(tmp_path, monkeypatch):
    service = daily.NativeDailyService(tmp_path / "study")
    try:
        times_and_ids = (
            ("2026-11-10T00:00:00+00:00", str(UUID(int=3))),
            ("2026-11-11T00:00:00+00:00", str(UUID(int=2))),
            ("2026-11-11T00:00:00+00:00", str(UUID(int=1))),
        )
        original = {}
        for created_at, key in times_and_ids:
            monkeypatch.setattr(daily, "_now", lambda value=created_at: value)
            original[key], _ = service.submit(daily.NativeRequest(), key)
        before = snapshot(service.root)
        forbid_effects(service, monkeypatch)
        with client(service) as http:
            response = http.get(PREFIX)
            assert response.status_code == 200, response.text
            jobs = response.json()["jobs"]
            assert [job["job_id"] for job in jobs] == [str(UUID(int=i)) for i in (1, 2, 3)]
            assert http.get(PREFIX).json() == response.json()
            for job in jobs:
                assert job == original[job["job_id"]]
                assert http.get(f"{PREFIX}/{job['job_id']}").json() == job
                assert job["report"] is job["decision"] is None
                assert "recovery_status" not in job
        assert snapshot(service.root) == before
    finally:
        service.close()


def test_service_collection_uses_existing_condition(tmp_path, monkeypatch):
    service = daily.NativeDailyService(tmp_path / "study")
    original = service._records
    entered = []
    condition = service._condition

    class ObservedCondition:
        def __enter__(self):
            condition.__enter__()
            entered.append(True)

        def __exit__(self, *args):
            entered.pop()
            return condition.__exit__(*args)

    def records():
        assert entered, "journal read bypassed the service condition"
        return original()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(service, "_condition", ObservedCondition())
            patch.setattr(service, "_records", records)
            assert service.list_jobs() == {"jobs": []}
    finally:
        service.close()


def test_cold_collection_reopens_original_report_and_decision_without_effects(
    tmp_path, monkeypatch
):
    # One synthetic setup produces originals; discovery itself is tested with execution disabled.
    root = tmp_path / "study"
    registered = daily.engineering_registration(ObjectStore(tmp_path / "inputs"), output_root=root)
    service = daily.NativeDailyService(root, registered=(registered,))
    key = str(uuid4())
    try:
        job, _ = service.submit(registered.request, key)
        assert job["state"] == "succeeded"
        job, _ = service.decide(
            key,
            daily.NativeDecisionRequest(
                request_digest=job["request_digest"],
                admission_digest=job["admission"]["digest"],
                report_digest=job["report"]["digest"],
                disposition="watch",
                reason="Synthetic archive discovery evidence only",
            ),
            str(uuid4()),
        )
        originals = {
            kind: service.artifact(key, kind) for kind in ("admission", "report", "decision")
        }
    finally:
        service.close()

    from quantmesh.data.calendars import CalendarService
    from quantmesh.research import native_daily_candidate as native

    monkeypatch.setattr(daily, "engineering_registration", forbidden)
    monkeypatch.setattr(native, "_calculate_matrix", forbidden)
    monkeypatch.setattr(native.engine, "run_cashbook", forbidden)
    monkeypatch.setattr(CalendarService, "__init__", forbidden)
    before = snapshot(root)
    cold = daily.NativeDailyService(root)  # No currently registered input is needed.
    try:
        forbid_effects(cold, monkeypatch)
        with client(cold) as http:
            response = http.get(PREFIX)
            assert response.status_code == 200, response.text
            assert response.json() == {"jobs": [job]}
            assert http.get(f"{PREFIX}/{key}").json() == job
            for kind, raw in originals.items():
                artifact = http.get(f"{PREFIX}/{key}/artifact", params={"kind": kind})
                assert artifact.status_code == 200
                assert artifact.content == raw
                assert artifact.headers["x-content-sha256"] == hashlib.sha256(raw).hexdigest()
        assert snapshot(root) == before
    finally:
        cold.close()


def test_actual_recovery_and_legacy_views_keep_exact_public_shape(tmp_path, monkeypatch):
    _, root, key, registration = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registration,))

    def stop_before_calculation(*args):
        raise RuntimeError("synthetic transport-only setup")

    try:
        monkeypatch.setattr(service, "_compute", stop_before_calculation)
        recovery, _ = service.submit(registration.request, key)
        legacy, _ = service.submit(daily.NativeRequest(), str(uuid4()))
        expected = {job["job_id"]: job for job in (recovery, legacy)}
        before = snapshot(root)
        forbid_effects(service, monkeypatch)
        with client(service) as http:
            response = http.get(PREFIX)
        assert response.status_code == 200, response.text
        assert {job["job_id"]: job for job in response.json()["jobs"]} == expected
        assert recovery["recovery_status"]["registered_attempts"] == 1
        for job in response.json()["jobs"]:
            assert set(job).isdisjoint(
                {"consumed_grant", "decision_key", "scope_trial_key", "real_binding", "transaction"}
            )
            assert job["financial_qualification"] == "INSUFFICIENT"
            assert job["paper_allowed"] is job["live_allowed"] is False
        assert snapshot(root) == before
    finally:
        service.close()


@pytest.mark.parametrize("damage", ["admission", "journal", "durability"])
def test_invalid_archive_never_returns_a_partial_or_empty_success(tmp_path, monkeypatch, damage):
    service = daily.NativeDailyService(tmp_path / "study")
    try:
        service.submit(daily.NativeRequest(), str(uuid4()))
        job, _ = service.submit(daily.NativeRequest(), str(uuid4()))
        if damage == "admission":
            reference = daily.ObjectRef.model_validate(job["admission"])
            service.objects.path_for(reference).write_bytes(b"{}")
        elif damage == "journal":
            with service._store.path.open("a", encoding="utf-8") as stream:
                stream.write('{"unreadable_private_input": true}\n')
        else:
            monkeypatch.setattr(service._store, "durability_uncertain", True)
        before = snapshot(service.root)
        forbid_effects(service, monkeypatch)
        with client(service) as http:
            response = http.get(PREFIX)
        assert response.status_code == 409, response.text
        assert response.json() == {"detail": "artifact_invalid"}
        assert snapshot(service.root) == before
    finally:
        service.close()


def test_existing_capacity_limit_is_neither_expanded_nor_silently_truncated(tmp_path, monkeypatch):
    service = daily.NativeDailyService(tmp_path / "study")
    try:
        keys = [str(UUID(int=i + 1)) for i in range(daily.MAX_JOBS)]
        for key in keys:
            service.submit(daily.NativeRequest(), key)
        with pytest.raises(daily.NativeError, match="capacity_exceeded"):
            service.submit(daily.NativeRequest(), str(UUID(int=100)))
        before = snapshot(service.root)
        forbid_effects(service, monkeypatch)
        with client(service) as http:
            response = http.get(PREFIX)
            assert response.status_code == 200, response.text
            assert {job["job_id"] for job in response.json()["jobs"]} == set(keys)
            schema = http.get("/openapi.json").json()["components"]["schemas"]
            assert schema["NativeJobCollection"]["properties"]["jobs"]["maxItems"] == 32
        assert snapshot(service.root) == before
        # Preserve the exact existing verifier's over-capacity refusal, not a list truncation.
        records = service._store.read()
        extra = records[-1].model_copy(update={"job_id": str(UUID(int=100))})
        with monkeypatch.context() as patch:
            patch.setattr(service._store, "read", lambda: [*records, extra])
            with client(service) as http:
                refused = http.get(PREFIX)
            assert refused.status_code == 409
            assert refused.json() == {"detail": "artifact_invalid"}
    finally:
        service.close()


@pytest.mark.parametrize("damage", ["private", "invalid_recovery", "over_capacity"])
def test_collection_response_validation_does_not_filter_invalid_public_records(
    tmp_path, monkeypatch, damage
):
    service = daily.NativeDailyService(tmp_path / "study")
    try:
        public, _ = service.submit(daily.NativeRequest(), str(uuid4()))
        if damage == "private":
            public["real_binding"] = {"secret": "must not escape"}
        elif damage == "invalid_recovery":
            public["recovery_status"] = {"business_key": "invalid"}
        jobs = [public] * (33 if damage == "over_capacity" else 1)
        monkeypatch.setattr(service, "list_jobs", lambda: {"jobs": jobs}, raising=False)
        with client(service) as http:
            response = http.get(PREFIX)
        assert response.status_code == 503, response.text
        assert response.json() == {"detail": "service_unavailable"}
        assert "must not escape" not in response.text
    finally:
        service.close()
