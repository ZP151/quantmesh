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

function Initialize-QmProbeJobType {
    if ('QmProbeJob' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class QmProbeJob {
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool SetInformationJobObject(IntPtr job, int kind, IntPtr info, uint size);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr handle);
    public static IntPtr Create() {
        var job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new InvalidOperationException("Probe job unavailable");
        var limits = new ExtendedLimits();
        limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(limits);
        var buffer = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(limits, buffer, false);
            if (!SetInformationJobObject(job, 9, buffer, (uint)size)) {
                CloseHandle(job);
                throw new InvalidOperationException("Probe containment unavailable");
            }
            return job;
        } finally { Marshal.FreeHGlobal(buffer); }
    }
}
'@ | Out-Null
}

function Invoke-QmBoundedProbe([string]$Path) {
    # A fixed encoded Python expression avoids nested PowerShell/SSH quoting.
    $code = 'import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(("127.0.0.1",11111)); print("QM_LISTENER_PRESENT" if r==0 else "QM_LISTENER_ABSENT" if r==111 else "QM_LISTENER_UNKNOWN"); s.close()'
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
    # Tailscale invokes native ssh and a proxy child. Contain this probe's entire
    # descendant tree, including when its outer wrapper exits before its pipes.
    # The bootstrap cannot launch the CLI until it has joined the anonymous job.
    $job = [IntPtr]::Zero
    $gate = $null
    $assigned = $false
    $process = New-Object Diagnostics.Process
    $gateName = 'Local\QuantMeshProbe-' + [Guid]::NewGuid().ToString('N')
    $literalPath = $Path.Replace("'", "''")
    $bootstrap = @'
$ErrorActionPreference='Stop'
$gate=[Threading.EventWaitHandle]::OpenExisting('__GATE__')
try {
 if (-not $gate.WaitOne(10000)) { exit 1 }
 & '__PATH__' ssh ubuntu@quantmesh-staging-8gb -o BatchMode=yes -o ConnectTimeout=8 'echo __CODE__ | base64 -d | python3'
 exit $LASTEXITCODE
} finally { $gate.Dispose() }
'@
    $bootstrap = $bootstrap.Replace('__GATE__', $gateName).Replace('__PATH__', $literalPath).Replace('__CODE__', $encoded)
    $command = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($bootstrap))
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = Join-Path $PSHOME 'powershell.exe'
    $info.Arguments = '-NoProfile -NonInteractive -EncodedCommand ' + $command
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process.StartInfo = $info
    try {
        Initialize-QmProbeJobType
        $job = [QmProbeJob]::Create()
        $gate = New-Object Threading.EventWaitHandle($false, [Threading.EventResetMode]::ManualReset, $gateName)
        if (-not $process.Start()) { return @{ ExitCode = -1; Output = '' } }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not [QmProbeJob]::AssignProcessToJobObject($job, $process.Handle)) {
            throw 'Probe containment unavailable'
        }
        $assigned = $true
        $gate.Set() | Out-Null
        if (-not $process.WaitForExit(12000)) {
            return @{ ExitCode = -1; Output = '' }
        }
        # Closing the job before draining prevents a surviving proxy from
        # holding stdout/stderr open after a successful outer-wrapper exit.
        [QmProbeJob]::CloseHandle($job) | Out-Null
        $job = [IntPtr]::Zero
        if (-not $stdout.Wait(1000) -or -not $stderr.Wait(1000)) {
            return @{ ExitCode = -1; Output = '' }
        }
        return @{ ExitCode = $process.ExitCode; Output = $stdout.Result.Trim() }
    }
    catch { return @{ ExitCode = -1; Output = '' } }
    finally {
        if ($job -ne [IntPtr]::Zero) { [QmProbeJob]::CloseHandle($job) | Out-Null }
        if (-not $assigned) {
            # Assignment failure leaves only the gated bootstrap, never a CLI.
            try { if (-not $process.HasExited) { $process.Kill() } } catch { }
        }
        if ($null -ne $gate) { $gate.Dispose() }
        $process.Dispose()
    }
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
