[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$EngineDir,
    [Parameter(Mandatory = $true)][string]$SecretFile,
    [Parameter(Mandatory = $true)][string]$StateFile
)

$ErrorActionPreference = "Stop"
foreach ($path in @($PythonExe, $EngineDir, $SecretFile)) {
    if (-not (Test-Path $path)) { throw "Required engine path is absent: $path" }
}

$Secrets = @{}
foreach ($line in Get-Content $SecretFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $name, $value = $trimmed.Split("=", 2)
    if ($name -notin @("RECLAIM_INGEST_TOKEN", "RECLAIM_READ_TOKEN") -or
        [string]::IsNullOrWhiteSpace($value)) {
        throw "Secret file must contain only non-empty RECLAIM_INGEST_TOKEN and RECLAIM_READ_TOKEN entries"
    }
    $Secrets[$name] = $value
}
if ($Secrets.Count -ne 2) { throw "Both independent engine credentials are required" }
if ($Secrets.RECLAIM_INGEST_TOKEN -eq $Secrets.RECLAIM_READ_TOKEN) {
    throw "Ingest and read credentials must be distinct"
}

$env:RECLAIM_INGEST_TOKEN = $Secrets.RECLAIM_INGEST_TOKEN
$env:RECLAIM_READ_TOKEN = $Secrets.RECLAIM_READ_TOKEN
$env:RECLAIM_INGEST_STATE = $StateFile
Set-Location $EngineDir
& $PythonExe push_ingest_dual.py --host 127.0.0.1 --port 8078 --env earth_lab --production --max-frame-age-s 15
exit $LASTEXITCODE
