# Linux dependency and scripted service qualification

Source: `9d5b3fab3bda0182663b1494865db298d6f3685f`, clean detached native Linux
filesystem checkout. CPython3.12.3/x86_64, separate81-wheel lock
`07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a`.
Every shared dependency version and the original77-package Windows lock remain
unchanged. Installer reports use actual public-registry wheel SHA256 values;
license inventory81 has no unknown licenses. Actual source imports in
`native-imports.log` bind the native checkout, rather than an editable parent.

Native runtime matrix:8 passed. Native offline service:25 passed/5 actual-PG
skips,11.08s, exit0. Native default gate:25 passed/5 skips,10.14s, exit1; its
only failure is missing real owned disposable PostgreSQL evidence. Fresh final
Windows gate also passes25/5skip, exit0 on the unchanged77-package environment.
Frozen schema/protocol digests match both platforms. Raw command logs, JUnit,
installed-wheel receipts, inventories and their byte hashes are archived here.

First attempts remain visible. The mounted-drive run failed pytest capture and
Windows Git pointer lookup; correction reached17 tests but expired at the
owned300-second driver limit. The first native-filesystem run passed, but its
`/tmp` directory disappeared before a later import-inspection invocation.
`native-imports.json` retains that inspection's raw stderr (despite its `.json`
suffix; it is not a valid qualification JSON). The subsequent persistent
`/var/tmp` run repeats the unchanged frozen version, checks imports and copies
raw receipts into this archive before exiting. Use `native-imports.log/.exit`
for the successful actual-import proof; retain the failed raw bytes separately.

These results qualify dependencies and offline scripted service boundaries.
They do not certify OCI/image/process-tree limits, Linux Worker recovery, real
PostgreSQL/model calls, production deployment, source independence or the
whole research foundation. Default native/DB release gates are not waived.
