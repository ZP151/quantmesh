"""One operator-owned US.SPY daily freeze, with no financial evaluation.

Source/account/use review is a trusted external prerequisite, not a permission
inferred from this tool's flags. Never run concurrently on another OpenD host.
Official field references: moomoo API get-rehab and corporate-actions-dividends.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import stat
import sys
from contextlib import contextmanager, nullcontext
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# A fixed repository location, never a caller-supplied import/code path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from quantmesh.data.calendars import CalendarService, SessionPolicy  # noqa: E402
from quantmesh.data.objects import ObjectRef, ObjectStore, is_reparse_point  # noqa: E402
from quantmesh.domain.models import Instrument, InstrumentType, Venue  # noqa: E402
from quantmesh.moomoo.opend import MoomooOpenDClient  # noqa: E402
from quantmesh.moomoo.provider import MoomooOpenDProvider  # noqa: E402
from quantmesh.research import spy_policy_exception as once  # noqa: E402

ENGINE_ORIGINAL_SHA256 = "bf69680b7d3e2be8e3c9b6baf8a19ab09972fa501118cc3b0c9aa9045b056f22"
MAX_BYTES = 8 * 1024 * 1024
MAX_ACTION_ROWS = 512
_LOADED_SOURCE = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_NY = ZoneInfo("America/New_York")
_SOURCE_MODULES = (
    "quantmesh.moomoo.provider",
    "quantmesh.moomoo.opend",
    "quantmesh.moomoo.market_data",
    "quantmesh.data.calendars",
    "quantmesh.data.objects",
)


def _source_identity():
    repo = Path(__file__).resolve().parents[2]
    result = {}
    for name in _SOURCE_MODULES:
        path = Path(sys.modules[name].__file__).resolve()
        identity = "src/" + name.replace(".", "/") + ".py"
        if path != repo / identity:
            raise ValueError("source_origin_invalid")
        result[identity] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


_LOADED_SOURCES = _source_identity()
_LOADED_POLICY_SOURCE = hashlib.sha256(Path(once.__file__).read_bytes()).hexdigest()


def _policy_source_identity():
    path = Path(once.__file__).resolve()
    expected = (
        Path(__file__).resolve().parents[2] / "src/quantmesh/research/spy_policy_exception.py"
    )
    if path != expected or hashlib.sha256(path.read_bytes()).hexdigest() != _LOADED_POLICY_SOURCE:
        raise ValueError("policy_source_origin_invalid")
    return _LOADED_POLICY_SOURCE


class FreezeError(ValueError):
    """Fixed safe code; CLI never prints raw SDK errors or input values."""


class SourceEvidence(BaseModel):
    """Historical v1 receipt; accepted only for strict read-only normalization/reopen."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]
    status: Literal["qualified_for_capture"]
    scope: Literal["US.SPY/1d/private_research"]
    use_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    account_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_semantics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checked_at_utc: str
    history_available: Literal[True]
    spy_quota_available: Literal[True]
    full_action_history_reviewed: Literal[True]
    feed: str = Field(min_length=1, max_length=200)
    currency: Literal["USD"]
    price_adjustment: Literal["raw"]
    daily_session_semantics: Literal["regular_session_daily_proxy"]
    volume_unit: Literal["shares"]
    dividend_unit: Literal["USD/share"]
    event_date_format: Literal["%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d"]
    sdk_version: str = Field(min_length=1, max_length=100)
    opend_version: str = Field(min_length=1, max_length=100)


class CaptureAuthorization(BaseModel):
    """Trusted external authorization for one request, never data qualification."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[2]
    status: Literal["authorized_for_bounded_capture"]
    scope: Literal["US.SPY/1d/private_research"]
    use_status: Literal["ALLOW_WITH_SCOPE"]
    use_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    account_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_observed_at_utc: str
    prechecked_at_utc: str
    as_of_utc: str
    window_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote_logged_in: Literal[True]
    program_ready: Literal[True]
    spy_quota_available: Literal[True]
    endpoint_host: Literal["127.0.0.1"]
    endpoint_port: int = Field(ge=1, le=65535)
    sdk_version: str = Field(min_length=1, max_length=100)
    opend_version: str = Field(min_length=1, max_length=100)


class PostReview(BaseModel):
    """External scoped review of actual bound responses; not independent legal proof."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[2]
    status: Literal["reviewed_for_freeze"]
    scope: Literal["US.SPY/1d/private_research"]
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_at_utc: str
    history_available: Literal[True]
    full_action_history_reviewed: Literal[True]
    action_coverage_status: Literal["complete_for_locked_window"]
    action_coverage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_semantics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feed: str = Field(min_length=1, max_length=200)
    currency: Literal["USD"]
    price_adjustment: Literal["raw"]
    daily_session_semantics: Literal["regular_session_daily_proxy"]
    volume_unit: Literal["shares"]
    dividend_unit: Literal["USD/share"]
    event_date_format: Literal["%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d"]


class CaptureAuthorizationV3(CaptureAuthorization):
    schema_version: Literal[3]
    use_status: Literal["POLICY_EXCEPTION_ONCE"]
    policy_exception: once.OnceBinding


class PostReviewV3(PostReview):
    schema_version: Literal[3]
    policy_exception: once.OnceBinding
    capture_intent_ref: ObjectRef


def _canonical(value) -> bytes:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise FreezeError("invalid_json") from None
    if len(raw) > MAX_BYTES:
        raise FreezeError("payload_too_large")
    return raw


def _stamp(value, code="timestamp_utc"):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if stamp.utcoffset() != timedelta(0):
            raise ValueError
        return stamp.astimezone(UTC)
    except (TypeError, ValueError, AttributeError):
        raise FreezeError(code) from None


def _evidence(record, at):
    try:
        if not isinstance(record, dict) or any(
            record.get(key) is not True
            for key in ("history_available", "spy_quota_available", "full_action_history_reviewed")
        ):
            raise ValueError
        valid = SourceEvidence.model_validate(record).model_dump()
        checked = _stamp(valid["checked_at_utc"])
        if not timedelta(0) <= at - checked <= timedelta(minutes=30):
            raise ValueError
        if any(
            valid[key] == "0" * 64
            for key in ("use_document_sha256", "account_metadata_sha256", "field_semantics_sha256")
        ):
            raise ValueError
        return valid
    except (ValueError, TypeError, ValidationError):
        raise FreezeError("evidence_unqualified_or_stale") from None


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _typed_record(model, record, true_fields, code):
    try:
        if not isinstance(record, dict) or type(record.get("schema_version")) is not int:
            raise ValueError
        if any(record.get(key) is not True for key in true_fields):
            raise ValueError
        valid = model.model_validate(record).model_dump()
        if any(value == "0" * 64 for key, value in valid.items() if key.endswith("_sha256")):
            raise ValueError
        return valid
    except (ValueError, TypeError, ValidationError):
        raise FreezeError(code) from None


def _authorization_time(valid, as_of, requested_at):
    """Cheap dispatch guard over an already validated, window-bound authorization."""
    observed = _stamp(valid["metadata_observed_at_utc"], "authorization_unqualified_or_stale")
    checked = _stamp(valid["prechecked_at_utc"], "authorization_unqualified_or_stale")
    if (
        not observed <= checked <= as_of <= requested_at
        or requested_at - observed > timedelta(minutes=30)
        or requested_at - as_of > timedelta(minutes=5)
        or _stamp(valid["as_of_utc"], "authorization_unqualified_or_stale") != as_of
    ):
        raise FreezeError("authorization_unqualified_or_stale")


def _authorization(record, as_of, requested_at, *, port=None, proof_store=None):
    v3 = (
        isinstance(record, dict)
        and type(record.get("schema_version")) is int
        and record["schema_version"] == 3
    )
    valid = _typed_record(
        CaptureAuthorizationV3 if v3 else CaptureAuthorization,
        record,
        ("quote_logged_in", "program_ready", "spy_quota_available"),
        "authorization_unqualified_or_stale",
    )
    _authorization_time(valid, as_of, requested_at)
    if valid["window_sha256"] != _digest(plan_window(as_of)) or (
        port is not None and valid["endpoint_port"] != port
    ):
        raise FreezeError("authorization_unqualified_or_stale")
    if v3:
        try:
            _policy_source_identity()
            binding = once.verify_authority(valid["policy_exception"], proof_store)
            if (
                binding.window_sha256 != valid["window_sha256"]
                or valid["use_document_sha256"] != binding.policy_document_ref.digest
            ):
                raise ValueError
        except Exception:
            raise FreezeError("policy_authority_invalid") from None
    return valid


_PAYLOAD_KEYS = {
    "received_at_utc",
    "history_pages",
    "adjustment_factors",
    "dividends",
    "stock_split_pages",
}


def _reviewed_inputs(raw, window, envelope, frozen_at):
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"schema_version", "authorization", "review"}
        or type(envelope["schema_version"]) is not int
        or envelope["schema_version"] != 2
    ):
        raise FreezeError("v2_evidence_envelope_invalid")
    if (
        not isinstance(raw, dict)
        or set(raw)
        != _PAYLOAD_KEYS | {"schema_version", "authorization_sha256", "requested_at_utc"}
        or type(raw["schema_version"]) is not int
        or raw["schema_version"] != 2
    ):
        raise FreezeError("v2_capture_schema_invalid")
    _canonical(raw)
    as_of = _stamp(window["as_of_utc"])
    requested, received = _stamp(raw["requested_at_utc"]), _stamp(raw["received_at_utc"])
    auth = _authorization(envelope["authorization"], as_of, requested)
    review = _typed_record(
        PostReview,
        envelope["review"],
        ("history_available", "full_action_history_reviewed"),
        "post_review_unqualified",
    )
    reviewed = _stamp(review["reviewed_at_utc"])
    if (
        not requested <= received <= reviewed <= frozen_at
        or frozen_at - reviewed > timedelta(minutes=30)
        or raw["authorization_sha256"] != _digest(auth)
        or review["authorization_sha256"] != _digest(auth)
        or review["capture_sha256"] != _digest(raw)
        or review["feed"].strip().upper().startswith(("UNKNOWN", "UNVERIFIED", "NOT_"))
        or not review["feed"].strip()
    ):
        raise FreezeError("post_review_binding_or_time_invalid")
    normalized = _normalize_payload({key: raw[key] for key in _PAYLOAD_KEYS}, window, review)
    return auth, review, normalized


def plan_window(as_of):
    as_of = _stamp(as_of, "as_of_utc")
    windows = CalendarService().sessions(
        "XNYS", as_of.date() - timedelta(days=365), as_of.date(), policy=SessionPolicy.REGULAR
    )
    completed = [w for w in windows if w.close_at + timedelta(minutes=30) <= as_of][-121:]
    if len(completed) != 121:
        raise FreezeError("insufficient_calendar_sessions")
    sessions = [w.session_date.isoformat() for w in completed]
    return {
        "as_of_utc": as_of.isoformat(),
        "source_grace_minutes": 30,
        "calendar_version": completed[0].calendar_version,
        "sessions": sessions,
        "warmup_start": sessions[0],
        "warmup_end": sessions[99],
        "score_start": sessions[100],
        "score_end": sessions[-1],
        "schedule": [w.model_dump(mode="json") for w in completed],
    }


def _number(value, *, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise FreezeError("nonfinite_or_non_numeric")
    if value < 0 if nonnegative else value <= 0:
        raise FreezeError("number_outside_domain")
    return value


def _day(value, fmt="%Y-%m-%d"):
    try:
        if not isinstance(value, str):
            raise ValueError
        result = datetime.strptime(value, fmt).date()
        if result.strftime(fmt) != value:
            raise ValueError
        return result.isoformat()
    except (TypeError, ValueError):
        raise FreezeError("date_format_unsupported") from None


def _rows(payload):
    if not isinstance(payload, dict) or payload.get("code") != "US.SPY":
        raise FreezeError("action_identity_invalid")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) > MAX_ACTION_ROWS:
        raise FreezeError("action_rows_invalid")
    if any(not isinstance(row, dict) for row in rows):
        raise FreezeError("action_rows_invalid")
    return rows


def _cash_statement(statement):
    if not isinstance(statement, str) or len(statement) > 1000:
        raise FreezeError("cash_statement_unsupported")
    amount = 0.0
    for component in statement.split(","):
        match = re.fullmatch(
            r"(?:Cash Dividend|Special Dividend|Capital Gains):\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s+USD\s+Per Share",
            component.strip(),
            re.I,
        )
        if match is None:
            raise FreezeError("cash_statement_unsupported")
        amount += _number(float(match[1]))
    return amount


def _actions(raw, window, evidence):
    sessions = set(window["sessions"])
    factors = {}
    ratios = (
        "per_share_div_ratio",
        "per_share_trans_ratio",
        "allotment_ratio",
        "stk_spo_ratio",
        "spin_off_ratio",
    )
    for row in _rows(raw["adjustment_factors"]):
        ex = _day(row.get("ex_div_date"))
        if ex not in sessions:
            continue
        if "split_ratio" not in row or any(key not in row for key in ratios):
            raise FreezeError("action_schema_unsupported")
        if row["split_ratio"] not in (None, 1) or any(row[key] not in (None, 0) for key in ratios):
            raise FreezeError("noncash_action_unsupported")
        amount = _number(row.get("per_cash_div"), nonnegative=True)
        if ex in factors:
            raise FreezeError("duplicate_adjustment_date")
        factors[ex] = amount
    events, seen = {}, set()
    for row in _rows(raw["dividends"]):
        ex = _day(row.get("ex_date"), evidence["event_date_format"])
        if ex not in sessions:
            continue
        amount = _cash_statement(row.get("statement"))
        pay_text = row.get("dividend_payable_date")
        pay = _day(pay_text, evidence["event_date_format"]) if pay_text else None
        if (pay is None and ex >= window["score_start"]) or (pay is not None and pay < ex):
            raise FreezeError("payment_date_missing_or_invalid")
        identity = (ex, pay, row["statement"])
        if identity in seen:
            raise FreezeError("duplicate_dividend")
        seen.add(identity)
        events.setdefault(ex, []).append({"ex_date": ex, "pay_date": pay, "amount": amount})
    for ex in set(events) | {d for d, amount in factors.items() if amount > 0}:
        amount = sum(item["amount"] for item in events.get(ex, []))
        if ex not in factors or not math.isclose(amount, factors[ex], rel_tol=0, abs_tol=1e-8):
            raise FreezeError("cash_event_reconciliation_failed")
    split_pages = raw["stock_split_pages"]
    if not isinstance(split_pages, list) or not 1 <= len(split_pages) <= 2:
        raise FreezeError("split_pages_invalid")
    cursor = None
    for index, page in enumerate(split_pages):
        if page.get("request_next_key") != cursor or _rows(page):
            # The existing engine has no stock-split accounting. A nonempty
            # split history needs explicit scope review rather than guessing dates.
            raise FreezeError("split_history_requires_review")
        cursor = page.get("next_key")
        if cursor != "-1" or index != len(split_pages) - 1:
            raise FreezeError("split_pagination_invalid")
    flat = [item for ex in sorted(events) for item in events[ex]]
    return (
        factors,
        [x for x in flat if x["ex_date"] >= window["score_start"]],
        [x for x in flat if x["ex_date"] < window["score_start"]],
    )


def normalize_capture(raw, window, evidence):
    """Read-only v1 normalization; v2 freeze validates its explicit post-review."""
    evidence = _evidence(evidence, _stamp(window["as_of_utc"]))
    return _normalize_payload(raw, window, evidence)


def _normalize_payload(raw, window, evidence):
    if window != plan_window(_stamp(window["as_of_utc"])):
        raise FreezeError("window_modified")
    _canonical(raw)
    if not isinstance(raw, dict) or set(raw) != {
        "received_at_utc",
        "history_pages",
        "adjustment_factors",
        "dividends",
        "stock_split_pages",
    }:
        raise FreezeError("capture_schema_invalid")
    if _stamp(raw["received_at_utc"]) < _stamp(window["as_of_utc"]):
        raise FreezeError("capture_predates_asof")
    pages = raw["history_pages"]
    if not isinstance(pages, list) or not 1 <= len(pages) <= 2:
        raise FreezeError("history_pages_invalid")
    rows, cursor, cursors = [], None, set()
    for index, page in enumerate(pages):
        if (
            not isinstance(page, dict)
            or page.get("code") != "US.SPY"
            or page.get("interval") != "1d"
            or page.get("autype") != "None"
            or page.get("request_page_req_key") != cursor
        ):
            raise FreezeError("history_identity_invalid")
        current = page.get("rows")
        if not isinstance(current, list) or not current or len(rows) + len(current) > 200:
            raise FreezeError("history_rows_invalid")
        rows.extend(current)
        cursor = page.get("next_page_req_key")
        if cursor is None:
            if index != len(pages) - 1:
                raise FreezeError("history_after_terminal")
        else:
            try:
                if (
                    not isinstance(cursor, str)
                    or not cursor.startswith("base64:")
                    or cursor in cursors
                ):
                    raise ValueError
                if not base64.b64decode(cursor[7:], validate=True):
                    raise ValueError
            except (ValueError, TypeError):
                raise FreezeError("history_cursor_invalid") from None
            cursors.add(cursor)
    if cursor is not None:
        raise FreezeError("history_incomplete_pagination")
    factors, events, warmup = _actions(raw, window, evidence)
    normalized = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("code") != "US.SPY"
            or row.get("currency", "USD") != "USD"
        ):
            raise FreezeError("bar_identity_invalid")
        label = row.get("time_key")
        if isinstance(label, str) and label.endswith(" 00:00:00"):
            label = label[:-9]
        day = _day(label)
        values = {
            key: _number(row.get(key), nonnegative=key == "volume")
            for key in ("open", "high", "low", "close", "volume")
        }
        if not (
            values["low"]
            <= min(values["open"], values["close"])
            <= max(values["open"], values["close"])
            <= values["high"]
        ):
            raise FreezeError("ohlc_invalid")
        normalized.append({"date": day, **values, "dividend": factors.get(day, 0)})
    if [row["date"] for row in normalized] != window["sessions"]:
        raise FreezeError("session_coverage_invalid")
    return {"bars": normalized, "distributions": events, "warmup_distributions": warmup}


class _BoundedClient:
    """Narrow the public provider's client before any data method is called."""

    def __init__(self, client):
        self.client = client

    def history_pages(self, code, **kwargs):
        if code != "US.SPY" or kwargs.get("interval") != "1d" or kwargs.get("autype") != "None":
            raise FreezeError("capture_scope_invalid")
        return self.client.history_pages(code, **kwargs, max_pages=2, max_rows=200, page_size=1000)

    def adjustment_factors(self, code):
        return self.client.adjustment_factors(code)

    def dividends(self, code):
        return self.client.dividends(code)

    def stock_splits(self, code):
        return self.client.stock_splits(code, max_pages=2, max_rows=100, page_size=50)


def _wire_json(value, path, tags):
    """Preserve plain transport values; tagged paths distinguish literal tag-shaped maps."""
    if isinstance(value, bytes):
        tags.append({"path": path, "type": "bytes"})
        return {"$bytes_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, float) and not math.isfinite(value):
        tags.append({"path": path, "type": "nonfinite_float"})
        return {"$nonfinite": "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")}
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {k: _wire_json(v, [*path, k], tags) for k, v in value.items()}
    if isinstance(value, list):
        return [_wire_json(v, [*path, i], tags) for i, v in enumerate(value)]
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise FreezeError("wire_value_unsupported")


class _RecordingTransport:
    """Persist at most six bounded plain returns before public-client validation.

    SDK failures before returning a plain value and oversized/unsupported values
    cannot be retained at this boundary. Never claim those are recorded responses.
    """

    def __init__(self, transport, root, clock, authorization, as_of):
        self.transport, self.root, self.clock = transport, Path(root), clock
        self.authorization, self.as_of = authorization, as_of
        self.requested_at = None
        self.count, self.total = 0, 0

    def _dispatch_time(self):
        requested_at = _stamp(self.clock())
        _authorization_time(self.authorization, self.as_of, requested_at)
        return requested_at

    def _call(self, target, method, code, **kwargs):
        if self.count >= 6:
            raise FreezeError("wire_call_cap")
        call = getattr(target, method)
        requested_at = self._dispatch_time()
        if self.requested_at is None:
            self.requested_at = requested_at
        response = call(code, **kwargs)
        tags = []
        observation = {
            "schema_id": "qm.spy-daily.wire-response.v1",
            "method": method,
            "received_at_utc": _stamp(self.clock()).isoformat(),
            "request": _wire_json({"code": code, **kwargs}, ["request"], tags),
            "response": _wire_json(response, ["response"], tags),
            "typed_values": tags,
        }
        raw = _canonical(observation)
        if self.total + len(raw) > MAX_BYTES:
            raise FreezeError("wire_bytes_cap")
        ref = ObjectStore(self.root).put_bytes(media_type="application/json", payload=raw)
        self.count += 1
        self.total += len(raw)
        with (self.root / f"wire-response-{self.count:02d}.json").open("xb") as handle:
            handle.write(_canonical(ref.model_dump(mode="json")))
            handle.flush()
            os.fsync(handle.fileno())
        return response

    @contextmanager
    def history_session(self):
        factory = getattr(self.transport, "history_session", None)
        self._dispatch_time()  # Before context setup; recheck after setup in each _call.
        with factory() if callable(factory) else nullcontext(self.transport) as session:
            self.history_transport = session
            try:
                yield self
            finally:
                del self.history_transport

    def history_kline_page(self, code, **kwargs):
        return self._call(self.history_transport, "history_kline_page", code, **kwargs)

    def adjustment_factors(self, code):
        return self._call(self.transport, "adjustment_factors", code)

    def dividends(self, code):
        return self._call(self.transport, "dividends", code)

    def stock_splits_page(self, code, **kwargs):
        return self._call(self.transport, "stock_splits_page", code, **kwargs)


def collect(transport, as_of, evidence, *, raw_root, clock=lambda: datetime.now(UTC)):
    """Caller owns transport lifetime; every plain return is journaled first."""
    as_of = _stamp(as_of, "as_of_utc")
    requested = _stamp(clock())
    evidence = _authorization(evidence, as_of, requested, proof_store=ObjectStore(Path(raw_root)))
    v3 = evidence["schema_version"] == 3
    intent_ref = None
    if v3:
        intent_path = Path(raw_root) / "capture-intent-ref.json"
        intent_ref = _read_json(intent_path)
        marker = once.verify_intent(
            evidence["policy_exception"],
            evidence,
            intent_ref,
            ObjectStore(Path(raw_root)),
            require_live_marker=True,
        )
        if _stamp(marker["consumed_at_utc"]) > requested:
            raise FreezeError("policy_intent_invalid")
    window = plan_window(as_of)
    start = datetime.combine(date.fromisoformat(window["sessions"][0]), time.min, tzinfo=_NY)
    end = datetime.combine(date.fromisoformat(window["score_end"]), time.max, tzinfo=_NY)
    recorder = _RecordingTransport(transport, raw_root, clock, evidence, as_of)
    client = MoomooOpenDClient(recorder)
    try:
        bundle = MoomooOpenDProvider(_BoundedClient(client)).fetch_raw_bundle(
            Instrument(
                symbol="SPY",
                venue=Venue.MOOMOO,
                instrument_type=InstrumentType.ETF,
                currency="USD",
                metadata={"market": "US"},
            ),
            interval="1d",
            start=start,
            end=end,
        )
    except Exception:
        raise FreezeError("capture_failed") from None
    raw = {
        "schema_version": 3 if v3 else 2,
        "authorization_sha256": _digest(evidence),
        "requested_at_utc": recorder.requested_at.isoformat(),
        "received_at_utc": _stamp(clock()).isoformat(),
        "history_pages": list(bundle.history_pages),
        "adjustment_factors": bundle.adjustment_factors,
        "stock_split_pages": list(bundle.stock_split_pages),
        "dividends": bundle.dividends,
    }
    if v3:
        raw["capture_intent_ref"] = intent_ref
    _canonical(raw)
    return raw


def _csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=("date", "open", "high", "low", "close", "volume", "dividend"),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _protocol(window):
    return {
        "schema_id": "qm.spy-daily.replay.protocol.v1",
        "window": window,
        "provider_symbol": "US.SPY",
        "currency": "USD",
        "interval": "1d",
        "purpose": "historical_development_diagnostic",
        "sample_role": "development_only",
        "exposure": "historical_dates_overlap_prior_consumed_SPY",
        "engine_original_sha256": ENGINE_ORIGINAL_SHA256,
        "normalizer_sha256": _LOADED_SOURCE,
        "source_code_sha256": dict(_LOADED_SOURCES),
        "runtime": {
            "python": platform.python_version(),
            "pandas": version("pandas"),
            "numpy": version("numpy"),
            "calendar": version("exchange-calendars"),
        },
        "rule": {
            "id": "SMA100-long-cash",
            "lookback": 100,
            "capital_usd": 100000,
            "extra_delay": 0,
            "integer_shares": True,
            "cash_interest": 0,
            "fill": "next_session_raw_OPEN_proxy",
            "terminal": "last_session_OPEN",
            "dividend": "ex_date_receivable_pay_date_cash",
            "volume_cap_fraction": 0.01,
        },
        "costs": {
            "model_id": "combined-turnover-proxy-v1",
            "unit": "one_way_bps_notional",
            "base_one_way_bps": 5,
            "stress_one_way_bps": 10,
            "fee_spread_slippage_components": None,
            "reason": "not_calibrated",
        },
        "benchmarks": ["same_cost_integer_SPY_buyhold", "cash_zero_interest_assumed"],
        "financial_qualification": "INSUFFICIENT",
        "paper_qualification": "NOT_AUTHORIZED",
        "field_proof_boundary": "external_review_receipt_not_independent_legal_or_PIT_proof",
    }


def _protocol_v2(window):
    protocol = _protocol(window)
    protocol["schema_id"] = "qm.spy-daily.replay.protocol.v2"
    protocol["evidence_contract"] = "preauthorization_before_request_post_review_before_freeze"
    return protocol


def freeze_capture(raw, as_of, evidence, output, *, frozen_at):
    if isinstance(evidence, dict) and evidence.get("schema_version") == 3:
        return _freeze_v3(raw, as_of, evidence, output, frozen_at=frozen_at)
    if isinstance(evidence, dict) and evidence.get("schema_version") == 1:
        raise FreezeError("v1_freeze_read_only")
    window = plan_window(as_of)
    frozen_at = _stamp(frozen_at)
    authorization, review, normalized = _reviewed_inputs(raw, window, evidence, frozen_at)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _LOADED_SOURCE:
        raise FreezeError("normalizer_source_changed")
    if _source_identity() != _LOADED_SOURCES:
        raise FreezeError("reused_source_changed")
    members = {
        "raw-capture.json": _canonical(raw),
        "capture-authorization.json": _canonical(authorization),
        "post-review.json": _canonical(review),
        "normalized-bars.csv": _csv_bytes(normalized["bars"]),
        "normalized-distributions.json": _canonical(normalized["distributions"]),
        "warmup-distributions.json": _canonical(normalized["warmup_distributions"]),
    }
    # Validate all inputs before creating/publishing any object.
    protocol = _protocol_v2(window)
    store = ObjectStore(Path(output))
    refs = {
        name: store.put_bytes(
            media_type="text/csv" if name.endswith(".csv") else "application/json", payload=content
        ).model_dump(mode="json")
        for name, content in members.items()
    }
    protocol["members"] = refs
    protocol_ref = store.put_bytes(media_type="application/json", payload=_canonical(protocol))
    freeze = {
        "schema_id": "qm.spy-daily.freeze.v2",
        "frozen_at_utc": frozen_at.isoformat(),
        "protocol_ref": protocol_ref.model_dump(mode="json"),
        "members": refs,
        "financial_evaluation_executed": False,
        "actual_data_acceptance": "REQUIRES_INDEPENDENT_SOURCE_AND_FIELD_REVIEW",
    }
    ref = store.put_bytes(media_type="application/json", payload=_canonical(freeze))
    return {"freeze_digest": ref.digest, "freeze_ref": ref.model_dump(mode="json"), **freeze}


def _loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise FreezeError("duplicate_json_key")
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(FreezeError("invalid_json")),
        )
    except (ValueError, TypeError, RecursionError):
        raise FreezeError("invalid_json") from None


def reopen_freeze(root, freeze_digest, *, policy_exception=False):
    if not isinstance(freeze_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", freeze_digest):
        raise FreezeError("freeze_digest_invalid")
    store = ObjectStore(Path(root))
    # Reopening an object by digest also needs its recorded size. Obtain it from
    # the same regular object path, then let ObjectStore verify hash and size.
    probe = ObjectRef(digest=freeze_digest, byte_length=0, media_type="application/json")
    path = store.path_for(probe)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise FreezeError("payload_too_large")
    reference = probe.model_copy(update={"byte_length": size})
    freeze = _loads(
        once.read_object(store, reference, limit=1024 * 1024)
        if policy_exception
        else store.get_bytes(reference)
    )
    if (
        isinstance(freeze, dict)
        and freeze.get("schema_id") == "qm.spy-daily.freeze.v3.policy-exception-once"
    ):
        return _reopen_v3(store, freeze)
    if policy_exception:
        raise FreezeError("v3_freeze_invalid")
    if (
        not isinstance(freeze, dict)
        or set(freeze)
        != {
            "schema_id",
            "frozen_at_utc",
            "protocol_ref",
            "members",
            "financial_evaluation_executed",
            "actual_data_acceptance",
        }
        or freeze["actual_data_acceptance"] != "REQUIRES_INDEPENDENT_SOURCE_AND_FIELD_REVIEW"
    ):
        raise FreezeError("freeze_envelope_invalid")
    frozen_at = _stamp(freeze["frozen_at_utc"])
    v2 = freeze["schema_id"] == "qm.spy-daily.freeze.v2"
    protocol = _loads(store.get_bytes(ObjectRef.model_validate(freeze["protocol_ref"])))
    if (
        freeze.get("schema_id") != ("qm.spy-daily.freeze.v2" if v2 else "qm.spy-daily.freeze.v1")
        or protocol.get("schema_id")
        != ("qm.spy-daily.replay.protocol.v2" if v2 else "qm.spy-daily.replay.protocol.v1")
        or protocol.get("members") != freeze.get("members")
        or freeze.get("financial_evaluation_executed") is not False
    ):
        raise FreezeError("freeze_integrity_invalid")
    expected = (_protocol_v2 if v2 else _protocol)(protocol["window"])
    for name in ("runtime", "normalizer_sha256", "source_code_sha256"):
        expected[name] = protocol[name]  # Reopen original runtime identity, never rewrite it.
    expected["members"] = freeze["members"]
    if (
        protocol != expected
        or set(protocol["runtime"]) != {"python", "pandas", "numpy", "calendar"}
        or not all(isinstance(v, str) and 0 < len(v) <= 100 for v in protocol["runtime"].values())
        or not re.fullmatch(r"[0-9a-f]{64}", protocol["normalizer_sha256"])
        or not isinstance(protocol["source_code_sha256"], dict)
        or set(protocol["source_code_sha256"])
        != {"src/" + name.replace(".", "/") + ".py" for name in _SOURCE_MODULES}
        or not all(
            isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) and v != "0" * 64
            for v in protocol["source_code_sha256"].values()
        )
    ):
        raise FreezeError("protocol_setup_invalid")
    members = {
        name: store.get_bytes(ObjectRef.model_validate(ref))
        for name, ref in freeze["members"].items()
    }
    raw = _loads(members["raw-capture.json"])
    if not _stamp(protocol["window"]["as_of_utc"]) <= _stamp(raw["received_at_utc"]) <= frozen_at:
        raise FreezeError("freeze_time_order_invalid")
    if v2:
        if set(members) != {
            "raw-capture.json",
            "capture-authorization.json",
            "post-review.json",
            "normalized-bars.csv",
            "normalized-distributions.json",
            "warmup-distributions.json",
        }:
            raise FreezeError("v2_members_invalid")
        envelope = {
            "schema_version": 2,
            "authorization": _loads(members["capture-authorization.json"]),
            "review": _loads(members["post-review.json"]),
        }
        _, _, normalized = _reviewed_inputs(raw, protocol["window"], envelope, frozen_at)
    else:
        evidence = _loads(members["source-evidence.json"])
        _evidence(evidence, frozen_at)
        normalized = normalize_capture(raw, protocol["window"], evidence)
    if (
        members["normalized-bars.csv"] != _csv_bytes(normalized["bars"])
        or members["normalized-distributions.json"] != _canonical(normalized["distributions"])
        or members["warmup-distributions.json"] != _canonical(normalized["warmup_distributions"])
    ):
        raise FreezeError("normalized_derivation_invalid")
    return {**freeze, "protocol": protocol}


def _protocol_v3(window, binding, intent_ref):
    protocol = _protocol_v2(window)
    protocol.update(
        schema_id="qm.spy-daily.replay.protocol.v3.policy-exception-once",
        evidence_contract="trusted_once_exception_and_consumed_intent_before_capture",
        policy_exception=binding,
        capture_intent_ref=intent_ref,
        policy_binding_code_sha256=_policy_source_identity(),
    )
    return protocol


def _reviewed_inputs_v3(raw, window, envelope, frozen_at, store):
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"schema_version", "authorization", "review"}
        or type(envelope["schema_version"]) is not int
        or envelope["schema_version"] != 3
        or not isinstance(raw, dict)
        or type(raw.get("schema_version")) is not int
        or raw.get("schema_version") != 3
        or set(raw)
        != _PAYLOAD_KEYS
        | {"schema_version", "authorization_sha256", "requested_at_utc", "capture_intent_ref"}
    ):
        raise FreezeError("v3_evidence_invalid")
    _canonical(raw)
    as_of = _stamp(window["as_of_utc"])
    requested, received = _stamp(raw["requested_at_utc"]), _stamp(raw["received_at_utc"])
    auth = _authorization(envelope["authorization"], as_of, requested, proof_store=store)
    if auth["schema_version"] != 3:
        raise FreezeError("v3_evidence_invalid")
    review = _typed_record(
        PostReviewV3,
        envelope["review"],
        ("history_available", "full_action_history_reviewed"),
        "post_review_unqualified",
    )
    reviewed = _stamp(review["reviewed_at_utc"])
    marker = once.verify_intent(auth["policy_exception"], auth, raw["capture_intent_ref"], store)
    if (
        not as_of
        <= _stamp(marker["consumed_at_utc"])
        <= requested
        <= received
        <= reviewed
        <= frozen_at
        or frozen_at - reviewed > timedelta(minutes=30)
        or raw["authorization_sha256"] != _digest(auth)
        or review["authorization_sha256"] != _digest(auth)
        or review["capture_sha256"] != _digest(raw)
        or review["policy_exception"] != auth["policy_exception"]
        or review["capture_intent_ref"] != raw["capture_intent_ref"]
        or review["feed"].strip().upper().startswith(("UNKNOWN", "UNVERIFIED", "NOT_"))
        or not review["feed"].strip()
    ):
        raise FreezeError("post_review_binding_or_time_invalid")
    normalized = _normalize_payload({key: raw[key] for key in _PAYLOAD_KEYS}, window, review)
    return auth, review, normalized


def _freeze_v3(raw, as_of, evidence, output, *, frozen_at):
    window, frozen_at = plan_window(as_of), _stamp(frozen_at)
    store = ObjectStore(Path(output))
    auth, review, normalized = _reviewed_inputs_v3(raw, window, evidence, frozen_at, store)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _LOADED_SOURCE:
        raise FreezeError("normalizer_source_changed")
    if _source_identity() != _LOADED_SOURCES:
        raise FreezeError("reused_source_changed")
    binding = once.OnceBinding.model_validate(auth["policy_exception"])
    members = {
        "raw-capture.json": _canonical(raw),
        "capture-authorization.json": _canonical(auth),
        "post-review.json": _canonical(review),
        "normalized-bars.csv": _csv_bytes(normalized["bars"]),
        "normalized-distributions.json": _canonical(normalized["distributions"]),
        "warmup-distributions.json": _canonical(normalized["warmup_distributions"]),
        "human-approval.json": once.read_object(store, binding.human_approval_ref),
        "source-use-policy.md": once.read_object(store, binding.policy_document_ref),
        "capture-intent.json": once.read_object(store, raw["capture_intent_ref"]),
    }
    refs = {
        name: store.put_bytes(
            "text/csv"
            if name.endswith(".csv")
            else "text/markdown"
            if name.endswith(".md")
            else "application/json",
            content,
        ).model_dump(mode="json")
        for name, content in members.items()
    }
    protocol = _protocol_v3(window, auth["policy_exception"], raw["capture_intent_ref"])
    protocol["members"] = refs
    protocol_ref = store.put_bytes("application/json", _canonical(protocol))
    freeze = dict(
        schema_id="qm.spy-daily.freeze.v3.policy-exception-once",
        frozen_at_utc=frozen_at.isoformat(),
        protocol_ref=protocol_ref.model_dump(mode="json"),
        members=refs,
        policy_exception=auth["policy_exception"],
        capture_intent_ref=raw["capture_intent_ref"],
        financial_evaluation_executed=False,
        actual_data_acceptance="REQUIRES_INDEPENDENT_SOURCE_AND_FIELD_REVIEW",
    )
    ref = store.put_bytes("application/json", _canonical(freeze))
    return dict(freeze_digest=ref.digest, freeze_ref=ref.model_dump(mode="json"), **freeze)


def _reopen_v3(store, freeze):
    if (
        set(freeze)
        != {
            "schema_id",
            "frozen_at_utc",
            "protocol_ref",
            "members",
            "policy_exception",
            "capture_intent_ref",
            "financial_evaluation_executed",
            "actual_data_acceptance",
        }
        or freeze["financial_evaluation_executed"] is not False
        or freeze["actual_data_acceptance"] != "REQUIRES_INDEPENDENT_SOURCE_AND_FIELD_REVIEW"
    ):
        raise FreezeError("v3_freeze_invalid")
    binding = once.verify_authority(freeze["policy_exception"], store)
    protocol = _loads(once.read_object(store, freeze["protocol_ref"], limit=1024 * 1024))
    if set(freeze["members"]) != {
        "raw-capture.json",
        "capture-authorization.json",
        "post-review.json",
        "normalized-bars.csv",
        "normalized-distributions.json",
        "warmup-distributions.json",
        "human-approval.json",
        "source-use-policy.md",
        "capture-intent.json",
    }:
        raise FreezeError("v3_members_invalid")
    data_names = {
        "raw-capture.json",
        "normalized-bars.csv",
        "normalized-distributions.json",
        "warmup-distributions.json",
    }
    members = {
        name: once.read_object(
            store, ref, limit=MAX_BYTES if name in data_names else once.MAX_PROOF
        )
        for name, ref in freeze["members"].items()
    }
    raw, auth, review = (
        _loads(members[name])
        for name in ("raw-capture.json", "capture-authorization.json", "post-review.json")
    )
    if (
        auth["policy_exception"] != freeze["policy_exception"]
        or freeze["members"]["human-approval.json"]
        != binding.human_approval_ref.model_dump(mode="json")
        or freeze["members"]["source-use-policy.md"]
        != binding.policy_document_ref.model_dump(mode="json")
        or freeze["members"]["capture-intent.json"] != freeze["capture_intent_ref"]
        or raw["capture_intent_ref"] != freeze["capture_intent_ref"]
    ):
        raise FreezeError("v3_policy_binding_invalid")
    window = protocol["window"]
    if plan_window(_stamp(window["as_of_utc"])) != window:
        raise FreezeError("protocol_setup_invalid")
    expected = _protocol_v3(window, freeze["policy_exception"], freeze["capture_intent_ref"])
    for name in (
        "runtime",
        "normalizer_sha256",
        "source_code_sha256",
        "policy_binding_code_sha256",
    ):
        expected[name] = protocol[name]  # Preserve original frozen runtime identity.
    expected["members"] = freeze["members"]
    if (
        protocol != expected
        or set(protocol["runtime"]) != {"python", "pandas", "numpy", "calendar"}
        or not all(isinstance(v, str) and 0 < len(v) <= 100 for v in protocol["runtime"].values())
        or not all(
            isinstance(protocol[k], str)
            and re.fullmatch(r"[0-9a-f]{64}", protocol[k])
            and protocol[k] != "0" * 64
            for k in ("normalizer_sha256", "policy_binding_code_sha256")
        )
        or set(protocol["source_code_sha256"])
        != {"src/" + name.replace(".", "/") + ".py" for name in _SOURCE_MODULES}
        or not all(
            isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) and v != "0" * 64
            for v in protocol["source_code_sha256"].values()
        )
    ):
        raise FreezeError("protocol_setup_invalid")
    _, _, normalized = _reviewed_inputs_v3(
        raw,
        window,
        dict(schema_version=3, authorization=auth, review=review),
        _stamp(freeze["frozen_at_utc"]),
        store,
    )
    if (
        members["normalized-bars.csv"] != _csv_bytes(normalized["bars"])
        or members["normalized-distributions.json"] != _canonical(normalized["distributions"])
        or members["warmup-distributions.json"] != _canonical(normalized["warmup_distributions"])
    ):
        raise FreezeError("normalized_derivation_invalid")
    return {**freeze, "protocol": protocol}


def _read_json(path):
    path = Path(path).absolute()
    if any(is_reparse_point(p) for p in (path, *path.parents)):
        raise FreezeError("unsafe_input_path")
    meta = path.stat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_BYTES:
        raise FreezeError("input_file_invalid")
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        raw = handle.read(MAX_BYTES + 1)
        after = os.fstat(handle.fileno())
    if (
        len(raw) > MAX_BYTES
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or not os.path.samestat(after, path.stat())
        or any(is_reparse_point(p) for p in (path, *path.parents))
    ):
        raise FreezeError("input_changed_or_oversized")
    return _loads(raw)


def _capture_once(args, clock):
    from quantmesh.moomoo.opend import SdkTransport

    if not 1 <= args.port <= 65535:
        raise FreezeError("invalid_port")
    as_of = _stamp(args.as_of)
    requested = _stamp(clock())
    root = args.root.absolute()
    evidence = _authorization(
        _read_json(args.authorization_json),
        as_of,
        requested,
        port=args.port,
        proof_store=ObjectStore(root),
    )
    if version("moomoo-api") != evidence["sdk_version"]:
        raise FreezeError("sdk_version_evidence_mismatch")
    window = plan_window(as_of)
    if any(is_reparse_point(p) for p in (root, *root.parents)):
        raise FreezeError("unsafe_output_path")
    root.mkdir(parents=True, exist_ok=True)
    v3 = evidence["schema_version"] == 3
    if v3:
        if getattr(args, "once_authority_root", None) is None:
            raise FreezeError("policy_intent_invalid")
        try:
            ref = once.consume_once(
                evidence["policy_exception"], evidence, args.once_authority_root, root, requested
            )
            with (root / "capture-intent-ref.json").open("xb") as handle:
                handle.write(_canonical(ref))
                handle.flush()
                os.fsync(handle.fileno())
        except Exception as error:
            raise FreezeError(
                "once_scope_consumed"
                if str(error) == "once_scope_consumed"
                else "policy_intent_invalid"
            ) from None
    else:
        _capture_v2_intent(root, window, evidence, requested)
    transport = SdkTransport(
        host="127.0.0.1", port=args.port, connect_timeout_s=10, request_timeout_s=30
    )
    try:
        raw = collect(transport, as_of, evidence, raw_root=root, clock=clock)
        reference = ObjectStore(root).put_bytes(
            media_type="application/json", payload=_canonical(raw)
        )
        with (root / "capture-ref.json").open("xb") as handle:
            handle.write(_canonical(reference.model_dump(mode="json")))
        authorization_ref = ObjectStore(root).put_bytes(
            media_type="application/json", payload=_canonical(evidence)
        )
        return {
            "schema_version": 3 if v3 else 2,
            "status": "CAPTURED_UNREVIEWED",
            "capture_digest": reference.digest,
            "capture_ref": reference.model_dump(mode="json"),
            "authorization_ref": authorization_ref.model_dump(mode="json"),
            "financial_evaluation_executed": False,
            "actual_data_acceptance": "NOT_REVIEWED",
        }
    finally:
        transport.close()


def _capture_v2_intent(root, window, evidence, requested):
    try:
        with (root / "capture-intent.json").open("xb") as handle:
            handle.write(
                _canonical(
                    {
                        "schema_version": 2,
                        "window": window,
                        "authorization_sha256": _digest(evidence),
                        "capture_started_at_utc": requested.isoformat(),
                    }
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise FreezeError("capture_already_attempted") from None


def main(argv=None, *, clock=lambda: datetime.now(UTC)):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("window", help="offline fixed-as-of calendar only")
    plan.add_argument("--as-of", required=True)
    freeze = sub.add_parser("freeze", help="validate/freeze an already captured JSON; no network")
    freeze.add_argument("--as-of", required=True)
    freeze.add_argument("--capture-json", required=True, type=Path)
    freeze.add_argument("--authorization-json", required=True, type=Path)
    freeze.add_argument("--review-json", required=True, type=Path)
    freeze.add_argument("--root", required=True, type=Path)
    capture = sub.add_parser("capture", help="designated OpenD owner only; one guarded attempt")
    capture.add_argument("--as-of", required=True)
    capture.add_argument("--authorization-json", required=True, type=Path)
    capture.add_argument("--root", required=True, type=Path)
    capture.add_argument("--port", required=True, type=int, metavar="1..65535")
    capture.add_argument("--once-authority-root", type=Path)
    capture.add_argument("--execute-once", action="store_true", required=True)
    verify = sub.add_parser("verify", help="reopen original frozen objects without evaluation")
    verify.add_argument("--root", required=True, type=Path)
    verify.add_argument("--digest", required=True)
    verify.add_argument("--policy-exception", action="store_true", help="bounded v3 manifest read")
    args = parser.parse_args(argv)
    try:
        if args.command == "window":
            result = plan_window(_stamp(args.as_of, "as_of_utc"))
        elif args.command == "verify":
            result = reopen_freeze(args.root, args.digest, policy_exception=args.policy_exception)
        elif args.command == "capture":
            result = _capture_once(args, clock)
        else:
            result = freeze_capture(
                _read_json(args.capture_json),
                _stamp(args.as_of),
                {
                    "schema_version": _read_json(args.authorization_json).get("schema_version"),
                    "authorization": _read_json(args.authorization_json),
                    "review": _read_json(args.review_json),
                },
                args.root,
                frozen_at=clock(),
            )
        print(_canonical(result).decode("utf-8"))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, FreezeError) else "freeze_failed"
        print(json.dumps({"status": "REFUSED", "code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
