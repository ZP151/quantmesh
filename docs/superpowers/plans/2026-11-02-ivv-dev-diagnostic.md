# IVV DEV diagnostic implementation plan

> **For agentic workers:** Use subagent-driven-development and test-driven-development. Parent owns integration and native execution.

**Goal:** Deliver the one already-approved DEV diagnostic capture route without restarting eabdda, then hand actual originals to independent input review.
**Architecture:** Keep strict capture and existing data/math core. Add an explicitly versioned DEV contract, trusted purpose-limited issuer/held permit, shared once consumption, native evidence acquisition/monitoring, and matching existing consumer.
**Tech:** Existing Python stdlib/helper, installed runtime and repository stores; no new dependency.
**Spec:** Operator-approved ROUTE-DECISION-MEMO.md (16971 bytes, SHA256 43abe7d5b31afacd6d291eeeadab33d182d60777986de828b230ca35615d4029), approval output/0038-orchestration/eabdda-route-A-approval-20261102.json in the research integration worktree; original issue272/259 invariants.

## Global constraints

- Original scope e28541ddae3d7b567e23e2963cc454995aa01c420bd567d8eb8aace6b6354f07, execution 0f523db13273e7325cad752e529eece44168a17903275d0047adf1e93b50efa3 and original effect; policy/helper versions never create a second opportunity.
- Preserve strict-v1 default, original five-field provider_actor, seven sends/one context, 121 dates/100 warmup/21 observations, capture512MiB/swap0/CPU50/Tasks32, output7MiB+SDK log1MiB, phase180/360/390/420/480 seconds and original mathematics.
- DEV only excepts provider32MiB/fullRO-sixRW enforcement and legacy loaded-guard provenance, with hard_limit_enforced=false and provider_tail_max=UNKNOWN. Monitoring is not a hard limit. G10500000000/P4500000000/free53687091200 remain thresholds, no increase.
- Actual identity, typed config, readonly Linux SDK/runtime pins and unknown external persistent-writer refusal remain required. No secret/XML/account/env/argv/terminal payload read or hash.
- Existing provider/login stays untouched; no B/c8 maintenance/restart, second context, automatic retry, new environment, paid resource or trading authority.
- All historical originals/failures/holds retained. Code/tests/reviews/Git/CI within centrally registered producer12582912 bytes (original8388608 plus net4194304 on2026-11-02); original capture local24MiB/remote64MiB held separately. See dev-A-01/CAPACITY-FORECAST-12MiB.json and central ivv-dev-diagnostic-producer-12MiB-20261102.json. No old hold borrowing or threshold increase.
- Single code writer; Parent owns docs/Git/publication/native. Review max R1 plus one known-fix R2. First actual execution failure or third structural review failure returns to Planner.

## Ownership and interfaces

Implementer task1 owns tools/research/capture_opend_ivv_daily.py, new tools/research/ivv_dev_diagnostic.py, src/quantmesh/research/ivv_admission.py, tests/test_ivv_capture_contract.py, tests/test_ivv_admission.py, new tests/test_ivv_dev_diagnostic.py. No engine/math/frontend change.
Task2 owns tools/research/ivv_native_producer.py, tests/test_ivv_native_producer.py and native integration in ivv_dev_diagnostic.py, only after task1's contract is frozen. Parent owns this plan, iteration, ADR0042/roadmap/ACTIVE, release artifacts.
All operations explicitly use isolated checkout output/ivv-native-producer-20261101/checkout, branch codex/0038-ivv-dev-diagnostic, base origin/main b70cbe8ea96f12e926bcb90474947242c2b53f25. Frozen old branch and source-copy originals remain.

DEV schema family uses suffix .dev-diagnostic.v1: capture-plan, provider-evidence, root-permit, root-go, capture-intent, capture, capture-parent-close, input-acceptance, registration. Policy schema is qm.ivv.capture-policy.dev-diagnostic.v1. DEV22 plan is exactly strict21 minus provider_bounds_ref plus provider_evidence_ref and policy_ref. Never downcast to v1.
Policy digest and actual Operator authorization digest must be bound consistently across trusted GO, permit, intent, manifest, parent close, acceptance and persisted binding; expected trusted pins are startup-only, never browser fields. Shared plain/normalizer formats may remain v1 because originals/data semantics are unchanged.
New DEV issuer must read actual root-protected files, actual actor/native controls, helper/catalog/provider/policy bindings and independently held descriptor metadata. A caller JSON boolean is never a native proof or authority. Actual successful preflight yields root0444/nlink1/O_RDONLY non-O_PATH permit. Caller owns supplied FD.
Once key depends only on scope/execution/effect, with fixed canonical ledger location independent of output/policy/version. Reservation plus file+directory fsync precedes backend factory/import/connect. Failed/uncertain reservations remain spent. Strict mode remains strict, and switching policy/root cannot recover another context.

## Review focus

1. Valid DEV policy paired with stale strict GO/permit/intent/parent-close must refuse before SDK/intent as applicable.
2. Same original effect with a different policy/helper/output root must remain spent, including failure/fsync uncertainty.
3. Forged actor, replaced held inode, O_PATH/writable/linked permit or changed provider evidence must refuse, never accept declarative booleans.
4. Closure/monitoring failures must retain original failure and prevent accepted handoff; capture child cannot attest later process exit.
5. DEV consumer must still require independently accepted H1/H2/H3 facts and original checks; cold reads do not compute or manufacture acceptance.

## Task 1: Consistent contract/issuer/capture/consumer slice

- [ ] Add tests in the owned files that first fail: DEV22 positive through actual helper admission/issuer seams and shared scripted backend to manifest, parent seal and consumer registration; strict baseline remains unchanged.
- [ ] Run existing .venv/Scripts/python.exe -B -m pytest tests/test_ivv_capture_contract.py tests/test_ivv_dev_diagnostic.py tests/test_ivv_admission.py -q -p no:cacheprovider, with a bounded private --basetemp under dev-A-01; preserve RED. Assert literal schema fields, seven ordered sends/one InitConnect, byte/presence limits, policy/authorization provenance and create/fsync order.
- [ ] Test missing/wrong/cross-version policy and authorization; strict rejects DEV22; DEV cannot use strict bounds or false hard-limit claims; permit binding/inode/flags failures; spent effect across roots/versions; child success without valid independent parent closure; consumer cannot run without actual accepted facts. Test actual functions, mock only kernel/provider external boundary, never fabricate native qualification.
- [ ] Implement shared fixed-data validation plus explicit DEV entry and purpose-limited issuer in existing helper/new module. Preserve old source bytes in historical artifacts. No generic bypass flag, callback-only signer, schema downcast or production synthetic authority.
- [ ] Adapt existing ivv_admission consumer and cold binding/archive closure for DEV provenance while keeping original trial key/math/default strict behavior and separately trusted input acceptance.
- [ ] Run GREEN, affected Ruff check/format, whitespace and source pins. Parent independently reruns relevant checks, records exact failure/pass evidence and commits coherent slice. Do not run full release for each small edit.

## Task 2: Actual native producer and one bounded route

- [ ] TDD actual typed channel classification/inventory closure using original channel-models-01 as constructed evidence only: owned TCP11112, fixed eabdda TMUX unconnected UNIX listener, same-chain PTY, finite role REG/DIR; unknown/connected external peers/FIFO/persistent writers or identity/namespace drift refuse.
- [ ] Implement trusted configuration projection without exposing secret fields, existing readonly Linux10.10.7008 SDK/runtime >=12 actual pins/origin, real capture actor limits and independent parent normal-close evidence.
- [ ] Implement bounded metadata monitor: <=16384 entries, <=2s/sample, every5s<=97 samples in same480s, growth stop33554432; inode dedup/positive high-water/no names/payload, all within original actor. Missing/unknown/race or threshold/identity drift stops owned capture, leaves provider running and effect spent.
- [ ] Integrate actual issuer and capture in root-owned Linux runner; normal close only after RC0/terminal/recursive cgroup empty/FD+socket+callbacks/resource proof, <=480. No callback/self-assertion substitutes for kernel acquisition.
- [ ] Targeted RED/GREEN and static checks, one independent two-axis R1 of full coherent slice; only located known-fix R2. Commit/push one integration branch, one final PR; normal exact-head required CI/merge/catalog, no admin bypass.
- [ ] Only merged source plus all volatile native gates may issue actual runtime GO/held permit and consume original once. Parent/original native executor alone performs it; no separate SDK health context.
- [ ] Actual capture originals hand off as CAPTURED_UNREVIEWED with DEV exception or explicit failure/INSUFFICIENT. Independent real input review precedes original Product study; H1/H2/H3 unknowns remain possible, no new semantic gate or relaxed math.

## Verification and recovery

Baseline and targeted checks use existing environment with PYTHONDONTWRITEBYTECODE=1, no install. Broad release is the naturally required exact-head CI (prior normal run ~65–90min), not old PR273 reruns. Final includes relevant full pytest, Ruff src/tests/tools, diff --check, submodule pins and matching merged catalog. Actual software evidence does not certify native or financial behavior.

Private progress under output/ivv-native-producer-20261101/dev-A-01. Current app Goal remains historical blocked/mismatched; tools cannot resume/edit its objective and no duplicate Goal is created. Active tracked A plan/iteration are execution truth; original2h/4h start UNKNOWN.

