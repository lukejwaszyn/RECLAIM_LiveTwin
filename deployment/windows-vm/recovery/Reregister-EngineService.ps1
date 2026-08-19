<#
.SYNOPSIS
Rebuilds the WinSW engine SCM registration from a validated immutable release.
.PARAMETER EngineSha
Full SHA of the staged release to register. Defaults to the proven scalar-state release.
.NOTES
Recovery-only. Preserves engine credentials and identity state and validates loopback health.
#>
[CmdletBinding()]
param(
    [string]$EngineSha = '726804b012279a0f3c675c4d9d3e76b16cf18d46'
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Engine service re-registration must run elevated.'
}

$serviceName = 'RECLAIMIngestEngine'
$serviceAccount = 'NT AUTHORITY\LocalService'
$release = "C:\ProgramData\RECLAIM\releases\$engineSha"
$engineRoot = 'C:\ProgramData\RECLAIM\engine'
$serviceDir = Join-Path $engineRoot 'service'
$serviceExe = Join-Path $serviceDir 'reclaim-ingest.exe'
$serviceXml = Join-Path $serviceDir 'reclaim-ingest.xml'
$runner = Join-Path $serviceDir 'run-ingest-engine.ps1'
$candidate = 'C:\ProgramData\RECLAIM\staging\WinSW-net461.exe'
$expectedWinSWHash = '91BCE26B4FA3A7534E7967C1804D7417737B7169014435E5B3B31924BF19F3EE'
$template = Join-Path $release 'cloud_engine\windows\reclaim-ingest.xml'

foreach ($required in @($release, $runner, $candidate, $template)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required recovery artifact is absent: $required"
    }
}
if ((git -C $release rev-parse HEAD) -ne $engineSha) {
    throw 'Immutable engine release SHA mismatch.'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash -ne $expectedWinSWHash) {
    throw 'Known-good WinSW net461 candidate hash mismatch.'
}

$registered = Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction SilentlyContinue
if ($registered -and $registered.PathName.Trim('"') -ne $serviceExe) {
    throw "Refusing to replace service registered at unexpected path: $($registered.PathName)"
}

# Generate the exact configuration that entered Running at 17:52 and 17:57.
$xml = Get-Content -Raw -LiteralPath $template
$xml = $xml.Replace('{{RUNNER_PATH}}', $runner)
$xml = $xml.Replace('{{PYTHON_EXE}}', (Join-Path $release '.venv\Scripts\python.exe'))
$xml = $xml.Replace('{{ENGINE_DIR}}', (Join-Path $release 'cloud_engine'))
$xml = $xml.Replace('{{SECRET_FILE}}', (Join-Path $engineRoot 'secrets\reclaim-ingest.env'))
$xml = $xml.Replace('{{STATE_FILE}}', (Join-Path $engineRoot 'state\ingest_state.json'))
$xml = $xml.Replace('{{LOG_DIR}}', (Join-Path $engineRoot 'logs'))
$xml = $xml.Replace('{{SERVICE_ACCOUNT}}', $serviceAccount)
$unresolvedPlaceholders = @(
    [regex]::Matches($xml, '{{[A-Z][A-Z0-9_]+}}') |
        ForEach-Object { $_.Value } |
        Sort-Object -Unique
)
if ($unresolvedPlaceholders.Count -ne 0) {
    throw "Generated WinSW XML still contains unresolved placeholders: $($unresolvedPlaceholders -join ', ')"
}
[xml]$validated = $xml
if ($validated.service.id -ne $serviceName -or $validated.service.serviceaccount.username -ne $serviceAccount) {
    throw 'Generated WinSW XML failed identity validation.'
}

$backup = "$serviceXml.before-reregister-$(Get-Date -Format 'yyyyMMddHHmmss').bak"
Copy-Item -LiteralPath $serviceXml -Destination $backup

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne 'Stopped') {
    Stop-Service -Name $serviceName
    $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
}

if ($service) {
    Push-Location $serviceDir
    try {
        & $serviceExe uninstall
        if ($LASTEXITCODE -ne 0) {
            throw "WinSW uninstall returned exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
    $removeDeadline = (Get-Date).AddSeconds(15)
    while ((Get-Service -Name $serviceName -ErrorAction SilentlyContinue) -and (Get-Date) -lt $removeDeadline) {
        Start-Sleep -Milliseconds 250
    }
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        throw 'Old SCM registration did not disappear; no reinstall was attempted.'
    }
}

Copy-Item -Force -LiteralPath $candidate -Destination $serviceExe
[IO.File]::WriteAllText($serviceXml, $xml, [Text.UTF8Encoding]::new($false))

Push-Location $serviceDir
try {
    & $serviceExe install
    if ($LASTEXITCODE -ne 0) {
        throw "WinSW install returned exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$installed = Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop
if ($installed.PathName.Trim('"') -ne $serviceExe -or $installed.StartName -ne $serviceAccount) {
    throw 'Fresh SCM registration does not match the validated executable/account.'
}

$startFailure = $null
try {
    Start-Service -Name $serviceName
    (Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(35))
} catch {
    $startFailure = $_.Exception.Message
}

if ($startFailure) {
    Write-Host 'ENGINE RE-REGISTRATION START DIAGNOSTICS'
    [pscustomobject]@{
        StartFailure = $startFailure
        ServiceState = (Get-Service -Name $serviceName -ErrorAction SilentlyContinue).Status
        WinSWHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $serviceExe).Hash
        XmlBackup = $backup
    } | Format-List
    & sc.exe qc $serviceName
    foreach ($dir in @($serviceDir, (Join-Path $engineRoot 'logs'))) {
        Write-Host "Directory: $dir"
        & icacls.exe $dir
        Get-ChildItem -LiteralPath $dir -Force -ErrorAction Continue |
            Select-Object FullName, Length, LastWriteTime |
            Format-Table -AutoSize
        Get-ChildItem -LiteralPath $dir -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '\.(wrapper|out|err)?\.log$' } |
            ForEach-Object {
                Write-Host "--- $($_.FullName) (last 80 lines) ---"
                Get-Content -LiteralPath $_.FullName -Tail 80 -ErrorAction Continue
            }
    }
    Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = (Get-Date).AddMinutes(-10) } |
        Where-Object {
            $_.ProviderName -eq 'Service Control Manager' -and $_.Message -match 'RECLAIM|Ingest'
        } |
        Select-Object -First 20 TimeCreated, Id, LevelDisplayName, Message |
        Format-List
    throw 'Fresh known-good engine registration still failed; diagnostics are printed above.'
}

$health = $null
$healthDeadline = (Get-Date).AddSeconds(60)
do {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8078/health' -TimeoutSec 3
    } catch {
        Start-Sleep -Milliseconds 500
    }
} while (-not $health -and (Get-Date) -lt $healthDeadline)
if (-not $health -or -not $health.ok) {
    throw 'Freshly registered service is Running but loopback health did not become ready.'
}

$listener = Get-NetTCPConnection -LocalPort 8078 -State Listen -ErrorAction Stop
if (@($listener).Count -ne 1 -or $listener.LocalAddress -ne '127.0.0.1') {
    throw 'Engine listener is not exactly one loopback listener.'
}

Write-Host 'ENGINE RE-REGISTRATION: HEALTHY'
[pscustomobject]@{
    Service = $serviceName
    State = (Get-Service -Name $serviceName).Status
    Identity = $installed.StartName
    Loopback = "$($listener.LocalAddress):$($listener.LocalPort)"
    HealthOk = [bool]$health.ok
    WinSWHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $serviceExe).Hash
    EngineSourceSha = $engineSha
    StateFilePreserved = (Test-Path -LiteralPath (Join-Path $engineRoot 'state\ingest_state.json'))
    XmlBackup = $backup
} | Format-List
