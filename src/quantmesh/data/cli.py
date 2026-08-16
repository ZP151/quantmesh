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
from quantmesh.data.objects import ObjectIntegrityError
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
        return {
            "provider": "hyperliquid-public",
            "read_only": True,
            "code_commit": commit,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "publications": [item.model_dump(mode="json") for item in publications],
        }

    if args.interval not in {"1m", "1d"}:
        raise ValueError("Moomoo interval must be 1m or 1d")
    if any(symbol not in {"AAPL", "NVDA"} for symbol in symbols):
        raise ValueError("Moomoo symbols are limited to AAPL and NVDA")
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
    return {
        "provider": "moomoo-opend",
        "read_only": True,
        "code_commit": commit,
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


def cli(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
        if args.command == "collect":
            payload = _collect(args)
        elif args.command == "replay":
            payload = _replay(args.root, args.manifest)
        else:
            payload = _inspect(args.root)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except (ManifestIntegrityError, ObjectIntegrityError, CatalogIntegrityError) as error:
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
