"""Deadline-bounded formal daily trusted-data soak state machine."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.data.collection_receipts import CollectionCycleReceipt
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    DailyStageReceiptV1,
    ImmutableRunConflictError,
    ImmutableRunStore,
    LeaseHeldError,
    LeaseOwner,
    SlotLease,
    SoakVerificationProof,
    StageOutcome,
    publish_create_once,
    reject_reparse_chain,
)
from quantmesh.ops.processes import ProcessResult, run_process
from quantmesh.ops.source_contract import SourceContractV1, verify_source_contract
from quantmesh.ops.trusted_data_soak import SoakReportV2, SoakStoreV2, SoakVerification
from quantmesh.ops.witness_outbox import (
    OutboxIntentError,
    WitnessKind,
    WitnessOutbox,
)


@dataclass(frozen=True)
class DailyRunConfig:
    repo: Path
    data_root: Path
    evidence_root: Path
    run_root: Path
    outbox_root: Path
    remote_ref: str
    dependency_digest: str
    script_digest: str
    config_digest: str
    source_timeout: float = 30
    hyperliquid_timeout: float = 300
    moomoo_timeout: float = 600
    observe_timeout: float = 600
    verify_timeout: float = 600
    lease_wait_timeout: float = 30

    def __post_init__(self) -> None:
        roots = (self.data_root, self.evidence_root, self.run_root, self.outbox_root)
        if not self.repo.is_absolute() or any(not path.is_absolute() for path in roots):
            raise ValueError("daily runner repository and roots must be absolute")
        resolved = tuple(path.resolve() for path in roots)
        if any(
            left == right or left.is_relative_to(right) or right.is_relative_to(left)
            for index, left in enumerate(resolved)
            for right in resolved[index + 1 :]
        ):
            raise ValueError("daily data, evidence, run and outbox roots must be disjoint")


class _StageFailure(RuntimeError):
    def __init__(self, stage: str, code: str, detail: str, *, status=DailyRunStatus.FAILED):
        super().__init__(detail)
        self.stage, self.code, self.detail, self.status = stage, code, detail, status


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _run_id(slot: str, commit: str, attempt: int = 1) -> str:
    return _digest(
        {
            "contract": "daily-operational-run-v1",
            "slot": slot,
            "attempt": attempt,
            "code_commit": commit,
        }
    )


def _ensure_daily_witness(
    config: DailyRunConfig,
    terminal: DailyRunReceiptV1,
    *,
    expected_commit: str,
    expected_source_contract_id: str,
):
    if terminal.status is not DailyRunStatus.PASSED:
        return None
    outbox = WitnessOutbox(config.outbox_root)
    try:
        return outbox.ensure_daily_intent(
            terminal,
            report_root=config.evidence_root,
            expected_commit=expected_commit,
            expected_source_contract_id=expected_source_contract_id,
        )
    except Exception as error:
        conflict = isinstance(error, ImmutableRunConflictError)
        outbox.record_reconciliation_failure(
            source_kind=WitnessKind.DAILY_ACCEPTED,
            terminal_receipt_id=terminal.receipt_id,
            error_code="intent-conflict" if conflict else "intent-error",
            detail=(
                "exact daily intent conflicts with durable outbox evidence"
                if conflict
                else f"daily intent enqueue raised {type(error).__name__}"
            ),
            observed_at=terminal.finished_at,
        )
        raise OutboxIntentError(
            "passing daily terminal is durable but its exact witness intent is missing"
        ) from error


def _crypto_window(now: datetime) -> str:
    end = (now - timedelta(minutes=7)).replace(second=0, microsecond=0)
    start = end - timedelta(minutes=30)
    return f"{start:%Y-%m-%dT%H:%M:%S}Z/{end:%Y-%m-%dT%H:%M:%S}Z"


def _moomoo_window(now: datetime) -> str:
    sessions = CalendarService().sessions(
        "XNYS", (now - timedelta(days=10)).date(), now.date(), policy=SessionPolicy.REGULAR
    )
    completed = tuple(item for item in sessions if item.close_at <= now)
    if not completed:
        raise _StageFailure("collect-moomoo", "no-session", "no completed XNYS session")
    end = completed[-1].close_at + timedelta(hours=1)
    start = end - timedelta(days=7)
    return f"{start:%Y-%m-%dT%H:%M:%S}Z/{end:%Y-%m-%dT%H:%M:%S}Z"


def _parse_collection(output: str, provider: str) -> CollectionCycleReceipt:
    stage = "collect-hyperliquid" if provider == "hyperliquid-public" else "collect-moomoo"
    try:
        outer = json.loads(output)
        if (
            not isinstance(outer, dict)
            or outer.get("provider") != provider
            or outer.get("read_only") is not True
        ):
            raise ValueError("invalid envelope")
        receipt = CollectionCycleReceipt.model_validate_json(
            json.dumps(outer["collection_receipt"])
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _StageFailure(
            stage, "invalid-collection-receipt", "collector output is not one typed exact receipt"
        ) from error
    return receipt


def _write_cycle(root: Path, receipt: CollectionCycleReceipt) -> Path:
    directory = root / "cycle-receipts"
    reject_reparse_chain(root)
    directory.mkdir(parents=True, exist_ok=True)
    reject_reparse_chain(directory)
    path = directory / f"{receipt.receipt_id}.json"
    payload = receipt.canonical_bytes()
    try:
        publish_create_once(path, payload, label="runner cycle receipt")
    except Exception as error:
        raise _StageFailure("persist-receipts", "receipt-conflict", str(error)) from error
    return path


def _stage(
    store: ImmutableRunStore,
    run_id: str,
    slot: str,
    name: str,
    argv: tuple[str, ...],
    timeout: float,
    cwd: Path,
    stage_ids: list[str],
) -> ProcessResult:
    started = _now()
    result = run_process(argv, timeout_seconds=timeout, cwd=cwd)
    receipt = DailyStageReceiptV1.build(
        run_id=run_id,
        slot=slot,
        stage=name,
        command_digest=_digest(list(argv)),
        started_at=started,
        finished_at=_now(),
        outcome=(
            StageOutcome.TIMED_OUT
            if result.timed_out
            else StageOutcome.PASSED
            if result.returncode == 0
            else StageOutcome.FAILED
        ),
        exit_code=result.returncode,
        stdout_digest=_digest(result.stdout),
        stderr_digest=_digest(result.stderr),
        output_digest=None,
    )
    store.publish_stage(receipt)
    stage_ids.append(receipt.receipt_id)
    return result


def _require(result: ProcessResult, stage: str) -> None:
    if result.timed_out:
        raise _StageFailure(
            stage,
            "deadline-exceeded",
            f"{stage} exceeded its deadline",
            status=DailyRunStatus.TIMED_OUT,
        )
    if result.returncode != 0:
        raise _StageFailure(stage, "child-nonzero", f"{stage} exited non-zero")


def _lease_wait_budget(config: DailyRunConfig) -> float:
    owner_budget = sum(
        (
            config.source_timeout,
            config.hyperliquid_timeout,
            config.moomoo_timeout,
            config.observe_timeout,
            config.verify_timeout,
        )
    )
    if not math.isfinite(owner_budget) or owner_budget <= 0:
        raise ValueError("owner stage deadlines must be finite and positive")
    if not math.isfinite(config.lease_wait_timeout) or config.lease_wait_timeout <= 0:
        raise ValueError("lease wait timeout must be finite and positive")
    return max(config.lease_wait_timeout, owner_budget + 30)


def _acquire_daily_slot(
    config: DailyRunConfig,
    store: ImmutableRunStore,
    slot: str,
    owner: LeaseOwner,
) -> SlotLease | DailyRunReceiptV1:
    """Wait finitely for the slot, converging on an already durable terminal."""
    deadline = time.monotonic() + _lease_wait_budget(config)
    while True:
        try:
            return SlotLease.acquire(config.run_root, slot, owner=owner, now=_now())
        except LeaseHeldError:
            existing = store.terminals(slot)
            if existing:
                return existing[-1]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LeaseHeldError(
                    "slot lease remained held without a durable terminal before deadline"
                )
            time.sleep(min(0.1, remaining))


def run_daily(config: DailyRunConfig) -> DailyRunReceiptV1:
    started = _now()
    slot = started.date().isoformat()
    store = ImmutableRunStore(config.run_root)
    owner = LeaseOwner.current(token=uuid.uuid4().hex)
    acquired = _acquire_daily_slot(config, store, slot, owner)
    if isinstance(acquired, DailyRunReceiptV1):
        if acquired.status is DailyRunStatus.PASSED:
            source = verify_source_contract(
                config.repo,
                config.remote_ref,
                config.dependency_digest,
                config.script_digest,
                config.config_digest,
                timeout_seconds=config.source_timeout,
            )
            _ensure_daily_witness(
                config,
                acquired,
                expected_commit=source.head_commit,
                expected_source_contract_id=source.source_contract_id,
            )
        return acquired
    lease = acquired
    source: SourceContractV1 | None = None
    hyper: CollectionCycleReceipt | None = None
    moomoo: CollectionCycleReceipt | None = None
    report: SoakReportV2 | None = None
    verification: SoakVerification | None = None
    stage_ids: list[str] = []
    attempt = 1
    status = DailyRunStatus.FAILED
    failure = ("runner", "unexpected-exception", "runner did not reach a terminal state")
    try:
        try:
            source = verify_source_contract(
                config.repo,
                config.remote_ref,
                config.dependency_digest,
                config.script_digest,
                config.config_digest,
                timeout_seconds=config.source_timeout,
            )
            python = str(config.repo / ".venv" / "Scripts" / "python.exe")
            existing = store.terminals(slot)
            attempt = 1 if not existing else existing[-1].attempt + 1
            run_id = _run_id(slot, source.head_commit, attempt)
            if existing:
                prior = existing[-1]
                if (
                    prior.code_commit != source.head_commit
                    or prior.source_contract_id != source.source_contract_id
                ):
                    raise _StageFailure(
                        "source-contract",
                        "retry-source-mismatch",
                        "same-day retry source contract changed",
                    )
                verify = _stage(
                    store,
                    run_id,
                    slot,
                    "verify",
                    (
                        python,
                        str(config.repo / "tools" / "trusted_data_soak.py"),
                        "verify",
                        "--data-root",
                        str(config.data_root),
                        "--evidence-root",
                        str(config.evidence_root),
                        "--minimum-hours",
                        "0",
                        "--minimum-xnys-sessions",
                        "1",
                    ),
                    config.verify_timeout,
                    config.repo,
                    stage_ids,
                )
                try:
                    verification = SoakVerification.model_validate_json(verify.stdout)
                except ValueError:
                    verification = None
                retry_passed = (
                    prior.status is DailyRunStatus.PASSED
                    and verify.returncode == 0
                    and not verify.timed_out
                    and verification is not None
                    and verification.accepted
                )
                status = (
                    DailyRunStatus.PASSED
                    if retry_passed
                    else DailyRunStatus.TIMED_OUT
                    if verify.timed_out
                    else DailyRunStatus.FAILED
                )
                failure = (
                    (None, None, None)
                    if retry_passed
                    else (
                        prior.failure_stage or "verify",
                        prior.failure_code or "verification-rejected",
                        prior.detail or "same-day verifier did not preserve pass",
                    )
                )
                hyper_id = prior.hyperliquid_receipt_id
                moomoo_id = prior.moomoo_receipt_id
                report_id = prior.soak_report_id
                proof = (
                    None
                    if verification is None
                    else SoakVerificationProof(**verification.model_dump())
                )
                terminal = DailyRunReceiptV1.build(
                    run_id=run_id,
                    slot=slot,
                    attempt=attempt,
                    started_at=started,
                    finished_at=_now(),
                    status=status,
                    code_commit=source.head_commit,
                    source_contract_id=source.source_contract_id,
                    stage_receipt_ids=tuple(stage_ids),
                    hyperliquid_receipt_id=hyper_id,
                    moomoo_receipt_id=moomoo_id,
                    soak_report_id=report_id,
                    verification=proof,
                    failure_stage=failure[0],
                    failure_code=failure[1],
                    detail=failure[2],
                    recovery_of_run_id=prior.run_id,
                )
                store.publish_terminal(terminal)
                _ensure_daily_witness(
                    config,
                    terminal,
                    expected_commit=source.head_commit,
                    expected_source_contract_id=source.source_contract_id,
                )
                return terminal
            durable_reports = tuple(
                item
                for item in SoakStoreV2(config.evidence_root).reports()
                if item.report_date == slot
            )
            if len(durable_reports) > 1:
                raise _StageFailure(
                    "recover-report",
                    "duplicate-durable-reports",
                    "more than one durable report exists for the UTC slot",
                )
            if durable_reports:
                report = durable_reports[0]
                if (
                    report.code_commit != source.head_commit
                    or report.source_contract_id != source.source_contract_id
                ):
                    raise _StageFailure(
                        "recover-report",
                        "report-source-mismatch",
                        "durable report does not match the verified source contract",
                    )
                evidence_store = SoakStoreV2(config.evidence_root)
                recovered = tuple(
                    evidence_store.load_cycle_receipt(receipt_id)
                    for receipt_id in report.collection_receipt_ids
                )
                by_provider = {item.provider: item for item in recovered}
                if set(by_provider) != {"hyperliquid-public", "moomoo-opend"} or any(
                    item.code_commit != source.head_commit for item in recovered
                ):
                    raise _StageFailure(
                        "recover-report",
                        "report-receipt-mismatch",
                        "durable report does not bind one exact receipt per provider",
                    )
                hyper = by_provider["hyperliquid-public"]
                moomoo = by_provider["moomoo-opend"]
                if hyper.collection_cycle != moomoo.collection_cycle:
                    raise _StageFailure(
                        "recover-report",
                        "mixed-cycle",
                        "durable report collection receipts disagree on cycle",
                    )
                verify = _stage(
                    store,
                    run_id,
                    slot,
                    "verify",
                    (
                        python,
                        str(config.repo / "tools" / "trusted_data_soak.py"),
                        "verify",
                        "--data-root",
                        str(config.data_root),
                        "--evidence-root",
                        str(config.evidence_root),
                        "--minimum-hours",
                        "0",
                        "--minimum-xnys-sessions",
                        "1",
                    ),
                    config.verify_timeout,
                    config.repo,
                    stage_ids,
                )
                try:
                    verification = SoakVerification.model_validate_json(verify.stdout)
                except ValueError:
                    verification = None
                recovered_passed = (
                    not verify.timed_out
                    and verify.returncode == 0
                    and verification is not None
                    and verification.accepted
                    and not report.critical_issues
                )
                status = (
                    DailyRunStatus.PASSED
                    if recovered_passed
                    else DailyRunStatus.TIMED_OUT
                    if verify.timed_out
                    else DailyRunStatus.FAILED
                )
                failure = (
                    (None, None, None)
                    if recovered_passed
                    else (
                        "verify",
                        "deadline-exceeded" if verify.timed_out else "verification-rejected",
                        "fresh verifier rejected the recovered exact report",
                    )
                )
                terminal = DailyRunReceiptV1.build(
                    run_id=run_id,
                    slot=slot,
                    attempt=attempt,
                    started_at=started,
                    finished_at=_now(),
                    status=status,
                    code_commit=source.head_commit,
                    source_contract_id=source.source_contract_id,
                    stage_receipt_ids=tuple(stage_ids),
                    hyperliquid_receipt_id=hyper.receipt_id,
                    moomoo_receipt_id=moomoo.receipt_id,
                    soak_report_id=report.report_id,
                    verification=(
                        None
                        if verification is None
                        else SoakVerificationProof(**verification.model_dump())
                    ),
                    failure_stage=failure[0],
                    failure_code=failure[1],
                    detail=failure[2],
                )
                store.publish_terminal(terminal)
                _ensure_daily_witness(
                    config,
                    terminal,
                    expected_commit=source.head_commit,
                    expected_source_contract_id=source.source_contract_id,
                )
                return terminal
            cycle = f"daily-{slot}"
            first = _stage(
                store,
                run_id,
                slot,
                "collect-hyperliquid",
                (
                    python,
                    "-m",
                    "quantmesh.data.cli",
                    "collect",
                    "--provider",
                    "hyperliquid",
                    "--root",
                    str(config.data_root),
                    "--symbols",
                    "BTC,ETH,SOL",
                    "--interval",
                    "1m",
                    "--window",
                    _crypto_window(started),
                    "--collection-cycle",
                    cycle,
                ),
                config.hyperliquid_timeout,
                config.repo,
                stage_ids,
            )
            _require(first, "collect-hyperliquid")
            hyper = _parse_collection(first.stdout, "hyperliquid-public")
            second = _stage(
                store,
                run_id,
                slot,
                "collect-moomoo",
                (
                    python,
                    "-m",
                    "quantmesh.data.cli",
                    "collect",
                    "--provider",
                    "moomoo",
                    "--root",
                    str(config.data_root),
                    "--symbols",
                    "AAPL,NVDA",
                    "--interval",
                    "1d",
                    "--window",
                    _moomoo_window(started),
                    "--collection-cycle",
                    cycle,
                ),
                config.moomoo_timeout,
                config.repo,
                stage_ids,
            )
            _require(second, "collect-moomoo")
            try:
                moomoo_outer = json.loads(second.stdout)
            except ValueError:
                moomoo_outer = {}
            if isinstance(moomoo_outer, dict) and moomoo_outer.get("status") != "published":
                reason = str(moomoo_outer.get("reason_code") or "unavailable")
                blocked = any(word in reason.lower() for word in ("auth", "login", "logged"))
                raise _StageFailure(
                    "collect-moomoo",
                    reason,
                    str(moomoo_outer.get("detail") or "Moomoo unavailable"),
                    status=DailyRunStatus.BLOCKED_USER_AUTH if blocked else DailyRunStatus.FAILED,
                )
            moomoo = _parse_collection(second.stdout, "moomoo-opend")
            if hyper.collection_cycle != moomoo.collection_cycle or {
                hyper.code_commit,
                moomoo.code_commit,
            } != {source.head_commit}:
                raise _StageFailure(
                    "validate-receipts",
                    "mixed-cycle",
                    "provider receipts disagree on cycle or commit",
                )
            paths = (_write_cycle(config.run_root, hyper), _write_cycle(config.run_root, moomoo))
            observe = _stage(
                store,
                run_id,
                slot,
                "observe",
                (
                    python,
                    str(config.repo / "tools" / "trusted_data_soak.py"),
                    "observe",
                    "--data-root",
                    str(config.data_root),
                    "--evidence-root",
                    str(config.evidence_root),
                    "--cycle-receipt",
                    str(paths[0]),
                    "--cycle-receipt",
                    str(paths[1]),
                    "--source-contract-id",
                    source.source_contract_id,
                ),
                config.observe_timeout,
                config.repo,
                stage_ids,
            )
            if observe.returncode == 0 and not observe.timed_out:
                try:
                    report = SoakReportV2.model_validate_json(observe.stdout)
                except ValueError:
                    report = None
            verify = _stage(
                store,
                run_id,
                slot,
                "verify",
                (
                    python,
                    str(config.repo / "tools" / "trusted_data_soak.py"),
                    "verify",
                    "--data-root",
                    str(config.data_root),
                    "--evidence-root",
                    str(config.evidence_root),
                    "--minimum-hours",
                    "0",
                    "--minimum-xnys-sessions",
                    "1",
                ),
                config.verify_timeout,
                config.repo,
                stage_ids,
            )
            if not verify.timed_out:
                try:
                    verification = SoakVerification.model_validate_json(verify.stdout)
                except ValueError:
                    verification = None
            if observe.timed_out or verify.timed_out:
                raise _StageFailure(
                    "verify",
                    "deadline-exceeded",
                    "observe or verify timed out",
                    status=DailyRunStatus.TIMED_OUT,
                )
            if (
                observe.returncode != 0
                or report is None
                or report.critical_issues
                or verify.returncode != 0
                or verification is None
                or not verification.accepted
            ):
                raise _StageFailure(
                    "verify", "verification-rejected", "full verifier rejected the exact report"
                )
            status, failure = DailyRunStatus.PASSED, (None, None, None)
        except _StageFailure as error:
            status, failure = error.status, (error.stage, error.code, error.detail)
        except KeyboardInterrupt:
            status, failure = (
                DailyRunStatus.INTERRUPTED,
                ("runner", "interrupted", "daily runner was interrupted"),
            )
        except OutboxIntentError:
            raise
        except Exception as error:
            status, failure = (
                DailyRunStatus.FAILED,
                (
                    "source-contract" if source is None else "runner",
                    "unexpected-exception",
                    str(error) or type(error).__name__,
                ),
            )
        proof = None if verification is None else SoakVerificationProof(**verification.model_dump())
        terminal = DailyRunReceiptV1.build(
            run_id=_run_id(slot, "0" * 40 if source is None else source.head_commit, attempt),
            slot=slot,
            attempt=attempt,
            started_at=started,
            finished_at=_now(),
            status=status,
            code_commit="0" * 40 if source is None else source.head_commit,
            source_contract_id=_digest({"unverified-source": config.remote_ref})
            if source is None
            else source.source_contract_id,
            stage_receipt_ids=tuple(stage_ids),
            hyperliquid_receipt_id=None if hyper is None else hyper.receipt_id,
            moomoo_receipt_id=None if moomoo is None else moomoo.receipt_id,
            soak_report_id=None if report is None else report.report_id,
            verification=proof,
            failure_stage=failure[0],
            failure_code=failure[1],
            detail=failure[2],
        )
        store.publish_terminal(terminal)
        if source is not None:
            _ensure_daily_witness(
                config,
                terminal,
                expected_commit=source.head_commit,
                expected_source_contract_id=source.source_contract_id,
            )
        return terminal
    finally:
        lease.release()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "data-root", "evidence-root", "run-root", "outbox-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("remote-ref", "dependency-digest", "script-digest", "config-digest"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--source-timeout", type=float, default=30)
    parser.add_argument("--hyperliquid-timeout", type=float, default=300)
    parser.add_argument("--moomoo-timeout", type=float, default=600)
    parser.add_argument("--observe-timeout", type=float, default=600)
    parser.add_argument("--verify-timeout", type=float, default=600)
    parser.add_argument("--lease-wait-timeout", type=float, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        receipt = run_daily(DailyRunConfig(**vars(_parser().parse_args(argv))))
    except Exception as error:
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(receipt.model_dump_json())
    return 0 if receipt.status is DailyRunStatus.PASSED else 1
