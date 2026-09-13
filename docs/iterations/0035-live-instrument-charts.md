# Iteration 0035 — Real charts from Markets and Watchlist

- Status: actual AWS user-loop ACCEPTED on 2026-09-13 12:07 UTC after sustained
  recovery; documentation closeout in progress. Earlier failures remain below.
- Issue: [#144](https://github.com/ZP151/quantmesh/issues/144).
- Original branch: `codex/0035-live-instrument-charts`, from `origin/main@2a50565`.
- Follow-up branch: `codex/0035-chart-acceptance`, from merged `origin/main@90fe577`.
- Plan: `docs/superpowers/plans/2026-09-12-live-instrument-charts.md`.
- Recovery: `docs/superpowers/plans/2026-09-13-sustained-live-chart-recovery.md`.
- Latest deployment: `76203e03476b120e149a0c06d9932849bb4d8e14` (PR #149).
- [Compact acceptance evidence](evidence/0035/aws-sustained-witness-summary.json)
  and [operator steps](../runbooks/live-chart-acceptance.md).

## User action and measurable outcome

From Markets or Watchlist on the existing private AWS workstation, open BTC,
ETH or SOL and inspect a full-size price line built from actual Hyperliquid
observations. Default to the current-day window and line mode, retain candle
switching, and show the current one-minute close update and a later candle
append without reload. Reload must retain actual recorded coverage. Observe
source times and coverage; do not imply complete-day or multi-month history.

## Planner and investigation evidence

The operator explicitly requested continued development and real streaming
charts through the previous Markets/Watchlist entry points. This existing
chart/data path is a bounded vertical slice before Moomoo readiness work.

Actual AWS `e185c3b` inspection: Markets lists BTC/ETH/SOL with empty marks and
outdated synthetic/demo descriptions. Watchlist's decision inbox is empty.
BTC click-through falls back to CockpitDetail with only a small four-close
chart instead of the existing full instrument chart.

Independent backend diagnosis: Hyperliquid subscribes 1m candles, but
LiveHistoryService permits only preferred/coarser resolution (minimum 5m for
1D), so real collected candles cannot satisfy any chart range. The default
workspace range is 6M. Existing replay/history composition and chart renderer
can be reused; no new provider, chart package or data-plane subsystem.

## Quant Researcher / design

- Permit an explicitly labelled Hyperliquid 1m replay fallback for 1D only when
  no preferred/coarser series exists. Preserve manifest preference, sequence,
  candle-open continuity, source/receipt bounds, gap/disconnect barriers and
  the minimum two-interval requirement. Other ranges retain their contract.
- Render actual candle closes (including the changing current candle), with
  line/candle controls and real coverage/interval/source labels. Short recorded
  coverage is not a full day, trusted history, forecast or promoted strategy.
- In live mode, Markets and Watchlist expose the configured feed instruments,
  actual quotes and freshness through shared existing live utilities. Keep
  registered decision watches intact and distinguish them from feed coverage;
  do not silently create favorites or paper decisions.
- No synthetic fallback, fabricated historical points or generated volume.
  Missing/collecting history has an explicit state. Existing stale/disconnect
  semantics apply to charts and source status; recovering cannot bridge a gap.

## Acceptance

- [x] Backend RED/GREEN covers actual 1m replay through history/workspace APIs,
  preferred resolution, revisions, append, reload, gaps and unavailable ranges.
- [x] Both Markets and Watchlist expose BTC/ETH/SOL chart entry points in live
  mode with actual quote provenance/freshness and accurate non-demo wording.
- [x] Default live chart is 1D/line; explicit URL choices and demo behavior remain
  intact. Current candle changes without reload; a new minute appends a point.
- [x] Keyboard, desktop/mobile and accessible chart table/attribution verified locally.
- [x] Final source checks, bounded independent review and required CI pass;
  integrate through PR and verify the exact approved AWS deployment.
- [x] Actual AWS navigation/chart update/reload witness is recorded separately
  from controlled disconnect/recovery tests. Paper true/live false; no orders.
- [x] Update roadmap/ACTIVE and retain Moomoo/OpenD readiness as next frontier.

## Boundaries and authority

Existing user approval covers this readonly application iteration and the
existing private AWS update after review and tests. No new resources, public
access, purchased entitlement, credentials, order or trading authority. Keep
#135 firewall acceptance and the 0021 soak independent. Moomoo still needs an
existing licensed OpenD host, approved private AWS route and actual entitlement;
AAPL/NVDA real charts cannot be claimed before those observations exist.

## Role checkpoints

Planner and Quant Researcher outputs above; independent backend investigator
confirmed the production/test interval mismatch. Implementation, Reviewer and
Verifier outcomes will be appended at their demonstrable slice boundaries.


## Implementation checkpoint — source/test boundary

- **Implementer / backend:** reproduced production-shaped 1m failure: 6 failed /
  16 passed. The existing resolution contract also required a narrow matching
  exception: contract RED 1 failed / 9 passed. It now requires exact replay
  identity and actual coverage; no manifest/quality qualification or general
  finer-resolution relaxation. Policy is recorded in ADR 0023.
- **Verifier / controller:** current-worktree history/workspace selection
  (`tests/test_live_history.py`, `tests/test_instrument_history.py`,
  `tests/test_instrument_workspace_api.py`) passed 131 tests in 11.59s; one
  existing Starlette deprecation warning. Includes revision/append/reopen,
  three symbols, manifest/coarser preference and no bridging on recovery.
- **Implementer / frontend:** entry/default RED 3 failed / 27 passed. Markets
  and decision-Watchlist now expose configured live quote rows independently
  of saved watches. Default live Hyperliquid range/mode is 1D/line; explicit
  selections and demo behavior remain. Collection copy RED 1 failed / 29 passed.
- **Verifier / controller:** Markets, Watchlist, InstrumentWorkspace and chart
  targeted Vitest gate passed 108 tests in 10.33s. Shared current-source quote
  state, streaming update and disconnected labels are covered. Package files
  and dependency locks are unchanged.
- **Implementer / chart:** live-edge append RED 2 failed / 14 passed, GREEN16.
  Preserve native live following without overriding manual pan or forecast
  ranges. Header cached-age RED5 failed /2 passed, GREEN47 header/shared-live
  tests; reuse monotonic age/source policy, preserve non-real/unavailable states
  and allow fresh HTTP recovery even with stream down. Controller combined
  verification and packaged/AWS browser acceptance remain pending.

## Reviewed local slice gate — 2026-09-12

- **Verifier / frontend:** full Vitest gate passed 351 tests in 29 files (19.58s).
  The actual `tsc -b` build found an extra argument to the shared time formatter,
  unsupported Testing Library role options and a missing fixture session field;
  corrected all three. The affected screens then passed 32 tests in 11.40s.
  Production build and API generation freshness passed; committed package assets
  were rebuilt. Oxlint reports only four existing fast-refresh warnings.
- **Verifier / packaged browser:** new deterministic loopback feed/replay test
  failed the old bundle's Markets entry (1 failed in 16.01s), then passed the new
  bundle (1 passed in 7.99s). It opens BTC from Markets and ETH/SOL from Watchlist,
  checks accessible observed closes against the history API, revises a candle,
  appends the next minute and reloads retained points. Keyboard Enter/Space
  switches line/candle mode. These are fixtures, not external venue observations.
- **Reviewer:** round 1 found a valid next-minute ingestion between replay capture
  and snapshot read could leave exact replay coverage behind the appended bar,
  producing history HTTP 500 / workspace HTTP 422. Controller reproduced both
  failures with a real LiveBuffer and controlled interleaving (RED 2 failed).
  Composition now updates coverage only for the validated 1m replay exception;
  manifest coverage remains fixed and replay-tail wording matches its coverage.
  Round 2 confirms the issue resolved, no further actionable correction finding.
- **Verifier / corrected source:** current-worktree combined history/contracts/
  workspace API and packaged browser gate passed 134 tests in 24.52s, with one
  existing Starlette deprecation warning. This supersedes earlier source counts.
- **Verifier / visual:** controller inspected the packaged deterministic fixture
  in Edge, including Markets BTC and Watchlist ETH. At 1280x900, document width
  was 1265px; at 390x844 it was 375px. Full chart remained 480px tall (289px and
  343px wide respectively), with accessible observed rows and TradingView
  attribution. Impeccable detector returned no findings for all changed UI
  targets. Existing chart/workspace design is retained; no dependency change.
- **Release boundary:** this checkpoint is local evidence. AWS still runs
  accepted `e185c3b`; final PR CI, exact-release deployment and actual upstream
  chart update/reload witness remain required before closing #144.

## Planner return — external boundary review

The local review used its two rounds. External PR #145 review rejected the
candidate before integration on four missing boundary cases. Return to
Planner/Product rather than expanding the patch/review loop: freeze chart UX,
providers, controls and data contracts; the remaining implementation is reduced
to one bounded acceptance correction batch:

1. Seed live rows from the configured market directory, retaining unavailable
   symbol links before the first update; overlay only actual observations.
2. Render loading/error while runtime identity is unresolved on Markets and
   Watchlist; do not infer demo mode from a missing health response.
3. Only a continuity-valid preferred/coarser replay may suppress valid 1m replay.
4. A raced observed replay tail advances its own generation receipt bound;
   manifest generation/coverage stay fixed.

Each case needs a failing regression and one combined corrected gate. No other
feature or visual polish is admitted. CI run 34697814465 for `940a74b` was
cancelled as superseded. A further structural failure returns to planning again
instead of extending this correction batch; AWS remains on `e185c3b`.

### Reduced boundary batch verification

- Frontend RED: 8 failures / 2 passes for empty/failed source snapshots and
  unresolved/failed runtime identity on both entry surfaces. GREEN: 70 combined
  Markets/Watchlist tests; full frontend 359 passed in 14.59s. The explicit
  source-error banner assertion subsequently passed all 10 entry tests.
- Backend RED: six invalid/single/gapped 5m/30m candidates failed, while two
  valid-candidate controls passed. Candidate GREEN8. Generation-time race
  RED2; corrected tests include fixed manifest generation and coverage even
  with an appended live bar. Agent combined backend GREEN142 in 22.72s.
- Controller final combined backend/contracts/workspace and packaged-browser
  gate: 143 passed in 26.91s. One existing Starlette deprecation warning.
  Production `tsc -b`/Vite build and API client freshness passed; rebuilt package
  assets committed with source. Ruff, scoped formatting and whitespace passed.
- Independent reduced-batch review: no actionable findings across all four
  boundaries. Valid coarse series retains priority; no broader range, provider,
  manifest authority, trading behavior or dependency changes.
- All four PR #145 findings are addressed by this checkpoint. Final-head CI
  must rerun; deployment and actual-source chart acceptance remain outstanding.

## Actual-source blocker / Planner dependency — 2026-09-12

While final CI was running, the existing AWS `e185c3b` feed stopped advancing
at 14:23:00 UTC. HTTP remained healthy and all three quote rows aged to stale;
the source tracker still reported its prior connected transition. The direct
`/api/live/state` age assertion failed (>30s). Current public Hyperliquid REST
still returned new prices from the same AWS host, excluding a general provider
or AWS outbound outage. No service restart or data deletion was used to hide it.

A stable copy of the unchanged live DuckDB plus WAL was inspected in an owned
AWS temporary directory (`/tmp/quantmesh-0035-stalled-lake-cvyi_zhd`): 226965
accepted updates, last receipt 14:23:00.745761 UTC, and one identity quarantine.
BTC's 14:22 candle arrived at 14:23:00.033701 with volume 26.45105, then at
14:23:00.538628 with volume 26.45336. OHLC stayed 77357/77377/77357/77362.
Both observations were locally classified final and assigned the same source
identity because `_on_candle` drops candle content from final IDs. The valid
late volume revision triggered `LiveIdentityConflictError` in persistence and
terminated the feed pump. This directly blocks the requested continuous charts.

Planner adds only the prerequisite candle-observation identity correction to
this same user loop. Distinguish revisions from exact redelivery, keep WebSocket
and REST identity parity, preserve actual conflict quarantine and append-only
legacy evidence, and exercise the real feed pump with the recorded pattern.
No watchdog redesign, blanket exception swallowing, grace-time heuristic, data
rewrite, provider expansion or 0021 soak change. Identity compatibility must be
explicit before implementation. CI 34698638115 / `025ac8d` is superseded and
cancelled; its chart checks do not establish real-source completion.

### Quant Researcher / revision identity decision

The recorded pair reproduced the same failure through real `LiveFeed.run` and
`LiveBuffer`: pump terminated with `LiveIdentityConflictError`, one accepted
candle and one quarantine; reopening retained the legacy identity and 14:22
checkpoint. No network, database rewrite or service substitute was involved.
The upstream candle schema has no immutable-final event flag; elapsed local
close time is insufficient evidence of final contents. ADR-0024 specifies
shared normalized OHLCV-qualified observation identity for WebSocket and REST.

Keep every legacy row and quarantine. A first equivalent closed observation
under the new mapping may append once; the chart coalesces same-minute rows,
and subsequent new-format repeats deduplicate. No retroactive exactly-once or
discovery of older corrections is claimed. Existing older-minute cursor policy
and visibility of a failed background collector task are separate follow-ups;
neither is silently redesigned inside this source-identity prerequisite.

### Operational recovery (unchanged release, not fix acceptance)

After preserving the source snapshot/quarantine, restarted the existing service
on unchanged `e185c3b`. Shutdown waited on background tasks and reached systemd's
90-second stop timeout at 14:42:15 UTC; systemd terminated the old process and
started PID 41012. The immediate startup health probe raced the listener and
failed; the following probe returned the exact same build, live market-data
profile, paper true and live trading false. At 14:43:08 UTC, BTC/ETH/SOL quotes
all had real labels and 1182ms source age. This restores current service only;
the legacy identity bug remains until the tested correction is deployed.
No lake deletion, unit change, new resource or firewall operation occurred.

### Task 2a implementation, review and controller verification

- Implementer RED: recorded pump and legacy admission regressions failed
  (2 failed/2 passed). Shared WS/REST normalized OHLCV helper corrected both;
  focused GREEN4, combined supervisor/feed/buffer/history GREEN176 in 15.07s.
  Final focused rerun after restoring unrelated formatting: 4 passed in 1.59s.
- Independent Task 2a round-one spec/correctness review: no actionable findings.
  Verified exact provisional ID preservation, final/source sequence semantics,
  real pump/subscriber path, REST parity, persistence/recovery lineage, legacy
  replay/chart compatibility and unchanged explicit conflict quarantine.
- Controller fresh combined gate: shared Python `-m pytest -q` on
  `test_live_candle_revisions`, `test_live_supervisor`, `test_live_feed`,
  `test_live_buffer`, `test_live_fence`, `test_live_history`,
  `test_instrument_history`, `test_instrument_workspace_api` and
  `test_live_chart_e2e`, with unique OS-temp basetemp: **306 passed in 32.57s**.
  One existing Starlette deprecation warning. Ruff `check src tests tools`,
  new-test format check and `git diff --check` passed. Submodule pointers are
  unchanged/uninitialized; no copied upstream code or new dependency.
- No frontend source/package changes after the previous production build and
  359-test frontend gate. Full final-head CI still precedes merge/deployment;
  the operational restart does not substitute for fixed-build AWS acceptance.

## Final CI and integration

CI [34700259858](https://github.com/ZP151/quantmesh/actions/runs/34700259858)
passed for `7230c686ab8f17ad6c2b35dd03272daf111ae380`: 3486 Python tests
passed, 56 skipped and 9 warnings in 2953.78s; 359 frontend tests passed.
Install, license/audit, generated API, typecheck, frontend lint, committed bundle
and Ruff gates all passed. Local packaged-browser evidence remains the explicit
browser gate; optional CI skips are not represented as executed tests.

All four PR threads were resolved, the final independent source-identity review
was clean and the worktree was clean. PR #145 squash-merged at 15:38:28 UTC as
`90fe57763835d4962c9431042f71ce0d54121c1c`. The candidate and merged commit
share tree `3a1fcad13fff759a4bc2b30fd6520ca6e363eaa1`; `git diff --exit-code`
between them passed. Remote feature branch deleted; local main preserved.
Acceptance closeout uses `codex/0035-chart-acceptance` from that origin/main.

### Additional unchanged-release evidence while CI ran

- At 15:05 UTC, SOL's 15:04 candle volume changed 1199.99 -> 1204.99 between
  receipts 15:05:00.264774 and .751846, with unchanged OHLC
  101.99/102.01/101.98/101.98. The same legacy final-ID collision stopped the
  feed. Stable snapshot `/tmp/quantmesh-0035-stalled-lake-x5u4qrre` retained
  256996 updates and two quarantine entries. The captured SOL pair passed
  candidate normalization/feed/buffer admission: two IDs, zero new quarantine.
- A second operational restart reached the 90s shutdown timeout at 15:17:51,
  then started PID 41316. Fresh-source verification failed: a BTC 15:17 final
  candle conflict stopped the feed again at 15:18:01.037070. Stable snapshot
  `/tmp/quantmesh-0035-stalled-lake-wt8vby3_` retained 257106 updates and three
  quarantine entries. No original row for the last conflicting ID was stored;
  original content is not inferred. No further restart loop or CI cancellation.
- The deployment acceptance quarantine baseline is therefore **three retained
  entries**. These existing records must remain; they are not new-build failures.
  Repeated old-build failures reinforce why restart/HTTP health cannot prove
  the requested continuously updating chart loop.

### Actual-source acceptance tooling review

The API witness now persists and checks quote provenance, freshness (0–30s),
continuity and exact symbols on every sample and at completion, preventing early
chart activity from hiding a later stalled collector. Actual fresh quotes passed;
recorded stale, age-only, delayed, gapped and unrecovered controls were rejected.

The actual AWS browser witness covers all six entry paths, then observes all
three charts together. Every changed DOM close or appended minute after baseline
must match real candle evidence received by that symbol's page. Settled points
are additionally compared with the history API; reload, keyboard, attribution
and desktop/mobile checks remain required. Both bounded acceptance-tool reviews
resolved their single finding in the second round. These are prepared tools,
not a claim of actual new-build acceptance before their deployed runs complete.

## Deployed attempt 1 and reduced follow-up boundary

The reviewed helper activated exact `90fe577` on private AWS. Independent
postchecks confirmed build, live market-data profile, paper true/live false,
service running, loopback 127.0.0.1:8765 and successful pip check. Both retained
releases remain. The outer stdin wrapper returned exit 1 only after successful
activation/postchecks because of a trailing CR-only line; independent checks
confirmed deployment, so it was not repeated.

**Verifier / actual browser:** all six Markets/Watchlist links reached the
three full charts. Over 302 seconds, BTC/ETH/SOL respectively had 22/21/15 DOM
changes matching their own received candle frames, three or four tail minutes,
and four/five/four distinct closes in one minute. Settled points matched the
history API and survived reload. Keyboard mode switches, TradingView attribution,
desktop 1440x1000 and mobile 390x844 overflow checks passed, with no page errors.
Artifacts are in `output/playwright/0035-aws-90fe577/attempt-1` (ignored).

**Verifier / actual continuous source: FAILED.** The parallel API witness
rejected an ETH quote aged 31811ms after all collection stopped at
15:45:47.617449 UTC. Stable DB/WAL copy
`/tmp/quantmesh-0035-stalled-lake-821r_gz_` retained 262548 updates and four
quarantine entries. The fourth is a new BTC **metrics** identity collision,
observed 15:45:47.609815: conflicting source time 15:45:47.265680, receipt
15:45:47.265719, funding -0.0000046821, mark 77371, index 77408.3 and open
interest 36310.0256. Original row is absent; do not infer its content. HTTP
health and early chart movement cannot establish sustained feed acceptance.

**Quant Researcher / source boundary:** local-observation identities must not
truncate a clock that remains full precision in the content digest. Audit only
Hyperliquid activeAssetCtx/allMids and retain genuine conflict quarantine and
legacy rows. Local observation time is not a new exchange timestamp guarantee.

**Verifier / workspace boundary:** an actual screenshot also showed a fresh
329ms quote degraded as received in the future. A deterministic public workspace
API reproduction returned generated_at 15:44:51.000000 with a quote ingested
during history assembly at receipt 15:44:51.000800. RED: one failed, two passed
in 24.09s; preexisting future receipt and excessive source skew remain refused.
Eight sequential actual API samples did not capture the race; they are not RED
evidence. The cause is a frozen request clock followed by a later latest-cache
read; `snapshot_exact(as_of)` labels freshness but does not select historical
observations.

**Planner/Product:** retain the same user action and five-minute freshness
success metric. Task 3a corrects only the two local-observation identities;
Task 3b atomically captures the workspace clock and exact detached quote/proof
before assembly. Exact file ownership, RED/GREEN and prohibitions are recorded
in the tracked plan. This is a reduced follow-up PR from merged origin/main,
with fresh review and final CI; no further UI/provider/watchdog expansion.
Current AWS remains deployed but unaccepted; quarantine baseline is now four.

### Reduced follow-up implementation and review — 16:00 UTC

- **Implementer / Task 3a:** repository RED 15 failed / 10 passed in 2.68s.
  Full UTC observation instant, channel, coin and canonical normalized payload
  now qualify only activeAssetCtx/allMids IDs. GREEN 168 passed in 9.42s across
  the new 25-case regression and supervisor/feed/buffer/candle tests. Exact
  repeats, changed microseconds/content, legacy reopen and real pump/subscriber
  continuation into all three quote streams are covered. A test-only JSON-key
  ordering assertion was corrected to compare persisted bytes and model fields;
  product serialization was not changed.
- **Implementer / Task 3b:** public replay/API race RED and clock/read-boundary
  RED preceded implementation. Capture the single clock read and exact detached
  quote/proof under the existing RLock, then release before workspace assembly.
  The clock callback must be quick and side-effect-free. Existing snapshot_exact
  semantics, valuation, receipt/source-future and continuity guards are unchanged.
  Final focused GREEN 79 passed in 9.62s, one existing Starlette warning.
- **Reviewer / fresh round one:** independent spec/correctness and standards/
  architecture reviews both found no actionable issues. No second round needed.
  Review included the strengthened actual API witness: each sample records and
  checks workspace availability, real provenance/label, age and receipt bound.
  Controlled assertion checks reject future receipt and eight recorded stale
  responses; these controls are not actual-source success claims.
- **Verifier / controller:** shared Python `-m pytest -q` with unique OS-temp
  basetemp on observation identity, candle revisions, supervisor, feed, buffer,
  fence, marks, live history, instrument history/workspace and packaged chart
  E2E: **342 passed, one existing warning in 49.14s**. Ruff across src/tests/tools,
  diff whitespace and submodule checks passed; pointers remain unchanged.
  Frontend source, generated assets and dependency locks are unchanged.
  Generated API freshness passed with the shared `QUANTMESH_PYTHON` and
  worktree `PYTHONPATH`; an initial invocation without these selected the wrong
  Python and failed package import before checking the API. No package install
  or schema regeneration was required.
- **Release gate:** commit this coherent reviewed correction, require final-head
  CI, then merge/update existing private AWS and repeat both actual witnesses.
  `90fe577` remains deployed but unaccepted. Do not close #144 at the code gate.

The correction was committed/pushed as
`6dc6ec38af49fea177540c0cd65785d150eb4fb2` and published as
[PR #146](https://github.com/ZP151/quantmesh/pull/146). Full final-head CI
[34704029214](https://github.com/ZP151/quantmesh/actions/runs/34704029214)
started 16:02:40 UTC. The initial PR review-thread query has no findings; recheck
at merge. The source is frozen while this gate runs. Deployment wrapper stdin
is prepared as explicit LF bytes to avoid the prior terminal CR-only line;
it has not been executed for the correction before the merge gate.

### Follow-up final CI and integration

CI 34704029214 completed successfully at 16:55:46 UTC for exact `6dc6ec3`:
**3517 Python tests passed, 56 skipped, 9 warnings in 3089.91s**; frontend
**359 passed** in 29 files. Install, dependency/license audit, generated API,
typecheck, lint and committed bundle checks passed. Full log is preserved in
OS-temp `qm0035-followup-ci.log`; watcher session48903 terminated with exit0.

Final PR query confirmed exact reviewed head, non-draft/CLEAN state, successful
required CI and no unresolved review threads. PR #146 squash-merged at
16:57:08 UTC as `9cfe1bc8ff910792b3f8cb6928763b667ba2442a`. Candidate and
merge share tree `bafcff7e3ba027d2cb329f2e3bc239b8fe0a30e8`; their full diff
is empty. Remote feature branch deleted, local main/worktrees preserved.
Closeout continues on `codex/0035-chart-closeout` from this origin/main.

The reviewed deployer/unit blob hashes remain unchanged. The LF-byte wrapper
has now started the exact merged release update in exec session49856. This is
deployment in progress, not renewed real-source acceptance; preserve the four
quarantine rows and wait for the same command before independent verification.

### Corrected AWS deployment and renewed witness

The exact `9cfe1bc` deploy command completed with exit0. Retained e185c3b and
4022942 releases remain; pip check passed. Independent HTTPS health confirms
exact build, live market-data profile, paper true/live false; service PID41909
is active/running on127.0.0.1:8765. A mid-update502 coincided with old PID41533
in systemd stop-sigterm and no listener; deployment finished without another
mutation. Reviewed helper: `/tmp/quantmesh-0035-deploy.4bByQL/deploy_release.py`.

Actual API witness started17:00:44 UTC and initially observed all three fresh
quotes, available workspace evidence and new minute appends. It remains a
300-second check, not completion from early movement. In-app tab6 was reloaded
to9cfe1bc and Markets->BTC visibly renders the real full line, WebSocket and
source/freshness labels without the prior false-future warning.

Browser attempt1 terminated on ETH chart loading at the assertion library's
default5s timeout (empty loading main), while the separate API witness remained
active. The helper had set only context timeout20s; assertions use their own
timeout. Set the assertion timeout to the intended20s and started a new browser
attempt2, retaining failed attempt1 evidence. No product change, feed restart,
source substitution or CI rerun. Final sustained/API/DOM/reload evidence remains
required before closing the iteration.

### Accepted actual-source checkpoint — corrected build 9cfe1bc

- **Verifier / actual API:** 313.748 seconds, 21 samples, ending 17:06:13 UTC
  on 2026-09-12. Each coin had 21 distinct source quote times; maximum sampled
  quote ages BTC2507ms / ETH3327ms / SOL2708ms. Every sampled workspace was
  available/real with age within30s and receipt no later than its request cut.
  All coins crossed six tail minutes, with3/4/5 distinct closes in one minute.
  History identifies Hyperliquid live replay and explicit5m-to-1m fallback;
  actual coverage grew from16:59–17:00 to16:59–17:05, two to seven bars.
  Final exact-build health, fresh quotes, unchanged orders and unchanged risk
  passed. These are21 sequential samples over313.748s, not a latency SLA or
  continuous measurement of every event between requests.
- **Verifier / actual browser:** 301.968 seconds and100 observations. All six
  Markets/Watchlist-to-BTC/ETH/SOL paths opened1D/line. Each coin crossed six
  minutes;6/5/5 distinct closes occurred within a minute. All41/20/21 changed
  DOM tails matched real candles received by that same page. Eight settled
  points per coin matched the history API before and after reload. Keyboard
  Candles/Line, TradingView attribution,1440x1000 and390x844 widths passed;
  no horizontal overflow or page errors. Success summary was written only
  after every assertion; the terminal handle is now closed. Root inspected
  the real mobile screenshot and current in-app full BTC line.
- **Reviewer / acceptance round one:** independent recomputation of both raw
  witnesses found no freshness, future-time or unmatched DOM-change failure.
  Persisted candle-frame counts are146/83/56; summary146/84/60 includes later
  callbacks during per-coin final checks. Use raw counts for artifact claims.
  This timing difference does not affect any matched observation or gate.
- **Verifier / persistence:** stable DB/WAL copy
  `/tmp/quantmesh-0035-stalled-lake-l3zrnx3z` contains270555 accepted updates
  through17:07:32.364892 UTC, versus262548 at the old stalled baseline. All four
  prior quarantine rows remain and no new quarantine was added. The helper's
  inherited `stalled-lake` prefix does not describe the current running feed.
  Only the stable copied database was opened; primary evidence was preserved.
- **Verifier / post-browser:** independent17:12:53–56 UTC HTTPS checks still
  returned exact9cfe1bc/live/paper true/live false and all three real available
  workspaces, ages BTC540ms / ETH499ms / SOL1556ms, with no future warning.
- **Artifacts:** ignored `output/playwright/0035-aws-9cfe1bc/attempt-1` contains
  API summary/JSONL; sibling `attempt-2` contains browser summary/JSONL, raw
  candle frames, per-coin desktop PNG/AX and BTC1440/390px PNG. OS-temp
  `qm0035-final-health.json` preserves the independent final response.
- **Controlled evidence stays separate:** the combined342-test gate and full
  CI include disconnect barriers, collecting/gap refusal, two-new-session-
  candle recovery, stale and genuine future/source-skew controls. No real
  provider outage was injected or claimed by the actual-source witness.

**Planner / closeout:** the requested crypto chart loop is accepted. Integrate
this documentation-only checkpoint and close #144 through its PR; no further
AWS deployment is needed for documentation. Next is existing licensed
Moomoo/OpenD host, approved private route and quote entitlement before an
AAPL/NVDA open-session witness. Short observed crypto history is not qualified
multi-month history or a forecast. Paper and live-execution boundaries remain.

Closeout review: independent acceptance review found no unmet runtime gate;
independent documentation review found one premature index completion date,
corrected to leave integration pending. Retained e185c3b is explicitly a prior
live artifact with known identity limitations. Fresh `ruff check src tests tools`,
`git diff --check` and submodule comparison passed; only seven documentation
files changed from the accepted deployed tree. Required closeout PR CI remains
an integration gate, with no duplicate full local suite or deployment.

## Reopened operator acceptance — 2026-09-13 07:55 UTC

The operator cannot see live data. Actual9cfe1bc BTC page remains in Loading
instrument workspace. BTC/ETH/SOL sampled quote ages are252837/252099/251895ms,
all stale; health, live/state and BTC workspace all exceed20s in the bounded
read-only probe qm0035-operator-probe.py. SSH localhost health also exceeds8s.

PID41909 remains running after~15h; memory/disk have headroom. t3.small has
73–79% sampled CPU steal (CPU-credit balance is not measured). Public
Hyperliquid allMids responds within5s. CPU profiling447samples attributes
52.57% to DuckDB string decompression,15.66% to column filtering and6.49% to
partial string scanning. Stable preserved DB/WAL copy:
/tmp/quantmesh-0035-stalled-lake-d17h3lj3,855594rows,402857256bytes,still4old
quarantines. This is a persistence/response-latency investigation, not a
reappearance of the previously fixed identity conflicts.

On a separate copied database /tmp/quantmesh-0035-lookup-benchmark-8e8jm7y4,
DuckDB1.5.5 exact identity lookups take0.872s(hit)/0.714s(miss), both Sequential
Scan. An additive source_event_id index alone does NOT fix the existing
four-predicate query:0.611/0.664s and still Sequential Scan. MAX(local_seq)
is~1ms. Query-shape benchmarking continues before implementation. No live
DB/index/service mutation, infrastructure change or trading action yet.

### Sustained-recovery implementation and retained workload evidence

- Planner: bounded admission lookup correction, with exact-file plan
  `docs/superpowers/plans/2026-09-13-sustained-live-chart-recovery.md`.
  Existing approved real-chart outcome and private-deployment authority apply.
- Researcher/root: reopened actual855594-row DuckDB1.5.5 copy still needs1.101s
  for the old four-predicate lookup; row-scoped equality plus source-ID index
  needs3.628ms and produces Index Scan with equal results. Independent local
  checkpointed200004-row SQL experiment confirms hits/misses/shared-ID scopes.
- Implementer RED3failed/4passed: actual captured admission query sequential,
  and the required index absent after legacy/reopen. GREEN7passed5.64s; focused
  buffer/feed/candle/observation/supervisor regression175passed14.31s. Add only
  the nonunique source-ID index after legacy migration and express complete
  scope as row equality. Preserve compositeUNIQUE and all transaction guards.
- Reviewer: independent spec/correctness and standards/architecture/safety
  round-one reviews found no actionable issues. No second round needed.
- Root whole-batch benchmark: local copies of the preserved actual lake using
  baseline9cfe1bc versus fixed LiveBuffer, six fresh21-event batches plus exact
  redeliveries. Each batch includes3candles/3quotes/6metrics/6paired-book/3trades.
  At100000rows, fresh median120.3ms->32.4ms and admission checks183->896/s.
  At855594rows, fresh median291.4ms->58.0ms, maximum-of-six360.9ms->106.6ms,
  whole-workload CPU17.94s->1.08s, checks74.9->458.9/s. Measured process RSS
 320.2MB->353.9MB and resulting DB395.1MB->487.1MB at the larger size.
  Each run preserved quarantine count4, exact replay/duplicate receipt
  sequences, expected inserted row count and reopened contents. These are
  local benchmarks, not AWS throughput guarantees; six samples do not establish
  a production latency percentile. Artifact OS-temp
  `qm0035-batch-benchmark-1lrsex6_/summary.json`.
- Benchmark setup caveat: an initial attempt to shrink a copied indexed lake
  using DELETE hit DuckDB's "Failed to delete all rows from index" error. Only
  that owned temporary copy was touched. The source backup and AWS primary
  remain intact. The100000-row fixture was then constructed by copying rows
  into a fresh schema; the855594-row test uses the full unchanged source copy.
  This DELETE behavior is recorded for separate retention triage, not silently
  repaired or applied to production during this slice.
- No frontend, API schema, provider, dependency or order behavior changed.
  Broad source/packaged-chart gate, final PR CI and actual retained-lake AWS
  acceptance follow. The current production build has not yet been updated.

Root combined source/packaged-browser gate:349 passed, one existing Starlette
warning in52.20s. Global Ruff and changed-test format checks passed; diff
whitespace passed. No submodule/dependency/frontend asset changes. Commit this
reviewed checkpoint and require exact-head full CI before merge/deployment.

### Supplementary retained local runtime — 2026-09-13 08:28 UTC

PR #148 candidate7f8065357946b399c0cc75983af1d8b92b4f49e9 is undergoing required
CI34747168953; AWS still runs9cfe1bc and remains unaccepted. This checkpoint
does not change the source candidate or substitute local evidence for AWS.

Verifier used a hash-verified COPY of the855594-row public-market snapshot.
All15 Settings storage roots and the fresh empty paper account were isolated
under OS-temp; only public Hyperliquid BTC/ETH/SOL and loopback56684 were used.
Index creation3.281s, buffer initialization4.269s, cold HTTP ready9.405s.
Over339.23s,285 API samples had no transport timeout: health/state114x200;
workspaces18 initial collecting404s, followed by153x200 from30.42s onward.
Every successful workspace was real/available with receipt<=generated_at.
Maximum workspace quote ages were2.730/3.954/5.177s for BTC/ETH/SOL.
Under concurrent browser load, maximum workspace response times were
4.097/4.354/5.691s; health maximum1.954s and state90ms. These are local sampled
limits, not AWS guarantees. Rows/sequence grew855594->862247 (+6653), the four
old quarantines remained, orders stayed0 and source snapshot hash was unchanged.
Owned runtime stopped cleanly08:28:15UTC; port closed and stderr empty.
Artifacts: OS-temp qm0035-retained-runtime-fbc2c6c6a1844d698c68e39ac09c0931
report.json/analysis.json, inspected by root.

Root supplementary browser witness reached all six Markets/Watchlist paths
and recorded50 samples through149.232s. Three minute tails per coin and
16/16/13 changed BTC/ETH/SOL DOM tails matched that page's own real candle
frames; maximum distinct closes within a minute were4/4/3. This browser run
is explicitly INCOMPLETE: its final BTC reload API comparison overlapped the
owned server's scheduled shutdown and got ECONNREFUSED. An earlier local
attempt expected the staging-only deployment badge; the isolated local server
correctly omits that field. Neither failure is hidden or counted as complete
AWS/browser acceptance. Actual deployed witness keeps the exact build check.
Artifacts: ignored output/playwright/0035-local-retained-7f80653/attempt-2,
including partial-summary.json and raw DOM/frame evidence.

Operational reviewer found no actionable issue in the exact-hash-verified
deployment wrapper using the existing deploy(...health_attempts=180) parameter.
The AWS copied-lake index build took32.63s, exceeding the CLI's default30
immediate-failure retries. The extended attempt count retains exact build,
runtime/paper safety and automatic rollback checks; it is not a strict180s
deadline because probes add time. No deployment has run at this checkpoint.

### Exact-head CI and integration service failure — 2026-09-13 09:16 UTC

Required CI34747168953 succeeded on candidate
7f8065357946b399c0cc75983af1d8b92b4f49e9:3524 Python tests passed,56 skipped,
9 existing warnings in3148.74s;359 frontend tests and all install/audit/license/
generated-client/typecheck/lint/bundle gates passed. Run completed09:08:17UTC.
Watcher1285 and enclosing wait77 are terminal exit0; do not poll/restart them.
Root inspected final logs in OS-temp qm0035-recovery-ci.log, PR OPEN/non-draft/
CLEAN, exact head/base8f9c25a and no unresolved review threads before integration.

Normal GitHub squash integration has not succeeded. GraphQL returned EOF then
an internal execution error; REST PUT returned HTTP500 with empty body
(request E363:88EC3:C59C48:D252A4:6AA668BF). Existing authenticated browser
showed checks passed/ready to merge, but Confirm squash and merge returned
"Unable to read response from the server. Please try again later." Subsequent
PR/main reads still show OPEN and8f9c25a. A REST merge_commit_sha while merged=false
is a prospective test merge, not proof of integration. No AWS deployment ran.

Independent integration reviewer confirmed there is no compliant direct-main
fallback: active branch rules require pull_request and standing goal authority
requires squash. A one-commit fast-forward or manually closing a local squash
would not meet those requirements. Preserve the reviewed green candidate and
retry normal GitHub squash after service recovery; do not bypass branch rules.
Acceptance documentation review resolved its one finding in round2: both
languages now require at least5min, two active-minute changes per symbol and
at least one later-minute append. Actual AWS acceptance remains outstanding.

Blocked audit09:22UTC: the same normal-squash integration failure has recurred
across three consecutive goal turns. Latest REST responseHTTP500/empty body,
requestCB11:14391B:BC67CB:C955F9:6AA66B3D. Post-attempt authoritative reads:
PR148 OPEN, same green7f806535 head, main8f9c25a; private SSH current release
still9cfe1bc8ff910792b3f8cb6928763b667ba2442a. Goal is externally blocked,
not completed. Source/review/CI work is preserved; merge, exact AWS deployment,
retained-lake source/browser acceptance and final evidence integration remain.
Three local documentation files contain the reviewed post-CI checkpoints and
operator instructions; keep them for closeout after PR148 integration rather
than altering its green head and triggering unrelated repeat CI.


### Manual integration, deployed recovery and failed load acceptance — 2026-09-13 10:00 UTC

Operator manually merged PR148 at09:39:11UTC as5332a19. Root verified MERGED
state and full tree2549e8df6a4c8c674ceb20fec88f0e558254e109 equality with green
7f806535. The prior GitHub service blocker is resolved. Existing reviewed
private deployer activated exact5332a19 successfully (exit0); PID44749 started
09:43:53UTC, quantmesh user, loopback8765, live data/papertrue/livefalse.
Retained data and rollback releases remain. No new infrastructure or order.

Verifier actual API attempt1 recorded16 complete rounds09:45:08–09:54:38UTC,
ten distinct minute tails per coin and coverage09:44–09:54/11rows at last round.
Maximum quote ages BTC4298ms/ETH4362ms/SOL4700ms; workspace2231/1678/5791ms;
all sampled source/workspace contracts passed real/fresh/receipt bounds.
The helper exited1 at its final BTC revision assertion: only2distinct closes
in a minute, required3; ETH4/SOL3 from raw records. Slow sequential sampling
cannot prove BTC's required two within-minute changes. In-memory per-request
latencies and final orders/risk comparison were not emitted after failure,
so those final gates remain unproved. No timeout exception occurred in the
completed API rounds. This is incomplete evidence, not a passed API witness.

Actual browser attempt2 independently failed its20s initial SOL chart wait.
BTC/ETH Markets+Watchlist paths passed by loop order; SOL displayed5332a19
shell without the instrument workspace. Six-path completion, sustained samples,
reload/keyboard/mobile were not reached. No silent retry or longer timeout.
Root viewed the user's actual BTC1DLine full chart with real Hyperliquid source,
WebSocket, fresh quote and changing closes; that page alone does not establish
full acceptance. The conservative future-receipt candle-join limitation also
appeared while valid replay/quotes continued; no time bound was loosened.

A strict stable COPY of DB+WAL succeeded on attempt6 after load witnesses:
/tmp/quantmesh-0035-recovered-lake-778zbzvd,416607600copiedbytes,896780accepted
rows/maxseq through09:56:58.781310UTC, source lookup index present and old
quarantines4unchanged. Primary never opened by diagnostic DuckDB connection.
The measured retention check exited0. API84521/browser72652/deploy80854 are
terminal; do not poll them. Ignored artifacts in
output/playwright/0035-aws-5332a19/attempt-1/partial-summary.json and
attempt-2/failure.json retain failed evidence.

Planner returns to bounded load diagnosis before any acceptance claim or next
market. Independent source audit identifies whole-workspace invalidation on
all matching updates every500ms plus retained10000-row replay/validation and
shared admission/read locking as a possible amplification path. Correlated
browser resource trace and copied-lake stage timings are required before a
new fix. Live perf439samples has no single dominant native DuckDB scan like
the old admission profile; do not assume the previous query repair failed or
claim CPU-credit exhaustion. CPU steal remains observed, not attributed.


### Planner / quant read-load slice — 2026-09-13 10:03 UTC

One diagnostic run (not a replacement acceptance run) opened all three charts:
workspace totals BTC3.163s/ETH13.167s/SOL13.225s, TTFB3.157/13.150/13.205s.
ETH/SOL lazy chunks15/34ms; health2.534/4.866/8.582s as pages accumulated.
Nineteen workspace starts, sixteen200completions, three pending at controlled
close; no page errors or price-trail calls. This localizes delay before the
workspace HTTP response; it does not alone prove the complete server cause.
Trace: OS-temp qm0035-aws-load-trace-jzf2y6cx. Owned browser closed, exit0.

Independent isolated retained replay profile (current5332a19, DuckDB1.5.5,
Windows20threads) returned10000models each; full history-equivalent377–409ms,
model conversion/validation236–259ms and SQL+fetch76/80/83ms. Only13/14/18rows
followed the last disconnect in that snapshot; all10000 were validated first.
AlternativeTOP-N query returned exactly equal rows but98/94/82ms, no consistent
improvement, so no query rewrite follows. Source hash unchanged. Artifact
OS-temp qm0035-replay-profile-j1u_o091/analysis.json. Native live439sample profile
aggregates DuckDB37.59%, Python31.89%, libc12.98%; unlike old admission it has
no single dominant scan symbol. Local stages cannot quantify AWS contention.

Planner and independent quant reviewer approve one bounded completion-based
refresh slice in the active plan. For live Hyperliquid only, matching events
cannot force back-to-back whole-workspace reads; automatic refresh waits5s
after request success/failure and never overlaps in-flight work. Reuse existing
ReactQuery polling, scopes and source authority; preserve all backend validation.
Spacing can be response duration+5s, so aging/stale indications must remain
honest. Do not represent this as tick-by-tick rendering. Actual three-chart AWS
latency and source acceptance remain the deciding gate. No other market,
backend/cache architecture, paid capacity or trading change is included.


### Task3a implementation and controller gates — 2026-09-13 10:14 UTC

Implementer owns only InstrumentWorkspace.tsx and its component test. Six new
regressions failed on old behavior (6failed/30skipped,3.69s) then passed with the
bounded fix (6passed/30skipped,3.89s). Live Hyperliquid invalidation now reads the
exact query state and refuses while non-idle or within5s of latest data/error
settlement. Polling stops during fetching and restarts5s after settlement.
Other venues retain the500ms event path. Stable exact query keys and timer
cleanup cover venue/symbol/range/comparison changes and unmount.

Real QueryClient/QueryObserver tests use deferred success/failure: no queued
invalidation while fetching, no new read at4999ms, eventual fallback at5000ms
without another event, wrong identity/sibling range isolation, authoritative
history revision/append, and stale labeling despite connected WebSocket.
Targeted107tests passed10.11s. Independent spec and standards reviewers each
found no actionable issues in round1; no second source-review round needed.

Controller gates: full frontend365tests passed16.19s; typecheck and Oxlint
passed (four existing Fast Refresh export warnings). Initial API-client check
used unconfigured global Python and failed import; rerun with documented shared
QUANTMESH_PYTHON and worktreePYTHONPATH passed, client unchanged. Global Ruff and
whitespace passed; submodule pointers unchanged. Production TypeScript/Vite
build succeeded and copied owned packaged assets; existing large-chunk warning
remains. Packaged actual-loopback chart E2E passed1test17.41s with existing
assertion limits, including revision/append/reload/source comparison/controls.
No packaged-test timeout or backend change was needed.

The reviewed documentation checkpoint cda1560 is already pushed. Commit this
source+asset gate and require new exact-head CI before merge/deploy; prior
PR148 CI does not certify this frontend change. AWS still5332a19 and complete
actual acceptance remains outstanding. Remote merged PR148 feature branch was
removed under standing authority; its local branch/main history is preserved.

### PR149 encoding correction and supplementary local acceptance — 2026-09-13 10:27 UTC

PR149 candidate6e2f63fc2033674b18bb80fe572e5475b9e0c8bf passed CI pre-test gates
and entered Python tests. GitHub review then correctly found Windows-1252 dash
bytes introduced by root's default-encoding documentation writes. Strict UTF-8
decoding reproduced both failures. Replaced exactly7 invalid punctuation bytes
in this ledger and3 in the plan with the intended UTF-8 en/em dashes, preserving
all existing valid content. Independent byte-level review found no remaining
issue; all343 tracked Markdown files decode strictly as UTF-8. Subsequent writes
must use explicit UTF-8. CI34751315247 was cancelled as superseded, not counted
as passed; watcher64952 is terminal exit1/cancelled. New final-head CI is required.

The unchanged6e2f63f source and packaged assets also passed a supplementary
LOCAL actual-public-feed witness on a hash-verified855594-row copy. All15
Settings Path roots and empty paper account were isolated. Six Markets/Watchlist
paths passed;300.260s/93 DOM samples per page proved six tail minutes each,
maximum distinct closes within a minute6/7/7, and33/33/35 changed BTC/ETH/SOL
DOM tails matched their own real candle frames. Six settled points per coin
matched API history before and after reload. Source/receipt/coverage checks,
papertrue/livefalse, orders/risk equality, keyboard and1440/390px passed.

Completed browser workspace requests60/59/59 had sampled p95 latency
748/788/875ms and maxima1229/999/1096ms; zero request violations or page errors.
Browser-native request/response timestamps show completion-to-next-read minima
5.001630/5.000903/5.001242s. Python callback arrival timestamps have small
delivery jitter (minimum4.9979s), retained separately rather than rounded into
a strict timing claim. Light API state/health probes and final workspace/history
checks replace the earlier redundant full-workspace probe loop; this is not a
controlled performance comparison with that different workload or an AWS result.

Runtime grew855594->863889rows (+8295), quarantine4->4, orders0; source SHA
unchanged. Server stopped10:24:45UTC, owned port49674 closed and processes exited.
Cleanup logged two Windows Proactor connection-reset callbacks and a5s Uvicorn
graceful-shutdown warning (Cancel0runningtasks); those logs are preserved, not
reported as warning-free shutdown. No source patch/retry was made for them.
Root inspected reports and raw request/DOM records. Artifacts: OS-temp
qm0035-local-paired-6e2f63f-y2nh76p9/{analysis.json,report.json,browser/}.

The actual AWS paired helper now has completed independent review: round1
caught a missing gate on slow/failed browser-origin workspace fetches; round2
verified explicit failed/non2xx/completed-or-pending>=20s rejection and narrow
navigation-cancellation handling. Eighteen offline gate controls pass. It keeps
all source, own-frame/DOM, reload and safety checks and persists failures.
Reviewed helper SHA2563dbab3130e33e26f718391321bff0f6bddbda39e652540ce91bcf5f3eb21ac58.
It has not run against AWS; exact new merge/deployment and actual acceptance
remain outstanding. The supplementary local result cannot close144.

### Verifier / integration and actual measurement failure — 2026-09-13 11:30 UTC

Final candidate e23ab823894763dd0acdd36541db410e61178071 passed required
CI34751913362:3524Python tests,56skipped,9warnings in3001.44s;365frontend tests
and license/audit/API/typecheck/lint/committed-bundle gates passed. The only
GitHub review thread was resolved. PR149 merged11:20:26UTC as
76203e03476b120e149a0c06d9932849bb4d8e14; exact fulltree
6e43a7754040bd35b2cef5b8094922fd90157e14 equals tested candidate. A PowerShell
unquoted HEAD^{tree} read failed; corrected quoted revision and explicit tree
comparison passed. No mutation occurred in the failed read.

The CI log's synthetic merge checkout b4b6adc2c9d203f7f7a17a3fe4d593eee786a0f7
was independently resolved through GitHub's commit API to that same fulltree;
the tested checkout, PR candidate and deployed squash merge agree.

Reviewed existing private deployer/unit blob IDs remain unchanged. Deployment
session59488 exited0, activated exact76203e0, pip check passed, service User
quantmesh/PID45254 started11:24:24UTC and listens only127.0.0.1:8765. One health
probe during release transition returned502; post-completion health returned
ok/exact build/runtime live/papertrue/livefalse. Both user's IAB QuantMesh tabs
were reloaded, BTC screenshot showed build76203e0 and real chart. No lake,
rollback, public access or trading configuration was changed.

Reviewed paired helper actual AWS attempt1/session59913 exited1. Six actual
Markets/Watchlist paths opened1D/Line real charts,102–103rows, but only one DOM
sample per coin preceded failure. SOL-60 remained pending at20.140s; no600s,
reload or final orders/risk gate was reached. Preserve artifacts in ignored
output/playwright/0035-aws-76203e0/attempt-1, including trace, request/frame/DOM/
source streams, screenshots and server journal. No retry or threshold change.

Independent browser audit matched helper events to native trace: SOL-56
completed200 at11:25:51.739; full Watchlist navigation began53.938; SOL-60 was
born56.753 in the old SOL document,5.014s after prior completion. Watchlist
document responded59.343. New-document SOL-70 started11:26:03.877 and completed
200 at14.454 (10.577s); all six paths passed14.965. SOL-60 tripped16.893 and
remained unresolved at21.004 cutoff. Native response/status/send timings are
also absent, so this is not evidence of a dropped Python completion callback,
but it does not prove the server held a request20s. Old-document abandonment
remains ambiguous. New SOL response was fresh200, not asset304 cache reuse.

Independent backend audit still identifies repeated10000-model replay
conversion as a potential workspace-specific cost. BTC/ETH completed requests
show native TTFB10.27/10.38s while nearby state/health probes were22/15ms;
neither that observation nor prior local profiles proves SOL-60's cause.
After owned witness browsers closed, a four-interval vmstat sample showed
0–2%steal; this is not a concurrent-load comparison with earlier42–62%steal.

Planner boundary: the helper already had two review rounds. Return to a
bounded document-lifecycle measurement design before patching it or choosing
another backend fix. Retain20s active-document request, actual source/freshness,
600s three-page changes/appends, reload and unchanged-safety gates. Issue144
and the goal remain incomplete; no additional market work has started.

### Task3b measurement controls and review checkpoint — 2026-09-13 11:50 UTC

Planner approved native CDP page/request/frame/loader identity with confirmed
document replacement as the only authority for censoring old-document requests.
Censored observations are never successes or completed-latency samples. Keep
20s active-document deadlines and all real-source/600s/reload/safety assertions.
An expected native canceled=true/net::ERR_ABORTED below20s requires exact old
identity, explicit full navigation/reload and subsequent commit; missing commit,
other failures and non2xx still fail. The active plan contains exact controls.

Implementer prepared separate OS-temp v2 helper; original helper/failure stay.
Pure controls recorded initial censor RED, seven-control RED, and expected-abort
RED, then GREEN13methods/35subtests. Root independently reran13methods, passed.
One authorized synthetic loopback wiring fixture used the same observer: old
loader request50016.2 had no native terminal event and was censored at1.537226s;
new loader50016.4 completedHTTP200 in5.15ms, sole completed latency sample.
This reproduces the lifecycle gap, not market-data acceptance. Browser/server
closed, port52044 closed. A late synthetic server write logged WinError10053,
preserved without retry. Root inspected raw loader events and report. Artifacts:
OS-temp qm0035-v2-cdp-wiring-s9bewrgw; helper/test reports adjacent in OS-temp.

Independent review round1 of v2 SHA
b20cf19350c95745318cb076b721ad700aede3c81e28512fbed62bdc93664ca8 found one P2:
drain applies queued frameNavigated at a later sampled clock before later queued
native completion. Start0, commit/response19.8/finish19.9, sampled20.1 could
permanently misclassify a valid completion as pending>=20s. Return to implementer
for one observer-level RED/GREEN correction before round2. Other original
acceptance gates remain intact. No new AWS witness has run at this checkpoint.

### Task3b round2 and actual run start — 2026-09-13 11:58 UTC

Observer-level RED reproduced both queued native finish19.9 at cut20.1 being
misclassified and a native event20.2 arriving during a sampled clock20.1.
Drain now reconciles known native outcomes before timestamp-less commits and
uses max(sampled clock,native batch timestamps) as one browser-clock frontier.
No deadline grace is added. True>=20s finishes/pending requests, HTTP503,
generic failures, exact new-loader deadlines and previously censored late
events have contrasting controls. GREEN18methods/40subtests; root reran18,
passed. Ruff/compile/format passed. Independent round2 resolved P2, no further
findings. Original source/assertions/failure remain unchanged.

Reviewed final helper SHA256
9a3a26014624a33855824f3ae1d29990bd70c78f827b95b159390ee51a88dcff.
Earlier loopback wire fixture tested b20cf193's shared CDP binding; the final
batch-order correction has observer-level controls, not a second wire run.
Actual new witness started11:56:35UTC on deployed76203e0, session97072,
output/playwright/0035-aws-76203e0/attempt-2. All six entry paths passed by
11:56:58.753 with133rows each;600s simultaneous sampling is in progress.
This start/progress checkpoint is not final acceptance.

### Actual AWS acceptance completed — 2026-09-13 12:15 UTC

Verifier: the reviewed v2 witness exited 0 at 12:07:43 UTC on deployed
`76203e03476b120e149a0c06d9932849bb4d8e14`. Sampling lasted 601.662 seconds
with 175 observations per page. All six Markets/Watchlist entry paths passed.
BTC/ETH/SOL produced 62/55/53 DOM changes matched to earlier real frames from
their own pages, 11 minute tails each and up to 6/5/7 distinct closes within
one minute. The first-to-last DOM sample span was 598.336 seconds; the sampling
loop duration, rather than that narrower span, establishes the ten-minute gate.

All 296 native workspace requests completed; none failed, timed out, remained
pending or were censored. Maximum latency was 5.743/6.278/5.737 seconds and p95
was 2.579/3.450/3.000 seconds. In each page's longest-lived sampling document,
minimum response-end-to-next-request spacing was 5.002073/5.002328/5.002287
seconds. Explicit full navigations and reloads are outside that spacing claim.
All 21 health observations matched the deployed build, paper enabled and live
execution disabled. Quote observations were real with complete continuity;
maximum reported quote age was 5.551 seconds. Orders and risk state were unchanged.

Each chart grew from 133 to 144 rows, covering 09:44 through 12:07 UTC. Settled
API history matched before and after reload; independently checked retained
points were 141/141/142. Keyboard Candles/Line switching, 1440px and 390px
layouts, no horizontal overflow and TradingView attribution passed. Root viewed
the actual BTC screenshot. Independent Reviewer/Verifier audited raw CDP events,
frames, source times and DOM observations offline and reported no findings.

Evidence: `output/playwright/0035-aws-76203e0/attempt-2` contains the raw witness,
`verifier-audit.json`, `refresh-spacing.json`, helper, controls and screenshots.
The portable tracked summary is
[aws-sustained-witness-summary.json](evidence/0035/aws-sustained-witness-summary.json);
operator steps are in [the acceptance guide](../runbooks/live-chart-acceptance.md).
Earlier failed/inconclusive attempts remain failures; this passing run needed
zero request censoring. No application change followed the deployed PR #149.

Retention: the existing in-process replay-window API reported 1,074,523 retained
rows, from 2026-09-12 10:47:14 UTC through 2026-09-13 12:11:55 UTC: 177,743 more
than the previous direct snapshot. A separate stable-copy attempt exhausted ten
tries while writes continued and exited 1. It did not alter or pause the primary
lake, and no unstable copy was read or retried. Current extent and growth are
API evidence; the last direct index/quarantine check remains 09:56 UTC, with the
lookup index present and four old quarantines. No fresh direct count is claimed.

Planner/Product: issue #144's real-chart user loop is accepted. This remains a
bounded ten-minute witness and partial recorded history, not indefinite uptime,
qualified full-day history, tick-by-tick rendering or all-market acceptance.
Documentation integration is the remaining closeout step. Next is existing
Moomoo/OpenD host, private route and quote-entitlement readiness for AAPL/NVDA;
the operator's connection-information reply is pending. No new market or paid
capacity is authorized by this acceptance, and paper remains the default.

### Documentation review and verification boundary

Independent closeout review found no material findings across the eight changed
documentation/evidence files. Root validation passed strict UTF-8 decoding of
344 Markdown files, 19 local links, JSON parsing and equality with the retained
raw audit/spacing/replay-extent files. `git diff --check` and
`ruff check src tests tools` passed. `git submodule status` completed; its nine
uninitialized pinned submodules were unchanged. Source/frontend/deploy/tests/tools
are identical to the deployed, CI-tested `76203e0` tree. No new application test
run is claimed for these documentation changes; the final documentation PR's
required CI must pass before integration. No redeployment is required.

### Documentation range correction — PR #150 review

GitHub review of `674141d` identified an ambiguous operator instruction: the
guide mentioned 1D and 5D beside the `5m->1m` fallback. Root verified
`live_history.py`: only Hyperliquid 1D admits the 1m fallback. The guide now
scopes that assertion to 1D and explains that live replay's 5D requires eligible
30m/coarser data, or an available historical dataset, otherwise correctly
reports unavailable. The review's suggested 5m value was checked against
`_PREFERRED_INTERVAL` and corrected to 30m. A direct BTC 1D link is included. This
corrects documentation only; no 5D capability or new acceptance run is claimed.
Required CI for the corrected documentation head must pass before integration.

Round-two bounded review found no findings. Existing `tests/test_live_history.py`
passed 34 tests with one warning in 12.76 seconds using a fresh owned basetemp.
The initial invocation reached test completion but failed pytest cleanup with
Windows access denied on the shared `pytest-current` path; it is not counted as
a passing run. No shared temporary path was changed. Documentation UTF-8, link,
JSON/raw-evidence equality and diff checks passed again. Source remains unchanged.
