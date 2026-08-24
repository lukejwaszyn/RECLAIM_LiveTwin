# Historical Windows gateway closeout

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

> **Superseded 2026-08-23:** the authoritative edge gateway is the MacBook.
> Nothing in this directory is an operational competition procedure. Retain it
> only as evidence of the earlier Windows commissioning and rollback design.

This directory contains the retired desktop-side workflow for the former Windows
edge gateway. `pi_gateway` is a legacy directory name; no Raspberry Pi is in the
live path.

For a replacement laptop, start with
`deployment/NEW_GATEWAY_SCENARIO_DEPLOYMENT.md`. It pins one Git SHA, stages the
service without overwriting its protected config, installs the gateway, and
requires correlated live exact-name gateway variables plus `sim_*` evidence. The current VM-side
blocking issue and its copy/paste owner prompt are in
`deployment/CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`.

## Fixed topology

```text
cRIO <CRIO_SOURCE_IP> / Scan Engine network-published variables
  -> NI-PSP read over the isolated Ethernet link
Historical Windows input-only PSP adapter
  -> compact LF-delimited TCP to <WINDOWS10_GATEWAY_IP>:9070 on the same desktop
MacBook scenario host process
  -> durable SQLite queue
  -> authenticated HTTPS /ingest through the VM Cloudflare hostname
Windows Server 2025 predictive-engine VM

Independent audit tap:
canonical gateway frame
  -> nonblocking /machine/publish using desktop machine credential
  -> raw gateway variables only
```

The desktop Convene agent never writes `sim_`. The VM is the only `sim_`
publisher. Neither path authorizes command actuation.

## 1. Direct cRIO network

Already applied on this desktop:

- Ethernet: `<WINDOWS10_GATEWAY_IP>/24`, Private, no default route.
- cRIO peer: `<CRIO_SOURCE_IP>/24`.
- Inbound TCP 9070 is allowed only from `<CRIO_SOURCE_IP>` on Ethernet.
- TCP 9080 is not exposed; status remains loopback-only.

Re-audit or idempotently reapply from elevated PowerShell:

```powershell
.\pi_gateway\windows\configure-crio-network-firewall.ps1 -Mode Audit
.\pi_gateway\windows\configure-crio-network-firewall.ps1 -Mode Apply
```

Do not configure or deploy a cRIO/LabVIEW TCP sender. The selected source is the
separate input-only Windows subscriber in `crio_psp_adapter`, which reads an
explicit POC allowlist and is the sole TCP writer to `<WINDOWS10_GATEWAY_IP>:9070`. Replace
that POC allowlist with the controls-approved production allowlist only after the
mapping gate passes.
The narrow inbound cRIO firewall rule remains unchanged as defensive historical
configuration, but it is not evidence of the selected adapter path. Do not add a
default gateway to the cRIO-facing Ethernet interface.

## 2. Desktop Convene identity and raw gateway audit tap

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
same canonical frame as raw gateway scalars directly. Verify its delivered/failed/
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
Convene raw gateway publisher, validates through the deployed Python loader, and
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

Before the PSP adapter is connected to the gateway, one supervised synthetic
frame may be used to prove both outbound paths. The script refuses to run while
a live source session is connected:

```powershell
.\pi_gateway\windows\send-commissioning-frame.ps1 `
  -VmBaseUrl 'https://REPLACE-WITH-CURRENT-TUNNEL.trycloudflare.com'
```

This creates explicitly labeled `COMMISSIONING-NOT-CRIO-*` data in both the VM
and desktop Convene raw gateway view. Run it once, retain the JSON evidence, and do not
confuse its values with physical measurements.

To span the predictive-state bridge and multiple Convene heartbeats, run a
bounded five-minute, 1 Hz stream through the same guarded ingress:

```powershell
.\pi_gateway\windows\send-commissioning-stream.ps1 `
  -VmBaseUrl 'https://REPLACE-WITH-CURRENT-TUNNEL.trycloudflare.com'
```

Every frame is labeled `COMMISSIONING-STREAM-NOT-CRIO-*`; the script aborts if a
live adapter session is present or attempts to connect, then requires exact desktop
receive and VM-ingest counts, a Convene delivery advance, an empty queue, and no
new dead letters.

### Current live PSP engineering POC

The input-only Windows adapter has exercised the selected live seam at an
observed sustainable cadence of one frame every three seconds. Nominal 1 Hz
produced downstream `timestamp_stale` rejections and is not an accepted live
cadence. Current source coverage is eight provisional contract-named
thermocouples plus `scan_Mod3_AI0_raw`, `scan_Mod3_AI1_raw`, and
`scan_Mod3_AI2_raw`. It does not provide `MW_*`, `PL_purge_pump`, the remaining
process fields, or authoritative state/chamber/cycle metadata.

The gateway forwards only fields present in the current frame. A Convene raw gateway
value retained from an earlier synthetic or live frame must be shown unavailable
when its source field is absent or its provenance/freshness does not match the
current frame. In particular, do not interpret retained `MW_*` or
`PL_purge_pump` values as current live telemetry.

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Do not claim cutover or full-cycle operation until all are factual:

- A full-contract PSP-adapter frame appears at `/latest` with live mode,
  source/run/sequence, authoritative state/chamber/cycle/time, and the approved
  raw variables.
- Every required contract name is present with approved units, types, scaling,
  range, and invalid semantics; absent fields are explicitly unavailable rather
  than displaying retained values.
- The approved cadence remains fresh without `timestamp_stale` rejection.
- The durable queue drains through authenticated TLS with no unexpected drops or
  dead letters, and the VM state reflects the same sequence.
- `/health` reports successful direct Convene publishes with no unexplained
  failures/coalescing, and raw gateway agrees with the independent cRIO/VM evidence.
- The VM remains the sole `sim_` publisher.
- `/command` remains advisory and disconnected from every actuator/control path.
