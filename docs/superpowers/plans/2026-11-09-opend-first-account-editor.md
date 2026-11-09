# First ACCOUNT editor implementation plan

> Execute inline with TDD and one independent narrow review. Preparation only.

**Goal:** Prepare the complete current6b4 two-stage candidate, without real input.
**Architecture:** Reuse immutable BoundPane, framing, Journal and normal login;
add a destination/editor policy, UserName-only accessor and delayed-material
client. Build exact offline derived entry/caller/channel and immutable pins.
**Tech stack:** Existing Python stdlib/Windows CredEnumerate/Linux held FDs.
**Spec:** ../specs/2026-11-09-opend-first-account-editor.md

## Constraints and review focus

No host/Vault/input/SDK/service/browser changes during preparation. New source
under .superpowers/sdd/opend-input-path-20261109/first-account-01; preserve all
observation originals. Default original sources stay byte-identical. Cover
unresolved journal intent, stale native identity/TTY, false echo/editor ACK,
generic/duplicate input and early password access. No broad old wire suites.

## One bounded candidate

- [x] Write test_first_account.py against the real original pure grammar and
  Journal plus inert synthetic OS/transport seams. Run Python313 -I -S -B and
  retain RED proving the missing route, then implement minimal username_only.py,
  account_editor.py and account_client.py; retain GREEN.
- [x] Build create-only candidate via build_candidate.py. Verify original input
  publication c7263a47 and every dependency, exact replacement counts, compile,
  source delta and complete geometry. No operational entrypoint is invoked.
- [x] Run focused tests/Ruff/format/whitespace, freeze PUBLICATION.json, request
  bounded independent source/spec review; at most one consolidated fix/R2.
- [ ] Record real metadata plus candidate limits, central512KiB receipt imported
  net0 into complete software/runtime forecast, checkpoint and iteration. Commit
  and push the coherent green preparation on the existing integration branch.
- [ ] Give Parent exact candidate/review/pub/forecast, remaining actual source
  publication/admission work and risks. Stop before any real account paste,
  Enter, material, SDK or service action. Main stays inert until actual ruling.
