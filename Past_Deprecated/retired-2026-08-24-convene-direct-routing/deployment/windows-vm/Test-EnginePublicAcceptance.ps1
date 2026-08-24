<#
.SYNOPSIS
Runs the 20-check public-ingress harness plus service-restart persistence proof.
.PARAMETER PublicUrl
HTTPS origin routed by cloudflared to the loopback production engine.
.PARAMETER ReleaseSha
Exact staged release containing the harness and locked Python environment.
.NOTES
Requires elevated PowerShell to read protected credentials and restart the engine service.
Credential values are never printed.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidatePattern('^https://')]
  [string]$PublicUrl,

  [string]$ReleaseSha = '726804b012279a0f3c675c4d9d3e76b16cf18d46'
)

$ErrorActionPreference = 'Stop'

$publicUrl = $PublicUrl.TrimEnd('/')
$release = "C:\ProgramData\RECLAIM\releases\$ReleaseSha"
$python = Join-Path $release '.venv\Scripts\python.exe'
$secretFile = 'C:\ProgramData\RECLAIM\engine\secrets\reclaim-ingest.env'
$stateFile = 'C:\ProgramData\RECLAIM\engine\state\ingest_state.json'

$secrets = @{}
foreach ($line in Get-Content -LiteralPath $secretFile) {
  $name, $value = $line.Split('=', 2)
  if ($name -in @('RECLAIM_INGEST_TOKEN', 'RECLAIM_READ_TOKEN')) { $secrets[$name] = $value }
}
if ($secrets.Count -ne 2) { throw 'Expected two engine credentials.' }
if ($secrets.RECLAIM_INGEST_TOKEN -eq $secrets.RECLAIM_READ_TOKEN) { throw 'Credentials are not distinct.' }
$env:RECLAIM_INGEST_TOKEN = $secrets.RECLAIM_INGEST_TOKEN
$env:RECLAIM_READ_TOKEN = $secrets.RECLAIM_READ_TOKEN

function Get-HttpStatus([scriptblock]$request) {
  try {
    & $request | Out-Null
    return 200
  } catch {
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
      return [int]$_.Exception.Response.StatusCode
    }
    throw
  }
}

try {
  $missing = Get-HttpStatus { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8078/state' }
  $wrong = Get-HttpStatus {
    Invoke-WebRequest -UseBasicParsing -Headers @{Authorization='Bearer deliberately-wrong'} `
      'http://127.0.0.1:8078/state'
  }
  if ($missing -ne 401 -or $wrong -ne 401) { throw "Read auth did not fail closed: missing=$missing wrong=$wrong" }
  $readHeaders = @{Authorization="Bearer $($secrets.RECLAIM_READ_TOKEN)"}
  Invoke-RestMethod -Headers $readHeaders 'http://127.0.0.1:8078/state' | Out-Null
  Write-Host "Read authentication: missing=$missing wrong=$wrong correct=200"

  Push-Location $release
  try {
    $harnessOutput = [Collections.Generic.List[string]]::new()
    & $python 'cloud_engine\tools\redteam_ingest.py' --url $publicUrl 2>&1 | ForEach-Object {
      $text = $_.ToString()
      $harnessOutput.Add($text)
      Write-Host $text
    }
    $harnessExit = $LASTEXITCODE
  } finally { Pop-Location }
  if ($harnessExit -ne 0 -or (($harnessOutput -join "`n") -notmatch '20/20')) {
    throw "Acceptance harness failed with exit code $harnessExit"
  }

  $state = Invoke-RestMethod -Headers $readHeaders 'http://127.0.0.1:8078/state'
  [pscustomobject]@{
    Boundary='post-harness-state'
    Timestamp=(Get-Date).ToUniversalTime().ToString('o')
    RunId=$state.run_id
    SourceId=$state.source_id
    Seq=$state.seq
    Mode=$state.mode
    IngestStatus=$state.ingest_status
    StateAgeMs=$state.state_age_ms
  } | Format-List

  $persistenceRun = "persistence-$([guid]::NewGuid().ToString('N'))"
  $frame = [ordered]@{
    schema_version='reclaim.telemetry.v1'
    mode='live'
    run_id=$persistenceRun
    source_id='vm-persistence-proof'
    seq=900001
    ts=(Get-Date).ToUniversalTime().ToString('o')
    cycle_id='persistence-check'
    source_op_state='S_Idle'
    active_chamber='NONE'
    vars=[ordered]@{
      PL_T_bed_tc1=300.0; PL_T_bed_tc2=300.0; PL_T_bed_tc3=300.0; PL_T_bed_tc4=300.0
      PL_T_wall_tc1=300.0; PL_P_fwd=0.0; PL_P_refl=0.0
    }
  }
  $ingestHeaders = @{Authorization="Bearer $($secrets.RECLAIM_INGEST_TOKEN)"}
  $body = ($frame | ConvertTo-Json -Depth 6 -Compress)
  $accepted = Invoke-RestMethod -Method Post -Headers $ingestHeaders -ContentType 'application/x-ndjson' `
    -Body $body "$publicUrl/ingest"
  if ($accepted.results[0].status -ne 'accepted') { throw 'Persistence proof frame was not accepted.' }
  $stateHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $stateFile).Hash

  Restart-Service RECLAIMIngestEngine
  (Get-Service RECLAIMIngestEngine).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
  $deadline = (Get-Date).AddSeconds(60)
  do {
    try { $health = Invoke-RestMethod 'http://127.0.0.1:8078/health'; break } catch { Start-Sleep -Milliseconds 500 }
  } while ((Get-Date) -lt $deadline)
  if (-not $health.ok) { throw 'Engine did not become healthy after restart.' }
  if ($health.active_run_id -ne $persistenceRun) { throw 'Active run identity was not restored after restart.' }

  $frame.ts = (Get-Date).ToUniversalTime().ToString('o')
  $body = ($frame | ConvertTo-Json -Depth 6 -Compress)
  $duplicate = Invoke-RestMethod -Method Post -Headers $ingestHeaders -ContentType 'application/x-ndjson' `
    -Body $body "$publicUrl/ingest"
  if ($duplicate.results[0].status -ne 'duplicate') { throw 'Sequence was not deduplicated after restart.' }
  $stateHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $stateFile).Hash
  [pscustomobject]@{
    Boundary='restart-persistence'
    Timestamp=(Get-Date).ToUniversalTime().ToString('o')
    RunId=$persistenceRun
    SourceId='vm-persistence-proof'
    Seq=900001
    FirstDisposition='accepted'
    PostRestartDisposition='duplicate'
    ActiveRunRestored=$true
    StateFileHashStable=($stateHashBefore -eq $stateHashAfter)
  } | Format-List
} finally {
  Remove-Item Env:RECLAIM_INGEST_TOKEN, Env:RECLAIM_READ_TOKEN -ErrorAction SilentlyContinue
  $secrets.Clear()
}
