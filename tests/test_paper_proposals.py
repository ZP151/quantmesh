from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, Quote, Side, Venue
from quantmesh.execution.accounting import PaperAccount, RiskLimits
from quantmesh.execution.journal import OrderJournal
from quantmesh.instruments.contracts import (
    CoverageSnapshot,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
)
from quantmesh.instruments.forecast import run_price_forecast
from quantmesh.instruments.proposals import PaperDecisionService, ProposalLedger
from quantmesh.live.contract import Provenance, UpdateKind
from quantmesh.live.feed import ExactUpdateSnapshot
from quantmesh.live.fence import QuoteFence

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
NVDA = Instrument(
    symbol="NVDA",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)


class ForecastCatalog:
    def __init__(self, artifact) -> None:  # noqa: ANN001
        self.artifact = artifact

    def get(self, artifact_id: str):  # noqa: ANN201
        if artifact_id != self.artifact.id:
            raise ValueError(f"forecast artifact {artifact_id!r} is unavailable")
        return self.artifact


class UnavailableForecastCatalog:
    def get(self, artifact_id: str):  # noqa: ANN201
        raise ValueError(f"forecast artifact {artifact_id!r} is unavailable")


@lru_cache(maxsize=2)
def _artifact(*, eligible: bool = True):  # noqa: ANN202
    timestamp = NOW
    dates: list[datetime] = []
    count = 650 if eligible else 420
    while len(dates) < count:
        if timestamp.weekday() < 5:
            dates.append(timestamp)
        timestamp -= timedelta(days=1)
    dates.reverse()
    bars = tuple(
        HistoricalBar(
            instrument=NVDA,
            timestamp=stamp,
            interval="1d",
            open=price * 0.999,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=1_000_000,
        )
        for index, stamp in enumerate(dates)
        for price in [100 * math.exp(0.0006 * index + 0.01 * math.sin(index / 7))]
    )
    series = HistoricalSeries(
        instrument=NVDA,
        range=HistoryRange.ONE_YEAR,
        as_of=dates[-1],
        bars=bars,
        dataset_id="proposal-fixture",
        dataset_revision=1,
        source="operator-import",
        license="operator-supplied",
        generated_at=dates[-1],
        interval="1d",
        calendar="XNYS",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval="1d",
            venue=Venue.MOOMOO,
            symbol="NVDA",
            start=dates[0],
            end=dates[-1],
            rows=len(dates),
        ),
    )
    artifact = run_price_forecast(
        series, generated_at=series.as_of, model_version="drift-conformal-v1"
    )
    assert artifact.eligible is eligible
    return artifact


def _snapshot(*, received_at: datetime = NOW, gap: bool = False) -> ExactUpdateSnapshot:
    return ExactUpdateSnapshot(
        venue=Venue.MOOMOO,
        instrument="NVDA",
        kind=UpdateKind.QUOTE,
        source="moomoo",
        provenance=Provenance.REAL,
        data_time=received_at,
        received_at=received_at,
        sequence=2,
        sequence_gap=gap,
        payload={
            "bid": 100.0,
            "ask": 100.1,
            "bid_size": 1_000.0,
            "ask_size": 1_000.0,
        },
        continuity_proven=not gap,
        predecessor_sequence=1,
        predecessor_data_time=received_at - timedelta(milliseconds=1),
        freshness_label="real",
        age_ms=0,
    )


def _service(
    tmp_path: Path,
    *,
    artifact=None,  # noqa: ANN001
    account: PaperAccount | None = None,
    snapshot=None,  # noqa: ANN001
    journal: OrderJournal | None | bool = True,
    demo_quote=None,  # noqa: ANN001
):
    selected = artifact or _artifact()
    state = {"account": account or PaperAccount(cash=100_000)}
    actual_journal = OrderJournal(tmp_path / "orders") if journal is True else journal
    service = PaperDecisionService(
        ledger=ProposalLedger(tmp_path / "proposals"),
        forecast_registry=ForecastCatalog(selected),
        account_provider=lambda: state["account"],
        account_sink=lambda value: state.__setitem__("account", value),
        journal=actual_journal,
        snapshot_provider=lambda _instrument, _now: (
            snapshot if snapshot is not None else _snapshot()
        ),
        quote_fence=QuoteFence(),
        demo_quote_provider=demo_quote,
        now=lambda: NOW,
    )
    return service, state, actual_journal


def test_proposal_is_a_preview_and_pins_the_forecast_without_ordering(tmp_path: Path) -> None:
    artifact = _artifact()
    service, state, journal = _service(tmp_path, artifact=artifact)

    proposal = service.propose(artifact.id, side=Side.BUY, quantity=10)

    assert proposal.status == "pending"
    assert proposal.artifact_id == artifact.id
    assert proposal.dataset_id == artifact.dataset_id
    assert proposal.dataset_revision == artifact.dataset_revision
    assert proposal.instrument == artifact.instrument
    assert proposal.confirmation_token
    assert state["account"].orders == {}
    assert journal.all() == []


def test_ledger_recovery_is_chronological_not_hash_id_order(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    times = iter(NOW + timedelta(seconds=index) for index in range(8))
    service._now = lambda: next(times)  # noqa: SLF001 - deterministic ledger probe

    created = tuple(
        service.propose(_artifact().id, side=Side.BUY, quantity=float(index + 1))
        for index in range(8)
    )

    assert service.ledger.all() == created


def test_ineligible_forecast_creates_a_blocked_non_confirmable_record(tmp_path: Path) -> None:
    artifact = _artifact(eligible=False)
    service, _, journal = _service(tmp_path, artifact=artifact)

    proposal = service.propose(artifact.id, side=Side.BUY, quantity=1)
    result = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)

    assert proposal.status == "blocked"
    assert proposal.blockers == artifact.blockers
    assert result.proposal.status == "blocked"
    assert result.order is None
    assert result.blocker == "; ".join(artifact.blockers)
    assert journal.all() == []


def test_confirm_requires_exact_operator_token_then_crosses_quote_fence(tmp_path: Path) -> None:
    service, state, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=10)

    refused = service.confirm(proposal.id, confirmation="", now=NOW)
    confirmed = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)

    assert refused.proposal.status == "pending"
    assert refused.order is None
    assert refused.blocker == "operator confirmation token does not match"
    assert confirmed.proposal.status == "confirmed"
    assert confirmed.order is not None
    assert confirmed.order.idempotency_key == f"proposal:{proposal.id}"
    assert confirmed.proposal.order_id == confirmed.order.order_id
    assert len(journal.all()) == 1
    assert state["account"].positions["moomoo:NVDA"].quantity == 10


def test_confirmation_binds_a_resting_limit_without_fabricating_a_fill(
    tmp_path: Path,
) -> None:
    service, state, journal = _service(tmp_path)
    proposal = service.propose(
        _artifact().id,
        side=Side.BUY,
        quantity=10,
        limit_price=99.0,
    )

    confirmed = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )
    replayed = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )

    assert confirmed.proposal.status == "confirmed"
    assert confirmed.proposal.order_id == confirmed.order.order_id
    assert confirmed.order.status == "accepted"
    assert confirmed.order.filled_quantity == 0
    assert confirmed.order.limit_price == 99.0
    assert confirmed.quote_provenance == "real"
    assert replayed == confirmed
    assert journal.all() == [state["account"].orders[confirmed.order.order_id]]
    assert "moomoo:NVDA" not in state["account"].positions
    assert len(service.ledger.events(proposal.id)) == 2


def test_confirmation_replay_is_exactly_once_even_concurrently(tmp_path: Path) -> None:
    service, state, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: service.confirm(
                    proposal.id,
                    confirmation=proposal.confirmation_token,
                    now=NOW,
                ),
                range(20),
            )
        )

    assert {result.order.order_id for result in results if result.order} == {
        results[0].order.order_id
    }
    assert len(journal.all()) == 1
    assert state["account"].positions["moomoo:NVDA"].quantity == 1
    assert len(service.ledger.events(proposal.id)) == 2


def test_two_service_instances_share_one_exactly_once_confirmation_boundary(
    tmp_path: Path,
) -> None:
    first, first_state, journal = _service(tmp_path)
    second, second_state, _ = _service(tmp_path)
    proposal = first.propose(_artifact().id, side=Side.BUY, quantity=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda service: service.confirm(
                    proposal.id,
                    confirmation=proposal.confirmation_token,
                    now=NOW,
                ),
                (first, second),
            )
        )

    assert results[0] == results[1]
    assert len(journal.all()) == 1
    assert len(first.ledger.events(proposal.id)) == 2
    assert all(
        state["account"].positions["moomoo:NVDA"].quantity == 1
        for state in (first_state, second_state)
    )


@pytest.mark.parametrize(
    ("account", "snapshot", "reason"),
    [
        (PaperAccount(cash=100_000, kill_switch=True), _snapshot(), "kill switch enabled"),
        (
            PaperAccount(cash=100_000),
            _snapshot(received_at=NOW - timedelta(minutes=2)),
            "quote is 120 s old; the fence horizon is 30 s",
        ),
        (
            PaperAccount(cash=100_000),
            _snapshot(gap=True),
            "quote sequence is discontinuous — the venue dropped updates",
        ),
        (
            PaperAccount(
                cash=100_000,
                risk_limits=RiskLimits(max_order_quantity=1),
            ),
            _snapshot(),
            "order quantity 10.0 exceeds limit 1.0",
        ),
    ],
)
def test_kernel_refusals_are_preserved_verbatim_and_never_retried(
    tmp_path: Path,
    account: PaperAccount,
    snapshot: dict[str, object],
    reason: str,
) -> None:
    service, state, journal = _service(tmp_path, account=account, snapshot=snapshot)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=10)

    refused = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)
    replay = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)

    assert refused.proposal.status == "rejected"
    assert refused.blocker == reason
    assert replay == refused
    assert len(journal.all()) == 1
    assert len(state["account"].orders) == 1


def test_missing_journal_fails_before_submission_and_remains_retryable(tmp_path: Path) -> None:
    service, state, _ = _service(tmp_path, journal=None)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    result = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)

    assert result.proposal.status == "pending"
    assert result.blocker == "paper order journal is not bound"
    assert state["account"].orders == {}


def test_confirmation_time_cannot_regress_before_paper_submission(tmp_path: Path) -> None:
    service, state, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    with pytest.raises(ValueError, match="cannot predate proposal creation"):
        service.confirm(
            proposal.id,
            confirmation=proposal.confirmation_token,
            now=NOW - timedelta(seconds=1),
        )

    assert service.ledger.get(proposal.id).status == "pending"
    assert state["account"].orders == {}
    assert journal.all() == []


def test_forecast_that_ages_after_preview_is_blocked_before_order(tmp_path: Path) -> None:
    service, state, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    result = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW + timedelta(days=5),
    )

    assert result.proposal.status == "blocked"
    assert "maximum is one session" in result.blocker
    assert state["account"].orders == {}
    assert journal.all() == []


def test_later_retry_recovers_after_order_was_journaled_before_proposal_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, state, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    transition = service.ledger.transition
    calls = 0

    def fail_once(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated ledger replace failure")
        return transition(*args, **kwargs)

    monkeypatch.setattr(service.ledger, "transition", fail_once)
    with pytest.raises(OSError, match="simulated"):
        service.confirm(
            proposal.id,
            confirmation=proposal.confirmation_token,
            now=NOW,
        )

    service._forecast_registry = UnavailableForecastCatalog()  # noqa: SLF001
    recovered = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW + timedelta(days=5),
    )

    assert recovered.proposal.status == "confirmed"
    assert service.ledger.events(proposal.id)[-1].recorded_at == NOW
    assert len(journal.all()) == 1
    assert state["account"].positions["moomoo:NVDA"].quantity == 1


def test_demo_quote_must_be_explicitly_injected_and_is_marked_in_confirmation(
    tmp_path: Path,
) -> None:
    def demo_quote(instrument: Instrument, now: datetime) -> Quote:
        return Quote(
            instrument=instrument,
            timestamp=now,
            bid=99.9,
            ask=100.0,
            last=100.0,
            volume=1_000,
        )

    service, _, _ = _service(
        tmp_path,
        snapshot={},
        demo_quote=demo_quote,
    )
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    result = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)

    assert result.proposal.status == "confirmed"
    assert result.quote_provenance == "demo-synthetic"


@pytest.mark.parametrize(
    ("quote_factory", "reason"),
    [
        (
            lambda _instrument, now: Quote(
                instrument=Instrument(
                    symbol="SOL-USD",
                    venue=Venue.HYPERLIQUID,
                    instrument_type=InstrumentType.SPOT,
                ),
                timestamp=now,
                bid=99.9,
                ask=100.0,
            ),
            "demo quote instrument does not match proposal instrument",
        ),
        (
            lambda instrument, now: Quote(
                instrument=instrument,
                timestamp=now + timedelta(seconds=1),
                bid=99.9,
                ask=100.0,
            ),
            "demo quote timestamp is in the future",
        ),
        (
            lambda instrument, now: Quote(
                instrument=instrument.model_copy(update={"currency": "EUR"}),
                timestamp=now,
                bid=99.9,
                ask=100.0,
            ),
            "demo quote instrument does not match proposal instrument",
        ),
    ],
)
def test_demo_quote_must_match_instrument_and_time(
    tmp_path: Path,
    quote_factory,
    reason: str,
) -> None:
    service, state, journal = _service(tmp_path, demo_quote=quote_factory)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    result = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )

    assert result.proposal.status == "blocked"
    assert result.blocker == reason
    assert state["account"].orders == {}
    assert journal.all() == []


def test_future_real_quote_is_rejected_by_the_paper_kernel(tmp_path: Path) -> None:
    service, _, journal = _service(
        tmp_path,
        snapshot=_snapshot(received_at=NOW + timedelta(seconds=1)),
    )
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)

    result = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )

    assert result.proposal.status == "rejected"
    assert result.blocker == "quote receipt time is in the future"
    assert len(journal.all()) == 1


def test_terminal_replay_rejects_a_journal_order_that_changed_intent(tmp_path: Path) -> None:
    service, _, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    confirmed = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )
    order = journal.get(confirmed.order.order_id)
    journal.update(order.model_copy(update={"quantity": 999.0}))

    with pytest.raises(ValueError, match="invalid derived state"):
        service.confirm(
            proposal.id,
            confirmation=proposal.confirmation_token,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"broker_order_id": "forged-broker-order"}, "immutable proposal intent"),
        ({"client_order_id": "forged-client-order"}, "immutable proposal intent"),
        ({"created_at": NOW + timedelta(seconds=1)}, "invalid derived state"),
    ],
)
def test_terminal_replay_rejects_unexpected_order_identity_fields(
    tmp_path: Path,
    update: dict[str, object],
    reason: str,
) -> None:
    service, _, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    confirmed = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )
    order = journal.get(confirmed.order.order_id)
    journal.update(order.model_copy(update=update))

    with pytest.raises(ValueError, match=reason):
        service.confirm(
            proposal.id,
            confirmation=proposal.confirmation_token,
            now=NOW,
        )


def test_confirmation_order_snapshot_is_deeply_immutable(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    result = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )

    with pytest.raises(Exception):
        result.order.quantity = 777
    with pytest.raises(Exception):
        result.order.events += result.order.events


def test_ledger_rejects_tampering_partial_lines_and_illegal_transitions(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    ledger_path = tmp_path / "proposals" / "proposals.jsonl"
    ledger_path.write_text(
        ledger_path.read_text(encoding="utf-8") + "{partial\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 2"):
        service.ledger.get(proposal.id)


def test_ledger_recomputes_the_proposal_identity_seal(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    ledger_path = tmp_path / "proposals" / "proposals.jsonl"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["proposal"]["quantity"] = 2.0
    ledger_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="id does not match its immutable intent"):
        service.ledger.get(proposal.id)


def test_ledger_seal_covers_the_complete_instrument_and_forecast_lineage(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    ledger_path = tmp_path / "proposals" / "proposals.jsonl"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["proposal"]["instrument"]["currency"] = "EUR"
    payload["proposal"]["dataset_revision"] += 1
    ledger_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="id does not match its immutable intent"):
        service.ledger.get(proposal.id)


def test_terminal_replay_rejects_coordinated_order_id_tampering(tmp_path: Path) -> None:
    service, _, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    confirmed = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )
    forged_id = "paper-forged-order"

    proposal_path = tmp_path / "proposals" / "proposals.jsonl"
    events = [json.loads(line) for line in proposal_path.read_text(encoding="utf-8").splitlines()]
    events[-1]["proposal"]["order_id"] = forged_id
    proposal_path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )

    journal_path = journal.root / "journal.jsonl"
    orders = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    own = next(order for order in orders if order["order_id"] == confirmed.order.order_id)
    own["order_id"] = forged_id
    journal_path.write_text(
        "".join(f"{json.dumps(order)}\n" for order in orders),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immutable proposal intent"):
        service.confirm(
            proposal.id,
            confirmation=proposal.confirmation_token,
            now=NOW,
        )


def test_terminal_replay_requires_exact_derived_fill_quantity(tmp_path: Path) -> None:
    service, _, journal = _service(tmp_path)
    proposal = service.propose(_artifact().id, side=Side.BUY, quantity=1)
    confirmed = service.confirm(
        proposal.id,
        confirmation=proposal.confirmation_token,
        now=NOW,
    )
    order = journal.get(confirmed.order.order_id)
    journal.update(order.model_copy(update={"filled_quantity": order.filled_quantity + 1e-10}))

    with pytest.raises(ValueError, match="derived state does not replay exactly"):
        service.confirm(
            proposal.id,
            confirmation=proposal.confirmation_token,
            now=NOW,
        )
