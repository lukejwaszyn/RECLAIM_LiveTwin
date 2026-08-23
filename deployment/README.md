# RECLAIM Deployment — Document Index (by integration stage)

This folder holds the deployment and handoff documentation for the RECLAIM Live
Twin. Historical, superseded, and spent one-time material has been moved to
[`../Past_Deprecated/`](../Past_Deprecated/README.md) (with a manifest) so this
folder stays current. Most docs carry a **stage/status banner** under their title.

**Where to start**

- **cRIO acquisition → acceptance (the live thread):** read
  `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` (authoritative decision + gate
  definitions 0–5), then the current acceptance brief
  `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md` (supersedes `_HANDOFF.md`'s state).
- **Endpoint boundary:** `THREE_ENDPOINT_HANDOFF.md` — strict Desktop / Windows
  Server 2025 VM / Convene ownership.
- **Project-wide context:** `HANDOFF.md` (full story) and `GATEWAY_GO_LIVE.md`
  (authoritative go/no-go). `DEPLOYMENT_TOPOLOGY.md` is the platform record.
- **Demo / rehearsal:** `RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md` and
  `NEXT_SESSION_CD_REHEARSAL_PLAN.md` (nominal / power-outage / lunar scenarios).

## Integration stages (status 2026-08-23)

| Stage | Scope | Status |
|---|---|---|
| **0** | Offline gateway staging + outbound access base | DONE (records archived) |
| **1** | Cloud predictive engine on the VM + Cloudflare route + tokens | Sustained synthetic path proven; VM `sim_` display operator-confirmed |
| **2** | cRIO ingress link + scoped firewall + offline contract | Link + firewall DONE; offline contract DONE (55/67/70 + bench replay green at `3608872`); real first-frame acceptance pending |
| **3** | RT producer review + signed maps | OPEN — producer evidence questionnaire issued; maps UNSIGNED |
| **4/5** | Supervised one-frame + sustained + fault/restart acceptance | Pending Phase B cutover + named-owner go |

Overall live-cRIO status remains **NO-GO**; the stream is an explicitly labeled
engineering shadow until the gates close. See
`CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md` §7.

## Documents

### cRIO acquisition & acceptance — the current thread (LIVING)

Read roughly in this order.

| Doc | Role |
|---|---|
| `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` | **Authoritative cRIO source decision** and full gate definitions (0–5): existing 34-field record → direct RT TCP, PSP fallback, staged gates, acceptance, rollback. |
| `CRIO_ACQUISITION_OPTIONS_TRADE_STUDY.md` | Evidence-backed transport/authority trade study and controls discovery worksheet. |
| `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md` | The standing acceptance brief (role, boundary, endpoints, three-phase work). |
| `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md` | **Current pickup.** Updates the brief's state (pre-flight green, Gate 3 checklist issued, cutover scripted, PL bed-bank finding) and folds in the next-session build scope (interfacing/deployment code + 1-command installer + scenarios). |
| `CRIO_TELEMETRY_SOCKET_SETUP.md` | The single-socket contract, both ends (bind `192.168.1.1:9070`, framing, timeouts). |
| `CRIO_LABVIEW_PRODUCER_HANDOFF.md` | Exactly what the RT producer must emit (build spec). |
| `CRIO_TELEMETRY_WRITE_PATH_AUDIT.md` | Receiver/cloud behavior relied on (input-only receiver, bed-bank rule, command relay display-only). |
| `CRIO_SOURCE_RECORD_SIGNED_MAPS.md` | **UNSIGNED** worksheet controls must sign (channel/quality/state/chamber/cycle/time maps). |
| `CRIO_SOURCE_RECORD_DECISION_RECORD.md` | Gate 2 decision + the running evidence table (`Claim | status | evidence | owner | gate`). |
| `CRIO_SOURCE_RECORD_RUNBOOK.md` | Offline contract/parser/conformance/bench-replay runbook. |
| `CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` | Gate 3 evidence questionnaire the LabVIEW/controls team answers and countersigns. |
| `CRIO_GATEWAY_CUTOVER_RUNSHEET.md` | Ordered bench-VI → production-listener cutover (desktop/gateway side). |
| `CONVENE_FIRESTORE_INDEX_HANDOVER.md` | Ready-to-apply fix for the Convene backend owner: the missing `machineCommands` composite index that blocks rehearsal scenarios from reaching Convene. |
| `CRIO_INTERFACING_TROUBLESHOOTING_HANDOFF.md` | **Start here when the cRIO is connected and frames are not flowing.** Known-good baseline, first-frame checklist, fault ladder, and known non-bugs. |
| `LIFECYCLE_RESTART_AUDIT_RECORD.md` | Audit record of graceful-closure/restart handling, scenario targets, and the open `active_heating_s`/`S_Restart` semantics question. |
| `CRIO_PSP_LIVE_ADAPTER_HANDOFF.md` | NI-PSP live adapter — retained as the diagnostic/**fallback** source, not the primary seam. |

### Cross-cutting (read first — LIVING)

| Doc | Role |
|---|---|
| `THREE_ENDPOINT_HANDOFF.md` | Current endpoint handoff: strict Desktop / VM / Convene ownership, separate `gw_`/`sim_` publishing, evidence, acceptance gates. |
| `DEPLOYMENT_TOPOLOGY.md` | Authoritative topology, OS boundaries, live data path, ownership rules. |
| `HANDOFF.md` | Full project story and pickup point. Authoritative narrative. |
| `GATEWAY_GO_LIVE.md` | Living go/no-go punch list across all stages. Authoritative status. |
| `RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md` | Guaranteed synthetic nominal demo, two practice scenarios, gated live stretch. |
| `NEXT_SESSION_CD_REHEARSAL_PLAN.md` | Fast advisory-only integration plan; MacBook/VM vs lab/gateway lanes; nominal/outage/lunar scenarios. |
| `RECLAIM_BACKEND_REMEDIATION_HANDOFF.md` | Implementation boundary and acceptance contract for the RT-03/RT-05 backend fixes (implemented). |
| `CONVENE_MISSION_OPERATIONS_RECAP.md` | VM integration evidence, root causes, display taxonomy, binding-ID worksheet. |

### Stage 1 — Cloud engine + egress (VM) (LIVING)

| Doc | Role |
|---|---|
| `LUKE_VM_LOCAL_HANDOFF.md` | Luke's owner lane: local source gate, VM deployment, endpoint acceptance, Convene cutover. |
| `VM_ENGINE_HANDOFF.md` | Read first for a VM session: endpoint story, guardrails, acceptance gates. |
| `VM_ENGINE_SESSION_BRIEF.md` | Turnkey brief for the VM engine session. |
| `VM_ENGINE_RUNBOOK.md` | Executable Windows Server 2025 steps: deploy, secrets/state ACLs, WinSW, cloudflared, verify. |
| `../docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md` | Fault/fix analysis (§4.1 design of record). |
| `../docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md` | Red-team findings (RT-01..08), advisory-default command authority. |
| `../cloud_engine/tools/redteam_ingest.py` | Live acceptance harness. |
| `../cloud_engine/windows/start-rehearsal-scenario.ps1` | Scenario launcher: `nominal` (8177) / `power-outage` (8178) / `lunar` (8179) / `loss-of-data` (8181), advisory-only, never production port 8078. |

### Stage 3 — Contract gates + V&V (reference, LIVING)

| Doc | Role |
|---|---|
| `CONVENE_GW_MAPPING.md` | `gw_` audit variables → gateway `/latest` jsonPaths. Feeds three-column V&V. |
| `CONVENE_REINTEGRATION_HANDOFF.md` | Cloud/gateway binding contract, isolated rehearsal identities, operator checkpoint. |
| `WINDOWS_VM_CONVENE_STATE_BRIDGE_HANDOFF.md` | Architecture + implementation contract for the VM `/state` → `sim_vars.json` bridge. |
| `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md` | Lease-aware Windows service config, guarded install, verification, rollback. |
| `windows-vm/README.md` | Index + security contract for the proven Windows VM deployment/recovery/acceptance scripts. |

### CI/CD (reference)

| Doc | Role |
|---|---|
| `CI_CD_ARCHITECTURE.md` | CI/CD architecture for the live-data path. |
| `CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md` | Red-team integration handoff for the CI/CD lane. |
| `../docs/RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md` | Promotion baseline; read before promotion. |

### Stage 0 — Base tooling / installers (reference)

| Doc | Role |
|---|---|
| `convene-setup-2.ps1` | Headless-by-default Windows VM Convene agent bootstrap. |
| `CONVENE_VARIABLE_BINDINGS.example.json` | Example Convene variable-binding manifest (no live IDs/values). |

> **One-command installer (planned):** the next session builds a single idempotent
> full-stack installer/updater that pulls the current SHA and deploys gateway + VM
> engine + state bridge and can stand up the scenarios, wrapping the existing
> guarded per-component scripts in `pi_gateway/windows/`, `cloud_engine/windows/`,
> `convene_bridge/windows/`, and `deployment/windows-vm/`. Scope + acceptance are
> specified in `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md` §6-E.

## Archived material

Historical, superseded, and spent one-time session prompts now live in
[`../Past_Deprecated/`](../Past_Deprecated/README.md). That folder's README lists
every moved file, its origin, and why. Notably archived: the Stage-0 staging
records (`START_HERE.md`, the `ClaudeCode_*_Prompts.md` pack), the spent
`NewChat_*` session prompts, and the superseded PSP-selection cRIO docs
(`CRIO_TELEMETRY_LINK_HANDOFF.md`, `CRIO_PSP_ADAPTER_DEVELOPMENT_PLAN.md`).

## Conventions

- **Visualization:** the live 3D path is the **Convene-native `.stp` visualization**
  binding published `sim_` variables to STEP-model elements. Spec:
  `../convene/RECLAIM_Convene_Live_Binding.md`.
- **Guardrails (all stages):** `--production` accepts `mode: "live"` only; deploy
  **side-by-side**, never overwrite a running stack in place; the engine binds
  **loopback** and cloudflared is the only ingress; all predictive output stays
  **advisory** with no actuator authority.
