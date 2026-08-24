# RECLAIM Deployment — Document Index (by integration stage)

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

This folder holds the deployment and handoff documentation for the RECLAIM Live
Twin. Historical, superseded, and spent one-time material has been moved to
[`../Past_Deprecated/`](../Past_Deprecated/README.md) (with a manifest) so this
folder stays current. Most docs carry a **stage/status banner** under their title.

**Where to start**

- **Current role boundary:** `LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md` —
  Windows 10 owns live data; MacBook owns scenarios only.
- **cRIO acquisition → acceptance (the live thread):** read
  `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` (authoritative decision + gate
  definitions 0–5), then the current acceptance brief
  `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md` (supersedes `_HANDOFF.md`'s state).
- **Endpoint boundary:** `THREE_ENDPOINT_HANDOFF.md` — strict Windows live gateway /
  MacBook scenario host / VM / Convene ownership.
- **Project-wide context:** `HANDOFF.md` (full story) and `GATEWAY_GO_LIVE.md`
  (authoritative go/no-go). `DEPLOYMENT_TOPOLOGY.md` is the platform record.
- **This MacBook now:** `pi_gateway/macos/README.md` and
  `NEW_GATEWAY_SCENARIO_DEPLOYMENT.md` define the loopback-only scenario service.
- **Demo / rehearsal:** `RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md` and
  `NEXT_SESSION_CD_REHEARSAL_PLAN.md` (nominal / power-outage / lunar scenarios).
- **Scenario host:** `NEW_GATEWAY_SCENARIO_DEPLOYMENT.md`; cloud/VM scenario
  routing is prepared separately.

## Integration stages (status 2026-08-23)

| Stage | Scope | Status |
|---|---|---|
| **0** | MacBook scenario host | GO — loopback-only harness runtime and capture replay proven |
| **1** | Cloud predictive engine on the VM + Cloudflare route + tokens | Sustained synthetic path proven; VM `sim_` display operator-confirmed |
| **2** | cRIO ingress on Windows 10 live gateway | Separate live-data workstream; MacBook is excluded |
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
| `NewChat_cRIO_Source_Record_TCP_Implementation_Prompt.md` | Turnkey source-proof and controls-coordination prompt retained for implementation history and gate context. |
| `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md` | The standing acceptance brief (role, boundary, endpoints, three-phase work). |
| `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md` | **Current pickup.** Updates the brief's state (pre-flight green, Gate 3 checklist issued, cutover scripted, PL bed-bank finding) and folds in the next-session build scope (interfacing/deployment code + 1-command installer + scenarios). |
| `CRIO_TELEMETRY_SOCKET_SETUP.md` | Historical socket details; Windows 10 now owns the live cRIO interface. |
| `CRIO_LABVIEW_PRODUCER_HANDOFF.md` | Exactly what the RT producer must emit (build spec). |
| `CRIO_TELEMETRY_WRITE_PATH_AUDIT.md` | Receiver/cloud behavior relied on (input-only receiver, bed-bank rule, command relay display-only). |
| `CRIO_SOURCE_RECORD_SIGNED_MAPS.md` | **UNSIGNED** worksheet controls must sign (channel/quality/state/chamber/cycle/time maps). |
| `CRIO_SOURCE_RECORD_DECISION_RECORD.md` | Gate 2 decision + the running evidence table (`Claim | status | evidence | owner | gate`). |
| `CRIO_SOURCE_RECORD_RUNBOOK.md` | Offline contract/parser/conformance/bench-replay runbook. |
| `CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` | Gate 3 evidence questionnaire the LabVIEW/controls team answers and countersigns. |
| `CRIO_GATEWAY_CUTOVER_RUNSHEET.md` | Historical Mac cutover plan; superseded by the role-boundary decision. |
| `ENGINE_SIDE_UPDATES_HANDOFF.md` | Proposals for the `cloud_engine` owner (not applied): chamber params for rehearsal, `/state` freshness field, and the deferred batch-boundary edge. |
| `CONVENE_FIRESTORE_INDEX_HANDOVER.md` | Ready-to-apply fix for the Convene backend owner: the missing `machineCommands` composite index that blocks rehearsal scenarios from reaching Convene. |
| `NEW_GATEWAY_SCENARIO_DEPLOYMENT.md` | Current MacBook loopback scenario-host deployment and replay procedure. |
| `CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md` | Copy/paste VM-owner prompt for the proven live gateway-ack failure blocking `sim_*`. |
| `CRIO_INTERFACING_TROUBLESHOOTING_HANDOFF.md` | **Start here when the cRIO is connected and frames are not flowing.** Known-good baseline, first-frame checklist, fault ladder, and known non-bugs. |
| `LIFECYCLE_RESTART_AUDIT_RECORD.md` | Audit record of graceful-closure/restart handling, scenario targets, and the open `active_heating_s`/`S_Restart` semantics question. |
| `CRIO_PSP_LIVE_ADAPTER_HANDOFF.md` | NI-PSP live adapter — retained as the diagnostic/**fallback** source, not the primary seam. |

### Cross-cutting (read first — LIVING)

| Doc | Role |
|---|---|
| `LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md` | Authoritative live/scenario host ownership. |
| `THREE_ENDPOINT_HANDOFF.md` | Windows live gateway / MacBook scenario / VM / Convene boundaries. |
| `THREE_PATH_CLOUDFLARE_ACCEPTANCE.md` | MacBook production-component proof through HTTPS Quick Tunnels: all three scenarios correlated across exact-name gateway variables/`sim_*`, with explicit real-VM/Convene limits. |
| `DEPLOYMENT_TOPOLOGY.md` | Authoritative topology, OS boundaries, live data path, ownership rules. |
| `HANDOFF.md` | Full project story and pickup point. Authoritative narrative. |
| `GATEWAY_GO_LIVE.md` | MacBook scenario-host go/no-go; Windows live acceptance is separate. |
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
| `../tools/synthetic_crio.py` | MacBook loopback scenario source; publishes through the scenario Convene machine. |
| `../tools/replay_windows_data_stream.py` | Bounded parser/replayer for approved Windows desktop capture files. |

### Stage 3 — Contract gates + V&V (reference, LIVING)

| Doc | Role |
|---|---|
| `CONVENE_GW_MAPPING.md` | raw gateway audit variables → gateway `/latest` jsonPaths. Feeds three-column V&V. |
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
> full-stack installer/updater that pins the current SHA and deploys gateway + VM
> engine + state bridge and can stand up scenarios, combining the MacBook workflow
> in `pi_gateway/macos/` with guarded VM scripts in `cloud_engine/windows/`,
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
