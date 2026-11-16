"""Opt-in account boundary: no external recipients, servers or credentials."""

import asyncio
import importlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.research.native_daily_real import NativeDailyService

ORIGIN = "http://localhost:8000"
ADMIN = {"Authorization": "Bearer test-only-bootstrap-token-32-bytes"}


@pytest.fixture
def beta_module():
    try:
        return importlib.import_module("quantmesh.auth.beta")
    except ModuleNotFoundError as error:
        if error.name not in {"quantmesh.auth", "quantmesh.auth.beta"}:
            raise
        pytest.fail("Beta account implementation is absent", pytrace=False)


@pytest.fixture
def beta_app(tmp_path, beta_module):
    clock = [2_000_000_000]
    access = beta_module.BetaAccess(
        tmp_path / "accounts",
        operator_token=SecretStr(ADMIN["Authorization"].removeprefix("Bearer ")),
        clock=lambda: clock[0],
    )
    original = NativeDailyService(tmp_path / "operator")
    app = create_workstation_app(
        account=PaperAccount(cash=100_000), native_daily_service=original, beta_access=access
    )
    with TestClient(app, base_url=ORIGIN) as http:
        yield http, access, clock


def invitation(http, name="Tester"):
    result = http.post("/api/beta/users", headers=ADMIN, json={"display_name": name})
    assert result.status_code == 201, result.text
    return result.json()


def login(http, invite):
    response = http.post(
        "/api/beta/sessions",
        headers={"Origin": ORIGIN},
        json={"invitation_token": invite["invitation"]["token"]},
    )
    assert response.status_code == 201, response.text
    return response


def test_invite_session_revoke_and_hashed_storage(beta_app):
    http, access, _ = beta_app
    invite = invitation(http, "研究测试者")
    result = login(http, invite)
    session = http.cookies.get("qm_beta_session")
    assert "HttpOnly" in result.headers["set-cookie"]
    assert "SameSite=strict" in result.headers["set-cookie"]
    assert "Path=/" in result.headers["set-cookie"]
    assert session not in result.text
    assert result.json()["user"]["role"] == "tester"
    assert result.json()["user"]["state"] == "active"
    assert http.get("/api/beta/me").json()["user"]["user_id"] == invite["user"]["user_id"]
    assert http.get("/api/beta/users").status_code == 403
    assert http.get("/api/beta/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    repeat = http.post(
        "/api/beta/sessions",
        headers={"Origin": ORIGIN},
        json={"invitation_token": invite["invitation"]["token"]},
    )
    assert repeat.status_code == 409
    records = http.get("/api/beta/users", headers=ADMIN)
    assert records.status_code == 200
    assert "digest" not in records.text and "token" not in records.text
    revoke = http.post(f"/api/beta/users/{invite['user']['user_id']}/revoke", headers=ADMIN)
    assert revoke.status_code == 200, revoke.text
    assert http.get("/api/beta/me").status_code == 401
    assert http.get("/api/research/native-daily/jobs").status_code == 401
    for path in access.root.rglob("*"):
        if path.is_file() and path.name != ".writer.lock":
            raw = path.read_bytes()
            for credential in (
                session,
                invite["invitation"]["token"],
                ADMIN["Authorization"].removeprefix("Bearer "),
            ):
                assert credential.encode() not in raw


@pytest.mark.parametrize(
    "path",
    [
        "/api/account",
        "/account",
        "/api/markets",
        "/docs",
        "/openapi.json",
        "/api/research/job-options",
    ],
)
def test_unauthenticated_and_tester_cannot_fall_through_other_surfaces(beta_app, path):
    http, _, _ = beta_app
    assert http.get(path, follow_redirects=False).status_code == 401
    login(http, invitation(http))
    assert http.get(path, follow_redirects=False).status_code == 403
    assert http.post(path, json={}, headers={"Origin": ORIGIN}).status_code == 403
    assert http.get("/app/research/jobs").status_code == 200


def test_websocket_boundary_rejects_testers(beta_app):
    http, _, _ = beta_app
    login(http, invitation(http))
    with pytest.raises(WebSocketDisconnect) as error:
        with http.websocket_connect("ws://localhost:8000/ws/quotes"):
            pytest.fail("tester websocket admitted")
    assert error.value.code == 1008


def test_cookie_writes_require_exact_origin_and_logout_invalidates_session(beta_app):
    http, _, _ = beta_app
    login(http, invitation(http))
    session = http.cookies.get("qm_beta_session")
    for origin in (None, "http://localhost:9999", "null", "https://evil.invalid"):
        headers = {} if origin is None else {"Origin": origin}
        assert http.delete("/api/beta/session", headers=headers).status_code == 403
    result = http.delete("/api/beta/session", headers={"Origin": ORIGIN})
    assert result.status_code == 204
    assert not http.cookies.get("qm_beta_session")
    assert (
        http.get("/api/beta/me", headers={"Authorization": f"Bearer {session}"}).status_code == 401
    )


def test_operator_session_is_not_returned_and_cannot_revoke_operator(beta_app):
    http, _, _ = beta_app
    result = http.post("/api/beta/sessions", headers=ADMIN, json={})
    assert result.status_code == 201, result.text
    assert result.json()["user"]["role"] == "operator"
    assert http.get("/api/markets").status_code == 200
    assert (
        http.post("/api/beta/users/operator/revoke", headers={"Origin": ORIGIN}).status_code == 403
    )
    assert http.delete("/api/beta/session", headers=ADMIN).status_code == 422


def test_invitation_and_session_expiry(beta_app):
    http, _, clock = beta_app
    first = invitation(http)
    clock[0] += 24 * 3600
    assert (
        http.post(
            "/api/beta/sessions", json={"invitation_token": first["invitation"]["token"]}
        ).status_code
        == 401
    )
    login(http, invitation(http, "Second"))
    clock[0] += 8 * 3600
    assert http.get("/api/beta/me").status_code == 401


def test_single_use_invitation_race_and_cold_session(tmp_path, beta_module):
    root = tmp_path / "accounts"
    secret = SecretStr(ADMIN["Authorization"].removeprefix("Bearer "))
    access = beta_module.BetaAccess(root, operator_token=secret)
    principal = access.authenticate(ADMIN["Authorization"], None)
    created = access.create_user(principal, "Race")

    def redeem(_):
        try:
            return access.exchange(created["invitation"]["token"])
        except beta_module.BetaError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, range(2)))
    successful = [item for item in results if not isinstance(item, str)]
    assert len(successful) == 1 and results.count("invitation_consumed") == 1
    token, _ = successful[0]
    access.close()
    reopened = beta_module.BetaAccess(root, operator_token=secret)
    try:
        assert reopened.authenticate(f"Bearer {token}", None).user_id == created["user"]["user_id"]
        reopened.revoke(
            reopened.authenticate(ADMIN["Authorization"], None), created["user"]["user_id"]
        )
        with pytest.raises(beta_module.BetaError, match="unauthorized"):
            reopened.authenticate(f"Bearer {token}", None)
    finally:
        reopened.close()


def test_payload_rejects_owner_role_and_oversize_input_without_echo(beta_app):
    http, _, _ = beta_app
    for payload in (
        {"display_name": "A", "role": "operator"},
        {"display_name": "A", "user_id": "operator"},
        {"display_name": " "},
        {"display_name": "X" * 9000},
    ):
        result = http.post("/api/beta/users", headers=ADMIN, json=payload)
        assert result.status_code == 422, result.text
        assert result.json() == {"detail": "invalid_request"}
    assert http.get("/api/beta/me").headers["cache-control"] == "private, no-store"


def test_personal_mode_remains_unauthenticated_and_beta_requires_original_service(
    tmp_path, beta_module
):
    with TestClient(create_workstation_app(account=PaperAccount(cash=100_000))) as http:
        assert http.get("/api/markets").status_code == 200
        assert http.get("/api/beta/me").status_code == 404
    access = beta_module.BetaAccess(
        tmp_path / "accounts", operator_token=SecretStr("test-only-bootstrap-token-32-bytes")
    )
    try:
        with pytest.raises(ValueError):
            create_workstation_app(account=PaperAccount(cash=100_000), beta_access=access)
    finally:
        access.close()


def test_storage_failure_is_sanitized_and_never_falls_through(beta_app, monkeypatch):
    http, access, _ = beta_app

    def broken():
        raise OSError("private-root-and-secret-must-not-appear")

    monkeypatch.setattr(access._lease, "validate", broken)
    result = http.get("/api/beta/me", headers=ADMIN)
    assert result.status_code == 503
    assert result.json() == {"detail": "auth_unavailable"}
    assert "private-root" not in result.text


def test_caps_fail_without_consuming_invitation_or_evicting_sessions(
    beta_app, beta_module, monkeypatch
):
    http, _, _ = beta_app
    monkeypatch.setattr(beta_module, "MAX_TESTERS", 1)
    created = invitation(http)
    assert (
        http.post("/api/beta/users", headers=ADMIN, json={"display_name": "Extra"}).status_code
        == 409
    )
    monkeypatch.setattr(beta_module, "MAX_SESSIONS", 0)
    result = http.post(
        "/api/beta/sessions", json={"invitation_token": created["invitation"]["token"]}
    )
    assert result.status_code == 409
    monkeypatch.setattr(beta_module, "MAX_SESSIONS", 1)
    login(http, created)
    assert http.get("/api/beta/me").status_code == 200


def test_revoke_waits_for_guarded_operation_and_rejects_stale_principal(tmp_path, beta_module):
    access = beta_module.BetaAccess(
        tmp_path / "accounts",
        operator_token=SecretStr(ADMIN["Authorization"].removeprefix("Bearer ")),
    )
    admin = access.authenticate(ADMIN["Authorization"], None)
    created = access.create_user(admin, "Concurrent")
    token, _ = access.exchange(created["invitation"]["token"])
    principal = access.authenticate(f"Bearer {token}", None)
    entered, release, revoke_started = threading.Event(), threading.Event(), threading.Event()
    events = []

    def work():
        entered.set()
        assert release.wait(2)
        events.append("work")

    def revoke():
        revoke_started.set()
        access.revoke(admin, principal.user_id)
        events.append("revoke")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(access.guard, principal, work)
            assert entered.wait(2)
            revoking = pool.submit(revoke)
            assert revoke_started.wait(2)
            assert not revoking.done()
            release.set()
            running.result(timeout=2)
            revoking.result(timeout=2)
        assert events == ["work", "revoke"]
        with pytest.raises(beta_module.BetaError, match="unauthorized"):
            access.guard(principal, lambda: pytest.fail("stale operation ran"))
    finally:
        release.set()
        access.close()


def test_secure_cookie_duplicate_auth_and_mixed_login(beta_app):
    http, _, _ = beta_app
    created = invitation(http)
    assert (
        http.post(
            "/api/beta/sessions",
            headers=ADMIN,
            json={"invitation_token": created["invitation"]["token"]},
        ).status_code
        == 422
    )
    assert (
        http.get(
            "/api/beta/me",
            headers=[("Authorization", ADMIN["Authorization"]), ("Authorization", "Bearer bad")],
        ).status_code
        == 401
    )
    with TestClient(http.app, base_url="https://localhost:8000") as secure:
        result = secure.post(
            "/api/beta/sessions", json={"invitation_token": created["invitation"]["token"]}
        )
        assert result.status_code == 201, result.text
        assert "Secure" in result.headers["set-cookie"]


def test_registry_refuses_hardlinked_database(tmp_path, beta_module):
    root = tmp_path / "accounts"
    root.mkdir()
    unrelated = tmp_path / "unrelated"
    unrelated.write_bytes(b"not a registry")
    os.link(unrelated, root / "accounts.sqlite")
    with pytest.raises(beta_module.BetaError, match="auth_unavailable"):
        beta_module.BetaAccess(root, operator_token=SecretStr("test-only-bootstrap-token-32-bytes"))


def test_registry_disappearance_refuses_old_connection(beta_app, monkeypatch):
    http, access, _ = beta_app
    # Windows holds the DB against rename; simulate a missing named path portably.
    original_stat = type(access._db_path).stat

    def missing(path, *args, **kwargs):
        if path == access._db_path:
            raise FileNotFoundError("auth database disappeared")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(type(access._db_path), "stat", missing)
    result = http.get("/api/beta/me", headers=ADMIN)
    assert result.status_code == 503
    assert result.json() == {"detail": "auth_unavailable"}


def test_openapi_declares_identity_and_one_time_invitation_response(beta_app):
    http, _, _ = beta_app
    schema = http.get("/openapi.json", headers=ADMIN).json()
    response = schema["paths"]["/api/beta/users"]["post"]["responses"]["201"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreatedUser"
    }
    session = schema["components"]["schemas"]["SessionCreated"]["properties"]
    assert set(session) == {"user", "expires_at"}
    user = schema["components"]["schemas"]["PublicUser"]["properties"]
    assert set(user) == {"user_id", "display_name", "role", "state", "created_at"}


def test_operator_cookie_websocket_refuses_other_loopback_origin(beta_app):
    http, _, _ = beta_app

    @http.app.websocket("/beta-test")
    async def socket(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("operator-only")
        await websocket.close()

    assert http.post("/api/beta/sessions", headers=ADMIN, json={}).status_code == 201
    with http.websocket_connect(
        "ws://localhost:8000/beta-test", headers={"Origin": ORIGIN}
    ) as websocket:
        assert websocket.receive_text() == "operator-only"
    with pytest.raises(WebSocketDisconnect) as error:
        with http.websocket_connect(
            "ws://localhost:8000/beta-test", headers={"Origin": "http://localhost:9999"}
        ):
            pytest.fail("cross-origin operator socket admitted")
    assert error.value.code == 1008


def test_authentication_wait_does_not_block_application_event_loop(beta_app, monkeypatch):
    http, access, _ = beta_app
    release = threading.Event()
    original = access.authenticate

    def waits_for_other_request(*args):
        assert release.wait(0.5), "authentication blocked the application event loop"
        return original(*args)

    monkeypatch.setattr(access, "authenticate", waits_for_other_request)

    async def request_and_release():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=http.app), base_url=ORIGIN
        ) as client:
            pending = asyncio.create_task(client.get("/api/beta/me", headers=ADMIN))
            await asyncio.sleep(0)
            release.set()
            return await pending

    assert asyncio.run(request_and_release()).status_code == 200
