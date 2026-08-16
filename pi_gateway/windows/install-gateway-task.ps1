# RECLAIM Edge Gateway — always-on installation for the Windows 10 laptop relay.
# Run once from an elevated PowerShell. Registers a Scheduled Task that:
#   * starts the gateway at machine boot (no login required, runs as SYSTEM),
#   * restarts it within 1 minute if it exits with a failure (the gateway
#     deliberately exits non-zero when a worker thread dies — fix M6), and
#   * never restarts a clean operator stop (exit 0), so intentional shutdowns
#     stay shut down.
# This is the architectural "constant transfer" guarantee: telemetry relays to
# the cloud continuously from boot, with no per-launch backend spin-up.

$ErrorActionPreference = "Stop"

$GatewayDir  = "C:\RECLAIM\pi_gateway"
$Python      = Join-Path $GatewayDir ".venv\Scripts\python.exe"
$ConfigPath  = Join-Path $GatewayDir "config.windows.yaml"
$TaskName    = "RECLAIM-EdgeGateway"

if (-not (Test-Path $Python))     { throw "venv python not found: $Python (create the venv first)" }
if (-not (Test-Path $ConfigPath)) { throw "config not found: $ConfigPath (the gateway fails fast without it)" }

# Config path as a MACHINE environment variable so the SYSTEM task sees it.
[Environment]::SetEnvironmentVariable("RECLAIM_EDGE_CONFIG", $ConfigPath, "Machine")

# Durable buffer location (matches config.windows.yaml buffer_path).
New-Item -ItemType Directory -Force "C:\ProgramData\RECLAIM" | Out-Null

$action    = New-ScheduledTaskAction -Execute $Python -Argument "-m reclaim_edge.main" `
                                     -WorkingDirectory $GatewayDir
$trigger   = New-ScheduledTaskTrigger -AtStartup
$settings  = New-ScheduledTaskSettingsSet `
                -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
                -ExecutionTimeLimit ([TimeSpan]::Zero) `
                -StartWhenAvailable `
                -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
                       -Settings $settings -Principal $principal -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started '$TaskName'."
Write-Host "Verify:  http://127.0.0.1:9080/health   (rx/tx/queue/dead_letter)"
Write-Host "         http://127.0.0.1:9080/command  (twin CommandSignal for the HMI)"
Write-Host "Stop:    Stop-ScheduledTask -TaskName $TaskName   (clean stop, no auto-restart)"
