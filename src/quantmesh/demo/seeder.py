"""The deterministic demo seeder (iteration 0014 Phase B).

``seed_demo_root`` writes one complete, labeled demo scenario into an
operator-chosen root: fixture files the real venue providers parse,
lake datasets the research registries pin against, JSONL ledgers every
domain service appends through its public API, and the paper account
replayed through real submits. Everything derives from the scenario's
fixed RNG seed and anchor — never the wall clock — so seeding the same
scenario twice produces byte-identical roots (the replay guarantee),
and every record carries the ``demo`` provenance label.

Isolation is enforced at the filesystem: a demo root must carry the
marker file written at seed time, and reset refuses to touch a root
that does not (the never-touches-non-demo-root guarantee). The seeder
never opens the operator's lake, orders, reports or any other
non-demo directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from quantmesh.ai.decisions import DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.retrieval import Citation, DocumentIndex
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.data.providers.hyperliquid import HyperliquidFixtureProvider
from quantmesh.data.providers.moomoo import MoomooFixtureProvider
from quantmesh.demo import generators
from quantmesh.demo.manifest import MARKER_NAME, DemoScenario
from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent
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
    _write_artifacts,
    forecast_report_id,
    run_forecast,
)
from quantmesh.events.mapping import (
    EventMappingReport,
    EventPairing,
    EvidenceKind,
    MappingEvidence,
    MappingLedger,
    MappingStatus,
    pair_key,
)
from quantmesh.events.models import EventMarket, EventVenue, Outcome, ResolutionRule
from quantmesh.execution.accounting import FeeModel, PaperAccount, PaperMatcher
from quantmesh.execution.journal import OrderJournal
from quantmesh.ops.enablement import ApprovalLedger
from quantmesh.research.drift import (
    AlertLedger,
    AlertRecord,
    PromotionEvidence,
    PromotionLedger,
    alert_id,
    promote_signal,
)
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    WindowResult,
    report_id,
)

# The seeded commit every demo record pins: a fixed, deterministic
# identity instead of the working tree's git HEAD (which would make
# replay depend on checkout state). Hex-shaped to satisfy the
# registries' commit validators.
DEMO_COMMIT = "0a1e2d3c4b5a69788796a5b4c3d2e1f0deadbeef"

# One deterministic paper-order sequence: fills across venues plus one
# resting limit below the market (the "working order" state). Quantities
# keep the buys inside the $100k starting cash at seeded prices.
ORDER_SEQUENCE: tuple[tuple[str, str, Side, float, float | None], ...] = (
    ("moomoo", "AAPL", Side.BUY, 10, None),
    ("moomoo", "MSFT", Side.BUY, 5, None),
    ("hyperliquid", "BTC-USD", Side.BUY, 0.5, None),
    ("moomoo", "AAPL", Side.SELL, 4, None),
    ("moomoo", "NVDA", Side.BUY, 3, None),
    ("hyperliquid", "BTC-USD", Side.SELL, 0.2, None),
    ("hyperliquid", "ETH-USD", Side.BUY, 5, None),
    ("hyperliquid", "SOL-USD", Side.BUY, 10, 0.9),  # limit below touch: resting
)

_DOCUMENT_TEXT = {
    "filing": (
        "10-K filing (demo): the seeded universe's fundamentals are synthetic; "
        "no real company data is implied. Symbols: {}."
    ),
    "news": (
        "Market news (demo, synthetic): the crypto cluster factor moved with "
        "the shared shock; cross-market correlation is a seeded relationship."
    ),
    "note": (
        "Research note (demo): the deterministic scenario pins this document's "
        "content; provenance is labeled demo, never mistaken for real data."
    ),
}


class DemoRootError(ValueError):
    """A demo root is missing its marker, or refuses a requested op."""


class DemoProviders:
    """One real fixture provider per seeded symbol.

    The fixture adapters are symbol-scoped by design (one fixture file
    set per symbol), so the demo assembles one provider per symbol
    over its own fixture directory and serves the universe through the
    real provider pipeline — fetch_bars/order_books/trades with the
    same fail-closed guarantees as any venue. A request outside the
    seeded universe fails closed.
    """

    def __init__(
        self,
        providers: dict[tuple[str, str], MoomooFixtureProvider | HyperliquidFixtureProvider],
        kinds: dict[tuple[str, str], str],
    ) -> None:
        self._by_key = dict(providers)
        self._kinds = dict(kinds)

    def _provider(
        self, venue: str, symbol: str
    ) -> MoomooFixtureProvider | HyperliquidFixtureProvider:
        try:
            return self._by_key[(venue, symbol)]
        except KeyError as error:
            raise ValueError(
                f"no demo provider for {venue}:{symbol} — outside the seeded universe"
            ) from error

    def _instrument(self, venue: str, symbol: str) -> Instrument:
        return _instrument(symbol, venue, self._kinds[(venue, symbol)])

    def instrument(self, venue: str, symbol: str) -> Instrument:
        """The canonical instrument for one seeded (venue, symbol)."""
        return self._instrument(venue, symbol)

    def series(self, venue: str, symbol: str, *, interval: str = "1d") -> list[Bar]:
        """The seeded bar series, through the real adapter."""
        return self._provider(venue, symbol).fetch_bars(
            self._instrument(venue, symbol), interval=interval
        )

    def order_books(self, venue: str, symbol: str) -> list[OrderBook]:
        return self._provider(venue, symbol).fetch_order_books(self._instrument(venue, symbol))

    def trades(self, venue: str, symbol: str) -> list[TradeEvent]:
        return self._provider(venue, symbol).fetch_trades(self._instrument(venue, symbol))

    def universe(self) -> set[tuple[str, str]]:
        """Every (venue, symbol) the demo serves."""
        return set(self._by_key)


@dataclass(frozen=True)
class DemoSeeded:
    """Everything a workstation app needs, built from one demo root.

    All objects are bound to files under ``root``; ``account`` is the
    replayed paper account, ``marks`` the position-keyed mark map, and
    ``markets`` the venue -> symbol -> mark board the UI renders.
    """

    root: Path
    scenario: DemoScenario
    account: PaperAccount
    marks: dict[str, float]
    markets: dict[str, dict[str, float]]
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
    providers: DemoProviders
    provenance: dict[str, object] = field(default_factory=dict)


def _marker(root: Path) -> Path:
    return root / MARKER_NAME


def is_demo_root(root: Path) -> bool:
    """True when the root carries the demo marker (and nothing else is
    required — the marker is the isolation contract)."""
    return _marker(root).is_file()


def _venue(name: str) -> Venue:
    return Venue(name)


def _instrument_type(kind: str) -> InstrumentType:
    if kind == "equity":
        return InstrumentType.EQUITY
    if kind == "crypto_perp":
        return InstrumentType.PERPETUAL
    if kind == "crypto_spot":
        return InstrumentType.SPOT
    return InstrumentType.EVENT_CONTRACT


def _instrument(symbol: str, venue: str, kind: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        venue=_venue(venue),
        instrument_type=_instrument_type(kind),
    )


def _provenance_rows(surfaces: dict[str, object], updated_at: datetime) -> dict[str, object]:
    """Every surface gets the uniform provenance shape."""
    labeled: dict[str, object] = {}
    for name, rows in surfaces.items():
        labeled[name] = {
            "source": "demo",
            "synthetic": True,
            "updated_at": updated_at.isoformat(),
            "rows": rows,
        }
    return labeled


def _seed_market_data(
    scenario: DemoScenario,
    draw: generators._Draw,
    root: Path,
    series: dict[str, dict[str, list[float]]],
) -> tuple[dict[str, int], DemoProviders, Path]:
    """Per-symbol fixture files the real venue providers parse, plus the
    demo lake the research registries pin against.

    One fixture directory per symbol (``market/fixtures/<venue>/<symbol>/``)
    holding the exact wire file names the adapters load; one real
    provider per symbol serves it. The provenance keys name the symbol
    and file, e.g. ``market:moomoo:AAPL:moomoo_bars.json``. ``series``
    is the single walk the caller's marks derive from — the fixture
    closes must be the same walk (see ``generators.fixture_files``).
    """
    fixture_root = root / "market" / "fixtures"
    files = generators.fixture_files(draw, scenario, series=series)
    rows: dict[str, int] = {}
    providers: dict[tuple[str, str], MoomooFixtureProvider | HyperliquidFixtureProvider] = {}
    for (venue, symbol), symbol_files in files.items():
        symbol_dir = fixture_root / venue / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        for name, file_rows in symbol_files.items():
            (symbol_dir / name).write_text(json.dumps(file_rows, indent=1), encoding="utf-8")
            rows[f"market:{venue}:{symbol}:{name}"] = len(file_rows)
        provider: MoomooFixtureProvider | HyperliquidFixtureProvider = (
            MoomooFixtureProvider(fixture_dir=symbol_dir)
            if venue == "moomoo"
            else HyperliquidFixtureProvider(fixture_dir=symbol_dir)
        )
        providers[(venue, symbol)] = provider
    kinds = {
        (spec.venue, spec.symbol): spec.kind for spec in (*scenario.equities, *scenario.crypto)
    }
    return rows, DemoProviders(providers, kinds), fixture_root


def _seed_lake(
    scenario: DemoScenario, series: dict[str, dict[str, list[float]]], root: Path
) -> tuple[Path, dict[str, int]]:
    """One dataset per symbol: real shards + a manifest whose ``source``
    label is ``demo-synthetic`` (the lake's own provenance field)."""
    lake_root = root / "market" / "lake"
    lake = Lake(lake_root)
    times = generators.session_times(scenario)
    # One deterministic manifest stamp for the whole bulk seed: after the
    # last seeded session, before the paper replay (the timeline the UI
    # renders reads oldest-first across surfaces).
    generated_at = scenario.anchor - timedelta(minutes=5)
    datasets: dict[str, int] = {}
    for spec in (*scenario.equities, *scenario.crypto):
        closes = series[spec.venue][spec.symbol]
        bars = [
            Bar(
                instrument=_instrument(spec.symbol, spec.venue, spec.kind),
                timestamp=time,
                interval="1d",
                open=closes[index] * 0.998,
                high=closes[index] * 1.004,
                low=closes[index] * 0.996,
                close=closes[index],
                volume=1_000_000.0,
            )
            for index, time in enumerate(times)
        ]
        dataset = f"demo-{spec.venue}-{spec.symbol.lower()}"
        lake.write_bars(dataset, bars)
        ManifestWriter(lake_root).generate(
            dataset,
            source="demo-synthetic",
            license="QuantMesh deterministic demo",
            generated_at=generated_at,
        )
        datasets[dataset] = len(bars)
    return lake_root, datasets


def _seed_account(
    scenario: DemoScenario, series: dict[str, dict[str, list[float]]], draw: generators._Draw
) -> tuple[PaperAccount, dict[str, float], dict[str, dict[str, float]], list[dict]]:
    """Replay the deterministic order sequence through real submits.

    Quotes derive from the same series the fixtures serve; order i is
    timestamped ``anchor - (n - i) * 5min`` so the whole replay sits
    inside the matcher's quote-age window and the timestamps are
    reproducible.
    """
    account = PaperAccount(
        cash=100_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    # The full universe board: every seeded symbol carries a mark from
    # the same walk the fixtures serve, not only the traded ones. The
    # mark rounds like the fixture rows (2dp), so the board, the
    # providers' series and the P&L numbers agree exactly.
    marks = {
        f"{_venue(venue).value}:{symbol}": round(closes[-1], 2)
        for venue, symbols in series.items()
        for symbol, closes in symbols.items()
    }
    markets = {
        venue: {symbol: round(closes[-1], 2) for symbol, closes in symbols.items()}
        for venue, symbols in series.items()
    }
    quotes: list[dict] = []
    for index, (venue, symbol, side, quantity, limit_price) in enumerate(ORDER_SEQUENCE):
        kind = next(
            spec.kind
            for spec in (*scenario.equities, *scenario.crypto)
            if spec.venue == venue and spec.symbol == symbol
        )
        close = series[venue][symbol][-1]
        quote_time = scenario.anchor - timedelta(minutes=5 * (len(ORDER_SEQUENCE) - index))
        spread = close * 0.002
        quote = Quote(
            instrument=_instrument(symbol, venue, kind),
            timestamp=quote_time,
            bid=round(close - spread, 4),
            ask=round(close + spread, 4),
            last=round(close, 4),
            volume=1_000.0,
        )
        request = OrderRequest(
            instrument=quote.instrument,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
        )
        result = account.submit(request, quote, now=quote_time)
        account = result.account
        quotes.append(
            {
                "symbol": symbol,
                "side": side.value,
                "quantity": quantity,
                "limit_price": limit_price,
                "fill": result.rejection is None,
            }
        )
    return account, marks, markets, quotes


def _seed_research(
    scenario: DemoScenario,
    draw: generators._Draw,
    root: Path,
    lake_root: Path,
    series: dict[str, dict[str, list[float]]],
) -> dict[str, int]:
    """Experiments and strategy reports, pinned to the demo lake."""
    datasets = list(
        sorted(
            f"demo-{spec.venue}-{spec.symbol.lower()}"
            for spec in (*scenario.equities, *scenario.crypto)
        )
    )
    experiments = ExperimentRegistry(root=root / "research" / "experiments", lake_root=lake_root)
    for index in range(scenario.surface_counts["experiments"]):
        dataset = datasets[index % len(datasets)]
        parameters = {
            "window": 3 + draw.index(5),
            "entry": draw.choice(("close", "open")),
            "vol_filter": draw.index(2) == 0,
        }
        metrics = {
            "oos_mae": round(draw.uniform(0.2, 2.0), 4),
            "oos_rmse": round(draw.uniform(0.3, 3.0), 4),
            "n_windows": 1 + draw.index(3),
        }
        experiments.record(
            dataset=dataset,
            revision=1,
            commit=DEMO_COMMIT,
            parameters=parameters,
            metrics=metrics,
            # Earliest research surface: 8h..48h before anchor, before
            # the reports/promotions/alerts/decisions the UI reads later.
            created_at=scenario.anchor - timedelta(hours=8 * (index + 1)),
        )

    reports = ReportRegistry(root=root / "research" / "reports", lake_root=lake_root)
    strategies = ("momentum", "mean_reversion", "book_imbalance", "lightgbm")
    intervals = ("1d", "1d", "1d", "1d")
    universe_specs = (
        (scenario.equities,),
        (scenario.equities,),
        (scenario.crypto,),
        (scenario.crypto,),
    )
    for index, (strategy, interval, specs) in enumerate(zip(strategies, intervals, universe_specs)):
        universe = [
            UniverseMember(venue=_venue(spec.venue), symbol=spec.symbol) for spec in specs[0]
        ]
        window_spec = WalkForwardSpec(train_bars=3, test_bars=1, step_bars=1)
        costs = CostModel(fee_bps=10, half_spread_bps=5, slippage_bps=0)
        dataset = datasets[index % len(datasets)]
        report = StrategyReport(
            id=report_id(
                dataset=dataset,
                revision=1,
                commit=DEMO_COMMIT,
                strategy=strategy,
                interval=interval,
                universe=universe,
                window_spec=window_spec,
                costs=costs,
            ),
            dataset=dataset,
            revision=1,
            commit=DEMO_COMMIT,
            strategy=strategy,
            interval=interval,
            universe=universe,
            window_spec=window_spec,
            costs=costs,
            created_at=scenario.anchor - timedelta(hours=index + 1),
            metrics={
                "total_return": round(draw.normal() * 0.03, 4),
                "sharpe": round(draw.uniform(0.2, 2.4), 3),
                "max_drawdown": round(-draw.uniform(0.01, 0.08), 4),
            },
            evidence={
                "oos_return": round(draw.normal() * 0.02, 4),
                "n_trades": 10 + draw.index(40),
            },
            windows=[
                WindowResult(
                    index=0,
                    train_end=scenario.anchor - timedelta(days=2),
                    test_start=scenario.anchor - timedelta(days=1),
                    test_end=scenario.anchor,
                    window_return=round(draw.normal() * 0.02, 4),
                    turnover=round(draw.uniform(0.2, 0.9), 3),
                    cost=round(draw.uniform(0.001, 0.01), 5),
                    n_trades=1 + draw.index(6),
                )
            ],
        )
        reports.record(report)
    return {
        "experiments": scenario.surface_counts["experiments"],
        "reports": len(strategies),
    }


def _seed_forecasts(scenario: DemoScenario, draw: generators._Draw, root: Path) -> dict[str, int]:
    """Forecast reports over the prediction-market universe, through
    the real evaluation pipeline.

    The records are built manually (instead of ``run_forecast_report``)
    only so ``created_at`` derives from the scenario anchor: the
    pipeline's wall-clock stamp would break the byte-for-byte replay
    guarantee. Evaluation and artifacts are the real pipeline. The
    report count is the manifest contract; each report varies ``n_bins``
    so its content-addressed id is distinct.
    """
    registry = ForecastReportRegistry(root=root / "research" / "reports")
    markets: list[ForecastMarket] = []
    for venue, ticker, title, kind, base in scenario.prediction:
        rule_text = f"Resolved by the venue's official adjudication of: {title}"
        event = EventMarket(
            venue=EventVenue(venue),
            venue_market_id=ticker,
            event_ticker=ticker,
            title=title,
            category="Policy" if venue == "kalshi" else "Sports",
            start_at=scenario.open,
            expiry_at=scenario.anchor + timedelta(days=180),
            outcomes=[
                Outcome(name="Yes", venue_outcome_id="yes"),
                Outcome(name="No", venue_outcome_id="no"),
            ],
            resolution_rule=ResolutionRule.of(rule_text),
        )
        observations: list[ForecastObservation] = []
        probability = base
        for index in range(8):
            probability = min(0.95, max(0.05, probability + draw.normal() * 0.02))
            observations.append(
                ForecastObservation(
                    timestamp=scenario.anchor - timedelta(hours=8 - index),
                    probability=round(probability, 4),
                    liquidity_confidence=round(draw.uniform(0.4, 0.9), 3),
                )
            )
        markets.append(ForecastMarket(market=event, observations=observations))
    window_spec = ForecastWindowSpec(train_observations=5, test_observations=2, step_observations=2)
    universe = [entry.market for entry in markets]
    reports: list[ForecastReport] = []
    for index, n_bins in enumerate((4, 5, 3, 6)):
        metrics, per_market = run_forecast(markets, window_spec=window_spec, n_bins=n_bins)
        report = ForecastReport(
            id=forecast_report_id(
                commit=DEMO_COMMIT, universe=universe, window_spec=window_spec, n_bins=n_bins
            ),
            commit=DEMO_COMMIT,
            universe=universe,
            window_spec=window_spec,
            n_bins=n_bins,
            created_at=scenario.anchor - timedelta(hours=2 + index),
            metrics=metrics,
            markets=per_market,
        )
        _write_artifacts(registry.root, report)
        registry.record(report)
        reports.append(report)
    return {"forecasts": len(reports)}


def _seed_ledgers(
    scenario: DemoScenario,
    draw: generators._Draw,
    root: Path,
    report_ids: list[str],
    experiment_ids: list[str],
) -> dict[str, int]:
    """Promotions, alerts, mappings, decisions, documents — every ledger
    through its public append API, every id content-addressed."""
    promotions = PromotionLedger(root=root / "research" / "promotions")
    signal_names = ("momentum_equity_demo", "book_imbalance_crypto_demo", "lightgbm_equity_demo")
    for index, name in enumerate(signal_names):
        promote_signal(
            signal_name=name,
            evidence=PromotionEvidence(
                benchmark_ids=sorted(report_ids[:2]),
                ablation_ids=[report_ids[index % len(report_ids)]],
                oos_report_id=report_ids[(index + 1) % len(report_ids)],
            ),
            ledger=promotions,
            promoted_at=scenario.anchor - timedelta(hours=3 * (index + 1)),
        )

    alerts = AlertLedger(root=root / "alerts")
    alert_specs = (
        ("feature_drift", "demo:equity-features", "equity feature drift over the demo window"),
        (
            "prediction_drift",
            "demo:crypto-signals",
            "crypto signal distribution moved outside tolerance",
        ),
        (
            "staleness",
            "demo:market-board",
            "demo fixture feed reports no new sessions since anchor",
        ),
        ("failure", "demo:provider-probe", "a demo venue provider probe rejected a request"),
        (
            "reliability_limit",
            "demo:paper-matcher",
            "paper fills reached the seeded reliability limit",
        ),
    )
    for index, (kind, source, message) in enumerate(alert_specs):
        detected_at = scenario.anchor - timedelta(hours=2 * (index + 1))
        observed = {"value": round(draw.uniform(0.0, 1.0), 3)}
        alerts.record(
            AlertRecord(
                id=alert_id(kind=kind, source=source, detected_at=detected_at, observed=observed),
                kind=kind,
                source=source,
                detected_at=detected_at,
                message=message,
                observed=observed,
            )
        )

    mappings = MappingLedger(root=root / "mappings")
    pair_specs = (
        (
            "poly-fed-1",
            "kalshi-fed-1",
            MappingStatus.MATCHED,
            (
                ("title", "identical wording"),
                ("outcome_set", "Yes/No matches"),
            ),
        ),
        (
            "poly-fed-2",
            "kalshi-fed-2",
            MappingStatus.PENDING,
            (("title", "candidate wording"),),
        ),
        (
            "poly-fed-3",
            "kalshi-fed-3",
            MappingStatus.AMBIGUOUS,
            (
                ("title", "overlapping wording"),
                ("expiry", "expiry window overlaps"),
            ),
        ),
    )
    report = EventMappingReport(
        pairs=[
            EventPairing(
                pair_key=pair_key(poly, kalshi),
                polymarket_market_id=poly,
                kalshi_market_id=kalshi,
                status=status,
                evidence=sorted(
                    (
                        MappingEvidence(kind=EvidenceKind(kind), detail=detail)
                        for kind, detail in evidence
                    ),
                    key=lambda item: (item.kind.value, item.detail),
                ),
            )
            for poly, kalshi, status, evidence in pair_specs
        ]
    )
    mappings.record(
        report,
        commit=DEMO_COMMIT,
        recorded_at=scenario.anchor - timedelta(days=3),
    )

    decisions = DecisionLog(root=root / "decisions")
    # Content-addressed run ids: `hash()` is per-process randomized
    # (PYTHONHASHSEED), which would break the replay guarantee.
    run_ids = [
        hashlib.sha256(f"demo-run-{index}".encode()).hexdigest()[:16]
        for index in range(scenario.surface_counts["decisions"])
    ]

    class _VerdictOutput(BaseModel):
        verdict: str

    roles = ("analyst", "critic", "risk", "portfolio")
    for index, role in enumerate(roles):
        # Document ids are deterministic by construction (kind + order).
        document_id = (
            f"demo-{tuple(_DOCUMENT_TEXT)[index % len(_DOCUMENT_TEXT)]}-"
            f"{index % len(_DOCUMENT_TEXT) + 1}"
        )
        decisions.record(
            DecisionRecord.for_stage(
                run_id=run_ids[index],
                role=role,
                model=ModelMeta(name="demo-seeder", version="0.1.0", endpoint_kind="loopback"),
                prompt=f"Seeded {role} stage over the deterministic demo scenario (redacted).",
                schema_id="demo/verdict.v1",
                output=_VerdictOutput(verdict="pass" if role in ("critic", "risk") else "neutral"),
                citations=[
                    Citation(
                        source_kind="document",
                        source_id=document_id,
                        span=(0, 24),
                    ),
                    Citation(
                        source_kind="experiment",
                        source_id=experiment_ids[index % len(experiment_ids)],
                    ),
                ],
                recorded_at=scenario.anchor - timedelta(hours=index + 4),
            )
        )

    documents = DocumentIndex(root=root / "documents")
    source_dir = root / "documents" / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    for index, (kind, _template) in enumerate(_DOCUMENT_TEXT.items()):
        doc_id = f"demo-{kind}-{index + 1}"
        content = _DOCUMENT_TEXT[kind].format(", ".join(spec.symbol for spec in scenario.equities))
        path = source_dir / f"{doc_id}.txt"
        path.write_text(content, encoding="utf-8")
        # Before the decisions that cite them (4h..7h before anchor).
        # The relative reference is read against — and stored relative
        # to — the registry root, so the ledger bytes are the same in
        # any demo root (portable, byte-reproducible records).
        documents.ingest_file(
            Path("sources") / f"{doc_id}.txt",
            kind=kind,
            doc_id=doc_id,
            ingested_at=scenario.anchor - timedelta(hours=12 + 2 * index),
        )

    return {
        "promotions": len(signal_names),
        "alerts": len(alert_specs),
        "mappings": len(pair_specs),
        "decisions": len(roles),
        "documents": len(_DOCUMENT_TEXT),
    }


def seed_demo_root(root: Path, scenario: DemoScenario = DemoScenario()) -> DemoSeeded:
    """Seed one complete demo root, failing closed on a re-seed.

    A root that already carries the marker is refused — re-seeding is
    an explicit reset (``reset_demo_root``), never a silent overwrite.
    """
    root = Path(root)
    if is_demo_root(root):
        raise DemoRootError(
            f"demo root {root} is already seeded — use reset_demo_root "
            "(re-seeding is explicit, never silent)"
        )
    root.mkdir(parents=True, exist_ok=True)
    _marker(root).write_text(
        "deterministic demo root — reset deletes only this tree\n", encoding="utf-8"
    )

    draw = generators._Draw(scenario.seed)
    series = generators.series_map(draw, scenario)

    fixture_rows, providers, _fixture_dir = _seed_market_data(scenario, draw, root, series)
    lake_root, dataset_rows = _seed_lake(scenario, series, root)
    account, marks, markets, order_quotes = _seed_account(scenario, series, draw)

    research_rows = _seed_research(scenario, draw, root, lake_root, series)
    forecast_rows = _seed_forecasts(scenario, draw, root)

    experiments = ExperimentRegistry(root=root / "research" / "experiments", lake_root=lake_root)
    reports = ReportRegistry(root=root / "research" / "reports", lake_root=lake_root)
    report_ids = [report.id for report in reports.all()]
    experiment_ids = [experiment.id for experiment in experiments.all()]
    forecasts = ForecastReportRegistry(root=root / "research" / "reports")

    # Documents must exist before decisions cite them.
    ledger_rows = _seed_ledgers(
        scenario, draw, root, report_ids=report_ids, experiment_ids=experiment_ids
    )

    # The paper journal snapshots the replayed orders (the audit trail).
    journal = OrderJournal(root=root / "orders")
    for order in account.orders.values():
        journal.record(order)

    watchlist = WatchlistStore(root=root / "watchlists")
    for symbol in ("BTC-USD", "AAPL", "NVDA", "SOL-USD"):
        watchlist.add(symbol, now=scenario.anchor - timedelta(hours=1))

    enablement = ApprovalLedger(root=root / "enablement")
    enablement.request(
        Venue.MOOMOO,
        actor="demo-operator",
        acted_at=scenario.anchor - timedelta(days=2),
    )
    enablement.request(
        Venue.HYPERLIQUID,
        actor="demo-operator",
        acted_at=scenario.anchor - timedelta(days=2),
    )
    enablement.withdraw(
        Venue.HYPERLIQUID,
        actor="demo-operator",
        acted_at=scenario.anchor - timedelta(days=1),
    )

    rows = {
        **fixture_rows,  # keys already carry the market: provenance prefix
        **{f"lake:{name}": count for name, count in dataset_rows.items()},
        "orders": len(order_quotes),
        **research_rows,
        **forecast_rows,
        **ledger_rows,
    }
    provenance = {
        "scenario": {
            "seed": scenario.seed,
            "anchor": scenario.anchor.isoformat(),
            "open": scenario.open.isoformat(),
            "commit": DEMO_COMMIT,
        },
        "surfaces": _provenance_rows(rows, scenario.anchor),
    }
    (root / "provenance.json").write_text(json.dumps(provenance, indent=1), encoding="utf-8")
    (root / "account.json").write_text(account.model_dump_json(), encoding="utf-8")

    return DemoSeeded(
        root=root,
        scenario=scenario,
        account=account,
        marks=marks,
        markets=markets,
        watchlist=watchlist,
        experiments=experiments,
        promotions=PromotionLedger(root=root / "research" / "promotions"),
        reports=reports,
        forecasts=forecasts,
        alerts=AlertLedger(root=root / "alerts"),
        journal=journal,
        mappings=MappingLedger(root=root / "mappings"),
        decisions=DecisionLog(root=root / "decisions"),
        documents=DocumentIndex(root=root / "documents"),
        enablement=enablement,
        providers=providers,
        provenance=provenance,
    )


def load_demo_root(root: Path, scenario: DemoScenario = DemoScenario()) -> DemoSeeded:
    """Rebuild the in-memory assembly from an existing demo root.

    The ledgers read their files lazily; the account comes from the
    persisted snapshot; marks/markets are re-derived from the same
    deterministic walk (identical by construction). Nothing is
    rewritten — a restart is a read, not a re-seed.
    """
    root = Path(root)
    if not is_demo_root(root):
        raise DemoRootError(
            f"{root} is not a demo root — it has no {MARKER_NAME} marker; "
            "reset and re-seed never touch a root that lacks it"
        )
    scenario = _load_scenario(root, scenario)
    draw = generators._Draw(scenario.seed)
    series = generators.series_map(draw, scenario)
    fixture_root = root / "market" / "fixtures"
    providers = DemoProviders(
        {
            (spec.venue, spec.symbol): (
                MoomooFixtureProvider(fixture_dir=fixture_root / spec.venue / spec.symbol)
                if spec.kind == "equity"
                else HyperliquidFixtureProvider(fixture_dir=fixture_root / spec.venue / spec.symbol)
            )
            for spec in (*scenario.equities, *scenario.crypto)
        },
        {(spec.venue, spec.symbol): spec.kind for spec in (*scenario.equities, *scenario.crypto)},
    )
    account = PaperAccount.model_validate_json((root / "account.json").read_text(encoding="utf-8"))
    marks = {
        f"{_venue(venue).value}:{symbol}": round(closes[-1], 2)
        for venue, symbols in series.items()
        for symbol, closes in symbols.items()
    }
    markets = {
        venue: {symbol: round(closes[-1], 2) for symbol, closes in symbols.items()}
        for venue, symbols in series.items()
    }
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    return DemoSeeded(
        root=root,
        scenario=scenario,
        account=account,
        marks=marks,
        markets=markets,
        watchlist=WatchlistStore(root=root / "watchlists"),
        experiments=ExperimentRegistry(
            root=root / "research" / "experiments", lake_root=root / "market" / "lake"
        ),
        promotions=PromotionLedger(root=root / "research" / "promotions"),
        reports=ReportRegistry(
            root=root / "research" / "reports", lake_root=root / "market" / "lake"
        ),
        forecasts=ForecastReportRegistry(root=root / "research" / "reports"),
        alerts=AlertLedger(root=root / "alerts"),
        journal=OrderJournal(root=root / "orders"),
        mappings=MappingLedger(root=root / "mappings"),
        decisions=DecisionLog(root=root / "decisions"),
        documents=DocumentIndex(root=root / "documents"),
        enablement=ApprovalLedger(root=root / "enablement"),
        providers=providers,
        provenance=provenance,
    )


def _load_scenario(root: Path, default: DemoScenario) -> DemoScenario:
    """Reconstruct the scenario the root was seeded with, so a restart
    with a different default never misreads a mismatched root."""
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    scenario = provenance.get("scenario", {})
    return DemoScenario(
        seed=int(scenario.get("seed", default.seed)),
        anchor=datetime.fromisoformat(scenario["anchor"]),
        open=datetime.fromisoformat(scenario["open"]),
    )


def reset_demo_root(root: Path, scenario: DemoScenario = DemoScenario()) -> DemoSeeded:
    """Wipe and re-seed a demo root, marker-guarded.

    The marker is the isolation contract: without it the root is not a
    demo root and reset refuses to touch it — a non-demo directory can
    never be wiped by the demo runtime.
    """
    root = Path(root)
    if not is_demo_root(root):
        raise DemoRootError(
            f"refusing to reset {root}: no {MARKER_NAME} marker — "
            "the demo runtime never touches a non-demo root"
        )
    shutil.rmtree(root)
    return seed_demo_root(root, scenario)
