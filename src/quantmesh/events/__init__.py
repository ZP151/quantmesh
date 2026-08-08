"""Canonical event-market domain (M6, issues #34-#37).

Venue-neutral event, outcome, resolution-rule, quote and implied-
probability models that both Polymarket and Kalshi adapters normalize
into (``quantmesh.events.models``); the pure fee/spread/liquidity-aware
calibration transforms (``quantmesh.events.calibration``); the
calibration forecast report stack with point-in-time replay
(``quantmesh.events.forecast``); and the evidence-disciplined
cross-platform event mapping and its ledger
(``quantmesh.events.mapping``).
"""

from quantmesh.events.calibration import (
    CalibrationBin,
    brier,
    brier_by_bin,
    brier_score,
    fee_adjusted_mid,
    history_signal,
    implied_probability,
    liquidity_confidence,
    liquidity_weighted_brier,
    with_history_fallback,
)
from quantmesh.events.forecast import (
    ForecastMarket,
    ForecastObservation,
    ForecastReport,
    ForecastReportRegistry,
    ForecastWindowResult,
    ForecastWindowSpec,
    MarketForecast,
    forecast_artifact_paths,
    forecast_report_id,
    run_forecast,
    run_forecast_report,
)
from quantmesh.events.mapping import (
    EventMappingReport,
    EventPairing,
    EvidenceKind,
    MappingEvidence,
    MappingLedger,
    MappingRecord,
    MappingStatus,
    map_events,
    normalize_event_text,
    pair_key,
)
from quantmesh.events.models import (
    EventMarket,
    EventVenue,
    ImpliedProbability,
    MarketQuote,
    Outcome,
    ResolutionRule,
)

__all__ = [
    "CalibrationBin",
    "EventMarket",
    "EventMappingReport",
    "EventPairing",
    "EventVenue",
    "EvidenceKind",
    "ForecastMarket",
    "ForecastObservation",
    "ForecastReport",
    "ForecastReportRegistry",
    "ForecastWindowResult",
    "ForecastWindowSpec",
    "ImpliedProbability",
    "MappingEvidence",
    "MappingLedger",
    "MappingRecord",
    "MappingStatus",
    "MarketForecast",
    "MarketQuote",
    "Outcome",
    "ResolutionRule",
    "brier",
    "brier_by_bin",
    "brier_score",
    "fee_adjusted_mid",
    "forecast_artifact_paths",
    "forecast_report_id",
    "history_signal",
    "implied_probability",
    "liquidity_confidence",
    "liquidity_weighted_brier",
    "map_events",
    "normalize_event_text",
    "pair_key",
    "run_forecast",
    "run_forecast_report",
    "with_history_fallback",
]
