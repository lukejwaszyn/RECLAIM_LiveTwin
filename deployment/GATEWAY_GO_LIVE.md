# RECLAIM Gateway — Go / No-Go Punch List

> **Stage:** cross-cutting (Stages 0–4 tracker) · **Status:** LIVING — authoritative
> go/no-go status. Update as items close; do not archive at cutover.

**Living document.** Started 2026-08-14 during the offline staging session
(cRIO disconnected, cloud endpoint not provisioned). Update it as items close;
do not archive it at cutover — §6 and §8 remain permanent fixtures.

**Scope:** everything between "the gateway code exists" and "live cRIO data is
flowing to the cloud and verified in Convene." Cross-references are to
`docs/RECLAIM_Remote_Gateway_Preflight.md` unless stated otherwise.

**Authoritative topology (2026-08-17):** the gateway is a Windows 10 laptop.
The cloud predictive-engine guest is Windows Server 2025 in Kubernetes-managed
infrastructure. There is no Linux host or Raspberry Pi in the live path. See
`DEPLOYMENT_TOPOLOGY.md`.

## How to read this

| Marker | Meaning |
|---|---|
| **DONE** | Completed and evidenced. Evidence cited inline. |
| **BLOCKED** | Cannot be done yet. The blocker is named. |
| **NOT DONE — DELIBERATE** | Achievable now, intentionally withheld. The reason is a safety constraint, not a scheduling one. Do not "helpfully" complete these. |

**Current overall status: partial live PSP engineering POC; a source-built USB
record is proven; full live remains NO-GO.** The physical link, gateway listener/task, protected cloud configuration,
sustained gateway-to-VM delivery, predictive processing, and independent Convene
`gw_`/`sim_` displays are commissioned with synthetic input. An input-only
Windows PSP adapter has also sent a partial live engineering stream: eight
NI-9213 thermocouple scans plus three raw NI-9205 scans. The evidence-gated
source profile exposes all eleven under audit-only scan names and supplies no
canonical PL/MT model measurement. The
remaining live gate is the authoritative mapping/scaling/metadata contract,
three-column correlation, stale behavior, and restart evidence across a full
physical cycle.

The PSP adapter is now a diagnostic fallback rather than the selected production
source. The selected direction is to preserve the existing USB logger and reuse
its source-built record through a bounded, lower-priority direct TCP branch after
the controls gates in `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` pass.

---

## 1. DONE — staging session 2026-08-14

| # | Item | Evidence |
|---|---|---|
| 1.1 | Repo intact; gateway test suite green on the gateway laptop | Current suite: `27 passed` (`C:\RECLAIM\pi_gateway` deployment venv). Covers the C1/H3 dead-letter contract, M7 seq high-water, M5 warn-once, §4.4 command relay, H7 config gates, the nonblocking direct Convene publisher, and guarded one-frame/five-minute Windows commissioning workflows. |
| 1.2 | Gateway staged to its deployment location | `C:\RECLAIM\pi_gateway` — refreshed non-destructively from repository commit `a5908387451d38d5ef08d30bea66ec3aee2e2a17`; 14 files copied, 0 failed. The venv, production config, queue, and timestamped pre-refresh config backup were preserved. |
| 1.3 | Deployment venv + runtime deps | `C:\RECLAIM\pi_gateway\.venv` (Python **3.13.0**). Installed: `pyyaml 6.0.3`, `requests 2.34.2`, `paho-mqtt 1.6.1` (correctly held `<2.0` by the M6 pin). |
| 1.4 | Package imports from the staged tree | `import reclaim_edge, reclaim_edge.main` → OK, resolved from `C:\RECLAIM\pi_gateway\reclaim_edge\__init__.py`, version `0.1.0`. |
| 1.5 | Durable buffer directory | `C:\ProgramData\RECLAIM` created. `queue.db` since created by the shakedown; inspected — tables `q`, `dl`, `meta`, `sqlite_sequence`, **all 0 rows**. No run/seq state carries into the live run. |
| 1.6 | `config.windows.yaml` built from preflight §4.2 | `C:\RECLAIM\pi_gateway\config.windows.yaml`, every field commented. All §4.2 values verbatim. `cloud_url` and `auth_token` are marked PLACEHOLDER — see §3. Loader parse confirmed; fail-fast guards proven by mutation (see §1.7). |
| 1.7 | Config fail-fast verified empirically, not just cited | Throwaway mutated copies raised as designed: missing explicit path → `FileNotFoundError`; `listen_prot` typo → `ValueError: unknown config key(s)`; `transport: htps` → `ValueError`; empty `auth_token` with live+https → `ValueError`. Code path `config.py:104-136` (review fix H7). |
| 1.8 | Local console shakedown — process healthy without hardware or cloud | `config.console.yaml` (differs from `config.windows.yaml` on exactly two lines: `transport: console`, `listen_host: 127.0.0.1`). Ran 30 s. Clean start, no traceback. `/health`, `/latest`, `/command`, `/` all answered. `uptime_s` 5.0 → 15.2 → 26.9 with the supervisor loop polling worker liveness every 0.5 s throughout — no silent thread death (`main.py:56-66`). Health lines logged on the configured 10 s cadence. |
| 1.9 | Loopback-only binding confirmed at the OS level | `netstat`: `127.0.0.1:9070` and `127.0.0.1:9080` LISTENING, same PID — never `0.0.0.0`. No inbound exposure created. Ports released on stop. |
| 1.10 | Convene `gw_` audit mapping derived | `deployment/CONVENE_GW_MAPPING.md` — 36 variables (9 envelope + 27 raw channels), each with jsonPath into `http://127.0.0.1:9080/latest`, type, `sim_` counterpart, unit conversion, and code citation. Derived statically from `status.py`, `framer.py`, `receiver.py`, `labview_map.py`. |
| 1.11 | Direct Convene `gw_` publisher implemented and commissioned | Convene-supplied `/api/machine/publish` contract integrated as `reclaim_edge.convene`: only scalar `gw_` names, one pending frame, nonblocking submit after durable VM enqueue, independent counters in `/health`, no `sim_` writes or VM acknowledgements. The five-minute synthetic proof delivered 296 audit updates and coalesced four while reporting zero failures. A partial live PSP engineering stream has since exercised the path; full-contract publication remains pending. |

---

## 2. PARTIAL — §4.1 input-only Windows PSP telemetry interface

**Selected topology:** the cRIO keeps its existing Scan Engine/network-published
variables. A separate input-only Windows adapter subscribes over NI-PSP and is
the sole TCP writer to the gateway on the same desktop. Do not configure or
deploy a new cRIO/LabVIEW TCP sender.

- [x] cRIO connected directly to the laptop Ethernet port
- [x] Laptop Ethernet retains the verified laboratory address `192.168.1.1/24`
- [x] cRIO Ethernet confirmed at `192.168.1.2/24`
- [ ] **No default gateway on either direct-link interface** — Wi-Fi remains
      Windows' default Internet route
- [x] Windows adapter PSP target confirmed as `192.168.1.2`; live values observed
- [x] Windows adapter TCP target confirmed as `192.168.1.1:9070`
- [x] Desktop-to-cRIO link and NI-PSP read path exercised without a cRIO deploy

**Recorded state on 2026-08-14:** Ethernet is `192.168.1.1/24`; `192.168.50.1`
is **not assigned** to any interface. Wi-Fi `104.39.44.203`, Tailscale
`100.103.166.57`, plus Hyper-V vSwitch `192.168.96.1` and link-local addresses.

**Onsite evidence 2026-08-19:** the direct cable negotiated **1 Gbps**. Windows
reported laptop `192.168.1.1/24` (manual) and resolved `192.168.1.2` to peer MAC
`00-80-2F-13-C9-10`; three laptop-to-cRIO probes succeeded in 0–2 ms. Wi-Fi
remained the only IPv4 default route and was associated over 802.11ac on channel
124 (5 GHz). The operator confirmed `192.168.1.2` is the cRIO and approved
preserving this working lab subnet instead of renumbering it to the originally
planned `192.168.50.0/24`. Ethernet was still **Public**, no process listened on
9070/9080, and no RECLAIM firewall rule existed. The reviewed, rollback-capable
script `pi_gateway/windows/configure-crio-network-firewall.ps1` was created but
has now been run from an elevated PowerShell session. It recorded the pre-change
state at `C:\ProgramData\RECLAIM\crio-network-firewall-before.json`, changed only
the Ethernet category from Public to Private, and made no address or route change.
Post-change laptop-to-cRIO probes again passed in 0–1 ms. The cRIO-side default
gateway remains unverified. Reverse-direction ping and cRIO-to-9070 reachability
are not requirements of the selected desktop-subscriber design.

**Manual listener proof 2026-08-19:** staging was refreshed from commit
`a5908387451d38d5ef08d30bea66ec3aee2e2a17`; the active config was corrected to
`listen_host: 192.168.1.1`. An isolated console-transport run used a separate
diagnostic queue and proved `192.168.1.1:9070` plus loopback-only
`127.0.0.1:9080` under one healthy process. `/health` reported zero errors and
`/latest` reported no frame received. No direct cRIO TCP connection arrived
during the 50-second window; that historical result is consistent with the
later-selected desktop PSP-subscriber topology. The diagnostic was stopped and
the production queue was untouched. A later foreground adapter POC exercised the
local TCP ingress, but no adapter startup task was installed.

**Consequence while unassigned:** `receiver.py:37` does a bare
`srv.bind((listen_host, listen_port))`. Binding an unassigned address raises
`WinError 10049`, the receiver thread dies, and M6 supervision exits the process
non-zero within 0.5 s. This is why the shakedown used `127.0.0.1` in a separate
console config — and why the boot task must not be installed yet (§6).

---

## 3. DONE for commissioning — cloud ingress and tokens

Endpoint 1 uses a protected live HTTPS configuration and the current Quick
Tunnel. Endpoint 2 accepted all 300 frames in the sustained proof and reported
the same active run. Tokens remain private and are not recorded in the repository.

- [x] Cloud dual engine deployed, bound **loopback only**, behind Cloudflare.
- [x] Current Quick Tunnel `/ingest` hostname finalized in the gateway config.
- [x] VM ingest credential stored in the VM secret file and protected gateway config.
- [x] Distinct VM read credential supports the state bridge and `sim_` publication.
- [x] Production ingest identity persistence is enabled.
- [x] Public `/health` is reachable from the Windows 10 gateway laptop.
- [x] Active config and token-bearing backup are restricted to SYSTEM and
      Administrators by the corrected exact-ACL finalizer.

Quick Tunnel hostnames remain ephemeral. Re-finalize Endpoint 1 whenever the
hostname changes, or replace the Quick Tunnel with an approved named tunnel for
unattended operation.

---

## 4. DONE — narrow defensive Windows Firewall rule for TCP 9070

The reviewed rule is active only on the Private direct-link Ethernet interface,
with local `192.168.1.1`, remote `192.168.1.2`, and TCP 9070. It was not required
by the diagnostic Windows PSP adapter, which reached the gateway locally. It is
the correctly scoped rule for the selected direct cRIO-to-gateway TCP direction,
subject to the controls deployment gates. Port 9080 remains loopback-only with no
inbound allow rule.

Applied rule shape (do not broaden):

```powershell
New-NetFirewallRule -DisplayName "RECLAIM cRIO telemetry (9070)" `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9070 `
    -Profile Private -InterfaceAlias Ethernet `
    -LocalAddress 192.168.1.1 -RemoteAddress 192.168.1.2
```

- [x] Rule created, Private profile only
- [x] Verified the Ethernet interface is classified **Private**, not Public
- [x] Verified the selected Windows adapter can reach the local 9070 listener
- [x] Confirmed the rule is restricted to interface alias `Ethernet`, so it does
      **not** apply to Wi-Fi even though Wi-Fi is also currently Private

Note: 9080 (status endpoint) must **never** get an inbound rule. It binds
loopback by design (`status.py:84`) and has no authentication (§9.4).

**Rule evidence 2026-08-19:** enabled inbound TCP 9070, local
`192.168.1.1`, remote `192.168.1.2`, Private profile, interface alias
`Ethernet`; no explicit inbound 9080 rule. The SYSTEM gateway now owns
`192.168.1.1:9070` and loopback `127.0.0.1:9080`.
Rollback is `configure-crio-network-firewall.ps1 -Mode Rollback` from an elevated
PowerShell. Two pre-existing broad Private allow rules named `python.exe` target
the user Python at
`C:\Users\latitude4\AppData\Local\Programs\Python\Python313\python.exe`, which
is used by the SYSTEM Convene agent, **not** the staged gateway venv executable.
They do not broaden this gateway rule but compound the open GW-01 management-plane
risk and must be dispositioned before a control-connected role.

---

## 5. DONE for commissioning — `RECLAIM-EdgeGateway` boot task

The guarded installer registered and started `RECLAIM-EdgeGateway` as SYSTEM
after the network, firewall, config, and exact-ACL checks passed. The task was
restarted once during commissioning to mint a fresh run ID after a VM-side
acceptance run retired the prior identity; the VM then accepted all 300 frames.

- [x] §3 cloud configuration and connectivity verified
- [x] Production config validated with protected ACL
- [x] `install-gateway-task.ps1 -Start` run elevated
- [x] Task runs as SYSTEM and owns the intended 9070/9080 listeners
- [x] Controlled stop/start produced a new run and resumed successful delivery
- [ ] Task starts at boot with no login; survives an intentional reboot
- [ ] Failure restart verified (kill the process → returns within 1 min)
- [x] Clean stop/start verified with queue preservation

This section applies only to the existing gateway task. The PSP adapter remains
a foreground engineering POC and has not been installed or approved as a startup
task.

Side effect to be aware of: the installer sets `RECLAIM_EDGE_CONFIG` as a
**machine-level** environment variable (`:22`), which persists beyond the task.

---

## 6. PARTIAL — §5 contract gates

Fresh sustained ingress, gateway-run supersession, VM predictive processing,
and both Convene views are proven synthetically. A partial cRIO-derived PSP
stream also traversed the live seam. Duplicate/cloud-restart, full-contract
source, and accepted-cadence freshness evidence remain open.

- [x] **Synthetic fresh-stream gate** — 300 fresh frames accepted in the
      sustained proof; Endpoint 2 processing and `sim_` display operator-confirmed.
- [x] **Engineering PSP transport gate** — eight Mod2 TC scans plus three Mod3
      analog scans reached the gateway from the input-only Windows subscriber.
      The evidence-gated source profile names them only
      `scan_Mod2_TC0_degC..TC7_degC` and `scan_Mod3_AI0_raw..AI2_raw`; its
      deployment is not claimed here. One frame every 3 seconds was observed as
      sustainable; nominal 1 Hz produced `timestamp_stale` rejection.
- [ ] **Full-contract real fresh frame** — one PSP-adapter v1 frame accepted;
      `/state` shows
      `schema_version: reclaim.state.v1`, `mode: live`, `run_id`, `source_id`,
      `seq`, `ts_source`, `cycle_id`, `source_op_state`, singular `op_state`,
      `PL_op_state`, `MT_op_state`, `ingest_status: accepted`
- [ ] **Cadence gate** — agree and sustain a source cadence without
      `timestamp_stale`; resolve why nominal 1 Hz failed before approving it
- [ ] **Duplicate** — repost the same frame → `duplicate`, ingestion count does
      not increment
- [ ] **Harness reject** — post `mode: harness` → rejected. The live-only proof
- [ ] **Stale gate** — batch of one stale + one fresh frame → HTTP **200** with
      per-frame results: stale = `rejected/timestamp_stale/final`, fresh =
      `accepted`. On the laptop, confirm the stale frame lands in `/health`
      `dead_letter`, **not** back in the queue
- [x] **Gateway-restart gate** — restart the gateway task; new `run_id` →
      cloud logs `RUN_SUPERSEDED`, keeps accepting, `active_run_id` updates,
      zero operator action
- [ ] **Cloud-restart gate** — restart the ingest service, repost the last
      accepted frame → `duplicate` (identity restored from
      `RECLAIM_INGEST_STATE`); `ingested_total` does not double-step
- [ ] **Freshness decay** — stop the feed, poll `/state`: `state_age_ms` grows
      and Convene flips to **DATA NOT LIVE** at the agreed limit

---

## 7. BLOCKED on full-contract real-source V&V — §6 three-column audit

**Blocker:** the PSP subscriber proved only a partial engineering POC. The selected
source-built-record path is not implemented or deployment-approved. Formal
validation still needs deployed-source identity, snapshot coherence, the approved
channel/scaling/validity map, and authoritative state, chamber, cycle, and time
sources. Cloud, predictive processing, and both Convene mechanisms are
commissioned synthetically.

- [x] Gateway running against the current authenticated cloud endpoint
- [x] Laptop registered as its own Convene machine publishing the `gw_` set
      per `deployment/CONVENE_GW_MAPPING.md` — separate namespace, read-only
      tap, never in the delivery path, **never writes `sim_*`**
- [x] Separate desktop `gw_` and VM `sim_` Convene displays confirmed for the
      sustained synthetic stream
- [x] **Record the evidence-gated partial key set:** eight audit-only
      `scan_Mod2_TCn_degC` names and three `scan_Mod3_AIn_raw` names (see §9.5)
- [ ] **Confirm the complete raw `vars` contract against a full live frame** and
      correct the mapping table if the stream differs
- [ ] Gate every absent field unavailable in Convene; retained `gw_MW_*`,
      `gw_PL_purge_pump`, or other older values must not appear current
- [ ] Unit conversions applied in the view (°C→K, Torr→kPa) so unlike units do
      not read as mismatches (`CONVENE_GW_MAPPING.md` §4.1)
- [ ] One full controlled sequence
      `S_BatchLoad → S_Evacuate → S_MicrowaveHeating → S_CoolDown → S_Complete`
      with all three columns in agreement at each transition
- [ ] Lag bound agreed with the team and met
- [ ] §4.5 RF coexistence check: Wi-Fi pinned to 5 GHz, `last_ack_age_s` and
      `dead_letter` watched **during** `S_MicrowaveHeating`

Both separate Convene writers are commissioned synthetically. Full-contract
three-column acceptance remains blocked on the authoritative PSP mapping and
metadata sources, not on deployment of a cRIO TCP sender.

---

## 8. Critical path

```text
§2 cRIO PSP link + Windows adapter ──┐
                                    ├─→ §4 listener/network safety
§3 cloud + tokens ───────────────────┘       │
                                             v
§5 gateway task ─→ §6 contract gates ─→ §7 V&V ─→ Convene cutover
```

Sections 3–5 and the downstream synthetic path are complete. Section 2 has a
partial live engineering proof; the critical path is now its full approved
mapping, scaling, metadata, cadence, and §6/§7 correlation evidence.

---

## 9. Environment deviations found during staging

These are real findings from this laptop, not doc nitpicks. Each needs a
decision from someone.

### 9.1 Preflight §1 remote access — RESOLVED 2026-08-17

The original §1 specified an OpenSSH server and tunneled status endpoint. The
preflight now records the actual outbound-only model: TeamViewer for hands-on
administration, Tailscale for the approved private network, and the existing
Convene agent for its narrow heartbeat/audit role.

The machine enforces a WDAC code-integrity policy and blocks inbound listener
services. **Do not attempt to stand up SSH/RDP listeners on this box.**

Gateway status remains loopback-only. Do not expose port 9080 through a status
tunnel because the endpoint has no application authentication (§9.4).

- [x] Preflight §1 rewritten around the approved outbound-only access model

### 9.2 Python version drift

Preflight §4.3 says "install Python 3.10+" and shows `py -3.10`; the staging
prompt pack assumed 3.12. **This box has only Python 3.13.0.** The venv was
built with `py -3.13`. 3.13 satisfies the 3.10+ target and all 10 gateway tests
pass on it, but no one has stated 3.13 as a supported version.

- [x] Python 3.13 is a supported target in the locked project/CI matrix; retain
      the staged 3.13 venv and re-run the locked gateway suite before go-live

### 9.3 Graceful shutdown path untested

The shakedown was terminated by an external kill, which on Windows does not
deliver a POSIX SIGTERM to Python, so `main.py`'s `_sig` handler never ran — no
`shutdown requested` / `stopped` lines. Thread liveness was proven by other
means (§1.8), but the clean-stop path — handler → `stop.set()` → thread joins →
`buffer.close()` → exit 0 — has **not** been exercised.

This matters because §5's task behavior ("never restarts a clean operator stop")
depends on that path producing exit 0.

- [ ] Run `python -m reclaim_edge.main` in an interactive console, press
      **Ctrl+C**, confirm the last two log lines are `shutdown requested` then
      `stopped`, and that the exit code is 0

### 9.4 Status server has no authentication

`status.py:72-86` has no token check on any endpoint; `/latest` serves raw
process telemetry. Safe today only because it binds `127.0.0.1` and the Convene
agent is local. Never give 9080 an inbound firewall rule. If it is ever
tunnelled, the tunnel must carry the authentication.

- [ ] Decide and document the policy before any tunnel exposes 9080

### 9.5 The full raw channel contract is only partially observed

`CONVENE_GW_MAPPING.md` §3 lists the target `vars` keys from the docx export
reproduced at `labview_map.py:206-216`. The live PSP transport POC observed only
eight Mod2 thermocouple scans and three Mod3 analog scans. The evidence-gated
source profile names them `scan_Mod2_TC0_degC` through
`scan_Mod2_TC7_degC` and `scan_Mod3_AI0_raw` through
`scan_Mod3_AI2_raw`; it supplies no canonical `PL_*`, `MT_*`, `MW_*`, process
flag, or authoritative metadata source. With `strict_fields: false` the gateway
forwards whatever arrives, so absent or mismatched names do not error;
corresponding canonical `gw_`/`sim_` fields are absent from the current frame.

The raw-name quarantine follows new controls evidence. The operator-panel
screenshot at 2026-08-19 22:37:54 EDT and sequence 1984 about 97 seconds later
contradicted the former `TC2 -> MT_top` and `TC5..TC7 -> PL_bottom2..4`
assignments. Repeated values near 1379 were non-identifying and do not establish
invalid semantics. An offline replay showed that old TC2/TC3 aliases could form
a false complete MT measurement and drive `CRITICAL`/`SAFE_STATE`, so all eight
Mod2 process aliases are withheld until an approved, versioned mapping/quality
profile exists. This is a source/review correction, not a deployment claim.

Convene can retain a value from an older synthetic or prior frame even when the
current canonical frame omits that field. Availability must therefore be gated
on current-frame presence plus matching provenance/freshness. In particular,
retained `gw_MW_*` and `gw_PL_purge_pump` values are unavailable, not live POC
measurements.

- [x] Retain and document the partial 8-raw-Mod2 + 3-raw-Mod3 key set
- [ ] Capture a full-contract adapter frame from `/latest`, diff its `vars` keys
      against the mapping table, correct the table, and only then consider
      `strict_fields: true`
- [ ] Approve scaling and renaming for the three NI-9205 scan values
- [ ] Prove absent-field unavailable gating in both audit and stakeholder views

### 9.6 Historical Pi-vs-laptop naming drift (`CODE_REVIEW.md` H6) — CLOSED

`README.md`, `FIXES.md`, and the architecture doc described a "Raspberry Pi 3B+
gateway" while the deployment is a Windows laptop; the preflight filename still
said `Pi` though its title already said laptop.

- [x] Prose and diagrams reconciled across `README.md`, `FIXES.md`, and
      `docs/RECLAIM_Live_Telemetry_Architecture.md`
- [x] Preflight renamed to `docs/RECLAIM_Remote_Gateway_Preflight.md`; all
      references updated
- [x] `FIXES.md` carries a dated platform note, so a 2026-08-10 changelog is
      not silently rewritten. Pi-specific *rationale* is retained where it
      explains why a fix exists (M5 warn-once and the bounded dead-letter table
      were driven by SD-card wear)
- [x] The retired Linux service unit was removed; the live gateway uses the
      Windows Scheduled Task template.
- [x] The `pi_gateway/` directory name is retained as a repository compatibility
      name only. It does not identify the deployment platform.

### 9.7 Historical Tailscale `reclaim-pi` node is offline

A `reclaim-pi` node exists in the tailnet but is offline. If it is a retired
artifact of the earlier Pi plan, remove it so it cannot be confused for a live
gateway.

- [ ] Confirm disposition

---

### 9.8 Convene agent — RESOLVED 2026-08-15, now running as SYSTEM at boot

**Was:** not running at all. Checked 2026-08-15 12:27 — no agent process,
service, or scheduled task; no Python process running anywhere; no `Run`-key
entry. `%USERPROFILE%\.convene` held only `convene_agent.py`.

**Root cause:** the agent had paired successfully on 2026-08-14 16:19
(`C:\Users\latitude4\.convene_agent.json`, 119 B, machine ID
`6xaiDIfauON8lGDVy2s1`) but had **no persistence mechanism** — it ran from a
console and died with it. The briefing's "paired and heartbeating" was true of
the pairing, not of any ongoing heartbeat.

**Now:**

- [x] Agent started and confirmed heartbeating (30 s interval); saved
      credentials reused, so no duplicate machine was registered
- [x] Credentials copied to `C:\Windows\System32\config\systemprofile\` —
      required because the agent reads `~/.convene_agent.json`, and SYSTEM's
      `~` is the SYSTEM profile, not the user profile
- [x] Scheduled Task **`Convene-Agent`** registered: `AtStartup` trigger,
      SYSTEM / RunLevel Highest, restart every 1 min on failure, no execution
      time limit, starts on battery. Launches
      `C:\Users\latitude4\.convene\run-agent.cmd`
- [x] Verified: exactly one agent process, owner `NT AUTHORITY\SYSTEM`, three
      established HTTPS sessions to the backend; `agent.log` shows
      `OK Using saved credentials` + `Heartbeating every 30s`
- [ ] **Confirm it comes back after a real reboot** — the boot trigger is
      registered but has not yet survived an actual restart
- [ ] Confirm in Convene that the machine shows as connected

**2026-08-19 desktop re-audit:** the persisted task and interactive profile had
diverged. SYSTEM still used revoked machine `6xaiDIfauON8lGDVy2s1` (heartbeat
HTTP 401), while the user profile held `NziS5l2uUARcPa8DUtQn`. A validation
heartbeat made the latter visible again, but the backend returned HTTP 500 after
updating presence. The response exposed the exact backend defect: Firestore is
missing the composite `machineCommands` index over `machineId`, `status`, and
`createdAt`. Until the Convene backend owner creates that index, the heartbeat
cannot return `autoVars`, so visibility alone does not prove telemetry. The
gateway now bypasses that failed response for its audit tap by sending only
`gw_` scalars through `/machine/publish` on a nonblocking one-frame worker. The
Firestore index still blocks the separate heartbeat/command response and remains
a Convene backend defect.

A guarded desktop-only audit/repair tool now lives at
`pi_gateway/windows/repair-convene-desktop-agent.ps1`. It never prints tokens,
does not touch VM bindings, and can persist an existing desktop identity for the
SYSTEM task with an explicit degraded-heartbeat acknowledgement. A test pairing
created machine `2rItUt06wMkwtuexiy89`, which Convene detected, but its one-time
token was intentionally not retained after the failed first heartbeat; remove
that unused record from Convene when practical.

**Logging:** the task appends to `C:\Users\latitude4\.convene\agent.log`
(`python -u`, unbuffered). This did not exist before and is the only on-disk
evidence the agent is alive — it grows unbounded, so rotate or truncate it
periodically.

### 9.9 Security posture of the Convene agent — read before extending it

The agent is a **remote-management agent, not a metrics reporter**. Recorded
here because it materially changes this laptop's exposure:

- `command_loop` polls the Convene backend every 2 s and executes whatever
  shell commands it returns, posting stdout/stderr/exit code back
  (`run_terminal_cmd`). `collect_from` also supports a `shell` collector type
  that runs arbitrary commands each heartbeat.
- It now runs as **SYSTEM at boot** (chosen deliberately — see §9.8), so that
  remote shell has full administrative rights on this machine.
- This is an outbound-polling design, so it works despite the WDAC block on
  inbound listeners. Note the consequence: it delivers the remote-access
  capability preflight §1 could not (§9.1), but through a third-party control
  plane rather than an authenticated tunnel the team operates.

**Never run the agent with `--desktop` on this machine.** That path sets
TightVNC `UseVncAuthentication=0` and `AllowLoopback=1` — screen sharing with
the VNC password disabled — then publishes it via a random
`trycloudflare.com` quick tunnel whose hostname is the only secret. The
launcher `run-agent.cmd` carries a comment saying so.

- [ ] Confirm the team accepts a SYSTEM-level third-party remote shell on the
      gateway laptop, and record it wherever §9.1's access model is decided
- [ ] Decide who may issue commands from the Convene side, and whether that
      account set is access-controlled

## 10. Changelog

| Date | Change |
|---|---|
| 2026-08-20 | Source discovery proved that `Data Stream.vi` initializes timestamp-named files beneath `U:\Data Stream` and retained captures contain repeating 30-, 32-, and stable 34-field records. The files lack per-record time and authoritative state/chamber/cycle metadata; early generations contain delimiter defects. Per-item PSP is retained as a diagnostic engineering POC. The selected production direction is now the existing source-built record through a bounded lower-priority direct TCP branch to the existing gateway, with a one-string shared variable as the controls fallback. All RT changes and full-live declaration remain NO-GO pending deployed-source, coherence, authority, safety, rollback, and supervised acceptance gates in `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`. |
| 2026-08-19 | Reconciled the selected live-source topology to the new input-only Windows NI-PSP subscriber: the cRIO remains unchanged and publishes existing Scan Engine variables; the desktop adapter is the sole TCP writer to the gateway. Recorded transport of eight Mod2 TCs plus three `scan_Mod3_AIn_raw` values at an observed sustainable three-second cadence. Later panel/sequence correlation contradicted several provisional process aliases, and offline replay exposed a false MT critical/safe-state path, so the evidence-gated source profile now quarantines all eleven as `scan_Mod2_TCn_degC`/`scan_Mod3_AIn_raw`; revised-profile deployment is not claimed. No `MW_*`, process fields, or authoritative cycle/state/chamber metadata were proven. Full-cycle acceptance and adapter deployment remain NO-GO, and retained Convene values for absent fields must be gated unavailable. |
| 2026-08-19 | Downstream synthetic commissioning PASS: after an intentional gateway restart generated fresh run `df24bf58-b2e5-4d80-90c1-2b41e21ff7a2`, the guarded five-minute stream sent 300 frames in 300.019 s; gateway receive and VM ingest deltas were both 300, desktop Convene delivered 296 and coalesced four, with zero failures, zero new dead letters, and an empty final queue. The operator confirmed VM predictive processing and the separate `sim_` Convene display. Full-contract PSP-adapter input and real-source correlation/recovery gates remained NO-GO. |
| 2026-08-19 | Integrated Convene's supplied direct `/machine/publish` contract into the gateway. The one-frame best-effort worker publishes only canonical `gw_` scalars after durable VM enqueue, exposes health counters, and cannot block/acknowledge the VM queue. The initial staging note was later superseded by the live protected configuration and sustained commissioning proof above. |
| 2026-08-19 | Hardened the desktop production handoff: live HTTPS config now rejects placeholder/non-HTTPS/non-`/ingest` destinations and disabled TLS; added secret-prompting config finalization with protected backups; replaced the task installer with guarded network/firewall/ACL/config gates; and published `pi_gateway/windows/README.md`. Fresh verification: 20 gateway tests and 63 bridge/operator-workflow tests passed; all changed PowerShell parsed cleanly. |
| 2026-08-19 | Reconciled the desktop Convene identity and found the backend's missing Firestore `machineCommands(machineId,status,createdAt)` index. Added secret-safe audit/repair tooling, then adopted Convene's documented direct `/machine/publish` contract for `gw_`: a bounded best-effort worker receives the same canonical frame only after durable VM enqueue and cannot block or acknowledge the VM path. Heartbeat/commands remain degraded by the backend index, while direct publish is independently testable. |
| 2026-08-19 | Refreshed `C:\RECLAIM\pi_gateway` from commit `a590838`, corrected the active bind to `192.168.1.1:9070`, installed locked pytest 9.1.1 in the staging venv, and passed all 11 gateway tests plus config/import gates. Reapplied and independently verified the Private profile and cRIO-only firewall rule. A 50-second isolated manual run proved the real 9070 listener and loopback-only 9080 status endpoint without touching the production queue or cloud; no source frame arrived, so the source-adapter seam remained open. The local Convene SYSTEM agent is running with live backend TLS connections, but Enterprise sign-in and `gw_` collector configuration remain. |
| 2026-08-19 | Onsite physical link established at 1 Gbps; laptop `192.168.1.1/24` and operator-confirmed cRIO `192.168.1.2/24` preserved as the approved lab subnet. Laptop-to-cRIO ping passed; Wi-Fi remained the only default route on 5 GHz. Applied the rollback-capable network script: Ethernet is Private and TCP 9070 is allowed only from the cRIO to the laptop on that interface; 9080 remains unopened. This record predates selection of the desktop PSP subscriber; reverse ping and cRIO-to-9070 reachability are not requirements of that selected topology. |
| 2026-08-17 | Corrected the authoritative live topology to a cloud-hosted Windows Server 2025 VM in Kubernetes-managed infrastructure and a Windows 10 gateway laptop; retired Linux service units, rewrote VM/preflight procedures for Windows, and closed §9.1/§9.2 documentation decisions. |
| 2026-08-15 | Handoff docs authored — `deployment/HANDOFF.md` (full project story) and `deployment/VM_ENGINE_SESSION_BRIEF.md` (turnkey brief for the cloud VM session). The Convene agent's always-on-at-boot status (§9.8) is framed there as the **architectural base** for the deferred ingress/egress build. Egress tunnel decision recorded: Cloudflare **quick tunnels** first, named tunnel + domain when interoperability warrants. Ingress/egress bring-up deliberately deferred. |
| 2026-08-15 | Convene agent started and made boot-persistent as SYSTEM (task `Convene-Agent`); §9.8 closed, §9.9 added recording its remote-shell capability. |
| 2026-08-15 | §9.6 closed — Pi-vs-laptop naming reconciled across `README.md`, `FIXES.md`, the architecture doc, and the preflight filename (now `RECLAIM_Remote_Gateway_Preflight.md`); two sub-items left open. §9.8 added: Convene agent confirmed **not running**, blocking §7. |
| 2026-08-14 | Created. §1 populated from the offline staging session (repo verify, staging, config, console shakedown, `gw_` mapping). §2–§8 opened as blocked/deliberate. §9 findings recorded. |
