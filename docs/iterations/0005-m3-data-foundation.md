# Iteration 0005 — M3 Data Foundation and Experiment Registry

- Status: complete
- Started: 2026-08-07
- Completed: 2026-08-07 — slice #1 (issue #14, merged `0bee38f`); slices #2-#6 (issues #15-#19, merged to main as squash `bcfb0b1` via the final M3 PR #23)
- Owner: unassigned agent team
- GitHub issue: issues #14-#19 (all closed; #12 was consumed by the M2 completion-records PR and #13 by the squash-divergence tracking issue)
- Pull request: [merged #23](https://github.com/ZP151/quantmesh/pull/23) — one final M3 integration PR from `feat/m3-data-foundation`, squash `bcfb0b1`
- Roadmap milestone: M3 (see `docs/roadmap/ROADMAP.md`) — DONE

## Outcome

Ingest, normalize and version research data without coupling strategies to
providers. A pinned dataset can reproduce an experiment on a clean checkout,
and missing, duplicated and out-of-order observations are detected — the two
roadmap exit criteria for M3.

## Scope

- In scope: normalized market-data schemas, Parquet/DuckDB local data lake
  with data-quality checks, dataset manifests, provider registry with
  fixture-driven adapters, experiment registry, scheduled ingestion with gap
  detection.
- Out of scope: live venue credentials, wallet signing, any order placement,
  AI order authority, M4 venue workflows (Moomoo), strategy backtesting
  engines (M7).

## Acceptance criteria

- [x] A pinned dataset reproduces an experiment on a clean checkout
      (integration test spanning manifest → lake → experiment registry) —
      `test_resolve_reopens_pinned_dataset_on_clean_checkout`.
- [x] Missing, duplicated and out-of-order observations are detected by the
      data-quality checks — lake quality primitives (issue #14) plus the
      ingestion roundtrip test and `coverage_gaps`.
- [x] A strategy-facing consumer cannot see which provider produced a dataset
      (provider isolation behind the registry contract) —
      `test_provider_isolation_lake_bytes_are_provider_agnostic`.
- [x] No live credentials, secrets or private keys appear in code, tests,
      fixtures, logs or manifests — secret scan of the full M3 diff clean
      (only policy-doc mentions of "credential").

## Plan and role assignments

Split into six single-session vertical tickets with explicit blocking edges,
mirroring the M2 slice chain. Issue numbers continue the shared
issues/PRs sequence: issues #1-#6 exist, PRs #7-#11 exist, so M3 issues are
#14-#19 (the M2 completion-records PR took #12 and the squash-divergence
tracking issue took #13).

1. [#14] Normalized market-data schemas (no deps) — `Bar`, `OrderBook`
   (depth levels), `TradeEvent` pydantic models plus monotonicity,
   gap and duplication primitives. Domain layer only, no I/O.
2. [#15] Parquet/DuckDB local data lake (blocks on #14) — lake layout and
   partition convention, DuckDB-backed read/write surface, data-quality
   checks (missing/duplicated/out-of-order). Writes ADR-0003 (data lake and
   normalization contract).
3. [#16] Dataset manifests (blocks on #15) — source, timezone, revision,
   license and coverage metadata; manifest generation and validation; a
   manifest is required before a dataset is queryable.
4. [#17] Provider registry (blocks on #14) — provider contract
   (bar/order-book/trade fetch), registry keyed by `Venue`, adapters
   isolated behind the contract; fixture data only, no live credentials.
5. [#18] Experiment registry (blocks on #16) — experiment IDs linking
   dataset manifest references (pinned revision), code commit, parameters
   and metrics; reproducible from a manifest on a clean checkout.
6. [#19] Scheduled ingestion and gap detection (blocks on #16, #17) —
   scheduler driving providers into the lake, gap detection comparing
   observed coverage against manifests.

- Planner: this record (2026-08-07).
- Quant researcher: define schema invariants and quality-check semantics
  (slice #14); define what "reproducible experiment" means in practice
  (slice #18).
- Implementer: TDD each slice on `feat/m3-data-foundation` under the solo
  fast lane, with one coherent commit per issue and a push after each verified
  slice.
- Reviewer: two-axis /code-review (standards + spec) on each slice before
  merge.
- Verifier: record exact commands and results in this record per slice.

## Decisions

- Normalized schemas live in `src/quantmesh/domain/market_data.py`,
  venue-agnostic and derived from the existing `Instrument` model in
  `src/quantmesh/domain/models.py` (`Venue` already enumerates internal,
  moomoo, hyperliquid, polymarket, kalshi). Provider-specific fields stay in
  adapter payloads, never in the canonical models.
- The lake is a local directory of Parquet files queried through DuckDB
  (already pinned in the `research` extra, `duckdb>=1.1,<2`, MIT). Issue #15
  asked to add `pyarrow`, but the slice review showed it is not required:
  pandas (already a main dependency) is the deterministic write bridge —
  column order and frame layout are dict-ordered, and COPY writes no index
  column — so pyarrow stays out (ADR-0003). Partition convention:
  `data/<dataset>/<interval>/<venue>/<symbol>/<date>/<shard>.parquet`.
  Local-first: the lake root comes from settings (pydantic-settings,
  `QUANTMESH_` prefix, `.env`), defaulting under the user's data directory —
  credentials, models and audit logs stay under user control (roadmap
  principle 5).
- The lake, partition layout and normalization contract are durable
  architecture: record them in a new ADR-0003 during slice #15.
- Canonical interval grammar is the compact form `\d+[smhdw]`
  (`"1m"`, `"1h"`, `"1d"`, …); adapters convert provider-specific
  interval strings into it (slice #14 decision, reviewed).
- Market-data timestamps are timezone-aware at the model boundary
  (stricter than the order-domain models, whose matcher guards at use
  time): the quality primitives' correctness depends on aware datetimes,
  and naive data failing at the model boundary is cheaper than failing
  in the lake (slice #14 decision, reviewed).
- `DepthLevel` bid/ask identity is positional (which list the level is
  in), not a field on the level; a redundant side field would invite
  drift (slice #14 decision, reviewed).
- Gap detection is grid-relative: `find_gaps` reports missing ticks
  between observations when every consecutive delta is an exact multiple
  of the interval; a shifted-but-regular grid is coverage/alignment
  detection, deferred to the manifest slice (#16).
- Manifests are versioned JSON beside each dataset, produced by a manifest
  writer and required by the validation gate before a dataset is queryable.
  They carry source, timezone, revision, license and coverage — the
  "pinned dataset" anchor for experiment reproducibility.
- The provider registry follows the OpenBB provider-pattern shape (registry
  + per-provider adapters) but is our own contract: OpenBB is AGPLv3 and
  stays a reference submodule, never embedded (REUSE_MATRIX.md). Adapters
  live in `src/quantmesh/data/providers/`, tested against fixtures only.
- Safety boundaries are unchanged from AGENTS.md: no live credentials in
  prompts, logs or fixtures; no order placement and no wallet signing in M3
  (execution stays paper-only from M2); AI output remains research input,
  never order authority. M3 introduces no execution surface at all.

## Work log

- 2026-08-07: Created the M3 plan from the roadmap's M3 section. Issues
  #14-#19 open once M2 merges to main (renumbered twice: the M2
  completion-records PR took #12, the squash-divergence tracking issue took
  #13); each slice then gets a branch, PR and verification evidence as in
  iteration 0003.
- 2026-08-07: M2 merged to main (PRs #7-#11); plan renumbering applied.
- 2026-08-07: Issues #14-#19 opened. Renumbered from #13-#18: #13 was taken
  by the squash-divergence tracking issue (PR #20, squash `a617ab6`); #12
  was taken by the M2 completion-records PR. Slice #1 (issue #14) is next.
- 2026-08-07: Slice #1 (issue #14) implemented with TDD on
  `feat/14-normalized-market-data-schemas`:
  - Vertical slices: models (`Bar` → `OrderBook` → `TradeEvent`) →
    invariants (OHLC consistency, per-side book ordering, positivity) →
    interval parsing → monotonicity → duplication → gap detection.
  - Added `Bar`, `DepthLevel`, `OrderBook`, `TradeEvent` plus
    `monotonic_violations`, `find_duplicates`, `find_gaps`,
    `interval_to_timedelta` in `src/quantmesh/domain/market_data.py`;
    32 tests in `tests/test_market_data.py`; 142 total passing.
  - /code-review two-axis (standards + spec): zero hard violations. Spec
    must-fixes resolved: `"0m"` intervals fail closed (ValueError /
    ValidationError, was ZeroDivisionError in `find_gaps`);
    `monotonic_violations` rejects `None` with a typed error (legal
    `TradeEvent.venue_sequence`); `find_gaps` validates timezone
    awareness on all inputs including single-element series; docstring
    made honest about grid-relative semantics. Standards judgement
    calls: interval unit map is the single source for the grammar (no
    regex/dict drift), `make_book`/`NAIVE_T0` test helpers, misleading
    error hint reworded. Decisions recorded above.
  - Verification evidence below.
- 2026-08-07: Slice #1 merged to main as squash `0bee38f` (PR #21);
  issue #14 auto-closed on merge. Next: slice #2 (issue #15, Parquet/
  DuckDB lake) — writes ADR-0003 (lake layout and normalization
  contract).
- 2026-08-07: Switched remaining M3 work (#15-#19) to the solo delivery fast
  lane on `feat/m3-data-foundation`: commits and iteration evidence remain
  per issue, while one final M3 PR replaces repeated per-slice PR/merge cycles.
- 2026-08-07: Slice #2 (issue #15) implemented with TDD on
  `feat/m3-data-foundation`:
  - Vertical slices: `Lake` write (canonical layout, day-shard grouping,
    wholesale day replacement) → read (stored order, inclusive UTC range
    filter, empty partition) → `Settings.lake_root` (default
    `~/.quantmesh/data`, `QUANTMESH_LAKE_ROOT` override) → quality
    (`Lake.quality` over the slice #14 primitives) → ADR-0003.
  - Added `src/quantmesh/data/lake.py` (`Lake`, `LakeQuality`,
    `validate_dataset_name`), `src/quantmesh/data/__init__.py`, the
    `lake_root` setting, ADR-0003; 34 lake tests in `tests/test_lake.py`;
    182 total passing.
  - Two-axis review found 3 real bugs, all fixed with regression tests:
    unvalidated `symbol`/`interval`/`day` path components (write could
    escape the lake root; read with `symbol=".."` could leak other
    partitions), unescaped COPY target (raw duckdb error / SQL surface
    for roots or symbols with quotes), naive `start`/`end` bounds
    (raw TypeError instead of fail-closed ValueError). Hardening also
    landed: temp-file + atomic rename per shard, day-dir filtering on
    read, per-duckdb-version determinism caveat.
  - ADR-0003 written and reviewed against the implementation before any
    ingestion; records the layout, normalization contract (UTC on write
    and read), stored-order reads, quality gate, and the pyarrow decision.
  - Verification evidence below.
- 2026-08-07: Slice #3 (issue #16) implemented with TDD on
  `feat/m3-data-foundation`:
  - Vertical slices: shared layout module (path grammar extracted from
    slice #15 into `src/quantmesh/data/layout.py`) → `SeriesCoverage` /
    `DatasetManifest` models → `scan_series` (duckdb count/min/max per
    series, UTC-normalized) → `ManifestWriter.generate` (revision bump,
    atomic unique-temp write) → gate `Lake.dataset()` + `Dataset` view
    (manifest required, name match, coverage freshness vs disk).
  - Added `layout.py` and `manifest.py`; 47 manifest + lake tests in
    `tests/test_manifest.py` (extended `test_lake.py` with reserved-name
    and extra symbol cases); 220 total passing (1 skipped: symlink
    creation not permitted on this Windows machine).
  - Adversarial review found 5 real bugs, all fixed with regression
    tests: symlink/junction components could point the lake at external
    bytes (now rejected at every layout level), concurrent `generate()`
    raced on a fixed temp name (now unique `mkstemp` files), stray files
    below the interval level crashed `scan_series` raw (now skipped;
    stray dirs still fail closed), Windows reserved names passed the
    whitelists (now rejected), and NULL/undecodable inputs leaked raw
    AttributeError/UnicodeDecodeError (now fail-closed ValueErrors).
    `Dataset.__init__` now also enforces the manifest-name match.
  - ADR-0003 extended with the manifest contract (location, fields,
    freshness semantics, point-in-time `Dataset` view).
  - Verification evidence below.
- 2026-08-07: Slice #4 (issue #17) implemented with TDD on
  `feat/m3-data-foundation`:
  - Vertical slices: `Provider`/`ProviderMode` contract (bars, order
    books, trades out) → `FixtureProvider` base (injectable fixture dir,
    fail-closed load) → hyperliquid + moomoo fixture adapters (canonical
    mapping, symbol/interval checks, explicit side map) →
    `ProviderRegistry` keyed by `Venue` (refuses SANDBOX/LIVE —
    fixture-only is the M3 posture per AGENTS.md; one provider per
    venue) → 6 fixture JSON files → provider-isolation test making the
    exit criterion concrete (canonical shard columns + manifest coverage
    fields, no provider identity).
  - Added `src/quantmesh/data/providers/` (5 modules, 6 fixtures) and
    `[tool.setuptools.package-data]` so fixtures ship in wheels; 23
    provider tests in `tests/test_providers.py`; 243 total passing.
  - Adversarial review found 3 real bugs + 2 design risks, all fixed
    with regression tests: moomoo books/trades never verified the
    requested symbol and no adapter rejected cross-venue instruments (a
    MSFT backtest could silently trade AAPL prices), `_utc` silently
    shifted naive fixture timestamps by the local machine offset
    (fail-open), and unknown side markers silently mapped to SELL.
    Hardening: empty fixtures fail closed ("no rows"), the bar-interval
    check covers every row, per-row parse errors carry fixture + row
    attribution (no raw KeyError / bare ValidationError), offset-form
    timestamps normalize to UTC (regression-tested).
  - Verification evidence below.
- 2026-08-07: Slice #5 (issue #18) implemented with TDD on
  `feat/m3-data-foundation`:
  - Vertical slices: `experiment_id` (deterministic setup hash —
    dataset, manifest revision, commit, canonical parameters; metrics
    excluded, so results never change identity) → `Experiment` model
    (grammar validation, aware UTC `created_at`, id-integrity
    recompute on load) → `ExperimentRegistry.record` (git-HEAD commit
    default, duplicate refusal, pin validated through the lake's
    manifest gate before anything is written) → JSONL persistence
    (atomic unique-temp + rename rewrites, fail-closed per-line reads
    with line attribution) → `resolve` (re-open the pinned dataset:
    gate + revision equality) → the clean-checkout integration test.
  - Added `src/quantmesh/research/experiments.py` (exports in
    `research/__init__.py`), `settings.experiments_dir` default
    `~/.quantmesh/experiments` (`QUANTMESH_EXPERIMENTS_DIR` override);
    22 experiment tests in `tests/test_experiments.py`; 265 total
    passing.
  - Adversarial review found 2 real bugs, both fixed with regression
    tests: NaN/Infinity parameter values made the persisted line's
    recomputed ID diverge (pydantic serializes them as `null`, the ID
    hash over raw `NaN` did not) and permanently bricked the whole
    registry file — non-finite floats are now rejected at the model
    boundary; duplicate IDs in the file passed read validation and a
    metrics-only tamper resolved silently — `_read` now refuses
    duplicate IDs with line attribution. Hardening: the duplicate
    check runs before the pin check (a re-record after the lake
    advanced reports "already recorded", not a misleading pin error),
    registry-root-is-a-file fails closed, and the docstring records
    that metrics are unsigned results (undetectable without signing,
    out of M3 scope) and that concurrent writers are last-writer-wins.
  - Verification evidence below.
- 2026-08-07: Slice #6 (issue #19) implemented with TDD on
  `feat/m3-data-foundation`:
  - Vertical slices: `IngestionJob` (dataset/interval/cadence grammar,
    cadence validated but unused — M3 ships no timer, the caller runs
    the deterministic loop) → `Ingestor.ingest` (fetch window re-opens
    the UTC day of the last stored tick so the day shard is rebuilt
    wholesale from the provider; full-OHLCV no-op comparison; stale
    manifest healing) → `run` (ordered slots, `None` = nothing new) →
    `coverage_gaps` (`SeriesGap`/`CoverageReport`: vanished series,
    missing day shards, undeclared bytes; interval-grid expected days;
    fails closed on missing/invalid/foreign manifests, corrupt shards
    and fully-empty datasets).
  - Added `src/quantmesh/data/ingestion.py`; 23 ingestion tests in
    `tests/test_ingestion.py` (15 initial + 8 review regressions); 288
    total passing.
  - Adversarial review found 2 real bugs + 3 risks, all fixed with
    regression tests: (1) the no-op check compared timestamps only, so
    a provider correction or retraction of the last day was silently
    dropped — the check now compares full OHLCV content, and the
    regression tests prove corrections (same timestamps, new values)
    and retractions (provider shrank) rebuild the day shard; (2) a
    write whose manifest regeneration failed (corrupt unrelated shard)
    left the dataset permanently gated because the next run no-op'd —
    an unchanged run now heals a stale manifest by regenerating, so
    the failure stays loud every run and recovery happens
    automatically once the shard is repaired. Risks: raw duckdb
    exceptions leaked from `scan_series` and `Lake.read_bars` (now
    wrapped as fail-closed ValueErrors with shard attribution, covering
    the gate, `generate`, `coverage_gaps` and `ingest`), calendar-day
    `missing_days` reported phantom gaps for coarse intervals (expected
    days now come from the interval grid anchored at the declared
    start; trading calendars explicitly out of scope), and a fully
    empty dataset was reported clean (now fails closed — a coverage
    report must never bless total data loss). Minor: the timestamp-set
    per-bar rebuild (O(fetched × stored)) is gone with the content
    comparison, and the previously untested documented semantics now
    have tests.
  - Verification evidence below.
  - Round-2 (final holistic review of the complete M3 diff): 1 real bug
    + 1 risk + 3 minors fixed. The real bug was interior-day-loss
    masking: after a day shard is deleted, a later ingest rewrites the
    day window and regenerates a manifest whose row counts and end are
    unchanged — the missing day is invisible to the lake gate and to
    `coverage_gaps` (same count, same range). Fixed with the
    monotonic-coverage invariant: `ManifestWriter.generate` now loads
    the previous manifest and refuses to declare less coverage —
    vanished series, shrunk rows, or a moved-back end unless the series
    is rebuilt from an authoritative source (`rewritten`), and a
    moved-forward start always (a new day must never mask a lost
    interior day); removing `manifest.json` is the documented explicit
    override. The risk: raw duckdb exceptions and NULL timestamps from
    tampered shards — `Lake.read_bars` now fails closed on NULL
    timestamps, and `_reject_symlinks` guards the raw `Lake` read/write
    surface (previously only the manifest scan rejected links, so a
    symlinked interval/venue/symbol dir could redirect raw reads/writes
    outside the root). Minors: the write path passes
    `rewritten=<the job's series>` so day rewrites stay legal,
    `coverage_gaps` documents its same-count/same-range blind spot,
    ADR-0003 records the monotonic rule, and 6 manifest + 3 lake
    regression tests added (297 total passing). CI then caught two more
    gaps: `duckdb` was only in the research extra while the lake
    hard-imports it (promoted to core dependencies — CI installs
    `.[dev]`), and `_reject_symlinks` only walked a path's parents, so a
    symlink at the terminal path itself (the symbol directory
    `read_bars` hands over, or a shard file) passed through — the
    terminal path is now checked too. Both surfaced only on Linux CI:
    the lake symlink tests skip where symlink creation is not permitted,
    and Windows runners skip them.
  - 2026-08-07 close-out: final M3 PR [#23](https://github.com/ZP151/quantmesh/pull/23)
    merged to main as squash `bcfb0b1` (non-draft; CI green on the PR
    branch head — the two follow-up commits CI caught are the `duckdb`
    core-dependency promotion and the terminal-path symlink fix);
    `feat/m3-data-foundation` deleted; issues #14-#19 closed. Main
    verified locally (297 passed, 3 skipped, ruff clean). All four M3
    exit criteria met (see checkboxes above). M3 complete.

## Verification evidence

Per slice: `pytest -q`, `ruff check src tests`, `git diff --check`,
`git submodule status`; integration evidence for the two roadmap exit
criteria in slices #15 and #17.

Slice #1 (issue #14, branch `feat/14-normalized-market-data-schemas`, PR
[#21](https://github.com/ZP151/quantmesh/pull/21), merged as squash
`0bee38f`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 148 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\ruff.exe check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: /code-review two-axis (standards + spec) — zero hard
violations; all must-fixes resolved (fail-closed `"0m"` interval,
`None`-safe monotonicity, tz-validation on all `find_gaps` inputs,
honest grid-relative docstring); standards judgement calls resolved
(single-source interval grammar, test helpers, reworded error hint).
Issue #14 closed on merge; remote feature branch deleted.

Slice #2 (issue #15, committed on `feat/m3-data-foundation`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 182 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: adversarial correctness review — 3 real bugs found and
fixed (symbol/interval/day path validation, SQL literal escaping,
naive-bound fail-closed) plus atomic temp+rename writes and read-side
day-dir filtering; 12 regression tests added (34 lake tests total).
ADR-0003 reviewed against the implementation: layout, UTC normalization
contract, stored-order reads, quality gate and the pyarrow decision all
match the code. Issue #15 closes only when its commit lands in the final
M3 PR.

Slice #3 (issue #16, committed on `feat/m3-data-foundation`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 220 passed, 1 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: adversarial review — 5 real bugs fixed (symlink escape,
temp-name race, stray-file crashes, Windows reserved names, NULL/
undecodable raw exceptions) plus `Dataset` constructor enforcement and
13 new regression tests (47 manifest+layout tests total). Issues #15
and #16 close only when their commits land in the final M3 PR.

Slice #4 (issue #17, committed on `feat/m3-data-foundation`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 243 passed, 1 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: adversarial correctness review — 3 real bugs fixed (moomoo
books/trades symbol check + cross-venue instrument rejection, naive
fixture-timestamp UTC drift, unknown-side silent SELL) plus fail-closed
empty fixtures, per-row interval checks, fixture+row error attribution
and wheel package-data; 9 regression tests added (23 provider tests
total). Provider-isolation test proves the exit criterion at the bytes
level: shard columns are exactly the 8 canonical lake columns and
manifest coverage carries only canonical fields (caller-supplied
`source` labels and the venue in partition paths are the only remaining
identity signals, which the criterion does not claim to remove).
Issues #15-#17 close only when their commits land in the final M3 PR.

Slice #5 (issue #18, committed on `feat/m3-data-foundation`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 265 passed, 1 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: adversarial correctness review — 2 real bugs fixed
(NaN/Infinity values bricking the registry via id/serialization
divergence, duplicate IDs passing read validation) plus dup-check
ordering and root-is-a-file fail-closed; 5 regression tests added (22
experiment tests total). The clean-checkout integration test
(`test_resolve_reopens_pinned_dataset_on_clean_checkout`) proves the
first M3 exit criterion: registry → manifest → lake resolution on
copied roots re-scans shard bytes via duckdb and refuses a regenerated
(revision-2) manifest; the known same-count/same-range byte-change
blind spot is inherited from the lake gate spec (documented in
manifest.py) and revision regeneration is the honest record of change.
Issues #15-#18 close only when their commits land in the final M3 PR.

Slice #6 (issue #19, committed on `feat/m3-data-foundation`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 297 passed, 3 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: adversarial correctness review — 2 real bugs fixed
(content-blind no-op check dropping last-day corrections/retractions;
write-without-manifest failure permanently gating the dataset, now
healed on the next unchanged run) plus duckdb-exception wrapping in
`scan_series`/`read_bars`, interval-grid expected days for
`missing_days`, and empty-dataset fail-closed; 8 regression tests
added (23 ingestion tests total). The roundtrip test
(`test_ingestion_and_detection_roundtrip`) completes the second M3
exit criterion: ingested data, then a deleted interior day detected by
both the lake quality checks (gaps) and `coverage_gaps` (named missing
day), regenerated to restore the gate.

Round-2 review gate (final holistic review of the complete M3 diff):
monotonic-coverage invariant in `ManifestWriter` (refuses vanished
series, shrunk rows, moved-back end unless `rewritten`; moved-forward
start always; manifest removal is the documented override) — 6
manifest regression tests including rewritten-start-forward refusal
and override-by-removal; `Lake.read_bars` fails closed on NULL
timestamps, `_reject_symlinks` on the raw read/write surface — 3 lake
regression tests (skipped where symlinks are not permitted); the one
pre-existing growth test that implicitly blessed an interior-day loss
now keeps its start. Issues #15-#19 close only when
their commits land in the final M3 PR.

## Risks and follow-ups

- Lake layout and partition conventions are hard to change once datasets
  exist: ADR-0003 in slice #15 must be reviewed before the first real
  ingestion.
- Provider adapters must never grow credentials: the registry contract
  should make "fixture-only" the default and live/sandbox an explicit,
  reviewable flag.
- DuckDB/Parquet versions move fast; pin and record the versions used in
  manifests so "pinned dataset" stays pinned (license checklist in
  REUSE_MATRIX.md).
- Same-count/same-range byte tampering is invisible to the lake gate and
  to `coverage_gaps`: a day shard replaced with different bars of the
  same row count and same first/last timestamp compares clean because
  nothing in M3 fingerprints content (monotonic coverage and
  `_unchanged` content comparison cover writes and shrinks, not
  blind tampering). Follow-up: a content fingerprint (e.g. shard-byte
  hashes) in the manifest, validated by the gate — deliberately out of
  M3 scope.
