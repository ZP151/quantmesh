# Early release contract and precise CI failure evidence

Issue [292](https://github.com/ZP151/quantmesh/issues/292), based on merged
77ea54471abe08fd9496fd3cac6c4dd9fda9c8c0. The user froze this independent CI
slice after the completed attempt8 engineering subtask. Parent owns review,
publication and all subsequent execution decisions.

One developer action runs `python tools/quality_gate.py contract` before push.
The same named command runs immediately after Python installation in the existing
fast job. Success gives explicit collection/source/environment evidence and an
early failure location. Target net validation is 2–5 minutes excluding install,
with actual platform/timing reported before any performance claim.

Reuse GateCommand and its unique external pytest basetemp. One deduplicated
selection includes the ten existing Init/authentication/lifecycle/recovery modules,
the whole portfolio qualification module, and a small static closure module.
Require all three helper bootstrap targets plus held-release authentication at
collection. Missing targets, collection errors, stale helper/issuer pins,
manifest roles, policy or public entry ABI must fail. Source comparisons use
actual Git blobs and owning source constants, without generating trusted pins.
Private Ops wiring23 and final carrier/status/header/frame geometry remain an
explicit local publication gate. Public CI cannot certify those private facts.

Full release pytest adds standard --maxfail=1 and retains its complete original
collection and subsequent successful release steps. Fixture teardown completes
normally on setup/call/teardown failures. Existing process timeout/descendant
cleanup and two-node CI_PROFILE/CI_PROFILE_EXPORT schemas remain covered.

Extend the existing pytest plugin with bounded JSONL evidence. Record collection
identity/count, sparse active node/phase and completed count, per-phase durations,
first failing exact node/phase and an ordinary pytest log reference. Keep assertion
text in the normal pytest log. Structured events never copy locals, arbitrary
exception text, environment/argv or provider payloads. Evidence includes Git
commit/tree plus current tracked-diff identity, Python/executable/pytest identity
and artifact identity. A diagnostic failure is visible and prevents false green.
Use one bounded event stream per pytest subprocess, avoiding nested-run collision.

No new job/protection, skipped test, quarantine, dependency/environment, parallel
matrix, SDK/provider/health request or modification of the seven reviewed runtime
roles. Failed evidence is retained. Passing scratch cleanup is limited to owned
ephemeral trees. P33 retains prior545MiB and adds local9MiB to all554MiB,
Source22/common121/software160MiB. Batch03/connection8 remains spent/UNKNOWN.

Acceptance uses causal RED/GREEN for gate selection, closure drift, fail-fast,
phase evidence, diagnostic failure and all-pass continuation. Then run the named
contract and one deduplicated affected union with the three gate test modules.
Required normal full CI follows independent review. Timing and dependency gaps
must be disclosed. No local repeat of the 8000-case release suite.
