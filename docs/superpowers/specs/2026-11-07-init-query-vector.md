# One complete guarded Init-query vector

Issue [#297](https://github.com/ZP151/quantmesh/issues/297), parent #281, follows
the pure reference in #293/PR296. Base is merged d0aaf291. This is one bounded
information method, not an established SDK behavior repair or runtime grant.

The actual reference10 returned exact -1/NON_OK and NOT_READY with owned normal
close. Its request1001 MAY is written inside wire.before_send, after successful
packing and entry into the SDK send path. It excludes the earlier status,
connect, packing and pre-send status branches for this call. It does not prove
the saved send returned, TCP accepted bytes, or a vendor response. This path
has no Init-response journal writer. The pinned ReqInfo.wait returns None;
late notify can overwrite err, so a later err==Ok cannot prove unpack entry.
The complete causal decision is the independently bound ADDENDUM2, SHA256
68d6852c604aec5d76a62b482ce632a8e7ae7d00c5c37b04487f56158e866844.

## User action and outcome

One operator action runs a guarded instrumented Init-only operation. One closed
terminal/STOP vector identifies guard, saved-send, actual primitive-wait and
actual unpack families and carries the same-attempt receive/socket boundary
facts. Success is correct finite attribution or explicit UNKNOWN across the
predefined decision tree. It is not READY, a unique vendor cause, real data,
profitability or permission to trade. No frontend or numerical slice is added.

## Explicit identity and compatibility

Keep qm.ivv.reference-control.v1 and pure reference v1/v2 behavior intact,
including pure hook-absence checks. New immutable control schema
qm.ivv.reference-control.v2 has the same common fields plus exactly
method=init-query-vector-v1. The held control/pair/source catalog and parent
authorization bind this literal. There is no arbitrary observer flag or runtime
caller override. The operation remains the existing reference role, with the
same owning-ledger identities and once/lease machinery.

Only that control selects _InstrumentedReferenceBackend and
_InstrumentedReferenceObserver. Pure _ReferenceBackend/_ReferenceObserver remain
unchanged. New terminal/observation v3 add method and query_vector. Historical
v1/v2 selectors stay closed and reject cross-version/method fields. The v3
query vector never participates in READY, close or conditional admission.
The original fixed capture stays a separate operation with its original data,
request policy and all admission requirements.

An internal derived method marker may be used only after held-control
validation and must agree with that authenticated control again at use. A bare
caller/test string cannot activate instrumentation. Reject v1 plus an
instrumented marker, v2 missing/wrong method and any derived-marker mismatch.

## Reuse and the one new hook

Reuse the existing guarded wire, request binding, saved-send/unpack observers,
_InitReceiveTrace and partial-context close. Reactivate the existing reviewed
SDK query/handler/processor observation only in this explicitly identified
method. Do not enter the business capture pipeline or inherit its post-READY
set_sync_query_connect_timeout call. Keep no reconnect, no health/business and
no-send KeepAlive. Do not copy or fork upstream SDK code into production.

The only newly introduced SDK-request observation point wraps the already-bound
Init request's Event.wait instance method. Delegate exactly once with the
original arguments/timeout, return the identical object, and propagate the
same exception. Capture only exact True/False, RAISED or UNKNOWN. Do not perform
a second wait or install a global Event/SDK-class patch. Restore instance
attributes in the existing per-request finally ordering, including failure.
Do not delay restoration to obtain a socket snapshot. Preserve the primary
exception if restoration also fails; an unsafe installed-hook restoration is
a real ownership/cleanup refusal, not an optional vendor diagnosis.

Observe actual unpack entry/return/exception. At that existing decoded-object
boundary classify only retType as OK/NON_OK/UNKNOWN. Never inspect retMsg,
account/key fields, s2c/body, arbitrary exception text or payload. In particular,
do not gate unpack-entry evidence on an earlier PacketErr snapshot being Ok.
The PacketErr value is explicitly a snapshot, not the value atomically consumed
by the SDK's later conditional.

## Closed query_vector v1

The vector schema is qm.ivv.init-query-vector.v1. It has exactly these fields:

| Field | Allowed value |
| --- | --- |
| schema | The exact schema above |
| attribution | BOUND, UNBOUND, RACE_OR_UNKNOWN |
| guard | Closed stage/code object below |
| send | UNOBSERVED, ENTERED, OK, NON_OK, RAISED, UNKNOWN |
| primitive_wait | UNOBSERVED, TRUE, FALSE, RAISED, UNKNOWN |
| packet_err_snapshot | UNOBSERVED, Ok, Timeout, Invalid, Disconnect, SendFail, UNKNOWN |
| unpack | UNOBSERVED, ENTERED, OK, NON_OK, RAISED, UNKNOWN |
| ret_type | UNOBSERVED, OK, NON_OK, UNKNOWN |
| errors | Closed send/wait/unpack finite error objects below |
| receive | The existing closed qm.ivv.init-receive-trace.v1 shape and bounds |
| socket | The closed snapshot object below |

Guard has exactly stage and code. Stage is NONE/WIRE/LIVE/REQUEST/
POST_CONSTRUCTOR/RESTORE/UNKNOWN. Code is NONE/REFERENCE_LIVE_REFUSED/
REFERENCE_SEND_REFUSED/REFERENCE_INIT_ONLY/OTHER_GUARD/UNKNOWN. These are fixed
categories; no arbitrary poison or exception text crosses the boundary. Retain
the first covered guard stage without changing the underlying throw/check order.
Shared wire may gain only an instrumented-profile scalar callback at its
existing refusal point; its ordinary/pure behavior is unchanged.

Errors has exactly send, wait and unpack; each has exactly type and errno.
The fixed type categories are NONE/UNKNOWN/GUARD/OS/BLOCKED/BROKEN_PIPE/
CONN_ABORTED/CONN_REFUSED/CONN_RESET/TIMEOUT/PERMISSION/TYPE/VALUE/ATTRIBUTE/
KEY/INDEX/RUNTIME/ASSERTION/MEMORY/OVERFLOW/EXCEPTION/INTERRUPT/SYSTEM_EXIT/
GENERATOR_EXIT. Use exact builtin type identity and the exact local guard type,
never arbitrary class names, str, args or message text. Exact other builtin
OSError family types may map to OS. Unknown user subclasses map to UNKNOWN
without reading their attributes. errno is null, or an exact non-boolean
integer0..65535 read only from the public errno of a whitelisted exact builtin
OSError-family instance. Unobserved/non-raised error is NONE/null. No error
object is retained. This adds no hook, call or logger. In this new mode the
saved-send contract is an exact two-element tuple and unpack an exact
three-element tuple with exact integer return code; unexpected shapes are
UNKNOWN and the identical result still reaches the SDK. Neither normal return
nor OK means vendor ACK. Preserve legacy observer behavior in the old mode.

Socket has exactly identity, selector, readable, unread, wait_delta_ms and
sample_order. identity is UNBOUND/VERIFIED/DRIFT/UNKNOWN; selector is
ABSENT/READ/NO_READ/UNKNOWN; readable is TRUE/FALSE/UNKNOWN; unread is
ZERO/LE_1K/LE_64K/GT_64K/UNKNOWN; wait_delta_ms is null or an exact integer
0..480000; sample_order is SEQUENTIAL. No FD number, address, message or raw
socket contents is exported. Invalid or unavailable metadata is UNKNOWN.

Reuse the existing collector's bounded counters, time order, overflow and
recorder-error semantics. Freeze the instrumented vector once before close and
trace teardown; do not emit a duplicate receive trace through an unrelated
capture lifecycle field. All maximum terminal/status/frame checks must include
the entire vector. Preserve the existing 327680 carrier, 262144 packed,
1048576 body, 8192 status, 9MiB stdout and complete 24MiB-per-side future bounds.

## Non-consuming own-socket snapshot

Take one fixed boundary sample after Init failure and before close/trace
teardown. Use the independently retained exact connection/socket identity;
derive field names from the pinned network_manager source rather than guessing
or broad reflection. Verify the same object/FD identity before and after.

Read only existing selector key/data/READ interest. Use an independent zero-time
select on the already-owned socket and, where available, FIONREAD to bucket
unread size. Never call the SDK's own poller to consume events, recv, MSG_PEEK,
SO_ERROR, dup, a new socket/FD, selector mutation or state mutation. No global
proc/socket scan, dependency install or permission change is allowed.

These are sequential observations. Positive unread does not identify an Init
response, readable+zero may be EOF, and zero does not prove no earlier response.
Unavailability, denied syscalls, closed/reused descriptors, identity drift or
inconsistent order yield UNKNOWN/RACE_OR_UNKNOWN. Optional probe failure must
not become vendor failure, relax mandatory guard/FD/source/once/close checks or
introduce a new data-send gate. No Linux/sandbox compatibility is claimed before
actual evidence; do not widen permissions to eliminate UNKNOWN.

## Decision and release boundaries

Covered guard first-stage precedes SDK attribution. Saved-send RAISED is not
proof of no bytes. Only actual bound unpack entry establishes that branch.
Primitive wait FALSE establishes that call's timeout, not absence of a late
response. Combine true wait/unpack/notify order and the finite receive chain;
inconsistency remains RACE_OR_UNKNOWN. Socket facts describe the sample only.
No concrete evidence currently warrants changing timeout, connection, READY,
thread, provider configuration or login.

TDD uses the actual pinned SDK function bodies and real Event boolean semantics
over synthetic external I/O. It covers late overwrite, actual unpack, swallowed
guard/send errors, identity/exception preservation, restoration, closed codec,
optional OS-query failure and pure/default compatibility in this one slice.
No real SDK context/host call is allowed during software work. Required normal
CI, independent two-axis review, normal merge and consistent source publication
precede any separately registered runtime method. Old negative pairs, counts
UNKNOWN, source publications, history and unused futures remain unchanged.
