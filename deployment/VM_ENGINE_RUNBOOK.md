# Windows Server 2025 Predictive-Engine VM Runbook

> **Stage:** VM engine, tunnel, and local state publication
> **Status:** CURRENT
> **Platform:** cloud-hosted Windows Server 2025 VM in Kubernetes-managed infrastructure

Read `DEPLOYMENT_TOPOLOGY.md` first. The Kubernetes layer hosts the Windows VM;
all guest operations below use PowerShell, Windows services, NTFS paths, and ACLs.
Do not use the retired Linux/systemd instructions preserved in Git history.

## 1. Freeze the reviewed source

Choose the reviewed PR head or merged `main` revision and record its full SHA as
`TARGET_SHA`. Deploy an exact revision into a fresh release directory:

```text
C:\ProgramData\RECLAIM\releases\<TARGET_SHA>\
```

Never overwrite a running release in place. Record the outer Kubernetes workload
or VM identity separately, without treating a pod/workload restart as an engine
state reset.

## 2. Discover before changing the VM

Run in elevated PowerShell and retain redacted output:

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
py -0p
Get-Service | Where-Object { $_.Name -match 'RECLAIM|Convene|cloudflared' }
Get-ScheduledTask | Where-Object { $_.TaskName -match 'RECLAIM|Convene|cloudflared' }
Get-NetTCPConnection -LocalPort 8078 -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'push_ingest_dual|8078|cloudflared' } |
  Select-Object ProcessId, Name, ExecutablePath, CommandLine
Get-ChildItem C:\ProgramData\RECLAIM -Force -ErrorAction SilentlyContinue
Get-ChildItem C:\ConveneAgent -Force -ErrorAction SilentlyContinue
```

Also record, without printing secret values:

- the current engine release and process/service owner;
- the process holding port 8078;
- existing Cloudflare tunnel type and hostname;
- whether engine secret and durable identity files exist and their ACLs;
- any VM Convene agent service/task and identity;
- every writer of `C:\ConveneAgent\sim_vars.json`; and
- whether the Windows VM disk paths survive Kubernetes workload rescheduling.

This VM is intentionally clean. Missing Python, `uv`, RECLAIM directories,
WinSW, cloudflared, engine/bridge services, `C:\ConveneAgent`, Convene task, and
bindings are the expected starting condition. Stop only if an unexpected
deployment, port owner, or writer exists.

## 3. Bootstrap the clean Windows VM

Run from elevated PowerShell. Install the supported toolchain when discovery
shows it is absent:

```powershell
winget install -e --id Python.Python.3.13 --scope machine `
  --accept-package-agreements --accept-source-agreements
winget install -e --id Cloudflare.cloudflared `
  --accept-package-agreements --accept-source-agreements
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + $env:Path
py -3.13 -m pip install "uv==0.11.21"
py -0p
py -3.13 -m uv --version
cloudflared --version
New-Item -ItemType Directory -Force C:\ProgramData\RECLAIM\releases | Out-Null
```

Obtain the reviewed WinSW 3.x executable from its official release channel and
record its version and `Get-FileHash -Algorithm SHA256` result. The executable is
an expected external prerequisite; do not commit it.

Install the Convene-provided, VM-specific agent in headless mode. The installer
for `reclaim-engine-2` contains its own VM token and **does not use a pairing
code**. Treat that script as a credential: verify its source/hash locally, never
commit it, and use process-scoped execution-policy bypass rather than changing
machine policy:

```powershell
Get-FileHash -Algorithm SHA256 'C:\path\to\convene-agent-reclaim-engine-2.ps1'
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File 'C:\path\to\convene-agent-reclaim-engine-2.ps1'
.\deployment\windows-vm\Register-ConveneAgentTask.ps1
Get-ScheduledTask -TaskName ConveneAgent
Get-ChildItem C:\ConveneAgent -Force
```

The final task runs as SYSTEM, remains headless, and sends the JSON object in
`sim_vars.json` as heartbeat `simVars`. Record the machine registration without
printing its embedded credential. The older pairing-based bootstrap remains a
reference for other deployments, not this VM's installation path.

## 4. Stage and verify the exact release

Copy or check out the exact source under the release path, then verify:

```powershell
Set-Location "C:\ProgramData\RECLAIM\releases\$env:TARGET_SHA"
git rev-parse HEAD
git status --short
$env:UV_CACHE_DIR = 'C:\ProgramData\RECLAIM\uv-cache'
py -3.13 -m uv sync --frozen --all-extras --dev --python 3.13
Push-Location cloud_engine
..\.venv\Scripts\python.exe -c "import numpy, scipy, sklearn; from scipy.stats import chi2; import push_ingest_dual; print('imports OK')"
Pop-Location
```

The printed SHA must equal `TARGET_SHA`. Python 3.11 through 3.13 is supported by
`pyproject.toml`; record the exact interpreter used.

Run the locked local gates before installing a service:

```powershell
$env:PYTHONPATH = 'cloud_engine;pi_gateway'
py -3.13 -m uv run --frozen pytest -q convene_bridge/tests
py -3.13 -m uv run --frozen pytest -q cloud_engine/tests pi_gateway/tests
py -3.13 -m uv run --frozen python scripts/check_repository_hygiene.py
Remove-Item Env:PYTHONPATH
```

## 5. Create Windows state, secret, and log directories

```powershell
$EngineRoot = 'C:\ProgramData\RECLAIM\engine'
$ServiceAccount = 'NT AUTHORITY\LocalService'
New-Item -ItemType Directory -Force `
  "$EngineRoot\config", "$EngineRoot\secrets", "$EngineRoot\state", `
  "$EngineRoot\logs", "$EngineRoot\service" | Out-Null
```

Use distinct high-entropy ingest and read credentials. Write them locally to:

```text
C:\ProgramData\RECLAIM\engine\secrets\reclaim-ingest.env
```

The file format is:

```text
RECLAIM_INGEST_TOKEN=<private value>
RECLAIM_READ_TOKEN=<different private value>
```

Never pass either token in a command-line argument, paste it into a transcript, or
store it in WinSW XML. Apply explicit ACLs:

```powershell
icacls "$EngineRoot\secrets\reclaim-ingest.env" /inheritance:r /grant:r `
  'SYSTEM:(F)' 'BUILTIN\Administrators:(F)' "${ServiceAccount}:(R)"
icacls "$EngineRoot\state" /inheritance:r /grant:r `
  'SYSTEM:(OI)(CI)(F)' 'BUILTIN\Administrators:(OI)(CI)(F)' `
  "${ServiceAccount}:(OI)(CI)(M)"
icacls "$EngineRoot\logs" /inheritance:r /grant:r `
  'SYSTEM:(OI)(CI)(F)' 'BUILTIN\Administrators:(OI)(CI)(F)' `
  "${ServiceAccount}:(OI)(CI)(M)"
```

The durable identity path is:

```text
C:\ProgramData\RECLAIM\engine\state\ingest_state.json
```

The Kubernetes/VM storage owner must confirm this path survives the required VM
recovery and rescheduling scenarios.

## 6. Install the engine as a Windows service

Use an operator-approved WinSW 3.x binary. Verify its official release provenance
and SHA-256; do not commit the executable.

Copy these repository files into `$EngineRoot\service`:

- `cloud_engine\windows\run-ingest-engine.ps1`
- `cloud_engine\windows\reclaim-ingest.xml`

Copy the approved binary as `reclaim-ingest.exe`. Replace the XML placeholders:

| Placeholder | Value |
|---|---|
| `{{RUNNER_PATH}}` | `$EngineRoot\service\run-ingest-engine.ps1` |
| `{{PYTHON_EXE}}` | `<release>\.venv\Scripts\python.exe` |
| `{{ENGINE_DIR}}` | `<release>\cloud_engine` |
| `{{SECRET_FILE}}` | `$EngineRoot\secrets\reclaim-ingest.env` |
| `{{STATE_FILE}}` | `$EngineRoot\state\ingest_state.json` |
| `{{LOG_DIR}}` | `$EngineRoot\logs` |
| `{{SERVICE_ACCOUNT}}` | reviewed Windows service identity |

The wrapper reads secrets from the ACL-protected file into the child environment;
the WinSW command line and XML remain non-secret. It starts exactly:

```text
push_ingest_dual.py --host 127.0.0.1 --port 8078 --env earth_lab --production --max-frame-age-s 15
```

Install but do not start until paths, XML, account, and ACLs have been reviewed:

```powershell
Set-Location "$EngineRoot\service"
.\reclaim-ingest.exe install
Get-Service RECLAIMIngestEngine
Start-Service RECLAIMIngestEngine
```

## 7. Verify the loopback engine

```powershell
Get-Service RECLAIMIngestEngine
Get-NetTCPConnection -LocalPort 8078
Invoke-RestMethod http://127.0.0.1:8078/health
```

Port 8078 must listen only on loopback. Load the read credential into a local
PowerShell variable without printing it, then verify `/state` rejects an absent or
wrong credential and accepts the correct bearer header. Never capture the header in
screenshots or logs.

Confirm the WinSW logs contain no credentials and that a service restart preserves
`ingest_state.json` identity/deduplication state.

## 8. Establish the Cloudflare route

Use the Windows cloudflared installed during bootstrap. Preserve an unexpected
named tunnel if discovery found one. For the demonstration, a foreground quick
tunnel is an acceptable temporary route:

```powershell
.\deployment\windows-vm\Get-ReclaimPredictiveVmInventory.ps1
.\deployment\windows-vm\Start-ReclaimQuickTunnel.ps1 -Mode Audit
.\deployment\windows-vm\Start-ReclaimQuickTunnel.ps1 -Mode Run
```

Its hostname is ephemeral and bearer credentials are the only application-layer
protection. A named tunnel with an approved DNS name and Access policy is preferred
for durable interoperability. Never route synthetic ports 8177–8181.
The launcher refuses a competing cloudflared service/process or existing
configuration, saves the generated base URL to
`C:\ProgramData\RECLAIM\cloudflared-quick\public-url.txt`, and prints the exact
gateway `cloud_url` ending in `/ingest`. It never reads credentials or touches the
Convene bridge/agent.

## 9. Run endpoint acceptance

From a trusted workstation, load credentials into environment variables rather
than process arguments:

```powershell
$env:RECLAIM_INGEST_TOKEN = '<private value>'
$env:RECLAIM_READ_TOKEN = '<different private value>'
python cloud_engine\tools\redteam_ingest.py --url https://<engine-host>
Remove-Item Env:RECLAIM_INGEST_TOKEN, Env:RECLAIM_READ_TOKEN
```

Required result: all 20 checks pass. Restart `RECLAIMIngestEngine` and verify the
last accepted frame remains a duplicate and fresh telemetry continues with durable
identity intact.

On the VM, the proven credential-safe wrapper performs both checks:

```powershell
.\deployment\windows-vm\Test-EnginePublicAcceptance.ps1 `
  -PublicUrl 'https://<approved-engine-origin>'
```

## 10. Install and accept the Convene state bridge

Follow `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`. The bridge is a separate
Windows service, uses only the read token, reads only loopback `/state`, and writes
the installed VM agent's `sim_vars.json` atomically. The expected Convene agent
identity is `NT AUTHORITY\SYSTEM`; verify the scheduled-task principal rather than
assuming it.

Convene acceptance must prove:

- prefix behavior using a harmless bridge metadata field;
- exactly one `sim_` writer;
- mode/status/freshness/data-live gating;
- independent expiration of `bridge_valid_until`; and
- no unintended change to the installed VM Convene agent or `/command` authority.

Tuesday integration is `PASS` only after the acceptance telemetry that entered
through the public Cloudflare route is correlated by run/source/sequence through
`/state`, the bridge file, the installed VM agent, and visible Convene `sim_`
fields. Stop the source and prove the Convene view becomes `DATA NOT LIVE` after
freshness/lease expiry. Ingress plus local `/state` without Convene evidence is
`PARTIAL`, not `PASS`.

The 2026-08-19 proof and mission-display variable decision are recorded in
`CONVENE_MISSION_OPERATIONS_RECAP.md`. Bind sensed variables by their
Convene-generated IDs; names alone are not a sufficient binding record.

## 11. Gateway handoff

Send the Windows 10 gateway operator, through an approved private channel:

- `https://<engine-host>/ingest`;
- ingest token only;
- full engine source SHA;
- 15-second maximum frame age; and
- planned availability window.

Do not send the read token unless a separately reviewed gateway function requires
it. ACL-lock the gateway configuration after inserting its credential.

## 12. Isolated rehearsal profiles

The synthetic nominal, power-outage, and lunar demonstrations are separate
GET-only services. They do not use port 8078, production credentials, the
production state bridge, or live `sim_`/`gw_` bindings. Start one per foreground
PowerShell terminal from the release root:

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal
.\cloud_engine\windows\start-rehearsal-scenario.ps1 power-outage
.\cloud_engine\windows\start-rehearsal-scenario.ps1 lunar
```

The profiles use ports 8177, 8178, 8179, and 8181 (`loss-of-data`) respectively. Verify their explicit
`mode`, `scenario`, `environment`, and `speed` through `/health`; use `/history`
to capture brief outage/restart transitions. Bind only to the isolated rehearsal
identities in `CONVENE_REINTEGRATION_HANDOFF.md`.

## Rollback

Stop and uninstall only `RECLAIMIngestEngine`, return the tunnel to its prior
configuration, and preserve the previous release, secret, durable identity, logs,
and unexpected services. Do not delete Kubernetes storage or VM disks as part of a
guest-service rollback. The bridge and installed Convene agent have separate rollback
procedures.

## Stop conditions

Stop rather than improvise if the selected SHA is not exact, port 8078 has an
unknown owner, the engine binds beyond loopback, tokens appear in command lines or
logs, durable state is not persistent, the tunnel routes an unintended port,
Convene remains live after lease expiry, another process writes `sim_vars.json`, or
any advisory output is connected to hardware control authority.
