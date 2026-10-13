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
 & 'C:/Program Files/Tailscale/tailscale.exe' ssh ubuntu@quantmesh-staging-8gb -o BatchMode=yes -o ConnectTimeout=8 '/opt/quantmesh/current/.venv/bin/quantmesh-moomoo readiness --symbols AAPL,NVDA --market US --json --timeout-seconds 20'
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
 if ($finished -and $stdout.Result.Trim().StartsWith('{')) {
 try {
  $ready = $stdout.Result | ConvertFrom-Json -ErrorAction Stop
  $result.Readiness=@{ Status=$ready.status; OrderChecked=$ready.order_checked; Symbols=@($ready.symbols | ForEach-Object { @{Code=$_.code;Status=$_.status;QuoteStatus=$_.quote_status;HistoryStatus=$_.history_status;HistoryRows=$_.history_rows} }) }
 } catch { $result.Readiness=@{Status='observer_json_invalid'} }
}
 $result | ConvertTo-Json -Depth 12 | Set-Content "$PSScriptRoot/post-auth-aws-readiness.json"
 $result | ConvertTo-Json -Depth 12
} finally {
 if ($job -ne [IntPtr]::Zero) { [QmProbeJob]::CloseHandle($job) | Out-Null }
 if (-not $assigned) { try { if (-not $process.HasExited) { $process.Kill() } } catch {} }
 $gate.Dispose()
 $process.Dispose()
}
