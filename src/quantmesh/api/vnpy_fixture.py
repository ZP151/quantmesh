"""Explicit opt-in local vn.py fixture composition and standalone launcher."""

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request

from quantmesh.api.research_jobs import _SafeRoute
from quantmesh.research.vnpy_fixture import FixtureManager, FixtureRequest, options


def create_vnpy_fixture_router(manager: FixtureManager | None) -> APIRouter:
    router = APIRouter(prefix="/research/vnpy-fixture", route_class=_SafeRoute)

    def configured():
        if manager is None:
            raise HTTPException(503, "fixture_runtime_unavailable")
        return manager

    def call(operation, *args):
        try:
            return operation(*args)
        except KeyError:
            raise HTTPException(404, "job_unknown") from None
        except ValueError as exc:
            code = str(exc)
            safe = {
                "idempotency_conflict",
                "capacity_exceeded",
                "report_unavailable",
                "report_invalid",
                "service_closed",
            }
            raise HTTPException(
                409 if code in safe else 503,
                code if code in safe else "fixture_runtime_unavailable",
            ) from None
        except OSError:
            raise HTTPException(503, "fixture_runtime_unavailable") from None

    @router.get("/options")
    def get_options():
        configured()
        return options()

    @router.post("/jobs", status_code=202)
    def submit(request: FixtureRequest, idempotency_key: UUID = Header()):
        return call(configured().submit, request, str(idempotency_key))

    @router.get("/jobs/{job_id}")
    def get_job(job_id: UUID):
        return call(configured().get, str(job_id))

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: UUID):
        return call(configured().cancel, str(job_id))

    @router.get("/jobs/{job_id}/report")
    def get_report(job_id: UUID):
        return call(configured().report, str(job_id))

    return router


def attach_fixture_runtime(app: FastAPI, manager: FixtureManager) -> None:
    """Attach one admitted manager while retaining the workstation's lifecycle."""
    from quantmesh.api.workstation import _json_guard_origin

    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with existing_lifespan(app):
                yield
        finally:
            manager.close()

    app.router.lifespan_context = lifespan

    def guard_fixture_write(request: Request) -> None:
        if request.method == "POST":
            _json_guard_origin(request, "vn.py fixture")

    app.include_router(
        create_vnpy_fixture_router(manager),
        prefix="/api",
        dependencies=[Depends(guard_fixture_write)],
    )


def create_fixture_app(manager: FixtureManager):
    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount

    app = create_workstation_app(account=PaperAccount(cash=100000), host="127.0.0.1")
    attach_fixture_runtime(app, manager)
    return app


def main(argv: list[str] | None = None):
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Local-only vn.py synthetic fixture experiment")
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    manager = FixtureManager(args.python, args.fixture, args.root)
    uvicorn.run(create_fixture_app(manager), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
