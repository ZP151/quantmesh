# Same-unit OpenD recovery implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Implement inline; one fresh independent whole-slice reviewer, at most two rounds.

**Goal:** Admit one explicit recovery of an existing persistent unit while retaining its spent initial nonce and refusing every unproved release.

**Architecture:** A pinned domain-only same_unit_recovery module holds closed-schema authority/FD identity and atomic consumption; stage_console selects it through existing fixed commands and invokes its lease at the existing final gated-child callback. Initial and backend behavior are retained.

**Tech Stack:** Existing Python stdlib/pytest, existing Git/CI, no install or new environment.

**Spec:** ../specs/2026-10-31-opend-same-unit-recovery.md

## Global Constraints

- Existing original unit/nonce/StateDirectory/vendor/backend/terminal and persistent1GiB/swap0/CPU50/tasks128 remain. Capture512MiB/swap0/CPU50/tasks32/480s and provider32MiB evidence are separate, unchanged gates.
- New control generation/startup/SDK/data/capture intent/trial are prohibited in software tests.
- Root-owned recovery file0444/nlink1, exact source/vendor/machine/UID and old object stamps; short control window<=300s, launch max_seconds180.
- All old permits/claims/failures remain. No scope/default/path/permission/quota platform extension, credentials in logs/fixtures or direct systemctl bypass.
- New independent32MiB fullhold covers all source/Git/docs/RED-GREEN/review/CI/publication. All old holds retained. Purpose forecast is output/opend-same-unit-recovery-software-20261031-0031/FORECAST.json. Shared source object store; sparse checkout only, no full49MB copy. Disable automatic Git GC per command.
- Base6cc3c113cd791024806e4fc7ad80401156d1dd42; branch codex/0038-opend-same-unit-recovery. Preserve dirty original W.

## Review Focus

- A check succeeds, then authority/claim/path/source changes before release: refuse and close only the attempted gated child.
- Concurrent checks both succeed: only O_EXCL winner may release; duplicate control never resets either initial or recovery marker.
- Failure after consuming but before gate acknowledgement: keep recovery spent and retain primary/cleanup facts.
- A recovery control exists for another unit or is malformed: fail closed rather than fallback; nonpersistent initial routes stay unchanged.
- Long-lived vendor after short admission expires: preserve existing persistent lifecycle, without credential reads in admission or any new market qualification.

## Task1: selector and closed authority (one reviewable vertical slice)

Files: create deploy/aws/opend/same_unit_recovery.py; modify deploy/aws/opend/stage_console.py; create tests/test_opend_same_unit_recovery.py; tracked spec/plan/iteration and short ADR0032/roadmap update only.

Interfaces: module load(ops, nonce) -> Control; Control.validate(now, identity, hashes), Control.check_available(), Control.release_lease() -> context manager yielding lease.check()/lease.consume(). ops is the already-fixed stage module (protected FD/directory helpers and constants), never user paths. Stage RecoveryWindow exposes claims/nonce/expires/persistent and its Control; select_console_window(nonce, persistent) uses recovery only for a present fixed file, otherwise legacy loader. reload_console_window(window) keeps branch identity.

- [x] Test CLI check-window with expired/mismatched legacy permit, existing initial claim and valid synthetic recovery file: original code returns denied; expect admitted, old bytes unchanged, no recovery marker or vendor/credential release. Run exact test RED with retained log under purpose/vectors/red01.
- [x] Implement strict closed schema, root file snapshots, prior public-permit identity/hash and old-claim binding, fixed selector and reload; no native effects. Keep the existing generic stdout qualification flags false.
- [x] Test repeated fixed check/prepare/pane selection, no recovery marker; malformed/foreign/missing/expiry/source/vendor/machine/mode/owner/nlink/claim drift controls deny. Retain focused GREEN.
- [x] Commit coherent authority/routing checkpoint with iteration role evidence.

## Task2: final release and irreversible recovery consumption

Interfaces: existing start_staging_console(window) retains the gated child/backend. Legacy initial _claim remains at its old point. Recovery holds an authority lease around child.release; an optional recovery-only before_gate callback runs after existing admission, child PID/handle and clock checks, consumes the marker and rechecks FD/path identity and expiry immediately before the existing gate write. Default None preserves the initial release path. Recovery marker filename is originalnonce.recovery; payload is safe control identity only, <=1024B.

- [x] RED lifecycle: one same-unit release with preserved initial marker, repeat refusal with release spy0, checks do not consume; existing source cannot recover. Add two concurrent contenders with barrier before real O_EXCL and assert one release only.
- [x] Implement held-FD/control/source/claim rechecks and create-only complete-write/fsync marker; never remove or refund it. No change to gated child/backend/vendor/credential machinery.
- [x] RED then GREEN mutation between successful check and start; mutation during spawn/final validation/consumption; expiry after expensive check; failure after consuming, before ack and during cleanup. Assert vendor and credential-value spies0 on denial and own-child closure only.
- [x] Run new controls plus existing staging/persistent/private-terminal/profile tests once at green boundary; record actual counts/skips, Ruff/format/diff checks and exact pins; commit.

## Task3: independent review and normal publication

- [ ] One fresh reviewer checks spec+quality on exact code/tree/plan and new test evidence; R1 plus one known-fix R2 only. If third structural failure, return a concrete reduced-scope alternative; no patch loop.
- [ ] Necessary known-fix RED/GREEN and affected gates only. Preserve failed logs and all prior consumed markers/control bytes. Update short iteration with Planner/Quant/Implementer/Reviewer/Verifier results; verify final source/module SHA.
- [ ] Push normal branch, open/attach PR for261, exact reviewed-head required CI (skip not pass), normal ready+match-head squash, no force/admin. Operator-specific software/agent-review/merge authorization23cca13f is recorded honestly; no invented independent human review or broad policy rewrite.
- [ ] Verify actual merge/tree equality and canonical changed-source/full-tree catalog, within32MiB including all Git and retained artifacts. Handoff new actual source/module pins to original executor for separate deployment/startup gates; no real recovery control or startup here.

## Rulings and self-review

Ruling after RED05: consuming inside final_admission was too early because the existing release method performs one further native PID check after admission. A synthetic name replacement during that check reproduced an incorrect release. The minimal integration is one optional before_gate callback at the existing gate, plus a clock recheck after it; no spawn/signal/vendor/backend replacement. RED06 also proved that opening a substituted FIFO could block before type validation; original-claim opens now use O_NONBLOCK in addition to NOFOLLOW. Both changes are within the selected bounded recovery behavior.

Checkpoint: Tasks1/2 are implemented together as one coherent authority-and-release slice. GREEN11 affected checks:167 passed/70 platform skips; focused Ruff/format/diff checks pass. Baseline fixture omissions, early fixture failures and genuine RED01/03/05/06 remain separately retained; no failed run is relabeled passed. Independent review/publication are still pending.

R1 known fixes: source/host/vendor admission is repeated after marker persistence,
then the authority lease and gate clocks are rechecked. The lease now reopens
the fixed private STATE directory, compares held/live stable directory identity
(device/inode/owner/group/mode/nlink), and resolves claim/marker through that
current directory. Directory size/timestamps naturally change when creating a
regular marker and are not identity pins. RED-R1-SOURCE4 and RED-R1-DIRECTORY5
reproduce the two findings; GREEN12 affected177 passed/70 platform skips.
Known-fix R2 is pending; no additional structural review or operational action.

Ruling: Root already selected design and delegated engineering decisions, execution/review and normal merge; do not ask for another design/method/standard-merge approval. Public test seams are the explicitly authorized fixed CLI, authority FD validation and gated-release callback. Inline is chosen because routing and consumption share one lifecycle; no implementer-agent overlap.

Ruling: native worktree API cannot request sparse/no-checkout; its49MB full tree exceeds32MiB. Existing dirty linked W cannot be reset. A manual no-checkout sparse linked worktree inside the ignored software purpose preserves original changes and shares objects; no setup/dependency install. Worktree-specific sparse config already supported.

Self-review: routing covers every fixed service phase; unique consumption is at final release, not checks/prepare. Original permit is preserved as the observed prior public control, not falsely described as the original unit's expired grant. Held FD/path checks, concurrent O_EXCL, post-consumption failure and unchanged persistent lifetime have explicit tests. No source/vendor/credential/SDK authority is inferred from synthetic green. Budget includes common Git metadata, failures, review and publication. No extra task/platform needed.
