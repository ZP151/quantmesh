# Iteration0038 — frozen experiment inspection, P2

Issue: [191](https://github.com/ZP151/quantmesh/issues/191).
Status: source implemented and checked; final-source page/review acceptance pending.
No merge claim.
Spec/plan: `docs/superpowers/{specs,plans}/2026-10-19-frozen-experiment-p2.md`.
Architecture: [ADR0031](../adr/0031-frozen-experiment-inspection.md).

## Planner

One user action: import the existing frozen SMA100/SPY evidence, inspect its
consumed holdout and recorded verdict, download originals and reopen it.
Measurable outcome: actual local UI completes this loop with all reference
digests checked, one deduplicated history entry and stable first receipt after
restart. No strategy execution, new evaluation or permission promotion.

The operator specifically approved P2's unique short design via the main
coordinator on 2026-10-19. Exact presented-question SHA256:
`785baf4120edc44208142f26db4def1b4db26e3331f242ac7354b70d2e27258f`.
The digest was computed when consuming the reply, not approved in advance.
P1 is merged as31b1c74; this isolated branch starts there. P1's existing preview
and immutable store are preserved. Future P2 merge and unseen P3 are separate.

## Quant researcher

This adapter imports recorded results and checks identity associations only.
Final primary 5bps net return26.12% is positive in absolute terms but below the
buy-and-hold benchmark; the result preserves proxy REJECT and formal R1/R2
INSUFFICIENT, R3 NOT_AUTHORIZED. Final OOS is consumed and not a pristine blind
or prospective test. One current trial/zero searched parameter variants does
not establish the complete prior trial count, which remains unknown.

Daily OPEN is a proxy for the original execution intent. Cost assumptions are
proxies, not observed NBBO costs. Keep eight diagnostics fixed and do not promote
the favorable lag+1 case. Confidence bounds are not probabilities of skill;
benchmark underperformance is not proof of intrinsically negative alpha.
PIT, rights, historical executable prices, utility/risk budget and the 2021
dividend discrepancy remain unresolved. Freeze receipts preserve claims without
independent chronology proof. No historical experiment/OOS was rerun here.

## Implementer

Exactly one writer owns the new catalog/router/page/API/tests and bounded
workstation/App/nav hooks. Main coordinated the exclusive messages.ts window:
only nav.frozenExperiments in en/zh-CN. All other new page copy is dedicated.
DataReadiness and its local tests/CSS remain under the UI owner's separate
approval. Parent owns local packet, docs and final generation/acceptance.

The retained package has 46 members and 1,037,090 bytes; archive SHA256:
`793c87d467059ae9a3bd2e1e7e82ffdd9d28474f633033ee8cf24ca224b47d4a`.
All 45 source members are byte-identical; the manifest is newly constructed.
No original source was executed. Existing frontend dependencies were physically
copied into this checkout; no install, symlink/shared write or upgrade occurred.
Current synthetic TDD results will be recorded at the completed boundary.

First backend boundary: the retained RED log shows 19 missing-feature failures;
the subsequent focused run passes 19 synthetic tests. Parent additionally imported
the actual 46-member package through the new catalog using an independent copy of
the P1 snapshot store: all associations verified, eight fixed cases and the
primary 5bps case preserved, economics marked imported/not recomputed, chronology
unverified, and original verdict/OOS unchanged. Source P1 store hashes stayed
unchanged. This is catalog preflight evidence, not final API/page acceptance.

## Reviewer

The independent source review confirmed one Important issue: replacing the fixed
signal/execution text and recomputing mutually consistent linkage hashes was
accepted. Parent added two synthetic regressions and observed both fail, then
pinned the original causal close>SMA100 and next-session daily-OPEN assumptions.
The selected backend checks then passed 52 tests. The reviewer inspected this
bounded correction and marked the source finding addressed. No UI/client/asset
change was required. Final-source cold reopen and image review remain pending.
Maximum two rounds; a third structural failure returns to scope reduction.

## Verifier

Fresh parent checks pass 52 backend tests, 72 frontend tests, changed-file Ruff and
format, targeted frontend lint, TypeScript/package build and generated API
currency. Existing NumPy/Starlette deprecations, intentional duplicate-ZIP
warning and bundle-size advisory remain; no dependency change was made.
One scratch runner failed printing a Unicode checkmark on Windows after the
frontend command had already passed and saved its complete log/exit0 receipt.
Its stdout encoding was corrected without rerunning that passing suite.

The actual page imported the original ZIP, exposed checking progress and the
recorded verdict, assumptions, trials, metrics, fixed diagnostics and gaps.
The two actual browser downloads match original bytes: archive 1,037,090 bytes,
SHA `793c87d4…`; report 15,898 bytes,
SHA `de3fa726b500b902264af3e315ffd4dae2616e56bb526347835f2d96be3604fc`.
All nine HTTP artifact responses match originals and advertised SHA256.
Actual duplicate import preserves one history entry and the first receipt.
Controlled restart/cold page reopen and final desktop/phone evidence are pending.
Old full suites, old CI, P1 acceptance and consumed OOS are not rerun. Raw data
and local outputs remain outside Git. The P1 preview/source/store are untouched.

## Continuation

Complete P2 and report exact source/evidence to main. Keep full P1→P2→P3 goal
active; design approval for P2 does not authorize unseen P3 controls or future
source merge. No server/deployment, paid resource or live authority changes.
