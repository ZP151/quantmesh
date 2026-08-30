from pathlib import Path

import pytest

import quantmesh.ops.source_contract as source_module
from quantmesh.ops.processes import ProcessResult
from quantmesh.ops.source_contract import verify_source_contract

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
        verify_source_contract(repo, "origin/main", DIGEST, "c" * 64, "d" * 64)

    assert not any("merge-base" in call for call in calls)


def test_unreachable_head_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    _install_git_results(monkeypatch, repo, reachable=False)

    with pytest.raises(ValueError, match="reachable"):
        verify_source_contract(repo, "origin/main", DIGEST, "c" * 64, "d" * 64)


def test_git_timeout_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path.resolve()

    def timed_out(argv, *, timeout_seconds: float, cwd: Path):
        command = tuple(str(item) for item in argv)
        return _result(command, returncode=-9, timed_out=True)

    monkeypatch.setattr(source_module, "run_process", timed_out)

    with pytest.raises(ValueError, match="timed out"):
        verify_source_contract(repo, "origin/main", DIGEST, "c" * 64, "d" * 64)


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

    verify_source_contract(
        repo,
        "origin/0021-soak-finalize",
        DIGEST,
        "c" * 64,
        "d" * 64,
        timeout_seconds=30,
    )

    assert observed_timeouts == [29.0, 28.0, 27.0, 26.0]
