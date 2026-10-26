# SPY once-only private policy exception — technical boundary / short plan

Status: **bounded offline implementation reviewed READY; real input/research pending**.
Final sourcebee08a95514639dd75b7fa42d3a4e80b6c64bfab/tree
09055fb3a6db1db503908bfe5580172c28be679f. One independent whole-slice R1 found
two P2; the same known-fix R2 closed both. No third structural review. Durable
evidence is in the owned iteration. Publisher and real operator gates remain.
Root selected this plan and one implementation writer. Initial implementation ACK
was 2026-10-26T07:44:53Z. A harness update interrupted execution; recovery ACK
2026-10-26T14:38:51Z starts the renewed core deadline15:38:51Z and final reviewed
packet deadline16:38:51Z. The earlier RED/GREEN evidence remains retained.
ACK2026-10-26T07:24:14Z (Singapore15:24:14); plan deadline07:44:14Z (15:44:14).
Base actualmain198a9f8776ed6531c8ca206086f4a600e1969a65/tree
006714ab12e841048162099ec9e06f36e3422154 (PR230 already merged). Do not redo import fix.

Authority: raw approval bytes SHA256
ff2d3886c07504854a6ece89f4029177d51182eb7f99b33354b6268610b9b2c9;
approved proposal SHA256
aafd036f8e5402a14cb0c2a85421a27ab98cc69180e693c6ab8d4f8bbd7ead13.
Copies HUMAN-APPROVAL.json / APPROVED-PROPOSAL.md retain those exact bytes.
Locked Quant policy, now consumed in full:policy document version1 SHA256
91cf0c560cadab5f80a3421604fa90b0ad5e7dc6b7ae5492058cb4013f2ccd36
(LOCKED-QUANT-POLICY.md). Policy document v1 is NOT capture/schema v1. Its output
scope is complete; no further policy/terms research or waiting for a new document.

## One action / success / non-goals

After the one real input independently qualifies, run the existing SMA100 job
under this internal exception and reopen its same immutable report/decision.
Software success before real input: a distinct, strictly bound v3 exception chain
is accepted only with trusted approval/policy/intent identities; old v1/v2 bytes
and semantics stay unchanged; no extra job or claim follows from client strings.

No source/engine/strategy/dependency/PG/platform/permission ledger or new data
request. No SDK, host, price acquisition, financial calculation or GH/CI by this
author in the offline slice. Original server alone collects once after BTC window;
Quant independently qualifies actual fields. No data identity exists yet, and
no controlled test fixture will be submitted as a real research result.

## Concrete file lock (five production files, no overlapping Quant writer)

| File | Bounded responsibility |
| --- | --- |
| NEW src/quantmesh/research/spy_policy_exception.py | Strict once-binding types and raw-byte/hash verification under operator-supplied trusted pins; no registry, database or policy editor |
| tools/research/freeze_opend_spy_daily.py | Explicit v3 authorization/raw/evidence/freeze/reopen dispatch; existing bounded collector, original normalization/data/time/budget predicates reused |
| src/quantmesh/research/spy_replay.py | v3 trusted descriptor/acceptance/input, once-job key guard, exception-only report variant and cold verification |
| frontend/src/lib/spy-replay-api.ts | Strict new-version parser and fixed trusted intent key; old request body remains the two existing digest pins |
| frontend/src/screens/SpyReplayPanel.tsx | Existing badge/evidence rows only: internal once exception, external UNKNOWN, approval/intent and reopen wording |

New tests only:tests/test_spy_policy_exception_freeze.py,
tests/test_spy_policy_exception_replay.py,
frontend/src/lib/spy-replay-api.policy-exception.test.ts,
frontend/src/screens/SpyReplayPanel.policy-exception.test.tsx.
Own docs:docs/superpowers/plans/2026-10-26-spy-private-policy-exception.md,
docs/iterations/0038-spy-private-policy-exception.md. Approved own ADR0035 records
the versioning/one-shot decision; no shared
root docs/roadmap/REUSE changes by this leaf. All source remains under one writer.

Quant independently owns only its new policy/checklist output, not these files.
Root has relayed its immutable policy above. Product consumes that policy; it
does not choose new use rules or repeat terms/customer research. Fresh window,
output root and capture-intent identity are registered by the sole server owner
only immediately before actual dispatch; no PRE clock or UUID is generated now.

## Shared binding B / trust boundary

One strict binding B carries:

- policy_status=POLICY_EXCEPTION_ONCE;
- internal_decision=APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION;
- internal_once_exception=HUMAN_APPROVED and provider_permission_verified=false;
- external_api_storage_applicability=UNKNOWN;
- diagnostic_status=diagnostic_only_under_policy_exception;
- scope=US.SPY/1d/private_research, private/noncommercial/no-distribution;
- once_scope_id: the complete human approval SHA above, stable across changed
  policy file, output root, window or nonce; those changes do not grant another try;
- capture_intent_id: one planned UUID bound to the sole registration at actual
  dispatch, fixing this once_scope_id, output root and window;
- job_idempotency_key: one deterministic UUIDv5 of the complete once_scope_id
  (`uuid5(NAMESPACE_URL, "quantmesh:spy-private-diagnostic-once:" + once_scope_id)`),
  never of policy/root/window/nonce. It is bound
  to the sole registered capture intent, not supplied by the browser;
- human_approval_ref: original raw-byte ObjectRef/digest above;
- proposal_sha256: exact approved proposal digest above;
- policy_document_ref: exact Quant decision raw bytes/hash, with matching approval,
  proposal, intent, scope and unchanged-data/math/budget/stop-if-prohibited limits.

At fresh PRE, B is additionally bound to the existing actual window_sha256. B's
policy doc is not self-hashed: ObjectStore supplies its digest over original bytes.
Approval is copied byte-for-byte, never canonicalized into a different authority.
Avoid a circular self-hash: authorization contains B0 (policy/scope/planned intent,
window/output-root pin/job key) but NOT the later marker's ObjectRef. The fsynced
marker contains B0 + authorization_sha256 + actual consumed timestamp. Raw3 and
post-review3 bind its capture_intent_ref; freeze/acceptance/report carry B1=B0 plus
that same marker reference. All cross-checks compare B0 first and then the bound
marker bytes. No authorization hash depends on its own future marker hash.

Trust is the existing private operator configuration + independent acceptance,
not a public POST or checkbox. The private configuration pins the exact approved
human SHA and the relayed91cf0c... policy SHA. The one registered root/window/
capture intent is added just before dispatch under that stable scope. Validators verify referenced
raw bytes, bounded lengths, duplicate-key rejection, exact scope and tuple equality.
A self-declared digest without those configured pins and bytes grants nothing.
No public API may provide approval/policy files, source paths or a new intent.
If Quant's locked record establishes explicit prohibition, dispatch refuses;
missing records are not filled with invented permission or data facts.

## Explicit version table / checked chain

| Layer | Old meaning retained | New exception-only meaning and checks |
| --- | --- | --- |
| Capture authorization | schema2 strictly ALLOW_WITH_SCOPE | schema3 strictly POLICY_EXCEPTION_ONCE + B0 + original PRE/window/metadata/endpoint/version fields. Exact approved pins/bytes and canonical once location checked, marker created/fsynced before SDK creation; timing rechecked before data calls. No translation into a v2 ALLOW object, even in memory. |
| Raw/envelope/post-review | v1 read-only; v2 current strict chain | raw/envelope3 and post-review3 bind the real raw digest, v3 authorization digest, B0 and consumed capture_intent_ref. Same original post-review real-field/action/time predicates; policy alone cannot qualify data. |
| Protocol/freeze | v1/v2 original schema and reopen | protocol/freeze3 explicitly identify policy exception and bind B plus approval/policy CAS members. rule/costs/benchmarks/engine identity unchanged; actual normalizer/source identity remains honest. Freeze requires matching auth/raw/review/window B. Reopen rehashes/revalidates those same objects and derivation, never rewrites them. |
| Independent acceptance | legacy acceptance model/meaning unchanged | acceptance3 explicitly accepted_for_policy_exception_historical_diagnostic; bind freeze/protocol/auth/post-review/independent-review digests and B, with time>=freeze. Independent Quant review and all original data gates remain mandatory. |
| Operator descriptor/input | old exact descriptor accepted only for old valid freeze | descriptor3 selects only freeze3+acceptance3 and trusted B pins. Loader checks all hashes, time order, B equalities, window identity and existing normalized input verification. Public ReplayRequest still contains only snapshot_digest/protocol_digest. |
| Job/report | old job contract and report1/2 unchanged | reuse job1/idempotency ledger. New report3 with exception-only sample-evidence2 + B and existing refs, financial=INSUFFICIENT, paper=false. New evidence_kind=reviewed_opend_policy_exception_once_v3; cannot label it reviewed_opend_freeze_v2. |
| Decision/cold read | existing decision1 report/request/job digest binding | decision continues binding report3 digest transitively to B, with same request/job/snapshot/protocol checks. Cold open validates stored report3 B and same job identity without current options or recomputation. |

For cold trust, copy only the bounded approval/policy/auth/consumed-intent/acceptance/freeze/protocol
proof objects needed by report3 into the existing job ObjectStore before its
running record is published. Preserve their original bytes/refs; do not copy raw
price history. Revalidate their B equalities on cold read. Account these small
objects under existing limits/admission; no new capacity allowance is granted.
Old report1/2 do not get new fields or proof objects added on read or reopen.

## Once semantics: reuse existing Idempotency-Key == job_id

For new exception input only, request key must equal trusted B.job_idempotency_key,
whose UUIDv5 derivation from the whole once_scope_id is verified by the backend. Different
key refuses before store writes/calculation. Same key + same digest payload returns
the existing job, including failed/interrupted terminal result; it does not rerun.
Same key + changed snapshot/protocol retains existing idempotency_conflict. The
existing WriterLease/lock/running-before-compute publication provides concurrency
and crash behavior. No new permission ledger/DB, reset or retry permission.

Capture reuses one exclusive capture-intent.json at the operator's canonical
once-scope authority location, pinned independently of the variable data output
root. Its original create-only+flush+fsync boundary remains before SDK construction;
its content binds the fixed output root/window/authorization and B. An existing
or uncertain marker is consumed regardless of a new root, policy copy or nonce;
no delete/reset/second registration. This is a single scoped intent file using
the existing mechanism, not a new ledger/database/permission platform. The sole
owner's actual dispatch registers its fixed authority location once. Freeze and
acceptance bind the consumed marker's original CAS bytes/ref. Privileged deletion
or cloning of all trusted private state is outside the application's guarantee.

Frontend uses the trusted configured intent UUID only for this new variant; the
backend remains authoritative. Subsequent UI action reopens that same diagnostic,
never advertises a second run. Original old reports display only saved facts;
current options describe the next configured input and cannot backfill policy.

## Mathematical / actual-data invariant lock

Do not edit spy_replay_engine.py or original SMA100 functions. Keep original
100+21/121 sessions, USD raw OHLC, shares/RTH proxy, warmup cash effects, full
cash-action ex/pay/amount/coverage and unsupported-action refusals, 5/10bps cost
and same-cost buyhold/cash benchmarks. Keep metadata30min/as-of5min, original
max pages/rows/calls/bytes and source/version/endpoint checks. No missing=>0,
QFQ/HFQ substitute, truncated window, external permission/PIT/OOS/financial or
Paper upgrade. New protocol envelope changes evidence/version, not math.

Pin packaged engine bytes and original normalization/window/protocol-rule ASTs
against actual198; confirm unchanged at final handoff. Historic captures/reports/
hashes and v1/v2 paths remain readable under their original rules, not migrated.

## Short executable plan after root technical selection

1. **Fresh isolated leaf from actual198.** Add strict B/version models and new
   REDs: missing/tampered trusted approval/policy, external verified instead of
   UNKNOWN, altered scope/intent, schema2+exception and schema3+ALLOW all refuse.
   Add v3 auth/freeze/reopen with controlled transport and existing original
   validation, then GREEN. Include changed-output-root/policy-copy/nonce refusal,
   consumed/uncertain intent and pre-SDK fsync-order tests. No SDK/financial
   execution in offline tests.
2. **Trusted loader to immutable report.** REDs for mismatched acceptance/B/window,
   missing independent review, different once key, same key changed payload,
   concurrent submits, failed-job retry and cold reopen. Reuse existing engine
   call seam: controlled test sentinel returns an existing engineering golden
   result, counts calls; it is not submitted as qualified real data. GREEN must
   establish exactly one call and zero cold recomputation. Old report bytes/hash
   and old schema rejection/semantics remain unchanged.
3. **Minimal visible distinction.** New TS validator REDs for missing/mismatched B
   and version laundering; new panel tests for internal exception / external
   UNKNOWN, bound-key submission and same-job reopen, old report vs new options.
   Show badge “私人诊断 · 单次内部政策例外”; evidence row “外部 API 原件保存适用性：未知”.
   No approval button, “许可已验证” claim or UI redesign. GREEN targeted tests only.
4. **Freeze + bounded review.** Scoped static checks, engine/AST pins and targeted
   new tests; one independent whole-slice review, at most known-fix round2, no
   third structural round. Immutable handoff with exact head/tree/hash and role
   evidence; author no GH/host/SDK. Sole publisher owns build/client/CI/merge.

Suggested implementation timebox for root to choose: first RED/GREEN<=30min,
source freeze<=90min and final reviewed offline packet<=120min from a new actual
implementation ACK. A new required file or gate outside this lock returns to root
with a concrete counterexample; no automatic platform expansion.

## Real continuation / stop conditions (already human-authorized)

Do not wait for BTC to implement offline. Physical SPY collection remains queued
behind original BTC owner window and fresh server admission. Quant locks policy
and actual data/acceptance; this author makes no new PRE clocks now.

Once root relays actual qualified freeze3/acceptance3/B identities and an existing
configured app URL, use the existing five operator HTTP operations: verify options
pins, POST one new job with B.job_idempotency_key, GET progress, fetch/verify report digest,
record Reject/Watch bound to that report, cold reopen same job without rerun.
No new human confirmation is required for that authorized run. No synthetic or
inspect-only input replaces a failed real qualification. First actual field/data
or capture refusal is preserved and stops that real path; no automatic source
switch or new capture. Original research Goal is not declared complete on the
offline software fixture or this technical plan.
