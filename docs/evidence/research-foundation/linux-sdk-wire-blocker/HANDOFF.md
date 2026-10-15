# #169 Linux SDK wire verifier — BLOCKED

Verifier session worktree: `C:/Users/15492/.codex-clean/worktrees/69d3/QuantMesh`.
Branch: `codex/0038-linux-moomoo-wire`.
Exact baseline and unchanged HEAD: `9b72aa4bf324021b81ec76e071c07b3125e6ee47`.
Stop condition: accurate safe blocking diagnosis. No candidate commit, tracked
lock, merge, deployment, authentication, paid operation, or shared-file change.

## Decision and exact RED

Native CPython 3.12.3 x86_64 / UID1000 successfully imports the pinned
`moomoo_api==10.10.7008` in the SAME fresh user/net/mount/PID namespace as the
freshly extracted pinned vendor CLI. Official `is_async_connect=True` produces
`WAIT_RECONNECT` then `CONNECTED`. The call-profile observer sees exactly the
original SDK `pack_pb_req` call for InitConnect1001. For 25.007 seconds the
public SDK status never becomes READY and `get_sync_conn_id()` stays0.
`protocol_handshake=false`. A pack call is NOT proof of bytes successfully sent
or an acknowledged response. No server connection ID is fabricated.

Public `SDK.close()` is called; after the bounded3s close observation the SDK
status is still CLOSING, not CLOSED. Its nonterminal process is killed via its
owned pidfd, exit-9. Vendor exit-15; inner supervisor records only PID1 remains.
Controller exit0, namespace PID1 pidfd readable/terminal, known sibling survives
then its own pidfd cleanup exits-15. Whole final attempt81.355s, below90s.
The outer qualification command reports exit1 through wsl.exe; this is RED,
even though the namespace controller itself exits0.

The exact root cause of the missing InitConnect acknowledgement is unresolved.
These observations do not prove that login is required or that the SDK/vendor
versions are incompatible. Do not request credentials or advance installation
on this evidence. Root may separately check the official pre-login InitConnect
contract before designing a narrower next action. No SDK patch, raw-protocol
replacement, general probe, get_global_state, account, quote, history, trade,
unlock, entitlement or order request occurred.

## Dependency and license evidence (GREEN, separate from wire RED)

Official SDK registry: https://pypi.org/pypi/moomoo-api/10.10.7008/json.
This exact release has only an official sdist, not an official wheel.
Official source6435262bytes, SHA256
`2c721a9b8daeb141f77408300056a7b398ff252ac06d35bad6dd3b21489185c7`.
Source is now outside the repository at
`/var/tmp/quantmesh-sdk-wire-zz47gnjl/source-artifacts/moomoo_api-10.10.7008.tar.gz`.
Source is Apache-2.0, inspected setup.py uses setuptools/find_packages and
declares pandas/simplejson/protobuf>=3.20.0/PyCryptodome (selectors2 only Python2).

Locally derived, unmodified-source SDK wheel SHA256
`1b52a6f9ebe475c098765ee63e961fde1a73796c4febd4b2157b37b5a740e891`,
`moomoo_api-10.10.7008-py3-none-any.whl`. It is NOT a vendor-published wheel.
Build uses SOURCE_DATE_EPOCH1786612579, independently SHA/license-audited
setuptools80.9.0/wheel0.45.1/packaging26.3 in an owned buildenv, no build isolation
network. Existing reviewed bootstrap pip26.2.1 is reused read-only from
`/var/tmp/quantmesh-bootstrap-krfg8kx6/build-tools`; no existing environment changed.

Ten-package runtime closure: moomoo_api10.10.7008, numpy2.5.2, pandas2.3.3,
protobuf7.36.1, pycryptodome3.23.0, python-dateutil2.9.0.post0,
pytz2026.3.post1, simplejson4.1.2, six1.17.0, tzdata2026.3. Runtime dependency
versions match the current core pins; no SDK/dependency upgrade to bypass failure.
`runtime-wheel-audit.json` records every external wheel URL/version/hash/license,
platform filename, requirements and retained license/notice digests.
`sdk-wheel-audit.json` records official-source and derived-build provenance.
`build-wheel-audit.json` covers the separate build closure.
Notices are under `notices/`, never tracked/copied into runtime source.

Fresh owned SDK venv, no ambient pip/setuptools or external closure import.
`sdk-install.log/.exit`: require-hashes/no-index/wheelhouse install exit0.
`closure-check.log/.exit`: pip check exit0.
`closure-license.log/.exit`: unchanged repository license_review over exact
closure.txt,10 classified/0 unknown/0 outside closure, exit0. No license exception
or policy change. `candidate.lock` stays IGNORED, is only a local wheelhouse
install receipt, and is not deployment admission. The planned tracked
`deploy/aws/opend/requirements.sdk-linux-cp312.lock` was not created because
the real handshake and normal SDK close gates failed.

## Genuine connection-ID provenance

Inspect the exact official source under
`/var/tmp/quantmesh-sdk-wire-zz47gnjl/moomoo_api-10.10.7008`.
`evidence-check.json` binds relevant full-file hashes/functions/native paths.
In quote/quote_query.py: InitConnect.unpack_rsp reads `rsp_pb.s2c.connID`
(line274) after validating retType and s2c. In common/open_context_base.py:
_send_init_connect_sync (line437) queries InitConnect and calls
_handle_init_connect_rsp only after RET_OK; that assigns _opend_conn_id from
the response (line679), then sets ContextStatus.READY (line684).
get_sync_conn_id (line454) returns _opend_conn_id; public status (line122)
returns _status. _conn_id is a DIFFERENT NetManager-local identity assigned
at line428. Initial _opend_conn_id is0 (line70).

QuoteContext creates an empty SubRecord; on_api_socket_reconnected iterates
its empty list and sends no subscription request. No trade context is created.
The call-profile observer only examines the original pack_pb_req proto_id
argument; it never packs/unpacks/replaces any protocol or patches SDK methods.
Any non1001 call would be recorded as disallowed and terminated BEFORE packing.
Observed final list is [1001]. READY/nonzero server ID remains mandatory and RED.
SDK logs are suppressed through the original logger properties before context
creation. SDK stdout/stderr go to DEVNULL; vendor PTY bytes are counted/discarded
in bounded chunks, never decoded/persisted. No vendor XML/log/history/account
state is read. Newly generated vendor state is left untouched in the owned home.

## Vendor and containment inputs

Original vendor tar remains untouched at
`C:/Users/15492/.codex-clean/worktrees/acf3/QuantMesh/output/task2-opend-qualification/moomoo_OpenD_10.10.7008_Ubuntu18.04.tar.gz`.
Every attempt rechecks466932458bytes and SHA256
`72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa`.
Fresh extraction of pristine CLI subtree rejects non-file/directory types,
links and path escapes, under new owned native storage. CLI SHA256
`e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601`.
Owned noncredential XML bytes exactly match reviewed
`d6c9c112004bd0866dacc5d0e4fae4d715fcd6db250cd68cae859f787583bffb`.
Each attempt has a fresh0700home and user/net/private-mount/PID namespace.
Only lo exists in its /proc/net/dev, interface enabled privately. No host external
network interface exists there. Vendor binds127.0.0.1:11112; no_monitor1,
simulate_trade disable, auto_hold_quote_right0, console1, log_level no.
Bare explicit env HOME/PATH/LANG (vendor library path only); no inherited
account/key/proxy environment, no stdin bytes, no old vendor state.

Controller, namespace PID1 pidfds and all4 namespace FDs are acquired and
verified BEFORE release. Controller directly owns PID1; gate reports pid1 and
matching namespace identities, each different from the verifier host namespace.
Vendor/SDK each get their own pidfd. Termination uses signal.pidfd_send_signal,
never bare PID enumeration/signalling. Namespace teardown is confirmed by
PID1 pidfd; no partial global /proc scan is turned into a global absence claim.
An independent owned sibling remains outside and survives; it is then closed
only through its own pidfd. This proves containment for newly owned resources,
not existing Windows/AWS/old Linux resources or graceful vendor lifecycle.

## Attempts and verifier-tool limitations

Attempt1:17.244s, namespace gate passed, controller exit1 before vendor start;
PID1 terminal/sibling survival true. Attempt2:16.415s, captured AssertionError
at ns_supervisor.py26: inherited `/sys/class/net` was wrongly used as namespace
inventory. Final diagnostic proves inherited sysfs shows eth0+lo while namespace
`/proc/net/dev` shows lo only. Corrected the test-owned verifier, no shared code.
Both failed attempts are retained and never called handshake evidence.

Attempt3:82.392s, listener observed, synchronous SDK constructor does not return
within observation; SDK exit-9, vendor-15, PID1 terminal, sibling survival true.
No import/pack stage evidence was emitted in that attempt, so do not infer why
it blocked. Attempt4: official async option enables exact status/pack observation
above;81.355s, still RED. No attempt was a successful SDK qualification.

Initial metadata-audit helper failed TypeError(unhashable email Header) before
runtime execution; corrected it to decoded string metadata as importlib.metadata
uses. Final evidence helper initially assumed every sdk_version event had a
namespaces field and failed KeyError; corrected to explicitly require BOTH SDK
and vendor namespace events. These are local helper issues, not upstream faults.
Earlier helper errors are described here from tool transcript, not invented
machine logs. Final helper performs byte-for-byte installed wheel member checks
(excluding installer-regenerated RECORD and wheel .data relocation entries),
not a complete arbitrary-file admission scanner. No runtime success is inferred.

## Reproduction commands and final evidence

All scripts/receipts/notices are ignored under this HANDOFF directory. Owned
native root is `/var/tmp/quantmesh-sdk-wire-zz47gnjl`; final runtime root is
its `attempt4` child. This session's newly built SDK env is read-only reused
across fresh runtime namespaces via an owned symlink, not an old/borrowed SDK
installation. Run records bind the actual imported module to exact wheel bytes.

Commands run through:
`wsl.exe --exec /usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/python3.12 SCRIPT`.
prepare.py: final wrapper exit0; runtime-download/build-download exit0;
runtime9/build3 wheels audited. build_install.py: wrapper0 and build-install,
sdk-wheel-build,sdk-install,closure-check,closure-license all0. Native script
native_witness.py: four wrapper exit1/RED receipts in attemptN-native-witness.json.
DO NOT rerun it in place: it deliberately refuses an existing owned attempt root.

check_evidence.py: final expected RED,22/25 checks pass. Exactly3 failed checks:
SDK normal exit, public SDK close reaches CLOSED, original READY/positive server
connection ID. This is not25 green tests. Final fresh native checker exit is
recorded separately in evidence-check-native.exit; wrapper output is saved.
Installed immutable wheel bytes and all10 wheel SHAs match; source provenance
and imported SDK bytes match. Native/wire/raw account output is not in files.
Final git status/diff checks confirm no tracked changes and shared profile bytes
unchanged. SHA256.json inventories these external evidence files.

Root retains ownership of REUSE/ACTIVE/iteration/profile/README/SDK transport
and all operational gates. Wire flag, quote/history rights, private human input,
actual AWS installation/auth/source/cutover/PC independence remain false/pending.
This verifier stops; no other completed session was redispatched.
