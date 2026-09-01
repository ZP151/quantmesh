param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$ReportRoot,
    [Parameter(Mandatory = $true)][string]$DailyRunRoot,
    [Parameter(Mandatory = $true)][string]$ConnectionRunRoot,
    [Parameter(Mandatory = $true)][string]$OutboxRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedCommit,
    [Parameter(Mandatory = $true)][string]$ExpectedSourceContractId,
    [string]$FormalTaskName = 'QuantMesh Daily Soak',
    [string]$ConnectionTaskName = 'QuantMesh Connection Witness',
    [ValidateSet('scheduled', 'supplemental')][string]$ExecutionKind = 'scheduled',
    [string]$ScheduledSlot,
    [double]$FormalDeadlineSeconds = 3600,
    [double]$StaleAfterSeconds = 93600,
    [double]$MatchEarlySeconds = 120,
    [double]$MatchLateSeconds = 900,
    [double]$PythonTimeoutSeconds = 10,
    [double]$TcpTimeoutSeconds = 5,
    [double]$SchedulerTimeoutSeconds = 15,
    [double]$SlotIdentityMaxAgeSeconds = 900,
    [double]$SlotLeaseSeconds = 900,
    [double]$DailyReceiptTimeoutSeconds = 10,
    [double]$MoomooTimeoutSeconds = 30,
    [double]$HyperliquidTimeoutSeconds = 15,
    [switch]$EmitInvocation
)

$ErrorActionPreference = 'Stop'
$RootInputs = @($Repo, $ReportRoot, $DailyRunRoot, $ConnectionRunRoot, $OutboxRoot)
if ($RootInputs.Where({ -not [IO.Path]::IsPathRooted($_) }).Count -ne 0) {
    throw 'Repository and evidence roots must be absolute paths'
}
$ResolvedRepo = [IO.Path]::GetFullPath($Repo)
$Python = Join-Path $ResolvedRepo '.venv\Scripts\python.exe'
$Driver = Join-Path $ResolvedRepo 'tools\connection_witness.py'

if (-not (Test-Path -LiteralPath $ResolvedRepo -PathType Container)) {
    throw "Repository does not exist: $ResolvedRepo"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Pinned Python interpreter does not exist: $Python"
}
if (-not (Test-Path -LiteralPath $Driver -PathType Leaf)) {
    throw "Tracked connection witness does not exist: $Driver"
}

$Arguments = @(
    $Driver,
    '--repo', $ResolvedRepo,
    '--report-root', [IO.Path]::GetFullPath($ReportRoot),
    '--daily-run-root', [IO.Path]::GetFullPath($DailyRunRoot),
    '--connection-run-root', [IO.Path]::GetFullPath($ConnectionRunRoot),
    '--outbox-root', [IO.Path]::GetFullPath($OutboxRoot),
    '--formal-task-name', $FormalTaskName,
    '--connection-task-name', $ConnectionTaskName,
    '--expected-commit', $ExpectedCommit,
    '--expected-source-contract-id', $ExpectedSourceContractId,
    '--execution-kind', $ExecutionKind,
    '--formal-deadline-seconds', $FormalDeadlineSeconds,
    '--stale-after-seconds', $StaleAfterSeconds,
    '--match-early-seconds', $MatchEarlySeconds,
    '--match-late-seconds', $MatchLateSeconds,
    '--python-timeout-seconds', $PythonTimeoutSeconds,
    '--tcp-timeout-seconds', $TcpTimeoutSeconds,
    '--scheduler-timeout-seconds', $SchedulerTimeoutSeconds,
    '--slot-identity-max-age-seconds', $SlotIdentityMaxAgeSeconds,
    '--slot-lease-seconds', $SlotLeaseSeconds,
    '--daily-receipt-timeout-seconds', $DailyReceiptTimeoutSeconds,
    '--moomoo-timeout-seconds', $MoomooTimeoutSeconds,
    '--hyperliquid-timeout-seconds', $HyperliquidTimeoutSeconds
)
if ($ExecutionKind -eq 'supplemental') {
    if ([string]::IsNullOrWhiteSpace($ScheduledSlot)) {
        throw 'ScheduledSlot is required for supplemental execution'
    }
    $Arguments += @('--scheduled-slot', $ScheduledSlot)
} elseif (-not [string]::IsNullOrWhiteSpace($ScheduledSlot)) {
    throw 'ScheduledSlot is forbidden for scheduled execution'
}

if ($EmitInvocation) {
    [ordered]@{ python = $Python; arguments = $Arguments } | ConvertTo-Json -Compress -Depth 4
    exit 0
}

& $Python @Arguments
exit $LASTEXITCODE
