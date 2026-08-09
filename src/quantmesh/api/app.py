"""HTTP observability layer for the paper-trading kernel.

`create_app` binds a read-only API to one `PaperAccount`: account
summary, positions, orders and P&L. Mark prices are injected (never
fetched) so responses stay deterministic — the operator replaces
`app.state.marks` as new marks arrive. This layer is intentionally
read-only with respect to execution: no order placement, no control
endpoints.

Since M11 (ADR-0013) the kernel API is registered twice on the same
app: at the root paths (the RC1 contract, pinned by `test_api.py`)
and under `/api` (the SPA surface the frontend calls). One router
registration serves both prefixes; handlers read state from
`request.app.state`, so both mounts see the same account and marks.
"""

from fastapi import APIRouter, FastAPI, HTTPException, Request

from quantmesh import __version__
from quantmesh.domain.orders import Order
from quantmesh.execution.accounting import PaperAccount
from quantmesh.settings import settings


def _health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "project": settings.app_name,
        "version": __version__,
        "paper_mode": settings.default_paper_mode,
        "live_trading": settings.allow_live_trading,
    }


def _order_summary(order: Order) -> dict:
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "instrument": order.instrument.model_dump(mode="json"),
        "side": order.side.value,
        "quantity": order.quantity,
        "order_type": order.order_type.value,
        "limit_price": order.limit_price,
        "status": order.status.value,
        "filled_quantity": order.filled_quantity,
        "average_fill_price": order.average_fill_price,
        "created_at": order.created_at.isoformat(),
        "events": [
            {
                "sequence": event.sequence,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "status": event.status.value,
                "quantity": event.quantity,
                "price": event.price,
                "reason": event.reason,
            }
            for event in order.events
        ],
    }


def observability_router() -> APIRouter:
    """The read-only kernel API (ADR-0013 Decision 1).

    Mounted at the root (RC1 contract) and under ``/api`` (the SPA
    surface). Handlers read ``request.app.state`` so one registration
    serves both prefixes with the same state.
    """
    router = APIRouter()

    @router.get("/health")
    def health(request: Request) -> dict[str, str | bool]:
        payload = _health()
        payload["runtime_mode"] = (
            "demo"
            if hasattr(request.app.state, "demo")
            else "live"
            if hasattr(request.app.state, "live")
            else "operator"
        )
        return payload

    @router.get("/account")
    def account_summary(request: Request) -> dict:
        current = request.app.state.account
        return {
            "cash": current.cash,
            "starting_cash": (
                current.starting_cash
                if current.starting_cash is not None
                else current.cash
            ),
            "total_fees": current.total_fees,
            "kill_switch": current.kill_switch,
            "order_sequence": current.order_sequence,
        }

    @router.get("/positions")
    def positions(request: Request) -> list[dict]:
        marks = dict(request.app.state.marks)
        return [
            {
                "key": key,
                "instrument": position.instrument.model_dump(mode="json"),
                "quantity": position.quantity,
                "average_cost": position.average_cost,
                "realized_pnl": position.realized_pnl,
                "unrealized_pnl": (
                    (marks[key] - position.average_cost) * position.quantity
                    if key in marks
                    else None
                ),
            }
            for key, position in request.app.state.account.positions.items()
        ]

    @router.get("/orders")
    def orders(request: Request) -> list[dict]:
        return [
            _order_summary(order)
            for order in request.app.state.account.orders.values()
        ]

    @router.get("/orders/{order_id}")
    def order(request: Request, order_id: str) -> dict:
        current = request.app.state.account.orders.get(order_id)
        if current is None:
            raise HTTPException(status_code=404, detail=f"unknown order {order_id}")
        return _order_summary(current)

    @router.get("/pnl")
    def pnl(request: Request) -> dict:
        current = request.app.state.account
        marks = dict(request.app.state.marks)
        return {
            "starting_cash": (
                current.starting_cash
                if current.starting_cash is not None
                else current.cash
            ),
            "realized_pnl": current.realized_pnl,
            "unrealized_pnl": current.unrealized_pnl(marks),
            "equity": current.equity(marks),
            "total_pnl": current.total_pnl(marks),
            "marks": marks,
            # Positions without a mark are excluded from equity-based
            # numbers; name them so understated equity is never silent.
            "missing_marks": sorted(
                key for key in current.positions if key not in marks
            ),
        }

    @router.get("/kill-switch")
    def kill_switch(request: Request) -> dict[str, object]:
        # M10 Phase C (issue #60): the global bit plus the per-venue
        # map, both read from the account object the control flips —
        # the JSON surface, the page context and the kernel gate are
        # the same state by construction.
        current = request.app.state.account
        return {
            "kill_switch": current.kill_switch,
            "kill_switches": {
                venue.value: engaged
                for venue, engaged in sorted(current.kill_switches.items())
            },
        }

    return router


def create_app(
    *, account: PaperAccount, marks: dict[str, float] | None = None
) -> FastAPI:
    """A read-only observability app bound to one paper account.

    `marks` is held by reference: mutating it after creation is the way
    the operator supplies updated mark prices. The kernel API is served
    at the root (RC1 contract) and under `/api` (ADR-0013 SPA surface).
    """
    app = FastAPI(title=settings.app_name, version=__version__)
    app.state.account = account
    app.state.marks = marks if marks is not None else {}
    router = observability_router()
    app.include_router(router)
    # The /api surface (ADR-0013) serves the same handlers under a
    # distinct prefix; operation ids are prefixed so /openapi.json
    # (the typed-client source) has no duplicates.
    app.include_router(
        router,
        prefix="/api",
        generate_unique_id_function=lambda route: f"api_{route.name}",
    )
    return app


# Smoke-test bootstrap only (matches test_smoke.py). The operational
# surface is create_app(...), which binds the kernel endpoints to an
# account instance; keep them in sync if the factory grows routes.
app = FastAPI(title=settings.app_name, version=__version__)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return _health()
