from collections.abc import Sequence
from typing import Protocol

from quantmesh.domain.models import Instrument, OrderRequest, Quote


class MarketConnector(Protocol):
    venue: str

    async def get_quotes(self, instruments: Sequence[Instrument]) -> list[Quote]: ...


class ExecutionConnector(MarketConnector, Protocol):
    async def place_order(self, order: OrderRequest) -> str: ...

