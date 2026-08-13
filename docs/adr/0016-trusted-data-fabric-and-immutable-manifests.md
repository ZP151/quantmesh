# ADR-0016 — Trusted data fabric and immutable manifests

- Status: accepted (Iteration 0021 Task 3 final review, 2026-08-14)
- Date: 2026-08-14
- Supersedes: none; preserves the schema-version-1 Parquet manifest and Lake
  compatibility boundary from ADR-0003.

## Context

The original research lake stores Parquet day shards and rewrites one
`manifest.json` beside a dataset. That contract remains useful for existing
fixtures, replay and research consumers, but its freshness declaration cannot
detect a same-row-count, same-time-range content change. Replacing the mutable
manifest also prevents an old reader from proving which exact bytes it saw.

Iteration 0021 must preserve real provider evidence through raw, normalized,
adjusted and feature layers. A correction, backfill, adjustment-policy change
or feature transformation must create a new identity without erasing the old
version. Publication also needs an atomic current-version handoff so concurrent
collectors cannot silently overwrite one another.

## Decision 1 — Address objects and manifests by canonical content

Trusted-data object bytes are stored once under
`.trusted-data-v2/objects/sha256/<first-two>/<digest>`. The leading-dot v2
namespace is impossible under the version-1 dataset-name grammar, so a legal
v1 dataset named `objects` or `datasets` cannot collide with fabric state.
Every read verifies byte length and the SHA-256 digest. Existing bytes are
never replaced; a conflicting or corrupted path fails closed.

Schema-version-2 `ArtifactManifest` bodies declare exact object references,
canonical instrument and catalog identity, data kind and interval, calendar
and session policy, schema and transformation digests, source rights and
entitlement, event and knowledge ranges, adjustment and quality references,
code commit and collection run. The manifest ID is SHA-256 over canonical JSON
of the validated body, excluding the ID itself. The full canonical manifest is
stored once under
`.trusted-data-v2/datasets/<dataset>/manifests/<manifest-id>.json`.

Only `.trusted-data-v2/datasets/<dataset>/current.json` is mutable. First
publication builds the
manifest, pointer and identical immutable `genesis.json` / `initialized.json`
markers in a same-filesystem staging directory, then atomically renames the
complete dataset directory into visibility. A crash before activation leaves
no visible dataset and is safely retried; a crash after activation leaves a
complete dataset. There is no visible half-initialized genesis state. The
dataset lock lives outside that directory, so acquiring it cannot create a
false initialization.

Later publication permanently reserves the revision for exactly one manifest
ID under `revisions/<zero-padded-revision>.json`, writes the immutable
manifest, then advances the pointer under the same cross-process lock with
compare-and-swap. An fsync-backed append-only `history.jsonl` independently
records each revision, manifest ID and previous-record digest; it is created
inside the atomic genesis directory and is the high-water authority. Revisions advance
exactly once and pointer rollback is forbidden. A crash may leave the pointer
exactly one history record behind; a retry may create or reuse only that
record's reservation and manifest before completing the pointer. Deleting the
latest manifest and reservation and restoring the predecessor pointer cannot
free or rebind the revision while the hash-chained history remains. A larger
lag, a history or reservation gap, a history/reservation/manifest mismatch, a
missing initialization marker, a deleted pointer in an established dataset or
a restored pointer used to publish different content fails closed. Losing
publications may leave safe immutable objects, history records, reservations
or manifests, but cannot replace the winning current pointer.

An interrupted append may leave a partial, uncommitted history tail. Recovery
may atomically replace only that tail when the complete hash chain ends exactly
at the current pointer, `expected_current` matches before mutation, the
remaining tail bytes are an exact prefix of the retry's canonical record, the
retry is exactly the next revision, and any existing reservation or manifest
already names the same manifest ID. Without that independent evidence, the
tail itself must contain the complete candidate manifest ID; a short common
prefix is ambiguous and fails closed. A torn record overlapping a committed
pointer revision or conflicting evidence fails closed; arbitrary history
truncation is never repaired.

## Decision 2 — Readers bind to an exact manifest

`ManifestStore.open(manifest_id)` validates canonical manifest bytes, object
integrity and path identity before returning an `ArtifactDataset`. The reader
keeps the exact manifest and object references, so a later publication cannot
change an already-open dataset. Data kind and media type are checked before
domain rows are decoded. Canonical bar layers also verify instrument, interval,
event coverage and row identities against their declaration. Instrument
identity fixes the admitted calendar and session policy: bounded Moomoo
equities use the pinned XNYS regular calendar, while bounded Hyperliquid
perpetuals use the continuous UTC calendar.

The manifest carries both event-time and knowledge-time ranges. This task does
not yet implement point-in-time vintage selection; Task 4 will build that
selection and the complete raw-to-feature lineage on these immutable
identities.

## Decision 3 — Preserve the version-1 Lake contract

`DatasetManifest`, `ManifestWriter`, `Lake.dataset()` and the existing Parquet
layout retain their current schema-version-1 behavior. `Lake.artifact_store()`
is a narrow accessor to the version-2 store rooted beside the existing lake;
it does not reinterpret or migrate version-1 data. Migration happens only by
an explicit future publisher that reads old data and writes new immutable
artifacts with truthful provenance.

## Consequences and rollback

- Same-range content changes produce different object and manifest IDs.
- Exact old readers remain reproducible after new publication.
- Hash, canonical-byte, pointer and revision corruption fail closed.
- Objects and manifests may accumulate and require a future reachability-aware
  retention policy; deletion is not part of Iteration 0021.
- SHA-256 and canonical JSON become persistent identity contracts. Changing
  either requires a new schema version and a superseding ADR.
- The local filesystem is the trust root. QuantMesh detects partial object,
  manifest, reservation, pointer and history tampering, but cannot prove a
  coordinated rollback or deletion of the entire local v2 namespace without
  an external append-only anchor or backup. This iteration does not claim
  protection against an administrator who can rewrite every local evidence
  file.
- The version-2 implementation can be removed without changing existing
  version-1 Lake readers. Published version-2 files remain inert evidence until
  an explicit retention decision removes them.
