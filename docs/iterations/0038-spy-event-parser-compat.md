# Iteration0038 — same-capture SPY event representation compatibility

Status: active software slice; real data qualification remains independent.
Issue: [#177](https://github.com/ZP151/quantmesh/issues/177).
Base actual main eee9d03a15852018f40aaa0c26463539c2859ef4/tree
93c50c309113ab3dc92300b6ff22e3b45a4e4d33, merged PR232.
Plan: [selected short plan](../superpowers/plans/2026-10-27-spy-event-parser-compat.md).

## Planner / Product

One action: interpret the same two actual English-month/compact-USD event rows
without recapture or changing economic rules. The source capture/auth/marker and
original31 event rows stay immutable; output is a reviewed offline representation
compatibility increment, not qualified input or a numerical result.

Actual ACK03:22:03Z on2026-10-27; plan delivered03:28:47Z before03:37:03Z deadline.
Root approved the exact2production+1newtest+3owned-doc lock and clarified warmup
missing pay remains permitted under the original rule. Implementation ACK03:32:49Z
is receipt only, not a fresh approval or clock reset. Human timebox approval SHA
52db7815f13f159dbce64ab1f7ae60b2fd3ba71cb835f6ba76c06f2f1b15a14e is already consumed.
Selected tighter deadlines remain04:22:03Z first GREEN and05:22:03Z reviewed packet.

## Quant researcher / facts consumed

Independent actual PostReview result SHA
fc198a08fee5d7fbd5f1ade677d7a1f35266b7970ed6088ab3e2383661577a5e separates A-format
failures from B-semantic gaps. Actual raw d882c232..., authbb456ef4..., marker82828629...
remain bound to original PR232 toolSHA85ffc0f2... and its five module identities.
Two same-ex per_cash_div amounts exactly match1.88883USD/1.90352USD statements;
actual ex/pay dates are retained, both ex dates in warmup. No new price/event source,
SDK, host, customer/terms search or strategy calculation is authorized here.
Volume shares, feed coverage and source price-USD mapping remain with independent
Quant. Parsing success cannot fill or approve those fields. Internal exception,
external UNKNOWN, financial INSUFFICIENT/paper=false and all budgets remain.

## Implementer

Reuse unchanged `_day`, `_cash_statement`, `_actions`, `_normalize_payload` through
an explicit read-only derived event view. Fixed English months avoid locale; exact
Decimal matching supplies only this cohort's compact cash interpretation. Window
selection occurs before pay/statement interpretation. Raw and original review
records are not rewritten; original actions still own noncash/duplicate/pay gates.

A strict v3-only PostReview subclass selects the closed-cohort profile. Its small
protocol normalization block preserves old capture/source identities. Existing
protocol normalizer_sha256 honestly describes the newly loaded offline tool.
Cold verification reconstructs that block from the validated profile and pinned
cohort; the same eight existing thin proofs carry it. Legacy models/field sets,
permission helper, public interfaces, engine, strategy and UI remain unchanged.

Ruling: test-only fixtures replace private trust/cohort constants in-process to
exercise synthetic freeze and sentinel-job paths without certifying actual data.
There is no public/cohort configuration override. These controlled facts are not
actual PostReview/freeze/acceptance. This keeps the real B gates closed while
verifying hash/source lineage and cold behavior.

## Verifier

Owned evidence: `output/spy-parser-compat-20261027/` in this leaf.
01-event-parser-red.log:33FAIL/1PASS for missing new helper;02-event-parser-green.log:
34PASS/1existing calendar warning. This first targeted GREEN precedes04:22:03Z.
03-profile-binding-red.log:10FAIL/34PASS, including strict non-string refusal and
missing profile lineage paths.04-profile-binding-green.log:44PASS/5existing warnings.
All checks are in the ONE NEW test file; no old44-suite/F0 or old full v3 review ran.
Synthetic calculator is explicitly NO_FINANCIAL_COMPUTATION. No actual normalized
prices, qualified PostReview/freeze/acceptance or financial calculation produced.
05 adds original noncash/duplicate/observation-pay refusal and self-declared
lineage counterexamples:49PASS. After scoped formatting,09 RuffPASS;10 source pins
match all15 original AST nodes, every non-verifier replay method/model and full
engine bytes. Declared capture origin matches original Git blobs, including the
old tool85ffc0f2...; new offline tool is0d94256bb55f7a1a61de4e25142400c091e7d03b584a131bd13b7899002a8a64.
12-final-targeted.log reports49PASS/5 existing calendar warnings on final bytes.

The allowed actual EVENT-ONLY probe uses only original action fields/window and
minimal format selectors, never constructs a qualified PostReview. All31 source
rows remain intact; exact two cash/ex/pay mappings and warmup membership pass.
Raw/auth/marker/original-manifest hashes match before/after. Status is explicitly
FORMAT_COMPAT_ONLY_NOT_DATA_QUALIFICATION, B semantics NOT_ASSESSED_BY_THIS_PROBE.
No normalized price data, freeze, acceptance, SDK or financial result is produced.
Historical08/11 logs and a narrowed date/cash-only final probe are retained.

## Reviewer / remaining gate

Freeze source after final targeted checks/pins and dispatch one fresh narrow
parser/lineage reviewer; at most known-fix R2. Do not reopen the old v3 slice.
Sole publisher owns generated artifacts/CI/normal merge/deployment. Independent
actual B evidence, later real PostReview→freeze→acceptance and the already-authorized
single actual job remain outside this software completion. Goal stays ACTIVE.
