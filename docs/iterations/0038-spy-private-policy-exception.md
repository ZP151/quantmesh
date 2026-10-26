# Iteration 0038: SPY private diagnostic exception, bounded product leaf

Status: implementation complete; source freeze and independent review pending.
Issue: [#177](https://github.com/ZP151/quantmesh/issues/177).
Base actual main:198a9f8776ed6531c8ca206086f4a600e1969a65,
tree006714ab12e841048162099ec9e06f36e3422154 (merged PR230).
Plan: [technical boundary](../superpowers/plans/2026-10-26-spy-private-policy-exception.md).
Decision: [ADR0035](../adr/0035-spy-private-policy-exception-once.md).

## Planner / Product

One action: after independently qualified real input arrives, start or reopen the
one existing SMA100 diagnostic and its immutable report/decision. Software success
is an explicit exception chain, one deterministic job and cold historical evidence
without current-options backfill. Five production files, four new tests and three
own documents are the complete lock. No engine, strategy, provider/feed, data
normalizer, dependency, database, public request, live-trading or platform changes.
The sole publisher owns generated artifacts, full CI, PR/merge and deployment.

Initial ACK07:44:53Z was interrupted by a harness update/os87. Root resumed the
same slice at14:38:51Z on2026-10-26, with core15:38:51Z/final16:38:51Z deadlines.
No work, approval or uninterrupted runtime is inferred during the interruption.

## Quant researcher

Consume the locked policy SHA91cf0c560cadab5f80a3421604fa90b0ad5e7dc6b7ae5492058cb4013f2ccd36
and approval SHAff2d3886c07504854a6ece89f4029177d51182eb7f99b33354b6268610b9b2c9.
External storage applicability stays UNKNOWN; provider permission stays false.
The 121-session100+21 split, original raw USD/shares/RTH gates, warmup cash,
ex-date/pay-date distinction,5/10bps costs, same-cost benchmarks, unknown PIT,
financial INSUFFICIENT and paper=false remain mandatory. This leaf performs no
SDK/host acquisition or financial calculation. Synthetic fixtures cannot qualify
actual data or establish a profitable strategy.

## Implementer

Added strict pinned B0/B1 proofs and canonical once consumption before SDK setup;
v3 collection/freeze/reopen reuses original gates; trusted descriptor and report3
preserve original proofs in the existing CAS. The existing job key prevents a
second computation, even after failure. UI parses explicit new versions, displays
internal exception/external UNKNOWN, and reopens the same job. Old report2 still
has no exception facts inferred from options.

Two concrete refinements: protocol30585B cannot fit a uniform16KiB proof cap, so
protocol/freeze retain the pre-existing1MiB ceiling; other proofs remain16KiB.
The canonical authority root comes from private operator configuration independently
of the authorization root pin. No budgets or public settings are added.

## Verifier

Evidence directory: `output/spy-policy-exception-once/` in this managed worktree.
Retain failures01,03,05,07–11,13–14,16,19–20,25 alongside their fixes; mislabeled
early GREEN filenames do not make their actual failed exits pass.

- 26-core-green.log:24 new Python checks passed,5 existing NumPy calendar warnings.
  Includes authority tampering, pre-read size rejection, fixed policy source,
  canonical marker/no-refund before doubled SDK construction, unchanged v2 reopen,
  descriptor pins, failed/concurrent once-job handling, cold proof/decision binding.
- 28-frontend-green.log:11 checks passed across the two new parser/panel files.
- 27-ruff.log: all five locked Python files pass; formatter applied only there.
- 29-typecheck.log: scoped TypeScript check exits0.

Python calculator tests use a deliberately nonfinancial sentinel, not an actual
backtest or a numerical golden. This is an explicit testing deviation from the
plan, allowing job/evidence verification without author financial execution.
Frontend uses a local ignored junction to existing dependencies: actual Vitest3.2.7
versus lock4.1.11. Local tests are not an exact-lock CI certificate. Owned config,
cache and buildinfo stay in output; publisher owns exact-lock CI. No old full
suite, SDK, host, financial calculation, GH or CI was run by this leaf.

## Reviewer

One independent whole-slice review follows source freeze. At most one known-fix
round2; a third structural failure returns to Planner rather than expanding scope.
No acceptance claim is made before that review returns.

## Remaining user-loop evidence

Actual qualified SPY input identities are still absent. Sole server owner must
register its fresh real B0 against one configured canonical root and consume once;
independent Quant reviews actual raw/freeze/acceptance. Only then run the authorized
one new actual job/report, record Reject or Watch and cold-open that same job.
The original independent research goal remains active. Root owns the Goal and
ongoing coordination; this leaf must not mark it complete.
