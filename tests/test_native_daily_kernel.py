"""New synthetic migration witnesses, not retained market/OOS experiments."""

import pandas as pd
import pytest

from quantmesh.research import spy_replay_engine as engine


def synthetic_frame(ramp=False):
    dates = pd.bdate_range("2026-01-01", periods=121).strftime("%Y-%m-%d").tolist()
    prices = [100.0] * 100 + ([101.0 + i for i in range(21)] if ramp else [100.0] * 21)
    return pd.DataFrame(
        dict(
            open=prices,
            high=prices,
            low=prices,
            close=prices,
            volume=[1000000.0] * 121,
            dividend=[0.0] * 121,
        ),
        index=dates,
    )


class Quantities:
    """An explicit quantity schedule exercises the real single cashbook loop."""

    def __init__(self, mapping, max_fraction=None):
        self.mapping, self.max_fraction = mapping, max_fraction
        self.fills, self.closes = [], []

    def propose(self, view):
        assert hasattr(engine, "QuantityOrder"), "approved quantity seam is missing"
        quantity = -view.shares if view.terminal else self.mapping.get(view.index, 0)
        return engine.QuantityOrder(quantity, max_fraction=self.max_fraction)

    def filled(self, view, order, quantity, friction, cash, shares, receivable):
        self.fills.append((view.index, quantity, friction, cash, shares, receivable))

    def closed(self, date, index, cash, shares, receivable):
        self.closes.append((date, index, cash, shares, receivable))


def run(policy, frame=None, events=None):
    frame = frame if frame is not None else synthetic_frame()
    assert hasattr(engine, "QuantityOrder"), "approved quantity seam is missing"
    return engine.run_cashbook(
        frame,
        engine.prepare_signals(frame),
        events or [],
        frame.index[100],
        frame.index[-1],
        _quantity_policy=policy,
    )


def test_quantity_seam_applies_fees_ex_pay_and_terminal_through_one_ledger():
    frame = synthetic_frame()
    policy = Quantities({100: 5, 101: 2, 102: -3})
    events = [{"ex_date": frame.index[101], "pay_date": frame.index[103], "amount": 2.0}]
    daily, trades = run(policy, frame, events)
    assert [t["quantity"] for t in trades] == [5, 2, -3, -4]
    assert [t["friction"] for t in trades] == pytest.approx([0.25, 0.10, 0.15, 0.20])
    assert daily.loc[frame.index[101]].receivable == 10  # only5 overnight shares
    assert daily.loc[frame.index[102]].cash == pytest.approx(99599.5)
    assert daily.loc[frame.index[103]].dividend_paid == 10
    assert daily.iloc[-1].cash == pytest.approx(100009.3)
    assert daily.iloc[-1].shares == 0
    assert len(policy.closes) == 20  # terminal close never creates a new decision
    engine._reconcile(daily, trades, 5)


def test_unpaid_receivable_is_wealth_but_never_cash():
    frame = synthetic_frame()
    events = [{"ex_date": frame.index[101], "pay_date": "2027-01-01", "amount": 2.0}]
    daily, trades = run(Quantities({100: 5}), frame, events)
    assert daily.iloc[-1].cash == pytest.approx(99999.5)
    assert daily.iloc[-1].receivable == 10
    assert daily.iloc[-1].equity == pytest.approx(100009.5)
    engine._reconcile(daily, trades, 5)


def test_legacy_control_still_uses_original_hand_derived_synthetic_arithmetic():
    frame = synthetic_frame(ramp=True)
    result = engine.calculate(frame, [], frame.index[100], frame.index[-1])
    base = result["scenarios"]["base5"]["strategy"]
    assert base["metrics"]["terminal_equity"] == pytest.approx(118491.8415)
    assert base["metrics"]["friction_usd"] == pytest.approx(109.1585)
    assert [t["quantity"] for t in base["trades"]] == [979, -979]


def test_native_quantity_cannot_borrow_cash_or_exceed_post_fee_cap():
    with pytest.raises(ArithmeticError, match="numeric_boundary"):
        run(Quantities({100: 1000}))
    with pytest.raises(ArithmeticError, match="numeric_boundary"):
        run(Quantities({100: 750}, max_fraction=0.75))


def test_volume_clips_requested_quantity_and_terminal_is_not_fabricated():
    frame = synthetic_frame()
    frame["volume"] = 1000.0
    _, trades = run(Quantities({100: 25}), frame)
    assert trades[0]["quantity"] == 10 and trades[0]["capacity_clipped"]
    frame.iloc[100:, frame.columns.get_loc("volume")] = 0
    with pytest.raises(ArithmeticError, match="terminal liquidation incomplete"):
        run(Quantities({100: 10}), frame)


def test_terminal_open_does_not_read_its_close():
    frame = synthetic_frame()
    original, trades = run(Quantities({100: 5}), frame)
    frame.iloc[-1, frame.columns.get_loc("close")] = 9999
    altered, later = run(Quantities({100: 5}), frame)
    assert later == trades
    assert altered.iloc[-1].equity == original.iloc[-1].equity


def test_native_guard_uses_actual_cash_debit_grouping_at_float_boundary():
    frame = synthetic_frame()
    frame[["open", "high", "low", "close"]] = 100.1
    # Exactly the existing ledger's debit. Regrouping cash-price-fee is negative.
    capital = 100.15005
    assert capital - 100.1 - 100.1 * 0.0005 < 0
    daily, trades = engine.run_cashbook(
        frame,
        engine.prepare_signals(frame),
        [],
        frame.index[100],
        frame.index[-1],
        capital=capital,
        _quantity_policy=Quantities({100: 1}),
    )
    assert trades[0]["post_cash"] == 0
    assert daily.iloc[-1].shares == 0
