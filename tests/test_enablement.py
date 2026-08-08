"""M10 Phase E (issue #62): the per-venue enablement approval state
machine and the keyring secret-store wrapper, pinned by fixtures and
drills — never by real approvals and never against the OS keyring.

The state machine's only path to ``enabled`` is an approval record
carrying the recorded live-enablement gate text verbatim (``GATE_TEXT``
— the standing long-running-goal gate). The keyring store refuses any
construction outside an explicit drill flag; the fixture backend is
what the drills exercise, so the OS keyring is never touched.
"""

import builtins
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.ops.cli import main as cli_main
from quantmesh.ops.enablement import (
    GATE_TEXT,
    ApprovalLedger,
    ApprovalRecord,
    EnablementGateError,
    EnablementState,
    EnablementTransitionError,
    approval_id,
)
from quantmesh.ops.secrets import (
    FixtureKeyringBackend,
    KeyringRefusalError,
    KeyringStore,
    KeyringUnavailableError,
)

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
OPERATOR = "operator-alpha"
LATER = NOW + timedelta(minutes=1)
HOURS = NOW + timedelta(hours=1)


def ledger_at(tmp_path) -> ApprovalLedger:
    return ApprovalLedger(root=tmp_path / "enablement")


class TestApprovalRecordModel:
    def test_gate_text_required_exactly_on_approvals(self, tmp_path) -> None:
        with pytest.raises(EnablementGateError, match="gate"):
            ledger_at(tmp_path).approve(
                Venue.MOOMOO, actor=OPERATOR, acted_at=NOW, gate_text=None
            )
        # A non-approval record must NOT carry gate text.
        with pytest.raises(ValueError, match="gate_text"):
            ApprovalRecord(
                id=approval_id(
                    venue=Venue.MOOMOO,
                    kind="request",
                    actor=OPERATOR,
                    acted_at=NOW,
                    gate_text=GATE_TEXT,
                ),
                venue=Venue.MOOMOO,
                kind="request",
                actor=OPERATOR,
                acted_at=NOW,
                gate_text=GATE_TEXT,
            )

    def test_approval_with_wrong_gate_text_is_refused(self, tmp_path) -> None:
        with pytest.raises(EnablementGateError, match="gate"):
            ledger_at(tmp_path).approve(
                Venue.MOOMOO,
                actor=OPERATOR,
                acted_at=NOW,
                gate_text="trading is fine",
            )

    def test_naive_acted_at_refused_and_id_is_checked(self, tmp_path) -> None:
        ledger = ledger_at(tmp_path)
        with pytest.raises(ValueError, match="timezone-aware"):
            ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=datetime(2026, 8, 8))
        record = ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        forged = record.model_copy(update={"id": "f" * 16})
        with pytest.raises(ValueError, match="does not match"):
            forged.model_validate(forged)

    def test_blank_actor_refused(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="actor"):
            ledger_at(tmp_path).request(
                Venue.MOOMOO, actor="   ", acted_at=NOW
            )

    def test_gate_text_is_the_verbatim_standing_gate(self) -> None:
        assert GATE_TEXT == (
            "real-money trading, wallet signing, live broker orders, "
            "credentials, paid infrastructure, and AI order authority all "
            "require explicit human approval"
        )


class TestStateMachine:
    def test_full_approval_drill_round_trip(self, tmp_path) -> None:
        ledger = ledger_at(tmp_path)
        assert ledger.state(Venue.MOOMOO) is EnablementState.DISABLED

        request = ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        assert ledger.state(Venue.MOOMOO) is EnablementState.PENDING
        assert request.actor == OPERATOR
        assert request.acted_at == NOW

        approval = ledger.approve(
            Venue.MOOMOO, actor=OPERATOR, acted_at=LATER, gate_text=GATE_TEXT
        )
        assert ledger.state(Venue.MOOMOO) is EnablementState.ENABLED
        # The approval record carries who, when, and which gate text.
        assert approval.kind == "approval"
        assert approval.actor == OPERATOR
        assert approval.acted_at == LATER
        assert approval.gate_text == GATE_TEXT

        revoke = ledger.revoke(Venue.MOOMOO, actor=OPERATOR, acted_at=HOURS)
        assert revoke.kind == "revoke"
        assert ledger.state(Venue.MOOMOO) is EnablementState.DISABLED

        # The cycle is repeatable: disabled -> pending -> disabled.
        ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=HOURS + timedelta(1))
        ledger.withdraw(Venue.MOOMOO, actor=OPERATOR, acted_at=HOURS + timedelta(2))
        assert ledger.state(Venue.MOOMOO) is EnablementState.DISABLED

    @pytest.mark.parametrize(
        ("setup", "kind"),
        [
            ((), "approval"),  # disabled -> enabled directly: refused
            ((), "withdraw"),  # disabled -> disabled: refused
            ((), "revoke"),  # disabled -> disabled: refused
            (("request",), "request"),  # pending -> pending: refused
            (("request",), "revoke"),  # pending -> disabled: revoke is the wrong edge
            (("request", "approval"), "request"),  # enabled -> pending: refused
            (("request", "approval"), "approval"),  # enabled -> enabled: refused
            (("request", "approval"), "withdraw"),  # enabled -> disabled: wrong edge
            (("request", "withdraw"), "approval"),  # disabled -> enabled: refused
            (("request", "withdraw"), "withdraw"),  # disabled -> disabled: refused
            (("request", "approval", "revoke"), "revoke"),  # disabled: refused
        ],
    )
    def test_illegal_transitions_are_typed_refusals(self, tmp_path, setup, kind) -> None:
        ledger = ledger_at(tmp_path)
        at = NOW
        for step in setup:
            if step == "request":
                ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=at)
            elif step == "approval":
                ledger.approve(
                    Venue.MOOMOO, actor=OPERATOR, acted_at=at, gate_text=GATE_TEXT
                )
            elif step == "withdraw":
                ledger.withdraw(Venue.MOOMOO, actor=OPERATOR, acted_at=at)
            elif step == "revoke":
                ledger.revoke(Venue.MOOMOO, actor=OPERATOR, acted_at=at)
            at += timedelta(minutes=1)
        before = ledger.all()
        with pytest.raises(EnablementTransitionError):
            if kind == "approval":
                ledger.approve(
                    Venue.MOOMOO, actor=OPERATOR, acted_at=at, gate_text=GATE_TEXT
                )
            else:
                getattr(ledger, kind)(Venue.MOOMOO, actor=OPERATOR, acted_at=at)
        # Atomic: the refusal wrote nothing.
        assert ledger.all() == before

    def test_approval_with_wrong_gate_text_leaves_state_untouched(
        self, tmp_path
    ) -> None:
        ledger = ledger_at(tmp_path)
        ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        before = ledger.all()
        with pytest.raises(EnablementGateError, match="gate"):
            ledger.approve(
                Venue.MOOMOO,
                actor=OPERATOR,
                acted_at=LATER,
                gate_text="a watered-down gate",
            )
        assert ledger.all() == before
        assert ledger.state(Venue.MOOMOO) is EnablementState.PENDING

    def test_states_are_derived_from_the_ledger_only(self, tmp_path) -> None:
        ledger = ledger_at(tmp_path)
        ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        ledger.approve(Venue.MOOMOO, actor=OPERATOR, acted_at=LATER, gate_text=GATE_TEXT)
        ledger.revoke(Venue.MOOMOO, actor=OPERATOR, acted_at=HOURS)
        ledger.request(Venue.HYPERLIQUID, actor=OPERATOR, acted_at=NOW)
        assert ledger.states() == {
            Venue.MOOMOO: EnablementState.DISABLED,
            Venue.HYPERLIQUID: EnablementState.PENDING,
        }
        # A fresh ledger over the same root derives the same state.
        assert ledger_at(tmp_path).states() == ledger.states()

    def test_venues_are_independent(self, tmp_path) -> None:
        ledger = ledger_at(tmp_path)
        ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        ledger.approve(Venue.MOOMOO, actor=OPERATOR, acted_at=LATER, gate_text=GATE_TEXT)
        assert ledger.state(Venue.MOOMOO) is EnablementState.ENABLED
        assert ledger.state(Venue.HYPERLIQUID) is EnablementState.DISABLED


class TestLedgerDiscipline:
    def test_missing_store_reads_empty_and_root_refusals(self, tmp_path) -> None:
        ledger = ledger_at(tmp_path)
        assert ledger.all() == []
        assert ledger.states() == {}
        (tmp_path / "enablement").write_text("not a directory", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            ledger.all()

    def test_corrupt_line_attributed(self, tmp_path) -> None:
        root = tmp_path / "enablement"
        root.mkdir()
        (root / "enablement.jsonl").write_text(
            '{"id": "x"}\n', encoding="utf-8"
        )
        with pytest.raises(ValueError, match="line 1 is invalid"):
            ledger_at(tmp_path).all()

    def test_duplicate_ids_in_file_refused_with_line_attribution(
        self, tmp_path
    ) -> None:
        root = tmp_path / "enablement"
        ledger = ledger_at(tmp_path)
        record = ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        with (root / "enablement.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        with pytest.raises(ValueError, match="share a record id"):
            ledger.all()

    def test_cross_instance_persistence(self, tmp_path) -> None:
        ledger_at(tmp_path).request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        other = ledger_at(tmp_path)
        assert len(other.all()) == 1
        assert other.state(Venue.MOOMOO) is EnablementState.PENDING

    def test_identical_replay_is_refused_any_difference_is_new(self, tmp_path) -> None:
        ledger = ledger_at(tmp_path)
        first = ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        # A second request at the same instant with the same content is
        # refused by identity even if the state allowed it (it does not).
        with pytest.raises((EnablementTransitionError, ValueError)):
            ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=NOW)
        # The same action a minute later is a new audit entry.
        ledger.withdraw(Venue.MOOMOO, actor=OPERATOR, acted_at=LATER)
        ledger.request(Venue.MOOMOO, actor=OPERATOR, acted_at=HOURS)
        assert len(ledger.all()) == 3
        assert first.id != ledger.all()[1].id


class TestKeyringStore:
    def test_construction_refused_outside_a_drill(self) -> None:
        with pytest.raises(KeyringRefusalError, match="drill"):
            KeyringStore()
        with pytest.raises(KeyringRefusalError, match="drill"):
            KeyringStore(service="quantmesh", backend=FixtureKeyringBackend())

    def test_fixture_backend_round_trip_and_missing(self) -> None:
        store = KeyringStore(drill=True, backend=FixtureKeyringBackend())
        assert store.get("signing-key") is None
        store.put("signing-key", b"\x00\x01key\xff")
        assert store.get("signing-key") == b"\x00\x01key\xff"
        store.delete("signing-key")
        assert store.get("signing-key") is None
        store.delete("signing-key")  # idempotent

    def test_services_do_not_share_values(self) -> None:
        backend = FixtureKeyringBackend()
        KeyringStore(drill=True, service="quantmesh", backend=backend).put(
            "drill-key", b"value"
        )
        other = KeyringStore(drill=True, service="other", backend=backend)
        assert other.get("drill-key") is None

    def test_names_are_safe(self) -> None:
        store = KeyringStore(drill=True, backend=FixtureKeyringBackend())
        for bad in ("../escape", "a/b", "with space"):
            with pytest.raises(ValueError, match="safe"):
                store.put(bad, b"x")

    def test_real_backend_import_guard_fails_closed(self, monkeypatch) -> None:
        """Without keyring importable, an explicit drill cannot construct
        the real backend — the typed unavailable error names it."""
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "keyring" or name.startswith("keyring."):
                raise ImportError("blocked")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        with pytest.raises(KeyringUnavailableError, match="keyring"):
            KeyringStore(drill=True)

    def test_real_backend_constructs_only_with_drill_when_installed(self) -> None:
        import importlib.util

        if importlib.util.find_spec("keyring") is None:
            pytest.skip("keyring not installed")
        # Construction only — the OS keyring is never read or written.
        store = KeyringStore(drill=True)
        assert store.service == "quantmesh"


class TestEnablementCli:
    def test_approval_workflow_drill_via_cli(self, tmp_path, capsys) -> None:
        root = tmp_path / "enablement"
        args = ["enable", "--root", str(root), "--actor", OPERATOR, "--at", NOW.isoformat()]
        assert cli_main([*args, "moomoo", "request"]) == 0
        assert cli_main(
            [
                *args,
                "moomoo",
                "approve",
                "--gate-text",
                GATE_TEXT,
            ]
        ) == 0
        assert cli_main([*args, "moomoo", "revoke"]) == 0
        ledger = ApprovalLedger(root=root)
        assert ledger.state(Venue.MOOMOO) is EnablementState.DISABLED
        assert len(ledger.all()) == 3
        approval = [r for r in ledger.all() if r.kind == "approval"][0]
        assert approval.gate_text == GATE_TEXT
        assert approval.actor == OPERATOR

    def test_approve_without_gate_text_refused(self, tmp_path, capsys) -> None:
        root = tmp_path / "enablement"
        base = ["enable", "--root", str(root), "--actor", OPERATOR, "--at", NOW.isoformat()]
        assert cli_main([*base, "moomoo", "request"]) == 0
        assert cli_main([*base, "moomoo", "approve"]) == 1
        assert "requires --gate-text" in capsys.readouterr().err
        assert ApprovalLedger(root=root).state(Venue.MOOMOO) is EnablementState.PENDING

    def test_approve_with_wrong_gate_text_refused(self, tmp_path, capsys) -> None:
        root = tmp_path / "enablement"
        base = ["enable", "--root", str(root), "--actor", OPERATOR, "--at", NOW.isoformat()]
        assert cli_main([*base, "moomoo", "request"]) == 0
        assert (
            cli_main(
                [*base, "moomoo", "approve", "--gate-text", "trading is fine"]
            )
            == 1
        )
        assert "refused" in capsys.readouterr().err
        assert ApprovalLedger(root=root).state(Venue.MOOMOO) is EnablementState.PENDING

    def test_illegal_transition_via_cli_exits_1(self, tmp_path, capsys) -> None:
        root = tmp_path / "enablement"
        base = ["enable", "--root", str(root), "--actor", OPERATOR, "--at", NOW.isoformat()]
        assert cli_main([*base, "moomoo", "approve", "--gate-text", GATE_TEXT]) == 1
        assert "requires state pending" in capsys.readouterr().err

    def test_unknown_venue_exits_2(self, tmp_path) -> None:
        with pytest.raises(SystemExit) as exc:
            cli_main(
                [
                    "enable",
                    "--root",
                    str(tmp_path / "enablement"),
                    "--actor",
                    OPERATOR,
                    "not-a-venue",
                    "request",
                ]
            )
        assert exc.value.code == 2

    def test_gate_text_is_presented_to_the_operator(self, tmp_path, capsys) -> None:
        root = tmp_path / "enablement"
        base = ["enable", "--root", str(root), "--actor", OPERATOR, "--at", NOW.isoformat()]
        cli_main([*base, "moomoo", "request"])
        cli_main([*base, "moomoo", "approve", "--gate-text", GATE_TEXT])
        err = capsys.readouterr().err
        assert "live-enablement gate" in err
        assert GATE_TEXT in err
