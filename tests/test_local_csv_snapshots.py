"""Owned daily CSV engineering samples; no real source or qualification claim."""

import hashlib
import importlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.data.objects import ObjectIntegrityError
from quantmesh.research.jobs import DatasetRejected

NOW = datetime(2026, 10, 25, 0, tzinfo=UTC)
CSV = (
    "timestamp_utc,open,high,low,close,volume\n"
    "2026-10-15T13:30:00Z,100,102,99,101,1000\n"
    "2026-10-16T13:30:00Z,101,103,100,102,1100\n"
)


def request(**overrides):
    value = dict(
        schema_version=1,
        label="Owned engineering sample",
        symbol="SPY",
        venue="moomoo",
        calendar_id="XNYS",
        interval="1d",
        required_start="2026-10-15",
        required_end="2026-10-16",
        evidence_kind="fixture",
        source={"provider": "owned synthetic", "received_at": None},
        csv_text=CSV,
    )
    value.update(overrides)
    return value


def local(tmp_path, **overrides):
    module = importlib.import_module("quantmesh.research.local_csv_snapshots")
    catalog = module.LocalCsvCatalog(tmp_path, clock=lambda: NOW)
    report = catalog.import_csv(module.LocalCsvRequest.model_validate(request(**overrides)))
    return catalog, report


def test_import_quality_reference_and_cold_reopen(tmp_path):
    assert importlib.util.find_spec("quantmesh.research.local_csv_snapshots") is not None
    module = importlib.import_module("quantmesh.research.local_csv_snapshots")
    catalog = module.LocalCsvCatalog(tmp_path, clock=lambda: NOW)
    report = catalog.import_csv(module.LocalCsvRequest.model_validate(request()))
    assert report.coverage.rows == 2
    assert report.coverage.valid_rows == 2
    assert report.coverage.missing_sessions == []
    assert report.qualification.structural_status == "PASS"
    assert report.qualification.status == "INSUFFICIENT"
    assert report.qualification.R3 == "NOT_AUTHORIZED"
    assert report.next_action.submission_allowed is False
    assert report.dataset_ref.permission_class == "local_research"
    assert catalog.original_bytes(report.snapshot_id) == CSV.encode()
    assert catalog.import_csv(module.LocalCsvRequest.model_validate(request())) == report
    reopened = module.LocalCsvCatalog(tmp_path, clock=lambda: NOW)
    assert reopened.get(report.snapshot_id) == report
    reference = reopened.reference(report.snapshot_id)
    assert reference.dataset_ref == report.dataset_ref
    assert reference.eligibility.status == "BLOCKED"
    assert reference.manifest.coverage[0].rows == 2
    assert (
        len(reopened.read_bars(report.snapshot_id, report.dataset_ref, engineering_only=True)) == 2
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("100,102,99,101,1000", "0,102,99,101,1000"),
        ("100,102,99,101,1000", "100,98,99,101,1000"),
        ("100,102,99,101,1000", "100,102,102,101,1000"),
        ("100,102,99,101,1000", "100,102,99,101,-1"),
        ("100,102,99,101,1000", "NaN,102,99,101,1000"),
        ("100,102,99,101,1000", "100,Infinity,99,101,1000"),
        ("100,102,99,101,1000", "true,102,99,101,1000"),
    ],
)
def test_invalid_values_are_retained_reject_not_repaired(tmp_path, old, new):
    value = CSV.replace(old, new)
    catalog, report = local(tmp_path, csv_text=value)
    assert report.qualification.status == "REJECT"
    assert report.dataset_ref is None
    assert catalog.reference(report.snapshot_id).normalized_csv is None
    assert catalog.original_bytes(report.snapshot_id) == value.encode()
    finding = next(check for check in report.checks if check.code == "bar_values")
    assert finding.status == "REJECT" and finding.locations[0].row == 2


@pytest.mark.parametrize(
    "case", ["duplicate", "reverse", "missing", "bad_time", "non_utc", "off_open", "empty"]
)
def test_time_duplicate_missing_order_and_empty_are_separate_facts(tmp_path, case):
    rows = CSV.splitlines()
    replacements = {
        "duplicate": CSV + rows[1] + "\n",
        "reverse": "\n".join([rows[0], rows[2], rows[1]]) + "\n",
        "missing": "\n".join(rows[:2]) + "\n",
        "bad_time": CSV.replace("2026-10-15T13:30:00Z", "not-a-time"),
        "non_utc": CSV.replace("2026-10-15T13:30:00Z", "2026-10-15T21:30:00+08:00"),
        "off_open": CSV.replace("13:30:00Z", "13:31:00Z"),
        "empty": rows[0] + "\n",
    }
    expected = {
        "duplicate": "bar_duplicates",
        "reverse": "bar_order",
        "missing": "session_coverage",
        "bad_time": "bar_time",
        "non_utc": "bar_time",
        "off_open": "bar_time",
        "empty": "bar_values",
    }
    catalog, report = local(tmp_path, csv_text=replacements[case])
    assert report.qualification.structural_status == "REJECT"
    assert report.dataset_ref is None
    assert next(check for check in report.checks if check.code == expected[case]).status == "REJECT"
    assert catalog.reference(report.snapshot_id).eligibility.status == "BLOCKED"
    if case == "missing":
        assert report.coverage.missing_sessions == ["2026-10-16"]


def test_dst_and_weekend_are_pinned_sessions_not_24hour_gaps(tmp_path):
    csv_text = CSV.replace("2026-10-15T13:30:00Z", "2026-03-06T14:30:00Z").replace(
        "2026-10-16T13:30:00Z", "2026-03-09T13:30:00Z"
    )
    _, report = local(
        tmp_path, csv_text=csv_text, required_start="2026-03-06", required_end="2026-03-09"
    )
    assert report.qualification.structural_status == "PASS"
    assert report.coverage.expected_sessions == 2
    assert report.coverage.missing_sessions == []


def test_half_day_bar_needs_actual_close_and_research_grace(tmp_path):
    from quantmesh.research.local_csv_snapshots import LocalCsvCatalog, LocalCsvRequest

    payload = request(
        csv_text=CSV.splitlines()[0] + "\n2026-11-27T14:30:00Z,100,102,99,101,0\n",
        required_start="2026-11-27",
        required_end="2026-11-27",
    )
    before = LocalCsvCatalog(
        tmp_path / "before", clock=lambda: datetime(2026, 11, 27, 18, 29, tzinfo=UTC)
    )
    rejected = before.import_csv(LocalCsvRequest.model_validate(payload))
    assert (
        next(check for check in rejected.checks if check.code == "unfinished_session").status
        == "REJECT"
    )
    after = LocalCsvCatalog(
        tmp_path / "after", clock=lambda: datetime(2026, 11, 27, 18, 30, tzinfo=UTC)
    )
    completed = after.import_csv(LocalCsvRequest.model_validate(payload))
    assert completed.qualification.structural_status == "PASS"
    assert completed.freshness.status == "CURRENT"
    assert (
        completed.qualification.status == "INSUFFICIENT"
    )  # zero volume never establishes fillability.


@pytest.mark.parametrize("receipt", ["2026-10-16T14:00:00Z", "2030-01-01T00:00:00Z"])
def test_receipt_contradictions_are_facts_not_pit_proof(tmp_path, receipt):
    _, report = local(tmp_path, source={"received_at": receipt})
    assert (
        next(check for check in report.checks if check.code == "source_receipt").status == "REJECT"
    )


def test_claimed_entitlement_and_phase1_digests_never_grant_qualification(tmp_path):
    catalog, report = local(
        tmp_path,
        evidence_kind="user_snapshot",
        source={
            "provider": "caller claimed source",
            "license_scope": "approved",
            "license_evidence": "caller says approved",
            "pit_status": "verified",
            "adjustment": "adjusted",
            "volume_unit": "shares",
        },
        evidence={
            "preauthorization_sha256": "a" * 64,
            "post_review_sha256": "b" * 64,
            "source_evidence_sha256": "c" * 64,
        },
    )
    assert report.qualification.structural_status == "PASS"
    assert report.qualification.status == "INSUFFICIENT"
    assert report.qualification.R1 == report.qualification.R2 == "INSUFFICIENT"
    assert report.qualification.R3 == "NOT_AUTHORIZED"
    assert report.source.received_at is None
    assert all(
        next(check for check in report.checks if check.code == code).status == "INSUFFICIENT"
        for code in ("source_rights", "point_in_time", "corporate_actions", "phase1_evidence")
    )
    with pytest.raises(DatasetRejected):
        catalog.read_bars(report.snapshot_id, report.dataset_ref, engineering_only=True)


def test_reference_and_pin_use_existing_contracts_without_fixture_permission(tmp_path):
    from quantmesh.research.jobs import ResearchJobRequest
    from quantmesh.research.strategy_registry import validate_dataset

    catalog, report = local(tmp_path)
    reference = catalog.reference(report.snapshot_id)
    assert reference.manifest.dataset == report.dataset_ref.dataset_id
    assert reference.manifest.source == "local_csv_unverified"
    assert report.dataset_ref.export_digest == reference.normalized_csv.digest
    assert reference.manifest.coverage[0].start.isoformat() == "2026-10-15T13:30:00+00:00"
    assert reference.runner_status == "blocked_unqualified_input"
    setup = ResearchJobRequest(
        strategy_id="momentum",
        strategy_version="1",
        dataset=report.dataset_ref,
        interval="1d",
        universe=[{"venue": "moomoo", "symbol": "SPY"}],
        costs={"fee_bps": 1, "half_spread_bps": 1, "slippage_bps": 1},
        window_spec={"train_bars": 2, "test_bars": 1, "step_bars": 1},
    )
    with pytest.raises(DatasetRejected, match="permission_unsupported"):
        validate_dataset(setup, tmp_path, NOW)
    with pytest.raises(DatasetRejected):
        catalog.read_bars(report.snapshot_id, report.dataset_ref)
    with pytest.raises(DatasetRejected):
        catalog.read_bars(
            report.snapshot_id,
            report.dataset_ref.model_copy(update={"revision": 2}),
            engineering_only=True,
        )


def test_generated_bars_hydrate_existing_costed_backtester_engineering_only(tmp_path):
    from quantmesh.research.baselines import run_walk_forward
    from quantmesh.research.reports import CostModel, WalkForwardSpec

    lines = [CSV.splitlines()[0]]
    for index in range(8):
        day = (datetime(2026, 10, 15, tzinfo=UTC) + timedelta(days=index)).isoformat()
        price = 100 + index
        lines.append(f"{day},{price},{price + 2},{price - 1},{price + 1},1000")
    catalog, report = local(
        tmp_path,
        csv_text="\n".join(lines) + "\n",
        venue="hyperliquid",
        calendar_id="24/7",
        symbol="BTC",
        required_end="2026-10-22",
    )
    bars = catalog.read_bars(report.snapshot_id, report.dataset_ref, engineering_only=True)
    assert bars[0].instrument.currency == "UNKNOWN"
    result = run_walk_forward(
        {"BTC": bars},
        strategy="momentum",
        window_spec=WalkForwardSpec(train_bars=2, test_bars=2, step_bars=2),
        costs=CostModel(fee_bps=1, half_spread_bps=1, slippage_bps=1),
    )
    assert len(result.windows) == 3
    assert (
        report.qualification.R1 == "INSUFFICIENT"
    )  # Engine execution is engineering evidence only.


def test_pinned_report_stays_unchanged_while_display_freshness_ages(tmp_path):
    from quantmesh.research.local_csv_snapshots import LocalCsvCatalog

    catalog, report = local(tmp_path)
    raw = catalog.report_bytes(report.snapshot_id)
    assert hashlib.sha256(raw).hexdigest() == report.report_digest
    later = LocalCsvCatalog(tmp_path, clock=lambda: NOW + timedelta(days=3))
    assert later.get(report.snapshot_id).freshness.age_sessions > report.freshness.age_sessions
    assert later.report_bytes(report.snapshot_id) == raw
    assert later.get(report.snapshot_id).imported_at == report.imported_at


def test_problem_locations_are_bounded_but_total_count_is_not_lost(tmp_path):
    rows = CSV.splitlines()
    _, report = local(tmp_path, csv_text=rows[0] + "\n" + (rows[1] + "\n") * 150)
    duplicate = next(check for check in report.checks if check.code == "bar_duplicates")
    assert duplicate.count == 149
    assert len(duplicate.locations) == 100 and duplicate.locations_truncated


def test_tampered_original_and_reference_are_not_silently_replaced(tmp_path):
    catalog, report = local(tmp_path)
    index_path = tmp_path / "snapshots" / f"{report.snapshot_id}.json"
    index = json.loads(index_path.read_bytes())
    from quantmesh.data.objects import ObjectRef

    original_path = catalog.objects.path_for(ObjectRef.model_validate(index["original"]))
    original_path.write_bytes(b"tampered owned fixture")
    with pytest.raises(ObjectIntegrityError):
        catalog.get(report.snapshot_id)
    with pytest.raises(ObjectIntegrityError):
        catalog.import_csv(
            importlib.import_module(
                "quantmesh.research.local_csv_snapshots"
            ).LocalCsvRequest.model_validate(request())
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "../SPY"},
        {"symbol": "CON"},
        {"symbol": "SPY."},
        {"schema_version": True},
        {"interval": "1m"},
        {"calendar_id": "unknown"},
        {"required_start": "2026-10-17", "required_end": "2026-10-16"},
        {"venue": "hyperliquid", "calendar_id": "XNYS"},
        {"source": {"received_at": "2026-10-16T14:00:00"}},
        {"evidence": {"preauthorization_sha256": "0" * 64}},
    ],
)
def test_invalid_metadata_is_rejected_before_storage(changes):
    from quantmesh.research.local_csv_snapshots import LocalCsvRequest

    with pytest.raises(ValidationError):
        LocalCsvRequest.model_validate(request(**changes))


def test_input_byte_and_row_budgets_are_enforced_before_publication(tmp_path):
    from quantmesh.research.local_csv_snapshots import LocalCsvCatalog, LocalCsvRequest
    from quantmesh.research.realdata_snapshots import SnapshotInputError, SnapshotTooLarge

    catalog = LocalCsvCatalog(tmp_path, clock=lambda: NOW)
    multi_byte = LocalCsvRequest.model_validate(request(csv_text="é" * (1024 * 1024 + 1)))
    with pytest.raises(SnapshotTooLarge):
        catalog.import_csv(multi_byte)
    over_rows = CSV.splitlines()[0] + "\n" + (CSV.splitlines()[1] + "\n") * 10001
    with pytest.raises(SnapshotInputError):
        catalog.import_csv(LocalCsvRequest.model_validate(request(csv_text=over_rows)))
    assert not (tmp_path / "snapshots").exists()


def test_replaced_reference_index_and_missing_objects_fail_closed(tmp_path):
    from quantmesh.data.objects import ObjectRef

    catalog, first = local(tmp_path)
    _, other = local(tmp_path, label="Second owned metadata version")
    first_path = tmp_path / "snapshots" / f"{first.snapshot_id}.json"
    second_path = tmp_path / "snapshots" / f"{other.snapshot_id}.json"
    index, second = json.loads(first_path.read_bytes()), json.loads(second_path.read_bytes())
    changed = {**index, "reference": second["reference"]}
    first_path.write_text(json.dumps(changed))
    with pytest.raises(ObjectIntegrityError):
        catalog.get(first.snapshot_id)
    first_path.write_text(json.dumps(index))
    catalog.objects.path_for(ObjectRef.model_validate(index["manifest"])).unlink()
    with pytest.raises(ObjectIntegrityError):
        catalog.get(first.snapshot_id)


def test_nonregular_index_and_root_link_are_refused(tmp_path, monkeypatch):
    import quantmesh.research.local_csv_snapshots as module

    catalog, report = local(tmp_path)
    monkeypatch.setattr(module, "is_reparse_point", lambda path: path == tmp_path)
    with pytest.raises(ObjectIntegrityError):
        catalog.get(report.snapshot_id)


def test_true_weekend_empty_window_is_explicit_reject_not_zero_coverage_success(tmp_path):
    _, report = local(tmp_path, required_start="2026-10-17", required_end="2026-10-18")
    assert report.coverage.expected_sessions == 0  # Known empty selected XNYS range.
    assert report.qualification.structural_status == "REJECT"
    assert (
        next(check for check in report.checks if check.code == "session_coverage").status
        == "REJECT"
    )
    assert report.dataset_ref is None


def test_elapsed_session_does_not_establish_source_finality(tmp_path):
    _, report = local(tmp_path)
    assert (
        next(check for check in report.checks if check.code == "unfinished_session").status
        == "PASS"
    )
    finality = next(check for check in report.checks if check.code == "source_finality")
    assert finality.status == "INSUFFICIENT"
    assert "not prove" in finality.message
    assert report.source.received_at is None
