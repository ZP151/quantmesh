# Iteration0038 continuation — market-only import boundary

Issue218: https://github.com/ZP151/quantmesh/issues/218.
Plan: docs/superpowers/plans/2026-10-26-market-data-import-boundary.md.
Base e0a8d7107758236f32abe92522937dcd97e779a7/tree
de8b642ae049f5ecbc66574b67cb8c5fc30bd053. Branch codex/market-data-import-boundary.

## Planner / product

Root selectedA from the original author's <=15min exact-source diagnosis. Native
source import was STOP/unarmed: workstation70 -> frozen_experiments -> research
jobs -> service_client -> job_store25 -> missing pg8000, before mode dispatch.
Counterfactual diagnostic isolated four eager edges (three routers plus type-only
client import); this leaf implements the selected bounded correction.

Action: start market-only CLI without unused research DB imports. Metric: fresh
missing-driver factory/CLI positive cases and normal-mode explicit fail-fast
negative cases, zero unrelated constructor/server/provider effects. Non-goals:
dependency installation/reclassification, ordinary research fallback, feed/buffer,
math/vendor/UI/PG change, host/native activation, old/full suites/CI or GH.
ACK00:15:24Z; first20min limit00:35:24Z; hard45min final01:00:24Z on2026-10-26UTC.

## Quant researcher / risk judgment

pg8000 is declared core in pyproject.toml; absence means selected runtime is not
certified for all QuantMesh modes. The isolated market-only graph has no actual
PG/research-store need. Preserve both facts. This fix cannot qualify dataset,
provider finality/PIT, research results, native runtime or trading. Existing
server STOP and prior failures remain; historical64PASS is not native evidence.

## Implementer

Four fresh-child REDs were recorded before source change. Same-file lazy router
loader now runs on ordinary factory/CLI after market early-return and before any
other effects. Type-only client imports use TYPE_CHECKING with unchanged postponed
annotation. No runtime annotation consumer found in source/tests (existing search
only found unrelated worker/session annotation inspection).

Production delta:workstation.py only. Three research-router imports move to the
loader; type-only service client names move under TYPE_CHECKING; ordinary factory
binds the same returned factories to existing registration calls; ordinary CLI
loads them before other initialization. Missing required PG dependency is not
caught or converted to a healthy fallback. Core dependency/lock files unchanged.

## Verifier / reviewer

Owned evidence:output/market-data-import-boundary/.

-01-import-boundary-red.log:4 FAIL10.29s, each atworkstation70 eager import before
  its intended factory/CLI seam. No product implementation preceded RED.
-02-import-boundary-green.log:4 PASS11.39s, first result recorded00:18:09Z, within
  20-minute deadline. Market factory reads health/403/closes actual readonly reader;
  normal factory/CLI both explicitly raise named ModuleNotFoundError(pg8000) before
  sentinel stores/account/model/catalog; market CLI bypasses ordinary loader and
  uses fake uvicorn call, no real bind/provider/transport or ordinary effects.
-03RuffPASS;04 formatter flags only new test quote style, fixed by scopedformat.
-06 call-boundary check retained a harness AttributeError:FastAPI included-router
  items are not all flat path-bearing routes. No product defect or source repair.
 08 corrected same check inspects item types, constructs all three real routers,
 confirms exact returned function identity, unchanged public signatures/postponed
 client annotation and ordinary factory/CLI AST bodies except loader insertion.
-07-final-targeted.log:4 PASS9.74s.09-final-ruff/10-final-format/11-final-diffcheck
 PASS;2 files already formatted. Historical59new/5compat and full suites not run.

One reused independent narrow reviewer pending exact source freeze. Known
corrections maxround2; no third review.
No package/host/server/provider/CI action or default/full-suite replay authorized.

No runtime get_type_hints consumer of these postponed client names was found.
This does not introduce a promise to evaluate every forward annotation without
its type-only modules; a concrete existing consumer would return to root before
any scope expansion. Native server remains the supplied STOP/unarmed state.
