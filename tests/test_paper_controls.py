"""Small synthetic fixtures exercise control authority without demo seeding."""

import json

import pytest

from quantmesh.execution.account_store import PaperAccountStore
from quantmesh.execution.accounting import PaperAccount, RiskLimits
from quantmesh.execution.journal import OrderJournal
from quantmesh.ops.paper_controls import PaperControlError, PaperControls


@pytest.fixture
def setup_control(tmp_path):
    account_path = tmp_path / "demo" / "account.json"
    account_path.parent.mkdir()
    account = PaperAccount(cash=1000)
    account_path.write_text(account.model_dump_json())
    journal = OrderJournal(tmp_path / "demo" / "orders")
    journal._store.write([])
    store = PaperAccountStore(
        account, publish=lambda a: account_path.write_text(a.model_dump_json())
    )
    controls = PaperControls(
        root=tmp_path / "controls",
        account_store=store,
        account_path=account_path,
        journal=journal,
        limits=RiskLimits(max_order_quantity=2, max_notional=500, max_position_quantity=4),
        scenario="tiny-synthetic",
    )
    yield controls, store, account_path, journal
    controls.close()


def resume(controls, key="resume-1"):
    revision = controls.preflight()["revision"]
    return controls.transition(
        "resume", key=key, reason="Local rehearsal reviewed", revision=revision, confirmation=True
    )


def test_startup_pause_resume_then_old_resume_replay_cannot_reopen(setup_control):
    c, store, _, _ = setup_control
    assert store.get().kill_switch
    first = resume(c)
    assert not store.get().kill_switch
    c.transition("pause", key="pause-1", reason="Inspect fills")
    replay = c.transition(
        "resume",
        key="resume-1",
        reason="Local rehearsal reviewed",
        revision=first["receipt"]["requested_revision"],
        confirmation=True,
    )
    assert replay["replay"] and replay["receipt"] == first["receipt"]
    assert replay["status"]["paused"] and store.get().kill_switch
    with pytest.raises(PaperControlError, match="key_conflict"):
        c.transition("pause", key="pause-1", reason="Changed")


def test_stale_confirmation_and_venue_stops(setup_control):
    c, store, _, _ = setup_control
    revision = c.preflight()["revision"]
    c.transition("pause", key="pause-new", reason="New pause")
    with pytest.raises(PaperControlError, match="stale_revision"):
        c.transition("resume", key="bad", reason="Reviewed", revision=revision, confirmation=True)
    with pytest.raises(PaperControlError, match="confirmation_required"):
        c.transition("resume", key="bad", reason="Reviewed", revision=c.preflight()["revision"])
    from quantmesh.domain.models import Venue

    store.update(lambda a: a.model_copy(update={"kill_switches": {Venue.MOOMOO: True}}))
    resume(c)
    assert store.get().kill_switches[Venue.MOOMOO]


@pytest.mark.parametrize("evidence", ["account", "journal", "audit", "limits"])
def test_missing_evidence_blocks_before_transaction_writes(setup_control, evidence):
    c, store, account_path, journal = setup_control
    resume(c)
    if evidence == "account":
        account_path.unlink()
    elif evidence == "journal":
        journal._store.path.unlink()
    elif evidence == "audit":
        c.audit.path.unlink()
    else:
        c.limits = None
    snapshot = store.get()
    assert c.preflight()["blocked"]
    with pytest.raises(PaperControlError):
        with store.transaction():
            pytest.fail("guard admitted unsafe transaction")
    assert store.get() == snapshot


@pytest.mark.parametrize("target", ["account", "journal", "audit"])
def test_corruption_is_preserved_and_refused(setup_control, target):
    c, store, account_path, journal = setup_control
    path = {"account": account_path, "journal": journal._store.path, "audit": c.audit.path}[target]
    path.write_text("corrupt-original")
    assert c.preflight()["blocked"]
    with pytest.raises(PaperControlError):
        resume(c)
    assert path.read_text() == "corrupt-original"


def test_cold_restart_pauses_and_preserves_first_receipt(setup_control):
    c, store, account_path, journal = setup_control
    first = resume(c)
    c.close()
    cold = PaperControls(
        root=c.root,
        account_store=store,
        account_path=account_path,
        journal=journal,
        limits=c.limits,
        scenario="tiny-synthetic",
    )
    try:
        assert cold.status()["paused"]
        assert cold.receipt(first["receipt"]["id"]) == first["receipt"]
    finally:
        cold.close()


def test_second_writer_refused(setup_control):
    c, store, account_path, journal = setup_control
    with pytest.raises(PaperControlError, match="writer"):
        PaperControls(
            root=c.root,
            account_store=store,
            account_path=account_path,
            journal=journal,
            limits=c.limits,
            scenario="tiny-synthetic",
        )


@pytest.mark.parametrize("failure", ["intent", "account", "outcome"])
def test_publication_failure_leaves_unresolved_intent_and_no_completed_receipt(
    setup_control,
    monkeypatch,
    failure,
):
    c, store, _, _ = setup_control
    original = store._publish
    append = c.audit.append
    if failure == "account":
        monkeypatch.setattr(store, "_publish", lambda _: (_ for _ in ()).throw(OSError("injected")))
    else:

        def fail_outcome(record):
            if record.kind == failure:
                raise OSError("injected")
            return append(record)

        monkeypatch.setattr(c.audit, "append", fail_outcome)
    with pytest.raises(PaperControlError, match="publication_failed"):
        resume(c)
    assert c.status()["blocked"]
    records = [json.loads(line) for line in c.audit.path.read_text().splitlines()]
    assert records[-1]["kind"] == ("outcome" if failure == "intent" else "intent")
    monkeypatch.setattr(store, "_publish", original)
    with pytest.raises(PaperControlError):
        with store.transaction():
            pytest.fail("incomplete publication admitted")


def test_revision_bound_target_and_concurrent_account_change(setup_control):
    from concurrent.futures import ThreadPoolExecutor

    from quantmesh.domain.models import Venue

    c, store, _, _ = setup_control
    preflight = c.preflight()
    with pytest.raises(PaperControlError, match="stale_revision"):
        c.transition(
            "resume",
            key="wrong-target",
            reason="Reviewed",
            revision=preflight["revision"],
            confirmation=True,
            target="moomoo",
        )
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            store.update, lambda a: a.model_copy(update={"kill_switches": {Venue.MOOMOO: True}})
        ).result()
    with pytest.raises(PaperControlError, match="stale_revision"):
        c.transition(
            "resume",
            key="old-account",
            reason="Reviewed",
            revision=preflight["revision"],
            confirmation=True,
        )


@pytest.mark.parametrize("damage", ["audit", "incomplete"])
def test_cold_damaged_audit_remains_paused_without_repair(setup_control, damage):
    c, store, account_path, journal = setup_control
    resume(c)
    if damage == "audit":
        c.audit.path.write_text("retained-corrupt-original")
    else:
        records = c._records()
        c._append("intent", {**records[-2].data, "key": "unfinished"}, records)
    original = c.audit.path.read_bytes()
    c.close()
    cold = PaperControls(
        root=c.root,
        account_store=store,
        account_path=account_path,
        journal=journal,
        limits=c.limits,
        scenario="tiny-synthetic",
    )
    try:
        assert cold.status()["paused"] and cold.status()["blocked"]
        assert c.audit.path.read_bytes() == original
    finally:
        cold.close()


def test_proposal_transaction_guard_precedes_lookup_and_matching(setup_control, tmp_path):
    from datetime import UTC, datetime
    from unittest.mock import Mock

    from quantmesh.instruments.proposals import PaperDecisionService, ProposalLedger
    from quantmesh.live.fence import QuoteFence

    c, store, account_path, journal = setup_control
    service = PaperDecisionService(
        ledger=ProposalLedger(tmp_path / "proposals"),
        forecast_registry=Mock(),
        account_provider=store.get,
        account_sink=store.replace,
        account_transaction=store.transaction,
        journal=journal,
        snapshot_provider=lambda *_: None,
        quote_fence=QuoteFence(),
    )
    before = journal._store.path.read_bytes()
    account_path.unlink()
    with pytest.raises(PaperControlError, match="evidence_blocked"):
        service.confirm("not-looked-up", confirmation="none", now=datetime.now(UTC))
    assert journal._store.path.read_bytes() == before


def test_guard_is_under_same_lock_and_pause_serializes_after_an_order_transaction(setup_control):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    c, store, _, _ = setup_control
    resume(c)
    held, release = Event(), Event()

    def admitted_transaction():
        with store.transaction():
            held.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=2) as pool:
        admitted = pool.submit(admitted_transaction)
        assert held.wait(5)
        paused = pool.submit(c.transition, "pause", key="parallel-pause", reason="Concurrent pause")
        assert not paused.done()
        release.set()
        admitted.result(timeout=5)
        paused.result(timeout=5)
    assert store.get().kill_switch


@pytest.fixture
def controlled_proposal(setup_control, tmp_path):
    """A sealed proposal over a tiny synthetic artifact stub; no forecast evaluation."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from quantmesh.domain.models import Instrument, InstrumentType, Quote, Side, Venue
    from quantmesh.instruments.forecast import _canonical_json, _config, _sha256
    from quantmesh.instruments.proposals import PaperDecisionService, ProposalLedger
    from quantmesh.live.fence import QuoteFence

    controls, store, account_path, journal = setup_control
    now = datetime(2026, 10, 20, tzinfo=UTC)
    instrument = Instrument(
        symbol="TINY", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY, currency="USD"
    )
    artifact = SimpleNamespace(
        id="forecast-" + "1" * 24,
        instrument=instrument,
        dataset_id="tiny-synthetic",
        dataset_revision=1,
        generated_at=now,
        train_end=now,
        model_version="synthetic-stub",
        config_digest=_sha256(_canonical_json(_config("legacy"))),
        history_digest="2" * 64,
        eligible=True,
        blockers=(),
        calendar="weekday",
    )
    service = PaperDecisionService(
        ledger=ProposalLedger(tmp_path / "tiny-proposal"),
        forecast_registry=SimpleNamespace(get=lambda _: artifact),
        account_provider=store.get,
        account_sink=store.replace,
        account_transaction=store.transaction,
        journal=journal,
        snapshot_provider=lambda *_: None,
        quote_fence=QuoteFence(),
        demo_quote_provider=lambda *_: Quote(
            instrument=instrument, timestamp=now, bid=99, ask=100, volume=10
        ),
        now=lambda: now,
    )
    # Public optional binding is ignored by old source, exposing its persistence bug.
    service.fresh_submission_guard = lambda account, target: controls.validate_fresh_submission(
        account, target
    )
    proposal = service.propose(artifact.id, side=Side.BUY, quantity=1)
    return controls, store, account_path, journal, service, proposal, now


@pytest.mark.parametrize("stop", ["global", "venue"])
def test_fresh_controlled_proposal_pause_has_zero_account_journal_and_fill_effects(
    controlled_proposal,
    stop,
):
    from quantmesh.domain.models import Venue

    c, store, account_path, journal, service, proposal, now = controlled_proposal
    if stop == "venue":
        resume(c)
        store.update(lambda a: a.model_copy(update={"kill_switches": {Venue.MOOMOO: True}}))
    before = (account_path.read_bytes(), journal._store.path.read_bytes(), store.get())
    with pytest.raises(PaperControlError, match="paper_control_paused"):
        service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=now)
    assert (account_path.read_bytes(), journal._store.path.read_bytes(), store.get()) == before
    assert not store.get().orders and not store.get().positions
    assert len(service.ledger.events(proposal.id)) == 1


def test_controlled_proposal_allowed_fill_then_completed_replay_after_pause(controlled_proposal):
    c, store, account_path, journal, service, proposal, now = controlled_proposal
    resume(c)
    completed = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=now)
    assert completed.proposal.status == "confirmed"
    assert len(journal.all()) == 1 and len(journal.all()[0].fills) == 1
    assert store.get().positions["moomoo:TINY"].quantity == 1
    c.transition("pause", key="proposal-later-pause", reason="Inspect completed proposal")
    before = (account_path.read_bytes(), journal._store.path.read_bytes(), store.get())
    assert (
        service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=now) == completed
    )
    assert (account_path.read_bytes(), journal._store.path.read_bytes(), store.get()) == before


@pytest.mark.parametrize("failure", ["missing", "changed", "guard"])
def test_controlled_proposal_evidence_or_guard_failure_has_zero_effects(
    controlled_proposal,
    failure,
):
    c, store, account_path, journal, service, proposal, now = controlled_proposal
    resume(c)
    if failure == "missing":
        account_path.unlink()
    elif failure == "changed":
        account_path.write_text("retained-corrupt-account")
    else:

        def refuse(_account, _instrument):
            raise PaperControlError("injected_fresh_guard_failure")

        service.fresh_submission_guard = refuse
    before_account = account_path.read_bytes() if account_path.exists() else None
    before_journal, before_state = journal._store.path.read_bytes(), store.get()
    with pytest.raises(PaperControlError):
        service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=now)
    assert (account_path.read_bytes() if account_path.exists() else None) == before_account
    assert journal._store.path.read_bytes() == before_journal and store.get() == before_state
    assert len(service.ledger.events(proposal.id)) == 1
