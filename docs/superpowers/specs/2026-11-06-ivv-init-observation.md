# Fixed IVV Init finite observation — issue281

Planner froze this slice on 2026-11-06 after consuming the ctx6 static diagnosis.
One operator action remains resume the fixed IVV capture. Success for this slice
is an attributable finite failure category from its one existing Init, or a normal
READY followed by the original same-context capture. Software tests do not prove
provider/login readiness or financial inputs.

Use the existing process-private OfficialBackend/OneShot/wire and recovery failure
lifecycle. Each backend owns its observation; bind context identity, the sole Init
send's protocol/serial and its actual ReqInfo object. Do not patch SDK globals or
write/fork SDK files. Retain only finite send-return/success, same-request PacketErr
whitelist, unpack-entry/return category, constructor-end status and whether the
existing successful Init handler ever reached READY. Never retain msg, exception
text, protobuf/body/payload, account IDs or connection keys. Unknown observed enum
or contradictory attribution must refuse capture conservatively, without changing
the delegated SDK return value or swallowing its exception. Observation state is
bounded memory; existing failure lifecycle publishes it, including normal closure.

The existing sync Init delegates through SDK _query_sync, not the helper business
processor. Its send MAY precedes actual enqueue. Constructor return is not proof
of READY. Ever-READY and constructor-end status remain separate so a READY-to-CLOSED
race can be distinguished. Do not treat missing1001 response instrumentation as
no vendor response; preserve historical/external UNKNOWN and all old nominal debits.

Selected approach: narrow instance-bound wrappers around existing calls and the
existing lifecycle. Alternatives rejected: unredacted logs/payload inspection
(privacy boundary), global ReqInfo/SDK monkeypatching (cross-context interference),
and another health context (extra effects). No retry/autoconnect/timeout, admission,
protocol/request order/count, normal-close, data/math or trading change is allowed.
Paper remains default/livefalse. No dependencies, paid resources or environment.

Approved test seam: the real _OfficialBackend open/send/failure-lifecycle boundary
using the exact installed moomoo10.10.7008 public source methods isolated from
imports, with authored fake transport/clock/event/response boundaries. Hash-check
the frozen SDK source before selecting AST definitions; do not copy upstream SDK
code into core or fixtures. CI already installs the pinned moomoo extra. Prove
local send failure/exception, request Timeout/Invalid/Disconnect, unpack exception/
non-OK/missing response shape, READY-then-CLOSED, normal READY, unknown enum, wrong
ReqInfo/context, sequential backends, original SDK returns/exceptions unchanged,
and absence of private canary values in retained trace/manifest. No real socket or
provider access. Legacy routes retain their current meaning.

P26 capacity: Source15MiB complete14925824, common82MiB complete84852736,
software114MiB, capture112MiB each, closeout3MiB each; all474MiB497025024 held.
Net40MiB retains all old434MiB, Source524288 future and32MiB DB scratch.
Policy22b518276a65fb88d50e56a3897ac9a47822cdbb43d0e1e1fbf3252af34f300f
records fresh batch02 one context/Init, seven business requests,96keepalive,
rate1/s and28800s wall from first durable begin. Old batch01 is not revived,
global next connection7 preserves prior history. Numerical1 is a structural field,
not permission to compute without independent input acceptance and later accounting.

Normal two-axis review (R1 plus one consolidated R2 at most), matching-head required
CI, ordinary expected-head merge and full merged catalog precede effects. The sole
executor then checks actual source/method/provider/config/resources/owned closure
and records one bounded new context. If READY, perform the fixed IVV calls in that
same context; otherwise stop with finite evidence for Planner, no same-method loop.

