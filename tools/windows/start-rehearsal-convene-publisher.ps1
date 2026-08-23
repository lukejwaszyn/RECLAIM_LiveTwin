<#
.SYNOPSIS
    Push a running rehearsal scenario's /state into Convene, without collectors.

.DESCRIPTION
    Convene is supposed to poll the rehearsal services through heartbeat-delivered
    collectors. That path is dead while the backend lacks its machineCommands
    composite index (deployment\CONVENE_FIRESTORE_INDEX_HANDOVER.md), so this
    pushes instead -- the same direct /machine/publish technique the gateway's
    gw_ audit tap already proves.

    Each profile publishes under its own non-live identity and rehearsal_ prefix
    per the isolation contract. Start the scenario first with
    start-rehearsal-scenario.ps1, then run this alongside it.

.EXAMPLE
    # Prove the mapping without touching Convene at all:
    .\start-rehearsal-convene-publisher.ps1 nominal -DryRun

.EXAMPLE
    .\start-rehearsal-convene-publisher.ps1 nominal `
        -Api https://<backend>/api `
        -Credential C:\ProgramData\RECLAIM\rehearsal\nominal.convene_agent.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("nominal", "power-outage", "lunar")]
    [string]$Scenario,

    [string]$Api = $env:CONVENE_API,
    [string]$Credential = $env:REHEARSAL_CONVENE_CREDENTIAL,
    [double]$Interval = 5.0,
    [switch]$Once,
    [switch]$DryRun,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolsDir = Split-Path -Parent $ScriptDir
$RepositoryRoot = Split-Path -Parent $ToolsDir

if (-not $PythonExe) {
    $PythonExe = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    throw "Locked environment not found at $PythonExe. Run cloud_engine\windows\start-rehearsal-scenario.ps1 once to bootstrap it, or pass -PythonExe."
}

# The scenario must already be serving; publishing an empty namespace would
# register a rehearsal machine that never advances, which is worse than a clear
# failure here.
$Ports = @{ "nominal" = 8177; "power-outage" = 8178; "lunar" = 8179 }
$Port = $Ports[$Scenario]
if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
    throw "No scenario is listening on 127.0.0.1:$Port. Start it first: .\cloud_engine\windows\start-rehearsal-scenario.ps1 $Scenario"
}

Write-Host "RECLAIM rehearsal Convene publisher - synthetic data, non-live identity"
Write-Host "Profile: $Scenario | source: http://127.0.0.1:$Port/state"
if ($DryRun) {
    Write-Host "DRY RUN - prints the variables and publishes nothing."
}

$PublisherArgs = @("-m", "rehearsal_convene", $Scenario, "--interval", $Interval)
if ($Api)        { $PublisherArgs += @("--api", $Api) }
if ($Credential) { $PublisherArgs += @("--credential", $Credential) }
if ($Once)       { $PublisherArgs += "--once" }
if ($DryRun)     { $PublisherArgs += "--dry-run" }

$env:PYTHONPATH = $ToolsDir
Push-Location $ToolsDir
$ProcessExitCode = 1
try {
    & $PythonExe @PublisherArgs
    $ProcessExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
exit $ProcessExitCode
