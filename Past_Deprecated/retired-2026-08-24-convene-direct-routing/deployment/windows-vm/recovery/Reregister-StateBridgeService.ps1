<#
.SYNOPSIS
Rebuilds the finalized WinSW state-bridge SCM registration after a post-install XML change.
.NOTES
Recovery-only. Preserves bridge configuration, read credential, state, and Convene handoff.
It verifies the engine boundary but never restarts the engine.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Bridge service re-registration must run elevated.'
}

$engineService = 'RECLAIMIngestEngine'
$bridgeService = 'RECLAIMStateBridge'
$bridgeAccount = 'NT AUTHORITY\LocalService'
$bridgeSha = '1d7512346806d994cd95a1b485f4f500f650286d'
$release = "C:\ProgramData\RECLAIM\releases\$bridgeSha"
$bridgeRoot = 'C:\ProgramData\RECLAIM\convene-bridge'
$serviceDir = Join-Path $bridgeRoot 'service'
$serviceExe = Join-Path $serviceDir 'reclaim-state-bridge.exe'
$serviceXml = Join-Path $serviceDir 'reclaim-state-bridge.xml'
$outputPath = 'C:\ConveneAgent\sim_vars.json'
$expectedWinSWHash = '91BCE26B4FA3A7534E7967C1804D7417737B7169014435E5B3B31924BF19F3EE'

# Hard boundary: verify the engine, but never stop, restart, or modify it here.
if ((Get-Service -Name $engineService -ErrorAction Stop).Status -ne 'Running') {
    throw 'Engine is not running; bridge re-registration was not attempted.'
}
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/health' -TimeoutSec 5
if (-not $health.ok) {
    throw 'Engine health is not OK; bridge re-registration was not attempted.'
}
$listener = @(Get-NetTCPConnection -LocalPort 8078 -State Listen -ErrorAction Stop)
if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') {
    throw 'Engine is not exactly one loopback listener; bridge re-registration was not attempted.'
}

foreach ($required in @(
    $release,
    $serviceExe,
    $serviceXml,
    (Join-Path $bridgeRoot 'config\bridge.yaml'),
    (Join-Path $bridgeRoot 'secrets\read-token.txt'),
    (Join-Path $bridgeRoot 'app\convene_bridge\state_bridge.py')
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required bridge artifact is absent: $required"
    }
}
if ((git -C $release rev-parse HEAD) -ne $bridgeSha) {
    throw 'Immutable bridge release SHA mismatch.'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $serviceExe).Hash -ne $expectedWinSWHash) {
    throw 'Bridge WinSW executable hash mismatch.'
}
foreach ($relative in @('state_bridge.py', 'contract.py', 'writer.py', 'config.py')) {
    $deployed = Join-Path (Join-Path $bridgeRoot 'app\convene_bridge') $relative
    $expected = Join-Path (Join-Path $release 'convene_bridge') $relative
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $deployed).Hash -ne
        (Get-FileHash -Algorithm SHA256 -LiteralPath $expected).Hash) {
        throw "Deployed bridge source mismatch: $relative"
    }
}

$xmlText = [IO.File]::ReadAllText($serviceXml)
$unresolved = @([regex]::Matches($xmlText, '{{[A-Z][A-Z0-9_]+}}') | ForEach-Object Value)
if ($unresolved.Count -ne 0) {
    throw "Bridge XML contains unresolved placeholders: $($unresolved -join ', ')"
}
[xml]$xml = $xmlText
if ($xml.service.id -ne $bridgeService -or
    $xml.service.serviceaccount.username -ne $bridgeAccount -or
    $xml.service.logpath -ne (Join-Path $bridgeRoot 'logs')) {
    throw 'Bridge XML identity/account/log-path validation failed.'
}

$registered = Get-CimInstance Win32_Service -Filter "Name='$bridgeService'" -ErrorAction SilentlyContinue
if ($registered -and $registered.PathName.Trim('"') -ne $serviceExe) {
    throw "Refusing to replace bridge registered at unexpected path: $($registered.PathName)"
}

$backup = "$serviceXml.before-reregister-$(Get-Date -Format 'yyyyMMddHHmmss').bak"
Copy-Item -LiteralPath $serviceXml -Destination $backup

$service = Get-Service -Name $bridgeService -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne 'Stopped') {
    Stop-Service -Name $bridgeService
    $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
}
if ($service) {
    Push-Location $serviceDir
    try {
        & $serviceExe uninstall
        if ($LASTEXITCODE -ne 0) {
            throw "Bridge WinSW uninstall returned exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
    $removeDeadline = (Get-Date).AddSeconds(15)
    while ((Get-Service -Name $bridgeService -ErrorAction SilentlyContinue) -and (Get-Date) -lt $removeDeadline) {
        Start-Sleep -Milliseconds 250
    }
    if (Get-Service -Name $bridgeService -ErrorAction SilentlyContinue) {
        throw 'Old bridge SCM registration did not disappear; reinstall was not attempted.'
    }
}

Push-Location $serviceDir
try {
    & $serviceExe install
    if ($LASTEXITCODE -ne 0) {
        throw "Bridge WinSW install returned exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$installed = Get-CimInstance Win32_Service -Filter "Name='$bridgeService'" -ErrorAction Stop
if ($installed.PathName.Trim('"') -ne $serviceExe -or $installed.StartName -ne $bridgeAccount) {
    throw 'Fresh bridge SCM registration has an unexpected executable or account.'
}

$startError = $null
try {
    Start-Service -Name $bridgeService
    (Get-Service -Name $bridgeService).WaitForStatus('Running', [TimeSpan]::FromSeconds(35))
} catch {
    $startError = $_.Exception.Message
}
if ($startError) {
    Write-Host 'BRIDGE RE-REGISTRATION START DIAGNOSTICS'
    [pscustomobject]@{
        EngineState = (Get-Service -Name $engineService).Status
        EngineHealthOk = [bool]$health.ok
        BridgeState = (Get-Service -Name $bridgeService -ErrorAction SilentlyContinue).Status
        BridgeStartError = $startError
        WinSWHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $serviceExe).Hash
        XmlBackup = $backup
    } | Format-List
    foreach ($dir in @((Join-Path $bridgeRoot 'logs'), $serviceDir)) {
        Write-Host "Directory: $dir"
        & icacls.exe $dir
        Get-ChildItem -LiteralPath $dir -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -eq '.log' } |
            ForEach-Object {
                Write-Host "--- $($_.FullName) (last 100 lines) ---"
                Get-Content -LiteralPath $_.FullName -Tail 100 -ErrorAction Continue
            }
    }
    throw 'Fresh bridge registration still failed; engine remains healthy and diagnostics are printed above.'
}

$payload = $null
$jsonText = $null
$deadline = (Get-Date).AddSeconds(45)
do {
    try {
        $jsonText = [IO.File]::ReadAllText($outputPath)
        $candidate = $jsonText | ConvertFrom-Json
        if ($candidate.bridge_source_sha -eq $bridgeSha) {
            $payload = $candidate
        }
    } catch {
        Start-Sleep -Milliseconds 250
    }
} while (-not $payload -and (Get-Date) -lt $deadline)
if (-not $payload) {
    throw 'Bridge is Running but expected JSON was not published within 45 seconds.'
}

$properties = @($payload.PSObject.Properties)
$invalid = @($properties | Where-Object {
    $null -eq $_.Value -or $_.Value -is [array] -or $_.Value -is [pscustomobject]
})
$prefixed = @($properties | Where-Object { $_.Name -like 'sim_*' })
$bytes = [Text.Encoding]::UTF8.GetByteCount($jsonText)
if ($invalid.Count -ne 0 -or $prefixed.Count -ne 0 -or $bytes -gt 65536) {
    throw 'Published JSON violates Convene flat-scalar, single-prefix, or size requirements.'
}

$task = Get-ScheduledTask -TaskName 'ConveneAgent' -ErrorAction Stop
Write-Host 'STATE BRIDGE RE-REGISTRATION: RUNNING AND PUBLISHING'
[pscustomobject]@{
    EngineState = (Get-Service -Name $engineService).Status
    EngineHealthOk = [bool]$health.ok
    BridgeState = (Get-Service -Name $bridgeService).Status
    BridgeIdentity = $installed.StartName
    BridgeSourceSha = $payload.bridge_source_sha
    BridgeStatus = $payload.bridge_status
    DataLive = $payload.data_live
    BridgeValidUntil = $payload.bridge_valid_until
    FieldCount = $properties.Count
    Utf8Bytes = $bytes
    FlatScalarOnly = ($invalid.Count -eq 0)
    ExistingSimPrefixCount = $prefixed.Count
    ConveneAgentTask = $task.State
    EngineUntouched = ((Get-Service -Name $engineService).Status -eq 'Running')
    XmlBackup = $backup
} | Format-List
