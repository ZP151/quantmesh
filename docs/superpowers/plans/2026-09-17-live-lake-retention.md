# Live Lake Retention Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the live DuckDB replay lake bounded on startup and during a running read-only feed so a growing BTC/ETH/SOL workload cannot recreate the AWS no-swap OOM loop.

**Architecture:** Expose the existing `LiveBuffer` retention window as `QUANTMESH_LIVE_RETENTION_DAYS`, defaulting to the existing seven-day policy. Prune rows before expensive identity-index migration when the schema supports it, wire the setting into the live workstation, and run the same bounded prune on a slow feed cadence. Preserve complete L2 snapshot epochs and keep `retention_days=0` as the explicit unbounded opt-out for local replay tests only.

**Tech Stack:** Python 3.11+, Pydantic Settings, DuckDB, asyncio, pytest, Ruff.

**Spec:** [Iteration 0036](../../iterations/0036-staging-recovery.md), [iteration plan](../../ITERATION_PLAN.md), and AWS OOM evidence in [ACTIVE](../../goals/ACTIVE.md).

## Global Constraints

- Keep `runtime_mode=live`, `paper_mode=true`, and `live_trading=false`.
- Keep the workstation loopback-only and behind the existing private Tailscale Serve origin.
- Do not expose OpenD, add public ingress, change credentials, place orders, or mutate the AWS lake from tests.
- Keep default retention at seven days and preserve `retention_days=0` as the documented opt-out.
- Prune only by `received_at`; preserve complete Hyperliquid L2 snapshot epochs and current source-status rows.
- Do not fabricate historical observations or silently relabel retained observations.

---

### Task 1: Bound startup and wire the retention setting

**Files:**
- Modify: `src/quantmesh/live/buffer.py`
- Modify: `src/quantmesh/settings.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `deploy/aws/lightsail/deploy_release.py`
- Test: `tests/test_live_buffer.py`
- Test: `tests/test_workstation.py`
- Test: `tests/test_deployment_identity.py`

**Interfaces:**
- `Settings.live_retention_days: int` reads `QUANTMESH_LIVE_RETENTION_DAYS`, defaults to `7`, and rejects negative values.
- `LiveBuffer(root, retention_days=7)` keeps its public signature.
- Schema-v2 lakes prune eligible rows before identity-index migration; legacy schemas still migrate first because they lack retention columns.
- The `--live` workstation constructs `LiveBuffer(root=settings.lake_root, retention_days=settings.live_retention_days)`.

- [x] **Step 1: Write failing tests** - added negative-setting, workstation wiring, startup prune, and cadence tests.
- [x] **Step 2: Verify red** - the focused command failed for the absent setting, default wiring, startup prune and scheduler (`4 failed, 3 passed, 209 deselected`).
- [x] **Step 3: Implement minimal guard** - moved index DDL out of schema migration, made the public `prune()` detach secondary indexes for every sweep and rebuild them in a `finally` block, migrated legacy rows before their first sweep, added `live_retention_days = Field(default=7, ge=0)`, and passed it to `LiveBuffer`.
- [x] **Step 4: Verify green** - focused buffer/feed/workstation/settings run passed `216 passed, 6 warnings`.
- [x] **Step 5: Commit** - `71961bc feat: bound live lake retention`.

### Task 2: Prune on a slow running-feed cadence

**Files:**
- Modify: `src/quantmesh/live/feed.py`
- Test: `tests/test_live_feed.py`

**Interfaces:**
- `LiveFeed.prune_if_due(now: datetime | None = None) -> int` returns removed rows, prunes immediately on its first call, and skips until the interval elapses.
- `LiveFeed(..., prune_interval: timedelta = timedelta(minutes=5))` keeps the default cadence slow enough not to compete with the one-second freshness tick.
- `LiveFeed._tick_loop()` invokes `prune_if_due()` without changing delivery, status or order behavior.

- [x] **Step 1: Write failing test** - seeded old and fresh updates in a real `LiveBuffer`, called `prune_if_due()` at controlled UTC times, and asserted first removal, pre-five-minute skip and post-five-minute eligibility.
- [x] **Step 2: Verify red** - the focused command failed with `AttributeError: 'LiveFeed' object has no attribute 'prune_if_due'`.
- [x] **Step 3: Implement minimal cadence** - stored interval/last timestamp, called attached lake `prune()` when due, and dispatched the synchronous sweep with `asyncio.to_thread` from the tick loop; no second writer/format was added.
- [x] **Step 4: Verify green** - the combined focused buffer/feed/workstation/settings run passed `216 passed, 6 warnings`.
- [x] **Step 5: Commit** - included in `71961bc feat: bound live lake retention`.

### Review correction checkpoint — 2026-09-17

The first PR CI run (`35138573308`) exposed one historical replay fixture that
was unintentionally subject to the new seven-day default (`3526 passed, 1
failed, 56 skipped`). The fixture now opts out with `retention_days=0` because
retention behavior is covered by the dedicated tests. The automated review also
identified three runtime hazards, all corrected in the current working tree:

- persisted secondary indexes are detached during the startup DELETE and
  rebuilt even when the sweep raises;
- legacy schemas are migrated, swept, and indexed in that order;
- the five-minute sweep runs in a worker thread so the asyncio feed loop keeps
  supervisor/network delivery responsive.

The correction tests were red-first (including the simulated indexed-DELETE
failure) and are now green. The focused release gate passes `234 passed, 6 warnings` across deployment identity, workstation,
buffer, lookup, feed and replay tests; Ruff and `git diff --check` pass. Fresh
PR CI is still required before merge or AWS deployment.

The runtime sweep first counts eligible rows using the same retention predicate
and skips index churn when the lake is already within its retention window.
The deployment health gate now uses a seven-minute elapsed deadline (with a
maximum of 420 one-second attempts) so a retained lake can finish its
multi-minute startup without allowing slow connection timeouts to stretch the
rollback window indefinitely.

### Startup query correction checkpoint — 2026-09-17

The first retention deployment (`ab90f92`, PR #155) reached the new release but
failed closed during `LiveFeed` startup: the old `latest()` window query
materialized the retained `market_updates` lake and DuckDB exhausted the
1.4 GiB process limit. The service was stopped and the previously accepted
`76203e0` release was restored; no failed release was counted as deployed.

Issue [#157](https://github.com/ZP151/quantmesh/issues/157) tracks the bounded
latest-state correction. PR [#158](https://github.com/ZP151/quantmesh/pull/158)
uses a grouped `MAX(local_seq)` lookup, adds a 100,000-row regression under a
32 MiB DuckDB limit, and bounds the health loop by elapsed time. Its focused
tests and the full CI release gate must pass before the exact merged commit is
deployed and the AWS health, live-smoke and browser gates are repeated.

### Task 3: Document and verify the recovery-to-guard handoff

**Files:**
- Modify: `docs/iterations/0036-staging-recovery.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/ITERATION_PLAN.md`
- Modify: `docs/roadmap/ROADMAP.md`
- Modify: `docs/iterations/INDEX.md`
- Modify: this plan

- [x] **Step 1: Record behavior** - the source comments and this plan document the seven-day default, `QUANTMESH_LIVE_RETENTION_DAYS`, startup-before-index guard, five-minute cadence, and explicit `0` opt-out. AWS remains paper-only and requires re-acceptance after a reviewed PR.
- [x] **Step 2: Verify** - the focused command passed `216 passed, 6 warnings`; Ruff and `git diff --check` pass. The local full-suite run was stopped during the long integration section; required PR CI remains the release gate.
- [x] **Step 3: Record release gate** - PR #158 records the bounded latest-state correction and exact focused counts; AWS acceptance remains deferred until the merged commit reports exact build plus live smoke and chart checks.
- [x] **Step 4: Commit** - `0cbc2e4 docs: record live lake retention verification`.

## Final requirements checklist

- [x] Schema-v2 lake prunes before expensive identity-index migration, with
  persisted secondary indexes detached and restored around every DELETE.
- [x] `QUANTMESH_LIVE_RETENTION_DAYS` defaults to 7 and rejects negatives.
- [x] Running feeds prune at most once every five minutes by default.
- [x] Complete L2 snapshot epochs and source-status rows remain intact.
- [x] Existing paper/live safety state is unchanged.
- [x] Deployment health uses a seven-minute elapsed deadline for the measured
  slow-lake startup window.
- [x] Latest-state startup lookup stays bounded under a 32 MiB DuckDB limit.
- [x] Focused tests and Ruff pass; the full-suite gate is delegated to PR CI.
- [ ] AWS operator witness is recorded separately after deployment.
