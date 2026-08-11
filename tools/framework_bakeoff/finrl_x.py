"""Pinned, process-isolated FinRL-X NVDA research bake-off."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from quantmesh.data.lake import Lake
from quantmesh.domain.models import Venue
from quantmesh.research.frameworks import FrameworkRunEvidence

from .fixture import load_pins
from .process import CommandFailure, CommandResult, run_command

FINRL_PIN = "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1"
FINRL_VERSION = "2.0.2"
FINRL_LICENSE_SHA256 = "afae3377fdbd0537635360e91585f3c5b478ffe8eb5308f1ddcb37b76a7325d2"
CANONICAL_ARTIFACTS = ("weights.csv", "backtest.json", "proposal.json")
_DATASET = "bakeoff-moomoo-nvda"
_PINS_PATH = Path(__file__).with_name("pins.json")
_DRIVER_PATH = Path(__file__).with_name("finrl_driver.py")
_DEPENDENCIES = (
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
    "bt",
    "ffn",
    "scikit-learn",
    "requests",
    "python-dotenv",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "yfinance",
)


@dataclass(frozen=True)
class IsolatedRunMetadata:
    """Measured facts returned by either the fake or real isolated runner."""

    revision: str
    version: str
    license_sha256: str
    duration_seconds: float
    peak_rss_mb: float
    environment_bytes: int
    commands: tuple[str, ...]
    environment_artifacts: dict[str, str]
    pip_check_exit_code: int
    limitations: tuple[str, ...] = ()


FinrlRunner = Callable[..., IsolatedRunMetadata]


def _write_json(path: Path, payload: object, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = (",", ":") if indent is None else None
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=separators, indent=indent) + "\n",
        encoding="utf-8",
    )


def write_evidence(path: Path, evidence: FrameworkRunEvidence) -> None:
    """Write sorted portable evidence; local raw logs remain under work_root."""
    _write_json(path, evidence.model_dump(mode="json"), indent=2)


def _digest_named_files(root: Path, names: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for name in names:
        payload = (root / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _input_digest(input_path: Path, config_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (input_path, config_path):
        payload = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _export_input(lake_root: Path, work_root: Path) -> tuple[Path, Path]:
    bars = Lake(lake_root).dataset(_DATASET).read_bars(
        interval="1d", venue=Venue.MOOMOO, symbol="NVDA"
    )
    if len(bars) != 420:
        raise ValueError(f"expected 420 manifest-gated NVDA bars, found {len(bars)}")
    if bars != sorted(bars, key=lambda bar: bar.timestamp):
        raise ValueError("manifest-gated NVDA bars are not chronological")

    work_root.mkdir(parents=True, exist_ok=True)
    input_path = work_root / "input.csv"
    with input_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
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
        )
        for bar in bars:
            date = bar.timestamp.date().isoformat()
            writer.writerow(
                [
                    date,
                    date,
                    "NVDA",
                    format(bar.open, ".17g"),
                    format(bar.high, ".17g"),
                    format(bar.low, ".17g"),
                    format(bar.close, ".17g"),
                    format(bar.close, ".17g"),
                    format(bar.volume, ".17g"),
                    format(bar.volume, ".17g"),
                ]
            )
    config_path = work_root / "driver-config.json"
    _write_json(
        config_path,
        {
            "costs_bps": {"fee": 10, "half_spread": 5, "slippage": 2},
            "seed": 20260811,
            "splits": {
                "test": [315, 420],
                "train": [0, 252],
                "validation": [252, 315],
            },
            "symbol": "NVDA",
        },
    )
    return input_path, config_path


def _directory_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _failure_summary(work_root: Path, error: CommandFailure) -> str:
    stderr_path = work_root / error.stderr_log
    try:
        lines = [
            line.strip()
            for line in stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
    except OSError:
        return "failure details unavailable; see the retained stderr log"
    errors = [
        line
        for line in lines
        if line.lower().startswith("error:") and "subprocess-exited-with-error" not in line
    ]
    summary = errors[0] if errors else (lines[-1] if lines else "no stderr output")
    replacements = {
        str(work_root): "{work_root}",
        str(Path.home()): "{user_home}",
        str(Path(__file__).parents[2].resolve()): "{quantmesh}",
    }
    ordered_replacements = sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    )
    for local, portable in ordered_replacements:
        summary = summary.replace(local, portable).replace(local.replace("\\", "/"), portable)
    summary = re.sub(r"pip-build-env-[A-Za-z0-9_-]+", "pip-build-env-{id}", summary)
    summary = re.sub(r"temp-build-[A-Za-z0-9_-]+", "temp-build-{id}", summary)
    return summary


def _command_payload(records: list[CommandResult]) -> list[dict[str, object]]:
    return [asdict(record) for record in records]


def _real_finrl_runner(
    *,
    input_path: Path,
    config_path: Path,
    output_roots: tuple[Path, Path],
    work_root: Path,
) -> IsolatedRunMetadata:
    pin = load_pins(_PINS_PATH)["finrl-x"]
    if pin.revision != FINRL_PIN:
        raise ValueError("FinRL-X code pin does not match pins.json")
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError(
            f"Task 2 requires Python 3.13, got {sys.version_info.major}.{sys.version_info.minor}"
        )

    started = time.perf_counter()
    checkout = (work_root / "checkout").resolve()
    venv = (work_root / "venv").resolve()
    logs_root = (work_root / "logs").resolve()
    environment_root = (work_root / "environment").resolve()
    environment_root.mkdir(parents=True, exist_ok=True)
    venv_python = venv / "Scripts" / "python.exe"
    repo_root = Path(__file__).parents[2].resolve()
    placeholders = {
        Path(sys.executable): "{host_python}",
        repo_root: "{quantmesh}",
        checkout: "{work_root}/checkout",
        venv_python: "{work_root}/venv/Scripts/python.exe",
        venv: "{work_root}/venv",
        work_root: "{work_root}",
    }
    records: list[CommandResult] = []

    def execute(
        command: list[str],
        *,
        label: str,
        cwd: Path,
        timeout: float,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        try:
            result = run_command(
                command,
                cwd=cwd,
                logs_root=logs_root,
                label=label,
                placeholders=placeholders,
                timeout_seconds=timeout,
                env=env,
                check=check,
            )
        except CommandFailure as error:
            records.append(
                CommandResult(
                    command=error.command,
                    exit_code=error.exit_code,
                    duration_seconds=error.duration_seconds,
                    peak_rss_mb=error.peak_rss_mb,
                    stdout_log=error.stdout_log,
                    stderr_log=error.stderr_log,
                )
            )
            error.peak_rss_mb = max(record.peak_rss_mb for record in records)
            _write_json(environment_root / "commands.json", _command_payload(records), indent=2)
            raise
        records.append(result)
        return result

    if checkout.exists() and not (checkout / ".git").is_dir():
        raise RuntimeError("existing checkout path is not a Git worktree")
    if not checkout.exists():
        execute(
            [
                "git",
                "-c",
                "credential.helper=",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                pin.repository,
                str(checkout),
            ],
            label="01-git-clone",
            cwd=work_root,
            timeout=600,
        )
    execute(
        [
            "git",
            "-C",
            str(checkout),
            "-c",
            "credential.helper=",
            "checkout",
            "--detach",
            FINRL_PIN,
        ],
        label="02-git-checkout",
        cwd=work_root,
        timeout=300,
    )
    revision_result = execute(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        label="03-git-revision",
        cwd=work_root,
        timeout=60,
    )
    revision = (work_root / revision_result.stdout_log).read_text(encoding="utf-8").strip()
    if revision != FINRL_PIN:
        raise RuntimeError(f"checked out revision {revision!r}, expected {FINRL_PIN}")
    license_sha256 = hashlib.sha256((checkout / "LICENSE").read_bytes()).hexdigest()

    if not venv_python.exists():
        execute(
            [sys.executable, "-m", "venv", str(venv)],
            label="04-create-venv",
            cwd=work_root,
            timeout=300,
        )
    execute(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(checkout),
        ],
        label="05-install-checkout-no-deps",
        cwd=work_root,
        timeout=600,
    )
    execute(
        [str(venv_python), "-m", "pip", "install", *_DEPENDENCIES],
        label="06-install-driver-imports",
        cwd=work_root,
        timeout=1200,
    )
    version_result = execute(
        [
            str(venv_python),
            "-c",
            "import importlib.metadata as m; print(m.version('finrl-trading'))",
        ],
        label="07-upstream-version",
        cwd=checkout,
        timeout=60,
    )
    version = (work_root / version_result.stdout_log).read_text(encoding="utf-8").strip()
    if version != FINRL_VERSION:
        raise RuntimeError(f"installed upstream version {version!r}, expected {FINRL_VERSION}")

    driver_environment = {
        "MPLBACKEND": "Agg",
        "PYTHONHASHSEED": "20260811",
    }
    for index, output_root in enumerate(output_roots, start=1):
        execute(
            [
                str(venv_python),
                str(_DRIVER_PATH),
                "--input",
                str(input_path),
                "--config",
                str(config_path),
                "--output-root",
                str(output_root),
            ],
            label=f"08-driver-run-{index}",
            cwd=checkout,
            timeout=600,
            env=driver_environment,
        )

    pip_check = execute(
        [str(venv_python), "-m", "pip", "check"],
        label="09-pip-check",
        cwd=work_root,
        timeout=120,
        check=False,
    )
    pip_freeze = execute(
        [str(venv_python), "-m", "pip", "freeze", "--all"],
        label="10-pip-freeze",
        cwd=work_root,
        timeout=120,
    )
    shutil.copyfile(work_root / pip_check.stdout_log, environment_root / "pip-check.txt")
    shutil.copyfile(work_root / pip_freeze.stdout_log, environment_root / "pip-freeze.txt")
    _write_json(environment_root / "commands.json", _command_payload(records), indent=2)
    return IsolatedRunMetadata(
        revision=revision,
        version=version,
        license_sha256=license_sha256,
        duration_seconds=time.perf_counter() - started,
        peak_rss_mb=max((record.peak_rss_mb for record in records), default=0.0),
        environment_bytes=_directory_bytes(venv),
        commands=tuple(record.command for record in records),
        environment_artifacts={
            "commands": "environment/commands.json",
            "pip_check": "environment/pip-check.txt",
            "pip_freeze": "environment/pip-freeze.txt",
        },
        pip_check_exit_code=pip_check.exit_code,
        limitations=(
            "isolated research comparator; not runtime-admitted",
            "peak RSS is the maximum direct child-process working set, not a process-tree sum",
        ),
    )


def _validate_outputs(
    work_root: Path,
    config_path: Path,
    output_roots: tuple[Path, Path],
    metadata: IsolatedRunMetadata,
) -> tuple[dict[str, bool], list[str], str | None, bool]:
    checks = {
        "chronological_split": False,
        "license": metadata.license_sha256 == FINRL_LICENSE_SHA256,
        "no_leakage": False,
        "windows_install": metadata.revision == FINRL_PIN,
    }
    problems: list[str] = []
    missing = [
        f"{root.relative_to(work_root).as_posix()}/{name}"
        for root in output_roots
        for name in CANONICAL_ARTIFACTS
        if not (root / name).is_file()
    ]
    if missing:
        return checks, [f"missing canonical artifacts: {', '.join(missing)}"], None, False

    first_digest = _digest_named_files(output_roots[0], CANONICAL_ARTIFACTS)
    second_digest = _digest_named_files(output_roots[1], CANONICAL_ARTIFACTS)
    deterministic = first_digest == second_digest
    if not deterministic:
        return checks, ["canonical output digests differ"], None, False

    config = json.loads(config_path.read_text(encoding="utf-8"))
    backtest = json.loads((output_roots[0] / "backtest.json").read_text(encoding="utf-8"))
    proposal = json.loads((output_roots[0] / "proposal.json").read_text(encoding="utf-8"))
    with (output_roots[0] / "weights.csv").open(newline="", encoding="utf-8") as handle:
        weights = list(csv.DictReader(handle))

    expected_splits = {
        "train": [0, 252],
        "validation": [252, 315],
        "test": [315, 420],
    }
    evaluation = backtest.get("evaluation", {})
    fit = backtest.get("fit", {})
    checks["chronological_split"] = (
        config.get("splits") == expected_splits
        and fit.get("start_index") == 0
        and fit.get("end_index_exclusive") == 315
        and evaluation.get("start_index") == 315
        and evaluation.get("end_index_exclusive") == 420
        and len(weights) == 105
        and [row["date"] for row in weights] == sorted({row["date"] for row in weights})
    )
    checks["no_leakage"] = (
        checks["chronological_split"]
        and fit["end_index_exclusive"] <= evaluation["start_index"]
        and (
            "end_date" not in fit
            or "start_date" not in evaluation
            or fit["end_date"] < evaluation["start_date"]
        )
    )
    costs = backtest.get("costs")
    if costs != {
        "fee_bps": 10,
        "half_spread_bps": 5,
        "slippage_bps": 2,
        "transaction_cost": 0.0017,
    }:
        problems.append("backtest cost semantics are not fee+spread+slippage = 17 bps")
    if not weights or list(weights[0]) != ["date", "NVDA"]:
        problems.append("weights.csv is not the canonical date,NVDA artifact")
    else:
        last_weight = float(weights[-1]["NVDA"])
        if proposal != {
            "paper": True,
            "symbol": "NVDA",
            "target_weight": last_weight,
            "venue": "moomoo",
        }:
            problems.append("proposal is not paper-only or does not derive from the last weight")
    if not checks["chronological_split"]:
        problems.append("chronological train/validation/test split is invalid")
    if not checks["no_leakage"]:
        problems.append("fit/generation overlaps the evaluation window")
    if not checks["license"]:
        problems.append("upstream LICENSE hash does not match the pinned checkout")
    if not checks["windows_install"]:
        problems.append("isolated checkout revision does not match the Windows pin")
    return checks, problems, first_digest, deterministic


def run_finrl_x(
    lake_root: Path,
    work_root: Path,
    *,
    runner: FinrlRunner = _real_finrl_runner,
) -> FrameworkRunEvidence:
    """Export one manifest-gated fixture and evaluate the pinned engine twice."""
    lake_root = lake_root.resolve()
    work_root = work_root.resolve()
    input_path, config_path = _export_input(lake_root, work_root)
    input_digest = _input_digest(input_path, config_path)
    output_roots = (work_root / "outputs" / "run-1", work_root / "outputs" / "run-2")
    started = time.perf_counter()
    try:
        metadata = runner(
            input_path=input_path,
            config_path=config_path,
            output_roots=output_roots,
            work_root=work_root,
        )
    except CommandFailure as error:
        license_path = work_root / "checkout" / "LICENSE"
        license_ok = license_path.is_file() and (
            hashlib.sha256(license_path.read_bytes()).hexdigest() == FINRL_LICENSE_SHA256
        )
        return FrameworkRunEvidence(
            framework="finrl-x",
            revision=FINRL_PIN,
            status="failed",
            deterministic=False,
            input_digest=input_digest,
            duration_seconds=time.perf_counter() - started,
            peak_rss_mb=error.peak_rss_mb,
            environment_bytes=_directory_bytes(work_root / "venv"),
            checks={
                "chronological_split": False,
                "license": license_ok,
                "no_leakage": False,
                "windows_install": False,
            },
            artifacts={
                "commands": "environment/commands.json",
                "failure_stderr": error.stderr_log,
                "failure_stdout": error.stdout_log,
            },
            limitations=[
                f"failed command: {error.command}",
                f"exit_code={error.exit_code}",
                f"failure: {_failure_summary(work_root, error)}",
                f"stderr_log={error.stderr_log}",
            ],
        )
    except Exception as error:
        return FrameworkRunEvidence(
            framework="finrl-x",
            revision=FINRL_PIN,
            status="failed",
            deterministic=False,
            input_digest=input_digest,
            duration_seconds=time.perf_counter() - started,
            peak_rss_mb=0,
            environment_bytes=_directory_bytes(work_root / "venv"),
            checks={
                "chronological_split": False,
                "license": False,
                "no_leakage": False,
                "windows_install": False,
            },
            artifacts={"commands": "environment/commands.json"},
            limitations=[f"orchestration failure: {type(error).__name__}: {error}"],
        )

    checks, problems, output_digest, deterministic = _validate_outputs(
        work_root, config_path, output_roots, metadata
    )
    limitations = [
        *metadata.limitations,
        f"upstream_version={metadata.version}",
        f"license_sha256={metadata.license_sha256}",
        f"pip_check_exit_code={metadata.pip_check_exit_code}",
        *(f"command: {command}" for command in metadata.commands),
        *problems,
    ]
    passed = deterministic and not problems and all(checks.values())
    artifacts = {
        "backtest": "outputs/run-1/backtest.json",
        "proposal": "outputs/run-1/proposal.json",
        "weights": "outputs/run-1/weights.csv",
        **metadata.environment_artifacts,
    }
    return FrameworkRunEvidence(
        framework="finrl-x",
        revision=metadata.revision,
        status="passed" if passed else "failed",
        deterministic=deterministic,
        input_digest=input_digest,
        output_digest=output_digest if passed else None,
        duration_seconds=metadata.duration_seconds,
        peak_rss_mb=metadata.peak_rss_mb,
        environment_bytes=metadata.environment_bytes,
        checks=checks,
        artifacts=artifacts,
        limitations=limitations,
    )
