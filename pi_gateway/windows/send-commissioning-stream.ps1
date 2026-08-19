<#
.SYNOPSIS
Streams clearly identified synthetic telemetry through the running edge gateway.

.DESCRIPTION
Exercises the actual cRIO-style TCP ingress, durable VM publisher, and independent
desktop Convene gw_ publisher for a bounded period. The script reads no credential
and refuses to start when a real cRIO session is present. All frames are labeled
COMMISSIONING-STREAM-NOT-CRIO and must not be treated as physical measurements.
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://[A-Za-z0-9.-]+$')]
    [string]$VmBaseUrl,

    [ValidateRange(60, 1800)]
    [int]$DurationSeconds = 300,

    [ValidateRange(250, 5000)]
    [int]$FrameIntervalMilliseconds = 1000,

    [ValidatePattern('^192\.168\.1\.1$')]
    [string]$GatewayAddress = '192.168.1.1',

    [ValidateRange(1, 65535)]
    [int]$GatewayPort = 9070
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$statusBase = 'http://127.0.0.1:9080'
$vmBase = $VmBaseUrl.TrimEnd('/')
$realCrioAddress = '192.168.1.2'

function Get-JsonEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSec = 10
    )
    Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec $TimeoutSec
}

function Get-RealCrioSessions {
    @(Get-NetTCPConnection -LocalPort $GatewayPort -RemoteAddress $realCrioAddress `
        -ErrorAction SilentlyContinue | Where-Object {
            $_.State -in @('Established', 'SynReceived')
        })
}

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $GatewayPort `
    -ErrorAction SilentlyContinue)
if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne $GatewayAddress) {
    throw "Expected exactly one gateway listener at ${GatewayAddress}:$GatewayPort."
}
if (@(Get-RealCrioSessions).Count -gt 0) {
    throw 'The real cRIO is connected or waiting; refusing synthetic telemetry.'
}

$before = Get-JsonEndpoint -Uri "$statusBase/health"
$vmBefore = Get-JsonEndpoint -Uri "$vmBase/health" -TimeoutSec 15
if ($vmBefore.PSObject.Properties.Name -contains 'ok' -and -not $vmBefore.ok) {
    throw 'VM health endpoint reported ok=false.'
}
if ([int64]$before.queue_depth -ne 0 -or [int64]$before.dead_letter -ne 0) {
    throw 'Gateway queue or dead-letter state is not clean; refusing to mix evidence.'
}

$startedAt = [DateTime]::UtcNow
$cycleId = 'COMMISSIONING-STREAM-NOT-CRIO-' + $startedAt.ToString('yyyyMMddTHHmmssZ')
$expectedFrames = [Math]::Ceiling(
    ($DurationSeconds * 1000.0) / $FrameIntervalMilliseconds
)

if (-not $PSCmdlet.ShouldProcess(
        "${GatewayAddress}:$GatewayPort",
        "Send $expectedFrames labeled synthetic frames over $DurationSeconds seconds"
    )) {
    return
}

$client = [Net.Sockets.TcpClient]::new()
$sent = 0
$timer = [Diagnostics.Stopwatch]::StartNew()
$nextCrioCheckSeconds = 10.0
$nextProgressSeconds = 30.0
try {
    $client.Connect($GatewayAddress, $GatewayPort)
    $stream = $client.GetStream()
    $encoding = [Text.UTF8Encoding]::new($false)

    while ($timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
        if ($timer.Elapsed.TotalSeconds -ge $nextCrioCheckSeconds) {
            if (@(Get-RealCrioSessions).Count -gt 0) {
                throw 'The real cRIO attempted to connect; ending synthetic telemetry immediately.'
            }
            $nextCrioCheckSeconds += 10.0
        }

        $stamp = [DateTime]::UtcNow
        $elapsed = $timer.Elapsed.TotalSeconds
        $bedRise = 0.02 * $elapsed
        $wallRise = 0.01 * $elapsed
        $power = 1000.0 + (50.0 * [Math]::Sin($elapsed / 15.0))
        $frame = [ordered]@{
            source_id = 'reclaim-commissioning-desktop-stream'
            cycle_id = $cycleId
            ts = $stamp.ToString('o')
            source_op_state = 'S_MicrowaveHeating'
            active_chamber = 'PL'
            vars = [ordered]@{
                PL_bottom1 = [Math]::Round(100.0 + $bedRise, 4)
                PL_bottom2 = [Math]::Round(101.0 + $bedRise, 4)
                PL_bottom3 = [Math]::Round(99.0 + $bedRise, 4)
                PL_bottom4 = [Math]::Round(100.5 + $bedRise, 4)
                PL_surface_temp = [Math]::Round(40.0 + $wallRise, 4)
                PL_top_condenser_temp = 25.0
                PL_bottom_condenser_temp = 26.0
                PL_chamber_pressure = 1000.0
                PL_output_pressure = 1010.0
                PL_process = $true
                PL_preprocess = $false
                PL_postprocess = $false
                PL_chamber_pump = $true
                PL_purge_pump = $false
                MT_bottom = 20.0
                MT_top = 21.0
                MW_power = [Math]::Round($power, 4)
                MW_reverse = 20.0
                MW_freq = 2450000000.0
                MW_width = 0.5
                MW_period = 1.0
                MW_water_temp = 20.0
                MW_flow_rate = 1.5
                MW_water_state = $true
                MW_flow_state = $true
                MW_RF = $true
                MW_status = $true
            }
        }

        $line = ($frame | ConvertTo-Json -Depth 5 -Compress) + "`n"
        $bytes = $encoding.GetBytes($line)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        $sent++

        if ($sent -eq 1 -or $timer.Elapsed.TotalSeconds -ge $nextProgressSeconds) {
            Write-Host ("Progress: elapsed={0:n1}s frames_sent={1}" -f `
                $timer.Elapsed.TotalSeconds, $sent)
            while ($nextProgressSeconds -le $timer.Elapsed.TotalSeconds) {
                $nextProgressSeconds += 30.0
            }
        }

        $nextDueMs = $sent * $FrameIntervalMilliseconds
        $sleepMs = [int][Math]::Max(0, $nextDueMs - $timer.Elapsed.TotalMilliseconds)
        if ($sleepMs -gt 0) {
            Start-Sleep -Milliseconds $sleepMs
        }
    }
}
finally {
    $timer.Stop()
    $client.Dispose()
}

$deadline = [DateTime]::UtcNow.AddSeconds(45)
do {
    Start-Sleep -Milliseconds 500
    $after = Get-JsonEndpoint -Uri "$statusBase/health"
    $vmAfter = Get-JsonEndpoint -Uri "$vmBase/health" -TimeoutSec 15
    $receivedDelta = [int64]$after.received - [int64]$before.received
    $vmDelta = [int64]$vmAfter.ingested_total - [int64]$vmBefore.ingested_total
    $conveneDelta = [int64]$after.convene.delivered - [int64]$before.convene.delivered
} until (([int64]$after.queue_depth -eq 0 -and $receivedDelta -ge $sent -and
          $vmDelta -ge $sent -and $conveneDelta -gt 0) -or
         [DateTime]::UtcNow -ge $deadline)

$latest = Get-JsonEndpoint -Uri "$statusBase/latest"
$result = [ordered]@{
    CapturedAtUtc = [DateTime]::UtcNow.ToString('o')
    CommissioningCycleId = $cycleId
    RequestedDurationSeconds = $DurationSeconds
    ActualDurationSeconds = [Math]::Round($timer.Elapsed.TotalSeconds, 3)
    FrameIntervalMilliseconds = $FrameIntervalMilliseconds
    FramesSent = $sent
    GatewayReceivedDelta = $receivedDelta
    VmIngestedDelta = $vmDelta
    ConveneDeliveredDelta = $conveneDelta
    ConveneFailedDelta = ([int64]$after.convene.failed - [int64]$before.convene.failed)
    ConveneCoalescedDelta = ([int64]$after.convene.coalesced - [int64]$before.convene.coalesced)
    LatestSourceId = $latest.source_id
    LatestRunId = $latest.run_id
    LatestSequence = $latest.seq
    QueueDepth = $after.queue_depth
    DeadLetterDelta = ([int64]$after.dead_letter - [int64]$before.dead_letter)
    VmActiveRunId = $vmAfter.active_run_id
    Passed = ($sent -eq $expectedFrames -and $receivedDelta -eq $sent -and
        $vmDelta -eq $sent -and $conveneDelta -gt 0 -and
        [int64]$after.queue_depth -eq 0 -and
        [int64]$after.dead_letter -eq [int64]$before.dead_letter -and
        $latest.source_id -eq 'reclaim-commissioning-desktop-stream')
}

[pscustomobject]$result | ConvertTo-Json -Depth 6
if (-not $result.Passed) {
    throw 'The five-minute stream did not complete every gateway/VM/Convene evidence gate.'
}
