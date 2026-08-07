"""l2Book-derived order-book imbalance signals (M5, issue #32, Phase D).

The order-book imbalance (OBI) signal is the canonical depth-weighted
measure — (Σbid − Σask) / (Σbid + Σask) over the full book, in (−1, 1)
— positive when buy-side depth dominates. ``imbalance_by_bar`` buckets
each snapshot into the bar whose window contains it and takes the mean,
so the signal series is aligned 1:1 with the bar grid the walk-forward
backtester consumes (a canonical series: same length, same order, no
fabricated values). Anything that cannot be computed or placed fails
closed: a snapshot outside every bar window, a bar without a snapshot,
or an empty book on both sides is an error, never a guessed value.
"""

from quantmesh.domain.market_data import Bar, OrderBook, interval_to_timedelta

__all__ = ["book_imbalance", "imbalance_by_bar"]


def book_imbalance(book: OrderBook) -> float:
    """Depth-weighted order-book imbalance over the full book, in (−1, 1).

    Positive when bid-side depth dominates. An empty book on both sides
    is 0/0 — undefined — and fails closed; a book with depth on only one
    side is a well-defined ±1.
    """
    bid_depth = sum(level.quantity for level in book.bids)
    ask_depth = sum(level.quantity for level in book.asks)
    if bid_depth == 0 and ask_depth == 0:
        raise ValueError(
            f"book for {book.instrument.symbol!r} at {book.timestamp.isoformat()} "
            "has no depth on either side; imbalance is undefined"
        )
    return (bid_depth - ask_depth) / (bid_depth + ask_depth)


def imbalance_by_bar(books: list[OrderBook], bars: list[Bar]) -> list[float]:
    """Per-bar mean imbalance, aligned 1:1 with ``bars`` (canonical series).

    Each snapshot is bucketed into the single bar whose window
    [timestamp, timestamp + interval) contains it; a snapshot outside
    every window, a bar with no snapshot, a non-monotonic snapshot
    series, or a symbol mismatch fails closed — the signal series must
    cover the bar grid exactly, or the walk-forward would be computed
    over fabricated or misaligned values.
    """
    if not books:
        raise ValueError("no book snapshots to derive an imbalance series from")
    if not bars:
        raise ValueError("no bars to align the imbalance series against")
    intervals = {bar.interval for bar in bars}
    if len(intervals) != 1:
        raise ValueError(f"bars carry mixed intervals {sorted(intervals)}")
    interval = intervals.pop()
    symbol = bars[0].instrument.symbol
    for book in books:
        if book.instrument.symbol != symbol:
            raise ValueError(
                f"book for {book.instrument.symbol!r} does not match the bar "
                f"series {symbol!r}"
            )
    for previous, current in zip(books, books[1:]):
        if current.timestamp < previous.timestamp:
            raise ValueError(
                "book snapshots are not monotonic: "
                f"{previous.timestamp.isoformat()} then {current.timestamp.isoformat()}"
            )

    step = interval_to_timedelta(interval)
    per_bar: list[list[float]] = [[] for _ in bars]
    cursor = 0
    for book in books:
        timestamp = book.timestamp
        while cursor < len(bars) and timestamp >= bars[cursor].timestamp + step:
            cursor += 1
        if cursor >= len(bars) or timestamp < bars[cursor].timestamp:
            raise ValueError(
                f"book snapshot at {timestamp.isoformat()} falls outside every "
                f"bar window of the {interval} series for {symbol!r}"
            )
        per_bar[cursor].append(book_imbalance(book))

    for index, values in enumerate(per_bar):
        if not values:
            raise ValueError(
                f"bar {index} ({bars[index].timestamp.isoformat()}) has no book "
                "snapshot; the imbalance series would be fabricated"
            )

    return [sum(values) / len(values) for values in per_bar]
