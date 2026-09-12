# Iteration 0035 — Real charts from Markets and Watchlist

- Status: implemented and locally reviewed; final CI and AWS acceptance pending, 2026-09-12.
- Issue: [#144](https://github.com/ZP151/quantmesh/issues/144).
- Branch: `codex/0035-live-instrument-charts`, from `origin/main@2a50565`.
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
