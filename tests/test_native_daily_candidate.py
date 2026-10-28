"""Closed synthetic protocol/matrix; no real sample or empirical qualification."""

import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

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
    assert any(c.Decimal(row["cash_view"]) < c.Decimal(row["cash_raw_decimal"]) for row in trace)
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


@pytest.mark.parametrize("change", ["costs", "real_input_enabled", "code"])
def test_cold_read_rejects_self_consistent_relabelled_protocol(tmp_path, change):
    c = candidate()
    value = c.engineering_input()
    raw = c.freeze_protocol(value)
    result = c.evaluate(value, raw)
    protocol = json.loads(raw)
    protocol[change] = {"model": "foreign"} if change in ("costs", "code") else True
    store = ObjectStore(tmp_path)
    for name, data in (
        ("bars", value.bars_csv),
        ("distributions", value.distributions_json),
        ("schedule", value.schedule_json),
    ):
        store.put_bytes(result["inputs"][name]["media_type"], data)
    changed = c.canonical(protocol)
    result["protocol_ref"] = store.put_bytes("application/json", changed).model_dump()
    result["request_digest"] = c._sha(changed)
    result["code"] = protocol["code"]
    ref = store.put_bytes("application/json", c.canonical(result))
    with pytest.raises(c.CandidateError, match="artifact_invalid"):
        c.read_result(store, ref)


def test_flat_fixed_case_has_zero_undefined_and_costed_benchmarks():
    c = candidate()
    value = c.engineering_input("flat-v1")
    base = c.evaluate(value, c.freeze_protocol(value))["calculation"]["base5"]
    assert base["T"]["metrics"]["terminal_equity"] == 100000
    assert base["TO"]["metrics"]["fills"] == 0
    assert base["T"]["metrics"]["naive_sharpe_rf_zero"] is None
    assert base["B100"]["metrics"]["friction_usd"] > 0
    assert base["B100"]["metrics"]["terminal_equity"] < 100000


def test_cli_is_actual_closed_engineering_matrix_and_rejects_data_paths():
    script = Path(__file__).resolve().parents[1] / "tools/research/run_native_daily_engineering.py"
    run = subprocess.run([sys.executable, "-B", str(script)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "SYNTHETIC ENGINEERING ONLY" in run.stdout
    assert "base5" in run.stdout and "stress10" in run.stdout and "B100" in run.stdout
    assert "protocol" in run.stdout and "INSUFFICIENT" in run.stdout
    refused = subprocess.run(
        [sys.executable, "-B", str(script), "--input", "prices.csv"], capture_output=True, text=True
    )
    assert refused.returncode == 2 and "usage:" in refused.stderr and not refused.stdout


def test_zero_prior_volume_cancels_entry_without_price_error():
    c = candidate()
    import io

    import pandas as pd

    frame = pd.read_csv(io.BytesIO(c.engineering_input().bars_csv)).set_index("date")
    frame.loc[frame.index[:101], "volume"] = 0
    arm = c._Arm(frame, "TO")
    daily, trades = c.engine.run_cashbook(
        frame,
        pd.Series(0, index=frame.index),
        [],
        frame.index[100],
        frame.index[-1],
        _quantity_policy=arm,
    )
    assert trades == []
    attempted = [row for row in arm.trace if row["order"]["requested_quantity"]]
    assert len(attempted) == 1 and attempted[0]["filled"] == 0
    assert attempted[0]["cancelled"] == attempted[0]["order"]["requested_quantity"]
    assert daily.iloc[-1].equity == 100000


def test_partial_full_exit_retains_origin_until_actual_kernel_flattens():
    c = candidate()
    import io

    import pandas as pd

    frame = pd.read_csv(io.BytesIO(c.engineering_input().bars_csv)).set_index("date")
    # Authored test-only variation: profit100 initiates exit, capacity permits 10/day.
    frame.loc[frame.index[106] :, ["open", "high", "low", "close"]] = 310
    frame.loc[frame.index[94:108], "volume"] = 1000
    arm = c._Arm(frame, "TO")
    daily, trades = c.engine.run_cashbook(
        frame,
        pd.Series(0, index=frame.index),
        [],
        frame.index[100],
        frame.index[-1],
        _quantity_policy=arm,
    )
    exits = [
        row
        for row in arm.trace
        if row["order"]["metadata"] and row["order"]["metadata"]["action"]["kind"] == "full_exit"
    ]
    assert len(exits) > 1
    origin = exits[0]["order"]["metadata"]["full_exit_origin"]
    assert origin["reason"] == "profit100"
    assert all(row["order"]["metadata"]["full_exit_origin"] == origin for row in exits)
    assert daily.iloc[-1].shares == 0
    assert sum(t["quantity"] for t in trades) == 0


@pytest.mark.parametrize("change", ["numeric_type", "negative_zero"])
def test_protocol_requires_exact_fixed_canonical_values_before_math(change, monkeypatch):
    c = candidate()
    value = c.engineering_input()
    raw = c.freeze_protocol(value)
    changed = (
        raw.replace(b'"base5":5', b'"base5":5.0')
        if change == "numeric_type"
        else raw.replace(b'"cash_interest":0', b'"cash_interest":-0.0')
    )
    assert changed != raw
    monkeypatch.setattr(c.engine, "run_cashbook", lambda *a, **k: pytest.fail("identity ran math"))
    with pytest.raises(c.CandidateError, match="protocol_not_qualified"):
        c.evaluate(value, changed)


def _fixture_frame_and_run():
    import io

    import pandas as pd

    c = candidate()
    frame = pd.read_csv(io.BytesIO(c.engineering_input().bars_csv)).set_index("date")

    def run(bars):
        arm = c._Arm(bars, "TO")
        daily, trades = c.engine.run_cashbook(
            bars,
            pd.Series(0, index=bars.index),
            [],
            bars.index[100],
            bars.index[-1],
            _quantity_policy=arm,
        )
        return arm, daily, trades

    return frame, run


def test_actual_partial_ordinary_stage_cancels_remainder_once():
    frame, run = _fixture_frame_and_run()
    frame.loc[frame.index[94:108], "volume"] = 1000
    frame.loc[frame.index[103:105], "close"] = 170
    arm, _, trades = run(frame)
    reductions = [
        row
        for row in arm.trace
        if row["order"]["metadata"] and row["order"]["metadata"]["action"]["kind"] == "reduce"
    ]
    assert len(reductions) == 1
    reduced = reductions[0]
    assert reduced["order"]["requested_quantity"] == 33
    assert reduced["filled"] == -10 and reduced["cancelled"] == 23
    assert "sell25" in reduced["campaign"]["consumed"]
    assert sum(t["quantity"] for t in trades) == 0


def test_future_closes_cannot_change_earlier_actual_candidate_fills():
    frame, run = _fixture_frame_and_run()
    _, _, trades = run(frame)
    changed = frame.copy()
    changed.loc[changed.index[110] :, "close"] = 80
    _, _, later = run(changed)
    boundary = frame.index[110]
    assert [t for t in trades if t["date"] <= boundary] == [
        t for t in later if t["date"] <= boundary
    ]
    assert trades != later


def test_actual_candidate_terminal_capacity_failure_cannot_finish_cashbook():
    frame, run = _fixture_frame_and_run()
    frame.loc[frame.index[102] :, "volume"] = 0
    with pytest.raises(ArithmeticError, match="terminal liquidation incomplete"):
        run(frame)
