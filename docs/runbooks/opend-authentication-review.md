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

1. Qualify operator input/lifecycle on a new owned native synthetic fixture.
   Prove private terminal ownership/mode, echo suppression, no transcript or
   journal capture, no assistant-readable credential relay, and process/TTY
   closure after operator disconnect and failed initialization. A sensitive
   marker stays within the fixture and is never archived. Preserve timeout,
   cleanup, sibling and negative permission/identity receipts. Current
   `/run/quantmesh-opend/operator-tty` is a proposal, not a qualified device.
2. Implement only the bounded staging/qualification phase needed to avoid the
   current admission cycle: the production unit correctly refuses startup until
   wire/private-input/auth are qualified. A separately reviewed one-shot staged
   launch must therefore have its own explicit authority and expiry; it cannot
   set those flags merely to bypass the production guard. No current script is
   authorized to bypass it. Keep implementation scope independent from market
   collection, core settings and trading.
3. Present the exact reviewed/merged staging script, SDK closure hashes,
   terminal proof, host identity, process owner, deadline and rollback packet.
   Complete ClassC CI and two human reviews including the safety owner before
   host installation. Obtain the operator's explicit authentication window.
   Notify of new-device verification and possible quote-authority transfer.
   Do not request an account password or verification code in chat.
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

No new operator action is requested yet: steps1–3 must produce concrete reviewable
artifacts first. Independent backup work continues. Native Linux Worker Engine
and model metadata/API-key prerequisites remain separate from this source path.
