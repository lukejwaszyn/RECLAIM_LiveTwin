# RECLAIM Laptop Gateway / Cloud Preflight

**Deployment:** onsite Windows 10 laptop gateway (relay + HMI hub) · cloud-hosted
Windows Server 2025 predictive-engine VM in Kubernetes-managed infrastructure,
behind Cloudflare Tunnel · Convene as consumer/visualizer.
The laptop receives cRIO frames over a direct Ethernet link and forwards them
over Wi-Fi/Internet to the cloud. Deployment is intentionally side-by-side: do
not replace an operating stack or change Convene bindings until the new live
contract is proven, and never run two gateways against the same cRIO stream.

**Live-only doctrine.** This deployment integrates with the live system.
The cloud engine runs `--production`, which accepts `mode: "live"` exclusively;
harness and replay frames are rejected per-frame, final, and logged. No
synthetic emitter runs anywhere in this stack, and no harness publisher ever
touches the production Convene namespace. Rehearsal (lunar operations, power
outage) is a separate isolated instance — see §8.

---

## 1. Remote access first

The gateway's enforced WDAC policy blocks inbound SSH and RDP listeners. Do not
install or expose an SSH server and do not tunnel the unauthenticated gateway
status port. Use the existing outbound-only administration plane:

- TeamViewer for hands-on Windows administration;
- Tailscale for the approved private network; and
- the existing boot-started Convene agent for its narrowly approved heartbeat
  and audit role, not as a general deployment runner.

The predictive-engine VM is also Windows. Use the cloud provider's approved
Windows console or remote-management path. Kubernetes is the infrastructure
hosting boundary, not an instruction to use Linux guest commands.

### 1.1 Observation

On the gateway, inspect `http://127.0.0.1:9080/health`, `/latest`, and `/command`
locally through the operator session. On the VM, inspect the engine at
`http://127.0.0.1:8078` and use the external Cloudflare hostname only for the
intended authenticated pipeline checks.

### 1.2 Exit gate for §1

TeamViewer access survives a gateway reboot; the approved VM management path is
recorded; the gateway Convene agent resumes its heartbeat; and the gateway can
reach the cloud ingress `/health` endpoint. Only then proceed.

---

## 2. Reconnaissance (record before changing anything)

On the Windows Server 2025 cloud VM (PowerShell):

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
py --version
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'python|cloudflared|convene|reclaim' } |
  Select-Object ProcessId, Name, ExecutablePath, CommandLine
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 8077,8078,8079,9070,9080 }
Get-Service | Where-Object { $_.Name -match 'reclaim|cloudflared|convene' }
Get-ScheduledTask | Where-Object { $_.TaskName -match 'reclaim|cloudflared|convene' }
```

On the Windows 10 laptop (through TeamViewer): `ipconfig`, `route print -4`,
`Get-NetTCPConnection -LocalPort 9070`, and
`Get-ScheduledTask | Where-Object {$_.TaskName -match 'reclaim'}`.

Identify the process and port currently feeding Convene; it remains untouched
while the new stack is tested. Do not infer engine identity from a process
name: save `/health`, `/manifest`, and `/state` from each observed cloud port.

---

## 3. Cloud preparation

Deploy the dual-engine package to a new versioned directory on the Windows VM
and use a free loopback port. Follow `deployment/VM_ENGINE_RUNBOOK.md`; the
authoritative paths are under `C:\ProgramData\RECLAIM`, with application code
in `releases\<SHA>` and secrets, state, and logs outside the release tree.

Set a long random `RECLAIM_INGEST_TOKEN`, and a distinct `RECLAIM_READ_TOKEN`
for the GET endpoints (`/state`, `/manifest`, `/history`, `/command`) used by
the Convene publisher and visualizer — `/health` stays open for probes.
The Cloudflare Tunnel (`cloudflared` on the VM) terminates TLS and forwards
both `POST /ingest` and the GET routes to the engine, which binds
**loopback only** so it is reachable exclusively through the tunnel. Never
expose the engine port directly to the Internet.

Install the repository's WinSW service template only after setting its absolute
Windows paths and verifying the WinSW binary. Tokens come from the ACL-protected
secret file read by `cloud_engine\windows\run-ingest-engine.ps1`; they never
appear in service XML or command-line arguments. The runner sets
`RECLAIM_INGEST_STATE` so run/sequence identity survives restarts. Protect the
state and secret paths with NTFS ACLs and confirm the VM platform preserves the
underlying Windows disk across Kubernetes rescheduling before declaring restart
recovery proven.

---

## 4. Laptop gateway configuration

### 4.1 cRIO link

Connect the cRIO directly to the laptop Ethernet port. Isolated link: laptop
Ethernet `192.168.50.1/24`, cRIO Ethernet `192.168.50.10/24`, **no default
gateway** on either direct-link interface. Keep Wi-Fi as Windows' default
Internet route. Configure the cRIO's TCP target as `192.168.50.1:9070`.
Create a Windows Firewall rule for inbound TCP `9070` on the **Private**
Ethernet profile.

### 4.2 Gateway config

Copy `pi_gateway/config.example.yaml` to
`C:\RECLAIM\pi_gateway\config.windows.yaml`. The gateway fails fast on a
missing or typo'd config instead of silently running on defaults. Set:

```yaml
src: reclaim-crio-laptop-01
listen_host: 192.168.50.1
listen_port: 9070
transport: https
cloud_url: https://<approved-ingress-host>/ingest
auth_token: <same RECLAIM_INGEST_TOKEN>
mode: live
run_id: ""                 # gateway creates one UUID at service start
schema_version: reclaim.telemetry.v1
strict_fields: false        # retain real LabVIEW raw fields for labview_map.py
buffer_path: C:/ProgramData/RECLAIM/queue.db
status_port: 9080
```

`strict_fields` remains false until the actual complete LabVIEW field manifest
has been captured — that prevents the gateway from dropping raw channels such
as the process flags before cloud-side normalization.

### 4.3 Install as an always-on service

Install Python 3.10+ and prepare the venv from `C:\RECLAIM\pi_gateway`:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then (elevated):

```powershell
.\windows\install-gateway-task.ps1
```

This registers the `RECLAIM-EdgeGateway` Scheduled Task: starts at machine
boot as SYSTEM (no login), restarts within 1 minute on failure (the gateway
exits non-zero when a worker thread dies, precisely so the supervisor restarts
it), and does not resurrect a clean operator stop. Telemetry transfer is
therefore continuous from boot — nothing is spun up per run. For a first
manual shakedown you may instead run
`$env:RECLAIM_EDGE_CONFIG="$PWD\config.windows.yaml"; python -m reclaim_edge.main`
in a console, but the production posture is the task.

### 4.4 CommandSignal return path

The digital twin's ControlCommand rides back in every `/ingest` response; the
gateway relays it and the control hub / HMI polls it locally at
`http://127.0.0.1:9080/command`. `command_age_s` lets the HMI invalidate a
stale command exactly as Convene gates stale state.

### 4.5 Wi-Fi uplink note (RF coexistence)

The SSMG radiates at 2.45 GHz — inside the 2.4 GHz Wi-Fi band. Pin the
laptop's Wi-Fi to **5 GHz** (disable band-steering fallback) and verify the
link **while a heating cycle is running**: watch `last_ack_age_s` and
`dead_letter` on `/health` during `S_MicrowaveHeating`. A 2.4 GHz association
that looks fine at idle can degrade precisely when telemetry and the returning
CommandSignal matter most. (Team assessment: laptop placement plus the
5 mW/cm² @ 5 in leakage requirement make interference unlikely; this check is
passive confirmation, not a blocker.)

---

## 5. Contract gates

From a trusted shell, post one fresh v1 frame through the authenticated
ingress. The response must report one accepted frame and zero errors. Then:

```powershell
Invoke-RestMethod https://<ingress>/health
$headers = @{ Authorization = "Bearer $env:RECLAIM_READ_TOKEN" }
Invoke-RestMethod https://<ingress>/state -Headers $headers
Invoke-RestMethod https://<ingress>/manifest -Headers $headers
```

Expected `/state` fields include `schema_version: reclaim.state.v1`,
`mode: live`, `run_id`, `source_id`, `seq`, `ts_source`, `cycle_id`,
`source_op_state`, singular `op_state`, `PL_op_state`, `MT_op_state`, and
`ingest_status: accepted`.

Repeat the same frame once: it must report `duplicate` and must not increment
the ingestion count. Post a `mode: harness` frame: it must be **rejected** —
this is the live-only proof (a rehearsal cannot overwrite the live run; retry
buffering cannot double-step the estimator).

Then the v1.1 recovery gates:

1. **Stale gate** — post a batch containing one stale frame (`ts` older than
   the freshness window) and one fresh frame. Response must be `200` with the
   stale frame `rejected/timestamp_stale/final` and the fresh frame
   `accepted` (per-frame results; the batch never fails as a whole). On the
   laptop, confirm the stale frame lands in the dead-letter count on
   `/health`, not back in the queue.
2. **Gateway-restart gate** — restart the laptop gateway task. The next frames
   carry a new `run_id`; the cloud must log `RUN_SUPERSEDED` and keep
   accepting, with `active_run_id` on cloud `/health` showing the new run and
   no operator action.
3. **Cloud-restart gate** — restart the ingest service, then re-post the last
   accepted frame. It must report `duplicate` (identity restored from
   `RECLAIM_INGEST_STATE`); `ingested_total` must not double-step.
4. **Freshness gate** — stop the laptop feed and poll `/state`:
   `state_age_ms` must grow, and Convene must flip to DATA NOT LIVE at the
   agreed limit.

---

## 6. Shadow run + data V&V (the gateway audit machine)

Run the laptop gateway against the new cloud endpoint without changing any
Convene binding. Compare source state, active chamber, sequence, and timestamp
between laptop `/latest` and cloud `/state` for at least one complete
controlled state transition.

**This step is formal verification and validation of the data itself.**
Register the laptop as its own Convene machine publishing the `gw_` audit set
from `/latest` (binding doc, "Gateway audit machine": strictly separate
namespace from `sim_`, read-only tap, never in the delivery path). The audit
view shows three columns per signal — LabVIEW indicator, `gw_*` submitted
frame, `sim_*` cloud state — with `gw_seq − sim_seq` plus `sim_ingest_age_ms`
as the live pipeline-lag readout.

What the V&V establishes, and why it matters for everything after:

- **Verification:** the frame the engine receives is byte-for-byte the frame
  LabVIEW produced (`gw_*` matches the LabVIEW indicators, every frame).
- **Validation:** the engine's provenance echo matches what was submitted
  (`sim_seq`/`sim_source_op_state` track `gw_*` with only transport lag).
- **Fault isolation:** with input equivalence proven at every boundary, any
  metric discrepancy downstream is attributable to **the engine alone** —
  never to ambiguity about what data it was fed. Every future model
  discussion (ADR-001, ADR-002, estimator alternatives) inherits this basis.

Exit gate: one full controlled sequence
`S_BatchLoad → S_Evacuate → S_MicrowaveHeating → S_CoolDown → S_Complete`
with all three columns in agreement at each transition and lag within the
agreed bound.

---

## 7. Convene cutover

Only after §6 passes, configure **one** publisher to Convene and bind:

- `sim_op_state` — system state
- `sim_PL_op_state` and `sim_MT_op_state` — chamber state
- `sim_run_id`, `sim_seq`, `sim_ingest_age_ms`, and `sim_mode` — provenance
  and live-data health

Disconnect legacy writers before enabling the new publisher. Rollback consists
of disabling the new publisher/binding only; it never involves sending
synthetic data into the production namespace. The `gw_` audit machine remains
running after cutover — it is a permanent V&V fixture, not scaffolding.

---

## 8. Rehearsal isolation (lunar operations, power outage)

The rehearsal scenarios run as **separate GET-only engine instances**, never by
switching the live one. On the Windows VM, start them with
`cloud_engine\windows\start-rehearsal-scenario.ps1` using `nominal`,
`power-outage`, `lunar`, or `loss-of-data`. They use loopback ports 8177–8181, publish explicit
`mode=harness` plus scenario/environment metadata, and bind only to separate
rehearsal Convene namespaces. Start and stop them without touching the live
stack; the live engine rejects rehearsal-labeled frames by design (§5 proved
it). Note ADR-002
separately provides the lunar-vs-terrestrial *cooldown contrast from live
data* via counterfactual projection — that is part of the live engine and is
not a rehearsal.

---

## Handoff checklist

- [ ] §1 outbound-only gateway access and approved VM management path verified
- [ ] §2 recon recorded (cloud ports/processes, laptop network state)
- [ ] §3 Windows cloud engine deployed: loopback bind, ACL-protected tokens,
      persistent state file configured, WinSW service running `--production`
- [ ] §4 cRIO link static IPs; gateway config in place; `RECLAIM-EdgeGateway`
      task installed and running from boot; `/health` `/latest` `/command`
      answering
- [ ] §5 all six contract gates passed (fresh, duplicate, harness-reject,
      stale, gateway-restart, cloud-restart) + freshness decay observed
- [ ] §6 audit machine publishing `gw_` set; three-column V&V agreement over
      one full state sequence; lag bound agreed and met
- [ ] §7 legacy writers disconnected; single `sim_` publisher enabled;
      rollback procedure understood
- [ ] §8 rehearsal instance documented/provisioned on isolated port +
      namespace (optional at cutover)
