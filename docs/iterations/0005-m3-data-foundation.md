# Iteration 0005 — M3 Data Foundation and Experiment Registry

- Status: planned
- Started: 2026-08-07
- Completed:
- Owner: unassigned agent team
- GitHub issue: issues #12-#17 (to be opened when M2 merges to main)
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
#12-#17.

1. [#12] Normalized market-data schemas (no deps) — `Bar`, `OrderBook`
   (depth levels), `TradeEvent` pydantic models plus monotonicity,
   gap and duplication primitives. Domain layer only, no I/O.
2. [#13] Parquet/DuckDB local data lake (blocks on #12) — lake layout and
   partition convention, DuckDB-backed read/write surface, data-quality
   checks (missing/duplicated/out-of-order). Writes ADR-0003 (data lake and
   normalization contract).
3. [#14] Dataset manifests (blocks on #13) — source, timezone, revision,
   license and coverage metadata; manifest generation and validation; a
   manifest is required before a dataset is queryable.
4. [#15] Provider registry (blocks on #12) — provider contract
   (bar/order-book/trade fetch), registry keyed by `Venue`, adapters
   isolated behind the contract; fixture data only, no live credentials.
5. [#16] Experiment registry (blocks on #14) — experiment IDs linking
   dataset manifest references (pinned revision), code commit, parameters
   and metrics; reproducible from a manifest on a clean checkout.
6. [#17] Scheduled ingestion and gap detection (blocks on #14, #15) —
   scheduler driving providers into the lake, gap detection comparing
   observed coverage against manifests.

- Planner: this record (2026-08-07).
- Quant researcher: define schema invariants and quality-check semantics
  (slice #12); define what "reproducible experiment" means in practice
  (slice #16).
- Implementer: TDD each slice on its own branch (`feat/12`…`feat/17`),
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
  architecture: record them in a new ADR-0003 during slice #13.
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
  #12-#17 open when M2 merges to main; each slice then gets a branch,
  PR and verification evidence as in iteration 0003.

## Verification evidence

Pending slices. Per slice: `pytest -q`, `ruff check src tests`,
`git diff --check`, `git submodule status`; integration evidence for the
two roadmap exit criteria in slices #14 and #16.

## Risks and follow-ups

- Lake layout and partition conventions are hard to change once datasets
  exist: ADR-0003 in slice #13 must be reviewed before the first real
  ingestion.
- Provider adapters must never grow credentials: the registry contract
  should make "fixture-only" the default and live/sandbox an explicit,
  reviewable flag.
- DuckDB/Parquet versions move fast; pin and record the versions used in
  manifests so "pinned dataset" stays pinned (license checklist in
  REUSE_MATRIX.md).
