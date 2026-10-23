"""Bounded freezer tests use synthetic wire prices, never market observations."""

import base64
import copy
import csv
import hashlib
import io
import json
import sys
import zlib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.data.objects import ObjectRef, ObjectStore
from tools.research import freeze_opend_spy_daily as freezer

AS_OF = datetime(2026, 10, 21, 16, tzinfo=UTC)


def digest(value):
    return hashlib.sha256(freezer._canonical(value)).hexdigest()


def authorization():
    return {
        "schema_version": 2,
        "status": "authorized_for_bounded_capture",
        "scope": "US.SPY/1d/private_research",
        "use_status": "ALLOW_WITH_SCOPE",
        "use_document_sha256": "a" * 64,
        "account_metadata_sha256": "b" * 64,
        "capture_authorization_sha256": "d" * 64,
        "metadata_observed_at_utc": (AS_OF - timedelta(minutes=2)).isoformat(),
        "prechecked_at_utc": (AS_OF - timedelta(minutes=1)).isoformat(),
        "as_of_utc": AS_OF.isoformat(),
        "window_sha256": digest(freezer.plan_window(AS_OF)),
        "quote_logged_in": True,
        "program_ready": True,
        "spy_quota_available": True,
        "endpoint_host": "127.0.0.1",
        "endpoint_port": 11111,
        "sdk_version": "synthetic-no-sdk",
        "opend_version": "synthetic-no-opend",
    }


def v2raw(raw=None, auth=None):
    raw = copy.deepcopy(raw if raw is not None else payload(freezer.plan_window(AS_OF)))
    return {
        **raw,
        "schema_version": 2,
        "authorization_sha256": digest(auth or authorization()),
        "requested_at_utc": (AS_OF + timedelta(seconds=30)).isoformat(),
    }


def post_review(raw, auth=None):
    return {
        "schema_version": 2,
        "status": "reviewed_for_freeze",
        "scope": "US.SPY/1d/private_research",
        "authorization_sha256": digest(auth or authorization()),
        "capture_sha256": digest(raw),
        "reviewed_at_utc": (AS_OF + timedelta(minutes=2)).isoformat(),
        "history_available": True,
        "full_action_history_reviewed": True,
        "action_coverage_status": "complete_for_locked_window",
        "action_coverage_sha256": "e" * 64,
        "field_semantics_sha256": "c" * 64,
        "feed": "synthetic-wire-test-only",
        "currency": "USD",
        "price_adjustment": "raw",
        "daily_session_semantics": "regular_session_daily_proxy",
        "volume_unit": "shares",
        "dividend_unit": "USD/share",
        "event_date_format": "%Y/%m/%d",
    }


def freeze_evidence(raw, auth=None, review=None):
    return {
        "schema_version": 2,
        "authorization": auth or authorization(),
        "review": review or post_review(raw, auth),
    }


def evidence():
    return {
        "schema_version": 1,
        "status": "qualified_for_capture",
        "scope": "US.SPY/1d/private_research",
        "use_document_sha256": "a" * 64,
        "account_metadata_sha256": "b" * 64,
        "field_semantics_sha256": "c" * 64,
        "checked_at_utc": AS_OF.isoformat(),
        "history_available": True,
        "spy_quota_available": True,
        "full_action_history_reviewed": True,
        "feed": "synthetic-wire-test-only",
        "currency": "USD",
        "price_adjustment": "raw",
        "daily_session_semantics": "regular_session_daily_proxy",
        "volume_unit": "shares",
        "dividend_unit": "USD/share",
        "event_date_format": "%Y/%m/%d",
        "sdk_version": "synthetic-no-sdk",
        "opend_version": "synthetic-no-opend",
    }


def payload(window):
    rows = [
        {
            "code": "US.SPY",
            "time_key": stamp,
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 10000,
        }
        for stamp in window["sessions"]
    ]
    return {
        "received_at_utc": (AS_OF + timedelta(minutes=1)).isoformat(),
        "history_pages": [
            {
                "code": "US.SPY",
                "interval": "1d",
                "autype": "None",
                "request_page_req_key": None,
                "next_page_req_key": None,
                "rows": rows,
            }
        ],
        "adjustment_factors": {
            "code": "US.SPY",
            "rows": [
                {
                    "ex_div_date": "2026-09-25",
                    "per_cash_div": 1.25,
                    "split_ratio": None,
                    "per_share_div_ratio": None,
                    "per_share_trans_ratio": None,
                    "allotment_ratio": None,
                    "stk_spo_ratio": None,
                    "spin_off_ratio": None,
                }
            ],
        },
        "dividends": {
            "code": "US.SPY",
            "rows": [
                {
                    "pub_date": "2026/09/24",
                    "statement": "Cash Dividend: 1.25000 USD Per Share",
                    "process": "",
                    "record_date": "",
                    "ex_date": "2026/09/25",
                    "dividend_payable_date": "2026/10/30",
                    "fiscal_year": "2026",
                }
            ],
        },
        "stock_split_pages": [
            {"code": "US.SPY", "request_next_key": None, "next_key": "-1", "rows": []}
        ],
    }


def test_calendar_uses_completed_us_sessions_not_singapore_day():
    window = freezer.plan_window(AS_OF)
    assert len(window["sessions"]) == 121
    assert window["sessions"][0] == "2026-04-29"
    assert window["warmup_end"] == "2026-09-21"
    assert window["score_start"] == "2026-09-22"
    assert window["score_end"] == "2026-10-20"
    assert "2026-10-21" not in window["sessions"]


@pytest.mark.parametrize(
    ("as_of", "last"),
    [
        ("2026-11-27T18:29:59+00:00", "2026-11-25"),
        ("2026-11-27T18:30:00+00:00", "2026-11-27"),
        ("2026-11-29T12:00:00+00:00", "2026-11-27"),
    ],
)
def test_half_day_and_thirty_minute_grace(as_of, last):
    assert freezer.plan_window(datetime.fromisoformat(as_of))["score_end"] == last


def test_naive_asof_is_refused():
    with pytest.raises(ValueError, match="as_of_utc"):
        freezer.plan_window(datetime(2026, 10, 21))


def test_raw_normalization_preserves_per_share_and_later_payment():
    window = freezer.plan_window(AS_OF)
    normalized = freezer.normalize_capture(payload(window), window, evidence())
    bars = normalized["bars"]
    assert len(bars) == 121
    assert bars[0]["open"] == 100
    assert next(row for row in bars if row["date"] == "2026-09-25")["dividend"] == 1.25
    assert normalized["distributions"] == [
        {"ex_date": "2026-09-25", "pay_date": "2026-10-30", "amount": 1.25}
    ]
    assert bars[-1]["dividend"] == 0


def test_warmup_payment_is_not_required_for_nonexistent_preperiod_positions():
    window = freezer.plan_window(AS_OF)
    raw = payload(window)
    raw["adjustment_factors"]["rows"][0]["ex_div_date"] = "2026-09-18"
    raw["dividends"]["rows"][0].update(ex_date="2026/09/18", dividend_payable_date="")
    normalized = freezer.normalize_capture(raw, window, evidence())
    assert normalized["distributions"] == []
    assert (
        next(row for row in normalized["bars"] if row["date"] == "2026-09-18")["dividend"] == 1.25
    )
    assert normalized["warmup_distributions"][0]["pay_date"] is None


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "missing",
        "future",
        "adjusted",
        "nan",
        "ohlc",
        "negative_volume",
        "wrong_code",
        "out_of_order",
    ],
)
def test_bad_raw_observations_stop_instead_of_filling_or_filtering(fault):
    window = freezer.plan_window(AS_OF)
    raw = payload(window)
    page = raw["history_pages"][0]
    if fault == "duplicate":
        page["rows"][-1] = copy.deepcopy(page["rows"][0])
    elif fault == "missing":
        page["rows"].pop()
    elif fault == "future":
        page["rows"][-1]["time_key"] = "2026-10-21"
    elif fault == "adjusted":
        page["autype"] = "qfq"
    elif fault == "nan":
        page["rows"][0]["open"] = float("nan")
    elif fault == "ohlc":
        page["rows"][0]["low"] = 105
    elif fault == "negative_volume":
        page["rows"][0]["volume"] = -1
    elif fault == "wrong_code":
        page["rows"][0]["code"] = "US.AAPL"
    else:
        page["rows"].reverse()
    with pytest.raises(ValueError):
        freezer.normalize_capture(raw, window, evidence())


@pytest.mark.parametrize(
    "fault",
    [
        "pay_missing",
        "amount_mismatch",
        "currency",
        "split",
        "unmatched",
        "ambiguous",
        "bonus",
        "duplicate",
    ],
)
def test_cash_and_non_cash_action_faults_stop(fault):
    window = freezer.plan_window(AS_OF)
    raw = payload(window)
    factor = raw["adjustment_factors"]["rows"][0]
    event = raw["dividends"]["rows"][0]
    if fault == "pay_missing":
        event["dividend_payable_date"] = ""
    elif fault == "amount_mismatch":
        factor["per_cash_div"] = 2
    elif fault == "currency":
        event["statement"] = "Cash Dividend: 1.25000 HKD Per Share"
    elif fault == "split":
        factor["split_ratio"] = 0.5
    elif fault == "unmatched":
        raw["dividends"]["rows"] = []
    elif fault == "ambiguous":
        event["statement"] = "USD 1.25 per ten shares or taxable distribution"
    elif fault == "bonus":
        factor["per_share_div_ratio"] = 0.1
    else:
        raw["dividends"]["rows"].append(copy.deepcopy(event))
    with pytest.raises(ValueError):
        freezer.normalize_capture(raw, window, evidence())


class Wire:
    """Only wire I/O is doubled; real client and provider run above it."""

    def __init__(self, raw, *, endless=False):
        self.raw, self.endless, self.requests = raw, endless, []

    def history_kline_page(self, code, **kwargs):
        self.requests.append((code, kwargs))
        index = len(self.requests)
        return {
            **self.raw["history_pages"][0],
            "rows": self.raw["history_pages"][0]["rows"][:1]
            if self.endless
            else self.raw["history_pages"][0]["rows"],
            "request_page_req_key": kwargs["page_req_key"],
            "next_page_req_key": str(index).encode() if self.endless else None,
        }

    def adjustment_factors(self, code):
        return self.raw["adjustment_factors"]

    def stock_splits_page(self, code, **kwargs):
        return self.raw["stock_split_pages"][0]

    def dividends(self, code):
        return self.raw["dividends"]

    def close(self):
        pass


def test_real_provider_capture_has_explicit_raw_dates_and_no_subscription(tmp_path):
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    raw = freezer.collect(
        wire, AS_OF, authorization(), raw_root=tmp_path, clock=lambda: AS_OF + timedelta(minutes=1)
    )
    assert len(raw["history_pages"][0]["rows"]) == 121
    code, args = wire.requests[0]
    assert code == "US.SPY"
    assert args == {
        "interval": "1d",
        "start": "2026-04-29",
        "end": "2026-10-20",
        "autype": "None",
        "max_count": 1000,
        "page_req_key": None,
    }


def test_pagination_never_reads_a_third_page(tmp_path):
    wire = Wire(payload(freezer.plan_window(AS_OF)), endless=True)
    with pytest.raises(ValueError, match="capture_failed"):
        freezer.collect(wire, AS_OF, authorization(), raw_root=tmp_path, clock=lambda: AS_OF)
    assert len(wire.requests) == 2


@pytest.mark.parametrize(
    "field",
    [
        "quote_logged_in",
        "spy_quota_available",
        "program_ready",
        "status",
        "prechecked_at_utc",
    ],
)
def test_unqualified_record_stops_before_wire_effects(field, tmp_path):
    record = authorization()
    record[field] = False if isinstance(record[field], bool) else "unverified"
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="authorization"):
        freezer.collect(wire, AS_OF, record, raw_root=tmp_path, clock=lambda: AS_OF)
    assert wire.requests == []


def test_freeze_and_reopen_bind_original_normalized_bytes_before_evaluation(tmp_path):
    window = freezer.plan_window(AS_OF)
    raw = v2raw(payload(window))
    record = freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
    )
    assert record["financial_evaluation_executed"] is False
    reopened = freezer.reopen_freeze(tmp_path, record["freeze_digest"])
    assert reopened["protocol"]["window"]["score_end"] == "2026-10-20"
    assert reopened["protocol"]["engine_original_sha256"].startswith("bf69680b7d3e2be8")
    assert reopened["protocol"]["costs"]["base_one_way_bps"] == 5
    assert reopened["protocol"]["costs"]["stress_one_way_bps"] == 10
    assert reopened["protocol"]["financial_qualification"] == "INSUFFICIENT"
    store = ObjectStore(tmp_path)
    original = store.get_bytes(ObjectRef.model_validate(reopened["members"]["raw-capture.json"]))
    assert json.loads(original) == raw
    csv_bytes = store.get_bytes(
        ObjectRef.model_validate(reopened["members"]["normalized-bars.csv"])
    )
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode())))
    assert len(rows) == 121 and rows[0]["open"] == "100"
    first = store.get_bytes(ObjectRef.model_validate(record["freeze_ref"]))
    freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
    )
    assert store.get_bytes(ObjectRef.model_validate(record["freeze_ref"])) == first
    ref = ObjectRef.model_validate(reopened["members"]["normalized-bars.csv"])
    store.path_for(ref).write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        freezer.reopen_freeze(tmp_path, record["freeze_digest"])


def test_invalid_capture_never_publishes_freeze(tmp_path):
    raw = v2raw()
    raw["history_pages"][0]["rows"].pop()
    with pytest.raises(ValueError):
        freezer.freeze_capture(
            raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
        )
    assert not list(tmp_path.rglob("*.json"))


def test_unknown_sensitive_evidence_fields_are_refused_before_capture(tmp_path):
    record = authorization()
    record["access_token"] = "not-a-real-secret"
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="authorization"):
        freezer.collect(wire, AS_OF, record, raw_root=tmp_path, clock=lambda: AS_OF)
    assert wire.requests == []


def test_numeric_true_does_not_authorize_a_source_record(tmp_path):
    record = authorization()
    record["program_ready"] = 1
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="authorization"):
        freezer.collect(wire, AS_OF, record, raw_root=tmp_path, clock=lambda: AS_OF)
    assert wire.requests == []


def test_explicit_foreign_currency_cannot_be_hidden_in_a_us_price_row():
    window = freezer.plan_window(AS_OF)
    raw = payload(window)
    raw["history_pages"][0]["rows"][0]["currency"] = "HKD"
    with pytest.raises(ValueError):
        freezer.normalize_capture(raw, window, evidence())


def test_reopen_rejects_a_content_addressed_but_different_cost_policy(tmp_path):
    raw = v2raw()
    result = freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
    )
    store = ObjectStore(tmp_path)
    changed = json.loads(store.get_bytes(ObjectRef.model_validate(result["protocol_ref"])))
    changed["costs"]["base_one_way_bps"] = 0
    changed_ref = store.put_bytes(
        media_type="application/json", payload=json.dumps(changed).encode()
    )
    receipt = json.loads(store.get_bytes(ObjectRef.model_validate(result["freeze_ref"])))
    receipt["protocol_ref"] = changed_ref.model_dump(mode="json")
    ref = store.put_bytes(media_type="application/json", payload=json.dumps(receipt).encode())
    with pytest.raises(ValueError, match="protocol"):
        freezer.reopen_freeze(tmp_path, ref.digest)


def test_offline_cli_and_reopen_never_import_a_research_engine(tmp_path, capsys):
    class NoResearch:
        def find_spec(self, fullname, path, target=None):
            if fullname in {"engine", "run_experiment"} or fullname.startswith(
                "quantmesh.research"
            ):
                raise AssertionError("financial import attempted")

    guard = NoResearch()
    sys.meta_path.insert(0, guard)
    try:
        raw_path, record_path, review_path = (
            tmp_path / "raw.json",
            tmp_path / "authorization.json",
            tmp_path / "review.json",
        )
        raw = v2raw()
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        record_path.write_text(json.dumps(authorization()), encoding="utf-8")
        review_path.write_text(json.dumps(post_review(raw)), encoding="utf-8")
        result = freezer.main(
            [
                "freeze",
                "--as-of",
                AS_OF.isoformat(),
                "--capture-json",
                str(raw_path),
                "--authorization-json",
                str(record_path),
                "--review-json",
                str(review_path),
                "--root",
                str(tmp_path / "store"),
            ],
            clock=lambda: AS_OF + timedelta(minutes=2),
        )
        assert result == 0
        first = json.loads(capsys.readouterr().out)
        assert (
            freezer.main(
                ["verify", "--root", str(tmp_path / "store"), "--digest", first["freeze_digest"]]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["financial_evaluation_executed"] is False
    finally:
        sys.meta_path.remove(guard)


def test_capture_cli_is_once_only_and_uses_real_client_provider(tmp_path, capsys, monkeypatch):
    from quantmesh.moomoo import opend

    wire = Wire(payload(freezer.plan_window(AS_OF)))
    monkeypatch.setattr(opend, "SdkTransport", lambda **kwargs: wire)
    old_version = freezer.version
    monkeypatch.setattr(
        freezer,
        "version",
        lambda name: "synthetic-no-sdk" if name == "moomoo-api" else old_version(name),
    )
    record = tmp_path / "evidence.json"
    record.write_text(json.dumps(authorization()), encoding="utf-8")
    args = [
        "capture",
        "--as-of",
        AS_OF.isoformat(),
        "--authorization-json",
        str(record),
        "--root",
        str(tmp_path / "owned"),
        "--port",
        "11111",
        "--execute-once",
    ]
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=2)) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["financial_evaluation_executed"] is False
    assert first["status"] == "CAPTURED_UNREVIEWED"
    assert first["actual_data_acceptance"] == "NOT_REVIEWED"
    assert not (tmp_path / "owned/freeze-receipt.json").exists()
    assert len(wire.requests) == 1
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=2)) == 2
    assert "capture_already_attempted" in capsys.readouterr().err
    assert len(wire.requests) == 1


def test_operator_help_is_bounded_and_readable(capsys):
    with pytest.raises(SystemExit) as stop:
        freezer.main(["capture", "--help"])
    assert stop.value.code == 0
    help_text = capsys.readouterr().out
    assert "--authorization-json" in help_text and "--execute-once" in help_text
    assert len(help_text) < 4000


@pytest.mark.parametrize("fault", ["out_of_range", "page_two"])
def test_refused_cli_retains_each_returned_wire_response(tmp_path, capsys, monkeypatch, fault):
    from quantmesh.moomoo import opend

    raw = payload(freezer.plan_window(AS_OF))
    if fault == "out_of_range":
        raw["history_pages"][0]["rows"][-1]["time_key"] = "2026-10-21"
    wire = Wire(raw, endless=fault == "page_two")
    monkeypatch.setattr(opend, "SdkTransport", lambda **kwargs: wire)
    old_version = freezer.version
    monkeypatch.setattr(
        freezer,
        "version",
        lambda name: "synthetic-no-sdk" if name == "moomoo-api" else old_version(name),
    )
    record = tmp_path / "evidence.json"
    record.write_text(json.dumps(authorization()), encoding="utf-8")
    root = tmp_path / "owned"
    args = [
        "capture",
        "--as-of",
        AS_OF.isoformat(),
        "--authorization-json",
        str(record),
        "--root",
        str(root),
        "--port",
        "11111",
        "--execute-once",
    ]
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=2)) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "capture_failed"
    assert len(wire.requests) == (1 if fault == "out_of_range" else 2)
    refs = sorted(root.glob("wire-response-*.json"))
    assert len(refs) == len(wire.requests)
    store = ObjectStore(root)
    observations = [
        json.loads(store.get_bytes(ObjectRef.model_validate(json.loads(p.read_bytes()))))
        for p in refs
    ]
    assert observations[0]["method"] == "history_kline_page"
    assert observations[0]["request"]["code"] == "US.SPY"
    assert observations[0]["request"]["start"] == "2026-04-29"
    first = observations[0]["response"]
    if fault == "out_of_range":
        assert first["rows"][-1]["time_key"] == "2026-10-21"
    else:
        assert first["next_page_req_key"] == {"$bytes_base64": "MQ=="}
        assert observations[1]["request"]["page_req_key"] == first["next_page_req_key"]
    assert not (root / "freeze-receipt.json").exists()
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=2)) == 2
    assert "capture_already_attempted" in capsys.readouterr().err
    assert len(wire.requests) == len(refs)


def test_protocol_binds_actual_reused_sources_and_preserves_original_identities(
    tmp_path, monkeypatch
):
    expected = {
        "src/quantmesh/moomoo/provider.py",
        "src/quantmesh/moomoo/opend.py",
        "src/quantmesh/moomoo/market_data.py",
        "src/quantmesh/data/calendars.py",
        "src/quantmesh/data/objects.py",
    }
    raw = v2raw()
    result = freezer.freeze_capture(
        raw,
        AS_OF,
        freeze_evidence(raw),
        tmp_path,
        frozen_at=AS_OF + timedelta(minutes=2),
    )
    original = freezer.reopen_freeze(tmp_path, result["freeze_digest"])["protocol"][
        "source_code_sha256"
    ]
    assert set(original) == expected
    from pathlib import Path

    repo = Path(freezer.__file__).resolve().parents[2]
    assert original == {
        name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in expected
    }
    monkeypatch.setattr(freezer, "_LOADED_SOURCES", dict.fromkeys(expected, "f" * 64))
    assert (
        freezer.reopen_freeze(tmp_path, result["freeze_digest"])["protocol"]["source_code_sha256"]
        == original
    )


def test_source_drift_refuses_before_freeze_publication(tmp_path, monkeypatch):
    raw = v2raw()
    monkeypatch.setattr(freezer, "_source_identity", lambda: {"changed": "f" * 64}, raising=False)
    with pytest.raises(ValueError, match="source_changed"):
        freezer.freeze_capture(
            raw,
            AS_OF,
            freeze_evidence(raw),
            tmp_path,
            frozen_at=AS_OF + timedelta(minutes=2),
        )
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("fault", ["qualification", "before_capture", "extra", "stale_evidence"])
def test_reopen_refuses_rebuilt_invalid_envelopes(tmp_path, fault):
    raw = v2raw()
    result = freezer.freeze_capture(
        raw,
        AS_OF,
        freeze_evidence(raw),
        tmp_path,
        frozen_at=AS_OF + timedelta(minutes=2),
    )
    store = ObjectStore(tmp_path)
    receipt = json.loads(store.get_bytes(ObjectRef.model_validate(result["freeze_ref"])))
    if fault == "qualification":
        receipt["actual_data_acceptance"] = "QUALIFIED_REAL_DATA_PASS"
    elif fault == "before_capture":
        receipt["frozen_at_utc"] = AS_OF.isoformat()
    elif fault == "extra":
        receipt["independent_oos_pass"] = True
    else:
        receipt["frozen_at_utc"] = (AS_OF + timedelta(minutes=33)).isoformat()
    ref = store.put_bytes(media_type="application/json", payload=json.dumps(receipt).encode())
    with pytest.raises(ValueError):
        freezer.reopen_freeze(tmp_path, ref.digest)


def test_v2_first_request_needs_authorization_not_future_data_facts(tmp_path):
    auth = authorization()
    assert "history_available" not in auth and "full_action_history_reviewed" not in auth
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    raw = freezer.collect(
        wire, AS_OF, auth, raw_root=tmp_path, clock=lambda: AS_OF + timedelta(minutes=1)
    )
    assert len(wire.requests) == 1
    assert raw["schema_version"] == 2 and raw["authorization_sha256"] == digest(auth)
    assert not (tmp_path / "freeze-receipt.json").exists()


@pytest.mark.parametrize("limit", ["metadata", "as_of"])
def test_v2_session_delay_expires_before_dispatch_and_consumes_cli_intent(
    tmp_path, monkeypatch, capsys, limit
):
    from quantmesh.moomoo import opend

    before = AS_OF + timedelta(seconds=59 if limit == "metadata" else 299)
    now = [before]
    auth = authorization()
    if limit == "metadata":
        auth["metadata_observed_at_utc"] = (AS_OF - timedelta(minutes=29)).isoformat()

    class Delayed(Wire):
        exited = False
        closed = False

        @contextmanager
        def history_session(self):
            now[0] += timedelta(seconds=2)
            try:
                yield self
            finally:
                self.exited = True

        def close(self):
            self.closed = True

    wire = Delayed(payload(freezer.plan_window(AS_OF)))
    constructions = []
    monkeypatch.setattr(
        opend, "SdkTransport", lambda **kwargs: (constructions.append(True), wire)[1]
    )
    old_version = freezer.version
    monkeypatch.setattr(
        freezer,
        "version",
        lambda name: "synthetic-no-sdk" if name == "moomoo-api" else old_version(name),
    )
    args = capture_args(tmp_path, auth)
    assert freezer.main(args, clock=lambda: now[0]) == 2
    assert json.loads(capsys.readouterr().err) == {"status": "REFUSED", "code": "capture_failed"}
    root = tmp_path / "capture"
    assert wire.requests == [] and wire.exited and wire.closed
    assert (root / "capture-intent.json").exists()
    assert not (root / "capture-ref.json").exists()
    assert not list(root.glob("wire-response-*.json"))
    assert not (root / "freeze-receipt.json").exists()
    now[0] = before
    assert freezer.main(args, clock=lambda: now[0]) == 2
    assert "capture_already_attempted" in capsys.readouterr().err
    assert len(constructions) == 1 and wire.requests == []


def test_v2_requested_time_is_first_dispatch_after_session_setup(tmp_path):
    now = [AS_OF + timedelta(minutes=1)]
    dispatched = AS_OF + timedelta(minutes=2)

    class Delayed(Wire):
        @contextmanager
        def history_session(self):
            now[0] = dispatched
            yield self

    wire = Delayed(payload(freezer.plan_window(AS_OF)))
    raw = freezer.collect(wire, AS_OF, authorization(), raw_root=tmp_path, clock=lambda: now[0])
    assert len(wire.requests) == 1
    assert raw["requested_at_utc"] == dispatched.isoformat()


def test_v2_expiry_after_history_stops_action_dispatch_and_keeps_return(tmp_path):
    now = [AS_OF + timedelta(minutes=4, seconds=59)]

    class SlowHistory(Wire):
        actions = 0

        def history_kline_page(self, code, **kwargs):
            result = super().history_kline_page(code, **kwargs)
            now[0] += timedelta(seconds=2)
            return result

        def adjustment_factors(self, code):
            self.actions += 1
            return super().adjustment_factors(code)

    wire = SlowHistory(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="capture_failed"):
        freezer.collect(wire, AS_OF, authorization(), raw_root=tmp_path, clock=lambda: now[0])
    assert len(wire.requests) == 1 and wire.actions == 0
    refs = list(tmp_path.glob("wire-response-*.json"))
    assert len(refs) == 1
    observation = json.loads(
        ObjectStore(tmp_path).get_bytes(ObjectRef.model_validate(json.loads(refs[0].read_bytes())))
    )
    assert observation["method"] == "history_kline_page"
    assert observation["received_at_utc"] == now[0].isoformat()


def test_v2_real_postreview_after_asof_freezes_and_reopens_original(tmp_path):
    raw = v2raw()
    result = freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=3)
    )
    original = ObjectStore(tmp_path).get_bytes(ObjectRef.model_validate(result["freeze_ref"]))
    reopened = freezer.reopen_freeze(tmp_path, result["freeze_digest"])
    assert reopened["schema_id"] == "qm.spy-daily.freeze.v2"
    assert reopened["financial_evaluation_executed"] is False
    assert reopened["actual_data_acceptance"] == "REQUIRES_INDEPENDENT_SOURCE_AND_FIELD_REVIEW"
    assert (
        ObjectStore(tmp_path).get_bytes(ObjectRef.model_validate(result["freeze_ref"])) == original
    )


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_use",
        "logged_out",
        "numeric_true",
        "stale_observation",
        "future_precheck",
        "unknown_account",
        "zero_once",
        "wrong_window",
        "remote_endpoint",
    ],
)
def test_v2_bad_preauthorization_never_reaches_wire(tmp_path, fault):
    auth = authorization()
    if fault == "unknown_use":
        auth["use_status"] = "PRECISE_UNKNOWN"
    elif fault == "logged_out":
        auth["quote_logged_in"] = False
    elif fault == "numeric_true":
        auth["program_ready"] = 1
    elif fault == "stale_observation":
        auth["metadata_observed_at_utc"] = (AS_OF - timedelta(minutes=31)).isoformat()
    elif fault == "future_precheck":
        auth["prechecked_at_utc"] = (AS_OF + timedelta(seconds=1)).isoformat()
    elif fault == "unknown_account":
        auth["account_metadata_sha256"] = "UNKNOWN"
    elif fault == "zero_once":
        auth["capture_authorization_sha256"] = "0" * 64
    elif fault == "wrong_window":
        auth["window_sha256"] = "f" * 64
    else:
        auth["endpoint_host"] = "remote.example"
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError):
        freezer.collect(
            wire, AS_OF, auth, raw_root=tmp_path, clock=lambda: AS_OF + timedelta(minutes=1)
        )
    assert wire.requests == [] and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "coverage_unknown",
        "empty_proof",
        "history_unavailable",
        "unknown_feed",
        "review_before_received",
        "review_after_freeze",
        "forged_raw",
        "forged_authorization",
        "requested_before_asof",
        "old_schema",
    ],
)
def test_v2_postreview_refuses_unknown_or_unbound_or_impossible_facts(tmp_path, fault):
    raw = v2raw()
    review = post_review(raw)
    if fault == "coverage_unknown":
        review["action_coverage_status"] = "UNKNOWN"
    elif fault == "empty_proof":
        review["action_coverage_sha256"] = "0" * 64
    elif fault == "history_unavailable":
        review["history_available"] = False
    elif fault == "unknown_feed":
        review["feed"] = "UNKNOWN"
    elif fault == "review_before_received":
        review["reviewed_at_utc"] = AS_OF.isoformat()
    elif fault == "review_after_freeze":
        review["reviewed_at_utc"] = (AS_OF + timedelta(minutes=4)).isoformat()
    elif fault == "forged_raw":
        review["capture_sha256"] = "f" * 64
    elif fault == "forged_authorization":
        review["authorization_sha256"] = "f" * 64
    elif fault == "requested_before_asof":
        raw["requested_at_utc"] = (AS_OF - timedelta(seconds=1)).isoformat()
        review = post_review(raw)
    else:
        review["schema_version"] = 1
    with pytest.raises(ValueError):
        freezer.freeze_capture(
            raw,
            AS_OF,
            freeze_evidence(raw, review=review),
            tmp_path,
            frozen_at=AS_OF + timedelta(minutes=3),
        )
    assert not list(tmp_path.iterdir())


def test_v1_new_freeze_is_read_only_not_a_capture_downgrade(tmp_path):
    with pytest.raises(ValueError, match="v1.*read.only"):
        freezer.freeze_capture(
            payload(freezer.plan_window(AS_OF)),
            AS_OF,
            evidence(),
            tmp_path,
            frozen_at=AS_OF + timedelta(minutes=2),
        )
    assert not list(tmp_path.iterdir())


def capture_args(tmp_path, auth):
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(auth), encoding="utf-8")
    return [
        "capture",
        "--as-of",
        AS_OF.isoformat(),
        "--authorization-json",
        str(path),
        "--root",
        str(tmp_path / "capture"),
        "--port",
        "11111",
        "--execute-once",
    ]


@pytest.mark.parametrize("fault", ["use_unknown", "port_mismatch", "stale", "v1_receipt"])
def test_v2_cli_bad_authorization_has_zero_transport_construction(
    tmp_path, monkeypatch, capsys, fault
):
    from quantmesh.moomoo import opend

    constructions = []
    monkeypatch.setattr(opend, "SdkTransport", lambda **kwargs: constructions.append(True))
    auth = authorization()
    if fault == "use_unknown":
        auth["use_status"] = "PRECISE_UNKNOWN"
    elif fault == "port_mismatch":
        auth["endpoint_port"] = 11112
    elif fault == "stale":
        auth["metadata_observed_at_utc"] = (AS_OF - timedelta(minutes=31)).isoformat()
    else:
        auth = evidence()
    assert (
        freezer.main(capture_args(tmp_path, auth), clock=lambda: AS_OF + timedelta(minutes=1)) == 2
    )
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSED"
    assert constructions == [] and not (tmp_path / "capture").exists()


def test_v2_permission_failure_preserves_intent_without_qualified_output_or_retry(
    tmp_path, monkeypatch, capsys
):
    from quantmesh.moomoo import opend

    class Denied(Wire):
        def history_kline_page(self, code, **kwargs):
            self.requests.append((code, kwargs))
            raise ValueError("synthetic permission denied; never echo vendor messages")

    wire = Denied(payload(freezer.plan_window(AS_OF)))
    constructions = []
    monkeypatch.setattr(
        opend, "SdkTransport", lambda **kwargs: (constructions.append(True), wire)[1]
    )
    old_version = freezer.version
    monkeypatch.setattr(
        freezer,
        "version",
        lambda name: "synthetic-no-sdk" if name == "moomoo-api" else old_version(name),
    )
    args = capture_args(tmp_path, authorization())
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=1)) == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {"status": "REFUSED", "code": "capture_failed"}
    assert (tmp_path / "capture/capture-intent.json").exists()
    assert not (tmp_path / "capture/freeze-receipt.json").exists()
    assert not (tmp_path / "capture/capture-ref.json").exists()
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=1)) == 2
    assert "capture_already_attempted" in capsys.readouterr().err
    assert len(wire.requests) == len(constructions) == 1


def test_v2_empty_action_responses_and_terminal_cursors_do_not_prove_coverage(tmp_path):
    raw = v2raw()
    raw["adjustment_factors"]["rows"] = []
    raw["dividends"]["rows"] = []
    review = post_review(raw)
    review["action_coverage_status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="post_review"):
        freezer.freeze_capture(
            raw,
            AS_OF,
            freeze_evidence(raw, review=review),
            tmp_path,
            frozen_at=AS_OF + timedelta(minutes=3),
        )
    assert not list(tmp_path.iterdir())


def test_v2_pre_observation_freshness_is_at_request_not_delayed_review(tmp_path):
    raw = v2raw()
    review = post_review(raw)
    review["reviewed_at_utc"] = (AS_OF + timedelta(hours=2)).isoformat()
    result = freezer.freeze_capture(
        raw,
        AS_OF,
        freeze_evidence(raw, review=review),
        tmp_path,
        frozen_at=AS_OF + timedelta(hours=2, minutes=1),
    )
    assert (
        freezer.reopen_freeze(tmp_path, result["freeze_digest"])["schema_id"]
        == "qm.spy-daily.freeze.v2"
    )


@pytest.mark.parametrize("fault", ["time", "coverage", "authorization", "v1_schema"])
def test_v2_reopen_rechecks_rebuilt_bound_review_without_fallback(tmp_path, fault):
    raw = v2raw()
    result = freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=3)
    )
    store = ObjectStore(tmp_path)
    receipt = json.loads(store.get_bytes(ObjectRef.model_validate(result["freeze_ref"])))
    review = post_review(raw)
    if fault == "time":
        review["reviewed_at_utc"] = AS_OF.isoformat()
    elif fault == "coverage":
        review["action_coverage_status"] = "UNKNOWN"
    elif fault == "authorization":
        review["authorization_sha256"] = "f" * 64
    else:
        review["schema_version"] = 1
    receipt["members"]["post-review.json"] = store.put_bytes(
        media_type="application/json", payload=freezer._canonical(review)
    ).model_dump(mode="json")
    protocol = json.loads(store.get_bytes(ObjectRef.model_validate(receipt["protocol_ref"])))
    protocol["members"] = receipt["members"]
    receipt["protocol_ref"] = store.put_bytes(
        media_type="application/json", payload=freezer._canonical(protocol)
    ).model_dump(mode="json")
    ref = store.put_bytes(media_type="application/json", payload=freezer._canonical(receipt))
    with pytest.raises(ValueError):
        freezer.reopen_freeze(tmp_path, ref.digest)


@pytest.mark.parametrize("fault", [None, "cost", "qualification", "timestamp", "bytes"])
def test_v1_original_bag_reopens_without_rewrite_and_keeps_strict_guards(tmp_path, fault):
    from pathlib import Path

    pack = json.loads(zlib.decompress(base64.b64decode(LEGACY_V1_PACK)))
    for relative, encoded in pack["objects"].items():
        path = tmp_path / relative
        assert path.is_relative_to(tmp_path) and ".." not in Path(relative).parts
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(encoded))
    digest_value = pack["digest"]
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = freezer.reopen_freeze(tmp_path, digest_value)
    assert result["schema_id"] == "qm.spy-daily.freeze.v1"
    assert (
        result["protocol"]["normalizer_sha256"]
        == "36be4fb0f8c725bdabda813f710f40f883cb3949d858e9b73f08bf2000057d0d"
    )
    assert {p: p.read_bytes() for p in before} == before
    if fault is None:
        return
    store = ObjectStore(tmp_path)
    receipt = {k: v for k, v in result.items() if k != "protocol"}
    if fault == "cost":
        protocol = copy.deepcopy(result["protocol"])
        protocol["costs"]["base_one_way_bps"] = 0
        receipt["protocol_ref"] = store.put_bytes(
            media_type="application/json", payload=freezer._canonical(protocol)
        ).model_dump(mode="json")
    elif fault == "qualification":
        receipt["actual_data_acceptance"] = "QUALIFIED"
    elif fault == "timestamp":
        receipt["frozen_at_utc"] = AS_OF.isoformat()
    else:
        store.path_for(
            ObjectRef.model_validate(receipt["members"]["normalized-bars.csv"])
        ).write_bytes(b"tampered")
    ref = store.put_bytes(media_type="application/json", payload=freezer._canonical(receipt))
    with pytest.raises(ValueError):
        freezer.reopen_freeze(tmp_path, ref.digest)


# Genuine synthetic v1 bag generated by merged tool36be4fb0 before this correction.
# No live data; original digest ed28d23f9202da01c9f3df56eac800cdaec18b873151532ed0d8c46c1dd3a437.
LEGACY_V1_PACK = (
    "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"
    "QI2CrXCNAm4/u55wAglwAglzQu4HJ1qvxSria7HbnqzFbgVqFGyFaxSA/fSiRgGXM2vNCdEaBUpPahQoAjUKFPEaBdue1CjY"
    "CtQo2ArXKGD204c5NpezfZwoxOPEpC9xQhHghCLOiW1POJEJcCIT5oTRjzjRukbBpa0gJ3pRo0ARqFGgiNco2PakRsFWYC12"
    "K7wWy+ynJ3Gi9b7YS1tRTqCecAILcAKLc8LtCSciAU5E4pzox7pTaQjECUM8Tij94AQRiBNEPE70Yi02FagXmwrXizV6Ui+W"
    "y9l2jl23FeGEClcf5thMzrZz7EtbEU4w+yE94cRSgBNLYU70Ind6bV+j4NJWlBNKTzihCnBCFedE2g9OtK5RkArXKDBe+1Gj"
    "gMtpteaEaI0CtSc1CpicUntOTCRhTpiLnnDCEuCEJcwJ2o/cqXWNgktbUU7gnnBCFuCELM6JsCeciAU4EQtzwuhHnCgF4kQp"
    "HidmPYkTs7I9J2alMCeSWT84kdD2nEioKCfKXux3YjVg288nSio8n5hJPeEEEuAEEufEqiecEIgTiXCcKPsSJwyBOGGIxwm1"
    "H5xofXaXKn52V9qPs7vMx/Zrsde27TnBzsTrw1psLWe7+cS1rQAnJud+rMVyOVvGiWtbAU5w+1n1hBOeACc8YU70YF9sLSdq"
    "zwmx/U7cfuSecEIR4IQizoltTziRCXAiE+aE0Y84UQjEiUI8Tkx6Eifa7ou9thXkRB/2xXI5l+05IbYvlttPD36zq+W02nNC"
    "bL8Ttx/UE05gAU5gcU64PeGEQJwwheNE0ZM40XZf7LWtICfa7otFUX1uuFYCVoDn4k/uQ0+gu00oM7y/r5HePGtPdkb2fnu+"
    "N8Pk27nVN2ea8rXjm7Nen772uZ7re9MHf+tTNvtsG30mzecUvEbet3Mhb/pIzT70tdnn23PURp+SNMfD9+zenKNTNvvQpmz8"
    "3KWbPkqzz62ur+fS3JxZcPuc3eXd1G/ndtz0Qc0+xlOzT9roMzk3+tTvNn2r+37Tp/mc4lYH17rYN32URp+SNPskpNFnJjX7"
    "0KZsfP/oTR+10ae6xTRs6lr+puvyMrf7Vpfvpo/S7HOL6bVu2U2dnqrRp6BN2cxVsw/+1qds9Emaz5kVjT4NXYdNXcvfdF1e"
    "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"
    "YbyilGVR61c1hzFn63z1ESWTOjL/7//+H+Qnm7M="
)
