[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallRoot = "C:\ProgramData\RECLAIM\convene-bridge",
    [switch]$ArchiveSimVars,
    [switch]$PurgeBridgeData
)

$ErrorActionPreference = "Stop"
$ServiceId = "RECLAIMStateBridge"
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$MarkerPath = Join-Path $InstallRoot ".reclaim-state-bridge-owned.json"

if (-not (Test-Path $InstallRoot)) {
    Write-Host "Bridge install root is already absent; nothing to roll back."
    return
}
if (-not (Test-Path $MarkerPath)) {
    throw "Ownership marker is absent. Refusing to remove an unexpected deployment."
}
$Marker = Get-Content -Raw $MarkerPath | ConvertFrom-Json
if ($Marker.schema -ne "reclaim.convene-bridge.install.v1" -or $Marker.service_id -ne $ServiceId) {
    throw "Ownership marker does not match this bridge. No changes made."
}
$OutputPath = [string]$Marker.output_path
$ServiceExe = Join-Path $InstallRoot "service\reclaim-state-bridge.exe"

Write-Host "Rollback scope: service=$ServiceId root=$InstallRoot output=$OutputPath"
Get-Service -Name $ServiceId -ErrorAction SilentlyContinue | Format-Table Name, Status | Out-Host
Get-ScheduledTask | Where-Object { $_.TaskName -match "Convene" } |
    Select-Object TaskName, TaskPath, State | Format-Table | Out-Host

if (-not $PSCmdlet.ShouldProcess($InstallRoot, "Uninstall only owned bridge artifacts")) { return }

$Service = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue
if ($Service) {
    if ($Service.Status -ne "Stopped") {
        Stop-Service -Name $ServiceId
        $Service.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
    }
    if (-not (Test-Path $ServiceExe)) {
        throw "Owned service exists but its WinSW executable is missing; stop for operator direction."
    }
    & $ServiceExe uninstall
    if ($LASTEXITCODE -ne 0) { throw "WinSW service uninstall failed" }
}

if ($ArchiveSimVars -and (Test-Path $OutputPath)) {
    $Archive = "$OutputPath.bridge-rollback-$(Get-Date -Format yyyyMMddHHmmss)"
    Copy-Item $OutputPath $Archive
    Write-Host "Archived sim_vars.json to $Archive; original remains in place."
}

# The existing Convene task and sim_vars.json are intentionally preserved.
foreach ($owned in @("app", "service", "venv")) {
    Remove-Item -Recurse -Force (Join-Path $InstallRoot $owned) -ErrorAction SilentlyContinue
}
if ($PurgeBridgeData) {
    Remove-Item -Recurse -Force $InstallRoot
    Write-Host "Removed all bridge-owned configuration, secret, state, and log data."
} else {
    Write-Host "Preserved bridge config, secrets, state, and logs under $InstallRoot for diagnosis/reinstall."
}
Write-Host "The existing VM Convene task and $OutputPath were not removed or unregistered."
