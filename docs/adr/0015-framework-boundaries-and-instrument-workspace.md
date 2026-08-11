# ADR-0015 — Framework boundaries and the instrument workspace

- Status: accepted (Task 4 independent review, 2026-08-12)
- Date: 2026-08-11
- Supersedes: none; preserves ADR-0014's live-data and quote-fence boundaries
  and every existing paper, risk, kill-switch, journal and audit decision.

## Context

Iteration 0020 evaluated two pinned frameworks before expanding the integrated
instrument workspace. FinRL-X was tested at commit
`e65d6f0483ead7d2ef4a5fc940cdf960392a25c1`; NautilusTrader was tested at tag
`v1.231.0` / commit
`27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`. Both ran only through external,
isolated bake-off tooling and emitted QuantMesh-owned
`FrameworkRunEvidence`. The generated decision record is
`docs/evidence/0020/framework-scorecard.json`.

The scorecard has seven hard gates: license, Windows installation,
determinism, chronological split, no leakage, paper-only behavior and contract
mapping. Runtime admission also requires a weighted score of at least 80. The
two committed run records contain no soft-score inputs. The generator therefore
records every missing category as `0.0`, lists every missing input explicitly,
and reports an honest total of `0.0`; it does not infer quality from prose.

## Decision 1 — Reject FinRL-X as a runtime or adapter dependency

FinRL-X is `reject`, not adopted. Its Apache-2.0 license gate passed, but the
pinned Windows CPython 3.13 environment failed while building dependency `bt`
because Microsoft Visual C++ 14.0 or greater was unavailable. The upstream
driver consequently produced no verified output digest, chronology result,
leakage result, paper proposal or QuantMesh contract mapping. Its Windows,
determinism, chronology, leakage, paper-only and contract-mapping gates are
false. A partial 13,275,793-byte environment is not evidence of a usable
runtime.

No FinRL-X package, transitive dependency or source enters QuantMesh. A later
reconsideration requires a fresh pinned run with verified outputs and a new ADR
revision; installing a compiler or changing Python merely to convert this
failed record into an adoption is outside this decision.

## Decision 2 — Retain NautilusTrader only as an isolated comparator

NautilusTrader is `isolated-comparator`, not adopted. The pinned run passed
license, Windows installation, determinism, chronology, no-leakage and
paper-only gates and produced deterministic output digest
`cfa10c25c523cfbd2f13d639d95f7d6116e57ea6e213d7d5ef0f26cec8f64514`.
It failed `contract_mapping`: Nautilus MARGIN collateral/account deltas differ
from QuantMesh cash-account semantics, and the pinned
`SandboxExecutionClientConfig` is a live `TradingNode` client configuration
with no standalone offline recorded-bar execution method. The comparator did
not fabricate a live data client or endpoint.

The LGPL-3.0 license, required process isolation, compatible isolated
`pandas==2.3.3` pin and 565,969,715-byte environment (about 566 MB decimal) are
material packaging and maintenance costs. The committed peak RSS is explicitly
only the direct-child working set, not the full process tree. NautilusTrader
may be rerun as external comparison tooling; it cannot be imported, linked or
packaged by the release runtime and cannot submit an order.

## Decision 3 — QuantMesh owns the product and execution boundaries

The copied-upstream-code count from both candidates is zero, and the number of
new release runtime dependencies is zero. QuantMesh retains ownership of:

- framework evidence and scorecard contracts;
- venue-aware historical and forecast artifacts, manifests and lineage;
- workspace composition and paper-proposal contracts;
- the deterministic paper account, quote fence, risk decisions, global and
  per-venue kill switches, matcher, journal and audit trail.

Tasks 5–10 therefore use the plan's native fallback: implement the instrument
workspace services against existing QuantMesh lake, live, research, portfolio,
risk, paper and audit contracts. Framework output, when evaluated later, may
only cross a validated data adapter into those owned contracts. It receives no
execution authority.

## Consequences and rollback

- Neither FinRL-X nor NautilusTrader becomes a release dependency. The release
  closure, audit lock and package metadata remain unchanged.
- NautilusTrader remains removable isolated tooling. Deleting its external
  checkout/venv and ceasing comparator runs has no product-runtime effect.
- FinRL-X's failed external environment and logs may be removed without losing
  the committed portable evidence or changing product behavior.
- The scorecard command is deterministic and can regenerate the committed JSON
  from the two immutable evidence files. Removing the command and generated
  scorecard rolls back only the admission record, not a runtime integration.
- Any future adoption requires new pinned evidence, nonzero evidence-backed
  soft inputs, all hard gates, license-closure review and a superseding ADR.
