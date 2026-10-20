"""Explicit local synthetic paper authority; account lock precedes audit access.

The audit is an atomic JSONL hash chain of intent/outcome pairs. An intent without
an outcome is never a completed receipt and permanently blocks this session/root
until operator-owned evidence recovery. Cold startup pauses; no automatic repair.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from quantmesh.domain.models import Instrument
from quantmesh.execution.account_store import PaperAccountStore, recover_account_from_journal
from quantmesh.execution.accounting import PaperAccount, RiskLimits
from quantmesh.execution.journal import OrderJournal
from quantmesh.persistence.jsonl import JsonlStore

MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
MAX_AUDIT_BYTES = 2 * 1024 * 1024
_KEY = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


class PaperControlError(ValueError):
    """Fixed local refusal code; never include caller paths or raw exceptions."""


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _safe(path: Path, *, file: bool = True) -> None:
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            meta = candidate.lstat()
            if stat.S_ISLNK(meta.st_mode) or getattr(meta, "st_file_attributes", 0) & 0x400:
                raise PaperControlError("unsafe_evidence")
    if file:
        meta = path.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
            raise PaperControlError("unsafe_evidence")


def _read(path: Path, maximum: int = MAX_EVIDENCE_BYTES) -> bytes:
    _safe(path)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_size > maximum:
            raise PaperControlError("evidence_too_large")
        data = handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
    if (
        len(data) > maximum
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or not os.path.samestat(after, path.stat())
    ):
        raise PaperControlError("evidence_changed")
    _safe(path)
    return data


class WriterLease:
    """A nonblocking process lifetime OS lease, following repository lock discipline."""

    def __init__(self, path: Path) -> None:
        self.handle = None
        self.path = path
        _safe(path.parent, file=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _safe(path)
        handle = path.open("a+b")
        try:
            if os.fstat(handle.fileno()).st_nlink != 1:
                raise PaperControlError("unsafe_evidence")
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _safe(path)
            if not os.path.samestat(os.fstat(handle.fileno()), path.stat()):
                raise PaperControlError("unsafe_evidence")
        except (OSError, ValueError) as error:
            handle.close()
            raise PaperControlError("paper_control_writer_unavailable") from error
        self.handle = handle

    def validate(self) -> None:
        _safe(self.path)
        if self.handle is None or not os.path.samestat(
            os.fstat(self.handle.fileno()), self.path.stat()
        ):
            raise PaperControlError("paper_control_writer_unavailable")

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()  # Closing releases the OS lock on both supported platforms.
            self.handle = None


def acquire_leases(root: Path, account_root: Path) -> tuple[bool, list[WriterLease]]:
    """Acquire before demo load/recovery, so another process cannot mutate first."""
    fresh = not root.exists()
    leases: list[WriterLease] = []
    try:
        for path in (
            account_root.parent / f".{account_root.name}.paper-control.lock",
            root / ".writer.lock",
        ):
            leases.append(WriterLease(path))
    except BaseException:
        for lease in leases:
            lease.close()
        raise
    return fresh, leases


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    previous: str
    kind: Literal["intent", "outcome"]
    data: dict


class PaperControls:
    """One explicitly synthetic account; the existing kernel remains execution authority."""

    def __init__(
        self,
        *,
        root: Path,
        account_store: PaperAccountStore,
        account_path: Path,
        journal: OrderJournal,
        limits: RiskLimits | None,
        scenario: str,
        leases: tuple[bool, list[WriterLease]] | None = None,
    ) -> None:
        self.root, self.store, self.account_path = Path(root), account_store, Path(account_path)
        self.journal, self.limits, self.scenario = journal, limits, scenario
        self.boot = uuid.uuid4().hex
        self.reason = "cold_start"
        self.failed = False
        fresh, self._leases = leases or acquire_leases(self.root, self.account_path.parent)
        self.audit = JsonlStore(
            self.root,
            filename="audit.jsonl",
            model=AuditRecord,
            label="paper controls",
            id_label="record",
            key=lambda r: r.id,
        )
        try:
            if fresh:
                self.audit.write([])
            # Boot pause may proceed without caps, but never repair invalid account evidence.
            with self.store.transaction(validate=False):
                self._account_evidence()
                try:
                    records = self._records()
                except (OSError, ValueError):
                    # Retain damaged/unresolved audit bytes. Publish only the safety stop,
                    # never an invented completed action or a replacement green audit.
                    self.store.replace(self.store.get().model_copy(update={"kill_switch": True}))
                    self.failed = True
                    self.reason = "audit_invalid_or_incomplete"
                else:
                    self._publish(
                        "startup",
                        key=f"boot-{self.boot}",
                        reason="cold_start",
                        revision="",
                        target=None,
                        records=records,
                    )
            self.store.transaction_validator = self.validate_transaction
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.store.transaction_validator == self.validate_transaction:
            self.store.transaction_validator = None
        for lease in self._leases:
            lease.close()

    def _account_evidence(self) -> tuple[bytes, bytes]:
        snapshot = _read(self.account_path)
        account = PaperAccount.model_validate_json(snapshot)
        if account != self.store.get():
            raise PaperControlError("account_mismatch")
        journal_bytes = _read(self.journal._store.path)  # Same public journal owns decoding.
        recovered = recover_account_from_journal(account, self.journal.all())
        if recovered != account or journal_bytes != _read(self.journal._store.path):
            raise PaperControlError("journal_mismatch")
        return snapshot, journal_bytes

    def _records(self) -> list[AuditRecord]:
        raw = _read(self.audit.path, MAX_AUDIT_BYTES)
        records = self.audit.read()
        if raw != _read(self.audit.path, MAX_AUDIT_BYTES):
            raise PaperControlError("audit_changed")
        previous = ""
        pending = None
        keys: set[str] = set()
        for record in records:
            if record.kind == "intent":
                data = record.data
                expected_keys = {
                    "action",
                    "key",
                    "reason",
                    "requested_revision",
                    "confirmation",
                    "target",
                    "boot",
                    "configuration",
                    "account_binding",
                    "recorded_at",
                }
                if (
                    set(data) != expected_keys
                    or data["action"] not in ("startup", "pause", "resume")
                    or not isinstance(data["key"], str)
                    or not _KEY.fullmatch(data["key"])
                    or not isinstance(data["reason"], str)
                    or not 1 <= len(data["reason"]) <= 240
                    or not isinstance(data["confirmation"], bool)
                    or data["target"] not in (None, "moomoo", "hyperliquid", "polymarket", "kalshi")
                    or data["account_binding"] != self._binding()
                    or not all(
                        isinstance(data[k], str)
                        for k in ("boot", "configuration", "recorded_at", "requested_revision")
                    )
                ):
                    raise PaperControlError("audit_corrupt")
            elif set(record.data) != {"intent"} or not isinstance(record.data["intent"], str):
                raise PaperControlError("audit_corrupt")
            if record.previous != previous or record.id != _digest(
                {"previous": record.previous, "kind": record.kind, "data": record.data}
            ):
                raise PaperControlError("audit_corrupt")
            if record.kind == "intent":
                if pending is not None or record.data.get("key") in keys:
                    raise PaperControlError("audit_corrupt")
                pending = record
                keys.add(record.data.get("key"))
            else:
                if pending is None or record.data.get("intent") != pending.id:
                    raise PaperControlError("audit_corrupt")
                pending = None
            previous = record.id
        if pending is not None:
            raise PaperControlError("publication_incomplete")
        return records

    def _append(
        self, kind: Literal["intent", "outcome"], data: dict, records: list[AuditRecord]
    ) -> AuditRecord:
        payload = {"previous": records[-1].id if records else "", "kind": kind, "data": data}
        record = AuditRecord(id=_digest(payload), **payload)
        # Reserve capacity for both intent and outcome before changing account state.
        if (
            self.audit.path.stat().st_size + len(record.model_dump_json().encode()) + 8192
            > MAX_AUDIT_BYTES
        ):
            raise PaperControlError("audit_capacity")
        self.audit.append(record)
        records.append(record)
        return record

    def _caps_valid(self) -> bool:
        return self.limits is not None and all(
            value is not None and math.isfinite(value) and value > 0
            for value in self.limits.model_dump().values()
        )

    def _inspect(self) -> tuple[list[str], str, list[AuditRecord]]:
        problems: list[str] = []
        snapshot = journal = b""
        records: list[AuditRecord] = []
        try:
            for lease in self._leases:
                lease.validate()
        except (OSError, ValueError):
            problems.append("paper_control_writer_unavailable")
        try:
            snapshot, journal = self._account_evidence()
        except (OSError, ValueError):
            problems.append("account_or_journal_invalid")
        try:
            records = self._records()
        except (OSError, ValueError):
            problems.append("audit_invalid_or_incomplete")
        if not self._caps_valid():
            problems.append("rehearsal_limits_missing_or_invalid")
        elif self.store.get().risk_limits != self.limits:
            problems.append("rehearsal_limits_mismatch")
        account = self.store.get()
        if not all(
            math.isfinite(v) and v >= 0
            for v in (
                account.fee_model.fee_bps,
                account.fee_model.min_fee,
                account.matcher.slippage_bps,
            )
        ):
            problems.append("cost_assumptions_invalid")
        if self.failed:
            problems.append("publication_failed")
        revision = _digest(
            {
                "account": hashlib.sha256(snapshot).hexdigest(),
                "journal": hashlib.sha256(journal).hexdigest(),
                "caps": self.limits.model_dump() if self._caps_valid() else None,
                "boot": self.boot,
                "scenario": self.scenario,
                "audit": records[-1].id if records else "invalid",
            }
        )
        return problems, revision, records

    def validate_transaction(self, account: PaperAccount) -> None:
        """Runs under the SAME account lock before proposal/demo matching or journal append."""
        if self._inspect()[0]:
            raise PaperControlError("paper_control_evidence_blocked")

    def validate_fresh_submission(self, account: PaperAccount, instrument: Instrument) -> None:
        """Guard only fresh proposal effects under its existing account transaction.

        Historical completed/journal replay is handled before this optional hook.
        Pause must refuse before the legacy proposal path journals a rejection.
        """
        self.validate_transaction(account)
        if account.kill_switch or account.kill_switches.get(instrument.venue, False):
            raise PaperControlError("paper_control_paused")

    def status(self) -> dict:
        with self.store.transaction(validate=False):
            problems, revision, records = self._inspect()
            account = self.store.get()
            receipts = [self._receipt(r, records) for r in records if r.kind == "outcome"]
            return {
                "synthetic": True,
                "paper": True,
                "paused": account.kill_switch,
                "blocked": bool(problems),
                "pause_reason": self.reason,
                "checks": problems,
                "revision": revision,
                "limits": self.limits.model_dump() if self._caps_valid() else None,
                "costs": {
                    "fee_bps": account.fee_model.fee_bps,
                    "min_fee": account.fee_model.min_fee,
                    "slippage_bps": account.matcher.slippage_bps,
                },
                "venue_stops": {v.value: stopped for v, stopped in account.kill_switches.items()},
                "last_receipt": receipts[-1] if receipts else None,
                "history": receipts[-20:],
            }

    def preflight(self, target: str | None = None) -> dict:
        with self.store.transaction(validate=False):
            result = self.status()
            result["revision"] = _digest({"state_revision": result["revision"], "target": target})
            result["target"] = target
            return result

    @staticmethod
    def _receipt(record: AuditRecord, records: list[AuditRecord]) -> dict:
        intent = next(r for r in records if r.id == record.data["intent"])
        return {"id": record.id, **intent.data, "outcome": "completed"}

    def receipt(self, identifier: str) -> dict:
        with self.store.transaction(validate=False):
            try:
                records = self._records()
            except (OSError, ValueError):
                raise PaperControlError("audit_invalid_or_incomplete") from None
            for record in records:
                if record.id == identifier and record.kind == "outcome":
                    return self._receipt(record, records)
        raise PaperControlError("receipt_not_found")

    def audit_bytes(self) -> bytes:
        with self.store.transaction(validate=False):
            try:
                self._records()
                return _read(self.audit.path, MAX_AUDIT_BYTES)
            except (OSError, ValueError):
                raise PaperControlError("audit_invalid_or_incomplete") from None

    def _binding(self) -> str:
        return _digest({"account": str(self.account_path.resolve()), "scenario": self.scenario})

    def _publish(
        self,
        action: str,
        *,
        key: str,
        reason: str,
        revision: str,
        target: str | None,
        records: list[AuditRecord],
        confirmation: bool = False,
    ) -> dict:
        payload = {
            "action": action,
            "key": key,
            "reason": reason,
            "requested_revision": revision,
            "confirmation": confirmation,
            "target": target,
            "boot": self.boot,
            "recorded_at": datetime.now(UTC).isoformat(),
            "account_binding": self._binding(),
            "configuration": _digest(
                {
                    "scenario": self.scenario,
                    "account": str(self.account_path.absolute()),
                    "caps": self.limits.model_dump() if self._caps_valid() else None,
                }
            ),
        }
        account = self.store.get()
        if action == "resume":
            if target is None:
                updated = account.model_copy(update={"kill_switch": False})
            else:
                stops = dict(account.kill_switches)
                from quantmesh.domain.models import Venue

                stops.pop(Venue(target), None)
                updated = account.model_copy(update={"kill_switches": stops})
        else:
            updates: dict = {"kill_switch": True}
            if action == "startup" and self._caps_valid():
                updates["risk_limits"] = self.limits
            if target is not None:
                from quantmesh.domain.models import Venue

                stops = dict(account.kill_switches)
                stops[Venue(target)] = True
                updates["kill_switches"] = stops
            updated = account.model_copy(update=updates)
        try:
            intent = self._append("intent", payload, records)
            self.store.replace(updated)
            outcome = self._append("outcome", {"intent": intent.id}, records)
        except (OSError, ValueError) as error:
            self.failed = True
            self.reason = "publication_failed"
            raise PaperControlError("publication_failed") from error
        self.reason = reason
        return self._receipt(outcome, records)

    def transition(
        self,
        action: Literal["pause", "resume"],
        *,
        key: str,
        reason: str,
        revision: str = "",
        confirmation: bool = False,
        target: str | None = None,
    ) -> dict:
        if not _KEY.fullmatch(key) or not reason.strip() or len(reason) > 240:
            raise PaperControlError("invalid_action")
        if action not in {"pause", "resume"}:
            raise PaperControlError("invalid_action")
        if target is not None:
            from quantmesh.domain.models import Venue

            try:
                Venue(target)
            except ValueError:
                raise PaperControlError("invalid_target") from None
        with self.store.transaction(validate=False):
            try:
                records = self._records()
            except (OSError, ValueError):
                raise PaperControlError("audit_invalid_or_incomplete") from None
            for record in records:
                if record.kind == "intent" and record.data["key"] == key:
                    expected = (action, reason, revision, confirmation, target)
                    actual = tuple(
                        record.data[k]
                        for k in (
                            "action",
                            "reason",
                            "requested_revision",
                            "confirmation",
                            "target",
                        )
                    )
                    if expected != actual:
                        raise PaperControlError("key_conflict")
                    outcome = next(
                        r for r in records if r.kind == "outcome" and r.data["intent"] == record.id
                    )
                    return {
                        "receipt": self._receipt(outcome, records),
                        "replay": True,
                        "status": self.status(),
                    }
            problems, current_revision, _ = self._inspect()
            if action == "resume":
                if not confirmation:
                    raise PaperControlError("confirmation_required")
                if problems:
                    raise PaperControlError("paper_control_evidence_blocked")
                if revision != _digest({"state_revision": current_revision, "target": target}):
                    raise PaperControlError("stale_revision")
            elif any(p != "rehearsal_limits_missing_or_invalid" for p in problems):
                raise PaperControlError("paper_control_evidence_blocked")
            receipt = self._publish(
                action,
                key=key,
                reason=reason,
                revision=revision,
                confirmation=confirmation,
                target=target,
                records=records,
            )
            return {"receipt": receipt, "replay": False, "status": self.status()}
