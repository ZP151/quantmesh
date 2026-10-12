# OpenD Private Terminal Qualification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, test-driven-development and verification-before-completion. Review only this new bounded Task2 prerequisite, max two rounds.

**Goal:** Demonstrate the native private-terminal admission and owned-process lifecycle needed before presenting an actual server OpenD login window.

**Architecture:** Reuse Linux terminal/pidfd primitives and the repository's admission-before-release pattern. Validate inherited terminal descriptors without reading input; qualify the behavior on a fresh synthetic PTY/process fixture. This delivers a reusable admission boundary and native evidence, not an installer, authentication relay or a successful source-host login.

**Tech Stack:** LinuxCPython3.12x86_64 standard library only; fresh owned native resources, no package/dependency changes.

**Spec:** Task2 of2026-10-12-server-market-independence.md, approved2026-10-12-research-foundation.md, and docs/runbooks/opend-authentication-review.md steps1–3; issue#169 / iteration0038.

## Global Constraints

- One product iteration, max two implementation sessions. Backup#a391 is the other live session. Root owns shared profile/unit/validator/app/REUSE/ADR/ACTIVE/iteration and integration. Completed SDK69d3/source4a9b/service5bc4/PGc7be stay idle.
- No AWS/SSH/network/vendor OpenD/SDK/login/account/market/provider/model/trading call, password, user credential, helper/tunnel/Windows/OS-service/global package/user/policy operation. This native local fixture is not a human authentication attempt.
- Create only tools/qualify_opend_private_terminal.py, tests/test_opend_private_terminal.py, docs/runbooks/opend-private-terminal-qualification.md. Scripts/raw receipts/HANDOFF in ignored output/169-private-terminal. No upstream copying or new dependency.
- Default CLI preflight is no-effect/pending with exit2. Only explicit --owned-fixture may create NEW0700root/PTY/processes. No command/DSN/TTY path/credential/production directory target accepted from CLI/config. Never inspect inherited vendor state or process env/cmdline.
- Parent admission code never reads terminal input/output. Only the explicit synthetic fixture owns a random noncredential marker and ephemeral PTY-master bytes to check echo behavior; never archive marker/raw terminal bytes. Emit whitelisted counts/booleans/IDs/hashes and safe error codes only.
- Total owned fixture deadline90seconds including startup/failure/cleanup; every child held behind admission until handle/identity registered. If ownership is unavailable, do not release; child gate exits independently. Use retained Popen/pidfd handles, not bare reused PID/PGID signals. Record incomplete cleanup explicitly, never PASS.
- Current authentication.private_input_verified, SDK wire, server startup/operator/install flags remain false. Final production_release_qualified=false and source_host_private_input_verified=false even on a genuine local fixture pass.

## Review Focus

1. Echo/ECHONL enabled, group-readable or non-terminal descriptors refuse before child input; zero captured bytes is not substitute for termios/owner/device inspection.
2. Different stdin/stdout/stderr terminals, wrong owner, replaced descriptor or descriptor identity change refuse; no arbitrary filesystem TTY path is admitted.
3. Startup interruption between child creation/handle registration, missing pidfd/proc identity or admission timeout cannot release an unowned process or leak one.
4. Operator-side disconnect/HUP, blocked child or output growth must retain bounded owned cleanup; a known sibling survives each individual termination.
5. Fixture success, mock policy checks or no logs alone cannot promote actual AWS/private-input/auth/source qualification.

## One bounded deliverable

**Files / interfaces:**
- tools/qualify_opend_private_terminal.py: TerminalQualificationError with fixed nonsecret codes; inspect_private_terminal(stdin_fd:int, stdout_fd:int, stderr_fd:int, *, expected_uid:int)->dict; run_owned_fixture()->dict; main(argv=None)->int.
- tests/test_opend_private_terminal.py: pure negative admission and actual native fixture/lifecycle regressions. Linux-only native cases skip explicitly on Windows; root Windows checks do not certify native behavior.
- docs/runbooks/opend-private-terminal-qualification.md: exact commands, recorded scope and next actual-host/human staging gates; no ready-to-run credential or installation instruction.

- [x] Restore required docs and exact frozen root integration SHA; create isolated feature branch from that SHA in the provided managed worktree, preserve localmain. Record actual native platform, UID and owned path.
- [x] RED admission cases: ECHO and ECHONL independently enabled, mode0620, wrong owner, non-character/non-TTY descriptors, mismatched terminal descriptors, boolean/invalid UID and changed fd identity all refuse before release. Terminal inspection returns only fd/device/inode/owner/mode/echo metadata, never input/output content.
  Run python -m pytest tests/test_opend_private_terminal.py -q with a workspace-owned basetemp; preserve RED log/exit.
- [x] Implement minimal inherited-FD admission using fstat/isatty/tcgetattr plus exact descriptor identity checks and expected owner; no read(), transcript, journal, environment or terminal path discovery. Refuse unsupported native inspection instead of guessing.
- [x] RED native lifecycle cases: interruption during identity registration, missing handle, gated child timeout, HUP/disconnect and a blocked synthetic child all require terminal owned cleanup and sibling survival. Capture original handles before release; pending identity cannot authorize bare PID signalling. No arbitrary child callable/command exposed via CLI.
- [x] Implement explicit fresh synthetic fixture using PTY and fixed helper entry. Parent admission never reads credentials; fixture-only master observer consumes bounded ephemeral synthetic bytes without persisting them. Check admitted echo-off input reaches only synthetic child; distinguish policy admission, transport, input confidentiality within this fixture, and cleanup evidence. Do not infer broader OS/same-UID secrecy.
- [x] GREEN focused tests and actual NEW native fixture. Independently assert mode/owner/device/echo state, marker-not-echoed and accepted byte count, disconnect/timeout/failure cleanup, all owned handles terminal, sibling survives, <=90s and all production flags false. Store counts/hashes/whitelisted witness JSON and raw command exits only.
- [x] Run Ruff/format/diff checks and Spec/Standards review for the new three-file slice, max2rounds. Fix actual findings with RED/GREEN and final fresh native proof on the committed candidate; no third completed source/profile architecture review.
- [x] HANDOFF clean exact SHA/three files/import hashes/native commands/exits/negative evidence and source-host limitations; stop. Root verifies/integrates/archives. No host deployment, vendor login or marker change follows from this session.

Planner: unblock the private-input prerequisite, retain actual one-shot staged
launch/ClassC-human/SDK/source acceptance after this fixture. Researcher: no
prices, strategy returns or model efficacy. Reviewer: terminal/handle/secret
boundaries. Verifier: real native PTY/process evidence, not fixture-labelled
booleans without operating-system observations.

Root acceptance: f99b020 integrated83517eb; native38/0skip, rootWindows4/34Linux skips, default2/fixture0, independent8children and73rawstreams verified. No actual source-host/input/auth qualification.
