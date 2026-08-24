# New Windows gateway deployment: live source and scenarios

> **Target:** replacement Windows edge-gateway laptop.
> **Rule:** deploy one exact Git commit and retain one data engine. Scenarios and
> the cRIO enter the same TCP listener; they never start a side estimator.

## Required topology

```text
cRIO or explicitly started TruthPlant scenario
  -> raw LF-delimited JSON -> 192.168.1.1:9070
  -> one RECLAIM-EdgeGateway process
       -> direct Convene /machine/publish -> gw_*
       -> durable authenticated HTTPS /ingest
  -> one production VM DualPushEngine
  -> VM state bridge + Convene agent -> sim_*
```

Never run the old 8177-8181 scenario services or the `rehearsal_*` direct
publisher as the operational scenario path. Never run a scenario while the real
cRIO/adapter owns port 9070.

## 1. Stage the exact revision

From an elevated PowerShell session on the new gateway:

```powershell
New-Item -ItemType Directory -Force C:\RECLAIM | Out-Null
Set-Location C:\RECLAIM
git clone https://github.com/lukejwaszyn/RECLAIM_LiveTwin.git source
Set-Location C:\RECLAIM\source
git fetch --tags --prune
git checkout <APPROVED_COMMIT_SHA>
git status --short
git rev-parse HEAD
```

The status must be clean and `HEAD` must equal the approved SHA. Do not deploy
from a ZIP, Downloads copy, or a moving branch tip.

Create the locked repository environment used by the scenario generator/tests:

```powershell
py -3.13 -m uv sync --locked --all-extras --dev --python 3.13
```

## 2. Stage the service directory

The Windows service uses `C:\RECLAIM\pi_gateway`; the Git checkout remains the
traceable source and scenario workspace.

```powershell
$source = 'C:\RECLAIM\source\pi_gateway'
$target = 'C:\RECLAIM\pi_gateway'
New-Item -ItemType Directory -Force $target | Out-Null
robocopy $source $target /E /PURGE /XD .venv __pycache__ .pytest_cache /XF config.windows.yaml
if ($LASTEXITCODE -gt 7) { throw "robocopy failed: $LASTEXITCODE" }

py -3.13 -m venv C:\RECLAIM\pi_gateway\.venv
& C:\RECLAIM\pi_gateway\.venv\Scripts\python.exe -m pip install `
  --requirement C:\RECLAIM\pi_gateway\requirements.txt
```

`/PURGE` applies only to the explicit service directory above. The exclusion
preserves an existing secret-bearing `config.windows.yaml` during updates. On a
new machine, create it from `config.crio-live.example.yaml`, review every
non-secret field, and do not enter a real token by hand into a console command.

## 3. Configure the isolated interface and firewall

Use the actual cRIO-facing adapter name:

```powershell
Set-Location C:\RECLAIM\source
.\pi_gateway\windows\configure-crio-network-firewall.ps1 `
  -Mode Apply -InterfaceAlias '<CRIO_ETHERNET_ALIAS>'
.\pi_gateway\windows\configure-crio-network-firewall.ps1 `
  -Mode Audit -InterfaceAlias '<CRIO_ETHERNET_ALIAS>'
```

Required state: gateway `192.168.1.1/24`, cRIO `192.168.1.2/24`, Private profile,
no default route on that adapter, TCP 9070 allowed only on the isolated link,
and no inbound exposure of loopback status port 9080.

## 4. Provision Convene and cloud ingress

Provision the desktop/SYSTEM Convene machine credential through the approved
pairing procedure. It must publish only the gateway-owned `gw_*` namespace.
Audit it without printing the credential:

```powershell
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Audit
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Validate
```

Obtain privately from the VM owner:

- current HTTPS endpoint ending exactly `/ingest`;
- the ingest token only (never the read token);
- deployed engine SHA and active freshness contract.

Finalize the deployed config; the script prompts for the token invisibly:

```powershell
.\pi_gateway\windows\finalize-gateway-config.ps1 `
  -GatewayDirectory C:\RECLAIM\pi_gateway `
  -CloudUrl 'https://<CURRENT-ENGINE-HOST>/ingest'
```

## 5. Verify and install the one gateway service

```powershell
$env:PYTHONPATH = 'C:\RECLAIM\pi_gateway'
& C:\RECLAIM\pi_gateway\.venv\Scripts\python.exe -m pytest -q `
  C:\RECLAIM\pi_gateway\tests
Remove-Item Env:PYTHONPATH

.\pi_gateway\windows\install-gateway-task.ps1 `
  -GatewayDirectory C:\RECLAIM\pi_gateway `
  -InterfaceAlias '<CRIO_ETHERNET_ALIAS>' `
  -Start
```

Verify the installed revision exposes `mode` and both fan-out counters:

```powershell
$health = Invoke-RestMethod http://127.0.0.1:9080/health
$health | ConvertTo-Json -Depth 6
Get-NetTCPConnection -State Listen -LocalPort 9070,9080
```

Required: `transport=https`, `mode=live`, `convene.enabled=true`, port 9070 bound
only as designed, and port 9080 loopback-only.

## 6. Live acceptance before the real source

The VM engine problem recorded on 2026-08-23 must be repaired first using
`CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`. Do not accept a gateway while
the cloud path final-rejects frames as `timestamp_stale`.

With the real cRIO/adapter disconnected, start a bounded nominal scenario from
the exact checkout:

```powershell
Set-Location C:\RECLAIM\source
& .\.venv\Scripts\python.exe .\tools\synthetic_crio.py `
  --scenario nominal --env earth_lab `
  --host 192.168.1.1 --port 9070 --speed 1 --max-frames 180
```

During/after the stream:

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

PASS requires received and cloud-delivered counters to advance, Convene-delivered
to advance without failures, queue depth to return to zero, no dead-letter
increase, cloud engine run/source/sequence correlation, visible advancing
`gw_*` and `sim_*`, and stale-state expiry after the stream stops. Tests alone
are not live acceptance.

After acceptance, normal scenario operation uses:

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal
```

Profiles are `nominal`, `power-outage`, `lunar`, and `loss-of-data`. The launcher
checks the gateway, refuses a real cRIO session, and feeds port 9070 at the
conservative 1 Hz shared-engine cadence.

## 7. Cut over to the real source

Stop every scenario sender and confirm no established synthetic connection.
Then connect/start exactly one approved cRIO or PSP-adapter producer. Repeat the
same counter/run/sequence/freshness checks. `/command` remains advisory and must
not connect to an actuator path.

Record the gateway source SHA, deployed service-file hashes, VM engine SHA,
Convene machine IDs, tunnel hostname, acceptance timestamps/counters, and
rollback directory. Never record tokens.
