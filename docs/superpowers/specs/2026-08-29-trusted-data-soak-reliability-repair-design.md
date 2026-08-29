# Trusted-Data Soak Reliability Repair Design

Status: draft for operator review

Date: 2026-08-29

Tracking issues:

- [#124 — real 168-hour trusted-data soak](https://github.com/ZP151/quantmesh/issues/124)
- [#127 — workstation connection witness](https://github.com/ZP151/quantmesh/issues/127)

Applies to: the post-merge Iteration 0021 stability gate only

## Purpose

The real-data soak has restarted repeatedly for different reasons: a collection
driver accepted an unavailable Moomoo result, the workstation slept through a
required cadence, an upstream NVDA daily bar was revised after publication,
the connection probe collided with the formal daily task, and remote witness
publication was not a single-writer operation. These are not independent
operator mishaps. They expose missing production control-plane semantics around
otherwise sound immutable evidence.

This repair makes the complete path fail closed and reproducible:

`collect -> validate exact outputs -> observe -> fully verify -> persist run receipt -> publish once`

It also adds the explicit, immutable overlap-resolution path already required
by ADR-0018. A resolution acknowledges one exact provider correction without
rewriting the failed evaluation or teaching the system to ignore turnover.

The repair does not complete the 168-hour gate immediately. It produces a
remotely reproducible runner, starts a new evidence root, and then requires 168
real elapsed hours of accepted evidence.

## Incident evidence and diagnosis

### NVDA provider correction

The rejected raw dataset is `moomoo-nvda-1d-raw-bars`. Revision 5 manifest
`4f398b0e...` and revision 6 manifest `6b95abac...` disagree on exactly one
overlapping row:

- identity: `NVDA:2026-08-27T04:00:00+00:00`;
- conflict fingerprint:
  `6e30bad00d3e0df50794a426c09c6ca01701b2bcda98a39f1cd684bfde1eb0a9`;
- `turnover`: `67,700,954,784.651` became `67,628,318,193`;
- timestamp, OHLC, volume, code and interval are identical;
- normalized, split-adjusted and log-return feature rows are identical.

The raw overlap failure is correct. Two provider snapshots prove that the
provider revised its payload; they do not prove which turnover value is
objectively correct. The only honest local disposition without external
corroboration is `operator-acknowledged`, not `provider-verified`.

### Missing production amendment path

ADR-0018 and the quality model support exact amendments, but the production
collection coordinator never supplies one. There is no operator inspection or
resolution command and no immutable lookup from a failed evaluation to a
resolution. Worse, the overlap evaluator compares only with the immediate
predecessor. A later revision matching the corrected revision can therefore
return to PASS without the required explicit acknowledgement.

### False-green daily execution

`tools/soak_daily.py` currently treats a successful observation subprocess as
the end of the formal task. The observation can append a report containing
critical issues while the Windows task still exits zero. The driver does not
run the complete verifier, uses a stderr substring to treat a duplicate UTC day
as success, does not type-check the Hyperliquid result, has no subprocess
deadlines, and can observe stale catalog heads rather than the exact five
outputs of the current cycle.

### Connection-witness races and stale state

The formal daily task and connection probe both start at the top of the hour.
At 08:00 the probe can see the legitimate Scheduler state `Running/0x41301`
and report failure while competing with the task for OpenD. Timed-out or
terminated probes (`0x41306`) may leave `latest.json` pointing to an older run
because the script writes only at normal completion. Probe children have no
hard deadline and run files are replaced with `Move-Item -Force`, so their
claimed immutability is not enforced.

### Non-reproducible runner and duplicate remote publication

The registered tasks execute a mutable developer checkout. The current
candidate commit and a previously reported candidate are not reachable from
the GitHub remote, so an external reviewer cannot reproduce the claimed
runner. GitHub publication uses a check-then-post sequence without a durable
outbox or cross-process lease; the issue history contains a duplicate-comment
incident.

## Selected approach

Add a versioned operational control plane around the existing trusted-data
stores. Preserve all v1 quality and report bytes, introduce a v2 overlap
baseline proof for new evaluations, and store exact overlap resolutions as
separate content-addressed evidence. Replace the daily script and connection
probe with deadline-bounded state machines that always write immutable run
receipts. Publish GitHub witnesses from one durable outbox authority.

This keeps provider history truthful and separates three claims:

- `clean`: no qualifying conflict exists;
- `qualified-with-resolution`: an exact prior conflict was acknowledged under
  a bounded downstream-use policy;
- `failed`: unresolved, mismatched, missing or newly changed evidence.

## Approaches rejected

### Ignore `turnover` or add a numeric tolerance

Rejected. Turnover is provider evidence used by liquidity, cost and slippage
research. A tolerance would silently authorize future corrections and would
not bind the decision to the reviewed row or manifests.

### Rewrite or delete the failed report

Rejected. The failure is correct historical knowledge and must remain
auditable. Correction is additive only.

### Let the next identical revision heal naturally

Rejected. This bypasses ADR-0018's explicit acknowledgement requirement and
makes trust depend on collection timing.

### Restart the soak without changing the control plane

Rejected. It would reproduce the same races, false-green exit status and
non-reproducible runner.

## Immutable overlap resolution

### Resolution object

Introduce `OverlapResolutionV1`, a content-addressed immutable object with:

- resolution schema/version and resolution ID;
- failed quality-evaluation ID and failed daily-report ID when applicable;
- quality-policy ID and dataset ID;
- accepted-baseline manifest ID and corrected-candidate manifest ID;
- exact sorted conflict fingerprints and row identities;
- exact canonical field differences, including old and new values;
- predecessor and candidate knowledge times;
- `reviewed_at`, operator identity and non-empty reason;
- attestation kind: `operator-acknowledged` or `provider-verified`;
- a downstream-use policy.

The initial downstream-use policy permits the unchanged canonical OHLCV path
and its adjusted/feature descendants. It does not qualify raw turnover or any
liquidity, cost, capacity or slippage consumer. The resolution takes effect at
`reviewed_at`; it never changes what was knowable before the two snapshots and
review.

### Resolution index

Store resolutions under their content hash and add a create-once binding keyed
by the failed evaluation ID. An exact retry is idempotent. A second different
resolution, missing object, altered binding, wrong policy/dataset/manifest,
unknown fingerprint, partial conflict set or wildcard is rejected. There is no
delete or supersede operation in this slice.

The operator CLI has separate inspection and mutation commands:

- inspect one unresolved evaluation and print exact manifests, rows, fields
  and fingerprints;
- resolve only when all expected IDs and fingerprints are repeated on the
  command line with operator, reason and attestation.

Human-readable output is diagnostic; canonical object bytes are the authority.

### Stable overlap baseline

New production evaluations use quality schema v2. The baseline selector walks
committed dataset history and quality bindings and chooses the latest accepted
manifest:

- an ordinary PASS evaluation is accepted;
- an overlap-only FAIL is accepted only through its exact valid resolution;
- any other hard failure remains unaccepted.

The new candidate is compared with that accepted baseline, not merely the
immediate predecessor. The v2 evaluation records baseline manifest ID,
baseline evaluation ID and optional resolution ID. Therefore:

- without a resolution, revision 7 is still compared with revision 5 and the
  same NVDA correction remains failed;
- after exact resolution of revision 6, revision 6 becomes the accepted
  baseline for later collections;
- a distinct later correction produces a new fingerprint and requires a new
  resolution;
- old v1 evaluations continue to verify byte-for-byte under v1 rules.

The original revision 6 evaluation and the 2026-08-29 daily report remain
failed forever. Catalog readers expose the additive resolution and the label
`qualified-with-resolution`; they never relabel the original evaluation PASS.

## Formal daily-run state machine

### Exact-cycle binding

Each daily run receives an immutable operational run ID and records the clean,
remotely reachable code commit, dependency-lock digest, script digest,
configuration digest, UTC slot and all stage outputs. The run refuses to start
when the checkout is dirty, the commit is not reachable from the configured
remote integration ref, or runtime dependencies do not match the frozen
contract.

The collector validates typed output for Hyperliquid BTC/ETH/SOL and Moomoo
AAPL/NVDA. Each target must return the expected job ID, run ID and exact raw,
normalized, adjusted and feature manifest IDs created or idempotently reopened
by this cycle. Observation receives those IDs explicitly. It cannot substitute
current catalog heads.

### Stage deadlines and receipts

Every external process has a monotonic deadline and process-tree termination.
The driver writes a create-once stage receipt after each transition and always
writes one terminal receipt from a `finally` boundary. Terminal states include
`passed`, `failed`, `timed-out`, `blocked-user-auth` and `interrupted`.

Operational receipts live in a separate versioned run root. They never modify
trusted provider objects. Writes use temporary files plus create-new atomic
publication; an existing different file is corruption, not overwrite.

### Verification determines exit status

After observation, the driver invokes the complete soak verifier for the exact
evidence root with `minimum-hours=0` and at least one session. Exit zero is
possible only when the verifier passes and its result is stored in the run
receipt. Critical issues, verifier exceptions, missing outputs and timeouts all
produce non-zero exit status.

A retry for an existing UTC day reopens the same immutable report and reruns
verification. It returns the same verdict: an existing passing report can
return zero; an existing failed report remains non-zero. No stderr substring is
used as control flow.

A cross-process lease protects a UTC slot. Concurrent attempts converge on one
canonical report and one terminal run result. Crash recovery accepts only exact
matching staged receipts and fails closed on ambiguity.

## Connection-witness state machine

Move probe behavior into a version-controlled, unit-testable Python command;
the scheduled PowerShell file is a minimal tracked wrapper. Each child call has
a hard deadline and tree kill. A terminal receipt is written in `finally`, even
when the scheduler, Python, TCP or OpenD checks throw.

Run receipts are immutable and keyed by scheduled slot plus attempt. A small
atomic latest pointer may advance only after the immutable receipt exists.
Concurrent attempts may not overwrite one another.

Scheduler interpretation is explicit:

- recent `Running/0x41301` for the formal task is `in-progress`, not failure;
- running past the formal deadline is failure;
- `0x41306` is failure and must produce a fresh receipt;
- a recent completed zero result is pass only when its matching daily terminal
  receipt and full-verifier proof exist;
- missing or stale task evidence is failure.

When the formal task is in progress, the connection probe does not start a
competing Moomoo SDK request. Process/TCP evidence plus the typed `in-progress`
state is sufficient for that slot.

## Scheduling and workstation contract

The installer owns and verifies both task definitions after registration:

- daily task: 08:00 Asia/Singapore;
- connection witness: every two hours at minute 10;
- remote publisher heartbeat: every two hours at minute 20;
- wake-to-run, start-when-available, battery execution, overlap policy,
  retries and execution limits must round-trip to the expected values.

Timing separation reduces deterministic contention, while state interpretation
still handles retries and long-running tasks correctly.

OpenD interactive authentication cannot be made unattended by repository code.
Missing daemon or logged-out state is `blocked-user-auth`, never a synthesized
report. A host-off, sign-out or hibernation gap beyond the accepted cadence
invalidates the current 168-hour candidate; missed days are not backfilled.

## Single-authority GitHub publication

Local runs append publication intents to a durable outbox. One publisher holds
a cross-process lease and publishes only terminal, locally reverified evidence.
The idempotency key includes issue, witness kind and exact run/report ID.

Before posting, the publisher reads the issue for the exact key. After an
ambiguous network result it reads again before retrying. A successful post is
recorded in a create-once receipt containing the comment URL and a read-back
digest. Conflicting receipts or multiple matching remote comments are reported
as failures requiring review.

Issue #124 receives a success witness only after the complete local verifier
passes. Issue #127 retains both scheduled failures and later supplemental
recovery checks; a recovery does not erase the failed slot.

## Migration and new 168-hour candidate

1. Implement and verify the resolution, runner, probe, scheduler and publisher
   changes on a clean integration branch created from `origin/main`, preserving
   the divergent local branch and all existing evidence.
2. Push the tested commit so every registered runner commit is reachable from
   the remote integration ref.
3. Append one exact `operator-acknowledged` resolution for the known NVDA
   conflict. Preserve the failed evaluation and report.
4. Perform one fresh five-target collection on the new commit and verify all
   objects can be reopened from exact recorded IDs.
5. Create a new `C:\QuantMesh\evidence-v3` candidate root; never copy passing
   duration or reports from the rejected root.
6. Register and round-trip-verify the new scheduled tasks and update the
   publisher heartbeat.
7. Publish one repair/restart witness to #124 and one scheduler/probe repair
   witness to #127 after local verification.
8. Accumulate 168 real hours. Any cadence violation, unresolved new conflict,
   runner drift or missing terminal receipt fails the candidate and starts a
   new root.

## Acceptance matrix

### Resolution and quality

- unresolved overlap cannot heal on a later identical revision;
- exact resolution admits only the recorded conflict set and use policy;
- wrong IDs, fingerprint, field diff, partial set and concurrent conflicting
  resolution fail closed;
- deleting a resolution object or binding makes verification fail;
- a new provider correction requires a new resolution;
- v1 historical evidence still verifies unchanged.

### Daily runner

- a report with any critical issue exits non-zero;
- complete-verifier failure and exception propagate non-zero;
- duplicate-day retry re-verifies and preserves the original verdict;
- malformed, unavailable or incomplete provider output is rejected;
- stale catalog heads cannot satisfy the exact-cycle target matrix;
- per-stage timeout kills descendants and leaves a terminal receipt;
- crash and concurrent attempts converge only on exact evidence;
- dirty or remotely unreachable code commits are refused.

### Scheduler and connection witness

- installed settings round-trip and drift is detected;
- sleep/wake and start-when-available drills retain an honest cadence;
- reboot or OpenD logout produces `blocked-user-auth`;
- recent formal `Running/0x41301` is not a connection failure;
- overdue running and `0x41306` are failures with fresh receipts;
- exceptions and timeouts always produce terminal receipts;
- immutable run files survive concurrent probes without overwrite;
- staggered schedules are asserted by installer tests.

### Remote publication

- one authority owns each idempotency key;
- ambiguous POST is followed by remote read before retry;
- restart and concurrent publishers cannot create a second intended comment;
- local receipt and remote comment digest audit each other;
- #124 success is impossible without a local full-verifier proof.

### Final operational proof

- a clean pinned install passes focused and full automated checks;
- injected gap, drift, provider outage and provider correction drills all fail
  closed;
- the registered real host starts a new candidate on the remotely reachable
  commit;
- completion is claimed only after 168 real elapsed hours and a final complete
  verifier pass.

## Delivery roles and checkpoints

- Planner owns phase boundaries, dependency order and acceptance criteria.
- Quant researcher owns correction semantics, knowledge time and downstream-use
  restrictions.
- Implementer owns one bounded vertical slice at a time using red-green-
  refactor tests.
- Reviewer is read-only and checks architecture, immutability, licensing and
  trading-safety invariants after each slice.
- Verifier runs focused, integration, full and real-host checks and records
  exact commands and outcomes in the Iteration 0021 ledger.

The main thread remains the only source writer. No change adds order authority,
credentials, synthetic market evidence or a release promotion.
