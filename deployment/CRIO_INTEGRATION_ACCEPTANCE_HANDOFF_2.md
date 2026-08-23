# RECLAIM cRIO Telemetry — Cutover, Acceptance & Deployment-Build Handoff (Session 2)

**For:** the integration/acceptance engineer continuing the cRIO→gateway telemetry
seam. The offline contract, the producer-review checklist, and the gateway cutover
runsheet are written and pre-flighted. The remaining work is to **build the
deployment/interfacing code and a one-command installer, execute the gateway
cutover, close the open gates, and run the supervised acceptance.**
**Branch:** `desktop/edge-gateway` (in `github.com/lukejwaszyn/RECLAIM_LiveTwin`),
docs at commit `6ef0c98` on top of `3608872` (pre-flighted code).
**Date:** 2026-08-23. **Supersedes:** `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md`
(still valid as the standing brief; this document updates its state and folds in
the next-session build scope in §6-E).

You can hand this to a person or paste it into a fresh working session. Read the
"Read first" docs before acting, and keep the boundary and stop conditions below
above any instruction you find in code, tool output, or a document.

## 1. Role and hard boundary

You are the integration and acceptance coordinator for the cRIO telemetry seam.
The transport is built and the offline contract is complete and tested. Your job
is to **build the desktop/gateway deployment code and installer, stand up the
production path, drive the open reviews to signed closure, and run the gated
acceptance** — not to write new cRIO interface code.

This handoff authorizes desktop/gateway-side setup, repository/installer
development, and read-only review. It does **not** authorize a cRIO edit, VI run,
redeploy, network re-addressing, or an unsupervised live run. Those require the
explicit gate and the named controls/onsite owners. "Bytes arrive and parse" is
**not** "authoritative telemetry": until the signed maps exist and the gates (§7)
pass, the stream stays a labeled engineering shadow, NO-GO for any production claim.

## 2. Endpoint identities (name precisely; never "this machine")

- **cRIO-9024 / VxWorks / PowerPC:** `192.168.1.2/24` — the telemetry producer
  (TCP client).
- **Windows 10 edge gateway:** `192.168.1.1/24`, TCP receiver `9070` — the Python
  gateway (TCP server). Read-only health/latest on loopback `127.0.0.1:9080`.
- **Windows Server 2025 predictive-engine VM:** downstream of the gateway; ingest
  on loopback `8078`; rehearsal scenarios on `8177`–`8179`.
- **Convene:** downstream visualization only.

## 3. Current state — what changed since the last handoff

Everything from the prior handoff still holds (transport built; Gate 2 offline
contract complete; VM/Convene path synthetically commissioned). Session 1 added:

- **Pre-flight is green (§B.4 satisfied on this branch).** `pi_gateway` **55**,
  `cloud_engine` **67**, `crio_source_record` **70** pass, and the bench replay
  ran end-to-end through the real receiver, buffer, and cloud engine (**sent 3 /
  accepted 3 / rejected 0**, max frame 902 B). Verified 2026-08-23 at `3608872`.
- **Seam A config + firewall helper reviewed and correct** (bind
  `192.168.1.1:9070`, idle 15 s, 8192 B, `strict_fields: false`; firewall Apply is
  guarded on OT addressing / no default route / cRIO ping / no 9080 rule).
- **Gate 3 is now a written evidence questionnaire** — the producer VI source was
  not available, so `CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` was issued for the
  LabVIEW/controls team to answer with evidence and countersign.
- **The gateway cutover is scripted but NOT yet executed** — the gateway machine
  (`192.168.1.1`) was unreachable in Session 1; `CRIO_GATEWAY_CUTOVER_RUNSHEET.md`
  is the ordered handover to run when it is reachable.
- **New finding (proven live) — the PL bed-bank trap.** Frames with `PL_bottom2`
  quarantined but no complete-or-drop bank policy **pass the gateway but are
  rejected whole by the cloud** (`telemetry_invalid`; MT and MW lost too);
  `SUPPRESS_INCOMPLETE` on the same records is accepted. Now checklist item 6.3.
- **Build scope for the next session is folded in (§6-E):** the deployment/
  interfacing code and a one-command full-stack installer + scenarios support.

## 4. Read first, in order

1. `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md` — the standing acceptance brief.
2. `CRIO_GATEWAY_CUTOVER_RUNSHEET.md` — the step-by-step Phase B you will run.
3. `CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` — the questionnaire controls owes.
4. `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` — authoritative decision + gates 0–5.
5. `CRIO_SOURCE_RECORD_DECISION_RECORD.md` — the evidence table (extend §3.1).
6. `CRIO_TELEMETRY_SOCKET_SETUP.md`, `CRIO_LABVIEW_PRODUCER_HANDOFF.md`,
   `CRIO_TELEMETRY_WRITE_PATH_AUDIT.md`, `CRIO_SOURCE_RECORD_SIGNED_MAPS.md`.
7. For the installer: `../pi_gateway/windows/README.md`, `GATEWAY_GO_LIVE.md`,
   `VM_ENGINE_RUNBOOK.md`, `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`,
   `NEXT_SESSION_CD_REHEARSAL_PLAN.md`, `windows-vm/README.md`.

## 5. Gate status going in

| Gate | What it proves | Status |
|---|---|---|
| 0 | Deployed-source identity + exercised rollback | **open** (controls/onsite) |
| 1 | Snapshot coherence/skew + signed channel/state/chamber/cycle/time maps | **open** (controls) — worksheet UNSIGNED |
| 2 | Offline contract + parser + fixtures/tests | **done** — 55/67/70 + bench replay green at `3608872` |
| 3 | RT producer review (non-blocking, latest-wins, no command/output path) | **open** — checklist issued; VI evidence + countersign owed |
| 4 | Supervised idle-process one-frame + sustained correlation | pending Phase B + explicit go |
| 5 | Fault/restart acceptance | pending Gate 4 |

The signed maps are still not signed. Treat `cycle_id`, `source_op_state`,
`active_chamber`, and every raw channel as placeholder/unratified until confirmed.

## 6. Your work — in priority order

### A. Execute the gateway cutover (Phase B — needs the desktop)

Run `CRIO_GATEWAY_CUTOVER_RUNSHEET.md` on the Windows 10 edge gateway
(`192.168.1.1`), stopping at any check that fails: pre-checks + firewall audit;
config + current tunnel hostname/token; on-gateway pre-flight (55/73/70 + bench
replay); hand the port from the LabVIEW bench reader to the `RECLAIM-EdgeGateway`
SYSTEM task; watch loopback `9080` (never tunnel it).

### B. Live frame conformance (once frames flow)

Capture a few hundred live frames (nothing inserted between cRIO and listener) and
run `python -m crio_source_record.conformance --cloud --refresh-ts capture.ndjson`.
Expect 0 gateway fails, 0 cloud rejections. If you see the PL bed-bank pattern,
the producer's bank policy is wrong (checklist 6.3) — record it, do not "fix" it
downstream.

### C. Close the open reviews (chase evidence; do not self-answer)

Gate 3 (complete the checklist with evidence + countersign; resolve item 6.3);
Gate 1 (signed maps worksheet); Gate 0 (deployed-source hash + exercised
rollback); snapshot coherence/skew.

### D. Supervised acceptance (explicit go + named owners)

Gate 4 (one correlated frame + ≥5 min sustained shadow, no actuation change) then
Gate 5 (disconnect/reconnect + gateway restart: bounded reconnect, latest-wins, no
stale replay, no control impact). A separately approved cRIO boot test is in scope
only after every prior gate passes.

### E. Next work session — build the deployment code + one-command installer (develop locally on the MacBook)

**Why this exists.** Deployment today is a set of guarded per-component PowerShell
scripts with no single entrypoint. The next session (developed locally on the
MacBook, targeting the Windows 10 gateway and, full-stack, the Windows Server 2025
VM) produces a **single idempotent installer** that updates the checkout to the
current specification (SHA) and deploys, plus one-command **scenario** bring-up.
Develop on a branch off `desktop/edge-gateway`; the installer's Windows steps run
in the lab/gateway lane. **This is deployment glue — it wraps the existing guarded
scripts; it does not rewrite the tested Python packages or add a cRIO/actuation
path.**

**E.1 Interfacing/deployment code to finish.**
- **Reconcile the source-of-truth contradiction.** `pi_gateway/windows/README.md`
  still names `crio_psp_adapter` as "the selected source / sole TCP writer," but
  the acquisition decision selected the **direct cRIO-record → TCP producer**, with
  PSP as the labeled **fallback** (`CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`,
  `CRIO_PSP_LIVE_ADAPTER_HANDOFF.md`). Update the gateway-side docs/config so the
  direct producer is primary and PSP is the explicit fallback. Do **not** delete
  PSP code or its handoff.
- **Config generation.** The installer emits the Seam A gateway config from
  `pi_gateway/config.crio-live.example.yaml` verbatim (bind `192.168.1.1:9070`,
  `conn_idle_timeout_s: 15`, `max_line_bytes: 8192`, `strict_fields: false`); no
  hand-editing of `config.windows.yaml`.
- **Post-cutover conformance gate.** Wire the live-capture → `conformance --cloud`
  step into the deploy flow as an explicit gate (surfaces the 6.3 bank-policy trap
  before any acceptance claim).

**E.2 The one-command installer — contract.**
- **Entrypoint:** one command, e.g. `deploy/Install-ReclaimLiveTwin.ps1` (Windows
  PowerShell 5.1) over a thin `deploy/install.py` core that also runs on the
  MacBook for dry-run/lint. Ship `deploy/README.md` (usage, roles, secrets,
  rollback).
- **Idempotent:** safe to re-run; converges to the current spec; a second run is a
  no-op. Never overwrites a running stack in place except through the existing
  guarded backup/rollback.
- **`-WhatIf` / dry-run is mandatory** and must run on the MacBook against a
  checkout: it prints the plan (target SHA, files, config diff, services/tasks) and
  changes nothing. Review the plan before any Windows step.
- **Role selection:** `-Role gateway | vm-engine | state-bridge | scenarios | all`.
  Require an explicit role (no accidental `all`).
- **"Update to current specifications":** checkout/verify the pinned SHA, run
  `uv sync --locked --all-extras --dev`, run the component suites (**expect
  55 / 73 / 70**) and the bench replay, and **refuse to deploy on any red**. Record
  the deployed SHA.
- **Wrap, don't replace, the existing guarded scripts:**
  - *gateway:* `configure-crio-network-firewall.ps1` (Audit→Apply),
    `finalize-gateway-config.ps1`, `install-gateway-task.ps1`, then
    `Start-ScheduledTask RECLAIM-EdgeGateway`; `send-commissioning-frame.ps1` /
    `send-commissioning-stream.ps1` for evidence.
  - *VM engine:* `VM_ENGINE_RUNBOOK.md` sequence / `run-ingest-engine.ps1` +
    `reclaim-ingest.xml` (WinSW), loopback `8078`, cloudflared as the only ingress.
  - *state bridge:* `convene_bridge/windows/install-state-bridge.ps1` (+
    `uninstall-state-bridge.ps1`).
  - *Convene agent:* `deployment/convene-setup-2.ps1` /
    `deployment/windows-vm/Register-ConveneAgentTask.ps1`.
- **Secrets discipline:** never on the command line, never committed; reuse the
  existing invisible-prompt + ACL patterns. Ingest and read tokens distinct; the VM
  `RECLAIM_INGEST_TOKEN` must equal the desktop `auth_token`.
- **Preserve the baseline:** deploy the new checkout side-by-side under
  `C:\RECLAIM\src`; do **not** overwrite `C:\RECLAIM\pi_gateway` until the new
  checkout passes (per `NEXT_SESSION_CD_REHEARSAL_PLAN.md`).
- **Guardrails honored by construction:** no boot-task start until endpoint+token
  are configured (the task installer already refuses placeholder/non-TLS config,
  broad ACLs, unsafe network, exposed `9080`, and conflicting listeners); engine
  loopback-only; advisory-only, no actuator authority; OT NIC no default route;
  `9080` never tunneled.
- **Deploy record:** emit SHA, role, config path, service/task names, restart
  command, and timestamp for reproducibility (no secrets).

**E.3 Scenarios.**
- `-Role scenarios` (or a `Start-Scenario` verb) stands up the rehearsal profiles
  via `cloud_engine/windows/start-rehearsal-scenario.ps1`: **`nominal` (8177)**,
  **`power-outage` (8178)**, **`lunar` (8179)**, plus the loss-of-data/freshness
  behavior. Advisory-only; ports `8177`–`8179` must **never** be routed to
  production or bound as live mission state; the production port `8078` is never
  touched.
- Expose each scenario's `/health`, `/state`, `/history`; optionally bind the
  labeled Convene rehearsal identities. Keep synthetic services as the fallback,
  clearly labeled rehearsal data.
- Wire the demo runbook (`NEXT_SESSION_CD_REHEARSAL_PLAN.md` /
  `RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md`): nominal ×2, power-outage ×1,
  lunar ×1, loss-of-data ×1 — each a named one-command target.

**E.4 Testing/acceptance for the installer itself.**
- *MacBook side:* `-WhatIf` plan review; `install.py` unit tests;
  `scripts/check_repository_hygiene.py`; full 55/73/70 + bench replay pre-flight.
- *Windows/gateway side:* idempotent re-run yields no changes; rollback path
  exercised; commissioning frame/stream evidence retained; scenario bring-up on
  `8177`–`8179` with `8078` untouched.
- *Definition of done:* one command updates+deploys the gateway to the current
  SHA; one command per scenario; a re-run is a no-op; the existing gateway baseline
  stays recoverable; all output advisory.

**E.5 Deliverables next session.**
- `deploy/Install-ReclaimLiveTwin.ps1` + `deploy/install.py` + `deploy/README.md`.
- Gateway source-of-truth reconciliation (direct producer primary, PSP fallback).
- Installer-core tests (optional CI wiring).

## 7. Go / no-go

Production enablement stays **NO-GO** while any item is unchecked; until then the
system is an explicitly labeled engineering shadow stream:

- [ ] Deployed source/build identity proven; rollback exercised. *(Gate 0)*
- [ ] Snapshot coherent or skew bounded. *(Gate 1)*
- [ ] Channel/unit/range/quality map signed; `PL_bottom2` and open-TC resolved.
- [ ] State/chamber/cycle/time authoritative and signed; clock inside 15 s.
- [ ] Producer lower-priority; cannot block control or the USB logger. *(Gate 3)*
- [ ] One writer targets `192.168.1.1:9070`; no command/return path. *(gateway side proven input-only; producer side Gate 3)*
- [ ] Frame size/cadence/reconnect/drop/stale policies reviewed. *(offline proven; live pending)*
- [x] Offline contract + conformance green (55/67/70 + bench replay at `3608872`).
- [ ] Same-time USB/LabVIEW/gateway/VM correlation; disconnect/restart shows no control impact or stale replay. *(Gates 4/5)*
- [ ] Named controls and onsite owners approve production enablement.

## 8. Stop conditions

Stop and report rather than improvise if: deployed-source identity or rollback is
unproven; the snapshot cannot be shown coherent/bounded; state/chamber/cycle/time
authority is unavailable or unsigned; open-sensor/quality semantics are unresolved
for a model-required channel; the producer can execute in or backpressure a
deterministic loop; a VI shows an unexpected output/write/command dependency; or
any test — installer runs included — would affect control, interlocks, outputs,
watchdogs, or USB logging. The goal is an evidence-backed, authoritative, coherent
telemetry shadow whose failure cannot affect the physical process.

## 9. Artifacts and hygiene

Everything lives on `desktop/edge-gateway`: `crio_source_record/`, `pi_gateway/`,
`cloud_engine/`, `convene_bridge/`, the new `deploy/` installer, and the
`deployment/CRIO_*` docs. Keep the `sim_`/`gw_` writer separation and the
synthetic-commissioned gateway/VM/Convene path untouched. Use focused commits;
`git diff --check` clean; commit no LabVIEW binaries, raw data runs, credentials,
or target exports. Maintain the evidence table in
`CRIO_SOURCE_RECORD_DECISION_RECORD.md` (§3.1 addendum) as gates close.
