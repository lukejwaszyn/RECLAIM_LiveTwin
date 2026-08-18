[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [string]$WinSWPath,
    [Parameter(Mandatory = $true)]
    [string]$WinSWSha256,
    [Parameter(Mandatory = $true)]
    [string]$ConveneAgentIdentity,
    [string]$InstallRoot = "C:\ProgramData\RECLAIM\convene-bridge",
    [string]$OutputPath = "C:\ConveneAgent\sim_vars.json",
    [string]$ServiceAccount = "NT AUTHORITY\LocalService",
    [switch]$StartService
)

$ErrorActionPreference = "Stop"
$ServiceId = "RECLAIMStateBridge"
$MarkerName = ".reclaim-state-bridge-owned.json"
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
$WinSWPath = [IO.Path]::GetFullPath($WinSWPath)
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$MarkerPath = Join-Path $InstallRoot $MarkerName
$ServiceExe = Join-Path $InstallRoot "service\reclaim-state-bridge.exe"
$ServiceXml = Join-Path $InstallRoot "service\reclaim-state-bridge.xml"
$ConfigPath = Join-Path $InstallRoot "config\bridge.yaml"
$SecretPath = Join-Path $InstallRoot "secrets\read-token.txt"
$AppDir = Join-Path $InstallRoot "app"
$PythonExe = Join-Path $InstallRoot "venv\Scripts\python.exe"

function Show-Discovery {
    Write-Host "Discovery only; no changes have occurred:"
    Write-Host "  install root: $InstallRoot exists=$([bool](Test-Path $InstallRoot))"
    Write-Host "  output:       $OutputPath exists=$([bool](Test-Path $OutputPath))"
    if (Test-Path $InstallRoot) {
        Get-ChildItem $InstallRoot -Force | Select-Object Name, FullName, Attributes |
            Format-Table | Out-Host
    }
    $services = Get-CimInstance Win32_Service | Where-Object {
        $_.Name -eq $ServiceId -or $_.PathName -like "*$InstallRoot*"
    }
    $services | Select-Object Name, State, StartName, PathName | Format-Table | Out-Host
    Get-ScheduledTask | Where-Object {
        $_.TaskName -match "Convene|RECLAIM" -or $_.TaskPath -match "Convene|RECLAIM"
    } | Select-Object TaskName, TaskPath, State | Format-Table | Out-Host
    foreach ($path in @($InstallRoot, (Split-Path $OutputPath -Parent), $OutputPath)) {
        if (Test-Path $path) {
            Write-Host "  ACL: $path"
            (Get-Acl $path).Access | Format-Table IdentityReference, FileSystemRights, AccessControlType, IsInherited | Out-Host
        }
    }
}

Show-Discovery

$ExistingService = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue
$WasRunning = $ExistingService -and $ExistingService.Status -eq "Running"
if ((Test-Path $InstallRoot) -and -not (Test-Path $MarkerPath)) {
    throw "Unexpected deployment at $InstallRoot has no ownership marker. Preserve it and obtain operator direction."
}
if ($ExistingService -and -not (Test-Path $MarkerPath)) {
    throw "Service $ServiceId exists without this installer's ownership marker. No changes made."
}
if (-not (Test-Path $RepositoryRoot)) { throw "Repository root not found: $RepositoryRoot" }
$SourcePackage = Join-Path $RepositoryRoot "convene_bridge"
if (-not (Test-Path (Join-Path $SourcePackage "state_bridge.py"))) {
    throw "convene_bridge source package not found under $RepositoryRoot"
}
if (-not (Test-Path $WinSWPath -PathType Leaf)) { throw "Approved WinSW binary not found: $WinSWPath" }
$ActualHash = (Get-FileHash -Algorithm SHA256 $WinSWPath).Hash
if ($ActualHash -ne $WinSWSha256.ToUpperInvariant()) {
    throw "WinSW SHA-256 mismatch. Expected $WinSWSha256; no files changed."
}
if ([string]::IsNullOrWhiteSpace($ConveneAgentIdentity)) {
    throw "ConveneAgentIdentity is required so sim_vars.json receives an explicit read ACL."
}

if (-not $PSCmdlet.ShouldProcess($InstallRoot, "Install RECLAIM state bridge")) { return }

$Directories = @("app", "config", "secrets", "state", "logs", "service", "venv") |
    ForEach-Object { Join-Path $InstallRoot $_ }
foreach ($directory in $Directories) {
    New-Item -ItemType Directory -Force $directory | Out-Null
}

if (-not (Test-Path $MarkerPath)) {
    @{
        schema = "reclaim.convene-bridge.install.v1"
        service_id = $ServiceId
        install_root = $InstallRoot
        output_path = $OutputPath
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $MarkerPath
}

if ($ExistingService -and $ExistingService.Status -ne "Stopped") {
    Stop-Service -Name $ServiceId
    (Get-Service -Name $ServiceId).WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
}

Remove-Item -Recurse -Force (Join-Path $AppDir "convene_bridge") -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force $SourcePackage (Join-Path $AppDir "convene_bridge")
Copy-Item -Force $WinSWPath $ServiceExe

if (-not (Test-Path $PythonExe)) {
    $SystemPython = (Get-Command python.exe -ErrorAction Stop).Source
    & $SystemPython -m venv (Join-Path $InstallRoot "venv")
    if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed" }
}
& $PythonExe -m pip install --disable-pip-version-check "PyYAML==6.0.3"
if ($LASTEXITCODE -ne 0) { throw "PyYAML installation failed; service was not installed" }

if (-not (Test-Path $ConfigPath)) {
    Copy-Item (Join-Path $SourcePackage "config.example.yaml") $ConfigPath
}
if (-not (Test-Path $SecretPath)) {
    New-Item -ItemType File $SecretPath | Out-Null
}
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Force (Split-Path $OutputPath -Parent) | Out-Null
    '{"data_live":false,"bridge_status":"starting","bridge_error_code":"INSTALL_NOT_CONFIGURED"}' |
        Set-Content -Encoding UTF8 $OutputPath
}

$XmlTemplate = Get-Content -Raw (Join-Path $SourcePackage "windows\reclaim-state-bridge.xml")
$Xml = $XmlTemplate.Replace("{{PYTHON_EXE}}", $PythonExe)
$Xml = $Xml.Replace("{{CONFIG_PATH}}", $ConfigPath)
$Xml = $Xml.Replace("{{APP_DIR}}", $AppDir)
$Xml = $Xml.Replace("{{SERVICE_ACCOUNT}}", $ServiceAccount)
$Xml | Set-Content -Encoding UTF8 $ServiceXml

$AclBackup = Join-Path $InstallRoot "state\sim_vars.acl.xml"
if (-not (Test-Path $AclBackup)) { Get-Acl $OutputPath | Export-Clixml $AclBackup }

& icacls.exe $InstallRoot /inheritance:r /grant:r `
    "SYSTEM:(OI)(CI)(F)" "BUILTIN\Administrators:(OI)(CI)(F)" "${ServiceAccount}:(OI)(CI)(RX)" | Out-Null
& icacls.exe (Join-Path $InstallRoot "logs") /grant:r "${ServiceAccount}:(OI)(CI)(M)" | Out-Null
& icacls.exe (Join-Path $InstallRoot "state") /grant:r "${ServiceAccount}:(OI)(CI)(M)" | Out-Null
& icacls.exe $SecretPath /inheritance:r /grant:r `
    "SYSTEM:(F)" "BUILTIN\Administrators:(F)" "${ServiceAccount}:(R)" | Out-Null
& icacls.exe $ConfigPath /inheritance:r /grant:r `
    "SYSTEM:(F)" "BUILTIN\Administrators:(F)" "${ServiceAccount}:(R)" | Out-Null
& icacls.exe $OutputPath /inheritance:r /grant:r `
    "SYSTEM:(F)" "BUILTIN\Administrators:(F)" "${ServiceAccount}:(M)" "${ConveneAgentIdentity}:(R)" | Out-Null

if (-not $ExistingService) {
    & $ServiceExe install
    if ($LASTEXITCODE -ne 0) { throw "WinSW service installation failed" }
}

Write-Host "Bridge installed but no credential was requested or printed."
Write-Host "Edit $ConfigPath, place the read token in $SecretPath using a secure local method, then verify ACLs."
if ($StartService -or $WasRunning) {
    if ((Get-Item $SecretPath).Length -eq 0) {
        throw "Refusing to start: read-token file is empty"
    }
    Start-Service -Name $ServiceId
}
Write-Host "Existing Convene tasks were discovered only and were not modified."
