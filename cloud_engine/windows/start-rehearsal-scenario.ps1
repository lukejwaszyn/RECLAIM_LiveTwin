[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("nominal", "power-outage", "lunar", "loss-of-data")]
    [string]$Scenario,

    [string]$PythonExe = "",
    [string]$GatewayAddress = "192.168.1.1",
    [ValidateRange(1, 65535)]
    [int]$GatewayPort = 9070,
    [string]$StatusBase = "http://127.0.0.1:9080"
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
        Speed = 1
        NoLoop = $false
        Expected = "Stable 2200 W Earth-lab heat-and-hold at the shared engine's 1 Hz acceptance cadence. One 400 s simulated cycle takes about 6 min 40 s, then repeats."
    }
    "power-outage" = @{
        EngineScenario = "power_outage"
        Environment = "earth_lab"
        Speed = 1
        NoLoop = $false
        Expected = "3500 W heating; S_PowerInterrupted/P_fwd=0 near 7 min 30 s, S_Restart near 12 min 30 s, and one 900 s cycle takes about 15 min at 1 Hz."
    }
    "lunar" = @{
        EngineScenario = "nominal"
        Environment = "lunar_surface"
        Speed = 1
        NoLoop = $false
        Expected = "Stable 2200 W heat-and-hold using lunar_surface physics at 1 Hz. One 400 s simulated cycle takes about 6 min 40 s, then repeats."
    }
    "loss-of-data" = @{
        EngineScenario = "nominal"
        Environment = "earth_lab"
        Speed = 1
        NoLoop = $true
        Expected = "Freshness/staleness rehearsal. Runs one 400 s cycle at 1 Hz (about 6 min 40 s), then disconnects. gw_* stops advancing and the cloud bridge must make sim_data_live false."
    }
}

$Selected = $Profiles[$Scenario]
$GatewayListener = @(Get-NetTCPConnection -State Listen -LocalPort $GatewayPort `
    -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -eq $GatewayAddress })
if ($GatewayListener.Count -ne 1) {
    throw "The edge gateway is not listening at ${GatewayAddress}:$GatewayPort. Start/restart the RECLAIM-Edge-Gateway task first."
}
$RealCrioSession = @(Get-NetTCPConnection -LocalPort $GatewayPort -RemoteAddress "192.168.1.2" `
    -ErrorAction SilentlyContinue | Where-Object { $_.State -in @("Established", "SynReceived") })
if ($RealCrioSession.Count -gt 0) {
    throw "The real cRIO is connected or waiting; refusing to mix scenario telemetry into its stream."
}
try {
    $GatewayHealth = Invoke-RestMethod -Uri "$StatusBase/health" -TimeoutSec 10
}
catch {
    throw "Gateway status is unavailable at $StatusBase/health. Restart the gateway from this repo before running a scenario. $($_.Exception.Message)"
}
if ($GatewayHealth.transport -ne "https") {
    throw "Gateway transport is '$($GatewayHealth.transport)', not https; frames would not reach the cloud engine."
}
if (-not $GatewayHealth.convene.enabled) {
    throw "Gateway Convene fan-out is disabled; frames would not produce gw_* output."
}
if (-not ($GatewayHealth.PSObject.Properties.Name -contains "mode")) {
    throw "Gateway status does not expose mode. Redeploy/restart the gateway from this revision before running a scenario."
}
if ($GatewayHealth.mode -ne "live") {
    throw "Gateway mode is '$($GatewayHealth.mode)'. The deployed cloud engine and sim_ bridge require mode=live."
}

Write-Host "RECLAIM synthetic rehearsal - advisory-only, no actuator authority"
Write-Host "Profile: $Scenario | scenario=$($Selected.EngineScenario) | environment=$($Selected.Environment) | speed=$($Selected.Speed)x"
Write-Host "Expected: $($Selected.Expected)"
Write-Host "ONE PATH: scenario -> gateway ${GatewayAddress}:$GatewayPort -> gw_* Convene + cloud engine -> sim_* Convene"
Write-Host "Monitor gateway: Invoke-RestMethod $StatusBase/health"
Write-Host "Inspect canonical frame: Invoke-RestMethod $StatusBase/latest"
Write-Host "Stop with Ctrl+C."

$EngineArgs = @(
    (Join-Path $RepositoryRoot "tools\synthetic_crio.py"),
    "--scenario", $Selected.EngineScenario,
    "--env", $Selected.Environment,
    "--host", $GatewayAddress,
    "--port", $GatewayPort,
    "--speed", $Selected.Speed
)
if ($Selected.NoLoop) { $EngineArgs += @("--cycles", 1) }

Push-Location $RepositoryRoot
$ProcessExitCode = 1
try {
    & $PythonExe @EngineArgs
    $ProcessExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ProcessExitCode
