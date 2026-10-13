# Server OpenD initialization: operator review packet

Issue#169 / iteration0038. Status: preparation only; **not approved for install,
login, service start or cutover**. Existing gateway profile flags remain false.
This packet removes an unsupported sequencing assumption, not a safety gate.

## Decision and evidence

The native offline/pre-login SDK audit passes package/import/license checks.
The original SDK sends its84-byte InitConnect request; attempts6/7 observe no
SDK receive callback/READY/serverID, and console0 does not change that result.
See [negative diagnostic](../evidence/research-foundation/sdk-boundary-diagnostic/README.md).
The official guide documents interactive CLI login from10.10. It does not
promise anonymous offline initialization. Do not require an unproven anonymous
ACK as a prerequisite to preparing the human-operated channel, or claim that
login will certainly resolve the missing ACK. Actual acknowledged SDK transport
remains mandatory before any market acceptance or production promotion.

## Concrete proposed target

- Existing private source host: `quantmesh-staging-8gb` in the Singapore region,
  operator SSH over its tailnet identity. No new resource, public port or charge
  is requested by this packet. The latest recorded resource intake is Oct12
  21:31UTC, not a capacity certificate.
- Proposed dedicated OS identity/home: `quantmesh-opend`,
  `/var/lib/quantmesh-opend`; installation `/opt/quantmesh/opend/10.10.7008/OpenD`,
  protected noncredential configuration `/etc/quantmesh/opend/OpenD.xml`.
- Official vendor artifact466932458bytes/SHA
  `72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa`;
  executable SHA `e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601`;
  configuration SHA `d6c9c112004bd0866dacc5d0e4fae4d715fcd6db250cd68cae859f787583bffb`.
- Candidate API only `127.0.0.1:11112`. Retain11111 and the Windows GUI/state
  without stopping or copying them. Application build69515b7 remains unchanged,
  paper=true/live=false; initial qualification makes no application switch.
- Proposed vendor launch options remain cfg_file pinned to the protected path,
  api_ip127.0.0.1, api_port11112, auto_hold_quote_right0, no_monitor1,
  simulate_trade disable, console1 and log_level no. No login arguments,
  remembered password, AutoLogin, trade context or unlock.

## Required staged sequence

### Current prerequisite evidence

The local private-terminal qualifier is integrated and accepted within its
synthetic scope. The four-file disarmed staging candidateb623a568 integrates
through7641eda/f82d5ee, with both review axes closed at round2. Root fresh
native83/zero skips and Windows52/31 native skips pass; original production
profile/unit/validator/private helper remain unchanged. See
[staging software receipts](../evidence/research-foundation/staging-window/README.md).

The separate signed Ubuntu tmux3.4-1ubuntu0.1 audit covers20 packages/17 sources/
27 executing ELF and locale data. Root independent216 checks and the owned
0.679403-second detached-creation-client proof pass. This is not an interactive
SSH detach, source-host systemd or stage-template execution witness. See
[backend audit](../evidence/research-foundation/terminal-backend/README.md).
The exact older signed dependency snapshot is reproducible, but production
security/current target closure admission remains open; no silent upgrade or
dependency permission broadening is authorized.

Exact staging launcher SHA256:
`2aabead42bb8211da1a7e9fa81b8f06e48b9b655e1651f992edcfdfa5be6eef4`.
Stage template SHA256:
`e108294e59e624d17b0f75034930c9ae3fe1f3d3353c44a90586069e1e0cfdac`.
Audited tmux package SHA256:
`2913e17aa61879d1f905aab6f374f153f1ece63aefba1b996e387325d1d5338d`;
executable SHA256:
`034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd`.
These are software/audit pins, not an operator window or host permit.

### Sequence and remaining live release gates

1. Local synthetic input/lifecycle prerequisite is accepted in the archived
   private-terminal and staging proofs; do not rerun completed fixtures.
   Actual host acceptance must verify private terminal ownership/mode, echo
   suppression, no transcript/journal capture or assistant credential relay,
   and closure after owned terminal HUP, expiry and failed initialization. The
   server-owned pane must survive loss of a mere SSH attach client; actual
   host/client-loss and descendant cleanup require separate observation. A sensitive
   marker stays within the fixture and is never archived. Preserve timeout,
   cleanup, sibling and negative permission/identity receipts. The actual nonce
   runtime/pane device has not been created or qualified on the source host.
2. The bounded staging/qualification software is integrated to avoid the
   current admission cycle: the production unit correctly refuses startup until
   wire/private-input/auth are qualified. A separately reviewed one-shot staged
   launch must therefore have its own explicit authority and expiry; it cannot
   set those flags merely to bypass the production guard. The integrated staging
   software is still disarmed; no live invocation is authorized yet. Keep scope
   independent from market
   collection, core settings and trading.
3. Present the exact reviewed/merged staging script, SDK closure hashes,
   terminal proof, host identity, process owner, deadline and rollback packet.
   Complete ClassC CI and two human reviews including the safety owner before
   host installation. Obtain the operator's explicit authentication window.
   Notify of new-device verification and possible quote-authority transfer.
   Do not request an account password or verification code in chat.
   Admit the actual target package/OS closure and fixed UID/GID, protected tree
   and complete-file machine hash convention. Test manager/pane ownership,
   descendants, detach/expiry/HUP and runtime socket cleanup using only newly
   owned synthetic resources before vendor input. libutempter must not write
   global utmp/wtmp, and libsystemd bus/cgroup effects must respect the exact
   unit boundary. Do not add writable global paths to force acceptance.
   A surviving socket is removed only after its owned backend is terminal and
   its recorded inode/device/owner still match. Unknown authority stops here.
4. The operator opens their own private SSH terminal and enters login only in
   the vendor interface. The assistant does not read that terminal, capture its
   output, receive inputs or save state/logs. Do not select remembering. Pause
   after human confirmation; if login or authority transfer fails, stop staging
   and retain the previous application route. Unexpected fees require separate
   operator approval; this packet authorizes none.
5. With confirmed operator login, run the original separately audited SDK
   InitConnect and require actual READY/server-produced connection identity and
   normal close, with verified source-host process/endpoint ownership. This
   may still fail; retain an accurate typed failure and diagnose directly.
   Only then perform the reviewed AAPL/NVDA quote/minute observer, calendar-aware
   session checks, provider-bracket OHLCV and browser paper-refusal acceptance.
6. After actual lifecycle/private-input/SDK/source proof and approved switch,
   the coordinator may record qualification markers and use the merged guarded
   production unit. Do not alter source flags, install the unit, restart the
   application or promise PC independence from preparation evidence.

## Stop and rollback limits

Any identity, hash, permission, terminal privacy, lifecycle or source uncertainty
stops the staged path. Stop only a newly owned staged process through verified
handles; no borrowed Windows/SSH/vendor process is stopped. No credential/state
backup, profile boolean fabrication, public remote desktop, provider order or
automatic GUI/latest-version fallback. A failed staged test is not permission to
restart the old collector. Vendor reauthentication after host/process restart
remains human work and operational recovery remains separately unaccepted.

No new login/operator action is requested yet: software/local prerequisites
are accepted, but ClassC CI/human/merged release and actual host prerequisites
must pass first. Owned local backup qualification is complete only for fixture
   reports; actual off-host/Worker-generated recovery remains open. Native Linux
   Worker Engine
and model metadata/API-key prerequisites remain separate from this source path.
