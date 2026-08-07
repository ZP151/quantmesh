"""Research and backtesting integration points."""

from quantmesh.research.baselines import (
    book_imbalance_weights,
    low_volatility_weights,
    run_baseline_report,
    run_walk_forward,
)
from quantmesh.research.experiments import (
    Experiment,
    ExperimentRegistry,
    experiment_id,
)
from quantmesh.research.features import (
    FEATURES,
    FeatureKind,
    FeatureRegistry,
    FeatureSet,
    FeatureSpec,
    compute_feature,
    compute_features,
    feature_id,
    featureset_id,
    frame_digest,
)
from quantmesh.research.models import (
    LinearModel,
    ModelRecord,
    ModelRegistry,
    ModelSpec,
    artifact_path,
    fit_model,
    model_id,
)
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    WindowResult,
    artifact_paths,
    report_id,
)

__all__ = [
    "CostModel",
    "Experiment",
    "ExperimentRegistry",
    "FEATURES",
    "FeatureKind",
    "FeatureRegistry",
    "FeatureSet",
    "FeatureSpec",
    "LinearModel",
    "ModelRecord",
    "ModelRegistry",
    "ModelSpec",
    "ReportRegistry",
    "StrategyReport",
    "UniverseMember",
    "WalkForwardSpec",
    "WindowResult",
    "artifact_path",
    "artifact_paths",
    "book_imbalance_weights",
    "compute_feature",
    "compute_features",
    "experiment_id",
    "feature_id",
    "featureset_id",
    "fit_model",
    "frame_digest",
    "low_volatility_weights",
    "model_id",
    "report_id",
    "run_baseline_report",
    "run_walk_forward",
]
