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


class FreezeError(ValueError):
    """Fixed safe code; CLI never prints raw SDK errors or input values."""


class SourceEvidence(BaseModel):
    """External review receipt. Matching metadata is not independent legal proof."""

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
    evidence = _evidence(evidence, _stamp(window["as_of_utc"]))
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

    def __init__(self, transport, root, clock):
        self.transport, self.root, self.clock = transport, Path(root), clock
        self.count, self.total = 0, 0

    def _call(self, target, method, code, **kwargs):
        if self.count >= 6:
            raise FreezeError("wire_call_cap")
        response = getattr(target, method)(code, **kwargs)
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
    _evidence(evidence, as_of)  # Must precede every SDK/data operation.
    window = plan_window(as_of)
    start = datetime.combine(date.fromisoformat(window["sessions"][0]), time.min, tzinfo=_NY)
    end = datetime.combine(date.fromisoformat(window["score_end"]), time.max, tzinfo=_NY)
    client = MoomooOpenDClient(_RecordingTransport(transport, raw_root, clock))
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
        "received_at_utc": _stamp(clock()).isoformat(),
        "history_pages": list(bundle.history_pages),
        "adjustment_factors": bundle.adjustment_factors,
        "stock_split_pages": list(bundle.stock_split_pages),
        "dividends": bundle.dividends,
    }
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


def freeze_capture(raw, as_of, evidence, output, *, frozen_at):
    window = plan_window(as_of)
    frozen_at = _stamp(frozen_at)
    evidence = _evidence(evidence, frozen_at)
    normalized = normalize_capture(raw, window, evidence)
    if frozen_at < _stamp(raw["received_at_utc"]):
        raise FreezeError("freeze_predates_capture")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _LOADED_SOURCE:
        raise FreezeError("normalizer_source_changed")
    if _source_identity() != _LOADED_SOURCES:
        raise FreezeError("reused_source_changed")
    members = {
        "raw-capture.json": _canonical(raw),
        "source-evidence.json": _canonical(evidence),
        "normalized-bars.csv": _csv_bytes(normalized["bars"]),
        "normalized-distributions.json": _canonical(normalized["distributions"]),
        "warmup-distributions.json": _canonical(normalized["warmup_distributions"]),
    }
    # Validate all inputs before creating/publishing any object.
    protocol = _protocol(window)
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
        "schema_id": "qm.spy-daily.freeze.v1",
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


def reopen_freeze(root, freeze_digest):
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
    freeze = _loads(store.get_bytes(probe.model_copy(update={"byte_length": size})))
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
    protocol = _loads(store.get_bytes(ObjectRef.model_validate(freeze["protocol_ref"])))
    if (
        freeze.get("schema_id") != "qm.spy-daily.freeze.v1"
        or protocol.get("schema_id") != "qm.spy-daily.replay.protocol.v1"
        or protocol.get("members") != freeze.get("members")
        or freeze.get("financial_evaluation_executed") is not False
    ):
        raise FreezeError("freeze_integrity_invalid")
    expected = _protocol(protocol["window"])
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
    evidence = _loads(members["source-evidence.json"])
    raw = _loads(members["raw-capture.json"])
    if not _stamp(protocol["window"]["as_of_utc"]) <= _stamp(raw["received_at_utc"]) <= frozen_at:
        raise FreezeError("freeze_time_order_invalid")
    _evidence(evidence, frozen_at)
    normalized = normalize_capture(raw, protocol["window"], evidence)
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
    evidence = _read_json(args.evidence_json)
    _evidence(evidence, _stamp(clock()))
    if not timedelta(0) <= _stamp(clock()) - as_of <= timedelta(minutes=5):
        raise FreezeError("capture_asof_not_current")
    if version("moomoo-api") != evidence["sdk_version"]:
        raise FreezeError("sdk_version_evidence_mismatch")
    window = plan_window(as_of)
    root = args.root.absolute()
    if any(is_reparse_point(p) for p in (root, *root.parents)):
        raise FreezeError("unsafe_output_path")
    root.mkdir(parents=True, exist_ok=True)
    try:
        with (root / "capture-intent.json").open("xb") as handle:
            handle.write(
                _canonical(
                    {
                        "window": window,
                        "evidence_sha256": hashlib.sha256(_canonical(evidence)).hexdigest(),
                    }
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise FreezeError("capture_already_attempted") from None
    transport = SdkTransport(
        host="127.0.0.1", port=args.port, connect_timeout_s=10, request_timeout_s=30
    )
    try:
        raw = collect(transport, as_of, evidence, raw_root=root, clock=clock)
        # Retain returned raw evidence even if later normalization refuses.
        reference = ObjectStore(root).put_bytes(
            media_type="application/json", payload=_canonical(raw)
        )
        with (root / "capture-ref.json").open("xb") as handle:
            handle.write(_canonical(reference.model_dump(mode="json")))
        receipt = freeze_capture(raw, as_of, evidence, root, frozen_at=clock())
        with (root / "freeze-receipt.json").open("xb") as handle:
            handle.write(_canonical(receipt))
        return receipt
    finally:
        transport.close()


def main(argv=None, *, clock=lambda: datetime.now(UTC)):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("window", help="offline fixed-as-of calendar only")
    plan.add_argument("--as-of", required=True)
    freeze = sub.add_parser("freeze", help="validate/freeze an already captured JSON; no network")
    freeze.add_argument("--as-of", required=True)
    freeze.add_argument("--capture-json", required=True, type=Path)
    freeze.add_argument("--evidence-json", required=True, type=Path)
    freeze.add_argument("--root", required=True, type=Path)
    capture = sub.add_parser("capture", help="designated OpenD owner only; one guarded attempt")
    capture.add_argument("--as-of", required=True)
    capture.add_argument("--evidence-json", required=True, type=Path)
    capture.add_argument("--root", required=True, type=Path)
    capture.add_argument("--port", required=True, type=int, metavar="1..65535")
    capture.add_argument("--execute-once", action="store_true", required=True)
    verify = sub.add_parser("verify", help="reopen original frozen objects without evaluation")
    verify.add_argument("--root", required=True, type=Path)
    verify.add_argument("--digest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "window":
            result = plan_window(_stamp(args.as_of, "as_of_utc"))
        elif args.command == "verify":
            result = reopen_freeze(args.root, args.digest)
        elif args.command == "capture":
            result = _capture_once(args, clock)
        else:
            result = freeze_capture(
                _read_json(args.capture_json),
                _stamp(args.as_of),
                _read_json(args.evidence_json),
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
