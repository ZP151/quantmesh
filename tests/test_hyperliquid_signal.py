"""Order-book imbalance signals from l2Book data (issue #32, Phase D).

The signal is pure: depth-weighted imbalance over the full book, and a
per-bar mean series aligned 1:1 with the bar grid. Everything fails
closed — an empty book, a snapshot outside every bar window, a bar
without a snapshot, a non-monotonic snapshot series, or a symbol
mismatch is an error, never a fabricated value.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.market_data import Bar, DepthLevel, OrderBook
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.signal import book_imbalance, imbalance_by_bar

START = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)


def book(
    *,
    timestamp: datetime,
    bid_depth: float = 10.0,
    ask_depth: float = 10.0,
) -> OrderBook:
    return OrderBook(
        instrument=BTC,
        timestamp=timestamp,
        bids=[DepthLevel(price=101.0, quantity=bid_depth)],
        asks=[DepthLevel(price=102.0, quantity=ask_depth)],
    )


def bar(index: int, *, close: float = 101.0) -> Bar:
    return Bar(
        instrument=BTC,
        timestamp=START + timedelta(minutes=index),
        interval="1m",
        open=100.0,
        high=max(100.0, close),
        low=min(100.0, close),
        close=close,
        volume=10.0,
    )


def bars(n: int = 3) -> list[Bar]:
    return [bar(index) for index in range(n)]


# --- the depth-weighted imbalance --------------------------------------------


def test_balanced_book_is_zero() -> None:
    assert book_imbalance(book(timestamp=START)) == 0.0


def test_bid_heavy_book_is_positive() -> None:
    assert book_imbalance(book(timestamp=START, bid_depth=30.0, ask_depth=10.0)) == 0.5


def test_ask_heavy_book_is_negative() -> None:
    assert book_imbalance(book(timestamp=START, bid_depth=10.0, ask_depth=30.0)) == -0.5


def test_depth_weights_across_all_levels() -> None:
    imbalance = book_imbalance(
        OrderBook(
            instrument=BTC,
            timestamp=START,
            bids=[
                DepthLevel(price=101.0, quantity=1.0),
                DepthLevel(price=100.5, quantity=2.0),
            ],
            asks=[DepthLevel(price=102.0, quantity=3.0)],
        )
    )
    assert imbalance == 0.0  # (1 + 2 − 3) / (1 + 2 + 3)


def test_one_sided_book_is_a_well_defined_extreme() -> None:
    assert book_imbalance(
        book(timestamp=START, bid_depth=0.0, ask_depth=5.0)
    ) == -1.0
    assert book_imbalance(
        book(timestamp=START, bid_depth=5.0, ask_depth=0.0)
    ) == 1.0


def test_an_empty_book_fails_closed() -> None:
    with pytest.raises(ValueError, match="no depth on either side"):
        book_imbalance(
            OrderBook(instrument=BTC, timestamp=START, bids=[], asks=[])
        )


# --- the per-bar canonical series -----------------------------------------------


def test_series_means_the_snapshots_inside_each_bar_window() -> None:
    series = imbalance_by_bar(
        [
            book(timestamp=START, bid_depth=30.0, ask_depth=10.0),  # +0.5
            book(timestamp=START + timedelta(seconds=30), bid_depth=10.0, ask_depth=30.0),  # −0.5
            book(timestamp=START + timedelta(minutes=1), bid_depth=10.0, ask_depth=10.0),  # 0.0
            book(timestamp=START + timedelta(minutes=2), bid_depth=10.0, ask_depth=30.0),  # −0.5
        ],
        bars(),
    )
    assert series == [0.0, 0.0, -0.5]  # bar 0: mean(0.5, −0.5)


def test_snapshot_at_a_bar_boundary_lands_in_the_next_bar() -> None:
    series = imbalance_by_bar(
        [
            book(timestamp=START, bid_depth=10.0, ask_depth=30.0),  # −0.5
            book(timestamp=START + timedelta(minutes=1), bid_depth=30.0, ask_depth=10.0),  # +0.5
        ],
        bars(2),
    )
    assert series == [-0.5, 0.5]


def test_a_bar_without_a_snapshot_fails_closed() -> None:
    with pytest.raises(ValueError, match="has no book snapshot"):
        imbalance_by_bar(
            [
                book(timestamp=START, bid_depth=10.0, ask_depth=30.0),
                book(timestamp=START + timedelta(minutes=1), bid_depth=30.0, ask_depth=10.0),
            ],
            bars(3),  # bar 2 never gets a snapshot
        )


def test_a_snapshot_outside_every_window_fails_closed() -> None:
    with pytest.raises(ValueError, match="falls outside every bar window"):
        imbalance_by_bar(
            [book(timestamp=START + timedelta(minutes=5))],
            bars(3),
        )


def test_a_snapshot_before_the_series_fails_closed() -> None:
    with pytest.raises(ValueError, match="falls outside every bar window"):
        imbalance_by_bar(
            [book(timestamp=START - timedelta(minutes=1))],
            bars(3),
        )


def test_non_monotonic_snapshots_fail_closed() -> None:
    with pytest.raises(ValueError, match="not monotonic"):
        imbalance_by_bar(
            [
                book(timestamp=START + timedelta(minutes=2)),
                book(timestamp=START + timedelta(minutes=1)),
            ],
            bars(3),
        )


def test_symbol_mismatch_fails_closed() -> None:
    other = Instrument(
        symbol="ETH",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
    )
    with pytest.raises(ValueError, match="does not match the bar series"):
        imbalance_by_bar(
            [
                OrderBook(
                    instrument=other,
                    timestamp=START,
                    bids=[DepthLevel(price=101.0, quantity=1.0)],
                    asks=[DepthLevel(price=102.0, quantity=1.0)],
                )
            ],
            bars(3),
        )


def test_no_books_fails_closed() -> None:
    with pytest.raises(ValueError, match="no book snapshots"):
        imbalance_by_bar([], bars(3))


def test_no_bars_fails_closed() -> None:
    with pytest.raises(ValueError, match="no bars to align"):
        imbalance_by_bar([book(timestamp=START)], [])


def test_mixed_interval_bars_fail_closed() -> None:
    with pytest.raises(ValueError, match="mixed intervals"):
        imbalance_by_bar(
            [book(timestamp=START), book(timestamp=START + timedelta(minutes=1))],
            [bar(0), bar(1), bar(2).model_copy(update={"interval": "5m"})],
        )
