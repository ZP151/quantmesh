# SPY sample evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the bounded slice;
> independent review follows the fresh-reviewer gate, capped at two rounds.

**Goal:** Open a saved replay and inspect its own sample evidence and read-time
session lag without recalculation or replacement of its original report.

**Architecture:** New reports use schema2 and one bounded immutable sample_evidence
constructed before math from the same verified input and safe receipt references.
GET job adds a separate read-time view; stored jobs/requests/protocols and original
v1 artifacts/decisions are unchanged. Existing three math functions are untouched.

**Tech stack:** Existing Python/Pydantic/FastAPI/ObjectStore/CalendarService only.

**Spec:** EVALUATION-AND-SAMPLE-CONTRACT-20261025.md SHA
78873b12b9fb96c4bc396d6eb4a8aa45abf97faaeef217f427e9222354df580a
under0038-research-integration/QuantMesh/output/0038-strategy-acceptance-research-20261018/.

## Global constraints and ownership

Base345470491e2f83b5c36409c13a16cb04c5357afc, isolated existing worktree,
new branch codex/spy-sample-evidence. Preserve833branch/handoff and PR226 freeze.
Only replay core/API plus new targeted tests and own records. No frontend,
generated/shared-root files, dependency, SDK, data acquisition, server or model.
No numerical protocol changes, new statistical metrics or source/Paper promotion.
ACK2026-10-25T07:04:28Z; interface07:19:28Z; first result08:19:28Z;
final09:04:28Z.90seconds is observational, not an acceptance blocker.

## Review focus

- Current input B must never fill missing evidence for old job A.
- Legacy v1 unknown fields never trigger artifact migration or decision rewriting.
- Read-time lag uses original calendar version/close+30min and complete sessions,
  including weekends/half-days; unknown calendar/identity yields null with reason.
- Synthetic declared timestamps/source absence never become actual receipt/PIT facts.
- F0 strategy has0 entries/fills and defined0 returns/cost, but nullable ratios;
  same-cost buyhold still pays friction. No independence inferred from fills.

## One vertical slice and exact files

Modify `src/quantmesh/research/spy_replay.py` for bounded evidence models, trusted
loader metadata, new report schema2, explicit v1/v2 validation and read view.
Modify `src/quantmesh/api/spy_replay.py` only GET job response model/read method.
Create `tests/test_spy_sample_evidence.py` for the new behavior and F0 recipe.
Own iteration record `docs/iterations/0038-spy-sample-evidence.md` records roles.
Engine source need not change; long_entries and gross_traded_notional_over_initial_capital
already exist in report JSON. UI owner exposes them with correct nonannualized units.

- [x] Freeze exact DTO/report2/read-view/F0 contract in owned output and send root.
- [x] Write behavioral REDs for v2/pins/trusted metadata and new GET read-view;
  meaningful failure before implementation, targeted file only.
- [x] Minimal core/API implementation. Known nullable facts retain reasons;
  no all-green additional admission gate or generic quality platform.
- [x] Generate fixed F0-v1 once, preserve recipe/bytes/content pins and verify
  zero/null/cost semantics through original arithmetic in one targeted new test.
- [x] New targeted checks cover real stored legacy v1 bytes/decision, cold B/A,
  no rerun, clock boundaries/version unknown and public claim refusal.
- [x] Scoped Ruff/format/diff and AST/source provenance. One independent R1 READY;
  23new targeted tests independently pass, no source correction requested.
  Coherent runtime commit plus final docs checkpoint and immutable handoff.

Command: process-local PYTHONPATH=this-worktree/src, Python313 -m pytest
tests/test_spy_sample_evidence.py -q --tb=short --basetemp
output/spy-sample-evidence/tmp-<unique>. Preserve all RED/GREEN logs. Old38/37/20
are not mechanically rerun. Sole publisher owns combined release after PR226 ends.
