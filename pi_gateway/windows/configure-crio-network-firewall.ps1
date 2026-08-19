# RECLAIM cRIO direct-link firewall preparation for the Windows 10 gateway.
#
# This script deliberately does NOT change either endpoint's IPv4 address,
# create a default route, start the gateway, or open the loopback status port.
# It preserves the verified laboratory link:
#   laptop 192.168.1.1/24 <-> cRIO 192.168.1.2/24
#
# Run read-only audit (default):
#   .\configure-crio-network-firewall.ps1
#
# Apply from an elevated PowerShell:
#   .\configure-crio-network-firewall.ps1 -Mode Apply
#
# Roll back from an elevated PowerShell:
#   .\configure-crio-network-firewall.ps1 -Mode Rollback

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [ValidateSet("Audit", "Apply", "Rollback")]
    [string]$Mode = "Audit",

    [string]$InterfaceAlias = "Ethernet",
    [string]$LaptopAddress = "192.168.1.1",
    [ValidateRange(1, 32)]
    [int]$PrefixLength = 24,
    [string]$CrioAddress = "192.168.1.2",
    [ValidateRange(1, 65535)]
    [int]$TelemetryPort = 9070,

    [string]$RuleName = "RECLAIM cRIO telemetry (TCP 9070, direct link)",
    [string]$BackupPath = "C:\ProgramData\RECLAIM\crio-network-firewall-before.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ExplicitPort9080AllowRules {
    $matches = @()
    foreach ($rule in @(Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow)) {
        $portFilter = $rule | Get-NetFirewallPortFilter
        if ([string]$portFilter.LocalPort -eq "9080") {
            $matches += $rule.DisplayName
        }
    }
    return $matches
}

function Get-ReclaimNetworkState {
    $adapter = Get-NetAdapter -Name $InterfaceAlias
    $addresses = @(Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4)
    $profile = Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias -ErrorAction SilentlyContinue
    $defaultRoutes = @(Get-NetRoute -InterfaceAlias $InterfaceAlias `
        -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)
    $rule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue

    [pscustomobject]@{
        CapturedAtUtc = [DateTime]::UtcNow.ToString("o")
        InterfaceAlias = $InterfaceAlias
        AdapterStatus = [string]$adapter.Status
        LinkSpeed = [string]$adapter.LinkSpeed
        MacAddress = [string]$adapter.MacAddress
        IPv4 = @($addresses | ForEach-Object {
            [pscustomobject]@{
                Address = $_.IPAddress
                PrefixLength = $_.PrefixLength
                PrefixOrigin = [string]$_.PrefixOrigin
            }
        })
        NetworkCategory = if ($null -ne $profile) { [string]$profile.NetworkCategory } else { $null }
        EthernetDefaultRoutes = @($defaultRoutes | ForEach-Object {
            [pscustomobject]@{ NextHop = $_.NextHop; RouteMetric = $_.RouteMetric }
        })
        ReclaimRulePresent = ($null -ne $rule)
        ExplicitInbound9080AllowRules = @(Get-ExplicitPort9080AllowRules)
    }
}

function Assert-DirectLinkPreconditions {
    $adapter = Get-NetAdapter -Name $InterfaceAlias
    if ([string]$adapter.Status -ne "Up") {
        throw "Interface '$InterfaceAlias' is not Up (status: $($adapter.Status))."
    }

    $matchingAddress = Get-NetIPAddress -InterfaceAlias $InterfaceAlias `
        -AddressFamily IPv4 -IPAddress $LaptopAddress -ErrorAction SilentlyContinue
    if ($null -eq $matchingAddress -or $matchingAddress.PrefixLength -ne $PrefixLength) {
        throw "Expected $LaptopAddress/$PrefixLength on '$InterfaceAlias'; refusing to change firewall state."
    }

    $defaultRoute = Get-NetRoute -InterfaceAlias $InterfaceAlias `
        -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
    if ($null -ne $defaultRoute) {
        throw "'$InterfaceAlias' has a default route; the isolated cRIO interface must not have one."
    }

    if (-not (Test-Connection -ComputerName $CrioAddress -Count 1 -Quiet)) {
        throw "cRIO peer $CrioAddress did not answer ping; refusing to change firewall state."
    }

    $statusRules = @(Get-ExplicitPort9080AllowRules)
    if ($statusRules.Count -gt 0) {
        throw "Explicit inbound allow rule(s) already expose TCP 9080: $($statusRules -join ', '). Remove or review them before proceeding."
    }
}

function Assert-RuleMatchesContract {
    param([Parameter(Mandatory = $true)]$Rule)

    $port = $Rule | Get-NetFirewallPortFilter
    $address = $Rule | Get-NetFirewallAddressFilter
    $interface = $Rule | Get-NetFirewallInterfaceFilter

    $problems = @()
    if ([string]$Rule.Enabled -ne "True") { $problems += "disabled" }
    if ([string]$Rule.Direction -ne "Inbound") { $problems += "direction is not Inbound" }
    if ([string]$Rule.Action -ne "Allow") { $problems += "action is not Allow" }
    if ([string]$Rule.Profile -notmatch "Private") { $problems += "profile is not Private-only" }
    if ([string]$port.Protocol -notmatch "TCP|6") { $problems += "protocol is not TCP" }
    if ([string]$port.LocalPort -ne [string]$TelemetryPort) { $problems += "local port is not $TelemetryPort" }
    if (@($address.LocalAddress) -notcontains $LaptopAddress) { $problems += "local address is not $LaptopAddress" }
    if (@($address.RemoteAddress) -notcontains $CrioAddress) { $problems += "remote address is not $CrioAddress" }
    if (@($interface.InterfaceAlias) -notcontains $InterfaceAlias) { $problems += "interface is not $InterfaceAlias" }

    if ($problems.Count -gt 0) {
        throw "Existing firewall rule '$RuleName' conflicts with the RECLAIM contract: $($problems -join '; ')."
    }
}

if (-not (Test-IsAdministrator)) {
    throw "Mode '$Mode' requires an elevated PowerShell session (Run as administrator) so firewall inspection is complete."
}

if ($Mode -eq "Audit") {
    Get-ReclaimNetworkState | ConvertTo-Json -Depth 6
    return
}

if ($Mode -eq "Rollback") {
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        throw "Rollback record not found: $BackupPath"
    }

    $before = Get-Content -Raw -LiteralPath $BackupPath | ConvertFrom-Json
    if ([string]$before.InterfaceAlias -ne $InterfaceAlias) {
        throw "Rollback record is for interface '$($before.InterfaceAlias)', not '$InterfaceAlias'."
    }

    $rule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
    if ($null -ne $rule -and $PSCmdlet.ShouldProcess($RuleName, "Remove scoped RECLAIM firewall rule")) {
        Remove-NetFirewallRule -DisplayName $RuleName
    }

    if (-not [string]::IsNullOrWhiteSpace([string]$before.NetworkCategory)) {
        $current = Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias
        if ([string]$current.NetworkCategory -ne [string]$before.NetworkCategory -and
            $PSCmdlet.ShouldProcess($InterfaceAlias, "Restore network category to $($before.NetworkCategory)")) {
            Set-NetConnectionProfile -InterfaceAlias $InterfaceAlias `
                -NetworkCategory $before.NetworkCategory
        }
    }

    Get-ReclaimNetworkState | ConvertTo-Json -Depth 6
    return
}

Assert-DirectLinkPreconditions

$backupDirectory = Split-Path -Parent $BackupPath
if (-not (Test-Path -LiteralPath $backupDirectory) -and
    $PSCmdlet.ShouldProcess($backupDirectory, "Create rollback-record directory")) {
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $BackupPath)) {
    if ($PSCmdlet.ShouldProcess($BackupPath, "Save pre-change network/firewall state")) {
        Get-ReclaimNetworkState | ConvertTo-Json -Depth 6 | Set-Content `
            -LiteralPath $BackupPath -Encoding UTF8
    }
} else {
    Write-Warning "Preserving existing rollback record: $BackupPath"
}

$profile = Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias
if ([string]$profile.NetworkCategory -ne "Private" -and
    $PSCmdlet.ShouldProcess($InterfaceAlias, "Set network category to Private")) {
    Set-NetConnectionProfile -InterfaceAlias $InterfaceAlias -NetworkCategory Private
}

$existingRule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($null -ne $existingRule) {
    Assert-RuleMatchesContract -Rule $existingRule
    Write-Host "Existing rule already matches the required scope: $RuleName"
} elseif ($PSCmdlet.ShouldProcess($RuleName, "Create cRIO-only inbound TCP $TelemetryPort rule")) {
    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Description "RECLAIM telemetry from the directly connected cRIO only; no status-port exposure." `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $TelemetryPort `
        -LocalAddress $LaptopAddress `
        -RemoteAddress $CrioAddress `
        -InterfaceAlias $InterfaceAlias `
        -Profile Private | Out-Null
}

$createdRule = Get-NetFirewallRule -DisplayName $RuleName
Assert-RuleMatchesContract -Rule $createdRule

Write-Host "RECLAIM cRIO firewall preparation is complete."
Write-Host "Allowed: $CrioAddress -> $LaptopAddress TCP $TelemetryPort on '$InterfaceAlias' (Private only)."
Write-Host "Not opened: TCP 9080. No IP address or route was changed."
Get-ReclaimNetworkState | ConvertTo-Json -Depth 6
