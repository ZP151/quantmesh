# Selected-instance OpenD maintenance design

Issue [301](https://github.com/ZP151/quantmesh/issues/301). Status: offline repair
preparation only. No active-provider interruption or runtime GO is granted.

## Acceptance-consumer amendment before maintenance

This supersedes the original assumption below that all Source7 bytes can stay
unchanged. The SDK method,20s wait, source/identity/privacy/resource/once/owned
close and READY gates stay unchanged. A necessary recovery-consumer change is
part of this same maintenance slice; it is not a source-version/hash change made
merely to obtain a retry or a new observer/collector platform.

Actual reference12 closed as `REFERENCE_INIT_OBSERVATION`, method542ab41e.
`RecoveryLedger.begin` currently rejects that structural failure with the same
method; both preparer and runner bind method to the canonical Source7 pins. Thus
changing only provider identity would fail before acceptance. PR295's previously
published pure method is not selected just because its older hash differs.

The minimum contract adds optional `provider_repair_ref` to `RecoveryLedger.begin`
in `tools/research/ivv_additional_task.py`, with a new focused test module. Default
legacy behaviour remains exact. For this selected maintenance path the fixed
private root adapter MUST require/validate repair evidence even if the source
hash changes incidentally because the consumer implementation changes.

The ref has exactly `previous_connection_attempt_id` and `proof_sha256`. It names
only that attempt's create-only `connection-NNNNNN.provider-repair.json` in the
same protected ledger, never a caller path/body. The reviewed Operator writes
that original only after actual successful selected stop/cleanup, sole-successor
start claim and strict authenticated successor binding. It is a finite technical
handoff, not a permission/READY/data qualification minted by the ledger.

The proof's closed schema is `qm.ivv.provider-repair.v1`, change
`same-build-owned-provider-replacement`, logical_task_id, previous attempt/method,
old/new provider-binding digests, maintenance id/control/source digests, actual
interruption-authority digest, STOP-CLOSED digest, SUCCESSOR-START-INTENT digest,
sole successor nonce, `owned_old_closed=true`, `successor_binding_verified=true`
and `sdk_or_data_qualification=false`. Public pins/ids have strict shapes. The
reviewed importer checks original control/stop/claim/binding lineage and old/new
host/vendor/config/endpoint equivalence; current new provider still passes every
ordinary live native/source/Fresh gate. Metadata assertions alone are not native
proof and the code must not let an untrusted JSON caller issue this handoff.

Under the existing serialized ledger lock, `begin` verifies the proof's exact
digest/schema, same logical task, latest old failure/method and that failure's
old reference-pair binding; requires a new reference pair with exactly the new,
different provider binding; and exclusively fsyncs the old attempt's
`provider-repair-claim.json` before new INTENT. The claim binds proof/new attempt/
new pair/method. Crash after claim stays SPENT; re-entry, changed nonce/changed
method or another new pair cannot consume it twice. Old failures/MAY/once/counts
remain immutable. Conditional capture continues only through the unchanged real
READY/normal-close transition, with no repair-ref orphan on capture/ordinary jobs.

The proof records a completed condition change, not a new time-limited action
permit. An expired consumed stop control cannot stop again, while its historical
successful closure remains historical evidence. Current pair/policy/Fresh/live
binding govern later acceptance; do not add an arbitrary new proof TTL.

Private native_packet/root packet admission needs one bounded ref and actual
protected-original import/claim seam, with strict role/orphan checks, source pin
cascade and complete unchanged-cap geometry. Do not alter the SDK actor or its
source-method binding to an invented digest. Only the additional-task Source7
role changes for this necessary implementation; its new pin is published normally
with actual exact-head CI, other six roles remain byte-identical. CI584/head75262
is an intermediate core checkpoint and never qualifies this later consumer delta.

The user confirms OpenD is logged in and requires browser-extension interaction,
not global desktop automation. Reference12's public Init received TCP ACK84 but
no response bytes during its actual20s wait; all owned resources closed normally.
Application disposition is unavailable from the permitted existing records.
Neither a login failure nor a specific vendor/configuration defect is proved.

## One operator action and outcome

Prepare one controlled same-build replacement of the selected owned instance.
After separately resolving the interruption decision, the operator can retire
exactly that instance, reuse the reviewed stopped-provider startup/private-login
route, and publish an authenticated successor binding. The service acceptance
metric is one actual SDK READY followed by complete normal owned closure after
the condition changes. Success does not identify the former vendor defect.

The whole fixed-IVV task remains ACTIVE. No data/math/window/cost, SDK actor or
call-method, OOS/Paper/live or provider-entitlement change belongs
to this slice. Old reference12 is SPENT; capture13 was not prepared/dispatched.
All UNKNOWN counts, failed attempts, old claims and future reservations remain.

## Approaches and selection

1. Preserve the current instance and give the finite public technical draft to
   official support. This avoids downtime but external response time is unknown;
   no supported per-connection handler-history API was found in the reviewed
   existing records or public operation-command list. Do not send the draft
   without actual authorization to contact the recipient.
2. Prepare one same-build selected-instance replacement. This is the proposed
   service-recovery alternative, not an established root-cause fix. It changes
   provider process state and may restore service without another observer
   release. It interrupts the logged-in instance and may require real OTP/device
   confirmation. Runtime selection remains a consolidated operator decision.
3. Change version/configuration/port. Not selected: no concrete mismatch, affected
   build fix or vendor-supported replacement has been established.

Offline design/preparation of option2 is within existing repair scope. The
existing0d296551 restore record describes confirmed-stopped startup, while the
currently running provider is active. Do not turn that document into a new human
prohibition, or pretend it explicitly approves this new interruption difference.

## Existing reuse and missing implementation

Reuse the byte-pinned `operator-restore-02` instance-data, installer/runtime,
private CB1 login adapter and authenticated origin/provider binding. The
published `stage_console.py` and console template already provide one-shot
fresh-instance admission, persistent lifetime, pidfd cleanup and systemd
KillMode=control-group/Restart=no. Keep host, OpenD/SDK10.10.7008, public config,
loopback11112, template, memory1GiB/swap0/CPU50%/tasks128 and no automatic restart.

Missing code is a finite selected-active retirement transaction and its fixed
operator adapter. `restore_runtime.require_stopped()` must remain unchanged;
raw `systemctl stop/restart` is not an alternative to the missing transaction.
The collector remains read-only. An existing snapshot closes its readers before
return, so a prior snapshot alone must not authorize signalling a numeric PID.

Add one separate operator module, `deploy/aws/opend/selected_maintenance.py`,
and one focused test module. A private byte-pinned adapter assembles this with
the existing authenticated producer/native/start/login modules; no new SDK
release or generic supervisor/platform is required. The final adapter and its
actual data bindings receive independent review before any maintenance.

One concrete startup reuse correction is already known: the retained installer
expects previous stage_console5fb27538 while the attributed installed manifest
pins35631085. Reusing it unchanged would refuse after stop. Prepare an explicit
data-only previous-pin successor, authenticated against the actual manifest and
same existing deployed35631085 bytes; preserve all protection checks and previous
bytes. Do not patch a live helper or discover this mismatch during downtime.

## Retirement contract

`MaintenanceControl.parse(raw, expected_sha256, now)` accepts only canonical,
bounded, root-owned control bytes. It binds the exact existing provider-binding
digest, operation source digest, recorded interruption authority digest, fixed
maintenance purpose, one fresh maintenance identifier, exactly one fresh successor
instance nonce and a maximum300s operation window. The successor differs from
every historical/reserved instance. Both stop receipts bind this same successor.
No control/identifier/authority digest is minted during this preparation phase.

`retire_selected(control, binding, ops)` performs this finite order:

1. Verify applicable interruption authority and exact source/control/binding;
   check trusted saved-credential **metadata only** is PRESENT and that the
   complete pinned successor/start/login/binding path is available before stop.
   This does not prove the password will still be accepted.
2. Hold pidfds for the three exact attributed cohort members. Re-run the full
   authenticated provider snapshot after handles are held, compare PID/start,
   unit/invocation/cgroup/source/resource/listener facts, and require every held
   handle live. Preserve held proc/cgroup identities for closure verification.
3. Exclusively create and fsync `STOP-INTENT.json` and its parent directory before
   any signal. The record binds control, source and old binding and cannot be
   overwritten. A crash after intent is spent/uncertain, never permission to
   signal again. Recheck control expiry, all live held handles and full current
   binding after durable persistence, immediately before the signal.
4. Send SIGTERM only to the held selected MainPID pidfd. Do not signal a PID
   integer, service-name lookup, process group, unknown descendant or whole host.
   Let the unchanged reviewed service manager perform its owned cgroup cleanup.
5. Within one bounded30s closure window prove all three held handles exited,
   the exact old cgroup is recursively empty or its held identity has disappeared,
   the old selected manager is inactive/dead/MainPID0 without a replacement
   invocation, and no listener remains on the fixed loopback endpoint. Missing,
   raced or unsupported proof is UNKNOWN. No extra operator-origin KILL
   escalation or retry follows; the unchanged manager's15s/control-group stop
   cleanup retains its existing behaviour.
6. Exclusively fsync `STOP-CLOSED.json` only after every closure predicate passes.
   Preserve primary errors and attempt mandatory handle/query-child cleanup on
   every exit; cleanup errors must not replace an interruption or primary failure.

The trusted-host/root and external-provider limitations are unchanged. This is
not a hostile-root proof or global absence proof. A new/foreign invocation or
listener is never killed to make acceptance pass. A failed stop does not allow
successor startup. A same-name replacement cgroup is not old-cgroup emptiness.

## Successor, private login and acceptance

Only the same transaction's proved closure permits a newly recorded instance
through the existing reviewed startup route. Its immutable control/claim and
origin are new; never reuse old nonce/claims or mutate the old binding. Exactly
one successor may be started. Before delegating startup, exclusively create and
fsync per-maintenance `SUCCESSOR-START-INTENT.json` and its parent directory,
binding the exact control/closed-receipt digests and the control's sole successor
nonce. Re-entry, changed nonce or crash after this claim cannot delegate startup
again; preserve the mature instance's separate START-INTENT as well. Same public
source/template/binary/config pins,
free50GiB/resource checks and authenticated attribution must pass normally.

Reuse remembered login first, otherwise the existing saved credential through
the trusted private helper. Credentials/private panes/logs/raw configuration,
environment and argv payloads never enter prompts, evidence or fixtures. Use
only the browser extension for ordinary browser authorization. An actual OTP or
device challenge hands off; no speculative manual-login question is generated.
Publish the successor provider binding only through existing strict native
identity checks; do not substitute a PID/digest manually in collector inputs.

Only changed-condition, current-policy/resource/Fresh/Source/once/owned-close
admission can release one normal existing Init validation. Timeout, identity
drift, incomplete closure or a further required variable change stops this
alternative. Genuine READY plus normal closure is the maintenance endpoint;
later fixed capture remains independently gated and is not old capture13.

## Failure, rollback and timing

Before signalling, failure leaves the current instance untouched. After stop,
the original process and its in-memory login cannot be restored; preserve HOME,
state, binaries, configuration and historical evidence without deletion/copying
private state. If startup fails, leave stopped and report the exact finite stage.
If a qualified successor needs OTP, retain its independently owned process for
that handoff. No automatic restart/login/acceptance loop or version fallback.

Plan and focused seam verification:10–20min. Missing code plus focused tests and
two review axes:45–90min, with at most one consolidated fix/R2. Necessary exact-
head CI/publication: budget45–75min based on current normal release duration;
classify the final actual diff rather than promising a docs-only shortcut.
Qualified same-build maintenance:15–45min. One Init validation:5–15min. Overall
after the interruption decision and implementation start: approximately2–4h,
excluding actual OTP/device confirmation, external support and new findings.
No SDK recovery or financial/capture completion time is promised.

## Complete forecast before implementation/runtime

Offline code/tests/review/plan preparation: new complete9MiB local future within
the already imported common64 only after a fresh conservative retained census
proves retained+all current uncompleted futures+9MiB+2MiB margin <=64MiB. Do not
reuse the earlier wiring8MiB forecast silently or count completed development
peaks as simultaneous future; preserve their records. Source64 and CI16 remain
separate. Stop if the actual census/complete future cannot fit; register a
standing-authority net increase rather than dropping tests/evidence.

Proposed later maintenance+successor complete future: local32MiB/remote64MiB;
later changed-condition reference/conditional-capture pair local48MiB/remote48MiB.
These are new reservations (192MiB total), not a refund/reuse of old pair96MiB.
Remote maintenance64 comprises16MiB for all new helper/control/origin/binding
material plus48MiB forecast same-provider-state growth headroom. Do not silently
borrow either suballocation; register a net increase if a complete forecast
exceeds it.
Shared existing vendor binary/config/state are not copied. The existing accepted
trusted-external-provider growth limitation remains; forecast is not a hard disk
quota. Root centrally registers actual deduplicated totals before runtime.

No runtime hold/permit is activated by this spec. Actual central software32MiB
import2337B/f7e0d043 sets common96MiB, allholds1465909248/software650117120;
administrative G12GiB/P6GiB/free50GiB and no new paid resources remain.

Initial forecast3350B/abd5e610 and explicit successor4112B/5a482aa4 retain prior
wiring8MiB future and charge retained source-generated caches to common64. Actual
core RED/GREEN evidence2,215,936B requires core3/native3/review2/Parent1MiB, all
other futures unchanged. Common retained plus all current futures/new9/margin2
totals49,889,280<67,108,864; source checkout
plus complete1MiB code/docs future66,211,840<67,108,864; free408,693,149,696. Net0
for that historical offline checkpoint. Later forecasts explicitly retain every
old future, add consumer6/privateOps6/fixed-entry4MiB and a complete24MiB final
publication/binding package after the actual common32 import. Current complete
common forward91,832,320<100,663,296 is recorded in forecast05 (5577B/8aae6d9a).
Proposed later192MiB is NOT imported: with that future full-net conservative
Parent accounting, allholds would become1,667,235,840,
guardG12,053,475,418/P6,015,403,022/stress6,072,026,126 under unchanged caps.
The earlier local-only Parent projection5,897,962,510 stays historical and is
superseded without another112MiB budget. Require actual current central receipt
before runtime; neither software import nor this projection grants runtime GO.
