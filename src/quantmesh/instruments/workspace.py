"""Point-in-time instrument workspace read model."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from quantmesh.domain.models import Venue
from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.instruments.contracts import (
    ComparisonSeries,
    HistoryRange,
    InstrumentWorkspace,
    PriceForecastArtifact,
    ProposalCapability,
    WorkspaceForecast,
    WorkspaceLiveEvidence,
    WorkspacePosition,
    WorkspaceRisk,
)
from quantmesh.instruments.forecast import PriceForecastRegistry
from quantmesh.instruments.history import HistoryService
from quantmesh.instruments.proposals import (
    PaperDecisionService,
    forecast_freshness_blocker,
)
from quantmesh.live.contract import Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed


def _positive(payload: Mapping[str, object], name: str) -> float | None:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _live_evidence(
    feed: LiveFeed | None,
    *,
    venue: Venue,
    symbol: str,
    as_of: datetime,
) -> WorkspaceLiveEvidence:
    if feed is None:
        return WorkspaceLiveEvidence(
            status="unavailable",
            reason="no live feed is attached",
        )
    snapshot = feed.snapshot_exact(venue, symbol, UpdateKind.QUOTE, as_of=as_of)
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
        history_digest=artifact.history_digest,
        benchmark_name=artifact.benchmark_name,
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
        history: HistoryService,
        forecasts: PriceForecastRegistry | None,
        account_provider: Callable[[], PaperAccount],
        marks_provider: Callable[[], Mapping[str, float]],
        live_feed: LiveFeed | None = None,
        decisions: PaperDecisionService | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._history = history
        self._forecasts = forecasts
        self._account_provider = account_provider
        self._marks_provider = marks_provider
        self._live_feed = live_feed
        self._decisions = decisions
        self._now = now

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

    def render(
        self,
        venue: Venue,
        symbol: str,
        selected_range: HistoryRange,
        *,
        peers: Sequence[tuple[Venue, str]] = (),
    ) -> InstrumentWorkspace:
        generated_at = self._now()
        if generated_at.tzinfo is None:
            raise ValueError("workspace clock must be timezone-aware")
        generated_at = generated_at.astimezone(UTC)
        history = self._history.history(
            venue,
            symbol,
            selected_range,
            as_of=generated_at,
        )
        comparison: ComparisonSeries | None = None
        if peers:
            comparison = self._history.compare(
                primary=(venue, symbol),
                peers=peers,
                range=selected_range,
                as_of=generated_at,
            )
        live = _live_evidence(
            self._live_feed,
            venue=venue,
            symbol=symbol,
            as_of=generated_at,
        )
        artifact, forecast_error = self._latest_forecast(
            venue,
            symbol,
            as_of=generated_at,
        )
        forecast = _forecast_summary(artifact) if artifact is not None else None

        if self._decisions is None:
            account = self._account_provider()
            proposals = ()
        else:
            account, proposals = self._decisions.workspace_snapshot(venue, symbol)
        marks = dict(self._marks_provider())
        key = position_key(history.instrument)
        held = account.positions.get(key)
        mark = marks.get(key)
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
            )
        limits = account.risk_limits
        risk = WorkspaceRisk(
            cash=account.cash,
            equity=account.equity(marks),
            starting_cash=(
                account.starting_cash if account.starting_cash is not None else account.cash
            ),
            max_order_quantity=limits.max_order_quantity,
            max_notional=limits.max_notional,
            max_position_quantity=limits.max_position_quantity,
            global_kill_switch=account.kill_switch,
            venue_kill_switch=account.kill_switches.get(venue, False),
            mark_available=mark is not None,
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
        if account.kill_switch:
            proposal_blockers.append("kill switch enabled")
        if account.kill_switches.get(venue):
            proposal_blockers.append(f"kill switch enabled for venue {venue.value}")
        proposal_blockers = list(dict.fromkeys(proposal_blockers))

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
            proposal=ProposalCapability(
                allowed=not proposal_blockers,
                blockers=tuple(proposal_blockers),
                proposals=proposals,
            ),
        )
