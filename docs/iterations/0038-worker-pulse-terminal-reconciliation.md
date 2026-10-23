# Worker pulse terminal reconciliation — issue198

Recovery parent: https://github.com/ZP151/quantmesh/issues/198
Base: `9348b2f664b4595dbdcf77523931880fb2dbe661`.

## Approved specification and Planner output

The operator authorized one bounded R source leaf through the coordinating root
on 2026-10-23. The diagnostic result and independent pulse review retained under
`output/0038-security-runtime-alignment/ops-preparation/R90-DIAG-{RESULT,PULSE-REVIEW}.md`
define this scope. The historical R90 result remains FAIL; normal exit is a
reachable race, not a proven historical cause or a promised 90-second recovery.

User action: run an already claimed owned Linux research attempt whose child
finishes between successful poll and pulse. Measurable outcome: a verified clean
terminal child continues once through the existing poll, two exit validations,
receipt validation, lease fence and publication, without a false containment
escalation. Pulse never publishes, claims, retries or renews a lease itself.

Only private fixed transport reasons may distinguish attach exit/closed pipe
from actual output overflow, writer timeout and uncertain reads. Reconciliation
requires fresh exact container ID, image, owner nonce, complete controls/config
and parent binding, stopped exit0/non-OOM, completely drained bounded streams,
and the original deadline and stop guards. All unknowns, running control loss,
identity/config/binding drift, inspect failure, overflow, writer timeout,
nonzero/OOM and uncertain drain remain fail-closed. Launch GO, watchdog,
controlled stop, daemon sibling stop, lease TTL/heartbeat and runtime pins stay
unchanged. Store cancellation and ownership retain the existing caller and
publication fences. No public error/schema/logging changes are authorized.

Expansion prohibitions: only `src/quantmesh/research/linux_owned.py`,
`tests/test_linux_owned.py`, `tests/test_worker_execution.py` and this new record.
No host/SSH/provider, new job, SDK/install, source monkeypatch, push/CI/merge or
changes to runner/store/bootstrap/daemon/service settings. Parent owns L and
independent review, capped at two rounds; structural scope failure returns STOP.

## Quant Researcher output

This is lifecycle correctness for existing synthetic operational recovery.
No new dataset, strategy, cost model, research metric or confidence claim;
no leakage assumption changes or promotion of research/trading authority.
Existing immutable numerical receipts remain necessary but insufficient without
exit, runtime, ownership and publication fencing. Reuse existing lifecycle,
transport and fake Engine interfaces; no upstream source or dependency added.

## Executable plan

- [x] Add deterministic runner RED: real poll/send/pulse, fake external Engine,
  current-record hook exits exact child after a running poll. Run existing WSL
  Python with `-m pytest -q tests/test_worker_execution.py -k normal_exit_during`;
  retain raw failure and SHA under `output/0038-pulse-terminal-reconciliation/`.
- [x] Add fixed private reasons and bounded complete-drain proof in transport;
  narrowly reconcile only pulse attach-exit/pipe-close ambiguity, fresh full
  inspection, strict terminal state, original deadline/stop checks. Re-run RED
  command for GREEN; do not change caller publication semantics.
- [x] Add deterministic pipe-close/late-overflow/read/drain/timeout and
  exact-owned mismatch/running/nonzero/OOM controls. Retain cancellation,
  receipt/runtime/lease/deadline/GO and daemon failure checks.
- [x] Run affected compatibility suite, full `python -m pytest -q`, full
  `ruff check src tests tools`, changed Python format, `git diff --check` and
  `git submodule status` using existing runtimes. Record origins, failures,
  warnings, exact raw SHA and byte pins; commit the locally reviewed candidate
  with any nonpassing broad gate explicit.
- [x] Parent independently reviews complete pinned diff and raw evidence.
  Local commit is reviewable only; no READY, merge or deployment acceptance
  before review/release-owner gates. Native R90 witness remains separate.

## Implementer and Verifier checkpoint

Implementation after R1 is frozen for final independent review at source SHA256
`1da629fe0776504f53f8aa90f73ea3116151c2e026e60021d85e5457068ae0bb`,
owned tests `5e0a47f322057f324a6ece00ac270554a563962512ae6c57b75133c0730b3a19`
and runner tests `85b89256cd52a843c121bd080bb5dacbda28b38b6e9555bf9066295a59e62129`.
There are no other production changes.

The first production-path RED failed at `_Transport.send("pulse")` with
`control_lost` after running poll and the current-record hook's clean exit.
Its GREEN performed ordinary poll, both exit validations, receipt validation,
heartbeat-before-publication, publication, finish and cleanup exactly once.
Further observed RED/GREEN stages cover read refusal versus explicit EOF,
absent parent binding, original-deadline expiry during incomplete drain, and
missing/unusable original-deadline context. The latter rejects None, infinity,
NaN, string and bool. Fixed private reasons preserve the public `control_lost`
string; overflow and writer timeout cannot enter the reconciliation branch.

The owned-process matrix covers exited attachment, pipe closing between send's
precheck and write, successful pulse immediately followed by exit, running OCI
control loss, nonzero/OOM, missing state/container, changed ID/image/nonce/full
controls, inspection refusal, stdout/stderr/queue overflow, late overflow,
failed/incomplete reads, nonzero attachment, attach wait timeout, missing/changed
binding, deadline and stop before/during inspection, unknown generic errors and
GO refusal. Identity mismatch refuses sibling cleanup; changed controls/binding
still allow exact-owned cleanup through the existing ownership-only check.

Six runner controls enter reconciliation with valid receipts before injecting
cancellation, receipt/runtime/binding corruption, lease reclaim or exact original
deadline expiry. None may publish. Pulse does not claim atomic database
cancellation knowledge: the current-record, heartbeat and final store fences
retain that authority. No lease operation or publication occurs inside pulse.

Verifier: focused final lifecycle matrix passed37/76deselected with the existing
NumPy warning. Corrected affected compatibility run passed228, skipped21 and
failed the unchanged `test_runtime_digest_binds_python_build` because Linux Git
cannot parse this Windows linked-worktree `.git` absolute path. Direct read-only
`git rev-parse HEAD` reproduced exit128. Command-local explicitly verified POSIX
Git paths recover the same base HEAD for that single unchanged test; no global
Git redirection, `.git` rewrite, source copy or environment installation is used.
That isolated unchanged test passed1 with the existing warning in7.84seconds;
its command and preflight are retained in `git-runtime-compatible.json`.
Full required pytest is running with cleared Git redirection variables and its
actual result will remain separate. Full Ruff, all three changed Python files'
format, whitespace and unchanged/uninitialized submodule pins pass.

Exploratory failures are preserved: the first combined run had26 new-helper
NameErrors and8 subprocess import failures without explicit PYTHONPATH. The
helper was corrected and the existing runtime now receives this checkout's
`src:tests:.`; receipts verify actual module path and byte SHA. A later run had
one test-authoring error: a301-second injection was below the default900-second
budget. The test now injects the exact request budget. An early full run was
stopped with SIGTERM/exit15 before source edits and is explicitly incomplete.
Raw evidence and JSON command/origin/hash receipts are under
`output/0038-pulse-terminal-reconciliation/`; none overwrite historical outputs.

Reviewer R1: independent frozen-diff review returned NOT_READY for one P2
external error-contract issue: reconciliation inspection failures could expose
engine/identity/binding codes instead of pulse's existing `control_lost`.
Actual Engine inspection refusal, wrong nonce and missing binding were changed
to assert exact `^control_lost$`; all3 failed as intended before the correction.
The inspection handler now translates only `LinuxContainmentError`, alongside
the existing malformed-state handling, back to the original delivery error.
Deadline exceptions remain separate; no catch-all exception suppression exists.
The focused matrix passed37 afterward. R1 raw RED SHA256:
`d43872f0fb8b2a1ca5ccb9716431fa426679017168975d72f9eb8d35d75cb83a`;
GREEN `8513c4135e37b43d401fba1aba3efce97d0a484caf9efb7e41721bbb5e246d18`.
The independent report and its full reviewed pins remain in
`independent-review-r1.{md,json}`. Only R2 remains; a further structural finding
returns STOP for scope reduction.

Verifier after R1: final formatted-byte source/owned/runner/deadline suite passed
152 with one existing warning in56.59seconds, raw SHA256
`47d3d1a54df63fa3947f6acce25071b104083a479b69b0cbb8fd0ded6a005a3c`.
The preceding affected run on the same production source reported227pass,
21skip and2fail: the existing WSL Git failure and an unexpected
`dataset_rejected` from unchanged launch-deadline binding case. The latter
passed in the final152 suite and as one isolated case; its cause remains
unproven and the earlier failure is retained rather than erased or repaired
outside scope. Static final gates pass. A formatting-only with-statement change
required stopping the just-started full run; that exit15 is preserved separately.
The `full-final-formatted` suite uses final formatted bytes with its original
cleared-Git environment. It was interrupted under the parent's time limit;
the broad gate is **NOT_PASS/INCOMPLETE**, not an all-green verification.

Final-byte compatibility suite passed76, skipped21 conditional cases and
deselected only the separately tested Git-dependent case, in19.68seconds with
the existing warning. It covers controlled stop, daemon failure/sibling cleanup,
failure observations and the rest of the runner file. Raw SHA256:
`e814833b5e43fe078ba780505c5cb68db803b69512092048e7bd182fdf8b1627`.
The isolated Git-dependent case also passed on the final production bytes with
the explicitly verified command-local paths in7.66seconds. The default full
command remains unmodified and has no global Git overrides.

Reviewer R2: final independent review is READY for the exact frozen code, with
zero remaining actionable findings. It verifies that the only R1-to-R2 source
change is the inspection exception tuple and the only owned-test behavior change
is exact external-code matching. Runner tests are unchanged. Both rounds and
their source/evidence pins are retained in `independent-review-r{1,2}.{md,json}`.
There is no third review round. This code-only verdict does not assert broad
verification, CI, human approval, merge, deployment, native Engine or historical
R90 acceptance.

Planner final verification limit: the coordinating parent bounded this exact
`full-final-formatted` run to18:21:55Z (900seconds nominal from its launch).
If still running, stop only that exact pytest process, preserve partial output
and exit15 with a separate time-limit receipt, and mark the broad gate explicitly
NOT_PASS/INCOMPLETE. Do not rerun a frozen whole suite or repair unrelated tests.
The reviewed source may be handed off as a local candidate with the sole
publisher's full CI gate still open; it is not an all-checks-passing release.

Final full result: actual run18:06:56.850345Z–18:22:03.489126Z, exit15 after
identity-bound SIGTERM. The stop target was18:21:55Z; actual signal was
18:22:03.431904Z,8.432seconds later from tool/scheduling overhead. PID23353,
the exact Python/pytest command and process start tick151762 were captured and
revalidated before the signal. Partial output reached reported10% and contains
no final test-count or failure summary; no completed-suite pass is inferred.
Raw640-byte log SHA256:
`ea024e4f1e5e584d56c5a7a2d1081bd7fca08a41fee3b2823ec90d51dfd6f74c`.
`full-final-formatted.json` and `full-time-limit.json` retain exact command,
origin/pins, dates, process identity and cap disposition. No further full run.

Handoff disposition: the source candidate has R2 code review and targeted
evidence, with the broad local gate explicitly incomplete and required publisher
CI/human/release gates still open. Only the four authorized tracked files enter
the local commit. Post-commit origin/byte-pin/clean-state checks and the complete
ignored evidence manifest bind the final commit and tree without rerunning the
unchanged tests. No push, GitHub/CI/merge, deployment, host/provider action or new
production job occurred. Historical R90 remains FAIL, with neither its original
cause proven nor its90-second target newly certified.

### Raw TDD evidence identities

The original runner RED uses unchanged base production source SHA256
`40f2ca8bb37a78b9c83358eb75f533a4f1597d4cce65d9ff3d582f938f750a2c`.
`runner-red.txt` SHA256 is
`16dfab472e1d9517b06f66a4e57a33f85045bbd94d97c0756aaf3bc6ce6419ef`;
it records1failed/21deselected/oneexistingwarning in7.99seconds.
`runner-green.txt` SHA256 is
`dadeb9dd507fd74d162d7f40eb8e91e8aa161af0e08e555cd68ac04c81aedafc`;
it records1passed/21deselected/oneexistingwarning in5.54seconds.
These initial raw tracebacks name this checkout's real production files. Later
staged receipts additionally pin actual imported module path/source SHA and all
three runtime/test file bytes at command start. Their paired phases are
`drain-{red,green}`, `binding-{red,green}`, `deadline-{red,green}` and
`original-context-{red,green}`. Failures and their raw logs remain available;
no old RED was overwritten by GREEN or a corrected harness run.
