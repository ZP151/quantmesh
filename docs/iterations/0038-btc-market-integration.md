# BTC market-data-only integration

This publisher checkout combines the frozen backend and UI leaves for issue #218 on top of the already reviewed #227 candidate. The opt-in mode shows bounded BTC minute-end public REST snapshots in the existing chart while trading remains disabled. It makes no claim of provider finality, complete history, point-in-time correctness, research qualification, or order authority.

## Frozen inputs and boundary

- Backend head `d5a0819411f6d5f72a67740544ea449f57ffeb13` (tree `0b3bb571387fef5e6f7ed2a5fc5d7fd549c5f5a7`) from main `7c49d341a40eb000ffd95cac0e4a56e06fc9d336`. Its R1 two important recovery findings were corrected in the same reviewed aggregate; original reviewer R2-known verdict is READY. Its handoff is `output/market-data-only/HANDOFF.json` in the source checkout, SHA-256 `717214961342eee10c70f4e21114aed7fd70631aa97ef1e01119cec67854a59c`.
- UI head `5ec1362bf20d563683801f671333e2a8fdec4e62` (tree `a25d19d8d1a9e357a87f76115919620b65f47778`) from the same main. Its R1 verdict is READY. Its handoff is `output/market-data-ui/HANDOFF.json` in the source checkout, SHA-256 `f1069c58e49981e7257bd62a76c6d55d5b3e165529c0e45084b8d8b5ab2c6079`.
- The shared interface contract `QM-BTC-MARKET-DATA-ONLY-v1` has SHA-256 `f7278698f20f676801058395044bdea4ca7f8e4ce855d9d0c7543ccd4ce628c0`. Both leaves are immutable and their 17 changed path blobs match the originals after clean cherry-picks, with no source conflict or manual merge resolution.
- The integration starts from #227 head `d1fb5e0c37ef2b085bf53ba4785cc2177401408a`, retaining its separate release-gate repair and preserving its own CI/merge boundary. The market leaf will be rebased onto #227's actual merged main tree before publication. It does not alter 8880/8881 previews or start a provider session.

## Local combination checks

The combined backend's three affected files passed 59 tests with six existing dependency warnings. The combined UI passed 65 tests across its two new files and the existing workspace file. OpenAPI client generation produced no tracked delta; `check:api` is current when `PYTHONPATH` points to this exact combined `src`. The single packaging build produced the committed SPA bundle, with no TypeScript/build failure. Scoped frontend lint and whitespace checks passed. No broad local suite, old browser acceptance or live provider request was repeated.

The only publisher code delta beyond the frozen leaves is the packaged SPA asset set. The complete combination still requires integration-delta review, exact-head required CI after publication, and operator-owned native evidence from two distinct newly completed minutes with normal stop/close/cold read. Those checks must use the exact final merged source, PID and URL. A fixture or old cached bar cannot stand in for native acceptance. Paper mode remains true and live trading false.
