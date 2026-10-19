# Frozen historical experiment inspection — P2

Issue: [191](https://github.com/ZP151/quantmesh/issues/191).
Date: 2026-10-19. Status: operator-approved design; implementation in progress.

## Approved user action

Import the retained SMA100/SPY experiment, inspect its protocol, snapshot,
recorded results and consumed holdout, then download the original evidence.
Success means the actual local page completes that loop, deduplicates a repeated
import and preserves its first receipt after restart, with verified associations.

The operator approved the unique presented short design through the main
coordinator: “P2短设计和UI改进方案都批准，继续并行执行。” The exact presented
question's UTF-8 SHA256 is
`785baf4120edc44208142f26db4def1b4db26e3331f242ac7354b70d2e27258f`.
This digest was calculated when binding the already-presented question to the
reply; it was not a preexisting human-approved digest. The original question and
consumption receipt remain local. Approval covers this design, not a future
source merge, unseen P3 design or independently approved UI owner's work.

## Architecture and bounded contract

Reuse ObjectStore/ObjectRef and the verified P1 SnapshotCatalog. Introduce one
local frozen-experiment catalog, one API router and one research page. Its root
is explicitly configured with `--frozen-experiments-root` alongside the P1
snapshot root. Unconfigured service stays unavailable. Storage lives outside
resettable demo roots; execution and trusted-data catalogs remain separate.

Schema `qm.frozen-spy-experiment.v1` has exactly 46 members: manifest, original
protocol/receipt/report, seven original snapshot inputs, five inert Python source
files, result JSON, strategy/benchmark/trades for eight fixed cases, and the
report's five local evidence targets. The manifest binds experiment ID,
snapshot archive SHA256 and every other member SHA256. Read ZIP members without
extracting paths. Caps: 8MiB compressed, 32MiB expanded, 64 members, bounded
JSON/CSV collections. Refuse duplicate, encrypted, symlink and unsafe paths.

Verify manifest members; protocol input/code hashes; protocol linkage from
receipt and result; experiment identity; all seven selected snapshot member
bytes; finite numeric/null result shapes. Immutable package identity is the
archive SHA256. Dedup preserves the first import time. Atomic publication and
verified cold reopen must detect missing/corrupt evidence. Retained Python is
never imported or executed. Imported Markdown is escaped/plain text.

API prefix `/api/research/frozen-experiments` supports bounded ZIP import,
list/get and fixed artifact downloads. IDs are opaque SHA256 strings. Downloads
carry actual content digests. Preserve the existing origin guard; reject caller
file paths and expose fixed safe errors. Route `/research/frozen-experiments`
offers import progress/error, history/reopen, report and original downloads.

## Truth and research limits

Show imported historical results, with cryptographic references checked. This
does not independently recompute economics or establish chronology, rights or
historical availability. Preserve proxy REJECT, formal R1/R2 INSUFFICIENT and
R3 NOT_AUTHORIZED, with the original hard evidence gaps. Inconsistent claims fail
closed. The existing final OOS is consumed and not pristine blind/prospective.
The current trial count 1 and zero searched variants do not mean a complete
historical trial count of zero: prior trials remain unknown. Freeze timestamps
and created-before-results are retained claims without independent time proof.

The primary case is final-base5bps, using next-session daily OPEN as a proxy,
with all eight fixed cases visible as diagnostics. Do not select the favorable
lag+1 result. Positive absolute return with benchmark underperformance does not
establish negative intrinsic alpha. Preserve null metrics and the confidence
bounds' actual meaning. No rerun, reset, strategy promotion or order control.

## Ownership and exclusions

One P2 source writer owns the backend and new P2 page/API/tests. Parent owns
documentation, local package and final generated resources/acceptance after that
writer stops. App.tsx/nav.ts have a main-coordinated exclusive window. The only
messages.ts change is nav.frozenExperiments in en and zh-CN; all page copy goes
in a dedicated module. DataReadiness and its local tests/CSS belong to the UI
owner. Preserve the separate P1 preview and immutable store.

No installation, new dependency, provider onboarding, network data/model call,
paid resource, original experiment mutation/execution, SSH/deployment, credential
change or live authority change. Do not rerun old full suites or consumed OOS.
Keep raw market bytes outside Git and preserve existing license restrictions.

## Acceptance

Synthetic RED→GREEN coverage verifies bindings, malformed archives/results,
unsafe claims, inert source, immutable/dedup/corrupt reopen, API/default-off,
origin, CLI and page states. Parent verifies a fresh targeted integration run,
generated API/build, actual original package import, SHA-checked downloads,
dedup, cold reopen, desktop and 375px ordinary viewport captures. Independent
review is capped at two rounds. The iteration records all five role outputs.
