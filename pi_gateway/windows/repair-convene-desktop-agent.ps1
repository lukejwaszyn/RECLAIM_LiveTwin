#Requires -RunAsAdministrator
<#
.SYNOPSIS
Audits or repairs the RECLAIM desktop Convene agent credential handoff.

.DESCRIPTION
The desktop Convene agent runs at boot as SYSTEM, so it reads a different
credential file than an interactive pairing. This script compares those two
desktop credentials without printing either token.

Repair validates the newer user-profile pairing with one minimal heartbeat,
backs up the SYSTEM credential, copies that already-created desktop identity to
the SYSTEM profile, and restarts the existing Convene-Agent task. It does not
create a machine, change a backend, configure VM bindings, create variables, or
publish raw gateway or sim_ values.

.EXAMPLE
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Audit

.EXAMPLE
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Validate

.EXAMPLE
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Repair

.EXAMPLE
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Repair -AllowDegradedHeartbeat

.EXAMPLE
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode RePair
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [ValidateSet('Audit', 'Validate', 'Repair', 'RePair')]
    [string]$Mode = 'Audit',

    [Security.SecureString]$PairingCode,

    [switch]$AllowDegradedHeartbeat,

    [string]$AgentPath = 'C:\Users\latitude4\.convene\convene_agent.py',

    [string]$RunnerPath = 'C:\Users\latitude4\.convene\run-agent.cmd',

    [string]$UserCredentialPath = 'C:\Users\latitude4\.convene_agent.json',

    [string]$SystemCredentialPath = 'C:\Windows\System32\config\systemprofile\.convene_agent.json',

    [string]$TaskName = 'Convene-Agent'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-AgentCredential {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Convene credential not found: $Path"
    }
    $raw = Get-Content -LiteralPath $Path -Raw
    $value = $raw | ConvertFrom-Json
    if (-not $value.machineId -or -not $value.agentToken) {
        throw "Convene credential must contain machineId and agentToken: $Path"
    }
    [pscustomobject]@{
        Path = $Path
        Raw = $raw
        MachineId = [string]$value.machineId
        AgentToken = [string]$value.agentToken
        LastWriteTimeUtc = (Get-Item -LiteralPath $Path).LastWriteTimeUtc.ToString('o')
    }
}

function Read-AgentBackend {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Installed Convene agent not found: $Path"
    }
    $text = Get-Content -LiteralPath $Path -Raw
    $match = [regex]::Match(
        $text,
        '(?m)^BACKEND\s*=\s*["''](?<url>https://[^"'']+/api)/?["'']\s*$'
    )
    if (-not $match.Success) {
        throw "Could not identify the desktop BACKEND assignment in $Path"
    }
    $uri = [Uri]$match.Groups['url'].Value
    if ($uri.Scheme -ne 'https' -or $uri.AbsolutePath.TrimEnd('/') -ne '/api') {
        throw "Installed desktop Convene backend is not an HTTPS /api URL: $uri"
    }
    return $uri.AbsoluteUri.TrimEnd('/')
}

function Test-AgentCredential {
    param(
        [Parameter(Mandatory)][string]$Backend,
        [Parameter(Mandatory)][string]$Token
    )

    try {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem
        $processors = @(Get-CimInstance -ClassName Win32_Processor)
        $systemDrive = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'"
        $cpuAverage = ($processors | Measure-Object -Property LoadPercentage -Average).Average
        $memoryPercent = if ([double]$os.TotalVisibleMemorySize -gt 0) {
            100.0 * (1.0 - ([double]$os.FreePhysicalMemory / [double]$os.TotalVisibleMemorySize))
        }
        else { 0.0 }
        $diskPercent = if ($systemDrive -and [double]$systemDrive.Size -gt 0) {
            100.0 * (1.0 - ([double]$systemDrive.FreeSpace / [double]$systemDrive.Size))
        }
        else { 0.0 }
        $uptime = [Math]::Max(
            1,
            [int]((Get-Date).ToUniversalTime() - $os.LastBootUpTime.ToUniversalTime()).TotalSeconds
        )
        $body = @{
            cpuPercent = [double]$cpuAverage
            memoryPercent = [Math]::Round($memoryPercent, 1)
            diskPercent = [Math]::Round($diskPercent, 1)
            uptime = $uptime
        } | ConvertTo-Json -Compress
    }
    catch {
        throw "Could not collect the installed agent's heartbeat statistics: $($_.Exception.Message)"
    }
    try {
        $response = Invoke-RestMethod -Method Post `
            -Uri "$Backend/machine/heartbeat" `
            -Headers @{ 'X-Agent-Token' = $Token } `
            -ContentType 'application/json' `
            -Body $body `
            -TimeoutSec 15
        $autoVarsProperty = $response.PSObject.Properties['autoVars']
        return [pscustomobject]@{
            Accepted = $true
            StatusCode = 200
            AutoVariableCount = if ($autoVarsProperty) { @($autoVarsProperty.Value).Count } else { 0 }
            FailureKind = $null
            Error = $null
        }
    }
    catch {
        $status = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        $serverDetail = [string]$_.ErrorDetails.Message
        $failureKind = if ($serverDetail -match 'FAILED_PRECONDITION:\s*The query requires an index') {
            'MissingFirestoreIndex'
        }
        elseif ($status -in 401, 403) {
            'CredentialRejected'
        }
        elseif ($status -ge 500) {
            'BackendServerError'
        }
        else {
            'RequestFailed'
        }
        return [pscustomobject]@{
            Accepted = $false
            StatusCode = $status
            AutoVariableCount = $null
            FailureKind = $failureKind
            Error = if ($status) { "HTTP $status" } else { $_.Exception.Message }
        }
    }
}

function New-DesktopPairing {
    param(
        [Parameter(Mandatory)][string]$Backend,
        [Parameter(Mandatory)][Security.SecureString]$Code
    )

    $codePointer = [IntPtr]::Zero
    try {
        $codePointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Code)
        $plainCode = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($codePointer)
        $payload = @{
            pairingCode = $plainCode
            name = $env:COMPUTERNAME
            hostname = $env:COMPUTERNAME
            os = 'windows'
            arch = if ($env:PROCESSOR_ARCHITECTURE) { $env:PROCESSOR_ARCHITECTURE } else { 'unknown' }
            agentVersion = '1.1.0'
        } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -Method Post `
            -Uri "$Backend/machine/pair" `
            -ContentType 'application/json' `
            -Body $payload `
            -TimeoutSec 15
        if (-not $response.machineId -or -not $response.agentToken) {
            throw 'Pairing response did not contain machineId and agentToken.'
        }
        return [pscustomobject]@{
            MachineId = [string]$response.machineId
            AgentToken = [string]$response.agentToken
            Raw = $response | ConvertTo-Json -Compress
        }
    }
    finally {
        if ($codePointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($codePointer)
        }
        $plainCode = $null
        $payload = $null
    }
}

$backend = Read-AgentBackend -Path $AgentPath
$userCredential = Read-AgentCredential -Path $UserCredentialPath
$systemCredential = Read-AgentCredential -Path $SystemCredentialPath
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
$expectedRunner = [IO.Path]::GetFullPath($RunnerPath)
$actionText = ($task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join "`n"
if ($actionText -notlike "*$expectedRunner*") {
    throw "Scheduled task '$TaskName' does not launch the expected desktop runner: $RunnerPath"
}

$report = [ordered]@{
    CapturedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    Mode = $Mode
    DesktopBackend = $backend
    UserProfileMachineId = $userCredential.MachineId
    UserCredentialLastWriteUtc = $userCredential.LastWriteTimeUtc
    SystemProfileMachineId = $systemCredential.MachineId
    SystemCredentialLastWriteUtc = $systemCredential.LastWriteTimeUtc
    CredentialIdentityDiverged = ($userCredential.MachineId -ne $systemCredential.MachineId)
    TaskName = $TaskName
    TaskState = $task.State.ToString()
    LastTaskResult = $taskInfo.LastTaskResult
    UserPairingValidation = $null
    SystemPairingValidation = $null
    NewMachineId = $null
    NewPairingValidation = $null
    HeartbeatDegraded = $false
    Changed = $false
}

if ($Mode -eq 'Audit') {
    [pscustomobject]$report | ConvertTo-Json -Depth 4
    return
}

if ($Mode -eq 'Validate') {
    $report.UserPairingValidation = Test-AgentCredential `
        -Backend $backend -Token $userCredential.AgentToken
    $report.SystemPairingValidation = Test-AgentCredential `
        -Backend $backend -Token $systemCredential.AgentToken
    [pscustomobject]$report | ConvertTo-Json -Depth 4
    return
}

if ($Mode -eq 'RePair') {
    if (-not $PairingCode) {
        $PairingCode = Read-Host 'Enter the new desktop Convene pairing code' -AsSecureString
    }
    if (-not $PSCmdlet.ShouldProcess(
            "desktop backend $backend and scheduled task '$TaskName'",
            'Create one new desktop machine, persist its credential for user and SYSTEM, and restart agent'
        )) {
        [pscustomobject]$report | ConvertTo-Json -Depth 4
        return
    }

    $newPairing = New-DesktopPairing -Backend $backend -Code $PairingCode
    $report.NewMachineId = $newPairing.MachineId
    $newValidation = Test-AgentCredential -Backend $backend -Token $newPairing.AgentToken
    $report.NewPairingValidation = $newValidation
    if (-not $newValidation.Accepted) {
        if ($AllowDegradedHeartbeat -and
            $newValidation.FailureKind -eq 'MissingFirestoreIndex') {
            # A successful /pair response is authoritative for the new token.
            # Convene can register/show the machine before its heartbeat response
            # path fails. Persist the token so it is not lost and the agent can
            # recover automatically when the backend-side fault clears.
            $report.HeartbeatDegraded = $true
            Write-Warning "Convene created desktop machine '$($newPairing.MachineId)' but heartbeat returned $($newValidation.Error). Persisting the valid pairing; raw gateway autoVars remain unverified until heartbeat returns HTTP 200."
        }
        else {
            [pscustomobject]$report | ConvertTo-Json -Depth 4
            throw "The backend created desktop machine '$($newPairing.MachineId)' but rejected its first heartbeat ($($newValidation.Error)). Credentials and task were not changed."
        }
    }

    $stamp = Get-Date -Format 'yyyyMMddTHHmmss'
    $userBackupPath = "$UserCredentialPath.before-desktop-repair-$stamp.bak"
    $systemBackupPath = "$SystemCredentialPath.before-desktop-repair-$stamp.bak"
    Copy-Item -LiteralPath $UserCredentialPath -Destination $userBackupPath
    Copy-Item -LiteralPath $SystemCredentialPath -Destination $systemBackupPath
    try {
        $utf8NoBom = [Text.UTF8Encoding]::new($false)
        [IO.File]::WriteAllText($UserCredentialPath, $newPairing.Raw, $utf8NoBom)
        [IO.File]::WriteAllText($SystemCredentialPath, $newPairing.Raw, $utf8NoBom)
        $writtenUser = Read-AgentCredential -Path $UserCredentialPath
        $writtenSystem = Read-AgentCredential -Path $SystemCredentialPath
        if ($writtenUser.MachineId -ne $newPairing.MachineId -or
            $writtenSystem.MachineId -ne $newPairing.MachineId) {
            throw 'Post-write machine identity verification failed.'
        }
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 3
        $report.UserProfileMachineId = $writtenUser.MachineId
        $report.UserCredentialLastWriteUtc = $writtenUser.LastWriteTimeUtc
        $report.SystemProfileMachineId = $writtenSystem.MachineId
        $report.SystemCredentialLastWriteUtc = $writtenSystem.LastWriteTimeUtc
        $report.CredentialIdentityDiverged = $false
        $report.Changed = $true
        $report.UserCredentialBackupPath = $userBackupPath
        $report.SystemCredentialBackupPath = $systemBackupPath
        $report.TaskState = (Get-ScheduledTask -TaskName $TaskName).State.ToString()
        $report.LastTaskResult = (Get-ScheduledTaskInfo -TaskName $TaskName).LastTaskResult
    }
    catch {
        Copy-Item -LiteralPath $userBackupPath -Destination $UserCredentialPath -Force
        Copy-Item -LiteralPath $systemBackupPath -Destination $SystemCredentialPath -Force
        Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        throw "Desktop re-pair persistence failed and both prior credentials were restored: $($_.Exception.Message)"
    }
    [pscustomobject]$report | ConvertTo-Json -Depth 4
    return
}

if ($userCredential.MachineId -eq $systemCredential.MachineId) {
    Write-Host "The interactive and SYSTEM profiles already use desktop machine $($userCredential.MachineId)."
    [pscustomobject]$report | ConvertTo-Json -Depth 4
    return
}

$validation = Test-AgentCredential -Backend $backend -Token $userCredential.AgentToken
$report.UserPairingValidation = $validation
if (-not $validation.Accepted) {
    if ($AllowDegradedHeartbeat -and
        $validation.FailureKind -eq 'MissingFirestoreIndex') {
        $report.HeartbeatDegraded = $true
        Write-Warning "Persisting existing desktop machine '$($userCredential.MachineId)' despite the known Convene MissingFirestoreIndex fault. It can remain visible, but raw gateway autoVars cannot operate until that backend index exists."
    }
    else {
    [pscustomobject]$report | ConvertTo-Json -Depth 4
    $classification = if ($validation.StatusCode -in 401, 403) {
        'rejected the credential'
    }
    elseif ($validation.StatusCode -ge 500) {
        'failed while processing the authenticated machine record'
    }
    else {
        'did not accept the heartbeat'
    }
    throw "The installed desktop backend $classification ($($validation.Error)). No credential or task was changed."
    }
}

$backupPath = "$SystemCredentialPath.before-desktop-rebind-$(Get-Date -Format 'yyyyMMddTHHmmss').bak"
if ($PSCmdlet.ShouldProcess(
        "$SystemCredentialPath and scheduled task '$TaskName'",
        "Persist existing desktop machine $($userCredential.MachineId) for SYSTEM and restart agent"
    )) {
    Copy-Item -LiteralPath $SystemCredentialPath -Destination $backupPath
    try {
        # Overwrite content in place so the existing protected SYSTEM-file ACL remains.
        [IO.File]::WriteAllText($SystemCredentialPath, $userCredential.Raw, [Text.UTF8Encoding]::new($false))
        $written = Read-AgentCredential -Path $SystemCredentialPath
        if ($written.MachineId -ne $userCredential.MachineId) {
            throw 'Post-write machine identity verification failed.'
        }
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 3
        $report.SystemProfileMachineId = $written.MachineId
        $report.SystemCredentialLastWriteUtc = $written.LastWriteTimeUtc
        $report.CredentialIdentityDiverged = $false
        $report.Changed = $true
        $report.BackupPath = $backupPath
        $report.TaskState = (Get-ScheduledTask -TaskName $TaskName).State.ToString()
        $report.LastTaskResult = (Get-ScheduledTaskInfo -TaskName $TaskName).LastTaskResult
    }
    catch {
        Copy-Item -LiteralPath $backupPath -Destination $SystemCredentialPath -Force
        Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        throw "Desktop Convene repair failed and the SYSTEM credential was restored: $($_.Exception.Message)"
    }
}

[pscustomobject]$report | ConvertTo-Json -Depth 4
