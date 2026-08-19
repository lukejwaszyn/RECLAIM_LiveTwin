# RECLAIM Windows Gateway Closeout

This directory contains the guarded desktop-side workflow for the Windows 10
edge gateway. `pi_gateway` is a legacy directory name; no Raspberry Pi is in the
live path.

## Fixed topology

```text
cRIO 192.168.1.2
  -> TCP 192.168.1.1:9070
Windows 10 gateway
  -> durable SQLite queue
  -> authenticated HTTPS /ingest through the VM Cloudflare hostname
Windows Server 2025 predictive-engine VM

Independent audit tap:
gateway http://127.0.0.1:9080/latest
  -> desktop Convene-Agent autoVars
  -> gw_ variables only
```

The desktop Convene agent never writes `sim_`. The VM is the only `sim_`
publisher. Neither path authorizes command actuation.

## 1. Direct cRIO network

Already applied on this desktop:

- Ethernet: `192.168.1.1/24`, Private, no default route.
- cRIO peer: `192.168.1.2/24`.
- Inbound TCP 9070 is allowed only from `192.168.1.2` on Ethernet.
- TCP 9080 is not exposed; status remains loopback-only.

Re-audit or idempotently reapply from elevated PowerShell:

```powershell
.\pi_gateway\windows\configure-crio-network-firewall.ps1 -Mode Audit
.\pi_gateway\windows\configure-crio-network-firewall.ps1 -Mode Apply
```

Configure the cRIO/LabVIEW sender to `192.168.1.1:9070`. Do not add a gateway to
the cRIO-facing Ethernet interface.

## 2. Desktop Convene identity and `gw_` audit tap

Use the desktop-only tool; it does not inspect or change VM bindings:

```powershell
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Audit
.\pi_gateway\windows\repair-convene-desktop-agent.ps1 -Mode Validate
```

As of 2026-08-19, the Convene backend updates machine presence but then returns
HTTP 500 because its Firestore project lacks the composite `machineCommands`
index over `machineId`, `status`, and `createdAt`. Until the backend owner creates
that index, heartbeat cannot return `autoVars`; an ONLINE machine does not prove
that `gw_` collectors are running.

After the index exists, validation must return HTTP 200 and the expected
collector count. The collectors must be HTTP/jsonPath readers of
`http://127.0.0.1:9080/latest` matching
`deployment/CONVENE_GW_MAPPING.md`; do not configure shell collectors.

## 3. VM and Cloudflare handoff

On the Windows Server 2025 predictive-engine VM, use the versioned scripts in
`deployment/windows-vm`:

```powershell
.\deployment\windows-vm\Get-ReclaimPredictiveVmInventory.ps1
.\deployment\windows-vm\Start-ReclaimQuickTunnel.ps1
```

The second script creates the temporary free `trycloudflare.com` route selected
for initial bring-up. Record the resulting HTTPS hostname privately. The desktop
gateway destination is that hostname plus `/ingest`. Keep the predictive engine
loopback-only on the VM; Cloudflare is the ingress boundary.

Do not put an ingest token on a command line or commit it. The VM
`RECLAIM_INGEST_TOKEN` and desktop `auth_token` must be the same secret.

## 4. Finalize the desktop HTTPS config

Back on this desktop, from elevated PowerShell:

```powershell
.\pi_gateway\windows\finalize-gateway-config.ps1 `
  -CloudUrl 'https://REPLACE-WITH-TUNNEL.trycloudflare.com/ingest'
```

The script prompts invisibly for the ingest token, backs up the prior config,
updates only `cloud_url` and `auth_token`, validates through the deployed Python
loader, and restricts the config to SYSTEM and Administrators.

## 5. Install and start the gateway

Registration is deliberately separate from startup:

```powershell
.\pi_gateway\windows\install-gateway-task.ps1
Start-ScheduledTask -TaskName 'RECLAIM-EdgeGateway'
```

Alternatively, use `-Start` during initial registration. Use `-ReplaceExisting`
only after inspecting an existing task. Do not start until
the real VM `/ingest` endpoint and token are configured. The installer refuses
placeholder/non-TLS config, broad config ACLs, unsafe network/firewall state,
exposed 9080 rules, and conflicting listeners.

## 6. Live acceptance evidence

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Do not claim cutover until all are factual:

- A real cRIO frame appears at `/latest` with live mode, source/run/sequence,
  state/chamber, and raw variables.
- The durable queue drains through authenticated TLS with no unexpected drops or
  dead letters, and the VM state reflects the same sequence.
- The desktop Convene heartbeat returns HTTP 200 with the expected `gw_`
  collectors, and `gw_` agrees with the independent cRIO/VM evidence.
- The VM remains the sole `sim_` publisher.
- `/command` remains advisory and disconnected from every actuator/control path.
