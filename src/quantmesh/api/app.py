"""HTTP observability layer for the paper-trading kernel.

`create_app` binds a read-only API to one `PaperAccount`: account
summary, positions, orders and P&L. Mark prices are injected (never
fetched) so responses stay deterministic — the operator replaces
`app.state.marks` as new marks arrive. This layer is intentionally
read-only with respect to execution: no order placement, no control
endpoints.
"""

from fastapi import FastAPI, HTTPException

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


def create_app(
    *, account: PaperAccount, marks: dict[str, float] | None = None
) -> FastAPI:
    """A read-only observability app bound to one paper account.

    `marks` is held by reference: mutating it after creation is the way
    the operator supplies updated mark prices.
    """
    app = FastAPI(title=settings.app_name, version=__version__)
    app.state.account = account
    app.state.marks = marks if marks is not None else {}

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return _health()

    @app.get("/account")
    def account_summary() -> dict:
        current = app.state.account
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

    @app.get("/positions")
    def positions() -> list[dict]:
        marks = dict(app.state.marks)
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
            for key, position in app.state.account.positions.items()
        ]

    @app.get("/orders")
    def orders() -> list[dict]:
        return [_order_summary(order) for order in app.state.account.orders.values()]

    @app.get("/orders/{order_id}")
    def order(order_id: str) -> dict:
        current = app.state.account.orders.get(order_id)
        if current is None:
            raise HTTPException(status_code=404, detail=f"unknown order {order_id}")
        return _order_summary(current)

    @app.get("/pnl")
    def pnl() -> dict:
        current = app.state.account
        marks = dict(app.state.marks)
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

    @app.get("/kill-switch")
    def kill_switch() -> dict[str, bool]:
        return {"kill_switch": app.state.account.kill_switch}

    return app


# Smoke-test bootstrap only (matches test_smoke.py). The operational
# surface is create_app(...), which binds the kernel endpoints to an
# account instance; keep them in sync if the factory grows routes.
app = FastAPI(title=settings.app_name, version=__version__)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return _health()
