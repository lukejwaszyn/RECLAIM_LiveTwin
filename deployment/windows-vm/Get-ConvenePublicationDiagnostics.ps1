<#
.SYNOPSIS
Prints a non-secret engine/bridge/task diagnostic snapshot and optional correlated log lines.
.PARAMETER ProofRun
Optional run_id used to select matching bridge log lines.
.PARAMETER IncludeFieldInventory
Print every current Convene handoff field with its scalar type and example value. The
handoff contract contains telemetry and provenance only; credentials are never included.
.NOTES
Read-only except for ordinary file access. Requires elevation because credentials and bridge
artifacts are ACL-protected; the read token itself is never printed.
#>
[CmdletBinding()]
param(
    [string]$ProofRun,
    [switch]$IncludeFieldInventory
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Publication diagnosis must run elevated.'
}

$secretFile = 'C:\ProgramData\RECLAIM\engine\secrets\reclaim-ingest.env'
$outputPath = 'C:\ConveneAgent\sim_vars.json'
$bridgeRoot = 'C:\ProgramData\RECLAIM\convene-bridge'
$bridgeHealthPath = Join-Path $bridgeRoot 'state\health.json'
$bridgeLogPath = Join-Path $bridgeRoot 'logs\bridge.log'

$readToken = $null
foreach ($line in Get-Content -LiteralPath $secretFile) {
    if ($line.StartsWith('RECLAIM_READ_TOKEN=')) {
        $readToken = $line.Substring('RECLAIM_READ_TOKEN='.Length)
        break
    }
}
if ([string]::IsNullOrWhiteSpace($readToken)) {
    throw 'Read credential is absent.'
}

try {
    $engineState = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/state' `
        -Headers @{ Authorization = "Bearer $readToken" } -TimeoutSec 5
    $bridgePayload = [IO.File]::ReadAllText($outputPath) | ConvertFrom-Json
    $bridgeHealth = [IO.File]::ReadAllText($bridgeHealthPath) | ConvertFrom-Json

    Write-Host 'CURRENT AUTHENTICATED ENGINE STATE (NON-SECRET FIELDS)'
    [pscustomobject]@{
        SchemaVersion = $engineState.schema_version
        Mode = $engineState.mode
        RunId = $engineState.run_id
        SourceId = $engineState.source_id
        Seq = $engineState.seq
        CycleId = $engineState.cycle_id
        TsSource = $engineState.ts_source
        TsEngine = $engineState.ts_engine
        ActiveChamber = $engineState.active_chamber
        SourceOpState = $engineState.source_op_state
        OpState = $engineState.op_state
        IngestStatus = $engineState.ingest_status
        StateAgeMs = $engineState.state_age_ms
        TopLevelFieldCount = @($engineState.PSObject.Properties).Count
    } | Format-List

    Write-Host 'CURRENT CONVENE HANDOFF (NON-SECRET FIELDS)'
    [pscustomobject]@{
        SchemaVersion = $bridgePayload.schema_version
        RunId = $bridgePayload.run_id
        SourceId = $bridgePayload.source_id
        Seq = $bridgePayload.seq
        BridgeStatus = $bridgePayload.bridge_status
        BridgeErrorCode = $bridgePayload.bridge_error_code
        DataLive = $bridgePayload.data_live
        StateAgeMs = $bridgePayload.state_age_ms
        BridgeObservedAt = $bridgePayload.bridge_observed_at
        BridgeValidUntil = $bridgePayload.bridge_valid_until
        TopLevelFieldCount = @($bridgePayload.PSObject.Properties).Count
        ExistingSimPrefixCount = @($bridgePayload.PSObject.Properties.Name -like 'sim_*').Count
        Utf8Bytes = (Get-Item -LiteralPath $outputPath).Length
    } | Format-List

    if ($IncludeFieldInventory) {
        $fieldInventory = foreach ($property in $bridgePayload.PSObject.Properties) {
            $value = $property.Value
            $scalarType = if ($null -eq $value) {
                'null'
            } elseif ($value -is [bool]) {
                'boolean'
            } elseif ($value -is [string]) {
                'string'
            } elseif ($value -is [byte] -or $value -is [int16] -or
                $value -is [int32] -or $value -is [int64] -or
                $value -is [single] -or $value -is [double] -or
                $value -is [decimal]) {
                'number'
            } elseif ($value -is [System.Collections.IEnumerable]) {
                'nested/array'
            } else {
                'nested/object'
            }
            [pscustomobject]@{
                Field = $property.Name
                ScalarType = $scalarType
                ExampleValue = [string]$value
            }
        }

        Write-Host 'CURRENT CONVENE HANDOFF FIELD INVENTORY (NON-SECRET)'
        $fieldInventory | Sort-Object Field | Format-Table -AutoSize
        [pscustomobject]@{
            FieldCount = @($fieldInventory).Count
            NullCount = @($fieldInventory | Where-Object ScalarType -eq 'null').Count
            NestedCount = @($fieldInventory | Where-Object ScalarType -like 'nested/*').Count
            ExistingSimPrefixCount = @($fieldInventory | Where-Object Field -like 'sim_*').Count
        } | Format-List
    }

    Write-Host 'CURRENT BRIDGE HEALTH RECORD'
    [pscustomobject]@{
        BridgeStatus = $bridgeHealth.bridge_status
        BridgeErrorCode = $bridgeHealth.bridge_error_code
        DataLive = $bridgeHealth.data_live
        LastSuccessfulPoll = $bridgeHealth.last_successful_poll
        ConsecutiveFailures = $bridgeHealth.consecutive_failures
        BridgeObservedAt = $bridgeHealth.bridge_observed_at
    } | Format-List

    if ($ProofRun) { Write-Host "BRIDGE LOG LINES FOR $ProofRun" }
    if (Test-Path -LiteralPath $bridgeLogPath) {
        if ($ProofRun) {
            Select-String -LiteralPath $bridgeLogPath -SimpleMatch $ProofRun |
                Select-Object -Last 120 |
                ForEach-Object { $_.Line }
        }
        Write-Host 'BRIDGE LOG TAIL (LAST 120 LINES)'
        Get-Content -LiteralPath $bridgeLogPath -Tail 120
    } else {
        Write-Host "Bridge application log is absent: $bridgeLogPath"
    }

    Write-Host 'SERVICE/TASK STATE'
    $task = Get-ScheduledTask -TaskName 'ConveneAgent' -ErrorAction Stop
    $taskInfo = Get-ScheduledTaskInfo -TaskName 'ConveneAgent' -ErrorAction Stop
    [pscustomobject]@{
        EngineService = (Get-Service RECLAIMIngestEngine).Status
        BridgeService = (Get-Service RECLAIMStateBridge).Status
        ConveneAgentTask = $task.State
        ConveneAgentLastRun = $taskInfo.LastRunTime
        ConveneAgentLastResult = $taskInfo.LastTaskResult
    } | Format-List
} finally {
    $readToken = $null
    Remove-Variable readToken -ErrorAction SilentlyContinue
}
