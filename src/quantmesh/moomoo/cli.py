"""``quantmesh-moomoo`` operator commands (issues #25/#28, Phases A/D).

``probe`` is the only way QuantMesh reaches a real local OpenD instance:
an explicit operator action that prints a redacted capability report,
writes nothing to disk, reads no credentials, and exits with a typed
status code.

``paper-order`` and ``reconcile`` are the simulated-only order surface:
they place orders against a deterministic fixture script and reconcile
the broker's side against the order journal. The live simulated account
(``SdkTradeTransport``) is deliberately unreachable from here until the
Phase E gate (local OpenD + Moomoo simulated-account drill) records a
human decision — until then the commands refuse any invocation that
does not name a ``--fixture`` script.
"""

import argparse
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Side,
    Venue,
)
from quantmesh.domain.orders import Order
from quantmesh.execution import OrderJournal
from quantmesh.moomoo import (
    MoomooExecutionAdapter,
    OpenDUnavailableError,
    ReconcileTolerance,
    SimulatedFixtureTransport,
    apply_reconciliation,
    run_reconciliation,
)
from quantmesh.moomoo.market_data import market_zone
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDSdkMissingError,
)
from quantmesh.settings import Settings, settings

_EXIT_OK = 0
_EXIT_UNAVAILABLE = 1  # probe: OpenD unreachable; reconcile: blocking findings
_EXIT_AUTH_REQUIRED = 2
_EXIT_SDK_MISSING = 3
_EXIT_GATED = 3  # paper-order/reconcile: live path locked behind the Phase E gate


def _build_client(config: Settings) -> MoomooOpenDClient:
    return MoomooOpenDClient.from_settings(config)


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{value!r} is not an ISO instant") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{value!r} has no timezone (use e.g. +00:00)")
    return parsed


def _gate_message() -> str:
    return (
        "live simulated-account trading unlocks at Phase E (local OpenD + "
        "Moomoo simulated-account drill); pass --fixture PATH to replay a "
        "deterministic script instead"
    )


def _add_tolerance_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--qty-bps", type=float, default=0, help="quantity tolerance in bps")
    parser.add_argument("--price-bps", type=float, default=0, help="price tolerance in bps")
    parser.add_argument("--fee-abs", type=float, default=0, help="fee tolerance in currency units")
    parser.add_argument(
        "--time-skew-s", type=float, default=0, help="time skew tolerance in seconds"
    )
    parser.add_argument(
        "--position-qty-bps", type=float, default=0, help="position tolerance in bps"
    )


def _paper_order(args: argparse.Namespace) -> int:
    if args.fixture is None:
        print(_gate_message(), file=sys.stderr)
        return _EXIT_GATED
    market = args.market.upper()
    try:
        market_zone(market)
    except ValueError as error:
        print(f"invalid market: {error}", file=sys.stderr)
        return _EXIT_UNAVAILABLE
    instrument = Instrument(
        symbol=args.symbol.upper(),
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency=args.currency,
        metadata={"market": market},
    )
    request = OrderRequest(
        instrument=instrument,
        side=Side.BUY if args.side == "buy" else Side.SELL,
        quantity=args.qty,
        limit_price=args.price,
        client_order_id=args.client_order_id,
    )
    journal = OrderJournal(root=args.orders_dir)
    transport = SimulatedFixtureTransport(args.fixture)
    adapter = MoomooExecutionAdapter(transport)
    order_id = args.client_order_id or uuid.uuid4().hex
    try:
        order = adapter.place(request, order_id=order_id, created_at=transport.now)
    except OpenDUnavailableError as error:
        # The placement ack was lost but the broker recorded the order;
        # record the unacknowledged order so reconciliation can recover
        # the mapping via the remark channel (ADR-0006 decision 1).
        order = Order.from_request(request, order_id=order_id, created_at=transport.now)
        journal.record(order)
        print(f"warning: {error}")
        print(f"recorded unacknowledged order {order_id} (recovery via remark on next reconcile)")
        return _EXIT_OK
    journal.record(order)
    print(f"placed simulated order {order_id} -> broker id {order.broker_order_id}")
    return _EXIT_OK


def _reconcile(args: argparse.Namespace) -> int:
    if args.fixture is None:
        print(_gate_message(), file=sys.stderr)
        return _EXIT_GATED
    journal = OrderJournal(root=args.orders_dir)
    transport = SimulatedFixtureTransport(args.fixture)
    transport.advance_to(args.at if args.at is not None else transport.end)
    snapshot = transport.snapshot()
    tolerance = ReconcileTolerance(
        qty_bps=args.qty_bps,
        price_bps=args.price_bps,
        fee_abs=args.fee_abs,
        time_skew_s=args.time_skew_s,
        position_qty_bps=args.position_qty_bps,
    )
    report = run_reconciliation(snapshot, journal, tolerance)

    counts = report.counts
    print(
        f"reconcile {counts['matched']} matched, {counts['pending']} pending, "
        f"{counts['missing']} missing, {counts['divergent']} divergent"
    )
    for outcome in report.outcomes:
        label = outcome.internal_order_id or outcome.broker_order_id or "?"
        recovered = " (recovered via remark)" if outcome.recovered_via_remark else ""
        print(f"  [{outcome.status}] {label}{recovered}")
        for finding in outcome.findings:
            print(f"      {finding.severity.value.upper()} {finding.kind.value}: {finding.message}")
    for order_id in report.missing_internal:
        print(f"  [missing] journal order {order_id} has no broker counterpart")
    for finding in report.position_findings:
        print(
            f"  position {finding.severity.value.upper()} "
            f"{finding.kind.value}: {finding.message}"
        )

    has_blocking = any(finding.severity.value == "error" for finding in report.findings)

    if args.apply:
        result = apply_reconciliation(report, journal, snapshot)
        for order_id in sorted(result.updated):
            print(f"  adopted {order_id}")
        for note in result.notes:
            print(f"    {note}")
        for order_id in result.refused:
            print(f"  refused {order_id}")
    return _EXIT_UNAVAILABLE if has_blocking else _EXIT_OK


def _probe() -> int:
    client = _build_client(settings)
    try:
        caps = client.probe()
    except OpenDSdkMissingError as error:
        print(f"sdk missing: {error}", file=sys.stderr)
        return _EXIT_SDK_MISSING
    except OpenDAuthRequiredError as error:
        print(f"auth required: {error}", file=sys.stderr)
        return _EXIT_AUTH_REQUIRED
    except OpenDUnavailableError as error:
        print(f"opend unavailable: {error}", file=sys.stderr)
        return _EXIT_UNAVAILABLE
    finally:
        client.close()
    print(
        "OpenD capabilities: "
        f"quote={caps.quote} history_kline={caps.history_kline} "
        f"order={caps.order} order_query={caps.order_query} "
        f"auth_required={caps.auth_required}"
    )
    return _EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quantmesh-moomoo",
        description=(
            "Moomoo OpenD operator commands (fixture-first; probe is read-only, "
            "trading is simulated-only until the Phase E gate)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("probe", help="capability probe of a local OpenD")

    paper = subparsers.add_parser(
        "paper-order", help="place a simulated order against a fixture script"
    )
    paper.add_argument("--symbol", required=True)
    paper.add_argument("--market", required=True, help="US | HK | CN (SDK code prefix)")
    paper.add_argument("--side", choices=["buy", "sell"], default="buy")
    paper.add_argument("--qty", type=_positive_float, required=True)
    paper.add_argument(
        "--price",
        type=_positive_float,
        default=None,
        help="limit price (market order if omitted)",
    )
    paper.add_argument("--currency", default="USD")
    paper.add_argument(
        "--client-order-id",
        default=None,
        help="order id and remark (else generated)",
    )
    paper.add_argument(
        "--fixture", default=None, help="JSONL fixture script (the live path is Phase E-gated)"
    )
    paper.add_argument("--orders-dir", type=Path, default=settings.orders_dir)

    reconcile = subparsers.add_parser(
        "reconcile", help="reconcile the broker snapshot against the order journal"
    )
    reconcile.add_argument(
        "--fixture", default=None, help="JSONL fixture script (the live path is Phase E-gated)"
    )
    reconcile.add_argument(
        "--at",
        type=_parse_iso,
        default=None,
        help="replay up to this ISO instant (default: the script's end)",
    )
    reconcile.add_argument("--orders-dir", type=Path, default=settings.orders_dir)
    reconcile.add_argument(
        "--apply",
        action="store_true",
        help="adopt broker-confirmed progress (default: report only)",
    )
    _add_tolerance_args(reconcile)

    args = parser.parse_args(argv)

    if args.command == "probe":
        return _probe()
    if args.command == "paper-order":
        return _paper_order(args)
    if args.command == "reconcile":
        return _reconcile(args)
    parser.error(f"unknown command {args.command!r}")  # unreachable
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
