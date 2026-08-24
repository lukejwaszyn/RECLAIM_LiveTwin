<#
.SYNOPSIS
Sends one clearly identified commissioning frame through the running gateway.

.DESCRIPTION
This exercises the real desktop fan-out without reading any credential:
TCP 9070 -> durable VM queue -> Cloudflare /ingest, plus the independent
Convene raw-variable publisher. It refuses to inject while the real cRIO peer has an
established connection. The frame is synthetic and explicitly labeled in its
source_id and cycle_id; use only for supervised commissioning.
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://[A-Za-z0-9.-]+$')]
    [string]$VmBaseUrl,

    [ValidatePattern('^192\.168\.1\.1$')]
    [string]$GatewayAddress = '192.168.1.1',

    [ValidateRange(1, 65535)]
    [int]$GatewayPort = 9070,

    [ValidateRange(5, 60)]
    [int]$TimeoutSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$statusBase = 'http://127.0.0.1:9080'
$vmBase = $VmBaseUrl.TrimEnd('/')

function Get-JsonEndpoint {
    param([Parameter(Mandatory = $true)][string]$Uri)
    Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec 10
}

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $GatewayPort `
    -ErrorAction SilentlyContinue)
if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne $GatewayAddress) {
    throw "Expected exactly one gateway listener at ${GatewayAddress}:$GatewayPort."
}

$realCrioSessions = @(Get-NetTCPConnection -State Established `
    -LocalPort $GatewayPort -RemoteAddress '192.168.1.2' -ErrorAction SilentlyContinue)
if ($realCrioSessions.Count -gt 0) {
    throw 'The real cRIO is already connected to TCP 9070; refusing synthetic injection.'
}

$before = Get-JsonEndpoint -Uri "$statusBase/health"
$vmBefore = Get-JsonEndpoint -Uri "$vmBase/health"
if ($vmBefore.PSObject.Properties.Name -contains 'ok' -and -not $vmBefore.ok) {
    throw 'VM health endpoint reported ok=false.'
}

$stamp = [DateTime]::UtcNow
$frame = [ordered]@{
    source_id = 'reclaim-commissioning-desktop'
    cycle_id = 'COMMISSIONING-NOT-CRIO-' + $stamp.ToString('yyyyMMddTHHmmssZ')
    ts = $stamp.ToString('o')
    source_op_state = 'S_MicrowaveHeating'
    active_chamber = 'PL'
    vars = [ordered]@{
        PL_bottom1 = 100.0
        PL_bottom2 = 101.0
        PL_bottom3 = 99.0
        PL_bottom4 = 100.5
        PL_surface_temp = 40.0
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
        MW_power = 1000.0
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

if (-not $PSCmdlet.ShouldProcess(
        "${GatewayAddress}:$GatewayPort",
        "Send one synthetic live commissioning frame $($frame.cycle_id) to VM and Convene"
    )) {
    return
}

$client = [Net.Sockets.TcpClient]::new()
try {
    $client.Connect($GatewayAddress, $GatewayPort)
    $stream = $client.GetStream()
    $line = ($frame | ConvertTo-Json -Depth 5 -Compress) + "`n"
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($line)
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
}
finally {
    $client.Dispose()
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$after = $null
$vmAfter = $null
do {
    Start-Sleep -Milliseconds 500
    $after = Get-JsonEndpoint -Uri "$statusBase/health"
    $vmAfter = Get-JsonEndpoint -Uri "$vmBase/health"
    $received = [int64]$after.received -gt [int64]$before.received
    $vmAdvanced = [int64]$vmAfter.ingested_total -gt [int64]$vmBefore.ingested_total
    $conveneAdvanced = (
        $after.convene.enabled -and
        [int64]$after.convene.delivered -gt [int64]$before.convene.delivered
    )
} until (($received -and $vmAdvanced -and $conveneAdvanced) -or
         [DateTime]::UtcNow -ge $deadline)

$latest = Get-JsonEndpoint -Uri "$statusBase/latest"
$result = [ordered]@{
    CapturedAtUtc = [DateTime]::UtcNow.ToString('o')
    CommissioningCycleId = $frame.cycle_id
    GatewayReceivedAdvanced = $received
    VmIngestedAdvanced = $vmAdvanced
    ConveneDeliveredAdvanced = $conveneAdvanced
    LatestSourceId = $latest.source_id
    LatestRunId = $latest.run_id
    LatestSequence = $latest.seq
    QueueDepth = $after.queue_depth
    DeadLetter = $after.dead_letter
    ConveneDelivered = $after.convene.delivered
    ConveneFailed = $after.convene.failed
    ConveneCoalesced = $after.convene.coalesced
    VmIngestedTotal = $vmAfter.ingested_total
    Passed = ($received -and $vmAdvanced -and $conveneAdvanced -and
        $latest.source_id -eq $frame.source_id -and
        [int64]$after.queue_depth -eq 0 -and
        [int64]$after.dead_letter -eq 0)
}

[pscustomobject]$result | ConvertTo-Json -Depth 5
if (-not $result.Passed) {
    throw 'Commissioning frame did not complete every desktop/VM/Convene gate before timeout.'
}
