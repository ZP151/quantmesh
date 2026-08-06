from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Venue(StrEnum):
    INTERNAL = "internal"
    MOOMOO = "moomoo"
    HYPERLIQUID = "hyperliquid"
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


class InstrumentType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    PERPETUAL = "perpetual"
    SPOT = "spot"
    EVENT_CONTRACT = "event_contract"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Instrument(BaseModel):
    symbol: str
    venue: Venue
    instrument_type: InstrumentType
    currency: str = "USD"
    metadata: dict[str, str] = Field(default_factory=dict)


class Quote(BaseModel):
    instrument: Instrument
    timestamp: datetime
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: float | None = None


class OrderRequest(BaseModel):
    instrument: Instrument
    side: Side
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    paper: bool = True
    client_order_id: str | None = None


class Signal(BaseModel):
    instrument: Instrument
    timestamp: datetime
    action: Side | None = None
    expected_return: float
    confidence: float = Field(ge=0, le=1)
    rationale: str
    model_name: str
    model_version: str

