<#
.SYNOPSIS
Registers the token-bearing, VM-specific Convene agent as a headless SYSTEM startup task.
.NOTES
Run elevated only after the Convene-provided installer has created C:\ConveneAgent\agent.ps1.
The script validates identity and handoff paths without emitting the embedded credential.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = [Security.Principal.WindowsPrincipal]$identity
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Convene task registration must run elevated.'
}

$agentRoot = 'C:\ConveneAgent'
$agentScript = Join-Path $agentRoot 'agent.ps1'
if (-not (Test-Path -LiteralPath $agentScript)) { throw 'Installed Convene agent script is absent.' }

# A prior partial hardening may have left SYSTEM as the only effective reader.
# Restore the two intended administrative principals before inspecting content;
# no token-bearing file content is emitted.
takeown.exe /F $agentRoot /A /R /D Y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not take ownership of the Convene agent directory.' }
icacls.exe $agentRoot /inheritance:r /grant:r `
  'SYSTEM:(OI)(CI)(F)' 'BUILTIN\Administrators:(OI)(CI)(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restore the Convene agent directory ACL.' }
icacls.exe (Join-Path $agentRoot '*') /inheritance:r /grant:r `
  'SYSTEM:(F)' 'BUILTIN\Administrators:(F)' /T /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restore Convene agent file ACLs.' }

$agentText = Get-Content -Raw -LiteralPath $agentScript
if ($agentText -notmatch '(?m)^\s*\$VMID\s*=\s*''reclaim-engine-2''\s*$') { throw 'Unexpected Convene VM identity.' }
if ($agentText -notmatch [regex]::Escape("C:\ConveneAgent\sim_vars.json")) { throw 'Agent does not read the required sim_vars path.' }
if ($agentText -notmatch 'reservation-backend-xczhrp2y6q-uc\.a\.run\.app') { throw 'Unexpected Convene backend.' }

$taskName = 'ConveneAgent'
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction -Execute $powershell `
  -Argument '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\ConveneAgent\agent.ps1"' `
  -WorkingDirectory $agentRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null

$inputPath = Join-Path $agentRoot 'convene_inputs.json'
$before = if (Test-Path $inputPath) { (Get-Item $inputPath).LastWriteTimeUtc } else { [datetime]::MinValue }
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 4
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
$after = if (Test-Path $inputPath) { (Get-Item $inputPath).LastWriteTimeUtc } else { [datetime]::MinValue }
if ($task.State -ne 'Running') { throw "Convene agent task state is $($task.State), expected Running." }
if ($after -le $before) { throw 'Convene input file did not advance after task start.' }
[pscustomobject]@{
  TaskName=$task.TaskName
  State=$task.State
  Principal=$task.Principal.UserId
  LogonType=$task.Principal.LogonType
  LastRunTime=$info.LastRunTime
  LastTaskResult=$info.LastTaskResult
  InputFileAdvanced=$true
  AgentRootAclLocked=$true
  DesktopStreaming=$false
} | Format-List
