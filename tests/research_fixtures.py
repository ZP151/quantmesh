"""Deterministic closed-form bar fixtures for research tests (issue #27).

Prices are pure functions of the bar index — no random generator, so
any backtest over these bars is byte-reproducible. The three symbols
have distinct characters: AAA trends up, BBB oscillates flat, CCC
trends down.
"""

import math
from datetime import UTC, datetime, timedelta

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

START = datetime(2026, 1, 5, tzinfo=UTC)

# symbol -> (base price, drift, amplitude); price(t) = base *
# (1 + drift * t / n + amplitude * sin(2*pi*t/14)) — the 14-bar cycle
# gives the oscillator character without any randomness.
SYMBOLS = {
    "AAA": (100.0, 0.15, 0.02),
    "BBB": (100.0, 0.0, 0.05),
    "CCC": (50.0, -0.08, 0.04),
}


def fixture_bars(symbol: str, n: int = 60) -> list[Bar]:
    """Hourly bars: 60 bars span three days, so the lake stores them as
    three date shards per symbol (ADR-0003 layout) instead of sixty —
    the walk-forward windows are count-based, so the interval change
    does not alter their meaning, only the fixture's cost.
    """
    base, drift, amplitude = SYMBOLS[symbol]
    instrument = Instrument(
        symbol=symbol,
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )
    return [
        Bar(
            instrument=instrument,
            timestamp=START + timedelta(hours=index),
            interval="1h",
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000.0,
        )
        for index in range(n)
        for price in [
            base * (1.0 + drift * index / n + amplitude * math.sin(2 * math.pi * index / 14))
        ]
    ]


def pinned_lake(root, *, name: str = "equities", n: int = 60) -> None:
    """A manifest-gated lake dataset over the fixture universe."""
    lake = Lake(root)
    for symbol in SYMBOLS:
        lake.write_bars(name, fixture_bars(symbol, n))
    ManifestWriter(root).generate(name, source="fixture", license="test")
