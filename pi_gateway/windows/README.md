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
canonical gateway frame
  -> nonblocking /machine/publish using desktop machine credential
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
index over `machineId`, `status`, and `createdAt`. The backend owner should still
create it, but direct `/machine/publish` is independent and reaches authenticated
request validation.

The production gateway enables a nonblocking one-frame worker that publishes the
same canonical frame as `gw_` scalars directly. Verify its delivered/failed/
coalesced counters under `/health` and compare its names with
`deployment/CONVENE_GW_MAPPING.md`. Do not configure shell collectors.

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
updates `cloud_url`/`auth_token`, enables the credential-reference-only direct
Convene `gw_` publisher, validates through the deployed Python loader, and
restricts the config to SYSTEM and Administrators.

If the installer reports an unexpected config ACL entry, repair the active file
and every token-bearing backup without re-entering the token:

```powershell
.\pi_gateway\windows\finalize-gateway-config.ps1 -RepairAclOnly
```

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

Before direct cRIO operation, one supervised synthetic frame may be used to prove
both outbound paths. The script refuses to run while the real cRIO is connected:

```powershell
.\pi_gateway\windows\send-commissioning-frame.ps1 `
  -VmBaseUrl 'https://REPLACE-WITH-CURRENT-TUNNEL.trycloudflare.com'
```

This creates explicitly labeled `COMMISSIONING-NOT-CRIO-*` data in both the VM
and desktop Convene `gw_` view. Run it once, retain the JSON evidence, and do not
confuse its values with physical measurements.

To span the predictive-state bridge and multiple Convene heartbeats, run a
bounded five-minute, 1 Hz stream through the same guarded ingress:

```powershell
.\pi_gateway\windows\send-commissioning-stream.ps1 `
  -VmBaseUrl 'https://REPLACE-WITH-CURRENT-TUNNEL.trycloudflare.com'
```

Every frame is labeled `COMMISSIONING-STREAM-NOT-CRIO-*`; the script aborts if a
real cRIO session is present or attempts to connect, then requires exact desktop
receive and VM-ingest counts, a Convene delivery advance, an empty queue, and no
new dead letters.

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Do not claim cutover until all are factual:

- A real cRIO frame appears at `/latest` with live mode, source/run/sequence,
  state/chamber, and raw variables.
- The durable queue drains through authenticated TLS with no unexpected drops or
  dead letters, and the VM state reflects the same sequence.
- `/health` reports successful direct Convene publishes with no unexplained
  failures/coalescing, and `gw_` agrees with the independent cRIO/VM evidence.
- The VM remains the sole `sim_` publisher.
- `/command` remains advisory and disconnected from every actuator/control path.
