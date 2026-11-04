# Fixed IVV recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans with Server and original
> Product as the two exclusive source writers; TDD and bounded independent review.

**Goal:** Resume the existing IVV user loop with durable external/compute attempts,
atomic accepted-input/result publication and readable committed originals.

**Architecture:** A small IVV-only shared policy/identity contract surrounds the
existing capture claims/observer, ObjectStore, WriterLease, JsonlStore and report
mechanisms. External uncertainty remains UNKNOWN. Source/authority versions are
provenance; experiments bind semantic inputs and the existing accounting contract.

**Tech stack:** Existing Python/stdlib/Pydantic, local immutable objects/JSONL and
existing owned native runner/SDK/transport. No dependencies, generic framework or
new permit issuer.

**Spec:** [frozen Server/Product boundary](../specs/2026-11-04-ivv-transaction-recovery.md).

## Global constraints and review focus

Preserve all old evidence/charges/futures and old-family interpretations. Current
human direction6db1254 replaces repeated single-shot approval gates. Current
12GiB/6GiB/free50GiB and complete236MiB hold apply; software44MiB is shared (Server7/Product16/common20/FS1). Data/math,
credentials, no-paid, read-only protocol scope and paper/live boundaries remain.
One integration branch/CI observer; no old PR280 revalidation or diagnostic sandbox.

Tests must exercise: lost acknowledgement/possibly sent request, interrupted owner
and UNKNOWN cleanup, cross-epoch partial input refusal, source/authority refresh
without semantic identity reset, and report-put/prepared/commit crash boundaries.
No success or zero-usage inference from a spent claim, limit or origin phase.

## Task 1 â€” shared policy and stable identity (Server)

Files: create src/quantmesh/research/ivv_recovery.py;
tests/test_ivv_transaction_recovery.py; shared spec/iteration/ACTIVE/roadmap/ADR.
Interfaces: business_key(identity), validate_identity(identity),
semantic_input_version(semantic), logical_job_id(identity), research_effect(identity),
capture_scope_id(), validate_policy(policy), policy_provenance(policy),
attempt_policy(policy,policy_ref), validate_attempt_policy(value,policy).

- [x] RED: unknown identity fields, wrong business key, semantic missing/extra raw
  authority aliases, malformed refs, policy booleans/overflow/headroom, allowance
  extension without a new identity. Run only the new direct tests and retain RED.
- [x] Implement exact closed canonical schemas and strict finite values; no effects.
- [x] GREEN targeted pytest, Ruff/format; publish immutable shared input to Product.
- [x] Commit coherent shared contract checkpoint; retain old branch/history.

## Task 2 â€” durable external attempts and actual recovery path (Server)

Files: tools/research/ivv_additional_task.py, capture_opend_ivv_daily.py,
ivv_dev_diagnostic.py, ivv_trusted_runner.py, direct tests; versioned private ops.
Consume shared policy; preserve old entry defaults. New family uses the current
human direction/pinned policy and existing native held controls, not a new issuer.

- [x] RED real durable intent -> MAY_HAVE_SENT -> response/close transitions with
  crash/uncertain flush, budget/rate refusal, same structural failure blockade,
  complete checkpoint reuse, and no cross-epoch assembly. Existing storage/owned
  process and SDK seams are modeled; do not issue real SDK calls during tests.
- [x] Persist intent/possible effects before SDK side effects. Bind all responses
  to exact request/context and immutable originals; preserve uncertainty/debits.
- [x] Adapt actual carrier/runner/observer to bounded expandable batches, actual
  protocol counters and proven owned cleanup before successor connection.
- [x] Validate and atomically publish a complete candidate manifest; retain failed
  originals. Run affected capture/authority/cleanup tests and record evidence.

## Task 3 â€” resumable numerical attempt/result loop (Product)

Files: ivv_admission.py,ivv_runtime.py,native_daily_real.py and direct tests;
minimum native-daily-api.ts/NativeDailyPanel.tsx consumer guard if necessary.
Consume shared helpers and exact trusted recovery_policy_ref/identity. Existing
WriterLease and JsonlStore remain the only job/result commit mechanism.

- [x] RED interrupted recovery, policy extension/cross-A non-reset, same-business
  concurrent duplicate, prepared report lostack/zero-recompute and immutable
  committed report/decision. Keep old-family regression behavior.
- [x] Implement trusted recovery registration, per-attempt state/counter and
  prepared-report-before-committed pointer. New experiments require registration;
  recovery computations are not new published/OOS experiments.
- [x] GREEN direct tests/static checks; freeze exact source/diff/owned paths and
  complete16MiB subset accounting for Server integration. No Product host/CI work.

## Task 4 â€” integration, independent review and normal publication (Server)

- [ ] Integrate only the disjoint frozen Product files; run the connected actual
  policy -> capture original -> acceptance -> registration -> recovery -> committed
  report/decision/cold-read harness. Engineering seams remain disclosed.
- [x] Fresh two-axis independent R1; at most one consolidated RED/GREEN correction
  and same-reader R2. Material structural R2 blocker returns to scope reduction.
- [x] Relevant broad checks at final boundary, one normal matching-head PR/CI,
  actual merge-policy scope and guarded merge/full source/catalog provenance.

PR282 merged0e0d3cf4 after final-head423113cf CI41909344046 and actual full-tree/
catalog/exact-lock verification. First actual entry then stopped at INITIAL/
EXECUTABLE with SDK counts UNKNOWN; see the bounded [failure-evidence addendum](2026-11-05-ivv-executable-failure-evidence.md).

## Task 5 â€” actual bounded recovery and user outcome (Server/Quant/Product)

- [ ] Adopt consistent current policy/source/manifest/guard and actual applicable
  owner/config/resource/free/cleanup checks; no standalone diagnostic sandbox.
- [ ] Resume a complete immutable checkpoint or record actual connection/request
  intents, finite failure evidence and possible effects; repair concrete structural
  refusals before continuing, register reasonable batch growth without per-attempt
  human questions. Stop/escalate actual OTP/new paid/security/data/math differences.
- [ ] Quant independently accepts actual H1/H2/H3/coherence or records INSUFFICIENT.
- [ ] Only accepted input enters Product; record compute recovery and one published
  report/decision, restart owned viewer and reopen same originals without compute.
- [ ] Mirror exact real outcomes and remaining blockers into active iteration and
  closeout. Source merge alone does not complete the long user goal.
