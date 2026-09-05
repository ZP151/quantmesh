"""Read-only Decision Inbox projection over the existing durable stores."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from quantmesh.api.watchlist import WatchlistRecord
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.contracts import (
    DECISION_PACKET_ID_PATTERN,
    PROPOSAL_ID_PATTERN,
    DecisionDisposition,
    DecisionPacket,
    HistoryRange,
    PaperProposal,
    PriceForecastArtifact,
    ProposalStatus,
    StrictContract,
)
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.instruments.forecast import PriceForecastRegistry
from quantmesh.instruments.proposals import PaperDecisionService, forecast_freshness_blocker
from quantmesh.instruments.reviews import ReviewClassification
from quantmesh.live.contract import UpdateKind
from quantmesh.live.feed import ExactUpdateSnapshot, LiveFeed
from quantmesh.live.fence import QuoteFence


class DecisionAttentionState(StrEnum):
    BLOCKED = "blocked"
    WATCH_TRIGGERED = "watch_triggered"
    PAPER_PENDING_CONFIRMATION = "paper_pending_confirmation"
    REVIEW_AVAILABLE = "review_available"
    PAPER_OPEN = "paper_open"
    WATCHING = "watching"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    DRAFT = "draft"
    NOT_STARTED = "not_started"
    UNAVAILABLE = "unavailable"


class DecisionInboxMarkContext(StrictContract):
    value: float | None = Field(default=None, gt=0)
    status: Literal["available", "stale", "unavailable"]
    received_at: datetime | None = None
    reason: str | None = None

    @field_validator("received_at")
    @classmethod
    def received_at_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        return value.astimezone(UTC)


class DecisionInboxPaperSummary(StrictContract):
    proposal_id: str = Field(pattern=PROPOSAL_ID_PATTERN)
    status: ProposalStatus
    order_id: str | None = None


class DecisionInboxPositionContext(StrictContract):
    quantity: float
    average_cost: float = Field(ge=0)
    realized_pnl: float
    mark: float = Field(gt=0)
    attribution: Literal["current-account-context-only"]


class DecisionInboxMonitoringSummary(StrictContract):
    registration_id: str = Field(pattern=r"^registration-[0-9a-f]{24}$")
    latest_evaluation_id: str | None = Field(
        default=None,
        pattern=r"^evaluation-[0-9a-f]{24}$",
    )
    triggered: bool


class DecisionInboxReviewSummary(StrictContract):
    review_id: str = Field(pattern=r"^review-[0-9a-f]{24}$")
    state: ReviewClassification


class DecisionInboxEntry(StrictContract):
    venue: Venue | None
    symbol: str = Field(min_length=1)
    instrument_type: InstrumentType | None = None
    attention_state: DecisionAttentionState
    attention_reason: str = Field(min_length=1)
    packet_id: str | None = Field(default=None, pattern=DECISION_PACKET_ID_PATTERN)
    parent_packet_id: str | None = Field(default=None, pattern=DECISION_PACKET_ID_PATTERN)
    selected_range: HistoryRange | None = None
    disposition: DecisionDisposition | None = None
    evidence_status: Literal["complete", "partial", "pending", "unavailable"] | None = None
    mark_context: DecisionInboxMarkContext
    paper: DecisionInboxPaperSummary | None = None
    position_context: DecisionInboxPositionContext | None = None
    monitoring: DecisionInboxMonitoringSummary | None = None
    review: DecisionInboxReviewSummary | None = None


class DecisionInbox(StrictContract):
    generated_at: datetime
    entries: tuple[DecisionInboxEntry, ...]

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(UTC)


class DecisionInboxError(StrictContract):
    code: Literal["decision_inbox_replay_unavailable"]
    message: str = Field(min_length=1, max_length=300)


_ATTENTION_REQUIRED_PRIORITY = {
    DecisionAttentionState.UNAVAILABLE: 0,
    DecisionAttentionState.BLOCKED: 1,
    DecisionAttentionState.WATCH_TRIGGERED: 2,
    DecisionAttentionState.PAPER_PENDING_CONFIRMATION: 3,
    DecisionAttentionState.REVIEW_AVAILABLE: 4,
}


class DecisionInboxService:
    """Compose a deterministic, side-effect-free watchlist projection.

    Store access stays behind providers so demo reset can replace app-state roots
    without leaving this long-lived query service attached to stale objects.
    """

    def __init__(
        self,
        *,
        watchlist_provider: Callable[[], Sequence[WatchlistRecord]],
        packet_store_provider: Callable[[], DecisionPacketStore | None],
        review_service_provider: Callable[[], object | None],
        account_provider: Callable[[], PaperAccount],
        markets_provider: Callable[[], Mapping[str, Mapping[str, float | None]]],
        now: Callable[[], datetime],
        paper_decisions_provider: Callable[[], PaperDecisionService | None] = lambda: None,
        forecast_registry_provider: Callable[[], PriceForecastRegistry | None] = lambda: None,
        live_feed_provider: Callable[[], LiveFeed | None] = lambda: None,
    ) -> None:
        self._watchlist_provider = watchlist_provider
        self._packet_store_provider = packet_store_provider
        self._review_service_provider = review_service_provider
        self._account_provider = account_provider
        self._markets_provider = markets_provider
        self._paper_decisions_provider = paper_decisions_provider
        self._forecast_registry_provider = forecast_registry_provider
        self._live_feed_provider = live_feed_provider
        self._now = now
        self._quote_fence = QuoteFence()

    def snapshot(self) -> DecisionInbox:
        """Read all participating state once and derive the immutable view."""
        generated_at = self._timestamp()
        watchlist = tuple(self._watchlist_provider())
        packet_store = self._packet_store_provider()
        packets = packet_store.all() if packet_store is not None else ()
        account = self._account_provider()
        markets = self._markets_provider()
        proposals = self._proposals_once()
        forecasts = self._forecasts_once()
        # The provider is deliberately invoked at the read boundary even though
        # Slice 1 leaves review enrichment absent. It protects reset semantics.
        self._review_service_provider()
        feed = self._live_feed_provider()

        by_identity: dict[tuple[Venue, str], list[DecisionPacket]] = {}
        for packet in packets:
            by_identity.setdefault((packet.instrument.venue, packet.instrument.symbol), []).append(
                packet
            )
        proposal_by_id = {proposal.id: proposal for proposal in proposals}
        forecast_by_id = {artifact.id: artifact for artifact in forecasts}

        entries = tuple(
            self._entry(
                record,
                by_identity.get((record.venue, record.symbol), []) if record.venue else [],
                proposal_by_id,
                forecast_by_id,
                account,
                markets,
                feed,
                generated_at,
            )
            for record in sorted(
                watchlist,
                key=lambda item: (item.symbol, item.venue.value if item.venue is not None else ""),
            )
        )
        return DecisionInbox(generated_at=generated_at, entries=entries)

    def _entry(
        self,
        record: WatchlistRecord,
        packets: Sequence[DecisionPacket],
        proposals: Mapping[str, PaperProposal],
        forecasts: Mapping[str, object],
        account: PaperAccount,
        markets: Mapping[str, Mapping[str, float | None]],
        feed: LiveFeed | None,
        now: datetime,
    ) -> DecisionInboxEntry:
        if record.venue is None:
            return DecisionInboxEntry(
                venue=None,
                symbol=record.symbol,
                attention_state=DecisionAttentionState.UNAVAILABLE,
                attention_reason="watchlist entry has no venue",
                mark_context=DecisionInboxMarkContext(
                    status="unavailable", reason="a venue is required to resolve a mark"
                ),
            )

        instrument_type = packets[0].instrument.instrument_type if packets else None
        mark_context = self._mark_context(
            record.venue,
            record.symbol,
            instrument_type,
            markets,
            feed,
            now,
        )
        if not packets:
            return DecisionInboxEntry(
                venue=record.venue,
                symbol=record.symbol,
                attention_state=DecisionAttentionState.NOT_STARTED,
                attention_reason="no saved decision packet",
                mark_context=mark_context,
            )

        candidates = [
            self._candidate(packet, proposals, forecasts, now)
            for packet in packets
        ]
        attention_required = [
            item for item in candidates if item[0] in _ATTENTION_REQUIRED_PRIORITY
        ]
        terminal = [
            item
            for item in candidates
            if item[2].disposition is not DecisionDisposition.DRAFT
        ]
        if attention_required:
            state, reason, packet, paper = max(
                attention_required,
                key=lambda item: (
                    -_ATTENTION_REQUIRED_PRIORITY[item[0]],
                    *self._recency_key(item),
                ),
            )
        elif terminal:
            state, reason, packet, paper = max(terminal, key=self._recency_key)
        else:
            state, reason, packet, paper = max(candidates, key=self._recency_key)
        position_context = self._position_context(
            record.venue,
            record.symbol,
            account,
            mark_context,
        )
        return DecisionInboxEntry(
            venue=record.venue,
            symbol=record.symbol,
            instrument_type=packet.instrument.instrument_type,
            attention_state=state,
            attention_reason=reason,
            packet_id=packet.packet_id,
            parent_packet_id=packet.parent_packet_id,
            selected_range=packet.selected_range,
            disposition=packet.disposition,
            mark_context=mark_context,
            paper=paper,
            position_context=position_context,
        )

    def _candidate(
        self,
        packet: DecisionPacket,
        proposals: Mapping[str, PaperProposal],
        forecasts: Mapping[str, object],
        now: datetime,
    ) -> tuple[DecisionAttentionState, str, DecisionPacket, DecisionInboxPaperSummary | None]:
        if packet.disposition is DecisionDisposition.DRAFT:
            return (DecisionAttentionState.DRAFT, "saved decision draft", packet, None)
        if packet.disposition is DecisionDisposition.REJECT:
            return (
                DecisionAttentionState.REJECTED,
                "operator rejected this decision",
                packet,
                None,
            )
        if packet.disposition is DecisionDisposition.WATCH:
            return (
                DecisionAttentionState.WATCHING,
                "operator is watching this decision",
                packet,
                None,
            )

        proposal = proposals.get(packet.proposal_id or "")
        if proposal is None:
            return (
                DecisionAttentionState.UNAVAILABLE,
                "paper proposal link is unavailable",
                packet,
                None,
            )
        if not self._proposal_matches_packet(proposal, packet):
            raise ValueError("paper proposal does not match immutable decision packet evidence")
        paper = DecisionInboxPaperSummary(
            proposal_id=proposal.id,
            status=proposal.status,
            order_id=proposal.order_id,
        )
        if proposal.status is ProposalStatus.BLOCKED:
            return (DecisionAttentionState.BLOCKED, "paper proposal is blocked", packet, paper)
        if proposal.status is ProposalStatus.REJECTED:
            return (DecisionAttentionState.REJECTED, "paper proposal was rejected", packet, paper)
        if proposal.status is ProposalStatus.CONFIRMED:
            return (DecisionAttentionState.PAPER_OPEN, "paper proposal is confirmed", packet, paper)

        artifact = forecasts.get(packet.evidence.forecast_artifact_id)
        if not isinstance(artifact, PriceForecastArtifact):
            return (
                DecisionAttentionState.UNAVAILABLE,
                "forecast linked to the pending paper proposal is unavailable",
                packet,
                paper,
            )
        if not self._forecast_matches_packet(artifact, packet):
            raise ValueError("forecast does not match immutable decision packet evidence")
        blocker = forecast_freshness_blocker(artifact, now)
        reason = "paper proposal is pending confirmation"
        if blocker is not None:
            reason = f"paper proposal is pending confirmation; {blocker}"
        return (DecisionAttentionState.PAPER_PENDING_CONFIRMATION, reason, packet, paper)

    def _mark_context(
        self,
        venue: Venue,
        symbol: str,
        instrument_type: InstrumentType | None,
        markets: Mapping[str, Mapping[str, float | None]],
        feed: LiveFeed | None,
        now: datetime,
    ) -> DecisionInboxMarkContext:
        snapshot = (
            feed.snapshot_exact(venue, symbol, UpdateKind.QUOTE, as_of=now)
            if feed is not None and instrument_type is not None
            else None
        )
        instrument = (
            Instrument(venue=venue, symbol=symbol, instrument_type=instrument_type)
            if instrument_type is not None
            else None
        )
        live = self._live_mark(snapshot, instrument, now)
        if live is not None:
            return live
        configured = markets.get(venue.value, {}).get(symbol)
        if (
            isinstance(configured, (int, float))
            and not isinstance(configured, bool)
            and configured > 0
        ):
            return DecisionInboxMarkContext(
                value=float(configured),
                status="unavailable",
                reason="configured mark has no freshness evidence",
            )
        return DecisionInboxMarkContext(
            status="unavailable",
            reason="no current mark is configured",
        )

    def _live_mark(
        self,
        snapshot: ExactUpdateSnapshot | None,
        instrument: Instrument | None,
        now: datetime,
    ) -> DecisionInboxMarkContext | None:
        if snapshot is None or instrument is None:
            return None
        decision = self._quote_fence.resolve(snapshot, instrument=instrument, now=now)
        if decision.allowed and decision.quote is not None and decision.quote.last is not None:
            return DecisionInboxMarkContext(
                value=decision.quote.last,
                status="available",
                received_at=snapshot.received_at,
            )
        status: Literal["stale", "unavailable"] = (
            "stale" if snapshot.freshness_label == "stale" else "unavailable"
        )
        return DecisionInboxMarkContext(
            status=status,
            received_at=snapshot.received_at,
            reason=decision.reason or "live quote cannot provide a current mark",
        )

    @staticmethod
    def _position_context(
        venue: Venue,
        symbol: str,
        account: PaperAccount,
        mark_context: DecisionInboxMarkContext,
    ) -> DecisionInboxPositionContext | None:
        position = account.positions.get(f"{venue.value}:{symbol}")
        if (
            position is None
            or mark_context.status != "available"
            or mark_context.value is None
        ):
            return None
        return DecisionInboxPositionContext(
            quantity=position.quantity,
            average_cost=position.average_cost,
            realized_pnl=position.realized_pnl,
            mark=mark_context.value,
            attribution="current-account-context-only",
        )

    def _proposals_once(self) -> tuple[PaperProposal, ...]:
        decisions = self._paper_decisions_provider()
        return decisions.ledger.all() if decisions is not None else ()

    def _forecasts_once(self) -> tuple[object, ...]:
        registry = self._forecast_registry_provider()
        return tuple(registry.all()) if registry is not None else ()

    @staticmethod
    def _recency_key(
        candidate: tuple[
            DecisionAttentionState,
            str,
            DecisionPacket,
            DecisionInboxPaperSummary | None,
        ],
    ) -> tuple[datetime, datetime, int, str]:
        packet = candidate[2]
        return (packet.as_of, packet.created_at, packet.version, packet.packet_id)

    @staticmethod
    def _proposal_matches_packet(proposal: PaperProposal, packet: DecisionPacket) -> bool:
        evidence = packet.evidence
        return (
            proposal.id == packet.proposal_id
            and proposal.instrument == packet.instrument
            and proposal.artifact_id == evidence.forecast_artifact_id
            and proposal.dataset_id == evidence.forecast_dataset_id
            and proposal.dataset_revision == evidence.forecast_dataset_revision
            and proposal.forecast_generated_at == evidence.forecast_generated_at
            and proposal.model_version == evidence.forecast_model_version
            and proposal.config_digest == evidence.forecast_config_digest
            and proposal.history_digest == evidence.forecast_history_digest
        )

    @staticmethod
    def _forecast_matches_packet(artifact: PriceForecastArtifact, packet: DecisionPacket) -> bool:
        evidence = packet.evidence
        return (
            artifact.id == evidence.forecast_artifact_id
            and artifact.instrument == packet.instrument
            and artifact.dataset_id == evidence.forecast_dataset_id
            and artifact.dataset_revision == evidence.forecast_dataset_revision
            and artifact.generated_at == evidence.forecast_generated_at
            and artifact.model_version == evidence.forecast_model_version
            and artifact.config_digest == evidence.forecast_config_digest
            and artifact.history_digest == evidence.forecast_history_digest
        )

    def _timestamp(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("decision inbox clock must return a timezone-aware datetime")
        return value.astimezone(UTC)
