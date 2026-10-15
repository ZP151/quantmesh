# Native SDK boundary diagnosis — negative wire evidence

Issue#169, iteration0038; root baseline866e016. These are diagnostic receipts,
not production/source-host qualification. All authentication, market, trading,
external network and shared deployment-profile operations remain absent.

Fresh attempts6/7 reuse the previously audited SDK10.10.7008 environment
read-only; each freshly extracts the pinned proprietary OpenD artifact and has
a new0700home plus user/network/mount/PID namespaces. Only loopback is enabled.
The original SDK is unchanged. A read-only Python profile observer records
numeric return codes/byte counts and SDK function/line stacks; it archives no
protocol bodies, response objects, account IDs, AES material or vendor output.

Both attempts record original pack ret0, original socket send84bytes/ret0,
no observed SDK receive callback/init-response handler, and init-query ret-1.
The25-second observation remains CONNECTED/serverID0/protocol_handshake=false;
public close remains CLOSING. This establishes that packaging/socket-send
occurred; it does not establish that the vendor consumed the bytes or why it
did not deliver a response to the observed SDK callback. A successful write is
not acknowledged initialization.

Attempt6 uses console1; attempt7 changes only that vendor argument to console0.
Their supervisor scripts differ only in this argument. Offline background mode
does not resolve the observed failure. Elapsed81.083/82.125seconds stays below
90seconds; owned namespace PID1 is terminal, new SDK/vendor exit-9/-15 and the
known sibling survives before its own cleanup. Neither SDK exits normally.
Native verifier exits2 for both. `checked-summary.json` certifies receipt
consistency while explicitly retaining wire_qualified=false.

Attempt5 is diagnostic-invalid: a Windows-to-WSL path substitution missed the
`/mnt/c` prefix and selected the old observer. The raw failed run is preserved;
the mutable old native receipt was restored byte-for-byte from the existing
tracked attempt4 archive. This verifier mistake is not a vendor fault and is
not used to support the new boundary conclusion. No old process was restarted.

The official [initialization contract](https://openapi.moomoo.com/moomoo-api-doc/en/ftapi/init.html)
identifies connID as a successful initialization response field. The official
[command-line guide](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html)
documents interactive login from10.10 and both console modes. These inspected
statements do not establish whether this isolated pre-login/offline gateway must
respond. Login-required, Internet-required and version incompatibility remain
unproven. Stop further unchanged anonymous retries; prepare a concrete private
operator-start/login/initialization review packet without promoting flags.

`sha256.json` binds19 raw files copied unchanged from ignored root output.
The scripts are retained diagnostic harnesses, not installers or a replacement
SDK. Vendor binary/source/dependency notices remain in their audited external
locations. The recorded ignored paths are historical; never rerun these scripts
in place or use them to authorize production install, authentication or cutover.
