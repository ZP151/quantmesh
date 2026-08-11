import csv
import json
import os
import sys
from pathlib import Path

import pytest

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
        "evaluation": {"end_index_exclusive": 420, "start_index": 315},
        "fit": {"end_index_exclusive": 315, "start_index": 0},
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
        "license": True,
        "no_leakage": True,
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
    assert str(work_root) not in result.model_dump_json()


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
