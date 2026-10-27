"""Directed synthetic policy cases; no replay, matcher, cashbook or market data."""

import importlib
import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal as D
from decimal import localcontext
from pathlib import Path

import pytest


def policy():
    try:
        return importlib.import_module("quantmesh.research.trend_overlay_candidate")
    except ModuleNotFoundError:
        pytest.fail("The approved pure policy module is not implemented")


def closes(value="100"):
    return (D(value),) * 101


def entering():
    return (D(100),) * 80 + (D(101),) * 10 + (D(99),) * 10 + (D(120),)


def exiting():
    return (D(100),) * 80 + (D(99),) * 10 + (D(101),) * 10 + (D(80),)


def held(p, *, shares=100, q0=100, consumed=(), pending_full_exit=None):
    return p.Campaign(
        shares=shares,
        initial_price=D(100),
        initial_quantity=q0,
        consumed=consumed,
        pending_full_exit=pending_full_exit,
    )


def account(p, shares=0, cash="100000", receivable="0"):
    return p.Account(D(cash), shares, D(receivable))


def opening(p, session=102, price="100", volume=1000000, cost="5"):
    return p.Open(session, D(price), (D(volume),) * 20, D(cost))


def decide(p, state, price="100", *, overlay=True, terminal=False, bars=None, acct=None):
    return p.on_close(
        state,
        p.Close(101, bars if bars is not None else closes(price), terminal=terminal),
        acct or account(p, state.shares),
        overlay=overlay,
    )


def test_signal_strict_cross_and_equality_have_no_sizing_dependency():
    p = policy()
    assert p.doublema_signal(entering()) == "enter_long"
    assert p.doublema_signal(exiting()) == "exit_long"
    assert p.doublema_signal(closes()) == "hold"
    assert p.doublema_signal((D(100),) * 100 + (D(120),)) == "hold"
    assert p.doublema_signal(entering()[:100]) == "warmup"


def test_close_decision_exposes_the_actual_averages_for_explanation():
    p = policy()
    _, action = decide(p, p.Campaign(), bars=entering())
    assert action.averages == (D("101.1"), D("100.95"), D("99"), D("100"))


def test_warmup_cannot_create_a_pending_order():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering()[:100])
    assert action.kind == "hold"
    assert action.reason == "warmup"
    assert state.pending is None


@pytest.mark.parametrize("cash", ["100000", "0"])
def test_next_open_price_and_cash_do_not_change_close_signal(cash):
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering(), acct=account(p, cash=cash))
    assert action.signal == "enter_long"
    assert action.kind == "entry"
    assert action.requested is None
    _, at100 = p.size_at_open(state, action, opening(p), account(p, cash=cash))
    _, at120 = p.size_at_open(state, action, opening(p, price="120"), account(p, cash=cash))
    assert at100.allowed == (499 if cash == "100000" else 0)
    assert at120.allowed == (416 if cash == "100000" else 0)


def test_entry_inclusive_budget_exact_fee_and_fill_anchors():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    state, sized = p.size_at_open(state, action, opening(p), account(p))
    assert sized.requested == 499
    assert sized.allowed == 499
    assert sized.fee_at_allowed == D("24.95")
    state = p.on_fill(state, sized, p.Fill(102, 499, D(100)))
    assert (state.initial_price, state.initial_quantity, state.shares) == (D(100), 499, 499)
    assert state.pending is None


def test_zero_fill_entry_does_not_start_campaign():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    state, sized = p.size_at_open(state, action, opening(p), account(p))
    state = p.on_fill(state, sized, p.Fill(102, 0, D(100)))
    assert state.shares == state.initial_quantity == 0
    assert state.initial_price is None


def test_receivables_are_never_spendable():
    p = policy()
    acct = account(p, 100, cash="0", receivable="100")
    state, action = decide(p, held(p), price="85", acct=acct)
    state, sized = p.size_at_open(state, action, opening(p, price="85"), acct)
    assert sized.requested == 10
    assert sized.allowed == 0
    assert "cash" in sized.constraints
    state = p.on_fill(state, sized, p.Fill(102, 0, D(85)))
    assert state.consumed == ("add15",)


def test_post_fee_concentration_refuses_the_extra_share():
    p = policy()
    acct = account(p, 74, cash="2600")
    state, action = decide(p, held(p, shares=74), price="85", acct=acct)
    _, sized = p.size_at_open(state, action, opening(p), acct)
    assert sized.requested == 10
    assert sized.allowed == 0
    assert "concentration" in sized.constraints


@pytest.mark.parametrize(
    ("price", "requested", "stages"),
    [
        ("85", 10, ("add15",)),
        ("75", 35, ("add15", "add25")),
        ("125", 10, ("sell25",)),
        ("145", 60, ("sell25", "sell35", "sell45")),
        ("160", 100, ("sell25", "sell35", "sell45", "sell60")),
    ],
)
def test_exact_thresholds_and_jump_merge(price, requested, stages):
    p = policy()
    _, action = decide(p, held(p), price=price)
    assert action.requested == requested
    assert action.stages == stages


@pytest.mark.parametrize("price", ["95", "105", "115"])
def test_noop_levels_do_not_trade(price):
    p = policy()
    state, action = decide(p, held(p), price=price)
    assert action.kind == "hold"
    assert state.pending is None


def test_round_each_stage_before_merging_not_combined_fraction():
    p = policy()
    state, action = decide(p, held(p, shares=9, q0=9), price="135")
    assert action.requested == 1  # floor(.9)+floor(1.8), not floor(2.7)
    assert action.stages == ("sell25", "sell35")
    state, sized = p.size_at_open(state, action, opening(p, price="135"), account(p, 9))
    state = p.on_fill(state, sized, p.Fill(102, 1, D(135)))
    state, action = p.on_close(state, p.Close(102, closes("135")), account(p, 8))
    assert action.kind == "hold"


def test_additions_do_not_reanchor_or_overstate_profit_sales():
    p = policy()
    state, action = decide(p, held(p, shares=135), price="160")
    assert action.requested == 100
    state, sized = p.size_at_open(state, action, opening(p, price="160"), account(p, 135))
    state = p.on_fill(state, sized, p.Fill(102, 100, D(160)))
    assert state.shares == 35
    assert (state.initial_price, state.initial_quantity) == (D(100), 100)


def test_partial_stage_cancels_remainder_and_cannot_refire():
    p = policy()
    state, action = decide(p, held(p), price="75")
    state, sized = p.size_at_open(
        state, action, opening(p, price="75", volume=1000), account(p, 100)
    )
    assert sized.requested == 35 and sized.allowed == 10
    state = p.on_fill(state, sized, p.Fill(102, 4, D(75)))
    assert state.shares == 104
    assert set(state.consumed) == {"add15", "add25"}
    state, action = p.on_close(state, p.Close(102, closes("75")), account(p, 104))
    assert action.kind == "hold"


def test_trend_exit_beats_add_and_latches_across_hold():
    p = policy()
    state, action = decide(p, held(p, shares=25), bars=exiting())
    assert action.kind == "full_exit" and action.reason == "trend_exit"
    assert action.stages == ()
    state, sized = p.size_at_open(
        state, action, opening(p, price="80", volume=1000), account(p, 25)
    )
    state = p.on_fill(state, sized, p.Fill(102, 10, D(80)))
    assert state.pending_full_exit == "trend_exit" and state.shares == 15
    state, action = p.on_close(state, p.Close(102, closes("75")), account(p, 15))
    assert action.kind == "full_exit" and action.requested == 15
    assert action.stages == ()  # hold close below add thresholds still cannot buy


def test_full_exit_clears_campaign_only_when_fully_filled():
    p = policy()
    state, action = decide(p, held(p, shares=35), price="200")
    assert action.reason == "profit100"
    state, sized = p.size_at_open(state, action, opening(p, price="200"), account(p, 35))
    state = p.on_fill(state, sized, p.Fill(102, 35, D(200)))
    assert state.initial_price is None and state.initial_quantity == 0
    assert not state.consumed and state.pending_full_exit is None
    _, action = p.on_close(state, p.Close(102, closes("200")), account(p))
    assert action.kind == "hold"  # a persistent level is not a new enter cross


def test_terminal_cap_cannot_be_reported_as_complete():
    p = policy()
    state, action = decide(p, held(p, shares=11), terminal=True)
    assert action.reason == "terminal"
    state, sized = p.size_at_open(state, action, opening(p, volume=1000), account(p, 11))
    assert sized.allowed == 10
    with pytest.raises(ValueError, match="terminal_liquidation_incomplete"):
        p.on_fill(state, sized, p.Fill(102, 10, D(100)))


def test_overlay_off_keeps_signal_and_exit_but_skips_all_stages():
    p = policy()
    _, action = decide(p, held(p), price="75", overlay=False)
    assert action.kind == "hold"
    _, action = decide(p, held(p), bars=exiting(), overlay=False)
    assert action.kind == "full_exit"


def test_unavailable_close_preserves_exit_without_consuming_stages():
    p = policy()
    original = held(p, pending_full_exit="trend_exit")
    state, action = p.on_close(
        original, p.Close(101, closes("75"), available=False), account(p, 100)
    )
    assert action.kind == "hold" and action.reason == "unavailable"
    assert state.pending_full_exit == "trend_exit" and not state.consumed


def test_same_session_open_and_another_action_cannot_execute():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    with pytest.raises(ValueError, match="execution_session"):
        p.size_at_open(state, action, opening(p, session=101), account(p))
    with pytest.raises(ValueError, match="pending_action"):
        p.size_at_open(state, replace(action, reason="foreign"), opening(p), account(p))
    with pytest.raises(ValueError, match="pending_action"):
        p.on_close(state, p.Close(102, entering()), account(p))


@pytest.mark.parametrize("quantity", [-1, 500, True, 1.5])
def test_invalid_or_excess_supplied_fill_is_refused(quantity):
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    state, sized = p.size_at_open(state, action, opening(p), account(p))
    with pytest.raises(ValueError):
        p.on_fill(state, sized, p.Fill(102, quantity, D(100)))


def test_fill_price_session_identity_and_duplicate_order_are_checked():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    state, sized = p.size_at_open(state, action, opening(p), account(p))
    for fill in (p.Fill(101, 1, D(100)), p.Fill(102, 1, D(99))):
        with pytest.raises(ValueError, match="fill_binding"):
            p.on_fill(state, sized, fill)
    with pytest.raises(ValueError, match="pending_execution"):
        p.on_fill(state, replace(sized, allowed=500), p.Fill(102, 1, D(100)))
    done = p.on_fill(state, sized, p.Fill(102, 1, D(100)))
    with pytest.raises(ValueError, match="pending_execution"):
        p.on_fill(done, sized, p.Fill(102, 1, D(100)))


@pytest.mark.parametrize("bad", [D("NaN"), D("Infinity"), D("-1"), 1.5, True])
def test_invalid_fixture_numeric_values_fail_closed(bad):
    p = policy()
    with pytest.raises(ValueError):
        p.Account(bad, 0, D(0))


def test_unsupported_action_inconsistent_shares_and_bad_volume_refuse():
    p = policy()
    with pytest.raises(ValueError, match="unsupported_action"):
        p.on_close(p.Campaign(), p.Close(101, entering(), unsupported_action=True), account(p))
    with pytest.raises(ValueError, match="account_shares"):
        decide(p, held(p), acct=account(p, 99))
    with pytest.raises(ValueError):
        p.Open(102, D(100), (D(100),) * 19)


def test_sell_never_exceeds_owned_shares_and_zero_cap_stays_pending():
    p = policy()
    state, action = decide(p, held(p, shares=9), price="160")
    state, sized = p.size_at_open(state, action, opening(p, price="160"), account(p, 9))
    assert sized.requested == 100 and sized.allowed == 9
    assert "ownership" in sized.constraints
    state = p.on_fill(state, sized, p.Fill(102, 9, D(160)))
    assert state.shares == 0 and state.initial_price is None
    state, action = decide(p, held(p), bars=exiting())
    state, sized = p.size_at_open(state, action, opening(p, volume=0), account(p, 100))
    state = p.on_fill(state, sized, p.Fill(102, 0, D(100)))
    assert state.pending_full_exit == "trend_exit" and state.shares == 100


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/run_trend_overlay_candidate.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)


def test_cli_rejects_unknown_case_and_paths_without_trace():
    for args in (("--case", "arbitrary.csv"), ("--input", "anything")):
        run = run_cli(*args)
        assert run.returncode == 2
        assert run.stdout == ""
        assert "usage:" in run.stderr


def test_cli_fixed_case_is_stable_and_explains_both_arms():
    first = run_cli("--case", "campaign", "--format", "json")
    assert first.returncode == 0, first.stderr
    second = run_cli("--case", "campaign", "--format", "json")
    assert first.stdout == second.stdout
    trace = json.loads(first.stdout)
    assert trace["evidence_kind"] == "synthetic_policy_trace"
    assert trace["account_and_fill_inputs"] == "explicitly_supplied_fixture"
    assert set(trace["arms"]) == {"overlay_off", "overlay_on"}
    assert len(trace["trace_sha256"]) == len(trace["fixture_sha256"]) == 64
    on = trace["arms"]["overlay_on"]
    off = trace["arms"]["overlay_off"]
    assert any(row["action"]["kind"] == "add" for row in on)
    assert not any(row["action"]["kind"] == "add" for row in off)
    assert not any(key in trace for key in ("equity", "pnl", "returns", "sharpe"))


@pytest.mark.parametrize("case", ["exit-cap", "cash-cap"])
def test_cli_actual_boundary_examples_are_readable(case):
    run = run_cli("--case", case)
    assert run.returncode == 0, run.stderr
    assert "SYNTHETIC POLICY TRACE" in run.stdout
    assert "overlay_off" in run.stdout and "overlay_on" in run.stdout
    assert "requested" in run.stdout and "allowed" in run.stdout
    assert "supplied" in run.stdout and "SHA256" in run.stdout


def test_fixture_friction_and_identity_ignore_ambient_decimal_precision():
    from tools import run_trend_overlay_candidate as demo

    ordinary = demo.build_trace("campaign")
    with localcontext() as context:
        context.prec = 3
        constrained = demo.build_trace("campaign")
    assert constrained == ordinary
    assert ordinary["arms"]["overlay_on"][0]["friction_for_supplied_fill"] == "24.975"


def test_ten_bps_friction_changes_cash_budget_without_resizing_the_signal():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    _, sized = p.size_at_open(state, action, opening(p, cost="10"), account(p))
    assert action.signal == "enter_long"
    assert sized.allowed == 499 and sized.fee_at_allowed == D("49.9")


def test_sizing_cannot_be_repeated_before_the_supplied_fill():
    p = policy()
    state, action = decide(p, p.Campaign(), bars=entering())
    state, _ = p.size_at_open(state, action, opening(p), account(p))
    with pytest.raises(ValueError, match="pending_execution"):
        p.size_at_open(state, action, opening(p), account(p))


def test_zero_rounded_stage_is_consumed_after_explicit_zero_fill():
    p = policy()
    state, action = decide(p, held(p, shares=9, q0=9), price="125")
    assert action.requested == 0
    state, sized = p.size_at_open(state, action, opening(p, price="125"), account(p, 9))
    state = p.on_fill(state, sized, p.Fill(102, 0, D(125)))
    assert state.consumed == ("sell25",)
    _, action = p.on_close(state, p.Close(102, closes("125")), account(p, 9))
    assert action.kind == "hold"


def test_trace_hash_covers_fixture_inputs_and_observed_policy_outputs():
    import hashlib

    from tools import run_trend_overlay_candidate as demo

    trace = demo.build_trace("exit-cap")
    claimed = trace.pop("trace_sha256")
    canonical = json.dumps(trace, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == claimed
    rows = trace["arms"]["overlay_on"]
    assert [row["sizing"]["allowed"] for row in rows] == [10, 10, 5]
    assert [row["action"]["signal"] for row in rows] == ["exit_long", "hold", "hold"]
    assert rows[-1]["campaign_after"]["shares"] == 0
