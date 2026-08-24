<#
.SYNOPSIS
Read-only audit of a Windows VM before the Convene-routed engine cutover.
#>
[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$EngineService = 'RECLAIMIngestEngine',
    [int]$EnginePort = 8078
)

$ErrorActionPreference = 'Stop'
$engineSource = Join-Path $RepositoryRoot 'cloud_engine\push_ingest_dual.py'
$runner = Join-Path $RepositoryRoot 'cloud_engine\windows\run-ingest-engine.ps1'
$serviceTemplate = Join-Path $RepositoryRoot 'cloud_engine\windows\reclaim-ingest.xml'

foreach ($required in @($engineSource, $runner, $serviceTemplate)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required current artifact is absent: $required"
    }
}

$sha = (& git -C $RepositoryRoot rev-parse HEAD 2>$null).Trim()
$dirty = @(& git -C $RepositoryRoot status --porcelain 2>$null)
$engineText = [IO.File]::ReadAllText($engineSource)
$requiredMarkers = @(
    'normalize_convene_frame',
    '_coerce_file_watch_value',
    'convene_result_variables',
    'live, harness, or replay mode'
)
$missingMarkers = @($requiredMarkers | Where-Object { $engineText -notmatch [regex]::Escape($_) })

$services = @('RECLAIMIngestEngine', 'RECLAIMStateBridge', 'cloudflared') | ForEach-Object {
    $service = Get-Service -Name $_ -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Name = $_
        Present = $null -ne $service
        Status = if ($service) { [string]$service.Status } else { 'NotFound' }
    }
}

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $EnginePort -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess)
$cloudflaredProcesses = @(Get-Process -Name cloudflared -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName)
$obsoleteTasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match 'RECLAIM.*(Bridge|Tunnel|Scenario)|StateBridge|QuickTunnel' } |
    Select-Object TaskName, State)
$obsoleteFiles = @(
    'C:\ConveneAgent\sim_vars.json',
    'C:\ProgramData\RECLAIM\convene-bridge',
    'C:\ProgramData\RECLAIM\cloudflared-quick'
) | ForEach-Object {
    [pscustomobject]@{ Path = $_; Present = Test-Path -LiteralPath $_ }
}

$health = $null
$healthError = $null
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$EnginePort/health" -TimeoutSec 5
} catch {
    $healthError = $_.Exception.Message
}

$blocking = @()
if ($dirty.Count -ne 0) { $blocking += 'repository_dirty' }
if ($missingMarkers.Count -ne 0) { $blocking += 'engine_contract_markers_missing' }
if (@($listeners).Count -ne 1 -or $listeners[0].LocalAddress -notin @('127.0.0.1', '::1')) {
    $blocking += 'engine_listener_not_single_loopback'
}
if (-not $health -or -not $health.ok) { $blocking += 'engine_health_failed' }
if (($services | Where-Object Name -eq 'RECLAIMStateBridge').Status -ne 'NotFound') {
    $blocking += 'deprecated_state_bridge_registered'
}
if (($services | Where-Object Name -eq 'cloudflared').Status -ne 'NotFound' -or
    $cloudflaredProcesses.Count -ne 0) {
    $blocking += 'deprecated_application_tunnel_present'
}
if (@($obsoleteFiles | Where-Object Present).Count -ne 0) { $blocking += 'deprecated_handoff_files_present' }
if ($obsoleteTasks.Count -ne 0) { $blocking += 'deprecated_scheduled_tasks_present' }

[pscustomobject]@{
    Schema = 'reclaim.convene-routed-vm-audit.v1'
    TimestampUtc = [DateTime]::UtcNow.ToString('o')
    RepositoryRoot = $RepositoryRoot
    GitSha = $sha
    RepositoryDirty = $dirty.Count -ne 0
    EngineSourceSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $engineSource).Hash
    MissingContractMarkers = $missingMarkers
    Services = $services
    Listeners = $listeners
    CloudflaredProcesses = $cloudflaredProcesses
    ObsoleteScheduledTasks = $obsoleteTasks
    ObsoleteFiles = $obsoleteFiles
    Health = $health
    HealthError = $healthError
    Blockers = $blocking
    ReadyForSupervisedContractTest = $blocking.Count -eq 0
} | ConvertTo-Json -Depth 8

if ($blocking.Count -ne 0) { exit 2 }
