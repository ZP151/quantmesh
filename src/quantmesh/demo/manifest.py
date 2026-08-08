"""The deterministic demo scenario (iteration 0014 Phase B).

One manifest is the single source of truth for what a demo root
contains: the instrument universe (equities on moomoo, crypto
perpetual/spot on hyperliquid, prediction markets on kalshi and
polymarket), the fixed scenario anchor, and the per-surface row
counts. Everything the seeder emits — fixture files, ledger lines,
paper orders — derives from this manifest plus the fixed RNG seed, so
the same manifest + seed always produces the identical demo root
(replay/reset guarantee) and the demo root can never drift into an
operator's non-demo data dirs.

Prediction-market instruments seed through the events/forecast/report
services (their natural surfaces); their continuous-time venue data is
recorded vendor wire payloads that Phase D's credential-free public
paths replace with live captures. Equities and crypto seed full
deterministic bars/order books/trades through the real fixture
providers, so the provider pipeline — the "public domain services"
path — serves the demo like any other venue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# The fixed scenario anchor: every seeded timestamp derives from this,
# never from the wall clock, so two seeds of the same manifest are
# byte-identical.
ANCHOR = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
MARKET_OPEN = datetime(2026, 8, 3, 13, 30, 0, tzinfo=UTC)  # five sessions back

# Bars per symbol in the fixture files; one bar per session, 5 sessions.
SESSIONS = 5
BAR_COUNT = SESSIONS

# Deterministic pseudo-random draws are shared across symbols so the
# cross-market relationships below are reproducible by construction.
CROSS_MARKET_CLUSTER = {
    "BTC-USD": "crypto",
    "ETH-USD": "crypto",
    "SOL-USD": "crypto",
    "DOGE-USD": "crypto",
}


@dataclass(frozen=True)
class InstrumentSpec:
    """One seeded instrument: venue, symbol, and its deterministic base."""

    venue: str
    symbol: str
    kind: str  # equity | crypto_perp | crypto_spot | binary_market | categorical_market
    base_price: float
    annual_vol: float  # per-bar volatility budget for the walk


EQUITIES = (
    InstrumentSpec("moomoo", "AAPL", "equity", 210.0, 0.012),
    InstrumentSpec("moomoo", "MSFT", "equity", 415.0, 0.011),
    InstrumentSpec("moomoo", "NVDA", "equity", 118.0, 0.020),
    InstrumentSpec("moomoo", "TSLA", "equity", 245.0, 0.024),
    InstrumentSpec("moomoo", "AMZN", "equity", 182.0, 0.013),
    InstrumentSpec("moomoo", "META", "equity", 510.0, 0.014),
)

CRYPTO = (
    # Hyperliquid lists perps and spot at the same ticker; the perp is
    # the liquid instrument, so the spot series mirrors it one venue
    # apart (the seeded cross-market relationship).
    InstrumentSpec("hyperliquid", "BTC-USD", "crypto_perp", 65_000.0, 0.018),
    InstrumentSpec("hyperliquid", "ETH-USD", "crypto_perp", 3_200.0, 0.020),
    InstrumentSpec("hyperliquid", "SOL-USD", "crypto_perp", 148.0, 0.028),
    InstrumentSpec("hyperliquid", "DOGE-USD", "crypto_perp", 0.128, 0.032),
)

PREDICTION = (
    # These seed through the events/forecast services (Phase B), not
    # fixture payloads: the kalshi/polymarket wire captures stay the
    # recorded vendor authority until Phase D's public paths land.
    ("kalshi", "KXFED25-RATE", "Fed funds rate above 4.00% by Dec 2026", "binary_market", 0.62),
    ("kalshi", "KXELONMARS-26", "Elon Musk visits Mars before Aug 2026", "binary_market", 0.09),
    ("polymarket", "nba-champion-2026", "NBA 2026 champion market", "categorical_market", 0.55),
)

# How many rows each surface seeds; the browser walks these counts in
# Phase C, so they are part of the acceptance contract.
SURFACE_COUNTS = {
    "experiments": 6,
    "promotions": 3,
    "reports": 4,
    "forecasts": 4,
    "alerts": 5,
    "orders": 7,
    "decisions": 4,
    "mappings": 3,
    "documents": 3,
}

# The marker that identifies a demo root; the seeder and the reset
# endpoint refuse to touch a root that does not carry it (the
# never-touches-non-demo-root guarantee, enforced at the filesystem).
MARKER_NAME = "QUANTMESH_DEMO_ROOT"


@dataclass(frozen=True)
class DemoScenario:
    """A concrete scenario: the manifest with its anchor and seed.

    `seed` drives every deterministic draw; `anchor` and `open` pin
    all timestamps. Two scenarios differing only in the random seed
    produce differently-priced but identically-structured roots.
    """

    seed: int = 20260809
    anchor: datetime = ANCHOR
    open: datetime = MARKET_OPEN
    equities: tuple[InstrumentSpec, ...] = EQUITIES
    crypto: tuple[InstrumentSpec, ...] = CRYPTO
    prediction: tuple[tuple[str, str, str, str, float], ...] = PREDICTION
    surface_counts: dict[str, int] = field(default_factory=lambda: dict(SURFACE_COUNTS))
