# Bounded certifi security patch — issue207

Owner: product agent acting as iteration0021 maintenance writer. Base fetched
origin/main aa62faeddd84c31887e43bf0dae532e649a4ecbe; branch
codex/0021-certifi-security-patch in its own managed worktree.
Tracking: https://github.com/ZP151/quantmesh/issues/207 (Refs205; do not close205).

## Goal and scope

Clear the reported PYSEC-2026-4320 dependency finding by moving only certifi
2026.7.22 to2026.10.19 in the four existing root/service locks. Preserve package
sets, all other versions/hashes and hash enforcement. This delivers a source
checkpoint for the release owner's combined review/CI, not a runtime repair.

Owned tracked files: requirements-audit.txt;
services/research_agent/requirements.linux-cp312.lock;
services/research_agent/requirements.lock;
services/research_agent/audit-constraints.txt; this plan and
docs/iterations/0021-certifi-security-patch.md. Any necessary additional direct
constraint requires an actual dependency explanation and coordinator handoff
before writing. No frontend, business/SDK source, Worker22-pin policy, historical
81-wheel evidence, shared ACTIVE, host, deployment, credentials or data calls.
No new environment or Goal; issue205 Goal remains blocked on actual input.

## Research and RED

- [x] Read required repository context, dependency/release process and exact CI
  finding/source-exposure mapping. Reproduce by auditing existing pinned input
  with an already installed pip-audit; preserve original CI RED unchanged.
- [x] Read current primary PyPA/GitHub advisory, exact PyPI release metadata and
  artifact provenance. Choose minimum reviewed fixed version2026.10.19: the
  original maintainer advisory says.18; current PyPA/GitHub Reviewed event and
  affected list say.19, which restores unaffected roots. Do not treat.18 as a
  sufficient audit repair or move the entire closure to latest.
- [x] Verify new wheel SHA/RECORD, metadata/Python tags, MPL-2.0 license and the
  affected root's absence using actual downloaded public artifact bytes.

## Generation and targeted verification

- [ ] Use existing pip dry-run/report per docs/release-process.md with old
  closure constraints changing certifi only, no install/build isolation. Compare
  root report to canonical Windows closure, retaining six Linux-only entries.
  NOT PROVED: editable metadata requires unavailable setuptools.build_meta;
  materialized binary-only root input cannot select the unchanged sdist-only
  moomoo SDK. Both failures are retained. No build tool/environment installed.
  Root file is a minimal refresh of the frozen, unchanged closure's certifi
  node; certifi's actual wheel metadata declares no external dependencies.
- [x] Resolve root/service dev closure against the full previous service pins
  with only certifi changed. Use existing lock_service.py official PyPI hash
  procedure for the Windows lock; do not bootstrap new pip-tools/environment.
  If existing tooling cannot safely perform the operation, record the exact
  smallest missing tool step instead of fabricating a resolver result.
  Pip-tools is unavailable. Static root/service dev dependency arrays were
  mechanically materialized (TOML has no dynamic dependencies) and resolved
  by existing pip26.2.1 without install/build hooks. Report matches all77 prior
  Windows service pins except certifi, then existing lock_service.py fully
  regenerated the Windows hashes. All76 non-certifi blocks are byte-identical.
- [x] Refresh the Linux certifi entry from the selected universal wheel's
  official hash, retaining its other80 selected wheels byte-for-byte. Check
  the universal wheel is accepted for both target interpreter/platform tags;
  this is not native Linux/Windows installation proof.
- [x] Audit all three pinned package closures with existing pip-audit,
  --no-deps --disable-pip; verify package-count/other-version/hash invariance,
  complete hash sets and dependency requirements from resolution/artifact
  metadata. Use existing license classification on the actual new wheel only;
  do not claim the ambient environment is the deterministic release closure.
  Local before audit: one vulnerability/exit1. After root79/Windows77/Linux81:
  zero known vulnerabilities/exit0. Existing parser and runtime lock selection
  accept both updated service locks; tag checks are compatibility, not installs.
- [x] Self-review the exact diff, git diff --check and commit Refs207/205.
  Stop after handoff. Release owner runs one combined independent review and
  new-head CI; no per-leaf full release/old48 tests or duplicate agent review.

## Runtime boundary

New Linux lock invalidates matching identity of old81-wheel metadata/admission.
Old artifacts stay unchanged as historical evidence. Future runtime remediation
needs a new matched certifi wheel/RECORD, metadata, capsule/image and admission
by the designated owner. No current host TLS path, install, restart, numerical
job, provider request or trading qualification is certified by this source patch.
