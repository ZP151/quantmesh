"""Approved SMA100 development arithmetic; no broker, provider or user code.

Mechanical reuse of retained QuantMesh research engine.py, original SHA256
bf69680b7d3e2be8e3c9b6baf8a19ab09972fa501118cc3b0c9aa9045b056f22.
prepare_signals/run_cashbook/metrics retain their original AST. No bootstrap or
old experiment runner is included. Financial/paper qualification is not granted.
"""

import math

import numpy as np
import pandas as pd

ORIGINAL_ENGINE_SHA256 = "bf69680b7d3e2be8e3c9b6baf8a19ab09972fa501118cc3b0c9aa9045b056f22"


def prepare_signals(frame, lookback=100):
    growth = (frame.close + frame.dividend) / frame.close.shift(1)
    growth.iloc[0] = 1.0
    total_return_index = growth.cumprod()
    average = total_return_index.rolling(lookback, min_periods=lookback).mean()
    return (total_return_index > average).astype(int)


def run_cashbook(
    frame,
    signal,
    distributions,
    start_date,
    end_date,
    capital=100000,
    cost_bps=5,
    extra_delay=0,
    benchmark=False,
):
    if capital <= 0 or cost_bps < 0 or extra_delay < 0:
        raise ValueError("invalid experiment inputs")
    cash, shares, pending = float(capital), 0, []
    prior_target = 0
    daily, trades = [], []
    dates = frame.index.tolist()
    chosen = [date for date in dates if start_date <= date <= end_date]
    if len(chosen) < 2:
        raise ValueError("insufficient sessions")
    ex_events = {}
    for item in distributions:
        ex_events.setdefault(item["ex_date"], []).append(item)
    fee_rate = cost_bps / 10000
    previous_equity = float(capital)
    for date in chosen:
        row = frame.loc[date]
        index = dates.index(date)
        earned, paid = 0.0, 0.0
        for event in ex_events.get(date, []):
            entitlement = shares * event["amount"]
            earned += entitlement
            if entitlement:
                pending.append((event["pay_date"], entitlement))
        remaining = []
        for pay_date, amount in pending:
            if pay_date <= date:
                paid += amount
                cash += amount
            else:
                remaining.append((pay_date, amount))
        pending = remaining
        lagged_index = index - 1 - extra_delay
        source_date = dates[lagged_index] if lagged_index >= 0 else None
        # A new period starts flat: delays cannot create a pre-period order.
        is_delayed_start = dates.index(date) - dates.index(chosen[0]) < extra_delay
        target = (
            1
            if benchmark
            else (int(signal.loc[source_date]) if source_date and not is_delayed_start else 0)
        )
        if date == chosen[-1]:
            target = 0
        quantity = 0
        if target != prior_target:
            quantity = (
                math.floor((cash + 1e-9) / (row.open * (1 + fee_rate))) if target else -shares
            )
        lag_volume = frame.volume.iloc[max(0, index - 20) : index]
        cap = math.floor(float(lag_volume.median()) * 0.01) if len(lag_volume) else 0
        clipped = abs(quantity) > cap
        if clipped:
            quantity = int(math.copysign(cap, quantity))
        friction = abs(quantity) * float(row.open) * fee_rate
        if quantity:
            cash -= quantity * float(row.open) + friction
            shares += quantity
            trades.append(
                {
                    "date": date,
                    "signal_date": source_date,
                    "quantity": quantity,
                    "price": float(row.open),
                    "friction": friction,
                    "post_cash": cash,
                    "post_shares": shares,
                    "participation_cap": cap,
                    "capacity_clipped": clipped,
                    "forced_terminal_liquidation": date == chosen[-1],
                }
            )
        if cash < -1e-7 or shares < 0:
            raise ArithmeticError("negative cash or shares")
        if not clipped:
            prior_target = target
        receivable = sum(amount for _, amount in pending)
        mark = float(row.open if date == chosen[-1] else row.close)
        equity = cash + shares * mark + receivable
        daily.append(
            {
                "date": date,
                "signal_date": source_date,
                "target": target,
                "shares": shares,
                "cash": cash,
                "receivable": receivable,
                "mark": mark,
                "equity": equity,
                "net_return": equity / previous_equity - 1,
                "dividend_earned": earned,
                "dividend_paid": paid,
                "friction": friction,
                "capacity_clipped": clipped,
            }
        )
        previous_equity = equity
    return pd.DataFrame(daily).set_index("date"), trades


def metrics(daily, trades, capital=100000):
    returns = daily.net_return.to_numpy()
    equity = np.r_[capital, daily.equity.to_numpy()]
    drawdown = equity / np.maximum.accumulate(equity) - 1
    elapsed = (pd.Timestamp(daily.index[-1]) - pd.Timestamp(daily.index[0])).days / 365.25
    total = float(equity[-1] / capital - 1)
    cagr = float((equity[-1] / capital) ** (1 / elapsed) - 1) if elapsed > 0 else None
    std = float(np.std(returns, ddof=1))
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2)))
    risk_tail = returns[returns <= np.quantile(returns, 0.05)]
    underwater, max_underwater = 0, 0
    for value in drawdown:
        underwater = underwater + 1 if value < -1e-12 else 0
        max_underwater = max(max_underwater, underwater)
    return {
        "sessions": len(daily),
        "start": daily.index[0],
        "end": daily.index[-1],
        "terminal_equity": float(equity[-1]),
        "net_profit_usd": float(equity[-1] - capital),
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": float(drawdown.min()),
        "max_underwater_sessions": max_underwater,
        "annualized_volatility": std * np.sqrt(252),
        "naive_sharpe_rf_zero": float(np.mean(returns) / std * np.sqrt(252)) if std else None,
        "sortino_target_zero": float(np.mean(returns) / downside * np.sqrt(252))
        if downside
        else None,
        "calmar": cagr / abs(float(drawdown.min()))
        if cagr is not None and drawdown.min() < 0
        else None,
        "worst_day": float(returns.min()),
        "historical_es_95": float(risk_tail.mean()),
        "es_tail_observations": len(risk_tail),
        "fills": len(trades),
        "long_entries": sum(item["quantity"] > 0 for item in trades),
        "friction_usd": float(sum(item["friction"] for item in trades)),
        "dividend_earned_usd": float(daily.dividend_earned.sum()),
        "dividend_paid_usd": float(daily.dividend_paid.sum()),
        "terminal_receivable": float(daily.iloc[-1].receivable),
        "gross_traded_notional_over_initial_capital": float(
            sum(abs(item["quantity"]) * item["price"] for item in trades) / capital
        ),
        "capacity_clipped_sessions": int(daily.capacity_clipped.sum()),
        "terminal_shares": int(daily.iloc[-1].shares),
    }


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        raise ArithmeticError("nonfinite report")
    return value


def _reconcile(daily, trades, cost_bps, capital=100000):
    """Independent cash/shares/receivable/fee identities before publication."""
    cash, shares, receivable, equity = float(capital), 0, 0.0, float(capital)
    by_date = {}
    for trade in trades:
        by_date.setdefault(trade["date"], []).append(trade)
    for day, row in daily.iterrows():
        cash += row.dividend_paid
        receivable += row.dividend_earned - row.dividend_paid
        friction = 0.0
        for trade in by_date.get(day, []):
            expected = abs(trade["quantity"]) * trade["price"] * cost_bps / 10000
            if not math.isclose(trade["friction"], expected, abs_tol=1e-8):
                raise ArithmeticError("fee reconciliation")
            cash -= trade["quantity"] * trade["price"] + expected
            shares += trade["quantity"]
            friction += expected
            if shares != trade["post_shares"] or not math.isclose(
                cash, trade["post_cash"], abs_tol=1e-7
            ):
                raise ArithmeticError("trade reconciliation")
        expected_equity = cash + shares * row.mark + receivable
        expected = [cash, receivable, expected_equity, expected_equity / equity - 1, friction]
        observed = [row.cash, row.receivable, row.equity, row.net_return, row.friction]
        if shares != row.shares or not all(
            math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-7)
            for a, b in zip(expected, observed, strict=True)
        ):
            raise ArithmeticError("daily reconciliation")
        equity = expected_equity


def calculate(frame, distributions, start_date, end_date):
    """Fixed base/stress and same-cost buyhold; no fitting or OOS inference."""
    signal = prepare_signals(frame)
    scenarios = {}
    for name, bps in (("base5", 5), ("stress10", 10)):
        scenario = {"one_way_bps": bps}
        for label, benchmark in (("strategy", False), ("buyhold", True)):
            daily, trades = run_cashbook(
                frame,
                signal,
                distributions,
                start_date,
                end_date,
                cost_bps=bps,
                benchmark=benchmark,
            )
            if len(daily) != 21:
                raise ValueError("expected21 observation sessions")
            _reconcile(daily, trades, bps)
            scenario[label] = {
                "metrics": metrics(daily, trades),
                "daily": daily.rename_axis("date").reset_index().to_dict(orient="records"),
                "trades": trades,
            }
        a, b = scenario["strategy"]["metrics"], scenario["buyhold"]["metrics"]
        scenario["comparison"] = {
            "terminal_equity_difference_usd": a["terminal_equity"] - b["terminal_equity"],
            "total_return_difference": a["total_return"] - b["total_return"],
        }
        scenarios[name] = scenario
    return _plain(
        {
            "scenarios": scenarios,
            "cash_benchmark": {
                "capital_usd": 100000,
                "terminal_equity": 100000,
                "total_return": 0,
                "max_drawdown": 0,
                "interest_rate_assumed": 0,
                "sessions": 21,
            },
        }
    )
