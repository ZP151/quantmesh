# Reversible current-user Startup provisioning. No administrator task or credential.
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [string]$OpenDPath,
    [string]$TailscalePath
)

$script:QmSupervisorSource = Join-Path $PSScriptRoot 'opend_recovery.ps1'

function Read-QmShortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($Path)
        return @{ TargetPath = $shortcut.TargetPath; Arguments = $shortcut.Arguments;
            WorkingDirectory = $shortcut.WorkingDirectory }
    }
    finally { [Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null }
}

function Write-QmShortcut([string]$Path, [string]$Target, [string]$Arguments, [string]$WorkingDirectory) {
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($Path)
        $shortcut.TargetPath = $Target
        $shortcut.Arguments = $Arguments
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.WindowStyle = 7
        $shortcut.Description = 'QuantMesh current-user OpenD and private tunnel recovery'
        $shortcut.Save()
    }
    finally { [Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null }
}

function Get-QmFileDigest([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Assert-QmPlainPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Linked installation path refused' }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Get-QmHelperActive {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    try { $mutex = [Threading.Mutex]::OpenExisting('Global\QuantMeshOpenDRecovery-' + $sid) }
    catch [Threading.WaitHandleCannotBeOpenedException] { return $false }
    try {
        try { $acquired = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $acquired = $true }
        if ($acquired) { $mutex.ReleaseMutex(); return $false }
        return $true
    }
    finally { $mutex.Dispose() }
}

function Assert-QmOwnedInstallation($Manifest, [string]$Directory, [string]$Shortcut) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($Manifest.Schema -ne 1 -or $Manifest.OwnerSid -ne $sid -or
        $Manifest.Product -ne 'QuantMeshOpenDRecovery' -or
        $Manifest.Directory -ne [IO.Path]::GetFullPath($Directory) -or
        $Manifest.Shortcut -ne [IO.Path]::GetFullPath($Shortcut)) { throw 'Foreign installation manifest' }
    $supervisor = Join-Path $Directory 'opend_recovery.ps1'
    if (-not (Test-Path -LiteralPath $supervisor -PathType Leaf) -or
        (Get-QmFileDigest $supervisor) -ne $Manifest.SupervisorDigest) { throw 'Foreign or modified supervisor' }
    if (Test-Path -LiteralPath $Shortcut) {
        $actual = Read-QmShortcut $Shortcut
        if ($actual.TargetPath -ne $Manifest.TargetPath -or
            $actual.Arguments -ne $Manifest.Arguments -or
            $actual.WorkingDirectory -ne $Manifest.Directory) { throw 'Foreign or modified startup shortcut' }
    }
}

function Invoke-QmStartupProvision([string]$Action, [string]$TargetDirectory, [string]$StartupDirectory, [string]$OpenD, [string]$Tailscale) {
    if ($Action -notin @('Install', 'Uninstall', 'Status')) { throw 'Unknown provision action' }
    $directory = [IO.Path]::GetFullPath($TargetDirectory)
    $shortcut = [IO.Path]::GetFullPath((Join-Path $StartupDirectory 'QuantMesh OpenD Recovery.lnk'))
    $manifestPath = Join-Path $directory 'owner.json'
    $supervisor = Join-Path $directory 'opend_recovery.ps1'
    foreach ($path in @($directory, $shortcut, $manifestPath, $supervisor,
        (Join-Path $directory 'status.json'), (Join-Path $directory 'status.tmp'))) {
        Assert-QmPlainPath $path
    }
    $manifest = $null
    if (Test-Path -LiteralPath $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Assert-QmOwnedInstallation $manifest $directory $shortcut
    }
    elseif ((Test-Path -LiteralPath $shortcut) -or
        ((Test-Path -LiteralPath $directory) -and @(Get-ChildItem -LiteralPath $directory -Force).Count -ne 0)) {
        throw 'Foreign target or startup shortcut'
    }
    if ($Action -eq 'Status') {
        return @{ Installed = ($null -ne $manifest -and (Test-Path -LiteralPath $shortcut)); Directory = $directory; Shortcut = $shortcut }
    }
    if ($Action -eq 'Uninstall') {
        if ($null -eq $manifest) { return @{ Installed = $false; State = 'not_installed' } }
        if (Get-QmHelperActive) {
            if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut }
            return @{ Installed = $false; State = 'startup_removed_cleanup_deferred'; RunningProcesses = 'untouched' }
        }
        foreach ($name in @('status.json', 'status.tmp')) {
            $path = Join-Path $directory $name
            if (Test-Path -LiteralPath $path) {
                $data = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
                if ($data.Schema -ne 1 -or $data.OwnerSid -ne $manifest.OwnerSid) { throw 'Foreign status file' }
            }
        }
        if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut }
        foreach ($name in @('opend_recovery.ps1', 'owner.json', 'status.json', 'status.tmp')) {
            $path = Join-Path $directory $name
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
        }
        # Non-recursive only: unrelated files are retained.
        if (@(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) { Remove-Item -LiteralPath $directory }
        return @{ Installed = $false; State = 'removed_owned_startup'; RunningProcesses = 'untouched' }
    }
    if (-not $OpenD -or -not $Tailscale) { throw 'Explicit executable paths required' }
    if ($null -ne $manifest -and (Get-QmHelperActive) -and
        (Get-QmFileDigest $script:QmSupervisorSource) -ne $manifest.SupervisorDigest) {
        throw 'Active helper update requires later cleanup'
    }
    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $supervisor +
        '" -OpenDPath "' + $OpenD + '" -TailscalePath "' + $Tailscale + '" -StatusDirectory "' + $directory + '"'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    Copy-Item -LiteralPath $script:QmSupervisorSource -Destination $supervisor -Force
    $newManifest = @{ Schema = 1; Product = 'QuantMeshOpenDRecovery'; OwnerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
        Directory = $directory; Shortcut = $shortcut; TargetPath = $powershell; Arguments = $arguments;
        SupervisorDigest = (Get-QmFileDigest $supervisor) }
    [IO.File]::WriteAllText($manifestPath, ($newManifest | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
    Write-QmShortcut $shortcut $powershell $arguments $directory
    Assert-QmOwnedInstallation $newManifest $directory $shortcut
    return @{ Installed = $true; Directory = $directory; Shortcut = $shortcut; SupervisorDigest = $newManifest.SupervisorDigest }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    try {
        if (@($Install, $Uninstall, $Status).Where({ $_ }).Count -ne 1) { throw 'Choose exactly one action' }
        $action = 'Status'
        if ($Install) {
            $action = 'Install'
            foreach ($path in @($OpenDPath, $TailscalePath)) {
                if (-not $path -or -not [IO.Path]::IsPathRooted($path) -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Explicit installed executables required' }
            }
            $signature = Get-AuthenticodeSignature -LiteralPath $OpenDPath
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Moomoo Technologies Inc\.') { throw 'Expected signed Moomoo GUI required' }
        }
        if ($Uninstall) { $action = 'Uninstall' }
        $directory = Join-Path $env:LOCALAPPDATA 'QuantMesh\OpenDRecovery'
        $startup = [Environment]::GetFolderPath('Startup')
        Invoke-QmStartupProvision $action $directory $startup $OpenDPath $TailscalePath | ConvertTo-Json -Compress
    }
    catch { Write-Output '{"State":"provisioning_refused"}'; exit 1 }
}
