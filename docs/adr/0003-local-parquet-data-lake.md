# ADR-0003: Local Parquet Data Lake

- Status: accepted
- Date: 2026-08-07

## Context

M3 builds a local-first research pipeline: providers fetch market data,
scheduled ingestion writes it, quality checks validate it, and experiments
reproduce from it. Every stage needs one deterministic, versionable store
with a stable on-disk contract — no server, no credentials, no vendor lock-in.
The canonical `Bar` schema (ADR-0001 era; extended in issue #14) must round-trip
losslessly, including the timezone of every timestamp.

## Decision

- The lake is a directory of Parquet files under a configurable root,
  defaulting to `~/.quantmesh/data` (overridable via `QUANTMESH_LAKE_ROOT`
  or `Settings.lake_root`).
- Canonical partition layout, relative to the root:

  ```
  <dataset>/<interval>/<venue>/<symbol>/<date>/shard-0000.parquet
  ```

  `<date>` is the UTC date of the observation; `interval` and `symbol` use
  their canonical string forms. One shard file per
  (dataset, interval, venue, symbol, date). Writing a day's bars again
  replaces that day's shard wholesale; other days are never touched.
- Shard files carry `timestamp, open, high, low, close, volume,
  instrument_type, currency` — the `instrument_type`/`currency` columns
  restore the full canonical `Instrument` on read, since the partition path
  only encodes venue and symbol.
- Timestamps are normalized to UTC on write and read back as
  timezone-aware UTC, so identical input produces byte-identical files
  (deterministic re-ingestion) and comparisons never depend on host
  timezone. DuckDB returns instants in the local zone; the lake normalizes
  them back to UTC on read.
- Reads return bars in stored (file) order — never silently sorted — so the
  quality checks can see disorder, and consumers order explicitly.
- The I/O surface is DuckDB over the pandas DataFrame bridge. pandas is
  already a main dependency; pyarrow is deliberately **not** added. Every
  write or read uses a fresh short-lived connection; the lake is files, not
  a database, so concurrent readers and restarts are always safe.
- `Lake.quality()` runs the issue #14 primitives over a stored series:
  `monotonic_violations` on stored order, `find_duplicates` keyed by
  timestamp, and `find_gaps` on the sorted unique timestamps (so duplicate
  rows are reported, not fatal). Misaligned series fail closed.
- A dataset becomes queryable-by-experiments only after it passes quality
  and carries a manifest (issue #16). Quality checks are the gate, not the
  default assumption.
- Manifests are versioned JSON at `<dataset>/manifest.json` (issue #16):
  `schema_version` (currently 1), source, timezone (must be `UTC` — the
  lake is UTC-normalized), license, revision, `generated_at` and per-series
  coverage (interval, venue, symbol, first/last timestamp, row count).
  `ManifestWriter.generate` scans the shards and bumps the revision;
  `Lake.dataset()` is the queryable surface and refuses to open a dataset
  whose manifest is missing, invalid, for a different name, or stale —
  "stale" means declared coverage (series set, rows, range) differs from
  the bytes on disk. A `Dataset` is a point-in-time view: re-open after
  writes. Regeneration is monotonic: `ManifestWriter` refuses to declare
  less coverage than the previous manifest — vanished series, shrunk
  rows, or a moved end are refused unless the series was rebuilt from an
  authoritative source (`rewritten`), and a moved-forward start is
  refused even for rewritten series, because a new day must never mask a
  lost interior day. Removing `manifest.json` is the explicit override
  for deliberate changes. Symlinks anywhere in the layout are rejected
  (on the manifest scan and on the raw `Lake` read/write surface), and
  every name is whitelist-checked, so a dataset can never point at bytes
  outside the lake root.
- Every path component is validated against a whitelist before any I/O:
  dataset `^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$`, symbol
  `^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$`, day `YYYY-MM-DD`, and
  interval via the canonical grammar — so no name can escape the lake
  root, cross partitions, or break the COPY statement (lake roots may
  legitimately contain quotes; they are escaped in SQL literals).
- Shards are written to a temp file in the day directory and atomically
  renamed into place; a crash or failed call never leaves a truncated
  shard at the canonical path. Writes are idempotent day replacements,
  so a failed call is repaired by re-running it.

## Consequences

- The lake is portable (plain files), diffable, and trivially inspectable
  with any Parquet tool; no database to migrate or back up separately.
- Wholesale day-shard replacement keeps writes idempotent and makes
  re-ingestion after provider replay safe, at the cost of day-granular
  atomicity: partial-day updates are never mixed with old data, and the
  temp-file-and-rename write means a failed ingestion leaves either the
  old day or the new day, never a mixture.
- Stored-order reads push ordering responsibility to consumers; callers
  that need chronological order must sort explicitly after quality passes.
- Provider adapters never touch the lake directly — they return canonical
  domain objects and ingestion writes them — keeping the provider contract
  (issue #17) independent of storage.
- Whole-day writes mean a gap spanning midnight touches two shards; the
  gap detection in issue #19 must therefore span shards, not files.
