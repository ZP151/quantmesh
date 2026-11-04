# Runtime-origin failure evidence implementation plan

> For agentic workers: original writer implements with TDD; one fresh scoped independent R1, at most one consolidated located-fix/same-reader R2. Parent owns verification and normal publication. No native execution.

**Goal:** A real trusted-entry failure retains the actually reached origin phase/predicate through the real finite STOP consumer, without changing admission or gathering another observation.

**Architecture:** Add finite per-call evidence to the existing runner. Preserve the original expression and need() truth tests. Carry the same bounded object through exception/IPC/aggregation and failure-file boundaries. Shared pure reader/STOP-selection functions in the existing runner are used by versioned actual carrier/profile adapters, avoiding a new release-source role or duplicated protocol policy.

**Tech stack:** Existing stdlib runner and adapters, pytest, existing Python/CI. No dependencies or environments.

**Spec:** [issue279](https://github.com/ZP151/quantmesh/issues/279). This repairs missing failure evidence, not the old SDK/runtime cause. Actual prior capture remains SPENT/UNKNOWN; the subsequent same-PID LL/cap differential did not reproduce it.

## Global constraints

- Branch codex/0038-runtime-origin-failure-evidence from actual origin/main381ac2c997dc35aec43bfd092ce85178fde249a9; preserve old e848 branch/user main and all old artifacts.
- Existing three predicates, short-circuit order, skipped lookups, equality/truthiness count, original exception object/type/args and fixed refusal codes remain. Traced lookup exceptions serialize only finite class/code, never raw args/messages; unrelated legacy reason handling stays. No eager booleans or additional SDK/proc/provider/env/argv/XML/log/old-once/K reads.
- Finite versioned evidence only: actual INITIAL/SESSION/UNKNOWN; actual last evaluated SDK_ROOT/PYTHON_VERSION/EXECUTABLE/UNKNOWN; FIRST_FALSE/EXCEPTION/UNKNOWN. EXCEPTION means the actual lookup/comparison/truth test raised, not a guessed underlying cause. No raw values, paths, messages or inferred usage/normal-close proof.
- No new CLI runtime flags/permissions, host action, SDK context/RPC, study/trial, capture opportunity, automatic retry, data/math or success-admission change. Product/Quant remain idle; no Product file dependency identified.
- Legacy two-key runner failures and old STOP payloads remain compatible; malformed new evidence fails closed. Released-runner context counts stay UNKNOWN even for INITIAL metadata.
- Original operations/native_packet.py, transport_profile.py, run_additional_once.py and return_frame.py are immutable. Preserve baseline sources/adapters in the new software leaf. Versioned successor adapters go under software/failure-evidence-20261104-01/operations and remain inert; no carrier submission/old claim revival.
- Complete software allocation32MiB/33554432, old complete24920424+8388608 new=33309032. New8MiB includes source/Git2MiB, tests/log/review1.5MiB, normalCI retention2MiB, necessarycatalog0.5MiB, failureFS2MiB. Central registration ced802fca5465f14b72a3dee51d505cf7780a6127e3f6227f31044b798fa4583; old holds/futures retained, total80MiB. No closeout/study borrowing or paid resource.
- No source-text byte limit. Keep the change bounded to this failure path. Required CI/human-policy merge gate is evaluated on the final concrete diff; never claim AI review is human review.

## Review focus

1. Stateful truthiness and exceptions must retain original order/object/arguments without evaluating a later predicate.
2. Both parent exception-wrapping points must preserve validated child evidence and primary versus cleanup meaning.
3. Production carrier reader and STOP selector must use the same tracked bounded codec, not an unused test-only helper.
4. Missing/malformed/private fields must not create facts or change counts/admission, including uncertain/nonzero paths.
5. Existing SPENT claims, old adapters and release catalogs must not be rewritten or executed by this software work.

## Task 1 — complete real failure-evidence path

**Tracked files (writer):** tools/research/ivv_trusted_runner.py; tests/test_ivv_runtime_failure_evidence.py; direct existing tests only when signatures/fixtures actually require adjustment.

**Versioned integration (writer):** new software leaf operations/native_packet.py and transport_profile.py, plus the minimal driver binding needed to select those actual successors. Reuse unchanged transport/owner libraries. Do not modify old operations. Preserve exact diffs/pins in the report. Default imports/preparation are inert; no native call or claim creation occurs in this task.

**Parent files:** this plan; docs/iterations/0038-ivv-origin-failure-evidence.md; a concise roadmap checkpoint. Parent handles commit/PR/CI/catalog.

**Interfaces:** _runtime gains an internal optional origin_phase=UNKNOWN; actual initial and session callbacks supply their literal stages. need may accept private optional origin context so FIRST_FALSE is marked only after its original not-ok test. Evidence extraction/attachment must never replace the original exception. Shared strict select_origin_failure(value), read_runner_failure(control,read_owned) and select_failure_status(status,publication_sha256) live in the existing runner; read_runner_failure consumes only the already-read failure file, and select_failure_status preserves existing transport selection/count rules. Equivalent private names are acceptable only if the writer records the exact mapping before review. The actual versioned adapters inject/load these exact published-source definitions and invoke them, with no new catalog role.

- [x] Write RED tests for each predicate false/exception in INITIAL/SESSION/UNKNOWN, explicit skipped lookups, stateful equality/truthiness and identical exception object/args. Add a case where a predicate itself raises Refused(RUNTIME_ORIGIN), distinct from an actual false need().
- [x] Write RED for actual error -> child packet -> parent supervision/aggregation -> main failure writer -> actual shared carrier reader -> actual STOP selector. Use fake kernel/SDK/transport seams; never execute the runner, SDK or private carrier.
- [x] Retain RED command/output under the software leaf; implement the minimal runner evidence/carry/codec path and versioned real adapter calls. Keep successful/legacy behavior unchanged.
- [x] Add malformed/private/absent evidence and uncertain/nonzero STOP tests, including INITIAL metadata still producing actual_contexts UNKNOWN. Check frame worst-status geometry with the optional evidence and existing output cap.
- [x] Run targeted new/direct affected pytest without cache/native effects, scoped Ruff/format and whitespace. Preserve failures. Update all actually changed source pins/fixtures rather than weakening checks.
- [x] Freeze tracked + versioned adapter diffs and report exact files/interfaces, RED/GREEN, hashes, physical/future accounting, untouched old adapter pins and known limits. Stop writing for fresh R1; no commit/native/publication by writer.

R1 reproduced three blockers. The sole consolidated correction retains finite
failure evidence on uncertain transport independently of success admission,
reads at most one authenticated queued failure after a nonzero pidfd-first exit,
and uses the built-in BaseException storage descriptor without subclass hooks.
Unsupported storage is safely declined. New RED6 source/RED5 actual-driver
failures are retained. Parent independently verified the complete two-file suite
181PASS and actual successor cases15PASS, broad Ruff, changed-file format and
whitespace. Same-reader R2 across the complete final diff is READY, all three
findings ADDRESSED and no new material blocker. No third structural repair or
review occurred. Its exact report pin is mirrored in the active iteration.

## Parent completion gates

- [x] Independently verify targeted tests/pins and complete budget; fresh scoped R1 across source and necessary private successor adapters, one located correction/same-reader R2 maximum.
- [ ] Run relevant broad static/affected checks and ordinary required CI once at final reviewed source boundary. Normal matching-head PR/merge only after actual merge-policy conditions; no administrator bypass/force push.
- [ ] Produce necessary source/catalog provenance from merged bytes only. Do not deploy, mint permits or build/submit a new capture opportunity.
- [ ] Record exact software delivery and remaining differences for any future authorized collection. Original failure cause, SDK/input/financial qualification remain unresolved.

Planner/Quant: this is an operability repair with zero new data/trial exposure. Tests/CI/merge do not establish SDK repair, normal capture or empirical research results.
