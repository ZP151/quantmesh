# ADR0043: Immutable reference Init conditional transition

Status: Accepted architecture in PR295/PR296; issue297 instrumented successor
remains in offline qualification. No real-input or financial qualification.

R2 clarification: the unchanged systemd-run --pipe client propagates the normal
diagnostic manager exit, so this exact reference STOP requires integer manager1
and client1 (not client0). Signal, boolean, other status or uncertain closure
cannot satisfy the condition. Ordinary successful capture still requires0/0.
The first paired operation also cross-checks control nonce, both attempt/context
IDs and SDK/policy/catalog pins before the sole begin and at held admission;
a matching control hash alone does not establish those semantic relationships.

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

## Versioned Init-return diagnostic successor (2026-11-07)

The reference override retains its already-returned exact integer classification:
0 is OK, -1 is NON_OK, all other objects/types are UNKNOWN. It returns the same
object and propagates the same exception. No new SDK method/hook or observation
of messages/responses is introduced. New terminal/observation v2 adds only
init_delegate_return; strict v1 acceptance remains for historical originals.
The scalar never changes READY, conditional admission or closure. Its offline
contract tests distinguish official Init failure from OK followed by loss of
READY before first sample, without claiming a root-cause repair. Ordinary
release/publication and physical admission still govern any new diagnostic.

## Explicit complete instrumented method (issue297,2026-11-07)

Actual reference10 returned NON_OK/NOT_READY with normal owned close and no
capture11. Its request MAY localizes execution beyond the guarded-send entry;
later err==Ok cannot establish unpack because late notify can overwrite err.
The existing pure reference and historical v1/v2 artifacts remain unchanged.

A new closed control.v2 adds only method=init-query-vector-v1. It explicitly
selects instrumented Init-only behavior and terminal/observation.v3 with one
complete closed query vector. Reuse existing reviewed send/query/unpack/receive
observation; the one newly introduced request hook wraps the bound Event.wait
call exactly once, preserving arguments, returned object, exception and finally
ordering. Record actual unpack entry and finite retType only. Do not infer
historical control flow from later mutable object state or response-journal
absence. No SDK fork, global hook, new observer platform or business path.

One snapshot of the already-owned connection/socket reads selector mapping,
independent zero-time readiness and unread-size category without consuming
events/bytes or changing state. No recv/MSG_PEEK/SO_ERROR/dup/newFD/registration
or permission expansion. Optional unavailability and sequential-sample races
remain UNKNOWN and do not imply vendor failure or a new data-send gate.
Mandatory source/once/FD/lease/resource/close and actual READY remain unchanged;
diagnostic fields cannot mint input or relax the conditional transition.

This is a software decision, not a concrete behavior repair or runtime grant.
The complete vector, actual wait/late-response semantics, restored hook lifetime,
legacy/default behavior and bounded geometry must be qualified in one slice,
followed by ordinary review/CI/merge/publication and separately applicable
actual admission. No automatic retry or old negative-pair reuse follows.
