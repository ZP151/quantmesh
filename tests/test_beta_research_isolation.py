"""Real Native router/store isolation, using a retained synthetic archive without computing."""

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.research.native_daily_real import NativeDailyService
from tests.test_beta_access import ADMIN, ORIGIN, beta_module, invitation, login  # noqa: F401,F811

PREFIX = "/api/research/native-daily/jobs"
ARCHIVE_ID = "ceb5c366-c91d-434b-8e01-5a6b8cfbdee9"


def copy_archive(root):
    frozen = json.loads((Path(__file__).parent / "fixtures/beta-native-archive.json").read_text())
    for name, content in frozen.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode())


def test_a_cannot_access_b_or_operator_and_revocation_blocks_known_ids(
    tmp_path,
    beta_module,  # noqa: F811
    monkeypatch,
):
    operator_root = tmp_path / "operator"
    copy_archive(operator_root)
    original = NativeDailyService(operator_root)
    original_options = original.options()
    monkeypatch.setattr(
        original,
        "options",
        lambda: {**original_options, "packages": ["operator-only-test-registration"]},
    )
    services = []

    def factory(root):
        # A fresh account has no grant; B's trusted test setup receives the retained archive.
        if services:
            copy_archive(root)
        service = NativeDailyService(root)
        services.append(service)
        return service

    access = beta_module.BetaAccess(
        tmp_path / "accounts",
        operator_token=SecretStr(ADMIN["Authorization"].removeprefix("Bearer ")),
        native_factory=factory,
    )
    app = create_workstation_app(
        account=PaperAccount(cash=100_000), native_daily_service=original, beta_access=access
    )
    with TestClient(app, base_url=ORIGIN) as http:
        operator_job = http.get(f"{PREFIX}/{ARCHIVE_ID}", headers=ADMIN)
        assert operator_job.status_code == 200, operator_job.text
        assert http.get("/api/research/native-daily/options", headers=ADMIN).json()["packages"] == [
            "operator-only-test-registration"
        ]
        invite_a, invite_b = invitation(http, "A"), invitation(http, "B")
        login(http, invite_a)
        a_token = http.cookies.get("qm_beta_session")
        a_headers = {"Authorization": f"Bearer {a_token}"}
        options = http.get("/api/research/native-daily/options")
        assert options.status_code == 200 and options.json()["packages"] == []
        a_id = str(uuid4())
        a_job = http.post(PREFIX, headers={**a_headers, "Idempotency-Key": a_id}, json={})
        assert a_job.status_code == 201, a_job.text
        assert a_job.json()["state"] == "not_run"
        http.cookies.clear()
        login(http, invite_b)
        b_token = http.cookies.get("qm_beta_session")
        b_headers = {"Authorization": f"Bearer {b_token}"}
        b_jobs = http.get(PREFIX)
        assert b_jobs.status_code == 200, b_jobs.text
        assert [j["job_id"] for j in b_jobs.json()["jobs"]] == [ARCHIVE_ID]
        original_artifacts = {}
        for kind in ("admission", "report", "decision"):
            owned = http.get(f"{PREFIX}/{ARCHIVE_ID}/artifact?kind={kind}")
            assert owned.status_code == 200, owned.text
            original_artifacts[kind] = owned.content
            foreign = http.get(f"{PREFIX}/{ARCHIVE_ID}/artifact?kind={kind}", headers=a_headers)
            assert foreign.status_code == 404, foreign.text
        assert http.get(f"{PREFIX}/{ARCHIVE_ID}", headers=a_headers).status_code == 404
        assert http.get(f"{PREFIX}/{a_id}", headers=b_headers).status_code == 404
        assert [j["job_id"] for j in http.get(PREFIX, headers=a_headers).json()["jobs"]] == [a_id]
        b_job = b_jobs.json()["jobs"][0]
        decision = {
            "request_digest": b_job["request_digest"],
            "admission_digest": b_job["admission"]["digest"],
            "report_digest": b_job["report"]["digest"],
            "disposition": "reject",
            "reason": "Cross-user mutation must fail",
        }
        assert (
            http.post(
                f"{PREFIX}/{ARCHIVE_ID}/decision",
                headers={**a_headers, "Idempotency-Key": str(uuid4())},
                json=decision,
            ).status_code
            == 404
        )
        assert (
            http.post(
                PREFIX,
                headers={**a_headers, "Idempotency-Key": str(uuid4())},
                json={"user_id": invite_b["user"]["user_id"]},
            ).status_code
            == 422
        )
        for kind, raw in original_artifacts.items():
            assert (
                http.get(f"{PREFIX}/{ARCHIVE_ID}/artifact?kind={kind}", headers=ADMIN).content
                == raw
            )
            assert (
                http.get(f"{PREFIX}/{ARCHIVE_ID}/artifact?kind={kind}", headers=b_headers).content
                == raw
            )
        revoked = http.post(f"/api/beta/users/{invite_b['user']['user_id']}/revoke", headers=ADMIN)
        assert revoked.status_code == 200
        assert (
            http.get(f"{PREFIX}/{ARCHIVE_ID}/artifact?kind=report", headers=b_headers).status_code
            == 401
        )
        assert http.get(f"{PREFIX}/{a_id}", headers=a_headers).status_code == 200
    assert all(service._closed for service in services)
    # A normal app lifespan closes every lease. A new app reuses persisted
    # sessions and Native originals, without a registration factory or execution.
    reopened = beta_module.BetaAccess(
        tmp_path / "accounts",
        operator_token=SecretStr(ADMIN["Authorization"].removeprefix("Bearer ")),
    )
    fresh_app = create_workstation_app(
        account=PaperAccount(cash=100_000),
        native_daily_service=NativeDailyService(operator_root),
        beta_access=reopened,
    )
    with TestClient(fresh_app, base_url=ORIGIN) as http:
        assert http.get(f"{PREFIX}/{a_id}", headers=a_headers).json() == a_job.json()
        assert http.get(f"{PREFIX}/{ARCHIVE_ID}", headers=a_headers).status_code == 404
        assert http.get(f"{PREFIX}/{ARCHIVE_ID}", headers=b_headers).status_code == 401
        for kind, raw in original_artifacts.items():
            assert (
                http.get(f"{PREFIX}/{ARCHIVE_ID}/artifact?kind={kind}", headers=ADMIN).content
                == raw
            )
