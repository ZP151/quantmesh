# Iteration0038 — approved minimal SPY daily replay

Date:2026-10-22 Asia/Singapore. Phase1 tool engineering READY; no actual data or
numerical report yet. Tracking: [issue205](https://github.com/ZP151/quantmesh/issues/205),
OPEN/ready-for-agent, assigned once by the main/release owner. Existing product
context issue184 remains historical.
Plan: `docs/superpowers/plans/2026-10-22-minimal-spy-replay.md`.

## Planner

One user action: freeze one latest-completed-session SPY daily sample, then run
one fixed SMA100 job and reopen its original report and Reject/Watch decision.
Metric: one actual, traceable submit/report/decision/cold-reopen loop. Phase1 is
only data preparation; no proxy or fixture can satisfy actual data acceptance.
The human explicitly approved the two-stage design and execution here, without
repeat approval, in the canonical20261022 approval JSON. This agent owns only
the two Phase1 tool/test files and own docs. No SSH, SDK, collector, trading,
dependencies or other writer files. Native worktree starts at aa62fae.

## Quant researcher

Consume the approved121-session OpenD option, current source-use/account/field
evidence still outstanding.100warmup/21development, raw prices, nextOPEN proxy,
fixed SMA100 and5/10bps/same-cost buyhold+0interest cash. Existing cash entitlement
semantics require exact ex/pay date and units, no unsupported split. Old final
remains consumed; source change/recent dates do not establish independent OOS.
This phase invokes no financial arithmetic. Paper remains unauthorized.

## Implementer

Inline sole writer, branch codex/0038-historical-development-replay. Read required
context/roadmap/prior iteration/ADRs/reuse/cross-agent docs and skills. Dependencies
already present: Python3.13.9, pytest9.1.1, pandas2.3.3, numpy2.5.2,
exchange-calendars4.13.2, Ruff0.16.8; none installed. Short plan self-reviewed,
then test-first work. External data qualification does not block local tool/tests.

## Reviewer

Independent read-only Phase1 review to cover calendar completeness, bounded source
reads, raw/action semantics, gate-before-effects and immutable artifact integrity.
At most2rounds; no new implementer or overlapping source writer.

## Verifier

Fresh targeted checkpoint:48tests passed,5upstream exchange-calendars/NumPy
deprecation warnings, changed-file Ruff/format and whitespace checks passed.
Receipts/logs live in output/0038-spy-replay; progress.json binds both source
hashes and actual own-worktree imports. Offline CLI window smoke confirms
2026-04-29..2026-09-21 warmup,09-22..10-20 score at as-of10-21T16:00Z.
No actual data request, financial evaluation or Phase2 source work occurred.

TDD: initial missing-module collection RED is separate from33behavioral REDs,
then34 after explicit warmup-only pay-date scope test. An initial global pytest
temp cleanup encountered a foreign stale permissions failure; subsequent runs
use unique worktree-owned --basetemp directories, preserving earlier output.
Core boundary RED exposed missing US market metadata, then a wrong stock-split
page_size1000 against the existing public client's maximum50; both were traced
and corrected without SDK changes. Additional5real behavioral REDs covered
integer1 masquerading as True in source evidence, foreign currency, forged cost
protocol, CLI assembly and once-only capture. Help RED exposed764557characters
from argparse choices=range; bounded port help now passes. All original logs
remain; no old CI/full-suite counts are reused.

The tool reuses public client/provider and ObjectStore. Source-use/account/field
receipts are externally reviewed inputs, not grants manufactured by the script.
Every frozen receipt still requires independent actual-source/field review.
The once-only CLI preserves its intent and bounded plain transport responses
before downstream client/provider validation, including refusals. Each observation
has the exact request, receipt time and content-addressed response reference;
typed paths distinguish encoded bytes/nonfinite values from literal JSON maps.
The journal caps six returned calls and8MiB total. SDK failures before returning
plain values, oversized payloads and unsupported value types cannot be retained
at this boundary. Root/data owner must not automatically retry another host/root.
Warmup dividends remain in signal inputs, while missing warmup pay-date does not
create preperiod positions. Observation-period cash events require exact dates.

Independent review round1 ran40tests and found three Important gaps: raw evidence
lost on downstream refusal, reused source fingerprints absent from the immutable
protocol, and outer qualification/time claims insufficiently checked on reopen.
One aggregate correction batch added8behavioral REDs (40prior tests still green),
then48passed. The actual loaded provider/client/market-data/calendar/ObjectStore
hashes are now protocol-bound, source drift refuses before freeze publication,
and reopen preserves original source/runtime identities while enforcing fixed
qualification, exact envelope fields, as-of<=capture<=freeze and evidence freshness.
Logs13-15 preserve RED/GREEN; Ruff import ordering was corrected mechanically
before the final48test checkpoint. No third structural correction round is allowed.

Independent verifier spy_phase1_verify completed final round2: READY, no remaining
Important/Critical findings,48passed/5warnings in one targeted run. Parent read
the actual report and independently ran48passed/5warnings again (log17), then
changed-file Ruff/format/whitespace checks. Tool SHA256
`36be4fb0f8c725bdabda813f710f40f883cb3949d858e9b73f08bf2000057d0d`,
tests SHA256 `426292db928d41ba7a7c298bdfd06ed232313f0bbd167c49a389a609990c0a7b`.
No second implementation writer and no further review round.
Actual capture remains blocked by outstanding external use/account/field evidence.
The current orchestration register records an actual existing-browser attempt
that reached a login boundary; this is not account/use qualification. No data was
fetched and no credential or contract-signing request is introduced here.

## Resumable product Goal

The human explicitly requested long Goal driving in this product thread. A new
active Goal tracks the approved research loop; old P1/P2/P3 completion remains
historical and unchanged. Engineering readiness is distinct from actual Phase1
sample acceptance. Phase2 remains conditional on the qualified sample and is not
started. Report evidence and concrete remaining inputs to the main coordinator;
do not repeat design approval or take over another owner's server/data work.

## Current acceptance checklist and next boundary

- Engineering: tool capture/freeze/verify assembly and refusal evidence tested;
  immutable source/protocol/runtime/member provenance checked. Local checkpoint
  only; no CI, merge, deployment or broad-suite claim.
- Actual input: NOT PASSED. Applicable existing API agreement/use evidence,
  fresh account/history quota and actual SDK/field compatibility are absent.
  The designated OpenD owner must supply them and perform the once-only capture.
- Financial/product loop: NOT STARTED for this new sample. Zero market-data
  calls and zero financial evaluations in this worktree. The earlier fixture
  loop does not establish this sample's report, decision or cold-reopen acceptance.
- After genuine input PASS: report the freeze receipt and exact Phase2 ownership
  to the main coordinator, then proceed under existing approval. Do not rerun the
  consumed final, change the fixed window after outcomes or promote to Paper.
