# Iteration 0021 — isolated dependency security base

## Scope and source mapping

This security-only publication is based directly on actual `origin/main` at
`aa62faeddd84c31887e43bf0dae532e649a4ecbe`. It consists only of four selected
source commits, applied with `git cherry-pick -x` so each source object and the
resulting normal integration commit are recorded here:

| Source commit | Integrated commit | Payload |
| --- | --- | --- |
| `ad9b67e2f3a57dd49f279d583395c4f3a6424da8` | `be3181833a660a597c538274b551363eb7106d52` | Certifi 2026.10.19 in the existing audit and Python lock inputs, with artifact hashes and its original evidence record. |
| `d7d1271644efe289b7922062a661d9eaa3164593` | `15d3762285da880bce01ad481f58f795e7b4af5b` | Frontend Vite/Vitest security closure, generated lock, license/provenance checker, focused security tests, and required Node type declaration. |
| `f74fe0428f66de0fe4f6be2182af2234a56f2e09` | `80a6d14d77dc144140b1dd5860904f66348548cf` | Original frontend checkpoint correction. |
| `791f6a6c472966e4569f3c815f04debec62b5737` | `b8bd0aedba8f13b0df6ecac1cff68ab9d7a807d6` | Test-only historical lock fixture and independently resealed current-lock refusal controls, with its original evidence records. |

The resulting diff contains 19 paths: those four commits' source files, tests,
plans, and iteration records. It does not include the PR206 SPY tool or other
feature payload, R441, L, diagnostic workflow/script, release-gate changes, or
any host/production admission change. The legacy lock is inert test data and is
never used as a current runtime certificate.

## Reused evidence and limits

The Certifi leaf record preserves the official wheel hashes, three pinned audit
receipts, and its explicit limitation that full root regeneration was not
proved. The frontend leaf record preserves the focused security-test results,
license/provenance checks, accepted-lock install and local build evidence. The
separate PR206 exact-head run remains authoritative for its integration result:
its fast gate passed, while release failed at the Linux Lightning CSS native
bundle load. The later isolated diagnostic run `39701476276` directly loaded
both locked native packages after one clean `npm ci`, but did not run the bundle
build and does not explain the earlier intermittent failure.

The 791 leaf retains the historical-fixture RED/GREEN and 116-pass affected-test
receipts, source hashes, and R2 round-two independent review. The existing
independent combined review found no actionable findings. Neither result is a
human approval or a runtime admission. No local 5554/545 suites were repeated
for this integration.

## Classification and gates

This changes dependency security inputs and a trust-bundle version, so the full
diff is treated as Class C under `docs/agents/review-policy.md`: two human
reviews including the safety owner, green required CI, paper-mode regression,
and explicit operator acceptance remain distinct gates. The exact new-head CI
for this security-only commit is the next verification step. The repository
gate classifier on the selected source diff returns `tier: release` with six
safety-path reasons across the frontend lock/manifest, Python audit input,
historical fixture, frontend security tests, and license checker. A green security
source result would not admit a newly built worker runtime, certify a host
installation, or resolve the separately recorded Lightning CSS bundle failure.
