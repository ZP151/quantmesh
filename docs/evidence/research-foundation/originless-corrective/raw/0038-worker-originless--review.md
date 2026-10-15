# Narrow originless-helper review

Two actionable P2 findings in the reviewed adapter; no native implementation or broader architecture review performed.

1. [P2] Reject non-exact-string raw dictionary keys before shape comparisons or lookups (worker_build.py:197-199 and 215-216). Exact ModuleType does not constrain its __dict__ keys: vars(module) can contain a str subclass with a hostile __eq__ and str.__hash__. Replacing a metadata key while the hook is unarmed, then arming it before admission, permits a hook invocation during set comparison/string-key lookup instead of hook-free refusal. An arbitrary RuntimeError from that equality hook also escapes the current sanitized exception tuple. Exact-dict-to-set conversion reuses cached hashes in CPython, so this finding specifically concerns equality/comparison, not a guaranteed repeated __hash__ call. Check every raw key's exact type before set construction, equality or string-key lookup in the runtime and typing namespaces. Add a regression asserting refusal without invoking the equality hook. [CPython set implementation](https://raw.githubusercontent.com/python/cpython/v3.12.15/Objects/setobject.c)

2. [P2] Sanitize the new compilation boundary (worker_build.py:245-248; outer exception tuple at 453). compile(measured_source, measured_path, 'exec') can raise SyntaxError, including the source path and source text. The outer gate catches ValueError/TypeError/etc. but not SyntaxError. A malformed measured typing source therefore exits with a raw compiler exception rather than WorkerBuildRejected. Convert SyntaxError to ValueError at the compile boundary or include it in the gate's sanitized rejection tuple. Add a malformed measured-source case that checks the outer gate's exact sanitized message and suppressed cause.

Positive observations within this scope: the adapter hashes actual typing source, compiles without executing it, compares defining metaclass method code and globals/closure identities, restricts alias members/shape, and rejects overridden runtime metadata or non-boolean payloads. The native Cython cache names receive no exemption and continue to fail the ordinary origin check. The full Cython/native admission gap remains explicitly pending; accepting these non-native helper shapes does not prove numerical/image admission.

Recorded evidence inspected without reruns: red.log/red.exit records 23 failures because the adapter is absent (exit 1); intermediate-name-mismatch.log/.exit records 2 failures and 21 passes (exit 1); green.log/.exit records 62 passes, 4 warnings, 6.27 seconds (exit 0), combining the helper tests and original worker-build tests including the separately reviewed CI fixture correction. Root states exact-string value guards and formatting were added after that GREEN run; the recorded result therefore does not cover every byte of the current diff. The two findings are based on current source inspection, not claimed reproductions or native execution.

Exact reviewed SHA-256 at inspection:

- src/quantmesh/research/worker_build.py: c56388d4c6d367b18168b7518b58254459156f33d0bd309d00ab06b5af3c3f6b
- tests/test_worker_originless.py: 47f7a9244745a666a21665f015ffaca7b8da6a1be8e7050a309220a7285ef9f1
- tests/test_worker_build.py: c75a0c19b62cb70714830579b359a0a79c687a0755747c57e3e73a016ce3cfa4

No source edits, test reruns, new interpreter/native inspection or runtime certification performed by this reviewer.

## Two-finding closeout

Both reported P2 findings are resolved in the exact current correction. No actionable P1/P2 remains in this two-finding closeout. The cython_runtime raw dictionary and measured typing namespace now reject any key whose exact type is not str before set construction, comparisons, or named lookups. Those guards inspect key types without invoking key equality/hash hooks. The new compile boundary catches SyntaxError and raises an empty ValueError from None; the existing outer gate converts ValueError into its fixed WorkerBuildRejected message with suppressed exception context.

Recorded corrective evidence inspected without reruns: review_red_plugin.py removes only those two guards and the compiler catch in a controlled previous-adapter overlay. review-red.log/.exit records both armed equality hooks and the compiler exception failing their new regressions (3 failed, 23 deselected, 1.98s, exit 1). review-green.log/.exit records the current helper plus worker-build tests passing (65 passed, 4 warnings, 6.99s, exit 0). The new malformed-source regression directly checks the helper's empty ValueError; the outer sanitized conversion is confirmed by the unchanged ValueError catch, not a claimed new outer-path execution.

Exact closeout SHA-256:

- src/quantmesh/research/worker_build.py: 329dc3b0e6512e12f2bbe246c1df5051544c9c3daa0115b5acea291790d8bbfb
- tests/test_worker_originless.py: 04493de9c5411d540a70a8239f87345f26852d1aa665b7f0b5b2e3fd0c63b9ca
- tests/test_worker_build.py: c75a0c19b62cb70714830579b359a0a79c687a0755747c57e3e73a016ce3cfa4

Native Cython caches remain unexempted and rejected downstream. Full numerical/image admission and native qualification remain pending. No source edits, test/native execution, or whole structural review performed in this closeout.
