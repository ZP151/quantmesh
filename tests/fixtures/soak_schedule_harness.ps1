param(
    [Parameter(Mandatory = $true)][string]$ScheduleScript,
    [Parameter(Mandatory = $true)][string]$ParametersJson,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [string]$SeedTasksJson,
    [string]$FailEnableTask,
    [string]$FailDisableTask
)

Import-Module Microsoft.PowerShell.Management
Import-Module Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = "None"
$global:QuantMeshMockTasks = @{}

function Write-Operation([string]$Value) {
    Add-Content -LiteralPath $LogPath -Value $Value -Encoding UTF8
}

function Convert-NormalizedTask([object]$Item) {
    $logonTypes = @{ "Interactive" = 3; "Password" = 1; "S4U" = 2 }
    $runLevels = @{ "Limited" = 0; "Highest" = 1 }
    $multipleInstances = @{ "Parallel" = 0; "Queue" = 1; "IgnoreNew" = 2; "StopExisting" = 3 }
    $repetition = if ($Item.trigger.kind -eq "repetition") {
        [pscustomobject]@{
            Interval = $Item.trigger.interval
            Duration = $Item.trigger.duration
            StopAtDurationEnd = [bool]$Item.trigger.stop_at_duration_end
        }
    } else { $null }
    $start = if ($Item.trigger.kind -eq "daily") {
        ([datetime]::Today + [timespan]::Parse($Item.trigger.at)).ToString("o")
    } else {
        [datetime]::SpecifyKind(
            [datetime]::ParseExact(
                $Item.trigger.start_boundary,
                "yyyy-MM-ddTHH:mm:ss",
                [System.Globalization.CultureInfo]::InvariantCulture
            ),
            [System.DateTimeKind]::Local
        ).ToString("o")
    }
    $actions = @([pscustomobject]@{
        Execute = $Item.action.execute
        Arguments = $Item.action.arguments
        WorkingDirectory = $Item.action.working_directory
    })
    if ($Item.extra_action) { $actions += $actions[0] }
    $triggers = @([pscustomobject]@{
        StartBoundary = $start
        Repetition = $repetition
        Enabled = [bool]$Item.trigger.enabled
        DaysInterval = $Item.trigger.days_interval
        CimClass = [pscustomobject]@{ CimClassName = $Item.trigger.class }
    })
    if ($Item.extra_trigger) { $triggers += $triggers[0] }
    return [pscustomobject]@{
        TaskPath = $Item.task_path
        TaskName = $Item.task_name
        Actions = $actions
        Triggers = $triggers
        Principal = [pscustomobject]@{
            UserId = $Item.principal.user_id
            LogonType = $logonTypes[[string]$Item.principal.logon_type]
            RunLevel = $runLevels[[string]$Item.principal.run_level]
        }
        Settings = [pscustomobject]@{
            Enabled = [bool]$Item.enabled
            WakeToRun = [bool]$Item.settings.wake_to_run
            StartWhenAvailable = [bool]$Item.settings.start_when_available
            DisallowStartIfOnBatteries = [bool]$Item.settings.disallow_start_on_battery
            StopIfGoingOnBatteries = [bool]$Item.settings.stop_on_battery
            MultipleInstances = $multipleInstances[[string]$Item.settings.multiple_instances]
            RestartCount = [int]$Item.settings.restart_count
            RestartInterval = $Item.settings.restart_interval
            ExecutionTimeLimit = $Item.settings.execution_time_limit
        }
    }
}

if ($SeedTasksJson) {
    $seedPayload = Get-Content -LiteralPath $SeedTasksJson -Raw | ConvertFrom-Json
    foreach ($item in $seedPayload) {
        $global:QuantMeshMockTasks[$item.task_name] = Convert-NormalizedTask $item
    }
}

function New-ScheduledTaskAction {
    param([string]$Execute, [string]$Argument, [string]$WorkingDirectory)
    return [pscustomobject]@{
        Execute = $Execute; Arguments = $Argument; WorkingDirectory = $WorkingDirectory
    }
}

function New-ScheduledTaskTrigger {
    param(
        [switch]$Daily,
        [switch]$Once,
        [object]$At,
        [timespan]$RepetitionInterval,
        [timespan]$RepetitionDuration
    )
    $repetition = if ($Once) {
        $duration = if ($RepetitionDuration -eq [timespan]::MaxValue) {
            "P99999999DT23H59M59S"
        } else { [System.Xml.XmlConvert]::ToString($RepetitionDuration) }
        [pscustomobject]@{
            Interval = [System.Xml.XmlConvert]::ToString($RepetitionInterval)
            Duration = $duration
            StopAtDurationEnd = $true
        }
    } else { $null }
    $start = if ($Daily) {
        ([datetime]::Today + [timespan]::Parse([string]$At)).ToString("o")
    } else { ([datetime]$At).ToString("o") }
    return [pscustomobject]@{
        StartBoundary = $start
        Repetition = $repetition
        Enabled = $true
        DaysInterval = if ($Daily) { 1 } else { $null }
        CimClass = [pscustomobject]@{
            CimClassName = if ($Daily) { "MSFT_TaskDailyTrigger" } else { "MSFT_TaskTimeTrigger" }
        }
    }
}

function New-ScheduledTaskPrincipal {
    param([string]$UserId, [string]$LogonType, [string]$RunLevel)
    return [pscustomobject]@{
        UserId = $UserId
        LogonType = if ($LogonType -ceq "Interactive") { 3 } else { 1 }
        RunLevel = if ($RunLevel -ceq "Limited") { 0 } else { 1 }
    }
}

function New-ScheduledTaskSettingsSet {
    param(
        [switch]$StartWhenAvailable,
        [switch]$AllowStartIfOnBatteries,
        [switch]$DontStopIfGoingOnBatteries,
        [switch]$WakeToRun,
        [timespan]$ExecutionTimeLimit,
        [string]$MultipleInstances,
        [int]$RestartCount = 0,
        [timespan]$RestartInterval
    )
    return [pscustomobject]@{
        Enabled = $true
        StartWhenAvailable = [bool]$StartWhenAvailable
        DisallowStartIfOnBatteries = -not [bool]$AllowStartIfOnBatteries
        StopIfGoingOnBatteries = -not [bool]$DontStopIfGoingOnBatteries
        WakeToRun = [bool]$WakeToRun
        ExecutionTimeLimit = [System.Xml.XmlConvert]::ToString($ExecutionTimeLimit)
        MultipleInstances = if ($MultipleInstances -ceq "IgnoreNew") { 2 } else { 0 }
        RestartCount = $RestartCount
        RestartInterval = if ($RestartCount -gt 0) {
            [System.Xml.XmlConvert]::ToString($RestartInterval)
        } else { $null }
    }
}

function Register-ScheduledTask {
    param(
        [string]$TaskPath,
        [string]$TaskName,
        [object]$Action,
        [object]$Trigger,
        [object]$Settings,
        [object]$Principal,
        [switch]$Force
    )
    Write-Operation "Register:$TaskName"
    Write-Operation "RegisterEnabled:${TaskName}:$($Settings.Enabled)"
    $global:QuantMeshMockTasks[$TaskName] = [pscustomobject]@{
        TaskPath = $TaskPath; TaskName = $TaskName; Actions = @($Action)
        Triggers = @($Trigger); Settings = $Settings; Principal = $Principal
    }
    return $global:QuantMeshMockTasks[$TaskName]
}

function Get-ScheduledTask {
    param([string]$TaskPath, [string]$TaskName)
    Write-Operation "Get:$TaskName"
    if (-not $global:QuantMeshMockTasks.ContainsKey($TaskName)) { throw "mock task missing: $TaskName" }
    return $global:QuantMeshMockTasks[$TaskName]
}

function Get-ScheduledTaskInfo {
    param([string]$TaskPath, [string]$TaskName)
    Write-Operation "Info:$TaskName"
    return [pscustomobject]@{ LastTaskResult = 0 }
}

function Enable-ScheduledTask {
    param([string]$TaskPath, [string]$TaskName)
    Write-Operation "Enable:$TaskName"
    if ($FailEnableTask -and $TaskName -ceq $FailEnableTask) { throw "mock enable failure" }
    $global:QuantMeshMockTasks[$TaskName].Settings.Enabled = $true
    return $global:QuantMeshMockTasks[$TaskName]
}

function Disable-ScheduledTask {
    param([string]$TaskPath, [string]$TaskName)
    Write-Operation "Disable:$TaskName"
    if ($FailDisableTask -and $TaskName -ceq $FailDisableTask) { throw "mock disable failure" }
    $global:QuantMeshMockTasks[$TaskName].Settings.Enabled = $false
    return $global:QuantMeshMockTasks[$TaskName]
}

$parametersObject = Get-Content -LiteralPath $ParametersJson -Raw | ConvertFrom-Json
$parameters = @{}
foreach ($property in $parametersObject.PSObject.Properties) {
    $parameters[$property.Name] = $property.Value
}
& $ScheduleScript @parameters
exit $LASTEXITCODE
