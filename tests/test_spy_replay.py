"""Synthetic engineering inputs only; never replay retained market observations."""

import pandas as pd
import pytest

from quantmesh.research import spy_replay_engine as engine
from tests.native_daily_legacy_fixtures import seed_archive


def frame():
    dates = pd.bdate_range("2026-01-01", periods=121).strftime("%Y-%m-%d").tolist()
    prices = [100.0] * 100 + [101.0 + i for i in range(21)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000000.0] * 121,
            "dividend": [0.0] * 121,
        },
        index=dates,
    )


def test_actual_math_has_costs_same_cost_benchmarks_and_terminal_cash():
    bars = frame()
    result = engine.calculate(bars, [], bars.index[100], bars.index[-1])
    base = result["scenarios"]["base5"]["strategy"]
    assert len(base["daily"]) == 21
    # Hand-derived: buy979 @102,fee49.929; sell979 @121,fee59.2295.
    assert base["metrics"]["terminal_equity"] == pytest.approx(118491.8415)
    assert base["metrics"]["friction_usd"] == pytest.approx(109.1585)
    assert base["metrics"]["terminal_shares"] == 0
    assert result["cash_benchmark"]["terminal_equity"] == 100000
    assert result["scenarios"]["base5"]["buyhold"]["trades"][0]["price"] == 101
    assert result["scenarios"]["stress10"]["strategy"]["metrics"]["friction_usd"] > 109.1585


def test_pay_date_cash_is_not_ex_date_cash():
    bars = frame()
    ex, pay = bars.index[103], bars.index[105]
    daily, _ = engine.run_cashbook(
        bars,
        engine.prepare_signals(bars),
        [{"ex_date": ex, "pay_date": pay, "amount": 1.0}],
        bars.index[100],
        bars.index[-1],
    )
    assert daily.loc[ex].receivable == 979
    assert daily.loc[ex].dividend_paid == 0
    assert daily.loc[pay].receivable == 0
    assert daily.loc[pay].dividend_paid == 979


def test_future_price_change_cannot_change_first_trade():
    bars = frame()
    original = engine.calculate(bars, [], bars.index[100], bars.index[-1])
    changed = bars.copy()
    changed.loc[changed.index[-1], ["open", "high", "low", "close"]] = 80
    altered = engine.calculate(changed, [], bars.index[100], bars.index[-1])
    assert (
        original["scenarios"]["base5"]["strategy"]["trades"][0]
        == altered["scenarios"]["base5"]["strategy"]["trades"][0]
    )


@pytest.mark.parametrize("terminal_volume", [0, 1000])
def test_incomplete_terminal_liquidation_cannot_produce_calculation(terminal_volume):
    bars = frame()
    bars.loc[bars.index[102] :, "volume"] = terminal_volume
    with pytest.raises(ArithmeticError, match="terminal liquidation incomplete"):
        engine.calculate(bars, [], bars.index[100], bars.index[-1])


def synthetic_input():
    """Trusted Python-only fixture; no public DTO can construct/admit this."""
    import csv
    import io
    from datetime import UTC, datetime

    from quantmesh.research.spy_replay import ReplayInput, canonical, digest
    from tools.research import freeze_opend_spy_daily as freezer

    window = freezer.plan_window(datetime(2026, 10, 21, 16, tzinfo=UTC))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["date", "open", "high", "low", "close", "volume", "dividend"])
    for i, day in enumerate(window["sessions"]):
        price = 100 if i < 100 else 101 + i - 100
        writer.writerow([day, price, price, price, price, 1000000, 0])
    bars = stream.getvalue().encode()
    distributions = b"[]"
    from quantmesh.data.objects import ObjectRef

    protocol = freezer._protocol_v2(window)
    protocol["members"] = {
        "normalized-bars.csv": ObjectRef(
            digest=digest(bars), byte_length=len(bars), media_type="text/csv"
        ).model_dump(),
        "normalized-distributions.json": ObjectRef(
            digest=digest(distributions), byte_length=2, media_type="application/json"
        ).model_dump(),
    }
    raw = canonical(protocol)
    return ReplayInput(
        snapshot_digest=digest(b"INTERNAL SYNTHETIC121" + bars + raw),
        protocol_bytes=raw,
        bars_csv=bars,
        distributions_json=distributions,
        frozen_at_utc=datetime(2026, 10, 21, 17, tzinfo=UTC),
        evidence_kind="engineering_fixture",
    )


def request_for(value):
    from quantmesh.research.spy_replay import ReplayRequest, digest

    return ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=digest(value.protocol_bytes)
    )


def test_real_store_report_decision_same_key_and_cold_reopen_do_not_recompute(
    tmp_path, monkeypatch
):
    import json
    from uuid import uuid4

    from quantmesh.research.spy_replay import DecisionRequest, ReplayError, ReplayService

    original, calls = engine.calculate, []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(engine, "calculate", counted)
    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    key, decision_key = uuid4(), uuid4()
    request = request_for(value)
    job = seed_archive(service, value, key)
    assert job.state == "succeeded" and calls == []
    raw = service.artifact(key)
    assert json.loads(raw)["calculation"]["scenarios"]["base5"]["strategy"]["metrics"][
        "terminal_equity"
    ] == pytest.approx(118491.8415)
    body = DecisionRequest(
        request_digest=job.request_digest,
        report_digest=job.report.digest,
        disposition="reject",
        reason="Development evidence only",
    )
    decided, created = service.decide(key, body, decision_key)
    assert created and decided.decision.snapshot_digest == request.snapshot_digest
    decision_bytes = service.artifact(key, "decision")
    assert service.submit(request, key)[0] == decided
    assert not service.decide(key, body, decision_key)[1]
    with pytest.raises(ReplayError, match="decision_conflict"):
        service.decide(key, body.model_copy(update={"disposition": "watch"}), decision_key)
    service.close()
    reopened = ReplayService(tmp_path)
    assert reopened.get(key) == decided
    assert reopened.artifact(key) == raw
    assert reopened.artifact(key, "decision") == decision_bytes
    assert reopened.submit(request, key)[0] == decided
    assert calls == []
    reopened.close()


def test_archived_read_concurrent_idempotency_and_retired_new_submit(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    value, key = synthetic_input(), uuid4()
    monkeypatch.setattr(engine, "calculate", lambda *a: pytest.fail("retired computation"))
    service = ReplayService(tmp_path, replay_input=value)
    original = seed_archive(service, value, key)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: service.submit(request_for(value), key), range(2)))
    assert results == [(original, False), (original, False)]
    with pytest.raises(ReplayError, match="input_not_qualified"):
        service.submit(request_for(value), uuid4())
    service.close()
    assert service._closed


def test_interrupted_intent_is_recovered_without_running_math_again(tmp_path, monkeypatch):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayService

    value, key = synthetic_input(), uuid4()
    monkeypatch.setattr(engine, "calculate", lambda *a: pytest.fail("interrupted recompute"))
    service = ReplayService(tmp_path, replay_input=value)
    seed_archive(service, value, key, state="running")
    service.close()
    reopened = ReplayService(tmp_path, replay_input=value)
    assert reopened.get(key).state == "interrupted"
    assert reopened.submit(request_for(value), key)[0].state == "interrupted"
    reopened.close()


def test_missing_input_and_public_fixture_claim_cannot_compute(tmp_path):
    from uuid import uuid4

    from pydantic import ValidationError

    from quantmesh.research.spy_replay import ReplayError, ReplayRequest, ReplayService

    value = synthetic_input()
    service = ReplayService(tmp_path)
    with pytest.raises(ReplayError, match="input_not_qualified"):
        service.submit(request_for(value), uuid4())
    with pytest.raises(ValidationError):
        ReplayRequest(**request_for(value).model_dump(), fixture=True)
    assert not (tmp_path / "jobs.jsonl").exists()
    service.close()


def test_report_object_without_record_publication_is_not_success_or_rerun(tmp_path, monkeypatch):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    value, key = synthetic_input(), uuid4()
    service = ReplayService(tmp_path, replay_input=value)
    orphan = service.objects.put_bytes(
        "application/json", b'{"unpublished_engineering_fixture":true}'
    )
    monkeypatch.setattr(engine, "calculate", lambda *a: pytest.fail("orphan rerun"))
    with pytest.raises(ReplayError, match="not_found"):
        service.get(key)
    with pytest.raises(ReplayError, match="input_not_qualified"):
        service.submit(request_for(value), key)
    assert service.objects.get_bytes(orphan) == b'{"unpublished_engineering_fixture":true}'
    assert not (tmp_path / "jobs.jsonl").exists()
    service.close()


def test_decision_response_loss_replays_original_without_second_write(tmp_path, monkeypatch):
    from uuid import uuid4

    from quantmesh.research.spy_replay import DecisionRequest, ReplayService

    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    key, decision_key = uuid4(), uuid4()
    job = seed_archive(service, value, key)
    body = DecisionRequest(
        request_digest=job.request_digest,
        report_digest=job.report.digest,
        disposition="reject",
        reason="Insufficient independent evidence",
    )
    service.decide(key, body, decision_key)  # Deliberately discard the returned response.
    original = service.artifact(key, "decision")

    def forbidden_write(records):
        pytest.fail("same decision retry attempted another publication")

    monkeypatch.setattr(service._store, "write", forbidden_write)
    assert not service.decide(key, body, decision_key)[1]
    assert service.artifact(key, "decision") == original
    service.close()


def test_corrupt_ledger_is_classified_as_artifact_failure(tmp_path):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    service = ReplayService(tmp_path)
    (tmp_path / "jobs.jsonl").write_bytes(b"not-json\n")
    with pytest.raises(ReplayError, match="artifact_invalid"):
        service.get(uuid4())
    service.close()


def test_actual_object_tamper_is_not_returned_as_original_report(tmp_path):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    key = uuid4()
    job = seed_archive(service, value, key)
    service.objects.path_for(job.report).write_bytes(b"{}")
    with pytest.raises(ReplayError, match="artifact_invalid"):
        service.artifact(key)
    service.close()


def test_writer_lease_refuses_second_writer_and_releases_on_close(tmp_path):
    from quantmesh.research.spy_replay import ReplayService

    first = ReplayService(tmp_path)
    with pytest.raises(ValueError):
        ReplayService(tmp_path)
    first.close()
    second = ReplayService(tmp_path)
    second.close()


def test_fixed_32_job_bound_blocks_33rd_before_computation(tmp_path):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    for _ in range(32):
        seed_archive(service, value, uuid4())
    with pytest.raises(ReplayError, match="input_not_qualified"):
        service.submit(request_for(value), uuid4())
    jobs = service._store.read()
    extra = jobs[0].model_copy(update={"job_id": str(uuid4())})
    service._store.write([*jobs, extra])
    with pytest.raises(ReplayError, match="artifact_invalid"):
        service.get(jobs[0].job_id)
    service.close()


def descriptor_fixture(tmp_path):
    """Reuse existing synthetic wire generators, not their tests or market data.

    The external acceptance here is a controlled test double at the operator
    config boundary. It cannot establish actual OpenD input qualification.
    """
    from datetime import timedelta

    from quantmesh.data.objects import ObjectStore
    from quantmesh.research.spy_replay import canonical
    from tests.test_freeze_opend_spy_daily import AS_OF, freeze_evidence, v2raw
    from tools.research import freeze_opend_spy_daily as freezer

    source = tmp_path / "source"
    raw = v2raw()
    frozen = freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), source, frozen_at=AS_OF + timedelta(minutes=3)
    )
    approval = dict(
        status="accepted_for_historical_development_replay",
        scope="US.SPY/1d/private_research",
        snapshot_digest=frozen["freeze_digest"],
        protocol_digest=frozen["protocol_ref"]["digest"],
        use_document_sha256="a" * 64,
        independent_input_review_sha256="f" * 64,
        reviewed_at_utc=(AS_OF + timedelta(minutes=4)).isoformat(),
    )
    ref = ObjectStore(source).put_bytes("application/json", canonical(approval))
    descriptor = dict(
        freeze_root=str(source), freeze_digest=frozen["freeze_digest"], acceptance=ref.model_dump()
    )
    path = tmp_path / "input.json"
    path.write_bytes(canonical(descriptor))
    return path, descriptor, approval


def test_operator_descriptor_validates_frozen_bytes_and_external_review_binding(tmp_path):
    from quantmesh.research.spy_replay import ReplayError, ReplayInput, ReplayService, canonical

    path, descriptor, _ = descriptor_fixture(tmp_path)
    value = ReplayInput.from_descriptor(path)
    assert len(value.verified()[1]) == 121
    assert value.source_root == tmp_path / "source"
    with pytest.raises(ReplayError, match="input_not_qualified"):
        ReplayService(tmp_path / "source" / "new", replay_input=value)
    # A freeze explicitly requires actual external input review; not enough by itself.
    path.write_bytes(canonical({k: v for k, v in descriptor.items() if k != "acceptance"}))
    with pytest.raises(ReplayError, match="input_not_qualified"):
        ReplayInput.from_descriptor(path)


@pytest.mark.parametrize(
    "change",
    [
        dict(snapshot_digest="1" * 64),
        dict(protocol_digest="2" * 64),
        dict(use_document_sha256="3" * 64),
        dict(independent_input_review_sha256="0" * 64),
        dict(reviewed_at_utc="2026-01-01T00:00:00+00:00"),
    ],
)
def test_static_admission_cannot_use_foreign_stale_or_placeholder_review(tmp_path, change):
    from quantmesh.data.objects import ObjectStore
    from quantmesh.research.spy_replay import ReplayError, ReplayInput, canonical

    path, descriptor, approval = descriptor_fixture(tmp_path)
    ref = ObjectStore(tmp_path / "source").put_bytes(
        "application/json", canonical({**approval, **change})
    )
    path.write_bytes(canonical({**descriptor, "acceptance": ref.model_dump()}))
    with pytest.raises(ReplayError, match="input_not_qualified"):
        ReplayInput.from_descriptor(path)


def test_failed_math_has_no_report_and_keeps_fixed_safe_error(tmp_path, monkeypatch):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    value, key = synthetic_input(), uuid4()
    service = ReplayService(tmp_path, replay_input=value)
    monkeypatch.setattr(engine, "calculate", lambda *a: pytest.fail("retired computation"))
    job = seed_archive(service, value, key, state="failed")
    assert service.submit(request_for(value), key)[0] == job
    assert job.report is None and job.error_code == "computation_failed"
    with pytest.raises(ReplayError, match="not_found"):
        service.artifact(key)
    service.close()


def test_archived_terminal_failure_cannot_publish_or_rerun(tmp_path):
    from uuid import uuid4

    from quantmesh.research.spy_replay import ReplayError, ReplayService

    # New kernel tests exercise actual terminal refusal. Here an archived failed job
    # must never acquire a report or another numerical attempt after retirement.
    value, key = synthetic_input(), uuid4()
    service = ReplayService(tmp_path, replay_input=value)
    job = seed_archive(service, value, key, state="failed")
    assert job.report is None and job.error_code == "computation_failed"
    with pytest.raises(ReplayError, match="not_found"):
        service.artifact(key)
    service.close()
    reopened = ReplayService(tmp_path, replay_input=value)
    assert reopened.get(key) == job
    assert reopened.submit(request_for(value), key)[0] == job
    reopened.close()


def test_separate_python_process_recovers_same_job_report_and_decision(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    from uuid import uuid4

    from quantmesh.research.spy_replay import DecisionRequest, ReplayService, digest

    value = synthetic_input()
    service = ReplayService(tmp_path, replay_input=value)
    key = uuid4()
    job = seed_archive(service, value, key)
    service.decide(
        key,
        DecisionRequest(
            request_digest=job.request_digest,
            report_digest=job.report.digest,
            disposition="reject",
            reason="Development only",
        ),
        uuid4(),
    )
    expected_report = digest(service.artifact(key))
    expected_decision = digest(service.artifact(key, "decision"))
    service.close()
    code = """
import json,sys
from pathlib import Path
from quantmesh.research.spy_replay import ReplayService,digest
service=ReplayService(Path(sys.argv[1]))
job=service.get(sys.argv[2])
print(json.dumps(dict(job_id=job.job_id,state=job.state,
report=digest(service.artifact(job.job_id)),decision=digest(service.artifact(job.job_id,'decision')))))
service.close()
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), str(key)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    actual = json.loads(result.stdout)
    assert actual == dict(
        job_id=str(key), state="succeeded", report=expected_report, decision=expected_decision
    )
