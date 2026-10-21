# Iteration0021 maintenance — certifi security patch

Date:2026-10-22 Asia/Singapore. Tracking: [issue207](https://github.com/ZP151/quantmesh/issues/207),
Refs205;205 stays open and its actual-input Goal remains blocked.
Plan: docs/superpowers/plans/2026-10-22-certifi-security-patch.md.

## Planner

One action: release with the existing Python closure using the minimum fixed
certifi bundle. Outcome: audited source locks preserve their package sets and
all other versions/hashes. Isolated branch codex/0021-certifi-security-patch from
fetched origin/main aa62fae. Only four specified dependency locks and own records.
Frontend owner works independently; release owner owns combined review/CI.

## Researcher

CI39638605450 on product checkpoint a205106 failed over tracked
requirements-audit.txt: certifi2026.7.22/PYSEC-2026-4320, fixed2026.10.19.
The same pin is in both service locks, constraints and historical81-wheel intake.
This is not merely pip-audit's own tool dependency. Conditional httpx TLS paths
select certifi, while network-disabled numeric work and stdlib PG TLS have
different exposure. No current live-host use or attack is established.

Primary sources accessed2026-10-22:

- [PyPA advisory](https://github.com/pypa/advisory-database/blob/main/vulns/certifi/PYSEC-2026-4320.yaml)
  and [GitHub Reviewed advisory](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)
  select2026.10.19. The original maintainer advisory lists.18; the current
  reviewed record explains.19 restores unaffected roots after.18 removed all
  emSign roots. Use.19 as the smallest audit-supported release.
- [PyPI release](https://pypi.org/project/certifi/2026.10.19/) supplies one
  py3-none-any wheel plus sdist, Python>=3.7 and MPL-2.0. Wheel SHA256
  42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b.
  Artifact verification and resolver/audit evidence follow below.

## Implementer / verifier

Maintenance source seat accepted before writes. Existing global Python3.13 has
pip26.2.1; existing project .venv has pip-audit2.10.1. Neither checked interpreter
has pip-tools; no package/environment is installed. The root documented pip
dry-run and report path and existing official-hash lock generator are available.
All raw logs and artifact bytes belong under ignored output/0021-certifi-patch.

## Actual source checkpoint

Only certifi2026.7.22->2026.10.19 changes in four locks: six removed/six added
lines in total. Root79 packages, constraints75, Windows service77 and Linux
service81 retain their exact sets; every non-certifi block is byte-identical.
No direct dependency constraint, package, business code or test was added.

Existing pip26.2.1 resolved the static root/service dev dependency arrays against
all77 previous service pins with only certifi changed; the report exactly matches
that candidate. TOML dependency fields are static, so mechanical materialization
does not invoke a project build hook. Existing lock_service.py then regenerated
the entire Windows lock using official release JSON hashes. Its other76 blocks
remain byte-identical. Linux refresh uses the verified py3-none-any wheel hash;
its other80 selected artifacts remain unchanged.

Source SHA256 values:

| File | Updated SHA256 |
|---|---|
| requirements-audit.txt | c9cfe6390e4bba50e64137b9873b95a830a48e80a55f0aacf4f067730f7a0cb4 |
| services/research_agent/audit-constraints.txt | ef0485591efaf5f50e3b8ef2b7359c75006a118c70480bfb9c49719e41ff3204 |
| services/research_agent/requirements.lock | d956153da961e0aa9da5bc0496ed73893ef5b293216a6cae5cfb9d5296980c46 |
| services/research_agent/requirements.linux-cp312.lock | 0de42c60394ad96a6a052b1e24a8cb88f14c87f0690b3b1e2467bf857afb7ea6 |

## Verification evidence and limits

- Original CI RED is preserved as original-ci-red.log; local audit-before.json
  and audit-before.log reproduce the single certifi advisory with exit1.
- Actual public wheel bytes match PyPI's SHA256. Every hashed RECORD member is
  verified. Wheel metadata is Python>=3.7, py3-none-any, no Requires-Dist.
  Target-tag checks accept CPython3.13/Windows and3.12/Linux. This does not
  execute either target installation.
- Actual old/new CA certificates were decoded: old121/new120 certificates;
  emSign ECC Root CA - G3 present in old, absent in new; three unaffected
  emSign roots retained in new. No trust store was installed or modified.
- Actual LICENSE bytes are identical old/new, SHA256
  e93716da6b9c0d5a4a1df60fe695b370f0695603d21f6f83f053e42cfc10caf7.
  Existing repository classifier returns MPL-2.0 (documented exception), which
  is already allowed. An initial inspection helper expected the shorter
  classifier string and refused; that helper log is preserved, the result
  was checked against the existing exception and no license policy changed.
- Existing pip-audit2.10.1 ran against root79, Windows77 and Linux81 locks:
  all exit0, no known vulnerabilities. Commands use --no-deps --disable-pip
  --strict --progress-spinner off --format json, with independent JSON/logs.
  This audits pinned inputs, not the current host runtime.
- check_patch.py verifies exact package/other-byte invariance, service lock
  parsing, fixed runtime selection and universal wheel tag acceptance, actual
  parent requirements (httpx/httpcore/requests) and all three audit JSONs.
  Result PASS_TARGETED_SOURCE_CHECKS in targeted-checks.json/log.

Full root editable regeneration is NOT PROVED. The prescribed pip dry-run with
--no-build-isolation failed because the existing interpreter cannot import
setuptools.build_meta; its original failure is root-editable-backend-refused.log.
Materialized root inputs with --only-binary :all: then refused the unchanged
moomoo-api10.10.7008, which has no compatible wheel. The standard root process
does not require --only-binary. Its complete rerun belongs in existing release
tooling with a setuptools backend, allowing the existing SDK source metadata:

```text
python -m pip --isolated --disable-pip-version-check install --dry-run \
  --ignore-installed --no-build-isolation -e ".[dev,research,e2e,moomoo]" \
  --constraint requirements-audit.txt --report audit-report.json
```

Then compare sorted external name/version pairs to the root lock, excluding
quantmesh and retaining the six documented Linux-only pins. No new environment,
build dependency, SDK version or source was installed here to force success.
The root lock is honestly a certifi-only frozen-node refresh, backed by the
artifact's empty dependency list, parent constraints and successful pinned audit;
it is not represented as a successful full root regeneration.

No Windows/full release/old48 suite was run. Source self-review checks the exact
four-lock delta and whitespace; git diff --check and the fresh final targeted
artifact/source checks passed. Native installation, combined review and exact
new-head CI remain the release owner's gates, not leaf acceptance claims.

## Reviewer and runtime handoff

This leaf self-reviews only. One independent combined frontend/Python review
and exact new-head CI belong to the unique release owner, capped at two rounds.
Old81-wheel/lock/admission evidence remains untouched. Changing the Linux lock
requires new matched wheel/metadata/admission before runtime cutover; this patch
cannot establish any host, native install, image or deployment result.
