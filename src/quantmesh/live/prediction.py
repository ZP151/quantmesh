"""Prediction-market pair registry + comparison board (iteration 0015
Phase E, ADR-0014).

Polymarket and Kalshi list the *same question* as different market
identifiers — a Polymarket token id and a Kalshi ticker. The pair is
the unit the comparison screen groups on: one event, one title and
expiry, the venue-native symbols that stream into the live surface.
The symbols are operator-supplied (``QUANTMESH_PREDICTION_WATCHLIST``
entries carry the venue ids from the venues' public discovery) — the
registry never invents an id, so an unconfigured venue honestly shows
as unavailable.

``PredictionBoard.render`` is a pure function of a
``latest_state``-shaped snapshot and an explicit clock: per pair, per
venue it derives the implied probability (mid), bid/ask, spread bps,
touch depth and book liquidity from the feed's QUOTE and L2 views,
carries the feed's own provenance+age label, and reports the
cross-venue probability difference in percentage points. Wall-clock-
free, so the drills script the clock exactly like the rest of the
live surface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime

from quantmesh.domain.models import Venue
from quantmesh.live.contract import UpdateKind

PREDICTION_VENUES = (Venue.POLYMARKET, Venue.KALSHI)


@dataclass(frozen=True)
class PredictionPair:
    """One event listed on one or both prediction venues.

    ``symbols`` maps venue → the venue-native market identifier that
    streams into the live feed (a Polymarket token id, a Kalshi
    ticker). At least one venue must be configured; a pair may be
    single-venue — the missing venue then renders as unavailable.
    """

    event_key: str
    title: str
    expiry: datetime | None
    symbols: Mapping[Venue, str]


def parse_prediction_watchlist(text: str) -> list[PredictionPair]:
    """``QUANTMESH_PREDICTION_WATCHLIST`` → the configured pairs.

    Entries are comma-separated
    ``key[:title[:pm_symbol[:kalshi_symbol[:expiry_date]]]]``: the
    event key is the stable identity, the title the display text (may
    contain spaces, never colons), the two venue symbols the public
    market ids to subscribe, and the optional expiry an ISO **date**
    (day granularity — the venue convention; a datetime would collide
    with the colon delimiter) the operator knows from the venues'
    public discovery. Neither stream carries expiry, so it stays
    operator-supplied or honestly absent. Omitted venue symbols are
    honest absences — that venue renders unavailable for the pair. An
    entry with no venue symbol at all is refused: a pair that streams
    nothing is a configuration error, not a silent empty card.
    """
    pairs: list[PredictionPair] = []
    seen: set[str] = set()
    for raw in text.split(","):
        entry = raw.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split(":")]
        if len(parts) > 5:
            raise ValueError(
                f"prediction watchlist entry {entry!r} has more than 5 colon parts "
                "(expected key[:title[:pm_symbol[:kalshi_symbol[:expiry_iso]]]])"
            )
        key = parts[0]
        if not key:
            raise ValueError(f"prediction watchlist entry {entry!r} has an empty key")
        if key in seen:
            raise ValueError(f"prediction watchlist entry {entry!r} repeats key {key!r}")
        seen.add(key)
        title = parts[1] if len(parts) > 1 and parts[1] else key
        symbols: dict[Venue, str] = {}
        if len(parts) > 2 and parts[2]:
            symbols[Venue.POLYMARKET] = parts[2]
        if len(parts) > 3 and parts[3]:
            symbols[Venue.KALSHI] = parts[3]
        if not symbols:
            raise ValueError(
                f"prediction watchlist entry {entry!r} names no venue symbol "
                "(a pair that streams nothing is a configuration error)"
            )
        expiry = _parse_expiry(parts[4]) if len(parts) > 4 and parts[4] else None
        pairs.append(
            PredictionPair(event_key=key, title=title, expiry=expiry, symbols=symbols)
        )
    if not pairs:
        raise ValueError("prediction watchlist is empty: name at least one event pair")
    return pairs


def _parse_expiry(raw: str) -> datetime:
    """ISO date text → midnight UTC (day granularity, the venue
    convention — a datetime would collide with the colon delimiter)."""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"prediction watchlist expiry {raw!r} is not an ISO date") from error
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _depth(l2_view: Mapping[str, object] | None) -> float | None:
    """Summed book sizes from the latest L2 view (the venue's depth)."""
    if l2_view is None:
        return None
    payload = l2_view.get("payload")
    if not isinstance(payload, Mapping):
        return None
    total = 0.0
    for entry in payload.get("levels") or []:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            return None
        size = _finite(entry[1])
        if size is None:
            return None
        total += size
    return total


class PredictionBoard:
    """Pure bridge from the feed's latest-state snapshot to the
    prediction comparison surface.

    ``venues`` derives each supervisor's watchlist from the pairs;
    ``render`` folds one snapshot at one explicit clock into the JSON
    the comparison screen draws — never a venue's internals leaking
    through, and never a fabricated probability when a venue is
    unavailable: a pair's venue row carries the feed's own label and
    ``probability=None`` until a real quote arrives.
    """

    def __init__(self, pairs: list[PredictionPair]) -> None:
        if not pairs:
            raise ValueError("a prediction board needs at least one pair")
        for pair in pairs:
            if not pair.event_key:
                raise ValueError("a prediction pair needs a non-empty event key")
            if not pair.title:
                raise ValueError(f"pair {pair.event_key!r} needs a non-empty title")
            for venue in pair.symbols:
                if venue not in PREDICTION_VENUES:
                    raise ValueError(
                        f"pair {pair.event_key!r} names venue {venue.value!r}; "
                        f"only {', '.join(v.value for v in PREDICTION_VENUES)} stream here"
                    )
        self.pairs = list(pairs)

    def venues(self) -> dict[Venue, list[str]]:
        """Per-venue watchlist for the supervisors (deduplicated)."""
        watchlists: dict[Venue, list[str]] = {venue: [] for venue in PREDICTION_VENUES}
        for pair in self.pairs:
            for venue, symbol in pair.symbols.items():
                if symbol not in watchlists[venue]:
                    watchlists[venue].append(symbol)
        return watchlists

    def render(
        self, snapshot: Mapping[str, object], now: datetime
    ) -> list[dict[str, object]]:
        """One comparison view: per pair, per venue, plus the diff."""
        instruments = snapshot.get("instruments")
        if not isinstance(instruments, Mapping):
            instruments = {}
        rows: list[dict[str, object]] = []
        for pair in self.pairs:
            venues: list[dict[str, object]] = []
            for venue in PREDICTION_VENUES:
                symbol = pair.symbols.get(venue)
                if symbol is None:
                    venues.append(self._venue_row(venue, None, None))
                    continue
                entry = instruments.get(symbol)
                kinds = entry.get("kinds") if isinstance(entry, Mapping) else None
                quote = (
                    kinds.get(UpdateKind.QUOTE.value) if isinstance(kinds, Mapping) else None
                )
                l2 = (
                    kinds.get(UpdateKind.L2_SNAPSHOT.value)
                    if isinstance(kinds, Mapping)
                    else None
                )
                venues.append(self._venue_row(venue, symbol, quote, l2_view=l2))
            rows.append(
                {
                    "event_key": pair.event_key,
                    "title": pair.title,
                    "expiry": (
                        pair.expiry.isoformat() if pair.expiry is not None else None
                    ),
                    "venues": venues,
                    "diff": self._diff(venues),
                }
            )
        return rows

    def _venue_row(
        self,
        venue: Venue,
        symbol: str | None,
        quote: Mapping[str, object] | None,
        *,
        l2_view: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        row: dict[str, object] = {
            "venue": venue.value,
            "symbol": symbol,
            "label": "unavailable",
            "probability": None,
            "bid": None,
            "ask": None,
            "spread_bps": None,
            "depth": None,
            "liquidity": None,
        }
        if quote is None or not isinstance(quote.get("payload"), Mapping):
            return row
        payload = quote["payload"]
        bid = _finite(payload.get("bid"))
        ask = _finite(payload.get("ask"))
        if bid is None or ask is None:
            return row
        label = quote.get("label")
        row["label"] = label if isinstance(label, str) else "unavailable"
        row["probability"] = round((bid + ask) / 2 * 100, 4)
        row["bid"] = bid
        row["ask"] = ask
        row["spread_bps"] = (
            round((ask - bid) / ((bid + ask) / 2) * 10_000, 2) if bid + ask > 0 else None
        )
        bid_size = _finite(payload.get("bid_size"))
        ask_size = _finite(payload.get("ask_size"))
        if bid_size is not None and ask_size is not None:
            row["depth"] = round(bid_size + ask_size, 4)
        row["liquidity"] = _depth(l2_view)
        return row

    @staticmethod
    def _diff(venues: list[dict[str, object]]) -> float | None:
        """Cross-venue probability difference (PM − Kalshi, percentage
        points) when both venues carry a probability."""
        by_venue = {row["venue"]: row for row in venues}
        pm = by_venue.get(Venue.POLYMARKET.value, {}).get("probability")
        ks = by_venue.get(Venue.KALSHI.value, {}).get("probability")
        if not isinstance(pm, (int, float)) or not isinstance(ks, (int, float)):
            return None
        return round(float(pm) - float(ks), 4)


def demo_board() -> PredictionBoard:
    """The fixture board for drills and the browser E2E: two pairs over
    scripted venue symbols, one single-venue pair to prove the honest
    unavailable state. Live operator boards come from the watchlist env
    — this constructor is for the test stack only."""
    return PredictionBoard(
        [
            PredictionPair(
                event_key="btc-100k",
                title="BTC above $100k on 2026-06-26",
                expiry=datetime(2026, 6, 26, tzinfo=UTC),
                symbols={
                    Venue.POLYMARKET: "0xasset-btc-100k",
                    Venue.KALSHI: "KXBTD-26JUN26-1000-C",
                },
            ),
            PredictionPair(
                event_key="eth-5k",
                title="ETH above $5,000 on 2026-09-30",
                expiry=datetime(2026, 9, 30, tzinfo=UTC),
                symbols={Venue.POLYMARKET: "0xasset-eth-5k", Venue.KALSHI: "KXETHD-30SEP26-5000-C"},
            ),
            PredictionPair(
                event_key="solo-pm",
                title="Solo Polymarket pair (Kalshi unconfigured)",
                expiry=None,
                symbols={Venue.POLYMARKET: "0xasset-solo"},
            ),
        ]
    )
