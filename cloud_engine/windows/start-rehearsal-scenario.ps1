[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("nominal", "power-outage", "lunar")]
    [string]$Scenario,

    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CloudEngineDir = Split-Path -Parent $ScriptDir
$RepositoryRoot = Split-Path -Parent $CloudEngineDir

if (-not $PythonExe) {
    $PythonExe = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    throw "Locked-environment Python was not found: $PythonExe"
}

$Profiles = @{
    "nominal" = @{
        EngineScenario = "nominal"
        Environment = "earth_lab"
        Port = 8177
        Speed = 2
        Expected = "Stable 2200 W Earth-lab heat-and-hold; one cycle is about 3 min 20 s wall time (400 s simulated at 2x)."
    }
    "power-outage" = @{
        EngineScenario = "power_outage"
        Environment = "earth_lab"
        Port = 8178
        Speed = 4
        Expected = "3500 W heating; S_PowerInterrupted/P_fwd=0 near 1 min 53 s, S_Restart near 3 min 8 s, cycle about 3 min 45 s wall time (900 s simulated at 4x)."
    }
    "lunar" = @{
        EngineScenario = "nominal"
        Environment = "lunar_surface"
        Port = 8179
        Speed = 2
        Expected = "Stable 2200 W heat-and-hold using lunar_surface physics; one cycle is about 3 min 20 s wall time (400 s simulated at 2x)."
    }
}

$Selected = $Profiles[$Scenario]
$ExistingListener = Get-NetTCPConnection -State Listen -LocalPort $Selected.Port `
    -ErrorAction SilentlyContinue
if ($ExistingListener) {
    throw "Port $($Selected.Port) already has a listener; stop it or verify ownership before continuing."
}

Write-Host "RECLAIM synthetic rehearsal — advisory-only, no actuator authority"
Write-Host "Profile: $Scenario | scenario=$($Selected.EngineScenario) | environment=$($Selected.Environment) | port=$($Selected.Port) | speed=$($Selected.Speed)x"
Write-Host "Expected: $($Selected.Expected)"
Write-Host "Verify: Invoke-RestMethod http://127.0.0.1:$($Selected.Port)/health"
Write-Host "Inspect: Invoke-RestMethod http://127.0.0.1:$($Selected.Port)/state"
Write-Host "History: Invoke-RestMethod http://127.0.0.1:$($Selected.Port)/history"
Write-Host "Stop with Ctrl+C. This command never uses production port 8078."

Push-Location $CloudEngineDir
$ProcessExitCode = 1
try {
    & $PythonExe -m reclaim_predictive_engine.service `
        --scenario $Selected.EngineScenario `
        --env $Selected.Environment `
        --host $BindHost `
        --port $Selected.Port `
        --speed $Selected.Speed `
        --feed harness
    $ProcessExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ProcessExitCode
