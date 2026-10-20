"""Controlled stop through real runner/store/owned cleanup with a fake Engine."""

import importlib
import signal
from datetime import UTC, datetime
from threading import Thread

import pytest
from test_research_jobs import request_for
from test_worker_execution import api, configured, linux_owner
from test_worker_execution import small_fixture as small_fixture
from test_worker_execution import small_fixture_data as small_fixture_data

from quantmesh.research import job_runner, linux_owned


def stop_token():
    return importlib.import_module("quantmesh.research.worker_stop")._WorkerStop()


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_stop_wakes_waiter_and_preserves_first_cause(signum):
    stop = stop_token()
    observed = []
    thread = Thread(target=lambda: observed.append(stop.wait(1)))
    thread.start()
    stop.request_signal(signum)
    stop.set()  # later slot failure cannot replace the signal-first cause
    thread.join(2)
    assert not thread.is_alive() and observed == [True]
    assert stop.is_set() and stop.controlled


def test_failure_first_cannot_be_upgraded_by_later_signal():
    stop = stop_token()
    assert not stop.wait(0)
    stop.set()
    stop.request_signal(signal.SIGTERM)
    assert stop.is_set() and not stop.controlled


@linux_owner
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_signal_handoff_requires_successful_owned_cleanup(
    small_fixture, monkeypatch, cleanup_fails
):
    runner, store, lake, calls, _, _, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    job = store.submit("local", "signal-handoff", request_for(lake))
    stop = stop_token()
    send = attachment.send

    def signal_after_go(value):
        send(value)
        if value.startswith("go:"):
            stop.request_signal(signal.SIGTERM)

    attachment.send = signal_after_go
    expire = store._expire_owned_lease
    handoffs = []

    def expire_after_cleanup(*args):
        assert attachment.closed and ["rm", "--force", "f" * 64] in calls
        handoffs.append(args)
        return expire(*args)

    monkeypatch.setattr(store, "_expire_owned_lease", expire_after_cleanup)
    if cleanup_fails:
        invoke = linux_owned.LinuxExecutionProfile.invoke

        def refuse_rm(self, args):
            if args[0] == "rm":
                raise linux_owned.LinuxContainmentError("owned cleanup rejected")
            return invoke(self, args)

        monkeypatch.setattr(linux_owned.LinuxExecutionProfile, "invoke", refuse_rm)

    with api()._worker_stop_scope(stop):
        if cleanup_fails:
            with pytest.raises(linux_owned.LinuxContainmentError):
                runner.run_next_job(store, "owner", lake, store.artifact_root)
        else:
            runner.run_next_job(store, "owner", lake, store.artifact_root)
    record = store.get("local", job.job_id)
    assert record.state == "running" and record.attempt == 1
    assert not record.cancel_requested and record.artifacts == []
    if cleanup_fails:
        assert handoffs == [] and record.lease_expires_at > datetime.now(UTC)
        assert store.claim("replacement", datetime.now(UTC)) is None
    else:
        assert len(handoffs) == 1 and record.lease_expires_at <= datetime.now(UTC)
        replacement = store.claim("replacement", datetime.now(UTC))
        assert replacement.job_id == job.job_id and replacement.attempt == 2


@linux_owner
@pytest.mark.parametrize("stage", ["constructor", "validation"])
def test_signal_during_attempt_exception_keeps_original_lease(small_fixture, monkeypatch, stage):
    runner, store, lake, _, _, _, attachment = configured(monkeypatch, small_fixture)
    job = store.submit("local", "signal-error", request_for(lake))
    stop = stop_token()

    def fail_with_signal(*args):
        stop.request_signal(signal.SIGINT)
        raise ValueError("synthetic internal failure")

    if stage == "constructor":
        monkeypatch.setattr(api().LinuxWorkerExecution, "start", fail_with_signal)
    else:
        monkeypatch.setattr(job_runner, "_validated_child_result", fail_with_signal)
    with api()._worker_stop_scope(stop):
        runner.run_next_job(store, "owner", lake, store.artifact_root)
    record = store.get("local", job.job_id)
    assert record.state == "running" and record.lease_expires_at > datetime.now(UTC)
    assert store.claim("replacement", datetime.now(UTC)) is None
    assert attachment.closed == (stage == "validation")


@linux_owner
def test_signal_after_observed_child_failure_keeps_original_lease(small_fixture, monkeypatch):
    runner, store, lake, _, _, _, attachment = configured(monkeypatch, small_fixture, code=1)
    job = store.submit("local", "signal-after-failure", request_for(lake))
    stop = stop_token()
    poll = linux_owned.LinuxOwnedProcess.poll

    def poll_then_signal(child):
        code = poll(child)
        assert code == 1
        stop.request_signal(signal.SIGTERM)
        return code

    monkeypatch.setattr(linux_owned.LinuxOwnedProcess, "poll", poll_then_signal)
    with api()._worker_stop_scope(stop):
        runner.run_next_job(store, "owner", lake, store.artifact_root)
    record = store.get("local", job.job_id)
    assert attachment.closed and record.lease_expires_at > datetime.now(UTC)
    assert store.claim("replacement", datetime.now(UTC)) is None


@linux_owner
def test_failure_first_stop_retains_lease_after_successful_cleanup(small_fixture, monkeypatch):
    runner, store, lake, _, _, _, attachment = configured(monkeypatch, small_fixture, running=True)
    job = store.submit("local", "failure-before-signal", request_for(lake))
    stop = stop_token()
    send = attachment.send

    def failure_before_signal(value):
        send(value)
        if value.startswith("go:"):
            stop.set()  # same operation used by daemon slot failure
            stop.request_signal(signal.SIGTERM)

    attachment.send = failure_before_signal
    with api()._worker_stop_scope(stop):
        runner.run_next_job(store, "owner", lake, store.artifact_root)
    record = store.get("local", job.job_id)
    assert attachment.closed and record.lease_expires_at > datetime.now(UTC)
    assert store.claim("replacement", datetime.now(UTC)) is None
