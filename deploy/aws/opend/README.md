# Fixed OpenD candidate: qualification only

Issue [#169](https://github.com/ZP151/quantmesh/issues/169), iteration 0038,
server-market-independence Task 2. **Blocked for installation, authentication
and cutover.** These are noncredential templates; no service has been installed
on AWS and no production endpoint has changed. Task 1 remains at `3f4863e`.

## Exact artifact and observed platform

| Item | Actual evidence, 2026-10-12 UTC |
| --- | --- |
| Official fixed URL | <https://softwaredownload.moomoo.com/moomoo_OpenD_10.10.7008_Ubuntu18.04.tar.gz> |
| Version / advertised target | `10.10.7008` / Ubuntu 18.04 |
| Download size | `466932458` bytes |
| SHA256, calculated from downloaded bytes | `72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa` |
| CLI executable SHA256 | `e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601` |
| Executable inspection | ELF 64-bit x86-64, dynamic interpreter `/lib64/ld-linux-x86-64.so.2` |
| Archive contents | CLI `OpenD` with bundled libraries/resources; separate GUI AppImage |
| Local qualification host | Ubuntu 24.04.3 WSL, x86_64; not the AWS host |
| Installed research SDK inspected | `moomoo-api==10.10.7008` on Windows |

The [vendor's download convention](https://github.com/MoomooOpen/moomoo-agent-hub/blob/main/Moomoo%20API%20Skills/install-moomoo-opend/SKILL.md)
uses the official softwaredownload host. The observed official Futu Ubuntu
redirect supplies the `Ubuntu18.04` suffix; the fixed Moomoo URL above returned
HTTP 200 and its archive actually contains the named version. The generic
`Ubuntu.tar.gz` suffix returned 404; the Moomoo discovery endpoint redirected
to its 403 page. No mutable discovery URL is admitted in the profile.
The pristine archive's top-level README explicitly offers CLI execution for
long-running server use and lists CentOS 7 or newer for CLI, Ubuntu 18.04 or
newer for GUI. This is package guidance, not an actual AWS compatibility witness.
The digest is our reproducible byte pin, not a vendor signature or published
vendor checksum. If the fixed URL later changes bytes, stop qualification.

Later local observation2026-10-12T21:41:06Z freshly extracts the same verified
archive on native owned storage and observes30seconds in user/network/mount/
PID namespaces with loopback only. Login/account keywords and11112 listener
are observed with zero input; terminal echo is off. No credential, SDK or
market query is sent. The test-owned parent exits-9 after bounded cleanup;
later /proc scan is partial because2same-UID processes are inaccessible.
See [raw bounded observation](../../../docs/evidence/research-foundation/opend-zero-input/README.md).
This closes neither SDK/private human input nor actual AWS/lifecycle proof;
the profile stays blocked/uninstalled and no vendor state/output is archived.

## SDK and startup limits

[Official version history](https://www.moomoo.com/download/OpenAPI) states that
SDK 10.10.7008 requires OpenD at least 10.10.7008. The installed SDK exposes
`subscribe`, `get_stock_quote`, `get_rt_ticker`, `get_cur_kline` and
`request_history_kline`. This verifies the documented version floor and method
surface; it does **not** prove Linux SDK wire/quote compatibility. No SDK upgrade
or repository dependency change was made. Local WSL has no installed SDK/pip;
venv creation refused because ensurepip is absent. No system package was installed.

Only pristine downloaded CLI resources were extracted after checking member
paths/types; no personal OpenD XML, credentials, Device.dat, token or logs were
read or copied. Execution used a fresh home, user/network/private-mount
namespaces and zero credentials/input. Initial help reported an app-directory
permission error despite exit 0. With an isolated native home mounted at `/root`,
help recognized the documented flags and exited 27; that is diagnostic execution,
not successful gateway startup. A separate five-second PTY sample, with loopback
11112 and auto-grab disabled, was terminated as a test-owned process group;
no login prompt, API listener or SDK handshake was proved. Offline network
isolation limits what this sample can establish. No raw startup output was archived.

`systemd-analyze verify` in local WSL reported the uninstalled executable path
(and Windows-mounted file permission warnings). No service was enabled or run.
Treat grammar/policy tests separately from startup on the actual host.

## Private human authentication candidate

[Official command-line documentation](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html)
documents Linux execution and interactive login from version 10.10. The vendor
installer skill instead mandates GUI and automatic latest upgrades. We did not
execute it. The package contains both variants; the tracked plan authorizes
qualifying the CLI. CLI authentication remains a candidate, with
`private_input_verified=false`, until private input and lifecycle are demonstrated.

After the coordinator presents and obtains the required authentication window:

1. Verify the artifact/executable hashes and Linux loader on the proposed host.
   Use a dedicated `quantmesh-opend` OS user with passwd home
   `/var/lib/quantmesh-opend`, root-owned installation/config/profile, and 0700
   state/runtime directories. Do not inherit Windows state or the application
   user's vendor home. Protect the profile and qualification marker from that user.
2. Qualify a **human-operated private SSH terminal** on the existing tailnet.
   The candidate PTY must be owned/access-controlled for the dedicated user,
   accessible only through the approved operator session, with no session
   recording, shell tracing or transcript capture. Test terminal echo/privacy
   before entering any account or password. Do not put credentials in commands,
   environment, XML, this profile, screenshots, assistant tools or journals.
3. The human enters account/password/verification only into the vendor's private
   interface. Notify beforehand about new-device verification and possible quote
   authority transfer. Do not select password remembering, enable AutoLogin or
   auto-grab rights. If CLI input/lifecycle cannot be qualified, stop; separately
   qualify the same pinned GUI AppImage using private operator access.
4. Authenticate only during that window, then prove the exact pinned SDK's
   quote-only handshake and AAPL/NVDA subscribed quote/history/minute contracts.
   Account/order queries and trade unlock remain prohibited. Follow Task 3 for
   real open-session advancement, two minute boundaries and provider OHLCV.
5. Only the coordinator can record actual proof, approve the profile/marker and
   installation. Current `--require-qualified` exits 1 and prevents service start.
   A boolean edited without observed evidence is not qualification.

The unit's private terminal is `/run/quantmesh-opend/operator-tty`; connecting it
and proving safe device permissions are unresolved. Input/output go to that
terminal, not journald. There is no automatic login/restart in this candidate;
human re-authentication is required after a process/host restart. Its real
operational recovery behavior is therefore unaccepted. ProtectHome hides
personal homes; only the dedicated state/runtime directories are writable.

`validate_profile.py --print-config` emits a QuantMesh-owned, fixed noncredential
XML template; it never reads or copies vendor state. Its exact SHA256 is
`d6c9c112004bd0866dacc5d0e4fae4d715fcd6db250cd68cae859f787583bffb`.
Startup admission checks the bytes at the profile's `/etc/quantmesh/opend/OpenD.xml`
against this pin as well as the executable pin. Added login fields, AutoLogin/
remember settings, WebSocket/Telnet ports or any other XML drift refuse startup.
No generated configuration has been installed on the source host. The template
and its digest are our own reproducible policy bytes, not a vendor signature.

## Safety, fees, ownership and rollback

The candidate API is `127.0.0.1:11112`, separate from the preserved 11111
Windows route. WebSocket/Telnet listeners are not enabled. Template argv disables
auto-grab, the vendor monitor and simulated trading. `trade_enabled=false` is
QuantMesh policy, **not** a vendor switch that removes every trading protocol;
only quote contexts are permitted, no trade unlock occurs, and workstation
paper=true/live=false remains required. A credential-free XML must explicitly
set loopback11112 and auto_hold_quote_right=0, matching the unit overrides.
No such configuration has been installed on a real host.

[Official market-rights FAQ](https://openapi.moomoo.com/moomoo-api-doc/en/qa/opend.html)
describes competition between simultaneous terminals and no official Docker image.
Logging in can affect rights even when automatic re-acquisition is disabled;
do not test this against the current Windows source without the operator window.

This work created no paid resource, purchase, paid API call or vendor login.
The proposal initially reuses the existing private AWS host; its spare capacity
and any required quote entitlement remain unqualified. Additional entitlement,
GUI hosting or a Windows cloud fallback must be separately priced and approved
under Option A's budget. No zero-cost entitlement or new-host price is promised.

Until Task 3 acceptance, keep the app on the existing 11111 route. Rollback is
to leave that reviewed endpoint/configuration unchanged and stop **only** a
future newly owned 11112 candidate after the coordinator approves its impact.
Never stop the original GUI/helper/tunnel or manufacture a personal-PC outage.
Do not remove vendor state as a rollback tactic. No personal-PC independence
or production recovery is claimed by these files.

OpenD and its bundled native libraries are vendor-distributed software; the
selected archive member list contains no LICENSE/NOTICE file. Do not commit or
redistribute the archive, binaries or vendor resources. Vendor terms and bundled
notices need review before distribution. The existing Python SDK is Apache-2.0
under its admitted dependency boundary. Only QuantMesh-owned templates/validator
and tests are committed; no third-party source is copied.

## Reviewable policy checks

```powershell
python -m pytest tests/test_server_opend_profile.py -q --basetemp output/pytest-task2
python deploy/aws/opend/validate_profile.py --profile deploy/aws/opend/gateway-profile.json
# Expected exit 1: blocked, NOT approved for installation/start.
python deploy/aws/opend/validate_profile.py --profile deploy/aws/opend/gateway-profile.json --require-qualified
```

Planner: one fixed package/profile and private authentication handoff; no install,
cutover or trading. Researcher: compatibility/readiness is separate from session
coverage and market authority. Implementer: exact noncredential profile, gated
dedicated unit and fail-closed validator. Verifier: initial RED 21 missing-boundary
failures; GREEN 21 policy cases. Independent review and final checks are recorded
in the coordinator handoff; root mirrors this checkpoint into iteration 0038.
The one bounded review found missing configuration-byte binding; its RED
6 failures/21 passes became GREEN 27 passes after requiring the actual reviewed
configuration at qualified startup. No second structural review or new source
installation was performed. Broad product certification belongs to root's
combined integration HEAD; no old full-suite certification was repeated here.
