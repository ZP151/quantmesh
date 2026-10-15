# Portfolio verifier Standards review R2

Decision: R1's actual initdb descendant P2 is closed on exact candidate `084c86316066297f2c817ce2380cb49099d4ee41`. No concrete remaining P1/P2 finding was established in this capped, narrow R2 review. Accept the bounded local Task 2 verifier scope for parent integration.

Reviewed the R2 delta from `a9b9ec693218069dc11dcacfc8f16e65cd77a4f5` in `C:/Users/15492/.codex-clean/worktrees/b7a1/QuantMesh`; HEAD matched, worktree was clean, and the total delta from reviewed implementation `b10762883edc1bbad164951d1a1adfb9f0f7457c` remains the three approved leaf files. Historical helpers remain unchanged. This review read the new fix, tests, and targeted native evidence; it did not modify source/runtime/binaries/clusters, repeat a full suite, run the old model path, or perform remote/paid/production operations.

## Closed R1 P2

The new `Commands.spawn` establishes an isolated session at launch. `Child.identity/scan` admit family members only after checking kernel group/session, current UID, start ticks, executable/hash, and inherited command owner nonce. The direct Popen child also requires its exact argv. A pidfd is opened and the generation is rechecked before registration. Admitted shell-to-pinned-image transitions remain recorded within the same generation.

`Child.close` freezes only positively identified members through pidfds, rescans until the identified family is stopped and stable, then sends per-pidfd signals. It does not send blind PID or process-group kills. Unknown live membership refuses cleanup; the exception path resumes only eligible members that the qualifier paused. Freeze and terminal waits use a three-second cleanup deadline, family registration is capped at 128 members, and pending ownership/terminal failures cannot produce successful cleanup. The temporary current-process subreaper is reference counted, restores its previous setting after the last clean close, and reaps only positively registered member PIDs. These changes remain inside the new verifier leaf.

The real regression first reproduces the previous defect at RED candidate `642b3f3e0cca670d0826132242e8a9fe365a2063`: initdb PID `58126` exited `-9` while owned stopped PostgreSQL bootstrap PID `58134` remained nonterminal. Its separate test custodian retired the leaked fixture only after recording failure.

The final exact-candidate native regression records initdb PID `62068`, shell PID `62075`, and PostgreSQL bootstrap PID `62076`, all terminal with exit `-9`. The shell and bootstrap were reaped by `owned_subreaper`; parent was reaped by `owned_Popen`. The bootstrap's pidfd was terminal **before** test fallback. `test_fallback_retired_leak` is absent, and sibling PID `62067` was still alive after qualifier cleanup. This closes the original observed failure without relying on custodian rescue.

Exact regression evidence:

- `C:/Users/15492/.codex-clean/worktrees/b7a1/QuantMesh/output/portfolio-budget-native/actual-native/test-witness-49a582866a944082901876140ab05141-test_actual_initdb_bootstrap_d0/bootstrap-cleanup.json`
- `command-001.json`, `command-001.stdout`, `command-001.stderr` in the same directory, including family identities, pidfd-terminal outcomes, signals, image hashes, and reaping receipts.

The actual deliberately unmarked live-member test checks that qualifier collection refuses ownership, the unknown member and direct parent remain alive, no registered member receives a qualifier signal, and the command receipt retains `exit=null` with `terminal=false`. The fixture is retired afterward using a separate test-only custody marker. Thus unknown membership is preserved and remains visibly unqualified. Raw receipt: `output/portfolio-budget-native/r1-unit-family-evidence/test_unknown_live_member_is_pr0/command-001.json` in the reviewed workspace; the exact native JUnit/stdout records that physical test passing.

## Targeted evidence verification

- Final native receipt binds exact `084c86316066297f2c817ce2380cb49099d4ee41` and records exit 0, `37 passed in 20.45s`, zero failures/skips. The invocation uses `-B`, `PYTHONDONTWRITEBYTECODE=1`, disabled pytest plugin/cache discovery, the admitted source paths, an explicit owned profile, and fresh output.
- Independently checked 12 selected current-manifest entries and all 20 success command stdout/stderr hashes: no mismatches. Both selected exact-head witness hashes matched the handoff. Observer/dump hashes matched; captured/restored seven-table JSON bytes were identical; the negative witness's source state still matched captured source.
- Success witness has source/sibling/restored postmasters `61256/61282/61770`, all exit 0, ten fixed command handles terminal and 19 registered family members terminal. Failure-injection witness remains `passed=false`, with postmasters `61932/61958` both exit 0, four fixed command handles terminal and no cleanup failures. Known private-input inventory is empty.
- The two-process last-slot race, independent SQL observation before scripted invocation, real dump/restore, both-category exhaustion, and all seven accounting negatives remain present on the exact fixed candidate. No policy/high-water/clock accounting reset was introduced by this fix.
- Before/after dependency receipts record 81 exact-lock packages/licenses, 6,669 RECORD entries and zero bytecode, with builder paths excluded. These existing native tests/admissions were inspected, not rerun by R2. `git diff --check` for the exact R2 delta passed.
- The handoff SHA256 is `f3a82504de3a40577c812d8be52485b9dabcfbd73a8fc7dc2959ded5c2b796d7`, matching its final manifest-check receipt. That receipt records 687 verified raw entries, zero mismatches, and journal finalization before hashing. Original 650-byte journal and previous mutable pointer/inventory versions are retained under their original hashes with the mismatch history; no earlier database witness is rewritten as a repair. The full 687-entry audit is root's verification, while this Standards review independently checked the selected entries above.

Acceptance remains `OWNED_LOCAL_POSTGRES_SCRIPTED_PORTFOLIO_ONLY`. Real model/provider billing, native numerical Worker/Engine, production TLS, off-host backup, protected source host, p95, trading and human release qualification remain false or pending; paid and real provider calls remain zero. R2 closes the bounded verifier finding and does not expand those release claims.
