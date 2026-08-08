# Active Goal

- Status: active
- Objective: deliver `v0.1.0-rc2` as a populated, coherent and browser-testable
  local quantitative workstation, then obtain explicit operator acceptance
- Started: 2026-08-09
- Active iteration:
  `docs/iterations/0014-v0.1.0-rc2-interactive-product-acceptance.md`
- Branch: `0014-rc2-product-acceptance`, based on `origin/main`; RC1 publication
  checkpoint `0fea221` was preserved as cherry-pick `e0f9c3d`
- Pull request: none; solo fast lane authorizes one integration PR for RC2
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
   0 failed, golden path 53/53, clone clean; real numbers in
   `docs/release-notes/v0.1.0-rc2.md`), PR #75 squash-merged into main
   at `710a931`, tag `v0.1.0-rc2` pushed on the merge commit, CI green
   on the PR; the two gate-caught E2E interleaving defects were fixed
   and recorded (iteration 0014 Checkpoint 5). Remaining: reproduce
   the install in an isolated directory
   (`C:\Users\15492\Develop\quantmesh-rc2-acceptance`), hand the
   operator the browser acceptance checklist, and promote to `v0.1.0`
   only after explicit human acceptance.

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
relevant ADRs, Git state and GitHub state. Continue through the documented
phases until RC2 is tagged and the isolated browser acceptance checklist is
ready for the operator. Implementation details and evidence belong in the
iteration record; keep this file limited to current truth and frontier.
