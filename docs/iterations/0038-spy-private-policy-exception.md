# Iteration 0038: SPY private diagnostic exception, bounded product leaf

Status: bounded offline software READY after the sole known-fix R2; actual data
and the original independent research Goal remain uncompleted.
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
- 30-source-pins.json:15 original data/calendar/wire AST nodes and the complete
  packaged engine bytes match base. The engine SHA is
  6e8ad80f134b7c1f44bcb4cb7695e784009953aba9060326e8ecb2a54e624b8e.
- 32-frontend-lint.log: scoped oxlint exits0. No frontend code changed after28/29/32.
- 33-original-trust-pins.json: copied original approval/policy/proposal hashes and
  production predicate values match. No canonical marker, real B0 or SDK created.

Python calculator tests use a deliberately nonfinancial sentinel, not an actual
backtest or a numerical golden. This is an explicit testing deviation from the
plan, allowing job/evidence verification without author financial execution.
Frontend uses a local ignored junction to existing dependencies: actual Vitest3.2.7
versus lock4.1.11. Local tests are not an exact-lock CI certificate. Owned config,
cache and buildinfo stay in output; publisher owns exact-lock CI. No old full
suite, SDK, host, financial calculation, GH or CI was run by this leaf.

## Reviewer

The sole fresh independent whole-slice Spec/Quality R1 found two P2 and no P1.
`review-r1.md` SHA1abf376fdafc1693ae10aecfe48aeb186e439ae4f2c636fe97b46d4ae1eb470c
and the authorized bounded synthetic probe preserve the counterexamples.
First, saved v3 displayed dates/scope/field facts could differ from original thin
proofs. Second, v3 acceptance allowed duplicate JSON keys and several proof paths
read before checking actual size. No tracked source was edited by the reviewer.

16 new negative regressions reproduce both roots (34-review-regressions-red.log).
The bounded correction routes new v3 loads/copies through one stat/capped-read/hash
reader, rejects duplicate acceptance on initial and cold paths, and binds saved
window/costs/as-of/frozen/source facts/calendar to original protocol/freeze/review.
V3 replay requests opt into a bounded manifest read; old calls retain their prior
path. No old schema, raw data budget, normalizer or financial calculation changes.
35-review-fix-green.log: all40 new Python checks pass,5 existing warnings.
After formatting,37-final-core.log repeats40PASS on the final source bytes;
38-final-ruff.log and39-final-source-pins.json pass. No frontend source changed.
During this same R2, reviewer freshly ran40PASS (review-r2-pytest.log) and identified
three remaining `_freeze_v3` rereads under the already-known size-check finding.
40-r2-known-residual-red.log records4 failing regressions before correction.
Those proof rereads now use the bounded reader. CLI `verify --policy-exception`
explicitly opts into the1MiB v3 manifest path; default legacy behavior is retained.
This is completion of the same known F2 correction, not a third structural review.
42-final-core.log:44PASS/5 existing warnings after that correction and formatting;
41-final-ruff.log and43-final-source-pins.json pass.
The same R2 is now CLOSED READY onbee08a95514639dd75b7fa42d3a4e80b6c64bfab/tree
09055fb3a6db1db503908bfe5580172c28be679f. Report `review-r2.md` SHA256
1daf83477ae3f5fc1ba71bba03be6f2689e8f9aa5d3c85e6901bbc71d0416800 closes both
R1 findings with no unresolved known finding. Reviewer independently ran40 checks
on6a0d plus the final4 residual regressions onbee08, inspected author44PASS and
original15AST pins, and freshly recomputed the unchanged engine hash. No third
structural round or actual data/numerical/CI/deployment acceptance is inferred.

## Commit and integration boundary

Core source freeze550bf3f9d8a0a7388fe9be0cb209e92dd8f8cf7c/tree
f207b854cd2d477bad753473590bf111105f02f8 at15:05Z precedes the15:38Z core deadline.
Immutable `CORE-FREEZE.json` is explicitly REVIEW_PENDING and retained even after
fixes; it is not final acceptance. Commit hooks were explicitly bypassed for the
scoped source freeze because the sole publisher owns broad suites/CI/generated
artifacts. No push, PR or CI was performed by this writer. New glue uses existing
project engines/packages and adds no copied upstream source or license changes.
Final reviewed source isbee08a9; the following administrative commit changes only
this iteration and the owned plan to record the completed review. The immutable
handoff and bundle preserve exact final commit/tree, proof/log hashes and collector
contract. Sole publisher owns API generation/build/exact-lock CI/merge/deployment;
software READY alone is not a dispatch admission or a real-input qualification.

## Remaining user-loop evidence

Actual qualified SPY input identities are still absent. Sole server owner must
register its fresh real B0 against one configured canonical root and consume once;
independent Quant reviews actual raw/freeze/acceptance. Only then run the authorized
one new actual job/report, record Reject or Watch and cold-open that same job.
The original independent research goal remains active. Root owns the Goal and
ongoing coordination; this leaf must not mark it complete.
