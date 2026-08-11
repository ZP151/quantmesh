# Active Goal

- Status: `v0.1.0` released; iteration 0020 active
- Objective: first decide, with reproducible evidence, whether FinRL-X and/or a
  process-isolated NautilusTrader boundary can replace substantial engine work;
  then deliver the integrated instrument decision workspace without changing
  paper-only execution authority.
- Started: 2026-08-11
- Completed release: `v0.1.0` at `5a7f660` (PR #106)
- Next iteration: `docs/iterations/0020-research-to-paper-loop.md`
- Tracking issue: [#107](https://github.com/ZP151/quantmesh/issues/107)
- Integration branch: `0020-research-to-paper-loop`
- Baseline: released `main` at `5a7f660`; all release candidates remain
  immutable historical tags.
- Next delivery: `v0.1.1-rc1`, clean-checkout gate and isolated operator
  acceptance. Promotion remains an explicit operator gate.
- Blockers: none at planning time. Every framework, chart and forecasting
  dependency must pass license, packaging, Windows, determinism, leakage and
  evidence gates before adoption.

## Iteration 0020 planning checkpoint — 2026-08-11

The operator asked to prefer coherent upstream frameworks over assembling
isolated features. The durable review is
`docs/architecture/framework-adoption-review-2026-08-11.md`:

- FinRL-X/FinRL-Trading is the first permissive, Python, end-to-end research
  workflow candidate.
- NautilusTrader is the closest event-driven execution architecture and has
  relevant Hyperliquid, Polymarket and IB adapters, but remains an isolated
  comparator because LGPL-3.0 and its process boundary require an ADR.
- Hummingbot Dashboard, vn.py, LEAN, Freqtrade and OpenBB remain bounded
  companions or references rather than a replacement product shell.
- No reviewed project covers QuantMesh's full equities + crypto + prediction
  markets + evidence + forecast UI + deterministic paper-control target.

The immediate frontier is Phase 0 of iteration 0020: reproduce one pinned NVDA
workflow in FinRL-X, a narrower Hyperliquid replay/sandbox comparison in
NautilusTrader, score both, and record an adoption/rejection ADR before feature
implementation expands. The shared Codex/Claude execution contract is
`docs/agents/cross-agent-execution.md`.

## Iteration 0020 implementation checkpoint — 2026-08-11

The executable plan is
`docs/superpowers/plans/2026-08-11-integrated-instrument-workspace.md` and is
the task-level source of truth. It defines 16 test-first tasks with fresh
implementation/review boundaries, exact upstream pins, one integration branch
and one final PR. Task completion and exact verification evidence must be
mirrored into iteration 0020 and this file before every pushed checkpoint.

Task 1 completed at `e251d8c`: the owned `FrameworkRunEvidence` and
`FrameworkScore` contracts, immutable exact pins, and a deterministic,
manifest-gated 420-session NVDA fixture passed 14 focused cases, Lake/Manifest
regression and Ruff. Fresh review found no Critical or Important issue; one
manifest-byte comparison Minor is parked for the final review.

Task 2 completed through `5bdf32d`. The real pinned FinRL-X run is retained as
an honest failed evaluation: checkout and Apache-2.0 license verification
passed, but upstream dependency `bt` requires Microsoft Visual C++ 14.0+ on
this CPython 3.13 Windows host. No runtime dependency was admitted. The fake
adapter and hardened controller passed 50/50 focused tests; four independent
review rounds closed all Critical/Important findings around process, path,
chronology, leakage and portable evidence boundaries.

Task 3 completed through `9d416d6`. The pinned NautilusTrader comparator is
deterministic and passes installation, license, chronology, leakage and
paper-only gates, but honestly fails `contract_mapping`: MARGIN collateral
semantics differ from QuantMesh cash accounting and the pinned sandbox client
has no standalone offline replay API. It remains an LGPL process-isolated
comparator and is not a release dependency. Final scoped review found no open
Critical or Important issue.

Task 4 is complete through `46a0669` and independently accepted with zero
Critical, Important or Minor findings.
The generated scorecard gives both candidates an honest `0.0` total because
both committed evidence files lack soft-score inputs. It rejects FinRL-X after
the `bt`/MSVC install failure and retains NautilusTrader only as an isolated
comparator after its deterministic contract mismatch. ADR-0015 records zero
copied upstream files, zero release dependencies and the native QuantMesh
workspace fallback. Strict evidence and scorecard validation rejected 28/28
independent malformed/tampered probes, the Task 1-4 compatibility run passed
173/173 tests, and the clean release-closure license gate exited zero. Task 5
(venue-aware historical data contracts and service) is complete through
`036d89c`: independent review closed all four first-round findings with zero
remaining Critical, Important or Minor issue. Task 6 (historical/live-tail API)
is complete through `629d3c8`: 211 focused tests, independent transaction
fault probes and the 100-update/eight-writer exactly-once drill passed, with
zero remaining Critical, Important or Minor issue. Task 7 (truthful multi-
horizon forecast artifacts) is now the active frontier.
Lightweight Charts remains a candidate until its later explicit admission gate.

## Current state

Iteration 0015 live-cockpit hardening is merged at `c47b83d` (PR #95), and the
replacement candidate `v0.1.0-rc5` is published at `cc8bde8` (PR #96). The
baseline has a deterministic demo workstation, live read-only cockpit,
Hyperliquid/Polymarket/Kalshi/Moomoo connector surfaces, replay lake,
provenance/freshness contracts and paper-only order authority. PR #100 merged
at `5069d1b`, completing global SPA localization; the old RC6 station remains
a historical pre-0017 build and must not be used to verify the fix.

The operator authorized immediate continuation after that merge. Therefore we
will not cut an interim localization-only RC: the next candidate will include
the bounded iteration-0019 live-research improvements. RC6 remains immutable;
formal promotion still requires a clean tagged-tree gate and explicit operator
acceptance.

Iteration 0019 was squash-merged by PR #101 at `298825b` on 2026-08-10. It
delivered the unified bounded live board, evidence/metric panels, compact
charts including watchlist sparklines, recorded replay and truthful degraded
state drills. Final evidence: backend `2131 passed, 3 skipped` from an
external-temp run, SPA E2E `5 passed`, Ruff clean, and the GitHub CI run for
the merged PR green. The fixed SPA E2E fixture reserves an OS-selected socket,
eliminating the shared-runner fixed-port race caught by CI.

## rc7 cycle

Released `v0.1.0-rc7` at `c1ea037` (PR #103), verified on the tagged tree:

| Step | Result |
|------|--------|
| clone current commit | PASS (1.9 s) |
| release version consistent (metadata, notes, tag) | PASS (0.2 s) |
| fresh venv | PASS (16.3 s) |
| install `.[dev,research,e2e]` | PASS (241.6 s) |
| ruff check src tests tools | PASS (3.0 s) |
| license review (closure contract) | PASS (2.2 s) |
| audit venv (isolated tooling) | PASS (14.2 s) |
| install pip-audit (isolated) | PASS (34.5 s) |
| pip-audit over requirements-audit.txt | PASS (12.7 s) |
| npm ci (frontend deps) | PASS (49.6 s) |
| frontend bundle current (build_frontend --check) | PASS (55.3 s) |
| frontend unit tests (vitest 73/73) | PASS (39.1 s) |
| full pytest suite (2134) | PASS (446.6 s) |
| golden path 53/53 | PASS (3.4 s) |
| clean-checkout proof | PASS (0.3 s) |

Workstation tested once from the tagged tree: `pip show quantmesh` → `0.1.0rc7`,
`import __version__` → `0.1.0rc7`, `/api/health` → `0.1.0rc7`, golden path
53/53 on the isolated install.

**RC7 is superseded by RC8 as the acceptance candidate.** RC7's documented
`--port` command was not accepted by its CLI; RC8 adds the tested loopback-only
override and its clean-checkout gate passed 15/15 on `085d0ad` (full pytest
353.2 s, golden path 53/53, browser cache present). The operator delegated
acceptance and promotion after the corrected candidate's automated browser
walk. Do not enable live-market execution as part of promotion.

## v0.1.0 promotion

The accepted RC8 line was promoted through the dedicated `release/v0.1.0`
tree. The formal clean-checkout gate passed 15/15 on `a317157`: version
consistency, full release extras, Ruff, license review, pip-audit, frontend
bundle and Vitest, full pytest (373.7 s), golden path and clean-checkout proof.
The final `v0.1.0` tag must point only at the green merged promotion commit;
all market access remains read-only or paper-only.

## Current frontier

1. Start iteration 0020 from the released `v0.1.0` baseline and record the
   implementation checkpoints in
   `docs/iterations/0020-research-to-paper-loop.md`.
2. Establish venue-aware instrument identity and a historical OHLCV/manifest
   API before replacing the current instrument sparkline.
3. Spike TradingView Lightweight Charts behind a local adapter; admit the
   dependency only after license/NOTICE, package, a11y, compact-width and
   deterministic browser checks pass.
4. Deliver the observed chart first, then transparent multi-horizon forecast
   baselines and uncertainty gates, then the contextual paper decision rail.
5. Cut `v0.1.1-rc1` only after complete lineage, safety and clean-checkout
   evidence; wait for explicit operator acceptance before final promotion.

## Historical delivery frontier

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
10. ~~Integrate the post-Phase-G acceptance hardening
    ([issue #94](https://github.com/ZP151/quantmesh/issues/94)): hydrate
    instrument details from `/api/live/state`, make shell/overview behavior
    runtime-aware, strengthen the read-only smoke contract, add an inclusive
    `through_local_seq` replay boundary, rebuild the packaged SPA, and retain
    browser evidence. The repaired candidate passed 82 targeted backend
    tests, 48 frontend tests, 5/5 live browser E2E, bundle freshness, Ruff,
    live smoke 14/14, desktop browser review with zero console errors, and a
    390 px walk with no horizontal overflow. The first PR CI run also exposed
    and fixed a fixed-port E2E bootstrap race (2,085 tests had passed before
    the setup-only collision; the repaired workstation E2E is 16/16). The
    single integration PR merged at `c47b83d` (PR #95), and the
    clean-checkout release gate on the merged tree PASSED 15/15 (pytest
    761.4 s, golden path 53/53; a first gate attempt was killed by the host
    mid-pytest with zero test failures — the passing run was detached and
    used the repo venv interpreter, since the version-consistency step runs
    before the gate's own venv exists). The replacement candidate
    `v0.1.0-rc5` is being cut: version metadata and tests pinned, release
    notes (EN + zh-CN) written, then tag, tagged-tree gate run and a
    regenerated isolated acceptance environment. Do not promote RC4; do not
    promote `v0.1.0` without the recorded operator verdict.~~ (done: PR #95
    merged at `c47b83d`; replacement RC5 tagged at `cc8bde8`; the rc5
    tagged-tree gate run is recorded in iteration 0015 Checkpoint H2; RC5
    awaits operator acceptance.)
11. Deliver iteration 0016 — Global Preferences and Workstation Continuity:
    persist English/Simplified Chinese language and system/light/dark theme
    preferences, apply them to the shell/navigation/command palette/settings,
    preserve first-paint theme state, add responsive/accessibility regression
    tests, rebuild the packaged SPA, then integrate through one tested PR.
    The single integration PR (#97) merged at `3514c18` with CI green, and
    the rc6 candidate is being cut from the merged tree (version metadata
    and tests pinned `0.1.0rc6`, release notes EN + zh-CN written; branch
    `0016-rc6`). After the branch-head gate: tag `v0.1.0-rc6`, run the
    tagged-tree gate, regenerate the isolated acceptance environment
    (superseding the rc4 build) and prepare the operator checklist. RC5
    remains immutable. Detailed evidence is in
    `docs/iterations/0016-global-preferences.md`.
12. Deliver iteration 0017 — roadmap vertical slice 1, domain-screen
    translations: extend the reviewed en / 简体中文 preference layer to
    all 12 scoped domain screens (Overview, Markets, Watchlist, Trading
    Orders/Positions/P&L, Order form, Risk, Research
    Experiments/Promotions/Forecasts, Connectors, Imports, Audit, Live
    Cockpit watchlist + instrument detail + freshness labels) via a
    standalone `screen.*` message table (`lib/messages.ts`), keeping
    every English string byte-identical, API-facing values raw, and
    provenance/freshness/paper-safety wording byte-exact in both
    locales. Prediction comparison, Ops kill-switch/enablement and
    legacy Jinja pages stay on the reviewed English fallback (safety-
    critical copy awaits explicit review). Extracted in 5 tested
    batches on one branch (`0017-translations`); locale coverage is now
    pinned by compile-time (`MessageKey` as-const) and runtime tests
    (en/zh-CN key parity, placeholder parity, zh-CN render smoke).
    Verification: tsc clean, oxlint 0, vitest 57/57, build clean,
    ruff clean, pytest 2116 passed (incl. browser E2E), clean-checkout
    release gate 15/15 on the branch head `c913df0`, CI green, PR #99
    squash-merged into main. No version bump; `v0.1.0-rc6` unchanged
    and still awaiting operator acceptance. Detailed evidence in
    `docs/iterations/0017-domain-translations.md`.
13. ~~Deliver iteration 0018 — global localization completion: translate the
    remaining Prediction, Kill switch, Enablement, NotFound, Loading and shell
    accessibility/provenance copy using the shared en/zh-CN dictionary; keep
    API-facing values and server safety verdicts semantically raw; rebuild the
    package-served SPA; merge one tested PR; then cut and verify a replacement
    RC because RC6 is immutable. Evidence belongs in
    `docs/iterations/0018-global-localization.md`.~~ (done: PR #100 merged at
    `5069d1b`; replacement candidate is deliberately deferred to include 0019.)
 14. ~~Deliver iteration 0019 — the bounded live research surface: quote/book/trade and
     prediction-market metrics, freshness/sequence semantics, compact charts,
     replay and degraded-stream drills. Reuse existing normalized contracts,
     lake, cockpit primitives and smoke fixtures; keep all venues read-only,
     bounded and provenance-first. Detailed scope is in
     `docs/iterations/0019-live-research-surface.md`.~~ (all four scope items
     merged by PR #101 at `298825b`: unified live board with
     filter model, research-grade metrics, compact charts including price-trend
     sparkline, recorded replay workflow with operator drills and browser
     acceptance; 6 slices, full suite 2134 backend + 73 frontend, E2E 7/7,
     SPA bundle current. The final GitHub CI is green after the E2E socket-race
     fix; all behavior remains read-only or paper-only.)

## Standing authority

Use the solo-developer fast lane: one integration branch, tested commits at
phase boundaries and one final PR. Do not pause for routine issue creation,
branch pushes or merging a green PR. Preserve protected main, branch from
`origin/main`, never force-push, and record every checkpoint in the iteration
file. Major language, database, financial representation or process-boundary
changes still require an ADR.

## External and safety gates

Moomoo OpenD simulated access and Hyperliquid testnet drills are optional
operator-dependent checks. Real-money orders, mainnet wallet signing,
credentials, paid infrastructure and AI order authority require separate
explicit approval and are outside this goal. Demo and imported data must be
labeled and isolated from non-demo operator state.

## Resume instruction

Run `/goal`, then read this file, `PRODUCT.md`, `docs/product-strategy.md`,
iteration 0020, the framework adoption review, the cross-agent execution
contract, the roadmap, relevant ADRs and current Git/CI state. Start with the
framework bake-off and its tool-neutral tracked implementation plan. Only after
the ADR gate, continue the integrated workspace with the selected adapter or
the recorded native fallback: venue-aware historical chart data, truthful
forecast artifacts and operator-confirmed paper-decision lineage. Use one
tested integration PR, mirror every phase checkpoint for Codex/Claude recovery,
and cut `v0.1.1-rc1` only from merged `main` after the clean-checkout gate. Do
not enable real-money, mainnet or AI order authority, and do not promote the
candidate without explicit human acceptance.
