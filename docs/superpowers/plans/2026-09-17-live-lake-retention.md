# Live Lake Retention Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Keep the live DuckDB replay lake bounded on startup and during a running read-only feed so a growing BTC/ETH/SOL workload cannot recreate the AWS no-swap OOM loop.

**Architecture:** Expose the existing \`LiveBuffer\` retention window as \`QUANTMESH_LIVE_RETENTION_DAYS\`, defaulting to the existing seven-day policy. Prune rows before expensive identity-index migration when the schema supports it, wire the setting into the live workstation, and run the same bounded prune on a slow feed cadence. Preserve complete L2 snapshot epochs and keep \`retention_days=0\` as the explicit unbounded opt-out for local replay tests only.

**Tech Stack:** Python 3.11+, Pydantic Settings, DuckDB, asyncio, pytest, Ruff.

**Spec:** [Iteration 0036](../../iterations/0036-staging-recovery.md), [iteration plan](../../ITERATION_PLAN.md), and AWS OOM evidence in [ACTIVE](../../goals/ACTIVE.md).

## Global Constraints

- Keep \`runtime_mode=live\`, \`paper_mode=true\`, and \`live_trading=false\`.
- Keep the workstation loopback-only and behind the existing private Tailscale Serve origin.
- Do not expose OpenD, add public ingress, change credentials, place orders, or mutate the AWS lake from tests.
- Keep default retention at seven days and preserve \`retention_days=0\` as the documented opt-out.
- Prune only by \`received_at\`; preserve complete Hyperliquid L2 snapshot epochs and current source-status rows.
- Do not fabricate historical observations or silently relabel retained observations.

---

### Task 1: Bound startup and wire the retention setting

**Files:**
- Modify: \`src/quantmesh/live/buffer.py\`
- Modify: \`src/quantmesh/settings.py\`
- Modify: \`src/quantmesh/api/workstation.py\`
- Test: \`tests/test_live_buffer.py\`
- Test: \`tests/test_workstation.py\`
- Test: \`tests/test_deployment_identity.py\`

**Interfaces:**
- \`Settings.live_retention_days: int\` reads \`QUANTMESH_LIVE_RETENTION_DAYS\`, defaults to \`7\`, and rejects negative values.
- \`LiveBuffer(root, retention_days=7)\` keeps its public signature.
- Schema-v2 lakes prune eligible rows before identity-index migration; legacy schemas still migrate first because they lack retention columns.
- The \`--live\` workstation constructs \`LiveBuffer(root=settings.lake_root, retention_days=settings.live_retention_days)\`.

- [ ] **Step 1: Write failing tests** - add a negative-setting validation test, a workstation wiring assertion, and a reopen test that removes an old row before startup completes.
- [ ] **Step 2: Verify red** - run \`python -m pytest -q tests/test_deployment_identity.py tests/test_workstation.py tests/test_live_buffer.py -k "retention or live_wires"\`; expected failure is the absent setting/default wiring/startup prune.
- [ ] **Step 3: Implement minimal guard** - move base indexes out of schema bootstrap, prune schema-v2 rows before \`_migrate_market_updates()\`, install base indexes after migration, add \`live_retention_days = Field(default=7, ge=0)\`, and pass it to \`LiveBuffer\`.
- [ ] **Step 4: Verify green** - rerun the command; existing L2 epoch and zero-retention tests must stay green.
- [ ] **Step 5: Commit** - \`git commit -m "feat: bound live lake startup retention"\`.

### Task 2: Prune on a slow running-feed cadence

**Files:**
- Modify: \`src/quantmesh/live/feed.py\`
- Test: \`tests/test_live_feed.py\`

**Interfaces:**
- \`LiveFeed.prune_if_due(now: datetime | None = None) -> int\` returns removed rows, prunes immediately on its first call, and skips until the interval elapses.
- \`LiveFeed(..., prune_interval: timedelta = timedelta(minutes=5))\` keeps the default cadence slow enough not to compete with the one-second freshness tick.
- \`LiveFeed._tick_loop()\` invokes \`prune_if_due()\` without changing delivery, status or order behavior.

- [ ] **Step 1: Write failing test** - seed an old and fresh update in a real \`LiveBuffer\`, call \`prune_if_due()\` at controlled UTC times, and assert first removes one, pre-five-minute call removes none, and post-five-minute call is eligible.
- [ ] **Step 2: Verify red** - run \`python -m pytest -q tests/test_live_feed.py -k "prune_if_due"\`; expected failure is the absent scheduler.
- [ ] **Step 3: Implement minimal cadence** - store interval/last timestamp, call attached lake \`prune()\` when due, and invoke from the tick loop; add no second writer/thread/format.
- [ ] **Step 4: Verify green** - run \`python -m pytest -q tests/test_live_feed.py -k "prune_if_due or tick"\`.
- [ ] **Step 5: Commit** - \`git commit -m "feat: prune live lake on feed cadence"\`.

### Task 3: Document and verify the recovery-to-guard handoff

**Files:**
- Modify: \`docs/iterations/0036-staging-recovery.md\`
- Modify: \`docs/goals/ACTIVE.md\`
- Modify: \`docs/ITERATION_PLAN.md\`
- Modify: \`docs/roadmap/ROADMAP.md\`
- Modify: \`docs/iterations/INDEX.md\`
- Modify: this plan

- [ ] **Step 1: Record behavior** - document the seven-day default, \`QUANTMESH_LIVE_RETENTION_DAYS\`, startup-before-index guard, five-minute cadence, and explicit \`0\` opt-out. State that AWS remains paper-only and requires re-acceptance after a reviewed PR.
- [ ] **Step 2: Verify** - run \`python -m pytest -q tests/test_live_buffer.py tests/test_live_feed.py tests/test_workstation.py tests/test_deployment_identity.py\`, \`ruff check src tests tools\`, and \`git diff --check\`.
- [ ] **Step 3: Record release gate** - record exact counts and scope; do not claim AWS acceptance until a new deployment reports exact build plus live smoke and chart checks.
- [ ] **Step 4: Commit** - \`git commit -m "docs: specify live lake retention release gate"\`.

## Final requirements checklist

- [ ] Schema-v2 lake prunes before expensive identity-index migration.
- [ ] \`QUANTMESH_LIVE_RETENTION_DAYS\` defaults to 7 and rejects negatives.
- [ ] Running feeds prune at most once every five minutes by default.
- [ ] Complete L2 snapshot epochs and source-status rows remain intact.
- [ ] Existing paper/live safety state is unchanged.
- [ ] Focused tests, Ruff and whitespace checks pass.
- [ ] AWS operator witness is recorded separately after deployment.
