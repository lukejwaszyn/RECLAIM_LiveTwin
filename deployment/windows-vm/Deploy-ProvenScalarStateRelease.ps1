<#
.SYNOPSIS
Transactionally deploys the exact scalar-state release proven on reclaim-engine-2.
.NOTES
Requires elevated PowerShell and a pre-staged immutable release. The script preserves and
hash-checks engine state and credentials, and restores the previous engine registration if
the new service fails to start.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Scalar-state release deployment must run elevated.'
}

$newSha = '726804b012279a0f3c675c4d9d3e76b16cf18d46'
$bridgeSha = '1d7512346806d994cd95a1b485f4f500f650286d'
$release = "C:\ProgramData\RECLAIM\releases\$newSha"
$engineRoot = 'C:\ProgramData\RECLAIM\engine'
$bridgeRoot = 'C:\ProgramData\RECLAIM\convene-bridge'
$engineService = 'RECLAIMIngestEngine'
$bridgeService = 'RECLAIMStateBridge'
$serviceAccount = 'NT AUTHORITY\LocalService'
$serviceDir = Join-Path $engineRoot 'service'
$serviceExe = Join-Path $serviceDir 'reclaim-ingest.exe'
$serviceXml = Join-Path $serviceDir 'reclaim-ingest.xml'
$runner = Join-Path $serviceDir 'run-ingest-engine.ps1'
$candidate = 'C:\ProgramData\RECLAIM\staging\WinSW-net461.exe'
$expectedWinSWHash = '91BCE26B4FA3A7534E7967C1804D7417737B7169014435E5B3B31924BF19F3EE'
$engineSecret = Join-Path $engineRoot 'secrets\reclaim-ingest.env'
$engineState = Join-Path $engineRoot 'state\ingest_state.json'
$bridgeSecret = Join-Path $bridgeRoot 'secrets\read-token.txt'
$bridgeConfig = Join-Path $bridgeRoot 'config\bridge.yaml'
$outputPath = 'C:\ConveneAgent\sim_vars.json'
$stamp = Get-Date -Format 'yyyyMMddHHmmss'

foreach ($required in @(
    $release,
    (Join-Path $release '.venv\Scripts\python.exe'),
    (Join-Path $release 'cloud_engine\push_ingest_dual.py'),
    (Join-Path $release 'cloud_engine\windows\reclaim-ingest.xml'),
    (Join-Path $release 'cloud_engine\windows\run-ingest-engine.ps1'),
    $candidate,
    $serviceExe,
    $serviceXml,
    $runner,
    $engineSecret,
    $engineState,
    $bridgeSecret,
    $bridgeConfig
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required deployment artifact is absent: $required"
    }
}
if ((git -C $release rev-parse HEAD) -ne $newSha -or (git -C $release status --porcelain)) {
    throw 'New immutable release SHA or cleanliness validation failed.'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash -ne $expectedWinSWHash) {
    throw 'Known-good WinSW net461 hash mismatch.'
}
if ((Get-Service -Name $engineService -ErrorAction Stop).Status -ne 'Running' -or
    (Get-Service -Name $bridgeService -ErrorAction Stop).Status -ne 'Running') {
    throw 'Engine and bridge must both be healthy before transactional deployment.'
}
$preHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/health' -TimeoutSec 5
if (-not $preHealth.ok) {
    throw 'Pre-deployment engine health failed.'
}

$engineSecretHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $engineSecret).Hash
$engineStateHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $engineState).Hash
$bridgeSecretHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $bridgeSecret).Hash
$oldXmlBackup = "$serviceXml.before-$newSha-$stamp.bak"
$oldRunnerBackup = "$runner.before-$newSha-$stamp.bak"
$bridgeConfigBackup = "$bridgeConfig.before-$newSha-$stamp.bak"
Copy-Item -LiteralPath $serviceXml -Destination $oldXmlBackup
Copy-Item -LiteralPath $runner -Destination $oldRunnerBackup
Copy-Item -LiteralPath $bridgeConfig -Destination $bridgeConfigBackup

# Validate the later bridge provenance edit before any service is stopped.
$configText = [IO.File]::ReadAllText($bridgeConfig)
$updatedConfig = [regex]::Replace(
    $configText,
    '(?m)^engine_source_sha:.*$',
    "engine_source_sha: $newSha"
)
if ($updatedConfig -eq $configText -and $configText -notmatch [regex]::Escape($newSha)) {
    throw 'Bridge configuration did not contain a replaceable engine_source_sha field.'
}

# Generate and validate the complete runtime XML before stopping anything.
$newXml = Get-Content -Raw -LiteralPath (Join-Path $release 'cloud_engine\windows\reclaim-ingest.xml')
$newXml = $newXml.Replace('{{RUNNER_PATH}}', $runner)
$newXml = $newXml.Replace('{{PYTHON_EXE}}', (Join-Path $release '.venv\Scripts\python.exe'))
$newXml = $newXml.Replace('{{ENGINE_DIR}}', (Join-Path $release 'cloud_engine'))
$newXml = $newXml.Replace('{{SECRET_FILE}}', $engineSecret)
$newXml = $newXml.Replace('{{STATE_FILE}}', $engineState)
$newXml = $newXml.Replace('{{LOG_DIR}}', (Join-Path $engineRoot 'logs'))
$newXml = $newXml.Replace('{{SERVICE_ACCOUNT}}', $serviceAccount)
$unresolved = @([regex]::Matches($newXml, '{{[A-Z][A-Z0-9_]+}}') | ForEach-Object Value)
if ($unresolved.Count -ne 0) {
    throw "Generated engine XML contains unresolved placeholders: $($unresolved -join ', ')"
}
[xml]$validatedXml = $newXml
if ($validatedXml.service.id -ne $engineService -or
    $validatedXml.service.serviceaccount.username -ne $serviceAccount -or
    $validatedXml.service.logpath -ne (Join-Path $engineRoot 'logs')) {
    throw 'Generated engine XML failed identity/account/log-path validation.'
}

# The restricted service account receives read/execute only on the immutable release.
& icacls.exe $release /grant "${serviceAccount}:(OI)(CI)(RX)" /T /C | Out-Null

function Remove-EngineRegistration {
    $service = Get-Service -Name $engineService -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne 'Stopped') {
        Stop-Service -Name $engineService
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }
    if ($service) {
        Push-Location $serviceDir
        try {
            & $serviceExe uninstall
            if ($LASTEXITCODE -ne 0) { throw "Engine uninstall returned $LASTEXITCODE." }
        } finally { Pop-Location }
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Service -Name $engineService -ErrorAction SilentlyContinue) -and
               (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 250
        }
        if (Get-Service -Name $engineService -ErrorAction SilentlyContinue) {
            throw 'Engine SCM registration did not disappear.'
        }
    }
}

function Install-And-Start-Engine {
    Push-Location $serviceDir
    try {
        & $serviceExe install
        if ($LASTEXITCODE -ne 0) { throw "Engine install returned $LASTEXITCODE." }
    } finally { Pop-Location }
    $installed = Get-CimInstance Win32_Service -Filter "Name='$engineService'" -ErrorAction Stop
    if ($installed.PathName.Trim('"') -ne $serviceExe -or $installed.StartName -ne $serviceAccount) {
        throw 'Engine SCM registration has an unexpected executable or account.'
    }
    Start-Service -Name $engineService
    (Get-Service -Name $engineService).WaitForStatus('Running', [TimeSpan]::FromSeconds(35))
    $health = $null
    $deadline = (Get-Date).AddSeconds(60)
    do {
        try { $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/health' -TimeoutSec 3 }
        catch { Start-Sleep -Milliseconds 500 }
    } while (-not $health -and (Get-Date) -lt $deadline)
    if (-not $health -or -not $health.ok) { throw 'Engine did not become healthy.' }
    return $health
}

Stop-Service -Name $bridgeService
(Get-Service -Name $bridgeService).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))

$newHealth = $null
try {
    Remove-EngineRegistration
    Copy-Item -Force -LiteralPath $candidate -Destination $serviceExe
    Copy-Item -Force -LiteralPath (Join-Path $release 'cloud_engine\windows\run-ingest-engine.ps1') -Destination $runner
    [IO.File]::WriteAllText($serviceXml, $newXml, [Text.UTF8Encoding]::new($false))
    $newHealth = Install-And-Start-Engine
} catch {
    $deploymentFailure = $_.Exception.Message
    Write-Warning "New engine failed; restoring the previously healthy registration: $deploymentFailure"
    try {
        Remove-EngineRegistration
        Copy-Item -Force -LiteralPath $candidate -Destination $serviceExe
        Copy-Item -Force -LiteralPath $oldRunnerBackup -Destination $runner
        Copy-Item -Force -LiteralPath $oldXmlBackup -Destination $serviceXml
        $rollbackHealth = Install-And-Start-Engine
        if ((Get-Service -Name $bridgeService).Status -ne 'Running') {
            Start-Service -Name $bridgeService
        }
        throw "New engine deployment failed and the previous healthy service was restored: $deploymentFailure"
    } catch {
        if ($_.Exception.Message -like 'New engine deployment failed and*') { throw }
        throw "New engine deployment failed and rollback also failed: $deploymentFailure / $($_.Exception.Message)"
    }
}

# Only after the new engine is healthy, update the bridge's non-secret provenance.
try {
    [IO.File]::WriteAllText($bridgeConfig, $updatedConfig, [Text.UTF8Encoding]::new($false))
    Start-Service -Name $bridgeService
    (Get-Service -Name $bridgeService).WaitForStatus('Running', [TimeSpan]::FromSeconds(35))
    $payload = $null
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $candidatePayload = [IO.File]::ReadAllText($outputPath) | ConvertFrom-Json
            if ($candidatePayload.engine_source_sha -eq $newSha -and
                $candidatePayload.bridge_source_sha -eq $bridgeSha) {
                $payload = $candidatePayload
            }
        } catch {}
        if (-not $payload) { Start-Sleep -Milliseconds 250 }
    } while (-not $payload -and (Get-Date) -lt $deadline)
    if (-not $payload) { throw 'Bridge did not publish updated engine provenance.' }
} catch {
    $bridgeFailure = $_.Exception.Message
    if ((Get-Service -Name $bridgeService -ErrorAction SilentlyContinue).Status -eq 'Running') {
        Stop-Service -Name $bridgeService
    }
    Copy-Item -Force -LiteralPath $bridgeConfigBackup -Destination $bridgeConfig
    Start-Service -Name $bridgeService
    throw "Engine is healthy on the new release, but bridge provenance update was rolled back: $bridgeFailure"
}

$listener = @(Get-NetTCPConnection -LocalPort 8078 -State Listen -ErrorAction Stop)
if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') {
    throw 'New engine is not exactly one loopback listener.'
}
$engineSecretHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $engineSecret).Hash
$engineStateHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $engineState).Hash
$bridgeSecretHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $bridgeSecret).Hash

Write-Host 'SCALAR-STATE RELEASE DEPLOYED'
[pscustomobject]@{
    EngineSourceSha = $newSha
    BridgeSourceSha = $payload.bridge_source_sha
    EngineService = (Get-Service -Name $engineService).Status
    BridgeService = (Get-Service -Name $bridgeService).Status
    EngineIdentity = (Get-CimInstance Win32_Service -Filter "Name='$engineService'").StartName
    BridgeIdentity = (Get-CimInstance Win32_Service -Filter "Name='$bridgeService'").StartName
    Loopback = "$($listener[0].LocalAddress):$($listener[0].LocalPort)"
    HealthOk = [bool]$newHealth.ok
    ActiveRunRestored = ($newHealth.active_run_id -eq $preHealth.active_run_id)
    EngineSecretHashStable = ($engineSecretHashAfter -eq $engineSecretHashBefore)
    EngineStateHashStable = ($engineStateHashAfter -eq $engineStateHashBefore)
    BridgeSecretHashStable = ($bridgeSecretHashAfter -eq $bridgeSecretHashBefore)
    BridgeStatus = $payload.bridge_status
    DataLive = $payload.data_live
    OutputFlatScalar = (-not @($payload.PSObject.Properties | Where-Object {
        $null -eq $_.Value -or $_.Value -is [array] -or $_.Value -is [pscustomobject]
    }))
    ExistingSimPrefixCount = @($payload.PSObject.Properties.Name -like 'sim_*').Count
} | Format-List
