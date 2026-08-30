"""Bounded operator CLI for trusted-data collection, replay and inspection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from quantmesh.data.artifacts import ManifestIntegrityError, ManifestStore
from quantmesh.data.catalog import CatalogIntegrityError, TrustedDataCatalog
from quantmesh.data.checkpoints import CheckpointIntegrityError, CheckpointStore
from quantmesh.data.collection_receipts import (
    derive_collection_receipt,
    validate_receipt_targets,
)
from quantmesh.data.hyperliquid_collection import (
    HyperliquidCollectionWindow,
    HyperliquidCollector,
)
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.data.moomoo_collection import (
    CollectionWindow,
    MoomooCollectionPlan,
    MoomooCollectionTarget,
    MoomooCollector,
)
from quantmesh.data.objects import FABRIC_NAMESPACE, ObjectIntegrityError
from quantmesh.data.overlap_resolutions import (
    OverlapResolution,
    OverlapResolutionIntegrityError,
    OverlapResolutionStore,
    ResolutionAttestation,
    ResolutionUsePolicy,
)
from quantmesh.data.quality import (
    QualityEvaluator,
    QualityEvidenceStore,
    QualityIntegrityError,
    QualityStatus,
)
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.hyperliquid.public_info import PublicInfoTransport


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="quantmesh-data",
        description="Collect and verify bounded read-only trusted-data evidence.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="collect one bounded provider window")
    collect.add_argument("--root", type=Path, required=True)
    collect.add_argument("--provider", choices=("hyperliquid", "moomoo"), required=True)
    collect.add_argument("--window", required=True, metavar="START/END")
    collect.add_argument("--symbols", required=True, help="comma-separated bounded symbols")
    collect.add_argument("--interval", default="1m")
    collect.add_argument("--collection-cycle", default="initial")

    replay = commands.add_parser("replay", help="verify and summarize one exact manifest")
    replay.add_argument("--root", type=Path, required=True)
    replay.add_argument("--manifest", required=True)

    inspect = commands.add_parser("inspect", help="print catalog and qualification state")
    inspect.add_argument("--root", type=Path, required=True)

    overlap = commands.add_parser("overlap", help="inspect or resolve one exact overlap failure")
    overlap_commands = overlap.add_subparsers(dest="overlap_command", required=True)
    overlap_inspect = overlap_commands.add_parser(
        "inspect",
        help="print exact immutable conflict evidence",
    )
    overlap_inspect.add_argument("--root", type=Path, required=True)
    overlap_inspect.add_argument("--evaluation", required=True)

    resolve = overlap_commands.add_parser(
        "resolve",
        help="record one exact operator-attested resolution",
    )
    resolve.add_argument("--root", type=Path, required=True)
    resolve.add_argument("--evaluation", "--failed-evaluation", dest="evaluation", required=True)
    resolve.add_argument("--report", "--failed-report", dest="report", required=True)
    resolve.add_argument("--policy", required=True)
    resolve.add_argument("--dataset", required=True)
    resolve.add_argument("--baseline-manifest", required=True)
    resolve.add_argument("--candidate-manifest", required=True)
    resolve.add_argument("--fingerprint", action="append", required=True)
    resolve.add_argument("--reviewed-at", type=_utc, required=True)
    resolve.add_argument("--operator", required=True)
    resolve.add_argument("--reason", required=True)
    resolve.add_argument(
        "--attestation",
        choices=tuple(item.value for item in ResolutionAttestation),
        required=True,
    )
    resolve.add_argument(
        "--use-policy",
        choices=(ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY.value,),
        required=True,
    )
    return parser


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("window timestamps must include UTC offsets")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError("window timestamps must be UTC")
    return parsed.astimezone(UTC)


def _window(value: str) -> tuple[datetime, datetime]:
    if value.count("/") != 1:
        raise ValueError("window must use START/END")
    start_text, end_text = value.split("/", maxsplit=1)
    start, end = _utc(start_text), _utc(end_text)
    if end < start:
        raise ValueError("window end must not precede start")
    return start, end


def _symbols(value: str) -> list[str]:
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("symbols must be a non-empty unique comma-separated list")
    return symbols


def _repository_commit() -> str:
    root = next(
        (parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()),
        None,
    )
    if root is None:
        raise RuntimeError("trusted collection requires an installed Git checkout")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    commit = result.stdout.strip()
    if len(commit) != 40:
        raise RuntimeError("Git did not return a full producing commit")
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout
    if status.strip():
        raise ValueError("trusted collection requires an exact clean Git checkout")
    return commit


def _validate_hyperliquid_scope(
    symbols: list[str], interval: str, start: datetime, end: datetime
) -> None:
    if any(symbol not in {"BTC", "ETH", "SOL"} for symbol in symbols):
        raise ValueError("Hyperliquid symbols are limited to BTC, ETH and SOL")
    step = interval_to_timedelta(interval)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    if (start - epoch) % step or (end - epoch) % step:
        raise ValueError("window boundaries must be interval-aligned")
    count = int((end - start) // step) + 1
    if count > 5_000:
        raise ValueError("requested horizon exceeds the provider's 5,000-candle limit")


def _collect(args: argparse.Namespace) -> dict[str, Any]:
    start, end = _window(args.window)
    symbols = _symbols(args.symbols)
    if args.provider == "hyperliquid":
        _validate_hyperliquid_scope(symbols, args.interval, start, end)
        validate_receipt_targets("hyperliquid-public", tuple(symbols))
        commit = _repository_commit()
        store = ManifestStore(args.root)
        collector = HyperliquidCollector(
            store,
            transport=PublicInfoTransport(),
            code_commit=commit,
        )
        publications = collector.collect_candles(
            symbols,
            args.interval,
            HyperliquidCollectionWindow(start=start, end=end),
            collection_cycle=args.collection_cycle,
        )
        receipt = derive_collection_receipt(
            root=args.root,
            provider="hyperliquid-public",
            code_commit=commit,
            collection_cycle=args.collection_cycle,
            manifest_ids=tuple(
                manifest_id for item in publications for manifest_id in item.manifest_ids
            ),
            targets=tuple(symbols),
            interval=args.interval,
        )
        return {
            "provider": "hyperliquid-public",
            "read_only": True,
            "code_commit": commit,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "publications": [item.model_dump(mode="json") for item in publications],
            "collection_receipt": receipt.model_dump(mode="json"),
        }

    if args.interval not in {"1m", "1d"}:
        raise ValueError("Moomoo interval must be 1m or 1d")
    if any(symbol not in {"AAPL", "NVDA"} for symbol in symbols):
        raise ValueError("Moomoo symbols are limited to AAPL and NVDA")
    validate_receipt_targets("moomoo-opend", tuple(symbols))
    commit = _repository_commit()
    store = ManifestStore(args.root)
    targets = tuple(
        MoomooCollectionTarget(
            provider_symbol=f"US.{symbol}",
            canonical_instrument=CanonicalInstrumentId(value=f"moomoo:US:{symbol}:XNAS"),
            interval=args.interval,
        )
        for symbol in symbols
    )
    with tempfile.TemporaryDirectory(prefix="quantmesh-moomoo-collection-") as scratch:
        result = MoomooCollector(
            store,
            code_commit=commit,
            scratch_root=Path(scratch),
        ).collect(
            MoomooCollectionPlan(targets=targets),
            CollectionWindow(start=start, end=end),
            collection_cycle=args.collection_cycle,
        )
    receipt = (
        None
        if not result.manifest_ids
        else derive_collection_receipt(
            root=args.root,
            provider="moomoo-opend",
            code_commit=commit,
            collection_cycle=args.collection_cycle,
            manifest_ids=result.manifest_ids,
            targets=tuple(symbols),
            interval=args.interval,
        )
    )
    return {
        "provider": "moomoo-opend",
        "read_only": True,
        "code_commit": commit,
        "collection_receipt": (
            None if receipt is None else receipt.model_dump(mode="json")
        ),
        **result.model_dump(mode="json"),
    }


def _replay(root: Path, manifest_id: str) -> dict[str, Any]:
    dataset = ManifestStore(root).open(manifest_id)
    # `open` verifies every object hash and the layer-specific typed contract.
    # Read all objects once more before reporting success so no output precedes
    # the exact replay boundary.
    for reference in dataset.manifest.objects:
        dataset.objects.get_bytes(reference)
    manifest = dataset.manifest
    return {
        "verified": True,
        "manifest_id": manifest.manifest_id,
        "dataset_id": manifest.dataset_id,
        "layer": manifest.layer.value,
        "data_kind": manifest.data_kind.value,
        "row_count": len(manifest.row_identities),
        "event_start": manifest.event_start.isoformat(),
        "event_end": manifest.event_end.isoformat(),
        "object_digests": [reference.digest for reference in manifest.objects],
        "parent_manifest_ids": list(manifest.parent_manifest_ids),
    }


def _inspect(root: Path) -> dict[str, Any]:
    entries = TrustedDataCatalog(root).entries()
    return {"datasets": [entry.model_dump(mode="json") for entry in entries]}


def _report_for_evaluation(root: Path, candidate_manifest_id: str, evaluation_id: str):
    evidence = QualityEvidenceStore(root)
    checkpoint_path = root / FABRIC_NAMESPACE / "control" / "collection-checkpoints.duckdb"
    if not checkpoint_path.is_file():
        raise QualityIntegrityError(
            "failed evaluation candidate has no committed checkpoint database"
        )
    owners = CheckpointStore(root).checkpoints_for_manifests((candidate_manifest_id,))
    checkpoint = owners.get(candidate_manifest_id)
    if checkpoint is None or checkpoint.quality_report_id is None:
        raise QualityIntegrityError(
            "failed evaluation candidate has no checkpoint-bound quality report"
        )
    report = evidence.verify_report_integrity(checkpoint.quality_report_id)
    if not any(
        binding.manifest_id == candidate_manifest_id and binding.evaluation_id == evaluation_id
        for binding in report.bindings
    ):
        raise QualityIntegrityError(
            "checkpoint-bound report does not contain the failed evaluation"
        )
    return report


def _overlap_context(root: Path, evaluation_id: str) -> dict[str, Any]:
    evidence = QualityEvidenceStore(root)
    failed = evidence.load(evaluation_id)
    if failed.status is not QualityStatus.FAIL or failed.issue_codes != (
        "historical-live-overlap",
    ):
        raise ValueError("overlap inspection requires an overlap-only failed evaluation")
    candidate = evidence.manifests.open(failed.manifest_id).manifest
    policy = evidence.load_policy(failed.policy_id)
    report = _report_for_evaluation(root, candidate.manifest_id, failed.evaluation_id)
    committed = evidence.manifests.manifests(candidate.dataset_id)
    admitted = frozenset(manifest.manifest_id for manifest in committed)
    evaluator = QualityEvaluator(evidence.manifests)
    matches = []
    for manifest_id in admitted:
        if manifest_id == candidate.manifest_id:
            continue
        baseline = evidence.manifests.open(manifest_id).manifest
        if (
            baseline.dataset_id != candidate.dataset_id
            or baseline.compatibility_revision >= candidate.compatibility_revision
            or baseline.knowledge_end > candidate.knowledge_start
        ):
            continue
        conflicts = evaluator.overlap_conflicts(
            candidate.manifest_id,
            baseline.manifest_id,
            admitted_manifest_ids=admitted,
        )
        if (
            tuple(sorted(item.legacy_evaluation_fingerprint for item in conflicts))
            == failed.overlap_conflict_fingerprints
        ):
            matches.append((baseline, conflicts))
    if not matches:
        raise QualityIntegrityError("no exact baseline reproduces the failed overlap conflict set")
    baseline, conflicts = max(
        matches,
        key=lambda item: (
            item[0].compatibility_revision,
            item[0].knowledge_end,
            item[0].manifest_id,
        ),
    )
    if not any(
        binding.evaluation_id == failed.evaluation_id
        and binding.manifest_id == candidate.manifest_id
        for binding in report.bindings
    ):
        raise QualityIntegrityError("quality report does not bind the failed candidate")
    return {
        "failed_evaluation_id": failed.evaluation_id,
        "failed_report_id": report.report_id,
        "policy_id": policy.policy_id,
        "dataset_id": candidate.dataset_id,
        "baseline_manifest_id": baseline.manifest_id,
        "candidate_manifest_id": candidate.manifest_id,
        "predecessor_known_at": baseline.knowledge_end,
        "candidate_known_at": candidate.knowledge_end,
        "failed_overlap_fingerprints": failed.overlap_conflict_fingerprints,
        "conflicts": conflicts,
        "admitted_manifest_ids": admitted,
    }


def _overlap_inspect(root: Path, evaluation_id: str) -> dict[str, Any]:
    context = _overlap_context(root, evaluation_id)
    return {
        key: (
            [item.model_dump(mode="json") for item in value]
            if key == "conflicts"
            else value.isoformat()
            if isinstance(value, datetime)
            else value
        )
        for key, value in context.items()
        if key != "admitted_manifest_ids"
    }


def _overlap_resolve(args: argparse.Namespace) -> dict[str, Any]:
    context = _overlap_context(args.root, args.evaluation)
    supplied = {
        "failed_evaluation_id": args.evaluation,
        "failed_report_id": args.report,
        "policy_id": args.policy,
        "dataset_id": args.dataset,
        "baseline_manifest_id": args.baseline_manifest,
        "candidate_manifest_id": args.candidate_manifest,
    }
    for field, value in supplied.items():
        if context[field] != value:
            raise ValueError(f"supplied {field} does not match immutable overlap evidence")
    fingerprints = tuple(sorted(set(args.fingerprint)))
    if len(fingerprints) != len(args.fingerprint) or fingerprints != tuple(
        item.fingerprint for item in context["conflicts"]
    ):
        raise ValueError("supplied fingerprints do not match the exact conflict set")
    resolution = OverlapResolution.build(
        **supplied,
        conflicts=context["conflicts"],
        predecessor_known_at=context["predecessor_known_at"],
        candidate_known_at=context["candidate_known_at"],
        reviewed_at=args.reviewed_at,
        operator=args.operator,
        reason=args.reason,
        attestation=ResolutionAttestation(args.attestation),
        use_policy=ResolutionUsePolicy(args.use_policy),
    )
    recorded = OverlapResolutionStore(args.root).record(
        resolution,
        admitted_manifest_ids=context["admitted_manifest_ids"],
    )
    return recorded.model_dump(mode="json")


def cli(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
        if args.command == "collect":
            payload = _collect(args)
        elif args.command == "replay":
            payload = _replay(args.root, args.manifest)
        elif args.command == "overlap" and args.overlap_command == "inspect":
            payload = _overlap_inspect(args.root, args.evaluation)
        elif args.command == "overlap":
            payload = _overlap_resolve(args)
        else:
            payload = _inspect(args.root)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        ManifestIntegrityError,
        ObjectIntegrityError,
        CatalogIntegrityError,
        QualityIntegrityError,
        OverlapResolutionIntegrityError,
        CheckpointIntegrityError,
    ) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    except (ValueError, ValidationError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
