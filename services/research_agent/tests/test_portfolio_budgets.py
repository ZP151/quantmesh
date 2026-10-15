"""Scripted/local accounting witnesses; no provider billing or production proof."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import publish
from qm_research_agent import budgets
from test_research_jobs import request_for

from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import RunBudget


def jobs(local, count=2):
    store, lake, clock = local
    result = []
    for i in range(count):
        job = store.submit("operator", f"portfolio-{i}", request_for(lake, analysis_requested=True))
        publish(store, job)
        lease = store.claim_analysis(f"analyst-{i}", clock[0])
        assert lease.job_id == job.job_id
        result.append((job, lease))
    return result


def reserve(ledger, pair, price="0.6", digest="a"):
    job, lease = pair
    return ledger.reserve_call(job.job_id, digest, Decimal(price), job.request.budget, lease)


def policy(operating="1", development="2", policy_id="scripted-local"):
    assert hasattr(budgets, "PortfolioBudgetPolicy"), "missing immutable portfolio policy"
    return budgets.PortfolioBudgetPolicy(policy_id, Decimal(operating), Decimal(development))


def ledger(local, category="operating", **limits):
    return budgets.EffectLedger(local[0], policy=policy(**limits), category=category)


def test_independent_jobs_share_exact_allowance(local):
    pairs = jobs(local)
    effects = ledger(local)
    assert reserve(effects, pairs[0])
    assert not reserve(effects, pairs[1])
    assert effects.read(pairs[1][0].job_id, "a") is None


def test_exact_boundary_decimal_precision_and_per_job_limit(local):
    pairs = jobs(local)
    effects = ledger(local, operating="0.3")
    assert reserve(effects, pairs[0], "0.1")
    assert reserve(effects, pairs[1], "0.2")
    assert not reserve(effects, pairs[1], "1e-40", "b")


def test_per_job_limits_still_apply_with_room_in_portfolio(local):
    pair = jobs(local, 1)[0]
    effects = ledger(local, operating="50")
    assert reserve(effects, pair, "0.6")
    assert not reserve(effects, pair, "0.6", "b")
    for i in range(11):
        assert reserve(effects, pair, "0", str(i))
    assert not reserve(effects, pair, "0", "thirteenth")


def test_last_slot_race_different_jobs_and_store_connections(local):
    pairs = jobs(local)
    ledger(local)

    def attempt(pair):
        store, lake, clock = local
        separate = SQLiteJobStore(store.path, lake_root=lake, clock=lambda: clock[0])
        return reserve(budgets.EffectLedger(separate, policy=policy(), category="operating"), pair)

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(attempt, pairs)) == [False, True]
    with local[0]._transaction() as con:
        assert con.execute("SELECT COUNT(*) FROM model_effects").fetchone()[0] == 1


def test_categories_are_separate_development_is_lifetime(local):
    pairs = jobs(local)
    operating = ledger(local, operating="0.6", development="0.6")
    development = ledger(local, "development", operating="0.6", development="0.6")
    assert reserve(operating, pairs[0])
    assert reserve(development, pairs[1])
    assert not reserve(operating, pairs[1], "0.01", "b")
    assert not reserve(development, pairs[0], "0.01", "b")
    # Completed development effects still count after a month and a restart.
    assert development.response(pairs[1][1], "a", "archived scripted response")
    local[2][0] += timedelta(days=40)
    replacement = local[0].claim_analysis("replacement", local[2][0])
    assert replacement is not None
    reopened = ledger(local, "development", operating="0.6", development="0.6")
    assert not reserve(reopened, (pairs[0][0], replacement), "0.01", "later")


@pytest.mark.parametrize("completed", [True, False])
def test_utc_month_transition_completed_reset_unresolved_carry(local, completed):
    local[2][0] = datetime(2026, 1, 31, 23, 59, 30, tzinfo=UTC)
    pairs = jobs(local)
    effects = ledger(local, operating="0.6")
    assert reserve(effects, pairs[0])
    if completed:
        assert effects.response(pairs[0][1], "a", "scripted response")
    local[2][0] = datetime(2026, 2, 1, tzinfo=UTC)
    assert reserve(effects, pairs[1]) is completed


def test_clock_rollback_and_stale_fence_deny_without_effect(local):
    pair = jobs(local, 1)[0]
    effects = ledger(local)
    assert reserve(effects, pair, "0")
    local[2][0] -= timedelta(seconds=1)
    assert not reserve(effects, pair, "0", "rollback")
    local[2][0] += timedelta(seconds=62)
    assert not reserve(effects, pair, "0", "expired")
    assert effects.read(pair[0].job_id, "rollback") is None
    assert effects.read(pair[0].job_id, "expired") is None


def test_missing_policy_denies_zero_estimate(local):
    pair = jobs(local, 1)[0]
    effects = budgets.EffectLedger(local[0])
    assert not reserve(effects, pair, "0")
    assert effects.read(pair[0].job_id, "a") is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operating": "50.01"},
        {"development": "200.01"},
        {"operating": "NaN"},
        {"development": "Infinity"},
        {"operating": "-1"},
        {"policy_id": "../bad"},
        {"policy_id": ""},
        {"policy_id": "x" * 65},
    ],
)
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        policy(**kwargs)


def test_policy_is_immutable_and_rejects_float():
    value = policy()
    with pytest.raises((AttributeError, TypeError)):
        value.operating_monthly_usd = Decimal("50")
    with pytest.raises(ValueError):
        budgets.PortfolioBudgetPolicy("fixture", 1.0, Decimal("2"))


@pytest.mark.parametrize(
    "limits", [{"policy_id": "other"}, {"operating": "2"}, {"development": "3"}]
)
def test_bound_policy_cannot_be_replaced(local, limits):
    ledger(local)
    with pytest.raises(ValueError):
        ledger(local, **limits)


def test_invalid_category_and_unpaired_policy(local):
    with pytest.raises(ValueError):
        budgets.EffectLedger(local[0], policy=policy(), category="scripted")
    with pytest.raises(ValueError):
        budgets.EffectLedger(local[0], policy=policy())
    with pytest.raises(ValueError):
        budgets.EffectLedger(local[0], category="operating")


def test_legacy_unattributed_effects_block_policy_activation_and_preserve_read(local):
    pair = jobs(local, 1)[0]
    old = budgets.EffectLedger(local[0])
    with local[0]._transaction() as con:
        con.execute(
            "INSERT INTO model_effects VALUES (?, 'legacy', '0', 'completed', 'raw', NULL)",
            (pair[0].job_id,),
        )
    with pytest.raises(ValueError):
        ledger(local)
    assert old.read(pair[0].job_id, "legacy") == ("completed", "raw", None)


def test_duplicate_crash_reopen_and_atomic_rollback(local, monkeypatch):
    pairs = jobs(local)
    effects = ledger(local)
    assert reserve(effects, pairs[0])
    assert not reserve(effects, pairs[0])
    reopened = ledger(local)
    assert reopened.read(pairs[0][0].job_id, "a") == ("reserved", None, None)
    assert not reserve(reopened, pairs[1])
    original = local[0]._transaction

    @contextmanager
    def interrupted():
        with original() as con:
            yield con
            raise RuntimeError("scripted crash before commit")

    monkeypatch.setattr(local[0], "_transaction", interrupted)
    with pytest.raises(RuntimeError):
        reserve(effects, pairs[1], "0.4", "rolled-back")
    monkeypatch.setattr(local[0], "_transaction", original)
    assert effects.read(pairs[1][0].job_id, "rolled-back") is None
    assert reserve(effects, pairs[1], "0.4", "after-rollback")


def test_unknown_accounting_version_rejects_activation_and_admission(local):
    pair = jobs(local, 1)[0]
    effects = ledger(local)
    with local[0]._transaction() as con:
        con.execute("UPDATE qm_portfolio_schema SET version=999")
    with pytest.raises(ValueError):
        ledger(local)
    assert not reserve(effects, pair)


def test_policy_mismatch_and_unattributed_history_deny_existing_instance(local):
    pair = jobs(local, 1)[0]
    effects = ledger(local)
    with local[0]._transaction() as con:
        con.execute("UPDATE qm_portfolio_policy SET policy_id='other'")
    assert not reserve(effects, pair)


@pytest.mark.parametrize("price", [None, 0.0, Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_invalid_estimate_denied(local, price):
    job, lease = jobs(local, 1)[0]
    assert not ledger(local).reserve_call(job.job_id, "invalid", price, RunBudget(), lease)


def test_remote_missing_policy_has_zero_external_invocations(local, monkeypatch):
    from pydantic import SecretStr
    from qm_research_agent import orchestrator

    pair = jobs(local, 1)[0]
    job = local[0].get("operator", pair[0].job_id)
    ref = next(ref for ref in job.artifacts if ref.kind == "report")
    gateway = orchestrator.ApprovedRemoteGateway(
        base_url="https://scripted-unused.example",
        model="unused",
        key=SecretStr(""),
        allowed_origins=frozenset({"https://scripted-unused.example"}),
        remote_consent=True,
    )
    invocations = []

    def forbidden(*args):
        invocations.append(args)
        raise AssertionError("external invocation must not occur")

    monkeypatch.setattr(orchestrator, "bounded_complete", forbidden)
    effects = budgets.EffectLedger(local[0])
    engine = orchestrator.AdvisoryRunner(
        local[0], effects, provider="explicit-remote", price=Decimal("0"), price_version="fixture"
    )
    result = engine.run_analysis(job, ref, gateway, lease=pair[1])
    assert result.error_code == "budget_exhausted"
    assert not invocations
    assert effects.read(job.job_id, ref.sha256) is None


@pytest.mark.parametrize("checkpointed", [False, True])
def test_archived_replay_usable_without_policy(local, monkeypatch, checkpointed):
    from qm_research_agent.orchestrator import AdvisoryRunner
    from test_agent import gateway

    pair = jobs(local, 1)[0]
    job = local[0].get("operator", pair[0].job_id)
    ref = next(ref for ref in job.artifacts if ref.kind == "report")
    effects = ledger(local)
    if not checkpointed:
        monkeypatch.setattr(effects, "checkpoint", lambda *args: False)
    model, transport = gateway(ref)
    engine = AdvisoryRunner(
        local[0], effects, provider="scripted", price=Decimal("0.6"), price_version="scripted"
    )
    original = engine.run_analysis(job, ref, model, lease=pair[1])
    assert original.state == "succeeded"
    local[2][0] += timedelta(seconds=61)
    replacement = local[0].claim_analysis("replacement", local[2][0])
    archived = AdvisoryRunner(
        local[0],
        budgets.EffectLedger(local[0]),
        provider="unavailable",
        price=None,
        price_version=None,
    )
    replayed = archived.run_analysis(job, ref, model, lease=replacement)
    assert replayed == original
    assert len(transport.seen_bodies) == 1
    with local[0]._transaction() as con:
        assert con.execute("SELECT COUNT(*) FROM qm_portfolio_reservations").fetchone()[0] == 1


def test_cancelled_unknown_reservation_keeps_allowance_next_month(local):
    local[2][0] = datetime(2026, 1, 31, 23, 59, 30, tzinfo=UTC)
    pairs = jobs(local)
    effects = ledger(local, operating="0.6")
    assert reserve(effects, pairs[0])
    local[0].request_cancel("operator", pairs[0][0].job_id)
    assert not effects.response(pairs[0][1], "a", "late")
    local[2][0] = datetime(2026, 2, 1, tzinfo=UTC)
    assert not reserve(effects, pairs[1])


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE qm_portfolio_reservations SET price='NaN'",
        "UPDATE qm_portfolio_reservations SET price='0.600'",
        "UPDATE qm_portfolio_reservations SET period='1900-01'",
        "UPDATE qm_portfolio_policy SET high_water='malformed'",
        "UPDATE model_effects SET price='0.1'",
        "DELETE FROM qm_portfolio_reservations",
        "INSERT INTO qm_portfolio_schema VALUES (1)",
    ],
)
def test_malformed_or_incomplete_accounting_denies_without_new_effect(local, sql):
    pairs = jobs(local)
    effects = ledger(local)
    assert reserve(effects, pairs[0])
    with local[0]._transaction() as con:
        con.execute(sql)
    assert not reserve(effects, pairs[1], "0")
    assert effects.read(pairs[1][0].job_id, "a") is None


def test_canonical_amounts_are_persisted_and_equivalent_policy_reopens(local):
    pair = jobs(local, 1)[0]
    effects = ledger(local, operating="1.00", development="2.000")
    assert reserve(effects, pair, "0.6000")
    ledger(local)
    with local[0]._transaction() as con:
        assert tuple(
            con.execute(
                "SELECT operating_monthly_usd,development_total_usd FROM qm_portfolio_policy"
            ).fetchone()
        ) == ("1", "2")
        assert con.execute("SELECT price FROM qm_portfolio_reservations").fetchone()[0] == "0.6"


def test_missing_version_does_not_reset_bound_authority(local):
    ledger(local)
    with local[0]._transaction() as con:
        con.execute("DELETE FROM qm_portfolio_schema")
    with pytest.raises(ValueError):
        ledger(local)


def test_completed_without_archived_response_cannot_release_old_allowance(local):
    local[2][0] = datetime(2026, 1, 31, 23, 59, 30, tzinfo=UTC)
    pairs = jobs(local)
    effects = ledger(local, operating="0.6")
    assert reserve(effects, pairs[0])
    with local[0]._transaction() as con:
        con.execute("UPDATE model_effects SET status='completed'")
    local[2][0] = datetime(2026, 2, 1, tzinfo=UTC)
    assert not reserve(effects, pairs[1])


@pytest.mark.parametrize("boundary", ["activation", "admission"])
def test_orphan_reservation_from_incomplete_import_fails_closed(local, boundary):
    pairs = jobs(local)
    effects = ledger(local, operating="0.6")
    assert reserve(effects, pairs[0])
    # Simulate an incomplete import using a separate fixture-only connection.
    # Service transactions retain their existing foreign-key enforcement.
    with sqlite3.connect(local[0].path) as imported:
        assert imported.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        imported.execute(
            "DELETE FROM model_effects WHERE job_id=? AND digest='a'", (pairs[0][0].job_id,)
        )
    if boundary == "activation":
        with pytest.raises(ValueError):
            ledger(local, operating="0.6")
    else:
        assert not reserve(effects, pairs[1])
    with local[0]._transaction() as con:
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert con.execute("SELECT price FROM qm_portfolio_reservations").fetchall() == [("0.6",)]
        assert con.execute("SELECT COUNT(*) FROM model_effects").fetchone()[0] == 0
