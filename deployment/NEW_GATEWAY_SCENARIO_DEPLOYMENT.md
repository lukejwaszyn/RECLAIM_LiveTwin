# MacBook scenario-host deployment

> Windows 10 remains the sole live-data client/gateway. This procedure deploys
> only the MacBook scenario service.

## Configure

```text
cRIO or explicitly started TruthPlant scenario
  -> raw LF-delimited JSON -> 192.168.1.1:9070
  -> one RECLAIM-EdgeGateway process
       -> direct Convene /machine/publish -> exact raw PL_*/MT_*/MW_* names
       -> durable authenticated HTTPS /ingest
  -> one production VM DualPushEngine
  -> VM state bridge + Convene agent -> sim_*
```

Confirm `src=reclaim-macbook-scenario-01`, `mode=harness`, `transport=console`,
and no cloud token. Confirm ports 9070 and 9080 listen only on loopback.

## Run generated scenarios

```bash
pi_gateway/macos/start-rehearsal-scenario.sh nominal
pi_gateway/macos/start-rehearsal-scenario.sh power-outage
pi_gateway/macos/start-rehearsal-scenario.sh lunar
pi_gateway/macos/start-rehearsal-scenario.sh loss-of-data
```

## Replay a capture

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" --max-frames 100 --speed 10
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
raw source names and `sim_*`, and stale-state expiry after the stream stops. Tests alone
are not live acceptance.

After acceptance, normal scenario operation uses:

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal
```

Profiles are `nominal`, `power-outage`, `lunar`, and `loss-of-data`. The launcher
checks the gateway, refuses a real cRIO session, and feeds port 9070 at the
conservative 1 Hz shared-engine cadence.

## 7. Cut over to the real source

## Accept

Require matching receive/deliver counts, zero queue depth, drops, dead letters,
and Convene failures, plus a scenario-labeled `/latest` frame. Never change the
MacBook to `mode=live`, a non-loopback listener, or direct cloud transport.
