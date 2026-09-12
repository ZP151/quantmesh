# Iteration 0035 — Real charts from Markets and Watchlist

- Status: chart PR merged/deployed; continuous-source acceptance failed;
  bounded identity/request-clock follow-up in progress, 2026-09-12.
- Issue: [#144](https://github.com/ZP151/quantmesh/issues/144).
- Original branch: `codex/0035-live-instrument-charts`, from `origin/main@2a50565`.
- Follow-up branch: `codex/0035-chart-acceptance`, from merged `origin/main@90fe577`.
- Plan: `docs/superpowers/plans/2026-09-12-live-instrument-charts.md`.

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
- [ ] Final source checks, bounded independent review and required CI pass;
  integrate through PR and verify the exact approved AWS deployment.
- [ ] Actual AWS navigation/chart update/reload witness is recorded separately
  from controlled disconnect/recovery tests. Paper true/live false; no orders.
- [ ] Update roadmap/ACTIVE and retain Moomoo/OpenD readiness as next frontier.

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
