# Active Goal

- Status: active (iteration 0015 acceptance hardening complete; integration
  and a replacement RC remain)
- Objective: integrate the acceptance hardening from issue #94, run the
  release gate on the merged tree, and publish a replacement release
  candidate for explicit operator acceptance. `v0.1.0-rc4` must not be
  promoted because the accepted fixes are newer than that immutable tag.
- Started: 2026-08-09
- Active iteration:
  `docs/iterations/0015-live-market-cockpit.md`
  (rc4 acceptance evidence: `docs/iterations/0014-...md` Checkpoint 10)
- Branch: `0015-acceptance-hardening`, based on the completed Phase G tree; RC1
  publication checkpoint `0fea221` was preserved as cherry-pick `e0f9c3d`;
  RC2 is the historical tag `v0.1.0-rc2` @ `710a931` (rejected, not rewritten);
  RC3 `e83e30c` (rejected, not rewritten); RC4 `c9444ba` (awaiting acceptance)
- Pull request: one acceptance-hardening integration PR, CI green,
  squash-merge; no doc-only follow-up PR
- Blockers: none for integration; final `v0.1.0` promotion remains an explicit
  operator gate

## Current state

Iteration 0015 Phase G is merged, but the 2026-08-10 operator-authorized
browser review rejected its first acceptance result. The live detail route
did not hydrate the latest snapshot, live pages emitted demo-only requests and
copy, smoke checks accepted unhealthy/malformed contracts, and timestamp-only
replay could not select between same-timestamp appends.
[Issue #94](https://github.com/ZP151/quantmesh/issues/94) contains the bounded
hardening work and evidence. The repaired candidate passes the targeted
backend, frontend, live-smoke, desktop and 390 px browser checks.
Because these fixes are newer than `v0.1.0-rc4`, RC4 remains historical and
must not be promoted; publish and accept a replacement RC from the integrated
tree.

## Immediate frontier

1. ~~Approve ADR-0013 through implementation evidence~~ (done, checkpoint
   bfa097c): the SPA spike is served from the packaged bundle with the
   rollback switch, `/api` double mount and a green 1811-test suite.
2. ~~Build deterministic `--demo` runtime assembly with provenance, freshness,
   reset/replay and representative cross-market/research/paper/risk/audit
   data.~~ (done, Phase B boundary): `src/quantmesh/demo/` seeds a labeled
   deterministic root under an operator-selected path — real fixture-provider
   market data with a reproducible cross-market cluster, forecast/report/
   experiment/promotion/alert/citation/audit surfaces through the public
   services, byte-identical replay and marker-guarded reset, provenance
   contract in `/api/demo/status` and response headers; `tests/test_demo.py`
   18/18 green.
3. ~~Deliver one browser tracer bullet from market evidence to paper fill,
   portfolio, risk and audit before migrating the remaining legacy pages.~~
   (done, Phase C boundary): the SPA shell, command palette and responsive
   navigation are live, the full research→paper-order→fill→position/P&L→
   risk/audit loop was verified over HTTP end to end (including kill-switch
   409, idempotent replay and reset), all 12 legacy routes 302 to `/app`,
   and the backend suite is 1,840/1,840 green.
4. ~~Add one public-data connector path and validated file import~~ (done,
   Phase D boundary): `src/quantmesh/demo/datalink.py` adds a 5-connector
   diagnostics panel, a credential-free testnet-pinned Hyperliquid l2Book
   path with rate-limit retry, `.datalink` caching, provenance and labeled
   synthetic fallback, and CSV/JSON/Parquet import with preview, mapping,
   per-row rejection reasons and `operator-import` manifests — missing
   software/credentials/network are instructive states, never blank pages.
   `tests/test_datalink.py` 20/20 green; live smoke on 8794 verified the
   fallback path, rejections and reset isolation.
5. ~~Complete bounded design, accessibility, E2E and clean-checkout
   verification~~ (done, Phase E boundary): 18/18 frontend unit tests
   (vitest), 5/5 SPA Playwright E2E, Impeccable one-pass detector
   `[]` with a programmatic visual audit clean at 28 route×viewport
   combos (0 overflow/clip/contrast/focus failures), real Tab-press
   keyboard walks, WCAG 2.2 AA contrast, non-color status cues,
   `prefers-reduced-motion` support, compact/desktop/tablet layouts,
   and the frontend build (`npm ci` → bundle-freshness check →
   vitest) added to the clean-checkout release gate; release notes
   (EN + zh-CN) written. Evidence in iteration 0014 Checkpoint 4.
6. ~~Run the full release gate from a clean checkout, merge the single
   RC2 PR, tag the verified merge commit `v0.1.0-rc2`~~ (done, Phase F):
   gate run 4 PASSED on HEAD `737f8c9` (14/14 steps, 1865 tests /
   0 failed, golden path 53/53, clone clean), PR #75 squash-merged
   into main at `710a931`, tag `v0.1.0-rc2` pushed, isolated install
   reproduced and the workstation live on 8766. **The operator then
   rejected RC2 (2026-08-09): the tag claimed `v0.1.0-rc2` while the
   package still reported `0.1.0rc1` in pyproject.toml, `__init__.py`
   and the pinned test — the gate could not see it because the test
   pinned rc1. Promotion to `v0.1.0` is forbidden.** The published rc2
   tag is the historical record and is not rewritten (iteration 0014
   Checkpoint 6).
7. ~~Fix the version drift and release `v0.1.0-rc3`~~ (done, rc3
   cycle, iteration 0014 Checkpoints 6–8): the three version
   locations read `0.1.0rc3`; new gate step
   `tools/check_release_version.py` asserts Git tag == package
   version == newest release notes (fails on the old rc2 commit,
   passes at the rc3 tag; PEP 440 tag comparison fixed post-tag,
   Checkpoint 7); gate run 5 PASSED 15/15, PR #80 merged, tag
   pushed; gate run 6 PASSED 15/15 on the exact tagged tree
   `e83e30c` after the checker fix; the isolated acceptance
   environment was regenerated from the tag (rejected rc2 build and
   workstation removed) and all four rejection items re-verified
   (`git describe` → `v0.1.0-rc3`, pip show → `0.1.0rc3`, import →
   `0.1.0rc3`, `/api/health` → `0.1.0rc3`); golden path 53/53 on the
   rc3 tree; workstation live at http://127.0.0.1:8766/app/ (PID
   41852) with `OPERATOR-ACCEPTANCE.md` at the acceptance root.
   **RC3 acceptance was subsequently re-run by an authorized automated
   browser review and found two product defects: Forecasts exposed neither a
   probability nor a calibration explanation, and the SPA chrome displayed
   `rc2` despite API/package RC3 metadata. RC3 must not be promoted.**
8. ~~Fix the two acceptance-surface defects, package a new RC, and re-run
   the clean-checkout release gate before asking for human sign-off.~~
   (done, rc4 cycle, iteration 0014 Checkpoint 10): the operator's locally
   fixed candidate (commit `8f462de`, both defects re-verified) was
   packaged as `v0.1.0-rc4`; gate run 1 PASSED 15/15 on the branch head,
   PR #83 squash-merged at `c9444ba`, tag `v0.1.0-rc4` pushed with the
   tag==version invariant verified at the tag; gate run 2 failed on the
   port-8643 environment flake (5 E2E setup errors, 0 product failures),
   gate run 3 PASSED 15/15 on the exact tagged tree; the isolated
   acceptance environment was regenerated from the tag (fresh clone +
   venv + install: import `0.1.0rc4`, golden path 53/53); the tag-build
   workstation is live at http://127.0.0.1:8766/app/ (PID 13196) with
   `OPERATOR-ACCEPTANCE-rc4.md` at the acceptance root. **Promotion to
   `v0.1.0` remains forbidden until the operator replies "accept RC4,
   promote to v0.1.0".**
9. Deliver iteration 0015 — Live Market Cockpit (operator `/goal`,
   2026-08-09): a local, read-only, replayable multi-venue real-time
   research workstation for a bounded watchlist (4–8 Hyperliquid perps,
   read-only Polymarket/Kalshi, Moomoo OpenD when locally available),
   built on the `MarketUpdate` contract, venue supervisors, DuckDB replay
   lake, local WS/SSE feed, cockpit screens, deterministic quote fence —
   all venues read-only, no credentials, no autonomous execution.
   Phase A (ADR-0014, contract, buffer, fixture WS server) merged via
   PR #85 (f48d4fd); Phase B (supervisor protocol + Hyperliquid venue
   supervisor, drill-tested 84/84 on the live surface) merged via
   PR #86 (641f3c6); Phase C (feed + cockpit screens + browser E2E,
   1983/1983 backend, 5/5 E2E) merged via PR #87 (553e944); Phase D
   (deterministic quote fence — provenance/age/sequence gates with
   explicit rejections over paper-order consumption, demo unchanged;
   2003/2003 backend, ruff clean) merged via PR #89; Phase E
   (read-only Polymarket + Kalshi public WS supervisors and the
   prediction comparison board — implied probability/bid-ask/spread/
   depth/liquidity per venue, signed cross-venue diff, honest
   distinct states; 71/71 board drills, 226/226 regression, 47/47
   vitest, 5/5 browser E2E on port 8646) landed on branch
   `0015-phase-e`; Phase F (Moomoo OpenD — poll-driven read-only venue
   supervisor + transport, METRICS last/volume + TRADE ticks with
   venue sequences and side, the venue-clock gate so a closed market
   or delayed feed is never labeled real, honest unavailable/
   disconnected/stale ladder; 13/13 F drills, 2066/2066 regression,
   ruff clean) landed on branch `0015-phase-f`; Phase G (replay
   determinism + live smoke drill + gate + acceptance, 8/8 replay
   drills including the TZ-determinism fix, 20/20 smoke checks E2E-
   verified healthy and degraded, full E2E 31/31 + frontend gate
   green, release gate 15/15 on the branch head `90c1d9c`, isolated
   acceptance env with degraded-state live station verified honestly
   unavailable and the smoke drill PASS/FAIL both proven) landed on
   branch `0015-phase-g` and merged into main via PR #92 (`e7ade9d`);
   **Phase G complete — its original self-acceptance record is preserved in
   `OPERATOR-ACCEPTANCE-0015.md` but superseded by the operator-authorized
   review in item 10.**
10. Integrate the post-Phase-G acceptance hardening
    ([issue #94](https://github.com/ZP151/quantmesh/issues/94)): hydrate
    instrument details from `/api/live/state`, make shell/overview behavior
    runtime-aware, strengthen the read-only smoke contract, add an inclusive
    `through_local_seq` replay boundary, rebuild the packaged SPA, and retain
    browser evidence. The repaired candidate passed 82 targeted backend
    tests, 48 frontend tests, 5/5 live browser E2E, bundle freshness, Ruff,
    live smoke 14/14, desktop browser review with zero console errors, and a
    390 px walk with no horizontal overflow. Next: merge the single
    integration PR, run the clean-checkout release gate, and cut a replacement
    RC; do not promote RC4.

## Standing authority

Use the solo-developer fast lane in iteration 0014: one integration branch,
tested commits at phase boundaries and one final PR. Do not pause for routine
issue creation, branch pushes or merging a green RC2 PR. Preserve protected
main, branch from `origin/main`, never force-push, and record every checkpoint
in the iteration file. Major language, database, financial representation or
process-boundary changes still require an ADR.

## External and safety gates

Moomoo OpenD simulated access and Hyperliquid testnet drills are optional
operator-dependent checks. Real-money orders, mainnet wallet signing,
credentials, paid infrastructure and AI order authority require separate
explicit approval and are outside this goal. Demo and imported data must be
labeled and isolated from non-demo operator state.

## Resume instruction

Run `/goal`, then read this file, `PRODUCT.md`, iteration 0015 Checkpoint H1,
the roadmap, relevant ADRs, Git state, issue #94 and the integration PR. Merge
only with green CI, then deliver a replacement RC through the clean-checkout
gate and a regenerated isolated acceptance environment; promote only after
explicit human acceptance. Implementation details and evidence belong in the
iteration record; keep this file limited to current truth and frontier.
