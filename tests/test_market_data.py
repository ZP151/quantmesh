from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.domain.market_data import (
    Bar,
    DepthLevel,
    OrderBook,
    TradeEvent,
    find_duplicates,
    find_gaps,
    interval_to_timedelta,
    monotonic_violations,
)
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    Side,
    Venue,
)

INSTRUMENT = Instrument(
    symbol="BTC-PERP", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
)
T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
NAIVE_T0 = datetime(2026, 8, 7, 12, 0, 0)


def make_book(**overrides: object) -> OrderBook:
    values: dict[str, object] = {
        "instrument": INSTRUMENT,
        "timestamp": T0,
        "bids": [DepthLevel(price=100.5, quantity=2.0), DepthLevel(price=100.0, quantity=5.0)],
        "asks": [DepthLevel(price=101.0, quantity=3.0), DepthLevel(price=101.5, quantity=1.0)],
    }
    values.update(overrides)
    return OrderBook(**values)


def make_bar(**overrides: object) -> Bar:
    values: dict[str, object] = {
        "instrument": INSTRUMENT,
        "timestamp": T0,
        "interval": "1m",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 12.5,
    }
    values.update(overrides)
    return Bar(**values)


def make_trade(**overrides: object) -> TradeEvent:
    values: dict[str, object] = {
        "instrument": INSTRUMENT,
        "timestamp": T0,
        "price": 100.0,
        "quantity": 1.5,
        "aggressor_side": Side.BUY,
        "venue_sequence": 7,
    }
    values.update(overrides)
    return TradeEvent(**values)


# --- Bar --------------------------------------------------------------------


def test_bar_accepts_valid_ohlcv() -> None:
    bar = make_bar()

    assert bar.open == 100.0
    assert bar.high == 105.0
    assert bar.low == 99.0
    assert bar.close == 104.0
    assert bar.volume == 12.5
    assert bar.interval == "1m"


def test_bar_high_below_max_open_close_is_rejected() -> None:
    with pytest.raises(ValidationError, match="high"):
        make_bar(high=100.0, close=101.0)


def test_bar_low_above_min_open_close_is_rejected() -> None:
    with pytest.raises(ValidationError, match="low"):
        make_bar(low=101.0, close=100.0)


def test_bar_rejects_negative_volume() -> None:
    with pytest.raises(ValidationError):
        make_bar(volume=-1.0)


def test_bar_rejects_nonpositive_price() -> None:
    with pytest.raises(ValidationError):
        make_bar(open=0.0)


def test_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        make_bar(timestamp=datetime(2026, 8, 7, 12, 0, 0))


def test_bar_rejects_unknown_interval() -> None:
    with pytest.raises(ValidationError, match="interval"):
        make_bar(interval="3x")


def test_bar_accepts_common_intervals() -> None:
    for interval in ("1s", "5m", "1h", "1d", "1w"):
        assert make_bar(interval=interval).interval == interval


# --- OrderBook --------------------------------------------------------------


def test_book_accepts_sorted_levels() -> None:
    book = make_book()

    assert book.bids[0].price == 100.5
    assert book.asks[0].price == 101.0


def test_book_rejects_unsorted_bids() -> None:
    with pytest.raises(ValidationError, match="bids"):
        make_book(
            bids=[DepthLevel(price=100.0, quantity=1.0), DepthLevel(price=100.5, quantity=1.0)]
        )


def test_book_rejects_unsorted_asks() -> None:
    with pytest.raises(ValidationError, match="asks"):
        make_book(
            asks=[DepthLevel(price=101.5, quantity=1.0), DepthLevel(price=101.0, quantity=1.0)]
        )


def test_book_rejects_duplicate_price_within_a_side() -> None:
    with pytest.raises(ValidationError, match="bids"):
        make_book(
            bids=[
                DepthLevel(price=100.5, quantity=2.0),
                DepthLevel(price=100.5, quantity=3.0),
            ]
        )


def test_book_rejects_nonpositive_level_price() -> None:
    with pytest.raises(ValidationError):
        DepthLevel(price=0.0, quantity=1.0)


def test_book_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        make_book(timestamp=NAIVE_T0)


# --- TradeEvent -------------------------------------------------------------


def test_trade_event_accepts_optional_side_and_sequence() -> None:
    trade = make_trade(aggressor_side=None, venue_sequence=None)

    assert trade.aggressor_side is None
    assert trade.venue_sequence is None


def test_trade_event_rejects_nonpositive_price() -> None:
    with pytest.raises(ValidationError):
        make_trade(price=0.0)


def test_trade_event_rejects_nonpositive_quantity() -> None:
    with pytest.raises(ValidationError):
        make_trade(quantity=-0.5)


def test_trade_event_rejects_negative_sequence() -> None:
    with pytest.raises(ValidationError):
        make_trade(venue_sequence=-1)


def test_trade_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        make_trade(timestamp=NAIVE_T0)


# --- interval_to_timedelta --------------------------------------------------


def test_interval_to_timedelta_common_intervals() -> None:
    assert interval_to_timedelta("1s") == timedelta(seconds=1)
    assert interval_to_timedelta("5m") == timedelta(minutes=5)
    assert interval_to_timedelta("1h") == timedelta(hours=1)
    assert interval_to_timedelta("1d") == timedelta(days=1)
    assert interval_to_timedelta("1w") == timedelta(weeks=1)


def test_interval_to_timedelta_rejects_garbage() -> None:
    for bad in ("3x", "", "m", "1M", "5 minutes"):
        with pytest.raises(ValueError):
            interval_to_timedelta(bad)


def test_interval_to_timedelta_rejects_zero_amount() -> None:
    with pytest.raises(ValueError, match="positive"):
        interval_to_timedelta("0m")


def test_bar_rejects_zero_interval() -> None:
    with pytest.raises(ValidationError, match="positive"):
        make_bar(interval="0m")


# --- monotonicity -----------------------------------------------------------


def test_monotonic_violations_empty_for_non_decreasing_values() -> None:
    later = datetime(2026, 8, 7, 12, 2, tzinfo=UTC)
    values = [datetime(2026, 8, 7, 12, 0, tzinfo=UTC), T0, T0, later]

    assert monotonic_violations(values) == []


def test_monotonic_violations_detects_out_of_order_pairs() -> None:
    t1 = datetime(2026, 8, 7, 12, 1, tzinfo=UTC)
    t3 = datetime(2026, 8, 7, 12, 3, tzinfo=UTC)
    values = [t1, T0, t3, t3, t1]

    assert monotonic_violations(values) == [(0, 1), (3, 4)]


def test_monotonic_violations_rejects_none_values() -> None:
    with pytest.raises(ValueError, match="None"):
        monotonic_violations([1, None, 2])


# --- duplication ------------------------------------------------------------


def test_find_duplicates_by_key_reports_indices_per_key() -> None:
    t1 = T0 + timedelta(minutes=1)
    trades = [
        make_trade(timestamp=T0, venue_sequence=1),
        make_trade(timestamp=T0, venue_sequence=2),
        make_trade(timestamp=t1, venue_sequence=1),
        make_trade(timestamp=t1, venue_sequence=1),  # duplicate
        make_trade(timestamp=t1, venue_sequence=1),  # duplicate
    ]

    found = find_duplicates(
        trades, key=lambda trade: (trade.timestamp, trade.venue_sequence)
    )

    assert found == {(t1, 1): [2, 3, 4]}


def test_find_duplicates_with_identity_on_hashable_rows() -> None:
    rows = [(T0, 1), (T0, 1), (T0, 2)]

    assert find_duplicates(rows) == {(T0, 1): [0, 1]}


def test_find_duplicates_empty_for_unique_rows() -> None:
    rows = [(T0, 1), (T0 + timedelta(minutes=1), 1)]

    assert find_duplicates(rows) == {}


# --- gap detection ----------------------------------------------------------


def test_find_gaps_none_for_contiguous_series() -> None:
    timestamps = [T0 + timedelta(hours=h) for h in range(4)]

    assert find_gaps(timestamps, interval="1h") == []


def test_find_gaps_detects_single_and_multiple_missing_ticks() -> None:
    timestamps = [T0, T0 + timedelta(hours=1), T0 + timedelta(hours=4)]

    assert find_gaps(timestamps, interval="1h") == [
        T0 + timedelta(hours=2),
        T0 + timedelta(hours=3),
    ]


def test_find_gaps_returns_single_missing_tick_between_adjacent_slots() -> None:
    timestamps = [T0, T0 + timedelta(hours=2)]

    assert find_gaps(timestamps, interval="1h") == [T0 + timedelta(hours=1)]


def test_find_gaps_rejects_non_increasing_input() -> None:
    with pytest.raises(ValueError, match="increasing"):
        find_gaps([T0, T0], interval="1h")


def test_find_gaps_rejects_naive_timestamps() -> None:
    naive = [NAIVE_T0, NAIVE_T0.replace(hour=13)]

    with pytest.raises(ValueError, match="timezone"):
        find_gaps(naive, interval="1h")


def test_find_gaps_rejects_single_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        find_gaps([NAIVE_T0], interval="1h")


def test_find_gaps_single_aware_timestamp_is_valid_and_gap_free() -> None:
    assert find_gaps([T0], interval="1h") == []


def test_find_gaps_shifted_regular_grid_has_no_internal_gaps() -> None:
    # A series aligned to its own grid (anchored at :30) is not missing
    # data; grid-shift detection belongs to the manifest coverage checks.
    timestamps = [
        T0.replace(minute=0, second=30),
        T0.replace(minute=1, second=30),
        T0.replace(minute=2, second=30),
    ]

    assert find_gaps(timestamps, interval="1m") == []


def test_find_gaps_rejects_series_misaligned_with_interval() -> None:
    timestamps = [T0, T0 + timedelta(minutes=90)]

    with pytest.raises(ValueError, match="aligned"):
        find_gaps(timestamps, interval="1h")
