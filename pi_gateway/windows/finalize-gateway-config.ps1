<#
.SYNOPSIS
Finalizes the Windows gateway HTTPS destination and secret-bearing config.

.DESCRIPTION
Run from elevated PowerShell after the predictive-engine operator privately
provides the final HTTPS /ingest URL and ingest token. The token is prompted as a
SecureString, never accepted on the command line, and never printed. The script
backs up the prior config under an ACL-protected directory, updates the VM
cloud_url/auth_token plus the credential-reference-only Convene gw_ audit path,
validates through the deployed Python loader, and restricts the active config to
SYSTEM and Administrators.
#>

[CmdletBinding(
    SupportsShouldProcess = $true,
    ConfirmImpact = "High",
    DefaultParameterSetName = "Finalize"
)]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Finalize")]
    [string]$CloudUrl,
    [Parameter(Mandatory = $true, ParameterSetName = "RepairAcl")]
    [switch]$RepairAclOnly,
    [string]$ConveneApi = "https://reservation-backend-25386666460.us-central1.run.app/api",
    [string]$ConveneCredentialPath = "C:/Windows/System32/config/systemprofile/.convene_agent.json",
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
    $trustedSids = @("S-1-5-18", "S-1-5-32-544")
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleSpecific($rule)
    }
    foreach ($sidText in $trustedSids) {
        $sid = [Security.Principal.SecurityIdentifier]::new($sidText)
        if ($item.PSIsContainer) {
            $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                $sid,
                [Security.AccessControl.FileSystemRights]::FullControl,
                [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                    [Security.AccessControl.InheritanceFlags]::ObjectInherit,
                [Security.AccessControl.PropagationFlags]::None,
                [Security.AccessControl.AccessControlType]::Allow
            )
        } else {
            $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                $sid,
                [Security.AccessControl.FileSystemRights]::FullControl,
                [Security.AccessControl.AccessControlType]::Allow
            )
        }
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl

    $verifiedAcl = Get-Acl -LiteralPath $Path
    if (-not $verifiedAcl.AreAccessRulesProtected) {
        throw "ACL inheritance remains enabled on $Path"
    }
    $presentSids = [Collections.Generic.HashSet[string]]::new()
    foreach ($entry in @($verifiedAcl.Access)) {
        $sid = $entry.IdentityReference.Translate(
            [Security.Principal.SecurityIdentifier]
        ).Value
        if ($entry.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $sid -notin $trustedSids -or
            ($entry.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -ne
                [Security.AccessControl.FileSystemRights]::FullControl) {
            throw "ACL verification found an unexpected entry for '$($entry.IdentityReference)' on $Path"
        }
        [void]$presentSids.Add($sid)
    }
    if ($presentSids.Count -ne $trustedSids.Count -or
        @($trustedSids | Where-Object { -not $presentSids.Contains($_) }).Count -gt 0) {
        throw "ACL verification did not find exactly SYSTEM and Administrators on $Path"
    }
}

function Set-YamlScalar {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$SerializedValue
    )
    $pattern = "(?m)^\s*$([regex]::Escape($Key))\s*:.*$"
    $count = [regex]::Matches($Text, $pattern).Count
    if ($count -gt 1) { throw "Expected at most one $Key key in the gateway config." }
    if ($count -eq 1) {
        $replacement = "$Key`: $SerializedValue"
        return [regex]::Replace(
            $Text,
            $pattern,
            [Text.RegularExpressions.MatchEvaluator]{ param($match) $replacement }
        )
    }
    return $Text.TrimEnd() + "`r`n$Key`: $SerializedValue`r`n"
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell session."
}

$configPath = Join-Path $GatewayDirectory "config.windows.yaml"
$python = Join-Path $GatewayDirectory ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $configPath)) { throw "Gateway config not found: $configPath" }
if (-not (Test-Path -LiteralPath $python)) { throw "Gateway Python not found: $python" }

if ($RepairAclOnly) {
    if (-not $PSCmdlet.ShouldProcess(
        "$configPath and $BackupDirectory",
        "Rebuild and verify the gateway secret ACLs without reading or changing credentials"
    )) { return }

    Set-SecretAcl -Path $configPath
    $backupCount = 0
    if (Test-Path -LiteralPath $BackupDirectory -PathType Container) {
        foreach ($backup in @(Get-ChildItem -LiteralPath $BackupDirectory `
                -Filter "config.windows.*.yaml" -File)) {
            Set-SecretAcl -Path $backup.FullName
            $backupCount++
        }
        Set-SecretAcl -Path $BackupDirectory
    }

    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $GatewayDirectory
        & $python -c `
            "from reclaim_edge.config import Config; c=Config.load(r'$configPath'); assert c.transport == 'https' and c.mode == 'live' and c.convene_enabled; print('Gateway dual-publish config validation: PASS')"
        if ($LASTEXITCODE -ne 0) { throw "Deployed config validation failed." }
    } finally {
        if ($null -eq $oldPythonPath) {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        } else {
            $env:PYTHONPATH = $oldPythonPath
        }
    }

    Write-Host "Gateway secret ACL repair: PASS"
    Write-Host "ACL: SYSTEM and Administrators only"
    Write-Host "Backup files repaired: $backupCount"
    return
}

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

try { $conveneUri = [Uri]$ConveneApi } catch { throw "ConveneApi is not a valid absolute URI." }
if (-not $conveneUri.IsAbsoluteUri -or $conveneUri.Scheme -ne "https" -or
    $conveneUri.UserInfo -or $conveneUri.Query -or $conveneUri.Fragment -or
    $conveneUri.AbsolutePath.TrimEnd('/') -ne "/api") {
    throw "ConveneApi must be a credential-free HTTPS URL ending exactly in /api."
}
$nativeConveneCredentialPath = $ConveneCredentialPath -replace '/', '\'
if (-not (Test-Path -LiteralPath $nativeConveneCredentialPath -PathType Leaf)) {
    throw "Desktop Convene SYSTEM credential not found: $nativeConveneCredentialPath"
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
    $quotedUrl = $CloudUrl.TrimEnd('/') | ConvertTo-Json -Compress
    $quotedToken = $plainToken | ConvertTo-Json -Compress
    $quotedConveneApi = $ConveneApi.TrimEnd('/') | ConvertTo-Json -Compress
    $quotedConveneCredential = $ConveneCredentialPath | ConvertTo-Json -Compress
    $text = Set-YamlScalar -Text $text -Key 'cloud_url' -SerializedValue $quotedUrl
    $text = Set-YamlScalar -Text $text -Key 'auth_token' -SerializedValue $quotedToken
    $text = Set-YamlScalar -Text $text -Key 'convene_enabled' -SerializedValue 'true'
    $text = Set-YamlScalar -Text $text -Key 'convene_api' -SerializedValue $quotedConveneApi
    $text = Set-YamlScalar -Text $text -Key 'convene_credentials_path' -SerializedValue $quotedConveneCredential
    $text = Set-YamlScalar -Text $text -Key 'convene_timeout_s' -SerializedValue '10.0'
    Set-Content -LiteralPath $configPath -Value $text -Encoding UTF8
    Set-SecretAcl -Path $configPath

    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $GatewayDirectory
        & $python -c `
            "from reclaim_edge.config import Config; c=Config.load(r'$configPath'); assert c.transport == 'https' and c.mode == 'live' and c.convene_enabled; print('Gateway dual-publish config validation: PASS')"
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
    Write-Host "Convene audit: $($ConveneApi.TrimEnd('/'))/machine/publish (gw_ only)"
    Write-Host "Credential: stored but not displayed"
    Write-Host "ACL: SYSTEM and Administrators only"
    Write-Host "Backup: $backupPath"
} finally {
    $plainToken = $null
    $credential = $null
    $secureToken = $null
}
