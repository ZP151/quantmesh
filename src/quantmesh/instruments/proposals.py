"""Append-only forecast-to-paper proposals with explicit operator confirmation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Quote, Side
from quantmesh.domain.orders import Order, OrderStatus, OrderType
from quantmesh.execution.accounting import PaperAccount
from quantmesh.execution.journal import OrderJournal
from quantmesh.instruments.contracts import (
    PROPOSAL_ID_PATTERN,
    PaperProposal,
    PriceForecastArtifact,
    ProposalConfirmation,
    ProposalEvent,
    ProposalStatus,
)
from quantmesh.instruments.forecast import validate_price_forecast_artifact
from quantmesh.live.fence import QuoteFence
from quantmesh.settings import settings

PROPOSALS_FILE = "proposals.jsonl"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _path_is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    if hasattr(path, "is_junction") and path.is_junction():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x400)


def _reject_reparse_components(path: Path) -> None:
    for component in (path, *path.parents):
        if component.exists() and _path_is_link_or_reparse(component):
            raise ValueError(
                f"proposal ledger path component {component} is a link or reparse point"
            )


def _proposal_identity(proposal: PaperProposal) -> dict[str, object]:
    return proposal.model_dump(
        mode="json",
        exclude={"status", "blockers", "order_id", "quote_provenance"},
    )


def _forecast_age_sessions(artifact: PriceForecastArtifact, now: datetime) -> int:
    continuous = artifact.instrument.instrument_type in {
        InstrumentType.SPOT,
        InstrumentType.PERPETUAL,
    }
    count = 0
    candidate = artifact.train_end + timedelta(days=1)
    while candidate.date() <= now.date():
        if continuous or candidate.weekday() < 5:
            count += 1
        candidate += timedelta(days=1)
    return count


def _freshness_blocker(artifact: PriceForecastArtifact, now: datetime) -> str | None:
    age = _forecast_age_sessions(artifact, now)
    if age <= 1:
        return None
    return f"forecast artifact is {age} sessions old at proposal time; maximum is one session"


class ProposalLedger:
    """Atomic JSONL event ledger; proposal identity is immutable across states."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.orders_dir / "proposals"
        self._lock = threading.RLock()

    def _safe_root(self) -> None:
        _reject_reparse_components(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise ValueError(f"proposal ledger root {self.root} is not a safe directory")

    def record(self, proposal: PaperProposal) -> PaperProposal:
        with self._lock:
            events = self._read()
            if any(event.proposal_id == proposal.id for event in events):
                raise ValueError(f"proposal {proposal.id!r} already recorded")
            if proposal.status not in {ProposalStatus.PENDING, ProposalStatus.BLOCKED}:
                raise ValueError("initial proposal state must be pending or blocked")
            self._write(
                [
                    *events,
                    ProposalEvent(
                        proposal_id=proposal.id,
                        sequence=1,
                        recorded_at=proposal.created_at,
                        proposal=proposal,
                    ),
                ]
            )
            return proposal

    def transition(self, proposal: PaperProposal, *, recorded_at: datetime) -> PaperProposal:
        with self._lock:
            events = self._read()
            own = [event for event in events if event.proposal_id == proposal.id]
            if not own:
                raise ValueError(f"no proposal recorded with id {proposal.id!r}")
            current = own[-1].proposal
            if current.status is not ProposalStatus.PENDING:
                raise ValueError(
                    f"proposal {proposal.id!r} is terminal in state {current.status.value!r}"
                )
            if proposal.status not in {
                ProposalStatus.BLOCKED,
                ProposalStatus.CONFIRMED,
                ProposalStatus.REJECTED,
            }:
                raise ValueError("pending proposal can only become blocked, confirmed or rejected")
            if _proposal_identity(current) != _proposal_identity(proposal):
                raise ValueError("proposal identity cannot change across transitions")
            self._write(
                [
                    *events,
                    ProposalEvent(
                        proposal_id=proposal.id,
                        sequence=len(own) + 1,
                        recorded_at=recorded_at,
                        proposal=proposal,
                    ),
                ]
            )
            return proposal

    def get(self, proposal_id: str) -> PaperProposal:
        if re.fullmatch(PROPOSAL_ID_PATTERN, proposal_id) is None:
            raise ValueError("invalid proposal id")
        own = [event for event in self._read() if event.proposal_id == proposal_id]
        if not own:
            raise ValueError(f"no proposal recorded with id {proposal_id!r}")
        return own[-1].proposal

    def events(self, proposal_id: str) -> tuple[ProposalEvent, ...]:
        self.get(proposal_id)
        return tuple(event for event in self._read() if event.proposal_id == proposal_id)

    def all(self) -> tuple[PaperProposal, ...]:
        latest: dict[str, PaperProposal] = {}
        for event in self._read():
            latest[event.proposal_id] = event.proposal
        return tuple(latest[key] for key in sorted(latest))

    def _write(self, events: list[ProposalEvent]) -> None:
        self._safe_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._safe_root()
        path = self.root / PROPOSALS_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{PROPOSALS_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(event.model_dump_json())
                    handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[ProposalEvent]:
        self._safe_root()
        if not self.root.exists():
            return []
        path = self.root / PROPOSALS_FILE
        if not path.exists():
            return []
        if not path.is_file() or _path_is_link_or_reparse(path):
            raise ValueError(f"proposal ledger {path} is missing or unsafe")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"proposal ledger {path} is unreadable") from error
        events: list[ProposalEvent] = []
        by_id: dict[str, list[ProposalEvent]] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = ProposalEvent.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(f"proposal ledger {path} line {line_number} is invalid") from error
            prior = by_id.setdefault(event.proposal_id, [])
            if event.sequence != len(prior) + 1:
                raise ValueError(
                    f"proposal ledger {path} line {line_number} has a non-contiguous sequence"
                )
            if not prior:
                if event.proposal.status not in {
                    ProposalStatus.PENDING,
                    ProposalStatus.BLOCKED,
                }:
                    raise ValueError(
                        f"proposal ledger {path} line {line_number} has an illegal initial state"
                    )
            else:
                previous = prior[-1].proposal
                if event.recorded_at < prior[-1].recorded_at:
                    raise ValueError(
                        f"proposal ledger {path} line {line_number} regresses event time"
                    )
                if previous.status is not ProposalStatus.PENDING:
                    raise ValueError(
                        f"proposal ledger {path} line {line_number} follows a terminal state"
                    )
                if event.proposal.status not in {
                    ProposalStatus.BLOCKED,
                    ProposalStatus.CONFIRMED,
                    ProposalStatus.REJECTED,
                }:
                    raise ValueError(
                        f"proposal ledger {path} line {line_number} has an illegal transition"
                    )
                if _proposal_identity(previous) != _proposal_identity(event.proposal):
                    raise ValueError(
                        f"proposal ledger {path} line {line_number} changes immutable identity"
                    )
            prior.append(event)
            events.append(event)
        return events


class PaperDecisionService:
    """Two-stage proposal service over the existing paper order authority."""

    def __init__(
        self,
        *,
        ledger: ProposalLedger,
        artifact_resolver: Callable[[str], PriceForecastArtifact | None],
        account_provider: Callable[[], PaperAccount],
        account_sink: Callable[[PaperAccount], None],
        journal: OrderJournal | None,
        snapshot_provider: Callable[[], Mapping[str, object] | None],
        quote_fence: QuoteFence,
        demo_quote_provider: Callable[[Instrument, datetime], Quote] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.ledger = ledger
        self._artifact_resolver = artifact_resolver
        self._account_provider = account_provider
        self._account_sink = account_sink
        self._journal = journal
        self._snapshot_provider = snapshot_provider
        self._quote_fence = quote_fence
        self._demo_quote_provider = demo_quote_provider
        self._now = now
        self._lock = threading.RLock()

    def _resolve_artifact(self, artifact_id: str) -> PriceForecastArtifact:
        artifact = self._artifact_resolver(artifact_id)
        if artifact is None:
            raise ValueError(f"forecast artifact {artifact_id!r} is unavailable")
        return validate_price_forecast_artifact(artifact)

    def propose(
        self,
        artifact: PriceForecastArtifact,
        *,
        side: Side,
        quantity: float,
        limit_price: float | None = None,
    ) -> PaperProposal:
        with self._lock:
            artifact = validate_price_forecast_artifact(artifact)
            resolved = self._resolve_artifact(artifact.id)
            if resolved != artifact:
                raise ValueError("proposal artifact does not match the registered artifact")
            created_at = self._now()
            if created_at.tzinfo is None:
                raise ValueError("proposal clock must be timezone-aware")
            created_at = created_at.astimezone(UTC)
            order_type = OrderType.LIMIT if limit_price is not None else OrderType.MARKET
            setup = {
                "artifact_id": artifact.id,
                "created_at": created_at.isoformat(),
                "limit_price": limit_price,
                "quantity": quantity,
                "side": side.value,
            }
            proposal_id = f"proposal-{_sha256(setup)[:24]}"
            confirmation_token = _sha256(
                {
                    "artifact_id": artifact.id,
                    "config_digest": artifact.config_digest,
                    "proposal_id": proposal_id,
                }
            )
            blockers = artifact.blockers if not artifact.eligible else ()
            freshness = _freshness_blocker(artifact, created_at)
            if freshness is not None:
                blockers = (*blockers, freshness)
            proposal = PaperProposal(
                id=proposal_id,
                artifact_id=artifact.id,
                instrument=artifact.instrument,
                dataset_id=artifact.dataset_id,
                dataset_revision=artifact.dataset_revision,
                forecast_generated_at=artifact.generated_at,
                model_version=artifact.model_version,
                config_digest=artifact.config_digest,
                history_digest=artifact.history_digest,
                side=side,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                created_at=created_at,
                confirmation_token=confirmation_token,
                status=(ProposalStatus.BLOCKED if blockers else ProposalStatus.PENDING),
                blockers=blockers,
            )
            try:
                existing = self.ledger.get(proposal.id)
            except ValueError as error:
                if "no proposal recorded" not in str(error):
                    raise
            else:
                if _proposal_identity(existing) != _proposal_identity(proposal):
                    raise ValueError("proposal id collision with different immutable facts")
                return existing
            return self.ledger.record(proposal)

    def _terminal_result(self, proposal: PaperProposal) -> ProposalConfirmation:
        order = None
        if proposal.order_id is not None:
            if self._journal is None:
                raise ValueError("terminal proposal has no bound order journal")
            order = self._journal.get(proposal.order_id)
        blocker = "; ".join(proposal.blockers) if proposal.blockers else None
        return ProposalConfirmation(
            proposal=proposal,
            order=order,
            blocker=blocker,
            quote_provenance=proposal.quote_provenance,
        )

    def _journal_order(self, proposal_id: str) -> Order | None:
        if self._journal is None:
            return None
        key = f"proposal:{proposal_id}"
        return next(
            (order for order in self._journal.all() if order.idempotency_key == key),
            None,
        )

    def _recover_account(self, account: PaperAccount, order: Order) -> PaperAccount:
        if order.order_id in account.orders:
            return account
        recovered = account
        for fill in order.fills:
            recovered = recovered.apply_fill(order, fill)
        orders = dict(recovered.orders)
        orders[order.order_id] = order
        return recovered.model_copy(
            update={
                "orders": orders,
                "order_sequence": recovered.order_sequence + 1,
            }
        )

    def _finish_from_order(
        self,
        proposal: PaperProposal,
        order: Order,
        *,
        now: datetime,
        quote_provenance: str,
    ) -> ProposalConfirmation:
        rejected = order.status is OrderStatus.REJECTED
        reason = next(
            (event.reason for event in reversed(order.events) if event.reason is not None),
            None,
        )
        terminal = PaperProposal.model_validate(
            {
                **proposal.model_dump(),
                "status": (ProposalStatus.REJECTED if rejected else ProposalStatus.CONFIRMED),
                "blockers": (reason or "paper kernel rejected the order",) if rejected else (),
                "order_id": order.order_id,
                "quote_provenance": quote_provenance,
            }
        )
        terminal = self.ledger.transition(terminal, recorded_at=now)
        return self._terminal_result(terminal)

    def confirm(
        self,
        proposal_id: str,
        *,
        confirmation: str,
        now: datetime,
    ) -> ProposalConfirmation:
        with self._lock:
            if now.tzinfo is None:
                raise ValueError("confirmation time must be timezone-aware")
            now = now.astimezone(UTC)
            proposal = self.ledger.get(proposal_id)
            if proposal.status is not ProposalStatus.PENDING:
                return self._terminal_result(proposal)
            if confirmation != proposal.confirmation_token:
                return ProposalConfirmation(
                    proposal=proposal,
                    blocker="operator confirmation token does not match",
                )
            if self._journal is None:
                return ProposalConfirmation(
                    proposal=proposal,
                    blocker="paper order journal is not bound",
                )
            try:
                artifact = self._resolve_artifact(proposal.artifact_id)
            except ValueError as error:
                blocked = PaperProposal.model_validate(
                    {
                        **proposal.model_dump(),
                        "status": ProposalStatus.BLOCKED,
                        "blockers": (str(error),),
                    }
                )
                blocked = self.ledger.transition(blocked, recorded_at=now)
                return self._terminal_result(blocked)
            if not artifact.eligible:
                blocked = PaperProposal.model_validate(
                    {
                        **proposal.model_dump(),
                        "status": ProposalStatus.BLOCKED,
                        "blockers": artifact.blockers,
                    }
                )
                blocked = self.ledger.transition(blocked, recorded_at=now)
                return self._terminal_result(blocked)
            freshness = _freshness_blocker(artifact, now)
            if freshness is not None:
                blocked = PaperProposal.model_validate(
                    {
                        **proposal.model_dump(),
                        "status": ProposalStatus.BLOCKED,
                        "blockers": (freshness,),
                    }
                )
                blocked = self.ledger.transition(blocked, recorded_at=now)
                return self._terminal_result(blocked)

            provenance = "demo-synthetic" if self._demo_quote_provider else "real"
            existing = self._journal_order(proposal.id)
            account = self._account_provider()
            if existing is not None:
                recovered = self._recover_account(account, existing)
                if recovered is not account:
                    self._account_sink(recovered)
                return self._finish_from_order(
                    proposal,
                    existing,
                    now=now,
                    quote_provenance=provenance,
                )

            request = OrderRequest(
                instrument=Instrument(
                    symbol=proposal.instrument.symbol,
                    venue=proposal.instrument.venue,
                    instrument_type=proposal.instrument.instrument_type,
                    currency=proposal.instrument.currency,
                    metadata=dict(proposal.instrument.metadata),
                ),
                side=proposal.side,
                quantity=proposal.quantity,
                limit_price=proposal.limit_price,
                paper=True,
                idempotency_key=f"proposal:{proposal.id}",
            )
            if self._demo_quote_provider is not None:
                quote = self._demo_quote_provider(proposal.instrument, now)
                result = account.submit(request, quote, now=now)
            else:
                snapshot = self._snapshot_provider()
                result = account.submit(
                    request,
                    now=now,
                    quote_fence=self._quote_fence,
                    snapshot={} if snapshot is None else snapshot,
                )
            self._journal.record(result.order)
            self._account_sink(result.account)
            return self._finish_from_order(
                proposal,
                result.order,
                now=now,
                quote_provenance=provenance,
            )
