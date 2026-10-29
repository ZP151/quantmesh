"""Closed synthetic candidate protocol over the sole native daily v2 cashbook.

No real-input admission, market access, public strategy loading or trading authority.
The policy receives a conservative view; only spy_replay_engine writes accounts.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import platform
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, Context, Decimal, localcontext
from pathlib import Path

import pandas as pd

from quantmesh.data.calendars import XNYS_REGULAR_VERSION, CalendarService, SessionPolicy
from quantmesh.data.objects import ObjectRef, ObjectStore
from quantmesh.research import spy_replay_engine as engine
from quantmesh.research import trend_overlay_candidate as policy

PROTOCOL = "qm.native-daily.candidate.protocol.v1"
REPORT = "qm.native-daily.candidate.report.v1"
CANDIDATE = "doublema_daily_overlay_candidate_v1"
ARMS = ("T", "TO", "B50", "B100", "C")
CASES = ("campaign-v1", "unpaid-v1", "flat-v1")
POLICY_SHA = "e2b3c018035c26f1d973022e0f3f4f8a93ba8ef8ecc8872ab5b649b56d49fbab"

# Immutable v1 fixture byte identities; no calendar/generator needed to reopen.
_V1_INPUTS = {
    "campaign-v1": {
        "bars": {
            "algorithm": "sha256",
            "byte_length": 4498,
            "digest": "31cf3153804996fbbedc4afedc1f99744cc425148a0086be50462ee3c2503439",
            "media_type": "text/csv",
        },
        "distributions": {
            "algorithm": "sha256",
            "byte_length": 63,
            "digest": "d2b4d4eb8654a0c80d920932ab2aac06854ebe5ec1eddf4c50b8291677a06bf2",
            "media_type": "application/json",
        },
        "schedule": {
            "algorithm": "sha256",
            "byte_length": 11254,
            "digest": "5555d340695b8d14248a3fc7a727369fa05aac2c0271c0e65fb3db1b134a497f",
            "media_type": "application/json",
        },
    },
    "flat-v1": {
        "bars": {
            "algorithm": "sha256",
            "byte_length": 4518,
            "digest": "7385d545621c4ae55ebdc4f4b8af3958bde8fdd45e2276e7ec8488cc59972561",
            "media_type": "text/csv",
        },
        "distributions": {
            "algorithm": "sha256",
            "byte_length": 2,
            "digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            "media_type": "application/json",
        },
        "schedule": {
            "algorithm": "sha256",
            "byte_length": 11254,
            "digest": "5555d340695b8d14248a3fc7a727369fa05aac2c0271c0e65fb3db1b134a497f",
            "media_type": "application/json",
        },
    },
    "unpaid-v1": {
        "bars": {
            "algorithm": "sha256",
            "byte_length": 4498,
            "digest": "31cf3153804996fbbedc4afedc1f99744cc425148a0086be50462ee3c2503439",
            "media_type": "text/csv",
        },
        "distributions": {
            "algorithm": "sha256",
            "byte_length": 63,
            "digest": "a515569f41383841a2a874d252c1d107ef4bc6f666483a1d29467496dda57b24",
            "media_type": "application/json",
        },
        "schedule": {
            "algorithm": "sha256",
            "byte_length": 11254,
            "digest": "5555d340695b8d14248a3fc7a727369fa05aac2c0271c0e65fb3db1b134a497f",
            "media_type": "application/json",
        },
    },
}

_AUTHORITY = object()
_MAX_OBJECT = 1024 * 1024


class CandidateError(ValueError):
    """Fixed safe engineering admission failure."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CandidateError("duplicate_key")
            result[key] = value
        return result

    if not isinstance(raw, bytes) or len(raw) > _MAX_OBJECT:
        raise CandidateError("object_bounds")
    try:
        return json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, TypeError, RecursionError):
        raise CandidateError("invalid_json") from None


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _ref(media, raw):
    return ObjectRef(digest=_sha(raw), byte_length=len(raw), media_type=media)


def _code():
    return {
        "kernel_version": engine.KERNEL_VERSION,
        "kernel_sha256": _sha(Path(engine.__file__).read_bytes()),
        "policy_sha256": _sha(Path(policy.__file__).read_bytes()),
        "adapter_sha256": _sha(Path(__file__).read_bytes()),
        "legacy_packaged_ancestor": engine.LEGACY_PACKAGED_SHA256,
    }


_LOADED_CODE = _code()


@dataclass(frozen=True)
class EngineeringInput:
    case: str
    bars_csv: bytes
    distributions_json: bytes
    schedule_json: bytes
    evidence_kind: str = "engineering_fixture"
    _authority: object = field(default=None, repr=False, compare=False)


def engineering_input(case="campaign-v1"):
    """Generate only the named, authored engineering fixture; not user data."""
    if case not in CASES:
        raise CandidateError("unknown_engineering_case")
    sessions = CalendarService().sessions(
        "XNYS", date(2026, 1, 2), date(2026, 7, 31), policy=SessionPolicy.REGULAR
    )[:121]
    dates = [s.session_date.isoformat() for s in sessions]
    closes = [100] * 80 + [101] * 10 + [99] * 10 + [120, 125, 135, 190] + [200] * 17
    opens = [100] * 101 + [150, 125, 135, 190] + [200] * 16
    if case == "flat-v1":
        closes, opens = [100] * 121, [100] * 121
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["date", "open", "high", "low", "close", "volume", "dividend"])
    for index, day in enumerate(dates):
        opening, closing = opens[index], closes[index]
        writer.writerow(
            [
                day,
                opening,
                max(opening, closing),
                min(opening, closing),
                closing,
                1000000,
                1 if index == 105 and case != "flat-v1" else 0,
            ]
        )
    events = [
        {
            "ex_date": dates[105],
            "pay_date": dates[108] if case == "campaign-v1" else "2027-01-04",
            "amount": 1.0,
        }
    ]
    if case == "flat-v1":
        events = []
    schedule = [
        {
            "date": s.session_date.isoformat(),
            "open": s.open_at.isoformat(),
            "close": s.close_at.isoformat(),
        }
        for s in sessions
    ]
    return EngineeringInput(
        case,
        stream.getvalue().encode(),
        canonical(events),
        canonical(schedule),
        _authority=_AUTHORITY,
    )


def _checked(value):
    if (
        not isinstance(value, EngineeringInput)
        or value._authority is not _AUTHORITY
        or value.evidence_kind != "engineering_fixture"
    ):
        raise CandidateError("input_not_qualified")
    expected = engineering_input(value.case)
    if (value.bars_csv, value.distributions_json, value.schedule_json) != (
        expected.bars_csv,
        expected.distributions_json,
        expected.schedule_json,
    ):
        raise CandidateError("input_not_qualified")
    if _code() != _LOADED_CODE or _LOADED_CODE["policy_sha256"] != POLICY_SHA:
        raise CandidateError("implementation_drift")
    return value


def _contract(case, inputs, code, runtime):
    """Versioned v1 semantics; archived validation never invokes current generation."""
    return {
        "schema_id": PROTOCOL,
        "candidate": CANDIDATE,
        "case": case,
        "evidence_kind": "engineering_fixture",
        "code": code,
        "runtime": runtime,
        "inputs": inputs,
        "window": {
            "warmup": 100,
            "observations": 21,
            "calendar": "XNYS",
            "decision": "completed_close_plus30min_assumed",
            "fill": "next_raw_OPEN_proxy",
            "terminal": "final_OPEN_no_final_close",
            "timestamps": "synthetic_declared",
        },
        "rules": {
            "fast": 10,
            "slow": 20,
            "initial_fraction": "0.50",
            "post_fee_cap": "0.75",
            "volume_cap": "0.01_prior20_median",
            "cash_view": "exact_float_decimal_floor_1e-8_readonly",
            "buy": [["-0.15", ".10"], ["-0.25", ".25"]],
            "sell": [[".25", ".10"], [".35", ".20"], [".45", ".30"], [".60", ".40"]],
            "all_exit": "+1.00_or_trend_or_terminal",
            "split": "refuse",
            "campaign_basis": "P0_Q0_are_initial_actual_fill",
            "ordinary_stage": "one_opportunity_cancel_unfilled",
            "full_exit": "retry_remaining_preserving_original_action",
            "distribution": "overnight_ex_entitlement_pay_OPEN_credit",
            "shorts": False,
            "leverage": False,
        },
        "costs": {
            "model": "combined_one_way_turnover_proxy",
            "base5": 5,
            "stress10": 10,
            "cash_interest": 0,
            "fee_components": None,
            "calibrated": False,
        },
        "arms": list(ARMS),
        "benchmark100_cap_exception": "1.00",
        "source_use": "synthetic_no_vendor",
        "currency": "USD",
        "price_adjustment": "constructed_raw",
        "action_coverage": "fixed_cash_dividends_ex_pay_no_splits",
        "source_review_refs": [],
        "exposure": {
            "historical_SPY": "exposed_consumed_not_admitted",
            "old_once_scope": "consumed_not_transferable",
            "new_empirical_trial_ledger_ref": None,
        },
        "volume_unit": "constructed_shares",
        "trade_venues": "not_market_evidence",
        "PIT": "not_applicable_synthetic",
        "sample_role": "fixed_engineering",
        "unseen_OOS": False,
        "empirical_trial": False,
        "historical_trial_count": None,
        "trial_count_reason": "unknown_prior_search_no_new_empirical_trial",
        "legacy_once_or_OOS_admission": False,
        "real_input_enabled": False,
        "financial_qualification": "INSUFFICIENT",
        "paper_allowed": False,
        "live_allowed": False,
    }


def _protocol(value):
    _checked(value)
    inputs = {
        "bars": _ref("text/csv", value.bars_csv).model_dump(),
        "distributions": _ref("application/json", value.distributions_json).model_dump(),
        "schedule": _ref("application/json", value.schedule_json).model_dump(),
    }
    if inputs != _V1_INPUTS[value.case]:
        raise CandidateError("implementation_drift")
    runtime = {
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": engine.np.__version__,
        "calendar": XNYS_REGULAR_VERSION,
    }
    return _contract(value.case, inputs, _LOADED_CODE, runtime)


def freeze_protocol(value):
    return canonical(_protocol(value))


def conservative_money(value):
    with localcontext(Context(prec=40)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CandidateError("numeric_boundary_mismatch")
        raw = Decimal.from_float(float(value))
        if not raw.is_finite() or raw < 0:
            raise CandidateError("numeric_boundary_mismatch")
        return raw.quantize(Decimal("0.00000001"), rounding=ROUND_FLOOR)


def _price(value):
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0 or number.as_tuple().exponent < -8:
        raise CandidateError("price_not_representable")
    return number


class _Arm:
    """Only campaign state/observations here; no cash or share-account mutation."""

    def __init__(self, frame, name):
        self.frame, self.name = frame, name
        self.state, self.sized = policy.Campaign(), None
        self.trace = []

    @staticmethod
    def account(cash, shares, receivable):
        return policy.Account(conservative_money(cash), shares, conservative_money(receivable))

    def propose(self, view):
        self.sized = None
        account = self.account(view.cash, view.shares, view.receivable)
        price = _price(view.open_price)
        if self.name in ("T", "TO"):
            action = self.state.pending
            if action is None:
                return engine.QuantityOrder(0)
            opening = policy.Open(
                view.index,
                price,
                tuple(Decimal(str(v)) for v in view.prior_volumes),
                Decimal(str(view.cost_bps)),
            )
            self.state, self.sized = policy.size_at_open(self.state, action, opening, account)
            signed = self.sized.allowed * (1 if action.kind in ("entry", "add") else -1)
            return engine.QuantityOrder(
                signed,
                self.sized.requested,
                0.75 if signed > 0 else None,
                0.5 if action.kind == "entry" else None,
                _plain(
                    {
                        "action": asdict(action),
                        "constraints": self.sized.constraints,
                        "full_exit_origin": asdict(self.state.full_exit_origin)
                        if self.state.full_exit_origin
                        else None,
                    }
                ),
            )
        if view.terminal:
            return engine.QuantityOrder(-view.shares)
        if view.first and self.name in ("B50", "B100"):
            fraction = Decimal(".5") if self.name == "B50" else Decimal(1)
            with localcontext(Context(prec=40)):
                equity = account.cash + view.shares * price + account.receivable
                quantity = int(
                    fraction * equity / (price * (1 + Decimal(str(view.cost_bps)) / 10000))
                )
            return engine.QuantityOrder(
                quantity,
                max_fraction=0.75 if self.name == "B50" else 1,
                budget_fraction=float(fraction),
            )
        return engine.QuantityOrder(0)

    def filled(self, view, order, quantity, friction, cash, shares, receivable):
        if self.sized is not None:
            self.state = policy.on_fill(
                self.state,
                self.sized,
                policy.Fill(view.index, abs(quantity), _price(view.open_price)),
            )
        self.trace.append(
            _plain(
                {
                    "session": view.index,
                    "date": view.date,
                    "order": asdict(order),
                    "filled": quantity,
                    "friction": friction,
                    "cash_view": conservative_money(view.cash),
                    "cash_raw_decimal": str(Decimal.from_float(float(view.cash))),
                    "post_cash": cash,
                    "post_shares": shares,
                    "post_receivable": receivable,
                    "cancelled": (
                        order.requested_quantity
                        if order.requested_quantity is not None
                        else abs(order.quantity)
                    )
                    - abs(quantity),
                    "campaign": asdict(self.state) if self.name in ("T", "TO") else None,
                }
            )
        )

    def closed(self, day, index, cash, shares, receivable):
        if self.name not in ("T", "TO"):
            return
        history = tuple(_price(v) for v in self.frame.close.iloc[: index + 1])
        self.state, _ = policy.on_close(
            self.state,
            policy.Close(index, history, terminal=index == len(self.frame) - 2),
            self.account(cash, shares, receivable),
            overlay=self.name == "TO",
        )


def _child_binding(request_digest, arm, bps):
    return {
        "schema_id": "qm.native-daily.candidate.arm.v1",
        "request_digest": request_digest,
        "arm": arm,
        "cost_bps": bps,
    }


_METRIC_FIELDS = frozenset(
    (
        "sessions",
        "start",
        "end",
        "terminal_equity",
        "net_profit_usd",
        "total_return",
        "cagr",
        "max_drawdown",
        "max_underwater_sessions",
        "annualized_volatility",
        "naive_sharpe_rf_zero",
        "sortino_target_zero",
        "calmar",
        "worst_day",
        "historical_es_95",
        "es_tail_observations",
        "fills",
        "friction_usd",
        "dividend_earned_usd",
        "dividend_paid_usd",
        "terminal_receivable",
        "gross_traded_notional_over_initial_capital",
        "capacity_clipped_sessions",
        "terminal_shares",
        "buy_fill_count",
        "campaign_entry_count",
    )
)
_DAILY_FIELDS = frozenset(
    (
        "date",
        "signal_date",
        "target",
        "shares",
        "cash",
        "receivable",
        "mark",
        "equity",
        "net_return",
        "dividend_earned",
        "dividend_paid",
        "friction",
        "capacity_clipped",
    )
)


_TRADE_FIELDS = frozenset(
    (
        "date",
        "signal_date",
        "quantity",
        "price",
        "friction",
        "post_cash",
        "post_shares",
        "participation_cap",
        "capacity_clipped",
        "forced_terminal_liquidation",
        "quantity_policy",
    )
)
_TRACE_FIELDS = frozenset(
    (
        "session",
        "date",
        "order",
        "filled",
        "friction",
        "cash_view",
        "cash_raw_decimal",
        "post_cash",
        "post_shares",
        "post_receivable",
        "cancelled",
        "campaign",
    )
)
_ORDER_FIELDS = frozenset(
    ("quantity", "requested_quantity", "max_fraction", "budget_fraction", "metadata")
)
_COUNT_FIELDS = frozenset(
    (
        "sessions",
        "max_underwater_sessions",
        "es_tail_observations",
        "fills",
        "capacity_clipped_sessions",
        "terminal_shares",
        "buy_fill_count",
        "campaign_entry_count",
    )
)


def _shaped(rows, fields):
    return isinstance(rows, list) and all(
        isinstance(row, dict) and set(row) == fields for row in rows
    )


def _check_matrix(result, schedule):
    """Check the complete v1 archive shape/bindings without rerunning any math."""
    dates = [row["date"] for row in schedule[100:]]
    matrix = result["calculation"]
    if not isinstance(matrix, dict) or set(matrix) != {"base5", "stress10"}:
        raise ValueError("matrix")
    for scenario, bps in (("base5", 5), ("stress10", 10)):
        if not isinstance(matrix[scenario], dict) or set(matrix[scenario]) != set(ARMS):
            raise ValueError("arms")
        for name in ARMS:
            child = matrix[scenario][name]
            binding = _child_binding(result["request_digest"], name, bps)
            if (
                not isinstance(child, dict)
                or set(child) != {"binding", "child_id", "metrics", "daily", "trades", "trace"}
                or canonical(child["binding"]) != canonical(binding)
                or child["child_id"] != _sha(canonical(binding))
            ):
                raise ValueError("child_identity")
            metrics, daily = child["metrics"], child["daily"]
            if (
                not isinstance(metrics, dict)
                or set(metrics) != _METRIC_FIELDS
                or any(type(metrics[key]) is not int or metrics[key] < 0 for key in _COUNT_FIELDS)
                or metrics["sessions"] != 21
                or metrics["start"] != dates[0]
                or metrics["end"] != dates[-1]
                or metrics["terminal_shares"] != 0
                or not isinstance(daily, list)
                or len(daily) != 21
                or any(not isinstance(row, dict) or set(row) != _DAILY_FIELDS for row in daily)
                or not _shaped(child["trades"], _TRADE_FIELDS)
                or not _shaped(child["trace"], _TRACE_FIELDS)
                or len(child["trace"]) != 21
            ):
                raise ValueError("incomplete_result")
            if [row["date"] for row in daily] != dates:
                raise ValueError("daily_sessions")
            for index, trace in enumerate(child["trace"], 100):
                if (
                    trace["session"] != index
                    or trace["date"] != dates[index - 100]
                    or not isinstance(trace["order"], dict)
                    or set(trace["order"]) != _ORDER_FIELDS
                    or type(trace["filled"]) is not int
                ):
                    raise ValueError("trace_binding")
            fills = [row for row in child["trace"] if row["filled"] != 0]
            if len(child["trades"]) != metrics["fills"] or len(fills) != metrics["fills"]:
                raise ValueError("fill_ledger_incomplete")
            # Compare original redundant records only; do not calculate balances/fees/metrics.
            for trade, fill in zip(child["trades"], fills, strict=True):
                expected = {
                    "date": fill["date"],
                    "quantity": fill["filled"],
                    "friction": fill["friction"],
                    "post_cash": fill["post_cash"],
                    "post_shares": fill["post_shares"],
                    "quantity_policy": fill["order"]["metadata"] or {},
                }
                if type(trade["quantity"]) is not int or any(
                    trade[key] != value for key, value in expected.items()
                ):
                    raise ValueError("fill_ledger_binding")


def _calculate_matrix(frame, distributions, protocol_digest):
    """Internal common calculation; each caller retains its own admission guard."""
    calculation = {}
    for name, bps in (("base5", 5), ("stress10", 10)):
        calculation[name] = {}
        for arm_name in ARMS:
            arm = _Arm(frame, arm_name)
            # Signal placeholder is not used by the quantity policy; no alternate cashbook.
            daily, trades = engine.run_cashbook(
                frame,
                pd.Series(0, index=frame.index),
                distributions,
                frame.index[100],
                frame.index[-1],
                cost_bps=bps,
                _quantity_policy=arm,
            )
            engine._reconcile(daily, trades, bps)
            measured = engine.metrics(daily, trades)
            measured["buy_fill_count"] = measured.pop("long_entries")
            measured["campaign_entry_count"] = sum(
                t["quantity"] > 0
                and t.get("quantity_policy", {}).get("action", {}).get("kind") == "entry"
                for t in trades
            )
            binding = _child_binding(protocol_digest, arm_name, bps)
            calculation[name][arm_name] = {
                "binding": binding,
                "child_id": _sha(canonical(binding)),
                "metrics": measured,
                "daily": daily.rename_axis("date").reset_index().to_dict(orient="records"),
                "trades": trades,
                "trace": arm.trace,
            }
    return calculation


def evaluate(value, protocol_bytes):
    _checked(value)
    protocol = _json(protocol_bytes)
    if protocol_bytes != canonical(_protocol(value)):
        raise CandidateError("protocol_not_qualified")
    frame = pd.read_csv(io.BytesIO(value.bars_csv), dtype={"date": str}).set_index("date")
    distributions = _json(value.distributions_json)
    calculation = _calculate_matrix(frame, distributions, _sha(protocol_bytes))
    report = {
        "schema_id": REPORT,
        "candidate": CANDIDATE,
        "evidence_kind": "engineering_fixture",
        "request_digest": _sha(protocol_bytes),
        "protocol_ref": _ref("application/json", protocol_bytes).model_dump(),
        "inputs": protocol["inputs"],
        "code": protocol["code"],
        "calculation": calculation,
        "financial_qualification": "INSUFFICIENT",
        "paper_allowed": False,
        "live_allowed": False,
    }
    result = engine._plain(report)
    if len(canonical(result)) > _MAX_OBJECT:
        raise CandidateError("result_too_large")
    return result


def publish(value, protocol_bytes, store: ObjectStore):
    result = evaluate(value, protocol_bytes)
    # No input/output object is written for a rejected protocol or failed calculation.
    for name, raw in (
        ("bars", value.bars_csv),
        ("distributions", value.distributions_json),
        ("schedule", value.schedule_json),
    ):
        expected = ObjectRef.model_validate(result["inputs"][name])
        if store.put_bytes(expected.media_type, raw) != expected:
            raise CandidateError("input_identity")
    if store.put_bytes("application/json", protocol_bytes).model_dump() != result["protocol_ref"]:
        raise CandidateError("protocol_identity")
    return store.put_bytes("application/json", canonical(result))


def read_result(store: ObjectStore, reference: ObjectRef):
    """Original validated bytes only. Never call evaluate or compare to current source."""
    raw = store.get_bytes(reference)
    result = _json(raw)
    try:
        protocol_raw = store.get_bytes(ObjectRef.model_validate(result["protocol_ref"]))
        protocol = _json(protocol_raw)
        if not isinstance(protocol, dict):
            raise ValueError
        code, runtime = protocol["code"], protocol["runtime"]
        if (
            not isinstance(code, dict)
            or set(code) != set(_LOADED_CODE)
            or code["kernel_version"] != "native-daily-v2"
            or code["legacy_packaged_ancestor"] != engine.LEGACY_PACKAGED_SHA256
            or code["policy_sha256"] != POLICY_SHA
            or any(
                not isinstance(code[key], str) or re.fullmatch(r"[0-9a-f]{64}", code[key]) is None
                for key in ("kernel_sha256", "policy_sha256", "adapter_sha256")
            )
            or not isinstance(runtime, dict)
            or set(runtime) != {"python", "pandas", "numpy", "calendar"}
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 80 for item in runtime.values()
            )
        ):
            raise ValueError
        # Archived source/runtime identities remain original; invariant v1 semantics do not.
        expected = _contract(protocol["case"], _V1_INPUTS[protocol["case"]], code, runtime)
        if protocol_raw != canonical(expected):
            raise ValueError
        if (
            result["schema_id"] != REPORT
            or protocol["schema_id"] != PROTOCOL
            or result["request_digest"] != _sha(protocol_raw)
            or result["candidate"] != protocol["candidate"]
            or result["candidate"] != CANDIDATE
            or result["inputs"] != protocol["inputs"]
            or result["code"] != protocol["code"]
            or result["evidence_kind"] != "engineering_fixture"
            or protocol["evidence_kind"] != "engineering_fixture"
            or result["financial_qualification"] != "INSUFFICIENT"
            or result["paper_allowed"] is not False
            or result["live_allowed"] is not False
        ):
            raise ValueError
        stored_inputs = {
            name: store.get_bytes(ObjectRef.model_validate(ref))
            for name, ref in result["inputs"].items()
        }
        _check_matrix(result, _json(stored_inputs["schedule"]))
    except (KeyError, ValueError, TypeError):
        raise CandidateError("artifact_invalid") from None
    return raw
