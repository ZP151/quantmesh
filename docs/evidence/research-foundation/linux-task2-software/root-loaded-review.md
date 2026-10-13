# Bounded loaded-origin corrective review

One actionable P2 remains: ordinary interpreter entry modules are rejected.

[P2] worker_build.py:264-290 applies the new non-QuantMesh dependency gate to sys.modules['__main__']. With a python -c entry, __main__ has no __file__, no package __path__, and __spec__ is None; lines 289-290 therefore reject even when every dependency origin is admitted. A stdin entry carrying the pseudo filename <stdin> likewise fails the absolute-path check. With python -m quantmesh.<entry>, __main__.__file__ points into the separately measured source_root; lines 273-274 require prefix membership and reject that measured source as well. This blocks normal admission callers rather than detecting a dependency shadow. Classify the entry module explicitly: permit source-file entry origins only when bound to admitted_source, and handle originless entry modules according to the intended supported invocation contract. Add a regression that retains __main__ in sys.modules. The six added cases replace sys.modules with a small fixture mapping that omits __main__, so the passing result cannot detect this production import regression.

The residual round2 shadow finding itself is addressed for the reviewed shapes: file and spec origins must be exact measured files under prefix; package and namespace paths must be real directories under prefix with link ancestry rejected by _path. Legitimate distribution metadata alone no longer admits the five external Python/extension/namespace/package/spec fixtures. Built-in/frozen spec markers and None module entries are handled explicitly.

Evidence read only: review-round2.md; root-loaded-red.log/.exit (5 failed, 30 passed, 1 warning, 2.41s, exit 1); root-loaded-green.log/.exit (35 passed, 1 warning, 2.16s, exit 0); corresponding observation JSONs. Observations identify a targeted source overlay and synthetic runtime fixtures on a borrowed read-only Linux environment, not a production admission run. No tests rerun, source edits, architecture/spec/standards review, environment mutations, or image/native/Task2 certification performed.

Exact reviewed SHA-256:

- src/quantmesh/research/worker_build.py: 605d5ab2c0fee97d1dfa1c10dd527c214592304645472402ff950caf0fd2390d
- tests/test_worker_build.py: e13e8c62551b7246a955b73904eb08b1bdce1bcfce7db3903a2253fd80266c89


## Final disposition after the entry correction

The concrete P2 measured-source entry regression is resolved. No actionable P1/P2 in this narrowly scoped correction. worker_build.py:270-275 now permits only the __main__ alias whose exact file origin is already in admitted_source, with spec origin absent or equal to that file and no effective package search path. admitted_source is constructed only after actual source inventory hashes and the declared complete Python-source set have been checked. The exception therefore does not admit an external dependency or an unmeasured source file. All other module names retain the loaded-prefix gate.

The earlier -c/stdin compatibility concern is closed by the explicit Planner contract supplied for this follow-up: image admission supports a trusted baked Python -B -I file entry and does not support arbitrary inline/stdin callers. Their rejection is intentional within that contract; this review does not alter or assess the separate default host/Windows branch.

Read-only evidence: root-loaded-entry-red.log/.exit reproduces the measured __main__ alias failure (1 failed, 36 passed, 1 warning, 2.34s, exit 1); root-loaded-entry-green.log/.exit records 37 passed, 1 warning, 1.92s, exit 0. New tests retain a measured source-origin __main__ alias (pass) and an originless inline __main__ (refuse). The matching origin is covered directly; the None spec-origin file-entry alternative is confirmed by inspection of the same explicit branch. Corresponding observation JSONs still describe synthetic targeted-overlay tests, not production image admission. No tests rerun, source changes, broader review, or image/native/Task2 certification performed.

Exact final reviewed SHA-256:

- src/quantmesh/research/worker_build.py: 0471bb4f0353fa3efe57004a9f303aea8825a8bd1934b8a8c48b4205ed5e672a
- tests/test_worker_build.py: 8e2b38fa123cfe9bd5bf14721e350ad82db9bc60da9357df04713bf21f300e3f

## Final disposition for measured base-stdlib correction

No actionable P1/P2 in the exact corrected loaded-origin closure change. This disposition supersedes the earlier same-prefix wording. Loaded non-QuantMesh file and spec origins now require exact membership in the verified inventory files (worker_build.py:278-284). Package/namespace paths must be existing non-symlink directories inside an admitted inventory root, with parent-link checks enforced by _path (lines 285-296). Verified roots are defined at line 234. This accepts an inventoried base stdlib outside a virtual environment's sys.prefix while continuing to reject the unmeasured external shadow fixtures. Distribution metadata/RECORD origins still require both virtual-environment-prefix membership and measured files (lines 310-320). The measured-source __main__ correction and intentional rejection of unsupported inline entries remain intact.

Recorded evidence inspected without rerunning tests: root-loaded-stdlib-red.log/.exit records the new legitimate measured-stdlib regression (1 failed, 37 passed, 1 warning, 2.35s, exit 1). The first root-loaded-stdlib-green.log/.exit remains a failed intermediate implementation (undefined roots; 4 failed, 34 passed, exit 1), not passing evidence. root-loaded-stdlib-green2.log/.exit records the corrected implementation (38 passed, 1 warning, 1.77s, exit 0). Its observation JSON retains the targeted-overlay, synthetic-fixture and borrowed-read-only-environment limitations. This is a specific corrective source review, not image/native/Task2 certification or a broader architecture review.

Exact final reviewed SHA-256 after the stdlib correction:

- src/quantmesh/research/worker_build.py: 9938d81fc9dd1ab618862a77c2e79a6ec1196bb9020a9d04c10893083c3d0984
- tests/test_worker_build.py: 59ad54c74c4da5bdad012f701b883a496258da0c80fed357df5411ae54cc7998
