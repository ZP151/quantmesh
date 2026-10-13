# Bounded missing-notice intake review

Actual reviewed SHA256: `F127B4504CA6E07FAB4162EAB5645D78CF9C5B3229E4F675C848F409264EED50` (`output/fetch_aws_missing_wheel_notices.py`).

Disposition: clear within this data-only operator recipe; no substantive P1/P2 found in the reviewed bounds, ownership, child cleanup or stated source provenance.

The recipe binds the existing metadata hash and both frozen wheel hashes/versions before creating a fresh owned phase. Host inputs use canonical/no-link, nonblocking regular-file descriptors with UID/nlink/size checks, bounded reads and descriptor/named identity validation. HTTPS requests disable proxy/redirect handling and reject credentials, query/fragment and unexpected hosts/ports. Downloads are limited to the fixed commit LICENSE (16 KiB), release metadata (128 KiB) and fixed-digest sdist (64 KiB). The sdist descriptor, size and actual bytes/hash are checked before TAR reading. Only one exact named regular non-link notice member is read, with its declared size and a 16 KiB body limit; no archive code is extracted or executed.

The parent applies the original Phase1 storage ledger/floor and 90-second leaf-child watchdog; cleanup uses pidfd or the unreaped direct-child fallback, bounds reap to five seconds and preserves NOT_PROVEN if not reaped. Existing partial files remain on failure; no retry, install, wheel change or Docker command appears.

Provenance is accurately limited: langsmith uses the fixed publisher commit supplied by the earlier primary-attestation intake, not a verification of that attestation inside this recipe. pyluach uses the exact pinned PyPI same-version sdist. The resulting notice hashes preserve the actual downloaded bodies; the text predicate does not establish legal-expression correctness or source-to-wheel equivalence, and both claims remain explicitly false.

Static read-only source review only. No download, remote command, tests, extraction execution, install, image mutation or native/runtime probe was performed. The recipe was unexecuted. This review does not establish complete license/native/ELF closure, numerical admission or Option A completion, and does not waive the original full-notice gate or change any wheel pin.
