# ADR0040 — Guarded private RAM auxiliary history profile

Date2026-10-30. Status: approved design; local implementation/review in progress.
Issue [255](https://github.com/ZP151/quantmesh/issues/255).

The actual human approved design a2119e83 through receipt b737f446, execution
c8b1be86. The archived spec keeps its original historical pending-approval header;
the explicit later human receipt supersedes that header. No approval is requested
again. Prior1GiB qualification/cause failures remain failures; errno30/OPEN_FILE
with targetOTHER_UNKNOWN does not identify TEMP or prove a repair.

Use a default-off private source capability for one fixed saved-history reader.
Normal constructor/default128MiB/temp0, public API/CLI and frontend stay unchanged.
The trusted native entry validates a fixed root-owned0444/single-link admission
artifact and independent root-owned expected-SHA receipt bound to THIS run. It
passes an O_RDONLY non-O_PATH FD plus receipt-derived SHA to Source. Source uses
an owned noninheritable duplicate and strict bounded JSON, not permission booleans
or caller-supplied verification functions. Receipt references bind the trusted
controller's completed full-content/generation/no-writer/dependency proofs; they
are not independent proofs merely because they are nonzero hashes.

Source also checks current actor/guard start identity, UID/cgroup, aggregate
2GiB/swap0/OOM group/CPU50, actual kernel whole-file POSIX READ lock, canonical
OS-readonly file identities, actual tmpfs mount/root/256MiB/noswap/noexec/0700,
headroom/deadline, and pinned runtime/source hashes. Guard and actor occupy the
same leaf below the common aggregate. The controller owns continuous guard and
headroom monitoring, full pre/post hashes and all operational admission evidence.
Source read-boundary checks do not replace that monitor or rehash7.42GB.

The new profile uses engine1GiB/thread1/UTC/tempmax256MiB and only the admitted
private RAM mount. Guard, Product, oracle and auxiliary pages share2GiB; there is
no extra256MiB grant, disk fallback, canonical mutation, data copy or writer stop.
The dedicated fresh-exec guard's own fd-close restriction remains operational;
Root must prove writer/alias/recovery generation coverage before any data read.
Default-off absence of evidence is refusal, not a synthetic success.

A private opener constructs real LiveBuffer read_only=True, then existing
LiveFeed(history_only=True), LiveHistoryService and ordinary workstation factory
are reused. It accepts only the original BTC/cut/twoUTC/1d/tail10000 request.
Nonreplay methods and out-of-scope filters refuse. Original SQL, _tail_rows,
constructor,17-column reconstruction, duplicate/missing, sort, transaction and
mathematics are retained. Close can release resources after revoked admission;
a rejected second claim cannot close the first reader's capability.

Local authored-fixture tests with explicitly synthetic OS/FD vectors prove source
behavior only. A later exact merged source/catalog plus real OS gates must yield
one original API200, independent a355 full111x17 originals/expectedmath/report,
same immutable cut, normal Product/reference/guard and independent closure,
unchanged DB/WAL/Paper/real clock. All remain unproved here. No strategy/provider,
financial result, Paper/live permission, dependency or upstream source copy is added.
