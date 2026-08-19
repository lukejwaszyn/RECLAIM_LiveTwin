<#
.SYNOPSIS
Finalizes the Windows gateway HTTPS destination and secret-bearing config.

.DESCRIPTION
Run from elevated PowerShell after the predictive-engine operator privately
provides the final HTTPS /ingest URL and ingest token. The token is prompted as a
SecureString, never accepted on the command line, and never printed. The script
backs up the prior config under an ACL-protected directory, updates only
cloud_url/auth_token, validates through the deployed Python loader, and restricts
the active config to SYSTEM and Administrators.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [string]$CloudUrl,
    [string]$GatewayDirectory = "C:\RECLAIM\pi_gateway",
    [string]$BackupDirectory = "C:\ProgramData\RECLAIM\gateway-config-backups"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Set-SecretAcl {
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path
    $systemGrant = if ($item.PSIsContainer) { "*S-1-5-18:(OI)(CI)(F)" } else { "*S-1-5-18:(F)" }
    $adminGrant = if ($item.PSIsContainer) { "*S-1-5-32-544:(OI)(CI)(F)" } else { "*S-1-5-32-544:(F)" }
    & icacls.exe $Path /inheritance:r /grant:r $systemGrant $adminGrant | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to restrict ACL on $Path" }
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell session."
}

$configPath = Join-Path $GatewayDirectory "config.windows.yaml"
$python = Join-Path $GatewayDirectory ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $configPath)) { throw "Gateway config not found: $configPath" }
if (-not (Test-Path -LiteralPath $python)) { throw "Gateway Python not found: $python" }

try { $uri = [Uri]$CloudUrl } catch { throw "CloudUrl is not a valid absolute URI." }
if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne "https" -or
    [string]::IsNullOrWhiteSpace($uri.Host)) {
    throw "CloudUrl must be an absolute HTTPS URL."
}
if ($uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath.TrimEnd('/') -ne "/ingest") {
    throw "CloudUrl must be a credential-free HTTPS URL ending exactly in /ingest."
}
if ($CloudUrl -match "(?i)placeholder|changeme|not.provisioned|example") {
    throw "CloudUrl still looks like a placeholder."
}

if ($WhatIfPreference) {
    $PSCmdlet.ShouldProcess($configPath, "Securely finalize the HTTPS destination/token and restrict ACLs") | Out-Null
    return
}

$secureToken = Read-Host "Enter the VM RECLAIM_INGEST_TOKEN (input is hidden)" -AsSecureString
$credential = [PSCredential]::new("RECLAIM", $secureToken)
$plainToken = $credential.GetNetworkCredential().Password
try {
    if ([string]::IsNullOrWhiteSpace($plainToken) -or $plainToken.Length -lt 32) {
        throw "The ingest token must be at least 32 characters."
    }
    if ($plainToken -match "(?i)placeholder|changeme|not.provisioned|example") {
        throw "The ingest token still looks like a placeholder."
    }
    if (-not $PSCmdlet.ShouldProcess(
        $configPath,
        "Back up and finalize the gateway HTTPS config, validate it, and restrict its ACL"
    )) { return }

    New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
    Set-SecretAcl -Path $BackupDirectory
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $backupPath = Join-Path $BackupDirectory "config.windows.$timestamp.yaml"
    Copy-Item -LiteralPath $configPath -Destination $backupPath
    Set-SecretAcl -Path $backupPath

    $text = Get-Content -Raw -LiteralPath $configPath
    if ([regex]::Matches($text, '(?m)^\s*cloud_url\s*:').Count -ne 1) {
        throw "Expected exactly one cloud_url key in $configPath"
    }
    if ([regex]::Matches($text, '(?m)^\s*auth_token\s*:').Count -ne 1) {
        throw "Expected exactly one auth_token key in $configPath"
    }

    $quotedUrl = $CloudUrl.TrimEnd('/') | ConvertTo-Json -Compress
    $quotedToken = $plainToken | ConvertTo-Json -Compress
    $text = [regex]::Replace($text, '(?m)^\s*cloud_url\s*:.*$', "cloud_url: $quotedUrl")
    $text = [regex]::Replace($text, '(?m)^\s*auth_token\s*:.*$', "auth_token: $quotedToken")
    Set-Content -LiteralPath $configPath -Value $text -Encoding UTF8
    Set-SecretAcl -Path $configPath

    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $GatewayDirectory
        & $python -c `
            "from reclaim_edge.config import Config; c=Config.load(r'$configPath'); assert c.transport == 'https' and c.mode == 'live'; print('Gateway HTTPS config validation: PASS')"
        if ($LASTEXITCODE -ne 0) { throw "Deployed config validation failed." }
    } catch {
        Copy-Item -LiteralPath $backupPath -Destination $configPath -Force
        Set-SecretAcl -Path $configPath
        throw
    } finally {
        if ($null -eq $oldPythonPath) {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        } else {
            $env:PYTHONPATH = $oldPythonPath
        }
    }

    Write-Host "Gateway config finalized and validated."
    Write-Host "Destination: $($CloudUrl.TrimEnd('/'))"
    Write-Host "Credential: stored but not displayed"
    Write-Host "ACL: SYSTEM and Administrators only"
    Write-Host "Backup: $backupPath"
} finally {
    $plainToken = $null
    $credential = $null
    $secureToken = $null
}
