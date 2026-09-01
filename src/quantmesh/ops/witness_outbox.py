"""Immutable local witness intents and an injected single-authority publisher."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.ops.connection_witness import (
    ConnectionWitnessReceiptV1,
    ConnectionWitnessStore,
)
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunConflictError,
    ImmutableRunStore,
    LeaseOwner,
    SlotLease,
    publish_create_once,
    read_safe_bytes,
    reject_reparse_chain,
)
from quantmesh.ops.trusted_data_soak import SoakStoreV2

_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_COMMIT_PATTERN = r"^[0-9a-f]{40}$"
_PUBLISHER_SLOT = "1970-01-01"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(UTC)


def _roots_overlap(left: Path, right: Path) -> bool:
    first, second = left.resolve(), right.resolve()
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


class WitnessKind(StrEnum):
    DAILY_ACCEPTED = "daily-accepted"
    CONNECTION_STATE = "connection-state"


def _idempotency_key(
    issue_number: int,
    witness_kind: WitnessKind,
    local_evidence_id: str,
) -> str:
    return _digest(
        {
            "issue_number": issue_number,
            "witness_kind": witness_kind.value,
            "local_evidence_id": local_evidence_id,
        }
    )


def _render_body(values: dict[str, Any], idempotency_key: str) -> str:
    report_id = values.get("report_id") or "none"
    return "\n".join(
        (
            f"<!-- quantmesh-witness-key:{idempotency_key} -->",
            "QuantMesh immutable local witness",
            f"kind: {values['witness_kind'].value}",
            f"local-evidence-id: {values['local_evidence_id']}",
            f"terminal-receipt-id: {values['terminal_receipt_id']}",
            f"report-id: {report_id}",
            f"source-contract-id: {values['source_contract_id']}",
            f"code-commit: {values['code_commit']}",
            f"occurred-at: {values['occurred_at'].isoformat()}",
            f"summary: {values['summary']}",
        )
    )


class WitnessIntentV1(_FrozenContract):
    contract: str = Field(default="witness-intent-v1", pattern=r"^witness-intent-v1$")
    issue_number: int = Field(ge=1, le=2**31 - 1)
    witness_kind: WitnessKind
    local_evidence_id: str = Field(pattern=_DIGEST_PATTERN)
    terminal_receipt_id: str = Field(pattern=_DIGEST_PATTERN)
    report_id: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    source_contract_id: str = Field(pattern=_DIGEST_PATTERN)
    code_commit: str = Field(pattern=_COMMIT_PATTERN)
    occurred_at: datetime
    summary: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(pattern=_DIGEST_PATTERN)
    body: str = Field(min_length=1)
    body_digest: str = Field(pattern=_DIGEST_PATTERN)
    intent_id: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("occurred_at")
    @classmethod
    def occurred_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "witness occurrence")

    @field_validator("summary")
    @classmethod
    def summary_is_one_line(cls, value: str) -> str:
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError("witness summary must be one nonblank line")
        return value

    @model_validator(mode="after")
    def authority_and_identity_match(self) -> Self:
        if self.witness_kind is WitnessKind.DAILY_ACCEPTED:
            if self.issue_number != 124 or self.report_id is None:
                raise ValueError("daily accepted witness requires issue 124 and a report")
        elif self.issue_number != 127:
            raise ValueError("connection state witness requires issue 127")
        expected_key = _idempotency_key(
            self.issue_number, self.witness_kind, self.local_evidence_id
        )
        if self.idempotency_key != expected_key:
            raise ValueError("witness idempotency key disagrees with its authority tuple")
        values = self.model_dump(mode="python")
        expected_body = _render_body(values, expected_key)
        if self.body != expected_body or self.body_digest != _text_digest(expected_body):
            raise ValueError("witness body disagrees with its exact local evidence")
        body = self.model_dump(mode="json", exclude={"intent_id"})
        if self.intent_id != _digest(body):
            raise ValueError("witness intent ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> WitnessIntentV1:
        clean = {
            key: value
            for key, value in values.items()
            if key
            not in {
                "contract",
                "idempotency_key",
                "body",
                "body_digest",
                "intent_id",
            }
        }
        key = _idempotency_key(
            clean["issue_number"], clean["witness_kind"], clean["local_evidence_id"]
        )
        body = _render_body(clean, key)
        complete = {
            **clean,
            "idempotency_key": key,
            "body": body,
            "body_digest": _text_digest(body),
        }
        probe = cls.model_construct(**complete, intent_id="0" * 64)
        return cls(
            **complete,
            intent_id=_digest(probe.model_dump(mode="json", exclude={"intent_id"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class RemoteCommentV1(_FrozenContract):
    contract: str = Field(default="remote-comment-v1", pattern=r"^remote-comment-v1$")
    issue_number: int = Field(ge=1)
    idempotency_key: str = Field(pattern=_DIGEST_PATTERN)
    comment_url: str = Field(min_length=1)
    body: str = Field(min_length=1)
    body_digest: str = Field(pattern=_DIGEST_PATTERN)
    read_back_digest: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("comment_url")
    @classmethod
    def url_is_https(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("remote comment URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def digests_match(self) -> Self:
        parsed = urlparse(self.comment_url)
        expected_path = f"/ZP151/quantmesh/issues/{self.issue_number}"
        if (
            parsed.netloc != "github.com"
            or parsed.path != expected_path
            or parsed.params
            or parsed.query
            or re.fullmatch(r"issuecomment-\d+", parsed.fragment) is None
        ):
            raise ValueError(
                "remote comment URL must identify the expected ZP151/quantmesh issue comment"
            )
        if self.body_digest != _text_digest(self.body):
            raise ValueError("remote comment body digest disagrees with read-back body")
        body = self.model_dump(mode="json", exclude={"read_back_digest"})
        if self.read_back_digest != _digest(body):
            raise ValueError("remote comment read-back digest disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> RemoteCommentV1:
        clean = {
            key: value
            for key, value in values.items()
            if key not in {"contract", "body_digest", "read_back_digest"}
        }
        complete = {**clean, "body_digest": _text_digest(clean["body"])}
        probe = cls.model_construct(**complete, read_back_digest="0" * 64)
        return cls(
            **complete,
            read_back_digest=_digest(probe.model_dump(mode="json", exclude={"read_back_digest"})),
        )


class WitnessPublicationReceiptV1(_FrozenContract):
    contract: str = Field(
        default="witness-publication-receipt-v1",
        pattern=r"^witness-publication-receipt-v1$",
    )
    idempotency_key: str = Field(pattern=_DIGEST_PATTERN)
    intent_id: str = Field(pattern=_DIGEST_PATTERN)
    issue_number: int = Field(ge=1)
    local_evidence_id: str = Field(pattern=_DIGEST_PATTERN)
    terminal_receipt_id: str = Field(pattern=_DIGEST_PATTERN)
    comment_url: str = Field(min_length=1)
    remote_body: str = Field(min_length=1)
    remote_body_digest: str = Field(pattern=_DIGEST_PATTERN)
    read_back_digest: str = Field(pattern=_DIGEST_PATTERN)
    recorded_at: datetime
    receipt_id: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("comment_url")
    @classmethod
    def publication_url_is_https(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("publication comment URL must use HTTPS")
        return value

    @field_validator("recorded_at")
    @classmethod
    def recorded_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "publication receipt time")

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        comment = RemoteCommentV1.build(
            issue_number=self.issue_number,
            idempotency_key=self.idempotency_key,
            comment_url=self.comment_url,
            body=self.remote_body,
        )
        if (
            self.remote_body_digest != comment.body_digest
            or self.read_back_digest != comment.read_back_digest
        ):
            raise ValueError("publication receipt remote read-back is inconsistent")
        body = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != _digest(body):
            raise ValueError("publication receipt ID disagrees with its body")
        return self

    @classmethod
    def build(
        cls,
        intent: WitnessIntentV1,
        comment: RemoteCommentV1,
        *,
        recorded_at: datetime,
    ) -> WitnessPublicationReceiptV1:
        values = {
            "idempotency_key": intent.idempotency_key,
            "intent_id": intent.intent_id,
            "issue_number": intent.issue_number,
            "local_evidence_id": intent.local_evidence_id,
            "terminal_receipt_id": intent.terminal_receipt_id,
            "comment_url": comment.comment_url,
            "remote_body": comment.body,
            "remote_body_digest": comment.body_digest,
            "read_back_digest": comment.read_back_digest,
            "recorded_at": recorded_at,
        }
        probe = cls.model_construct(**values, receipt_id="0" * 64)
        return cls(
            **values,
            receipt_id=_digest(probe.model_dump(mode="json", exclude={"receipt_id"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class OutboxReconciliationFailureV1(_FrozenContract):
    contract: str = Field(
        default="outbox-reconciliation-failure-v1",
        pattern=r"^outbox-reconciliation-failure-v1$",
    )
    source_kind: WitnessKind
    terminal_receipt_id: str = Field(pattern=_DIGEST_PATTERN)
    error_code: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    detail: str = Field(min_length=1)
    observed_at: datetime
    failure_id: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("observed_at")
    @classmethod
    def observed_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "outbox reconciliation failure time")

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        body = self.model_dump(mode="json", exclude={"failure_id"})
        if self.failure_id != _digest(body):
            raise ValueError("outbox reconciliation failure ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> OutboxReconciliationFailureV1:
        probe = cls.model_construct(**values, failure_id="0" * 64)
        return cls(
            **values,
            failure_id=_digest(probe.model_dump(mode="json", exclude={"failure_id"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class AmbiguousRemoteResult(RuntimeError):
    """Remote POST may have committed even though the response was lost."""


class DuplicateRemoteWitnessError(RuntimeError):
    """More than one remote comment claims one idempotency key."""


class PublicationValidationError(RuntimeError):
    """Remote read-back cannot validate the exact intended bytes."""


class IneligibleWitnessError(ValueError):
    """A local terminal is not eligible for the requested witness kind."""


class OutboxIntentError(RuntimeError):
    """An eligible durable terminal could not be paired with its exact intent."""


class RemoteWitnessClient(Protocol):
    def list_exact(self, issue_number: int, idempotency_key: str) -> Sequence[RemoteCommentV1]: ...

    def post_comment(self, issue_number: int, idempotency_key: str, body: str) -> None: ...


class WitnessOutbox:
    """Create-once local intents, receipts and typed reconciliation failures."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("witness outbox root must be absolute")
        self.intent_dir = self.root / "intents"
        self.publication_dir = self.root / "publications"
        self.failure_dir = self.root / "reconciliation-failures"
        self.publisher_root = self.root / "publisher-authority"

    def intent_path(self, idempotency_key: str) -> Path:
        return self.intent_dir / f"{idempotency_key}.json"

    def publication_path(self, idempotency_key: str) -> Path:
        return self.publication_dir / f"{idempotency_key}.json"

    def failure_path(self, failure: OutboxReconciliationFailureV1) -> Path:
        return (
            self.failure_dir
            / failure.source_kind.value
            / failure.terminal_receipt_id
            / f"{failure.error_code}.json"
        )

    def enqueue(self, intent: WitnessIntentV1) -> WitnessIntentV1:
        self._prepare()
        intent = WitnessIntentV1.model_validate(intent.model_dump(mode="python"))
        publish_create_once(
            self.intent_path(intent.idempotency_key),
            intent.canonical_bytes(),
            label="witness intent",
        )
        return self.intent(intent.idempotency_key)

    def intent(self, idempotency_key: str) -> WitnessIntentV1:
        intent = self._read_model(self.intent_path(idempotency_key), WitnessIntentV1)
        if intent.idempotency_key != idempotency_key:
            raise ValueError("witness intent path disagrees with its body")
        return intent

    def pending(self) -> tuple[WitnessIntentV1, ...]:
        self._prepare()
        paths = tuple(self.intent_dir.iterdir())
        if any(
            path.suffix != ".json" or re.fullmatch(r"[0-9a-f]{64}", path.stem) is None
            for path in paths
        ):
            raise ValueError("witness intent store contains an unexpected entry")
        intents = tuple(self.intent(path.stem) for path in paths)
        publication_paths = tuple(self.publication_dir.iterdir())
        if any(
            path.suffix != ".json" or re.fullmatch(r"[0-9a-f]{64}", path.stem) is None
            for path in publication_paths
        ):
            raise ValueError("witness publication store contains an unexpected entry")
        published = {self.publication(path.stem).idempotency_key for path in publication_paths}
        pending = [intent for intent in intents if intent.idempotency_key not in published]
        return tuple(sorted(pending, key=lambda item: item.idempotency_key))

    def publication(self, idempotency_key: str) -> WitnessPublicationReceiptV1:
        receipt = self._read_model(
            self.publication_path(idempotency_key), WitnessPublicationReceiptV1
        )
        intent = self.intent(idempotency_key)
        self._validate_publication(intent, receipt)
        return receipt

    def record_publication(
        self, receipt: WitnessPublicationReceiptV1
    ) -> WitnessPublicationReceiptV1:
        self._prepare()
        receipt = WitnessPublicationReceiptV1.model_validate(receipt.model_dump(mode="python"))
        intent = self.intent(receipt.idempotency_key)
        self._validate_publication(intent, receipt)
        publish_create_once(
            self.publication_path(receipt.idempotency_key),
            receipt.canonical_bytes(),
            label="witness publication receipt",
        )
        return self.publication(receipt.idempotency_key)

    def acquire_publisher(
        self,
        *,
        owner: LeaseOwner,
        now: datetime,
        stale_after: timedelta,
        owner_alive: Callable[[LeaseOwner], bool] | None = None,
    ) -> SlotLease:
        self._prepare()
        return SlotLease.acquire(
            self.publisher_root,
            _PUBLISHER_SLOT,
            owner=owner,
            now=now,
            stale_after=stale_after,
            owner_alive=owner_alive,
        )

    def ensure_daily_intent(
        self,
        terminal: DailyRunReceiptV1,
        *,
        report_root: Path,
        expected_commit: str,
        expected_source_contract_id: str,
    ) -> WitnessIntentV1:
        if not Path(report_root).is_absolute() or _roots_overlap(self.root, Path(report_root)):
            raise ValueError("report and outbox roots must be absolute and disjoint")
        return self.enqueue(
            _daily_intent(
                terminal,
                report_root=report_root,
                expected_commit=expected_commit,
                expected_source_contract_id=expected_source_contract_id,
            )
        )

    def ensure_connection_intent(self, terminal: ConnectionWitnessReceiptV1) -> WitnessIntentV1:
        return self.enqueue(_connection_intent(terminal))

    def record_reconciliation_failure(
        self,
        *,
        source_kind: WitnessKind,
        terminal_receipt_id: str,
        error_code: str,
        detail: str,
        observed_at: datetime,
    ) -> OutboxReconciliationFailureV1:
        self._prepare()
        failure = OutboxReconciliationFailureV1.build(
            source_kind=source_kind,
            terminal_receipt_id=terminal_receipt_id,
            error_code=error_code,
            detail=detail,
            observed_at=observed_at,
        )
        publish_create_once(
            self.failure_path(failure),
            failure.canonical_bytes(),
            label="outbox reconciliation failure",
        )
        return failure

    def reconciliation_failures(self) -> tuple[OutboxReconciliationFailureV1, ...]:
        self._prepare()
        failures: list[OutboxReconciliationFailureV1] = []
        kind_directories = tuple(self.failure_dir.iterdir())
        allowed_kinds = {item.value for item in WitnessKind}
        if any(not path.is_dir() or path.name not in allowed_kinds for path in kind_directories):
            raise ValueError("outbox failure store contains an unexpected kind")
        for kind_directory in kind_directories:
            reject_reparse_chain(kind_directory)
            terminal_directories = tuple(kind_directory.iterdir())
            if any(
                not path.is_dir() or re.fullmatch(r"[0-9a-f]{64}", path.name) is None
                for path in terminal_directories
            ):
                raise ValueError("outbox failure store contains an unexpected terminal")
            for terminal_directory in terminal_directories:
                reject_reparse_chain(terminal_directory)
                paths = tuple(terminal_directory.iterdir())
                if any(path.suffix != ".json" for path in paths):
                    raise ValueError("outbox failure store contains an unexpected entry")
                for path in paths:
                    failure = self._read_model(path, OutboxReconciliationFailureV1)
                    if path != self.failure_path(failure):
                        raise ValueError(
                            "outbox reconciliation failure path disagrees with its body"
                        )
                    failures.append(failure)
        return tuple(sorted(failures, key=lambda item: item.failure_id))

    def _prepare(self) -> None:
        reject_reparse_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(self.root)
        for directory in (
            self.intent_dir,
            self.publication_dir,
            self.failure_dir,
            self.publisher_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
            reject_reparse_chain(directory)

    @staticmethod
    def _validate_publication(
        intent: WitnessIntentV1, receipt: WitnessPublicationReceiptV1
    ) -> None:
        if (
            receipt.idempotency_key != intent.idempotency_key
            or receipt.intent_id != intent.intent_id
            or receipt.issue_number != intent.issue_number
            or receipt.local_evidence_id != intent.local_evidence_id
            or receipt.terminal_receipt_id != intent.terminal_receipt_id
            or receipt.remote_body != intent.body
            or receipt.remote_body_digest != intent.body_digest
        ):
            raise PublicationValidationError(
                "publication receipt disagrees with the exact witness intent"
            )

    @staticmethod
    def _read_model(path: Path, model: type[_FrozenContract]):
        payload = read_safe_bytes(path)
        evidence = model.model_validate_json(payload)
        if payload != canonical_json_bytes(evidence.model_dump(mode="json")):
            raise ValueError(f"outbox evidence JSON is not canonical: {path}")
        return evidence


class WitnessPublisher:
    """Pure coordinator; all remote behavior is supplied by the injected client."""

    def __init__(
        self,
        outbox: WitnessOutbox,
        remote: RemoteWitnessClient,
        *,
        lease_seconds: float = 300,
    ) -> None:
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("publisher lease duration must be positive")
        self.outbox = outbox
        self.remote = remote
        self.lease_seconds = lease_seconds

    def publish_pending(
        self,
        *,
        now: datetime,
        owner: LeaseOwner | None = None,
    ) -> tuple[WitnessPublicationReceiptV1, ...]:
        if not self.outbox.pending():
            return ()
        publisher = owner or LeaseOwner.current(token=uuid.uuid4().hex)
        lease = self.outbox.acquire_publisher(
            owner=publisher,
            now=now,
            stale_after=timedelta(seconds=self.lease_seconds),
        )
        try:
            pending = self.outbox.pending()
            return tuple(self._publish_one(intent, now=now) for intent in pending)
        finally:
            lease.release()

    def _publish_one(
        self, intent: WitnessIntentV1, *, now: datetime
    ) -> WitnessPublicationReceiptV1:
        matches = self._matches(intent)
        if matches:
            return self._record_match(intent, matches, now=now)
        for attempt in range(2):
            try:
                self.remote.post_comment(intent.issue_number, intent.idempotency_key, intent.body)
            except AmbiguousRemoteResult:
                matches = self._matches(intent)
                if matches:
                    return self._record_match(intent, matches, now=now)
                if attempt == 1:
                    raise
                continue
            matches = self._matches(intent)
            if not matches:
                raise PublicationValidationError(
                    "remote POST completed without exact read-back evidence"
                )
            return self._record_match(intent, matches, now=now)
        raise AssertionError("publisher retry loop did not terminate")

    def _matches(self, intent: WitnessIntentV1) -> tuple[RemoteCommentV1, ...]:
        matches = tuple(
            RemoteCommentV1.model_validate(item)
            for item in self.remote.list_exact(intent.issue_number, intent.idempotency_key)
        )
        if len(matches) > 1:
            raise DuplicateRemoteWitnessError(
                "multiple remote comments claim one witness idempotency key"
            )
        return matches

    def _record_match(
        self,
        intent: WitnessIntentV1,
        matches: tuple[RemoteCommentV1, ...],
        *,
        now: datetime,
    ) -> WitnessPublicationReceiptV1:
        comment = matches[0]
        if (
            comment.issue_number != intent.issue_number
            or comment.idempotency_key != intent.idempotency_key
            or comment.body_digest != intent.body_digest
        ):
            raise PublicationValidationError(
                "remote read-back digest disagrees with the exact witness intent"
            )
        return self.outbox.record_publication(
            WitnessPublicationReceiptV1.build(intent, comment, recorded_at=now)
        )


def _daily_intent(
    terminal: DailyRunReceiptV1,
    *,
    report_root: Path,
    expected_commit: str,
    expected_source_contract_id: str,
) -> WitnessIntentV1:
    proof = terminal.verification
    if (
        terminal.status is not DailyRunStatus.PASSED
        or proof is None
        or not proof.accepted
        or proof.reasons
        or proof.report_count < 1
        or proof.xnys_session_count < 1
        or terminal.soak_report_id is None
    ):
        raise IneligibleWitnessError("issue 124 success requires a passing full-verifier proof")
    try:
        validated = DailyRunReceiptV1.model_validate(terminal.model_dump(mode="python"))
    except ValueError as error:
        raise IneligibleWitnessError("daily terminal contract is invalid") from error
    if (
        validated.code_commit != expected_commit
        or validated.source_contract_id != expected_source_contract_id
    ):
        raise IneligibleWitnessError("daily terminal source identity is not expected")
    try:
        store = SoakStoreV2(report_root)
        candidate = store.load_candidate()
        reports = store.reports()
        matches = tuple(item for item in reports if item.report_id == validated.soak_report_id)
    except (OSError, ValueError) as error:
        raise IneligibleWitnessError("daily report read-back is invalid") from error
    if len(matches) != 1:
        raise IneligibleWitnessError("exact daily report is missing or ambiguous")
    report = matches[0]
    if (
        report.critical_issues
        or proof.report_count != len(reports)
        or report.candidate_id != candidate.candidate_id
        or report.candidate_id != proof.candidate_id
        or report.code_commit != expected_commit
        or report.source_contract_id != expected_source_contract_id
        or candidate.code_commit != expected_commit
        or candidate.source_contract_id != expected_source_contract_id
        or candidate.config_digest != report.config_digest
    ):
        raise IneligibleWitnessError("daily report, candidate and verifier proof do not match")
    return WitnessIntentV1.build(
        issue_number=124,
        witness_kind=WitnessKind.DAILY_ACCEPTED,
        local_evidence_id=validated.run_id,
        terminal_receipt_id=validated.receipt_id,
        report_id=report.report_id,
        source_contract_id=validated.source_contract_id,
        code_commit=validated.code_commit,
        occurred_at=validated.finished_at,
        summary=f"daily slot {validated.slot} attempt {validated.attempt} accepted",
    )


def _connection_intent(terminal: ConnectionWitnessReceiptV1) -> WitnessIntentV1:
    try:
        validated = ConnectionWitnessReceiptV1.model_validate(terminal.model_dump(mode="python"))
    except ValueError as error:
        raise IneligibleWitnessError("connection terminal contract is invalid") from error
    return WitnessIntentV1.build(
        issue_number=127,
        witness_kind=WitnessKind.CONNECTION_STATE,
        local_evidence_id=validated.run_id,
        terminal_receipt_id=validated.receipt_id,
        report_id=validated.soak_report_id,
        source_contract_id=validated.expected_source_contract_id,
        code_commit=validated.expected_commit,
        occurred_at=validated.finished_at,
        summary=(
            f"connection slot {validated.slot} attempt {validated.attempt} "
            f"{validated.execution_kind.value} {validated.status.value}"
        ),
    )


class WitnessReconciler:
    """Scan exact local terminal stores and repair missing intent pairings."""

    def __init__(
        self,
        outbox: WitnessOutbox,
        *,
        report_root: Path,
        expected_commit: str,
        expected_source_contract_id: str,
    ) -> None:
        self.outbox = outbox
        self.report_root = Path(report_root)
        if not self.report_root.is_absolute():
            raise ValueError("witness reconciliation report root must be absolute")
        if _roots_overlap(self.outbox.root, self.report_root):
            raise ValueError("witness reconciliation report and outbox roots must be disjoint")
        if re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
            raise ValueError("witness reconciliation commit must be a full SHA")
        if re.fullmatch(r"[0-9a-f]{64}", expected_source_contract_id) is None:
            raise ValueError("witness reconciliation source contract must be a digest")
        self.expected_commit = expected_commit
        self.expected_source_contract_id = expected_source_contract_id

    def reconcile_daily(self, run_root: Path) -> tuple[WitnessIntentV1, ...]:
        if not Path(run_root).is_absolute():
            raise ValueError("daily reconciliation root must be absolute")
        if _roots_overlap(self.outbox.root, Path(run_root)) or _roots_overlap(
            self.report_root, Path(run_root)
        ):
            raise ValueError("daily run, report and outbox roots must be disjoint")
        created: list[WitnessIntentV1] = []
        for terminal in _daily_terminals(run_root):
            if terminal.status is not DailyRunStatus.PASSED:
                continue
            try:
                intent = _daily_intent(
                    terminal,
                    report_root=self.report_root,
                    expected_commit=self.expected_commit,
                    expected_source_contract_id=self.expected_source_contract_id,
                )
                existed = self.outbox.intent_path(intent.idempotency_key).exists()
                paired = self.outbox.enqueue(intent)
                if not existed:
                    created.append(paired)
            except Exception as error:
                self._record_failure(WitnessKind.DAILY_ACCEPTED, terminal, error)
                raise
        return tuple(created)

    def reconcile_connection(self, run_root: Path) -> tuple[WitnessIntentV1, ...]:
        if not Path(run_root).is_absolute():
            raise ValueError("connection reconciliation root must be absolute")
        if _roots_overlap(self.outbox.root, Path(run_root)) or _roots_overlap(
            self.report_root, Path(run_root)
        ):
            raise ValueError("connection run, report and outbox roots must be disjoint")
        created: list[WitnessIntentV1] = []
        for terminal in _connection_terminals(run_root):
            if (
                terminal.expected_commit != self.expected_commit
                or terminal.expected_source_contract_id != self.expected_source_contract_id
            ):
                error = IneligibleWitnessError(
                    "connection terminal source identity is not expected"
                )
                self._record_failure(WitnessKind.CONNECTION_STATE, terminal, error)
                raise error
            try:
                intent = _connection_intent(terminal)
                existed = self.outbox.intent_path(intent.idempotency_key).exists()
                paired = self.outbox.enqueue(intent)
                if not existed:
                    created.append(paired)
            except Exception as error:
                self._record_failure(WitnessKind.CONNECTION_STATE, terminal, error)
                raise
        return tuple(created)

    def _record_failure(
        self,
        kind: WitnessKind,
        terminal: DailyRunReceiptV1 | ConnectionWitnessReceiptV1,
        error: Exception,
    ) -> None:
        conflict = isinstance(error, ImmutableRunConflictError)
        self.outbox.record_reconciliation_failure(
            source_kind=kind,
            terminal_receipt_id=terminal.receipt_id,
            error_code="intent-conflict" if conflict else "intent-error",
            detail=(
                "exact intent conflicts with durable outbox evidence"
                if conflict
                else f"intent reconciliation raised {type(error).__name__}"
            ),
            observed_at=terminal.finished_at,
        )


def _daily_terminals(root: Path) -> tuple[DailyRunReceiptV1, ...]:
    store = ImmutableRunStore(root)
    if not store.terminal_dir.exists():
        return ()
    reject_reparse_chain(store.terminal_dir)
    directories = tuple(store.terminal_dir.iterdir())
    if any(
        not path.is_dir() or re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name) is None
        for path in directories
    ):
        raise ValueError("daily terminal store contains an unexpected entry")
    return tuple(
        terminal
        for directory in sorted(directories, key=lambda item: item.name)
        for terminal in store.terminals(directory.name)
    )


def _connection_terminals(root: Path) -> tuple[ConnectionWitnessReceiptV1, ...]:
    store = ConnectionWitnessStore(root)
    if not store.terminal_dir.exists():
        return ()
    reject_reparse_chain(store.terminal_dir)
    directories = tuple(store.terminal_dir.iterdir())
    if any(
        not path.is_dir() or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{4}Z", path.name) is None
        for path in directories
    ):
        raise ValueError("connection terminal store contains an unexpected entry")
    terminals: list[ConnectionWitnessReceiptV1] = []
    for directory in sorted(directories, key=lambda item: item.name):
        token = directory.name
        slot = f"{token[:13]}:{token[13:15]}Z"
        terminals.extend(store.terminals(slot))
    return tuple(terminals)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantmesh-soak-witness-outbox")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--outbox-root", type=Path, required=True)
    show = subparsers.add_parser("show")
    show.add_argument("--outbox-root", type=Path, required=True)
    show.add_argument("--idempotency-key", required=True)
    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--outbox-root", type=Path, required=True)
    reconcile.add_argument("--report-root", type=Path, required=True)
    reconcile.add_argument("--daily-run-root", type=Path, required=True)
    reconcile.add_argument("--connection-run-root", type=Path, required=True)
    reconcile.add_argument("--expected-commit", required=True)
    reconcile.add_argument("--expected-source-contract-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    outbox = WitnessOutbox(args.outbox_root)
    try:
        if args.command == "list":
            print(
                canonical_json_bytes(
                    [item.model_dump(mode="json") for item in outbox.pending()]
                ).decode("utf-8")
            )
            return 0
        if args.command == "show":
            print(outbox.intent(args.idempotency_key).canonical_bytes().decode("utf-8"))
            return 0
        if args.command == "reconcile":
            reconciler = WitnessReconciler(
                outbox,
                report_root=args.report_root,
                expected_commit=args.expected_commit,
                expected_source_contract_id=args.expected_source_contract_id,
            )
            created = (
                *reconciler.reconcile_daily(args.daily_run_root),
                *reconciler.reconcile_connection(args.connection_run_root),
            )
            print(
                canonical_json_bytes([item.model_dump(mode="json") for item in created]).decode(
                    "utf-8"
                )
            )
            return 0
        raise AssertionError(f"unsupported outbox command: {args.command}")
    except Exception as error:
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
