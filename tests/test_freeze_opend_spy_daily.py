"""Bounded freezer tests use synthetic wire prices, never market observations."""

import copy
import csv
import hashlib
import io
import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.data.objects import ObjectRef, ObjectStore
from tools.research import freeze_opend_spy_daily as freezer

AS_OF = datetime(2026, 10, 21, 16, tzinfo=UTC)


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
        wire, AS_OF, evidence(), raw_root=tmp_path, clock=lambda: AS_OF + timedelta(minutes=1)
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
        freezer.collect(wire, AS_OF, evidence(), raw_root=tmp_path, clock=lambda: AS_OF)
    assert len(wire.requests) == 2


@pytest.mark.parametrize(
    "field",
    [
        "history_available",
        "spy_quota_available",
        "full_action_history_reviewed",
        "status",
        "checked_at_utc",
    ],
)
def test_unqualified_record_stops_before_wire_effects(field, tmp_path):
    record = evidence()
    record[field] = False if isinstance(record[field], bool) else "unverified"
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="evidence"):
        freezer.collect(wire, AS_OF, record, raw_root=tmp_path, clock=lambda: AS_OF)
    assert wire.requests == []


def test_freeze_and_reopen_bind_original_normalized_bytes_before_evaluation(tmp_path):
    window = freezer.plan_window(AS_OF)
    raw = payload(window)
    record = freezer.freeze_capture(
        raw, AS_OF, evidence(), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
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
    freezer.freeze_capture(raw, AS_OF, evidence(), tmp_path, frozen_at=AS_OF + timedelta(minutes=2))
    assert store.get_bytes(ObjectRef.model_validate(record["freeze_ref"])) == first
    ref = ObjectRef.model_validate(reopened["members"]["normalized-bars.csv"])
    store.path_for(ref).write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        freezer.reopen_freeze(tmp_path, record["freeze_digest"])


def test_invalid_capture_never_publishes_freeze(tmp_path):
    raw = payload(freezer.plan_window(AS_OF))
    raw["history_pages"][0]["rows"].pop()
    with pytest.raises(ValueError):
        freezer.freeze_capture(
            raw, AS_OF, evidence(), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
        )
    assert not list(tmp_path.rglob("*.json"))


def test_unknown_sensitive_evidence_fields_are_refused_before_capture(tmp_path):
    record = evidence()
    record["access_token"] = "not-a-real-secret"
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="evidence"):
        freezer.collect(wire, AS_OF, record, raw_root=tmp_path, clock=lambda: AS_OF)
    assert wire.requests == []


def test_numeric_true_does_not_authorize_a_source_record(tmp_path):
    record = evidence()
    record["history_available"] = 1
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    with pytest.raises(ValueError, match="evidence"):
        freezer.collect(wire, AS_OF, record, raw_root=tmp_path, clock=lambda: AS_OF)
    assert wire.requests == []


def test_explicit_foreign_currency_cannot_be_hidden_in_a_us_price_row():
    window = freezer.plan_window(AS_OF)
    raw = payload(window)
    raw["history_pages"][0]["rows"][0]["currency"] = "HKD"
    with pytest.raises(ValueError):
        freezer.normalize_capture(raw, window, evidence())


def test_reopen_rejects_a_content_addressed_but_different_cost_policy(tmp_path):
    raw = payload(freezer.plan_window(AS_OF))
    result = freezer.freeze_capture(
        raw, AS_OF, evidence(), tmp_path, frozen_at=AS_OF + timedelta(minutes=2)
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
        raw_path, record_path = tmp_path / "raw.json", tmp_path / "evidence.json"
        raw_path.write_text(json.dumps(payload(freezer.plan_window(AS_OF))), encoding="utf-8")
        record_path.write_text(json.dumps(evidence()), encoding="utf-8")
        result = freezer.main(
            [
                "freeze",
                "--as-of",
                AS_OF.isoformat(),
                "--capture-json",
                str(raw_path),
                "--evidence-json",
                str(record_path),
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
    record.write_text(json.dumps(evidence()), encoding="utf-8")
    args = [
        "capture",
        "--as-of",
        AS_OF.isoformat(),
        "--evidence-json",
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
    assert len(wire.requests) == 1
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=2)) == 2
    assert "capture_already_attempted" in capsys.readouterr().err
    assert len(wire.requests) == 1


def test_operator_help_is_bounded_and_readable(capsys):
    with pytest.raises(SystemExit) as stop:
        freezer.main(["capture", "--help"])
    assert stop.value.code == 0
    help_text = capsys.readouterr().out
    assert "--evidence-json" in help_text and "--execute-once" in help_text
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
    record.write_text(json.dumps(evidence()), encoding="utf-8")
    root = tmp_path / "owned"
    args = [
        "capture",
        "--as-of",
        AS_OF.isoformat(),
        "--evidence-json",
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
    result = freezer.freeze_capture(
        payload(freezer.plan_window(AS_OF)),
        AS_OF,
        evidence(),
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
    monkeypatch.setattr(freezer, "_source_identity", lambda: {"changed": "f" * 64}, raising=False)
    with pytest.raises(ValueError, match="source_changed"):
        freezer.freeze_capture(
            payload(freezer.plan_window(AS_OF)),
            AS_OF,
            evidence(),
            tmp_path,
            frozen_at=AS_OF + timedelta(minutes=2),
        )
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("fault", ["qualification", "before_capture", "extra", "stale_evidence"])
def test_reopen_refuses_rebuilt_invalid_envelopes(tmp_path, fault):
    result = freezer.freeze_capture(
        payload(freezer.plan_window(AS_OF)),
        AS_OF,
        evidence(),
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
        receipt["frozen_at_utc"] = (AS_OF + timedelta(minutes=31)).isoformat()
    ref = store.put_bytes(media_type="application/json", payload=json.dumps(receipt).encode())
    with pytest.raises(ValueError):
        freezer.reopen_freeze(tmp_path, ref.digest)
