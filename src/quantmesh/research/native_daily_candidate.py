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
CASES = ("campaign-v1", "unpaid-v1")
POLICY_SHA = "e2b3c018035c26f1d973022e0f3f4f8a93ba8ef8ecc8872ab5b649b56d49fbab"
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
                1 if index == 105 else 0,
            ]
        )
    events = [
        {
            "ex_date": dates[105],
            "pay_date": dates[108] if case == "campaign-v1" else "2027-01-04",
            "amount": 1.0,
        }
    ]
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


def _protocol(value):
    _checked(value)
    return {
        "schema_id": PROTOCOL,
        "candidate": CANDIDATE,
        "case": value.case,
        "evidence_kind": "engineering_fixture",
        "code": _LOADED_CODE,
        "runtime": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": engine.np.__version__,
            "calendar": XNYS_REGULAR_VERSION,
        },
        "inputs": {
            "bars": _ref("text/csv", value.bars_csv).model_dump(),
            "distributions": _ref("application/json", value.distributions_json).model_dump(),
            "schedule": _ref("application/json", value.schedule_json).model_dump(),
        },
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
                tuple(_price(v) for v in view.prior_volumes),
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


def evaluate(value, protocol_bytes):
    _checked(value)
    protocol = _json(protocol_bytes)
    if protocol != _protocol(value) or canonical(protocol) != protocol_bytes:
        raise CandidateError("protocol_not_qualified")
    frame = pd.read_csv(io.BytesIO(value.bars_csv), dtype={"date": str}).set_index("date")
    distributions = _json(value.distributions_json)
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
            calculation[name][arm_name] = {
                "metrics": measured,
                "daily": daily.rename_axis("date").reset_index().to_dict(orient="records"),
                "trades": trades,
                "trace": arm.trace,
            }
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
        for ref in result["inputs"].values():
            store.get_bytes(ObjectRef.model_validate(ref))
    except (KeyError, ValueError, TypeError):
        raise CandidateError("artifact_invalid") from None
    return raw
