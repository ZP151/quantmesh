# Trusted-data soak scheduling runbook

Status: installation and verification procedure; it does not authorize a
candidate clock, publication, release promotion or trading.

## Safety boundary

The repaired Windows schedule has one daily collection task at 08:00 local
time and one connection witness every two hours from minute 10. The separate
publisher is intentionally outside this installer and, if admitted by Task 9B,
runs at minute 20 under the single-authority outbox protocol.

Keep both owned tasks disabled unless all of these conditions hold:

- the execution host is explicitly designated as the sole scheduler authority;
- every legacy task and publisher on the former host is disabled and not
  running, with administrator-confirmed read-back;
- the checkout is clean, its exact commit is reachable from the configured
  remote integration ref, and its pinned interpreter/environment is final;
- Moomoo OpenD is authenticated interactively and only read-only market-data
  capabilities are used;
- the trusted-data, evidence, daily-run, connection-run, outbox and schedule
  manifest roots are new, absolute and pairwise disjoint; and
- Task 9B host admission and the reviewed read-only preflight have passed.

Old evidence remains audit-only. Never copy its passing duration into a new
candidate, repair immutable receipts in place, run two scheduler authorities,
or treat AI output, a provider login, a passing soak, or this runbook as order
authority.

## Prepare a frozen host configuration

Use the exact pushed candidate commit in a dedicated checkout. Confirm both
source state and the pinned environment before creating any task:

```powershell
git fetch origin
git status --porcelain
git rev-parse HEAD
git merge-base --is-ancestor HEAD origin/0021-soak-finalize
& C:\QuantMesh\runtime\.venv\Scripts\python.exe -m pip check
```

The first command below publishes a create-once `ScheduleContractV1` manifest
named by its configuration digest. The daily task pins that exact manifest;
each run reopens it and recomputes configuration, scripts, dependency files,
interpreter identity and installed distribution inventory before any provider
work begins.

Define the shared arguments once, replacing every example path and identity
with the reviewed new-host values:

```powershell
$schedule = @{
  Repo = "C:\QuantMesh\runtime\quantmesh"
  PythonPath = "C:\QuantMesh\runtime\.venv\Scripts\python.exe"
  DataRoot = "D:\QuantMesh\trusted-data-v3"
  EvidenceRoot = "D:\QuantMesh\evidence-v3"
  DailyRunRoot = "D:\QuantMesh\daily-runs-v3"
  ConnectionRunRoot = "D:\QuantMesh\connection-runs-v3"
  OutboxRoot = "D:\QuantMesh\witness-outbox-v3"
  ManifestRoot = "D:\QuantMesh\schedule-contracts-v3"
  RemoteRef = "origin/0021-soak-finalize"
  Principal = "HOSTNAME\operator"
  TimeZoneId = [System.TimeZoneInfo]::Local.Id
}
```

Do not put credentials, tokens, passwords, private keys or account unlock data
in these arguments, manifests, task actions or preflight output.

## Install disabled and verify read-only

`InstallDisabled` creates or replaces both task definitions with their
settings already disabled, explicitly disables them again, and performs a full
Scheduler read-back. Success is one JSON object with `accepted=true`, two
disabled tasks, no drift fields and no unsafe enabled task:

```powershell
& .\tools\soak_schedule.ps1 -Mode InstallDisabled @schedule
```

Inspect the returned action, trigger, principal and settings contracts. The
daily task must show 08:00, three 15-minute retries and a one-hour limit. The
connection task must show a two-hour interval from minute 10, zero automatic
retries and a 15-minute limit. Both use `IgnoreNew`, allow battery execution,
wake the host and start when available.

`Verify` is the normal audit command. It calls no Scheduler registration,
enable or disable mutation:

```powershell
& .\tools\soak_schedule.ps1 -Mode Verify -ExpectedState Disabled @schedule
```

Any missing task, extra action/trigger, field drift, source/environment drift,
unexpected enabled state or unreadable manifest returns non-zero. Preserve the
JSON output as incident evidence; do not overwrite the contract merely to
match an unexplained observed value.

## Guarded enable

Do not run this section during development or before Task 9B host admission.
The preflight executable and argument vector must be an independently reviewed,
bounded, read-only host probe. Shell command text is not accepted; arguments
are passed as a JSON argv vector through the deadline-bounded process runner.

```powershell
$preflightExe = "C:\QuantMesh\runtime\.venv\Scripts\python.exe"
$preflightArgv = @(
  "C:\QuantMesh\runtime\quantmesh\tools\reviewed_read_only_preflight.py"
)

& .\tools\soak_schedule.ps1 -Mode GuardedEnable @schedule `
  -PreflightExecutable $preflightExe `
  -PreflightArguments $preflightArgv `
  -PreflightTimeoutSeconds 900
```

The placeholder preflight path above is deliberately not supplied by Task 7;
Task 9B must name the exact accepted host probe. `GuardedEnable` first verifies
both tasks disabled, then runs that finite preflight, enables both tasks and
reads back the full enabled contracts. Any failure causes best-effort disable
of both followed by mandatory read-back. `unsafe-partial-enable` is an
incident: deny the candidate clock and use an administrator to disable the
named task before doing anything else.

After a successful enable, run a separate read-only confirmation:

```powershell
& .\tools\soak_schedule.ps1 -Mode Verify -ExpectedState Enabled @schedule
```

Publisher installation and its minute-20 cadence are verified separately.
Neither local intent creation nor the local outbox CLI can write publication
receipts; only the injected single-authority publisher may record a receipt
after remote exact-key read-back.

## Stop, incident and restart rules

On source, dependency, configuration, schedule, provider, cadence, immutable
evidence or publication ambiguity:

1. disable both owned tasks and read them back;
2. stop candidate-clock admission without backfilling a missed slot;
3. retain terminals, reports, outbox intents/failures and old roots unchanged;
4. diagnose on a copy or in an isolated test root; and
5. start a new candidate in new empty roots only after a reviewed, pushed fix
   and a fresh `InstallDisabled`/`Verify`/Task 9B admission sequence.

Re-enabling an old host requires a new explicit single-authority decision. A
failed or unavailable provider is honest negative evidence, never permission
to synthesize data, loosen quality policy, publish success or place an order.
