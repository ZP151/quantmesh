# Integrated Instrument Decision Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reproducibly decide the FinRL-X and NautilusTrader integration boundaries, then ship one venue-aware NVDA-to-paper decision workspace as `v0.1.1-rc1` without weakening QuantMesh safety authority.

**Architecture:** Frameworks run only in pinned subprocess environments and emit a small QuantMesh-owned JSON evidence contract. Product runtime remains FastAPI plus React; owned historical, forecast, proposal, and workspace services compose existing lake, live-feed, registry, paper-account, risk, and audit contracts. The SPA uses a single venue-aware route and a locally wrapped Lightweight Charts dependency, while all orders still cross the existing quote fence, deterministic risk gate, kill switches, matcher, and journal.

**Tech Stack:** Python 3.13, Pydantic, FastAPI, DuckDB/Parquet, pandas/numpy/scikit-learn, React 19, TypeScript 5.9.3, Vite 8, TanStack Query, shadcn/ui, Tailwind 4, Lightweight Charts 5.2.0, Vitest, Playwright, Ruff, pytest.

## Global Constraints

- Work only on `0020-research-to-paper-loop`, based on released `v0.1.0` at `5a7f660`, and deliver one final PR linked to issue #107.
- Pin FinRL-X to `e65d6f0483ead7d2ef4a5fc940cdf960392a25c1` and NautilusTrader to stable `v1.231.0` / commit `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`.
- Framework checkouts, wheels, virtual environments, and generated evidence live outside the package and never enter the release dependency closure before ADR approval.
- Every behavior change follows red, green, refactor; record the failing and passing command in the task report and iteration ledger.
- Every task receives a fresh implementer and fresh reviewer. Resolve all Critical and Important findings before the next task.
- All external venues remain read-only or paper-only. No credentials, mainnet signing, real-money order, autonomous AI order, or synthetic-as-live output.
- A forecast is a dated distribution, not a promise. Every path carries dataset/model lineage, vintage, chronological OOS metrics, uncertainty, benchmark, limitations, and a promotion gate.
- The deterministic paper kernel, quote fence, stale/gap checks, global/per-venue kill switches, risk rules, matcher, journal, and audit trail are the only order authority.
- The canonical SPA route is `/app/instruments/:venue/:symbol`; `/app/cockpit/:symbol` remains a compatibility route until acceptance.
- UI direction is an established product extension: shadcn/Tailwind/Geist, black/green dark-technical identity, `DESIGN_VARIANCE 3`, `MOTION_INTENSITY 2`, `VISUAL_DENSITY 8`; state motion only, no decorative choreography or nested card grids.
- Every UI value exposes venue, source, timestamp, freshness, and synthetic/real classification. Loading, empty, unavailable, stale, gap, error, and partial-evidence states are first-class.
- English is primary; every new visible string has a Simplified-Chinese translation. Keep keyboard use, visible focus, reduced motion, WCAG 2.2 AA, and 390 px no-overflow coverage.
- Commit each green task, push each durable checkpoint, and synchronize this plan, `docs/iterations/0020-research-to-paper-loop.md`, and `docs/goals/ACTIVE.md` at every phase boundary.

## File Structure

- `src/quantmesh/research/frameworks.py`: framework-neutral evidence and scorecard models; no imports from candidate frameworks.
- `tools/framework_bakeoff/`: pinned fixture export, isolated environment orchestration, FinRL-X driver, Nautilus driver, scorecard command, and pin file.
- `src/quantmesh/instruments/contracts.py`: venue-aware historical, comparison, forecast, proposal, and workspace response models.
- `src/quantmesh/instruments/history.py`: manifest-gated multi-resolution history and normalized comparison service.
- `src/quantmesh/instruments/forecast.py`: deterministic chronological price-path baselines, OOS evidence, artifact writer, and registry.
- `src/quantmesh/instruments/proposals.py`: append-only proposal lineage and operator-confirmed paper execution service.
- `src/quantmesh/instruments/workspace.py`: read-side BFF composing history, live, forecast, portfolio, risk, and proposal context.
- `src/quantmesh/instruments/api.py`: `/api/instruments/*` and `/api/paper/proposals/*` routes only; no venue SDK calls.
- `frontend/src/components/charts/InstrumentChart.tsx`: the only Lightweight Charts adapter.
- `frontend/src/screens/InstrumentWorkspace.tsx`: integrated operator surface; leaf components live beside it under `frontend/src/screens/instrument/`.
- `docs/adr/0015-framework-boundaries-and-instrument-workspace.md`: scored adoption/rejection decision and runtime boundaries.
- `docs/evidence/0020/`: checked-in small JSON scorecard, command transcript, dependency/license summary, and hashes; no external framework source or environment.

---

### Task 1: Framework evidence contract and deterministic NVDA manifest

**Files:**
- Create: `src/quantmesh/research/frameworks.py`
- Create: `tools/framework_bakeoff/__init__.py`
- Create: `tools/framework_bakeoff/pins.json`
- Create: `tools/framework_bakeoff/fixture.py`
- Test: `tests/test_framework_bakeoff_contract.py`

**Interfaces:**
- Consumes: `Lake.write_bars(dataset, bars)`, `ManifestWriter.generate(...)`, `Dataset.read_bars(interval, venue, symbol)`.
- Produces: `FrameworkRunEvidence`, `FrameworkScore`, `load_pins(path)`, and `build_nvda_fixture(root, sessions=420) -> DatasetManifest`.

- [x] **Step 1: Write the failing contract and fixture tests**

```python
def test_nvda_fixture_is_manifest_gated_and_byte_reproducible(tmp_path):
    left = build_nvda_fixture(tmp_path / "left")
    right = build_nvda_fixture(tmp_path / "right")
    assert left.coverage[0].rows == 420
    assert left.model_dump(mode="json", exclude={"generated_at"}) == right.model_dump(
        mode="json", exclude={"generated_at"}
    )

def test_framework_evidence_rejects_an_unpinned_or_nondeterministic_pass():
    with pytest.raises(ValueError, match="passing run requires"):
        FrameworkRunEvidence(
            framework="finrl-x", revision="", status="passed",
            deterministic=False, input_digest="0" * 64, output_digest="1" * 64,
            duration_seconds=1.0, peak_rss_mb=1.0, environment_bytes=1,
            checks={}, artifacts={},
        )
```

- [x] **Step 2: Run the tests and capture the red result**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_framework_bakeoff_contract.py --basetemp .pytest-0020-task1`

Expected: collection fails because `quantmesh.research.frameworks` and `tools.framework_bakeoff.fixture` do not exist.

- [x] **Step 3: Implement the owned evidence types**

```python
class FrameworkRunEvidence(BaseModel):
    schema_version: Literal[1] = 1
    framework: Literal["finrl-x", "nautilus-trader"]
    revision: str = Field(min_length=7)
    status: Literal["passed", "failed"]
    deterministic: bool
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duration_seconds: float = Field(ge=0)
    peak_rss_mb: float = Field(ge=0)
    environment_bytes: int = Field(ge=0)
    checks: dict[str, bool]
    artifacts: dict[str, str]
    score_inputs: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def passed_runs_are_complete(self) -> "FrameworkRunEvidence":
        required = {"windows_install", "chronological_split", "no_leakage", "license"}
        if self.status == "passed" and (
            not self.deterministic
            or self.output_digest is None
            or not required.issubset(self.checks)
            or not all(self.checks[name] for name in required)
        ):
            raise ValueError("passing run requires deterministic output and all mandatory checks")
        if any(not math.isfinite(value) or not 0 <= value <= 100 for value in self.score_inputs.values()):
            raise ValueError("score inputs must be finite values between 0 and 100")
        return self

class FrameworkScore(BaseModel):
    schema_version: Literal[1] = 1
    framework: Literal["finrl-x", "nautilus-trader"]
    revision: str = Field(min_length=7)
    hard_gates: dict[str, bool]
    soft_scores: dict[str, float]
    total: float = Field(ge=0, le=100)
    runtime_admissible: bool
    disposition: Literal["adopt-adapter", "isolated-comparator", "reject"]
    limitations: list[str] = Field(default_factory=list)
```

- [x] **Step 4: Implement the synthetic-but-labeled NVDA lake fixture**

Generate 420 Monday-Friday UTC sessions from a fixed `2025-01-02T21:00:00Z` anchor. Use a deterministic close formula `120 * exp(0.0004*i + 0.018*sin(2*pi*i/21))`, derive OHLC and integer-like volume, write dataset `bakeoff-moomoo-nvda`, and generate a manifest with source `quantmesh-deterministic-bakeoff`, license `QuantMesh synthetic test data`, and fixed `generated_at`.

- [x] **Step 5: Add exact upstream pins**

`load_pins(path)` returns a typed mapping and rejects mutable or malformed
metadata: each repository must be an HTTPS GitHub URL, every revision exactly
40 lowercase hexadecimal characters, every license nonblank, and an optional
tag nonblank. Add focused positive and negative tests.

```json
{
  "finrl-x": {
    "repository": "https://github.com/AI4Finance-Foundation/FinRL-Trading.git",
    "revision": "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1",
    "license": "Apache-2.0"
  },
  "nautilus-trader": {
    "repository": "https://github.com/nautechsystems/nautilus_trader.git",
    "tag": "v1.231.0",
    "revision": "27a8e54e7ac3c57d6cbf8891f0283dfbaee97317",
    "license": "LGPL-3.0"
  }
}
```

- [x] **Step 6: Run green verification and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_framework_bakeoff_contract.py --basetemp .pytest-0020-task1`

Run: `.\.venv\Scripts\ruff.exe check src tests tools`

Commit: `git commit -am "test: define framework bakeoff evidence contract (#107)"` after staging the new files.

### Task 2: Pinned isolated FinRL-X NVDA workflow

**Files:**
- Create: `tools/framework_bakeoff/process.py`
- Create: `tools/framework_bakeoff/finrl_driver.py`
- Create: `tools/framework_bakeoff/finrl_x.py`
- Create: `tools/framework_bakeoff/run.py`
- Test: `tests/test_finrl_x_bakeoff.py`
- Evidence: `docs/evidence/0020/finrl-x-run.json`

**Interfaces:**
- Consumes: Task 1 manifest and `FrameworkRunEvidence`; pinned FinRL-X `BaseStrategy`, `StrategyResult`, `BacktestConfig`, and `BacktestEngine` in a child process.
- Produces: `run_finrl_x(lake_root, work_root) -> FrameworkRunEvidence` and canonical `weights.csv`, `backtest.json`, `proposal.json` artifacts.

- [x] **Step 1: Write subprocess-boundary tests**

```python
def test_finrl_driver_emits_target_weights_costs_and_paper_proposal(tmp_path):
    manifest = build_nvda_fixture(tmp_path / "lake")
    result = run_finrl_x(tmp_path / "lake", tmp_path / "work", runner=fake_finrl_runner)
    assert result.revision == FINRL_PIN
    assert result.checks["chronological_split"]
    assert result.checks["no_leakage"]
    proposal = json.loads(Path(result.artifacts["proposal"]).read_text())
    assert proposal == {"venue": "moomoo", "symbol": "NVDA", "target_weight": 1.0, "paper": True}
    assert manifest.dataset == "bakeoff-moomoo-nvda"
```

- [x] **Step 2: Run the focused test and verify the missing runner fails**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_finrl_x_bakeoff.py --basetemp .pytest-0020-task2`

Expected: FAIL because `run_finrl_x` is undefined.

- [x] **Step 3: Implement deterministic dataset export and driver input**

Export manifest-validated NVDA bars to `input.csv` with exact columns `date,datadate,tic,open,high,low,close,adj_close,volume,cshtrd`. Write `driver-config.json` with train `[0,252)`, validation `[252,315)`, test `[315,420)`, fee `10 bps`, half-spread `5 bps`, slippage `2 bps`, and seed `20260811`.

- [x] **Step 4: Implement the FinRL-X driver in the isolated checkout**

```python
class NvdaTimingStrategy(BaseStrategy):
    def generate_weights(self, data, target_date=None):
        close = data["prices"]["NVDA"]
        fast = close.rolling(20).mean()
        slow = close.rolling(60).mean()
        weights = (fast > slow).astype(float).to_frame("NVDA")
        return StrategyResult("nvda_timing", weights.fillna(0.0))

config = BacktestConfig(
    start_date=str(prices.index.min().date()),
    end_date=str(prices.index.max().date()),
    transaction_cost=0.0017,
    benchmark_tickers=[],
    integer_positions=False,
)
result = BacktestEngine(config).run_backtest("nvda_timing", prices, weights)
```

The driver must fit/generate weights only through index 314, evaluate only 315-419, write sorted-key compact JSON, and derive the proposal from the last target weight. It must never import Alpaca or call a data provider.

- [x] **Step 5: Implement isolated environment orchestration**

Clone at the exact commit, create a Python 3.13 venv, install the checkout with `--no-deps`, install only the imports exercised by the driver (`numpy`, `pandas`, `scipy`, `matplotlib`, `bt`, `ffn`, `scikit-learn`, `requests`, `python-dotenv`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `yfinance`), assert `git rev-parse HEAD`, run the driver twice into separate output roots, and compare canonical output digests. Record installation bytes, elapsed seconds, `pip freeze`, `pip check`, and the upstream LICENSE hash.

- [x] **Step 6: Run the real Windows bake-off twice**

Run: `.\.venv\Scripts\python.exe -m tools.framework_bakeoff.run finrl-x --lake-root artifacts\0020\finrl-lake --work-root artifacts\0020\finrl-work`

Expected: exit 0 only when the two output digests match and all mandatory checks pass. If installation or execution fails, write a `status="failed"` evidence file with the exact failing command and limitation; do not weaken the schema.

- [x] **Step 7: Verify, record, and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_framework_bakeoff_contract.py tests/test_finrl_x_bakeoff.py --basetemp .pytest-0020-task2-green`

Run: `.\.venv\Scripts\ruff.exe check src tests tools`

Commit: `git commit -m "research: run pinned FinRL-X NVDA bakeoff (#107)"`.

### Task 3: Pinned NautilusTrader Hyperliquid replay and sandbox comparator

**Files:**
- Create: `tools/framework_bakeoff/nautilus_driver.py`
- Create: `tools/framework_bakeoff/nautilus.py`
- Test: `tests/test_nautilus_bakeoff.py`
- Evidence: `docs/evidence/0020/nautilus-run.json`

**Interfaces:**
- Consumes: Task 1 evidence contract; `src/quantmesh/hyperliquid/fixtures/wire_candles.json`; NautilusTrader v1.231.0 in an isolated venv.
- Produces: `run_nautilus(fixture_path, work_root) -> FrameworkRunEvidence`, `events.jsonl`, `fills.json`, and `account.json`.

- [x] **Step 1: Write fixture-export and deterministic-fill tests**

```python
def test_nautilus_comparator_preserves_replay_order_and_fill_identity(tmp_path):
    result = run_nautilus(FIXTURE, tmp_path / "work", runner=fake_nautilus_runner)
    fills = json.loads(Path(result.artifacts["fills"]).read_text())
    assert [row["sequence"] for row in fills] == sorted(row["sequence"] for row in fills)
    assert fills[0]["venue"] == "hyperliquid"
    assert fills[0]["paper"] is True
    assert result.deterministic
```

- [x] **Step 2: Run the test and capture the red result**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_nautilus_bakeoff.py --basetemp .pytest-0020-task3`

Expected: FAIL because the Nautilus runner does not exist.

- [x] **Step 3: Export recorded Hyperliquid candles without changing provenance**

Parse through QuantMesh's existing Hyperliquid wire parser, then write `timestamp,open,high,low,close,volume,sequence,source` rows. The export must reject a symbol mismatch, duplicate timestamp, non-monotonic sequence, or a gap lacking an explicit `sequence_gap=true` mark.

- [x] **Step 4: Implement the isolated Nautilus driver**

Use the pinned low-level `BacktestEngine`, add venue `HYPERLIQUID` with `OmsType.NETTING`, `AccountType.MARGIN`, USD/USDC starting balance, deterministic IDs, and a 1-minute external `BarType`. Convert the exported frame through `BarDataWrangler`, submit one limit buy after the first eligible bar, and capture order/fill/account events. The driver source must retain its own QuantMesh copyright only; do not copy upstream example bodies.

- [x] **Step 5: Add the sandbox semantics comparison**

Run the same order intent through Nautilus's `SandboxExecutionClientConfig` with `use_random_ids=False`, `bar_execution=True`, `trade_execution=True`, and `use_reduce_only=True`. Compare status transitions, fill quantity/price, deterministic IDs, and account delta with QuantMesh's `PaperAccount` over the same bars. Record mismatches rather than normalizing them away.

- [x] **Step 6: Install and execute in a separate pinned venv**

Install `nautilus_trader==1.231.0`, assert package version and repository tag commit, run twice, compare canonical hashes, run `pip check`, record environment bytes/RSS/duration, and hash LGPL-3.0. No Hyperliquid key or network endpoint may be read.

- [x] **Step 7: Verify, record, and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_nautilus_bakeoff.py tests/test_hyperliquid_risk.py tests/test_live_replay.py --basetemp .pytest-0020-task3-green`

Run: `.\.venv\Scripts\ruff.exe check src tests tools`

Commit: `git commit -m "research: compare Nautilus Hyperliquid replay semantics (#107)"`.

### Task 4: Common scorecard and ADR gate

**Files:**
- Modify: `src/quantmesh/research/frameworks.py`
- Create: `tools/framework_bakeoff/score.py`
- Create: `docs/evidence/0020/framework-scorecard.json`
- Create: `docs/adr/0015-framework-boundaries-and-instrument-workspace.md`
- Modify: `docs/REUSE_MATRIX.md`
- Modify: `docs/licenses.md`
- Modify: `docs/iterations/0020-research-to-paper-loop.md`
- Modify: `docs/goals/ACTIVE.md`
- Test: `tests/test_framework_scorecard.py`

**Interfaces:**
- Consumes: Tasks 2-3 evidence JSON.
- Produces: `score_framework(run, weights=DEFAULT_SCORE_WEIGHTS) -> FrameworkScore`, a signed-off ADR disposition of `adopt-adapter`, `isolated-comparator`, or `reject` for each framework.

- [x] **Step 1: Write the scoring-gate tests**

```python
def test_runtime_admission_requires_every_hard_gate_and_score_80():
    score = score_framework(
        passing_evidence(
            score_inputs={name: 80 for name in DEFAULT_SCORE_WEIGHTS}
        )
    )
    assert score.total == 80
    assert score.runtime_admissible
    assert not score_framework(failed_license_evidence()).runtime_admissible
```

- [x] **Step 2: Run red, then implement deterministic scoring**

Use hard gates `license`, `windows_install`, `deterministic`, `chronological_split`, `no_leakage`, `paper_only`, `contract_mapping`; use weighted soft scores `workflow_fit 25`, `adapter_cost 20`, `maintenance 15`, `resource_cost 15`, `packaging 10`, `observability 10`, `migration 5`. Runtime admission requires every hard gate and total at least 80.

- [x] **Step 3: Generate the scorecard from evidence, not prose**

Run: `.\.venv\Scripts\python.exe -m tools.framework_bakeoff.score --finrl docs/evidence/0020/finrl-x-run.json --nautilus docs/evidence/0020/nautilus-run.json --output docs/evidence/0020/framework-scorecard.json`

Expected: compact sorted-key JSON with exact revisions, checks, scores, resource values, limitations, and disposition.

- [x] **Step 4: Write ADR-0015 from the generated facts**

The ADR must state: FinRL-X's accepted/rejected boundary; Nautilus's isolated comparator boundary due LGPL/process cost even if technically successful; QuantMesh-owned contracts that remain; copied code count (expected zero); runtime dependency decision; rollback; and the native fallback. Do not describe a failed run as adopted.

- [x] **Step 5: Verify the architecture gate and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_framework_scorecard.py tests/test_security.py --basetemp .pytest-0020-task4`

Run: `.\.venv\Scripts\python.exe tools/license_review.py`

Commit: `git commit -m "docs: decide framework boundaries from bakeoff evidence (#107)"` and push the phase checkpoint.

### Task 5: Venue-aware multi-resolution historical contract

**Files:**
- Create: `src/quantmesh/instruments/__init__.py`
- Create: `src/quantmesh/instruments/contracts.py`
- Create: `src/quantmesh/instruments/history.py`
- Test: `tests/test_instrument_history.py`

**Interfaces:**
- Consumes: manifest-gated `Dataset`, `Bar`, `Instrument`, and `Venue`.
- Produces: `HistoryRange`, `DatasetBinding`, `HistoricalSeries`, `ComparisonSeries`, `HistoryService.history(...)`, and `HistoryService.compare(...)`.

- [x] **Step 1: Write range, manifest, and comparison tests**

```python
def test_history_is_manifest_gated_venue_aware_and_chronological(history_service):
    series = history_service.history(Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS)
    assert series.instrument.venue is Venue.MOOMOO
    assert series.dataset_revision == 1
    assert series.bars == sorted(series.bars, key=lambda row: row.timestamp)
    assert series.adjustment == "unadjusted"

def test_comparison_rebases_only_the_shared_observed_window(history_service):
    comparison = history_service.compare(primary=(Venue.MOOMOO, "NVDA"), peers=[(Venue.MOOMOO, "AAPL")], range=HistoryRange.ONE_YEAR)
    assert comparison.points[0].values == {"moomoo:NVDA": 100.0, "moomoo:AAPL": 100.0}
```

- [x] **Step 2: Run red and add strict models**

Define ranges `1d`, `5d`, `1m`, `3m`, `6m`, `1y`; response bars carry aware UTC timestamp, OHLCV, `adjusted_close: float | None`, and `is_live_tail`. Historical series carries dataset/revision/source/license/generated-at, interval, calendar, adjustment mode, coverage, gaps, duplicates, and limitations.

- [x] **Step 3: Implement range-to-resolution selection**

Use preferred intervals `1d->5m`, `5d->30m`, `1m->1h`, `3m/6m/1y->1d`, falling back only to a coarser available binding while recording `resolution_fallback`. Refuse an unknown venue/symbol, stale manifest, mixed instruments, duplicate timestamp, non-monotonic series, or an empty requested window.

- [x] **Step 4: Implement normalized comparisons**

Intersect observed timestamps across all series, divide each close by its first shared close, multiply by 100, and refuse fewer than two shared points. Never forward-fill across missing sessions or mix a forecast value into the comparison.

- [x] **Step 5: Verify and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_instrument_history.py tests/test_lake.py tests/test_manifest.py --basetemp .pytest-0020-task5`

Commit: `git commit -m "feat: add venue-aware historical series service (#107)"`.

### Task 6: Historical and live-tail API

**Files:**
- Create: `src/quantmesh/instruments/api.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `frontend/src/lib/api.ts`
- Test: `tests/test_instrument_api.py`

**Interfaces:**
- Consumes: `HistoryService`, optional `LiveFeed`.
- Produces: `GET /api/instruments/{venue}/{symbol}/history?range=6m&compare=moomoo:AAPL` and typed frontend `HistoricalPayload`.

- [x] **Step 1: Write API tests for success and honest absence**

```python
response = client.get("/api/instruments/moomoo/NVDA/history?range=6m&compare=moomoo:AAPL")
assert response.status_code == 200
assert response.json()["primary"]["source"] == "quantmesh-deterministic-bakeoff"
assert client.get("/api/instruments/moomoo/NVDA/history?range=bogus").status_code == 422
assert plain_client.get("/api/instruments/moomoo/NVDA/history?range=6m").status_code == 404
```

- [x] **Step 2: Run red and mount the router twice consistently**

Add `history: HistoryService | None = None` to `create_workstation_app`, store it on `app.state`, and include `instrument_router()` under `/api`. Handlers return 404 `"no historical service is attached"` when absent.

- [x] **Step 3: Join only continuity-safe live candle tails**

When a live candle matches venue, symbol, and interval, append or replace the same timestamp only if provenance is real/delayed, sequence is continuous, and timestamp is newer than the manifest bar. Mark `is_live_tail=true`; otherwise return history unchanged plus a limitation string.

- [x] **Step 4: Add exact TypeScript response types and client function**

```typescript
history: (venue: string, symbol: string, range: HistoryRange, compare: string[]) =>
  request<HistoricalPayload>(
    `/api/instruments/${encodeURIComponent(venue)}/${encodeURIComponent(symbol)}/history?${new URLSearchParams({ range, compare: compare.join(',') })}`,
  )
```

- [x] **Step 5: Verify and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_instrument_api.py tests/test_spa_api.py --basetemp .pytest-0020-task6`

Run: `npm exec tsc -- --noEmit` in `frontend/`.

Commit: `git commit -m "feat: expose historical instrument API (#107)"`.

### Task 7: Truthful multi-horizon price forecast artifact — completed

**Files:**
- Modify: `src/quantmesh/instruments/contracts.py`
- Create: `src/quantmesh/instruments/forecast.py`
- Test: `tests/test_price_forecast.py`

**Interfaces:**
- Consumes: one manifest-gated daily `HistoricalSeries` with at least 315 observed sessions.
- Produces: `PriceForecastArtifact`, `PriceForecastRegistry`, and `run_price_forecast(series, generated_at, model_version) -> PriceForecastArtifact`.

- [x] **Step 1: Write artifact, leakage, reproducibility, and gate tests**

```python
def test_forecast_has_three_horizons_quantiles_and_lineage(nvda_series):
    artifact = run_price_forecast(nvda_series, generated_at=ANCHOR, model_version="drift-conformal-v1")
    assert [path.sessions for path in artifact.paths] == [7, 30, 126]
    assert all(
        point.p025 <= point.p10 <= point.p25 <= point.p50
        <= point.p75 <= point.p90 <= point.p975
        for path in artifact.paths for point in path.points
    )
    assert artifact.dataset_revision == nvda_series.dataset_revision
    assert artifact.eligible == (artifact.blockers == [])

def test_future_flip_does_not_change_earlier_oos_predictions(nvda_series):
    original = rolling_oos_forecasts(nvda_series.bars, horizon=30)
    flipped = rolling_oos_forecasts(flip_after(nvda_series.bars, original[-1].origin), horizon=30)
    assert original[:-1] == flipped[:-1]
```

- [x] **Step 2: Run red and define the artifact models**

Each artifact includes id, instrument, dataset/revision/source, generated-at,
train start/end, model name/version/config digest, benchmark name, three
forecast paths with p2.5/p10/p25/p50/p75/p90/p97.5 points, OOS rows,
MAE/RMSE and 50/80/95-percent interval coverage per horizon, benchmark MAE,
residual sample count, eligible flag, blockers, limitations, and artifact
hashes.

- [x] **Step 3: Implement deterministic drift plus conformal intervals**

For each origin, estimate median daily log-return from only the preceding 252
observations; project `last_close * exp(median_return * k)`. Compute
horizon-specific historical residuals from chronological rolling origins, use
empirical residual quantiles for the 50/80/95-percent boundaries, and use
last-price random walk as benchmark. Generate future equity dates by
Monday-Friday sessions and crypto dates daily.

- [x] **Step 4: Implement promotion gates**

Block when history has fewer than 315 sessions, any unexplained calendar gap
or duplicate, fewer than 30 OOS residuals for 7/30 or 12 for 126,
80-percent interval coverage outside `[0.60, 0.98]`, model MAE exceeds
benchmark MAE by more than 10 percent, artifact age exceeds one session, or
any lineage field is absent. Always report 50/80/95 coverage; only the
predeclared 80-percent range is an admission gate in this prototype.

- [x] **Step 5: Implement append-only registry and byte-stable artifacts**

Write `report.json`, `paths.csv`, `oos.csv` under `artifacts/forecasts/{artifact_id}/`; exclude `created_at` only from byte-identity if and only if it is not part of setup. Registry reads fail closed with file/line attribution, duplicate IDs refuse, and dataset pins re-resolve through the lake gate.

- [x] **Step 6: Verify and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_price_forecast.py tests/test_research_models.py tests/test_research_reports.py --basetemp .pytest-0020-task7`

Commit: `git commit -m "feat: add truthful multi-horizon price forecasts (#107)"`.

### Task 8: Paper proposal lineage and operator confirmation — completed

**Files:**
- Modify: `src/quantmesh/instruments/contracts.py`
- Create: `src/quantmesh/instruments/proposals.py`
- Test: `tests/test_paper_proposals.py`

**Interfaces:**
- Consumes: `PriceForecastArtifact`, `PaperAccount.submit`, `QuoteFence`, `OrderJournal`.
- Produces: `ProposalLedger`, `PaperDecisionService.propose(...)`, and `PaperDecisionService.confirm(...) -> ProposalConfirmation`.

- [x] **Step 1: Write safety and idempotency tests**

```python
def test_confirm_requires_operator_token_and_crosses_quote_fence(service, eligible_artifact):
    proposal = service.propose(eligible_artifact, side=Side.BUY, quantity=10)
    refused = service.confirm(proposal.id, confirmation="", now=NOW)
    assert refused.proposal.status == "pending"
    confirmed = service.confirm(proposal.id, confirmation=proposal.confirmation_token, now=NOW)
    assert confirmed.order.idempotency_key == f"proposal:{proposal.id}"
    assert confirmed.proposal.order_id == confirmed.order.order_id

def test_ineligible_forecast_kill_switch_and_stale_quote_each_block(service):
    assert service.propose(ineligible_artifact(), side=Side.BUY, quantity=1).status == "blocked"
```

- [x] **Step 2: Run red and define append-only proposal states**

Use states `pending`, `blocked`, `confirmed`, `rejected`; proposal identity pins artifact id, venue/symbol, side, quantity, order type, limit price, and confirmation nonce. The ledger records every transition with aware UTC time and rejects illegal or duplicate transitions.

- [x] **Step 3: Implement deterministic confirmation**

Confirmation resolves the latest account and live snapshot, invokes `PaperAccount.submit(..., quote_fence=QuoteFence(), snapshot=...)` for real/delayed operation or an explicitly injected synthetic demo quote provider, records the order once with idempotency key `proposal:<id>`, then appends the proposal-to-order link. It never calls a broker SDK.

- [x] **Step 4: Preserve all existing safety failures verbatim**

Return typed blockers for ineligible forecast, stale/gapped/unprovenanced quote, global/per-venue kill switch, max quantity/notional/position, matcher liquidity, duplicate confirmation, and missing journal. Do not translate a refusal into an order retry.

- [x] **Step 5: Verify and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_paper_proposals.py tests/test_live_fence.py tests/test_orders.py --basetemp .pytest-0020-task8`

Commit: `git commit -m "feat: add confirmed paper proposal lineage (#107)"`.

### Task 9: Integrated workspace BFF and proposal API — completed

**Files:**
- Create: `src/quantmesh/instruments/workspace.py`
- Modify: `src/quantmesh/instruments/api.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `frontend/src/lib/api.ts`
- Test: `tests/test_instrument_workspace_api.py`

**Interfaces:**
- Consumes: history, live feed, price forecast registry, account, marks, risk limits, proposal service.
- Produces: `GET /api/instruments/{venue}/{symbol}/workspace`, `POST /api/paper/proposals`, `POST /api/paper/proposals/{id}/confirm`, and frontend `InstrumentWorkspace` types.

- [x] **Step 1: Write one-response truth and mutation tests**

Assert the workspace response carries one `generated_at`, history, live evidence, latest eligible/ineligible forecast, current position, P&L, paper limits, kill switches, and proposal capability. Assert proposal creation does not place an order, and confirmation creates exactly one journal order.

- [x] **Step 2: Run red and implement `InstrumentWorkspaceService.render`**

Capture one explicit clock, resolve each read model at that clock, and return typed unavailable sections instead of dropping keys. Position keys use existing `position_key(instrument)`; P&L uses existing `PaperAccount` methods and the same mark map as `/api/pnl`.

- [x] **Step 3: Add guarded mutation routes**

Apply `_json_guard_origin`, Pydantic request validation, 404 for unknown proposal, 409 for blocked/refused confirmation, and 200 for idempotent replay. Never accept account, quote, forecast eligibility, or risk result from browser input.

- [x] **Step 4: Add the typed frontend client**

Expose `api.instrumentWorkspace`, `api.createPaperProposal`, and `api.confirmPaperProposal`; request bodies contain only venue, symbol, artifact id, side, quantity, optional limit, and confirmation token.

- [x] **Step 5: Verify and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_instrument_workspace_api.py tests/test_api.py tests/test_spa_api.py --basetemp .pytest-0020-task9`

Run: `npm exec tsc -- --noEmit` in `frontend/`.

Commit: `git commit -m "feat: compose instrument workspace API (#107)"`.

### Task 10: Deep deterministic demo history and forecast/proposal assembly — completed

**Files:**
- Modify: `src/quantmesh/demo/manifest.py`
- Modify: `src/quantmesh/demo/generators.py`
- Modify: `src/quantmesh/demo/seeder.py`
- Modify: `src/quantmesh/demo/runtime.py`
- Test: `tests/test_demo_instrument_workspace.py`

**Interfaces:**
- Consumes: Tasks 5-9 services.
- Produces: seeded NVDA multi-resolution history, one eligible forecast artifact, one blocked artifact example, and resettable proposal ledger under the demo root.

- [x] **Step 1: Write deterministic seed/reset tests**

Seed two roots and assert identical history/forecast/proposal artifact bytes; assert NVDA has 650 daily sessions and short-range intraday coverage; create and confirm one proposal, reset, and assert the proposal disappears while seeded state returns. The 650-session floor is required to fit 252 returns, observe 126-session outcomes, and evaluate later 126-session intervals without leakage.

- [x] **Step 2: Run red and expand the generator without wall-clock reads**

Keep the current five-session live fixture contract unchanged. Add a separate historical generator for 650 daily sessions plus bounded 5-minute/30-minute/hourly windows, all derived from scenario seed and anchor and labeled `demo-synthetic`.

- [x] **Step 3: Seed the forecast registry and proposal service**

Run the real Task 7 pipeline over seeded NVDA history; bind history, price forecast, proposal ledger, and decision service into `create_workstation_app`. Demo confirmation uses the seeded order-book touch and labels the quote synthetic; non-demo confirmation continues to require the live quote fence.

- [x] **Step 4: Update demo provenance row counts**

Add surfaces `history`, `price_forecasts`, and `paper_proposals`; status/reset must derive counts from disk, not constants that can drift.

- [x] **Step 5: Verify and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_demo_instrument_workspace.py tests/test_demo.py tests/test_datalink.py --basetemp .pytest-0020-task10`

Commit: `git commit -m "feat: seed the integrated NVDA demo decision loop (#107)"` and push the backend phase checkpoint.

### Task 11: Licensed market-chart adapter — completed

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/components/charts/InstrumentChart.tsx`
- Create: `frontend/src/components/charts/InstrumentChart.test.tsx`
- Modify: `docs/licenses.md`
- Modify: `docs/REUSE_MATRIX.md`

**Interfaces:**
- Consumes: `HistoricalPayload` and forecast path DTOs.
- Produces: `<InstrumentChart mode="candles|line" primary comparisons forecast volume />` with no direct library usage elsewhere.

- [x] **Step 1: Install the exact permissive dependency**

Run: `npm install --save-exact lightweight-charts@5.2.0` in `frontend/`.

Record Apache-2.0, package URL, version, unpacked size, TradingView attribution requirement, and NOTICE handling in license docs.

- [x] **Step 2: Write adapter lifecycle and accessible-fallback tests**

Mock `createChart`; assert one chart per mount, `remove()` on unmount, no
duplicate series on rerender, resize handling, candlestick/line mode, volume
histogram, comparison lines, forecast median plus 50/80/95 interval
boundaries, and an off-canvas accessible summary table.

- [x] **Step 3: Run red and implement the single adapter**

Use v5 APIs `createChart`, `CandlestickSeries`, `LineSeries`, and `HistogramSeries`. All numeric data arrives through props; set `autoSize`, UTC time scale, crosshair, locale-aware price formatting, and semantic green/neutral/red tokens. No venue fetch occurs in the component.

- [x] **Step 4: Implement state-safe updates**

Create chart and series once in `useEffect`, update series with `setData`, preserve visible range on live-tail updates, call `fitContent` only on instrument/range changes, and honor reduced motion by disabling animated transitions.

- [x] **Step 5: Verify and commit**

Run: `npm exec vitest run -- src/components/charts/InstrumentChart.test.tsx`.

Run: `npm run lint && npm run build`.

Commit: `git commit -m "feat(frontend): add licensed instrument chart adapter (#107)"`.

### Task 12: Venue-aware route and workspace state shell — completed

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/screens/InstrumentWorkspace.tsx`
- Create: `frontend/src/screens/instrument/WorkspaceHeader.tsx`
- Create: `frontend/src/screens/instrument/WorkspaceStates.tsx`
- Modify: `frontend/src/screens/Cockpit.tsx`
- Modify: `frontend/src/screens/CockpitDetail.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Test: `frontend/src/screens/InstrumentWorkspace.test.tsx`

**Interfaces:**
- Consumes: `api.instrumentWorkspace` and existing live WebSocket hook.
- Produces: canonical `/instruments/:venue/:symbol` screen and compatibility navigation from cockpit.

- [x] **Step 1: Write route, loading, error, and degraded-state tests**

Render `/instruments/moomoo/NVDA`; assert venue and symbol are both sent to API, skeleton matches the three-column final layout, a 404 explains missing history, stale live state remains visible but blocks paper action, and `/cockpit/NVDA` links to the venue-aware route.

- [x] **Step 2: Run red and add the route**

Add `<Route path="instruments/:venue/:symbol" element={<InstrumentWorkspaceScreen />} />`; retain the old cockpit detail route as a compatibility surface, not the primary implementation.

- [x] **Step 3: Implement the shell hierarchy**

Use one sticky context header, one dominant chart canvas, a compact evidence strip, and a right decision rail at `xl`; collapse to chart then evidence then decision at 390 px. Use separators/negative space instead of nested cards; all numbers are tabular mono.

- [x] **Step 4: Add English and Simplified-Chinese state copy**

Add keys for ranges, chart modes, loading, missing history, resolution fallback, stale/gap, forecast blocked, no position, proposal blocked, confirm, rejected, and audit lineage. Do not add visible untranslated literals.

- [x] **Step 5: Verify and commit**

Run: `npm exec vitest run -- src/screens/InstrumentWorkspace.test.tsx src/lib/messages.test.ts`.

Run: `npm exec tsc -- --noEmit && npm run lint`.

Commit: `git commit -m "feat(frontend): add venue-aware instrument workspace shell (#107)"`.

### Task 13: Observed chart, ranges, indicators, and comparisons — completed

**Files:**
- Create: `frontend/src/screens/instrument/MarketCanvas.tsx`
- Create: `frontend/src/screens/instrument/IndicatorStrip.tsx`
- Create: `frontend/src/screens/instrument/ComparisonPicker.tsx`
- Modify: `frontend/src/screens/InstrumentWorkspace.tsx`
- Test: `frontend/src/screens/instrument/MarketCanvas.test.tsx`

**Interfaces:**
- Consumes: Task 11 chart adapter and Task 6 historical payload.
- Produces: operator controls for `1D/5D/1M/3M/6M/1Y`, line/candle mode, volume, SMA20/SMA50, realized volatility, drawdown, and at most three normalized peers.

- [x] **Step 1: Write interaction and truthfulness tests**

Assert range changes refetch with the selected range, comparison selection is capped at three, indicators derive only from observed closes, live tails do not duplicate the last bar, disabled controls explain unavailable resolution, and tooltip text identifies observed versus forecast values.

- [x] **Step 2: Run red and implement range/chart controls**

Use shadcn-owned button/toggle primitives with real labels and `aria-pressed`; preserve controls in URL query parameters so refresh/back navigation retains context.

- [x] **Step 3: Implement bounded indicators**

Compute SMA20, SMA50, annualized realized volatility from log returns, and drawdown in pure TypeScript helpers with finite-number guards. No RSI/MACD library or unbounded indicator menu enters this slice.

- [x] **Step 4: Implement normalized peer comparison**

Render API-produced rebased series and label them `Indexed to 100 at <shared timestamp>`; never normalize independently in the browser or forward-fill a gap.

- [x] **Step 5: Verify and commit**

Run: `npm exec vitest run -- src/screens/instrument/MarketCanvas.test.tsx src/components/charts/InstrumentChart.test.tsx`.

Commit: `git commit -m "feat(frontend): add observed chart analysis controls (#107)"`.

### Task 14: Forecast evidence and paper decision rail — completed

**Files:**
- Create: `frontend/src/screens/instrument/ForecastEvidence.tsx`
- Create: `frontend/src/screens/instrument/DecisionRail.tsx`
- Create: `frontend/src/screens/instrument/ProposalConfirmation.tsx`
- Modify: `frontend/src/screens/InstrumentWorkspace.tsx`
- Test: `frontend/src/screens/instrument/DecisionRail.test.tsx`

**Interfaces:**
- Consumes: Task 9 workspace/proposal APIs.
- Produces: horizon selector, uncertainty/quality/lineage evidence, current position/P&L/risk, proposal preview, explicit confirmation, and resulting order/audit link.

- [x] **Step 1: Write decision-flow tests**

Assert 7/30/126-session paths display the median, selectable 50/80/95
intervals and vintage; ineligible forecasts show blockers and disable
proposal; proposal preview does not order; confirmation requires the displayed
token/action; stale quote and kill switch refusals remain visible; successful
confirmation shows order id and audit link; retry does not duplicate.

- [x] **Step 2: Run red and implement forecast evidence**

Show benchmark comparison, OOS MAE/RMSE/coverage, sample count, dataset revision, model version/config digest, train cutoff, generated-at, limitations, and promotion state. Label synthetic demo artifacts on every forecast block.

- [x] **Step 3: Implement current portfolio/risk context**

Show position quantity, average cost, marked/unmarked P&L, account equity, max quantity/notional/position, global/per-venue kill-switch state, and quote freshness. Missing marks render `Unavailable`, never zero.

- [x] **Step 4: Implement two-stage paper action**

Stage one creates a proposal from side/quantity/optional limit. Stage two renders the immutable proposal facts and requires explicit confirmation. Disable action while mutation is pending; preserve the backend refusal message; on success invalidate workspace/orders/positions/P&L/audit queries.

- [x] **Step 5: Verify and commit**

Run: `npm exec vitest run -- src/screens/instrument/DecisionRail.test.tsx src/screens/InstrumentWorkspace.test.tsx`.

Run: `npm exec tsc -- --noEmit && npm run lint && npm run build`.

Commit: `git commit -m "feat(frontend): complete forecast-to-paper decision rail (#107)"` and push the product phase checkpoint.

### Task 15: Browser acceptance, accessibility, responsive finish, and design record

**Files:**
- Create: `tests/test_instrument_workspace_e2e.py`
- Modify: `tests/test_workstation_e2e.py`
- Modify: `tools/golden_path.py`
- Create: `DESIGN.md`
- Modify: `docs/iterations/0020-research-to-paper-loop.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**
- Consumes: complete demo workspace.
- Produces: browser-proven NVDA inspect-to-paper loop and durable visual/operational record.

- [x] **Step 1: Write the failing Playwright acceptance**

Walk: open NVDA route, switch 6M to 1M, toggle candles/line, enable volume/SMA20, compare AAPL, inspect 30-session forecast and lineage, create BUY 10 proposal, confirm, observe fill/position/P&L/risk/audit link, engage kill switch, verify next proposal receives 409, reset, verify deterministic state.

- [x] **Step 2: Add keyboard, locale, and 390 px assertions**

Tab through all controls in logical order; use controls without mouse; switch zh-CN and assert translated range/forecast/proposal copy; assert no horizontal overflow at 390 px; assert focus visibility and reduced-motion behavior; include landmarks and chart accessible summary.

- [x] **Step 3: Run the browser suite and fix product defects test-first**

Run: `.\.venv\Scripts\python.exe -m pytest -q tests/test_instrument_workspace_e2e.py tests/test_workstation_e2e.py --basetemp .pytest-0020-task15`

Expected after fixes: PASS with no browser skip in the acceptance environment.

- [x] **Step 4: Run the Impeccable mechanical detector once**

Run: `node .codex/skills/impeccable/scripts/detect.mjs --json frontend/src/screens/InstrumentWorkspace.tsx frontend/src/screens/instrument frontend/src/components/charts/InstrumentChart.tsx frontend/src/index.css`.

Fix all mechanical findings, then do not rerun the detector. Capture desktop dark/light and 390 px screenshots for the fresh finish reviewer.

- [x] **Step 5: Run the fresh Impeccable finish review and close findings**

Provide the reviewer the original objective, screenshots, design read, changed files, PRODUCT.md, and the product-register constraints. Apply one batched fix round, recapture, and obtain a verdict with no open material finding before claiming UI completion.

- [x] **Step 6: Record the built visual system and golden path**

Write `DESIGN.md` from the implemented tokens/components: restrained black/green palette, Geist/mono numeric hierarchy, 10 px base radius, separator-first dense layout, chart palette, semantic states, motion durations, responsive rail collapse, and accessibility rules. Extend `tools/golden_path.py` with the workspace GET, proposal preview, confirmation, lineage, kill-switch refusal, and reset checks.

- [x] **Step 7: Verify and commit**

Run: `.\.venv\Scripts\python.exe tools/golden_path.py`.

Run: `npm exec tsc -- --noEmit && npm run lint && npm exec vitest run && npm run build`.

Commit: `git commit -m "test: accept the integrated instrument decision loop (#107)"`.

### Task 16: Full review, release gates, PR, merge, and `v0.1.1-rc1`

**Files:**
- Modify: `docs/iterations/0020-research-to-paper-loop.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/roadmap/ROADMAP.md`
- Modify: `docs/iterations/INDEX.md`
- Modify: `pyproject.toml`
- Modify: `src/quantmesh/__init__.py`
- Create: `docs/release-notes/v0.1.1-rc1.md`
- Create after tag checkout: acceptance-root `OPERATOR-ACCEPTANCE.md` and `OPERATOR-ACCEPTANCE.zh-CN.md`

**Interfaces:**
- Consumes: all prior green commits and reviewer reports.
- Produces: one green squash-merged PR, immutable `v0.1.1-rc1` tag, and an isolated acceptance station; no final `v0.1.1` promotion.

- [x] **Step 1: Request a fresh broad code review against `origin/main`**

Review standards and intent, framework/license isolation, chronology/leakage, determinism, API types, quote/risk/kill-switch authority, frontend state honesty, accessibility, and release packaging. Fix every Critical and Important finding using a new failing regression test first.

- [x] **Step 2: Run the complete local verification matrix**

Run in order:

```powershell
.\.venv\Scripts\ruff.exe check src tests tools
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-0020-final
Push-Location frontend
npm ci
npm exec tsc -- --noEmit
npm run lint
npm exec vitest run
npm run build
Pop-Location
.\.venv\Scripts\python.exe tools\build_frontend.py --check
.\.venv\Scripts\python.exe tools\golden_path.py
.\.venv\Scripts\python.exe tools\live_smoke.py --url http://127.0.0.1:8771 --watchlist AAPL,NVDA
.\.venv\Scripts\python.exe tools\license_review.py
.\.venv\Scripts\pip-audit.exe -r requirements-audit.txt --no-deps
git diff --check
git submodule status
```

The broad developer venv may contain optional research/audit tools outside the
frozen release closure; in that environment `tools/license_review.py` must
refuse them. Record the refusal, never allowlist ambient packages, and obtain
the authoritative license PASS from Step 3's fresh release venv.

- [x] **Step 3: Run the clean-checkout release gate before opening the PR**

Run: `.\.venv\Scripts\python.exe tools/release_gate.py --branch HEAD`.

Record all step counts, elapsed times, pytest totals, browser totals, golden-path totals, bundle hash, and clean-checkout proof in iteration 0020.

- [x] **Step 4: Open the one final PR and wait for CI**

Push the branch, open a non-draft PR titled `M13: integrated instrument decision workspace`, link `Closes #107`, include framework dispositions and verification evidence, then wait for CI/Security. Fix failures on the same branch and rerun the affected local gate.

- [x] **Step 5: Squash-merge under standing authority**

Merge only when every required check is green and no Critical/Important finding remains. Delete the remote branch, fetch `origin/main`, and fast-forward local `main` without manufacturing a merge commit.

- [x] **Step 6: Cut the release candidate from merged main**

Update every version surface to PEP 440 `0.1.1rc1` / tag `v0.1.1-rc1`, write English-primary release notes with a Simplified-Chinese acceptance section, commit through a release PR if branch protection requires it, merge, then create one annotated immutable tag on the merged commit.

- [x] **Step 7: Verify the exact tag in an isolated acceptance root**

Fresh-clone the tag, create a new venv, install `.[dev,research,e2e]`, run the release gate against the exact tag, start a deterministic demo station and a read-only live/degraded station on unused loopback ports, execute the smoke drill, and write English plus zh-CN operator checklists covering the NVDA loop, failure states, keyboard/390 px, persistence/reset, and kill switch.

- [x] **Step 8: Stop at the operator gate**

Report the tag commit, install/import/API versions, station URLs/PIDs, all verification counts, framework decisions, acceptance checklist paths, and any honest degraded external source. Do not create or promote `v0.1.1` until the operator explicitly accepts `v0.1.1-rc1`.

## Self-Review Result

- Spec coverage: every framework, evidence, historical/live chart, comparison, forecast, lineage, paper action, safety, UI, verification, merge, RC, and acceptance requirement maps to Tasks 1-16.
- Placeholder scan: the plan contains no deferred implementation marker; every conditional framework outcome resolves through the Task 4 evidence gate and native-owned Tasks 5-10.
- Type consistency: `FrameworkRunEvidence`, `HistoryService`, `PriceForecastArtifact`, `PriceForecastRegistry`, `PaperDecisionService`, `InstrumentWorkspaceService`, and their frontend DTO names remain stable from producer task to consumer task.
