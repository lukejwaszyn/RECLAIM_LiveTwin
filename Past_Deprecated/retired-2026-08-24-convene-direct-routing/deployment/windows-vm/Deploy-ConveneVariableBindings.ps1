<#
.SYNOPSIS
Publishes the current RECLAIM scalar handoff to exact Convene variable IDs.
.DESCRIPTION
Reads C:\ConveneAgent\sim_vars.json and an environment-local binding manifest,
validates every source field and scalar type before sending anything, then posts
each value to Convene's per-variable agent-value endpoint.

The Convene agent token is read at runtime from -AgentTokenFile, from the
CONVENE_AGENT_TOKEN environment variable, from the installed token-bearing agent
PowerShell script, or from a masked interactive prompt. The installed script is
parsed as data and is never executed or modified. The token is never printed or
written by this script.
.PARAMETER MappingPath
Path to the populated, git-ignored CONVENE_VARIABLE_BINDINGS.local.json manifest.
.PARAMETER BackendBaseUrl
Convene backend API base URL. Keep this parameterized because Cloud Run hostnames
and approved environments may change.
.PARAMETER AgentTokenFile
Optional ACL-protected file containing only the Convene agent token.
.PARAMETER AgentScriptPath
Installed token-bearing Convene agent script. Defaults to C:\ConveneAgent\agent.ps1.
.PARAMETER NonInteractive
Fail instead of prompting when neither AgentTokenFile nor CONVENE_AGENT_TOKEN is set.
.EXAMPLE
.\deployment\windows-vm\Deploy-ConveneVariableBindings.ps1 -WhatIf
.EXAMPLE
.\deployment\windows-vm\Deploy-ConveneVariableBindings.ps1 `
  -AgentTokenFile 'C:\secure\convene-agent-token.txt'
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param(
    [string]$MappingPath = (Join-Path $PSScriptRoot '..\CONVENE_VARIABLE_BINDINGS.local.json'),

    [ValidatePattern('^https://')]
    [string]$BackendBaseUrl = 'https://reservation-backend-xczhrp2y6q-uc.a.run.app/api',

    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$MachineId = 'reclaim-engine-2',

    [string]$SourcePath = 'C:\ConveneAgent\sim_vars.json',

    [string]$AgentTokenFile,

    [string]$AgentScriptPath = 'C:\ConveneAgent\agent.ps1',

    [ValidateRange(0, 5000)]
    [int]$DelayMilliseconds = 50,

    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'

function Test-IsNumber {
    param([object]$Value)
    if ($Value -is [bool]) { return $false }
    return $Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or
        $Value -is [decimal]
}

function Assert-ScalarType {
    param(
        [Parameter(Mandatory)][string]$VariableName,
        [Parameter(Mandatory)][string]$ExpectedType,
        [AllowNull()][object]$Value
    )
    $valid = switch ($ExpectedType) {
        'boolean' { $Value -is [bool] }
        'string' { $Value -is [string] }
        'number' { Test-IsNumber -Value $Value }
        default { throw "Unsupported scalar type '$ExpectedType' for $VariableName." }
    }
    if (-not $valid) {
        $actual = if ($null -eq $Value) { 'null' } else { $Value.GetType().FullName }
        throw "Type mismatch for ${VariableName}: expected $ExpectedType, received $actual."
    }
}

function Read-AtomicJsonObject {
    param([Parameter(Mandatory)][string]$LiteralPath)
    $lastError = $null
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            $document = [IO.File]::ReadAllText($LiteralPath) | ConvertFrom-Json
            if ($null -eq $document -or $document -is [array]) {
                throw "JSON document at $LiteralPath is not an object."
            }
            return $document
        } catch {
            $lastError = $_
            if ($attempt -lt 5) { Start-Sleep -Milliseconds 100 }
        }
    }
    throw "Could not read a complete JSON object from $LiteralPath after 5 attempts: $($lastError.Exception.Message)"
}

function Read-AgentToken {
    if (-not [string]::IsNullOrWhiteSpace($AgentTokenFile)) {
        if (-not (Test-Path -LiteralPath $AgentTokenFile -PathType Leaf)) {
            throw "Agent token file does not exist: $AgentTokenFile"
        }
        $tokenFromFile = [IO.File]::ReadAllText($AgentTokenFile).Trim()
        if ([string]::IsNullOrWhiteSpace($tokenFromFile)) {
            throw 'Agent token file is empty.'
        }
        return $tokenFromFile
    }

    if (-not [string]::IsNullOrWhiteSpace($env:CONVENE_AGENT_TOKEN)) {
        return $env:CONVENE_AGENT_TOKEN
    }

    if (-not [string]::IsNullOrWhiteSpace($AgentScriptPath) -and
        (Test-Path -LiteralPath $AgentScriptPath -PathType Leaf)) {
        $parseTokens = $null
        $parseErrors = $null
        $agentAst = [System.Management.Automation.Language.Parser]::ParseFile(
            $AgentScriptPath,
            [ref]$parseTokens,
            [ref]$parseErrors
        )
        if ($parseErrors.Count -ne 0) {
            throw "Installed Convene agent script could not be parsed safely: $AgentScriptPath"
        }

        $tokenAssignments = @($agentAst.FindAll({
            param($node)
            if ($node -isnot [System.Management.Automation.Language.AssignmentStatementAst]) {
                return $false
            }
            if ($node.Left -isnot [System.Management.Automation.Language.VariableExpressionAst]) {
                return $false
            }
            if ($node.Right -isnot [System.Management.Automation.Language.StringConstantExpressionAst]) {
                return $false
            }
            return $node.Left.VariablePath.UserPath -match '^(?i:token|agenttoken|agent_token|vmtoken|vm_token|convenetoken|convene_token)$'
        }, $true))

        $tokenCandidates = @($tokenAssignments |
            ForEach-Object { $_.Right.Value } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique)
        if ($tokenCandidates.Count -eq 1) {
            return $tokenCandidates[0]
        }
        if ($tokenCandidates.Count -gt 1) {
            throw 'Installed Convene agent script contains multiple candidate token assignments.'
        }
    }

    if ($NonInteractive) {
        throw 'No unambiguous agent token source was found in non-interactive mode.'
    }

    $secureToken = Read-Host 'Convene agent token' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ([string]::IsNullOrWhiteSpace($plainToken)) { throw 'Agent token is empty.' }
        return $plainToken
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secureToken.Dispose()
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Convene variable deployment must run elevated to read the protected handoff.'
}

$resolvedMappingPath = (Resolve-Path -LiteralPath $MappingPath).Path
$mapping = Read-AtomicJsonObject -LiteralPath $resolvedMappingPath
$source = Read-AtomicJsonObject -LiteralPath $SourcePath

if ($mapping.schema -ne 'reclaim.convene-variable-bindings.v1') {
    throw "Unexpected binding manifest schema: $($mapping.schema)"
}
if ($mapping.machine -ne $MachineId) {
    throw "Binding manifest machine '$($mapping.machine)' does not match requested machine '$MachineId'."
}

$bindings = @($mapping.bindings)
if ($bindings.Count -eq 0) { throw 'Binding manifest contains no bindings.' }

$duplicateNames = @($bindings | Group-Object convene_variable | Where-Object Count -gt 1)
$duplicateIds = @($bindings | Group-Object convene_id | Where-Object Count -gt 1)
if ($duplicateNames.Count -ne 0) { throw 'Binding manifest contains duplicate Convene variable names.' }
if ($duplicateIds.Count -ne 0) { throw 'Binding manifest contains duplicate Convene IDs.' }

$planned = foreach ($binding in $bindings) {
    $field = [string]$binding.logical_state_field
    $variable = [string]$binding.convene_variable
    $variableId = [string]$binding.convene_id
    $scalarType = [string]$binding.scalar_type

    if ([string]::IsNullOrWhiteSpace($field) -or
        [string]::IsNullOrWhiteSpace($variable) -or
        [string]::IsNullOrWhiteSpace($variableId)) {
        throw 'Every binding requires logical_state_field, convene_variable, and convene_id.'
    }
    if ($variable -ne "sim_$field") {
        throw "Prefix mismatch: $variable must map exactly to source field $field."
    }
    if ($variableId -notmatch '^[A-Za-z0-9_-]+$') {
        throw "Convene ID for $variable contains unsupported characters."
    }

    $property = $source.PSObject.Properties[$field]
    if ($null -eq $property) {
        throw "Required source field '$field' for $variable is absent from $SourcePath."
    }
    Assert-ScalarType -VariableName $variable -ExpectedType $scalarType -Value $property.Value

    [pscustomobject]@{
        Field = $field
        Variable = $variable
        Id = $variableId
        ScalarType = $scalarType
        Value = $property.Value
    }
}

Write-Host "Validated $($planned.Count) unique, type-safe Convene bindings for $MachineId."
Write-Host "Source: $SourcePath"
Write-Host "Backend: $($BackendBaseUrl.TrimEnd('/'))"

if ($WhatIfPreference) {
    foreach ($item in $planned) {
        $target = "$MachineId/$($item.Variable) [$($item.Id)]"
        [void]$PSCmdlet.ShouldProcess($target, 'Publish current scalar value to Convene')
    }
    return
}

$agentToken = $null
$headers = $null
$publishedCount = 0
try {
    $agentToken = Read-AgentToken
    $headers = @{ 'x-agent-token' = $agentToken }
    $base = $BackendBaseUrl.TrimEnd('/')

    foreach ($item in $planned) {
        $target = "$MachineId/$($item.Variable) [$($item.Id)]"
        if (-not $PSCmdlet.ShouldProcess($target, 'Publish current scalar value to Convene')) {
            continue
        }

        $uri = "$base/vm/$MachineId/variables/$($item.Id)/agent-value"
        $body = @{ value = $item.Value } | ConvertTo-Json -Compress
        try {
            Invoke-RestMethod -Method Post -Uri $uri -Headers $headers `
                -ContentType 'application/json' -Body $body -TimeoutSec 15 | Out-Null
        } catch {
            $statusCode = if ($_.Exception.Response) {
                [int]$_.Exception.Response.StatusCode
            } else {
                $null
            }
            if ($statusCode -in @(401, 403)) {
                throw "Convene rejected the agent credential for $base. Confirm that the token and backend came from the same installed agent."
            }
            throw
        }
        $publishedCount++
        Write-Host "Published $($item.Variable) [$($item.ScalarType)]"
        if ($DelayMilliseconds -gt 0) { Start-Sleep -Milliseconds $DelayMilliseconds }
    }

    Write-Host "Published $publishedCount of $($planned.Count) validated Convene variable bindings."
} finally {
    if ($headers) { $headers['x-agent-token'] = $null }
    $headers = $null
    $agentToken = $null
    Remove-Variable agentToken -ErrorAction SilentlyContinue
}
