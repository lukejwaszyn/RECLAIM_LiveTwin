<#
.SYNOPSIS
Installs the validated RECLAIM gateway boot task on the Windows 10 laptop.

.DESCRIPTION
This guarded installer refuses placeholder/invalid HTTPS configuration, an
unsafe secret-file ACL, a non-Private cRIO interface, a mismatched firewall rule,
an exposed status port, active gateway listeners, or an unexpected existing task.
Registration does not start the gateway unless -Start is explicitly supplied.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [switch]$Start,
    [switch]$ReplaceExisting,
    [string]$GatewayDirectory = "C:\RECLAIM\pi_gateway",
    [string]$InterfaceAlias = "Ethernet",
    [string]$LaptopAddress = "192.168.1.1",
    [string]$CrioAddress = "192.168.1.2",
    [string]$FirewallRuleName = "RECLAIM cRIO telemetry (TCP 9070, direct link)",
    [string]$TaskName = "RECLAIM-EdgeGateway"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-ConfigAcl {
    param([Parameter(Mandatory = $true)][string]$Path)
    $trustedSids = @("S-1-5-18", "S-1-5-32-544")
    $presentSids = [Collections.Generic.HashSet[string]]::new()
    foreach ($entry in (Get-Acl -LiteralPath $Path).Access) {
        if ($entry.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) { continue }
        try {
            $sid = $entry.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        } catch {
            throw "Could not resolve config ACL identity '$($entry.IdentityReference)'."
        }
        if ($sid -notin $trustedSids) {
            throw "Unsafe config ACL grants '$($entry.FileSystemRights)' to '$($entry.IdentityReference)'. Run finalize-gateway-config.ps1 first."
        }
        [void]$presentSids.Add($sid)
    }
    foreach ($requiredSid in $trustedSids) {
        if (-not $presentSids.Contains($requiredSid)) {
            throw "Config ACL is missing required principal SID $requiredSid. Run finalize-gateway-config.ps1 first."
        }
    }
}

function Assert-FirewallContract {
    $rule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
    if ($null -eq $rule) { throw "Required firewall rule not found: $FirewallRuleName" }
    $port = $rule | Get-NetFirewallPortFilter
    $address = $rule | Get-NetFirewallAddressFilter
    $interface = $rule | Get-NetFirewallInterfaceFilter
    if ([string]$rule.Enabled -ne "True" -or [string]$rule.Direction -ne "Inbound" -or
        [string]$rule.Action -ne "Allow" -or [string]$rule.Profile -notmatch "Private" -or
        [string]$port.Protocol -notmatch "TCP|6" -or [string]$port.LocalPort -ne "9070" -or
        @($address.LocalAddress) -notcontains $LaptopAddress -or
        @($address.RemoteAddress) -notcontains $CrioAddress -or
        @($interface.InterfaceAlias) -notcontains $InterfaceAlias) {
        throw "Firewall rule '$FirewallRuleName' does not match the reviewed cRIO-only contract."
    }

    foreach ($candidate in @(Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow)) {
        $candidatePort = $candidate | Get-NetFirewallPortFilter
        if ([string]$candidatePort.LocalPort -eq "9080") {
            throw "Inbound firewall rule '$($candidate.DisplayName)' exposes loopback-only status port 9080."
        }
    }
}

if (-not (Test-IsAdministrator)) {
    throw "Run this installer from an elevated PowerShell session."
}

$python = Join-Path $GatewayDirectory ".venv\Scripts\python.exe"
$configPath = Join-Path $GatewayDirectory "config.windows.yaml"
if (-not (Test-Path -LiteralPath $python)) { throw "Gateway Python not found: $python" }
if (-not (Test-Path -LiteralPath $configPath)) { throw "Gateway config not found: $configPath" }

$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $GatewayDirectory
    & $python -c `
        "import os; from reclaim_edge.config import Config; c=Config.load(r'$configPath'); assert c.transport == 'https' and c.mode == 'live' and c.listen_host == '$LaptopAddress' and c.listen_port == 9070 and c.status_port == 9080 and c.convene_enabled and os.path.isfile(os.path.expandvars(os.path.expanduser(c.convene_credentials_path))); print('Gateway dual-publish config gate: PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Production config gate failed." }
} finally {
    if ($null -eq $oldPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $oldPythonPath
    }
}

Assert-ConfigAcl -Path $configPath

$profile = Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias
if ([string]$profile.NetworkCategory -ne "Private") {
    throw "Interface '$InterfaceAlias' is not Private. Run configure-crio-network-firewall.ps1 -Mode Apply."
}
$address = Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 `
    -IPAddress $LaptopAddress -ErrorAction SilentlyContinue
if ($null -eq $address) { throw "$LaptopAddress is not assigned to '$InterfaceAlias'." }
if (Get-NetRoute -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 `
        -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue) {
    throw "The isolated cRIO interface has a default route."
}
Assert-FirewallContract

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 9070,9080 -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    throw "Gateway/status listener already active; stop the manual process before task installation."
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask -and -not $ReplaceExisting) {
    throw "Task '$TaskName' already exists. Preserve and inspect it, or rerun with -ReplaceExisting after review."
}

if (-not $PSCmdlet.ShouldProcess($TaskName, "Register validated SYSTEM boot task")) { return }

[Environment]::SetEnvironmentVariable("RECLAIM_EDGE_CONFIG", $configPath, "Machine")
New-Item -ItemType Directory -Force "C:\ProgramData\RECLAIM" | Out-Null

$action = New-ScheduledTaskAction -Execute $python -Argument "-m reclaim_edge.main" `
    -WorkingDirectory $GatewayDirectory
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" `
    -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

if ($Start -and $PSCmdlet.ShouldProcess($TaskName, "Start gateway task now")) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Registered and started '$TaskName'."
} else {
    Write-Host "Registered '$TaskName' without starting it."
}
Write-Host "Verify locally: http://127.0.0.1:9080/health"
Write-Host "Stop: Stop-ScheduledTask -TaskName $TaskName"
