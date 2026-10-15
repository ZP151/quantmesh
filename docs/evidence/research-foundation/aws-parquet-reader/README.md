# Actual AWS canonical Parquet prerequisites — 2026-10-14

The existing private research Engine/image was reused; no production service or
Worker admission was activated. These observations use only fixed synthetic
canonical two-row data, not market records or user jobs.

- Schema observation: actual exit0,1155B/two rows/eight flat columns; Docker
  started01:35:26.451974258Z and finished01:35:29.440934071Z.
- Ordinary held-FD candidate: actual exit1 at02:08:05UTC. Diagnostic exit1 at
  02:14:25UTC proves DuckDB canonicalized the FD allowlist to an ordinary path.
  These failed raw receipts remain byte-exact; that route is not admitted.
- Replacement sealed anonymous data-file phase: actual exit0; Docker started
  02:23:51.757950093Z and finished02:23:54.879226758Z. All nine cases pass:
  original rows after path replacement, exact sealed read, ordinary/sibling
  refusals, nonempty write/shrink/grow/chmod-X EPERM, stable identity/hash/seals.
  MFD flags11, actual seals47, UID10001/mode0400/nlink0,5775B total fixtures.
- Each owned container was removed, noOOM/PID0, same Engine2images/0containers.
  Final original AWS introduced1,401,495,552B/free160,029,757,440B; baseline not reset.

The raw receipt50334ba2 and raw outputd1238efd were recovered through private
SSHexit0 and revalidated from actual serialized times/fields. SHA256.json pins
all stored bytes including the reviewed operator93da1b0e and child071fd24b.
The scoped source review found a transfer-pin P2; exact reviewed length/hash is
now checked before payload/SSH, with retained altered-source RED and GREEN4.

Full executable mmap/mprotect/seccomp/native-load closure, independent parent
binding, job-wide reader/physical-row admission and actual private jobs/reports
remain pending. MFD_NOEXEC_SEAL alone is not executable-mapping denial. Formal
168h is NOT_REQUIRED/on-demand. Paper stays enabled; live execution stays disabled.

Source behavior references: [DuckDB1.5.5 config](https://github.com/duckdb/duckdb/blob/v1.5.5/src/main/config.cpp#L753),
[local filesystem](https://github.com/duckdb/duckdb/blob/v1.5.5/src/common/local_file_system.cpp#L1342),
[Linux non-executable memfd](https://docs.kernel.org/userspace-api/mfd_noexec.html).
