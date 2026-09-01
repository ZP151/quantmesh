[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("InstallDisabled", "Verify", "GuardedEnable")]
    [string]$Mode,
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$DailyRunRoot,
    [Parameter(Mandatory = $true)][string]$ConnectionRunRoot,
    [Parameter(Mandatory = $true)][string]$OutboxRoot,
    [Parameter(Mandatory = $true)][string]$ManifestRoot,
    [Parameter(Mandatory = $true)][string]$RemoteRef,
    [Parameter(Mandatory = $true)][string]$Principal,
    [Parameter(Mandatory = $true)][string]$TimeZoneId,
    [string]$TaskPath = "\QuantMesh\",
    [string]$DailyTaskName = "QuantMesh Daily Soak",
    [string]$ConnectionTaskName = "QuantMesh Connection Witness",
    [string]$DailyAt = "08:00",
    [ValidateSet("Disabled", "Enabled")][string]$ExpectedState = "Disabled",
    [double]$SourceTimeoutSeconds = 30,
    [double]$HyperliquidTimeoutSeconds = 300,
    [double]$MoomooTimeoutSeconds = 600,
    [double]$ObserveTimeoutSeconds = 600,
    [double]$VerifyTimeoutSeconds = 600,
    [double]$LeaseWaitTimeoutSeconds = 30,
    [double]$ConnectionFormalDeadlineSeconds = 900,
    [double]$ConnectionStaleAfterSeconds = 10800,
    [double]$ConnectionMatchEarlySeconds = 300,
    [double]$ConnectionMatchLateSeconds = 900,
    [double]$ConnectionPythonTimeoutSeconds = 30,
    [double]$ConnectionTcpTimeoutSeconds = 5,
    [double]$ConnectionSchedulerTimeoutSeconds = 30,
    [double]$ConnectionSlotIdentityMaxAgeSeconds = 300,
    [double]$ConnectionSlotLeaseSeconds = 900,
    [double]$ConnectionDailyReceiptTimeoutSeconds = 30,
    [double]$ConnectionMoomooTimeoutSeconds = 30,
    [double]$ConnectionHyperliquidTimeoutSeconds = 30,
    [string]$PreflightExecutable,
    [string[]]$PreflightArguments = @(),
    [double]$PreflightTimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param([string]$Value, [string]$Label, [switch]$MustExist)
    if (-not [System.IO.Path]::IsPathRooted($Value)) { throw "$Label must be absolute" }
    $resolved = [System.IO.Path]::GetFullPath($Value)
    if ($MustExist -and -not (Test-Path -LiteralPath $resolved)) {
        throw "$Label does not exist: $resolved"
    }
    return $resolved
}

function Quote-Argument {
    param([string]$Value)
    $quoted = [System.Text.StringBuilder]::new()
    $null = $quoted.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes += 1
            continue
        }
        if ($character -eq '"') {
            for ($index = 0; $index -lt (2 * $backslashes + 1); $index++) {
                $null = $quoted.Append('\')
            }
            $null = $quoted.Append('"')
        }
        else {
            for ($index = 0; $index -lt $backslashes; $index++) {
                $null = $quoted.Append('\')
            }
            $null = $quoted.Append($character)
        }
        $backslashes = 0
    }
    for ($index = 0; $index -lt (2 * $backslashes); $index++) {
        $null = $quoted.Append('\')
    }
    $null = $quoted.Append('"')
    return $quoted.ToString()
}

function ConvertTo-FlatMap {
    param([object]$Value, [string]$Prefix = "")
    $result = @{}
    if ($null -eq $Value) { $result[$Prefix] = $null; return $result }
    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in ($Value.Keys | Sort-Object)) {
            $child = if ($Prefix) { "$Prefix.$key" } else { [string]$key }
            $nested = ConvertTo-FlatMap -Value $Value[$key] -Prefix $child
            foreach ($entry in $nested.GetEnumerator()) { $result[$entry.Key] = $entry.Value }
        }
        return $result
    }
    if ($Value -is [string] -or $Value -is [ValueType]) {
        $result[$Prefix] = $Value
        return $result
    }
    if ($Value -is [pscustomobject]) {
        $ordered = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            $ordered[$property.Name] = $property.Value
        }
        return ConvertTo-FlatMap -Value $ordered -Prefix $Prefix
    }
    if (($Value -is [System.Collections.IEnumerable]) -and -not ($Value -is [string])) {
        $index = 0
        foreach ($item in $Value) {
            $nested = ConvertTo-FlatMap -Value $item -Prefix "$Prefix[$index]"
            foreach ($entry in $nested.GetEnumerator()) { $result[$entry.Key] = $entry.Value }
            $index += 1
        }
        if ($index -eq 0) { $result[$Prefix] = @() }
        return $result
    }
    $result[$Prefix] = $Value
    return $result
}

function Compare-Contract {
    param([object]$Expected, [object]$Observed)
    $left = ConvertTo-FlatMap $Expected
    $right = ConvertTo-FlatMap $Observed
    $keys = @($left.Keys) + @($right.Keys) | Sort-Object -Unique
    return @(
        foreach ($key in $keys) {
            if (-not $left.ContainsKey($key) -or -not $right.ContainsKey($key) -or
                ([string]$left[$key] -cne [string]$right[$key])) { $key }
        }
    )
}

function Convert-LogonType {
    param([object]$Value)
    $names = @{ "0" = "None"; "1" = "Password"; "2" = "S4U"; "3" = "Interactive"
        "4" = "Group"; "5" = "ServiceAccount"; "6" = "InteractiveOrPassword" }
    $text = [string]$Value
    return $(if ($names.ContainsKey($text)) { $names[$text] } else { $text })
}

function Convert-RunLevel {
    param([object]$Value)
    $text = [string]$Value
    return $(if ($text -eq "0") { "Limited" } elseif ($text -eq "1") { "Highest" } else { $text })
}

function Convert-MultipleInstances {
    param([object]$Value)
    $names = @{ "0" = "Parallel"; "1" = "Queue"; "2" = "IgnoreNew"; "3" = "StopExisting" }
    $text = [string]$Value
    return $(if ($names.ContainsKey($text)) { $names[$text] } else { $text })
}

function Convert-CanonicalPrincipalId {
    param([string]$Value)
    try {
        $account = [System.Security.Principal.NTAccount]::new($Value)
        $sid = $account.Translate([System.Security.Principal.SecurityIdentifier])
        $canonical = $sid.Translate([System.Security.Principal.NTAccount])
        return ([string]$canonical.Value).ToLowerInvariant()
    }
    catch {
        return $Value.ToLowerInvariant()
    }
}

function New-RuntimeConfig {
    param([hashtable]$Paths)
    return [ordered]@{
        runner = [ordered]@{
            repo = $Paths.Repo; data_root = $Paths.DataRoot
            evidence_root = $Paths.EvidenceRoot; run_root = $Paths.DailyRunRoot
            outbox_root = $Paths.OutboxRoot; remote_ref = $RemoteRef
            source_timeout = $SourceTimeoutSeconds
            hyperliquid_timeout = $HyperliquidTimeoutSeconds
            moomoo_timeout = $MoomooTimeoutSeconds
            observe_timeout = $ObserveTimeoutSeconds; verify_timeout = $VerifyTimeoutSeconds
            lease_wait_timeout = $LeaseWaitTimeoutSeconds
        }
        scheduler = [ordered]@{
            task_path = $TaskPath; daily_task_name = $DailyTaskName
            connection_task_name = $ConnectionTaskName; principal = $Principal
            timezone = $TimeZoneId; daily_at = $DailyAt
            connection_interval = "PT2H"; connection_minute = 10
            connection_start_boundary = "2026-01-01T00:10:00"
            connection_repetition_duration = $null
            daily_restart_count = 3; daily_restart_interval = "PT15M"
            daily_execution_limit = "PT1H"; connection_restart_count = 0
            connection_execution_limit = "PT15M"; multiple_instances = "IgnoreNew"
            wake_to_run = $true; start_when_available = $true
            disallow_start_on_battery = $false; stop_on_battery = $false
            connection_root = $Paths.ConnectionRunRoot; manifest_root = $Paths.ManifestRoot
        }
    }
}

function Invoke-SourceContract {
    param([hashtable]$Paths, [object]$RuntimeConfig, [switch]$PublishManifest)
    $temp = [System.IO.Path]::GetTempFileName()
    $oldPythonPath = $env:PYTHONPATH
    try {
        [System.IO.File]::WriteAllText(
            $temp, ($RuntimeConfig | ConvertTo-Json -Depth 20 -Compress),
            [System.Text.UTF8Encoding]::new($false)
        )
        $env:PYTHONPATH = Join-Path $Paths.Repo "src"
        $snapshotOutput = & $Paths.PythonPath -m quantmesh.ops.source_contract snapshot `
            --repo $Paths.Repo --remote-ref $RemoteRef --runtime-config-file $temp `
            --python-executable $Paths.PythonPath --timeout-seconds $SourceTimeoutSeconds
        if ($LASTEXITCODE -ne 0) { throw "source-contract snapshot failed" }
        $snapshot = $snapshotOutput | ConvertFrom-Json
        $manifestPath = Join-Path $Paths.ManifestRoot ($snapshot.config_digest + ".json")
        if ($PublishManifest) {
            $manifestOutput = & $Paths.PythonPath -m quantmesh.ops.source_contract `
                publish-manifest --manifest-root $Paths.ManifestRoot --runtime-config-file $temp
            if ($LASTEXITCODE -ne 0) { throw "source manifest publication failed" }
            $manifest = $manifestOutput | ConvertFrom-Json
            if ($manifest.config_digest -cne $snapshot.config_digest) {
                throw "source manifest digest differs from source snapshot"
            }
            $manifestPath = $manifest.manifest_path
        }
        elseif (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw "frozen source config manifest is missing: $manifestPath"
        }
        return [ordered]@{ source = $snapshot; manifest_path = $manifestPath }
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Join-Arguments {
    param([string[]]$Values)
    return (($Values | ForEach-Object { Quote-Argument $_ }) -join " ")
}

function New-ExpectedContracts {
    param([hashtable]$Paths, [object]$SourceBundle, [bool]$Enabled)
    $source = $SourceBundle.source
    $dailyArgs = @(
        (Join-Path $Paths.Repo "tools\soak_daily.py"), "--repo", $Paths.Repo,
        "--data-root", $Paths.DataRoot, "--evidence-root", $Paths.EvidenceRoot,
        "--run-root", $Paths.DailyRunRoot, "--outbox-root", $Paths.OutboxRoot,
        "--source-config-manifest", $SourceBundle.manifest_path,
        "--remote-ref", $RemoteRef, "--dependency-digest", $source.dependency_digest,
        "--script-digest", $source.script_digest, "--config-digest", $source.config_digest
    )
    $connectionArgs = @(
        "-NoProfile", "-NonInteractive", "-File",
        (Join-Path $Paths.Repo "tools\connection_witness.ps1"), "-Repo", $Paths.Repo,
        "-ReportRoot", $Paths.EvidenceRoot, "-DailyRunRoot", $Paths.DailyRunRoot,
        "-ConnectionRunRoot", $Paths.ConnectionRunRoot, "-OutboxRoot", $Paths.OutboxRoot,
        "-FormalTaskPath", $TaskPath, "-FormalTaskName", $DailyTaskName,
        "-ConnectionTaskPath", $TaskPath, "-ConnectionTaskName", $ConnectionTaskName,
        "-ExpectedCommit", $source.head_commit,
        "-ExpectedSourceContractId", $source.source_contract_id,
        "-ExecutionKind", "scheduled",
        "-FormalDeadlineSeconds", [string]$ConnectionFormalDeadlineSeconds,
        "-StaleAfterSeconds", [string]$ConnectionStaleAfterSeconds,
        "-MatchEarlySeconds", [string]$ConnectionMatchEarlySeconds,
        "-MatchLateSeconds", [string]$ConnectionMatchLateSeconds,
        "-PythonTimeoutSeconds", [string]$ConnectionPythonTimeoutSeconds,
        "-TcpTimeoutSeconds", [string]$ConnectionTcpTimeoutSeconds,
        "-SchedulerTimeoutSeconds", [string]$ConnectionSchedulerTimeoutSeconds,
        "-SlotIdentityMaxAgeSeconds", [string]$ConnectionSlotIdentityMaxAgeSeconds,
        "-SlotLeaseSeconds", [string]$ConnectionSlotLeaseSeconds,
        "-DailyReceiptTimeoutSeconds", [string]$ConnectionDailyReceiptTimeoutSeconds,
        "-MoomooTimeoutSeconds", [string]$ConnectionMoomooTimeoutSeconds,
        "-HyperliquidTimeoutSeconds", [string]$ConnectionHyperliquidTimeoutSeconds
    )
    $commonSettings = [ordered]@{
        wake_to_run = $true; start_when_available = $true
        disallow_start_on_battery = $false; stop_on_battery = $false
        multiple_instances = "IgnoreNew"
    }
    $principalContract = [ordered]@{
        user_id = Convert-CanonicalPrincipalId $Principal
        logon_type = "Interactive"; run_level = "Limited"
    }
    $dailySettings = [ordered]@{} + $commonSettings
    $dailySettings.restart_count = 3; $dailySettings.restart_interval = "PT15M"
    $dailySettings.execution_time_limit = "PT1H"
    $connectionSettings = [ordered]@{} + $commonSettings
    $connectionSettings.restart_count = 0; $connectionSettings.restart_interval = $null
    $connectionSettings.execution_time_limit = "PT15M"
    $daily = [ordered]@{
        task_path = $TaskPath; task_name = $DailyTaskName; enabled = $Enabled
        action = [ordered]@{
            execute = $Paths.PythonPath; arguments = Join-Arguments $dailyArgs
            working_directory = $Paths.Repo
        }
        trigger = [ordered]@{
            class = "MSFT_TaskDailyTrigger"; enabled = $true; kind = "daily"
            at = $DailyAt; start_boundary = $null; days_interval = 1
            interval = $null; duration = $null; stop_at_duration_end = $null; minute = $null
            timezone = $TimeZoneId
        }
        principal = $principalContract; settings = $dailySettings
    }
    $connection = [ordered]@{
        task_path = $TaskPath; task_name = $ConnectionTaskName; enabled = $Enabled
        action = [ordered]@{
            execute = [string](Join-Path $PSHOME "powershell.exe")
            arguments = Join-Arguments $connectionArgs; working_directory = $Paths.Repo
        }
        trigger = [ordered]@{
            class = "MSFT_TaskTimeTrigger"; enabled = $true; kind = "repetition"
            at = $null; start_boundary = "2026-01-01T00:10:00"; days_interval = $null
            interval = "PT2H"; duration = $null
            stop_at_duration_end = $true; minute = 10
            timezone = $TimeZoneId
        }
        principal = $principalContract; settings = $connectionSettings
    }
    return @($daily, $connection)
}

function New-TaskObjects {
    param([object]$Contract)
    $action = New-ScheduledTaskAction -Execute $Contract.action.execute `
        -Argument $Contract.action.arguments -WorkingDirectory $Contract.action.working_directory
    if ($Contract.trigger.kind -eq "daily") {
        $trigger = New-ScheduledTaskTrigger -Daily -At $Contract.trigger.at
    }
    else {
        $anchor = [datetime]::SpecifyKind(
            [datetime]::ParseExact(
                $Contract.trigger.start_boundary,
                "yyyy-MM-ddTHH:mm:ss",
                [System.Globalization.CultureInfo]::InvariantCulture
            ),
            [System.DateTimeKind]::Unspecified
        )
        $trigger = New-ScheduledTaskTrigger -Once -At $anchor `
            -RepetitionInterval ([timespan]::FromHours(2))
    }
    $principalObject = New-ScheduledTaskPrincipal -UserId $Principal `
        -LogonType Interactive -RunLevel Limited
    $settingsArguments = @{
        StartWhenAvailable = $true; AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true; WakeToRun = $true
        ExecutionTimeLimit = [System.Xml.XmlConvert]::ToTimeSpan(
            $Contract.settings.execution_time_limit
        )
        MultipleInstances = "IgnoreNew"
    }
    if ($Contract.settings.restart_count -gt 0) {
        $settingsArguments.RestartCount = $Contract.settings.restart_count
        $settingsArguments.RestartInterval = [System.Xml.XmlConvert]::ToTimeSpan(
            $Contract.settings.restart_interval
        )
    }
    $settings = New-ScheduledTaskSettingsSet @settingsArguments
    $settings.Enabled = [bool]$Contract.enabled
    return [ordered]@{
        Action = $action; Trigger = $trigger; Principal = $principalObject; Settings = $settings
    }
}

function Get-NormalizedTask {
    param([object]$Expected)
    $task = Get-ScheduledTask -TaskPath $Expected.task_path -TaskName $Expected.task_name
    $null = Get-ScheduledTaskInfo -TaskPath $Expected.task_path -TaskName $Expected.task_name
    $actions = @($task.Actions); $triggers = @($task.Triggers)
    if ($actions.Count -ne 1 -or $triggers.Count -ne 1) {
        return [ordered]@{
            task_path = $task.TaskPath; task_name = $task.TaskName
            action_count = $actions.Count; trigger_count = $triggers.Count
        }
    }
    $action = $actions[0]; $trigger = $triggers[0]
    $triggerClass = [string]$trigger.CimClass.CimClassName
    $repetitionInterval = $null
    if ($null -ne $trigger.Repetition) { $repetitionInterval = [string]$trigger.Repetition.Interval }
    $repetitionDuration = $null
    if ($null -ne $trigger.Repetition -and $trigger.Repetition.Duration) {
        $repetitionDuration = [string]$trigger.Repetition.Duration
    }
    $kind = if ($repetitionInterval -and $repetitionInterval -ne "PT0S") { "repetition" } else { "daily" }
    $start = [datetimeoffset]::Parse([string]$trigger.StartBoundary)
    $localStart = [System.TimeZoneInfo]::ConvertTime($start, [System.TimeZoneInfo]::Local)
    $settings = $task.Settings; $restartCount = [int]$settings.RestartCount
    return [ordered]@{
        task_path = [string]$task.TaskPath; task_name = [string]$task.TaskName
        enabled = [bool]$settings.Enabled
        action = [ordered]@{
            execute = [string]$action.Execute; arguments = [string]$action.Arguments
            working_directory = [string]$action.WorkingDirectory
        }
        trigger = [ordered]@{
            class = $triggerClass; enabled = [bool]$trigger.Enabled; kind = $kind
            at = if ($kind -eq "daily") { $localStart.ToString("HH:mm") } else { $null }
            start_boundary = if ($kind -eq "repetition") {
                $localStart.ToString("yyyy-MM-ddTHH:mm:ss")
            } else { $null }
            days_interval = if ($kind -eq "daily") { [int]$trigger.DaysInterval } else { $null }
            interval = if ($kind -eq "repetition") { $repetitionInterval } else { $null }
            duration = if ($kind -eq "repetition") { $repetitionDuration } else { $null }
            stop_at_duration_end = if ($kind -eq "repetition") {
                [bool]$trigger.Repetition.StopAtDurationEnd
            } else { $null }
            minute = if ($kind -eq "repetition") { $localStart.Minute } else { $null }
            timezone = $TimeZoneId
        }
        principal = [ordered]@{
            user_id = Convert-CanonicalPrincipalId ([string]$task.Principal.UserId)
            logon_type = Convert-LogonType $task.Principal.LogonType
            run_level = Convert-RunLevel $task.Principal.RunLevel
        }
        settings = [ordered]@{
            wake_to_run = [bool]$settings.WakeToRun
            start_when_available = [bool]$settings.StartWhenAvailable
            disallow_start_on_battery = [bool]$settings.DisallowStartIfOnBatteries
            stop_on_battery = [bool]$settings.StopIfGoingOnBatteries
            multiple_instances = Convert-MultipleInstances $settings.MultipleInstances
            restart_count = $restartCount
            restart_interval = if ($restartCount -gt 0) { [string]$settings.RestartInterval } else { $null }
            execution_time_limit = [string]$settings.ExecutionTimeLimit
        }
    }
}

function Test-Contracts {
    param([object[]]$Expected)
    $observed = @(); $drift = @()
    foreach ($contract in $Expected) {
        try {
            $actual = Get-NormalizedTask $contract; $observed += $actual
            foreach ($field in (Compare-Contract $contract $actual)) {
                $drift += ($contract.task_name + "." + $field)
            }
        }
        catch { $drift += ($contract.task_name + ".missing") }
    }
    return [ordered]@{
        observed = @($observed); drift_fields = @($drift | Sort-Object -Unique)
    }
}

function Disable-BothBestEffort {
    param([object[]]$EnabledExpected)
    foreach ($contract in $EnabledExpected) {
        try {
            Disable-ScheduledTask -TaskPath $contract.task_path `
                -TaskName $contract.task_name | Out-Null
        }
        catch { Write-Error $_ -ErrorAction Continue }
    }
    $disabledExpected = @(
        foreach ($contract in $EnabledExpected) {
            $copy = $contract | ConvertTo-Json -Depth 20 | ConvertFrom-Json
            $copy.enabled = $false; $copy
        }
    )
    $readback = Test-Contracts $disabledExpected
    $unsafe = @(
        $readback.observed | Where-Object { $_.enabled } |
            ForEach-Object { $_.task_name } | Sort-Object -Unique
    )
    return [ordered]@{
        status = if ($unsafe.Count -eq 0 -and $readback.drift_fields.Count -eq 0) {
            "confirmed-disabled"
        } else { "unsafe-partial-enable" }
        unsafe_enabled_tasks = $unsafe; drift_fields = $readback.drift_fields
    }
}

function Write-Result {
    param([hashtable]$Result, [int]$ExitCode)
    $Result | ConvertTo-Json -Depth 20 -Compress
    exit $ExitCode
}

$paths = [ordered]@{
    Repo = Resolve-AbsolutePath $Repo "repo" -MustExist
    PythonPath = Resolve-AbsolutePath $PythonPath "Python" -MustExist
    DataRoot = Resolve-AbsolutePath $DataRoot "data root"
    EvidenceRoot = Resolve-AbsolutePath $EvidenceRoot "evidence root"
    DailyRunRoot = Resolve-AbsolutePath $DailyRunRoot "daily run root"
    ConnectionRunRoot = Resolve-AbsolutePath $ConnectionRunRoot "connection run root"
    OutboxRoot = Resolve-AbsolutePath $OutboxRoot "outbox root"
    ManifestRoot = Resolve-AbsolutePath $ManifestRoot "manifest root"
}
$rootValues = @(
    $paths.DataRoot, $paths.EvidenceRoot, $paths.DailyRunRoot,
    $paths.ConnectionRunRoot, $paths.OutboxRoot, $paths.ManifestRoot
)
for ($left = 0; $left -lt $rootValues.Count; $left++) {
    for ($right = $left + 1; $right -lt $rootValues.Count; $right++) {
        $a = $rootValues[$left].TrimEnd('\') + '\'
        $b = $rootValues[$right].TrimEnd('\') + '\'
        if ($a.StartsWith($b, [System.StringComparison]::OrdinalIgnoreCase) -or
            $b.StartsWith($a, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "all runtime and manifest roots must be disjoint"
        }
    }
}
if ([System.TimeZoneInfo]::Local.Id -cne $TimeZoneId) {
    throw "configured timezone does not match this Windows host"
}

$result = [ordered]@{
    mode = $Mode; accepted = $false; source_contract_id = $null
    expected_state = if ($Mode -eq "GuardedEnable") { "Enabled" } else { $ExpectedState }
    tasks = @(); drift_fields = @(); preflight = $null; rollback = $null
    unsafe_enabled_tasks = @()
}

try {
    $runtimeConfig = New-RuntimeConfig $paths
    $sourceBundle = Invoke-SourceContract $paths $runtimeConfig `
        -PublishManifest:($Mode -eq "InstallDisabled")
    $result.source_contract_id = $sourceBundle.source.source_contract_id
    $disabledExpected = New-ExpectedContracts $paths $sourceBundle $false
    $enabledExpected = New-ExpectedContracts $paths $sourceBundle $true
    if ($Mode -eq "InstallDisabled") {
        foreach ($contract in $disabledExpected) {
            $objects = New-TaskObjects $contract
            Register-ScheduledTask -TaskPath $contract.task_path -TaskName $contract.task_name `
                -Action $objects.Action -Trigger $objects.Trigger -Settings $objects.Settings `
                -Principal $objects.Principal -Force | Out-Null
            Disable-ScheduledTask -TaskPath $contract.task_path `
                -TaskName $contract.task_name | Out-Null
        }
        $check = Test-Contracts $disabledExpected
        $result.tasks = $check.observed; $result.drift_fields = $check.drift_fields
        if ($check.drift_fields.Count -gt 0) { throw "disabled install read-back drift" }
    }
    elseif ($Mode -eq "Verify") {
        $expected = if ($ExpectedState -eq "Enabled") { $enabledExpected } else { $disabledExpected }
        $check = Test-Contracts $expected
        $result.tasks = $check.observed; $result.drift_fields = $check.drift_fields
        $result.unsafe_enabled_tasks = @(
            $check.observed | Where-Object { $_.enabled -and $ExpectedState -ne "Enabled" } |
                ForEach-Object { $_.task_name } | Sort-Object -Unique
        )
        if ($check.drift_fields.Count -gt 0) { Write-Result $result 1 }
    }
    else {
        $check = Test-Contracts $disabledExpected
        if ($check.drift_fields.Count -gt 0) { throw "pre-enable verification drift" }
        if (-not $PreflightExecutable) { throw "GuardedEnable requires a preflight executable" }
        $preflightFile = [System.IO.Path]::GetTempFileName()
        $oldPythonPath = $env:PYTHONPATH
        try {
            [System.IO.File]::WriteAllText(
                $preflightFile,
                ((@($PreflightExecutable) + @($PreflightArguments)) | ConvertTo-Json -Compress),
                [System.Text.UTF8Encoding]::new($false)
            )
            $env:PYTHONPATH = Join-Path $paths.Repo "src"
            $preflightOutput = & $paths.PythonPath -m quantmesh.ops.source_contract `
                run-preflight --argv-file $preflightFile --cwd $paths.Repo `
                --timeout-seconds $PreflightTimeoutSeconds
            if ($LASTEXITCODE -ne 0) { throw "guarded preflight failed" }
            $result.preflight = $preflightOutput | ConvertFrom-Json
        }
        finally {
            $env:PYTHONPATH = $oldPythonPath
            Remove-Item -LiteralPath $preflightFile -Force -ErrorAction SilentlyContinue
        }
        foreach ($contract in $enabledExpected) {
            Enable-ScheduledTask -TaskPath $contract.task_path `
                -TaskName $contract.task_name | Out-Null
        }
        $check = Test-Contracts $enabledExpected
        $result.tasks = $check.observed; $result.drift_fields = $check.drift_fields
        if ($check.drift_fields.Count -gt 0) { throw "post-enable read-back drift" }
    }
    $result.accepted = $true
    Write-Result $result 0
}
catch {
    $result.drift_fields = @(
        $result.drift_fields + ("error." + $_.Exception.Message) | Sort-Object -Unique
    )
    if ($Mode -ne "Verify" -and $null -ne $enabledExpected) {
        $result.rollback = Disable-BothBestEffort $enabledExpected
        $result.unsafe_enabled_tasks = $result.rollback.unsafe_enabled_tasks
    }
    Write-Result $result 1
}
