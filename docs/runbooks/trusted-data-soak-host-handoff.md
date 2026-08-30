# Trusted-data soak host handoff

Status: local scheduler retirement approved on 2026-08-31

Tracking:

- [#124 — 168h soak daily witness](https://github.com/ZP151/quantmesh/issues/124)
- [#127 — two-hour connection witness](https://github.com/ZP151/quantmesh/issues/127)
- branch `0021-soak-finalize`
- approved repair design:
  `docs/superpowers/specs/2026-08-29-trusted-data-soak-reliability-repair-design.md`
- executable repair plan:
  `docs/superpowers/plans/2026-08-29-trusted-data-soak-reliability-repair.md`

## Purpose and authority

This document is the durable handoff from workstation `LAPTOP-EGHJ7IJ1` to a
different execution host. The old workstation is no longer an authorized soak
or witness scheduler after the handoff commit is pushed and the retirement
checks below pass.

The selected topology keeps the original five-target acceptance contract:

- Codex Cloud or another clean development host may implement, test, review
  and push the repair plan;
- a continuously available Windows execution host owns Moomoo OpenD, the real
  five-target collection, immutable local evidence and Windows scheduling;
- GitHub issues provide the independent remote witness;
- the old laptop must not run a second scheduler after ownership transfers.

Codex Cloud alone cannot replace the Windows runtime boundary. OpenD requires
an interactive Moomoo login and exposes a loopback service. Credentials,
passwords, phone numbers and unlock secrets must never be copied into the
repository, Codex prompts, fixtures, logs or host-transfer artifacts.

This handoff does not authorize orders, release promotion, live trading,
synthetic evidence, evidence rewriting or a weaker quality policy.

## Repository state handed off

The durable source of truth is the pushed remote branch
`origin/0021-soak-finalize`. Before this handoff checkpoint, the branch carried
seven local commits beyond remote parent `dfff3df`:

| Commit | Durable change |
| --- | --- |
| `d6e9b23` | reject unavailable, malformed or evidence-free Moomoo results before observation |
| `3b5522b` | harden and document the daily Windows schedule |
| `287be34` | support the Python 3.14 research closure with `arch` 8 |
| `87b4855` | record correct Moomoo OpenD activation |
| `795281c` | record isolated soak simulations and their limits |
| `23783e6` | record the approved reliability-repair design |
| `ad6b49f` | record the executable TDD reliability-repair plan |

After cloning, resolve the exact handoff head rather than trusting a copied
hash:

```powershell
git fetch origin
git switch --detach origin/0021-soak-finalize
git status --short --branch
git rev-parse HEAD
```

The checkout must be clean. A scheduled runner must never execute a mutable
developer checkout or an unpushed commit.

## Acceptance state at retirement

The current evidence root is rejected and cannot contribute time to a later
168-hour claim.

- Formal roots on the old host:
  `C:\QuantMesh\trusted-data` and `C:\QuantMesh\evidence-v2`.
- Witness results on the old host:
  `C:\QuantMesh\witness-test\results`.
- The last formal task attempt was
  `2026-08-30T17:47:50+08:00`, result `0x00000001`.
- No immutable daily report exists for 2026-08-30. The incident is recorded at
  [#124 comment 5467966561](https://github.com/ZP151/quantmesh/issues/124#issuecomment-5467966561).
- The last local connection result observed before retirement started at
  `2026-08-31T00:00:03+08:00`, run ID
  `a69920e151191373bfe398f11cfeee5bcd46d986342a13b8f6280115a6bcd1b8`.
  OpenD, loopback TCP, Moomoo, Hyperliquid, Scheduler and repository import
  passed; the overall result failed because the formal task remained
  `0x00000001`.

Do not copy only `evidence-v2` and call it a continuation. Its reports bind
local filesystem times, exact manifests, the frozen candidate and predecessor
chain. Preserve the old roots read-only for audit. After the reliability plan
passes, create the new candidate on the new Windows host in a new empty root as
specified by the plan.

## Retired local schedules

The following definitions describe the old host at retirement. They are
diagnostic evidence, not an instruction to recreate the known-broken topology.

### Formal daily task

- Name: `QuantMesh Daily Soak`.
- Trigger: daily at `08:00` Asia/Singapore.
- Interpreter:
  `C:\Users\15492\Develop\quantmesh\.venv\Scripts\python.exe`.
- Command:
  `tools\soak_daily.py --repo C:\Users\15492\Develop\quantmesh
  --data-root C:\QuantMesh\trusted-data
  --evidence-root C:\QuantMesh\evidence-v2`.
- Interactive-user principal, non-elevated.
- Start when available, wake to run and battery execution enabled.
- Ignore overlapping starts, one-hour execution limit, three retries at
  15-minute intervals.

### Two-hour connection task

- Name: `QuantMesh 2h Connection Witness`.
- Trigger: every two hours from minute `00`.
- Script: `C:\QuantMesh\witness-test\probe.ps1`.
- Script SHA-256:
  `2070cbe666e07f345249fc25876dd093d9b8938805afc2ffda26b2301cf2af98`.
- Inputs: repository path, result root and the installed `moomoo_OpenD.exe`.
- Output: mutable `latest.json` plus per-run JSON under `results\runs`.
- Start when available, wake to run and battery execution enabled.
- Ignore overlapping starts, 15-minute execution limit, three retries at
  five-minute intervals.

The script lived outside the repository and is therefore not a reproducible
runner. The repair plan replaces it with a version-controlled,
deadline-bounded state machine before a new candidate starts.

### Codex witness heartbeat

- ID: `quantmesh-daily-witness`.
- Previous status: `ACTIVE`.
- Previous recurrence: every two hours at minute `15`.
- It read the old host's local task/result paths, deduplicated issue comments
  by `run_id` or `report_id`, posted #127 pass/failure results, and posted at
  most one formal #124 result per day after full verification.

The heartbeat is paused at retirement because its prompt is tied to the old
host and old roots. The replacement publisher must be installed only after the
new host implements the durable outbox/single-writer contract in the approved
plan.

## Incident ledger and lessons

### Provider and environment boundaries

1. The first gateway download was a Futu-family OpenD package and rejected the
   Moomoo Singapore account even though the web login worked. Installing the
   signed Moomoo OpenD package and authenticating interactively resolved the
   account-family mismatch.
2. Python 3.14 initially lacked a compatible older `arch` wheel. The dependency
   contract was moved to `arch>=8,<9`; CPython 3.14.7 then passed the recorded
   full suite.
3. A missing or logged-out OpenD caused honest Moomoo unavailability. A prior
   daily driver treated the CLI's zero exit code as success without validating
   the typed result. Commit `d6e9b23` closes that specific false-green path.
4. A pre-close/manual collection returned the latest completed Friday session
   and correctly failed the 172800-second freshness policy. The policy was not
   relaxed; the scheduled post-close window was the intended remedy.

### Evidence and verifier failures

5. A 39.5-hour laptop sleep/hibernate gap broke continuous cadence. A missed
   interval cannot be backfilled and invalidates the candidate.
6. Moomoo revised one NVDA raw daily row for 2026-08-27. Only `turnover`
   changed, from `67,700,954,784.651` to `67,628,318,193`; fingerprint
   `6e30bad00d3e0df50794a426c09c6ca01701b2bcda98a39f1cd684bfde1eb0a9`.
   The overlap rejection is correct and remains immutable.
7. The formal driver could finish zero after writing a report that the complete
   verifier rejected. The approved plan makes full verification determine the
   terminal task result and records immutable stage receipts.

### Scheduling and probe failures

8. The formal task and connection witness both started at the top of the hour.
   At 08:00 the witness interpreted the legitimate formal state
   `Running/0x41301` as a failure and competed for OpenD.
9. Probe child processes lacked hard deadlines. Observed runs degraded from
   seconds to 128, 223, 426 and 621 seconds; scheduled probes were terminated
   with `0x41306` or `0xC000013A` and sometimes left `latest.json` stale.
10. At 2026-08-30 08:00 the laptop schedule did not run. Start-when-available
    later launched the formal task and connection task together at 17:47,
    reproducing the collision; the formal task ended `0x00000001`.
11. The witness treated any non-zero formal last result as an overall
    connection failure even when OpenD, Moomoo and Hyperliquid were healthy.
    This was useful negative evidence but did not distinguish connectivity from
    formal-soak validity.

### Remote publication failures

12. The original Windows task had no GitHub publication action, so successful
    local work could remain absent from #124 until a separate publisher ran.
13. Check-then-post publication was not a single-writer protocol. The 2026-08-28
    14:00 witness produced duplicate comments; two were later marked
    superseded.
14. Network interruption and a stopped/sleeping host delayed or omitted
    publication. Supplemental runs were necessary, including
    [the 2026-08-30 recovery](https://github.com/ZP151/quantmesh/issues/127#issuecomment-5467965902)
    and
    [the 22:00 terminated-slot supplement](https://github.com/ZP151/quantmesh/issues/127#issuecomment-5469523457).

These failures are why the new host must execute the repair plan before
starting a replacement 168-hour clock. Simply recreating the old tasks on a
more available host is not acceptance.

## New-host resume sequence

### Development in Codex Cloud or another clean host

1. Clone `ZP151/quantmesh` and fetch `origin/0021-soak-finalize`.
2. Read `AGENTS.md`, `CONTEXT.md`, `docs/goals/ACTIVE.md`, the Iteration 0021
   ledger, the approved repair design and the executable plan.
3. Confirm issues #124 and #127 and the latest branch head from GitHub. Chat
   history and the old laptop are not sources of truth.
4. Execute the repair plan from its first incomplete task with TDD, bounded
   commits, review and fresh verification. Preserve paper/read-only defaults.
5. Push each accepted checkpoint. Do not register a real runner against an
   unpushed or dirty commit.

### Windows execution-host prerequisites

1. Use an always-on Windows host with automatic time synchronization and
   enough retained disk for trusted data, evidence, run receipts and logs.
2. Install Python 3.14 and create a fresh environment from the pinned branch:

   ```powershell
   py -3.14 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -e ".[dev,research,e2e,moomoo]"
   .\.venv\Scripts\python.exe -m pip check
   ```

3. Install the official signed Moomoo OpenD, authenticate interactively and
   keep it on loopback port `11111`. Do not automate or transfer credentials.
4. Confirm read-only capabilities with `quantmesh-moomoo probe` and confirm
   Hyperliquid public API access. A capability named `order` does not authorize
   an order; the soak uses quote/history only.
5. Complete the repair plan's automated checks and injected-failure drills.
6. Create a new empty trusted-data/evidence/run root only after the repair
   runner is pushed and verified. Do not import passing duration from
   `evidence-v2`.
7. Register the repaired staggered schedule: daily collection at 08:00,
   connection witness at minute 10 and publisher at minute 20. Round-trip the
   actual definitions and run each once before starting the 168-hour clock.
8. Publish one explicit restart/handoff witness to #124 and one scheduler
   acceptance witness to #127. Read both comments back and store their URLs in
   immutable publication receipts.

## Retirement and rollback checks

The old host retirement is complete only when all of the following are true:

- the handoff commit is visible at `origin/0021-soak-finalize`;
- `QuantMesh Daily Soak` is disabled and not running;
- `QuantMesh 2h Connection Witness` is disabled and not running;
- Codex automation `quantmesh-daily-witness` is paused;
- #124 and #127 contain a handoff notice with the pushed commit;
- the old trusted-data, evidence and witness files remain unchanged.

Rollback is explicit: re-enable nothing on the old host unless the new-host
transfer is abandoned and a new operator decision names the old host as the
single scheduler authority. Never permit both hosts to own the same slot.
