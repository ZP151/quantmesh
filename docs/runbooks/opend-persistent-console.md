# Single-operator persistent private OpenD console (#192)

The actual operator explicitly requested single-person approval and a persistent
private login process. `Operator` is one human serving operator, reviewer and
SafetyOwner roles. This is an explicit scope-specific override of the historical
two-person stage authority, not a claim of two independent human reviews. It does
not change credential ownership for the separate model advisory service.

Use the reviewed `stage_console.py` with `--persistent` and the separate
`quantmesh-opend-console@.service` template. The original schema1 stage and its
900-second termination remain unchanged. Default invocation remains disarmed.

Root-controlled `/etc/quantmesh/opend/persistent-session.json` has the original
permit fields, schema_version2, purpose `opend_persistent_private_console`,
human_reviewers `["Operator"]`, safety_owner `Operator`, and the additional
session_lifetime `until_operator_stop`. Build/source/tmux/machine/UID pins and
actual successful release checks must match. Unknown fields, credentials,
fabricated second reviewers, duplicate nonces, wrong roles and expired initial
launch permits deny. `max_seconds` and timestamps still bound initial release
to at most900 seconds; successful release does not renew a stage permit.

The persistent service starts the foreground audited tmux backend and a fixed
private pane. It retains the vendor child by pidfd and parent-death protection,
with no vendor lifetime alarm. The service has no time-based termination or
automatic restart: MemoryMax1GiB, MemoryHigh768MiB, swap0, CPU50%, TasksMax128,
control-group cleanup and15-second stop grace. There is no install/boot-enable
target. Source, vendor, noncredential XML and unit bytes remain pinned; the
API stays at loopback11112. No remembered password, AutoLogin, capture, journal
terminal output or assistant observation is authorized. A running session is
not authentication, SDK, market-right or source qualification.

Only after actual merged-source and host lifecycle checks, root mints one fresh
nonce permit and starts that exact instance. The human attaches from a private
nonrecording Windows terminal using Tailscale SSH and the pinned tmux, with
`-N -f /dev/null -S /run/quantmesh-opend-console-<actual_nonce>/socket`
`attach-session -t =opend` as the dedicated identity. Do not publish an invented
nonce. The human enters login and device verification directly in that pane,
declines remembering the password, and reports only success/failure in chat.
The assistant must never capture, read, screenshot or control that vendor pane.

SSH-client loss leaves the same backend/guard/vendor process under systemd
ownership. The authenticated session lasts while the process and vendor session
remain active; no automatic reauthentication is promised after exit/reboot.
Stop only the recorded owned unit after checking its nonce/PID/start identity.
Keep old Windows11111/tunnel/application routes and all failure history.
After human confirmation, actual SDK READY/source evidence remains a separate
read-only acceptance step; do not switch the application endpoint automatically.

Verification: affected stage/persistent/private-terminal tests in an existing
native Linux tool environment, Ruff/format/whitespace, independent review and
exact-current CI. Then an actual installed-source synthetic persistent
manager/PTY/client-detach/owned-stop proof, followed by the real human pane.
