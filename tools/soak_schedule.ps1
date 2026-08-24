# Register the daily QuantMesh soak observation in Windows Task Scheduler.
# Run once per UTC day; the script is idempotent (one report per UTC day).
#
#   .\tools\soak_schedule.ps1 -Repo C:\...\QuantMesh-0021-finalize `
#       -DataRoot C:\QuantMesh\trusted-data `
#       -EvidenceRoot C:\QuantMesh\trusted-data-evidence
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [string]$TaskName = "QuantMesh Daily Soak",
    [string]$At = "08:00"
)

$python = Join-Path $Repo ".venv\Scripts\python.exe"
$driver = Join-Path $Repo "tools\soak_daily.py"
if (-not (Test-Path $python)) { throw "python not found: $python" }
if (-not (Test-Path $driver)) { throw "driver not found: $driver" }

$action = "`"$python`" `"$driver`" --repo `"$Repo`" --data-root `"$DataRoot`" --evidence-root `"$EvidenceRoot`""
schtasks /Create /TN $TaskName /TR $action /SC DAILY /ST $At /F
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew
Set-ScheduledTask -TaskName $TaskName -Settings $settings | Out-Null
schtasks /Query /TN $TaskName /FO LIST
