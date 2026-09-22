# 8 GB Capacity Observation and Provider Handoff Plan

> **For agentic workers:** Follow the repository's reviewed PR workflow. This plan is an operational/documentation gate; it does not authorize a disruptive rollback, reboot, public ingress, credential change or live execution.

**Goal:** Close the 8 GB staging migration with reproducible sustained-capacity evidence, then unlock the private Moomoo/OpenD readiness slice without hiding the historical collection gap.

**Architecture:** Keep the new Tailscale-only origin authoritative while a local read-only observer samples API freshness and host capacity. Preserve the old instance and verified backups as a rollback source. Treat Moomoo/OpenD as a separate readiness boundary that cannot start until the capacity gate and private route/entitlement prerequisites are explicit.

**Tech Stack:** `tools/live_smoke.py`, the read-only freshness sampler under `output/lightsail-8gb-migration/`, Tailscale SSH, FastAPI health/live surfaces, GitHub PR #159, and the iteration/goal ledgers.

**Spec:** `docs/iterations/0036-staging-recovery.md`, PR #159, and issue #156.

## Global constraints

- Keep the private origin tailnet-only and the application bound to loopback.
- Keep `paper_mode=true` and `live_trading=false`; no order, account or strategy-promotion calls.
- Do not expose OpenD publicly, purchase an entitlement, or put credentials in chat or source control.
- Do not fabricate or silently backfill the 2026-09-17–22 collection gap.
- CI stays paused until the operator resumes it; a cancelled check cannot be used as a green merge gate.
- Do not perform rollback or reboot without a separate operator-approved Class C window.

## Review focus

- A green API shape check must not hide stale quote/candle data: each sample records source times and enforces a 60-second age ceiling.
- A healthy process must not hide host pressure: each capacity sample records available memory, swap activity, disk and restart count.
- A restart witness must not imply rollback safety: rollback preserves new observations and rechecks the exact build and safety flags.
- A later live replay must not become qualified history: the known source gap remains visible in the ledger and UI limitations.
- Local OpenD capability must not imply AWS reachability or entitlement: the private TCP route and Basic-data response are independent gates.

## Task 1: Finish the sustained observer

**Files:**
- Read: `output/lightsail-8gb-migration/observer-manifest.json`
- Read: `output/lightsail-8gb-migration/live-smoke-24h.log`
- Read: `output/lightsail-8gb-migration/freshness-24h.jsonl`
- Read: `output/lightsail-8gb-migration/host-capacity-24h.log`

- [x] Start five-minute read-only smoke, freshness and host-capacity observers at the new origin.
- [ ] Let the observer reach its recorded 24-hour end time.
- [ ] Verify every freshness record has `freshness_ok=true`, exact build `33aa0521`, paper mode enabled, live trading disabled, all three instruments real, and quote/candle age at or below 60 seconds.
- [ ] Verify the host log contains no automatic restart, OOM evidence, swap-in or swap-out, and review memory/disk/latency trend rather than relying on one sample.

## Task 2: Record the capacity checkpoint

**Files:**
- Modify: `docs/iterations/0036-staging-recovery.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/ITERATION_PLAN.md`
- Modify: `docs/roadmap/ROADMAP.md`

- [ ] Append the observer end time, sample count, maximum quote/candle age, maximum health/state latency, restart count, memory range, swap activity and disk range.
- [ ] Keep the September 17–22 source gap and the old 90-second shutdown timeout as explicit limitations.
- [ ] Link the final evidence and state whether rollback/reboot were completed or deliberately deferred.

## Task 3: Run disruptive recovery checks only in an approved window

**Files:**
- Read: `deploy/aws/lightsail/quantmesh-staging.service`
- Read: `deploy/aws/lightsail/deploy_release.py`
- Read: `docs/agents/review-policy.md`

- [ ] Before the window, capture the new host's exact build, source times, paper/live flags, archive path and current observer checkpoint.
- [ ] Stop the new collector, retain its later observations, enable/start the retained old service, and verify the old private origin's exact health and safety flags. Do not delete the new data.
- [ ] Restore the new collector, verify the new origin and exact build again, and record the interval where the new feed was intentionally paused.
- [ ] Reboot the new host only if the operator has approved the interruption; after boot, repeat private Serve, health, smoke and freshness checks.

## Task 4: Unlock Moomoo/OpenD readiness

**Files:**
- Read: `https://github.com/ZP151/quantmesh/issues/156`
- Read: `tests/test_moomoo_opend.py`
- Read: `src/quantmesh/moomoo/`

- [ ] Prove a private route from AWS `100.86.41.64` to the licensed OpenD host without public exposure. The current probe to Windows `100.91.234.68:11111` is `CLOSED` and therefore fails this gate.
- [ ] Run only the read-only capability and quote/history probes; a Basic-data rejection remains `unavailable`.
- [ ] During an open session, capture at least two distinct provider timestamps for AAPL and NVDA, with explicit `real`, `delayed`, `closed` or `unavailable` labels.
- [ ] Only after readiness passes, write the exact-file test-first implementation plan and a reviewed PR. Keep five-second polling explicit; it is not native tick push.

## Release gate

- [ ] Resume CI only when the operator's capacity window is ready; wait for a green check on PR #159 before merging its documentation.
- [ ] After any runtime change, deploy only the merged exact SHA and repeat private health, 13-check smoke, real chart paths, restart and freshness evidence.
- [ ] Do not mark iteration 0036 complete while the sustained observation, rollback/reboot decision, historical-gap record or safety flags are unresolved.
