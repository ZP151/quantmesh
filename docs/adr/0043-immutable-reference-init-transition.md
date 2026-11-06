# ADR0043: Immutable reference Init conditional transition

Status: Proposed implementation; offline qualification only (issue293).

## Context

A guarded Init-only diagnostic must not become capture success. Its normal
non-data STOP is a structural failure under the default recovery ledger. A
separately authorized fixed pair needs one conditional original capture using
the same source identity; changing the method hash would misrepresent provenance.

## Decision

Keep all default ledger refusals. Register immutable pair data with the first
intent and allow only an explicit versioned transition for its exact adjacent
capture attempt. The existing remote claim lease owns a durable exclusive
condition claim before evaluation. Missing result, negative result and crashes
spend this pair permanently. They do not change unrelated historical rules.

The trusted carrier verifies held originals for SDK and parent normal closure,
manager normal exit, unit result and independently established cleanup. Recovery
cleanup cannot establish normal reference completion. After these checks it
observes current kernel boot/monotonic time, reuses verified_provider_snapshot,
checks the pinned SDK sources, and records the bounded post-close sample.
Pair, source, policy, provider cohort/configuration, SDK and every close original
are hash-bound. No caller boolean or child claim substitutes for these checks.

Only the exact positive outcome enables the existing sole second begin. Its
intent binds the outcome and the original child rechecks it before MAY. All
other structural failures retain their old semantics. Diagnostic output never
satisfies capture seal/manifest, FRAME, STORED, input or research requirements.

The condition claim binds controller identity, named inode and exact descriptor.
Only after the exclusive durable claim succeeds does its existing open file
description receive a bounded seek-position epoch derived from the pair hash.
No bytes, file size, extra lock or descriptor are added. A reopened lease starts
at position zero; a failed duplicate claim never sets the epoch. The parent
checks bounded procfs fdinfo for this epoch and the exact FLOCK write owner,
device and inode, with descriptor/name/controller rechecks. This is evidence
of the existing lease lifetime, not a new authority or secret.

The child sandbox remains unchanged: it cannot read another process's procfs
or the boot ID. Its existing authenticated observe IPC requests only the exact
conditional transition. The owning parent rechecks lease, outcome, boot/age and
existing live provider/child guards before a finite bound reply. The child
rechecks immutable originals and remains the sole MAY writer. Default observe
and unpaired recovery retain their existing behavior.

## Consequences

No new runtime role, general coordinator or grant service is introduced. No
source literal assigns a nonce/context. ABI, private staging/publication,
maximum geometry, independent review and ordinary release CI must qualify the
complete implementation. This decision is not SDK/runtime authorization.

Local WSL Windows mounts translate flock into POSIX locks. Production refuses
those. The local kernel tests use Linux anonymous files and explicitly model
named lookup in that case; ordinary Linux CI also exercises a named temporary
file. No POSIX-lock acceptance or sandbox permission is added for tests.
