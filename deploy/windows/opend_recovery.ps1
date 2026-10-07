# Current-user recovery of the existing GUI and private loopback route.
# No vendor settings, credentials, orders, or unrelated processes are inspected.
[CmdletBinding()]
param(
    [string]$OpenDPath,
    [string]$TailscalePath,
    [string]$StatusDirectory,
    [switch]$Once,
    [switch]$ObserveOnly
)

function New-QmRecoveryState {
    return @{ Child = $null; ChildStartedAt = 0; ChildEstablished = $false;
        NextAttempt = 0; Failures = 0; LastStatus = '' }
}

function Enter-QmSingleton([string]$Name) {
    $mutex = New-Object Threading.Mutex($false, $Name)
    try {
        try { $acquired = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $acquired = $true }
        if ($acquired) { return $mutex }
    }
    catch { $mutex.Dispose(); throw }
    $mutex.Dispose()
    return $null
}

function Test-QmLocalPort {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect('127.0.0.1', 11111, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(1000)) { return $false }
        $client.EndConnect($pending)
        return $true
    }
    catch { return $false }
    finally { $client.Close() }
}

function Get-QmOpenDRunning([string]$Path) {
    $name = [IO.Path]::GetFileNameWithoutExtension($Path)
    $unknown = $false
    foreach ($process in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
        try {
            if ([string]::IsNullOrEmpty($process.Path)) { $unknown = $true }
            elseif ([IO.Path]::GetFullPath($process.Path) -eq [IO.Path]::GetFullPath($Path)) {
                return $true
            }
        }
        catch { $unknown = $true }
    }
    if ($unknown) { return $null }
    return $false
}

function Invoke-QmBoundedProbe([string]$Path) {
    # A fixed encoded Python expression avoids nested PowerShell/SSH quoting.
    $code = 'import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(("127.0.0.1",11111)); print("QM_LISTENER_PRESENT" if r==0 else "QM_LISTENER_ABSENT" if r==111 else "QM_LISTENER_UNKNOWN"); s.close()'
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Path
    $info.Arguments = 'ssh ubuntu@quantmesh-staging-8gb -o BatchMode=yes -o ConnectTimeout=8 "echo ' + $encoded + ' | base64 -d | python3"'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { return @{ ExitCode = -1; Output = '' } }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(12000)) {
            $process.Kill() # Only this bounded, owned probe.
            $process.WaitForExit()
            return @{ ExitCode = -1; Output = '' }
        }
        return @{ ExitCode = $process.ExitCode; Output = $stdout.Result.Trim() }
    }
    catch { return @{ ExitCode = -1; Output = '' } }
    finally { $process.Dispose() }
}

function Get-QmRemoteListener([string]$Path) {
    $result = Invoke-QmBoundedProbe $Path
    if ($result.ExitCode -eq 0) {
        if ($result.Output -eq 'QM_LISTENER_PRESENT') { return 'present' }
        if ($result.Output -eq 'QM_LISTENER_ABSENT') { return 'absent' }
    }
    return 'unknown'
}

function Get-QmObservation([string]$OpenD, [string]$Tailscale) {
    $local = Test-QmLocalPort
    $remote = 'unknown'
    if ($local) { $remote = Get-QmRemoteListener $Tailscale }
    return @{ OpenDRunning = (Get-QmOpenDRunning $OpenD); LocalReady = $local; RemoteListener = $remote }
}

function Start-QmOpenD([string]$Path) {
    try {
        Start-Process -FilePath $Path -WorkingDirectory ([IO.Path]::GetDirectoryName($Path)) -WindowStyle Hidden | Out-Null
        return $true
    }
    catch { return $false }
}

function Get-QmTunnelArguments {
    return @('ssh', 'ubuntu@quantmesh-staging-8gb', '-N', '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3', '-o', 'ConnectTimeout=8',
        '-R', '127.0.0.1:11111:127.0.0.1:11111')
}

function Start-QmTunnel([string]$Path) {
    # Consume output without logging raw authentication URLs or account details.
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Path
    $info.Arguments = (Get-QmTunnelArguments) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { $process.Dispose(); return $null }
        # Keep drain tasks alive on the owned Process. No raw content is retained.
        $process | Add-Member -NotePropertyName QmOutput -NotePropertyValue $process.StandardOutput.ReadToEndAsync()
        $process | Add-Member -NotePropertyName QmError -NotePropertyValue $process.StandardError.ReadToEndAsync()
        return $process
    }
    catch { $process.Dispose(); return $null }
}

function Invoke-QmRecoveryStep($State, [string]$OpenD, [string]$Tailscale, [long]$Now, [switch]$ObserveOnly) {
    $observation = Get-QmObservation $OpenD $Tailscale
    if ($ObserveOnly) {
        if ($null -eq $observation.OpenDRunning) { return 'opend_process_unknown' }
        if (-not $observation.LocalReady) {
            if ($observation.OpenDRunning) { return 'needs_opend_login' }
            return 'opend_not_running'
        }
        if ($observation.RemoteListener -eq 'present') { return 'existing_private_tunnel' }
        if ($observation.RemoteListener -eq 'absent') { return 'private_tunnel_absent' }
        return 'needs_tailscale_or_ssh'
    }
    if (-not $observation.LocalReady) {
        if ($null -eq $observation.OpenDRunning) { return 'opend_process_unknown' }
        if ($observation.OpenDRunning) { return 'needs_opend_login' }
        if ($Now -lt $State.NextAttempt) { return 'retry_wait' }
        $State.NextAttempt = $Now + 60
        if (Start-QmOpenD $OpenD) { return 'opend_started' }
        return 'opend_launch_failed'
    }
    if ($null -ne $State.Child) {
        if (-not $State.Child.HasExited) {
            if ($observation.RemoteListener -eq 'present') {
                $State.ChildEstablished = $true
                $State.Failures = 0
                if (-not $observation.LocalReady) { return 'needs_opend_login' }
                return 'managed_private_tunnel'
            }
            if ($observation.RemoteListener -eq 'unknown') { return 'needs_tailscale_or_ssh' }
            if ($State.ChildEstablished) { return 'private_tunnel_unavailable' }
            if ($Now - $State.ChildStartedAt -lt 60) {
                if (-not $observation.LocalReady) { return 'needs_opend_login' }
                return 'private_tunnel_connecting'
            }
            $State.Child.Kill() # Only an owned child that never established its route.
            $State.Child.WaitForExit()
        }
        if ($State.Child -is [IDisposable]) { $State.Child.Dispose() }
        $State.Child = $null
        $State.ChildEstablished = $false
        $State.Failures++
        $State.NextAttempt = $Now + [Math]::Min(300, 30 * [Math]::Pow(2, [Math]::Min($State.Failures - 1, 4)))
    }
    if ($observation.RemoteListener -eq 'present') { return 'existing_private_tunnel' }
    if ($observation.RemoteListener -ne 'absent') { return 'needs_tailscale_or_ssh' }
    if ($Now -lt $State.NextAttempt) { return 'retry_wait' }
    $State.Child = Start-QmTunnel $Tailscale
    $State.ChildEstablished = $false
    $State.ChildStartedAt = $Now
    $State.NextAttempt = $Now + 30
    if ($null -ne $State.Child) { return 'private_tunnel_started' }
    return 'private_tunnel_launch_failed'
}

function Write-QmStatus($State, [string]$Label, [string]$Directory) {
    if ($State.LastStatus -eq $Label) { return }
    $State.LastStatus = $Label
    $status = @{ Schema = 1; OwnerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
        State = $Label; ObservedAtUtc = [DateTime]::UtcNow.ToString('o') }
    $json = $status | ConvertTo-Json -Compress
    Write-Output $json
    if ($Directory) {
        try {
            $temporary = Join-Path $Directory 'status.tmp'
            [IO.File]::WriteAllText($temporary, $json, (New-Object Text.UTF8Encoding($false)))
            Move-Item -LiteralPath $temporary -Destination (Join-Path $Directory 'status.json') -Force -ErrorAction Stop
        }
        catch {
            # Auxiliary persistence cannot stop recovery or an established route.
            # The next state change can attempt to persist its own observation.
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    try {
        foreach ($path in @($OpenDPath, $TailscalePath)) {
            if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Missing configured executable' }
        }
        if ($ObserveOnly -and -not $Once) { throw 'ObserveOnly requires Once' }
        $state = New-QmRecoveryState
        $mutex = $null
        if (-not $ObserveOnly) {
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $mutex = Enter-QmSingleton ('Global\QuantMeshOpenDRecovery-' + $sid)
            if ($null -eq $mutex) { Write-Output '{"State":"duplicate_helper"}'; exit 0 }
        }
        try {
            do {
                $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
                $label = Invoke-QmRecoveryStep $state $OpenDPath $TailscalePath $now -ObserveOnly:$ObserveOnly
                $directory = $StatusDirectory
                if ($ObserveOnly) { $directory = '' }
                Write-QmStatus $state $label $directory
                if (-not $Once) { Start-Sleep -Seconds 30 }
            } while (-not $Once)
        }
        finally {
            # Never stop an existing GUI/tunnel. Close only our own child on shutdown.
            if ($null -ne $state.Child) {
                if (-not $state.Child.HasExited) { $state.Child.Kill(); $state.Child.WaitForExit() }
                $state.Child.Dispose()
            }
            if ($null -ne $mutex) { $mutex.ReleaseMutex(); $mutex.Dispose() }
        }
    }
    catch { Write-Output '{"State":"configuration_or_runtime_error"}'; exit 1 }
}
