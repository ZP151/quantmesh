# Canonical DuckDB finite diagnostic plan

> **For agentic workers:** Use superpowers:executing-plans and verification-before-completion. This is an operator prerequisite, not a production decoder change.

**Goal:** Observe DuckDB1.5.5 exact-path and configuration-lock behavior in the actually installed canonical AWS image.

**Architecture:** One nonce-owned, non-root, readonly/no-network container runs fixed literal SQL over two tiny self-created Parquet files in noexec tmpfs. The host observer validates the immutable image against the actual installation receipt, captures output before evaluating exit, and removes only its exact stopped container. No model/provider/research input or production module is mounted.

**Tech Stack:** Existing AWS Docker29.9.0, canonical CPython3.12.15, installed81-wheel image, Python standard-library observer and DuckDB1.5.5.

**Spec:** Existing approved Option A and 2026-10-13-aws-numerical-materialization.md G1 investigation; raw installation receipt output/0038-aws-numeric-wheel-install-success.json (5336bytes/SHA30a62b81e8712534288e3381c0a71f610305b56a6a0092ac8831058666b61e8f).

## Global constraints

- Original root /home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a, UID1000/0700 and original free-before are preserved. New phase canonical-duckdb-policy is exclusive; inspect after an unknown outcome, never recreate or retry blindly.
- Exact Engine cfe71bf3-9059-4059-887d-ac401f2283ec; expected2images/0containers. Image sha256:093b47341cb1c02ae0d9490ed40fbf0bc325ff224bced40329674942cced991c and all five diffIDs must match the actual saved installation receipt. No image commit/pull/tag/delete.
- Child /usr/local/bin/python3 -B -I -S, UID/GID10001, readonly rootfs, network none, cap-drop ALL, no-new-privileges, CPU1, pids32, memory/swap512MiB, tmpfs/tmp16MiB/noexec/nosuid/nodev and no host mounts. No RLIMIT_AS substitution for the cgroup limit: old WSL1GB virtual-address diagnostics crashed and remain unqualified.
- Set and verify this child's Linux dumpability0 before importing DuckDB; CORE0 alone does not prove no piped crash capture. Use fixed libc prctl SET4/GET3 with explicit C argument types and return checks. No global core_pattern/sysctl change and no claim about all possible host startup faults. Primary references: https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html and Linux include/uapi/linux/prctl.h.
- Fixed source only; no user data, Worker/Agent/research import, extension INSTALL/LOAD, HTTP request, key, vendor connection, trade, production activation or per-type native exemption. Disable known extension autoload/autoinstall, community/unsigned extensions and persistent secrets before either connection. Exact allowlisted files remain inside owned/tmp.
- Probe deadline30s/poll0.5s; bounded host CLI output64KiB and preserved raw stdout/stderr before exit evaluation. Stop/reap/remove only exact nonce/CID, no force or global cleanup. Failed or unobserved outcomes stay failed/unproven.
- Whole original AWS numeric-materialization5GB/free50GB; expected new host artifacts <=100KB and ephemeral tmpfs <=16MiB. Prior PG831,553,536B and all old source/install failures remain separately retained.
- Explicit NEW120KB software/source/evidence/review/copy reservation on SAME8,876,772B baseline and SAME24MB ceiling; full5.5MB foundation/250KBoperator/2MBfixtures/200KBTask178 reservations and524,611,584B private unread crash payload stay intact. No new local native execution/env/wheels/images/clone. Recheck full frontier plus600KB Task177/178 bound before writing/executing. Whole-C attribution remains pending/no reset/no waiver.

## Review focus

1. Wrong image/layers or owned phase must refuse before container creation/start.
2. Incomplete/failed create/start/log observation must not imply success or trigger broad cleanup.
3. Initial fixture creation must use the same disarmed extension settings and exact two-path allowance; no unguarded default connection.
4. Sibling-path and locked-setting cases pass only for their precise expected DuckDB exceptions; unrelated errors are failures.
5. A passing finite diagnostic must not activate or certify native Worker/G3/schema/row bounds/kernel/real reports.

## One task: fixed probe and actual AWS receipt

**Files:** New ignored output/probe_aws_duckdb_policy.py and output/check_duckdb_policy_observers.py; narrow resource-helper update and this plan. No production source/test/lock/config change.

- [ ] Write pure-software negative observer checks for failed child exit, malformed/false case output and mismatched canonical observation. Retain RED and GREEN; these are scripted observer checks, not native qualification.
- [ ] Implement fixed child policy and immutable/owned host observer, output capture, deadline and exact cleanup. Reuse reviewed canonical/installer boundary shapes and retain all old diagnostics.
- [ ] Obtain one bounded review of this new fixed diagnostic recipe only; no third full architecture review or redispatch of completed178.
- [ ] After review/resource checks and fresh phase observation, execute once through the existing authenticated AWS console. Recover raw receipt with a byte hash, verify actual exit/noOOM/PID0/exact cleanup/Engine2/0 and exact cases/settings. A failure is retained and diagnosed directly, not rerun under weaker settings.
- [ ] Mirror actual scoped evidence and remaining G1/G3/full-runtime/private-service/real-job/Agent/provider gates. Keep Option A ACTIVE.

## Source-bound initialization-order continuation

The first actual canonical phase failed before fixture creation and remains
retained (receipt SHA4305803c). DuckDB1.5.5 custom_settings.cpp236-242 and206-211
refuse constructor allowed_paths/allowed_directories before file_system exists;
database.cpp63-65 applies those options before Configure441-445 initializes it.
The exact first exception message was not saved, so it is not reconstructed.

Corrected recipe uses NEW exclusive canonical-duckdb-policy-order, binding that
prior receipt before create. One fixed child characterizes both constructor
refusals with exact source-derived messages, then connects with initial disabled
extension/secrets controls. It clears temp_directory, sets exact paths/empty
directories, disables external access and locks configuration BEFORE COPY/read.
Container isolation, fixed SQL, dumpability, resource limits and cleanup remain.
Fixed-fixture errors now retain a bounded2048-character message/finer step.
No local native retry or production decoder change. Scripted initialization
boundary RED1/GREEN30/0 is retained; actual corrected AWS execution is pending
the narrowly changed recipe review and same original resource/phase gates.

## Latest canonical policy PASS — CI release repair pending

Actual AWS order phase20:43:48UTC exits0 on reviewedbd7585d2/installed093b4734.
Both constructor path refusals and four exact-path/configuration-lock cases pass;
CPython3.12.15/DuckDB1.5.5, dumpable0,424B fixtures, noOOM/PID0, owned CID removed,
same Engine2images/0containers. Receipt3821B/SHAf37609f7bb1617b98512aa66175d3cdabaf7195e4800181610cbef127ec54f8e
and stdout2212B recovered byte-exact. Independent saved-field checks pass;
start/finish are source-checked during execution but not serialized. Earlier
function replay used synthetic timestamp labels, not actual timing evidence.
Old failed phase/source remain. No full native/Worker/kernel/production certificate.

Owned-leader retirement repairs now pass7focused Linux cases/35deselected4.01s;
source33916bb4/tests a8a33007 are integrated in draft PR175; formatting AST is unchanged.
Bounded retirement review is clear; Ruff/format/diff pass. Full CI/human gates pending.
Old2948 CI38454677312 stays terminalFAILED/no rerun. Both deterministic REDs,
partial1fail8pass, and two test-fixture budget overruns are retained. Root preserved
one newly created2MiB synthetic output byte-exact as2055B compressed before removing
only that disposable plaintext; no historical/private crash files touched. Resource
pass is not inferred from test pass. Option A ACTIVE; next closes release gates,
then G1/G3/full runtime and actual private jobs/reports/Agent/server-source acceptance.

## Latest finite diagnostic failure and terminal CI — still ACTIVE

Actual AWS finite DuckDB diagnostic20:28:56UTC used reviewed source9a6a9c45,
canonical installed image093b4734 and one exclusive canonical-duckdb-policy
phase. The two bounded review P2s were fixed with extracted-function RED1 and
scripted GREEN27/0: exact inherited installation/probe label union and exact
path/setting refusal reasons plus unchanged settings. Scoped follow-up is clear.

Actual child exits1/InvalidInputException at disarmed_fixture_creation; noOOM,
PID0, owned container removed, same Engine2images/0containers. Raw failed receipt
1100bytes/SHA4305803c5a353f75078b6e47eaf41ebbc9f395ca33a18ad5b8739df451d7f82b
and raw stdout230bytes/SHA40cd356629d4be9bb7145000d0864e322356ff7d2e7f1f2f5f5b5e2c5237492f
were recovered byte-exact from named server files; stderr is empty. Original
phase/source/failures are retained, no native retry or weaker-policy rerun.
Original host introduced1,181,843,456B/free160,249,409,536B. Native/Worker/kernel/
numerical/production/Option A acceptance remain false. Source inspection points
to allowed_paths/allowed_directories constructor ordering, but the first receipt
does not retain an exception message or finer step; exact cause is unproven.

PR175 exact2948 CI38454677312 is TERMINAL FAILURE20:25:55UTC, not still running.
Release:4600passed/139skipped/1failed/21warnings3377.18s. Only failed case is
test_stdout_stderr_and_nonzero_exit_are_retained: expected command failed,
actual command family ownership refused; no unowned signal. Research_service,
fast and classify pass; python aggregation fails from release. Retained bounded
actual terminal tail and read-only source diagnosis indicate a possible short-
lived child retirement race, not a verified predicate/call site. Next requires
deterministic terminal-window reproduction preserving unknown-live and identity
guards. No old/new CI rerun, merge, deployment or full local suite was performed.

Next: isolate canonical connection/setting order with source-bound diagnostic
evidence and diagnose the one ownership failure without weakening either gate;
then full canonical G1/G3/native admission and real private services/jobs/reports/
Agent/server-market cutover. Task177/178 remain completed/no redispatch. The
initial research Tailnet authentication confirmation is accepted; extra Tailnet
SSH check is still not claimed. Existing authenticated AWS console route worked.
No new fee/key/model call, Windows/helper/tunnel/GUI change or trade. Formal168h
remains NOT_REQUIRED/on-demand. All original baselines/caps and private unread
crash payloads stay retained. Full Option A remains ACTIVE, not complete.
