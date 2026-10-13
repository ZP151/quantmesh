import hashlib,json,pathlib,subprocess
O=pathlib.Path(__file__).resolve().parent;R=pathlib.Path((O/'native-root.txt').read_text().strip());F=pathlib.Path((O/'fixture-root.txt').read_text().strip())
M=json.loads((O/'audit-manifest.json').read_text());N=json.loads((O/'receipt-native.json').read_text());C=json.loads((O/'native-controller.json').read_text());V=json.loads((O/'independent-check.json').read_text());L=json.loads((O/'license-admission.json').read_text())
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
G=json.loads((O/'git-final.json').read_text(encoding='utf-8-sig'))
assert G['head']['stdout'].strip()=='5aab2346f2f4f4378ed1fe0570abb3be258a8fc7'
assert G['branch']['stdout'].strip()=='codex/0038-terminal-backend-audit'
assert G['status']['stdout']=='' and G['diff']['stdout']=='' and all(q['exit']==0 for q in G.values())
(O/'git-final.json').write_text(json.dumps(G,indent=2))
tmux=next(p for p in M['packages'] if p['name']=='tmux');source=next(s for s in M['sources'] if s['name']=='tmux')
packages='\n'.join('| '+p['name']+' | `'+p['version']+'` | '+next(q['license'] for q in L['packages'] if q['name']==p['name'])+' |' for p in M['packages'])
sourcefiles='\n'.join('- `'+f['uri']+'` SHA256 `'+f['sha256']+'`' for f in source['files'])
handoff=f'''# #169 External tmux backend audit — HANDOFF

Status: LOCAL EXTERNAL AUDIT AND OWNED DETACHED LIFETIME VERIFIED. STOP.
Frozen Git: `5aab2346f2f4f4378ed1fe0570abb3be258a8fc7`.
Branch: `codex/0038-terminal-backend-audit`. No tracked edits, commits, pushes,
new manual worktrees, main reset, shared-file changes, or stage4836 changes.
All artifacts are ignored here or in new owned WSL storage `{R}` (0700).
Final runtime filesystem: `{F}`. Earlier failed fixture roots are retained,
with their own failed receipts. Their owned inactive sockets are now removed.

## Exact provenance and admission

Official Ubuntu amd64 tmux package `3.4-1ubuntu0.1` was available; no upgrade.
URI: `{tmux['uri']}`.
Package SHA256: `{tmux['package_sha256']}` (479838 bytes).
Executable SHA256: `034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd`.
Copyright SHA256: `{tmux['notice_sha256']}`.
Exact packaged manual gzip SHA256: `{V['manual_sha256']}`.
Full archive key fingerprint: `F6ECB3762474EDA9D21B7022871920D1991BC93C`.
Retained keyring SHA256: `{M['keyring_sha256']}`.

Five InRelease signatures (noble/current, updates/current, security/current,
updates/20260924T180000Z, security/20260924T180000Z) independently revalidated
with gpgv, exact full VALIDSIG fingerprint, exit0. Their SHA256-covered amd64
Packages.xz and Sources.xz were rehashed AND independently reparsed before
checking binary/source hashes. No filename guessing, unsigned origin admission,
global apt install/update, distro configuration, or weakened signature check.
The original installed tmux/copyright hashes match authenticated extracted
bytes, but runtime used privately extracted packages rather than installed tmux.

The current index no longer contained installed libevent
`2.1.12-stable-9ubuntu2.1` (current alternative `.2` recorded). The official
signed September24 snapshot supplied exact original package and source bytes.
`tmux-alternatives.json` retains base `3.4-1build1` and target metadata without
silently changing the candidate. Current releases and snapshot diagnostics are
independent; old snapshot is reproducibility evidence, not a security-update
recommendation.

Signed source bytes:
{sourcefiles}

The closure contains {len(M['packages'])} packages, {len(M['sources'])} source groups,
{sum(len(s['files']) for s in M['sources'])} source archive/signature/DSC files,
{len(M['paths'])} statically inspected reachable ELF files, and 44 retained
source LICENSE/COPYING/NOTICE texts. Runtime server/pane maps confirm admitted
ELF paths plus authenticated libc locale/cache data. Complete exact URI/hash/
architecture/source/notice graph is `audit-manifest.json`; dynamic graph is
readelf-derived without executing candidate bytes. Fixed fixture Python,
ctypes/libffi, reviewed terminal admission/hashlib/libcrypto, and utempter's
executing helper are included. No shell, vendor, SDK, systemd daemon, readline,
or other unrelated OS utility is executed by this fixture.

| External package | Exact version | Executing component license |
| --- | --- | --- |
{packages}

Tmux source/header and Debian notice licenses are ISC/BSD/MIT; packaged build
files retain their own permissive notices. External LGPL libraries AND the
utempter helper remain unmodified, dynamically linked and replaceable, outside
core/service Git admission. Complete corresponding upstream source plus Debian
patches/build files and full LGPL texts are retained externally. Keep all
copyright/license notices and source with any later distribution; allow LGPL
modification/relinking/reverse engineering. Dual-licensed library portions use
the permissive grant. GPL-only tools/build/tests elsewhere in source archives
are not executing; they remain intact, with notices, in retained source.
XZ's exact COPYING distinguishes public-domain liblzma from GPL scripts/build
files. No executing MPL component was identified. No LGPL/MPL obligation is
silently waived; this is not permission to embed these components into core.
See `license-admission.json`, `all-notices.txt`, and `{R}/notices`.

## Exact manual/source facts and fixed command sequence

Packaged 3.4 manual: `-D` runs server without daemonizing, turns exit-empty off,
and forbids command arguments. `-N` forbids clients from starting another server.
`-S` uses exactly the supplied socket. `-f` replaces ambient config selection.
Multiple shell-command arguments execute directly without `sh -c`.
`server.c`, `tmux.c`, `spawn.c`, `cfg.c`, `compat/systemd.c`, `window.c`, exact
Debian patches and utempter source were inspected and retained outside Git.
No guessed `tmux -D new-session ...` ordering is admitted.

Foreground server, AFTER owned pidfd/namespace gate release:
```
/usr/bin/tmux -S /run/fixture.sock -f /proof/tmux.conf -D
```
Then a separate metadata-only client:
```
/usr/bin/tmux -S /run/fixture.sock -f /proof/tmux.conf -N new-session -d -s fixture -x 80 -y 24 /usr/bin/python3.12 -I -S /proof/pane.py
```
Then display-message/list-clients/show-options (allowlisted formats only) and
kill-server. Every argv, metadata stdout and raw client exit is in
`receipt-native.json`; all six clients exit0. All client/server stdio endpoints
are synthetic/private or /dev/null, never human/source input. No attach,
capture-pane, pipe-pane, show-buffer, send-keys, transcript or raw terminal read.
Config disables history, prompt/message history, clipboard/passthrough,
automatic rename and inherited update-environment. No verbose/debug logging.
Candidate environment is only HOME/PATH/TERM/LANG/PYTHONDONTWRITEBYTECODE,
with fresh bare home and LANG=C.UTF-8.

Important staging integration facts:
- tmux does not establish this proof's echo-off policy automatically. The fixed
  synthetic pane child performs chmod0600 and termios ECHO/ECHONL disabling,
  then the exact reviewed helper SHA
  `c18a81701ce432cb93e1ac2243b31add34f3ec10944dc381b92ff8e1d0133b63`
  inspects/rechecks descriptors before release. Real staging must establish
  and verify the same private policy before any human/vendor input. This audit
  does not amend or approve stage_console's actual implementation.
- libutempter forks its fixed helper and updates utmp/wtmp. This fixture mounts
  private devpts, chroots to new package-only storage, supplies private
  /run/utmp and /var/log/wtmp, clears inherited descriptors, and sets
  no-new-privileges before any tmux release. Final private byte counts were
  384/768; no record contents were read or retained.
- libsystemd can consult socket activation/session bus and attempt transient
  cgroup operations. No LISTEN_*, NOTIFY_SOCKET, user bus or systemd manager
  exists in the bare environment/chroot. Failure there is contained locally,
  not real cgroup acceptance. No global filesystem path is reachable to tmux.
- Exact tmux exit does not unlink its filesystem socket. Fixture cleanup checks
  retained owned socket identity and terminal pidfds, then unlinks only that
  owned socket through its private directory descriptor. Real service runtime
  directory/socket cleanup must be separately verified.

## Genuine owned proof and raw outcomes

Final proof script SHA256: `{V['proof_script_sha256']}`.
Native invocation:
```
wsl -d Ubuntu -- python3 -I -S /mnt/c/Users/15492/.codex-clean/worktrees/13a1/QuantMesh/output/169-terminal-backend/proof.py
```
Raw exit0, total including cleanup {C['elapsed_seconds_including_cleanup']:.9f}s <90.
New user/net/private-mount/PID namespaces, mapped UID0 only to caller UID1000,
private new devpts, chroot, private utmp, bare home, no-new-privileges1, only lo
and no routes. Namespace identities differ from the controller; handles may
reuse kernel inode numbers after earlier namespaces cease, not evidence of
reusing a live namespace. Setup pidfd is retained before namespace setup;
namespace PID1 pidfd and all four namespace handles are transferred and
independently checked BEFORE candidate release. Server pidfd and namespace
handles precede exec. Pane pidfd/identity precede its synthetic lifetime gate.

The originating `new-session -d` client fully exits. No attached client remains.
Two separate metadata clients observe identical `{N['metadata_before']}`:
same server PID3, pane PID5, pane ID%0, private TTY, attached0/dead0. Both
pidfds remain alive between/after clients, with unchanged start ticks and
namespace identities. This proves detached creation/client termination
lifetime; no real interactive user attach/detach was performed.

Actual pane has one matching0600 TTY on descriptors0/1/2, correct mapped owner,
ECHO/ECHONL false, no-new-privileges1 and same namespaces as the owned server.
Six actual negative cases deny: wrong UID,0620 mode, echo enabled, /dev/null,
wrong output direction, different private PTY. Missing pidfd and substituted
namespace identity deny before signal/release. These two ownership negatives
exercise the local fixture admission predicate, not production stage logic.
Input/output bytes are both0; no actual synthetic input injection/echoed-byte
measurement, human terminal privacy, same-UID/root secrecy or vendor input is
claimed. That distinction is deliberate; terminal attrs are actual kernel facts.

kill-server client exit0; server exits0; pane terminates SIGHUP(-1), reaped by
owned PID1; same-namespace known sibling survives that individual stop and is
then killed/reaped through its own pidfd(-9). Outside known sibling also
survives namespace termination, then is owned-pidfd killed/reaped(-9).
Namespace PID1 is terminal and its parent setup is reaped. Independent checker
confirms both known host PIDs absent. Final socket absent. No bare PID/PGID
signal, borrowed process/socket targeting, live-process leftovers, or unknown
ownership cleanup PASS was used.

Failure evidence is preserved, never rewritten as PASS:
1. Exact installed libevent absent in current official index: acquisition exit1;
   signed official historical snapshot correction, exact version retained.
2. Shared Python copyright directory symlink: exit1; explicit authenticated
   referenced package notice used.
3. Empty-value Sources Checksum field parsing bug: exit1; parser handles `key:`.
4. Initial runtime exited before pane creation, exit1,0.029606758s. Exact tmux
   source requires UTF-8 locale; libc-bin locale data added as a signed/source/
   notice-audited data supplier. No unchanged retry. Raw startup stderr had been
   discarded, so locale cause is source-supported diagnosis, not observed stderr.
5. Next runtime proves detach/privacy/stop but socket-unlink expectation fails:
   exit1,0.677355792s. Foreground socket persists; revised identity-bound owned
   cleanup in a fresh v3 root. The preceding failed socket is separately cleaned
   by exact recorded inode/device/mode match; original receipt stays pending.
Final corrected native exit0,0.679402935s. Preflights (no candidate execution)
exit0. Final independent checker exit0,{V['count']} actual checks. Earlier first
checker219 included three one-time old-socket cleanup checks; final216 reparses
all signed indices and sees old socket already absent. No repeat runtime was
performed after final success. Scripts, acquisition/preparation/gpgv/native/
controller/negative/cleanup receipts and hashes are retained.

## Boundaries, roles and root continuation

Planner: unsupported SSH-client-lifetime requirement removed by actual bounded
foreground server and independently ending clients. No extra user action or
gateway operation added. Researcher: no datasets, strategy/model results,
supplier data or statistical claim. Implementer: only ignored audit/fixture
scripts, no maintained runtime/shared files. Reviewer/verifier: static exact
source/manual/closure/licensing inspection and independent signed/kernel/raw
receipt checks, no third old architecture review. Root owns tracked iteration,
ADR/REUSE/profile/unit/ACTIVE/locks and adoption/archival. No message was sent
to another chat and no completed agent was redispatched.

All source-host/private-input/authentication/SDK wire/installation/production/
market/PC-independence/real-systemd-cgroup qualification flags remain FALSE.
No AWS/SSH/systemd service/user/daemon/policy/global package install, vendor,
SDK, Windows/helper/tunnel, market/model/paid/API-key or production action.
No core/source embedding in Git. Operator/ClassC/CI/two-human/real host/private
interactive terminal/cgroup lifecycle/authenticated original SDK/source/calendar/
browser/rollback acceptance remains open. Root must independently verify hashes,
archive this evidence, and convey audited pins plus foreground ordering,
UTF-8 data, echo admission, helper side effects and socket cleanup to stage4836.
Do not treat this file as an installation, authentication or release permit.

Official trust references: [Ubuntu archive verification](https://documentation.ubuntu.com/security/software-integrity/archive-verification/),
[archive fingerprint](https://wiki.ubuntu.com/Security/FAQ),
[official snapshot semantics](https://snapshot.ubuntu.com/).
Full LGPL texts and exact source are retained; external licence decision is
recorded in `license-admission.json` for root's independent review.
'''
(O/'HANDOFF.md').write_text(handoff)
inventory=[]
for base in [R,O]:
    for p in sorted(base.rglob('*')):
        if p.is_file() and not p.is_symlink() and p.name not in ['SHA256SUMS.json','native-inventory.json']:
            inventory.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
(O/'SHA256SUMS.json').write_text(json.dumps(inventory,indent=2))
print(json.dumps({'status':'handoff-written','head':G['head']['stdout'].strip(),'tracked_clean':True,'inventory_regular_files':len(inventory),'handoff_sha256':sha(O/'HANDOFF.md')}))
