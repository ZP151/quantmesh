# Linux SDK audit GREEN, anonymous offline wire RED

Exact unchanged verifier baseline9b72aa4; managed69d3 has stopped/idle with no
tracked lock or commit. Thirty selected raw files match the original123-file
inventory. SDK/source/build wheels, all retained licence notices and verifier
scripts remain in its ignored output/native owned root, not embedded here.
The official SDK10.10.7008 has only an sdist: its locally derived wheel is
unmodified-source build output, not a vendor-published wheel. Full10-package
SHA/license/import audit and require-hashes installation pass independently.

The final fresh local user/network/mount/PID namespace sends zero login input,
has loopback only/no internet and no personal vendor state. Official SDK sends
the original InitConnect1001 pack call; CONNECTED does not progress to READY
for25.007s, server connection ID stays0. A pack call alone does not prove actual
send or acknowledged response. protocol_handshake=false, outer native exit1.
SDK.close stays CLOSING after3s. Own pidfd cleanup terminates SDKexit-9,
vendorexit-15, namespacePID1terminal and sibling survives; total81.355s<90s.
The controller's exit0 is not a wire PASS. Final evidence checker22/25checks
has exactly3failed handshake/normal-close/normal-SDK-exit checks, not25green.

Actual source provenance distinguishes server-minted _opend_conn_id from the
NetManager-local _conn_id; no raw protocol rewrite or upstream method patch.
Only1001 is observed, no general probe/account/quote/history/trade/auth/order
call, raw SDK/vendor output, source/Windows/AWS or paid operation. Profile flags
are unchanged and no host/auth/source/PC independence is qualified.

Cause remains unresolved: these offline pre-login observations establish
neither mandatory login nor incompatible SDK/vendor versions. Inspect the
documented initialization contract and this setup before designing another
controlled observation; do not request credentials or advance installation
merely because this handshake failed. The failed earlier attempts remain RED.
