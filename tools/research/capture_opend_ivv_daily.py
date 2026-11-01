"""Private one-shot IVV capture leaf. Importing this module never imports an SDK.

Provider originals and normalization are unreviewed inputs, never qualification
or financial authority. The production entry requires a trusted Root permit.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib
import importlib.util
import json
import logging
import logging.handlers
import math
import os
import re
import signal
import stat
import struct
import sys
import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath

SCOPE = "e28541ddae3d7b567e23e2963cc454995aa01c420bd567d8eb8aace6b6354f07"
APPROVAL = "37e4667460e66026ba6f281116ceeb6bb525f9aebc1b10d432405a410a139e45"
EXECUTION = "0f523db13273e7325cad752e529eece44168a17903275d0047adf1e93b50efa3"
WINDOW = "c3c218ad159edabdf38faddf802109b09208e166b4e50e6d25ad7c64b169a262"
FULL_WINDOW = "38f7822357ce458d4fe1d974821e7fda89deb3a31208c68dcea6abb85b04eaf4"
SCHEDULE_SHA = "218786ac3b29e04d3a90cc90b971c7536ce8f0795c6746b002cb9a7ae79445de"
DATES_SHA = "50e126ad528c49c458517407fda23ca4dcd6205d663ea4b44d49836e183f016a"
MIB = 1024 * 1024
ONCE_LEDGER = Path("/var/lib/quantmesh/ivv-capture-once")
DEV_SUFFIX = ".dev-diagnostic.v1"


class CaptureRejected(ValueError):
    """Fixed codes only: never include provider/account/credential error text."""


def _require(condition, code):
    if not condition:
        raise CaptureRejected(code)


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError) as error:
        raise CaptureRejected("noncanonical_input") from error


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) and value != "0" * 64


def capture_evidence_digest(plain):
    return hashlib.sha256(
        _canonical(
            {
                "scope_id": plain.get("scope_id"),
                "window_digest": WINDOW,
                "raw_source_hashes": plain.get("raw_source_hashes"),
            }
        )
    ).hexdigest()


def _raw(row):
    _require(type(row) is dict and type(row.get("raw")) is dict, "raw_fields_missing")
    raw = row["raw"]
    _require(
        type(row.get("presence")) is list and sorted(raw) == row["presence"],
        "field_presence_mismatch",
    )
    return raw


def _day(value):
    _require(type(value) is str, "date_missing")
    text = value.replace("/", "-")
    if len(text) > 10:
        _require(text[10:] == " 00:00:00", "daily_timestamp_unsupported")
        text = text[:10]
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise CaptureRejected("date_invalid") from error
    _require(parsed.isoformat() == text, "date_invalid")
    return text


def _number(value, *, positive=False):
    _require(type(value) in (int, float) and math.isfinite(value), "numeric_missing_or_nonfinite")
    _require(value > 0 if positive else value >= 0, "numeric_out_of_range")
    return Decimal(str(value))


def _cash_statement(value):
    _require(type(value) is str, "cash_currency_missing")
    patterns = (
        r"(?:USD|US\$)\s*([0-9]+(?:\.[0-9]+)?)(?:\s+per share)?",
        r"每股(?:派息|派现)?\s*([0-9]+(?:\.[0-9]+)?)\s*美元",
        r"([0-9]+(?:\.[0-9]+)?)\s*USD(?:\s+per share)?",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value.strip(), re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    raise CaptureRejected("cash_currency_or_amount_ambiguous")


def _explicit_non_usd(statement):
    """Recognize only definite contrary currency lexemes, never infer USD."""
    codes = r"EUR|HKD|SGD|AUD|CAD|NZD|GBP|CNY|CNH|RMB|JPY|CHF|KRW|TWD|INR|MYR"
    symbols = r"HK\$|SG\$|S\$|AU\$|A\$|CA\$|C\$|NZ\$|[€£¥￥₩₹]"
    names = (
        r"港元|港币|港幣|人民币|人民幣|日元|日圆|日圓|欧元|歐元|英镑|英鎊|"
        r"新加坡元|澳元|加元|瑞郎|韩元|韓元|台币|台幣"
    )
    pattern = (
        r"(?<![A-Za-z])(?:" + codes + r")(?![A-Za-z])|(?<![A-Za-z])(?:" + symbols + ")|" + names
    )
    return re.search(pattern, statement, re.IGNORECASE) is not None


def normalize_capture(plain, *, schedule, source_facts):
    """Deterministic transformation only; evidence claims still need review.

    Returns the existing bars/distributions/schedule shapes. This function does
    not authenticate reviewer refs, issue grants, connect, calculate or qualify.
    """
    _require(
        type(plain) is dict
        and plain.get("schema_id") == "qm.ivv.capture-plain.v1"
        and plain.get("symbol") == "US.IVV"
        and plain.get("scope_id") == SCOPE,
        "capture_identity",
    )
    _require(
        type(schedule) is list and hashlib.sha256(_canonical(schedule)).hexdigest() == SCHEDULE_SHA,
        "schedule_mismatch",
    )
    dates = [r["date"] for r in schedule]
    hashes = plain.get("raw_source_hashes")
    _require(
        type(hashes) is dict
        and set(hashes) == {"history", "rehab", "dividends", "splits"}
        and all(_digest(v) for v in hashes.values()),
        "original_hashes_missing",
    )
    facts = source_facts
    _require(
        type(facts) is dict
        and facts.get("capture_evidence_sha256") == capture_evidence_digest(plain)
        and facts.get("price_currency") == "USD"
        and facts.get("volume_unit") == "shares"
        and type(facts.get("volume_venue")) is str
        and bool(facts["volume_venue"].strip())
        and facts.get("coverage_start") == dates[0]
        and facts.get("coverage_end") == dates[-1]
        and type(facts.get("evidence_refs")) is list
        and bool(facts["evidence_refs"])
        and all(_digest(v) for v in facts["evidence_refs"]),
        "pending_source_facts_review",
    )
    pages = plain.get("history_pages")
    _require(type(pages) is list and len(pages) == 1, "history_pages_invalid")
    page = pages[0]
    _require(
        page.get("code") == "US.IVV"
        and page.get("autype") == "None"
        and page.get("interval") == "1d"
        and page.get("next_key_has_field") is False
        and page.get("next_page_req_key") is None,
        "history_paging_or_identity",
    )
    splits = plain.get("stock_split_pages")
    _require(
        type(splits) is list
        and len(splits) == 1
        and splits[0].get("code") == "US.IVV"
        and splits[0].get("next_key_has_field") is True
        and splits[0].get("next_key") == "-1",
        "split_paging_presence",
    )
    for item in splits[0].get("rows", []):
        r = _raw(item)
        ex = _day(r.get("exDateStr"))
        _require(ex not in dates, "unsupported_split")
    rehab = plain.get("adjustment_factors", {})
    dividends = plain.get("dividends", {})
    _require(rehab.get("code") == dividends.get("code") == "US.IVV", "action_identity")
    cash = {}
    for item in rehab.get("rows", []):
        r = _raw(item)
        day = _day(r.get("time"))
        flag = r.get("companyActFlag")
        _require(type(flag) is int and 0 <= flag <= 511, "action_flag_missing")
        if day not in dates:
            continue
        _require(flag & ~(64 | 128) == 0, "unsupported_action")
        if flag & (64 | 128):
            _require(day not in cash, "ambiguous_rehab_event")
            amount = Decimal(0)
            if flag & 64:
                amount += _number(r.get("dividend"))
            if flag & 128:
                amount += _number(r.get("spDividend"))
            _require(math.isfinite(float(amount)), "cash_sum_nonfinite")
            cash[day] = amount
    records = {}
    for item in dividends.get("rows", []):
        r = _raw(item)
        day = _day(r.get("exDate"))
        if day not in dates:
            continue
        _require(day not in records and day in cash, "ambiguous_or_unmatched_cash")
        pay = _day(r.get("dividendPayableDate"))
        _require(
            pay >= day and _cash_statement(r.get("statement")) == cash[day],
            "cash_amount_or_pay_conflict",
        )
        records[day] = {"ex_date": day, "pay_date": pay, "amount": float(cash[day])}
    _require(set(records) == set(cash), "cash_pay_date_missing")
    bars = []
    for item in page.get("rows", []):
        r = _raw(item)
        _require(r.get("isBlank") is False, "blank_bar")
        day = _day(r.get("time"))
        open_price, high_price, low_price, close_price = [
            _number(r.get(k), positive=True)
            for k in ("openPrice", "highPrice", "lowPrice", "closePrice")
        ]
        volume = _number(r.get("hpVolume") if "hpVolume" in r else r.get("volume"))
        _require(volume == volume.to_integral_value(), "volume_unit_fractional")
        _require(
            low_price <= min(open_price, close_price) <= max(open_price, close_price) <= high_price,
            "ohlc_inconsistent",
        )
        bars.append(
            {
                "date": day,
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": int(volume),
                "dividend": float(cash.get(day, Decimal(0))),
            }
        )
    _require([r["date"] for r in bars] == dates, "sessions_missing_duplicate_or_extra")
    return {
        "status": "NORMALIZED_UNREVIEWED",
        "bars": bars,
        "distributions": [records[d] for d in dates if d in records],
        "schedule": [dict(r) for r in schedule],
        "capture_evidence_sha256": capture_evidence_digest(plain),
        "source_fact_refs": list(facts["evidence_refs"]),
    }


# The orchestration below is transport-injected for owned scripted vectors.
# Only capture_once can create the production admitted invocation.

RPCS = {
    "state": 1002,
    "quota": 3104,
    "basic": 3202,
    "rehab": 3105,
    "dividends": 3234,
    "splits": 3236,
    "history": 3103,
}
ORDER = tuple(RPCS)
DATA = ("rehab", "dividends", "splits", "history")
PARAMS = {
    "state": {},
    "quota": {"get_detail": False},
    "basic": {"market": "US", "stock_type": "ETF", "code_list": ["US.IVV"]},
    "rehab": {"stock": "US.IVV"},
    "dividends": {"code": "US.IVV"},
    "splits": {"code": "US.IVV", "next_key": None, "num": 50},
    "history": {
        "code": "US.IVV",
        "start_date": "2026-05-08 00:00:00",
        "end_date": "2026-10-29 23:59:59",
        "ktype": "K_DAY",
        "autype": "None",
        "fields": ["1", "2", "4", "5", "3", "8"],
        "max_num": 121,
        "next_req_key": None,
        "extended_time": False,
        "session": "RTH",
    },
}


class _Clock:
    mono = staticmethod(time.monotonic)
    wall = staticmethod(lambda: datetime.now(UTC))
    sleep = staticmethod(time.sleep)


def _validate_production_plan_keys(plan, *, schema="qm.ivv.capture-plan.v1"):
    _require(plan.get("schema_id") == schema, "plan_schema")
    allowed = {
        "schema_id",
        "scope_id",
        "symbol",
        "approval_sha256",
        "execution_sha256",
        "input_window_digest",
        "full_window_sha256",
        "effect_id",
        "capture_helper_sha256",
        "catalog_sha256",
        "sdk_pins_sha256",
        "started_monotonic",
        "endpoint",
        "receipt_root",
        "provider_bounds_ref",
        "sdk_root",
        "sdk_pins_ref",
        "dates_ref",
        "input_window_ref",
        "window_ref",
        "schedule_ref",
    }
    if schema == "qm.ivv.capture-plan" + DEV_SUFFIX:
        allowed = (allowed - {"provider_bounds_ref"}) | {"provider_evidence_ref", "policy_ref"}
    _require(type(plan) is dict and set(plan) <= allowed, "unknown_plan_fields")
    _require(set(plan) == allowed, "missing_plan_fields")


def _validate_fixed_plan(plan, *, schema="qm.ivv.capture-plan.v1"):
    _require(
        type(plan) is dict
        and plan.get("schema_id") == schema
        and plan.get("scope_id") == SCOPE
        and plan.get("symbol") == "US.IVV"
        and plan.get("approval_sha256") == APPROVAL
        and plan.get("execution_sha256") == EXECUTION
        and plan.get("input_window_digest") == WINDOW
        and plan.get("full_window_sha256") == FULL_WINDOW,
        "fixed_scope_or_authority",
    )
    for key in ("capture_helper_sha256", "catalog_sha256", "sdk_pins_sha256"):
        _require(_digest(plan.get(key)), "release_source_binding")
    _require(
        type(plan.get("effect_id")) is str
        and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", plan["effect_id"]),
        "effect_id_invalid",
    )
    ep = plan.get("endpoint", {})
    _require(
        set(ep) == {"host", "port", "is_encrypt", "security_firm"}
        and ep["host"] == "127.0.0.1"
        and type(ep["port"]) is int
        and ep["port"] == 11112
        and type(ep["is_encrypt"]) is bool
        and ep["security_firm"]
        in {"NONE", "FUTUSG", "FUTUINC", "FUTUSECURITIES", "FUTUAU", "FUTUCA", "FUTUMY", "FUTUJP"},
        "original_endpoint_binding",
    )
    _require(
        type(plan.get("started_monotonic")) in (int, float)
        and math.isfinite(plan["started_monotonic"])
        and plan["started_monotonic"] >= 0,
        "clock_binding",
    )


def _dev_provenance(value):
    keys = (
        "policy_sha256",
        "authorization_sha256",
        "diagnostic_mode",
        "hard_limit_enforced",
        "provider_tail_max",
    )
    _require(
        _digest(value.get("policy_sha256"))
        and _digest(value.get("authorization_sha256"))
        and value.get("diagnostic_mode") == "DEV_DIAGNOSTIC"
        and value.get("hard_limit_enforced") is False
        and value.get("provider_tail_max") == "UNKNOWN",
        "dev_provenance",
    )
    return {key: value[key] for key in keys}


def _reserve_once(plan, *, sync_dir=None):
    """Create-only canonical effect key. An uncertain fsync remains spent."""
    # effect_id is an attempt label, not authority for another effect. Bind
    # the original immutable effect approval across every policy and label.
    key = {
        "scope_id": plan["scope_id"],
        "execution_sha256": plan["execution_sha256"],
        "effect_sha256": plan["approval_sha256"],
    }
    raw = _canonical(key)
    name = hashlib.sha256(raw).hexdigest()
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    _require(
        ONCE_LEDGER.is_absolute() and ONCE_LEDGER.resolve() == ONCE_LEDGER, "once_ledger_alias"
    )
    if sys.platform == "linux":
        for parent in (ONCE_LEDGER, *ONCE_LEDGER.parents):
            info = parent.stat()
            _require(
                stat.S_ISDIR(info.st_mode)
                and info.st_uid == 0
                and not stat.S_IMODE(info.st_mode) & 0o022,
                "once_ledger_control",
            )
    try:
        fd = os.open(ONCE_LEDGER / name, flags, 0o600)
    except FileExistsError as error:
        raise CaptureRejected("spent_capture_effect") from error
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            _require(count > 0, "once_short_write")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    (sync_dir or _sync_dir)(ONCE_LEDGER)


def _sync_dir(path):
    _require(os.name == "posix", "native_posix_required")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class _Writer:
    def __init__(self, root, sync_dir):
        self.root = Path(root)
        self.sync_dir = sync_dir
        self.written = 0
        _require(self.root.is_absolute() and not self.root.exists(), "spent_capture_root")
        _require(self.root.parent.resolve() == self.root.parent, "receipt_parent_alias")
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError as error:
            raise CaptureRejected("spent_capture_root") from error
        self.sync_dir(self.root.parent)

    def write(self, name, payload, maximum=MIB):
        _require(
            re.fullmatch(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)?\.(json|pb|log)", name), "receipt_name"
        )
        _require(
            type(payload) is bytes
            and len(payload) <= maximum
            and self.written + len(payload) <= 7 * MIB,
            "receipt_byte_bound",
        )
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        fd = os.open(self.root / name, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                done = os.write(fd, view)
                _require(done > 0, "receipt_short_write")
                view = view[done:]
            os.fsync(fd)
        finally:
            os.close(fd)
        self.written += len(payload)
        self.sync_dir(self.root)
        return {"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}

    def json(self, name, value):
        return self.write(name, _canonical(value) + b"\n")


class _CaptureObserver:
    def __init__(self, plan, writer, clock):
        self.plan = plan
        self.writer = writer
        self.clock = clock
        self.contexts = 0
        self.initializations = 0
        self.pack_attempts = []
        self.pending = {}
        self.sent = []
        self.controls = {}
        self.responses = {}
        self.trees = {}
        self.poison = None
        self.asof = None

    def check(self, limit=480):
        verifier = self.plan.get("_live_verifier")
        if verifier is not None:
            verifier()
        _require(self.poison is None, self.poison or "poisoned")
        _require(
            0 <= self.clock.mono() - self.plan["started_monotonic"] < limit, "absolute_deadline"
        )

    def reject(self, code):
        self.poison = code
        raise CaptureRejected(code)

    def context_created(self):
        if self.contexts:
            self.reject("second_context")
        self.contexts += 1
        self.check(180)

    def initializing(self):
        if self.initializations:
            self.reject("second_initialization")
        self.initializations += 1
        self.check(180)

    def reserve(self, tag, params):
        self.check(360 if tag in DATA else 180)
        if len(self.pack_attempts) >= len(ORDER) or ORDER[len(self.pack_attempts)] != tag:
            self.reject("request_budget_or_order")
        expected = PARAMS[tag]
        for key, value in expected.items():
            seen = params.get(key)
            if key == "fields":
                if type(seen) is not list or len(seen) != 6 or set(seen) != set(value):
                    self.reject("fixed_request_parameters")
            elif seen != value or (type(value) is bool and type(seen) is not bool):
                self.reject("fixed_request_parameters")
        self.pack_attempts.append(tag)

    def register(self, tag, proto, serial):
        if (
            proto != RPCS[tag]
            or type(serial) is not int
            or serial < 0
            or (proto, serial) in self.pending
        ):
            self.reject("request_wire_binding")
        self.pending[(proto, serial)] = tag

    def before_send(self, proto, serial):
        self.check()
        if proto in (1001, 1004):
            self.controls[proto] = self.controls.get(proto, 0) + 1
            if self.controls[proto] > (1 if proto == 1001 else 96):
                self.reject("control_wire_budget")
            return
        key = (proto, serial)
        tag = self.pending.pop(key, None)
        if tag is None or len(self.sent) >= 7 or ORDER[len(self.sent)] != tag:
            self.reject("unregistered_or_duplicate_send")
        self.check(360 if tag in DATA else 180)
        if tag in DATA:
            if self.asof is None or not 0 <= (self.clock.wall() - self.asof).total_seconds() <= 300:
                self.reject("data_asof_stale")
        self.sent.append(tag)  # reserve BEFORE the actual SDK network send

    def response(self, tag, sdk_bytes, tree, observed_code=None):
        self.check(360)
        _require(
            tag in DATA and tag in self.sent and tag not in self.responses,
            "response_request_binding",
        )
        _require(type(tree) is dict and tree.get("retType") == 0, "provider_ret_error")
        body = _canonical(tree)
        _require(
            type(sdk_bytes) is bytes and len(sdk_bytes) + len(body) <= MIB,
            "provider_original_bound",
        )
        if tag == "history":
            _require(observed_code == "US.IVV", "response_asset_mismatch")
        self.responses[tag] = {
            "sdk_ref": self.writer.write(tag + ".sdk.pb", sdk_bytes),
            "fields_ref": self.writer.write(tag + ".fields.json", body),
            "encoding": "SDK_PROTOBUF_REENCODING_NOT_NETWORK_FRAME",
            "observed_code": observed_code,
        }
        self.trees[tag] = tree
        if tag == "splits":
            _require(
                tree.get("s2c", {}).get("nextKey") == "-1" and "nextKey" in tree.get("s2c", {}),
                "split_terminal_presence",
            )

    def counts(self):
        return {
            "contexts": self.contexts,
            "initializations": self.initializations,
            "pack_attempts": len(self.pack_attempts),
            "application_sends": len(self.sent),
            "history_sends": self.sent.count("history"),
            "control_sends": {str(k): v for k, v in self.controls.items()},
        }


def _view_rows(items):
    _require(type(items) is list and all(type(x) is dict for x in items), "provider_rows_shape")
    return [{"raw": dict(x), "presence": sorted(x)} for x in items]


def _plain_from_originals(o):
    trees = o.trees
    p = {
        "schema_id": "qm.ivv.capture-plain.v1",
        "symbol": "US.IVV",
        "scope_id": SCOPE,
        "raw_source_hashes": {k: v["sdk_ref"]["sha256"] for k, v in o.responses.items()},
        "adjustment_factors": {
            "code": "US.IVV",
            "rows": _view_rows(trees.get("rehab", {}).get("s2c", {}).get("rehabList", [])),
        },
        "dividends": {
            "code": "US.IVV",
            "rows": _view_rows(trees.get("dividends", {}).get("s2c", {}).get("dividendList", [])),
        },
        "stock_split_pages": [],
        "history_pages": [],
    }
    if "splits" in trees:
        s = trees["splits"]["s2c"]
        p["stock_split_pages"] = [
            {
                "code": "US.IVV",
                "request_next_key": None,
                "next_key_has_field": "nextKey" in s,
                "next_key": s.get("nextKey"),
                "rows": _view_rows(s.get("splitItemList", [])),
            }
        ]
    if "history" in trees:
        h = trees["history"]["s2c"]
        p["history_pages"] = [
            {
                "code": o.responses["history"]["observed_code"],
                "interval": "1d",
                "autype": "None",
                "request_page_req_key": None,
                "next_key_has_field": "nextReqKey" in h,
                "next_page_req_key": h.get("nextReqKey"),
                "rows": _view_rows(h.get("klList", [])),
            }
        ]
    return p


def _precheck_actions(o, dates):
    p = _plain_from_originals(o)
    cash = {}
    for item in p["adjustment_factors"]["rows"]:
        r = _raw(item)
        day = _day(r.get("time"))
        flag = r.get("companyActFlag")
        _require(type(flag) is int, "action_flag_missing")
        if day in dates:
            _require(flag & ~(64 | 128) == 0, "unsupported_action")
            if flag:
                _require(day not in cash, "ambiguous_rehab_event")
                cash[day] = (_number(r.get("dividend")) if flag & 64 else Decimal(0)) + (
                    _number(r.get("spDividend")) if flag & 128 else Decimal(0)
                )
                _require(math.isfinite(float(cash[day])), "cash_sum_nonfinite")
    seen = set()
    for item in p["dividends"]["rows"]:
        r = _raw(item)
        day = _day(r.get("exDate"))
        if day in dates:
            _require(day in cash and day not in seen, "ambiguous_or_unmatched_cash")
            _require(_day(r.get("dividendPayableDate")) >= day, "cash_amount_or_pay_conflict")
            statement = r.get("statement")
            _require(type(statement) is str and bool(statement.strip()), "cash_statement_missing")
            _require(not _explicit_non_usd(statement), "cash_currency_conflict")
            try:
                amount = _cash_statement(statement)
            except CaptureRejected:
                # Unknown nonempty locale is retained for CLOSED input review.
                # It establishes neither currency nor amount, never qualification.
                amount = None
            _require(amount is None or amount == cash[day], "cash_amount_or_pay_conflict")
            seen.add(day)
    _require(seen == set(cash) and bool(seen), "action_coverage_not_proven_before_price")
    for item in p["stock_split_pages"][0]["rows"]:
        _require(_day(_raw(item).get("exDateStr")) not in dates, "unsupported_split")


def _failure(stage, error):
    code = error.args[0] if type(error) is CaptureRejected and error.args else "exception"
    if type(code) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", code):
        code = "capture_rejected"
    kind = (
        type(error).__name__
        if type(error).__name__
        in {
            "CaptureRejected",
            "RuntimeError",
            "OSError",
            "TimeoutError",
            "ValueError",
            "KeyboardInterrupt",
        }
        else "Exception"
    )
    return {"stage": stage, "class": kind, "code": code}


def _run_capture(plan, root, *, backend_factory, clock, sync_dir, synthetic=False, dates=None):
    suffix = DEV_SUFFIX if plan.get("schema_id") == "qm.ivv.capture-plan" + DEV_SUFFIX else ".v1"
    _validate_fixed_plan(plan, schema="qm.ivv.capture-plan" + suffix)
    provenance = _dev_provenance(plan["_verified_binding"]) if suffix == DEV_SUFFIX else {}
    _require(
        type(dates) is list
        and len(dates) == 121
        and hashlib.sha256(("\n".join(dates) + "\n").encode()).hexdigest() == DATES_SHA,
        "capture_dates",
    )
    writer = _Writer(root, sync_dir)
    intent = writer.json(
        "capture-intent.json",
        {
            "schema_id": "qm.ivv.capture-intent" + suffix,
            **provenance,
            "state": "ATTEMPTED",
            "synthetic": synthetic,
            "scope_id": SCOPE,
            "effect_id": plan["effect_id"],
            "window_digest": WINDOW,
            "approval_sha256": APPROVAL,
            "execution_sha256": EXECUTION,
            "helper_sha256": plan["capture_helper_sha256"],
            "catalog_sha256": plan["catalog_sha256"],
        },
    )
    observer = _CaptureObserver(plan, writer, clock)
    backend = None
    primary = close_failure = None
    normal = {"context_closed": False, "callbacks_stopped": False, "data_socket_closed": False}
    stage = "initialize"
    safe_meta = {}
    try:
        observer.check(180)
        with _phase(clock, plan["started_monotonic"] + 180):
            backend = backend_factory(observer, writer, plan, clock)
            backend.open()
        for tag in ORDER:
            stage = tag
            observer.check(360 if tag in DATA else 180)
            wall = plan["started_monotonic"] + (360 if tag in DATA else 180)
            with _phase(clock, min(wall, clock.mono() + 20)):
                result = backend.invoke(tag, dict(PARAMS[tag]))
            observer.check(360 if tag in DATA else 180)
            if tag == "state":
                _require(
                    type(result) is dict and result.get("qot_logined") is True,
                    "quote_not_logged_in",
                )
                ver = result.get("server_ver")
                _require(
                    type(ver) in (str, int) and re.fullmatch(r"[0-9.]{1,32}", str(ver)),
                    "provider_version_metadata",
                )
                stamp = float(result.get("timestamp"))
                _require(
                    math.isfinite(stamp) and abs(clock.wall().timestamp() - stamp) <= 1800,
                    "metadata_clock_age",
                )
                safe_meta[tag] = {"qot_logined": True, "server_ver": str(ver), "timestamp": stamp}
            elif tag == "quota":
                _require(
                    type(result) is dict
                    and type(result.get("remaining")) is int
                    and result["remaining"] >= 1,
                    "history_quota_unproved",
                )
                _require(
                    type(result.get("used")) is int and result["used"] >= 0, "quota_metadata_shape"
                )
                safe_meta[tag] = {"used": result["used"], "remaining": result["remaining"]}
            elif tag == "basic":
                _require(
                    type(result) is dict
                    and result.get("code") == "US.IVV"
                    and result.get("stock_type") == "ETF",
                    "instrument_metadata",
                )
                safe_meta[tag] = {
                    k: result[k]
                    for k in ("code", "stock_type", "lot_size", "exchange_type")
                    if k in result
                }
                observer.asof = clock.wall()
            elif tag == "splits":
                _precheck_actions(observer, dates)
        _require(
            observer.counts()["application_sends"] == 7 and len(observer.responses) == 4,
            "capture_incomplete",
        )
        p = _plain_from_originals(observer)
        _require(
            len(p["history_pages"][0]["rows"]) == 121
            and p["history_pages"][0]["next_key_has_field"] is False,
            "history_page_incomplete",
        )
    except BaseException as error:
        primary = _failure(stage, error)
    finally:
        if backend is not None:
            try:
                with _phase(clock, min(plan["started_monotonic"] + 390, clock.mono() + 30)):
                    backend.close()
                normal = backend.close_evidence()
                _require(
                    type(normal) is dict
                    and set(normal) == {"context_closed", "callbacks_stopped", "data_socket_closed"}
                    and all(v is True for v in normal.values()),
                    "normal_close_not_proven",
                )
                _require(clock.mono() - plan["started_monotonic"] < 390, "normal_close_deadline")
            except BaseException as error:
                close_failure = _failure("close", error)
    if observer.poison is not None and primary is None:
        primary = {"stage": "late_guard", "class": "CaptureRejected", "code": observer.poison}
    state = (
        "CAPTURED_UNREVIEWED"
        if primary is None and close_failure is None
        else "FAILED_CAPTURE_REQUIRES_PARENT_SEAL"
    )
    manifest = {
        "schema_id": "qm.ivv.capture" + suffix,
        **provenance,
        "state": state,
        "scope_id": SCOPE,
        "symbol": "US.IVV",
        "effect_id": plan["effect_id"],
        "window_digest": WINDOW,
        "full_window_sha256": FULL_WINDOW,
        "intent_ref": intent,
        "asof": observer.asof.isoformat() if observer.asof else None,
        "counts": observer.counts(),
        "counter_semantics": "SDK_SEND_INVOCATIONS_RESERVED_BEFORE_ENQUEUE_NOT_ACK",
        "responses": observer.responses,
        "normal_close": normal,
        "requires_parent_close_receipt": True,
        "primary_failure": primary,
        "close_failure": close_failure,
        "input_review": "REQUIRED_NOT_QUALIFIED",
        "synthetic": synthetic,
        "source_binding": plan.get("_verified_binding", {}),
    }
    manifest["metadata_ref"] = writer.json("metadata-safe.json", safe_meta)
    manifest["plain_ref"] = writer.json("plain.json", _plain_from_originals(observer))
    manifest["request_ref"] = writer.json(
        "requests.json",
        {
            "pack_attempts": observer.pack_attempts,
            "sent": observer.sent,
            "control_counts": observer.controls,
            "poison": observer.poison,
        },
    )
    try:
        observer.check(480) if observer.poison is None else None
    except BaseException as error:
        if manifest["primary_failure"] is None:
            manifest["primary_failure"] = _failure("final_guard", error)
        manifest["state"] = "FAILED_CAPTURE_REQUIRES_PARENT_SEAL"
    writer.json("capture-manifest.json", manifest)
    return manifest


_QUERY_TAGS = {
    "GlobalStateQuery": "state",
    "HistoryKLQuota": "quota",
    "StockBasicInfoQuery": "basic",
    "RequestRehab": "rehab",
    "GetCorporateActionsDividendsQuery": "dividends",
    "GetCorporateActionsStockSplitsQuery": "splits",
    "RequestHistoryKlineQuery": "history",
}


def _protobuf_tree(message, depth=0):
    _require(depth <= 10 and message.IsInitialized(), "protobuf_not_initialized")
    result = {}

    def value(v):
        if hasattr(v, "ListFields"):
            return _protobuf_tree(v, depth + 1)
        if type(v) is bytes:
            return {"$bytes": base64.b64encode(v).decode("ascii")}
        if type(v) is float and not math.isfinite(v):
            return {"$float": repr(v)}
        _require(type(v) in (str, int, float, bool), "protobuf_scalar_type")
        return v

    for field, item in message.ListFields():
        repeated = getattr(field, "is_repeated", None)
        if repeated is None:
            repeated = field.label == 3
        result[field.name] = [value(x) for x in item] if repeated else value(item)
    return result


class _PrivateSdkLog:
    """No provider message formatting; records only numeric severity."""

    def __init__(self, writer):
        self.path = writer.root / "sdk-client.log"
        self.lock = threading.Lock()
        self.used = 0
        self.fd = os.open(
            self.path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )

    def event(self, level):
        with self.lock:
            if self.fd is None:
                return
            payload = (str(int(level)) + " SDK_EVENT\n").encode()
            if self.used + len(payload) <= MIB:
                os.write(self.fd, payload)
                self.used += len(payload)

    def close(self):
        with self.lock:
            if self.fd is not None:
                os.fsync(self.fd)
                os.close(self.fd)
                self.fd = None


def _load_official_sdk(writer, plan):
    _require(
        not any(k == "moomoo" or k.startswith("moomoo.") for k in sys.modules),
        "sdk_preloaded_before_intent",
    )
    # FTLog checks/makes this directory before constructing its file handler.
    # Refuse if missing rather than modifying HOME or the original provider tree.
    home = os.environ.get("HOME")
    _require(type(home) is str and bool(home), "sdk_log_directory_not_ready")
    logdir = Path(home) / ".com.moomoo.OpenD/Log"
    _require(logdir.is_dir() and not logdir.is_symlink(), "sdk_log_directory_not_ready")
    spec = importlib.util.find_spec("moomoo")
    expected = Path(plan["sdk_root"]) / "moomoo/__init__.py"
    _require(
        spec is not None
        and spec.origin is not None
        and Path(spec.origin).resolve() == expected.resolve(),
        "sdk_import_origin",
    )
    sink = _PrivateSdkLog(writer)

    class Redacted(logging.Handler):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.baseFilename = str(sink.path)

        def emit(self, record):
            sink.event(record.levelno)

    old_file = logging.handlers.TimedRotatingFileHandler
    old_stream = logging.StreamHandler
    try:
        logging.handlers.TimedRotatingFileHandler = Redacted
        logging.StreamHandler = Redacted
        sdk = importlib.import_module("moomoo")
        util = importlib.import_module("moomoo.common.utils")
        constants = importlib.import_module("moomoo.common.constant")
        return (sdk, util, constants), sink
    except BaseException:
        sink.close()
        raise
    finally:
        logging.handlers.TimedRotatingFileHandler = old_file
        logging.StreamHandler = old_stream


class _OfficialBackend:
    """Fixed process-private wrappers; never modifies installed SDK bytes."""

    def __init__(self, observer, writer, plan, clock, *, modules=None):
        self.o = observer
        self.writer = writer
        self.plan = plan
        self.clock = clock
        self.ctx = None
        self.sink = None
        self._net = None
        self._old_send = self._old_connect = None
        self._connects = 0
        self._closed = {
            "context_closed": False,
            "callbacks_stopped": False,
            "data_socket_closed": False,
        }
        if modules is None:
            modules, self.sink = _load_official_sdk(writer, plan)
        self.sdk, self.util, self.constants = modules

    def _install_wire(self, ctx):
        net = ctx._net_mgr
        _require(self._net is None or self._net is net, "second_network_manager")
        if self._net is not None:
            return
        self._net = net
        self._old_send = net.send
        self._old_connect = net.connect

        def connect(addr, *args, **kwargs):
            self.o.check(180)
            self._connects += 1
            if self._connects != 1 or addr != ("127.0.0.1", 11112):
                self.o.reject("second_or_foreign_connection")
            return self._old_connect(addr, *args, **kwargs)

        def send(conn, raw, *args, **kwargs):
            try:
                _require(conn == getattr(ctx, "_conn_id", None), "foreign_sdk_connection")
                head_size = struct.calcsize(self.util.MESSAGE_HEAD_FMT)
                _require(type(raw) in (bytes, bytearray) and len(raw) >= head_size, "wire_header")
                head = self.util.parse_head(bytes(raw[:head_size]))
                self.o.before_send(head["proto_id"], head["serial_no"])
                return self._old_send(conn, raw, *args, **kwargs)
            except CaptureRejected as error:
                self.o.poison = error.args[0]
                raise

        net.connect = connect
        net.send = send

    def _processor(self, ctx, parent, pack, unpack):
        owner = getattr(pack, "__self__", None)
        tag = _QUERY_TAGS.get(getattr(owner, "__name__", ""))
        _require(tag is not None, "unapproved_query_processor")

        def guarded_pack(**params):
            self.o.reserve(tag, params)
            result = pack(**params)
            _require(
                type(result) is tuple
                and len(result) == 5
                and type(result[0]) is int
                and result[0] == 0,
                "sdk_pack_failed",
            )
            self.o.register(tag, result[3], result[4])
            return result

        def observed_unpack(pb):
            if tag in DATA:
                try:
                    tree = _protobuf_tree(pb)
                    _require(
                        type(tree.get("retType")) is int and tree["retType"] == 0,
                        "provider_ret_error",
                    )
                    encoded = pb.SerializeToString(deterministic=True)
                    code = None
                    if tag == "history":
                        sec = tree.get("s2c", {}).get("security", {})
                        code = self.util.merge_qot_mkt_stock_str(sec.get("market"), sec.get("code"))
                    self.o.response(tag, encoded, tree, code)
                except CaptureRejected as error:
                    self.o.poison = error.args[0]
                    raise
            return unpack(pb)

        return parent(guarded_pack, observed_unpack)

    def open(self):
        self.o.context_created()
        backend = self
        base = self.sdk.OpenQuoteContext

        class OneShot(base):
            def _init_connect_sync(ctx):
                backend.o.initializing()
                ctx._auto_reconnect = False
                backend._install_wire(ctx)
                return super()._init_connect_sync()

            def _get_sync_query_processor(ctx, pack, unpack):
                return backend._processor(ctx, super()._get_sync_query_processor, pack, unpack)

        _require(
            self.plan["endpoint"]["is_encrypt"] is False,
            "encrypted_transport_not_prepared_no_downgrade",
        )
        # Hold partial construction so finally can close it after any failure.
        self.ctx = OneShot.__new__(OneShot)
        OneShot.__init__(
            self.ctx,
            host="127.0.0.1",
            port=11112,
            is_encrypt=False,
            is_async_connect=False,
            security_firm=getattr(self.sdk.SecurityFirm, self.plan["endpoint"]["security_firm"]),
        )
        _require(
            self.ctx.status == self.constants.ContextStatus.READY, "sdk_initial_connection_failed"
        )
        self.ctx.set_sync_query_connect_timeout(5)

    def invoke(self, tag, params):
        c = self.ctx
        s = self.sdk
        if tag == "state":
            result = c.get_global_state()
        elif tag == "quota":
            result = c.get_history_kl_quota(get_detail=False)
        elif tag == "basic":
            result = c.get_stock_basicinfo(
                market=s.Market.US, stock_type=s.SecurityType.ETF, code_list=["US.IVV"]
            )
        elif tag == "rehab":
            result = c.get_rehab("US.IVV")
        elif tag == "dividends":
            result = c.get_corporate_actions_dividends("US.IVV")
        elif tag == "splits":
            result = c.get_corporate_actions_stock_splits("US.IVV", next_key=None, num=50)
        elif tag == "history":
            result = c.request_history_kline(
                "US.IVV",
                start="2026-05-08",
                end="2026-10-29",
                ktype=s.KLType.K_DAY,
                autype=s.AuType.NONE,
                fields=[
                    s.KL_FIELD.DATE_TIME,
                    s.KL_FIELD.OPEN,
                    s.KL_FIELD.HIGH,
                    s.KL_FIELD.LOW,
                    s.KL_FIELD.CLOSE,
                    s.KL_FIELD.TRADE_VOL,
                ],
                max_count=121,
                page_req_key=None,
                extended_time=False,
                session=s.Session.RTH,
            )
        else:
            raise CaptureRejected("unapproved_endpoint")
        _require(
            type(result) is tuple
            and len(result) == (3 if tag == "history" else 2)
            and type(result[0]) is int
            and result[0] == 0,
            "provider_ret_error",
        )
        if tag == "quota":
            q = result[1]
            _require(type(q) in (tuple, list) and len(q) == 3, "quota_shape")
            return {"used": q[0], "remaining": q[1]}
        if tag == "basic":
            records = result[1].to_dict("records")
            _require(type(records) is list and len(records) == 1, "single_instrument_metadata")
            return records[0]
        return result[1]

    def close(self):
        try:
            if self.ctx is None:
                return
            cb = getattr(getattr(self.ctx, "_callback_executor", None), "_thread", None)
            conn = getattr(self.ctx, "_conn_id", None)
            self.ctx.close()
            until = min(self.plan["started_monotonic"] + 390, self.clock.mono() + 30)
            while (
                self.ctx.status != self.constants.ContextStatus.CLOSED and self.clock.mono() < until
            ):
                self.clock.sleep(min(0.02, max(0, until - self.clock.mono())))
            context_closed = self.ctx.status == self.constants.ContextStatus.CLOSED
            if cb is not None:
                cb.join(timeout=max(0, until - self.clock.mono()))
            self._closed = {
                "context_closed": context_closed,
                "callbacks_stopped": cb is not None and not cb.is_alive(),
                "data_socket_closed": self._net is not None
                and conn is not None
                and self._net._get_conn(conn) is None,
            }
        finally:
            if self._net is not None:
                self._net.send = self._old_send
                self._net.connect = self._old_connect
            if self.sink is not None:
                self.sink.close()

    def close_evidence(self):
        return dict(self._closed)


def _strict_json(raw):
    def pairs(items):
        r = {}
        for key, value in items:
            _require(key not in r, "duplicate_json_key")
            r[key] = value
        return r

    def bad(value):
        raise CaptureRejected("nonfinite_json")

    try:
        result = json.loads(raw.decode("utf8"), object_pairs_hook=pairs, parse_constant=bad)
    except (ValueError, UnicodeError) as error:
        raise CaptureRejected("invalid_json") from error
    _require(type(result) is dict, "json_object_required")
    return result


def _check_limits(values):
    _require(
        values.get("memory.max") == "536870912" and values.get("memory.swap.max") == "0",
        "native_memory_swap",
    )
    pids = values.get("pids.max", "")
    _require(pids.isdecimal() and 0 < int(pids) <= 32, "native_tasks")
    cpu = values.get("cpu.max", "").split()
    _require(
        len(cpu) == 2
        and all(x.isdecimal() for x in cpu)
        and int(cpu[0]) > 0
        and int(cpu[0]) * 2 <= int(cpu[1]),
        "native_cpu",
    )


def _fd_stamp(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_uid,
        info.st_nlink,
        stat.S_IMODE(info.st_mode),
    )


def _read_held_json(fd, expected_sha256):
    import fcntl

    _require(type(fd) is int and fd >= 0 and _digest(expected_sha256), "root_permit_fd_required")
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    before = os.fstat(fd)
    _require(
        stat.S_ISREG(before.st_mode)
        and before.st_uid == 0
        and before.st_nlink == 1
        and stat.S_IMODE(before.st_mode) == 0o444
        and 0 < before.st_size <= 32768
        and flags & os.O_ACCMODE == os.O_RDONLY
        and not flags & getattr(os, "O_PATH", 0),
        "root_control_file",
    )
    raw = os.pread(fd, before.st_size + 1, 0)
    _require(
        len(raw) == before.st_size
        and _fd_stamp(before) == _fd_stamp(os.fstat(fd))
        and hashlib.sha256(raw).hexdigest() == expected_sha256,
        "root_control_sha_or_lifetime",
    )
    return _strict_json(raw)


def _read_root_ref(ref, *, maximum=MIB, exact_mode=False):
    _require(
        type(ref) is dict and set(ref) == {"path", "sha256"} and _digest(ref["sha256"]),
        "root_ref_shape",
    )
    p = Path(ref["path"])
    _require(p.is_absolute() and p.resolve(strict=True) == p, "root_ref_alias")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        _require(
            stat.S_ISREG(s.st_mode)
            and s.st_uid == 0
            and s.st_nlink == 1
            and not stat.S_IMODE(s.st_mode) & 0o022
            and (not exact_mode or stat.S_IMODE(s.st_mode) == 0o444)
            and 0 < s.st_size <= maximum,
            "root_ref_file",
        )
        raw = os.pread(fd, s.st_size + 1, 0)
        _require(
            len(raw) == s.st_size
            and _fd_stamp(s) == _fd_stamp(os.fstat(fd))
            and hashlib.sha256(raw).hexdigest() == ref["sha256"],
            "root_ref_sha_or_lifetime",
        )
        return raw
    finally:
        os.close(fd)


def _native_actor():
    raw = Path("/proc/self/stat").read_bytes()
    fields = raw.rpartition(b")")[2].split()
    lines = Path("/proc/self/cgroup").read_text().strip().splitlines()
    _require(len(lines) == 1 and lines[0].startswith("0::/"), "native_cgroup_v2")
    return {
        "pid": os.getpid(),
        "uid": os.getuid(),
        "start_ticks": int(fields[19]),
        "cgroup": lines[0][3:],
    }


def _native_recheck(actor, root_parent):
    _require(_native_actor() == actor, "native_actor_lifetime")
    cgroup = actor["cgroup"]
    _require(
        cgroup.startswith("/system.slice/") and ".." not in cgroup.split("/"), "native_unit_binding"
    )
    base = Path("/sys/fs/cgroup") / cgroup.lstrip("/")
    limits = {
        name: (base / name).read_text().strip()
        for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")
    }
    _check_limits(limits)
    fs = os.statvfs(root_parent)
    _require(fs.f_bavail * fs.f_frsize >= 53687091200 + 64 * MIB, "fresh_capture_capacity")


def _validate_provider_bounds(bounds, plan):
    _require(
        type(bounds) is dict
        and bounds.get("schema_id") == "qm.ivv.provider-bounds.v1"
        and bounds.get("state") == "COMPLETED_EXISTING_BOUNDS"
        and bounds.get("effect_id") == plan["effect_id"]
        and type(bounds.get("max_incremental_bytes")) is int
        and 0 <= bounds["max_incremental_bytes"] <= 32 * MIB
        and type(bounds.get("valid_until_monotonic")) in (int, float)
        and math.isfinite(bounds["valid_until_monotonic"])
        and bounds["valid_until_monotonic"] >= plan["started_monotonic"] + 480,
        "provider_bounds_not_proven",
    )
    actor = bounds.get("provider_actor")
    _require(
        type(actor) is dict
        and set(actor) == {"pid", "uid", "start_ticks", "exe_sha256", "machine_identity_sha256"}
        and all(
            type(actor.get(k)) is int and actor[k] >= (0 if k == "uid" else 1)
            for k in ("pid", "uid", "start_ticks")
        )
        and _digest(actor.get("exe_sha256"))
        and _digest(actor.get("machine_identity_sha256")),
        "provider_bounds_identity",
    )
    refs = bounds.get("evidence_refs")
    _require(
        type(refs) is list
        and 0 < len(refs) <= 8
        and all(
            type(r) is dict
            and set(r) == {"path", "sha256"}
            and type(r["path"]) is str
            and PurePosixPath(r["path"]).is_absolute()
            and _digest(r["sha256"])
            for r in refs
        ),
        "provider_bounds_evidence",
    )
    return refs


def _admit(plan_path, receipt_root, fd, expected_sha256):
    _require(
        sys.platform == "linux" and type(fd) is int and _digest(expected_sha256),
        "native_root_permit_required",
    )
    permit = _read_held_json(fd, expected_sha256)
    _require(
        permit.get("schema_id") == "qm.ivv.root-permit.v1"
        and permit.get("state") == "ROOT_INTERNAL_GO"
        and permit.get("approval_sha256") == APPROVAL
        and permit.get("execution_sha256") == EXECUTION
        and permit.get("scope_id") == SCOPE
        and _digest(permit.get("root_go_sha256")),
        "root_effect_authority",
    )
    raw = _read_root_ref(
        {"path": str(plan_path), "sha256": permit.get("plan_sha256")},
        maximum=32768,
        exact_mode=True,
    )
    plan = _strict_json(raw)
    _validate_production_plan_keys(plan)
    _validate_fixed_plan(plan)
    bounds = _strict_json(
        _read_root_ref(plan["provider_bounds_ref"], maximum=32768, exact_mode=True)
    )
    for ref in _validate_provider_bounds(bounds, plan):
        _read_root_ref(ref, maximum=32768, exact_mode=True)
    plan, dates, permit = _admit_material(
        plan, plan_path, receipt_root, permit, fd, expected_sha256
    )
    plan["_verified_binding"].update(
        provider_bounds_ref=plan["provider_bounds_ref"], provider_actor=bounds["provider_actor"]
    )
    return plan, dates, permit


def _admit_material(plan, plan_path, receipt_root, permit, fd, expected_sha256):
    for key in (
        "scope_id",
        "effect_id",
        "capture_helper_sha256",
        "catalog_sha256",
        "sdk_pins_sha256",
        "input_window_digest",
        "full_window_sha256",
        "started_monotonic",
    ):
        _require(plan.get(key) == permit.get(key), "root_effect_plan_binding")
    _require(
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == plan["capture_helper_sha256"],
        "released_helper_sha",
    )
    _require(
        Path(receipt_root).is_absolute() and str(receipt_root) == plan.get("receipt_root"),
        "approved_receipt_root",
    )
    actor = permit.get("actor")
    _require(
        type(actor) is dict and set(actor) == {"pid", "uid", "start_ticks", "cgroup"},
        "root_actor_binding",
    )
    _native_recheck(actor, Path(receipt_root).parent)
    _require(0 <= time.monotonic() - plan["started_monotonic"] < 180, "root_effect_expired")
    budget = permit.get("budget", {})
    _require(
        type(budget.get("G")) is int
        and 0 < budget["G"] <= 10500000000
        and type(budget.get("P")) is int
        and 0 < budget["P"] <= 4500000000,
        "root_budget_fit",
    )
    expected_refs = {
        "dates_ref": DATES_SHA,
        "input_window_ref": WINDOW,
        "window_ref": FULL_WINDOW,
        "schedule_ref": SCHEDULE_SHA,
    }
    date_bytes = None
    for key, sha in expected_refs.items():
        ref = plan.get(key)
        _require(type(ref) is dict and ref.get("sha256") == sha, "fixed_window_ref")
        body = _read_root_ref(ref)
        if key == "dates_ref":
            date_bytes = body
    pins_ref = plan.get("sdk_pins_ref")
    _require(
        type(pins_ref) is dict and pins_ref.get("sha256") == plan["sdk_pins_sha256"],
        "sdk_pinset_binding",
    )
    pins = _strict_json(_read_root_ref(pins_ref, maximum=32768))
    sdk_root = Path(plan.get("sdk_root", ""))
    _require(sdk_root.is_absolute() and sdk_root.resolve() == sdk_root, "sdk_root_binding")
    rows = pins.get("pins")
    _require(type(rows) is list and len(rows) >= 12, "sdk_pinset_incomplete")
    for item in rows:
        source = (
            item.get("relative_path")
            or str(item.get("path", "")).replace("\\", "/").split("/site-packages/")[-1]
        )
        rel = Path(source)
        target = sdk_root / rel
        _require(
            not rel.is_absolute()
            and ".." not in rel.parts
            and target.resolve().is_relative_to(sdk_root),
            "sdk_pin_path",
        )
        _require(os.statvfs(target).f_flag & os.ST_RDONLY, "sdk_source_not_readonly")
        content = target.read_bytes()
        _require(
            _digest(item.get("LF_sha256"))
            and hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest() == item["LF_sha256"],
            "sdk_source_pin",
        )
    _require(os.statvfs(__file__).f_flag & os.ST_RDONLY, "helper_source_not_readonly")

    # The purpose-limited Root issuer validates the same material before it
    # creates the permit. Public capture admission always requires a held FD.
    if fd is None:
        return plan, date_bytes.decode("ascii").splitlines(), permit
    held_stamp = _fd_stamp(os.fstat(fd))

    def live():
        _require(_fd_stamp(os.fstat(fd)) == held_stamp, "held_permit_replaced")
        _read_held_json(fd, expected_sha256)
        _read_root_ref(
            {"path": str(plan_path), "sha256": permit["plan_sha256"]},
            maximum=32768,
            exact_mode=True,
        )
        _native_recheck(actor, Path(receipt_root).parent)

    plan["_live_verifier"] = live
    plan["_verified_binding"] = {
        k: permit[k]
        for k in (
            "actor",
            "root_go_sha256",
            "catalog_sha256",
            "capture_helper_sha256",
            "sdk_pins_sha256",
        )
    }
    plan["_verified_binding"].update(
        {
            "plan_sha256": permit["plan_sha256"],
            "root_permit_sha256": expected_sha256,
            "approval_sha256": APPROVAL,
            "execution_sha256": EXECUTION,
        }
    )
    return plan, date_bytes.decode("ascii").splitlines(), permit


class _NativeClock(_Clock):
    @contextlib.contextmanager
    def phase(self, until):
        depth = getattr(self, "_depth", 0)
        previous = getattr(self, "_until", None)
        if depth == 0:
            _require(signal.getitimer(signal.ITIMER_REAL)[0] == 0, "foreign_alarm_present")
            self._prior_handler = signal.getsignal(signal.SIGALRM)

            def expired(signum, frame):
                raise CaptureRejected("absolute_deadline")

            self._alarm_handler = expired
            signal.signal(signal.SIGALRM, expired)
        else:
            _require(
                signal.getsignal(signal.SIGALRM) is self._alarm_handler, "alarm_ownership_lost"
            )
        self._depth = depth + 1
        self._until = min(until, previous) if previous is not None else until
        signal.setitimer(signal.ITIMER_REAL, max(0.001, self._until - self.mono()))
        try:
            yield
        finally:
            _require(
                signal.getsignal(signal.SIGALRM) is self._alarm_handler, "alarm_ownership_lost"
            )
            self._depth = depth
            self._until = previous
            if depth == 0:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, self._prior_handler)
            else:
                signal.setitimer(signal.ITIMER_REAL, max(0.001, previous - self.mono()))


def capture_once(plan_path, receipt_root, *, permit_fd=None, expected_sha256=None):
    """Production boundary: Root FD authority before any SDK import or effect.

    Caller FD is positional-read only and remains caller-owned. The returned
    manifest still requires independent parent normal-process close evidence.
    """
    plan, dates, permit = _admit(plan_path, receipt_root, permit_fd, expected_sha256)
    _reserve_once(plan)
    clock = _NativeClock()
    with clock.phase(plan["started_monotonic"] + 480):
        result = _run_capture(
            plan,
            receipt_root,
            backend_factory=_OfficialBackend,
            clock=clock,
            sync_dir=_sync_dir,
            dates=dates,
        )
    return result


def _dev_contract():
    spec = importlib.util.spec_from_file_location(
        "ivv_dev_diagnostic", Path(__file__).with_name("ivv_dev_diagnostic.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture_dev_once(
    plan_path,
    receipt_root,
    *,
    permit_fd=None,
    expected_sha256=None,
    expected_policy_sha256=None,
    expected_authorization_sha256=None,
    expected_go_sha256=None,
):
    """Explicit DEV policy; startup trust pins never come from browser fields."""
    _require(
        sys.platform == "linux"
        and type(permit_fd) is int
        and all(
            _digest(value)
            for value in (
                expected_sha256,
                expected_policy_sha256,
                expected_authorization_sha256,
                expected_go_sha256,
            )
        ),
        "dev_trusted_held_authority",
    )
    module = sys.modules.get(__name__)
    # Modules loaded by an isolated file loader may not be registered globally.
    if module is None:
        from types import SimpleNamespace

        module = SimpleNamespace(**globals())
    plan, dates, permit = _dev_contract().admit_dev(
        module,
        plan_path,
        receipt_root,
        permit_fd,
        expected_sha256,
        expected_policy_sha256=expected_policy_sha256,
        expected_authorization_sha256=expected_authorization_sha256,
        expected_go_sha256=expected_go_sha256,
    )
    _reserve_once(plan)
    clock = _NativeClock()
    with clock.phase(plan["started_monotonic"] + 480):
        return _run_capture(
            plan,
            receipt_root,
            backend_factory=_OfficialBackend,
            clock=clock,
            sync_dir=_sync_dir,
            dates=dates,
        )


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--receipt-root", required=True)
    parser.add_argument("--permit-fd", required=True, type=int)
    parser.add_argument("--permit-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = capture_once(
            args.plan,
            args.receipt_root,
            permit_fd=args.permit_fd,
            expected_sha256=args.permit_sha256,
        )
        print(json.dumps({"state": result["state"], "requires_parent_close_receipt": True}))
        return 0 if result["state"] == "CAPTURED_UNREVIEWED" else 1
    except BaseException as error:
        print(
            json.dumps(
                {"state": "STOP_READINESS_NO_DATA_OR_FAILED", "failure": _failure("entry", error)}
            )
        )
        return 1


def _phase(clock, until):
    phase = getattr(clock, "phase", None)
    return phase(until) if phase is not None else contextlib.nullcontext()


if __name__ == "__main__":
    raise SystemExit(main())
