# Active Goal

- Status: active (two threads — rc4 acceptance pending, Live Market Cockpit in flight)
- Objective: obtain explicit operator acceptance of `v0.1.0-rc4` (promotion
  to v0.1.0 only after the recorded "accept RC4, promote to v0.1.0" reply),
  then deliver the Live Market Cockpit prototype (iteration 0015)
- Started: 2026-08-09
- Active iteration:
  `docs/iterations/0015-live-market-cockpit.md`
  (rc4 acceptance evidence: `docs/iterations/0014-...md` Checkpoint 10)
- Branch: `0015-live-market-cockpit`, based on `origin/main`; RC1
  publication checkpoint `0fea221` was preserved as cherry-pick `e0f9c3d`;
  RC2 is the historical tag `v0.1.0-rc2` @ `710a931` (rejected, not rewritten);
  RC3 `e83e30c` (rejected, not rewritten); RC4 `c9444ba` (awaiting acceptance)
- Pull request: one integration PR per phase, CI green, squash-merge
- Blockers: none external for deterministic demo and UI work

## Current state

`v0.1.0-rc1` is published at `fb37fcd` and remains the immutable engineering
baseline. Its clean-checkout release gate, 1,801-test suite, 53/53 golden path,
CI and Security checks passed. Human browser review did not accept it as a
product release: the server-rendered UI is minimally styled, startup state is
empty, raw APIs occupy primary navigation and no demo/provider/import path
makes the business workflow directly testable. Do not promote RC1 to
`v0.1.0`.

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
   PR #86 (641f3c6); Phases C–G per the iteration record.

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

Run `/goal`, then read this file, `PRODUCT.md`, iteration 0014, the roadmap,
relevant ADRs, Git state and GitHub state. Deliver the next RC through its
clean-checkout gate and a regenerated isolated acceptance environment; promote
only after explicit human acceptance. Implementation details and evidence
belong in the iteration record; keep this file limited to current truth and
frontier.
