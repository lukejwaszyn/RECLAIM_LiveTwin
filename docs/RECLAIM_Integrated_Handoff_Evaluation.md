# Integrated Handoff Evaluation

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

> **Historical review record — not an operational runbook.** The platform
> assumptions in this 2026-08-16 snapshot were corrected on 2026-08-17. The live
> cloud guest is Windows Server 2025 in Kubernetes-managed infrastructure, and
> the live gateway is a MacBook. Findings that cite Linux VM paths,
> systemd units, Raspberry Pi deployment, missing Git initialization, or absent
> locks describe the repository at review time and are superseded by
> `deployment/DEPLOYMENT_TOPOLOGY.md` plus the current runbooks. Safety findings
> remain historical evidence until individually closed.

**Review date:** 2026-08-16
**Repository reviewed:** `/Users/lukewaszyn/RECLAIM_LiveTwin`
**Review mode:** Read-only architecture, safety, and execution-readiness review. No runtime, service, deployment, CI, secret, host, or Git changes were made.

Citation convention: source references below are repository-relative to `/Users/lukewaszyn/RECLAIM_LiveTwin` and include exact line numbers. This makes, for example, `cloud_engine/push_ingest_dual.py:518-594` an exact local reference to `/Users/lukewaszyn/RECLAIM_LiveTwin/cloud_engine/push_ingest_dual.py`, lines 518 through 594.

## Executive Verdict

**READY WITH BLOCKERS**

The integrated architecture is directionally sound and is sufficient to guide one narrow, test-first working session. It is **not** yet sufficient or safe as an executable runtime or deployment handoff.

The current source still contains all RT-01 through RT-08 and GW-01 through GW-10 failure modes in scope, while the current deployment materials still describe the insecure or non-reproducible paths that the integrated architecture prohibits. Most importantly, the documented advisory/fail-closed command fields do not exist in the running implementation, the gateway republishes the last cloud command without local enforcement, a failed dual-chamber step leaves mutated state, and neither a reproducible release pipeline nor a maintenance-gated installer exists.

The next working session may establish a locked test environment and add failing RT-03/RT-05 regression tests. It must not deploy, alter command authority, expose a command endpoint, or modify a production host.

### Verification performed

- All eleven requested handoff and assessment documents were read in full.
- The requested engine, gateway, service/task, dependency, and existing test sources were inspected, together with the engine's mutable service/publisher/metrics/GP support objects needed to evaluate transactionality.
- A direct local fault check forced an exception after the plastics chamber stepped. The returned disposition was retryable `internal_error`, while `DualPushEngine.count`, `DualPushEngine.t`, `_last_ts`, plastics chamber time, UKF state, lifecycle elapsed time, and live charge mass had all changed. This directly reproduces RT-03 from `cloud_engine/push_ingest_dual.py:487-498` and `cloud_engine/push_ingest_dual.py:528-594`.
- The same local check confirmed that a current `ChamberEngine` can be deep-copied, which makes a candidate-state approach technically plausible. It does **not** prove that generic deep copy is a safe transaction design: the full engine contains locks, persistence, service publication, mutable nested objects, and future publisher implementations.
- The existing pytest suites could not be executed. `/opt/homebrew/opt/python@3.14/bin/python3.14` reported `No module named pytest`. No repository virtual environment or executable `pytest` was present. This is an environment limitation, not a passing test result. It also confirms the missing locked development/test baseline described in `deployment/CI_CD_ARCHITECTURE.md:94-98`.
- The workspace is not currently recognized as a Git repository, and no `.github` workflow, dependency lock, signed-manifest builder, fixed release installer, or compatibility verifier was found. This agrees with `deployment/CI_CD_ARCHITECTURE.md:62-73` and `deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md:212-214`.

## What Is Sound

1. **Advisory authority and independent physical protection are the correct top-level constraints.** The integrated architecture states that active authority is not authorized, that missing/untrusted signals cannot become actionable, and that the physical interlock remains independent (`docs/RECLAIM_Integrated_Remediation_Architecture.md:7-21`, `docs/RECLAIM_Integrated_Remediation_Architecture.md:64-68`). These constraints are appropriate and must remain requirements rather than inferred code behavior.

2. **Plane separation is the right safety boundary.** Separating telemetry, model, command, safety, and management/release responsibilities prevents cloud reachability, visualization state, CI, or a raw measurement from becoming command authority (`docs/RECLAIM_Integrated_Remediation_Architecture.md:54-62`).

3. **The proposed dual-chamber transaction is the correct integrity goal.** Validate, prepare isolated candidates, commit only after both chambers and publication preparation succeed, and discard candidates on failure is the right semantic contract (`docs/RECLAIM_Integrated_Remediation_Architecture.md:95-104`). The current per-engine object graph can support an explicit clone/snapshot design, provided every mutable field and persistence boundary is enumerated.

4. **The model-parity direction is technically correct.** Charge mass and reaction heat must be propagated consistently, constitutive functions must be shared, and held-input forecasts must be labeled as assumptions (`docs/RECLAIM_Integrated_Remediation_Architecture.md:106-122`). Relabeling the current sigma-point crossing fraction as an ensemble-risk indicator is also correct because the UKF weights are non-uniform (`cloud_engine/reclaim_predictive_engine/estimator.py:66-74`, `cloud_engine/reclaim_predictive_engine/forecaster.py:207-225`).

5. **Continuity failure is correctly treated as a mode change, not a smaller integration step.** Degraded state, forecast/rate suppression, explicit reacquisition, and a healthy-frame recovery requirement are sound (`docs/RECLAIM_Integrated_Remediation_Architecture.md:124-134`).

6. **Gateway freshness and strict acknowledgement are correctly identified as separate from durability.** Local expiry, current-data recovery, persistent loss audit, explicit `DATA_NOT_LIVE`/`BACKLOGGED`, and exact response correlation are required to make store-and-forward operationally useful (`docs/RECLAIM_Integrated_Remediation_Architecture.md:85-93`, `docs/RECLAIM_Integrated_Remediation_Architecture.md:255-263`).

7. **The release trust model is sound.** CI should have no production access, production should run a fixed pull-based installer, artifacts should be signed and digest-bound, dependencies should be hash-locked, stable runtime roots should be used, and deployment receipts and verified rollback should be produced (`docs/RECLAIM_Integrated_Remediation_Architecture.md:154-200`).

8. **The maintenance and shadow-isolation gates are appropriate.** An active batch must prohibit cutover, and a candidate must have a distinct listener/namespace and no production writer or command route (`docs/RECLAIM_Integrated_Remediation_Architecture.md:202-213`, `deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md:125-131`).

## Blocking Gaps

### IH-B01 — Current operational runbooks still authorize a prohibited topology

- **Severity:** P0
- **Evidence:**
  - The integrated architecture prohibits a general remote shell on a production control host and requires advisory-only operation (`docs/RECLAIM_Integrated_Remediation_Architecture.md:54-68`).
  - The gateway go-live document records a third-party command loop that executes arbitrary shell commands as `SYSTEM` and still leaves team acceptance as an open checkbox (`deployment/GATEWAY_GO_LIVE.md:367-392`).
  - The VM runbook is marked `CURRENT (active)` and directs a quick-tunnel deployment with an ephemeral hostname and no Access policy (`deployment/VM_ENGINE_RUNBOOK.md:1-21`, `deployment/VM_ENGINE_RUNBOOK.md:157-196`, `deployment/VM_ENGINE_RUNBOOK.md:264-267`).
  - The VM handoff directs operators to deploy the current engine in advisory mode even though the described authority fields are not implemented (`deployment/VM_ENGINE_HANDOFF.md:113-136`).
- **Why it matters:** A working session following the documents in their stated order can create exactly the exposed, remotely administrable, command-relaying system the integrated architecture says not to deploy. Document status is part of the control surface when runbooks contain executable commands.
- **Required resolution:** Before any host session, mark the quick-tunnel/current deployment instructions as non-production bring-up only; add an explicit integrated-remediation NO-GO banner to the VM and gateway runbooks; remove or relocate the SYSTEM remote-command agent before any control-connected role; and make the integrated release/maintenance gates authoritative.
- **Which phase it blocks:** Phases 0, 3, 4, 6, and 7; all production deployment.

### IH-B02 — Advisory authority and fail-closed command semantics are described but not implemented

- **Severity:** P0
- **Evidence:**
  - The proposed command contract requires schema, command ID, authority, actionable flag, exact source binding, issue/expiry time, health, reason, and artifact version (`docs/RECLAIM_Integrated_Remediation_Architecture.md:136-152`).
  - `EngineConfig` has no command-authority configuration (`cloud_engine/reclaim_predictive_engine/config.py:190-200`).
  - The live command is derived from observed forward power and severity and contains only chamber, mode, power, and a safe-state flag (`cloud_engine/push_ingest_dual.py:162-186`). The manifest exposes only those four command fields (`cloud_engine/push_ingest_dual.py:334-345`).
  - `/command` returns the last command without freshness or health enforcement (`cloud_engine/push_ingest_dual.py:690-704`).
  - The gateway stores any response `command` dictionary before it has established a strict acknowledgement contract (`pi_gateway/reclaim_edge/publisher.py:89-100`) and republishes it verbatim with only informational age (`pi_gateway/reclaim_edge/status.py:38-49`).
  - The existing gateway test positively asserts this unsafe relay behavior (`pi_gateway/tests/test_publisher_ack_contract.py:107-132`).
- **Why it matters:** There is no enforceable distinction between an advisory and an actuator command. A stale, malformed, replayed, unmatched, or compromised cloud value remains locally available indefinitely. Informational age is not expiry, and a downstream HMI convention is not fail-closed enforcement.
- **Required resolution:** Keep the command path disconnected. Establish a versioned advisory envelope that is always non-actionable for this milestone, then implement a separate local verifier/governor that rejects missing, unknown, stale, unhealthy, replayed, out-of-cap, or source-mismatched envelopes. The actuator/control owner must independently enforce absence/expiry. Do not implement or expose an active-authority option in this remediation program.
- **Which phase it blocks:** Phase 0 advisory baseline, Phase 4, Phase 7, and any control-connected or operator-relied deployment.

### IH-B03 — The transaction design does not yet cover all mutable or durable state

- **Severity:** P1
- **Evidence:**
  - `_step_locked` mutates `_last_ts`, count, service time, the plastics engine, the metals engine, the command, and published service state in sequence (`cloud_engine/push_ingest_dual.py:518-594`).
  - Each chamber step mutates lifecycle state, may reset per-cycle objects, mutates the UKF, NIS/CUSUM/seal monitors, measurement/GP windows, forecast cache, counters, performance accumulators, publisher state, and charge mass (`cloud_engine/reclaim_predictive_engine/engine.py:138-200`, `cloud_engine/reclaim_predictive_engine/engine.py:215-294`).
  - The exception path returns a retryable result without restoring any of that state (`cloud_engine/push_ingest_dual.py:487-498`).
  - The existing retry test throws in the first chamber, before partial success, and checks only sequence identity (`cloud_engine/tests/test_live_ingest_contract.py:251-268`); it therefore does not cover RT-03.
  - Identity persistence suppresses write errors and still lets the caller proceed as if commit succeeded (`cloud_engine/push_ingest_dual.py:222-239`). Identity is committed after model/publication mutation (`cloud_engine/push_ingest_dual.py:500-513`), so model, visible output, in-memory identity, and durable identity do not share one atomic boundary.
- **Why it matters:** A candidate clone of only UKF arrays would still miss lifecycle, adaptive state, mass, performance, publisher, command, time, and durability. A crash or persistence failure can also leave an accepted/visible model result without durable dedup identity.
- **Required resolution:** Define an explicit transaction aggregate and commit order. At minimum it includes both `ChamberEngine` object graphs, dual count/time/timestamp, command, staged output/event record, run supersession/gap changes, and durable identity. Candidate publishers must have no external side effects. Persistence failure must be surfaced and have a defined disposition; do not swallow it. Add byte/field-equivalence tests across every mutable member and a restart/crash-window test.
- **Which phase it blocks:** Phase 1 and every later phase.

### IH-B04 — Physical validation cannot be completed from the current handoff alone

- **Severity:** P1
- **Evidence:**
  - Cloud validation checks envelope, timestamp freshness, state enumeration, chamber, and sequence, but does not validate `vars` types, dimensions, finiteness, units, sensor agreement, or physical ranges (`cloud_engine/push_ingest_dual.py:366-425`).
  - `_mean` removes NaN by equality but accepts infinity, and scalar temperature helpers coerce values after validation (`cloud_engine/push_ingest_dual.py:126-159`).
  - The gateway's production preflight explicitly sets `strict_fields: false` until the real cRIO manifest is captured (`docs/RECLAIM_Remote_Gateway_Preflight.md:162-185`), and the gateway forwards unknown fields and values without type/range checks (`pi_gateway/reclaim_edge/framer.py:49-80`).
  - The integrated architecture correctly identifies the physical limits as a human decision (`docs/RECLAIM_Integrated_Remediation_Architecture.md:335-345`).
- **Why it matters:** Code cannot safely invent temperature, pressure, power, reflection, disagreement, or continuity limits. Finite/type validation can start, but the RT-05/GW-08 release gate cannot close without a versioned real cRIO schema and approved envelopes.
- **Required resolution:** Controls/thermal owners must approve units and ranges, including reflected-versus-forward power semantics and sensor disagreement. Capture a representative real frame/schema. Separate raw audit storage from the strict telemetry envelope. Implement all checks before any candidate model mutation or queue insertion.
- **Which phase it blocks:** Phase 1 exit, Phase 3 exit, Phase 4, and live ingest.

### IH-B05 — Forecast parity requires a state-model redesign, not a local forecaster patch

- **Severity:** P1
- **Evidence:**
  - The proposed common state is four-dimensional and includes charge mass (`docs/RECLAIM_Integrated_Remediation_Architecture.md:106-122`).
  - The current plant/UKF state is three-dimensional; mass is hidden mutable state on `ForwardModel`, outside UKF covariance (`cloud_engine/reclaim_predictive_engine/plant.py:42-51`, `cloud_engine/reclaim_predictive_engine/engine.py:51-70`).
  - The live derivative includes `q_rxn` and mass-dependent capacity (`cloud_engine/reclaim_predictive_engine/plant.py:74-102`, `cloud_engine/reclaim_predictive_engine/plant.py:131-141`), while the forecast derivative omits reaction heat and uses static bed capacity plus a fixed latent term (`cloud_engine/reclaim_predictive_engine/forecaster.py:61-109`).
  - Both production chambers enable mass flow, while metals also enables ignition and latent heat (`cloud_engine/reclaim_predictive_engine/config.py:308-334`).
  - Live mass is advanced after the thermal/filter step with separate explicit integration (`cloud_engine/reclaim_predictive_engine/engine.py:282-294`); the forward event forecast and time-to-target path do not propagate it (`cloud_engine/reclaim_predictive_engine/forecaster.py:57-145`, `cloud_engine/reclaim_predictive_engine/forecaster.py:147-193`).
  - The advisor still treats the equal-weight crossing fraction as probability (`cloud_engine/reclaim_predictive_engine/advisor.py:70-121`), and the manifest calls it a probability (`cloud_engine/reclaim_predictive_engine/thread.py:123-126`).
- **Why it matters:** Adding `q_rxn` alone would still leave inconsistent capacity, mass evolution, reaction coupling, recovery forecast, and uncertainty. Because mass is not currently measured or estimated, a four-state UKF also introduces observability, initialization, process-noise, and covariance decisions not present in the handoff.
- **Required resolution:** Choose and document one common transition function and integration scheme for `[T_bed, T_wall, beta, charge_mass]`, used by live prediction, event forecast, recovery forecast, and full-model residual. Define mass initialization and uncertainty with the model/controls owners. Until calibration exists, rename/remove `p_event` probability semantics and prohibit it from driving command severity.
- **Which phase it blocks:** Phase 2, Phase 4, and operator reliance in Phase 7.

### IH-B06 — Gateway remediation is incomplete in both code and the integrated release mapping

- **Severity:** P1
- **Evidence:**
  - The receiver is one synchronous client with no source authentication or peer allowlist and an unbounded byte buffer until newline (`pi_gateway/reclaim_edge/receiver.py:34-48`, `pi_gateway/reclaim_edge/receiver.py:50-90`).
  - Framing accepts arbitrary JSON top-level values and assumes `.get()`/`.items()` (`pi_gateway/reclaim_edge/framer.py:49-80`, `pi_gateway/reclaim_edge/framer.py:103-115`); framing/enqueue exceptions are outside the per-line catch (`pi_gateway/reclaim_edge/receiver.py:92-108`).
  - Live HTTPS requires only a non-empty token; an HTTP URL or disabled TLS verification remains constructible (`pi_gateway/reclaim_edge/config.py:125-137`).
  - A malformed or mismatched 2xx response acks the whole batch; result indices, content type, schema version, and batch correlation are not checked (`pi_gateway/reclaim_edge/publisher.py:71-110`).
  - Queue recovery is oldest-first and has no local expiry (`pi_gateway/reclaim_edge/buffer.py:78-83`, `pi_gateway/reclaim_edge/publisher.py:178-217`). Drop count is memory-only and dead-letter history is silently capped (`pi_gateway/reclaim_edge/buffer.py:26-34`, `pi_gateway/reclaim_edge/buffer.py:67-76`, `pi_gateway/reclaim_edge/buffer.py:92-110`).
  - The status endpoint has no application authentication (`pi_gateway/reclaim_edge/status.py:69-86`).
  - The integrated Phase 3 exit row omits GW-01, GW-02, and GW-09 (`docs/RECLAIM_Integrated_Remediation_Architecture.md:219-230`), while its verification table has no explicit proof for GW-01, GW-08, or GW-09 (`docs/RECLAIM_Integrated_Remediation_Architecture.md:308-325`).
- **Why it matters:** The target gateway cannot be declared hardened when three gateway findings are absent from its explicit phase exit and test mapping. Current behavior permits denial of service, injection, stale recovery, silent dequeue, insecure transport, and unauthenticated local command exposure.
- **Required resolution:** Add GW-01/GW-02/GW-08/GW-09 explicitly to Phase 3/4 gates and to required tests. Implement bounded/authenticated ingress, strict raw schema, local expiry/current-data recovery, durable loss alarms, strict response correlation, enforced secure live configuration, application endpoint authorization, and a disconnected/non-actionable command path.
- **Which phase it blocks:** Phases 3, 4, and 7.

### IH-B07 — CI/CD remains a proposal and the older CI architecture still contradicts it

- **Severity:** P1
- **Evidence:**
  - `CI_CD_ARCHITECTURE.md` still proposes an outbound self-hosted GitHub Actions runner on the production VM (`deployment/CI_CD_ARCHITECTURE.md:153-157`), while the red-team handoff and integrated architecture prohibit it (`deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md:17-24`, `docs/RECLAIM_Integrated_Remediation_Architecture.md:180-193`).
  - Runtime dependencies use lower bounds and production runbooks resolve from public indexes (`cloud_engine/deploy/requirements-cloud.txt:1-7`, `pi_gateway/requirements.txt:1-6`, `deployment/VM_ENGINE_RUNBOOK.md:43-63`).
  - The proposed stable release roots do not match the current systemd service or Windows task (`cloud_engine/deploy/reclaim-ingest.service:11-24`, `pi_gateway/windows/install-gateway-task.ps1:13-29`).
  - The Windows task installer immediately starts the SYSTEM task and has no artifact signature, digest, compatibility, maintenance, receipt, or rollback interface (`pi_gateway/windows/install-gateway-task.ps1:18-44`).
  - No Git repository, workflow, lock, wheel set, signed manifest, SBOM builder, fixed production installer, release receipt, state/queue compatibility check, or executable rollback test was found. The handoff itself describes this as unimplemented (`deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md:201-214`).
- **Why it matters:** Checksums without an independent signature do not establish provenance; mutable dependency resolution means CI and production can run different code; changing a `current` pointer cannot work if the service/task ignores it; and paper rollback is not recovery evidence.
- **Required resolution:** Amend or supersede the older CI document; establish repository controls; select supported platforms/Python; create hash-locked per-target wheel sets; define and sign the compatibility manifest; update templates to stable roots; and implement fixed least-privilege installers with preflight, receipt, verified switch, and tested restore. CI must have no production credentials or network route.
- **Which phase it blocks:** Phases 0, 5, 6, and 7.

### IH-B08 — Maintenance, persistence compatibility, and rollback are not executable gates

- **Severity:** P1
- **Evidence:**
  - The integrated maintenance gate requires independent idle/power confirmation, no actionable command, bounded queue/loss, health, approver, artifact digest, rollback target, and window record (`docs/RECLAIM_Integrated_Remediation_Architecture.md:202-213`).
  - The active VM runbook installs and starts the service without querying plant state, queue state, current writer, compatibility, or maintenance approval (`deployment/VM_ENGINE_RUNBOOK.md:123-153`).
  - Existing state persistence records only ingest run/sequence identity, without a schema version or migration contract (`cloud_engine/push_ingest_dual.py:189-248`).
  - Existing gateway tables likewise have no on-disk schema version/compatibility contract (`pi_gateway/reclaim_edge/buffer.py:29-49`).
- **Why it matters:** A release or rollback can interrupt a batch, discard process-resident estimator/lifecycle/mass state, or run an old binary against incompatible identity/queue semantics. The current process intentionally has no hot state handoff (`docs/RECLAIM_Integrated_Remediation_Architecture.md:95-105`).
- **Required resolution:** Define machine-readable maintenance and compatibility preflights, schema versions, backup/migration/restore rules, a single-writer check, and tested upgrade/rollback drills on packaged artifacts. Until a state snapshot/migration design is separately validated, cutover is idle-only.
- **Which phase it blocks:** Phase 6 and Phase 7.

### IH-B09 — Hardware-interlock independence has not been evidenced by this repository

- **Severity:** P1 for this advisory program; P0 for any control-connected proposal
- **Evidence:**
  - The architecture correctly makes the hardware interlock independent and non-negotiable (`docs/RECLAIM_Integrated_Remediation_Architecture.md:13-20`, `docs/RECLAIM_Integrated_Remediation_Architecture.md:359-370`).
  - The inspected repository contains only a software-in-the-loop `HardwareInterlock` model (`cloud_engine/reclaim_predictive_engine/control.py:1-24`, `cloud_engine/reclaim_predictive_engine/control.py:114-139`). The module's statement that the same design becomes hardware-in-the-loop when wired is an aspiration, not evidence of electrical/PLC/cRIO independence.
- **Why it matters:** Software class separation does not prove independent sensing, power removal, latching, reset authority, failure modes, or inability of the twin/gateway/network to bypass or weaken the physical interlock.
- **Required resolution:** Controls/safety owners must provide an interface/hazard record and independent test evidence for the physical interlock. The release pipeline must explicitly exclude modifying its logic or thresholds. Keep all command outputs non-actionable and disconnected.
- **Which phase it blocks:** Phase 4 safety claims and Phase 7; any active or control-connected use.

### IH-B10 — Named red-team regressions and an executable test baseline do not exist

- **Severity:** P1
- **Evidence:**
  - The architecture declares every §10 proof release-blocking (`docs/RECLAIM_Integrated_Remediation_Architecture.md:308-333`).
  - Existing tests cover lifecycle and earlier ingest/queue contracts, but none carries an RT-, GW-, or CD-ID, and the RT-03 test does not inject failure after the first successful chamber (`cloud_engine/tests/test_live_ingest_contract.py:251-268`).
  - Gateway tests currently bless permissive command relay and do not cover malformed top-level JSON, buffer bounds, insecure live URLs, strict result indices/correlation, local expiry, durable loss, endpoint auth, or local governor (`pi_gateway/tests/test_framer_contract.py:1-21`, `pi_gateway/tests/test_publisher_ack_contract.py:45-151`).
  - The test runner is not installed in the available Python environment, and no lock/dev environment exists (`deployment/CI_CD_ARCHITECTURE.md:94-98`).
- **Why it matters:** CI could be green while every known safety/integrity defect remains. The handoff cannot claim a phase exit without executable, named evidence.
- **Required resolution:** Establish the supported locked test environment first. Add one or more tests for every traceability row below, use stable test IDs containing the finding ID, and publish a machine-readable ID-to-result report from the exact packaged artifact.
- **Which phase it blocks:** All phase exits, especially Phases 1, 3, 4, 5, and 6.

## Cross-Document Contradictions

| Topic | Proposed/safer statement | Conflicting current statement or implementation | Required reconciliation |
|---|---|---|---|
| Advisory deployment gate | Integrated architecture requires Phases 0-6 for advisory production (`docs/RECLAIM_Integrated_Remediation_Architecture.md:346-357`). | Predictive remediation says only RT-03/RT-05 block imminent advisory deployment (`docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md:120-137`), and the current VM handoff routes toward that deployment (`deployment/VM_ENGINE_HANDOFF.md:128-147`). | Declare the integrated gate authoritative. Earlier “imminent deploy” language must be superseded. |
| Command authority | Documents describe `cmd_authority`, `cmd_actionable`, `cmd_health`, and `cmd_valid_until` (`docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md:23-54`; `deployment/VM_ENGINE_HANDOFF.md:113-130`). | None exists in `EngineConfig`, manifest, command output, or gateway enforcement (`cloud_engine/reclaim_predictive_engine/config.py:190-200`; `cloud_engine/push_ingest_dual.py:326-345`; `pi_gateway/reclaim_edge/status.py:38-49`). | Label these fields proposed, not current; disconnect `/command` until an advisory envelope and local rejection path exist. |
| “Ingest pipeline proven” | VM handoff says not to modify `_validate_frame`/`ingest_line` (`deployment/VM_ENGINE_HANDOFF.md:100-104`). | The same handoff says RT-03/RT-05 block advisory deployment (`deployment/VM_ENGINE_HANDOFF.md:132-136`), and both fixes necessarily affect validation/transaction boundaries. | Narrow the guardrail to preserving the accepted ack/identity contract, not freezing defective code. |
| Retry cleanliness | Live telemetry contract says a retryable internal error does not commit and “re-steps cleanly” (`docs/RECLAIM_Live_Telemetry_Architecture.md:117-122`). | Current step mutates model/time/lifecycle before the retryable error (`cloud_engine/push_ingest_dual.py:487-498`, `cloud_engine/push_ingest_dual.py:528-594`). | Mark the current claim false until RT-03 passes. |
| Gateway schema | Integrated design requires an allowlisted raw schema and early finite/range rejection (`docs/RECLAIM_Integrated_Remediation_Architecture.md:72-83`). | Preflight intentionally deploys `strict_fields: false` and preserves unknown values (`docs/RECLAIM_Remote_Gateway_Preflight.md:162-185`; `pi_gateway/reclaim_edge/framer.py:58-80`). | Separate temporary raw capture from production strict ingress; raw passthrough cannot pass the live gate. |
| Remote management | Integrated management plane prohibits a general remote shell on the control host (`docs/RECLAIM_Integrated_Remediation_Architecture.md:54-62`). | Go-live records the Convene agent executing arbitrary backend commands as SYSTEM (`deployment/GATEWAY_GO_LIVE.md:367-392`); preflight also treats remote shell as step zero (`docs/RECLAIM_Remote_Gateway_Preflight.md:19-98`). | Remove/relocate arbitrary command capability; define a narrow audited management plane. |
| Production runner | Integrated/red-team design forbids a general CI runner on production (`docs/RECLAIM_Integrated_Remediation_Architecture.md:180-193`; `deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md:28-36`). | `CI_CD_ARCHITECTURE.md` still proposes a self-hosted runner on the VM (`deployment/CI_CD_ARCHITECTURE.md:153-157`). | Amend/supersede the older architecture before CI work. |
| Release dependencies | Integrated design requires exact hash-locked dependencies and audited wheels (`docs/RECLAIM_Integrated_Remediation_Architecture.md:163-179`). | Requirements use lower bounds, and the current runbook installs them from public indexes (`cloud_engine/deploy/requirements-cloud.txt:1-7`; `deployment/VM_ENGINE_RUNBOOK.md:43-63`). | Replace production resolution with per-target locks and wheel sets tested as the artifact. |
| Stable switching | Integrated design requires `/opt/reclaim/current` and `C:\RECLAIM\current` (`docs/RECLAIM_Integrated_Remediation_Architecture.md:180-200`). | Service/task execute `/opt/reclaim/engine` and `C:\RECLAIM\pi_gateway` (`cloud_engine/deploy/reclaim-ingest.service:14-24`; `pi_gateway/windows/install-gateway-task.ps1:13-29`). | Update templates first and prove resolved executable changes on upgrade and rollback. |
| Tunnel posture | CI architecture says replace the ephemeral quick tunnel before unattended operation (`deployment/CI_CD_ARCHITECTURE.md:173-178`). | VM runbook is current/active and installs a boot-persistent quick tunnel with no Access policy (`deployment/VM_ENGINE_RUNBOOK.md:157-196`). | Restrict quick tunnels to isolated non-production bring-up; use stable approved ingress for a pilot. |
| Phase 1/3 dependency | Integrated table makes Phase 3 depend on Phase 1 (`docs/RECLAIM_Integrated_Remediation_Architecture.md:219-228`). | The following sentence says Phases 1 and 3 may run in parallel after Phase 0 (`docs/RECLAIM_Integrated_Remediation_Architecture.md:230`). | Split Phase 3: ingress/schema/queue unit work may run in parallel; strict cloud-ack integration waits for Phase 1's engine contract. |
| CI phase dependency | Phase 6 lists only Phase 5 as a dependency (`docs/RECLAIM_Integrated_Remediation_Architecture.md:226-228`). | Controlled CD also requires Phase 4 command-schema compatibility and maintenance assertions, and the advisory gate requires Phases 0-6 (`docs/RECLAIM_Integrated_Remediation_Architecture.md:297-306`, `docs/RECLAIM_Integrated_Remediation_Architecture.md:346-357`). | Make Phase 6 depend on completed Phases 0-5, including the advisory command contract. |
| Interlock proof | Documents correctly require independent physical enforcement (`docs/RECLAIM_Integrated_Remediation_Architecture.md:359-370`). | Repository evidence is only a software simulation class and prose assertion (`cloud_engine/reclaim_predictive_engine/control.py:1-24`, `cloud_engine/reclaim_predictive_engine/control.py:114-139`). | Require controls-owner hardware evidence; do not infer it from source separation. |

## Requirement Traceability Matrix

“Partial” and “gap” in the architecture column are review findings, not implementation status. All implementation items remain open unless separately evidenced.

| ID | Proposed architecture section | Expected implementation phase | Required regression/integration test | Release gate |
|---|---|---:|---|---|
| RT-01 | §4.4 unified state/physics; §10 parity | 2 | `test_RT_01_forecast_live_derivative_parity` across PL/MT, held/ramped power, mass transitions, reaction, ignition, and latent band | Phase 2; advisory reliance/shadow gate |
| RT-02 | §4.5 continuity + §4.6 envelope/governor | 4 | `test_RT_02_missing_stale_unhealthy_never_actionable` at engine, gateway, and actuator boundary | Phase 4; control-connected release prohibited |
| RT-03 | §4.3 transaction; §10 integrity | 1 | `test_RT_03_failure_after_PL_preserves_complete_prior_state`, identical retry vs clean one-pass, plus persistence-failure case | Phase 1; all advisory production |
| RT-04 | §4.4 ensemble-risk semantics; §10 | 2 | `test_RT_04_risk_not_probability_or_probability_is_calibrated`; advisor cannot use probability thresholds in interim | Phase 2; operator reliance gate |
| RT-05 | §4.3 validate before mutation; §10 | 1 | `test_RT_05_nonfinite_type_dimension_range_rejected_pre_mutation` for every chamber/channel | Phase 1 and live ingest |
| RT-06 | §4.5 degraded mode; §10 | 2 | `test_RT_06_gap_enters_degraded_and_requires_N_healthy_frames`; no normal forecast/rate escalation | Phase 2; Phase 4 health gate |
| RT-07 | §3.1 plane separation + §4.6 authorized setpoint | 4 | `test_RT_07_command_uses_authorized_demand_not_measured_power`; no demand means non-actionable | Phase 4; control-connected release prohibited |
| RT-08 | §4.4 shared derivative/residual; §10 | 2 | `test_RT_08_full_model_residual_includes_all_q_rxn_terms`, with separately named reduced residual if retained | Phase 2; affected chemical configs |
| GW-01 | Partial: §3.1 management-plane prohibition and §11 decision 5; absent from Phase 3 exit/test table | 0, 3 | `test_GW_01_gateway_host_has_no_general_remote_shell_agent` as host attestation/configuration audit | Phase 0/3; any control-connected gateway |
| GW-02 | §4.6 command envelope/local governor; absent from Phase 3 but logically Phase 4 | 4 | `test_GW_02_invalid_expired_replayed_unmatched_command_not_exposed_or_acted_on` | Phase 4; command endpoint remains disconnected |
| GW-03 | §4.1 bounded/authenticated ingress; §10 | 3 | `test_GW_03_oversized_slow_competing_untrusted_client_is_bounded_and_rejected` | Phase 3 live-gateway gate |
| GW-04 | §4.1 per-frame fault isolation; §10 | 3 | `test_GW_04_array_scalar_nested_invalid_utf8_does_not_kill_receiver` | Phase 3 live-gateway gate |
| GW-05 | §3 target authenticated publisher + §7 Session C + §10 | 3 | `test_GW_05_live_requires_https_verified_CA_approved_host` | Phase 3 live transport gate |
| GW-06 | §4.2 freshness-aware recovery; §10 | 3 | `test_GW_06_long_outage_expires_locally_and_recovers_to_current_sample` at maximum rate | Phase 3 outage/recovery gate |
| GW-07 | §3 target strict per-frame correlation + §7 Session C + §10 | 3 | `test_GW_07_malformed_reordered_mismatched_2xx_never_dequeues` including content type/schema/batch ID/index | Phase 3 ingest-ack gate |
| GW-08 | §4.1 raw schema/finiteness; missing explicit §10 row | 3 | `test_GW_08_unknown_type_unit_range_and_nonfinite_rejected_before_queue` against captured cRIO schema | Phase 3 live-schema gate |
| GW-09 | **Gap:** no explicit local status application-auth/endpoint-exposure requirement | 3 | `test_GW_09_status_authz_and_command_endpoint_disabled_by_default`; tunnel misconfiguration test | Phase 3 remote-observation gate |
| GW-10 | §4.2 persistent loss/dead-letter audit; §10 | 3 | `test_GW_10_queue_cap_disk_low_and_DL_retention_persist_loss_watermark_and_alarm` | Phase 3 operational alarm gate |
| CD-01 | §3.1/§5.3 fixed host installer, no production runner; §10 | 0, 6 | `test_CD_01_prod_host_executes_only_fixed_installer_and_has_no_CI_runner` | Governance and Phase 6 security review |
| CD-02 | §5.2 signed immutable candidate + §5.3 verification; §10 | 5, 6 | `test_CD_02_tampered_unsigned_or_tag_only_artifact_rejected` | Release candidate and host preflight |
| CD-03 | §5.3 stable runtime roots; §10 | 6 | `test_CD_03_upgrade_and_rollback_resolve_expected_executable_version` on VM and Windows | Phase 6 switch/rollback drill |
| CD-04 | §5.2 hash-locked dependencies/wheels | 5 | `test_CD_04_offline_hash_locked_install_reproduces_CI_environment` per target ABI/platform | Phase 5 artifact reproducibility |
| CD-05 | §5.1 protected repo/actions/owners | 0, 5 | `test_CD_05_repository_policy_and_workflow_permissions` including SHA-pinned actions/no PR secrets | Phase 0 governance; Phase 5 CI gate |
| CD-06 | §5.4 maintenance gate; §10 | 6 | `test_CD_06_active_batch_or_unconfirmed_power_off_refuses_switch` | Phase 6 deployment authorization |
| CD-07 | §5.2 manifest compatibility + §5.3 preflight + §9; §10 | 6 | `test_CD_07_upgrade_and_rollback_block_incompatible_state_queue_command_schema` and exercise backup/restore | Phase 6 compatibility/rollback gate |
| CD-08 | §10 finding-to-test proof | 5 | `test_CD_08_release_report_maps_all_RT_GW_CD_IDs_to_passing_evidence` | Phase 5 release-candidate gate |
| CD-09 | §5.3 non-secret deployment receipt | 6 | `test_CD_09_receipt_binds_digest_operator_machine_path_health_and_outcome_without_secrets` | Phase 6 audit gate |
| CD-10 | §7 Session E isolated shadow + §10 | 7 | `test_CD_10_shadow_has_distinct_port_namespace_no_prod_writer_no_command_route` | Phase 7 shadow entry and exit |

## Phase-by-Phase Feasibility Review

### Phase 0 — Governance and baseline

**Feasible only after scope reconciliation.** The workspace is not a Git repository and the command-authority policy is not implemented. Phase 0 must also freeze/supersede unsafe runbooks, decide the SYSTEM remote agent's disposition, and state that `/command` is disconnected. Establish a locked local test environment here, not in late Phase 5, because no later exit gate is meaningful without a runnable baseline.

**Order change:** Add Phase 0A “documentation/operational freeze and advisory hard-disable” before any host work. Add Phase 0B “supported Python + locked developer test runner.”

### Phase 1 — Engine integrity

**Technically feasible, but the transaction aggregate must be designed explicitly.** Current chamber objects can be cloned, but correctness requires all nested mutable state, staged publication, dual time/count, command, and identity persistence to participate. Start with failing RT-03/RT-05 tests. Basic type/dimension/finiteness validation can be implemented before owner-approved physical limits; the phase cannot exit until the latter exist.

**Order change:** Separate Phase 1A tests and transaction-state inventory from Phase 1B runtime implementation. Do not combine this work with forecast refactoring.

### Phase 2 — Forecast fidelity and degraded mode

**Feasible after a model decision, not as currently specified at code level.** A common four-state transition is the cleanest target, but mass observability/uncertainty and operator-splitting semantics require model-owner decisions. Use one shared constitutive/derivative implementation for live, event forecast, recovery forecast, and residual. Implement risk relabeling before any advisor rule consumes the current `p_event`.

**Order change:** Define common-state semantics and parity fixtures before changing the forecast. Degraded continuity can be developed alongside the model refactor after Phase 1 guarantees rollback.

### Phase 3 — Gateway hardening

**Partly parallelizable after Phase 0.** Receiver bounds, parser shape checks, TLS config enforcement, schema scaffolding, loss persistence, and endpoint auth can proceed independently of Phase 1. Strict response-correlation integration and retry semantics depend on the finalized engine ingest/ack contract. GW-01, GW-02, GW-08, and GW-09 need explicit ownership/gates.

**Order change:** Split 3A ingress/queue/transport unit work (parallel with Phase 1) from 3B gateway-to-engine ack/recovery integration (after Phase 1).

### Phase 4 — Command envelope and local governor

**Feasible only as advisory/non-actionable in this program.** A versioned envelope and gateway verifier can be built, but a gateway verifier alone is not actuator-side independence. The control owner must define the local enforcement boundary, fail-safe semantics, expiry clock, source correlation, and caps. The current `/command` should remain unused and not remotely exposed.

**Order change:** Land the non-actionable advisory contract after Phases 1 and 3B. Forecast health can populate it after Phase 2, but no active option should be implemented or released.

### Phase 5 — Reproducible CI

**Feasible after repository/platform decisions.** The release CI can be built only after supported Python/OS/ABI targets and the signer/trust policy are chosen. A minimal locked local/PR test runner belongs in Phase 0; signed packaged-artifact certification remains Phase 5 and must run the Phase 4 advisory/governor tests too.

**Order change:** Split early developer CI from late release-candidate CI. Full Phase 5 depends on Phases 1-4, not only 1-3.

### Phase 6 — Controlled CD

**Not currently executable.** Service/task templates, stable roots, manifest verifier, fixed installers, maintenance query, compatibility preflight, receipt, and rollback verification all need implementation and non-production drills. Current runbooks are manual installation guides, not controlled CD.

**Order change:** Make Phase 6 depend on completed Phases 0-5. Update runtime templates before implementing pointer switching. Exercise state/queue migration and rollback with packaged artifacts while idle.

### Phase 7 — Shadow pilot

**Feasible only as an isolated advisory evidence campaign after all prior gates.** Feed a candidate with sanitized replay or a deliberate read-only tee. It must have a distinct port/namespace, no production tunnel route, no production state writer, and no command endpoint consumed by the plant. Live shadow activity also requires GW-01/GW-09 closure and owner approval of data handling.

**Order change:** Rename this phase “Advisory shadow pilot.” Remove active-authority enablement from its exit; any future consideration of active control must be a separately chartered safety program after independent evidence. This review does not recommend enabling active command authority.

### Revised dependency summary

1. Phase 0A operational freeze/advisory hard-disable.
2. Phase 0B supported locked test environment and repository governance.
3. Phase 1A RT-03/RT-05 failing tests and transaction inventory.
4. Phase 1B engine integrity implementation.
5. Phase 2 model/continuity work and Phase 3A gateway boundary unit work may proceed in parallel after Phase 1 integrity semantics are stable where shared contracts are involved.
6. Phase 3B strict gateway-to-engine integration follows the finalized engine acknowledgement contract.
7. Phase 4 advisory envelope/local rejection path follows Phases 1, 2, and 3B; no active option.
8. Phase 5 full packaged-artifact CI follows Phases 1-4.
9. Phase 6 follows Phases 0-5 and completes non-production upgrade/rollback drills.
10. Phase 7 is isolated advisory shadow only.

## First Working Session Plan

### Objective

Create an executable, failing integrity baseline for RT-03 and the inference-safe portion of RT-05, without changing runtime behavior or touching a production host. This is the smallest safe slice because it proves the two mode-independent integrity blockers before selecting a transaction implementation.

### Exact files likely to change

- Create `cloud_engine/tests/test_rt03_rt05_integrity.py` with stable test IDs in function names.
- Create the development/CI dependency input and target lock file only after the team selects the supported Python/platform and lock tool. Do not guess filenames or targets before that decision.
- **Do not change in this first slice:** `cloud_engine/push_ingest_dual.py`, predictive-engine modules, gateway modules, service/task templates, deployment scripts, runbooks, CI workflows, or production configuration.

The immediate follow-on runtime slice, after the tests and transaction inventory are reviewed, is expected to be limited initially to `cloud_engine/push_ingest_dual.py` plus the same test file. If an explicit snapshot/clone API is required, its ownership must be declared before editing `cloud_engine/reclaim_predictive_engine/engine.py`, `estimator.py`, `lifecycle.py`, `anomaly.py`, `metrics.py`, `plant.py`, `thread.py`, or `service.py`.

### Tests to add first

1. `test_RT_03_failure_after_PL_before_MT_preserves_dual_engine_state`
   - Arrange one valid dual-chamber frame.
   - Snapshot every mutable member identified in IH-B03.
   - Force MT failure after PL returns successfully.
   - Assert retryable disposition and exact pre-frame equivalence of model, lifecycle, time/count, command, service state/history, run identity, and durable identity file.

2. `test_RT_03_retry_after_partial_failure_equals_clean_one_pass`
   - Retry the identical frame after removing the injected fault.
   - Compare against a fresh engine that processed it once.

3. `test_RT_03_identity_persist_failure_is_not_reported_accepted`
   - Force durable identity write/replace failure.
   - Assert the selected transaction policy and no false accepted response/visible commit.

4. `test_RT_05_nan_inf_bool_string_and_wrong_dimension_rejected_before_mutation`
   - Parameterize every numeric chamber input and envelope numeric field.
   - Include NaN, positive/negative infinity, booleans, numeric strings, nested structures, and wrong-sized sensor banks.
   - Assert final rejection and exact state equivalence.

5. Add physical-range cases only after controls/thermal owners provide approved values. Until then, mark those cases blocked by named decision ID rather than inventing thresholds.

### Acceptance criteria

- The supported Python and lock are recorded; pytest runs from the locked local environment without downloading during the test run.
- Existing tests execute and their baseline outcomes are recorded. No claim is made that they pass until observed.
- All new RT-03/RT-05 tests fail on the current code for the intended reasons, not import/setup errors.
- The transaction-state inventory includes both chamber object graphs, lifecycle/reset side effects, UKF/adaptation, anomaly monitors, performance, mass, forecaster/advisor cache, time/count, service output/history, command, run/gap identity, and persistence.
- No runtime code, service/task, deployment host, secret, Git configuration, CI workflow, gateway, command endpoint, or hardware interlock is changed.

### Explicit scope exclusions

- No implementation of transactionality in this first session.
- No physical range values until owner-approved.
- No forecast/model changes.
- No gateway hardening changes.
- No command envelope, governor, actuator integration, or active authority.
- No production deployment, quick tunnel, Convene binding, task/service installation, or release automation.
- No assertion that the hardware interlock has been verified.

## Decisions Required From the Team

Only decisions that cannot safely be inferred are listed.

1. **Milestone authority and exposure:** Confirm the entire remediation milestone is advisory-only, `actionable=false`, with `/command` disconnected from HMI/actuator consumption. Decide whether the endpoint is disabled or serves only an authenticated advisory view.
2. **Fail-safe semantics and owner:** Define what the actuator/control hub does on no command, invalid command, expiry, clock uncertainty, stale/missing telemetry, source mismatch, and gateway/cloud loss. Resolve the ambiguity between “hold last safe state,” “power zero,” and an independently commanded `SAFE_STATE`.
3. **Physical envelopes:** Controls/thermal owners must approve temperature, pressure, forward/reflected power, reflected ratio/relationship, sensor disagreement, units, source-time continuity, command deadline, clock skew, and recovery-frame count.
4. **cRIO schema and ingress security:** Approve the exact versioned raw schema; state whether cRIO can provide mTLS or per-frame MAC/replay protection; define key provisioning/rotation. If not, formally classify the link as non-security-grade and keep it isolated/advisory.
5. **Charge-mass model:** Model/controls owners must choose mass initialization/source, live transition semantics, uncertainty/process noise, observability treatment, and calibration evidence for PL and MT.
6. **Gateway host boundary:** Decide and authorize removal or relocation of the SYSTEM-level Convene remote-shell agent; identify the permitted narrow remote-management mechanism and its approvers/audit controls.
7. **Local governor/actuator boundary:** Name the component and owner that independently enforces command schema, source correlation, expiry, replay/idempotency, caps, health, and non-actionable advisory policy. Provide the physical-interlock independence evidence owner.
8. **Supported build targets:** Choose supported Python versions and target OS/ABI for Mac development, Linux VM, and MacBook scenario host. Python 3.13 on the staged gateway is not yet an approved target (`deployment/GATEWAY_GO_LIVE.md:254-262`).
9. **Release trust root:** Choose the signer/identity, trusted verifier policy/key location, tag/release immutability rules, CODEOWNERS, required safety reviewers, and artifact/evidence retention.
10. **Persistence compatibility:** Define telemetry, command, state, ingest-identity, and queue schema versions; migration/backup/restore rules; and coordinated VM/gateway rollout order.
11. **Maintenance authority:** Name who may attest idle state and independent power removal, approve artifact digest/rollback target/window, and authorize rollback.
12. **Outage and audit policy:** Approve maximum useful telemetry age, queue cap, recovery coalescing rule, disk-low threshold, loss alarm response, and immutable dead-letter/audit retention period.
13. **Status/observation access:** Decide whether `/latest`, `/health`, and any advisory endpoint may be tunnel-exposed; define application authentication/authorization independent of tunnel configuration.

## Final Recommendation

Do **not** execute the current VM or gateway runbooks and do not connect or expose the command path.

The next exact action is a controls/development review that records Decisions 1, 2, 3, 6, 7, and 8 above, marks the current deployment runbooks NO-GO under the integrated remediation program, and authorizes only the test-first session described here. That session should establish the locked test runner and commit failing RT-03/RT-05 regression evidence. Runtime implementation should begin only after those tests and the complete transaction-state inventory are reviewed.
