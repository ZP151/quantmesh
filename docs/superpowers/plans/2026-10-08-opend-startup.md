# Windows OpenD and private-tunnel recovery plan

> **For agentic workers:** Use superpowers:executing-plans for the bounded
> implementation, test-driven-development for behavior, and an independent
> reviewer before installing persistent startup configuration.

**Goal:** After the current Windows user logs in, the existing GUI OpenD starts
once and the existing AWS loopback reverse tunnel recovers without a Codex turn.

**User action / metric:** Log in to Windows normally; when OpenD is authenticated
and Tailscale authorization is valid, AWS localhost11111 becomes reachable and
the read-only market feed recovers. Two concurrent helper launches must leave
one helper, one OpenD and no duplicate tunnel. Login/reboot witness is deferred
without restarting Windows in this task.

**Architecture:** Reuse the installed vendor-signed GUI, Windows current-user
Startup shortcut and Tailscale SSH. A hidden current-user PowerShell supervisor
waits for localhost11111, respects any already-running private tunnel, and
retries only its own SSH child after failure. It never reads vendor credentials.

**Tech:** Windows PowerShell 5.1-compatible scripts, native WScript.Shell shortcut,
existing Tailscale CLI, pytest/native PowerShell behavior harness. No dependency.

**Basis:** User requested OpenD self-start after the checked minute-chart release;
the October 8 heartbeat authorizes this reversible operational follow-up.
Issue [#156](https://github.com/ZP151/quantmesh/issues/156); existing private
runbook `docs/runbooks/moomoo-readiness.md` defines the precise route.

## Constraints and inspected state

- OpenD vendor-signed GUI 10.10.7008:
  `C:/Users/15492/AppData/Roaming/moomoo_OpenD/moomoo_OpenD.exe`.
- CLI `C:/Program Files/Tailscale/tailscale.exe`; no existing OpenD Startup/Run
  entry or helper task. Leave unrelated soak/connection tasks untouched.
- Reuse only `ubuntu@quantmesh-staging-8gb`, forwarding
  `127.0.0.1:11111:127.0.0.1:11111`, with existing checked host-key handling,
  `ExitOnForwardFailure=yes`, keepalive30s/count3. No public port or trade APIs.
- Keep existing OpenD and reverse tunnel session75590 alive. Do not kill or take
  ownership of unrelated processes. A remote listener of unknown ownership is
  respected; an indeterminate SSH probe means wait, not spawn competing tunnels.
- Store helper scripts/status outside the worktree under current-user LocalAppData;
  credentials, account IDs, vendor XML/logs and raw SSH output are excluded.
- No remembered-login changes, Windows reboot, logoff, global execution-policy
  change, admin service, credentials, new SDK, alternate broker or AWS redeploy.
- GUI auto-login is a separate vendor setting handled by the user if necessary.
  Launching the program cannot prove authentication or real-time entitlement.
  Official GUI docs show Remember Me/Auto Login; command-line remembered login
  requires account parameters, so it is excluded from this wrapper:
  https://openapi.moomoo.com/pdfs/moomoo-API-Doc-en-Python.pdf and
  https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html.

## Review focus

1. Duplicate logon/manual launches: one current-user mutex prevents duplicates.
2. OpenD process exists but login/11111 is unavailable: wait; no restart or password.
3. Existing reverse listener: leave original tunnel alive; do not compete or kill.
4. Tailscale offline/reauth: bounded wait and a redacted needs-user state; no retry storm.
5. Rollback/uninstall: remove only owned startup/config files; never broad deletion.
6. Auxiliary status-file locks/missing directory: preserve recovery/connection;
   persistence cannot become a route-lifecycle dependency.

## Task 1 — Reviewed supervisor and reversible provisioning

**Files:** Create `deploy/windows/opend_recovery.ps1`,
`deploy/windows/install_opend_startup.ps1`,
`tests/test_windows_opend_startup.py`; update the private readiness runbook.

**Interfaces:** `opend_recovery.ps1 -Once -ObserveOnly` reports redacted state
without process/config mutations; normal mode runs the singleton recovery loop.
Installer supports `-Install`, `-Uninstall`, `-Status`, with explicit existing
OpenD/Tailscale paths, owned target directory and a fixed shortcut name.
The loop must bound connection/probe waits, emit status only when changed,
and terminate only owned child processes when explicitly shutting itself down.

- [x] Write behavior tests first: duplicate helper is suppressed; already-running
  OpenD is not relaunched; absent port waits for login; existing remote listener
  avoids child launch; failed/unknown probe waits; owned child exit causes bounded
  retry; uninstall refuses foreign targets and preserves unrelated files/tasks.
  Mock OS process/socket boundaries without a vendor account or remote machine.
- [x] Run `python -m pytest tests/test_windows_opend_startup.py -q` red, ensuring
  failures name missing recovery/provisioning behavior rather than fixture errors.
- [x] Implement only those states using native tools. Bind both endpoints to
  loopback. Use hidden child windows; never store or expose credentials, and
  never disable host-key verification. Respect existing SSH revalidation.
- [x] Run the focused suite green, PowerShell AST parse for both scripts,
  whole-tree Ruff and `git diff --check`. Record native Windows evidence and
  platform-specific skipped tests separately from cross-platform coverage.
- [x] Independent spec/standards review, maximum two rounds; resolve executable
  findings before installing startup persistence. Commit coherent green slice.

## Task 2 — Current-user installation and actual non-destructive witness

CI37685852546 has one existing replay-fixture failure after 3676 passing tests.
Before Task2, isolate that fixture's retention clock using freeze_buffer_clock
and explicitly exercise the real sweep in its eight interval/state cases.
The forced-sweep RED reproduces its 404; targeted history/native GREEN and
the complete corrected-head CI must pass. This is test-only scope: no runtime
retention or replay change, repeated full local suite, or new structural review.

**Files:** same installer/runbook, `docs/goals/ACTIVE.md`, iteration0037;
ignored reports under `output/0037-opend-startup/`.

- [x] Run `-Status` and `-Once -ObserveOnly` against actual existing processes;
  exact local/remote listeners must be healthy before installation.
- [ ] Install only the named current-user startup shortcut and owned helper
  files. Record target paths and digests; read shortcut back and verify exact
  executable/arguments/working directory. No account credentials or admin task.
- [ ] Launch hidden helper now; launch a second copy and prove singleton exit,
  with existing OpenD PID and original tunnel still present. Verify AWS
  localhost11111 and exact app build/paper=true/live=false afterward.
- [ ] Verify uninstall/reinstall only in an isolated test-owned temp directory.
  Do not uninstall the user's active helper or close existing source/tunnel.
- [ ] Record configuration done separately from next-login/reboot and real
  reconnect witnesses. Do not claim automatic vendor authentication. If login
  is needed, give the user the specific vendor-UI step; never request credentials.
- [ ] One PR for reviewed scripts/runbook evidence; follow standing green-CI
  merge authority. These Windows changes do not require an AWS application
  redeploy. Preserve pending open-session minute-chart acceptance independently.

## Remaining chart acceptance

PR #163 is already merged/deployed as `69515b7`; never repeat deployment.
Four AWS equity paths/reload and supplier-matching closed OHLCV pass, but
open-session source progression, revisions and two new minute boundaries
remain pending. The startup slice may proceed while markets are closed. When
the next regular session is actually open, complete those read-only witnesses
and update the durable records. Capacity and shutdown drills remain later work.
