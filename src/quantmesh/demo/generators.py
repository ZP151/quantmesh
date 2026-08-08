"""Deterministic synthetic market series for the demo (iteration 0014).

Every draw comes from one ``random.Random`` seeded by the scenario, and
every timestamp from the scenario anchor — never the wall clock — so a
seed reproduces byte-identical fixture files. The cross-market
relationship is a shared per-session factor over the crypto cluster:
each symbol carries a beta on the common shock plus its own
idiosyncratic walk, so the seeded returns are correlated by
construction and the correlation is reproducible.

Rows are emitted in the exact fixture row shapes the real venue
adapters parse (moomoo/hyperliquid wire formats), so the demo market
data flows through the provider pipeline like any other venue; nothing
here knows about the UI. One series map per symbol is the single draw
source: the fixture closes, the order-book midpoints, the trade prices
and the served marks all derive from the same walk.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from quantmesh.demo.manifest import SESSIONS, DemoScenario, InstrumentSpec


class _Draw:
    """One deterministic draw stream per scenario."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def uniform(self, low: float, high: float) -> float:
        return self._rng.uniform(low, high)

    def normal(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return self._rng.gauss(mu, sigma)

    def choice(self, items: tuple[str, ...]) -> str:
        return self._rng.choice(items)

    def index(self, count: int) -> int:
        return self._rng.randrange(count)


def _round(value: float, places: int) -> float:
    return round(value, places)


def session_times(scenario: DemoScenario) -> list[datetime]:
    """One timestamp per seeded session, open + i trading days."""
    return [scenario.open + timedelta(days=i) for i in range(SESSIONS)]


def series_map(draw: _Draw, scenario: DemoScenario) -> dict[str, dict[str, list[float]]]:
    """The one draw source: venue -> symbol -> session closes.

    The crypto cluster shares a per-session factor (beta 1.0 on the
    common shock plus an idiosyncratic component), so the seeded
    cross-market relationship is real and reproducible.
    """
    series: dict[str, dict[str, list[float]]] = {}
    for spec in (*scenario.equities, *scenario.crypto):
        closes: list[float] = []
        price = spec.base_price
        for _ in range(SESSIONS):
            if spec.kind.startswith("crypto"):
                factor = draw.normal()  # shared cluster shock
                shock = 0.6 * factor + 0.8 * draw.normal()
            else:
                shock = draw.normal()
            price *= 1.0 + spec.annual_vol * shock / math.sqrt(252)
            closes.append(price)
        series.setdefault(spec.venue, {})[spec.symbol] = closes
    return series


def _equity_bars_rows(
    draw: _Draw, spec: InstrumentSpec, closes: list[float], times: list[datetime]
) -> list[dict]:
    """moomoo_bars.json rows: symbol/interval/datetime/open/high/low/close/volume."""
    rows = []
    previous = spec.base_price
    for index, (time, close) in enumerate(zip(times, closes)):
        open_ = previous if index else spec.base_price
        high = max(open_, close) * (1.0 + abs(draw.normal()) * 0.001)
        low = min(open_, close) * (1.0 - abs(draw.normal()) * 0.001)
        rows.append(
            {
                "symbol": spec.symbol,
                "interval": "1d",
                "datetime": time.isoformat(),
                "open": _round(open_, 2),
                "high": _round(high, 2),
                "low": _round(low, 2),
                "close": _round(close, 2),
                "volume": round(draw.uniform(200_000, 2_000_000), 0),
            }
        )
        previous = close
    return rows


def _crypto_bars_rows(
    draw: _Draw, spec: InstrumentSpec, closes: list[float], times: list[datetime]
) -> list[dict]:
    """hyperliquid_bars.json rows: t/o/h/l/c/v/i."""
    rows = []
    previous = spec.base_price
    for index, (time, close) in enumerate(zip(times, closes)):
        open_ = previous if index else spec.base_price
        high = max(open_, close) * (1.0 + abs(draw.normal()) * 0.002)
        low = min(open_, close) * (1.0 - abs(draw.normal()) * 0.002)
        rows.append(
            {
                "t": time.isoformat(),
                "o": _round(open_, 2),
                "h": _round(high, 2),
                "l": _round(low, 2),
                "c": _round(close, 2),
                "v": round(draw.uniform(10.0, 400.0), 4),
                "i": "1d",
            }
        )
        previous = close
    return rows


def _book_rows_equity(
    draw: _Draw, spec: InstrumentSpec, last_close: float, timestamp: datetime
) -> dict:
    """One order-book snapshot around the last close (moomoo shape)."""
    tick = spec.base_price * 0.0005
    spread = tick * (2 + draw.index(4))
    bids = [
        [_round(last_close - spread * (i + 1), 2), round(draw.uniform(50, 800), 0)]
        for i in range(3)
    ]
    asks = [
        [_round(last_close + spread * (i + 1), 2), round(draw.uniform(50, 800), 0)]
        for i in range(3)
    ]
    return {
        "symbol": spec.symbol,
        "datetime": timestamp.isoformat(),
        "bid_levels": bids,
        "ask_levels": asks,
    }


def _book_rows_crypto(
    draw: _Draw, spec: InstrumentSpec, last_close: float, timestamp: datetime
) -> dict:
    """One order-book snapshot (hyperliquid shape: bids/asks arrays).

    Prices round to 6dp: at sub-dollar tickers (DOGE) 2dp would
    collapse every level onto the same price, and the book's
    strictly-descending bids validator would refuse it.
    """
    tick = spec.base_price * 0.0002
    spread = tick * (2 + draw.index(4))
    bids = [
        [_round(last_close - spread * (i + 1), 6), round(draw.uniform(0.5, 40.0), 4)]
        for i in range(3)
    ]
    asks = [
        [_round(last_close + spread * (i + 1), 6), round(draw.uniform(0.5, 40.0), 4)]
        for i in range(3)
    ]
    return {"ts": timestamp.isoformat(), "bids": bids, "asks": asks}


def _trades_rows(
    draw: _Draw,
    spec: InstrumentSpec,
    last_close: float,
    times: list[datetime],
    *,
    hyperliquid: bool,
) -> list[dict]:
    """A few executed trades per symbol at deterministic prices."""
    rows = []
    tick = spec.base_price * (0.0005 if hyperliquid else 0.001)
    for index in range(3):
        side = draw.choice(("B", "S"))
        price = _round(last_close + draw.uniform(-1, 1) * tick, 2)
        quantity = _round(draw.uniform(1.0, 20.0), 2)
        if hyperliquid:
            rows.append(
                {
                    "t": times[index].isoformat(),
                    "px": price,
                    "sz": quantity,
                    "side": side,
                    "seq": 5000 + index,
                }
            )
        else:
            rows.append(
                {
                    "symbol": spec.symbol,
                    "datetime": times[index].isoformat(),
                    "price": price,
                    "quantity": quantity,
                    "side": side,
                    "seq": 5000 + index,
                }
            )
    return rows


def fixture_files(
    draw: _Draw,
    scenario: DemoScenario,
    series: dict[str, dict[str, list[float]]] | None = None,
) -> dict[tuple[str, str], dict[str, list[dict]]]:
    """Per-symbol fixture contents, keyed (venue, symbol) -> {file: rows}.

    The real fixture providers are symbol-scoped by design — one
    fixture file set serves exactly one symbol (the bundled fixtures
    are AAPL-only), so the demo writes one directory per symbol and
    the seeder constructs one real provider per symbol over it. The
    file names are the exact wire names the adapters load
    (moomoo_*/hyperliquid_*), and the draw stream stays in symbol
    order so the refactor never changes the seeded bytes.

    ``series`` must be the same map the caller's marks derive from:
    the draw stream is stateful, so a second ``series_map`` call would
    consume a *different* walk and the served closes would disagree
    with the board. The seeder passes the one map it built.
    """
    times = session_times(scenario)
    books_time = scenario.anchor - timedelta(minutes=1)
    series = series_map(draw, scenario) if series is None else series
    files: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for spec in (*scenario.equities, *scenario.crypto):
        closes = series[spec.venue][spec.symbol]
        if spec.kind == "equity":
            books = _book_rows_equity(draw, spec, closes[-1], books_time)
            files[(spec.venue, spec.symbol)] = {
                "moomoo_bars.json": _equity_bars_rows(draw, spec, closes, times),
                "moomoo_books.json": [books],
                "moomoo_trades.json": _trades_rows(
                    draw, spec, closes[-1], times, hyperliquid=False
                ),
            }
        else:
            books = _book_rows_crypto(draw, spec, closes[-1], books_time)
            files[(spec.venue, spec.symbol)] = {
                "hyperliquid_bars.json": _crypto_bars_rows(draw, spec, closes, times),
                "hyperliquid_books.json": [books],
                "hyperliquid_trades.json": _trades_rows(
                    draw, spec, closes[-1], times, hyperliquid=True
                ),
            }
    return files


def latest_marks(series: dict[str, dict[str, list[float]]]) -> dict[str, dict[str, float]]:
    """The venue -> symbol -> mark price map the workstation renders.

    Marks are the last seeded close — the same walk the fixtures serve,
    so the UI board, the providers' series and the P&L marks all agree
    on the demo universe. Pure derivation: consumes no draws.
    """
    return {
        venue: {symbol: round(closes[-1], 2) for symbol, closes in symbols.items()}
        for venue, symbols in series.items()
    }
