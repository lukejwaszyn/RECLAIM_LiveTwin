<#
.SYNOPSIS
Proves public ingress, exact engine-to-bridge correlation, Convene handoff, and stale expiry.
.PARAMETER PublicUrl
HTTPS origin routed by cloudflared to the loopback production engine.
.PARAMETER FrameCount
Number of monotonically sequenced live frames to publish.
.PARAMETER FrameIntervalMs
Delay between frames; defaults to 900 ms to span multiple Convene heartbeats.
.PARAMETER ExpiryTimeoutSec
Maximum time allowed for the bridge to publish stale/data_live=false after source stop.
.NOTES
Requires elevated PowerShell to read protected engine credentials and Convene task state.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^https://')]
    [string]$PublicUrl,

    [ValidateRange(10, 300)]
    [int]$FrameCount = 50,

    [ValidateRange(100, 5000)]
    [int]$FrameIntervalMs = 900,

    [ValidateRange(20, 120)]
    [int]$ExpiryTimeoutSec = 35
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Live/expiry proof must run elevated.'
}

$publicUrl = $PublicUrl.TrimEnd('/')
$engineService = 'RECLAIMIngestEngine'
$bridgeService = 'RECLAIMStateBridge'
$secretFile = 'C:\ProgramData\RECLAIM\engine\secrets\reclaim-ingest.env'
$outputPath = 'C:\ConveneAgent\sim_vars.json'
$runId = "convene-live-$([guid]::NewGuid().ToString('N').Substring(0,12))"
$sourceId = 'vm-convene-bridge-proof'

if ((Get-Service -Name $engineService -ErrorAction Stop).Status -ne 'Running' -or
    (Get-Service -Name $bridgeService -ErrorAction Stop).Status -ne 'Running') {
    throw 'Engine and bridge must both be running; no telemetry was sent.'
}
$localHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/health' -TimeoutSec 5
$publicHealth = Invoke-RestMethod -Uri "$publicUrl/health" -TimeoutSec 15
if (-not $localHealth.ok -or -not $publicHealth.ok) {
    throw 'Local or public health failed; no telemetry was sent.'
}

$secrets = @{}
foreach ($line in Get-Content -LiteralPath $secretFile) {
    $name, $value = $line.Split('=', 2)
    if ($name -in @('RECLAIM_INGEST_TOKEN', 'RECLAIM_READ_TOKEN')) {
        $secrets[$name] = $value
    }
}
if ($secrets.Count -ne 2 -or
    [string]::IsNullOrWhiteSpace($secrets.RECLAIM_INGEST_TOKEN) -or
    [string]::IsNullOrWhiteSpace($secrets.RECLAIM_READ_TOKEN) -or
    $secrets.RECLAIM_INGEST_TOKEN -eq $secrets.RECLAIM_READ_TOKEN) {
    throw 'Expected two distinct non-empty engine credentials.'
}

$ingestHeaders = @{ Authorization = "Bearer $($secrets.RECLAIM_INGEST_TOKEN)" }
$readHeaders = @{ Authorization = "Bearer $($secrets.RECLAIM_READ_TOKEN)" }
$livePayload = $null
$lastSeq = 0

try {
    Write-Host "Publishing correlated live telemetry through $publicUrl"
    Write-Host "RunId=$runId SourceId=$sourceId"
    for ($seq = 1; $seq -le $FrameCount; $seq++) {
        $frame = [ordered]@{
            schema_version = 'reclaim.telemetry.v1'
            mode = 'live'
            run_id = $runId
            source_id = $sourceId
            seq = $seq
            ts = (Get-Date).ToUniversalTime().ToString('o')
            cycle_id = "convene-proof-$seq"
            source_op_state = 'S_MicrowaveHeating'
            active_chamber = 'PL'
            vars = [ordered]@{
                PL_T_bed_tc1 = 623.15 + ($seq * 0.01)
                PL_T_bed_tc2 = 624.15 + ($seq * 0.01)
                PL_T_bed_tc3 = 622.15 + ($seq * 0.01)
                PL_T_bed_tc4 = 623.65 + ($seq * 0.01)
                PL_T_wall_meas = 450.0
                PL_P_fwd = 3000.0
                PL_P_refl = 100.0
                PL_P_chamber = 95.0
                MT_T_bed_tc1 = 700.0
                MT_T_wall_meas = 500.0
                MT_P_fwd = 0.0
                MT_P_refl = 0.0
                MT_P_chamber = 101.0
            }
        }
        $body = $frame | ConvertTo-Json -Depth 6 -Compress
        $response = Invoke-RestMethod -Method Post -Uri "$publicUrl/ingest" `
            -Headers $ingestHeaders -ContentType 'application/x-ndjson' -Body $body -TimeoutSec 15
        if ($response.results[0].status -ne 'accepted') {
            throw "Public ingress did not accept sequence $seq; disposition=$($response.results[0].status)"
        }
        $lastSeq = $seq

        try {
            $candidate = [IO.File]::ReadAllText($outputPath) | ConvertFrom-Json
            if ($candidate.run_id -eq $runId -and
                $candidate.source_id -eq $sourceId -and
                $candidate.data_live -eq $true -and
                $candidate.bridge_status -eq 'ok') {
                $livePayload = $candidate
            }
        } catch {
            # Atomic replacement can make the file transiently unavailable to a reader.
        }

        if ($seq % 10 -eq 0) {
            Write-Host "  accepted through seq=$seq"
        }
        Start-Sleep -Milliseconds $FrameIntervalMs
    }

    $state = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/state' -Headers $readHeaders -TimeoutSec 5
    if ($state.schema_version -ne 'reclaim.state.v1' -or
        $state.run_id -ne $runId -or $state.source_id -ne $sourceId -or
        $state.seq -ne $lastSeq -or $state.ingest_status -ne 'accepted') {
        throw 'Authenticated engine state did not correlate to the final public-ingress frame.'
    }

    # Require the exact final sequence at both engine and bridge boundaries.
    $livePayload = $null
    $liveDeadline = (Get-Date).AddSeconds(8)
    do {
        try {
            $candidate = [IO.File]::ReadAllText($outputPath) | ConvertFrom-Json
            if ($candidate.run_id -eq $runId -and
                $candidate.source_id -eq $sourceId -and
                $candidate.seq -eq $lastSeq -and
                $candidate.data_live -eq $true -and
                $candidate.bridge_status -eq 'ok') {
                $livePayload = $candidate
            }
        } catch {}
        if (-not $livePayload) { Start-Sleep -Milliseconds 250 }
    } while (-not $livePayload -and (Get-Date) -lt $liveDeadline)
    if (-not $livePayload) {
        throw 'Bridge did not publish correlated live state after the public telemetry stream.'
    }

    $liveProperties = @($livePayload.PSObject.Properties)
    $liveInvalid = @($liveProperties | Where-Object {
        $null -eq $_.Value -or $_.Value -is [array] -or $_.Value -is [pscustomobject]
    })
    $livePrefixed = @($liveProperties | Where-Object { $_.Name -like 'sim_*' })
    if ($liveInvalid.Count -ne 0 -or $livePrefixed.Count -ne 0) {
        throw 'Live bridge payload violated the flat scalar or exactly-one-prefix contract.'
    }

    $liveEvidence = [pscustomobject]@{
        Boundary = 'convene-live-public-ingress'
        Timestamp = (Get-Date).ToUniversalTime().ToString('o')
        RunId = $livePayload.run_id
        SourceId = $livePayload.source_id
        EngineSeq = $state.seq
        BridgeSeq = $livePayload.seq
        EngineStateAgeMs = $state.state_age_ms
        BridgeStatus = $livePayload.bridge_status
        DataLive = $livePayload.data_live
        BridgeValidUntil = $livePayload.bridge_valid_until
        FlatScalarOnly = ($liveInvalid.Count -eq 0)
        ExistingSimPrefixCount = $livePrefixed.Count
        PublicIngress = $publicUrl
    }

    Write-Host 'LIVE BOUNDARY PROVEN; telemetry source is now stopped.'
    $liveEvidence | Format-List

    $expiredPayload = $null
    $expiryDeadline = (Get-Date).AddSeconds($ExpiryTimeoutSec)
    do {
        try {
            $candidate = [IO.File]::ReadAllText($outputPath) | ConvertFrom-Json
            if ($candidate.run_id -eq $runId -and
                $candidate.source_id -eq $sourceId -and
                $candidate.seq -eq $lastSeq -and
                $candidate.data_live -eq $false -and
                $candidate.bridge_status -eq 'stale') {
                $expiredPayload = $candidate
            }
        } catch {}
        if (-not $expiredPayload) { Start-Sleep -Milliseconds 500 }
    } while (-not $expiredPayload -and (Get-Date) -lt $expiryDeadline)
    if (-not $expiredPayload) {
        throw "Bridge did not transition the correlated source to stale/data_live=false within $ExpiryTimeoutSec seconds."
    }

    $task = Get-ScheduledTask -TaskName 'ConveneAgent' -ErrorAction Stop
    $taskInfo = Get-ScheduledTaskInfo -TaskName 'ConveneAgent' -ErrorAction Stop
    Write-Host 'FAIL-CLOSED EXPIRY PROVEN'
    [pscustomobject]@{
        Boundary = 'convene-source-expired'
        Timestamp = (Get-Date).ToUniversalTime().ToString('o')
        RunId = $expiredPayload.run_id
        SourceId = $expiredPayload.source_id
        Seq = $expiredPayload.seq
        BridgeStatus = $expiredPayload.bridge_status
        BridgeErrorCode = $expiredPayload.bridge_error_code
        DataLive = $expiredPayload.data_live
        BridgeObservedAt = $expiredPayload.bridge_observed_at
        BridgeValidUntil = $expiredPayload.bridge_valid_until
        EngineService = (Get-Service -Name $engineService).Status
        BridgeService = (Get-Service -Name $bridgeService).Status
        ConveneAgentTask = $task.State
        ConveneAgentLastResult = $taskInfo.LastTaskResult
        ExpectedConveneFields = 'sim_run_id, sim_source_id, sim_seq, sim_data_live, sim_bridge_status'
    } | Format-List
} finally {
    $ingestHeaders.Clear()
    $readHeaders.Clear()
    $secrets.Clear()
    Remove-Variable body, frame, response -ErrorAction SilentlyContinue
}
