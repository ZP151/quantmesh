# HANDOFF — private terminal prerequisite, issue169 / iteration0038

STOP: bounded deliverable complete; coordinator independently verifies,
integrates and archives. No further host/authentication action authorized.

## Exact candidate and ownership

Baseline `5788cf7057b7d9670982a16cc9bd3aaae01b83c2`. Reviewed/committed candidate `f99b020153a31d7d8a5265c9795edbd5a7884ddb`.
Branch `codex/0038-opend-private-terminal`, clean managed worktree:
`C:/Users/15492/.codex-clean/worktrees/2088/QuantMesh`.
Exactly three new tracked files, no shared profile/unit/validator/app/locks/
REUSE/ADR/ACTIVE/iteration edits. Local main preserved; no other worktree,
push, PR, merge, deployment or network operation.

- `tools/qualify_opend_private_terminal.py`: `c18a81701ce432cb93e1ac2243b31add34f3ec10944dc381b92ff8e1d0133b63`
- `tests/test_opend_private_terminal.py`: `e6705346494dd1cceefa69d9f266c489b48a7451a31dfd834f303e5d6d5f9269`
- `docs/runbooks/opend-private-terminal-qualification.md`: `0fd26c7c0fc48f296c703592598605def423994d05ccbeadda11eb115cd6f763`

`candidate.tar` is the exact Git archive of these files plus unchanged pytest
config. Final native snapshot `/var/tmp/quantmesh-terminal-check-k3mrwna5`, mode0700, Linux x86_64,
CPython3.12.3, UID1000. Native imported qualifier:
`/var/tmp/quantmesh-terminal-check-k3mrwna5/tools/qualify_opend_private_terminal.py`, SHA matches the commit above. The snapshot
is retained for coordinator inspection; each runtime fixture root was removed.
Existing bootstrap pytest9.1.1 was used read-only with plugin autoload disabled;
runtime helper/CLI use only CPython standard library. No dependency installation.

## Commands, observed exits and evidence

Native driver invocation:
`wsl.exe --exec /usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/python3.12 /mnt/c/Users/15492/.codex-clean/worktrees/2088/QuantMesh/output/169-private-terminal/native_checks.py final`
Observed outer exit0. Individual commands/exits below are recorded by the driver.

- `/var/tmp/quantmesh-bootstrap-krfg8kx6/venv/bin/python -B -m pytest tests/test_opend_private_terminal.py -q --basetemp /var/tmp/quantmesh-terminal-check-k3mrwna5/pytest-temp`: exit0, **38 passed / 0 skipped / 2.32s**.
- `/usr/bin/python3.12 -I -B tools/qualify_opend_private_terminal.py`:
  exit2, pending/PREFLIGHT_NO_EFFECT, no resources created.
- `/usr/bin/python3.12 -I -B tools/qualify_opend_private_terminal.py --owned-fixture`:
  exit0, genuine local fixture, elapsed2.174925s including cleanup.
- `/usr/bin/python3.12 -I -B /var/tmp/quantmesh-terminal-check-k3mrwna5/native_witness.py`:
  exit0, independent new fixture elapsed2.179974s.
- `python -m pytest tests/test_opend_private_terminal.py -q --basetemp output/169-private-terminal/windows-final-temp`:
  exit0, 4passed/34explicit Linux skips. Windows is not native certification.
- `ruff check tools/qualify_opend_private_terminal.py tests/test_opend_private_terminal.py`:
  exit0. `ruff format --check` on the same files: exit0.
- `git diff 5788cf7057b7d9670982a16cc9bd3aaae01b83c2..f99b020153a31d7d8a5265c9795edbd5a7884ddb --check`: exit0.

Raw whitelisted JSON: final-preflight.json, final-fixture.json,
final-independent-witness.json; tests/native import/hash/platform evidence:
final-native-tests.log/.exit and final-native-context.json; separate `.exit`
files contain observed subprocess statuses. driver/witness scripts are retained.

Independent witness checks actual kernel pidfd-to-child identity before release,
owned child stdio character-device/inode/UID/0600 metadata and parent termios,
and terminal pidfd readability after waits. It observes eight retained Popen
children reaped, including failed registration children, and independently checks
fresh runtime root removal. No terminal byte capture is added by this witness.

Input65bytes accepted; transient digest matches; marker not echoed; only4ACK
bytes observed. Real disconnect yields -SIGHUP, blocked/output growth -SIGKILL,
gate timeout and failed registration exit40 without release. The known sibling
survives all six individual cases, then its retained pidfd is cleaned up.
No marker, marker digest, terminal stream, transcript or credential is archived.

## RED/GREEN and review

Initial Windows collection RED(exit2) was missing-module evidence only. Native
stub RED:31fail/exit1 -> native GREEN31. Added permission-setup/access-direction
regressions RED4fail/32pass -> GREEN36. Actual SIGINT during Popen return and
second-pipe allocation RED2fail/36pass -> GREEN38. Files red-native-tests.log,
red-resource-access-native-tests.log and red-interruption-native-tests.log plus
their exits preserve failures. Final fresh native38 remains green on committed
bytes. The first ACK-count failure was real default OPOST CRLF; the synthetic
fixture disables OPOST, preserving the independent four-byte expectation.

Independent Spec and Standards ROUND1 review of exactf99b020153a31d7d8a5265c9795edbd5a7884ddb: zero actionable
findings, no second/third round. Reports spec-round1.md, standards-round1.md.
Reviewers inspected native evidence but did not rerun it; the separate final
independent native witness follows review. Completed source/profile/service
architecture was not re-reviewed. No rulings or deferred minor findings.

Planner: private-input/lifecycle prerequisite only, one explicit local action,
one native proof within90s, expansion prohibitions intact. Quant researcher:
no strategy/data/market/model efficacy claim. Implementer: inherited FD admission,
gated fixed children and retained kernel ownership. Reviewer: both axes clean.
Verifier: fresh native/Windows/Ruff/format/diff and independent kernel evidence
above. Root mirrors accepted roles/checkpoint into shared ACTIVE/iteration.

## Limits and next owner

Scope is only OWNED_LOCAL_PRIVATE_TERMINAL_FIXTURE. Every production release,
source-host private input, authentication.private_input_verified, SDK wire,
server startup, operator authentication, installation and market flag remains
false. No original vendor process/state/log/env/cmdline or real credential was
read, and no network/AWS/SSH/vendor/SDK/login/helper/tunnel/daemon/global-package/
user/policy action was taken. No genuine source-host/human login/market acceptance.

Admission is a point-in-time metadata check, not same-UID/root secrecy. A hostile
external termios mutation, indefinitely hung kernel, global OS/journal policy,
arbitrary descendants or real credential transport is not certified. Work stops
at80s, cleanup shares89s, total90s; incomplete cleanup cannot pass. Named native
faults and normal cleanup were operated; deadline-exhaustion branches were
reviewed statically, not a kernel/scheduler fault simulation. Hour-scale core
tests were explicitly excluded; only this new slice was certified.

Coordinator now independently checks exactcommit/hash/import/kernel receipts,
integrates/archives and updates shared ledger. Actual source-host private-input
proof and the reviewed one-shot staging authority/expiry, ClassC CI/two-human
safety review, explicit operator authentication window, original acknowledged
SDK transport and market/provider/browser/rollback gates remain pending.
Do not request credentials or advance authentication from this handoff.
