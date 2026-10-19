"""Synthetic historical-package contracts; retained Python must stay inert."""

import hashlib
import importlib
import io
import json
import zipfile
from datetime import UTC, datetime

import pytest

from quantmesh.data.objects import ObjectIntegrityError
from quantmesh.research.realdata_snapshots import SnapshotCatalog
from tests.test_realdata_snapshots import package as snapshot_package

CASES = (
    "final-base5bps",
    "final-stress10bps",
    "final-delay1session5bps",
    "final-gross0bps",
    "development2020-base5bps",
    "validation2022-base5bps",
    "validation2023-base5bps",
    "validation2024-base5bps",
)
EXPERIMENT = "QM-REAL-ETF-001-D-20261018"
MISSING = [
    "PIT availability/revision history",
    "historical executable09:35 NBBO/size and costs",
    "trading/product data entitlement",
    "pristine blind holdout and full prior trial ledger",
    "unresolved2021 dividend source discrepancy",
    "user investment utility/risk budget",
]


def backend():
    assert importlib.util.find_spec("quantmesh.research.frozen_experiments") is not None, (
        "frozen experiment preservation is not implemented"
    )
    return importlib.import_module("quantmesh.research.frozen_experiments")


def encoded(value):
    return json.dumps(value).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def pack(files, extras=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in [*files.items(), *extras]:
            archive.writestr(name, value)
    return buffer.getvalue()


def package(
    snapshot,
    *,
    change_protocol=None,
    change_result=None,
    change_files=None,
    change_manifest=None,
    extras=(),
):
    with zipfile.ZipFile(io.BytesIO(snapshot)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}
    code = ["engine.py", "data_io.py", "xlsx_rows.py", "run_experiment.py", "test_engine.py"]
    inputs = {name: sha(value) for name, value in files.items()}
    for name in code:
        files[name] = b'raise RuntimeError("never execute imported Python")\n'
    protocol = {
        "experiment_id": EXPERIMENT,
        "frozen_at_utc": "2026-10-18T15:07:06+00:00",
        "inputs": inputs,
        "code": {name: sha(files[name]) for name in code},
        "strategy": {
            "symbol": "SPY",
            "lookback": 100,
            "comparison": (
                "causal total-return close > trailing100-session mean, "
                "including current completed close; equal=>cash"
            ),
            "execution": "next-session raw DAILY OPEN proxy; not original09:35 execution",
            "short_allowed": False,
            "leverage": False,
        },
        "accounting": {"capital_usd": 100000},
        "costs": {
            "single_side_proxy_bps": 5,
            "stress_bps": 10,
            "gross_diagnostic_bps": 0,
            "extra_delay_stress_sessions": 1,
            "actual_nbbo_and_costs_verified": False,
            "fee_spread_slippage_breakdown": "unknown; combined research proxy only",
        },
        "data": {
            "license": (
                "public research access observed; no redistribution/live entitlement verified"
            ),
            "secondary_source_conflict": {
                "date": "2021-12-17",
                "yahoo_usd": 1.633,
                "issuer_usd": 1.636431,
                "resolution": "unresolved; retain conflict",
            },
        },
        "splits": {"final": ["2025-01-02", "2026-10-16"]},
        "exposure_and_trials": {
            "current_empirical_trial": 1,
            "parameter_variants_searched": 0,
            "source_discovery_exposed_some_2026_SPY_prices": True,
            "no_strategy_results_evaluated_before_this_freeze": True,
            "pristine_blind_or_prospective_test": False,
            "historical_external_research_trials": "unknown; no complete ledger",
        },
        "rules": {
            "proxy_economic_pass": (
                "net profit>0 AND main/sensitivity95% lower bounds>0 "
                "AND stress net profit>0 AND no capacity clipping"
            ),
            "proxy_reject": (
                "net profit<=0 OR mean paired daily difference<=0; "
                "if mean>0 but lower bound<=0 => INSUFFICIENT"
            ),
            "formal_R1_R2": (
                "all data/PIT/license/execution/selection gates required; "
                "unresolved hard evidence=>INSUFFICIENT regardless proxy arithmetic"
            ),
            "R3": "NOT_AUTHORIZED; no forward sample, user risk budget or live approval",
        },
    }
    if change_protocol:
        change_protocol(protocol)
    files["protocol.json"] = encoded(protocol)
    files["freeze-receipt.json"] = encoded(
        {
            "protocol_sha256": sha(files["protocol.json"]),
            "frozen_at_utc": protocol["frozen_at_utc"],
            "created_before_results": True,
            "input_files": 7,
            "code_files": 5,
        }
    )
    numeric = (
        "terminal_equity net_profit_usd total_return cagr max_drawdown "
        "max_underwater_sessions annualized_volatility naive_sharpe_rf_zero "
        "sortino_target_zero calmar worst_day historical_es_95 es_tail_observations "
        "fills long_entries friction_usd dividend_earned_usd dividend_paid_usd "
        "terminal_receivable gross_traded_notional_over_initial_capital "
        "capacity_clipped_sessions terminal_shares"
    ).split()
    metrics = {key: 0.0 for key in numeric}
    metrics.update(
        sessions=2,
        start="2025-01-02",
        end="2026-10-16",
        total_return=0.2,
        net_profit_usd=20000,
        max_drawdown=-0.1,
        naive_sharpe_rf_zero=None,
    )
    result = {
        "experiment_id": EXPERIMENT,
        "protocol_sha256": sha(files["protocol.json"]),
        "cases": {
            name: {
                "strategy": dict(metrics),
                "benchmark": dict(metrics, total_return=0.3),
                "cash_benchmark_total_return": 0.0,
                "net_total_return_difference": -0.1,
                "inference": [],
            }
            for name in CASES
        },
        "verdict": {
            "proxy_economic_criterion": "REJECT",
            "formal_research_R1": "INSUFFICIENT",
            "formal_tradeable_candidate_R2": "INSUFFICIENT",
            "R3": "NOT_AUTHORIZED",
            "hard_missing_evidence": MISSING,
        },
    }
    windows = {
        "development2020-base5bps": ("2020-01-02", "2020-12-31"),
        "validation2022-base5bps": ("2022-01-03", "2022-12-30"),
        "validation2023-base5bps": ("2023-01-03", "2023-12-29"),
        "validation2024-base5bps": ("2024-01-02", "2024-12-31"),
    }
    for name, (start, end) in windows.items():
        for side in ("strategy", "benchmark"):
            result["cases"][name][side].update(start=start, end=end)
    if change_result:
        change_result(result)
    files["run-1/result.json"] = encoded(result)
    for name in CASES:
        for suffix in ("strategy.csv", "benchmark.csv", "trades.json"):
            files[f"run-1/{name}-{suffix}"] = (
                b"[]" if suffix.endswith("json") else b"date,nav\n2025-01-02,100000\n"
            )
    files.update(
        {
            "report.md": b"<script>throw new Error('inert')</script>",
            "local-timeline.json": b"[]",
            "review.md": b"recorded review",
            "checks-red.log": b"recorded RED",
            "checks-green.log": b"recorded GREEN",
            "verification.json": b"{}",
        }
    )
    if change_files:
        change_files(files)
    manifest = {
        "schema_id": "qm.frozen-spy-experiment.v1",
        "experiment_id": EXPERIMENT,
        "snapshot_id": sha(snapshot),
        "files": {name: sha(value) for name, value in files.items()},
    }
    if change_manifest:
        change_manifest(manifest)
    files["manifest.json"] = encoded(manifest)
    return pack(files, extras)


@pytest.fixture
def source(tmp_path):
    snapshots = SnapshotCatalog(tmp_path / "snapshots")
    payload = snapshot_package()
    snapshots.import_archive(payload)
    return snapshots, payload


def test_import_binds_originals_and_reopens_immutable_first_receipt(tmp_path, source):
    mod = backend()
    snapshots, snapshot = source

    def clock():
        return datetime(2026, 10, 19, tzinfo=UTC)

    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots, clock=clock)
    payload = package(snapshot)
    report = catalog.import_archive(payload)
    assert report["package_id"] == sha(payload)
    assert report["snapshot_id"] == sha(snapshot)
    assert report["proxy_verdict"] == "REJECT"
    assert report["formal_verdict"] == {
        "R1": "INSUFFICIENT",
        "R2": "INSUFFICIENT",
        "R3": "NOT_AUTHORIZED",
    }
    assert report["oos"] == {"state": "CONSUMED", "pristine_blind": False}
    assert report["trials"]["prior"] is None
    assert report["verification"]["chronology"] == "UNVERIFIED"
    assert report["verification"]["economics"] == "IMPORTED_NOT_RECOMPUTED"
    assert report["cases"][0]["case_id"] == "final-base5bps"
    assert report["cases"][0]["strategy"]["naive_sharpe_rf_zero"] is None
    assert len(report["cases"]) == 8
    reopened = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    assert reopened.import_archive(payload) == report
    assert reopened.get(sha(payload)) == report
    assert reopened.list() == [report]
    assert reopened.artifact_bytes(sha(payload), "archive") == payload
    assert reopened.artifact_bytes(sha(payload), "report").startswith(b"<script>")
    assert not list(tmp_path.rglob("*.py"))


@pytest.mark.parametrize(
    "change",
    [
        {"change_manifest": lambda m: m.update(snapshot_id="a" * 64)},
        {"change_protocol": lambda p: p["inputs"].update({"normalized-bars.csv": "0" * 64})},
        {"change_protocol": lambda p: p["code"].update({"engine.py": "0" * 64})},
        {"change_result": lambda r: r.update(protocol_sha256="0" * 64)},
        {"change_result": lambda r: r.update(experiment_id="other")},
        {"change_files": lambda f: f.update({"freeze-receipt.json": b"{}"})},
    ],
)
def test_binding_failures_publish_nothing(tmp_path, source, change):
    mod = backend()
    snapshots, snapshot = source
    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    with pytest.raises(mod.FrozenExperimentInputError):
        catalog.import_archive(package(snapshot, **change))
    assert catalog.list() == []


@pytest.mark.parametrize(
    "change",
    [
        {"change_result": lambda r: r["verdict"].update(proxy_economic_criterion="PASS")},
        {"change_result": lambda r: r["verdict"].update(formal_research_R1="PASS")},
        {
            "change_result": lambda r: r["cases"]["final-base5bps"]["strategy"].update(
                total_return=float("nan")
            )
        },
        {
            "change_result": lambda r: r["cases"]["final-base5bps"]["strategy"].update(
                total_return="0.2"
            )
        },
        {"change_protocol": lambda p: p["costs"].update(actual_nbbo_and_costs_verified=True)},
        {
            "change_protocol": lambda p: p["exposure_and_trials"].update(
                pristine_blind_or_prospective_test=True
            )
        },
        {
            "change_protocol": lambda p: p["exposure_and_trials"].update(
                historical_external_research_trials=0
            )
        },
    ],
)
def test_unsafe_claims_and_malformed_metrics_are_refused(tmp_path, source, change):
    mod = backend()
    snapshots, snapshot = source
    with pytest.raises(mod.FrozenExperimentInputError, match="^frozen_experiment_invalid$"):
        mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots).import_archive(
            package(snapshot, **change)
        )


def test_different_verified_snapshot_bytes_are_refused(tmp_path, source):
    mod = backend()
    snapshots, snapshot = source
    other = snapshot_package(mutate=lambda f: f.update({"data-quality.json": b'{"changed":true}'}))
    snapshots.import_archive(other)
    with pytest.raises(mod.FrozenExperimentInputError):
        mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots).import_archive(
            package(snapshot, change_manifest=lambda m: m.update(snapshot_id=sha(other)))
        )


@pytest.mark.parametrize("extras", [[("../escape", b"bad")], [("protocol.json", b"duplicate")]])
def test_exact_members_and_no_extraction(tmp_path, source, extras):
    mod = backend()
    snapshots, snapshot = source
    with pytest.raises(mod.FrozenExperimentInputError):
        mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots).import_archive(
            package(snapshot, extras=extras)
        )
    assert not (tmp_path / "escape").exists()


def test_corrupt_stored_archive_fails_cold_reopen(tmp_path, source):
    mod = backend()
    snapshots, snapshot = source
    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    report = catalog.import_archive(package(snapshot))
    index = json.loads(next((catalog.root / "experiments").glob("*.json")).read_bytes())
    from quantmesh.data.objects import ObjectRef

    catalog.objects.path_for(ObjectRef.model_validate(index["archive"])).write_bytes(b"corrupt")
    with pytest.raises(ObjectIntegrityError):
        mod.FrozenExperimentCatalog(catalog.root, snapshots).get(report["package_id"])


def test_archive_and_json_collection_bounds(tmp_path, source):
    mod = backend()
    snapshots, snapshot = source
    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    with pytest.raises(mod.FrozenExperimentTooLarge):
        catalog.import_archive(b"0" * (8 * 1024 * 1024 + 1))
    with pytest.raises(mod.FrozenExperimentInputError):
        catalog.import_archive(
            package(
                snapshot,
                change_files=lambda f: f.update({"local-timeline.json": encoded([0] * 10001)}),
            )
        )


def test_first_import_receipt_cannot_be_rewritten_in_index(tmp_path, source):
    mod = backend()
    snapshots, snapshot = source
    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    record = catalog.import_archive(package(snapshot))
    path = next((catalog.root / "experiments").glob("*.json"))
    index = json.loads(path.read_bytes())
    index["imported_at"] = "2020-01-01T00:00:00Z"
    path.write_bytes(encoded(index))
    with pytest.raises(ObjectIntegrityError):
        mod.FrozenExperimentCatalog(catalog.root, snapshots).get(record["package_id"])


@pytest.mark.parametrize("field,value", [("formal_R1_R2", "all gates PASS"), ("R3", "AUTHORIZED")])
def test_protocol_cannot_contradict_recorded_formal_verdict(tmp_path, source, field, value):
    mod = backend()
    snapshots, snapshot = source
    with pytest.raises(mod.FrozenExperimentInputError):
        mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots).import_archive(
            package(snapshot, change_protocol=lambda p: p.update(rules={field: value}))
        )


def test_expanded_archive_cap_and_symlink_member(tmp_path, source):
    import stat

    mod = backend()
    snapshots, snapshot = source
    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    with pytest.raises(mod.FrozenExperimentTooLarge):
        catalog.import_archive(
            package(
                snapshot, change_files=lambda f: f.update({"engine.py": b"0" * (32 * 1024 * 1024)})
            )
        )
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(package(snapshot))) as original,
        zipfile.ZipFile(buffer, "w") as archive,
    ):
        for info in original.infolist():
            if info.filename == "engine.py":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, original.read(info))
    with pytest.raises(mod.FrozenExperimentInputError):
        catalog.import_archive(buffer.getvalue())


@pytest.mark.parametrize(
    "change",
    [
        {
            "change_result": lambda r: r["cases"]["final-base5bps"]["strategy"].update(
                start="2020-01-02"
            )
        },
        {"change_protocol": lambda p: p["data"].update(license="all rights and PIT verified")},
    ],
)
def test_protocol_windows_and_source_claims_cannot_be_upgraded(tmp_path, source, change):
    mod = backend()
    snapshots, snapshot = source
    with pytest.raises(mod.FrozenExperimentInputError):
        mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots).import_archive(
            package(snapshot, **change)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution", "same-session raw DAILY CLOSE execution with future close signal"),
        ("comparison", "causal total-return close < trailing100-session mean; equal=>long"),
    ],
)
def test_changed_fixed_strategy_assumptions_fail_closed(tmp_path, source, field, value):
    mod = backend()
    snapshots, snapshot = source
    catalog = mod.FrozenExperimentCatalog(tmp_path / "experiments", snapshots)
    with pytest.raises(mod.FrozenExperimentInputError):
        catalog.import_archive(
            package(snapshot, change_protocol=lambda p: p["strategy"].update({field: value}))
        )
    assert catalog.list() == []
