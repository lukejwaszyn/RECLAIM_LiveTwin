<#
.SYNOPSIS
Collects a credential-safe, read-only inventory of the RECLAIM predictive VM.

.DESCRIPTION
Run this script from an elevated PowerShell session on the Windows Server 2025
predictive-engine VM before changing the engine or Cloudflare route. It does not
read service command lines, Cloudflare configuration contents, or secret files.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host "`n=== $Title ==="
}

Write-Section "VM IDENTITY"
hostname.exe
Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion, OsBuildNumber

Write-Section "ENGINE"
Get-Service -Name "RECLAIMIngestEngine" -ErrorAction SilentlyContinue |
    Select-Object Name, Status, StartType

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8078 -ErrorAction SilentlyContinue)
$listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8078/health" -TimeoutSec 5 |
        ConvertTo-Json -Depth 6
} catch {
    Write-Warning "Engine health check failed: $($_.Exception.Message)"
}

Write-Section "CLOUDFLARED"
$cloudflared = Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue
if ($null -eq $cloudflared) {
    Write-Warning "cloudflared.exe was not found on PATH."
} else {
    & $cloudflared.Source --version
}

# Do not display service ImagePath or process command lines: remotely managed
# tunnel tokens can appear there.
Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue |
    Select-Object Name, Status, StartType
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue |
    Select-Object Id, Path, StartTime
Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match "cloudflared|RECLAIM" } |
    Select-Object TaskName, TaskPath, State

$cloudflareConfigPaths = @(
    (Join-Path $env:USERPROFILE ".cloudflared\config.yml"),
    (Join-Path $env:USERPROFILE ".cloudflared\config.yaml"),
    "C:\Windows\System32\config\systemprofile\.cloudflared\config.yml",
    "C:\Windows\System32\config\systemprofile\.cloudflared\config.yaml"
)
$cloudflareConfigPaths | ForEach-Object {
    [pscustomobject]@{ Path = $_; Exists = Test-Path -LiteralPath $_ }
}

Write-Section "RECLAIM PATHS"
@(
    "C:\ProgramData\RECLAIM",
    "C:\ProgramData\RECLAIM\releases",
    "C:\ProgramData\RECLAIM\engine",
    "C:\ProgramData\RECLAIM\convene-bridge",
    "C:\ProgramData\RECLAIM\cloudflared-quick"
) | ForEach-Object {
    [pscustomobject]@{ Path = $_; Exists = Test-Path -LiteralPath $_ }
}

Write-Section "CLOUDFLARE EGRESS"
Test-NetConnection -ComputerName "region1.v2.argotunnel.com" -Port 7844 |
    Select-Object ComputerName, RemotePort, TcpTestSucceeded

Write-Host "`nInventory complete. No configuration or service state was changed."
