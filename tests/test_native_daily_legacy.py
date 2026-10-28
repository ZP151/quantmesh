"""Retired profile refusal and genuine archived synthetic bytes, with no recompute."""

import base64
from contextlib import closing
from uuid import uuid4

import pytest

from quantmesh.research import spy_replay as replay
from tests.test_spy_replay import request_for, synthetic_input
from tests.test_spy_sample_evidence import legacy_root


def test_new_legacy_submission_refuses_before_calculator_even_with_valid_input(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(replay.engine, "calculate", lambda *args: calls.append(args))
    value = synthetic_input()
    with closing(replay.ReplayService(tmp_path, replay_input=value)) as service:
        with pytest.raises(replay.ReplayError, match="input_not_qualified"):
            service.submit(request_for(value), uuid4())
        assert calls == []
        assert not (tmp_path / "jobs.jsonl").exists()
        assert not service.options().configured


def test_original_legacy_id_report_and_decision_survive_changed_engine_without_math(
    tmp_path, monkeypatch
):
    bag = legacy_root(tmp_path / "legacy")
    monkeypatch.setattr(replay.engine, "calculate", lambda *args: pytest.fail("read recomputed"))
    with closing(replay.ReplayService(tmp_path / "legacy")) as service:
        key = bag["job"]["job_id"]
        job = service.get(key)
        assert service.artifact(key) == base64.b64decode(bag["report"])
        assert service.artifact(key, "decision") == base64.b64decode(bag["decision"])
        request = replay.ReplayRequest.model_validate(bag["job"]["request"])
        assert service.submit(request, key) == (job, False)
        assert job.report.digest == bag["job"]["report"]["digest"]
