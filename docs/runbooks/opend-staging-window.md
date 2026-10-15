# Expiring OpenD staging window (#169)

Status: disarmed software candidate. This runbook grants no installation,
service start, login, market-right transfer or production authority. The approved
plan is [the staging window plan](../superpowers/plans/2026-10-13-opend-staging-window.md),
within server-market-independence Task2. Existing Windows OpenD, tunnel,
application endpoint11111 and paper=true/live=false stay intact.

The user action after external approval is to open one private server-owned
vendor pane for initial qualification, for at most900 seconds. The measurable
outcome is a denied launch before release when any required authority is missing,
or a bounded owned launch with cgroup cleanup. Numerical research, authentication,
SDK initialization, market data, production cutover and permanent startup are
separate acceptance steps.

## Fixed authority

`stage_console.py` defaults to pending/exit2 without file inspection, resource
creation or a child. `--owned-fixture` is a separate synthetic path. Only
`--start --nonce <32-lowercase-hex>` and the fixed service `--pane` path may
release the original pinned vendor. No arbitrary command, endpoint, home,
credential, password, account ID or token parameter is accepted.

The only permit is `/etc/quantmesh/opend/staging-window.json`. Root mints it
**after** actual ClassC CI, two distinct human reviews including the safety owner,
and explicit operator/new-device/market-right-transfer window approval. Claiming
those approvals in a fixture is not authority. Permits are strict JSON, reject
duplicate/unknown fields, and contain exactly:

| Fields | Required meaning |
| --- | --- |
| schema_version, purpose | integer1, `opend_initialization_qualification` |
| nonce | fresh32 lowercase hex; never reuse |
| approved_build, launcher_sha256 | reviewed40-hex Git commit and exact64-hex installed launcher bytes |
| tmux_version, tmux_sha256 | `3.4`; `034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd` |
| machine_sha256 | SHA256 of the complete `/etc/machine-id` file bytes; fixed `a6645ff4a0ce2ff2625300b3d084e4ed878ce0b3a8cd9a7bd30f0f7126085191` |
| gateway_uid, gateway_gid | actual positive IDs of fixed `quantmesh-opend` user/group; no supplementary authority |
| not_before, expires_at | explicit UTC-aware timestamps, ordered window no longer than900 seconds |
| max_seconds | integer1..900; booleans rejected |
| human_reviewers, safety_owner | two distinct noncredential reviewer IDs; safety owner is one of them |
| ci_conclusion | `success`, backed by actual reviewed-build CI |
| operator_window_approved, new_device_approved, market_right_transfer_approved | literal true, backed by the operator's approval |

There are no source, installation, private-input or SDK qualification fields.
The original blocked profile digest is mandatory; setting qualification flags
true makes staging deny. The production unit retains `--require-qualified`.
Every receipt keeps production/source/authentication/installation/market flags
false, including a successfully stopped staging launch. A root file expresses
trusted external review authority; the launcher does not query GitHub or certify
that review's truth. The coordinator must confirm the machine digest's byte
convention against the recorded intake before minting; disagreement denies and
does not permit replacing the machine pin.

## Protected installation and backend prerequisites

The fixed target is `quantmesh-staging-8gb`, dedicated nonroot `quantmesh-opend`,
loopback11112, `/opt/quantmesh/opend/10.10.7008/OpenD` and the existing exact
profile argv. No Windows device/state/config is imported. The coordinator must
protect the complete pristine vendor installation, source helpers, reviewed
noncredential XML, profile, launcher and template with root-owned immutable
parents. Regular files must be no-follow, single-link, non-writable by group/
others, with no set-ID/capability executable. The launcher inspects installation
metadata and fixed QuantMesh XML only; it never reads vendor state, credentials,
logs, process cmdline/environment or journal bytes.

Install the unchanged validator at `/opt/quantmesh/opend/validate_profile.py`
(SHA53fb2821b21dc695a2934dd20d6822f69714e960585e371181d20d0b81441736)
and unchanged private-terminal helper at
`/opt/quantmesh/opend/qualify_opend_private_terminal.py`
(SHAc18a81701ce432cb93e1ac2243b31add34f3ec10944dc381b92ff8e1d0133b63).
Only pinned source bytes are compiled; import loaders/bytecode/shadow paths are
not used for those helpers. Live modes require native single-threaded
CPython3.12x86_64 with `-I -S -B`, root-controlled OS stdlib/libc and real pidfds.
This is not a signature or complete OS/vendor closure certificate.

The new template goes at `/etc/systemd/system/quantmesh-opend-stage@.service`;
its exact bytes are pinned in the launcher, overrides denied. It is separate
from the production unit and has no install/enable target. The manager must
report exact user/group, runtime, modes, null standard streams,900-second maximum,
15-second stop grace, control-group kill and no restart. Missing/unknown properties
deny. Vendor/runtime directories must already satisfy the declared protection;
unexpected links/layouts require returning the fact to the coordinator, not a
local permission workaround.

tmux3.4 is only a candidate. The coordinator's read-only Ubuntu3.4-1ubuntu0.1
binary/copyright hash check does not establish signatures, dependency closure,
actual-host admission or lifecycle. Complete the external backend audit and
real manager/property/pane verification before actual operation. No tmux,
systemd daemon or vendor was executed by the local implementation proof.

## Foreground ordering and private pane

The [official tmux3.4 manual](https://raw.githubusercontent.com/tmux/tmux/3.4/tmux.1)
forbids commands after `-D`. `ExecCondition` checks the fixed permit without a
terminal/vendor; `ExecStartPre --prepare` writes only a fixed runtime configuration
to the nonce-specific0700 directory. `ExecStart` executes tmux `-D -f` that
configuration and `-S` that private socket. Configuration contains only fixed
privacy settings. A fixed `ExecStartPost --create-pane` waits at most5 seconds
for the socket, verifies the own backend/unit/cgroup, then invokes a subsequent
`tmux -N` client to create the detached session using multiple direct executable
arguments, with no `sh -c` or user configuration. Type=exec orders that step
after successful foreground exec; actual backend readiness still needs native
backend proof. tmux's [3.4 config selection](https://raw.githubusercontent.com/tmux/tmux/3.4/tmux.c)
clears ambient config paths when `-f` is specified. The template's null streams
keep both daemon and vendor terminal output out of journals.

Pane/history/command-prompt history, clipboard, copy commands and key bindings
are disabled. tmux3.4 [requires buffer-limit >=1](https://raw.githubusercontent.com/tmux/tmux/3.4/options-table.c):
use1 and disable buffer-creation mechanisms, rather than invalid0. No
capture-pane, pipe-pane, buffers, transcripts, verbose logging, shell tracing or
journal capture is used by the launcher. An authorized same-UID operator/root
can still change tmux settings or observe memory; this is an explicit trusted
operator boundary, not secrecy from that authority. Ordinary terminal scrollback
on the human's SSH client is also outside the kernel fixture's claim; the human
must use a private non-recording client.

The fixed pane sets0600/echo-off on its own inherited terminal. Before vendor
release, the guard checks three retained descriptor directions/devices/owners,
actual MainPID parentage, exact own unit/cgroup, retained backend pidfd, protected
tmux executable inode/hash, socket, pane PID/TTY and recording metadata. It
reloads the same permit, all source pins and manager state immediately before
opening the child's release gate. The parent never reads/relays terminal bytes.
The vendor inherits those descriptors directly and a bare fixed environment.

An exclusive0600 nonce claim in persistent `/var/lib/quantmesh-opend-stage`
survives service runtime-directory removal. A failed claimed attempt consumes
the nonce; do not delete claims to retry. Root/operator are trusted to protect
the permit, persistent claims and dedicated identity.

The guard binds remaining wall expiry to a monotonic deadline, monitors both,
and uses retained pidfds for direct-child stop. The gated child has independent
registration timeout, timer and Linux parent-death signal. Registration blocks
INT/TERM/HUP and retains ownership before unblocking. Unregistered children exit
on gate EOF/timeout; no bare PID/PGID kill. Ending a stage signals the verified
backend MainPID so systemd's control-group cleanup includes descendants before
the permit can be treated as an ongoing window. Stop grace is at most15 seconds.
The SSH client only attaches to the owned socket: detach/client loss does not
govern tmux/vendor lifetime. Actual backend/client-detach and descendant cleanup
remain source-host acceptance work.

After all external gates, the human coordinator may start the exact nonce unit
and the operator may attach with the pinned tmux's `-N -f /dev/null -S` fixed
nonce socket and `attach-session -t =opend`. These are future manual actions,
not implementation-session commands. The assistant does not observe or control
the login terminal. Notify before device verification, market-right transfer
or costs; do not request a password/verification code in chat.

## Local proof and handoff

Use an existing pytest tool environment, never install packages globally:

```text
python -m pytest tests/test_opend_staging_window.py -q --basetemp output/169-staging-window/test-temp
python3.12 -I -S -B deploy/aws/opend/stage_console.py
python3.12 -I -S -B deploy/aws/opend/stage_console.py --owned-fixture
ruff check deploy/aws/opend/stage_console.py tests/test_opend_staging_window.py
ruff format --check deploy/aws/opend/stage_console.py tests/test_opend_staging_window.py
git diff --check
```

The synthetic fixture runs under90 seconds including cleanup. It creates only
a fresh owned0700 root, private0600 echo-off PTY and fixed stdlib synthetic
children. Real fork/gates/pidfd/waitpid/expiry/HUP/parent-loss and sibling survival
are measured; root permit, real systemd manager/cgroups, tmux backend and source
host are explicitly mocked/absent. No terminal marker, vendor stdout, account,
auth, market or SDK call is made. Child/fixture receipts cannot establish actual
host privacy, authentication, source clocks or production qualification.

Keep raw failing/passing commands, exits, checksums and final committed fresh
native proof plus HANDOFF under ignored `output/169-staging-window`. Review only
these four new files on Spec and Standards, at most two rounds. Coordinator owns
integration and tracked iteration/ADR/REUSE/ACTIVE updates; no push/merge/deploy
or login follows this handoff. ClassC human/CI/operator and source/backend gates
stay pending, and fixture success does not complete Option A.
