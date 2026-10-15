"""Job-owned, canonical numerical publication; fixtures are not market evidence."""

import hashlib
import json
from datetime import timedelta

import pytest
from test_research_jobs import request_for

from quantmesh.research.baselines import run_baseline_report
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.reports import ReportRegistry
from tests.research_fixtures import pinned_lake


@pytest.fixture
def result(tmp_path):
    lake = tmp_path / "lake"
    pinned_lake(lake)
    store = SQLiteJobStore(tmp_path / "jobs.sqlite", lake_root=lake)
    job = store.submit("local", "fixture", request_for(lake))
    r = job.request
    report = run_baseline_report(
        dataset=r.dataset.dataset_id,
        revision=r.dataset.revision,
        strategy=r.strategy_id,
        interval=r.interval,
        universe=r.universe,
        window_spec=r.window_spec,
        costs=r.costs,
        commit=job.implementation_digest,
        registry=ReportRegistry(tmp_path / "registry", lake_root=lake),
    )
    report.evidence.update(
        manifest_digest=r.dataset.manifest_digest,
        export_digest=r.dataset.export_digest,
        request_digest=job.request_digest,
        build_digest="b" * 64,
        dependency_digest="d" * 64,
    )
    return store, job, report


def test_canonical_result_excludes_receipt_time(result):
    from quantmesh.research.job_artifacts import canonical_result

    _, _, report = result
    later = report.model_copy(update={"created_at": report.created_at + timedelta(seconds=30)})
    assert canonical_result(report) == canonical_result(later)
    assert "created_at" not in json.loads(canonical_result(report))


def test_publish_result_envelope_is_exact_job_owned_bytes(result):
    from quantmesh.research.job_artifacts import canonical_result, publish_result

    store, job, report = result
    raw = canonical_result(report)
    ref = publish_result(job, raw, store.artifact_root)
    data = (store.artifact_root / ref.object_key).read_bytes()
    assert ref.sha256 == ref.artifact_id == hashlib.sha256(data).hexdigest()
    assert ref.byte_size == len(data)
    assert ref.object_key == f"{job.job_id}/{ref.sha256}.json"
    envelope = json.loads(data)
    assert envelope == dict(
        schema_version=1,
        request_digest=job.request_digest,
        implementation_digest=job.implementation_digest,
        result=json.loads(raw),
    )
    assert publish_result(job, raw, store.artifact_root) == ref
    (store.artifact_root / ref.object_key).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        publish_result(job, raw, store.artifact_root)


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "nan",
        "strategy",
        "input",
        "runtime",
        "costs",
        "null_metric",
        "cost_result",
        "aggregate",
        "signals",
        "negative_cost",
        "win_rate",
    ],
)
def test_publication_rejects_invalid_numerical_or_lineage_content(result, fault):
    from quantmesh.research.job_artifacts import canonical_result, publish_result

    store, job, report = result
    data = json.loads(canonical_result(report))
    if fault == "empty":
        data["windows"] = []
    elif fault == "nan":
        data["metrics"]["total_return"] = float("nan")
    elif fault == "strategy":
        data["strategy"] = "mean_reversion"
    elif fault == "input":
        data["evidence"]["export_digest"] = "a" * 64
    elif fault == "runtime":
        del data["evidence"]["build_digest"]
    elif fault == "costs":
        data["costs"]["fee_bps"] = 0
    elif fault == "null_metric":
        data["metrics"]["total_return"] = None
    elif fault == "cost_result":
        data["windows"][0]["cost"] = 0.0
    elif fault == "aggregate":
        data["metrics"]["total_cost"] = 99
    elif fault == "negative_cost":
        data["metrics"]["total_cost"] = -1.0
    elif fault == "win_rate":
        data["metrics"]["win_rate"] = 2.0
    else:
        from quantmesh.research.reports import report_id

        data["signals_digest"] = "a" * 16
        data["id"] = report_id(
            dataset=report.dataset,
            revision=report.revision,
            commit=report.commit,
            strategy=report.strategy,
            interval=report.interval,
            universe=report.universe,
            window_spec=report.window_spec,
            costs=report.costs,
            signals_digest="a" * 16,
        )
    with pytest.raises(ValueError):
        publish_result(
            job,
            json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
            store.artifact_root,
        )
    assert not list(store.artifact_root.glob("*/*.json"))


def test_job_id_traversal_rejects_before_write(result, tmp_path):
    from quantmesh.research.job_artifacts import canonical_result, publish_result

    store, job, report = result
    with pytest.raises(ValueError):
        publish_result(
            job.model_copy(update={"job_id": "../escape"}),
            canonical_result(report),
            store.artifact_root,
        )
    assert not (tmp_path / "escape").exists()
