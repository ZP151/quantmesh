from pathlib import Path
from types import SimpleNamespace

import pytest

import quantmesh.ops.source_contract as source_module
from quantmesh.ops.processes import ProcessResult
from quantmesh.ops.source_contract import (
    PLATFORM_TOLERATED,
    RuntimeDigestsV1,
    ScheduleContractV1,
    compute_runtime_digests,
    load_schedule_manifest,
    publish_schedule_manifest,
    verify_source_contract,
)

COMMIT = "a" * 40
DIGEST = "b" * 64


def _result(
    argv: tuple[str, ...],
    *,
    returncode: int = 0,
    stdout: str = "",
    timed_out: bool = False,
) -> ProcessResult:
    return ProcessResult(
        argv=argv,
        returncode=returncode,
        stdout=stdout,
        stderr="",
        elapsed_seconds=0.1,
        timed_out=timed_out,
        tree_terminated=timed_out,
    )


def _install_git_results(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    *,
    dirty: bool = False,
    reachable: bool = True,
) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def run(argv, *, timeout_seconds: float, cwd: Path):
        assert timeout_seconds > 0
        assert cwd == repo
        command = tuple(str(item) for item in argv)
        calls.append(command)
        if "--show-toplevel" in command:
            return _result(command, stdout=str(repo.resolve()) + "\n")
        if command[-2:] == ("rev-parse", "HEAD"):
            return _result(command, stdout=COMMIT + "\n")
        if "status" in command:
            return _result(command, stdout=" M source.py\n" if dirty else "")
        return _result(command, returncode=0 if reachable else 1)

    monkeypatch.setattr(source_module, "run_process", run)
    monkeypatch.setattr(
        source_module,
        "compute_runtime_digests",
        lambda *args, **kwargs: RuntimeDigestsV1(
            dependency_digest=DIGEST,
            script_digest="c" * 64,
            config_digest="d" * 64,
        ),
    )
    return calls


def test_source_contract_requires_clean_remotely_reachable_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    calls = _install_git_results(monkeypatch, repo)

    contract = verify_source_contract(
        repo,
        "origin/0021-soak-finalize",
        DIGEST,
        "c" * 64,
        "d" * 64,
        runtime_config={},
    )

    assert contract.head_commit == COMMIT
    assert contract.clean is True
    assert contract.reachable is True
    assert calls[-1][-4:] == (
        "merge-base",
        "--is-ancestor",
        "HEAD",
        "origin/0021-soak-finalize",
    )


def test_dirty_checkout_stops_before_reachability_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    calls = _install_git_results(monkeypatch, repo, dirty=True)

    with pytest.raises(ValueError, match="clean"):
        verify_source_contract(
            repo,
            "origin/main",
            DIGEST,
            "c" * 64,
            "d" * 64,
            runtime_config={},
        )

    assert not any("merge-base" in call for call in calls)


def test_unreachable_head_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    _install_git_results(monkeypatch, repo, reachable=False)

    with pytest.raises(ValueError, match="reachable"):
        verify_source_contract(
            repo,
            "origin/main",
            DIGEST,
            "c" * 64,
            "d" * 64,
            runtime_config={},
        )


def test_git_timeout_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path.resolve()

    def timed_out(argv, *, timeout_seconds: float, cwd: Path):
        command = tuple(str(item) for item in argv)
        return _result(command, returncode=-9, timed_out=True)

    monkeypatch.setattr(source_module, "run_process", timed_out)
    monkeypatch.setattr(
        source_module,
        "compute_runtime_digests",
        lambda *args, **kwargs: RuntimeDigestsV1(
            dependency_digest=DIGEST,
            script_digest="c" * 64,
            config_digest="d" * 64,
        ),
    )

    with pytest.raises(ValueError, match="timed out"):
        verify_source_contract(
            repo,
            "origin/main",
            DIGEST,
            "c" * 64,
            "d" * 64,
            runtime_config={},
        )


def test_git_steps_share_one_monotonic_stage_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path.resolve()
    observed_timeouts: list[float] = []

    def run(argv, *, timeout_seconds: float, cwd: Path):
        assert cwd == repo
        observed_timeouts.append(timeout_seconds)
        command = tuple(str(item) for item in argv)
        if "--show-toplevel" in command:
            return _result(command, stdout=str(repo) + "\n")
        if command[-2:] == ("rev-parse", "HEAD"):
            return _result(command, stdout=COMMIT + "\n")
        return _result(command)

    monotonic = iter((10.0, 11.0, 12.0, 13.0, 14.0))
    monkeypatch.setattr(source_module, "run_process", run)
    monkeypatch.setattr(source_module.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(
        source_module,
        "compute_runtime_digests",
        lambda *args, **kwargs: RuntimeDigestsV1(
            dependency_digest=DIGEST,
            script_digest="c" * 64,
            config_digest="d" * 64,
        ),
    )

    verify_source_contract(
        repo,
        "origin/0021-soak-finalize",
        DIGEST,
        "c" * 64,
        "d" * 64,
        runtime_config={},
        timeout_seconds=30,
    )

    assert observed_timeouts == [29.0, 28.0, 27.0, 26.0]


def _runtime_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    files = {
        "pyproject.toml": b"[project]\nname='quantmesh'\n",
        "requirements-audit.txt": b"required==1.0\nuvloop==0.22.1\n",
        "requirements-build.txt": b"pip==26.2.1\nsetuptools==84.0.0\nwheel==0.48.0\n",
        "tools/soak_daily.py": b"daily\n",
        "tools/trusted_data_soak_acceptance.py": b"acceptance-entrypoint\n",
        "tools/connection_witness.py": b"connection-python\n",
        "tools/connection_witness.ps1": b"connection-powershell\n",
        "tools/soak_witness_outbox.py": b"outbox-entrypoint\n",
        "src/quantmesh/ops/connection_witness.py": b"connection-module\n",
        "src/quantmesh/ops/soak_acceptance.py": b"acceptance-module\n",
        "src/quantmesh/ops/soak_runner.py": b"daily-module\n",
        "src/quantmesh/ops/source_contract.py": b"source-module\n",
        "src/quantmesh/ops/witness_outbox.py": b"outbox-module\n",
    }
    for relative, payload in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    python = tmp_path / "python.exe"
    python.write_bytes(b"pinned-python")
    return repo, python


def _distributions(*, include_required: bool = True, extra_version: str = "2.0"):
    values = [
        SimpleNamespace(metadata={"Name": "quantmesh"}, version="0.1.1rc1"),
        SimpleNamespace(metadata={"Name": "extra"}, version=extra_version),
    ]
    if include_required:
        values.append(SimpleNamespace(metadata={"Name": "required"}, version="1.0"))
    return tuple(values)


def test_runtime_digests_cover_files_python_inventory_and_normalized_config(
    tmp_path: Path,
) -> None:
    repo, python = _runtime_repo(tmp_path)
    values = dict(
        repo=repo,
        runtime_config={"root": repo / "data", "config_digest": "ignored"},
        python_executable=python,
        python_implementation="CPython",
        python_version="3.14.0",
        distributions=_distributions(),
    )

    baseline = compute_runtime_digests(**values)
    assert baseline == compute_runtime_digests(**values)
    reordered = tuple(reversed(_distributions()))
    assert compute_runtime_digests(**{**values, "distributions": reordered}) == baseline

    (repo / "tools/soak_daily.py").write_bytes(b"changed\n")
    script_changed = compute_runtime_digests(**values)
    assert script_changed.script_digest != baseline.script_digest
    assert script_changed.dependency_digest == baseline.dependency_digest

    config_changed = compute_runtime_digests(
        **{**values, "runtime_config": {"root": repo / "other"}}
    )
    assert config_changed.config_digest != baseline.config_digest

    inventory_changed = compute_runtime_digests(
        **{**values, "distributions": _distributions(extra_version="2.1")}
    )
    assert inventory_changed.dependency_digest != baseline.dependency_digest

    python.write_bytes(b"changed-python")
    assert compute_runtime_digests(**values).dependency_digest != baseline.dependency_digest


def test_runtime_digest_requires_every_non_tolerated_pin(tmp_path: Path) -> None:
    repo, python = _runtime_repo(tmp_path)
    assert "uvloop" in PLATFORM_TOLERATED

    with pytest.raises(ValueError, match="required==1.0"):
        compute_runtime_digests(
            repo,
            {},
            python_executable=python,
            distributions=_distributions(include_required=False),
        )

    with pytest.raises(ValueError, match="uvloop==0.22.1 version drift"):
        compute_runtime_digests(
            repo,
            {},
            python_executable=python,
            distributions=(
                *_distributions(),
                SimpleNamespace(metadata={"Name": "UVLOOP"}, version="0.21.0"),
            ),
        )


def test_runtime_digest_rejects_missing_fixed_operational_script(tmp_path: Path) -> None:
    repo, python = _runtime_repo(tmp_path)
    (repo / "tools/connection_witness.ps1").unlink()

    with pytest.raises(ValueError, match="connection_witness.ps1"):
        compute_runtime_digests(
            repo,
            {},
            python_executable=python,
            distributions=_distributions(),
        )


def test_verify_source_contract_rejects_supplied_digest_drift_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    monkeypatch.setattr(
        source_module,
        "compute_runtime_digests",
        lambda *args, **kwargs: RuntimeDigestsV1(
            dependency_digest="e" * 64,
            script_digest="c" * 64,
            config_digest="d" * 64,
        ),
    )
    monkeypatch.setattr(
        source_module,
        "run_process",
        lambda *args, **kwargs: pytest.fail("Git started after runtime digest drift"),
    )

    with pytest.raises(ValueError, match="dependency digest drift"):
        verify_source_contract(
            repo,
            "origin/main",
            DIGEST,
            "c" * 64,
            "d" * 64,
            runtime_config={},
        )


def test_schedule_manifest_is_named_by_recomputed_config_digest_and_create_once(
    tmp_path: Path,
) -> None:
    config = {
        "runner": {"repo": tmp_path / "repo", "config_digest": "ignored"},
        "scheduler": {"daily": {"at": "08:00"}},
    }

    path = publish_schedule_manifest(tmp_path / "manifests", config)
    manifest = load_schedule_manifest(path)

    assert path.name == f"{manifest.config_digest}.json"
    assert manifest == ScheduleContractV1.build(config)
    assert publish_schedule_manifest(tmp_path / "manifests", config) == path

    forged = path.with_name(f"{'f' * 64}.json")
    forged.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="filename"):
        load_schedule_manifest(forged)
