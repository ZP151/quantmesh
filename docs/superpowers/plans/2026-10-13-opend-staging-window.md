# OpenD Expiring Operator Staging Window Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans, test-driven-development and verification-before-completion. New bounded Task2 slice; Spec/Standards max two rounds, no review of completed source/terminal/service architecture.

**Goal:** Deliver a usable, explicitly authorized temporary OpenD launch path before actual login/SDK qualification, without weakening production admission or making vendor lifetime depend on the personal SSH client.

**Architecture:** A distinct disarmed systemd stage template owns a foreground private tmux server; its pane invokes a fixed Python guard. The guard verifies an expiring root-owned operator window and private inherited terminal, then starts only the pinned OpenD through a gated retained kernel handle. Input/output go directly to the private pane, never through Python, logs or journals. The original production unit/profile remain unchanged and blocked.

**Tech Stack:** LinuxCPython3.12x86_64 stdlib, existing pinned validate_profile/private-terminal helper, external tmux3.4 and systemd candidates. No new core/service package. External backend audit and actual host operation remain independent release prerequisites.

**Spec:** approved2026-10-12-research-foundation.md; server-market-independence Task2; opend-authentication-review.md steps2–3. Local terminal f99b020 is integrated83517eb; source SDK anonymous ACK remains unqualified, not an authentication prerequisite assumption.

## Global Constraints

- Only new deploy/aws/opend/stage_console.py, deploy/aws/opend/quantmesh-opend-stage@.service, tests/test_opend_staging_window.py and docs/runbooks/opend-staging-window.md. Root owns existing profile/unit/validator/private helper/REUSE/ADR/ACTIVE/iteration. No production settings edit.
- No actual host/install/systemd/tmux daemon/vendor/SDK/SSH/network/auth/market/paid/model/Windows/helper/tunnel/user/policy operation in this implementation session. Public read-only official backend documentation/licence metadata allowed; do not install or execute an unaudited backend. Native fixtures use fixed synthetic stdlib children, not a vendor or daemon.
- Staging lifetime <=900seconds, stop grace<=15seconds; native fixture<=90seconds including cleanup. Default CLI is no-effect/pending exit2. Only --start may launch a real pinned vendor after EVERY live authority/identity/terminal/backend/cgroup check; implementation must not invoke it on a real host. Explicit --owned-fixture has a separate fixed synthetic path and always production/source/auth qualification=false.
- Existing production --require-qualified stays intact. A staging permit is qualification authority only, never a source/wire/private-input success receipt. Missing/malformed/expired/reused/non-root-owned permit or unavailable kernel/systemd/backend identity denies before release.
- Fixed source target is existing quantmesh-staging-8gb: machine-ID SHA a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191, dedicated quantmesh-opend, paths/port11112/argv from existing profile, paper=true/live=false. No arbitrary commands/endpoints/config/vendor-home or credential parameter accepted.
- Root-protected fixed files: /etc/quantmesh/opend/staging-window.json, gateway-profile.json, OpenD.xml; /opt/quantmesh/opend/stage_console.py plus validated helper files and vendor10.10.7008. Protected roots/regular no-follow single-link files, immutable parents and hash checks; no vendor state/credential XML/log/env/cmdline reading. Only QuantMesh-owned pinned noncredential config is inspected.
- Private helper SHA c18a81701ce432cb93e1ac2243b31add34f3ec10944dc381b92ff8e1d0133b63; validator SHA53fb2821b21dc695a2934dd20d6822f69714e960585e371181d20d0b81441736; blocked profile SHA0e0b15be83e2b7b435d4e6dbb94f2cbd9c7833e681c4af517e361f5b80b40e17. Vendor/config pins unchanged. Reject shadow/bytecode/import drift; --start requires isolated interpreter and single-threaded registration.
- Parent never reads/relays terminal bytes. Synthetic fixture only uses ephemeral noncredential marker bytes, never archives marker, raw terminal content or raw exception. No tmux capture-pane/pipe-pane/buffers/transcripts, shell tracing or journal capture. Nothing promotes same-UID/root secrecy or actual source-host privacy from a fixture.

## Authority and backend contracts

StagingWindow strict schema: schema_version=1, purpose=opend_initialization_qualification,
nonce(lowerhex32), approved_build(lowerhex40), launcher_sha256(lowerhex64),
tmux_version=3.4, tmux_sha256(lowerhex64), machine_sha256 above, gateway_uid/gid
(actual fixed named account, nonroot), not_before/expires_at(UTC aware),
max_seconds(int1..900), human_reviewers(two distinct IDs), safety_owner(in reviewers),
ci_conclusion=success, operator_window_approved/new_device_approved/market_right_transfer_approved=true.
These claims come only from a root-controlled file minted AFTER real ClassC
CI/two-human review and operator window approval; tests cannot create that
authority. No passwords/account IDs/tokens/unknown fields. Source/SDK/install
qualification flags are NOT permit fields. Recheck before release, bind wall
expiry to a monotonic deadline, prevent normal duplicate nonce launch through
an exclusive owned runtime claim. Trusted root/operator threat boundary explicit.

Template derives fixed nonce from its systemd instance, uses User/Group
quantmesh-opend, RuntimeMaxSec=900, TimeoutStopSec=15, KillMode=control-group,
Restart=no, UMask0077 and a0700distinct runtime/socket directory. Foreground
tmux -D uses no ambient user config, recording/history disabled and approved
helpers only. ExecCondition runs --check-window without terminal/spawn effects;
guard --start in its pane verifies same own unit/cgroup, backend MainPID/exe/hash,
User/runtime/kill/restart/null-journal properties and private pane TTY, not a
borrowed global tmux/server. Prefix/no matching cgroup is insufficient.
Implementer must reconcile real tmux foreground/pane-creation ordering from
official docs; if the template cannot express reliable creation/ownership without
another maintained helper or authority change, stop to root with evidence.
No guessed command with shell interpolation or implicit daemon lifetime.

## Bounded delivery

Interfaces: load_staging_window(path)->StagingWindow; validate_staging_window(window,
*, now, identity, hashes)->None; inspect_staging_context(window)->dict;
start_staging_console(window)->dict; run_owned_fixture()->dict; main(argv=None)->int.
Code may keep a smaller internal split, but no new unowned files or public
arbitrary child/command API. Output fixed safe status/error and false release flags.

- [ ] Restore required docs/exact frozen coordinator SHA, isolated managed worktree and independent codex branch; no divergentmain reset. Only four additive files.
- [ ] RED policy: expired/future/overlong/boolean duration, unknown/credential fields, wrong machine/uid/root ownership/hash, malformed review/source claims, duplicate nonce, true profile qualification or unsafe argv all deny before any spawn/input. Preserve actual RED/exit.
- [ ] Implement minimal strict bounded/no-follow/root-protected permit and exact blocked profile/helper/artifact admission; unknown live state denies. No GitHub/network authority lookup or credential discovery; operator minting requires actual external review evidence later.
- [ ] RED live-context cases: nonprivate/echoing/mismatched/wrong-direction/replaced TTY, borrowed cgroup/backend/pidfd, missing manager/nonce ownership and unsupported Python/native platform deny. Verify template has900/15/control-group/no restart/no journals/private socket/history; no test calls a real manager/daemon.
- [ ] Implement fixed pane guard with admission-before-release, interruption-safe registration, parent-loss/deadline/HUP cleanup through retained handles and explicit pending failures; cgroup authority owns any vendor descendants. Default and --check-window have no start effects. Bare fixed child environment; no account/trade/market calls or secret relay.
- [ ] GREEN pure/native tests and fresh actual synthetic lifecycle proof: expiry, wrong authority, interrupted handle registration, parent loss, blocked child and known sibling survival; record what systemd/root/backend checks are mocked separately from kernel/PTY facts. No real service/daemon/vendor execution. Final receipt explicitly production/source/auth=false.
- [ ] New four-file Spec/Standards max2rounds; Ruff/format/diff and exact committed fresh native proof. No third old architecture review. Review focus: permit≠qualification; root/bytecode/path race; interruption before registration; client detach≠server lifetime; expiry/cgroup cleanup and false positive native admission.
- [ ] HANDOFF clean reviewed commit/four files/raw commands/exits/hashes/native-vs-mocked limits, STOP. Root verifies/integrates/archives then completes backend audit, actual host/ClassC/CI/operator prerequisites. No stage invocation, marker change or login follows automatically.

Planner: advance real temporary source-start software, not another anonymous SDK
retry. Researcher: no numerical/data/model claim. Verifier: local kernel proof
does not certify manager/backend/host. Actual protected installation, independent
server terminal/client-detach lifecycle, human login, acknowledged original SDK,
market/calendar/browser/rollback and final permanent gateway remain required.
