"""Execute the recovery policy against isolated native OS boundaries."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "deploy/windows/opend_recovery.ps1"
INSTALLER = ROOT / "deploy/windows/install_opend_startup.ps1"
POWERSHELL = shutil.which("powershell.exe")


def ps(script: str, *, sources: tuple[Path, ...] = (RECOVERY,)) -> dict:
    for source in sources:
        assert source.exists(), f"Missing recovery/provisioning behavior: {source.name}"
    if os.name != "nt" or not POWERSHELL:
        pytest.skip("Native Windows PowerShell 5.1 witness requires Windows")
    prefix = (
        "$ErrorActionPreference='Stop'\n"
        f"$testRecoverySource='{str(RECOVERY).replace(chr(39), chr(39) * 2)}'\n"
        f"$testInstallerSource='{str(INSTALLER).replace(chr(39), chr(39) * 2)}'\n"
    ) + "\n".join(f". '{str(source).replace(chr(39), chr(39) * 2)}'" for source in sources)
    encoded = base64.b64encode((prefix + "\n" + script).encode("utf-16-le")).decode()
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout.strip())


@pytest.mark.parametrize(
    ("running", "local", "remote", "wanted"),
    [
        (True, False, "absent", "needs_opend_login"),
        (True, True, "present", "existing_private_tunnel"),
        (True, True, "unknown", "needs_tailscale_or_ssh"),
        (True, True, "absent", "private_tunnel_started"),
        (False, False, "unknown", "opend_started"),
    ],
)
def test_recovery_waits_or_launches_only_the_missing_owned_component(
    running: bool, local: bool, remote: str, wanted: str
) -> None:
    # A wrong state branch would launch a duplicate GUI or private tunnel.
    result = ps(
        f"""
$script:gui=0; $script:tunnel=0
function Get-QmObservation {{ @{{ OpenDRunning=${str(running).lower()};
 LocalReady=${str(local).lower()}; RemoteListener='{remote}' }} }}
function Start-QmOpenD {{ $script:gui++; return $true }}
function Start-QmTunnel {{ $script:tunnel++; return [pscustomobject]@{{ HasExited=$false }} }}
$state=New-QmRecoveryState
$label=Invoke-QmRecoveryStep $state 'C:\\fake\\OpenD.exe' 'C:\\fake\\tailscale.exe' 100
@{{label=$label; gui=$gui; tunnel=$tunnel}} | ConvertTo-Json -Compress
"""
    )
    assert result == {
        "label": wanted,
        "gui": int(not running and not local),
        "tunnel": int(local and remote == "absent"),
    }


def test_observe_only_never_mutates_processes_or_retry_state() -> None:
    result = ps(
        """
function Get-QmObservation { @{OpenDRunning=$false; LocalReady=$false; RemoteListener='absent'} }
function Start-QmOpenD { throw 'unexpected GUI launch' }
function Start-QmTunnel { throw 'unexpected tunnel launch' }
$state=New-QmRecoveryState
$label=Invoke-QmRecoveryStep $state 'fake' 'fake' 100 -ObserveOnly
@{label=$label; next=$state.NextAttempt; child=($null -eq $state.Child)} | ConvertTo-Json -Compress
"""
    )
    assert result == {"label": "opend_not_running", "next": 0, "child": True}


def test_owned_child_exit_is_retried_after_delay_and_external_listener_is_respected() -> None:
    result = ps(
        """
$script:starts=0; $script:remote='absent'
function Get-QmObservation {
 @{OpenDRunning=$true; LocalReady=$true; RemoteListener=$script:remote}
}
function Start-QmTunnel { $script:starts++; [pscustomobject]@{HasExited=$false} }
$state=New-QmRecoveryState
$a=Invoke-QmRecoveryStep $state 'fake' 'fake' 100
$state.Child.HasExited=$true
$b=Invoke-QmRecoveryStep $state 'fake' 'fake' 101
$c=Invoke-QmRecoveryStep $state 'fake' 'fake' 120
$script:remote='present'
$d=Invoke-QmRecoveryStep $state 'fake' 'fake' 131
$script:remote='absent'
$e=Invoke-QmRecoveryStep $state 'fake' 'fake' 132
@{labels=@($a,$b,$c,$d,$e); starts=$starts} | ConvertTo-Json -Compress
"""
    )
    assert result == {
        "labels": [
            "private_tunnel_started",
            "retry_wait",
            "retry_wait",
            "existing_private_tunnel",
            "private_tunnel_started",
        ],
        "starts": 2,
    }


def test_unknown_process_observation_does_not_launch_gui() -> None:
    result = ps(
        """
function Get-QmObservation { @{OpenDRunning=$null; LocalReady=$false; RemoteListener='unknown'} }
function Start-QmOpenD { throw 'unexpected launch' }
$label=Invoke-QmRecoveryStep (New-QmRecoveryState) 'fake' 'fake' 100
@{label=$label} | ConvertTo-Json -Compress
"""
    )
    assert result == {"label": "opend_process_unknown"}


def test_gui_launch_is_not_repeated_while_process_start_is_unobserved() -> None:
    result = ps(
        """
$script:starts=0
function Get-QmObservation { @{OpenDRunning=$false; LocalReady=$false; RemoteListener='unknown'} }
function Start-QmOpenD { $script:starts++; return $true }
$state=New-QmRecoveryState
$a=Invoke-QmRecoveryStep $state 'fake' 'fake' 100
$b=Invoke-QmRecoveryStep $state 'fake' 'fake' 110
@{starts=$starts; second=$b} | ConvertTo-Json -Compress
"""
    )
    assert result == {"starts": 1, "second": "retry_wait"}


def test_native_singleton_rejects_second_helper_without_releasing_first() -> None:
    result = ps(
        """
$name='Local\\QuantMeshTest-'+[guid]::NewGuid().ToString('N')
$first=Enter-QmSingleton $name
$command=@'
. '{0}'; $m=Enter-QmSingleton '{1}'; if($null -eq $m){{exit 23}}
$m.ReleaseMutex(); $m.Dispose(); exit 0
'@ -f $testRecoverySource,$name
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$parameters=@('-NoProfile','-NonInteractive','-EncodedCommand',$encoded)
$child=Start-Process powershell.exe -ArgumentList $parameters -PassThru -Wait -WindowStyle Hidden
$first.ReleaseMutex(); $first.Dispose()
@{second=$child.ExitCode} | ConvertTo-Json -Compress
"""
    )
    assert result == {"second": 23}


def test_tunnel_command_keeps_both_endpoints_private_and_preserves_host_verification() -> None:
    result = ps(
        """
$args=Get-QmTunnelArguments
@{arguments=$args} | ConvertTo-Json -Compress
"""
    )
    args = result["arguments"]
    assert args[0:2] == ["ssh", "ubuntu@quantmesh-staging-8gb"]
    assert args[args.index("-R") + 1] == "127.0.0.1:11111:127.0.0.1:11111"
    assert "BatchMode=yes" in args
    assert "ExitOnForwardFailure=yes" in args
    assert not any("StrictHostKeyChecking=no" in arg for arg in args)


@pytest.mark.parametrize(
    "exit_code,token,wanted",
    [
        (0, "QM_LISTENER_PRESENT", "present"),
        (0, "QM_LISTENER_ABSENT", "absent"),
        (1, "QM_LISTENER_ABSENT", "unknown"),
        (0, "bad", "unknown"),
    ],
)
def test_failed_or_unrecognized_remote_probe_never_authorizes_spawn(
    exit_code: int, token: str, wanted: str
) -> None:
    result = ps(
        f"""
function Invoke-QmBoundedProbe {{ @{{ ExitCode={exit_code}; Output='{token}' }} }}
@{{listener=(Get-QmRemoteListener 'fake')}} | ConvertTo-Json -Compress
"""
    )
    assert result == {"listener": wanted}


def test_owned_install_is_reversible_and_preserves_unrelated_files(tmp_path: Path) -> None:
    root = str(tmp_path).replace("'", "''")
    result = ps(
        f"""
$script:links=@{{}}
function Write-QmShortcut($Path,$Target,$Arguments,$WorkingDirectory) {{
 $script:links[$Path]=@{{TargetPath=$Target; Arguments=$Arguments;
 WorkingDirectory=$WorkingDirectory}}
 Set-Content -LiteralPath $Path -Value 'test shortcut'
}}
function Read-QmShortcut($Path) {{ return $script:links[$Path] }}
$target=Join-Path '{root}' 'owned'; $startup=Join-Path '{root}' 'startup'
New-Item -ItemType Directory -Path $startup | Out-Null
Invoke-QmStartupProvision Install $target $startup 'C:\\fake\\OpenD.exe' `
 'C:\\fake\\tailscale.exe' | Out-Null
Set-Content -LiteralPath (Join-Path $target 'unrelated.txt') -Value 'keep'
$installationStatus=Invoke-QmStartupProvision Status $target $startup 'fake' 'fake'
Invoke-QmStartupProvision Uninstall $target $startup 'fake' 'fake' | Out-Null
@{{installed=$installationStatus.Installed;
 unrelated=(Test-Path (Join-Path $target 'unrelated.txt'));
 shortcut=(Test-Path (Join-Path $startup 'QuantMesh OpenD Recovery.lnk'));
 supervisor=(Test-Path (Join-Path $target 'opend_recovery.ps1'))}} | ConvertTo-Json -Compress
""",
        sources=(INSTALLER,),
    )
    assert result == {"installed": True, "unrelated": True, "shortcut": False, "supervisor": False}


@pytest.mark.parametrize("foreign", ["directory", "script", "shortcut"])
def test_provisioning_refuses_foreign_owned_target_or_replaced_files(
    tmp_path: Path, foreign: str
) -> None:
    root = str(tmp_path).replace("'", "''")
    result = ps(
        f"""
$script:links=@{{}}
function Write-QmShortcut($Path,$Target,$Arguments,$WorkingDirectory) {{
 $script:links[$Path]=@{{TargetPath=$Target; Arguments=$Arguments;
 WorkingDirectory=$WorkingDirectory}}
 Set-Content -LiteralPath $Path -Value 'test shortcut'
}}
function Read-QmShortcut($Path) {{ return $script:links[$Path] }}
$target=Join-Path '{root}' 'owned'; $startup=Join-Path '{root}' 'startup'
New-Item -ItemType Directory -Path $startup | Out-Null
if ('{foreign}' -eq 'directory') {{
 New-Item -ItemType Directory -Path $target | Out-Null
 Set-Content (Join-Path $target 'foreign.txt') 'keep'; $action='Install'
}}
else {{
 Invoke-QmStartupProvision Install $target $startup 'C:\\fake\\OpenD.exe' `
  'C:\\fake\\tailscale.exe' | Out-Null
 $action='Uninstall'
 if('{foreign}' -eq 'script') {{
  Set-Content (Join-Path $target 'opend_recovery.ps1') 'foreign'
 }} else {{
  $script:links[(Join-Path $startup 'QuantMesh OpenD Recovery.lnk')].Arguments='foreign'
 }}
}}
$refused=$false
try {{ Invoke-QmStartupProvision $action $target $startup 'fake' 'fake' | Out-Null }}
catch {{ $refused=$true }}
@{{refused=$refused; target=(Test-Path $target)}} | ConvertTo-Json -Compress
""",
        sources=(INSTALLER,),
    )
    assert result == {"refused": True, "target": True}


def test_scripts_parse_on_windows_powershell_51() -> None:
    result = ps(
        """
$bad=@()
foreach($path in @($testRecoverySource,$testInstallerSource)) {
 $tokens=$null; $errors=$null
 [Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors) | Out-Null
 $bad+=@($errors)
}
@{errors=$bad.Count; version=$PSVersionTable.PSVersion.Major} | ConvertTo-Json -Compress
""",
        sources=(RECOVERY, INSTALLER),
    )
    assert result == {"errors": 0, "version": 5}


def test_live_owned_child_without_remote_listener_does_not_claim_a_working_tunnel() -> None:
    result = ps(
        """
function Get-QmObservation { @{OpenDRunning=$true; LocalReady=$true; RemoteListener='unknown'} }
$state=New-QmRecoveryState
$state.Child=[pscustomobject]@{HasExited=$false}
$state.ChildStartedAt=100
$label=Invoke-QmRecoveryStep $state 'fake' 'fake' 110
@{label=$label} | ConvertTo-Json -Compress
"""
    )
    assert result == {"label": "needs_tailscale_or_ssh"}


def test_installer_rejects_junction_target_without_writing_external_files(tmp_path: Path) -> None:
    root = str(tmp_path).replace("'", "''")
    result = ps(
        f"""
$victim=Join-Path '{root}' 'victim'; $target=Join-Path '{root}' 'linked'
$startup=Join-Path '{root}' 'startup'
New-Item -ItemType Directory -Path $victim,$startup | Out-Null
New-Item -ItemType Junction -Path $target -Target $victim | Out-Null
$refused=$false
try {{ Invoke-QmStartupProvision Install $target $startup 'fake' 'fake' | Out-Null }}
catch {{ $refused=$true }}
@{{refused=$refused; files=@(Get-ChildItem $victim -Force).Count}} | ConvertTo-Json -Compress
""",
        sources=(INSTALLER,),
    )
    assert result == {"refused": True, "files": 0}


def test_unestablished_owned_child_times_out_without_stopping_external_processes() -> None:
    result = ps(
        """
function Get-QmObservation { @{OpenDRunning=$true; LocalReady=$true; RemoteListener='absent'} }
function Start-QmTunnel { throw 'unexpected competing launch' }
$script:stops=0
$child=[pscustomobject]@{HasExited=$false}
$child | Add-Member -MemberType ScriptMethod -Name Kill -Value {
 $script:stops++; $this.HasExited=$true
}
$child | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {}
$state=New-QmRecoveryState
$state.Child=$child; $state.ChildStartedAt=100
$label=Invoke-QmRecoveryStep $state 'fake' 'fake' 161
@{label=$label; stops=$stops; cleared=($null -eq $state.Child)} | ConvertTo-Json -Compress
"""
    )
    assert result == {"label": "retry_wait", "stops": 1, "cleared": True}


def test_existing_owned_tunnel_does_not_prevent_recovering_an_exited_gui() -> None:
    result = ps(
        """
$script:starts=0
function Get-QmObservation { @{OpenDRunning=$false; LocalReady=$false; RemoteListener='unknown'} }
function Start-QmOpenD { $script:starts++; return $true }
$state=New-QmRecoveryState
$state.Child=[pscustomobject]@{HasExited=$false}
$state.ChildStartedAt=100
$label=Invoke-QmRecoveryStep $state 'fake' 'fake' 110
@{label=$label; starts=$starts; existing=($null -ne $state.Child)} | ConvertTo-Json -Compress
"""
    )
    assert result == {"label": "opend_started", "starts": 1, "existing": True}


def test_uninstall_active_helper_only_removes_startup_and_defers_file_cleanup(
    tmp_path: Path,
) -> None:
    root = str(tmp_path).replace("'", "''")
    result = ps(
        f"""
$script:links=@{{}}
function Write-QmShortcut($Path,$Target,$Arguments,$WorkingDirectory) {{
 $script:links[$Path]=@{{TargetPath=$Target; Arguments=$Arguments;
 WorkingDirectory=$WorkingDirectory}}
 Set-Content -LiteralPath $Path -Value 'test shortcut'
}}
function Read-QmShortcut($Path) {{ return $script:links[$Path] }}
function Get-QmHelperActive {{ return $true }}
$target=Join-Path '{root}' 'owned'; $startup=Join-Path '{root}' 'startup'
New-Item -ItemType Directory -Path $startup | Out-Null
Invoke-QmStartupProvision Install $target $startup 'fake' 'fake' | Out-Null
$result=Invoke-QmStartupProvision Uninstall $target $startup 'fake' 'fake'
@{{state=$result.State; supervisor=(Test-Path (Join-Path $target 'opend_recovery.ps1'));
 startup=(Test-Path (Join-Path $startup 'QuantMesh OpenD Recovery.lnk'))
}} | ConvertTo-Json -Compress
""",
        sources=(INSTALLER,),
    )
    assert result == {
        "state": "startup_removed_cleanup_deferred",
        "supervisor": True,
        "startup": False,
    }


def test_bounded_probe_invokes_native_cli_with_host_before_ssh_options(tmp_path: Path) -> None:
    root = str(tmp_path).replace("'", "''")
    result = ps(
        rf"""
$source=@'
using System;
public class FakeCli {{
 public static int Main(string[] args) {{
  Console.Write(Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(String.Join("\0",args))));
  return 0;
 }}
}}
'@
$path=Join-Path '{root}' 'fake-cli.exe'
Add-Type -TypeDefinition $source -OutputAssembly $path -OutputType ConsoleApplication
$result=Invoke-QmBoundedProbe $path
@{{code=$result.ExitCode; encoded=$result.Output}} | ConvertTo-Json -Compress
"""
    )
    assert result["code"] == 0
    arguments = base64.b64decode(result["encoded"]).decode().split("\0")
    assert arguments[:2] == ["ssh", "ubuntu@quantmesh-staging-8gb"]
    assert arguments[-1].startswith("echo ")
    assert arguments[-1].endswith(" | base64 -d | python3")


@pytest.mark.parametrize(
    ("observed", "wanted"),
    [("unknown", "needs_tailscale_or_ssh"), ("absent", "private_tunnel_unavailable")],
)
def test_established_child_survives_later_unknown_or_absent_probe(
    observed: str, wanted: str
) -> None:
    result = ps(
        f"""
$script:remote='absent'; $script:stops=0; $script:starts=0
function Get-QmObservation {{
 @{{OpenDRunning=$true; LocalReady=$true; RemoteListener=$script:remote}}
}}
function Start-QmTunnel {{
 $script:starts++
 $child=[pscustomobject]@{{HasExited=$false}}
 $child | Add-Member -MemberType ScriptMethod -Name Kill -Value {{
  $script:stops++; $this.HasExited=$true
 }}
 $child | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {{}}
 return $child
}}
$state=New-QmRecoveryState
$started=Invoke-QmRecoveryStep $state 'fake' 'fake' 100
$script:remote='present'
$established=Invoke-QmRecoveryStep $state 'fake' 'fake' 110
$original=$state.Child
$script:remote='{observed}'
$later=Invoke-QmRecoveryStep $state 'fake' 'fake' 170
@{{labels=@($started,$established,$later); stops=$stops; starts=$starts;
 retained=[object]::ReferenceEquals($original,$state.Child)}} | ConvertTo-Json -Compress
"""
    )
    assert result == {
        "labels": ["private_tunnel_started", "managed_private_tunnel", wanted],
        "stops": 0,
        "starts": 1,
        "retained": True,
    }


def test_replacement_child_has_its_own_startup_timeout_after_established_child_exits() -> None:
    result = ps(
        """
$script:remote='absent'; $script:stops=0; $script:starts=0
function Get-QmObservation {
 @{OpenDRunning=$true; LocalReady=$true; RemoteListener=$script:remote}
}
function Start-QmTunnel {
 $script:starts++
 $child=[pscustomobject]@{HasExited=$false}
 $child | Add-Member -MemberType ScriptMethod -Name Kill -Value {
  $script:stops++; $this.HasExited=$true
 }
 $child | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {}
 return $child
}
$state=New-QmRecoveryState
$a=Invoke-QmRecoveryStep $state 'fake' 'fake' 100
$script:remote='present'
$b=Invoke-QmRecoveryStep $state 'fake' 'fake' 110
$state.Child.HasExited=$true; $script:remote='absent'
$c=Invoke-QmRecoveryStep $state 'fake' 'fake' 120
$d=Invoke-QmRecoveryStep $state 'fake' 'fake' 150
$e=Invoke-QmRecoveryStep $state 'fake' 'fake' 211
@{labels=@($a,$b,$c,$d,$e); starts=$starts; stops=$stops;
 cleared=($null -eq $state.Child)} | ConvertTo-Json -Compress
"""
    )
    assert result == {
        "labels": [
            "private_tunnel_started",
            "managed_private_tunnel",
            "retry_wait",
            "private_tunnel_started",
            "retry_wait",
        ],
        "starts": 2,
        "stops": 1,
        "cleared": True,
    }
