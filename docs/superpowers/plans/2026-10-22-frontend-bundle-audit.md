# Issue207 frontend audit repair implementation plan

> **For agentic workers:** Execute inline with TDD and self-review. Root owns the single combined independent review and CI; do not dispatch another branch review.

**Goal:** Admit standard bundled packages through verified parent bytes, then remove frontend advisories using the exact minimum compatible fixes.
**Architecture:** Keep ordinary registry/SRI/SPDX checks intact. A pure API accepts raw archive bytes and re-verifies locked parent SRI before bounded tar interpretation; CLI acquires only required public artifacts into its own rechecked cache.
**Tech Stack:** Existing Python3.13 stdlib, Node22.23.2/npm10.9.8; CI Node22.12 unchanged.
**Spec:** https://github.com/ZP151/quantmesh/issues/207 and root's explicit2026-10-22 support-branch authorization.

## Global constraints

Owned: tools/npm_license_review.py, tests/test_frontend_security.py, frontend/package.json/package-lock.json and these own207records only.
No Python locks/host/Worker pins/CI policy/registry allowlist/product components/test behavior/timeouts/new package/platform/global npm changes.
Only one non-nested bundle parent,16MiBcompressed/32MiBexpanded/1024members; no extraction/execution. Verify parent raw bytes against original lockedsha512 every invocation. Missing/extra/ambiguous/unsupported data fails closed.
Preserve allowed SPDX set; inspect every child independently. Missing notice bodies remain NOT_QUALIFIED_FOR_FULL_NOTICE_REDISTRIBUTION.
Original audit RED/probes stay retained. Never claim rejected localnode_modules is accepted. Final lock must npmci before compatibility.
Review focus: false bundle claims, parent/child coverage, tar ambiguity/resource bounds, real vs synthetic artifact evidence, exact frozen member snapshot.

## One bounded leaf

- [x] Synthetic positive/adversarial RED observed:41failed/7passed; old ordinary denial assertions retained. Later edge REDs expose malformed license/URL/manifest handling, trailing content, deadline and boolean receipts.
- [x] Pure raw-byte API and bounded cache implemented; final targeted module63passed:62offline cases and one actual repository artifact qualification.
- [x] npm generated exact Vite8.2.4/Vitest4.1.11/Rolldown1.2.4 closure. Actual matched Vitest family is4.1.11; obsolete tinypool/vite-node no longer exist.
- [x] Full lock delta reviewed; exact278count plus full immutable member set committed to the test. All six bundled children are counted and proven from original parent bytes.
- [x] Accepted-lock npmci, audit0vulnerabilities, frontend44files/545tests, lint, APIcurrency and buildcheck pass. Generated bundle is byte-identical.
- [x] Validator59tests, broadRuff, changed-file format, whitespace and unchanged submodule pins checked; no hours-long Windows suite or old UI browser.
- [x] Author self-review complete; tested checkpoint is ready for ordinary commit/push. Final exacthead/tree belong in output/0021-dependency-audit-security/FRONTEND207-DELIVERY.json.
- [ ] Unique release owner integrates with the frozen Python leaf, performs combined independent reviewÃ¢â€°Â¤2rounds and one new exact-headCI. This writer does not create a duplicate CI/review or merge.

## Recorded implementation rulings

- npm10.9.8's optional-peer recursion initially chased wildcard Vitest5/devtools and crashed. Exact literal Vite/Vitest overrides, matching the direct versions, constrain the approved closure without force/legacy-peer-deps. Dollar references failed resolution and were not retained. No generator/environment change.
- Mechanical configuration scope: frontend/tsconfig.app.json adds only node to its types array. Official Vitest4 migration removes accidental @types/node inclusion; tests already import node:crypto/node:buffer. Actual tsc-bRED, isolated explicit-type probeGREEN and final real build/bundle identity prove this restores declarations without component/test behavior edits. This uses root's prior allowed mechanical-config exception.
- Inventory362Ã¢â€ â€™278 is an exact reviewed closure snapshot, not a relaxed threshold. Every original member removal/addition is retained in the final proof; actual six bundled children remain explicit.
- Original non-bundle denial clauses/messages and allowedSPDX set are AST-identical. Supported bundle proof is an additional raw-parent trust chain, never synthetic registry/integrity fields or installednode_modules authority.

**Stop:** Within90minutes deliver a reviewable commit or one exact blocker. No design-approval loop or newGoal.
