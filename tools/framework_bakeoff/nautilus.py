"""Pinned, process-isolated NautilusTrader Hyperliquid bake-off."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.hyperliquid.wire import parse_candle
from quantmesh.research.frameworks import FrameworkRunEvidence

from .finrl_x import (
    _directory_bytes,
    _existing_artifacts,
    _lexical_work_root,
    _path_is_link_or_reparse,
    _portable_text,
    _resolve_safe_work_root,
    _safe_directory_bytes,
    _validate_work_root_lexeme,
)
from .fixture import load_pins
from .process import (
    CommandFailure,
    CommandResult,
    OwnedWorkRootPolicy,
    WorkRootOwnershipError,
    prepare_owned_work_root,
    run_command,
)

NAUTILUS_PIN = "27a8e54e7ac3c57d6cbf8891f0283dfbaee97317"
NAUTILUS_VERSION = "1.231.0"
NAUTILUS_PANDAS_VERSION = "2.3.3"
NAUTILUS_LICENSE_SHA256 = (
    "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c"
)
CANONICAL_ARTIFACTS = ("events.jsonl", "fills.json", "account.json")
_PINS_PATH = Path(__file__).with_name("pins.json")
_DRIVER_PATH = Path(__file__).with_name("nautilus_driver.py")
_SOURCE_FIXTURE = "src/quantmesh/hyperliquid/fixtures/wire_candles.json"
_UNAVAILABLE_INPUT_DIGEST = hashlib.sha256(
    b"nautilus-trader-input-unavailable"
).hexdigest()
_WORK_POLICY = OwnedWorkRootPolicy(
    marker_name=".quantmesh-nautilus-work-root.json",
    marker_payload={
        "owner": "quantmesh-framework-bakeoff",
        "schema_version": 1,
        "task": "0020-nautilus-trader",
    },
    owned_children=frozenset(
        {
            "checkout",
            "driver-config.json",
            "environment",
            "input.jsonl",
            "logs",
            "outputs",
            "venv",
        }
    ),
)
_CONTROLLER_ARTIFACTS = {
    "account": "outputs/run-1/account.json",
    "commands": "environment/commands.json",
    "events": "outputs/run-1/events.jsonl",
    "fills": "outputs/run-1/fills.json",
    "pip_check": "environment/pip-check.txt",
    "pip_freeze": "environment/pip-freeze.txt",
}


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


NautilusRunner = Callable[..., IsolatedRunMetadata]


def _write_json(path: Path, payload: object, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = (",", ":") if indent is None else None
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=separators,
            indent=indent,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_evidence(path: Path, evidence: FrameworkRunEvidence) -> None:
    """Write sorted portable evidence; raw local logs remain under work_root."""
    _write_json(path, evidence.model_dump(mode="json"), indent=2)


def _base_checks() -> dict[str, bool]:
    return {
        "chronological_split": False,
        "contract_mapping": False,
        "deterministic": False,
        "license": False,
        "no_leakage": False,
        "paper_only": False,
        "windows_install": False,
    }


def _prepare_output_roots(work_root: Path) -> tuple[Path, Path]:
    roots = (work_root / "outputs" / "run-1", work_root / "outputs" / "run-2")
    for root in roots:
        if root.parent.parent.resolve() != work_root.resolve():
            raise WorkRootOwnershipError("output root escaped the resolved work root")
        root.mkdir(parents=True)
        if any(root.iterdir()):
            raise WorkRootOwnershipError("output root was not empty before runner invocation")
    return roots


def _paper_expectation(bars: list[object]) -> dict[str, object]:
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USDC",
    )
    second = bars[1]
    request = OrderRequest(
        instrument=instrument,
        side=Side.BUY,
        quantity=0.1,
        limit_price=105.0,
        paper=True,
        client_order_id="QM-NAUTILUS-ORDER-001",
        idempotency_key="qm-nautilus-order-001",
    )
    quote = Quote(
        instrument=instrument,
        timestamp=second.timestamp,
        bid=second.open,
        ask=second.open,
        last=second.open,
        volume=second.volume,
    )
    starting_cash = 100_000.0
    result = PaperAccount(cash=starting_cash).submit(
        request,
        quote,
        now=second.timestamp,
    )
    if result.rejection or len(result.fills) != 1:
        raise ValueError("QuantMesh PaperAccount did not produce the bounded reference fill")
    fill = result.fills[0]
    position = result.account.positions[position_key(instrument)]
    return {
        "account_delta": result.account.cash - starting_cash,
        "cash": result.account.cash,
        "fill_price": fill.price,
        "fill_quantity": fill.quantity,
        "order_id": result.order.order_id,
        "position_quantity": position.quantity,
        "starting_cash": starting_cash,
        "status_transitions": ["submitted", "accepted", "filled"],
    }


def _export_fixture(fixture_path: Path, work_root: Path) -> tuple[Path, Path]:
    try:
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Hyperliquid fixture is unreadable") from error
    if not isinstance(raw, list) or len(raw) != 6:
        raise ValueError("expected the six-row Hyperliquid BTC 1m fixture")
    previous_open: int | None = None
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"fixture row {index} is not an object")
        opened = row.get("t")
        if isinstance(opened, bool) or not isinstance(opened, int):
            raise ValueError(f"fixture row {index} timestamp is not unix milliseconds")
        if previous_open is not None:
            delta = opened - previous_open
            if delta <= 0:
                raise ValueError("duplicate or nonmonotonic fixture timestamp")
            if delta != 60_000 and row.get("sequence_gap") is not True:
                raise ValueError("unmarked 1m gap in Hyperliquid fixture")
        previous_open = opened

    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USDC",
    )
    bars = []
    exported = []
    for ordinal, row in enumerate(raw):
        try:
            bar = parse_candle(row, instrument, interval="1m")
        except Exception as error:
            raise ValueError(
                f"candle symbol/interval/timestamp validation failed: {error}"
            ) from error
        bars.append(bar)
        exported.append(
            {
                "close": bar.close,
                "high": bar.high,
                "interval": bar.interval,
                "low": bar.low,
                "open": bar.open,
                "replay_ordinal": ordinal,
                "sequence_source": "quantmesh-fixture-order",
                "source": "quantmesh-hyperliquid-wire-fixture",
                "source_row": row,
                "symbol": bar.instrument.symbol,
                "timestamp": bar.timestamp.isoformat(),
                "venue": bar.instrument.venue.value,
                "volume": bar.volume,
            }
        )
    input_path = work_root / "input.jsonl"
    input_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
            for row in exported
        ),
        encoding="utf-8",
    )
    expected = _paper_expectation(bars)
    config_path = work_root / "driver-config.json"
    _write_json(
        config_path,
        {
            "interval": "1m",
            "order_intent": {
                "fill_id": "QM-NAUTILUS-FILL-001",
                "limit_price": 105.0,
                "order_id": "QM-NAUTILUS-ORDER-001",
                "quantity": 0.1,
                "side": "BUY",
                "submit_after_replay_ordinal": 0,
            },
            "paper": True,
            "quantmesh_expected": expected,
            "seed": 20260811,
            "source": "quantmesh-hyperliquid-wire-fixture",
            "symbol": "BTC",
            "venue": "HYPERLIQUID",
        },
    )
    return input_path, config_path


def _input_digest(input_path: Path, config_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (input_path, config_path):
        payload = path.read_bytes()
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _digest_outputs(root: Path) -> str:
    digest = hashlib.sha256()
    for name in CANONICAL_ARTIFACTS:
        payload = (root / name).read_bytes()
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _load_events(path: Path) -> list[dict[str, object]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"events.jsonl line {line_number} is not an object")
        rows.append(value)
    return rows


def _equal_number(left: object, right: object) -> bool:
    return (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
        and math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-9)
    )


def _validate_outputs(
    work_root: Path,
    input_path: Path,
    config_path: Path,
    output_roots: tuple[Path, Path],
    metadata: IsolatedRunMetadata,
) -> tuple[dict[str, bool], list[str], str | None, bool]:
    checks = _base_checks()
    checks["license"] = metadata.license_sha256 == NAUTILUS_LICENSE_SHA256
    checks["windows_install"] = (
        metadata.revision == NAUTILUS_PIN
        and metadata.version == NAUTILUS_VERSION
        and metadata.pip_check_exit_code == 0
    )
    problems: list[str] = []
    expected_names = set(CANONICAL_ARTIFACTS)
    for root in output_roots:
        entries = list(root.iterdir())
        missing = [name for name in CANONICAL_ARTIFACTS if not (root / name).is_file()]
        unexpected = [entry.name for entry in entries if entry.name not in expected_names]
        linked = [entry.name for entry in entries if _path_is_link_or_reparse(entry)]
        if missing:
            problems.append(f"missing canonical artifacts: {', '.join(missing)}")
        if unexpected:
            problems.append(f"unexpected output artifacts: {', '.join(unexpected)}")
        if linked:
            problems.append(f"linked canonical artifacts are forbidden: {', '.join(linked)}")
    if problems:
        return checks, problems, None, False

    physical_files = [root / name for root in output_roots for name in CANONICAL_ARTIFACTS]
    for index, path in enumerate(physical_files):
        for other in physical_files[:index]:
            try:
                shared = path.samefile(other)
            except (NotImplementedError, OSError):
                return checks, ["canonical physical-file uniqueness is unverifiable"], None, False
            if shared:
                return checks, ["canonical runs share physical files"], None, False

    first_digest = _digest_outputs(output_roots[0])
    deterministic = first_digest == _digest_outputs(output_roots[1])
    checks["deterministic"] = deterministic
    if not deterministic:
        return checks, ["canonical output digests differ"], None, False

    exported = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines()]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    events = _load_events(output_roots[0] / "events.jsonl")
    fills = json.loads((output_roots[0] / "fills.json").read_text(encoding="utf-8"))
    account = json.loads((output_roots[0] / "account.json").read_text(encoding="utf-8"))
    if not isinstance(fills, list) or not isinstance(account, dict):
        raise ValueError("fills.json/account.json have invalid top-level shapes")

    event_ordinals = [row.get("replay_ordinal") for row in events]
    fill_ordinals = [row.get("replay_ordinal") for row in fills if isinstance(row, dict)]
    ordinals_valid = (
        event_ordinals == sorted(event_ordinals)
        and fill_ordinals == sorted(fill_ordinals)
        and all(isinstance(value, int) and 0 <= value < 6 for value in event_ordinals)
        and all(isinstance(value, int) and 0 <= value < 6 for value in fill_ordinals)
    )
    source_valid = all(
        row.get("sequence_source") == "quantmesh-fixture-order"
        and "sequence" not in row
        and isinstance(row.get("source_row"), dict)
        for row in exported
    )
    checks["chronological_split"] = (
        len(exported) == 6
        and [row.get("replay_ordinal") for row in exported] == list(range(6))
        and ordinals_valid
        and source_valid
    )
    checks["no_leakage"] = (
        checks["chronological_split"]
        and all(
            row.get("replay_ordinal", -1) >= 1
            for row in fills
            if isinstance(row, dict)
        )
        and all(
            row.get("replay_ordinal", -1) >= 0
            for row in events
            if row.get("status") == "submitted"
        )
    )
    records = [*events, *(row for row in fills if isinstance(row, dict))]
    checks["paper_only"] = (
        account.get("paper") is True
        and account.get("venue") == "hyperliquid"
        and bool(records)
        and all(
            row.get("paper") is True and row.get("venue") == "hyperliquid"
            for row in records
        )
    )

    expected = config["quantmesh_expected"]
    identity_valid = all(
        row.get("order_id") == "QM-NAUTILUS-ORDER-001"
        for row in records
    ) and all(
        row.get("fill_id") == "QM-NAUTILUS-FILL-001"
        for row in fills
        if isinstance(row, dict)
    )
    comparison = account.get("comparison")
    mismatches = comparison.get("mismatches") if isinstance(comparison, dict) else None
    if not isinstance(mismatches, list):
        mismatches = ["account comparison did not contain a mismatches list"]
    for mismatch in mismatches:
        problems.append(f"semantic mismatch: {mismatch}")
    baseline = account.get("quantmesh")
    modes_valid = True
    for mode in ("quantmesh", "nautilus_backtest", "nautilus_sandbox"):
        view = account.get(mode)
        if not isinstance(view, dict):
            modes_valid = False
            problems.append(f"missing {mode} account view")
            continue
        for key in (
            "account_delta",
            "cash",
            "fill_price",
            "fill_quantity",
            "position_quantity",
        ):
            if not _equal_number(view.get(key), expected.get(key)):
                modes_valid = False
                problems.append(f"{mode} {key} does not match QuantMesh PaperAccount")
        if view.get("order_id") != expected.get("order_id") or view.get(
            "status_transitions"
        ) != expected.get("status_transitions"):
            modes_valid = False
            problems.append(f"{mode} identity/status transitions do not match")
    sandbox = account.get("nautilus_sandbox")
    sandbox_config = sandbox.get("config") if isinstance(sandbox, dict) else None
    sandbox_valid = isinstance(sandbox, dict) and sandbox.get("supported") is True and (
        sandbox_config
        == {
            "account_type": "MARGIN",
            "bar_execution": True,
            "oms_type": "NETTING",
            "trade_execution": True,
            "use_random_ids": False,
            "use_reduce_only": True,
            "venue": "HYPERLIQUID",
        }
    )
    if not sandbox_valid:
        problems.append("pinned sandbox execution path/config is unsupported or incomplete")
    checks["contract_mapping"] = (
        checks["chronological_split"]
        and checks["no_leakage"]
        and checks["paper_only"]
        and identity_valid
        and baseline == account.get("quantmesh")
        and modes_valid
        and sandbox_valid
        and not mismatches
    )
    if not checks["license"]:
        problems.append("upstream LICENSE hash does not match the pinned checkout")
    if metadata.revision != NAUTILUS_PIN:
        problems.append("isolated checkout revision does not match the Nautilus pin")
    if metadata.version != NAUTILUS_VERSION:
        problems.append("installed NautilusTrader version does not match 1.231.0")
    if metadata.pip_check_exit_code != 0:
        problems.append(f"pip check failed with exit code {metadata.pip_check_exit_code}")
    return checks, problems, first_digest, deterministic


def _command_payload(records: list[CommandResult]) -> list[dict[str, object]]:
    return [asdict(record) for record in records]


def _real_nautilus_runner(
    *,
    input_path: Path,
    config_path: Path,
    output_roots: tuple[Path, Path],
    work_root: Path,
) -> IsolatedRunMetadata:
    pin = load_pins(_PINS_PATH)["nautilus-trader"]
    if pin.revision != NAUTILUS_PIN or pin.tag != "v1.231.0":
        raise ValueError("Nautilus code pin does not match pins.json")
    started = time.perf_counter()
    checkout = (work_root / "checkout").resolve()
    venv = (work_root / "venv").resolve()
    logs = (work_root / "logs").resolve()
    environment = (work_root / "environment").resolve()
    environment.mkdir(parents=True, exist_ok=True)
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
        network: bool = False,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        try:
            result = run_command(
                command,
                cwd=cwd,
                logs_root=logs,
                label=label,
                placeholders=placeholders,
                timeout_seconds=timeout,
                inherit_proxy=network,
                check=check,
                env=env,
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
            _write_json(environment / "commands.json", _command_payload(records), indent=2)
            raise
        records.append(result)
        return result

    if checkout.exists() or venv.exists():
        raise WorkRootOwnershipError("checkout and venv must be absent in a fresh owned run")
    execute(
        [
            "git",
            "-c",
            "credential.helper=",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            "--branch",
            "v1.231.0",
            "--single-branch",
            pin.repository,
            str(checkout),
        ],
        label="01-git-clone-tag",
        cwd=work_root,
        timeout=600,
        network=True,
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
            NAUTILUS_PIN,
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
    if revision != NAUTILUS_PIN:
        raise RuntimeError("checked-out revision does not match the pinned tag commit")
    license_sha256 = hashlib.sha256((checkout / "LICENSE").read_bytes()).hexdigest()
    if license_sha256 != NAUTILUS_LICENSE_SHA256:
        raise RuntimeError("pinned LGPL-3.0 license hash does not match")

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
            "nautilus_trader==1.231.0",
            f"pandas=={NAUTILUS_PANDAS_VERSION}",
        ],
        label="05-install-nautilus",
        cwd=work_root,
        timeout=1200,
        network=True,
    )
    version_result = execute(
        [
            str(venv_python),
            "-c",
            "import importlib.metadata as m; print(m.version('nautilus_trader'))",
        ],
        label="06-version",
        cwd=work_root,
        timeout=60,
    )
    version = (work_root / version_result.stdout_log).read_text(encoding="utf-8").strip()
    if version != NAUTILUS_VERSION:
        raise RuntimeError("installed NautilusTrader version does not match 1.231.0")
    for index, output_root in enumerate(output_roots, 1):
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
            label=f"07-driver-run-{index}",
            cwd=checkout,
            timeout=300,
            env={"PYTHONHASHSEED": "20260811"},
        )
    pip_check = execute(
        [str(venv_python), "-m", "pip", "check"],
        label="08-pip-check",
        cwd=work_root,
        timeout=120,
        check=False,
    )
    pip_freeze = execute(
        [str(venv_python), "-m", "pip", "freeze", "--all"],
        label="09-pip-freeze",
        cwd=work_root,
        timeout=120,
    )
    shutil.copyfile(work_root / pip_check.stdout_log, environment / "pip-check.txt")
    shutil.copyfile(work_root / pip_freeze.stdout_log, environment / "pip-freeze.txt")
    _write_json(environment / "commands.json", _command_payload(records), indent=2)
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
            "LGPL-3.0 isolated comparator; never runtime-admitted by this evidence",
            "pandas==2.3.3 pinned because BarDataWrangler in NautilusTrader 1.231.0 "
            "rejects pandas 3 read-only arrays",
            "peak RSS is maximum direct child working set, not process-tree sum",
        ),
    )


def _static_failure() -> FrameworkRunEvidence:
    payload = {
        "framework": "nautilus-trader",
        "revision": NAUTILUS_PIN,
        "status": "failed",
        "deterministic": False,
        "input_digest": _UNAVAILABLE_INPUT_DIGEST,
        "output_digest": None,
        "duration_seconds": 0.0,
        "peak_rss_mb": 0.0,
        "environment_bytes": 0,
        "checks": _base_checks(),
        "artifacts": {},
        "score_inputs": {},
        "limitations": [
            "failure_stage=fallback-evidence",
            "failure_type=EvidenceConstructionError",
            "failure_code=static-fallback",
        ],
    }
    try:
        return FrameworkRunEvidence(**payload)  # type: ignore[arg-type]
    except Exception:
        return FrameworkRunEvidence.model_construct(**payload)


def _failure_evidence(
    *,
    stage: str,
    error: Exception,
    started: float,
    input_digest: str,
    work_root: Path | None,
) -> FrameworkRunEvidence:
    try:
        duration = max(0.0, time.perf_counter() - started)
        code = getattr(error, "code", "orchestration-failure")
        limitations = [
            f"failure_stage={stage}",
            f"failure_type={type(error).__name__}",
            f"failure_code={code}",
        ]
        if stage == "input-export":
            reason = str(error).replace("\r", " ").replace("\n", " ")[:256]
            limitations.append(f"failure_reason={reason}")
        return FrameworkRunEvidence(
            framework="nautilus-trader",
            revision=NAUTILUS_PIN,
            status="failed",
            deterministic=False,
            input_digest=(
                input_digest
                if re.fullmatch(r"[0-9a-f]{64}", input_digest)
                else _UNAVAILABLE_INPUT_DIGEST
            ),
            duration_seconds=duration if math.isfinite(duration) else 0.0,
            peak_rss_mb=0,
            environment_bytes=_safe_directory_bytes(work_root / "venv" if work_root else None),
            checks=_base_checks(),
            artifacts=(
                _existing_artifacts(work_root, _CONTROLLER_ARTIFACTS)
                if work_root is not None
                else {}
            ),
            score_inputs={},
            limitations=limitations,
        )
    except Exception:
        return _static_failure()


def _command_failure_evidence(
    error: CommandFailure,
    *,
    started: float,
    input_digest: str,
    work_root: Path,
) -> FrameworkRunEvidence:
    license_path = work_root / "checkout" / "LICENSE"
    license_ok = False
    try:
        license_ok = (
            hashlib.sha256(license_path.read_bytes()).hexdigest()
            == NAUTILUS_LICENSE_SHA256
        )
    except OSError:
        pass
    try:
        stderr = (work_root / error.stderr_log).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        stderr = ""
    portable_stderr = _portable_text(stderr, work_root)
    relevant = [line.strip() for line in portable_stderr.splitlines() if line.strip()]
    excerpt = (relevant[-1] if relevant else "failure details unavailable")[:512]
    return FrameworkRunEvidence(
        framework="nautilus-trader",
        revision=NAUTILUS_PIN,
        status="failed",
        deterministic=False,
        input_digest=input_digest,
        duration_seconds=max(0.0, time.perf_counter() - started),
        peak_rss_mb=max(0.0, error.peak_rss_mb),
        environment_bytes=_safe_directory_bytes(work_root / "venv"),
        checks={**_base_checks(), "license": license_ok},
        artifacts=_existing_artifacts(
            work_root,
            {
                "commands": "environment/commands.json",
                "failure_stderr": error.stderr_log,
                "failure_stdout": error.stdout_log,
            },
        ),
        limitations=[
            f"failed command: {_portable_text(error.command, work_root)}",
            f"exit_code={error.exit_code}",
            f"failure={excerpt}",
            f"failure_sha256={hashlib.sha256(excerpt.encode()).hexdigest()}",
            f"stderr_log={error.stderr_log}",
            "peak_rss_scope=direct-child-process-only",
        ],
    )


def _portable_runner_text(value: object, work_root: Path) -> str:
    """Bound and reject runner text that remains path-bearing after redaction."""
    if not isinstance(value, str):
        return "invalid-runner-metadata-omitted"
    portable = _portable_text(value, work_root)
    if re.search(r"(?i)(?:[a-z]:[\\/]|\\\\|(?:^|[=\s])/[^/\s])", portable):
        return "nonportable-runner-metadata-omitted"
    return portable.replace("\r", " ").replace("\n", " ")[:512]


def run_nautilus(
    fixture_path: Path,
    work_root: Path | str,
    *,
    runner: NautilusRunner = _real_nautilus_runner,
) -> FrameworkRunEvidence:
    """Export one validated fixture and evaluate the pinned engine twice."""
    started = time.perf_counter()
    input_digest = _UNAVAILABLE_INPUT_DIGEST
    trusted_root: Path | None = None
    stage = "work-root-validation"
    try:
        lexeme = _validate_work_root_lexeme(work_root)
        lexical = _lexical_work_root(Path(lexeme))
        stage = "fixture-resolution"
        fixture_path = Path(fixture_path).resolve(strict=True)
        stage = "work-root-resolution"
        trusted_root = _resolve_safe_work_root(lexical)
        stage = "work-root-preparation"
        prepare_owned_work_root(trusted_root, _WORK_POLICY)
        stage = "input-export"
        input_path, config_path = _export_fixture(fixture_path, trusted_root)
        stage = "input-hash"
        input_digest = _input_digest(input_path, config_path)
        stage = "output-root-preparation"
        output_roots = _prepare_output_roots(trusted_root)
        stage = "runner-execution"
        metadata = runner(
            input_path=input_path,
            config_path=config_path,
            output_roots=output_roots,
            work_root=trusted_root,
        )
        stage = "output-validation"
        checks, problems, output_digest, deterministic = _validate_outputs(
            trusted_root,
            input_path,
            config_path,
            output_roots,
            metadata,
        )
        stage = "evidence-construction"
        passed = deterministic and all(checks.values()) and not problems
        artifacts = _existing_artifacts(
            trusted_root,
            {
                **(
                    metadata.environment_artifacts
                    if isinstance(metadata.environment_artifacts, dict)
                    else {}
                ),
                **_CONTROLLER_ARTIFACTS,
            },
        )
        safe_version = (
            metadata.version
            if metadata.version == NAUTILUS_VERSION
            else "unexpected-version"
        )
        safe_license = (
            metadata.license_sha256
            if isinstance(metadata.license_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", metadata.license_sha256)
            else "invalid-license-hash"
        )
        limitations = [
            *(
                _portable_runner_text(limitation, trusted_root)
                for limitation in metadata.limitations
            ),
            f"upstream_version={safe_version}",
            f"license_sha256={safe_license}",
            f"pip_check_exit_code={metadata.pip_check_exit_code}",
            *(
                f"command: {_portable_runner_text(command, trusted_root)}"
                for command in metadata.commands
            ),
            *problems,
        ]
        return FrameworkRunEvidence(
            framework="nautilus-trader",
            revision=NAUTILUS_PIN,
            status="passed" if passed else "failed",
            deterministic=deterministic,
            input_digest=input_digest,
            output_digest=output_digest if deterministic else None,
            duration_seconds=metadata.duration_seconds,
            peak_rss_mb=metadata.peak_rss_mb,
            environment_bytes=metadata.environment_bytes,
            checks=checks,
            artifacts=artifacts,
            score_inputs={},
            limitations=limitations,
        )
    except CommandFailure as error:
        assert trusted_root is not None
        return _command_failure_evidence(
            error,
            started=started,
            input_digest=input_digest,
            work_root=trusted_root,
        )
    except Exception as error:
        return _failure_evidence(
            stage=stage,
            error=error,
            started=started,
            input_digest=input_digest,
            work_root=trusted_root,
        )
