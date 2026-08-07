# Iteration 0005 — M3 Data Foundation and Experiment Registry

- Status: planned
- Started: 2026-08-07
- Completed:
- Owner: unassigned agent team
- GitHub issue: issues #14-#19 (open; #12 was consumed by the M2 completion-records PR and #13 by the squash-divergence tracking issue)
- Pull request: to be opened per slice
- Roadmap milestone: M3 (see `docs/roadmap/ROADMAP.md`)

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

- [ ] A pinned dataset reproduces an experiment on a clean checkout
      (integration test spanning manifest → lake → experiment registry).
- [ ] Missing, duplicated and out-of-order observations are detected by the
      data-quality checks.
- [ ] A strategy-facing consumer cannot see which provider produced a dataset
      (provider isolation behind the registry contract).
- [ ] No live credentials, secrets or private keys appear in code, tests,
      fixtures, logs or manifests.

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
- Implementer: TDD each slice on its own branch (`feat/14`…`feat/19`),
  one slice per session.
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
  (already pinned in the `research` extra, `duckdb>=1.1,<2`, MIT). Add
  `pyarrow` for deterministic schema control and pandas interop
  (Apache-2.0). Partition convention:
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
