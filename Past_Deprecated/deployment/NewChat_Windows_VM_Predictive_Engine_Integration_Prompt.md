# Fresh Codex Prompt — Windows VM Predictive-Engine Integration

> **Archived platform notice (2026-08-23):** the authoritative edge gateway is now the MacBook. Any Windows, Linux, Raspberry Pi, desktop-gateway, address, service, or task instructions below are historical evidence only and must not be used for the competition deployment. Use `deployment/DEPLOYMENT_TOPOLOGY.md` and `pi_gateway/macos/README.md`.

Copy the prompt below into a new Codex session running directly on the
cloud-hosted Windows Server 2025 VM.

---

You are the integration operator for the RECLAIM predictive-engine codebase on
the cloud-hosted Windows Server 2025 VM. Kubernetes is the outer hosting layer;
all guest work uses PowerShell, Windows services, NTFS paths, and Windows ACLs.
Do not create Linux, systemd, Docker, or Raspberry Pi deployment instructions.

Your job is to execute and verify the repository-owned pipeline inside this
boundary:

```text
BOUNDARY START
authenticated telemetry transmitted by the Windows 10 gateway
  -> Cloudflare public route
  -> POST /ingest on the loopback Windows predictive engine
  -> normalized reclaim.state.v1 GET /state
  -> independent Windows state bridge
  -> atomic C:\ConveneAgent\sim_vars.json
  -> headless VM Convene agent installed from this repository
  -> bound Convene sim_ variables and fail-closed operator view
BOUNDARY END
```

Today is Tuesday and the gateway/cRIO hardware is not the source. Generate
live-shaped test telemetry with `cloud_engine\tools\redteam_ingest.py` and send it
through the same public Cloudflare hostname, authenticated `/ingest` route, and
loopback port 8078 that the gateway will use Wednesday. Do not bypass Cloudflare
by posting only to localhost for the end-to-end proof.

The production engine correctly rejects envelopes whose `mode` is `harness`.
The acceptance tool therefore sends live-shaped frames with `mode: live` for the
pipeline test and separately proves that a `mode: harness` frame is rejected.
Call the source "synthetic acceptance telemetry" in evidence; never present it as
real cRIO telemetry.

## Read before changing the VM

Read these files completely, in this order:

1. `deployment/DEPLOYMENT_TOPOLOGY.md`
2. `deployment/VM_ENGINE_HANDOFF.md`
3. `deployment/VM_ENGINE_SESSION_BRIEF.md`
4. `deployment/VM_ENGINE_RUNBOOK.md`
5. `deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`
6. `deployment/CONVENE_REINTEGRATION_HANDOFF.md`
7. `convene/RECLAIM_Convene_Live_Binding.md`
8. `deployment/RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md`

Then inspect the exact source and tests used by the runbooks:

- `cloud_engine/push_ingest_dual.py`
- `cloud_engine/tools/redteam_ingest.py`
- `cloud_engine/windows/run-ingest-engine.ps1`
- `cloud_engine/windows/reclaim-ingest.xml`
- `convene_bridge/`
- `cloud_engine/windows/start-rehearsal-scenario.ps1`

## Non-negotiable scope

- Work only on the Windows VM, its repository checkout/release directory, engine
  service, Cloudflare route, state bridge, VM Convene agent installation, and
  bindings.
- Do not modify the Windows 10 gateway, cRIO, LabVIEW, PLC, firewall, hardware
  interlock, Kubernetes infrastructure, or any actuator path.
- Keep `/command` advisory and non-actionable. Do not connect it to hardware.
- Never print or commit live credentials. Keep ingest and read tokens distinct.
- This is an intentionally clean VM. Missing Python, `uv`, RECLAIM directories,
  WinSW, cloudflared, engine/bridge services, `C:\ConveneAgent`, the Convene task,
  and bindings are expected bootstrap work—not stop conditions.
- Preserve unexpected services, tunnels, files, ACLs, and `sim_vars.json` writers.
  Stop and report conflicts instead of overwriting them.
- Use one exact reviewed `TARGET_SHA`. Do not deploy a moving branch or an
  uncommitted checkout.

## Start with a read-only report

Before mutation, report:

- Windows edition/build and VM/workload identity;
- current branch, exact HEAD, worktree status, and remote;
- services/tasks/processes matching RECLAIM, Convene, Python, and cloudflared;
- owner and binding of port 8078;
- release, secret, state, log, bridge, and `C:\ConveneAgent` paths and ACLs,
  without secret contents;
- current Cloudflare route/hostname;
- Convene agent/task presence and every writer of `sim_vars.json`; and
- whether `C:\ProgramData\RECLAIM` persists across required VM/Kubernetes
  recovery events.

An empty result for the application/tooling checks is the planned baseline. Stop
only if the platform is not Windows Server 2025, the selected SHA is ambiguous,
port 8078 has an unexpected owner, an unexpected deployment exists, or another
writer owns `sim_vars.json`. Record infrastructure-level reschedule persistence as
verified or pending; absence of pre-created application directories is not a
blocker.

## Execute in this order

### Phase 0 — bootstrap the clean Windows VM

You are authorized and expected to install the deployment prerequisites and
create the repository-owned paths. Use elevated PowerShell:

```powershell
winget install -e --id Python.Python.3.13 --scope machine `
  --accept-package-agreements --accept-source-agreements
winget install -e --id Cloudflare.cloudflared `
  --accept-package-agreements --accept-source-agreements
py -3.13 -m pip install "uv==0.11.21"
```

Refresh the process PATH, then verify `py -0p`, `py -3.13 -m uv --version`, and
`cloudflared --version`. Retrieve the reviewed WinSW 3.x binary from its official
release channel, record its version and SHA-256, and use it only through the
repository templates. Create `C:\ProgramData\RECLAIM` and its release/service/
state/secret/log paths as directed by the runbooks.

Install and pair the headless VM Convene agent from the repository; do not enable
desktop streaming:

```powershell
$PairingCode = Read-Host 'Convene pairing code'
.\deployment\convene-setup-2.ps1 -PairingCode $PairingCode
```

This creates `C:\ConveneAgent`, registers `Convene-Agent` at startup as SYSTEM,
and includes `sim_vars.json` as the heartbeat's `simVars` object. Verify the task
and machine registration before installing the bridge.

### Phase 1 — exact release and local proof

Follow `VM_ENGINE_RUNBOOK.md` to stage `TARGET_SHA` beneath
`C:\ProgramData\RECLAIM\releases`, create the locked environment, and run the
complete tests and repository hygiene check. Record the exact Python version and
test counts.

### Phase 2 — Windows engine service

Configure the ACL-protected secret and durable identity paths outside the release
directory. Install/reconcile `RECLAIMIngestEngine` with the reviewed WinSW binary
and repository wrapper. Confirm it runs exactly:

```text
push_ingest_dual.py --host 127.0.0.1 --port 8078 --env earth_lab --production --max-frame-age-s 15
```

Prove port 8078 is loopback-only, `/health` responds, authenticated read routes
work, missing/wrong read credentials fail, logs contain no credentials, and an
engine restart preserves ingest identity/deduplication state.

### Phase 3 — real ingress route with synthetic acceptance telemetry

Preserve or establish the approved Windows cloudflared route from the public
hostname to `http://127.0.0.1:8078`. From a trusted PowerShell session, keep
credentials in environment variables and run:

```powershell
$env:RECLAIM_INGEST_TOKEN = '<private ingest value>'
$env:RECLAIM_READ_TOKEN = '<different private read value>'
python cloud_engine\tools\redteam_ingest.py --url https://<gateway-ingress-host>
Remove-Item Env:RECLAIM_INGEST_TOKEN, Env:RECLAIM_READ_TOKEN
```

The URL is the base hostname, not a localhost URL and not a URL ending in
`/ingest`. Require `20/20` checks. Correlate the accepted `run_id`, `source_id`,
and advancing `seq` with authenticated loopback `/state` and engine logs.

### Phase 4 — `/state` delivery to Convene

Follow `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`. The bridge uses the read
token only, polls only `http://127.0.0.1:8078/state`, and atomically replaces
`C:\ConveneAgent\sim_vars.json`. The newly installed headless VM Convene agent
remains the only heartbeat transport and the only `sim_` publisher.

Determine whether the VM agent adds the `sim_` prefix or expects it in the JSON;
prove exactly one prefix. Bind the process/provenance fields plus:

```text
sim_data_live
sim_bridge_status
sim_bridge_valid_until
sim_mode
sim_ingest_status
sim_state_age_ms
sim_run_id
sim_source_id
sim_seq
sim_op_state
```

Capture Convene evidence showing the same acceptance run/sequence that entered
through Cloudflare. The view must evaluate its own UTC clock against
`sim_bridge_valid_until`.

### Phase 5 — fail-closed proof

Stop the synthetic telemetry source. Prove Convene changes to `DATA NOT LIVE`
after the approved freshness/lease interval. Also prove the same outcome for a
stopped bridge or expired lease. Do not claim acceptance if Convene merely freezes
on the last good values.

## Tuesday PASS definition

Declare `PASS` only when all of these are evidenced for the exact `TARGET_SHA`:

1. Synthetic acceptance telemetry traverses the public Cloudflare hostname and
   authenticated production `POST /ingest` route into Windows loopback port 8078.
2. The acceptance harness reports `20/20` and `/state` advances with the correlated
   run/source/sequence.
3. The Windows bridge publishes that state atomically to `sim_vars.json`.
4. The installed VM agent delivers the correlated state to the bound Convene
   `sim_` fields.
5. Convene shows `DATA IS LIVE` only while status, freshness, and
   `bridge_valid_until` are valid, then shows `DATA NOT LIVE` after feed/lease
   expiry.
6. Exactly one `sim_` writer exists and no command/hardware authority changed.

Ingress without Convene evidence is `PARTIAL`. A local `/state` response alone is
not `PASS`. A Convene value that remains apparently live after lease expiry is
`FAIL`.

## Isolated rehearsal scenarios

These are separate GET-only demonstration services. They never use production
port 8078, production tokens, the production bridge, or the live `sim_`/`gw_`
namespaces. Start one profile per foreground PowerShell terminal from the exact
release root:

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal
.\cloud_engine\windows\start-rehearsal-scenario.ps1 power-outage
.\cloud_engine\windows\start-rehearsal-scenario.ps1 lunar
```

Expected profiles:

| Profile | Port | Expected result |
|---|---:|---|
| `nominal` | 8177 | `scenario=nominal`, `environment=earth_lab`, stable 2200 W heat-and-hold; cycle about 67 wall-clock seconds at 6x |
| `power-outage` | 8178 | 3500 W heating; history contains `S_PowerInterrupted` with `P_fwd=0` near 38 wall-clock seconds and `S_Restart` near 63 seconds; cycle about 75 seconds at 12x |
| `lunar` | 8179 | `scenario=nominal`, `environment=lunar_surface`, 2200 W heat-and-hold under lunar physics; cycle about 67 seconds at 6x |

Verify `/health`, `/state`, and `/history`; capture the power-outage history
during or immediately after its cycle so both transitions remain in the
600-frame buffer. Bind them only through the three
rehearsal identities/prefixes in `CONVENE_REINTEGRATION_HANDOFF.md`. Label every
view `SYNTHETIC REHEARSAL — ADVISORY ONLY`. Never tunnel ports 8177–8179 to the
production hostname.

## Final handoff

Return a concise evidence table with PASS/PARTIAL/FAIL for: exact source, local
tests, Windows service, public ingress, authenticated state, restart persistence,
bridge, `sim_vars.json`, VM agent, Convene correlation, lease expiry, single
writer, and each rehearsal profile. Include non-secret commands, timestamps,
run/sequence identifiers, paths, service names, and redacted screenshots/log
locations. List remaining blockers for Wednesday's Windows 10 gateway/cRIO work.
