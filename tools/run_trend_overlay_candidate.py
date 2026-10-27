"""Inspect fixed synthetic policy cases, never market backtests or generated fills."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from decimal import Context, Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantmesh.research import trend_overlay_candidate as policy  # noqa: E402

CASES = ("campaign", "exit-cap", "cash-cap")
ARMS = ("overlay_off", "overlay_on")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fixture_friction(fill, opening):
    with localcontext(Context(prec=40)):
        return fill.quantity * fill.price * opening.cost_bps / 10000


def _step(session, history, price, off_account, on_account, off_fill, on_fill, **flags):
    return {
        "session": session,
        "closes": history,
        "open_price": price,
        "prior_volume": flags.pop("volume", "1000000"),
        "terminal": flags.pop("terminal", False),
        "accounts": {"overlay_off": off_account, "overlay_on": on_account},
        "supplied_fills": {"overlay_off": off_fill, "overlay_on": on_fill},
    }


def fixed_fixture(case):
    """Literal preauthored account/fill snapshots; no trade-derived cash updates."""
    if case not in CASES:
        raise ValueError("unknown_case")
    flat = {"shares": 0, "initial_price": None, "initial_quantity": 0}
    if case == "campaign":
        history = ["100"] * 80 + ["101"] * 10 + ["99"] * 10 + ["120"]
        steps = [
            _step(101, history.copy(), "150", ["100000", 0, "0"], ["100000", 0, "0"], 333, 333)
        ]
        # These cash numbers are authored fixture values, never computed by the runner.
        history = history + ["125"]
        steps.append(
            _step(
                102,
                history.copy(),
                "125",
                ["50025.025", 333, "0"],
                ["50025.025", 333, "0"],
                None,
                33,
            )
        )
        history = history + ["135"]
        steps.append(
            _step(
                103,
                history.copy(),
                "135",
                ["50025.025", 333, "0"],
                ["45897.9625", 366, "0"],
                None,
                None,
            )
        )
        history = history + ["190"]
        steps.append(
            _step(
                104,
                history.copy(),
                "190",
                ["50025.025", 333, "0"],
                ["45897.9625", 366, "0"],
                None,
                33,
            )
        )
        history = history + ["200"]
        steps.append(
            _step(
                105,
                history.copy(),
                "200",
                ["50025.025", 333, "0"],
                ["52164.8275", 333, "0"],
                333,
                333,
                terminal=True,
            )
        )
        episodes = [{"name": "entry_add_reduce_scheduled_exit", "initial": flat, "steps": steps}]
    elif case == "exit-cap":
        initial = {"shares": 25, "initial_price": "100", "initial_quantity": 100}
        history = ["100"] * 80 + ["99"] * 10 + ["101"] * 10 + ["80"]
        steps = [
            _step(
                101,
                history.copy(),
                "80",
                ["90000", 25, "0"],
                ["90000", 25, "0"],
                10,
                10,
                volume="1000",
            )
        ]
        history = history + ["75"]
        steps.append(
            _step(
                102,
                history.copy(),
                "75",
                ["90799.6", 15, "0"],
                ["90799.6", 15, "0"],
                10,
                10,
                volume="1000",
            )
        )
        history = history + ["70"]
        steps.append(
            _step(
                103,
                history.copy(),
                "70",
                ["91549.225", 5, "0"],
                ["91549.225", 5, "0"],
                5,
                5,
                volume="1000",
            )
        )
        episodes = [
            {"name": "persistent_exit_after_partial_fill", "initial": initial, "steps": steps}
        ]
    else:
        episodes = []
        for name, shares, cash, receivable, price in (
            ("receivable_is_not_cash", 100, "0", "100", "85"),
            ("post_fee_concentration", 74, "2600", "0", "100"),
        ):
            initial = {"shares": shares, "initial_price": "100", "initial_quantity": 100}
            acct = [cash, shares, receivable]
            steps = [_step(101, ["85"] * 101, price, acct, acct, None, 0)]
            episodes.append({"name": name, "initial": initial, "steps": steps})
    return {"evidence_kind": "synthetic_fixture", "case": case, "episodes": episodes}


def build_trace(case):
    fixture = fixed_fixture(case)
    arms = {}
    for arm in ARMS:
        rows = []
        for episode in fixture["episodes"]:
            initial = episode["initial"]
            state = policy.Campaign(
                shares=initial["shares"],
                initial_price=(
                    Decimal(initial["initial_price"])
                    if initial["initial_price"] is not None
                    else None
                ),
                initial_quantity=initial["initial_quantity"],
            )
            for step in episode["steps"]:
                cash, shares, receivable = step["accounts"][arm]
                account = policy.Account(Decimal(cash), shares, Decimal(receivable))
                observation = policy.Close(
                    step["session"],
                    tuple(Decimal(item) for item in step["closes"]),
                    terminal=step["terminal"],
                )
                before = state
                state, action = policy.on_close(
                    state, observation, account, overlay=arm == "overlay_on"
                )
                row = {
                    "episode": episode["name"],
                    "close_session": step["session"],
                    "close_input": asdict(observation),
                    "supplied_account": asdict(account),
                    "campaign_before": asdict(before),
                    "action": asdict(action),
                    "sizing": None,
                    "supplied_fill": None,
                }
                provided = step["supplied_fills"][arm]
                if action.kind == "hold":
                    if provided is not None:
                        raise ValueError("fixture_fill_without_action")
                else:
                    if type(provided) is not int:
                        raise ValueError("fixture_explicit_fill_required")
                    opening = policy.Open(
                        step["session"] + 1,
                        Decimal(step["open_price"]),
                        (Decimal(step["prior_volume"]),) * 20,
                    )
                    state, sized = policy.size_at_open(state, action, opening, account)
                    fill = policy.Fill(opening.session, provided, opening.price)
                    state = policy.on_fill(state, sized, fill)
                    row.update(
                        open_input=asdict(opening),
                        sizing=asdict(sized),
                        supplied_fill=asdict(fill),
                        cancelled_remainder=sized.requested - fill.quantity,
                        # Engineering proxy on the supplied fill, never a cash-account write.
                        friction_for_supplied_fill=_fixture_friction(fill, opening),
                    )
                row["campaign_after"] = asdict(state)
                rows.append(_plain(row))
        arms[arm] = rows
    trace = {
        "schema_version": 1,
        "candidate": "doublema_daily_overlay_candidate_v1",
        "case": case,
        "evidence_kind": "synthetic_policy_trace",
        "account_and_fill_inputs": "explicitly_supplied_fixture",
        "assumptions": [
            "Ordinal sessions describe close then next open; no real calendar/PIT qualification.",
            "All account/fill snapshots are authored fixtures; no generated trades or balances.",
            "5bps one-way friction is an engineering proxy, not calibrated execution cost.",
            "No cash ledger, matching engine, returns, profitability or trading authority.",
        ],
        "fixture_sha256": _digest(fixture),
        "source_identity": {
            "policy_sha256": hashlib.sha256(Path(policy.__file__).read_bytes()).hexdigest(),
            "cli_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "arms": arms,
    }
    return {**trace, "trace_sha256": _digest(trace)}


def render_text(trace):
    lines = [
        f"SYNTHETIC POLICY TRACE | {trace['case']}",
        "Account and fill events: explicitly supplied fixtures. No generated fills or P&L.",
        f"Trace SHA256: {trace['trace_sha256']}",
        f"Fixture SHA256: {trace['fixture_sha256']}",
    ]
    for arm, rows in trace["arms"].items():
        lines.extend(("", arm))
        for row in rows:
            action, sized = row["action"], row["sizing"]
            lines.append(
                f"  {row['episode']} | CLOSE {row['close_session']} "
                f"signal={action['signal']} action={action['kind']} reason={action['reason']}"
            )
            if action["averages"]:
                fast, slow, previous_fast, previous_slow = action["averages"]
                lines.append(
                    f"    F={fast} S={slow} prior_F={previous_fast} prior_S={previous_slow}"
                )
            if sized:
                lines.append(
                    f"    next OPEN {sized['session']} price={sized['price']} "
                    f"requested={sized['requested']} allowed={sized['allowed']} "
                    f"supplied_fill={row['supplied_fill']['quantity']} "
                    f"cancelled={row['cancelled_remainder']} "
                    f"proxy_friction={row['friction_for_supplied_fill']} "
                    f"constraints={','.join(sized['constraints']) or 'none'}"
                )
            else:
                lines.append("    requested=0 allowed=0 supplied_fill=none")
            state = row["campaign_after"]
            lines.append(
                f"    shares={state['shares']} P0={state['initial_price']} "
                f"Q0={state['initial_quantity']} "
                f"consumed={','.join(state['consumed']) or 'none'} "
                f"pending_full_exit={state['pending_full_exit'] or 'none'}"
            )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--case", choices=CASES, default="campaign")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        trace = build_trace(args.case)
    except ValueError as error:
        parser.error(f"Invalid fixed fixture: {error}")
    print(_canonical(trace).decode() if args.format == "json" else render_text(trace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
