# Bounded review of the two CI test repairs

Reviewed 2026-10-13 at HEAD `cedebd13036d4db9b76368bf09f7c700e3762488`, with working changes confined to `tests/test_linux_owned.py` and `tests/test_live_router.py`. This is one review of those new repairs, not another structural review or native qualification run.

**Result: clear; no actionable P1/P2 findings.**

The Linux command fixture now uses the caller's nonzero POSIX UID/GID, retaining nonzero 10001 fallbacks for root identities and Windows. `LinuxOwnedProcess` still executes the production `os.chown` and mode assignment before container creation; neither is mocked or bypassed. The new `--user` assertion checks that the configured identity reaches the Docker command. Existing unsafe-profile checks still reject UID/GID zero. The foreign-UID test uses the real ownership boundary and requires `PermissionError` before any fake `create` call. Its non-root POSIX condition is truthful: root can assign foreign ownership, and Windows has no POSIX `chown` boundary. Short-circuit evaluation avoids accessing Windows' absent `os.geteuid`. The recorded green XML shows this negative test executed, rather than skipped. The unchanged runbook explicitly requires callers to be able to assign the configured output identity.

The state-mount comparison publishes through the actual feed, then captures the original bound `latest_state` method and wraps only that fixture instance to supply one evaluation time. Both HTTP requests still execute the production route, feed lookup, state fold, freshness evaluation and HTTP JSON serialization. It does not return a canned snapshot or patch the route. Comparing the complete raw JSON strengthens the previous contract: top-level `generated_at`, kind `age_ms`, and both levels of nested session freshness remain in the comparison. The update is published before the shared clock is captured, preserving a coherent request time.

The other live-router changes are formatting only. `format-ast.json` records identical ASTs before/after formatting. A fresh scoped `git diff --check` also exited zero. No production source files were changed in the reviewed working diff.

## Evidence inspected

- `output/0038-ci-test-repairs/red.stdout`, `red.json`, and `red.exit`: two targeted failures, exit 1; actual POSIX `chown` EPERM and retained nested freshness `evaluated_at` mismatch, using production source `bf64883f0a18e3d4e1e07c83522cbc41276abf7e`.
- `output/0038-ci-test-repairs/green.stdout`, `green.json`, `green.xml`, and `green.exit`: both complete test files, 78 passed, zero failures/errors/skips, exit 0, 23.005 seconds in XML. XML explicitly includes both repaired tests and the new foreign-owner rejection test.
- `output/0038-ci-test-repairs/format.stdout`, `format.exit`, and `format-ast.json`: formatting exit 0 and unchanged AST after the native green run.
- Current test diff, the relevant production profile/constructor/route/feed implementations, `docs/runbooks/linux-research-worker.md`, and the bounded historical diagnostic `output/0038-ci-quiet-failure-diagnosis.md`.

## Limits

This review inspected existing raw evidence and source; it did not repeat tests or operate Docker, a model, or a real provider. The green run identifies its production source as `bf64883...`; it is not a complete qualification of the current integration HEAD or old CI's Python 3.13 environment. Windows/root fallback behavior was checked in source, not newly executed. The old CI's 14 failure identities remain inferred from collection reconstruction; the two recorded red failures are direct reproductions, not proof of all historical failure identities. No OCI, Engine, model, or real-feed qualification claim follows from this review.
