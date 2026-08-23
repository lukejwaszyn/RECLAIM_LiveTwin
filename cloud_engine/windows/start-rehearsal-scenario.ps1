[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("nominal", "power-outage", "lunar", "loss-of-data")]
    [string]$Scenario,

    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CloudEngineDir = Split-Path -Parent $ScriptDir
$RepositoryRoot = Split-Path -Parent $CloudEngineDir

# One-step bring-up: if the locked environment is not there yet, build it rather
# than failing. This is what makes any scenario runnable at any time from a fresh
# checkout with a single command.
if (-not $PythonExe) {
    $PythonExe = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonExe)) {
    Write-Host "Locked environment not found - bootstrapping it once (this takes a minute)..."
    Push-Location $RepositoryRoot
    try {
        & py -3.13 -m uv sync --locked --all-extras --dev --python 3.13
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE." }
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path $PythonExe)) {
        throw "Bootstrap did not produce $PythonExe. Run 'py -3.13 -m uv sync --locked --all-extras --dev --python 3.13' manually, or pass -PythonExe."
    }
    Write-Host "Locked environment ready."
}

$Profiles = @{
    "nominal" = @{
        EngineScenario = "nominal"
        Environment = "earth_lab"
        Port = 8177
        Speed = 2
        NoLoop = $false
        Expected = "Stable 2200 W Earth-lab heat-and-hold. One cycle is about 3 min 20 s wall time (400 s simulated at 2x), then it repeats until you stop it."
    }
    "power-outage" = @{
        EngineScenario = "power_outage"
        Environment = "earth_lab"
        Port = 8178
        Speed = 4
        NoLoop = $false
        Expected = "3500 W heating; S_PowerInterrupted/P_fwd=0 near 1 min 53 s, S_Restart near 3 min 8 s, cycle about 3 min 45 s wall time (900 s simulated at 4x), then it repeats until you stop it."
    }
    "lunar" = @{
        EngineScenario = "nominal"
        Environment = "lunar_surface"
        Port = 8179
        Speed = 2
        NoLoop = $false
        Expected = "Stable 2200 W heat-and-hold using lunar_surface physics. One cycle is about 3 min 20 s wall time (400 s simulated at 2x), then it repeats until you stop it."
    }
    "loss-of-data" = @{
        EngineScenario = "nominal"
        Environment = "earth_lab"
        Port = 8181
        Speed = 2
        NoLoop = $true
        Expected = "Freshness/staleness rehearsal. Runs ONE cycle (about 3 min 20 s wall time) then STOPS UPDATING while the endpoints stay served: /health and /state keep answering with the last values readable, but status flips to stopped and t_sim freezes. The stack must report staleness, not hold or fabricate a last-good value."
    }
}

$Selected = $Profiles[$Scenario]
$ExistingListener = Get-NetTCPConnection -State Listen -LocalPort $Selected.Port `
    -ErrorAction SilentlyContinue
if ($ExistingListener) {
    throw "Port $($Selected.Port) already has a listener; stop it or verify ownership before continuing."
}

Write-Host "RECLAIM synthetic rehearsal - advisory-only, no actuator authority"
Write-Host "Profile: $Scenario | scenario=$($Selected.EngineScenario) | environment=$($Selected.Environment) | port=$($Selected.Port) | speed=$($Selected.Speed)x"
Write-Host "Expected: $($Selected.Expected)"
Write-Host "Verify: Invoke-RestMethod http://127.0.0.1:$($Selected.Port)/health"
Write-Host "Inspect: Invoke-RestMethod http://127.0.0.1:$($Selected.Port)/state"
Write-Host "History: Invoke-RestMethod http://127.0.0.1:$($Selected.Port)/history"
Write-Host "Stop with Ctrl+C. This command never uses production port 8078."

$EngineArgs = @(
    "-m", "reclaim_predictive_engine.service",
    "--scenario", $Selected.EngineScenario,
    "--env", $Selected.Environment,
    "--host", $BindHost,
    "--port", $Selected.Port,
    "--speed", $Selected.Speed,
    "--feed", "harness"
)
if ($Selected.NoLoop) { $EngineArgs += "--no-loop" }

Push-Location $CloudEngineDir
$ProcessExitCode = 1
try {
    & $PythonExe @EngineArgs
    $ProcessExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ProcessExitCode
