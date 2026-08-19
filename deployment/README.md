# RECLAIM Deployment — Document Index (by integration stage)

This folder holds the deployment and handoff documentation for the RECLAIM Live
Twin. Every doc carries a **stage/status banner** under its title so you can tell,
at a glance, which phase of integration it belongs to. This index sorts them.

**Where to start for endpoint execution:** read
`THREE_ENDPOINT_HANDOFF.md`; it is the current strict Desktop / Windows Server
2025 VM / Convene boundary and pickup point. For the immediate 72-hour demo and
backend remediation, read
`RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md`, then
`RECLAIM_BACKEND_REMEDIATION_HANDOFF.md`. The implementation-session prompt is
`NewChat_Cloud_Pipeline_Convene_Fix_Prompt.md`, which includes the backend,
cloud-pipeline, and Convene sequence. `ClaudeCode_Backend_Remediation_Prompt.md`
remains the narrower backend-only prompt. For the **current VM engine session**,
read `VM_ENGINE_HANDOFF.md` first. For project-wide context, `HANDOFF.md` is the
full project story and `GATEWAY_GO_LIVE.md` is the authoritative go/no-go list.
`DEPLOYMENT_TOPOLOGY.md` is the authoritative platform record: Windows Server
2025 cloud VM plus Windows 10 gateway laptop.

## Integration stages

| Stage | Scope | Status (2026-08-19) |
|---|---|---|
| **0** | Offline gateway staging + outbound access base | DONE |
| **1** | Cloud predictive engine on the VM + Cloudflare route + tokens | Repository records prior proof; live VM inventory and current route handback pending |
| **2** | cRIO ingress link + scoped firewall | Desktop IP/link/firewall DONE; cRIO sender target and first real frame pending |
| **3** | Contract gates + three-column V&V (`gw_` audit) | Direct desktop publisher staged/tested; real cRIO-to-VM correlation pending |
| **4** | Separate desktop `gw_` and VM `sim_` Convene views | Mechanisms are distinct and documented; visible live-value acceptance pending |

Repository evidence records a proven VM ingestion-to-Convene sensing path,
including fail-closed expiry, but this desktop session did not inventory the live
VM. Overall hardware/live-cRIO status remains **NO-GO** until Stages 2–4 pass
with one real correlated frame. See
[`CONVENE_MISSION_OPERATIONS_RECAP.md`](CONVENE_MISSION_OPERATIONS_RECAP.md) for
the evidence and display decision.

The executable plan for the next endpoint session is
[`NEXT_SESSION_CD_REHEARSAL_PLAN.md`](NEXT_SESSION_CD_REHEARSAL_PLAN.md). It
splits work between the MacBook/VM lane and Adam's direct lab/gateway lane,
preserves the gateway's existing staged code, and targets a fast advisory-only
integration rather than production-grade CD.

## Documents

### Cross-cutting (read first — LIVING)

| Doc | Role |
|---|---|
| `THREE_ENDPOINT_HANDOFF.md` | **Current endpoint handoff:** strict Desktop / Windows Server 2025 VM / Convene ownership, separate `gw_` and `sim_` publishing mechanisms, present evidence, next commands, and acceptance gates. |
| `CRIO_TELEMETRY_LINK_HANDOFF.md` | Endpoint-specific architecture, discovery, wire contract, safety, and acceptance plan for cRIO/LabVIEW telemetry into the Windows 10 edge gateway. |
| `NewChat_cRIO_Telemetry_Link_Architecture_Prompt.md` | Self-contained prompt for the agent assigned to inspect and design the cRIO/LabVIEW telemetry producer seam. |
| `DEPLOYMENT_TOPOLOGY.md` | Authoritative deployment topology, OS boundaries, live data path, and ownership rules. |
| `RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md` | Critical path for a guaranteed synthetic nominal demo, two practice scenarios, and a separately gated live stretch path. |
| `RECLAIM_BACKEND_REMEDIATION_HANDOFF.md` | Implementation boundary and acceptance contract for RT-03/RT-05 backend fixes. |
| `NewChat_Cloud_Pipeline_Convene_Fix_Prompt.md` | **Primary fresh-chat prompt:** implement backend fixes, prove the cloud pipeline, and prepare isolated Convene reintegration. |
| `ClaudeCode_Backend_Remediation_Prompt.md` | Turnkey prompt for the focused backend implementation session. |
| `HANDOFF.md` | Full project story and current pickup point. Authoritative narrative. |
| `GATEWAY_GO_LIVE.md` | Living go/no-go punch list across all stages. Authoritative status. |
| `CONVENE_MISSION_OPERATIONS_RECAP.md` | 2026-08-18/19 VM integration evidence, root causes, stakeholder display taxonomy, variable types, and binding-ID worksheet. |

### Stage 1 — Cloud engine + egress (CURRENT)

| Doc | Role |
|---|---|
| `LUKE_VM_LOCAL_HANDOFF.md` | **Luke's active owner lane:** local source gate, VM deployment, endpoint acceptance, Adam rendezvous, and Convene cutover. |
| `VM_ENGINE_HANDOFF.md` | **Read first.** Full story of the endpoint (prior reboot/discrepancy + fix), the DO-NOT-DEBUG-IT-BACK guardrails, and the acceptance gates. |
| `VM_ENGINE_SESSION_BRIEF.md` | Turnkey brief for the VM engine session (objective + step outline). |
| `NewChat_Windows_VM_Predictive_Engine_Integration_Prompt.md` | Turnkey prompt for a Codex session running on the Windows VM: exact ingress-to-Convene boundary, Tuesday PASS evidence, and isolated rehearsal profiles. |
| `VM_ENGINE_RUNBOOK.md` | Executable Windows Server 2025 steps: deploy, ACL-protected secrets/state, WinSW service, cloudflared, verify, hand back. |
| `../docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md` | Authoritative fault/fix analysis (why the reboot was needed; §4.1 design of record). |
| `../docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md` | Red-team findings (RT-01..08), the command-authority mode (advisory default), and the deploy-blocking disposition. |
| `../cloud_engine/tools/redteam_ingest.py` | Live acceptance harness (LabVIEW-terminology emitter + pipeline/lifecycle assertions). Gate 2 in the handoff. |
| `../cloud_engine/tests/test_lifecycle_continuous.py` | Continuous-run regression test (Gate 1). |

### Stage 3 — Contract gates + V&V (reference, LIVING)

| Doc | Role |
|---|---|
| `CONVENE_GW_MAPPING.md` | `gw_` audit variables → gateway `/latest` jsonPaths (36 vars). Feeds the three-column V&V. |
| `CONVENE_REINTEGRATION_HANDOFF.md` | Repository-proven cloud/gateway binding contract, isolated rehearsal identities, field gaps, and the explicit external operator checkpoint. |
| `WINDOWS_VM_CONVENE_STATE_BRIDGE_HANDOFF.md` | Approved architecture and implementation contract for the independent Windows VM `/state` → `sim_vars.json` bridge. |
| `NewChat_Windows_VM_Convene_State_Bridge_Prompt.md` | Turnkey fresh-agent prompt to implement and test the Windows VM state bridge without mutating the VM. |
| `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md` | Lease-aware Windows service configuration, guarded installation, verification, logging, acceptance, and rollback procedure. |
| `windows-vm/README.md` | Index and security contract for the proven Windows VM deployment, recovery, diagnostics, and acceptance scripts. |

### Stage 0 — Base tooling / installers (reference)

| Doc | Role |
|---|---|
| `convene-setup-2.ps1` | Headless-by-default Windows VM Convene agent bootstrap: Python dependency setup, pairing, startup task, and `sim_vars.json` heartbeat transport. |

### Historical / superseded (kept for context — NOT current work plans)

| Doc | Stage | Why kept |
|---|---|---|
| `START_HERE.md` | 0 | Kickoff pointer for the staging session. Complete; superseded by `HANDOFF.md`. |
| `ClaudeCode_Staging_Prompts.md` | 0 | The staging session's prompt pack. Record of how the gateway was staged. |
| `ClaudeCode_Gateway_Reconciliation_Prompts.md` | 0.5 | Historical Pi→Windows-laptop naming reconciliation (GO_LIVE §9.6). Executed; not a live deployment plan. |
| `SSH_Tailscale_ClaudeCode_Setup.md` | 0 | Access setup. **SSH parts superseded** by the outbound-only model (§9.1); Tailscale/Claude Code steps still valid. |

## Conventions

- **Visualization:** the Unreal/Twinmotion path is retired. Live 3D is the
  **Convene-native `.stp` visualization** — it binds the published `sim_`
  variables to elements of a STEP model. Spec lives in
  `../convene/RECLAIM_Convene_Live_Binding.md`.
- **Guardrails (all stages):** `--production` accepts `mode: "live"` only;
  deploy **side-by-side**, never overwrite a running stack in place; the engine
  binds **loopback** and cloudflared is the only path in.
