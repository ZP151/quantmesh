# Selected-instance OpenD maintenance implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (or the repository's bounded fresh-implementer/reviewer equivalent) task by
> task. No runtime interruption is released by this plan.

**Goal:** Prepare one exact-owned-instance retirement and same-build successor
route for consolidated operator review, then execute only after the actual
interruption decision and all applicable admission gates.

**Architecture:** One finite operator retirement module uses existing authenticated
provider identity plus held pidfds; the unchanged reviewed service manager owns
descendant cleanup. An immutable private adapter reuses stopped-provider start,
private CB1 login and authenticated successor binding. Source7/collector stay
unchanged; offline preparation and actual maintenance are separate phases.

**Tech Stack:** Existing Python stdlib, Linux pidfd/proc/cgroup2/systemd and the
already reviewed Windows secure-credential/browser-extension route. No install.

**Spec:** `docs/superpowers/specs/2026-11-07-opend-selected-maintenance.md`.
Issue [301](https://github.com/ZP151/quantmesh/issues/301).

## Global constraints

- Exact same host/OpenD+SDK10.10.7008/config/loopback11112/template and limits.
- Provider memory1GiB/swap0/CPU50%/tasks128; no automatic restart/boot enablement.
- Current login preserved during preparation; no host/SDK/credential actions.
- No new observer/platform/collector version/dependency/data/math/live changes.
- Spent/UNKNOWN/old holds/futures retained; fresh control/once after real decision.
- Maximum300s maintenance control and30s selected closure window; no escalation.
- Complete fresh census/forecasts before writes/runtime; free floor50GiB.
- Roles and independent reviews are visible in iteration0038; one consolidated
  fix/R2 maximum, then reduce scope on a third structural failure.

## Review focus

1. PID reuse or changed invocation between snapshot/fsync/signal never targets a
   replacement process; hold handles and revalidate after durable intent.
2. Signal or crash after durable intent is never retried; UNKNOWN cannot start a
   successor or refund a request/hold.
3. Same-name cgroup replacement, lingering descendant or foreign listener never
   counts as old closure and is never killed.
4. Cleanup exceptions do not mask primary interruption; all owned handles and
   query children receive mandatory cleanup attempts.
5. Saved credential metadata is not credential validity or vendor login; OTP and
   failed startup preserve honest state without automatic loops.

## Task1: exact selected retirement and proof

**Files:** Create `deploy/aws/opend/selected_maintenance.py` and
`tests/test_selected_opend_maintenance.py`; update the active iteration and reuse
matrix. Do not change stage_console/restore runtime/native/Source7.

**Interfaces:** `MaintenanceControl.parse(raw: bytes, expected_sha256: str,
now: datetime) -> MaintenanceControl`; `retire_selected(control, binding, ops)
returns a closed receipt only after all stop predicates`. Native operations have
fixed paths/commands and finite enums. Test operations are inert injected fakes;
no arbitrary caller-selected service, PID, path or signal is accepted by the
operational entry point. The exact adapter must instantiate native operations
from authenticated existing modules, not from runtime caller objects.

- [ ] Write RED `test_intent_fsync_precedes_only_held_main_pidfd_sigterm`:
  assert sequence verify/hold/reverify/intent+parentfsync/reverify/signal/closure,
  and exactly one SIGTERM to the held MainPID handle.
- [ ] Write RED control rejection tests for noncanonical/extra fields, wrong
  source/binding/authority, expiry and >300s window; assert no intent or signal.
- [ ] Run focused pytest and preserve actual failures before implementation.
- [ ] Implement only the closed control and finite retirement state machine.
- [ ] Add GREEN rejection tests for PID reuse, dead/replaced held handle,
  changed invocation after fsync, spent intent, fsync failure, query timeout,
  missing credential metadata, unavailable successor source path, closure timeout,
  lingering descendant, foreign listener and same-name replacement cgroup.
- [ ] Add cleanup-combination regressions: primary KeyboardInterrupt/OSError
  survives cleanup failure; all remaining handles/children are still closed.
- [ ] Run `python -m pytest -q tests/test_selected_opend_maintenance.py`, changed
  file Ruff/format and `git diff --check`; record exact counts and limitations.
- [ ] Prove the native adapter's pidfd behaviour on an owned synthetic Linux
  process group/cgroup fixture. Never target the provider or production manager;
  if native fixture unavailable, report the exact missing check, not all-green.
  Successful native held-pidfd/owned-cleanup verification or an exact applicable
  reviewed prior result is mandatory before actual maintenance release.
- [ ] Independent Spec/Standards review of the complete module and native seam;
  one consolidated correction and same readers' R2 if required. Commit/push one
  coherent green source checkpoint from fresh origin/main4887f75b.

## Task2: concrete successor/operation packet

**Files:** New immutable ignored `operator-maintenance-01` package under the
existing recovery output, using pinned operator-restore-02 modules and the frozen
candidate Task1 helper for offline assembly/review. Actual publication/runtime
consumes the byte-identical final merged helper. Include tracked spec/plan/
iteration/ADR0032 checkpoint and one normal final PR.

**Interfaces:** Consumes the closed receipt from Task1, existing
`instance_data.validate(raw, sha) -> Instance`, restore installer/runtime `start`/`bind`, private CB1 login
adapter and provider validator. Produces pinned dry preparation, complete
geometry/forecast, operation order, one consolidated interruption decision
packet and a disabled default entry point. Actual controls/nonce/Fresh/intent and
provider binding are not fabricated during preparation.

- [ ] Write RED assembly test: no stop unless complete successor helper/source,
  same-build pins, credential metadata preflight and applicable interruption
  authority exist. All expected data are explicit, bounded and hash-bound.
- [ ] Write RED start test: a forged/missing/UNKNOWN closure receipt or changed
  old binding cannot reach mature start; a valid synthetic closed receipt reaches
  exactly the control-bound fresh synthetic instance, with old markers/binding
  unchanged. Concurrent/repeated entry, a changed successor nonce and interruption
  after per-maintenance SUCCESSOR-START-INTENT fsync but before mature start each
  prove at most one start delegation across the whole maintenance transaction.
- [ ] Write RED secure-login/binding test: finite OTP/device/failed-login states
  cannot claim READY; successful attributed synthetic binding preserves every
  strict source/identity/resource gate. No credential bytes in output/fixtures.
- [ ] Implement per-maintenance exclusive/fsynced SUCCESSOR-START-INTENT before
  delegating mature startup; its bound closed-receipt/control/sole successor and
  parent-directory persistence prevent a second start after failure or re-entry.
- [ ] Implement the minimal fixed orchestration and byte-pinned actual adapter;
  reuse existing secure credential API and launcher without copied SDK/vendor
  code, alternative raw service command or manual pin substitution.
- [ ] Verify focused complete package locally, source pin/closure/claim order,
  caps/forecasts, forbidden-call AST and Linux synthetic process cleanup. Retain
  all failed evidence. Two fresh independent Spec/Standards axes review actual
  complete adapter bytes, not only an abstract model.
- [ ] Run appropriate normal exact-head CI/publication for the actual tracked
  diff and standard guarded merge. No old healthy CI rerun, admin/force/bypass
  or fake human/GitHub approval. Source7 equality must remain exact.
- [ ] Present the complete reviewable packet to Root for the sole new active
  interruption decision. Include rollback limit (original login process cannot
  be restored), verified available saved-credential route, one successor/one
  acceptance attempt, full capacity and timing. No repeat ordinary login/count/
  capacity approval question. Do not touch the active unit while waiting.

## Task3: released maintenance and one real acceptance

- [ ] Consume actual applicable interruption authority and central net capacity
  receipt; create new immutable operational control only then. Freshly verify
  exact current binding/host/source/resource/free floor and login recovery route.
- [ ] Execute Task1 once. On UNKNOWN/incomplete closure: preserve old facts and
  stop; no successor or re-signal.
- [ ] Execute existing reviewed fresh-instance start once, private remembered/
  saved login and authenticated binding. Hand off only actual OTP/device event.
  Any new source/pin/config/endpoint/version difference returns to Planner.
- [ ] With genuinely changed condition and all new current normal admission
  gates, execute one existing-method Init validation. Timeout or incomplete
  closure stops this alternative; no new queue sampler or identical retry.
- [ ] Record actual READY+normal closure, or exact failure stage and UNKNOWN.
  Only real READY allows planning the later independently gated fixed capture;
  never revive capture13 or claim data/math/financial qualification.

## Self-review and current status

Planner selected only offline preparation of the same-build alternative; actual
interruption selection remains unresolved. Quant Researcher: no data/math or
sample reuse is touched and software/maintenance success is not financial
qualification. Required failure classes above have concrete tests. No missing
actual runtime data is replaced with a guessed nonce/authority/receipt. Task1–3
are not released for runtime. Builder R1 found one cross-instance start-once gap;
control/receipts now bind the sole successor and the transaction-level durable
start claim. Same-reader R2 ADDRESSED/READY2999B/59aea719 confirms the offline plan
is executable. Task1 and Task2 are ACTIVE under two independent source owners;
Parent owns only docs/Git/integration data while they write. Task3 NOT_STARTED.
First Task1 causal RED1/RED22 -> GREEN22 is intermediate software evidence, not
final review or native qualification. Native adapter/source/geometry/publication
and the consolidated interruption decision remain separate.
