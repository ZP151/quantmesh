"""``quantmesh-ops`` operator commands (M10 Phase A/B, issues #58/#59).

``record-metric`` records one metric sample; ``export-audit`` writes
the HMAC-signed audit bundle over the four journals; ``verify-export``
verifies a bundle under the given key; ``recover`` replays the order
journal into a fresh account and reconciles it (the Phase B recovery
drill). All local computation — no network, no credentials beyond the
local key file the operator names explicitly (the keyring backend
lands in Phase E behind the same KeyStore protocol).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.ai.decisions import DecisionLog
from quantmesh.events.mapping import MappingLedger
from quantmesh.execution import OrderJournal
from quantmesh.execution.accounting import DEFAULT_FEE_BPS
from quantmesh.execution.reconciliation import ReconcileTolerance, Severity
from quantmesh.ops.export import export_audit_bundle, verify_audit_bundle
from quantmesh.ops.metrics import Metric, MetricsStore, metric_id
from quantmesh.ops.recover import recover
from quantmesh.ops.secrets import KeyFileStore


def _parse_at(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {text!r}") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"timestamp must be timezone-aware: {text!r}")
    return parsed.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quantmesh-ops",
        description=(
            "QuantMesh operational commands: metric recording, signed "
            "audit exports, and journal recovery drills (M10 Phase A/B)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record-metric", help="record one metric sample")
    record.add_argument("--name", required=True, help="snake_case metric name")
    record.add_argument("--kind", required=True, choices=("gauge", "counter"))
    record.add_argument("--unit", required=True, help="measurement unit")
    record.add_argument("--value", required=True, type=float)
    record.add_argument("--at", type=_parse_at, help="ISO-8601 aware timestamp")
    record.add_argument("--root", type=Path, help="metrics store root (default: settings)")

    export = subparsers.add_parser("export-audit", help="write the signed audit bundle")
    export.add_argument("--out", required=True, type=Path)
    export.add_argument("--key-file", required=True, type=Path)
    export.add_argument("--orders-dir", type=Path, help="order journal root")
    export.add_argument("--mappings-dir", type=Path, help="mapping ledger root")
    export.add_argument("--decisions-dir", type=Path, help="decision log root")
    export.add_argument("--metrics-dir", type=Path, help="metrics store root")

    verify = subparsers.add_parser("verify-export", help="verify a signed audit bundle")
    verify.add_argument("--bundle", required=True, type=Path)
    verify.add_argument("--key-file", required=True, type=Path)

    recover_drill = subparsers.add_parser(
        "recover", help="replay the order journal and reconcile (recovery drill)"
    )
    recover_drill.add_argument("--journal", required=True, type=Path)
    recover_drill.add_argument(
        "--cash", required=True, type=float, help="the account's starting cash"
    )
    recover_drill.add_argument(
        "--fee-bps", type=float, default=DEFAULT_FEE_BPS, help="the account's fee schedule"
    )
    recover_drill.add_argument(
        "--against",
        type=Path,
        help="surviving PaperAccount JSON snapshot to reconcile against",
    )
    recover_drill.add_argument("--qty-bps", type=float, default=0)
    recover_drill.add_argument("--price-bps", type=float, default=0)
    recover_drill.add_argument("--fee-abs", type=float, default=0)
    recover_drill.add_argument("--position-bps", type=float, default=0)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "record-metric":
        store = MetricsStore(root=args.root)
        measured_at = args.at if args.at is not None else datetime.now(UTC)
        metric = Metric(
            id=metric_id(name=args.name, measured_at=measured_at),
            name=args.name,
            kind=args.kind,
            unit=args.unit,
            value=args.value,
            measured_at=measured_at,
        )
        store.record(metric)
        print(f"recorded metric {metric.id} ({metric.name}={metric.value})")
        return 0
    if args.command == "export-audit":
        key = KeyFileStore(args.key_file.parent).get(args.key_file.name)
        if key is None:
            print(f"key file {args.key_file} not found", file=sys.stderr)
            return 2
        export_audit_bundle(
            args.out,
            orders=OrderJournal(root=args.orders_dir).all(),
            mappings=MappingLedger(root=args.mappings_dir).all(),
            decisions=DecisionLog(root=args.decisions_dir).all(),
            metrics=MetricsStore(root=args.metrics_dir).all(),
            key=key,
        )
        print(f"wrote audit bundle {args.out}")
        return 0
    if args.command == "verify-export":
        key = KeyFileStore(args.key_file.parent).get(args.key_file.name)
        if key is None:
            print(f"key file {args.key_file} not found", file=sys.stderr)
            return 2
        try:
            content = verify_audit_bundle(args.bundle, key=key)
        except ValueError as error:
            print(f"verification failed: {error}", file=sys.stderr)
            return 1
        counts = {name: len(rows) for name, rows in content.items()}
        print(f"bundle verifies: {counts}")
        return 0
    if args.command == "recover":
        outcome = recover(
            args.journal,
            cash=args.cash,
            fee_bps=args.fee_bps,
            tolerance=ReconcileTolerance(
                qty_bps=args.qty_bps,
                price_bps=args.price_bps,
                fee_abs=args.fee_abs,
                position_qty_bps=args.position_bps,
            ),
            against=args.against,
        )
        if outcome.refusals:
            for refusal in outcome.refusals:
                print(f"refused: {refusal}", file=sys.stderr)
            return 1
        account = outcome.account
        report = outcome.report
        if account is None or report is None:
            print("recovery produced no account state", file=sys.stderr)
            return 1
        positions = {key: position.quantity for key, position in account.positions.items()}
        print(
            f"replayed {len(outcome.orders)} order(s) -> cash "
            f"{account.cash:.6f}, fees {account.total_fees:.6f}, "
            f"pnl {account.realized_pnl:.6f}, {len(positions)} position(s)"
        )
        print(f"reconciliation {report.counts}")
        for finding in report.findings:
            print(f"{finding.severity.value}: {finding.message}")
        if any(
            finding.severity is Severity.ERROR for finding in report.findings
        ) or report.counts["missing"]:
            return 1
        return 0
    raise AssertionError(f"unhandled command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
