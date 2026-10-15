# Measured interpreter alias integration

> For agentic workers: execute inline with TDD and one bounded independent review under the approved Option A fixed-entry/parent integration design.

**Goal:** Let the canonical `/usr/local/bin/python3` entry use its declared, measured `python3.12` target without bypassing inventory verification.

**Architecture:** Keep the unchanged five-field runtime and inventory schema. Resolve only the actual interpreter leaf when inventory explicitly declares that exact link. Require its target inside the measured prefix and regular file map; retain all module, namespace, distribution, source and lock refusals. Recheck the link target and executable bytes before returning the runtime fingerprint. No native-cache exception, image certificate or default Linux activation.

**Tech stack:** Existing pathlib/os/hashlib and pytest. No dependency/environment/image installation.

Issue #172 / PR #175 follow-up on `codex/0038-worker-kernel` (parent candidate f5e38ea unchanged). The actual frozen image inventory records `/usr/local/bin/python3 -> python3.12`; measured ELF aliases match. Current `_inventory` correctly validates links but returns only regular file pins, so `measure_worker_runtime` rejects that alias as absent. Fixed entry requires the alias; changing its argv to manufacture a pass is forbidden.

Planner/Quant ruling: use the existing baseline engine, fee/spread/slippage and report contracts. No algorithm or dataset changes. This is a prerequisite for the same complete Worker/report user loop, not a substitute for actual image/kernel/parent admission. Preserve original baselines/all failures/whole-C attribution pending. New software phase4MB, cumulative ceiling55MB from previous51MB allocation (last measured46,194,343B); fresh workspace-owned WSL test roots and >=50GB free, no old-temp deletion or local full-suite repeat. AWS original5GB/free50GB limits remain.

## One bounded tested slice

- [x] Add Linux tests in `tests/test_worker_build.py`: declared interpreter symlink passes with target digest; undeclared, changed, prefix-escaping and unmeasured targets refuse; a link change between inventory and fingerprint publication refuses. Existing ordinary-file path remains covered.
- [x] RED: existing WSL Python, focused alias tests, `-B -m pytest ... -q --tb=short -p no:cacheprovider --basetemp=<fresh owned WSL directory>`; preserve legitimate alias failure.
- [x] Update only `src/quantmesh/research/worker_build.py` interpreter measurement. No global symlink allowance or changes to source, module or native helper admission.
- [x] GREEN: whole worker-build test module plus parent-binding tests, then Ruff/format/diff. Preserve actual no-profile-load kernel-field intake: first64-profile bound refused, named-only1024-bound intake discovers116 profiles and kernel raw_data/raw_sha256 support. No loaded-policy byte attestation is claimed yet.
- [x] One scoped review, one fix pass if needed, coherent commit/push on dependency branch; mirror result into CONTEXT/ACTIVE/iteration.
- [ ] Continue loaded-policy byte attestation, immutable entry/source materialization and independent parent, full baseline/report/two-job recovery. Do not re-run the already passing native kernel sub-witness.

Verified RED1fail/5pass, GREEN61pass/6.15s; bounded review clear. Actual compiled binary62,633B/SHA d5a828a5; no loaded-profile attestation yet. PR175 CI38584253826 failed4928pass/141skip/two SSE startup errors; separate diagnosis open. Resource receipt retains original baselines and all failures.
