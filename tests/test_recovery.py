"""M10 Phase B tests (issue #59): idempotency keys on the paper
kernel and journal recovery drills.

The idempotency suite pins the typed replay contract: a keyed
submission derives the order id, a replay returns the original order
with ``replay_of`` naming it — never duplicated, never re-gated, never
consuming a sequence number — and keys participate in journal identity
(a duplicate key in the file fails the read closed).

The recovery suite drills the fail-closed journal read (partial
append, truncated tail, duplicate keys, unbookable replay), the pure
event replay (recovered account equals the live account, mid-lifecycle
orders preserved as recorded), the event-history verification (a
hand-edited order is named, never replayed) and the ADR-0006
reconciliation against a surviving snapshot (matched counts, orphaned
orders, position and quantity divergence, declared tolerances) —
acceptance criterion 3's evidence.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.domain.orders import Order, OrderEvent, OrderStatus
from quantmesh.execution import OrderJournal
from quantmesh.execution.accounting import PaperAccount
from quantmesh.execution.journal import JOURNAL_FILE
from quantmesh.execution.reconciliation import ReconcileTolerance
from quantmesh.ops.recover import (
    read_journal_lines,
    reconcile_recovered,
    recover,
    replay_orders,
    verify_event_history,
)

T0 = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)
CASH = 10_000.0
KEY = "buy-aapl-001"


def _request(
    *,
    side: Side = Side.BUY,
    quantity: float = 10,
    limit_price: float | None = None,
    key: str | None = None,
) -> OrderRequest:
    return OrderRequest(
        instrument=INSTRUMENT,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        idempotency_key=key,
    )


def _quote(now: datetime) -> Quote:
    return Quote(
        instrument=INSTRUMENT, timestamp=now, bid=99.0, ask=100.0, volume=100
    )


def _live_universe(
    tmp_path: Path, *, cash: float = CASH
) -> tuple[PaperAccount, OrderJournal]:
    """A live account with four orders through the kernel — filled
    buy, partial close, an accepted-but-unfilled limit, a rejection —
    and their journal, the crash-mid-stream drill universe."""
    account = PaperAccount(cash=cash)
    journal = OrderJournal(root=tmp_path / "orders")
    steps: list[tuple[OrderRequest, datetime]] = [
        (_request(side=Side.BUY, quantity=10, key="buy-aapl-001"), T0),
        (
            _request(side=Side.SELL, quantity=4, key="sell-aapl-002"),
            T0 + timedelta(seconds=1),
        ),
        (
            _request(side=Side.BUY, quantity=10, limit_price=90.0, key="limit-aapl-003"),
            T0 + timedelta(seconds=2),
        ),
        (_request(side=Side.BUY, quantity=100, key="reject-aapl-004"), T0 + timedelta(seconds=3)),
    ]
    for request, at in steps:
        result = account.submit(request, _quote(at), now=at)
        journal.record(result.order)
        account = result.account
    return account, journal


class TestIdempotencyKeys:
    def test_keyed_submission_replays_original_typed(self) -> None:
        account = PaperAccount(cash=CASH)
        first = account.submit(_request(key=KEY), _quote(T0), now=T0)
        assert first.order.order_id == f"paper-{KEY}"
        replay = first.account.submit(_request(key=KEY), _quote(T0), now=T0)
        assert replay.replay_of == first.order.order_id
        assert replay.order.order_id == first.order.order_id
        assert replay.order is first.order
        assert replay.fills == []
        # Never duplicated, never re-consumed: account state is unchanged.
        assert len(replay.account.orders) == 1
        assert replay.account.order_sequence == first.account.order_sequence
        assert replay.account.cash == first.account.cash
        assert replay.account.positions == first.account.positions

    def test_replay_never_re_runs_the_risk_gate(self) -> None:
        # The keyed submission is REJECTED (100 shares against 10k cash).
        account = PaperAccount(cash=CASH)
        first = account.submit(_request(quantity=100, key=KEY), _quote(T0), now=T0)
        assert first.rejection is not None
        assert first.order.status is OrderStatus.REJECTED
        replay = first.account.submit(_request(quantity=100, key=KEY), _quote(T0), now=T0)
        assert replay.replay_of == first.order.order_id
        assert replay.order.status is first.order.status
        assert replay.rejection is None  # nothing re-evaluated
        assert len(replay.account.orders) == 1

    def test_replay_never_re_applies_fills(self) -> None:
        account = PaperAccount(cash=CASH)
        first = account.submit(_request(quantity=10, key=KEY), _quote(T0), now=T0)
        assert first.fills  # filled on the original
        replay = first.account.submit(_request(quantity=10, key=KEY), _quote(T0), now=T0)
        assert replay.fills == []
        assert replay.account.cash == first.account.cash
        assert replay.account.positions == first.account.positions

    def test_different_key_is_a_new_order(self) -> None:
        account = PaperAccount(cash=CASH)
        first = account.submit(_request(key="buy-aapl-001"), _quote(T0), now=T0)
        second = first.account.submit(_request(key="buy-aapl-002"), _quote(T0), now=T0)
        assert second.order.order_id != first.order.order_id
        assert second.replay_of is None
        assert len(second.account.orders) == 2

    def test_key_colliding_with_unkeyed_id_is_refused(self) -> None:
        account = PaperAccount(cash=CASH)
        account = account.submit(_request(key=None), _quote(T0), now=T0).account
        account = account.submit(
            _request(key=None), _quote(T0 + timedelta(seconds=1)), now=T0 + timedelta(seconds=1)
        ).account  # paper-2
        with pytest.raises(ValueError, match="order id already exists"):
            account.submit(
                _request(key="2"), _quote(T0 + timedelta(seconds=2)), now=T0 + timedelta(seconds=2)
            )

    def test_invalid_key_shape_refused_at_the_boundary(self) -> None:
        with pytest.raises(ValueError, match="idempotency_key"):
            _request(key="bad key!")

    def test_key_recorded_in_journal_and_duplicate_key_refused(
        self, tmp_path: Path
    ) -> None:
        journal = OrderJournal(root=tmp_path / "orders")
        account = PaperAccount(cash=CASH)
        result = account.submit(_request(key=KEY), _quote(T0), now=T0)
        journal.record(result.order)
        assert journal.all()[0].idempotency_key == KEY
        # A duplicate key in the file participates in journal identity:
        # the read fails closed instead of replaying a duplicate.
        forged = result.order.model_copy(update={"order_id": "paper-x", "events": []})
        (tmp_path / "orders" / JOURNAL_FILE).write_text(
            result.order.model_dump_json() + "\n" + forged.model_dump_json() + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="share an idempotency key"):
            journal.all()

    def test_client_order_id_still_derives_identity(self) -> None:
        account = PaperAccount(cash=CASH)
        request = _request(key=KEY).model_copy(update={"client_order_id": "cloid-001"})
        first = account.submit(request, _quote(T0), now=T0)
        assert first.order.order_id == "cloid-001"
        assert first.order.idempotency_key == KEY
        replay = first.account.submit(request, _quote(T0), now=T0)
        assert replay.replay_of == "cloid-001"

    def test_same_key_with_regenerated_client_id_is_still_a_replay(
        self,
    ) -> None:
        # The key is the replay unit: a retry that regenerates the
        # client_order_id (a naive retry wrapper rebuilds the request)
        # must not duplicate the order — the original is returned.
        account = PaperAccount(cash=CASH)
        first = account.submit(
            _request(key=KEY).model_copy(update={"client_order_id": "cloid-001"}),
            _quote(T0),
            now=T0,
        )
        assert first.fills
        retry = first.account.submit(
            _request(key=KEY).model_copy(update={"client_order_id": "cloid-002"}),
            _quote(T0),
            now=T0,
        )
        assert retry.replay_of == "cloid-001"
        assert retry.order.order_id == "cloid-001"
        assert retry.fills == []
        assert len(retry.account.orders) == 1
        assert retry.account.cash == first.account.cash


class TestRecoveryDrills:
    def test_replay_matches_live_account_exactly(self, tmp_path: Path) -> None:
        live, journal = _live_universe(tmp_path)
        replayed = replay_orders(journal.all(), cash=CASH)
        assert replayed.cash == live.cash
        assert replayed.total_fees == live.total_fees
        assert replayed.realized_pnl == live.realized_pnl
        assert replayed.positions == live.positions
        assert set(replayed.orders) == set(live.orders)
        for order_id in live.orders:
            assert replayed.orders[order_id] == live.orders[order_id]

    def test_crash_mid_stream_replays_midlifecycle_order_as_recorded(
        self, tmp_path: Path
    ) -> None:
        _, journal = _live_universe(tmp_path)
        outcome = recover(tmp_path / "orders", cash=CASH)
        assert outcome.clean
        assert outcome.report is not None
        assert outcome.report.counts == {
            "matched": 4,
            "pending": 0,
            "missing": 0,
            "divergent": 0,
        }
        assert outcome.report.findings == []
        # The accepted-but-unfilled limit order stays unacknowledged —
        # no fabricated fill, no fabricated state.
        limit = next(
            order
            for order in journal.all()
            if order.idempotency_key == "limit-aapl-003"
        )
        replayed = outcome.account
        assert replayed is not None
        assert replayed.orders[limit.order_id].status is limit.status
        assert replayed.orders[limit.order_id].fills == []

    def test_partial_append_refused_with_line_attribution(self, tmp_path: Path) -> None:
        _, journal = _live_universe(tmp_path)
        path = tmp_path / "orders" / JOURNAL_FILE
        text = path.read_text(encoding="utf-8")
        path.write_text(text[: len(text) // 2], encoding="utf-8")
        orders, refusals = read_journal_lines(tmp_path / "orders")
        assert refusals, "a truncated journal must refuse, never partially replay"
        assert orders  # valid lines parse; the replay is gated on refusals
        outcome = recover(tmp_path / "orders", cash=CASH)
        assert not outcome.clean
        assert outcome.account is None  # nothing was replayed
        assert outcome.report is None
        assert any("is invalid" in refusal for refusal in outcome.refusals)

    def test_truncated_tail_refused(self, tmp_path: Path) -> None:
        _, journal = _live_universe(tmp_path)
        path = tmp_path / "orders" / JOURNAL_FILE
        lines = path.read_text(encoding="utf-8").splitlines()
        # Cut the last record mid-JSON: the final line is unparseable.
        cut = lines[-1][: len(lines[-1]) // 2]
        path.write_text("\n".join(lines[:-1] + [cut]) + "\n", encoding="utf-8")
        outcome = recover(tmp_path / "orders", cash=CASH)
        assert not outcome.clean
        assert outcome.account is None
        assert any("is invalid" in refusal for refusal in outcome.refusals)

    def test_duplicate_key_in_journal_refused(self, tmp_path: Path) -> None:
        _, journal = _live_universe(tmp_path)
        path = tmp_path / "orders" / JOURNAL_FILE
        first = journal.all()[0]
        forged = first.model_copy(update={"order_id": "paper-forged", "events": []})
        path.write_text(
            first.model_dump_json() + "\n" + forged.model_dump_json() + "\n",
            encoding="utf-8",
        )
        outcome = recover(tmp_path / "orders", cash=CASH)
        assert not outcome.clean
        assert any(
            "share an idempotency key" in refusal for refusal in outcome.refusals
        )

    def test_event_history_inconsistency_named(self, tmp_path: Path) -> None:
        _, journal = _live_universe(tmp_path)
        orders = journal.all()
        order = orders[0]  # FILLED with fill events
        forged = order.model_copy(update={"status": OrderStatus.ACCEPTED})
        assert verify_event_history(forged)  # filled history vs accepted state
        path = tmp_path / "orders" / JOURNAL_FILE
        others = [o for o in orders if o.order_id != order.order_id]
        path.write_text(
            "\n".join(o.model_dump_json() for o in [forged, *others]) + "\n",
            encoding="utf-8",
        )
        outcome = recover(tmp_path / "orders", cash=CASH)
        assert not outcome.clean
        assert outcome.report is not None
        assert any(
            "disagrees with its event history" in f.message
            for f in outcome.report.findings
        )

    def test_replay_refused_on_unbookable_fill(self, tmp_path: Path) -> None:
        # A hand-forged SELL fill with no prior position cannot re-book.
        request = _request(side=Side.SELL, quantity=10, key="sell-x")
        order = Order.from_request(request, order_id="paper-sell-x", created_at=T0)
        order = order.model_copy(
            update={
                "status": OrderStatus.FILLED,
                "filled_quantity": 10,
                "events": [
                    OrderEvent(
                        sequence=1,
                        timestamp=T0,
                        event_type="accepted",
                        status=OrderStatus.ACCEPTED,
                    ),
                    OrderEvent(
                        sequence=2,
                        timestamp=T0,
                        event_type="fill",
                        status=OrderStatus.FILLED,
                        quantity=10,
                        price=100.0,
                    ),
                ],
            }
        )
        root = tmp_path / "orders"
        root.mkdir()
        (root / JOURNAL_FILE).write_text(
            order.model_dump_json() + "\n", encoding="utf-8"
        )
        outcome = recover(root, cash=CASH)
        assert not outcome.clean
        assert any("replay refused" in refusal for refusal in outcome.refusals)
        assert outcome.account is None

    def test_empty_journal_recovers_clean(self, tmp_path: Path) -> None:
        outcome = recover(tmp_path / "orders", cash=CASH)
        assert outcome.clean
        assert outcome.orders == []
        assert outcome.account is not None
        assert outcome.account.cash == CASH
        assert outcome.report is not None
        assert outcome.report.counts["matched"] == 0

    def test_missing_order_in_snapshot_detected(self, tmp_path: Path) -> None:
        live, _ = _live_universe(tmp_path)
        removed = next(iter(live.orders))
        snapshot = live.model_copy(
            update={"orders": {k: v for k, v in live.orders.items() if k != removed}}
        )
        (tmp_path / "snap.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
        outcome = recover(tmp_path / "orders", cash=CASH, against=tmp_path / "snap.json")
        assert not outcome.clean
        assert outcome.report is not None
        assert removed in outcome.report.missing_internal
        assert outcome.report.counts["missing"] == 1

    def test_orphaned_account_order_detected(self, tmp_path: Path) -> None:
        live, _ = _live_universe(tmp_path)
        forged = Order.from_request(
            _request(key="forged-001"), order_id="paper-forged-001", created_at=T0
        )
        snapshot = live.model_copy(
            update={"orders": {**live.orders, forged.order_id: forged}}
        )
        (tmp_path / "snap.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
        outcome = recover(tmp_path / "orders", cash=CASH, against=tmp_path / "snap.json")
        assert not outcome.clean
        assert outcome.report is not None
        assert any("orphaned" in f.message for f in outcome.report.findings)
        assert any(o.status == "divergent" for o in outcome.report.outcomes)

    def test_position_divergence_detected_and_tolerance_applies(
        self, tmp_path: Path
    ) -> None:
        live, _ = _live_universe(tmp_path)
        key = next(iter(live.positions))
        drifted = live.positions[key].model_copy(update={"quantity": 5.9999})
        snapshot = live.model_copy(update={"positions": {key: drifted}})
        (tmp_path / "snap.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
        exact = recover(tmp_path / "orders", cash=CASH, against=tmp_path / "snap.json")
        assert not exact.clean
        assert exact.report is not None
        assert any(f.kind.value == "position" for f in exact.report.findings)
        tolerant = recover(
            tmp_path / "orders",
            cash=CASH,
            tolerance=ReconcileTolerance(position_qty_bps=10),
            against=tmp_path / "snap.json",
        )
        assert tolerant.clean
        assert tolerant.report is not None
        assert tolerant.report.findings == []

    def test_reconcile_recovered_against_replay_is_clean(self, tmp_path: Path) -> None:
        _, journal = _live_universe(tmp_path)
        replayed = replay_orders(journal.all(), cash=CASH)
        report = reconcile_recovered(journal.all(), replayed)
        assert report.findings == []
        assert report.counts == {
            "matched": 4,
            "pending": 0,
            "missing": 0,
            "divergent": 0,
        }


class TestRecoveryCli:
    def _cli(self) -> object:
        from quantmesh.ops.cli import main

        return main

    def test_cli_recover_round_trip_exit_0(self, tmp_path: Path) -> None:
        main = self._cli()
        live, _ = _live_universe(tmp_path)
        (tmp_path / "snap.json").write_text(live.model_dump_json(), encoding="utf-8")
        assert (
            main(
                [
                    "recover",
                    "--journal",
                    str(tmp_path / "orders"),
                    "--cash",
                    "10000",
                    "--against",
                    str(tmp_path / "snap.json"),
                ]
            )
            == 0
        )

    def test_cli_recover_corrupt_journal_exits_1(self, tmp_path: Path) -> None:
        main = self._cli()
        _, journal = _live_universe(tmp_path)
        path = tmp_path / "orders" / JOURNAL_FILE
        text = path.read_text(encoding="utf-8")
        path.write_text(text[: len(text) // 2], encoding="utf-8")
        assert (
            main(["recover", "--journal", str(tmp_path / "orders"), "--cash", "10000"])
            == 1
        )

    def test_cli_recover_divergent_snapshot_exits_1(self, tmp_path: Path) -> None:
        main = self._cli()
        live, _ = _live_universe(tmp_path)
        snapshot = live.model_copy(update={"positions": {}})
        (tmp_path / "snap.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
        assert (
            main(
                [
                    "recover",
                    "--journal",
                    str(tmp_path / "orders"),
                    "--cash",
                    "10000",
                    "--against",
                    str(tmp_path / "snap.json"),
                ]
            )
            == 1
        )

    def test_cli_recover_quantity_tolerance_exits(self, tmp_path: Path) -> None:
        main = self._cli()
        live, _ = _live_universe(tmp_path)
        first = next(iter(live.orders))
        order = live.orders[first]
        drifted = order.model_copy(
            update={"filled_quantity": order.filled_quantity - 0.0005}
        )
        snapshot = live.model_copy(
            update={"orders": {**live.orders, first: drifted}}
        )
        (tmp_path / "snap.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
        # 0.0005/10 = 0.5 bps: exact refuses, a 100 bps tolerance accepts.
        assert (
            main(
                [
                    "recover",
                    "--journal",
                    str(tmp_path / "orders"),
                    "--cash",
                    "10000",
                    "--against",
                    str(tmp_path / "snap.json"),
                    "--qty-bps",
                    "0",
                ]
            )
            == 1
        )
        assert (
            main(
                [
                    "recover",
                    "--journal",
                    str(tmp_path / "orders"),
                    "--cash",
                    "10000",
                    "--against",
                    str(tmp_path / "snap.json"),
                    "--qty-bps",
                    "100",
                ]
            )
            == 0
        )
