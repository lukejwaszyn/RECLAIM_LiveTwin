# RECLAIM Laptop Gateway / Cloud Preflight

**Deployment:** onsite Windows 10 laptop gateway (relay + HMI hub) · cloud VM
predictive engine behind Cloudflare Tunnel · Convene as consumer/visualizer.
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

## 1. Remote access first (step zero — replaces TeamViewer)

Persistent, scriptable shell access is the foundation; every later
configuration action happens through this shell. All inbound access rides
Cloudflare Tunnel — outbound-only from the laptop, no port forwarding,
protected by a Cloudflare Access policy.

### 1.1 SSH server on the laptop (elevated PowerShell)

```powershell
# OpenSSH server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic
Start-Service sshd

# key auth for an admin account (Windows quirk: admin keys live here)
Add-Content C:\ProgramData\ssh\administrators_authorized_keys "<your ssh-ed25519 public key>"
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r `
       /grant "Administrators:F" /grant "SYSTEM:F"
# after key login is verified: set 'PasswordAuthentication no' in
# C:\ProgramData\ssh\sshd_config and Restart-Service sshd
```

### 1.2 Named tunnel as a boot-started service

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create reclaim-laptop
cloudflared tunnel route dns reclaim-laptop ssh-gw.<your-domain>
cloudflared tunnel route dns reclaim-laptop status-gw.<your-domain>
cloudflared service install
Set-Service cloudflared -StartupType Automatic
```

`config.yml`:

```yaml
tunnel: reclaim-laptop
credentials-file: C:\Users\<user>\.cloudflared\<tunnel-id>.json
ingress:
  - hostname: ssh-gw.<your-domain>
    service: ssh://localhost:22
  - hostname: status-gw.<your-domain>
    service: http://localhost:9080
  - service: http_status:404
```

In the Cloudflare dashboard, create a self-hosted Access application covering
both hostnames with a policy allowing team emails only.

### 1.3 PuTTY client (any workstation)

Install `cloudflared` on the client. In PuTTY: Session → Host Name
`ssh-gw.<your-domain>`, port 22; Connection → Proxy → Proxy type **Local**,
local proxy command:

```
cloudflared access ssh --hostname %host
```

First connection opens a browser for the Access login, then the session lands.
For scripted use (scp/rsync of configs), the equivalent `ssh_config` entry is
`ProxyCommand cloudflared access ssh --hostname %h`.

### 1.4 Observation by URL (interim)

`https://status-gw.<domain>/health` is the interim observation point: rx/tx
counters, queue depth, dead-letter count, last-ack age. `/latest` shows the
most recent submitted frame; `/command` shows the returning CommandSignal.
Once the new cloud engine deployment is the observation plane, the same
numbers are read from cloud `/health` + `/state` and the status hostname
becomes a maintenance-only path.

### 1.5 Exit gate for §1

Remote SSH works from an offsite network via PuTTY; both tunnel hostnames
answer after a laptop reboot with no login; Convene loads from the laptop;
cloud ingress `/health` reachable from the laptop (`curl
https://<ingress>/health`, record round-trip times). Only then proceed.

---

## 2. Reconnaissance (record before changing anything)

On the cloud host:

```bash
hostnamectl
python3 --version
ps aux | grep -E '[p]ush_ingest|[r]eclaim_edge|[c]onvene'
ss -tlnp | grep -E '8077|8078|8079|9070|9080'
systemctl list-units --all | grep -i reclaim
```

On the laptop (over the new SSH path): `ipconfig`, `route print -4`,
`Get-NetTCPConnection -LocalPort 9070`, and
`Get-ScheduledTask | Where-Object {$_.TaskName -match 'reclaim'}`.

Identify the process and port currently feeding Convene; it remains untouched
while the new stack is tested. Do not infer engine identity from a process
name: save `/health`, `/manifest`, and `/state` from each observed cloud port.

---

## 3. Cloud preparation

Deploy the dual-engine package to a new directory and use a free port. Before
starting its production service, create the secret file:

```bash
sudo install -d -m 700 /etc/reclaim
sudo sh -c 'umask 077; cp reclaim-ingest.env.example /etc/reclaim/reclaim-ingest.env'
sudoedit /etc/reclaim/reclaim-ingest.env
```

Set a long random `RECLAIM_INGEST_TOKEN`, and a distinct `RECLAIM_READ_TOKEN`
for the GET endpoints (`/state`, `/manifest`, `/history`, `/command`) used by
the Convene publisher and visualizer — `/health` stays open for probes.
The Cloudflare Tunnel (`cloudflared` on the VM) terminates TLS and forwards
both `POST /ingest` and the GET routes to the engine, which binds
**loopback only** so it is reachable exclusively through the tunnel. Never
expose the engine port directly to the Internet.

Install the supplied `reclaim-ingest.service` only after setting its absolute
Python and working-directory paths for the actual host. Tokens come from the
`EnvironmentFile` only — never on the command line (visible in `ps`). The unit
sets `RECLAIM_INGEST_STATE` so run/sequence identity survives restarts; both
are required in `--production`.

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

```bash
curl -sS https://<ingress>/health                                  # open (probe)
curl -sS -H 'Authorization: Bearer <READ token>' https://<ingress>/state
curl -sS -H 'Authorization: Bearer <READ token>' https://<ingress>/manifest
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

The two rehearsal scenarios run on a **separate engine instance**, never by
switching the live one: different port, fed by the scenario generator
(`--scenario power_outage`, `--env lunar_habitat` / `lunar_surface`), output
labeled non-live, bound only to a separate rehearsal Convene namespace. Start
and stop it at any time without touching the live stack; the live engine
rejects rehearsal-labeled frames by design (§5 proved it). Note ADR-002
separately provides the lunar-vs-terrestrial *cooldown contrast from live
data* via counterfactual projection — that is part of the live engine and is
not a rehearsal.

---

## Handoff checklist

- [ ] §1 SSH via PuTTY from offsite; tunnel survives reboot; Access policy on
- [ ] §2 recon recorded (cloud ports/processes, laptop network state)
- [ ] §3 cloud engine deployed: loopback bind, env-file tokens (600), state
      file configured, `--production`
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
