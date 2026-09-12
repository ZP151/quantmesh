"""Point-in-time instrument workspace read model."""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from quantmesh.domain.models import Venue
from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.instruments.contracts import (
    ComparisonSeries,
    DecisionPacket,
    DecisionWorkspaceState,
    HistoricalSeries,
    HistoryRange,
    InstrumentWorkspace,
    PaperProposal,
    PriceForecastArtifact,
    ProposalCapability,
    WorkspaceForecast,
    WorkspaceLiveEvidence,
    WorkspaceMarkStatus,
    WorkspacePosition,
    WorkspaceRisk,
)
from quantmesh.instruments.decision_analysis import compose_decision_packet
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.instruments.forecast import PriceForecastRegistry
from quantmesh.instruments.history import HistoryService
from quantmesh.instruments.live_history import LiveHistoryService
from quantmesh.instruments.proposals import (
    PaperDecisionService,
    forecast_freshness_blocker,
)
from quantmesh.live.contract import Provenance, UpdateKind
from quantmesh.live.feed import ExactUpdateSnapshot, LiveFeed
from quantmesh.live.marks import (
    AccountValuationSnapshot,
    LiveMarkSnapshot,
    account_valuation_snapshot,
)


def _positive(payload: Mapping[str, object], name: str) -> float | None:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _live_evidence(
    snapshot: ExactUpdateSnapshot | None,
    *,
    feed_attached: bool,
    as_of: datetime,
) -> WorkspaceLiveEvidence:
    if not feed_attached:
        return WorkspaceLiveEvidence(
            status="unavailable",
            reason="no live feed is attached",
        )
    if snapshot is None:
        return WorkspaceLiveEvidence(
            status="unavailable",
            reason="no live quote is available for this venue and symbol",
        )
    bid = _positive(snapshot.payload, "bid")
    ask = _positive(snapshot.payload, "ask")
    bid_size = _positive(snapshot.payload, "bid_size")
    ask_size = _positive(snapshot.payload, "ask_size")
    last = _positive(snapshot.payload, "last")
    if last is None and bid is not None and ask is not None:
        last = (bid + ask) / 2
    reasons: list[str] = []
    if snapshot.provenance not in {Provenance.REAL, Provenance.DELAYED}:
        reasons.append(f"quote provenance is {snapshot.provenance.value}")
    if snapshot.freshness_label not in {"real", "delayed"}:
        reasons.append(f"quote freshness is {snapshot.freshness_label or 'unknown'}")
    if snapshot.received_at > as_of:
        reasons.append("quote receipt time is in the future")
    if snapshot.sequence_gap:
        reasons.append("quote sequence has a gap (discontinuous)")
    elif snapshot.sequence_gap is not False or not snapshot.continuity_proven:
        reasons.append("quote continuity is unproven")
    if bid is None or ask is None or bid > ask or bid_size is None or ask_size is None:
        reasons.append("quote has no usable bid/ask depth")
    return WorkspaceLiveEvidence(
        status="degraded" if reasons else "available",
        reason="; ".join(reasons) if reasons else None,
        source=snapshot.source,
        provenance=snapshot.provenance.value,
        label=snapshot.freshness_label,
        data_time=snapshot.data_time,
        received_at=snapshot.received_at,
        age_ms=snapshot.age_ms,
        sequence=(
            snapshot.sequence if type(snapshot.sequence) is int and snapshot.sequence >= 0 else None
        ),
        sequence_gap=snapshot.sequence_gap,
        bid=bid,
        ask=ask,
        last=last,
    )


def _forecast_summary(artifact: PriceForecastArtifact) -> WorkspaceForecast:
    return WorkspaceForecast(
        artifact_id=artifact.id,
        generated_at=artifact.generated_at,
        target=artifact.target,
        train_start=artifact.train_start,
        train_end=artifact.train_end,
        validation_start=artifact.validation_start,
        validation_end=artifact.validation_end,
        test_start=artifact.test_start,
        test_end=artifact.test_end,
        model_name=artifact.model_name,
        model_version=artifact.model_version,
        config_digest=artifact.config_digest,
        dataset_id=artifact.dataset_id,
        dataset_revision=artifact.dataset_revision,
        manifest_id=artifact.manifest_id,
        quality_evaluation_id=artifact.quality_evaluation_id,
        history_digest=artifact.history_digest,
        benchmark_name=artifact.benchmark_name,
        synthetic=artifact.source == "demo-synthetic",
        eligible=artifact.eligible,
        blockers=artifact.blockers,
        limitations=artifact.limitations,
        paths=artifact.paths,
        metrics=artifact.metrics,
    )


class InstrumentWorkspaceService:
    """Compose existing read models at one explicit clock."""

    def __init__(
        self,
        *,
        history: HistoryService | LiveHistoryService,
        forecasts: PriceForecastRegistry | None,
        account_provider: Callable[[], PaperAccount],
        marks_provider: Callable[[], Mapping[str, float]],
        valuation_provider: Callable[[datetime], AccountValuationSnapshot] | None = None,
        live_feed: LiveFeed | None = None,
        decisions: PaperDecisionService | None = None,
        decision_packets: DecisionPacketStore | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._history = history
        self._forecasts = forecasts
        self._account_provider = account_provider
        self._marks_provider = marks_provider
        self._valuation_provider = valuation_provider
        self._live_feed = live_feed
        self._decisions = decisions
        self._decision_packets = decision_packets
        self._now = now
        self._draft_lock = threading.RLock()
        self._staged_drafts: OrderedDict[str, tuple[DecisionPacket, str | None]] = OrderedDict()

    def staged_draft(
        self,
        packet_id: str,
        *,
        venue: Venue,
        symbol: str,
        selected_range: HistoryRange,
        horizon: Literal[7, 30] | None = None,
        forecast_id: str | None = None,
    ) -> DecisionPacket | None:
        """Return an exact draft previously exposed by this workspace process."""
        with self._draft_lock:
            staged = self._staged_drafts.get(packet_id)
            if staged is None:
                return None
            draft, selected_forecast_id = staged
            if (
                draft.instrument.venue is not venue
                or draft.instrument.symbol != symbol
                or draft.selected_range is not selected_range
                or (draft.scenario_lab.selected_horizon if draft.scenario_lab else None) != horizon
                or (forecast_id is not None and selected_forecast_id != forecast_id)
            ):
                raise ValueError("staged decision packet does not match the requested scope")
            self._staged_drafts.move_to_end(packet_id)
            return draft

    def _stage_draft(self, draft: DecisionPacket, forecast_id: str | None = None) -> None:
        with self._draft_lock:
            # Preserve a refused requested pin without claiming it as forecast evidence.
            self._staged_drafts[draft.packet_id] = (
                draft,
                forecast_id or draft.evidence.forecast_artifact_id,
            )
            self._staged_drafts.move_to_end(draft.packet_id)
            while len(self._staged_drafts) > 256:
                self._staged_drafts.popitem(last=False)

    def clear_staged_drafts(self) -> None:
        """Forget process-local drafts when their backing root is replaced."""
        with self._draft_lock:
            self._staged_drafts.clear()

    def _latest_forecast(
        self, venue: Venue, symbol: str, *, as_of: datetime
    ) -> tuple[PriceForecastArtifact | None, str | None]:
        if self._forecasts is None:
            return None, "no price forecast registry is attached"
        try:
            matches = [
                artifact
                for artifact in self._forecasts.all()
                if artifact.instrument.venue is venue
                and artifact.instrument.symbol == symbol
                and artifact.generated_at <= as_of
            ]
        except ValueError as error:
            return None, f"price forecast registry is unavailable: {error}"
        if not matches:
            return None, (
                "no price forecast artifact exists at or before the workspace clock "
                f"for {venue.value}:{symbol}"
            )
        return max(matches, key=lambda item: (item.generated_at, item.id)), None

    def _exact_forecast(
        self,
        forecast_id: str,
        venue: Venue,
        symbol: str,
        *,
        as_of: datetime,
    ) -> tuple[PriceForecastArtifact | None, str | None]:
        if self._forecasts is None:
            return None, "no price forecast registry is attached"
        try:
            artifact = self._forecasts.get(forecast_id)
            if (
                artifact.instrument.venue is not venue
                or artifact.instrument.symbol != symbol
                or artifact.generated_at > as_of
            ):
                raise ValueError("exact forecast does not match the instrument or decision clock")
        except (OSError, ValueError) as error:
            return None, f"exact forecast is unavailable: {error}"
        return artifact, None

    def _validate_chart_pin(
        self,
        history: HistoricalSeries,
        artifact: PriceForecastArtifact,
    ) -> None:
        """Check chart bytes against the registry's verified dataset, not current/latest data."""
        if (
            history.instrument != artifact.instrument
            or history.dataset_id != artifact.dataset_id
            or history.dataset_revision != artifact.dataset_revision
            or history.manifest_id != artifact.manifest_id
            or history.quality_evaluation_id != artifact.quality_evaluation_id
            or history.source != artifact.source
            or history.license != artifact.license
            or history.generated_at != artifact.dataset_generated_at
            or history.interval != "1d"
            or history.calendar != artifact.calendar
            or history.adjustment != artifact.adjustment
            or history.coverage != artifact.coverage
            or history.bars[-1].timestamp != artifact.train_end
            or any(bar.timestamp > artifact.train_end or bar.is_live_tail for bar in history.bars)
        ):
            raise ValueError("chart history does not match exact forecast provenance or as-of cut")
        dataset = self._forecasts.resolve_pin(artifact)
        if artifact.manifest_id is not None:
            rows = dataset.read_bars()
        else:
            rows = dataset.read_bars(
                interval="1d",
                venue=artifact.instrument.venue,
                symbol=artifact.instrument.symbol,
                start=history.bars[0].timestamp,
                end=artifact.train_end,
            )
        pinned = tuple(
            row for row in rows if history.bars[0].timestamp <= row.timestamp <= artifact.train_end
        )

        def values(bar):
            return (bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)

        if tuple(map(values, pinned)) != tuple(map(values, history.bars)):
            raise ValueError("chart history bytes do not match the exact forecast dataset")

    def _valuation_and_proposals(
        self,
        venue: Venue,
        symbol: str,
        *,
        as_of: datetime,
    ) -> tuple[AccountValuationSnapshot, tuple[PaperProposal, ...]]:
        if self._decisions is None:
            valuation = (
                self._valuation_provider(as_of)
                if self._valuation_provider is not None
                else account_valuation_snapshot(
                    self._account_provider(),
                    LiveMarkSnapshot(marks=dict(self._marks_provider()), statuses={}),
                )
            )
            return valuation, ()

        # Confirmation takes these locks in ledger -> account order. Holding
        # the same re-entrant boundary makes account, marks and proposal state
        # one point-in-time read without introducing a lock-order inversion.
        with self._decisions.ledger.transaction(), self._decisions._account_transaction():
            account, proposals = self._decisions.workspace_snapshot(venue, symbol)
            valuation = (
                self._valuation_provider(as_of)
                if self._valuation_provider is not None
                else account_valuation_snapshot(
                    account,
                    LiveMarkSnapshot(marks=dict(self._marks_provider()), statuses={}),
                )
            )
            if valuation.account != account:
                valuation = account_valuation_snapshot(
                    account,
                    LiveMarkSnapshot(
                        marks=dict(valuation.marks),
                        statuses={key: dict(value) for key, value in valuation.statuses.items()},
                    ),
                )
            return valuation, proposals

    def render(
        self,
        venue: Venue,
        symbol: str,
        selected_range: HistoryRange,
        *,
        peers: Sequence[tuple[Venue, str]] = (),
        horizon: Literal[7, 30] | None = None,
        forecast_id: str | None = None,
    ) -> InstrumentWorkspace:
        if self._live_feed is None:
            generated_at, live_snapshot = self._now(), None
        else:
            generated_at, live_snapshot = self._live_feed.capture_exact(
                venue, symbol, UpdateKind.QUOTE, clock=self._now
            )
        if generated_at.tzinfo is None:
            raise ValueError("workspace clock must be timezone-aware")
        generated_at = generated_at.astimezone(UTC)
        if horizon is not None and (
            horizon not in (7, 30) or venue is not Venue.MOOMOO or symbol not in {"AAPL", "NVDA"}
        ):
            raise ValueError("scenario lab supports Moomoo AAPL/NVDA and 7/30 sessions only")
        latest = (
            self._decision_packets.latest(
                venue,
                symbol,
                selected_range,
                horizon=horizon,
                forecast_id=forecast_id,
            )
            if self._decision_packets is not None
            else None
        )
        valuation, proposals = self._valuation_and_proposals(
            venue,
            symbol,
            as_of=generated_at,
        )
        artifact, forecast_error = (
            self._exact_forecast(forecast_id, venue, symbol, as_of=generated_at)
            if forecast_id is not None
            else self._latest_forecast(venue, symbol, as_of=generated_at)
        )
        history = self._history.history(
            venue,
            symbol,
            selected_range,
            as_of=artifact.generated_at
            if horizon is not None and artifact is not None
            else generated_at,
        )
        if horizon is not None and artifact is not None:
            observed = tuple(bar for bar in history.bars if bar.timestamp <= artifact.train_end)
            history = history.model_copy(update={"as_of": generated_at})
            try:
                if not observed:
                    raise ValueError("exact forecast chart history is unavailable")
                history = history.model_copy(update={"bars": observed})
                self._validate_chart_pin(history, artifact)
            except (OSError, ValueError) as error:
                forecast_error = f"exact forecast chart binding is unavailable: {error}"
                artifact = None
        comparison: ComparisonSeries | None = None
        if peers:
            comparison = self._history.compare(
                primary=(venue, symbol),
                peers=peers,
                range=selected_range,
                as_of=generated_at,
            )
        live = _live_evidence(
            live_snapshot,
            feed_attached=self._live_feed is not None,
            as_of=generated_at,
        )
        forecast = _forecast_summary(artifact) if artifact is not None else None

        account = valuation.account
        marks = valuation.marks
        key = position_key(history.instrument)
        held = account.positions.get(key)
        mark = marks.get(key)
        mark_evidence = valuation.statuses.get(key, {})
        mark_status = None
        if held is not None:
            received_at = mark_evidence.get("received_at")
            if isinstance(received_at, str):
                received_at = datetime.fromisoformat(received_at)
            raw_status = mark_evidence.get("status")
            status = (
                raw_status
                if raw_status in {"available", "stale", "unavailable"}
                else "available"
                if mark is not None
                else "unavailable"
            )
            mark_status = WorkspaceMarkStatus.model_validate(
                {
                    "status": status,
                    "provenance": mark_evidence.get("provenance", "injected"),
                    "received_at": received_at,
                    "reason": mark_evidence.get("reason"),
                }
            )
        position = None
        if held is not None:
            position = WorkspacePosition(
                quantity=held.quantity,
                average_cost=held.average_cost,
                realized_pnl=held.realized_pnl,
                mark=mark,
                unrealized_pnl=(
                    (mark - held.average_cost) * held.quantity if mark is not None else None
                ),
                mark_status=mark_status,
            )
        limits = account.risk_limits
        risk = WorkspaceRisk(
            cash=account.cash,
            equity=account.equity(marks) if valuation.complete else None,
            starting_cash=(
                account.starting_cash if account.starting_cash is not None else account.cash
            ),
            max_order_quantity=limits.max_order_quantity,
            max_notional=limits.max_notional,
            max_position_quantity=limits.max_position_quantity,
            global_kill_switch=account.kill_switch,
            venue_kill_switch=account.kill_switches.get(venue, False),
            mark_available=mark is not None,
            valuation_complete=valuation.complete,
            valuation_reason=valuation.reason,
        )

        proposal_blockers: list[str] = []
        if artifact is None:
            proposal_blockers.append(forecast_error or "forecast is unavailable")
        else:
            proposal_blockers.extend(artifact.blockers)
            freshness = forecast_freshness_blocker(artifact, generated_at)
            if freshness is not None:
                proposal_blockers.append(freshness)
        if self._decisions is None:
            proposal_blockers.append("paper proposal service is not attached")
        else:
            if not self._decisions.demo_mode and (
                live.status != "available" or live.provenance != Provenance.REAL.value
            ):
                proposal_blockers.append(
                    live.reason or "a fresh real quote is required for paper confirmation"
                )
        if self._decision_packets is None:
            proposal_blockers.append("decision packet persistence is not attached")
        if account.kill_switch:
            proposal_blockers.append("kill switch enabled")
        if account.kill_switches.get(venue):
            proposal_blockers.append(f"kill switch enabled for venue {venue.value}")
        proposal_blockers = list(dict.fromkeys(proposal_blockers))

        proposal = ProposalCapability(
            allowed=not proposal_blockers,
            blockers=tuple(proposal_blockers),
            proposals=proposals,
        )
        draft = compose_decision_packet(
            history=history,
            forecast=forecast,
            live=live,
            risk=risk,
            proposal=proposal,
            account=account,
            selected_range=selected_range,
            as_of=generated_at,
            horizon=horizon,
        )
        self._stage_draft(draft, forecast_id)

        return InstrumentWorkspace(
            generated_at=generated_at,
            instrument=history.instrument,
            history=history,
            comparison=comparison,
            live=live,
            forecast=forecast,
            forecast_unavailable_reason=forecast_error,
            position=position,
            risk=risk,
            proposal=proposal,
            decision=DecisionWorkspaceState(draft=draft, latest=latest),
        )
