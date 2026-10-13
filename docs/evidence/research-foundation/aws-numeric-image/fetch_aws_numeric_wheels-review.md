# Bounded pre-execution wheel-intake review

Actual reviewed SHA256:

- `output/fetch_aws_numeric_wheels.py`: `FD726BF77B924D0D23169EDC9BFA71D81A8BE2FE27595754D55762885BBA7994`.
- `output/launch_aws_numeric_wheels.py`: `59C829598AF320D16741D876EEEA9D79E43F91079F54F4C3209E0AA572E4628F`.

## Findings

1. **P2 — Validate and bound parent input reads through one descriptor** (`fetch_aws_numeric_wheels.py:55–56,95–97`). The stat checks omit regular-file type and link count, and `read_bytes()` opens the path separately without a strict read limit or descriptor/named-file identity checks. An owned FIFO at the canonical ownership path has size zero, passes this preflight, and blocks the parent before the downloader fork/watchdog exists. A replaced or growing file can also invalidate the pre-read size check. Use the previously reviewed bounded regular-file reader for ownership and worker receipts: canonical/no-links, UID/nlink/type/size before reading, strict byte count, same fd before/after plus named identity, then parse those bytes.

2. **P2 — Handle a phase created before wheelhouse creation succeeds** (`fetch_aws_numeric_wheels.py:82,118–123`). `created=True` is set immediately after creating PHASE. If the following wheelhouse mkdir fails, or creation is interrupted between these steps, the final unconditional `wheelhouse.iterdir()` raises and prevents the failure receipt/output. Track successful wheelhouse creation and condition retained-byte accounting on it; preserve a truthful failed outcome even when only the phase directory exists.

No additional substantive P1/P2 found in the fixed public URL constraints, proxy/redirect rejection, pinned metadata/lock matching, exact 81-file/byte-total validation, bounded per-file download/hash checks, or cleanup of the captured sole unreaped child. The launcher has no install/unzip/Docker command. These observations do not close the two findings above.

## Limits

Static read-only review of the two supplied exact versions only. No remote command, HTTP/download, tests, wheel installation, Docker mutation or native/runtime execution was performed. Both recipes were unexecuted at review. This is not an image, runtime, numerical/native or Option A certificate.

## Two-finding correction closeout

Actual corrected fetch source SHA256: `3F8C7EAC66D482B0CE5EC2B2089435BF2A1119EF10A3588B3EF3372F20F7B06F`.

Clear within the requested corrections: both original P2 findings are closed; no new substantive P1/P2 found in these changed boundaries. Ownership and worker receipts now use `read_owned`: canonical paths without links, O_NOFOLLOW/O_NONBLOCK, regular-file/UID/nlink/size validation before reading, limit+1 bounded read, and same descriptor/named identity validation before parsing those bytes. FIFO input is refused before read. `wheelhouse_ready` becomes true only after successful owned-directory validation; final accounting avoids enumerating a wheelhouse whose creation failed, allowing the original failed outcome and receipt to survive that window.

This addendum is a static recheck only. Root reported preparing small FIFO and injected-mkdir counterexamples; their outcomes were not yet inspected for this disposition and are not claimed as passed here. No execution, download, broad testing or architecture re-review was performed. The launcher was not modified or newly reviewed in this closeout. Native/image/runtime certification remains outside scope.
