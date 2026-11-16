"""Opt-in HTTP/WS boundary and Operator invitation/session API."""

import asyncio
import re
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from quantmesh.api.research_jobs import _SafeRoute
from quantmesh.auth.beta import SESSION_SECONDS, BetaError

COOKIE = "qm_beta_session"
_STATUSES = {
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "capacity_exceeded": 409,
    "invitation_consumed": 409,
    "invalid_request": 422,
}
_NATIVE = "/api/research/native-daily"


def refusal(error):
    return HTTPException(
        _STATUSES.get(error.code, 503),
        error.code if error.code in _STATUSES else "auth_unavailable",
    )


class _BetaRoute(_SafeRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                if request.method == "POST":
                    from quantmesh.research.native_daily_real import _loads

                    raw = bytearray()
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > 8192:
                            raise HTTPException(422, "invalid_request")
                        raw.extend(chunk)
                    try:
                        _loads(raw or b"{}")
                    except (ValueError, TypeError, RecursionError):
                        raise HTTPException(422, "invalid_request") from None

                    async def receive():
                        return {
                            "type": "http.request",
                            "body": bytes(raw or b"{}"),
                            "more_body": False,
                        }

                    request = Request(request.scope, receive)
                return await handler(request)
            except BetaError as error:
                raise refusal(error) from None
            except RequestValidationError:
                raise HTTPException(422, "invalid_request") from None

        return guarded


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateUser(_Body):
    display_name: str = Field(min_length=1, max_length=80, strict=True)


class ExchangeSession(_Body):
    invitation_token: SecretStr | None = None


class PublicUser(_Body):
    user_id: str
    display_name: str
    role: Literal["operator", "tester"]
    state: Literal["invited", "active", "revoked"]
    created_at: int


class Invitation(_Body):
    token: str
    expires_at: int


class CreatedUser(_Body):
    user: PublicUser
    invitation: Invitation


class Users(_Body):
    users: list[PublicUser] = Field(max_length=33)


class SessionCreated(_Body):
    user: PublicUser
    expires_at: int


class CurrentUser(_Body):
    user: PublicUser
    expires_at: int | None


def create_beta_router(access):
    router = APIRouter(prefix="/api/beta", route_class=_BetaRoute)

    @router.post("/users", status_code=201, response_model=CreatedUser)
    def create(body: CreateUser, request: Request):
        try:
            return access.create_user(request.state.beta_principal, body.display_name)
        except BetaError as error:
            raise refusal(error) from None

    @router.get("/users", response_model=Users)
    def users(request: Request):
        try:
            return access.users(request.state.beta_principal)
        except BetaError as error:
            raise refusal(error) from None

    @router.post("/users/{user_id}/revoke", response_model=PublicUser)
    def revoke(user_id: str, request: Request):
        try:
            return access.revoke(request.state.beta_principal, user_id)
        except BetaError as error:
            raise refusal(error) from None

    @router.post("/sessions", status_code=201, response_model=SessionCreated)
    def exchange(body: ExchangeSession, request: Request, response: Response):
        try:
            if body.invitation_token is not None:
                if request.headers.get("authorization") is not None:
                    raise BetaError("invalid_request")
                token, value = access.exchange(body.invitation_token.get_secret_value())
            else:
                principal = access.authenticate(request.headers.get("authorization"), None)
                token, value = access.operator_session(principal)
            response.set_cookie(
                COOKIE,
                token,
                max_age=SESSION_SECONDS,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
                path="/",
            )
            return value
        except BetaError as error:
            raise refusal(error) from None

    @router.get("/me", response_model=CurrentUser)
    def me(request: Request):
        try:
            return access.me(request.state.beta_principal)
        except BetaError as error:
            raise refusal(error) from None

    @router.delete("/session", status_code=204)
    def logout(request: Request, response: Response):
        try:
            access.logout(request.state.beta_principal)
            response.delete_cookie(
                COOKIE,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
                path="/",
            )
        except BetaError as error:
            raise refusal(error) from None

    return router


def _tester_route(path, method):
    if path == "/api/beta/me" and method == "GET":
        return True
    if path == "/api/beta/session" and method == "DELETE":
        return True
    if method == "GET" and path in {_NATIVE + "/options", _NATIVE + "/jobs"}:
        return True
    if method == "POST" and path == _NATIVE + "/jobs":
        return True
    suffix = r"/[0-9a-fA-F-]{36}"
    if method == "GET":
        return (
            re.fullmatch(re.escape(_NATIVE + "/jobs") + suffix + r"(?:/artifact)?", path)
            is not None
        )
    return (
        method == "POST"
        and re.fullmatch(re.escape(_NATIVE + "/jobs") + suffix + "/decision", path) is not None
    )


class BetaBoundary:
    def __init__(self, app, *, access):
        self.app, self.access = app, access

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        path, method = scope["path"], scope.get("method", "GET")

        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ] + [(b"cache-control", b"private, no-store")]
            await send(message)

        try:
            public = (
                scope["type"] == "http"
                and method in {"GET", "HEAD"}
                and (path == "/app" or path.startswith("/app/") or path.startswith("/static/"))
            )
            if not public:
                if len(headers.getlist("authorization")) > 1:
                    raise BetaError("unauthorized")
                request = Request({**scope, "type": "http"})
                cookie = request.cookies.get(COOKIE)
                authorization = headers.get("authorization")
                if scope["type"] == "websocket" or method not in {"GET", "HEAD", "OPTIONS"}:
                    origin = headers.get("origin")
                    if origin is not None or (cookie is not None and authorization is None):
                        from quantmesh.api.workstation import _is_allowed_browser_origin

                        if origin is None or not _is_allowed_browser_origin(origin):
                            raise BetaError("forbidden")
                        parsed = urlsplit(origin)
                        if (
                            parsed.scheme
                            != ("https" if scope["scheme"] in {"https", "wss"} else "http")
                            or parsed.netloc.lower() != headers.get("host", "").lower()
                        ):
                            raise BetaError("forbidden")
                login = (
                    scope["type"] == "http" and path == "/api/beta/sessions" and method == "POST"
                )
                if not login:
                    principal = await run_in_threadpool(
                        self.access.authenticate, authorization, cookie
                    )
                    scope.setdefault("state", {})["beta_principal"] = principal
                    if principal.role != "operator" and (
                        scope["type"] == "websocket" or not _tester_route(path, method)
                    ):
                        raise BetaError("forbidden")
            return await self.app(scope, receive, private_send)
        except BetaError as error:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                exception = refusal(error)
                await JSONResponse({"detail": exception.detail}, status_code=exception.status_code)(
                    scope, receive, private_send
                )


class ScopedNative:
    def __init__(self, access, principal, original):
        self.access, self.principal, self.original = access, principal, original

    def __getattr__(self, name):
        if name not in {"options", "submit", "list_jobs", "read", "artifact", "decide"}:
            raise AttributeError(name)

        def call(*args):
            try:
                return self.access.native_call(self.principal, self.original, name, *args)
            except BetaError as error:
                raise refusal(error) from None

        return call


def attach_beta_access(app, access):
    original = app.router.lifespan_context
    app.state.beta_access = access
    app.include_router(create_beta_router(access))
    app.add_middleware(BetaBoundary, access=access)

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original(app):
                yield
        finally:
            task = asyncio.create_task(asyncio.to_thread(access.close))
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            task.result()

    app.router.lifespan_context = lifespan
