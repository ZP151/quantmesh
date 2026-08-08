# Incident: local disk exhaustion

## Symptoms

- `OSError: [Errno 28] No space left on device` in any store write
  (order journal, metrics store, experiment registry, watchlists).
- `quantmesh-ops record-metric` or `export-audit` exits with a
  raw OSError.
- Structured logs show repeated `No space left` messages from any
  logger under `quantmesh.`.

## Checks

1. Confirm the drive hosting `~/.quantmesh` (and the lake root, if
   separate) is the full volume: `df -h` (or `Get-PSDrive` on
   Windows).
2. List the largest store roots:
   `du -sh ~/.quantmesh/*` and the lake `data/` shards.
3. Check for stale temp files — a crashed atomic write leaves
   `.<file>.NNNN.tmp` next to a store root; they are safe to delete
   (the discipline never leaves the real file half-written).
4. Verify the last good record boundary: `tail -5
   ~/.quantmesh/orders/orders.jsonl` parses as JSON lines.

## Recovery

1. Free space: remove stale `.tmp` files, prune the lake's old
   shards only via the documented manifest discipline (never raw
   deletes of shard files — the manifest is the system of record).
2. If a store root is missing its `*.jsonl` file entirely, reads
   return empty (fail-closed to the empty list, never an error) —
   re-create the file by recording from the last known-good
   boundary, then reconcile against the surviving surfaces.
3. Record a `reliability_limit`-class operational note and re-run
   the export: the audit bundle must still verify with the same
   key.

## Prevent

- Monitor free space under `~/.quantmesh` (a gauge metric named
  `free_space_bytes`, limit alert wired per `docs/threat-model.md`).
