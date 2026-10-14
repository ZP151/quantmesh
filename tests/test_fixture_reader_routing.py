"""Routing integration checks using inert readers and child collaborators."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.data.lake import Lake
from quantmesh.domain.models import Venue
from quantmesh.research import job_runner, strategy_registry
from quantmesh.research.reports import ReportRegistry


def test_lake_routes_dataset_and_bars_before_legacy_validation(monkeypatch, tmp_path):
    from quantmesh.data import _fixture_read_scope as scope

    calls = []
    dataset = object()

    class Reader:
        def dataset(self):
            calls.append(("dataset",))
            return dataset

        def read_bars(self, **kwargs):
            calls.append(("bars", kwargs))
            return ["pinned"]

    reader = Reader()
    with scope.bind_reader(tmp_path, "fixture", reader):
        lake = Lake(tmp_path)
        monkeypatch.setattr(
            "quantmesh.data.lake.validate_dataset_name", lambda *_: pytest.fail("legacy validation")
        )
        assert lake.dataset("fixture") is dataset
        assert lake.read_bars(
            "fixture", interval="invalid", venue=Venue.MOOMOO, symbol="bad", start=None
        ) == ["pinned"]
    assert calls == [
        ("dataset",),
        (
            "bars",
            {
                "interval": "invalid",
                "venue": Venue.MOOMOO,
                "symbol": "bad",
                "start": None,
                "end": None,
            },
        ),
    ]


def test_fixture_pin_routes_live_reader_without_filesystem(monkeypatch, tmp_path):
    from quantmesh.data import _fixture_read_scope as scope

    expected = (object(), object())

    class Reader:
        def pin(self):
            return expected

    monkeypatch.setattr(
        strategy_registry, "validate_dataset_name", lambda *_: pytest.fail("legacy pin")
    )
    with scope.bind_reader(tmp_path, "fixture", Reader()):
        assert strategy_registry._fixture_pin(tmp_path, "fixture") == expected


def test_report_registry_resolve_and_record_repin_through_active_reader(tmp_path):
    from quantmesh.data import _fixture_read_scope as scope

    dataset = SimpleNamespace(manifest=SimpleNamespace(revision=3))

    class Reader:
        def dataset(self):
            return dataset

    class Store:
        def read(self):
            return []

        def check_absent(self, *_args):
            pass

        def write(self, *_args):
            pass

    registry = ReportRegistry(tmp_path / "registry", lake_root=tmp_path)
    registry._store = Store()
    report = SimpleNamespace(dataset="fixture", revision=3)
    with scope.bind_reader(tmp_path, "fixture", Reader()):
        assert registry.resolve_pin("fixture", 3) is dataset
        assert registry.record(report) is report


def test_lake_outside_job_keeps_legacy_read_path(monkeypatch, tmp_path):
    monkeypatch.setattr("quantmesh.data.lake.validate_dataset_name", lambda _: None)
    monkeypatch.setattr("quantmesh.data.lake.interval_to_timedelta", lambda _: object())
    monkeypatch.setattr("quantmesh.data.lake.validate_symbol", lambda _: None)
    monkeypatch.setattr("quantmesh.data.lake._reject_symlinks", lambda *_: None)
    monkeypatch.setattr("quantmesh.data.lake.shards_in", lambda _: [])
    assert (
        Lake(tmp_path).read_bars("fixture", interval="1d", venue=Venue.MOOMOO, symbol="AAPL") == []
    )


def test_verify_identity_is_separate_from_dataset_admission(monkeypatch):
    job = SimpleNamespace(
        request=SimpleNamespace(strategy_id="base", strategy_version="1"),
        request_digest="digest",
        implementation_digest="engine",
    )
    monkeypatch.setattr(job_runner, "canonical_request_digest", lambda _: "digest")
    monkeypatch.setattr(
        job_runner, "get_strategy", lambda *_: SimpleNamespace(implementation_digest="engine")
    )
    monkeypatch.setattr(
        job_runner, "validate_dataset", lambda *_: pytest.fail("identity read dataset")
    )
    job_runner._verify_identity(job)


def test_child_binds_same_reader_for_verification_report_record_and_outputs(monkeypatch, tmp_path):
    from quantmesh.data import _fixture_read_scope as scope

    path = tmp_path.resolve() / "attempt"
    output = path
    path.mkdir()
    events = []
    reader = object()
    request = SimpleNamespace(
        dataset=SimpleNamespace(
            dataset_id="fixture", revision=3, manifest_digest="m", export_digest="e"
        ),
        budget=SimpleNamespace(timeout_seconds=12, memory_mib=64),
        strategy_id="base",
        interval="1d",
        universe=[],
        window_spec=object(),
        costs=object(),
    )
    job = SimpleNamespace(
        request=request,
        attempt=1,
        lease_owner="owner",
        request_digest="digest",
        implementation_digest="engine",
    )
    runtime = {"build_digest": "build", "dependency_digest": "deps"}

    class Binding:
        def __enter__(self):
            events.append(("enter",))
            self.context = scope.bind_reader(path / "inputs", "fixture", reader)
            self.context.__enter__()
            return self

        def __exit__(self, *args):
            events.append(("exit",))
            return self.context.__exit__(*args)

    class FakeReader:
        def __init__(self, *args):
            events.append(("reader-init", args[1], args[2]))

        def __enter__(self):
            events.append(("reader-enter",))
            return reader

        def __exit__(self, *args):
            events.append(("reader-exit",))

    class Registry:
        def __init__(self, *args, **kwargs):
            events.append(("registry", scope.current_reader(path / "inputs", "fixture")))

        def resolve_pin(self, *_args):
            events.append(("resolve-pin", scope.current_reader(path / "inputs", "fixture")))

        def record(self, report):
            events.append(("record", scope.current_reader(path / "inputs", "fixture")))
            return report

    class Report:
        evidence = {}

        def model_dump(self, **_kwargs):
            return {"evidence": self.evidence}

    def verify(*args):
        events.append(("verify", scope.current_reader(path / "inputs", "fixture")))

    def baseline(**kwargs):
        events.append(("baseline", scope.current_reader(path / "inputs", "fixture")))
        kwargs["registry"].resolve_pin("fixture", 3)
        return kwargs["registry"].record(Report())

    monkeypatch.setattr(
        job_runner,
        "_read_child_file",
        lambda _root, file, _limit: (
            b'{"build_digest":"build","dependency_digest":"deps"}'
            if file.name == "runtime.json"
            else b"metadata"
        ),
    )
    monkeypatch.setattr(job_runner, "runtime_fingerprint", lambda **_: runtime)
    monkeypatch.setattr(job_runner.JobRecord, "model_validate_json", lambda _: job)
    monkeypatch.setattr(job_runner, "_verify_identity", lambda _: events.append(("identity",)))
    monkeypatch.setattr(job_runner, "_verify", verify)
    monkeypatch.setattr(job_runner, "FixtureReader", FakeReader, raising=False)
    monkeypatch.setattr(job_runner, "bind_reader", lambda *_: Binding(), raising=False)
    monkeypatch.setattr(job_runner, "ReportRegistry", Registry)
    monkeypatch.setattr(job_runner, "run_baseline_report", baseline)
    monkeypatch.setattr(job_runner, "canonical_result", lambda _: b"result")
    monkeypatch.setattr(
        job_runner,
        "_canonical",
        lambda _: (
            events.append(("canonical", scope.current_reader(path / "inputs", "fixture"))),
            b"receipt",
        )[1],
    )
    original_write_bytes = Path.write_bytes

    def track_write(self, data):
        if self.name in {"receipt.json", "result.json"}:
            events.append((f"write-{self.name}", scope.current_reader(path / "inputs", "fixture")))
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", track_write)
    job_runner._child_main(str(path))
    assert [event[0] for event in events] == [
        "identity",
        "reader-init",
        "reader-enter",
        "enter",
        "verify",
        "registry",
        "baseline",
        "resolve-pin",
        "record",
        "verify",
        "canonical",
        "write-receipt.json",
        "write-result.json",
        "exit",
        "reader-exit",
    ]
    assert all(
        event[1] is reader
        for event in events
        if event[0]
        in {
            "verify",
            "registry",
            "baseline",
            "resolve-pin",
            "record",
            "canonical",
            "write-receipt.json",
            "write-result.json",
        }
    )
    assert (output / "receipt.json").read_bytes() == b"receipt"
    assert (output / "result.json").read_bytes() == b"result"


def test_child_reader_scopes_clean_up_on_failure(monkeypatch, tmp_path):
    from quantmesh.data import _fixture_read_scope as scope

    path = tmp_path.resolve() / "attempt"
    path.mkdir()
    request = SimpleNamespace(
        dataset=SimpleNamespace(dataset_id="fixture"),
        budget=SimpleNamespace(timeout_seconds=1),
    )
    job = SimpleNamespace(request=request)
    reader = object()

    class FakeReader:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return reader

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        job_runner,
        "_read_child_file",
        lambda _root, file, _limit: (
            b'{"build_digest":"b","dependency_digest":"d"}'
            if file.name == "runtime.json"
            else b"metadata"
        ),
    )
    monkeypatch.setattr(
        job_runner,
        "runtime_fingerprint",
        lambda **_: {"build_digest": "b", "dependency_digest": "d"},
    )
    monkeypatch.setattr(job_runner.JobRecord, "model_validate_json", lambda _: job)
    monkeypatch.setattr(job_runner, "_verify_identity", lambda _: None)
    monkeypatch.setattr(job_runner, "FixtureReader", FakeReader, raising=False)

    @contextmanager
    def binding(root, dataset, active):
        with scope.bind_reader(root, dataset, active):
            yield

    monkeypatch.setattr(job_runner, "bind_reader", binding, raising=False)

    def fail_verify(*_args):
        raise RuntimeError("stop")

    monkeypatch.setattr(job_runner, "_verify", fail_verify)
    with pytest.raises(SystemExit):
        job_runner._child_main(str(path))
    assert scope.current_reader(path / "inputs", "fixture") is None
