# IVV native producer implementation plan

Refs: issue #272; spec ../specs/2026-11-01-ivv-native-producer.md. Base origin/main ca0856e35026da32837818639854be02a1521baa. Original helper and prior evidence stay immutable.

## Ownership and files

Parent: this plan/spec, docs/iterations/0038-ivv-native-producer.md, active/roadmap/ADR checkpoint, Git/integration/whole-packet verification.
Implementer/original executor: tools/research/ivv_native_producer.py, tests/test_ivv_native_producer.py; private artifacts only under the new implementation purpose.
Fresh Reviewer: read-only independent specification/quality R1, only located known-fix R2 if needed. Quant role: Parent verifies no market request, data, cost, leakage or math change.

## Phase A — first verifiable user loop

- [x] Record real invariant/interface design and separate 8MiB complete forecast before writing implementation/fixtures.
- [x] Add behavior tests at the real check/collector seams; run Python 3.12 -B -m unittest discover -s tests -p test_ivv_native_producer.py. Retain actual RED output and failed fixtures within the assigned test bucket.
- [x] Implement the smallest stdlib-only native collector/evaluator that produces a safe exact failed predicate or feasibility-only facts. Cover fixed lifetime/identity, post-read races, mount graph, readonly parent/RW child, same-prefix/hidden/extra write paths, forged image claims, underlying storage and unknown writable FD channels. No positive production admission from synthetic facts.
- [x] Run the same targeted command GREEN, Python 3.12 compilation, available existing Ruff/format, whitespace and unchanged helper SHA checks. Do not install dependencies or invoke SDK.
- [x] Fresh independent R1 at the complete feasibility boundary; correct only located findings and run bounded known-fix R2 if needed. Stop/replan after a third structural failure.
- [x] Parent independently reads code/diff/tests, checks private outputs/full physical futures and freezes one packet. Original executor may invoke the check at most once with bounded transport; no SDK/source CLI/intent/permit/service effects.
- [x] Record actual native result and closure. If infeasible, stop issuer work, commit the coherent reviewed increment and give one exact failed predicate/minimum disposition. Do not claim current provider lacks a runtime/cap solely because proof is missing. Actual HOME_NOT_FINITE on2026-11-01T14:35Z; normal publication remains pending.

## Phase B — conditional, only if Phase A proves feasible

- [ ] Reconstruct actual trusted bool/enum configuration, source/control/FD provenance and readonly Linux SDK/runtime >=12 pins without XML/secret/env/argv reads. Missing proof refuses before intent.
- [ ] TDD the original actor's real 512MiB/swap0/CPU50%/Tasks32 controls and root-protected canonical evidence; bind actual actor/plan/catalog/provider independent hashes to regular root0444/nlink1/O_RDONLY held permit. Preserve caller FD ownership and fail closed on partial/replaced/stale input or close errors.
- [ ] Retain the original one-effect issuance/consumption and durable create-only intent before SDK factory/import/connect; call unchanged capture_once only after actual native gates. First state belongs to the original seven sends. No retry/context/nonce or wall reset.
- [ ] Independent parent proves actual normal RC0, owned actor terminal/recursive cgroup empty, callbacks/socket/FD closure, resource bounds and <=480 wall before CAPTURED_UNREVIEWED. Never terminate existing provider/login/tunnel.
- [ ] Independent actual input/Quant acceptance still precedes the separate original ten-arm development trial.

## Publication and recovery

At coherent green commit/final PR boundaries run the relevant repository gates, exact source review and unchanged-helper/contract checks. Source changes use normal matching-head CI/merge and a real merged catalog; no old ca085 catalog grandfathering. Carry reviewed export fix b833 only if compatible with the naturally required final CI. No standalone CI/duplicate watcher.

Commit each coherent green checkpoint and preserve RED/review/native failures. Record every phase in the iteration. Keep issue #259/#272 open while original native/data user-loop acceptance remains unmet. No cleanup, reset, force push, quota refund or borrowed old purpose.
