# CI/CD Red-Team Integration Handoff

**Date:** 2026-08-16  
**Status:** Required amendments before implementing `CI_CD_ARCHITECTURE.md`  
**Audience:** controls lead, developer, VM operator, gateway operator, and future CI maintainer.

## Purpose

This handoff red-teams the proposed [CI/CD architecture](CI_CD_ARCHITECTURE.md) and turns the two existing red-team assessments into an integration plan:

- [Predictive engine assessment](../PREDICTIVE_ENGINE_RED_TEAM_ASSESSMENT.md)
- [Gateway deployment assessment](../GATEWAY_DEPLOYMENT_RED_TEAM_ASSESSMENT.md)
- [Predictive-engine remediation plan](../docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md)

The goal is frequent, controlled bug-fix delivery **without** allowing a fast code path to bypass model validation, command authority controls, deployment traceability, or the independent hardware interlock.

## Bottom line

Adopt CI/CD in stages, but do **not** implement the document literally yet.

1. CI may validate code and produce an immutable, signed release candidate.
2. Production machines must pull and verify that candidate through a narrowly scoped deployment agent/script; a general GitHub Actions runner must not execute on the production VM or gateway.
3. Every deployment must be tied to an artifact digest, tested state-compatibility decision, maintenance/operational gate, and a recorded rollback target.
4. The command path remains `advisory` until the predictive-engine remediation plan’s active-authority gates are complete.

## Red-team findings against the CI/CD architecture

### CD-01 — A production self-hosted GitHub Actions runner collapses the trust boundary

**Severity:** P0 — do not adopt as proposed.

The architecture proposes an outbound GitHub self-hosted runner on the predictive-engine VM to execute approved deployment workflows ([CI/CD architecture](CI_CD_ARCHITECTURE.md#vm-deployment)). A runner executes workflow-defined code. Anyone able to modify a workflow, compromise a maintainer account, exploit an action/dependency, or abuse incorrectly scoped dispatch inputs can execute code on the production VM.

That VM holds live service secrets and persistent ingest identity. The gateway host is even more sensitive because the documented deployment posture includes a SYSTEM-level remote-command agent; it must never become a general CI runner.

**Required design:** Use a pull-based release installer on each production host, with one fixed, reviewed command surface: download an approved artifact by immutable digest, verify signature, execute pre-defined health/rollback actions, and emit an audit record. It must not run repository-supplied workflow code. Keep GitHub-hosted CI separate from production credentials and networks.

### CD-02 — SHA-256 alone is not a release trust anchor

**Severity:** P0 — supply-chain release blocker.

The proposed archive contains a SHA-256 checksum, but the plan does not define who signs it, where the verifier obtains the trusted public key, whether release tags/assets are immutable, or how approvals bind to a digest rather than a mutable version label ([CI/CD architecture](CI_CD_ARCHITECTURE.md#release-build)). A checksum downloaded from the same compromised release location detects accidental corruption, not malicious replacement.

**Required design:** Produce a manifest containing artifact digest, source commit, tree digest, dependency-lock digest, test/fault-campaign references, and schema versions. Sign it with a key/identity trusted independently by the production host (for example, a keyless provenance/signature flow with pinned issuer policy, or an offline/team signing key). Production verifies the signature and exact digest before extraction. Protect tag creation and release publication.

### CD-03 — Proposed release switching does not match the current runtime entrypoints

**Severity:** P1 — deployment plan is incomplete and rollback may be ineffective.

The CI/CD document proposes stable Windows release roots. Existing runtime
entrypoints still require deliberate alignment before automated promotion:

- [`cloud_engine/windows/reclaim-ingest.xml`](../cloud_engine/windows/reclaim-ingest.xml)
  is the Windows Server 2025 WinSW template and must resolve the reviewed engine
  release beneath `C:\ProgramData\RECLAIM\releases`.
- [`pi_gateway/windows/install-gateway-task.ps1`](../pi_gateway/windows/install-gateway-task.ps1) registers a task using `C:\RECLAIM\pi_gateway\.venv\Scripts\python.exe` and a working directory of `C:\RECLAIM\pi_gateway`.

Changing `current` therefore does not change what either deployed service executes unless the unit/task is deliberately rewritten to use that stable path.

**Required design:** Choose one Windows release-root convention and make the
runtime templates use it before the first CI/CD deployment. The VM root is
`C:\ProgramData\RECLAIM\current`; the gateway root is `C:\RECLAIM\current`.
Release directories are immutable, switching is atomic, and deployment verifies
the resolved executable path after restart. Add a rollback test that proves the
process version actually changes in both directions.

### CD-04 — Dependencies are not reproducible between CI and production

**Severity:** P1 — release reproducibility and supply-chain blocker.

The plan calls for pinned dependencies, but actual deployment requirements contain lower-bound ranges, such as `numpy>=1.24`, `scipy>=1.10`, and `requests>=2.31`:

- [`cloud_engine/deploy/requirements-cloud.txt`](../cloud_engine/deploy/requirements-cloud.txt)
- [`pi_gateway/requirements.txt`](../pi_gateway/requirements.txt)

An artifact may pass CI with one dependency set and resolve a different package set at installation time on the VM/gateway. Installing from public indexes during a production change also adds an availability and supply-chain dependency.

**Required design:** Generate per-target, hash-verified lock files from a controlled build environment; record Python ABI/platform in the manifest; build or cache the exact wheels used by CI; and install production environments with hash enforcement and no dependency resolution. Test the exact release artifact, not only the source tree.

### CD-05 — Workflow/repository controls are unspecified

**Severity:** P1 — CI compromise can become release compromise.

The plan requires a protected branch but does not specify:

- required reviewers/CODEOWNERS for workflow, deployment, safety-model, and gateway changes;
- protected, immutable version tags;
- GitHub Actions permissions defaulting to read-only;
- pinning actions by full commit SHA;
- no repository/environment secrets in pull-request workflows;
- artifact retention and release-approval audit requirements.

**Required design:** Define these as mandatory repository settings before the first workflow. A change to `.github/workflows/`, deployment templates, Windows service/task definitions, command authority code, or safety thresholds requires explicit controls/safety owner approval in addition to normal code review.

### CD-06 — Restart/deploy during an active batch is not gated

**Severity:** P1 in advisory mode; P0 if active command authority is ever enabled.

The VM sequence unconditionally stops `reclaim-ingest` before switching release ([CI/CD architecture](CI_CD_ARCHITECTURE.md#vm-deployment)). The engine is stateful: filter, lifecycle, mass, and adaptive state are process-resident. The gateway maintains a durable queue whose backlog can then become stale. A restart during a real batch can therefore interrupt observation and invalidate any predictive continuity.

**Required design:** Require an operational deployment gate: system in a defined safe/idle maintenance state, active chamber is `NONE`, power is removed/verified by the independent control system, queue is below threshold, and the release owner has approved the maintenance window. For urgent defects during a batch, use a separately running shadow/canary instance and defer cutover; never “hot patch” the active process without a proven state-handoff protocol.

### CD-07 — Rollback has no persistent-state compatibility contract

**Severity:** P1 — rollback may worsen an incident.

The plan preserves `/var/lib/reclaim-ingest/` and `C:\ProgramData\RECLAIM\queue.db`, which is correct, but does not version or validate their format/state semantics. An upgrade may change ingest identity, queued payload schema, command semantics, or state interpretation; rolling an older binary back against newer persisted state is then undefined.

**Required design:** Each release manifest declares compatible queue/state schema versions and whether it performs a migration. Back up state before a migration; make migrations forward-only, reversible, or require explicit restore; perform a compatibility preflight before both upgrade and rollback. Treat command-envelope/schema changes as breaking changes requiring a coordinated gateway/VM rollout plan.

### CD-08 — Test plan does not yet gate the known red-team failures

**Severity:** P1 — green CI could certify known unsafe behavior.

The architecture’s generic fault tests are valuable, but they do not explicitly require the regressions needed for the findings already documented in this repository:

- predictive transactional stepping, finite/range validation, forecast/live-model parity, probability semantics, and degraded continuity;
- gateway malformed/oversized/single-client ingress behavior, strict cloud-response correlation, stale-backlog recovery, and command-envelope expiry;
- actuator-side `advisory` versus `active` authority behavior.

The remediation plan already sets the correct baseline: Workstream A is required before advisory deployment, while B–D gate any active authority ([remediation plan](../docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md#disposition-matrix--does-it-block-deployment)).

**Required design:** Turn each red-team finding into a named regression test and a CI-required check. A release must include a machine-readable test report mapping RT/GW/CD IDs to test IDs and outcome.

### CD-09 — The gateway’s manual delivery path lacks an artifact-to-action audit trail

**Severity:** P2 — operational traceability gap.

TeamViewer is a reasonable interim transport constraint, but a human-operated PowerShell process needs stronger control than “download version, verify checksum, run script.” The plan does not specify how the selected artifact digest, operator identity, machine identity, resolved runtime path, service/task result, health results, and rollback decision are recorded.

**Required design:** The gateway deployment script accepts only a manifest URI plus immutable digest, verifies signature locally, writes an append-only deployment receipt, and refuses non-approved/unknown versions. It must never print tokens. Preserve a transcript and upload the non-secret receipt to the release record.

### CD-10 — Side-by-side validation is not yet a safe canary design

**Severity:** P2 — avoid accidental dual writers or dual control paths.

The plan correctly requires one live gateway and one live Convene writer, but it does not specify how a candidate receives representative traffic without becoming a second writer or command source. Starting a second engine against live telemetry can create duplicate action paths unless it is explicitly isolated.

**Required design:** Candidate services run in `advisory` mode with a distinct listener/namespace and no tunnel route consumed by the production gateway. Feed them a recorded, sanitized replay or a deliberate tee that cannot alter production state. Compare outputs against the active release, then perform a maintenance-window cutover—not traffic splitting—until state handoff and command authority are formally validated.

## Integration plan: CI/CD that supports frequent safe fixes

### Phase 0 — Establish release governance before automation

1. Initialize the private Git repository with a reviewed baseline.
2. Protect `main` and version tags; require review and required checks.
3. Add CODEOWNERS for workflow/deployment files, predictive/control code, gateway code, and safety thresholds.
4. Keep deployment secrets exclusively on production hosts. CI receives no production credentials and makes no live connections.
5. Set command authority to `advisory` by default and prevent an `active` configuration from being released until its dedicated evidence gates are satisfied.

### Phase 1 — Build trustworthy CI

CI runs on pull requests and `main`, with no production access:

| Required check | Purpose |
|---|---|
| Compilation, lint, format, secret/config scan | Basic correctness and accidental-secret prevention |
| Locked-environment unit tests | Reproducible gateway and engine behavior |
| Gateway-to-engine loopback integration | Ingest/ack/identity contract |
| Named RT/GW/CD regressions | Prevent reintroduction of red-team findings |
| Seeded small fault campaign | Data-loss/retry/recovery behavior |
| Release-candidate full campaign | Required before a production promotion |

CI produces a release candidate only from a protected `main` commit. The candidate is an immutable archive plus signed manifest, dependency locks/wheels, SBOM, test reports, fault seeds, and release notes.

### Phase 2 — Controlled, pull-based production promotion

1. A reviewer approves an **artifact digest**, not an arbitrary branch/tag.
2. The target host’s fixed deployment tool downloads that artifact, verifies its signature/digest and compatibility manifest, then creates an immutable release directory.
3. It runs local preflight checks using the artifact’s locked environment.
4. It verifies the operational maintenance gate before switching the stable release path.
5. It restarts only the intended service/task, verifies the executable path/version, loopback health, configuration integrity, queue/state compatibility, and—for the VM—ingest readiness.
6. It writes a deployment receipt. Failure restores the previously recorded release and verifies recovery.

The VM deployment tool may run as a narrowly permissioned service account or manual operator command. It must not be a general GitHub Actions runner. The Windows gateway remains operator-triggered until a similarly narrow, approved pull agent exists.

### Phase 3 — Change classes for rapid bug fixes

Fast delivery should shorten the approval path for low-risk changes, not remove safety gates.

| Change class | Examples | Minimum promotion path |
|---|---|---|
| Documentation / non-runtime | docs, comments, operator checklist | PR CI; no deployment required |
| Observability-only | metrics, logs, non-command status fields | PR CI + artifact approval; VM/gateway maintenance gate if deployed |
| Telemetry/ingest | schema, framing, queue, normalization | Full contract/fault suite + staged/shadow validation + coordinated VM/gateway compatibility review |
| Predictive/advisory | UKF, forecast, residual, advisor | Full engine regression suite + replay/fault evidence + shadow comparison before cutover |
| Command/safety/deployment | authority mode, command schema, power limits, TLS, runtime template, workflow | Independent reviewer, full release-candidate suite, maintenance window, explicit rollback drill; no active-command authority unless B–D gates are closed |

No change class permits modifying the hardware interlock through this pipeline.

## Required CI acceptance mapping

Before implementation, create one test per row and make it a required check:

| ID | Required proof |
|---|---|
| RT-01 / RT-08 | Forecast/residual parity with all enabled plant terms and mass evolution |
| RT-03 / RT-05 | Failure after first chamber leaves no state mutation; malformed/non-finite input is rejected before mutation |
| RT-04 | Output is not named/used as probability without calibration evidence |
| RT-06 | Gap enters degraded state; no actionable command until healthy-frame recovery |
| RT-02 / RT-07 | Advisory is non-actionable; active command envelope has source correlation and expires fail-closed |
| GW-02 | Gateway rejects invalid/expired/unmatched command and does not surface it as actionable |
| GW-03 / GW-04 | Bounded receiver rejects arrays, invalid shapes, oversized/slow lines, and competing clients without service loss |
| GW-05 / GW-07 | Live config rejects insecure endpoint/TLS; malformed/unmatched 2xx response does not acknowledge queue items |
| GW-06 / GW-10 | Outage recovery drops/archives expired data locally, surfaces degraded state, and persists loss audit |
| CD-03 / CD-07 | Upgrade and rollback execute the intended binary and pass state/queue compatibility preflight |
| CD-06 / CD-10 | Deployment is refused during active operation; shadow candidate cannot publish/command production |

## Handoff checklist

- [ ] Decide whether the SYSTEM-level remote-command agent is removed or moved off the gateway before any control-connected deployment.
- [ ] Amend `CI_CD_ARCHITECTURE.md` to reject production self-hosted Actions runners and to require signed digest-bound artifacts.
- [ ] Define stable release roots and update the Windows services/tasks to execute through them.
- [ ] Create lock files, a wheel/artifact build, and a signed manifest format.
- [ ] Implement the regression tests above before calling CI a safety gate.
- [ ] Create fixed, least-privilege VM and gateway deployment tools with receipts and tested rollback.
- [ ] Define active-batch maintenance gates and state/queue compatibility policy.
- [ ] Keep authority `advisory`; do not release `active` authority until the predictive and gateway safety plans are fully closed and independently reviewed.

## Verification note

This review found no `.github` workflow, dependency lock file, release builder, or deployment script implementing the proposed CI/CD architecture in the workspace. The document is therefore a design review and integration handoff, not a validation of an existing pipeline.
