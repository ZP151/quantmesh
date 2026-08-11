import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from tools.framework_bakeoff import finrl_x as finrl_module
from tools.framework_bakeoff import process as process_module
from tools.framework_bakeoff.finrl_x import (
    CANONICAL_ARTIFACTS,
    FINRL_PIN,
    IsolatedRunMetadata,
    run_finrl_x,
    write_evidence,
)
from tools.framework_bakeoff.fixture import build_nvda_fixture
from tools.framework_bakeoff.process import CommandFailure, CommandResult, run_command


def _compact_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def fake_finrl_runner(
    *,
    input_path: Path,
    config_path: Path,
    output_roots: tuple[Path, Path],
    work_root: Path,
) -> IsolatedRunMetadata:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    with input_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 420
    assert config == {
        "costs_bps": {"fee": 10, "half_spread": 5, "slippage": 2},
        "seed": 20260811,
        "splits": {
            "test": [315, 420],
            "train": [0, 252],
            "validation": [252, 315],
        },
        "symbol": "NVDA",
    }
    evaluation_rows = rows[315:420]
    backtest = {
        "costs": {
            "fee_bps": 10,
            "half_spread_bps": 5,
            "slippage_bps": 2,
            "transaction_cost": 0.0017,
        },
        "evaluation": {
            "end_date": rows[419]["date"],
            "end_index_exclusive": 420,
            "start_date": rows[315]["date"],
            "start_index": 315,
        },
        "fit": {
            "end_date": rows[314]["date"],
            "end_index_exclusive": 315,
            "start_date": rows[0]["date"],
            "start_index": 0,
        },
        "strategy": "nvda_timing",
        "upstream_result": {"total_return": 0.125},
    }
    proposal = {
        "paper": True,
        "symbol": "NVDA",
        "target_weight": 1.0,
        "venue": "moomoo",
    }
    for output_root in output_roots:
        output_root.mkdir(parents=True, exist_ok=True)
        with (output_root / "weights.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["date", "NVDA"])
            writer.writerows((row["date"], "1.0") for row in evaluation_rows)
        _compact_json(output_root / "backtest.json", backtest)
        _compact_json(output_root / "proposal.json", proposal)

    environment_root = work_root / "environment"
    environment_root.mkdir(parents=True, exist_ok=True)
    (environment_root / "pip-freeze.txt").write_text(
        "finrl-trading @ file:///{checkout}\npandas==2.3.1\n", encoding="utf-8"
    )
    (environment_root / "pip-check.txt").write_text(
        "No broken requirements found.\n", encoding="utf-8"
    )
    (environment_root / "commands.json").write_text("[]\n", encoding="utf-8")
    return IsolatedRunMetadata(
        revision=FINRL_PIN,
        version="0.1.0",
        license_sha256="afae3377fdbd0537635360e91585f3c5b478ffe8eb5308f1ddcb37b76a7325d2",
        duration_seconds=1.25,
        peak_rss_mb=32.5,
        environment_bytes=4096,
        commands=("{python} {checkout}/driver.py",),
        environment_artifacts={
            "commands": "environment/commands.json",
            "pip_check": "environment/pip-check.txt",
            "pip_freeze": "environment/pip-freeze.txt",
        },
        pip_check_exit_code=0,
        limitations=("isolated research comparator; not runtime-admitted",),
    )


def test_finrl_fake_runner_exports_canonical_paper_only_evidence(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    manifest = build_nvda_fixture(lake_root)

    result = run_finrl_x(lake_root, work_root, runner=fake_finrl_runner)

    assert result.revision == FINRL_PIN
    assert result.status == "passed"
    assert result.deterministic
    assert result.checks == {
        "chronological_split": True,
        "contract_mapping": True,
        "license": True,
        "no_leakage": True,
        "paper_only": True,
        "windows_install": True,
    }
    assert result.score_inputs == {}
    assert result.artifacts["weights"] == "outputs/run-1/weights.csv"
    assert set(result.artifacts) == {
        "backtest",
        "commands",
        "pip_check",
        "pip_freeze",
        "proposal",
        "weights",
    }
    assert manifest.dataset == "bakeoff-moomoo-nvda"

    input_path = work_root / "input.csv"
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        assert next(reader) == [
            "date",
            "datadate",
            "tic",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "cshtrd",
        ]
        assert len(list(reader)) == 420

    proposal = json.loads(
        (work_root / result.artifacts["proposal"]).read_text(encoding="utf-8")
    )
    assert proposal == {
        "venue": "moomoo",
        "symbol": "NVDA",
        "target_weight": 1.0,
        "paper": True,
    }
    for name in CANONICAL_ARTIFACTS:
        assert (work_root / "outputs" / "run-1" / name).read_bytes() == (
            work_root / "outputs" / "run-2" / name
        ).read_bytes()


def test_finrl_fake_runner_rejects_volatile_or_unsafe_canonical_outputs(
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)

    def nondeterministic_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_finrl_runner(**kwargs)  # type: ignore[arg-type]
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        proposal_path = output_roots[1] / "proposal.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal["target_weight"] = 0.0
        _compact_json(proposal_path, proposal)
        return metadata

    result = run_finrl_x(lake_root, work_root, runner=nondeterministic_runner)

    assert result.status == "failed"
    assert not result.deterministic
    assert result.output_digest is None
    assert "canonical output digests differ" in result.limitations


def test_nonzero_pip_check_forces_failed_evidence(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)

    def broken_environment_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_finrl_runner(**kwargs)  # type: ignore[arg-type]
        return replace(metadata, pip_check_exit_code=1)

    result = run_finrl_x(lake_root, work_root, runner=broken_environment_runner)

    assert result.status == "failed"
    assert result.checks["windows_install"] is False
    assert "pip check failed with exit code 1" in result.limitations


def test_stale_outputs_are_removed_and_cannot_satisfy_a_later_run(
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)
    assert run_finrl_x(lake_root, work_root, runner=fake_finrl_runner).status == "passed"

    def outputless_runner(**kwargs: object) -> IsolatedRunMetadata:
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        assert all(root.is_dir() and not any(root.iterdir()) for root in output_roots)
        return IsolatedRunMetadata(
            revision=FINRL_PIN,
            version="0.1.0",
            license_sha256=finrl_module.FINRL_LICENSE_SHA256,
            duration_seconds=0.1,
            peak_rss_mb=1.0,
            environment_bytes=0,
            commands=(),
            environment_artifacts={},
            pip_check_exit_code=0,
        )

    result = run_finrl_x(lake_root, work_root, runner=outputless_runner)

    assert result.status == "failed"
    assert "weights" not in result.artifacts
    assert any("missing canonical artifacts" in item for item in result.limitations)


def test_forged_weight_dates_and_missing_boundaries_fail_contract_mapping(
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)

    def forged_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_finrl_runner(**kwargs)  # type: ignore[arg-type]
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        for output_root in output_roots:
            weights_path = output_root / "weights.csv"
            lines = weights_path.read_text(encoding="utf-8").splitlines()
            lines[1] = "1999-01-01,1.0"
            weights_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            backtest_path = output_root / "backtest.json"
            backtest = json.loads(backtest_path.read_text(encoding="utf-8"))
            del backtest["fit"]["end_date"]
            del backtest["evaluation"]["start_date"]
            _compact_json(backtest_path, backtest)
        return metadata

    result = run_finrl_x(lake_root, work_root, runner=forged_runner)

    assert result.status == "failed"
    assert result.deterministic
    assert result.checks["chronological_split"] is False
    assert result.checks["no_leakage"] is False
    assert result.checks["contract_mapping"] is False
    assert any("weights dates do not exactly match" in item for item in result.limitations)
    assert any("boundary dates" in item for item in result.limitations)


def test_committed_evidence_is_portable_and_excludes_volatile_digest_inputs(
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work-with-uuid-8ee6e557"
    build_nvda_fixture(lake_root)
    result = run_finrl_x(lake_root, work_root, runner=fake_finrl_runner)
    evidence_path = tmp_path / "finrl-x-run.json"

    write_evidence(evidence_path, result)

    payload = evidence_path.read_text(encoding="utf-8")
    assert "C:\\Users" not in payload
    assert os.environ.get("USERNAME", "forbidden-username") not in payload
    assert "8ee6e557" not in payload
    assert "{checkout}" in payload
    assert "outputs/run-1/proposal.json" in payload


def test_failed_runner_records_a_portable_exact_failure(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)

    def failed_runner(**_kwargs: object) -> IsolatedRunMetadata:
        logs = work_root / "logs"
        logs.mkdir(parents=True)
        (logs / "install.stderr.log").write_text(
            f"building in {work_root}\\temp-build-5f16\n"
            "Building wheel for bt (pyproject.toml): finished with status 'error'\n"
            "error: compiler unavailable for pinned dependency\n",
            encoding="utf-8",
        )
        raise CommandFailure(
            CommandResult(
                command="{python} -m pip install pinned-dependency",
                exit_code=1,
                duration_seconds=2.0,
                peak_rss_mb=8.0,
                stdout_log="logs/install.stdout.log",
                stderr_log="logs/install.stderr.log",
            )
        )

    result = run_finrl_x(lake_root, work_root, runner=failed_runner)

    assert result.status == "failed"
    assert "failure: error: compiler unavailable for pinned dependency" in result.limitations
    assert "failure_stage=dependency-install" in result.limitations
    assert "failure_package=bt" in result.limitations
    assert any(item.startswith("failure_excerpt=") for item in result.limitations)
    excerpt_hash = next(
        item.removeprefix("failure_excerpt_sha256=")
        for item in result.limitations
        if item.startswith("failure_excerpt_sha256=")
    )
    assert len(excerpt_hash) == 64
    assert "peak_rss_scope=direct-child-process-only" in result.limitations
    assert str(work_root) not in result.model_dump_json()


def test_export_failure_returns_redacted_evidence_without_phantom_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work-export-uuid-7dd1"

    def failed_export(_lake: Path, _work: Path) -> tuple[Path, Path]:
        raise OSError(f"cannot export {work_root}\\temp-build-7dd1")

    monkeypatch.setattr(finrl_module, "_export_input", failed_export)
    result = run_finrl_x(lake_root, work_root, runner=fake_finrl_runner)
    payload = result.model_dump_json()

    assert result.status == "failed"
    assert result.artifacts == {}
    assert len(result.input_digest) == 64
    assert str(work_root) not in payload
    assert "7dd1" not in payload
    assert result.limitations == [
        "failure_stage=input-export",
        "failure_type=OSError",
        "failure_code=orchestration-failure",
    ]


def test_generic_runner_failure_is_redacted_and_lists_only_existing_artifacts(
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work-generic-uuid-4ac2"
    build_nvda_fixture(lake_root)

    def failed_runner(**_kwargs: object) -> IsolatedRunMetadata:
        raise RuntimeError(f"runner rejected {work_root}\\pip-build-env-4ac2")

    result = run_finrl_x(lake_root, work_root, runner=failed_runner)
    payload = result.model_dump_json()

    assert result.status == "failed"
    assert result.artifacts == {}
    assert str(work_root) not in payload
    assert "4ac2" not in payload
    assert result.limitations == [
        "failure_stage=runner-execution",
        "failure_type=RuntimeError",
        "failure_code=orchestration-failure",
    ]


@pytest.mark.parametrize(
    ("corruption", "failure_type"),
    [("malformed-json", "JSONDecodeError"), ("invalid-weight", "ValueError")],
)
def test_malformed_canonical_output_returns_portable_failed_evidence(
    tmp_path: Path,
    corruption: str,
    failure_type: str,
) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)

    def malformed_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_finrl_runner(**kwargs)  # type: ignore[arg-type]
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        for output_root in output_roots:
            if corruption == "malformed-json":
                (output_root / "backtest.json").write_text("{partial", encoding="utf-8")
            else:
                weights_path = output_root / "weights.csv"
                lines = weights_path.read_text(encoding="utf-8").splitlines()
                lines[-1] = f"{lines[-1].split(',', maxsplit=1)[0]},not-a-number"
                weights_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return metadata

    result = run_finrl_x(lake_root, work_root, runner=malformed_runner)

    assert result.status == "failed"
    assert result.deterministic is False
    assert result.output_digest is None
    assert set(result.artifacts) == {
        "backtest",
        "commands",
        "pip_check",
        "pip_freeze",
        "proposal",
        "weights",
    }
    assert result.limitations == [
        "failure_stage=output-validation",
        f"failure_type={failure_type}",
        "failure_code=orchestration-failure",
    ]


def test_generic_failure_never_persists_unrelated_absolute_path(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "work"
    build_nvda_fixture(lake_root)
    unrelated_windows_path = "C:\\Operators\\private-user\\secrets.txt"
    unrelated_posix_path = "/var/private/operator/secrets.txt"

    def path_leaking_runner(**_kwargs: object) -> IsolatedRunMetadata:
        raise OSError(f"failed at {unrelated_windows_path} and {unrelated_posix_path}")

    result = run_finrl_x(lake_root, work_root, runner=path_leaking_runner)
    payload = result.model_dump_json()

    assert result.status == "failed"
    assert result.artifacts == {}
    assert unrelated_windows_path not in payload
    assert unrelated_posix_path not in payload
    assert "private-user" not in payload
    assert result.limitations == [
        "failure_stage=runner-execution",
        "failure_type=OSError",
        "failure_code=orchestration-failure",
    ]


def test_subprocess_boundary_sanitizes_credentials_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "must-not-reach-child")
    logs_root = tmp_path / "logs"
    result = run_command(
        [
            sys.executable,
            "-c",
            "import os,sys; print('credential=' + str('ALPACA_API_KEY' in os.environ)); "
            "print('utf8=' + str(sys.flags.utf8_mode))",
        ],
        cwd=tmp_path,
        logs_root=logs_root,
        label="credential-check",
        placeholders={Path(sys.executable): "{python}", tmp_path: "{work_root}"},
        timeout_seconds=30,
    )

    assert result.exit_code == 0
    assert result.command.startswith("{python} -c")
    assert (logs_root / "credential-check.stdout.log").read_text(
        encoding="utf-8"
    ).splitlines() == ["credential=False", "utf8=1"]

    with pytest.raises(CommandFailure) as caught:
        run_command(
            [sys.executable, "-c", "import sys; print('boom'); sys.exit(7)"],
            cwd=tmp_path,
            logs_root=logs_root,
            label="expected-failure",
            placeholders={Path(sys.executable): "{python}", tmp_path: "{work_root}"},
            timeout_seconds=30,
        )
    assert caught.value.exit_code == 7
    assert caught.value.command.startswith("{python} -c")
    assert caught.value.stdout_log == "logs/expected-failure.stdout.log"
    assert (logs_root / "expected-failure.stdout.log").read_text(
        encoding="utf-8"
    ).strip() == "boom"


def test_network_subprocess_rejects_credential_bearing_proxy_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-user:proxy-secret@proxy.local:8080")

    with pytest.raises(ValueError, match="credential-bearing proxy URL"):
        run_command(
            [sys.executable, "-c", "print('must not execute')"],
            cwd=tmp_path,
            logs_root=tmp_path / "logs",
            label="proxy-credential",
            placeholders={Path(sys.executable): "{python}", tmp_path: "{work_root}"},
            timeout_seconds=30,
            inherit_proxy=True,
        )


def test_offline_driver_environment_excludes_all_proxy_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.local:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:8080")
    monkeypatch.setenv("ALL_PROXY", "socks5://proxy.local:1080")
    monkeypatch.setenv("NO_PROXY", "localhost")
    result = run_command(
        [
            sys.executable,
            "-c",
            "import os; keys=(k for k in os.environ if k.upper().endswith('_PROXY')); "
            "print(','.join(sorted(keys)))",
        ],
        cwd=tmp_path,
        logs_root=tmp_path / "logs",
        label="offline-driver-environment",
        placeholders={Path(sys.executable): "{python}", tmp_path: "{work_root}"},
        timeout_seconds=30,
    )

    assert result.exit_code == 0
    assert (tmp_path / result.stdout_log).read_text(encoding="utf-8").strip() == ""


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
def test_timeout_terminates_descendants_and_bounds_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "pids.txt"
    real_assign = process_module._assign_kill_on_close_job
    assignment_observation: dict[str, bool] = {}

    def delayed_assignment(process: subprocess.Popen[object]) -> int | None:
        time.sleep(0.5)
        assignment_observation["child_started"] = pid_path.exists()
        return real_assign(process)

    monkeypatch.setattr(process_module, "_assign_kill_on_close_job", delayed_assignment)
    child_code = "import time; time.sleep(10)"
    parent_code = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
        f"Path({str(pid_path)!r}).write_text(f'{{child.pid}}', encoding='utf-8'); "
        "time.sleep(10)"
    )
    started = time.perf_counter()

    with pytest.raises(CommandFailure) as caught:
        run_command(
            [sys.executable, "-c", parent_code],
            cwd=tmp_path,
            logs_root=tmp_path / "logs",
            label="tree-timeout",
            placeholders={Path(sys.executable): "{python}", tmp_path: "{work_root}"},
            timeout_seconds=2,
        )

    elapsed = time.perf_counter() - started
    child_pid = int(pid_path.read_text(encoding="utf-8"))
    tasklist = subprocess.run(
        ["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    descendant_survived = str(child_pid) in tasklist.stdout
    if descendant_survived:
        subprocess.run(
            ["taskkill", "/PID", str(child_pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    assert caught.value.exit_code == -1
    assert elapsed < 4
    assert assignment_observation == {"child_started": False}
    assert not descendant_survived


@pytest.mark.skipif(os.name != "nt", reason="Windows process containment contract")
@pytest.mark.parametrize("failure", ["assignment", "resume"])
def test_windows_containment_setup_failure_never_runs_or_leaks_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    marker = tmp_path / "child-ran.txt"
    captured_pid: list[int] = []
    real_assign = process_module._assign_kill_on_close_job

    def capture_assignment(process: subprocess.Popen[object]) -> int | None:
        captured_pid.append(process.pid)
        return None if failure == "assignment" else real_assign(process)

    monkeypatch.setattr(process_module, "_assign_kill_on_close_job", capture_assignment)
    if failure == "resume":
        monkeypatch.setattr(
            process_module,
            "_resume_windows_process",
            lambda _process: False,
            raising=False,
        )

    with pytest.raises(RuntimeError, match="Windows process containment setup failed"):
        run_command(
            [
                sys.executable,
                "-c",
                f"from pathlib import Path; import time; "
                f"Path({str(marker)!r}).write_text('ran'); time.sleep(10)",
            ],
            cwd=tmp_path,
            logs_root=tmp_path / "logs",
            label=f"containment-{failure}",
            placeholders={Path(sys.executable): "{python}", tmp_path: "{work_root}"},
            timeout_seconds=1,
        )

    assert len(captured_pid) == 1
    tasklist = subprocess.run(
        ["tasklist", "/FI", f"PID eq {captured_pid[0]}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert not marker.exists()
    assert str(captured_pid[0]) not in tasklist.stdout


def test_cli_builds_fixture_writes_evidence_and_uses_status_as_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.framework_bakeoff import run as cli

    lake_root = tmp_path / "cli-lake"
    work_root = tmp_path / "cli-work"
    evidence_path = tmp_path / "evidence" / "finrl-x-run.json"

    def fake_run(lake: Path, work: Path):
        return run_finrl_x(lake, work, runner=fake_finrl_runner)

    monkeypatch.setattr(cli, "run_finrl_x", fake_run)
    exit_code = cli.main(
        [
            "finrl-x",
            "--lake-root",
            str(lake_root),
            "--work-root",
            str(work_root),
            "--evidence-path",
            str(evidence_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["status"] == "passed"
    assert (lake_root / "bakeoff-moomoo-nvda" / "manifest.json").is_file()


def test_unmarked_nonempty_work_root_is_preserved_and_rejected(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "unknown-work"
    build_nvda_fixture(lake_root)
    work_root.mkdir()
    sentinel = work_root / "operator-file.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    result = run_finrl_x(lake_root, work_root, runner=fake_finrl_runner)

    assert result.status == "failed"
    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert not (work_root / "input.csv").exists()
    assert result.limitations == [
        "failure_stage=work-root-preparation",
        "failure_type=WorkRootOwnershipError",
        "failure_code=work-root-ownership",
    ]


def test_owned_work_root_recreates_checkout_venv_and_outputs(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    work_root = tmp_path / "owned-work"
    build_nvda_fixture(lake_root)
    assert run_finrl_x(lake_root, work_root, runner=fake_finrl_runner).status == "passed"
    (work_root / "checkout").mkdir()
    (work_root / "checkout" / "untracked-shadow.py").write_text("bad", encoding="utf-8")
    site_packages = work_root / "venv" / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    (site_packages / "injected.pth").write_text("bad", encoding="utf-8")

    def clean_root_runner(**kwargs: object) -> IsolatedRunMetadata:
        assert not (work_root / "checkout").exists()
        assert not (work_root / "venv").exists()
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        assert all(root.is_dir() and not any(root.iterdir()) for root in output_roots)
        return fake_finrl_runner(**kwargs)  # type: ignore[arg-type]

    result = run_finrl_x(lake_root, work_root, runner=clean_root_runner)

    assert result.status == "passed"


@pytest.mark.parametrize("linked_component", ["root", "ancestor"])
def test_work_root_link_or_reparse_component_is_rejected_without_target_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    linked_component: str,
) -> None:
    lake_root = tmp_path / "lake"
    build_nvda_fixture(lake_root)
    real_parent = tmp_path / "real-parent"
    target_root = real_parent if linked_component == "root" else real_parent / "owned"
    assert run_finrl_x(lake_root, target_root, runner=fake_finrl_runner).status == "passed"
    victim = target_root / "checkout" / "must-survive.txt"
    victim.parent.mkdir()
    victim.write_text("preserve target bytes", encoding="utf-8")

    link = tmp_path / "linked"
    link_target = target_root if linked_component == "root" else real_parent
    try:
        link.symlink_to(link_target, target_is_directory=True)
    except OSError:
        original_guard = getattr(
            finrl_module,
            "_path_is_link_or_reparse",
            lambda path: path.is_symlink(),
        )

        def simulated_reparse(path: Path) -> bool:
            return path == link or original_guard(path)

        monkeypatch.setattr(
            finrl_module,
            "_path_is_link_or_reparse",
            simulated_reparse,
            raising=False,
        )
    caller_root = link if linked_component == "root" else link / "owned"

    result = run_finrl_x(lake_root, caller_root, runner=fake_finrl_runner)

    assert result.status == "failed"
    assert victim.read_text(encoding="utf-8") == "preserve target bytes"
    assert result.limitations == [
        "failure_stage=work-root-validation",
        "failure_type=WorkRootOwnershipError",
        "failure_code=work-root-link-or-reparse",
    ]


def test_repository_root_is_rejected_as_a_sensitive_work_root(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    build_nvda_fixture(lake_root)
    repository_root = Path(finrl_module.__file__).parents[2]

    result = run_finrl_x(lake_root, repository_root, runner=fake_finrl_runner)

    assert result.status == "failed"
    assert result.limitations == [
        "failure_stage=work-root-resolution",
        "failure_type=WorkRootOwnershipError",
        "failure_code=work-root-sensitive-location",
    ]
