"""Closed synthetic protocol/matrix; no real sample or empirical qualification."""

import importlib
import json
from dataclasses import replace

import pytest

from quantmesh.data.objects import ObjectStore


def candidate():
    try:
        return importlib.import_module("quantmesh.research.native_daily_candidate")
    except ModuleNotFoundError:
        pytest.fail("approved closed candidate protocol is not implemented")


def test_fixed_matrix_is_computed_by_one_kernel_with_costed_cash_and_ex_pay():
    c = candidate()
    value = c.engineering_input()
    raw = c.freeze_protocol(value)
    report = c.evaluate(value, raw)
    assert report["schema_id"] == "qm.native-daily.candidate.report.v1"
    assert report["evidence_kind"] == "engineering_fixture"
    assert report["financial_qualification"] == "INSUFFICIENT"
    assert report["paper_allowed"] is report["live_allowed"] is False
    assert set(report["calculation"]) == {"base5", "stress10"}
    for scenario in report["calculation"].values():
        assert set(scenario) == {"T", "TO", "B50", "B100", "C"}
        for arm in scenario.values():
            assert arm["metrics"]["sessions"] == 21
            assert arm["metrics"]["terminal_shares"] == 0
            assert "buy_fill_count" in arm["metrics"]
            assert "long_entries" not in arm["metrics"]
    base = report["calculation"]["base5"]
    assert [t["quantity"] for t in base["TO"]["trades"]] == [333, 33, -33, -333]
    assert [t["quantity"] for t in base["T"]["trades"]] == [333, -333]
    assert base["TO"]["metrics"]["friction_usd"] == pytest.approx(63.4725)
    assert base["TO"]["metrics"]["dividend_earned_usd"] == 333
    assert base["TO"]["metrics"]["dividend_paid_usd"] == 333
    assert base["C"]["metrics"]["terminal_equity"] == 100000
    assert base["C"]["metrics"]["fills"] == 0
    ex_rows = [row for row in base["TO"]["daily"] if row["dividend_earned"]]
    assert len(ex_rows) == 1 and ex_rows[0]["receivable"] == 333
    assert ex_rows[0]["dividend_paid"] == 0


def test_numeric_view_is_conservative_and_never_writes_back_to_ledger():
    c = candidate()
    assert c.conservative_money(1.000000019) == c.Decimal("1.00000001")
    report = c.evaluate(c.engineering_input(), c.freeze_protocol(c.engineering_input()))
    trace = report["calculation"]["base5"]["TO"]["trace"]
    assert any(row["cash_view"] != row["cash_raw_decimal"] for row in trace)
    assert all(c.Decimal(row["cash_view"]) <= c.Decimal(row["cash_raw_decimal"]) for row in trace)


@pytest.mark.parametrize(
    "field", ["schema_id", "candidate", "code", "costs", "arms", "evidence_kind"]
)
def test_identity_or_role_mismatch_refuses_before_math(field, monkeypatch):
    c = candidate()
    value = c.engineering_input()
    protocol = json.loads(c.freeze_protocol(value))
    protocol[field] = "foreign_or_legacy_or_real"
    monkeypatch.setattr(c.engine, "run_cashbook", lambda *a, **kw: pytest.fail("refusal ran math"))
    with pytest.raises(c.CandidateError, match="protocol_not_qualified"):
        c.evaluate(value, c.canonical(protocol))


def test_fixture_bytes_cannot_be_relabelled_as_qualified_real_or_changed():
    c = candidate()
    value = c.engineering_input()
    raw = c.freeze_protocol(value)
    with pytest.raises(c.CandidateError, match="input_not_qualified"):
        c.evaluate(replace(value, bars_csv=value.bars_csv.replace(b"150", b"151")), raw)
    with pytest.raises(c.CandidateError, match="input_not_qualified"):
        c.evaluate(replace(value, evidence_kind="reviewed_real"), raw)
    with pytest.raises(c.CandidateError):
        c.engineering_input("d882c232_old_once_capture")


def test_unpaid_distribution_stays_receivable_through_terminal():
    c = candidate()
    value = c.engineering_input("unpaid-v1")
    arm = c.evaluate(value, c.freeze_protocol(value))["calculation"]["base5"]["TO"]
    assert arm["metrics"]["terminal_receivable"] == 333
    assert arm["metrics"]["dividend_paid_usd"] == 0


def test_original_publication_reopens_without_calculation_or_reidentifying_source(
    tmp_path, monkeypatch
):
    c = candidate()
    value = c.engineering_input()
    store = ObjectStore(tmp_path)
    ref = c.publish(value, c.freeze_protocol(value), store)
    original = store.get_bytes(ref)
    monkeypatch.setattr(c, "evaluate", lambda *args: pytest.fail("read recomputed"))
    assert c.read_result(store, ref) == original
    assert c.read_result(ObjectStore(tmp_path), ref) == original


def test_publish_does_not_create_objects_for_rejected_protocol(tmp_path):
    c = candidate()
    value = c.engineering_input()
    store = ObjectStore(tmp_path)
    with pytest.raises(c.CandidateError):
        c.publish(value, b'{"schema_id":"old-spy-profile"}', store)
    assert not list(tmp_path.rglob("*.json"))
