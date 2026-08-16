from datetime import UTC, date, datetime, timedelta

import pytest

from quantmesh.data.adjustments import (
    AdjustmentUnavailableError,
    EquityAdjustmentPolicy,
    EquitySplitAction,
    adjust_split,
    build_adjusted_series,
    normalize_moomoo_split_actions,
)
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

T0 = datetime(2026, 8, 10, 13, 30, tzinfo=UTC)
AAPL_ID = CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS")
AAPL = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)


def _bar(*, timestamp: datetime = T0, close: float = 100.0) -> Bar:
    return Bar(
        instrument=AAPL,
        timestamp=timestamp,
        interval="1d",
        open=close,
        high=close + 2.0,
        low=close - 2.0,
        close=close,
        volume=1_000.0,
    )


def _split(
    *,
    announced_at: datetime = T0 + timedelta(days=1),
    effective_at: datetime = T0 + timedelta(days=2),
    ratio: float = 2.0,
) -> EquitySplitAction:
    return EquitySplitAction(
        action_id="split-aapl-2026",
        canonical_instrument=AAPL_ID,
        announced_at=announced_at,
        effective_at=effective_at,
        ratio=ratio,
    )


def _policy(*, known_at: datetime) -> EquityAdjustmentPolicy:
    return EquityAdjustmentPolicy(
        canonical_instrument=AAPL_ID,
        factor_manifest_id="a" * 64,
        action_manifest_id="b" * 64,
        known_at=known_at,
    )


def test_split_adjustment_changes_ohlc_and_inverse_volume() -> None:
    adjusted = adjust_split(_bar(), factor=2.0)

    assert adjusted.open == 50.0
    assert adjusted.high == 51.0
    assert adjusted.low == 49.0
    assert adjusted.close == 50.0
    assert adjusted.volume == 2_000.0


def test_future_announced_action_is_not_used_for_earlier_knowledge_time() -> None:
    known_at = T0 + timedelta(hours=1)

    with pytest.raises(AdjustmentUnavailableError, match="knowledge time"):
        build_adjusted_series(
            bars=[_bar()],
            actions=[_split(announced_at=T0 + timedelta(days=1))],
            policy=_policy(known_at=known_at),
        )


def test_only_pre_effective_bars_are_backward_adjusted() -> None:
    effective_at = T0 + timedelta(days=2)
    bars = [
        _bar(timestamp=T0, close=100.0),
        _bar(timestamp=effective_at, close=52.0),
    ]

    adjusted = build_adjusted_series(
        bars=bars,
        actions=[_split(effective_at=effective_at)],
        policy=_policy(known_at=effective_at + timedelta(days=1)),
    )

    assert [bar.close for bar in adjusted] == [50.0, 52.0]
    assert [bar.volume for bar in adjusted] == [2_000.0, 1_000.0]


def test_policy_refuses_wrong_instrument_and_ambiguous_actions() -> None:
    nvda = AAPL.model_copy(update={"symbol": "NVDA"})
    with pytest.raises(AdjustmentUnavailableError, match="instrument"):
        build_adjusted_series(
            bars=[_bar().model_copy(update={"instrument": nvda})],
            actions=[_split()],
            policy=_policy(known_at=T0 + timedelta(days=3)),
        )

    conflicting = _split(ratio=3.0).model_copy(update={"action_id": "split-conflict"})
    with pytest.raises(AdjustmentUnavailableError, match="ambiguous"):
        build_adjusted_series(
            bars=[_bar()],
            actions=[_split(), conflicting],
            policy=_policy(known_at=T0 + timedelta(days=3)),
        )


@pytest.mark.parametrize("factor", [0.0, -1.0, float("inf"), float("nan"), True])
def test_split_factor_must_be_finite_positive_number(factor: float) -> None:
    with pytest.raises(AdjustmentUnavailableError, match="factor"):
        adjust_split(_bar(), factor=factor)


def test_action_timestamps_must_be_utc_and_announcement_precedes_effective_date() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _split(announced_at=datetime(2026, 8, 11, 13, 30))

    with pytest.raises(ValueError, match="after effective"):
        _split(
            announced_at=T0 + timedelta(days=3),
            effective_at=T0 + timedelta(days=2),
        )


def test_official_factor_and_action_surfaces_cross_check_forward_split() -> None:
    announced = datetime(2020, 8, 17, tzinfo=UTC)
    actions = normalize_moomoo_split_actions(
        canonical_instrument=AAPL_ID,
        factor_rows=[
            {
                "ex_div_date": "2020-08-31",
                "split_base": 1.0,
                "split_ert": 4.0,
                "join_base": None,
                "join_ert": None,
                "split_ratio": 0.25,
            }
        ],
        split_rows=[
            {
                "dir_deci_pub_date": int(announced.timestamp()),
                "dir_deci_pub_date_str": "2020-08-17",
                "reform_type": "Split",
                "rate": "1->4",
            }
        ],
    )

    assert len(actions) == 1
    assert actions[0].ratio == 4.0
    assert actions[0].effective_at == datetime(2020, 8, 31, 4, tzinfo=UTC)


def test_split_rate_accepts_unicode_arrow_from_real_opend_payload() -> None:
    announced = datetime(2020, 8, 17, tzinfo=UTC)
    actions = normalize_moomoo_split_actions(
        canonical_instrument=AAPL_ID,
        factor_rows=[
            {
                "ex_div_date": "2020-08-31",
                "split_base": 1.0,
                "split_ert": 4.0,
                "join_base": None,
                "join_ert": None,
                "split_ratio": 0.25,
            }
        ],
        split_rows=[
            {
                "dir_deci_pub_date": int(announced.timestamp()),
                "dir_deci_pub_date_str": "2020-08-17",
                "reform_type": "Split",
                "rate": "1→4",
            }
        ],
    )

    assert len(actions) == 1
    assert actions[0].ratio == 4.0


def test_same_ratio_actions_match_nearest_effective_factor_independent_of_order() -> None:
    first_announcement = datetime(2019, 8, 17, tzinfo=UTC)
    second_announcement = datetime(2021, 8, 17, tzinfo=UTC)
    actions = normalize_moomoo_split_actions(
        canonical_instrument=AAPL_ID,
        factor_rows=[
            {
                "ex_div_date": "2021-08-31",
                "split_base": 1.0,
                "split_ert": 4.0,
                "split_ratio": 0.25,
            },
            {
                "ex_div_date": "2019-08-31",
                "split_base": 1.0,
                "split_ert": 4.0,
                "split_ratio": 0.25,
            },
        ],
        split_rows=[
            {
                "dir_deci_pub_date": int(first_announcement.timestamp()),
                "dir_deci_pub_date_str": "2019-08-17",
                "reform_type": "Split",
                "rate": "1->4",
            },
            {
                "dir_deci_pub_date": int(second_announcement.timestamp()),
                "dir_deci_pub_date_str": "2021-08-17",
                "reform_type": "Split",
                "rate": "1->4",
            },
        ],
    )

    assert [item.effective_at.date() for item in actions] == [
        date(2019, 8, 31),
        date(2021, 8, 31),
    ]
    assert [item.announced_at for item in actions] == [
        first_announcement,
        second_announcement,
    ]


def test_reverse_split_uses_new_shares_over_old_shares() -> None:
    announced = datetime(2020, 8, 17, tzinfo=UTC)
    actions = normalize_moomoo_split_actions(
        canonical_instrument=AAPL_ID,
        factor_rows=[
            {
                "ex_div_date": "2020-08-31",
                "split_base": None,
                "split_ert": None,
                "join_base": 5.0,
                "join_ert": 1.0,
                "split_ratio": 5.0,
            }
        ],
        split_rows=[
            {
                "dir_deci_pub_date": int(announced.timestamp()),
                "dir_deci_pub_date_str": "2020-08-17",
                "reform_type": "Merge",
                "rate": "5->1",
            }
        ],
    )

    assert actions[0].ratio == 0.2


def test_factor_action_mismatch_refuses_adjustment() -> None:
    announced = datetime(2020, 8, 17, tzinfo=UTC)
    with pytest.raises(AdjustmentUnavailableError, match="ambiguous or incomplete"):
        normalize_moomoo_split_actions(
            canonical_instrument=AAPL_ID,
            factor_rows=[
                {
                    "ex_div_date": "2020-08-31",
                    "split_base": 4.0,
                    "split_ert": 1.0,
                    "split_ratio": 4.0,
                }
            ],
            split_rows=[
                {
                    "dir_deci_pub_date": int(announced.timestamp()),
                    "dir_deci_pub_date_str": "2020-08-17",
                    "reform_type": "Split",
                    "rate": "1->5",
                }
            ],
        )


def test_dividend_only_factor_rows_need_no_split_action() -> None:
    assert normalize_moomoo_split_actions(
        canonical_instrument=AAPL_ID,
        factor_rows=[{"ex_div_date": "2026-01-01", "per_cash_div": 0.25}],
        split_rows=[],
    ) == []
