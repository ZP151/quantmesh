# Owned encrypted research backup and fresh-target recovery

Issue#171 / iteration0038. Completed source candidate4fceaf21af3fbe513fc1b02b210d2305112bfca7,
frozen0503d49; six leaf commits map to root7bbe883/6f6cef3/a77ec77/516d2c3/
90ebec1/6e25532. Root2dd5f4a adds Linux test classification only; qualifier and
runbook remain byte-identical to the reviewed candidate. Shared production
source/store/schema/protocol/locks/service gate are unchanged. Sessiona391 is
completed/idle; do not redispatch.

Actual local PG18.6/restic fixture exits0 in10.011seconds. The same exported
repeatable-read snapshot supplies captured SQL and pg_dump: three jobs and one
257-byte nonempty report. Source then advances to four jobs with a queued→cancelled
transition; fresh-target restored SQL retains exactly the captured earlier
state. Report/manifest/14,781-byte dump hashes agree. Completed/reserved model
effects and advisory outbox survive without a model call. `result.fixture=true`
is explicit: genuine storage/encryption/recovery with synthetic contract content,
not numerical Worker, strategy-return or ROI evidence.

Six attributed negatives pass: wrong key (actual exit12), newly owned corrupted
ciphertext copy (actual exit1), missing/substituted artifact, substituted manifest
and incompatible restored schema. Each leaves source state unchanged. Four
clusters and17 command handles close; sibling survives individual shutdown.
Independent terminal inspection finds23 known PG/command/helper PIDs absent,
generated inputs removed and original/copied six PG hashes unchanged. Unknown
identity never authorizes stop.

Two Spec/Standards rounds and scoped dispositions are retained. Round2's same
P2 included cluster and fixed-command registration. Root noticed the latter
remained open at349d969; final4fceaf2 closes it. Genuine native child RED proves
the old leak, with independent identity-checked cleanup; fixed SIGALRM GREEN
records owned exit-15. No third structural review occurred.

Candidate native45tests/0skip and unchanged independent service85tests/0fail/
0error/0skip, including all five actual PG cases/81 licences, pass. Root Windows
initially had11 failures/24passes/10skips from Linux descriptor assumptions.
Explicit platform classification gives Windows23pass/22skip and Linux45pass/
0skip with all Linux guards unchanged. Root's first native harness omitted the
unchanged PG helper (3fail/42pass); a new complete owned harness gives45/0skip.
All failures remain raw evidence. Root unit proof does not replace the candidate's
actual DB/crypto recovery. Whole-tree Ruff, owned-file format and diff checks pass.

External restic0.19.1 asset/checksum/source signatures were audited before use,
fingerprintCF8F18F2844575973F79D4E191A6868BD3F7A907. Compressed asset10107515bytes
SHAf415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c;
binary SHA20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639.
79 Go modules/98 notices and950-entry tool/prefix/source manifest are verified.
Unmodified MPL source and Apache/MIT/BSD notices remain externally retained;
no upstream code/binary or dependency enters the core release closure. The
local no-TLS PG build is not a production database qualification.

`sha256.json` binds198 selected raw streams/metadata, reviews/HANDOFF, SQL,
manifest/report evidence and root logs copied byte-for-byte. Root independently
checks XML counts, SQL advancement/equality, dump/report/manifest bytes, negatives,
cleanup, audit pin and source equivalence. Complete ignored output remains in
a391; upstream assets, private native roots, dump and encrypted repository stay
outside Git. Preserve full ignored output separately before archiving that worktree.
The two raw report copies use short archive aliases payload/report.json and
recovered/report.json to avoid Windows path-length and generic artifacts-ignore
rules. Their bytes are unchanged; original job-owned object keys remain in the
raw manifests. Whitespace exclusions apply only to preserved raw logs/reviews.

Final **OWNED_LOCAL_FIXTURE_ONLY**, **production_release_qualified=false**.
Off-host/vault custody, production PG/TLS, actual Worker report/recovery, model,
p95, final CI/human release and deployment remain pending. No cloud, paid,
source, Windows, trading or old-service action occurred. Whole Option A ACTIVE.
