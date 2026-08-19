# RECLAIM Three-Endpoint Integration Handoff

> **Status:** authoritative endpoint-boundary handoff
>
> **Snapshot:** 2026-08-19
>
> **Repository:** `RECLAIM_LiveTwin`
>
> **Branch:** `desktop/edge-gateway`
>
> **Commissioning baseline commit:** `322d333`
>
> **Overall live status:** **NO-GO** until a real cRIO frame traverses all three
> endpoints and the evidence in §8 passes.

## 1. The three endpoints are distinct

Do not merge their credentials, Convene machine identities, variable namespaces,
services, or deployment procedures.

| Endpoint | Platform | Owns | Sends to Convene as |
|---|---|---|---|
| **1 — Desktop edge gateway** | This Windows 10 laptop | cRIO TCP ingress, canonical framing, durable outbound queue, Cloudflare-bound VM delivery, raw audit publication | `gw_` |
| **2 — Predictive-engine VM** | Cloud-hosted Windows Server 2025 | `/ingest`, predictive algorithms, derived stakeholder state, VM state bridge, separate VM Convene publisher/binding | `sim_` |
| **3 — Convene** | External Convene service/UI | Displays the independent desktop audit and VM predictive/stakeholder views | Receives both, but does not fuse their credentials or writers |

### Non-negotiable topology

```text
cRIO / LabVIEW (authoritative raw telemetry)
  |
  | direct Ethernet, newline-delimited TCP to 192.168.1.1:9070
  v
ENDPOINT 1 — WINDOWS 10 DESKTOP EDGE GATEWAY
  |
  |-- A. Pairing-code desktop credential -> /api/machine/publish
  |      -> Convene gw_ raw/audit namespace --------------------------+
  |                                                                  |
  |-- B. Durable SQLite queue -> authenticated HTTPS POST /ingest     |
         -> Cloudflare tunnel hostname                               |
         -> VM loopback 127.0.0.1:8078                               |
              v                                                     |
ENDPOINT 2 — WINDOWS SERVER 2025 PREDICTIVE-ENGINE VM                 |
  |                                                                  |
  | predictive algorithms -> validated stakeholder state             |
  | -> VM state bridge / VM-specific Convene binding                  |
  | -> Convene sim_ namespace ----------------------------------------+
                                                                     |
                                                                     v
ENDPOINT 3 — CONVENE
  - desktop machine/view: gw_ raw values and source provenance
  - VM machine/view: sim_ estimates, margins, health, advisories, stakeholder values
```

The two arrows into Convene are intentionally independent:

- The **desktop** uses a Convene pairing code to obtain its desktop machine
  credential, then the gateway posts `gw_` values directly to
  `/api/machine/publish`.
- The **VM** uses its own installed agent/binding/state-bridge mechanism and its
  own credential/variable IDs. It does not read, copy, or reuse the desktop
  credential or `gw_` writer.

## 2. Namespace and authority rules

| Rule | Enforcement |
|---|---|
| Desktop writes only `gw_` | `pi_gateway/reclaim_edge/convene.py` prefixes every scalar and tests prohibit `sim_` output. |
| VM is the only `sim_` writer | VM state bridge and VM-specific binding scripts own derived stakeholder publication. |
| Convene is visualization/consumer | Convene values never become cRIO, microwave, PLC, HMI, or actuator commands. |
| Cloud-returned `/command` is advisory only | It may be observed locally but remains disconnected from all actuation. |
| cRIO is the raw source of truth | The first real frame must be retained and compared with the expected contract before strict schema enforcement. |
| VM delivery is durable; desktop Convene audit is best effort | Convene cannot block or acknowledge the SQLite queue feeding the VM. |

## 3. Endpoint 1 — Windows 10 desktop edge gateway

### 3.1 Current factual state

| Item | State |
|---|---|
| Repository | `C:\Users\latitude4\Documents\Codex\2026-08-16\i\RECLAIM_LiveTwin` |
| Branch | `desktop/edge-gateway`, pushed through `322d333` before evidence capture |
| Staged runtime | `C:\RECLAIM\pi_gateway` |
| Laptop cRIO interface | Ethernet `192.168.1.1/24`, Private, no desktop-side default route |
| cRIO peer | `192.168.1.2/24`, reachable by laptop ping |
| Firewall | TCP 9070 allowed inbound only from `192.168.1.2` on Ethernet/Private |
| Status port | 9080 loopback-only; no inbound allow rule |
| Desktop Convene machine | Persistent SYSTEM task has launched with machine `BcryPSMP2iLbSRns5uhm` |
| Desktop Convene API | `https://reservation-backend-25386666460.us-central1.run.app/api` |
| Direct publish probe | Empty `variables` reached authenticated semantic validation: HTTP 400 `no variables to publish`, not 401; no variable was created |
| Gateway source | Dual-output source and non-secret Convene settings are staged |
| Gateway task | `RECLAIM-EdgeGateway` installed and running as SYSTEM; listeners verified on `192.168.1.1:9070` and `127.0.0.1:9080` |
| VM route | Current Quick Tunnel is `https://renewal-conclude-associates-relief.trycloudflare.com/ingest`; temporary and must be re-finalized if restarted |
| Production config | Live HTTPS URL/token finalized; active file and one token-bearing backup verified as SYSTEM/Administrators only |
| Synthetic fan-out | **PASS** at `2026-08-19T20:45:20Z`; desktop receive, VM ingest, and desktop Convene publish all advanced once |
| Real cRIO frame | **Not yet observed** |
| Tests | 26 gateway tests and 63 bridge/operator-workflow tests passed |

### 3.1.1 Retained commissioning evidence

The single supervised frame was deliberately labeled as synthetic and must not
be treated as a physical measurement:

| Evidence | Value |
|---|---|
| `source_id` | `reclaim-commissioning-desktop` |
| `cycle_id` | `COMMISSIONING-NOT-CRIO-20260819T204518Z` |
| Canonical `run_id` / `seq` | `8a7ba244-0535-476b-ba1c-961822e05cc9` / `1` |
| Desktop receive advanced | yes |
| VM `ingested_total` | advanced from 0 to 1 |
| Desktop Convene delivered | advanced from 0 to 1 |
| Desktop Convene failed/coalesced | `0` / `0` |
| Durable queue / dead letter after delivery | `0` / `0` |
| VM accepted active run | `8a7ba244-0535-476b-ba1c-961822e05cc9` |
| cRIO peer reachability after test | `192.168.1.2`, two replies |

This proves the desktop gateway's two outbound paths and the VM ingress service.
It does **not** prove the cRIO field names/types, predictive-engine processing,
the VM-specific `sim_` Convene writer, stale-state behavior, or restart recovery.
Until a real run supersedes it, the desktop `/latest` record and VM
`active_run_id` identify this commissioning frame; operators must continue to
treat it as synthetic and not as current physical process state.

### 3.2 Desktop data handling order

For each valid cRIO line:

1. Parse and construct the canonical frame.
2. Persist the frame and sequence high-water mark in the SQLite VM queue.
3. Expose the frame locally at `http://127.0.0.1:9080/latest`.
4. Submit the same scalar envelope/raw values to the nonblocking Convene worker.
5. Convene receives names prefixed with `gw_` through `/machine/publish`.
6. The durable cloud publisher independently retries VM `/ingest` until the VM
   returns an accepted/duplicate/final-rejection disposition.

The Convene worker holds at most one pending audit frame. During a Convene
outage it coalesces to the newest frame and increments health counters; it never
blocks cRIO receipt or removes VM queue records.

### 3.3 Desktop Convene pairing mechanism

The pairing code is used to create the desktop connected-machine credential. It
is not sent on every telemetry request. At runtime:

- User credential: `C:\Users\latitude4\.convene_agent.json`
- SYSTEM credential used by services/tasks:
  `C:\Windows\System32\config\systemprofile\.convene_agent.json`
- Existing task: `Convene-Agent`
- Gateway reads only the SYSTEM credential path; the token is not copied into
  `config.windows.yaml` or Git.
- Direct telemetry endpoint: `/api/machine/publish`

The connected-machine heartbeat currently returns HTTP 500 after updating
presence because the Convene backend lacks the Firestore composite
`machineCommands` index over `machineId`, `status`, and `createdAt`. This degrades
the separate heartbeat/command response, but direct `/machine/publish` is a
different route and does not depend on returned `autoVars`.

Cleanup after stability is proven: remove unused/revoked desktop Convene records,
including credentialless test record `2rItUt06wMkwtuexiy89`. Do not delete the
active desktop record while validating.

### 3.4 Expected raw cRIO contract

Required source metadata:

```text
cycle_id
source_op_state
active_chamber       # PL | MT | NONE
ts                   # ISO-8601 UTC strongly preferred
source_id            # strongly preferred; gateway has a configured fallback
```

Expected raw scalar fields under `vars`:

```text
PL_bottom1                 PL_bottom2
PL_bottom3                 PL_bottom4
PL_surface_temp            PL_top_condenser_temp
PL_bottom_condenser_temp   PL_chamber_pressure
PL_output_pressure         PL_process
PL_preprocess              PL_postprocess
PL_chamber_pump            PL_purge_pump
MT_bottom                  MT_top
MW_power                   MW_reverse
MW_freq                    MW_width
MW_period                  MW_water_temp
MW_flow_rate               MW_water_state
MW_flow_state              MW_RF
MW_status
```

This list is repository-derived, not live-observed. `strict_fields: false`
preserves unexpected fields in the first real frame. Confirm names, types, units,
and semantics before enabling a strict manifest. The predictive engine expects
numeric values to be finite and the listed flags to be actual booleans.

### 3.5 Desktop activation after VM handback

The VM operator must privately return:

1. The temporary or approved Cloudflare base hostname.
2. Confirmation that `<base>/ingest` routes only to VM loopback port 8078.
3. The existing VM `RECLAIM_INGEST_TOKEN`, transferred securely and never pasted
   into chat, command history, logs, or Git.

Then run from **elevated PowerShell on this desktop**:

```powershell
Set-Location 'C:\Users\latitude4\Documents\Codex\2026-08-16\i\RECLAIM_LiveTwin'

.\pi_gateway\windows\finalize-gateway-config.ps1 `
  -CloudUrl 'https://REPLACE.trycloudflare.com/ingest'

.\pi_gateway\windows\install-gateway-task.ps1 -Start
```

The finalizer prompts invisibly for the VM ingest token, protects backups and the
active YAML with SYSTEM/Administrators-only ACLs, enables the direct desktop
Convene publisher by credential reference, and validates the deployed loader.

Do not use `transport: console` for live cRIO data; console transport acknowledges
frames without sending them to the VM.

### 3.6 Desktop verification

```powershell
Get-ScheduledTask -TaskName 'RECLAIM-EdgeGateway','Convene-Agent' |
  Select-Object TaskName,State

Get-NetTCPConnection -State Listen -LocalPort 9070,9080 |
  Select-Object LocalAddress,LocalPort,OwningProcess

Invoke-RestMethod http://127.0.0.1:9080/health |
  ConvertTo-Json -Depth 6

Invoke-RestMethod http://127.0.0.1:9080/latest |
  ConvertTo-Json -Depth 8
```

Expected binding:

- `192.168.1.1:9070` for cRIO ingress.
- `127.0.0.1:9080` for local status only.

`/health` must show cRIO receive count, VM delivered/queue/dead-letter counters,
and the independent Convene `delivered`, `failed`, `coalesced`, and
`last_success_age_s` counters.

## 4. Endpoint 2 — Windows Server 2025 predictive-engine VM

### 4.1 Endpoint ownership

The VM owns all of the following and the desktop owns none of them:

- Predictive engine Windows service `RECLAIMIngestEngine`.
- Loopback production listener `127.0.0.1:8078`.
- VM ingest/read secrets under
  `C:\ProgramData\RECLAIM\engine\secrets\reclaim-ingest.env`.
- Cloudflare client/tunnel exposing only VM port 8078.
- Predictive state and sequence persistence.
- Windows state bridge and `C:\ConveneAgent\sim_vars.json`.
- VM-specific Convene agent/token/machine/variable IDs.
- `sim_` stakeholder publication and Convene-native `.stp` binding.

### 4.2 Current knowledge boundary

Repository records describe a previously proven VM ingestion-to-state-to-Convene
path, but this desktop session did **not** inspect the live VM. Treat actual VM
service, tunnel, release, token, bridge, and Convene state as unknown until the
VM inventory is run. Do not overwrite an existing service, named tunnel, or
Convene writer.

### 4.3 First actions on the VM

From elevated PowerShell in a fresh checkout/pull of this branch:

```powershell
Set-Location 'C:\path\to\RECLAIM_LiveTwin'
git fetch origin
git switch desktop/edge-gateway
git pull --ff-only

.\deployment\windows-vm\Get-ReclaimPredictiveVmInventory.ps1
.\deployment\windows-vm\Start-ReclaimQuickTunnel.ps1 -Mode Audit
```

The inventory is read-only and does not print service command lines or secret
contents. Preserve and review anything already installed before changing it.

Expected VM engine gate:

```powershell
Get-Service RECLAIMIngestEngine
Get-NetTCPConnection -State Listen -LocalPort 8078
Invoke-RestMethod http://127.0.0.1:8078/health | ConvertTo-Json -Depth 6
```

There must be exactly one production listener on `127.0.0.1:8078`, never
`0.0.0.0:8078`.

### 4.4 Temporary Cloudflare route

Only after the audit reports no competing tunnel/configuration and the engine is
healthy:

```powershell
.\deployment\windows-vm\Start-ReclaimQuickTunnel.ps1 -Mode Run
```

This is a foreground temporary tunnel. Keep its PowerShell window open. It
exposes only `http://127.0.0.1:8078`, writes a redacted operational log, and
saves the generated base URL under:

```text
C:\ProgramData\RECLAIM\cloudflared-quick\public-url.txt
```

In another elevated VM shell:

```powershell
.\deployment\windows-vm\Start-ReclaimQuickTunnel.ps1 -Mode ShowUrl
```

Return `<base>/ingest` to the desktop operator. Quick Tunnel hostnames change on
restart; the desktop must be re-finalized whenever the hostname changes. A named
tunnel/domain is the later durability step, not required for initial bring-up.

### 4.5 VM ingest and predictive processing

The VM receives the desktop's canonical live frame. Production ingestion
requires:

```text
schema_version
mode=live
run_id
source_id
seq
ts
cycle_id
source_op_state
active_chamber
vars
```

The engine's `labview_map.py` converts the raw contract into chamber-tagged SI
measurements, including °C→K, mbar→kPa, plastics bed-bank aggregation, and shared
microwave-power attribution based on `active_chamber`. It then calculates the
stakeholder-facing values: estimates, uncertainty/trust, margins, anomaly
metrics, lifecycle state, forecasts, advisory severity/action, freshness, and
provenance.

### 4.6 VM-to-Convene mechanism — separate from desktop

The VM does **not** call the desktop `/machine/publish` worker and does not use
the desktop pairing credential. Its path is:

```text
VM /state
  -> Windows state bridge
  -> atomic C:\ConveneAgent\sim_vars.json
  -> VM-specific Convene agent/bindings
  -> Convene sim_ stakeholder variables
```

Relevant VM-only artifacts:

```text
deployment/windows-vm/Deploy-ConveneVariableBindings.ps1
deployment/windows-vm/Get-ConvenePublicationDiagnostics.ps1
deployment/windows-vm/Register-ConveneAgentTask.ps1
deployment/windows-vm/Test-ConveneLiveExpiry.ps1
deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md
```

The environment-local populated variable-ID file remains git-ignored. Never
invent IDs, copy desktop IDs, or repoint VM bindings to `gw_`.

### 4.7 Immediate VM diagnostic after desktop commissioning

The desktop commissioning frame was accepted by VM ingress as run
`8a7ba244-0535-476b-ba1c-961822e05cc9`, sequence `1`, but no VM-originated
`sim_` update was observed in Convene. An accepted frame updates engine `/state`
immediately; the estimator does not require a warm-up series. The remaining
boundary is therefore `/state` -> `RECLAIMStateBridge` -> `sim_vars.json` -> the
VM Convene agent/bindings. A single state also becomes stale after 15 seconds and
can expire between downstream heartbeats.

After pulling this branch on the VM, run from an elevated repository shell:

```powershell
.\deployment\windows-vm\Get-ConvenePublicationDiagnostics.ps1 `
  -ProofRun '8a7ba244-0535-476b-ba1c-961822e05cc9'
```

This read-only command reports the authenticated engine identity/state, bridge
payload and health, engine/bridge service states, VM Convene task state, and
matching non-secret log lines. Do not send additional frames until it establishes
whether the bridge and VM Convene agent are healthy.

If that path is healthy, the repository acceptance workflow deliberately sends
50 monotonically sequenced frames at 900 ms intervals so fresh state spans
multiple VM bridge and Convene heartbeats, then proves stale expiry:

```powershell
.\deployment\windows-vm\Test-ConveneLiveExpiry.ps1 `
  -PublicUrl 'https://renewal-conclude-associates-relief.trycloudflare.com'
```

This VM-only workflow validates predictive-state publication. A later sustained
stream from the real cRIO must still prove the complete desktop-originated path.

## 5. Endpoint 3 — Convene display and acceptance

Convene receives two independently attributable views:

### 5.1 Desktop gateway audit view

- Writer: desktop machine credential created by the pairing-code workflow.
- Prefix: `gw_`.
- Content: raw cRIO values plus gateway provenance (`gw_run_id`, `gw_seq`,
  source timestamp/state/chamber, etc.).
- Purpose: prove exactly what left the hardware/gateway boundary.

### 5.2 VM predictive/stakeholder view

- Writer: VM-specific state bridge/agent/binding.
- Prefix: `sim_`.
- Content: normalized measurements, estimates, margins, health/trust,
  freshness, forecast, advisory, and correlation/provenance fields.
- Purpose: stakeholder interpretation and Convene-native `.stp` visualization.

### 5.3 Required three-column correlation

For every live transition, compare:

```text
LabVIEW indicator | desktop gw_ submitted value | VM sim_ derived/state value
```

At minimum correlate:

```text
gw_run_id / gw_seq / gw_ts / gw_source_op_state / gw_active_chamber
sim_run_id / sim_seq / sim_ts_source / sim_source_op_state / sim_active_chamber
```

Raw and derived values may use different units or aggregation. For example,
`gw_PL_bottom1..4` are individual °C readings while `sim_PL_T_bed_meas` is a
Kelvin bank aggregate. Apply the conversions in `CONVENE_GW_MAPPING.md` before
declaring disagreement.

Convene ONLINE status alone is not acceptance. Require changing values,
freshness behavior, correct prefix ownership, and correlated source/sequence.

## 6. Secrets and identities — never cross these boundaries

| Secret/identity | Location/owner | May be used by |
|---|---|---|
| Desktop Convene agent token | User/SYSTEM `.convene_agent.json` on desktop | Desktop `Convene-Agent` and desktop gateway `gw_` publisher only |
| VM ingest token | VM ACL-protected `reclaim-ingest.env` | VM `/ingest` validation and desktop gateway HTTPS bearer after secure handoff |
| VM read token | VM ACL-protected engine/bridge secret material | VM state bridge/read acceptance only |
| VM Convene token/IDs | VM installed agent and protected local binding manifest | VM `sim_` binding only |
| Cloudflare Quick Tunnel URL | VM quick-tunnel state directory; temporary | Desktop `cloud_url` plus `/ingest` |

Never commit, print, email, or paste tokens into chat. Never copy either Convene
token to the other endpoint.

## 7. What is complete and what remains

### Complete on the desktop

- Direct Ethernet cable/link, laptop IP, Private profile, and scoped TCP 9070
  firewall rule.
- cRIO peer ping from laptop.
- Gateway staged under `C:\RECLAIM\pi_gateway`.
- Durable queue and loopback status software shakedown.
- Guarded HTTPS config finalizer and Windows boot-task installer.
- Desktop Convene pairing recovery/persistence tooling.
- Direct nonblocking `gw_` `/machine/publish` implementation.
- Live VM HTTPS configuration with exact secret ACL repair and verification.
- SYSTEM boot task running with cRIO-only ingress and loopback-only status.
- One retained, explicitly synthetic dual-output commissioning pass.
- Production loader rejects placeholder/non-TLS configuration.
- Tests and GitHub branch publication.

### Remaining/blocking

1. Configure the cRIO/LabVIEW sender for `192.168.1.1:9070` and emit one real
   newline-delimited frame.
2. Retain that first real frame and reconcile its names, types, units, chamber,
   state, and cycle semantics before tightening schema enforcement.
3. On the VM, prove the accepted run/source/sequence reaches the predictive
   engine rather than only the `/ingest` service.
4. Prove the VM's separate publisher writes fresh `sim_` stakeholder values to
   its own Convene machine while the desktop continues writing only `gw_`.
5. Decide whether to replace the temporary Quick Tunnel with a durable named
   tunnel or document/rehearse re-finalization whenever its hostname changes.
6. Exercise source-stop/stale behavior and confirm no stale value remains green.
7. Record desktop and VM restart recovery only after the live path passes.

## 8. End-to-end acceptance gate

Do not call the three-endpoint path live until all boxes pass:

- [ ] cRIO sends to `192.168.1.1:9070`; a real typed frame appears at `/latest`.
- [ ] Gateway `/health` shows **real cRIO** frames and no unexplained local drops.
- [x] Desktop direct Convene counters show successful `gw_` publication for the
      labeled synthetic commissioning frame.
- [x] Gateway queue drained over TLS through the current Cloudflare hostname for
      the labeled synthetic commissioning frame.
- [ ] VM `/state` carries the same run/source/sequence and fresh source time.
- [ ] Predictive values respond to the correct chamber and operating state.
- [ ] VM bridge publishes the separate `sim_` stakeholder set.
- [ ] Convene shows both distinct machines/namespaces with no duplicate writer.
- [ ] `gw_` raw values and `sim_` derived values agree after documented
      conversion/aggregation.
- [ ] Source stop produces stale/not-live behavior; no stale value remains green.
- [x] No command/advisory is connected to hardware actuation in the deployed
      desktop gateway path.
- [ ] Desktop and VM services recover after an intentional reboot/restart test.

## 9. Rollback boundaries

- Stop desktop gateway only:
  `Stop-ScheduledTask -TaskName 'RECLAIM-EdgeGateway'`.
- Stop temporary Cloudflare route: press `Ctrl+C` in its VM foreground window.
- Do not delete the desktop queue during rollback; retained frames are evidence.
- Do not unregister/delete either Convene machine while investigating values.
- Do not replace VM services or binding IDs without preserving their current
  inventory, release, secrets, logs, and rollback artifacts.
- Network rollback for the desktop is implemented by
  `pi_gateway/windows/configure-crio-network-firewall.ps1` and its saved state;
  use only after confirming the intended rollback target.
## 10. Read-next index

- Desktop execution: `pi_gateway/windows/README.md`
- Authoritative live tracker: `deployment/GATEWAY_GO_LIVE.md`
- Raw gateway audit mapping: `deployment/CONVENE_GW_MAPPING.md`
- VM engine handoff: `deployment/VM_ENGINE_HANDOFF.md`
- VM Windows scripts: `deployment/windows-vm/README.md`
- VM state bridge: `deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`
- Convene binding contract: `convene/RECLAIM_Convene_Live_Binding.md`
