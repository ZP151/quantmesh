"""Local runtime assembly (iteration 0026, issue #116 follow-up).

The workstation and demo used to construct the same eleven ADR-0006 stores and
registries inline, each time binding them to slightly different roots. This
module is the "build once" seam: one frozen ``WorkstationStores`` bundle and one
factory that lays them out under a single root (demo) or the operator's
settings dirs (non-demo). The workstation page assembly reads the bundle; the
demo seeder builds it once.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantmesh.ai.decisions import DecisionLog
from quantmesh.ai.retrieval import DocumentIndex
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.events.forecast import ForecastReportRegistry
from quantmesh.events.mapping import MappingLedger
from quantmesh.execution.journal import OrderJournal
from quantmesh.instruments.copilot import PacketCopilotStore
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.ops.enablement import ApprovalLedger
from quantmesh.research.drift import AlertLedger, PromotionLedger
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.research.reports import ReportRegistry
from quantmesh.settings import settings


@dataclass(frozen=True)
class WorkstationStores:
    """The ADR-0006 store/registry assembly the workstation reads."""

    watchlist: WatchlistStore
    experiments: ExperimentRegistry
    promotions: PromotionLedger
    reports: ReportRegistry
    forecasts: ForecastReportRegistry
    alerts: AlertLedger
    journal: OrderJournal
    mappings: MappingLedger
    decisions: DecisionLog
    documents: DocumentIndex
    enablement: ApprovalLedger
    decision_packets: DecisionPacketStore
    packet_copilot: PacketCopilotStore


def build_workstation_stores(
    *, root: Path | None = None, lake_root: Path | None = None
) -> WorkstationStores:
    """Build once: construct every workstation store/registry.

    With ``root`` the stores land under the demo layout (``root/<surface>``,
    lake under ``root/market/lake`` unless ``lake_root`` overrides); without
    ``root`` they use the operator's settings dirs (``settings.*_dir`` and
    ``settings.lake_root``).
    """
    if root is None:
        return WorkstationStores(
            watchlist=WatchlistStore(),
            experiments=ExperimentRegistry(lake_root=lake_root),
            promotions=PromotionLedger(),
            reports=ReportRegistry(lake_root=lake_root),
            forecasts=ForecastReportRegistry(),
            alerts=AlertLedger(),
            journal=OrderJournal(),
            mappings=MappingLedger(),
            decisions=DecisionLog(),
            documents=DocumentIndex(),
            enablement=ApprovalLedger(),
            decision_packets=DecisionPacketStore(settings.decisions_dir / "packets"),
            packet_copilot=PacketCopilotStore(settings.decisions_dir / "copilot"),
        )
    root = Path(root)
    effective_lake = root / "market" / "lake" if lake_root is None else Path(lake_root)
    return WorkstationStores(
        watchlist=WatchlistStore(root=root / "watchlists"),
        experiments=ExperimentRegistry(
            root=root / "research" / "experiments", lake_root=effective_lake
        ),
        promotions=PromotionLedger(root=root / "research" / "promotions"),
        reports=ReportRegistry(
            root=root / "research" / "reports", lake_root=effective_lake
        ),
        forecasts=ForecastReportRegistry(root=root / "research" / "reports"),
        alerts=AlertLedger(root=root / "alerts"),
        journal=OrderJournal(root=root / "orders"),
        mappings=MappingLedger(root=root / "mappings"),
        decisions=DecisionLog(root=root / "decisions"),
        documents=DocumentIndex(root=root / "documents"),
        enablement=ApprovalLedger(root=root / "enablement"),
        decision_packets=DecisionPacketStore(root / "decisions" / "packets"),
        packet_copilot=PacketCopilotStore(root / "decisions" / "copilot"),
    )
