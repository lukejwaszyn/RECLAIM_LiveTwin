<#
.SYNOPSIS
Tests the current flat Convene/text-extraction contract locally and optionally
exercises the deployed loopback engine.
#>
[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$PythonExe = '',
    [switch]$ExerciseEndpoint
)

$ErrorActionPreference = 'Stop'
if (-not $PythonExe) {
    $PythonExe = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Locked Python environment is absent: $PythonExe"
}

$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "$(Join-Path $RepositoryRoot 'cloud_engine');$(Join-Path $RepositoryRoot 'pi_gateway');$(Join-Path $RepositoryRoot 'tools')"
    & $PythonExe -m pytest -q `
        (Join-Path $RepositoryRoot 'cloud_engine\tests\test_live_ingest_contract.py') `
        (Join-Path $RepositoryRoot 'pi_gateway\tests\test_file_watch_publisher.py')
    if ($LASTEXITCODE -ne 0) { throw "Current source contract tests failed with exit code $LASTEXITCODE." }
} finally {
    $env:PYTHONPATH = $oldPythonPath
}

if (-not $ExerciseEndpoint) {
    Write-Host 'Source contract passed. Endpoint was not mutated.'
    exit 0
}
if ([string]::IsNullOrWhiteSpace($env:RECLAIM_INGEST_TOKEN) -or
    [string]::IsNullOrWhiteSpace($env:RECLAIM_READ_TOKEN)) {
    throw 'ExerciseEndpoint requires existing RECLAIM_INGEST_TOKEN and RECLAIM_READ_TOKEN environment variables.'
}

& $PythonExe (Join-Path $RepositoryRoot 'cloud_engine\tools\redteam_ingest.py') `
    --url 'http://127.0.0.1:8078'
if ($LASTEXITCODE -ne 0) { throw "Deployed endpoint contract failed with exit code $LASTEXITCODE." }
Write-Host 'Convene-routed loopback engine contract passed.'
