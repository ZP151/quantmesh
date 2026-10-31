# Iteration0038 — same-unit OpenD recovery

Issue [261](https://github.com/ZP151/quantmesh/issues/261), directly blocking259. [Spec](../superpowers/specs/2026-10-31-opend-same-unit-recovery.md), [plan](../superpowers/plans/2026-10-31-opend-same-unit-recovery.md).

Planner: Root23cca13f selected the explicit one-recovery branch under the existing actual operator repair/start/login/software/agent-review/normal-merge authorization. The initial900s permit and spent nonce correctly deny reuse. Same original unit/nonce and all old permit/claim/failure bytes remain. One action is same-unit recovery; success is exactly one gated release, zero on every rejection. Not a new human design answer or two-person review fact.

Quant: no dataset/strategy/math/fees/SDK/captureintent/trial work. Initial/parent/provider qualification flags stay false. Vendor32MiB and readonly source/runtime/native/encryption gates remain later actual requirements; financialINSUFFICIENT/livefalse.

Implementer: sparse isolated branch codex/0038-opend-same-unit-recovery from actual merged6cc3c113. Original W dirty ADR/iteration/untracked plans untouched. New purpose output/opend-same-unit-recovery-software-20261031-0031 has independent32MiB fullhold; all previous serverlocal24MiB/metadata1MiB and other holds remain. No env/dependency/service changes or host action. G10028851290/P4219368462; local Cfree>50GiB. Forecaster includes source/Git/retained test fixtures/review/publication, not just log bytes.

Reviewer: one fresh independent spec+quality review pending; maximum R1/known-fixR2. No third structural round or old helper review reuse.

Verifier: original actual prestart denied permit_denied; old permit expired/nonmatching and original claim present; service start0/credentialreadhash0/SDK0/captureonce0. Canonical launcher789b equals actual merged6cc source, without a recovery mode. New synthetic RED/GREEN and baseline affected checks pending. First increment target10:30:59SGT/reviewable12:30:59SGT are new software-phase estimates; old attained deadlines and sealed STOPs remain history.

## Coherent software checkpoint — 2026-10-31 Singapore

Implementer: fixed persistent selectors/reload now use a pinned closed-schema
recovery module. Root0444 authority binds the same unit/nonce, exact old claim,
observed public prior permit, source/vendor/host/service pins and <=300s window.
Check/prepare/create-pane repeat without consumption. Final release holds and
rechecks authority FDs/live names, creates one private atomic consumption record
and never refunds it. Original initial loader/claim and persistent lifecycle stay.

Planner ruling: RED05 showed that consumption inside admission preceded the
existing final PID check. One optional recovery-only before_gate hook now commits
after that check; initial callers omit it. RED06 reproduced a possible FIFO wait
before claim type validation; claim opens now include nonblocking/no-follow.
Neither changes the existing spawn/signal/backend ownership implementation.

Verifier: genuine missing-route RED01, duplicate_nonce RED03, late-claim-change
RED05 and nonblocking-open RED06 are retained. GREEN11:167 passed/70 platform
skips across the new test and existing staging/persistent/terminal/profile files;
Ruff/format/whitespace pass. Controls cover repeated checks, atomic concurrent
consumers, same-byte object replacement, source/machine drift, expiry after
checks/fsync, short/zero/failed writes, file/directory fsync failure, gate/ack
failure and owned-FD/child cleanup. Failed consumed attempts stay spent.

Baseline01's two missing-template errors and several early lifecycle-double
errors were test setup failures, not successful REDs. A concurrent synthetic
failure was traced to Windows stat/fstat ctime views; the adapter now explicitly
models POSIX ctime consistently on Windows, retaining native timestamps on
Linux. Ownership/dirfd/native terminal are modeled locally; native-only70 skips
are not passes. No SDK, credentials, real service or recovery control was touched.
Fresh independent spec+quality review and exact-head publication remain pending.

## Independent R1 and bounded known fixes

Reviewer: fresh R1 checked80015c68/treea9ca85eb and required two changes: source
identity could change during marker fsync after admission, and held STATE dirfd
checks did not reopen its current fixed path/privacy. Report is retained under
the new purpose/review/R1.md; this is agent review, not a human approval fact.

Implementer/Verifier: RED-R1-SOURCE4 reproduced machine/launcher/vendor/tmux
drift releasing incorrectly; RED-R1-DIRECTORY5 reproduced live directory
replacement/owner/group/mode/nlink drift. The recovery-only hook now repeats
admission after persistence, then rechecks the lease and clocks. Lease checks
reopen fixed STATE, compare stable held/live directory identity/private metadata,
and compare claim/marker through the current directory. Directory size/time are
excluded because consumption legitimately changes them. GREEN12:177 passed,
70 platform skips, including late authority change during post-persistence
admission; owned cleanup and spent failure semantics remain intact. One known-fix
R2 and exact-head CI/normal publication remain; no third structural round.
