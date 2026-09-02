"""Pure deterministic composition of an immutable DecisionPacket."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.instruments.contracts import (
    DecisionBlocker,
    DecisionCostEvidence,
    DecisionDisposition,
    DecisionEvidence,
    DecisionForecastChronology,
    DecisionMarketState,
    DecisionPacket,
    DecisionPaperCapability,
    DecisionRiskPlan,
    DecisionScenario,
    HistoricalSeries,
    HistoryRange,
    ProposalCapability,
    WorkspaceForecast,
    WorkspaceLiveEvidence,
    WorkspaceRisk,
)
from quantmesh.instruments.decision_packets import decision_packet_id

_KEY_LEVEL_LOOKBACK = 20
_FORECAST_FRESHNESS = timedelta(days=1)
_HISTORY_FRESHNESS = timedelta(days=1)
_BLOCKER_ORDER = (
    "history-quality", "history-lineage", "history-freshness", "forecast-missing",
    "forecast-ineligible", "forecast-freshness", "leakage", "chronology",
    "cost-evidence", "valuation", "kill-switch", "proposal-service",
)


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values)


def _observed_volatility(closes: tuple[float, ...]) -> float:
    if len(closes) < 2:
        return 0.0
    returns = tuple(
        closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))
    )
    average = _mean(returns)
    return math.sqrt(sum((value - average) ** 2 for value in returns) / len(returns))


def _maximum_drawdown(closes: tuple[float, ...]) -> float:
    peak = closes[0]
    drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        drawdown = max(drawdown, (peak - close) / peak)
    return drawdown


def _blocker(code: str, message: str, ref: str) -> DecisionBlocker:
    return DecisionBlocker(code=code, message=message, evidence_ref=ref)


def _normalized_blockers(blockers: list[DecisionBlocker]) -> tuple[DecisionBlocker, ...]:
    grouped: dict[str, list[DecisionBlocker]] = {}
    for blocker in blockers:
        grouped.setdefault(blocker.code, []).append(blocker)
    return tuple(
        DecisionBlocker(
            code=code,
            message="; ".join(dict.fromkeys(item.message for item in grouped[code])),
            evidence_ref="; ".join(dict.fromkeys(item.evidence_ref for item in grouped[code])),
        )
        for code in _BLOCKER_ORDER
        if code in grouped
    )


def _suggested_quantity(
    account: PaperAccount,
    *,
    entry_price: float,
    risk_per_unit: float,
    instrument_key: str,
) -> float | None:
    """Bound a 1% cash-risk suggestion by the account's explicit hard limits."""
    limits = account.risk_limits
    limits_to_apply = [account.cash * 0.01 / risk_per_unit, account.cash / entry_price]
    if limits.max_order_quantity is not None:
        limits_to_apply.append(limits.max_order_quantity)
    if limits.max_notional is not None:
        limits_to_apply.append(limits.max_notional / entry_price)
    if limits.max_position_quantity is not None:
        held = account.positions.get(instrument_key)
        limits_to_apply.append(limits.max_position_quantity - (held.quantity if held else 0.0))
    candidate = min(limits_to_apply)
    return candidate if candidate > 0 else None


def compose_decision_packet(
    *,
    history: HistoricalSeries,
    forecast: WorkspaceForecast | None,
    live: WorkspaceLiveEvidence,
    risk: WorkspaceRisk,
    proposal: ProposalCapability,
    account: PaperAccount,
    selected_range: HistoryRange,
    as_of: datetime,
) -> DecisionPacket:
    """Compose one analysis from pinned inputs only; it never calls a provider or executor."""
    selected_as_of = _utc(as_of, "as_of")
    if selected_range is not history.range:
        raise ValueError("selected_range must match historical series range")
    if history.as_of != selected_as_of:
        raise ValueError("packet as_of must match historical series as_of")
    observed = tuple(bar for bar in history.bars if bar.timestamp <= selected_as_of)
    if not observed:
        raise ValueError("decision packet requires observed bars at or before as_of")
    if tuple(bar.timestamp for bar in observed) != tuple(
        sorted(bar.timestamp for bar in observed)
    ):
        raise ValueError("decision packet observed bars must be chronological")

    closes = tuple(bar.close for bar in observed)
    latest_close = closes[-1]
    key_bars = observed[-_KEY_LEVEL_LOOKBACK:]
    support_bar = min(key_bars, key=lambda bar: (bar.low, bar.timestamp))
    resistance_bar = max(key_bars, key=lambda bar: (bar.high, -bar.timestamp.timestamp()))
    sma20 = _mean(closes[-20:])
    sma50 = _mean(closes[-50:])
    trend = "bullish" if sma20 > sma50 else "bearish" if sma20 < sma50 else "neutral"
    market_state = DecisionMarketState(
        trend=trend,
        latest_close=latest_close,
        sma20=sma20,
        sma50=sma50,
        support=support_bar.low,
        resistance=resistance_bar.high,
        invalidation=support_bar.low,
        observed_drawdown=_maximum_drawdown(closes),
        observed_volatility=_observed_volatility(closes),
        key_level_bar_times=tuple(sorted({support_bar.timestamp, resistance_bar.timestamp})),
    )

    blockers: list[DecisionBlocker] = []
    if history.gaps or history.duplicates or history.limitations:
        blockers.append(
            _blocker(
                "history-quality",
                "history records gaps, duplicates, or stated limitations",
                f"history:{history.dataset_id}",
            )
        )
    if history.source != "demo-synthetic" and (
        history.manifest_id is None or history.quality_evaluation_id is None
    ):
        blockers.append(
            _blocker(
                "history-lineage",
                "non-demo history requires manifest and quality evidence",
                f"history:{history.dataset_id}",
            )
        )
    if history.generated_at > selected_as_of:
        blockers.append(
            _blocker(
                "history-freshness",
                "history generated_at is after the decision clock",
                f"history:{history.dataset_id}",
            )
        )
    elif selected_as_of - history.generated_at > _HISTORY_FRESHNESS:
        blockers.append(
            _blocker(
                "history-freshness",
                "history is older than one day",
                f"history:{history.dataset_id}",
            )
        )
    if selected_as_of - observed[-1].timestamp > _HISTORY_FRESHNESS:
        blockers.append(
            _blocker(
                "history-freshness",
                "latest observed bar is older than one day",
                f"history:{history.dataset_id}",
            )
        )

    final_quantiles: tuple[float, float, float] | None = None
    forecast_chronology: DecisionForecastChronology | None = None
    if forecast is None:
        blockers.append(
            _blocker("forecast-missing", "no forecast is attached", "forecast:missing")
        )
    else:
        if not forecast.eligible:
            blockers.append(
                _blocker(
                    "forecast-ineligible",
                    "forecast is ineligible for paper proposal",
                    f"forecast:{forecast.artifact_id}",
                )
            )
        if forecast.generated_at > selected_as_of:
            blockers.append(
                _blocker(
                    "chronology",
                    "forecast generated_at is after the decision clock",
                    f"forecast:{forecast.artifact_id}",
                )
            )
        elif selected_as_of - forecast.generated_at > _FORECAST_FRESHNESS:
            blockers.append(
                _blocker(
                    "forecast-freshness",
                    "forecast is older than one day at the decision clock",
                    f"forecast:{forecast.artifact_id}",
                )
            )
        path30 = next((path for path in forecast.paths if path.sessions == 30), None)
        if path30 is None or any(
            point.timestamp <= forecast.train_end
            for path in forecast.paths
            for point in path.points
        ):
            blockers.append(
                _blocker(
                    "chronology",
                    "forecast paths do not preserve future-only chronology",
                    f"forecast:{forecast.artifact_id}",
                )
            )
        else:
            final = path30.points[-1]
            final_quantiles = (final.p75, final.p50, final.p25)
        forecast_chronology = DecisionForecastChronology(
            train_start=forecast.train_start,
            train_end=forecast.train_end,
            validation_start=forecast.validation_start,
            validation_end=forecast.validation_end,
            test_start=forecast.test_start,
            test_end=forecast.test_end,
        )
        if forecast.train_end > selected_as_of:
            blockers.append(
                _blocker(
                    "leakage",
                    "forecast training end is after the decision clock",
                    f"forecast:{forecast.artifact_id}",
                )
            )
        if not forecast.synthetic and (
            forecast.manifest_id is None or forecast.quality_evaluation_id is None
        ):
            blockers.append(
                _blocker(
                    "forecast-ineligible",
                    "real forecast requires manifest and quality evidence",
                    f"forecast:{forecast.artifact_id}",
                )
            )
    if any(bar.timestamp > selected_as_of for bar in history.bars):
        blockers.append(
            _blocker(
                "leakage",
                "history contains a bar after the decision clock",
                f"history:{history.dataset_id}",
            )
        )
    if not risk.valuation_complete or not risk.mark_available:
        blockers.append(
            _blocker(
                "valuation",
                risk.valuation_reason or "paper valuation or mark is incomplete",
                "risk:valuation",
            )
        )
    if risk.global_kill_switch or risk.venue_kill_switch:
        blockers.append(
            _blocker("kill-switch", "a paper kill switch is enabled", "risk:kill-switch")
        )
    if not proposal.allowed:
        blockers.append(
            _blocker(
                "proposal-service",
                "; ".join(proposal.blockers),
                "proposal:capability",
            )
        )

    # A non-positive forecast base target is not actionable, but the market
    # packet still renders.  Keep the risk plan internally coherent while the
    # evidence blocker prevents Paper from becoming authoritative.
    base_target = final_quantiles[1] if final_quantiles is not None else market_state.resistance
    stop_price = min(market_state.invalidation, latest_close * 0.99)
    target_price = max(base_target, latest_close * 1.01)
    risk_per_unit = latest_close - stop_price
    reward_per_unit = target_price - latest_close
    quantity = _suggested_quantity(
        account,
        entry_price=latest_close,
        risk_per_unit=risk_per_unit,
        instrument_key=position_key(history.instrument),
    )
    if quantity is None:
        blockers.append(
            _blocker(
                "valuation",
                "account limits leave no positive suggested paper size",
                "risk:limits",
            )
        )
    risk_plan = DecisionRiskPlan(
        entry_price=latest_close,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_unit=risk_per_unit,
        reward_per_unit=reward_per_unit,
        reward_to_risk=reward_per_unit / risk_per_unit,
        suggested_quantity=quantity,
        suggested_notional=quantity * latest_close if quantity is not None else None,
        proposal_input_only=True,
    )
    targets = final_quantiles or (target_price, target_price, stop_price)
    confidence_reason = "forecast quantiles are qualitative and not calibrated probabilities"
    scenarios = (
        DecisionScenario(
            kind="bull",
            thesis="observed trend and upper forecast quantile support continuation",
            trigger="observed close holds above resistance",
            invalidation=stop_price,
            target=targets[0],
            confidence_reason=confidence_reason,
        ),
        DecisionScenario(
            kind="base",
            thesis="observed structure and median forecast path remain intact",
            trigger="observed close holds above support",
            invalidation=stop_price,
            target=targets[1],
            confidence_reason=confidence_reason,
        ),
        DecisionScenario(
            kind="bear",
            thesis="support failure invalidates the observed structure",
            trigger="observed close falls below support",
            invalidation=stop_price,
            target=targets[2],
            confidence_reason=confidence_reason,
        ),
    )
    evidence = DecisionEvidence(
        history_dataset_id=history.dataset_id,
        history_dataset_revision=history.dataset_revision,
        history_manifest_id=history.manifest_id,
        history_quality_evaluation_id=history.quality_evaluation_id,
        history_source=history.source,
        history_generated_at=history.generated_at,
        history_gaps=history.gaps,
        history_duplicates=history.duplicates,
        history_limitations=history.limitations,
            forecast_artifact_id=forecast.artifact_id if forecast is not None else None,
            forecast_dataset_id=forecast.dataset_id if forecast is not None else None,
            forecast_dataset_revision=forecast.dataset_revision if forecast is not None else None,
            forecast_manifest_id=forecast.manifest_id if forecast is not None else None,
            forecast_quality_evaluation_id=(
                forecast.quality_evaluation_id if forecast is not None else None
            ),
            forecast_synthetic=forecast.synthetic if forecast is not None else None,
            forecast_eligible=forecast.eligible if forecast is not None else None,
            forecast_blockers=forecast.blockers if forecast is not None else (),
            forecast_limitations=forecast.limitations if forecast is not None else (),
        forecast_model_name=forecast.model_name if forecast is not None else None,
        forecast_model_version=forecast.model_version if forecast is not None else None,
        forecast_config_digest=forecast.config_digest if forecast is not None else None,
        forecast_history_digest=forecast.history_digest if forecast is not None else None,
        forecast_benchmark_name=forecast.benchmark_name if forecast is not None else None,
        forecast_generated_at=forecast.generated_at if forecast is not None else None,
        forecast_chronology=forecast_chronology,
        forecast_paths=forecast.paths if forecast is not None else (),
        forecast_metrics=forecast.metrics if forecast is not None else (),
        costs=DecisionCostEvidence(
            fee_bps=account.fee_model.fee_bps,
            slippage_bps=account.matcher.slippage_bps,
            half_spread_bps=None,
            spread_status="confirmation-quote-required",
        ),
    )
    packet = DecisionPacket(
        packet_id="packet-" + "0" * 24,
        version=1,
        parent_packet_id=None,
        instrument=history.instrument,
        selected_range=selected_range,
        as_of=selected_as_of,
        created_at=selected_as_of,
        market_state=market_state,
        scenarios=scenarios,
        risk_plan=risk_plan,
        evidence=evidence,
        paper_capability=DecisionPaperCapability(
            allowed=not _normalized_blockers(blockers),
            blockers=_normalized_blockers(blockers),
        ),
        disposition=DecisionDisposition.DRAFT,
    )
    return packet.model_copy(update={"packet_id": decision_packet_id(packet)})
