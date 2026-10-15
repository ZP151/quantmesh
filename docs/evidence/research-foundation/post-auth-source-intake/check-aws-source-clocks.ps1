$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/merged/deploy/windows/opend_recovery.ps1"
Initialize-QmProbeJobType
$job = [QmProbeJob]::Create()
$gateName = 'Local\QuantMeshReleaseObserve-' + [Guid]::NewGuid().ToString('N')
$gate = New-Object Threading.EventWaitHandle($false, [Threading.EventResetMode]::ManualReset, $gateName)
$bootstrap = @'
$gate=[Threading.EventWaitHandle]::OpenExisting('__GATE__')
try {
 if (-not $gate.WaitOne(10000)) { exit 1 }
 & 'C:/Program Files/Tailscale/tailscale.exe' ssh ubuntu@quantmesh-staging-8gb -o BatchMode=yes -o ConnectTimeout=8 'echo aW1wb3J0IGpzb24sc3lzLHRlbXBmaWxlCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aApmcm9tIHF1YW50bWVzaC5kYXRhLmNvbGxlY3Rpb25fcHJvY2VzcyBpbXBvcnQgcnVuX2JvdW5kZWRfanNvbl9wcm9jZXNzCndvcmtlcj0iIiIKaW1wb3J0IGpzb24sc3lzLG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppZiAiSE9NRSIgbm90IGluIG9zLmVudmlyb246IG9zLmVudmlyb25bIkhPTUUiXT1zdHIoUGF0aC5ob21lKCkpCmZyb20gZGF0ZXRpbWUgaW1wb3J0IGRhdGV0aW1lLHRpbWV6b25lCmZyb20gcXVhbnRtZXNoLm1vb21vby5vcGVuZCBpbXBvcnQgTW9vbW9vT3BlbkRDbGllbnQsU2RrVHJhbnNwb3J0CmNsaWVudD1Nb29tb29PcGVuRENsaWVudChTZGtUcmFuc3BvcnQoaG9zdD0iMTI3LjAuMC4xIixwb3J0PTExMTExLGNvbm5lY3RfdGltZW91dF9zPTUscmVxdWVzdF90aW1lb3V0X3M9OCkpCnRyeToKICAgIHJlc3VsdD1jbGllbnQuc3RvY2tfcXVvdGUoWyJVUy5BQVBMIiwiVVMuTlZEQSJdKQogICAgcm93cz1be2s6cm93LmdldChrKSBmb3IgayBpbiAoImNvZGUiLCJkYXRhX2RhdGUiLCJkYXRhX3RpbWUiKX0gZm9yIHJvdyBpbiByZXN1bHRbInJvd3MiXV0KICAgIHJlcG9ydD17InN0YXR1cyI6Im9ic2VydmVkIiwicXVvdGVfc291cmNlX2Nsb2NrcyI6cm93cywib2JzZXJ2ZWRfYXQiOmRhdGV0aW1lLm5vdyh0aW1lem9uZS51dGMpLmlzb2Zvcm1hdCgpLCJvcmRlcl9jaGVja2VkIjpGYWxzZX0KZXhjZXB0IEV4Y2VwdGlvbiBhcyBleGM6CiAgICByZXBvcnQ9eyJzdGF0dXMiOiJxdW90ZV9wcm9iZV9mYWlsZWQiLCJlcnJvcl90eXBlIjp0eXBlKGV4YykuX19uYW1lX18sIm9yZGVyX2NoZWNrZWQiOkZhbHNlfQpmaW5hbGx5OgogICAgY2xpZW50LmNsb3NlKCkKUGF0aChzeXMuYXJndlsyXSkud3JpdGVfdGV4dChqc29uLmR1bXBzKHJlcG9ydCksZW5jb2Rpbmc9InV0Zi04IikKIiIiCnRyeToKICAgIHdpdGggdGVtcGZpbGUuVGVtcG9yYXJ5RGlyZWN0b3J5KHByZWZpeD0icW0tc291cmNlLWNsb2NrLSIpIGFzIHNjcmF0Y2g6CiAgICAgICAgcmVzdWx0PXJ1bl9ib3VuZGVkX2pzb25fcHJvY2Vzcyhbc3lzLmV4ZWN1dGFibGUsIi1CIiwiLWMiLHdvcmtlciwie3JlcXVlc3R9Iiwie291dHB1dH0iXSxyZXF1ZXN0PXt9LHRpbWVvdXRfc2Vjb25kcz0xNSxzY3JhdGNoX3Jvb3Q9UGF0aChzY3JhdGNoKSkKZXhjZXB0IEV4Y2VwdGlvbjoKICAgIHJlc3VsdD17InN0YXR1cyI6ImJvdW5kZWRfcXVvdGVfcHJvYmVfZmFpbGVkIiwib3JkZXJfY2hlY2tlZCI6RmFsc2V9CnByaW50KGpzb24uZHVtcHMocmVzdWx0KSk= | base64 -d | /opt/quantmesh/current/.venv/bin/python -B -'
 exit $LASTEXITCODE
} finally { $gate.Dispose() }
'@
$bootstrap = $bootstrap.Replace('__GATE__', $gateName)
$info = New-Object Diagnostics.ProcessStartInfo
$info.FileName = 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
$info.Arguments = '-NoProfile -NonInteractive -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($bootstrap))
$info.UseShellExecute=$false
$info.CreateNoWindow=$true
$info.RedirectStandardOutput=$true
$info.RedirectStandardError=$true
$process=New-Object Diagnostics.Process
$process.StartInfo=$info
$assigned=$false
try {
 if (-not $process.Start()) { throw 'Observer launch failed' }
 $stdout=$process.StandardOutput.ReadToEndAsync()
 $stderr=$process.StandardError.ReadToEndAsync()
 if (-not [QmProbeJob]::AssignProcessToJobObject($job,$process.Handle)) { throw 'Observer containment unavailable' }
 $assigned=$true
 $gate.Set() | Out-Null
 $finished=$process.WaitForExit(45000)
 [QmProbeJob]::CloseHandle($job) | Out-Null
 $job=[IntPtr]::Zero
 if (-not $stdout.Wait(1000) -or -not $stderr.Wait(1000)) { throw 'Observer drain unavailable' }
 $urls=@([regex]::Matches($stderr.Result,'https://login\.tailscale\.com/a/[A-Za-z0-9]+') | ForEach-Object { $_.Value } | Select-Object -Unique)
 $result=@{AtUtc=[DateTime]::UtcNow.ToString('o'); Finished=$finished; AuthenticationUrls=$urls; ObserverPid=$process.Id; ObserverTreeClosed=$true}
 if ($finished) { $result.ExitCode=$process.ExitCode }
 if ($finished -and $process.ExitCode -eq 0) { $result.SourceClock=($stdout.Result | ConvertFrom-Json) }
 $result | ConvertTo-Json -Depth 12 | Set-Content "$PSScriptRoot/post-auth-aws-source-clocks.json"
 $result | ConvertTo-Json -Depth 12
} finally {
 if ($job -ne [IntPtr]::Zero) { [QmProbeJob]::CloseHandle($job) | Out-Null }
 if (-not $assigned) { try { if (-not $process.HasExited) { $process.Kill() } } catch {} }
 $gate.Dispose()
 $process.Dispose()
}

