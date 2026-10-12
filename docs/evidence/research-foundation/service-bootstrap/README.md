# Explicit service startup and genuine local HTTP/SQL acceptance

Reviewed bounded source97f53d046faaa6293edea2497836d1ed69819637. Root already
owns18ff2f1 health; child equivalent634e54c was not reapplied. Root integrates
only a759303/66f7667/0f8b71e/97f53d0 asb8f771c/9591e0d/93810b8/8e72a7b.
Four new runtime/CLI/test/runbook files; no store/gate/lock/schema changes.

Final actual owned native witness proof-edc8f7c006fb passes37 checks: no-effect
preflight, real DB/build/auth, configured fixture options, submit/same-key replay,
durable queued/cancelled status across API restart, one authoritative SQL job,
DB-outage scrubbed503 and known sibling survival. No backtest/model executes;
a queued/cancelled job is not report success. All5owned processes stop after
identity checks; original PG/env/cluster remain read-only and unchanged.

Both full-service JUnit and independently repeated POSTGRES_REQUIRED gate
report85tests,0failures/errors/skips, exit0, including all5realPG cases.
Native CPython3.12.3/81licensed wheels and existing Linux lock/schema/protocol
are unchanged. Actual source/dependency/bytecode/link admission precedes SQL
and serving. API fixes loopback8110/oneworker/noaccesslogs/noreload/proxytrust.
Explicit private0600credential files never enter body/env/argv/logs/artifacts.

Round1 dependency/cache gap and round2 directory-link gap have direct RED/GREEN
and fresh final candidate gates; no third structural review. reviews.md keeps
the initial findings/closure. Native system lacked ensurepip; a separately
copied read-only pip26.2.1 build tool is used only by the gate, outside the
API81-wheel runtime. Earlier failed witness directories stay failures.

This archive contains65raw streams:59original native files plus handoff/reviews/
progress/inventory/rootchecks. SHA256.json binds archived bytes; original
native-sha256.json binds the native subset. Root independently checks both
85/0/0/0JUnit receipts/all5PGcases,37true checks,5terminal owned cleanups,
81licenses,clean exactHEAD and actual imported source hashes against committed
candidate and integrated root blobs. Initial archive checking incorrectly
treated loaded_modules as a mapping; actual receipt is a list. Correcting that
checker did not change receipts or product code. Root Windows integration
10pass/46Linux-only skips/1.57s/exit0 is separate partial evidence.

No current-root merged/deployed build, productionTLS/HA/encryptedbackup/restore,
nativeWorker/model aggregate containment, Linux report/recovery, actual provider,
market/source/Windows/AWS or paid operation is certified here. Those final A
requirements remain open and must be measured on their exact runtime.
