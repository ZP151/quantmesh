"""Portfolio construction, constraints and scenario testing (M7 Phase D).

Risk-budget construction via scipy SLSQP over a typed constraint
surface (per-venue caps, asset-class caps, risk-weighted event-exposure
caps from the M6 implied probabilities, per-venue leverage limits from
the M5 risk checks); exposure decomposition by venue, asset class and
event; deterministic scenario shocks (gap moves, funding spikes,
liquidation cascades, event mis-resolutions) replayed through the M2
paper kernel; scenario reports on the M5 report stack with setup-only
identity.
"""

from quantmesh.portfolio.constraints import (
    AssetClassCap,
    ConstraintChecks,
    ConstraintKind,
    ConstraintValue,
    EventRiskCap,
    LeverageCap,
    PortfolioConstraints,
    VenueCap,
    check_constraints,
    constraint_values,
    leverage_cap_from_risk_limits,
)
from quantmesh.portfolio.exposure import (
    ExposureDecomposition,
    PortfolioHolding,
    decompose_exposure,
    holding_key,
)
from quantmesh.portfolio.optimizer import (
    OptimizationFailure,
    OptimizationResult,
    risk_budget_weights,
)
from quantmesh.portfolio.reports import (
    AccountConfig,
    ScenarioReport,
    ScenarioReportRegistry,
    account_config,
    run_scenario_report,
    scenario_report_artifact_paths,
    scenario_report_id,
)
from quantmesh.portfolio.scenarios import (
    EventMisresolutionShock,
    FundingShock,
    GapShock,
    LiquidationShock,
    Scenario,
    ScenarioRun,
    ScenarioRunWindow,
    ScenarioStep,
    Shock,
    run_scenario,
    scenario_id,
)

__all__ = [
    "AccountConfig",
    "AssetClassCap",
    "ConstraintChecks",
    "ConstraintKind",
    "ConstraintValue",
    "EventMisresolutionShock",
    "EventRiskCap",
    "ExposureDecomposition",
    "FundingShock",
    "GapShock",
    "LeverageCap",
    "LiquidationShock",
    "OptimizationFailure",
    "OptimizationResult",
    "PortfolioConstraints",
    "PortfolioHolding",
    "Scenario",
    "ScenarioReport",
    "ScenarioReportRegistry",
    "ScenarioRun",
    "ScenarioRunWindow",
    "ScenarioStep",
    "Shock",
    "VenueCap",
    "account_config",
    "check_constraints",
    "constraint_values",
    "decompose_exposure",
    "holding_key",
    "leverage_cap_from_risk_limits",
    "risk_budget_weights",
    "run_scenario",
    "run_scenario_report",
    "scenario_id",
    "scenario_report_artifact_paths",
    "scenario_report_id",
]
