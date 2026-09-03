"""The repo-canonical golden-path walk (iteration 0013 Phase C).

The operator-facing proof that a release checkout works end to end:

  fixture/public data -> data lake -> strategy reports -> internal
  paper -> UI (all 13 workstation screens), then restart and confirm
  data, orders and every audit ledger recover from the same data root
  (the M10 recovery drill replays the order journal into a fresh paper
  account).

Generated state lives under an explicit root. By default the root is a
temporary directory that is removed on success and kept (with its path
printed) on failure; pass ``--root PATH`` for an operator-owned root
that is never removed, or ``--keep`` to keep the temporary root even
after a successful run. A fresh checkout therefore stays clean after
the walk (iteration 0013 Phase B review finding 4).

Run with the release extras installed, from the repository root:
``python tools/golden_path.py``. Prints PASS/FAIL per check and exits
non-zero on any failure.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import BaseModel

from quantmesh.ai.decisions import Citation, DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.retrieval import DocumentIndex
from quantmesh.api import workstation
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.api.workstation import create_workstation_app
from quantmesh.data.ingestion import IngestionJob, Ingestor
from quantmesh.data.lake import Lake
from quantmesh.data.providers import HyperliquidFixtureProvider, ProviderRegistry
from quantmesh.demo.runtime import create_demo_app
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.events.forecast import (
    ForecastMarket,
    ForecastObservation,
    ForecastReport,
    ForecastReportRegistry,
    ForecastWindowSpec,
    forecast_report_id,
    run_forecast,
)
from quantmesh.events.mapping import (
    MAPPINGS_FILE,
    EvidenceKind,
    MappingEvidence,
    MappingLedger,
    MappingRecord,
    MappingStatus,
)
from quantmesh.events.models import EventMarket, EventVenue, Outcome, ResolutionRule
from quantmesh.execution.accounting import FeeModel, PaperAccount, PaperMatcher
from quantmesh.execution.journal import OrderJournal
from quantmesh.ops.enablement import ApprovalLedger
from quantmesh.ops.metrics import Metric, MetricsStore, metric_id
from quantmesh.research.drift import (
    AlertLedger,
    AlertRecord,
    PromotionLedger,
    PromotionRecord,
    alert_id,
    promotion_id,
)
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    report_id,
)

PORT = 8643
HOST = "127.0.0.1"
BASE = f"http://{HOST}:{PORT}"
NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
COMMIT = "a" * 40
DEMO_RESET_BUDGET_SECONDS = 30.0

failures: list[str] = []
checks_run = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks_run  # noqa: PLW0603
    checks_run += 1
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def http_get(base: str, path: str) -> str:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as response:
            body = response.read().decode("utf-8")
            if response.status != 200:
                raise AssertionError(f"{path}: status {response.status}")
            return body
    except urllib.error.HTTPError as error:
        raise AssertionError(f"{path}: HTTP {error.code}") from error


class _Claim(BaseModel):
    claim: str
    confidence: float
    citations: list[str]


def run(root: Path) -> None:
    """The full walk over ``root``. Every store writes under the root;
    nothing is written into the checkout itself."""
    # -------------------------------------------------------------------
    # 1. Fixture/public data -> data lake
    # -------------------------------------------------------------------

    BTC = Instrument(
        symbol="BTC-PERP",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
    )
    AAPL = Instrument(symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY)
    POSITION_KEY = "internal:AAPL"
    MARKETS = {
        "hyperliquid": {"BTC": 65_000.0, "ETH": 3_200.0},
        "moomoo": {"AAPL": 210.0},
    }
    SPEC = WalkForwardSpec(train_bars=10, test_bars=5, step_bars=10)
    COSTS = CostModel(fee_bps=5, half_spread_bps=2, slippage_bps=1)
    UNIVERSE = [UniverseMember(venue=Venue.INTERNAL, symbol="AAPL")]

    lake_root = root / "lake"
    registry = ProviderRegistry([HyperliquidFixtureProvider()])
    manifest = Ingestor(registry, lake_root).ingest(
        IngestionJob(dataset="algo", instrument=BTC, interval="1m")
    )
    check("fixture -> data lake: ingest writes bars + manifest", manifest is not None)
    bars = (
        Lake(lake_root)
        .dataset("algo")
        .read_bars(interval="1m", venue=Venue.HYPERLIQUID, symbol="BTC-PERP")
    )
    check("data lake holds fixture bars", len(bars) > 0, f"{len(bars)} bars")

    # -------------------------------------------------------------------
    # 2. Data lake -> strategy reports
    # -------------------------------------------------------------------

    experiments = ExperimentRegistry(root=root / "experiments", lake_root=lake_root)
    experiments.record(
        dataset="algo",
        revision=1,
        commit=COMMIT,
        parameters={"lookback": 20, "rebalance": "daily"},
        metrics={"sharpe": 1.5, "max_drawdown": -0.12, "optimized": True, "note": None},
    )
    check(
        "strategy reports: experiment recorded (lake-pinned)",
        len(experiments.all()) == 1,
    )

    reports = ReportRegistry(root=root / "reports", lake_root=lake_root)

    def make_report(strategy: str, interval: str = "1d") -> StrategyReport:
        rid = report_id(
            dataset="algo",
            revision=1,
            commit=COMMIT,
            strategy=strategy,
            interval=interval,
            universe=UNIVERSE,
            window_spec=SPEC,
            costs=COSTS,
        )
        return StrategyReport(
            id=rid,
            dataset="algo",
            revision=1,
            commit=COMMIT,
            strategy=strategy,
            interval=interval,
            universe=UNIVERSE,
            window_spec=SPEC,
            costs=COSTS,
            created_at=NOW,
            metrics={"sharpe": 1.5},
            evidence={},
        )

    benchmark = reports.record(make_report("momentum"))
    ablation = reports.record(make_report("mean_reversion"))
    oos = reports.record(make_report("momentum", interval="1h"))
    check("strategy reports: reports recorded (lake-pinned)", len(reports.all()) == 3)

    promotions = PromotionLedger(root=root / "promotions")
    promotions.record(
        PromotionRecord(
            id=promotion_id(
                signal_name="momentum_plus",
                benchmark_report_ids=[benchmark.id],
                ablation_report_ids=[ablation.id],
                oos_report_id=oos.id,
                kill_switch=False,
            ),
            signal_name="momentum_plus",
            benchmark_report_ids=[benchmark.id],
            ablation_report_ids=[ablation.id],
            oos_report_id=oos.id,
            kill_switch=False,
            promoted_at=NOW,
        )
    )
    check("strategy reports: promotion recorded", len(promotions.all()) == 1)

    event_market = EventMarket(
        venue=EventVenue.KALSHI,
        venue_market_id="mkt-1",
        event_ticker="event-1",
        title="Will it rain?",
        category="test",
        outcomes=[
            Outcome(name="Yes", venue_outcome_id="yes"),
            Outcome(name="No", venue_outcome_id="no"),
        ],
        resolution_rule=ResolutionRule.of("fixture rule text"),
        resolution=[],
        resolved_at=None,
    )
    observations = [
        ForecastObservation(
            timestamp=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=i),
            probability=0.3 + 0.01 * i,
            liquidity_confidence=1.0,
        )
        for i in range(10)
    ]
    window_spec = ForecastWindowSpec(train_observations=5, test_observations=5, step_observations=5)
    metrics, per_market = run_forecast(
        [ForecastMarket(market=event_market, observations=observations)],
        window_spec=window_spec,
        n_bins=10,
    )
    forecasts = ForecastReportRegistry(root=root / "forecasts")
    forecasts.record(
        ForecastReport(
            id=forecast_report_id(
                commit=COMMIT,
                universe=[event_market],
                window_spec=window_spec,
                n_bins=10,
            ),
            commit=COMMIT,
            universe=[event_market],
            window_spec=window_spec,
            n_bins=10,
            created_at=NOW,
            metrics=metrics,
            markets=per_market,
        )
    )
    check("strategy reports: forecast report recorded", len(forecasts.all()) == 1)

    # -------------------------------------------------------------------
    # 3. Internal paper + audit records
    # -------------------------------------------------------------------

    account = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )

    def quote() -> Quote:
        return Quote(instrument=AAPL, timestamp=NOW, bid=99.0, ask=100.0, volume=100)

    for side, quantity in ((Side.BUY, 10), (Side.SELL, 4), (Side.BUY, 10)):
        account = account.submit(
            OrderRequest(instrument=AAPL, side=side, quantity=quantity),
            quote(),
            now=NOW,
        ).account
    check("internal paper: 3 orders filled on AAPL", len(account.orders) == 3)
    check(
        "internal paper: 16 AAPL held",
        account.positions.get(POSITION_KEY) is not None
        and account.positions[POSITION_KEY].quantity == 16,
    )

    journal = OrderJournal(root=root / "journal")
    for order in account.orders.values():
        journal.record(order)
    check("audit: order journal records the 3 orders", len(journal.all()) == 3)

    mappings_root = root / "mappings"
    mappings_root.mkdir(parents=True, exist_ok=True)
    (mappings_root / MAPPINGS_FILE).write_text(
        MappingRecord(
            pair_key="a" * 16,
            status=MappingStatus.MATCHED,
            evidence=[
                MappingEvidence(kind=EvidenceKind.OUTCOME_SET, detail="yes/no"),
                MappingEvidence(kind=EvidenceKind.TITLE, detail="same title"),
            ],
            commit="b" * 40,
            recorded_at=NOW,
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    mappings = MappingLedger(root=mappings_root)
    check("audit: mapping ledger holds the matched pair", len(mappings.all()) == 1)

    decisions = DecisionLog(root=root / "decisions")
    decisions.record(
        DecisionRecord.for_stage(
            run_id="c" * 16,
            role="analyst",
            model=ModelMeta(name="fixture-model", version="1.0", endpoint_kind="scripted"),
            prompt="What is the state of the market?",
            schema_id="analyst-claim-v1",
            output=_Claim(
                claim="The market is calm.",
                confidence=0.7,
                citations=[
                    "experiment:a1b2c3d4e5f60718",
                    "document:doc-1",
                    "audit:paper-1",
                ],
            ),
            citations=[
                Citation(source_kind="experiment", source_id="a1b2c3d4e5f60718"),
                Citation(source_kind="document", source_id="doc-1"),
                Citation(source_kind="audit", source_id="paper-1"),
            ],
            recorded_at=NOW,
        )
    )
    check("audit: decision log records the analyst decision", len(decisions.all()) == 1)

    metrics_store = MetricsStore(root=root / "metrics")
    metrics_store.record(
        Metric(
            id=metric_id(name="paper_pnl", measured_at=NOW),
            name="paper_pnl",
            kind="gauge",
            unit="usd",
            value=-80.0,
            measured_at=NOW,
        )
    )
    check("audit: metrics store records the sample", len(metrics_store.all()) == 1)

    alerts = AlertLedger(root=root / "alerts")
    alerts.record(
        AlertRecord(
            id=alert_id(kind="staleness", source="fixture-walk", detected_at=NOW, observed={}),
            kind="staleness",
            source="fixture-walk",
            detected_at=NOW,
            message="fixture walk staleness alert",
            observed={},
        )
    )
    check("audit: alert ledger records the alert", len(alerts.all()) == 1)

    watchlist = WatchlistStore(root=root / "watchlists")
    watchlist.add("SOL")
    check(
        "audit: watchlist store holds SOL",
        [r.symbol for r in watchlist.all()] == ["SOL"],
    )

    documents = DocumentIndex(root=root / "documents")
    news_file = root / "news.txt"
    news_file.write_text("The Fed holds rates steady at the July meeting.", encoding="utf-8")
    documents.ingest_file(news_file, kind="news", doc_id="doc-1")
    check("audit: document index holds doc-1", len(documents.all()) == 1)

    enablement = ApprovalLedger(root=root / "enablement")
    enablement.request(Venue.HYPERLIQUID, actor="operator", acted_at=NOW)
    check(
        "audit: enablement ledger records the request",
        enablement.state(Venue.HYPERLIQUID).value == "pending",
    )

    # -------------------------------------------------------------------
    # 4. UI walk
    # -------------------------------------------------------------------

    def build_app() -> object:
        # The UI walk pins the RC1 Jinja2 pages (ADR-0013 decision 6,
        # the rollback switch); Phase C migrates these checks to the
        # SPA surface.
        workstation.settings.legacy_ui = True
        return create_workstation_app(
            account=account,
            marks={POSITION_KEY: 95.0},
            markets=dict(MARKETS),
            watchlist=watchlist,
            experiments=experiments,
            promotions=promotions,
            reports=reports,
            forecasts=forecasts,
            alerts=alerts,
            journal=journal,
            mappings=mappings,
            decisions=decisions,
            documents=documents,
            enablement=enablement,
            host=HOST,
        )

    def start_server(app: object, port: int, base: str) -> None:
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
        threading.Thread(target=server.run, daemon=True).start()
        for _ in range(200):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                return
            except Exception:
                time.sleep(0.05)
        raise AssertionError(f"uvicorn never came up on {HOST}:{port}")

    def walk_ui(base: str, phase: str) -> None:
        body = http_get(base, "/")
        check(
            f"UI ({phase}): overview renders paper account + hyperliquid",
            "Paper account" in body and "hyperliquid" in body,
        )

        body = http_get(base, "/watchlist")
        check(f"UI ({phase}): watchlist shows SOL", "SOL" in body)

        body = http_get(base, "/instruments")
        check(
            f"UI ({phase}): instruments renders cross-venue list",
            "Cross-venue instruments" in body,
        )

        body = http_get(base, "/portfolio/positions")
        check(
            f"UI ({phase}): positions show AAPL and mark-derived P&L -80.0",
            "AAPL" in body and "-80.0" in body,
        )

        body = http_get(base, "/portfolio/orders")
        check(
            f"UI ({phase}): orders render paper-1 with a fill",
            "paper-1" in body and "fill" in body,
        )

        body = http_get(base, "/portfolio/pnl")
        check(f"UI ({phase}): P&L renders equity", "Equity" in body)

        body = http_get(base, "/experiments")
        check(
            f"UI ({phase}): experiments render the recorded run",
            "lookback" in body,
        )

        body = http_get(base, "/promotions")
        check(f"UI ({phase}): promotions render momentum_plus", "momentum_plus" in body)

        body = http_get(base, "/forecasts")
        check(f"UI ({phase}): forecasts render the report", "Will it rain?" in body)

        body = http_get(base, "/risk")
        check(f"UI ({phase}): risk page renders", "Risk" in body)

        body = http_get(base, "/audit")
        check(f"UI ({phase}): audit page renders", "Audit" in body)

        body = http_get(base, "/kill-switch/control")
        check(f"UI ({phase}): kill-switch page renders", "Kill switch" in body)

        body = http_get(base, "/enablement")
        check(
            f"UI ({phase}): enablement renders hyperliquid pending",
            "hyperliquid" in body and "pending" in body,
        )

    start_server(build_app(), PORT, BASE)
    walk_ui(BASE, "first boot")

    # -------------------------------------------------------------------
    # 5. Restart: the same roots re-bound; the account comes back
    #    through the M10 Phase B recovery drill (journal replay).
    # -------------------------------------------------------------------
    PORT2 = 8644
    BASE2 = f"http://{HOST}:{PORT2}"

    from quantmesh.ops.recover import replay_orders

    recovered = replay_orders(journal.all(), cash=10_000.0, fee_bps=10)
    check(
        "restart: journal replay recovers the paper account (16 AAPL)",
        recovered.positions.get(POSITION_KEY) is not None
        and recovered.positions[POSITION_KEY].quantity == 16,
    )
    account = recovered
    start_server(build_app(), PORT2, BASE2)
    walk_ui(BASE2, "restart")

    # Every audit ledger re-reads its records from the same data root.
    reports_rebound = ReportRegistry(root=root / "reports", lake_root=lake_root)
    check(
        "restart: report registry re-reads 3 reports",
        len(reports_rebound.all()) == 3,
    )
    journal_rebound = OrderJournal(root=root / "journal")
    check("restart: order journal re-reads 3 orders", len(journal_rebound.all()) == 3)
    mappings_rebound = MappingLedger(root=mappings_root)
    check(
        "restart: mapping ledger re-reads the matched pair",
        len(mappings_rebound.all()) == 1,
    )
    metrics_rebound = MetricsStore(root=root / "metrics")
    check(
        "restart: metrics store re-reads the sample",
        len(metrics_rebound.all()) == 1,
    )
    decisions_rebound = DecisionLog(root=root / "decisions")
    check(
        "restart: decision log re-reads the decision",
        len(decisions_rebound.all()) == 1,
    )
    alerts_rebound = AlertLedger(root=root / "alerts")
    check("restart: alert ledger re-reads the alert", len(alerts_rebound.all()) == 1)
    promotions_rebound = PromotionLedger(root=root / "promotions")
    check(
        "restart: promotion ledger re-reads the promotion",
        len(promotions_rebound.all()) == 1,
    )
    documents_rebound = DocumentIndex(root=root / "documents")
    check("restart: document index re-reads doc-1", len(documents_rebound.all()) == 1)
    watchlist_rebound = WatchlistStore(root=root / "watchlists")
    check(
        "restart: watchlist re-reads SOL",
        [r.symbol for r in watchlist_rebound.all()] == ["SOL"],
    )
    enablement_rebound = ApprovalLedger(root=root / "enablement")
    check(
        "restart: enablement ledger re-reads the request (pending)",
        enablement_rebound.state(Venue.HYPERLIQUID).value == "pending",
    )

    # -------------------------------------------------------------------
    # 6. Integrated instrument workspace -> proposal -> lineage -> safety
    # -------------------------------------------------------------------

    workstation.settings.legacy_ui = False
    integrated = create_demo_app(root=root / "integrated-workspace", host=HOST)
    with TestClient(integrated) as client:
        workspace_response = client.get(
            "/api/instruments/moomoo/NVDA/workspace?range=6m"
        )
        workspace = workspace_response.json()
        check(
            "workspace: GET composes observed history, forecast and paper authority",
            workspace_response.status_code == 200
            and len(workspace["history"]["bars"]) > 0
            and workspace["forecast"]["eligible"] is True
            and workspace["proposal"]["allowed"] is True,
        )

        order_rows_before = client.get("/api/demo/status").json()["surfaces"]["orders"]["rows"]
        draft = workspace["decision"]["draft"]
        saved_response = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": draft["packet_id"],
            },
        )
        saved = saved_response.json()
        action_payload = {
            "disposition": "paper_proposal",
            "operator_reason": None,
            "side": "buy",
            "quantity": 1.0,
            "limit_price": None,
        }
        preview_response = client.post(
            f"/api/decision-packets/{saved['packet_id']}/actions",
            json=action_payload,
        )
        preview = preview_response.json()["proposal"]
        order_rows_after_preview = client.get("/api/demo/status").json()["surfaces"][
            "orders"
        ]["rows"]
        check(
            "workspace: proposal preview is pending and creates no order",
            saved_response.status_code == 200
            and preview_response.status_code == 200
            and preview["status"] == "pending"
            and order_rows_after_preview == order_rows_before,
        )

        confirmed_response = client.post(
            f"/api/paper/proposals/{preview['id']}/confirm",
            json={"confirmation_token": preview["confirmation_token"]},
        )
        confirmed = confirmed_response.json()
        order_id = confirmed.get("order", {}).get("order_id")
        check(
            "workspace: exact-token confirmation creates one linked paper order",
            confirmed_response.status_code == 200
            and confirmed["proposal"]["status"] == "confirmed"
            and confirmed["proposal"]["order_id"] == order_id
            and confirmed["proposal"]["quote_provenance"] == "demo-synthetic",
        )
        audit_body = client.get("/api/audit").text
        check(
            "workspace: confirmed order is discoverable through audit lineage",
            isinstance(order_id, str) and order_id in audit_body,
        )

        race_reset = client.post("/api/demo/reset")
        race_workspace = client.get(
            "/api/instruments/moomoo/NVDA/workspace?range=6m"
        ).json()
        race_draft = race_workspace["decision"]["draft"]
        race_saved = client.post(
            "/api/decision-packets",
            json={
                "venue": "moomoo",
                "symbol": "NVDA",
                "selected_range": "6m",
                "expected_packet_id": race_draft["packet_id"],
            },
        ).json()
        race_preview_response = client.post(
            f"/api/decision-packets/{race_saved['packet_id']}/actions",
            json={**action_payload, "quantity": 2.0},
        )
        race_preview = race_preview_response.json()["proposal"]
        client.post("/api/kill-switch", json={"action": "engage"})
        refused_response = client.post(
            f"/api/paper/proposals/{race_preview['id']}/confirm",
            json={"confirmation_token": race_preview["confirmation_token"]},
        )
        refused = refused_response.json()
        check(
            "workspace: kill-switch race refuses confirmation with typed evidence",
            race_reset.status_code == 200
            and race_preview_response.status_code == 200
            and refused_response.status_code == 409
            and refused["proposal"]["status"] in {"blocked", "rejected"}
            and bool(refused["blocker"]),
        )

        reset_started = time.monotonic()
        reset_response = client.post("/api/demo/reset")
        reset_seconds = time.monotonic() - reset_started
        restored = client.get(
            "/api/instruments/moomoo/NVDA/workspace?range=6m"
        ).json()
        check(
            "workspace: deterministic reset stays inside the operator latency budget",
            reset_response.status_code == 200
            and reset_seconds < DEMO_RESET_BUDGET_SECONDS,
            f"reset took {reset_seconds:.2f}s (budget < {DEMO_RESET_BUDGET_SECONDS:.0f}s)",
        )
        check(
            "workspace: reset clears mutations and restores deterministic authority",
            reset_response.status_code == 200
            and restored["proposal"]["proposals"] == []
            and restored["risk"]["global_kill_switch"] is False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the golden-path walk over a temporary or operator-owned state root.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--root",
        metavar="PATH",
        help="operator-owned state root; never removed",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the temporary state root after a successful run",
    )
    args = parser.parse_args()

    temporary = args.root is None
    root = Path(args.root) if args.root else Path(tempfile.mkdtemp(prefix="qmesh-golden-path-"))
    print(f"golden path root: {root}" + (" (temporary)" if temporary else ""))

    run(root)

    if failures:
        print(f"\nGOLDEN PATH FAILED: {len(failures)} of {checks_run} checks")
        if temporary:
            print(f"state kept for diagnostics at {root}")
        return 1
    if temporary and not args.keep:
        shutil.rmtree(root, ignore_errors=True)
        print("generated state removed (temporary root)")
    print(
        "\nGOLDEN PATH PASSED: "
        f"{checks_run} checks — fixture -> lake -> reports -> paper -> "
        "UI -> restart recovery -> integrated workspace decision loop"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
