<#
.SYNOPSIS
Audits or starts the temporary RECLAIM Cloudflare Quick Tunnel.

.DESCRIPTION
This launcher exposes only the production predictive engine at
http://127.0.0.1:8078 through a randomly assigned trycloudflare.com hostname.
It does not install a service, create a scheduled task, read credentials, touch
Convene, or route gateway status port 9080 or rehearsal ports 8177-8179.

Quick Tunnel URLs are temporary and change when cloudflared is restarted. Use a
named tunnel on a Cloudflare-managed domain for durable operation.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [ValidateSet("Audit", "Run", "ShowUrl")]
    [string]$Mode = "Audit",

    [ValidatePattern('^127\.0\.0\.1$')]
    [string]$EngineHost = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$EnginePort = 8078,

    [string]$StateDirectory = "C:\ProgramData\RECLAIM\cloudflared-quick"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$urlPath = Join-Path $StateDirectory "public-url.txt"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-QuickTunnelPreflight {
    $cloudflared = Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue
    $engineService = Get-Service -Name "RECLAIMIngestEngine" -ErrorAction SilentlyContinue
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $EnginePort -ErrorAction SilentlyContinue)
    $cloudflaredService = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    $cloudflaredProcesses = @(Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue)
    $configPaths = @(
        (Join-Path $env:USERPROFILE ".cloudflared\config.yml"),
        (Join-Path $env:USERPROFILE ".cloudflared\config.yaml"),
        "C:\Windows\System32\config\systemprofile\.cloudflared\config.yml",
        "C:\Windows\System32\config\systemprofile\.cloudflared\config.yaml"
    )
    $existingConfigs = @($configPaths | Where-Object { Test-Path -LiteralPath $_ })

    [pscustomobject]@{
        CapturedAtUtc = [DateTime]::UtcNow.ToString("o")
        ComputerName = $env:COMPUTERNAME
        CloudflaredFound = ($null -ne $cloudflared)
        CloudflaredPath = if ($null -ne $cloudflared) { $cloudflared.Source } else { $null }
        EngineServiceStatus = if ($null -ne $engineService) { [string]$engineService.Status } else { "NotFound" }
        EngineListeners = @($listeners | ForEach-Object {
            [pscustomobject]@{
                LocalAddress = $_.LocalAddress
                LocalPort = $_.LocalPort
                OwningProcess = $_.OwningProcess
            }
        })
        CloudflaredServiceStatus = if ($null -ne $cloudflaredService) { [string]$cloudflaredService.Status } else { "NotFound" }
        CloudflaredProcessIds = @($cloudflaredProcesses.Id)
        ExistingConfigFiles = $existingConfigs
        SavedPublicUrlExists = Test-Path -LiteralPath $urlPath
    }
}

function Assert-QuickTunnelPreconditions {
    param([Parameter(Mandatory = $true)]$State)

    if (-not $State.CloudflaredFound) {
        throw "cloudflared.exe was not found on PATH. Install the approved Cloudflare package before continuing."
    }
    if ($State.EngineServiceStatus -ne "Running") {
        throw "RECLAIMIngestEngine is not Running (status: $($State.EngineServiceStatus))."
    }
    if ($State.EngineListeners.Count -ne 1 -or
        $State.EngineListeners[0].LocalAddress -ne $EngineHost -or
        $State.EngineListeners[0].LocalPort -ne $EnginePort) {
        throw "Expected exactly one loopback listener at ${EngineHost}:$EnginePort; refusing public exposure."
    }
    if ($State.CloudflaredServiceStatus -ne "NotFound") {
        throw "A cloudflared Windows service already exists (status: $($State.CloudflaredServiceStatus)); preserve and review it instead of starting a competing tunnel."
    }
    if ($State.CloudflaredProcessIds.Count -gt 0) {
        throw "Existing cloudflared process(es) found: $($State.CloudflaredProcessIds -join ', '). Preserve and review them instead of starting a competing tunnel."
    }
    if ($State.ExistingConfigFiles.Count -gt 0) {
        throw "Cloudflare configuration file(s) already exist: $($State.ExistingConfigFiles -join ', '). Quick Tunnels do not use these files; preserve and review them."
    }

    $health = Invoke-RestMethod -Uri "http://${EngineHost}:$EnginePort/health" -TimeoutSec 5
    if ($health.PSObject.Properties.Name -contains "ok" -and -not $health.ok) {
        throw "The predictive-engine health endpoint reported ok=false."
    }

    $egress = Test-NetConnection -ComputerName "region1.v2.argotunnel.com" -Port 7844 -WarningAction SilentlyContinue
    if (-not $egress.TcpTestSucceeded) {
        throw "Outbound TCP 7844 to Cloudflare failed. No firewall rule will be changed automatically."
    }
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell session."
}

if ($Mode -eq "ShowUrl") {
    if (-not (Test-Path -LiteralPath $urlPath)) {
        throw "No saved Quick Tunnel URL was found at $urlPath."
    }
    $publicUrl = (Get-Content -Raw -LiteralPath $urlPath).Trim().TrimEnd('/')
    Write-Host "Gateway cloud_url: $publicUrl/ingest"
    Write-Warning "This temporary URL changes whenever cloudflared restarts."
    return
}

$state = Get-QuickTunnelPreflight
if ($Mode -eq "Audit") {
    $state | ConvertTo-Json -Depth 6
    Write-Host "Audit complete. No configuration or service state was changed."
    return
}

Assert-QuickTunnelPreconditions -State $state

if (-not $PSCmdlet.ShouldProcess(
    "http://${EngineHost}:$EnginePort",
    "Start a temporary public Cloudflare Quick Tunnel in the foreground"
)) {
    return
}

New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$logPath = Join-Path $StateDirectory "cloudflared-$timestamp.log"
Remove-Item -LiteralPath $urlPath -Force -ErrorAction SilentlyContinue

Write-Host "Starting temporary Cloudflare tunnel to http://${EngineHost}:$EnginePort"
Write-Host "Log: $logPath"
Write-Host "The process stays in this window. Stop it with Ctrl+C."
Write-Warning "After any restart, rerun this script and update the gateway cloud_url."

$cloudflaredPath = $state.CloudflaredPath
& $cloudflaredPath tunnel --url "http://${EngineHost}:$EnginePort" --no-autoupdate 2>&1 |
    ForEach-Object {
        $line = $_.ToString()
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
        Write-Host $line

        $match = [regex]::Match($line, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) {
            $publicUrl = $match.Value.TrimEnd('/')
            Set-Content -LiteralPath $urlPath -Value $publicUrl -Encoding ASCII
            Write-Host "`nRECLAIM gateway cloud_url: $publicUrl/ingest" -ForegroundColor Green
            Write-Host "Saved base URL: $urlPath`n"
        }
    }

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "cloudflared exited with code $exitCode. Review $logPath."
}
