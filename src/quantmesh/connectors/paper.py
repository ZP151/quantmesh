from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from quantmesh.domain.models import Instrument, OrderRequest, Quote


class PaperConnector:
    """Minimal internal connector used before external execution is enabled."""

    venue = "internal"

    def __init__(self) -> None:
        self.orders: dict[str, OrderRequest] = {}

    async def get_quotes(self, instruments: Sequence[Instrument]) -> list[Quote]:
        return [Quote(instrument=item, timestamp=datetime.now(UTC)) for item in instruments]

    async def place_order(self, order: OrderRequest) -> str:
        order_id = order.client_order_id or f"paper-{uuid4()}"
        self.orders[order_id] = order
        return order_id

