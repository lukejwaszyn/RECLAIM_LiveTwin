# RECLAIM Live Twin — CI/CD Architecture

> **Status:** Local CI/release-candidate baseline implemented; remote repository
> controls and every production-promotion mechanism remain pending. The red-team
> requirements in [CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md](CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md)
> take precedence over any conflicting language in this document.
>
> **Scope:** controlled code verification and future promotion from the MacBook
> workspace to the predictive-engine VM and Windows gateway.

## Purpose

RECLAIM deployment is a controlled promotion path, not a mechanism to overwrite
live machines whenever code is pushed. Each deployed version must be traceable to
an exact source commit, verified before deployment, and reversible.

```text
Developer changes code on Mac
        |
        v
Commit + pull request
        |
        v
CI validates the exact commit
        |
        v
Approved release artifact is created
        |
        +--> VM deployment --> systemd predictive engine + named Cloudflare Tunnel
        |
        +--> Gateway deployment --> TeamViewer-operated PowerShell script
                                      -> Windows Scheduled Task
```

## Topology and responsibilities

| Component | Role | Deployment mechanism |
|---|---|---|
| MacBook workspace | Source development, local sanity checks, Monte Carlo fault injection, release approval | Git client and GitHub web interface / CLI |
| CI service | Tests, release packaging, traceability | GitHub Actions hosted runner |
| Predictive-engine VM | Production engine, loopback-only ingest service, Cloudflare Tunnel | Future fixed, least-privilege pull installer; never a general CI runner |
| Windows gateway | cRIO receiver, durable queue, authenticated cloud publisher | Approved, operator-run PowerShell release script through TeamViewer |
| cRIO / LabVIEW | Live telemetry producer | Never deployed by this pipeline |
| Convene | Read-only state consumer and visualization | Not changed until live V&V passes |

The Windows gateway's WDAC policy prevents conventional inbound SSH/RDP
administration. This is an architectural constraint: use TeamViewer for the
gateway deployment step until a specifically approved, restricted outbound
deployment mechanism exists. Do **not** repurpose the SYSTEM-level Convene agent
as a general CI deployment runner.

## Source code enters the system

The MacBook workspace is the working copy and eventual source of truth.

1. Modify code, tests, or deployment templates in the workspace.
2. Run local sanity tests and non-production fault injection.
3. Commit the changes to a feature branch.
4. Push the branch and open a pull request.
5. CI validates that exact commit.
6. Merge an approved pull request to `main`.
7. Create a version tag, such as `v0.2.0`, to produce an immutable release bundle.

Production machines receive the approved release bundle, not arbitrary files
copied from the Mac. A future promotable bundle must bind its source commit and
artifact digest to an independently verifiable signed manifest. The current
workflow produces an explicitly unsigned, non-promotable candidate only.

### Initial prerequisite

This workspace was not a Git repository when this plan was drafted. The local
baseline now contains CI configuration, a dependency lock, and release-candidate
tooling. Before enabling remote CI and any promotion:

1. Create a private remote repository under the approved organization/owner.
2. Review and publish the local baseline commit.
3. Configure a protected `main` branch and protected version tags.
4. Require the named checks in
   [RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md](../docs/RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md)
   before merge.
5. Replace the CODEOWNERS placeholders with approved user/team identities.

Do not treat `RECLAIM_LiveTwin 2.zip` as a deployment source. It is an archive or
handoff artifact; Git tags and release bundles become the controlled lineage.

## CI: verification before promotion

Use GitHub Actions for CI. It is low-maintenance, supports a private repository,
and provides an auditable record of every release. CI never receives production
tokens and never contacts the live VM, gateway, cRIO, or Convene namespace.

Run these checks on every pull request and `main` push.

### 1. Static checks

- Python compilation (`python -m compileall`).
- Lint and format check (for example, Ruff).
- Secret scan.
- Verify example configuration contains no live URLs or tokens.

### 2. Unit and contract tests

- Gateway: `PYTHONPATH=. python -m pytest tests -q` from `pi_gateway/`.
- Engine: `python -m pytest tests -q` from `cloud_engine/`.
- Run the matrix on Python 3.11 and 3.13. Do not make Python 3.14 a deployment
  target until its dependencies and tests are proven compatible.

`pytest` and lint tools belong in an explicit development/CI requirements file;
they must not be assumed present on the MacBook or deployment hosts.

### 3. Local integration contract

Start the engine locally on loopback with an ephemeral test token, then submit
frames through the gateway HTTPS publisher. Assert:

- fresh frame acceptance;
- duplicate recognition without a second state step;
- stale final rejection and gateway dead-letter behavior;
- restart-safe run/sequence identity;
- production rejection of `mode: harness`.

### 4. Deterministic fault injection

Keep Monte Carlo runs reproducible: record a seed and save it with every report.
Inject delayed, duplicated, out-of-order, malformed, and stale frames; dropped
acknowledgements; engine restarts; and gateway restarts.

Safety assertions must include:

- no duplicate engine step;
- bounded durable-queue growth;
- final rejects become dead letters rather than endless retries;
- recovery after connection loss;
- no synthetic/harness frame reaches a production-mode service.

Run a small seeded campaign on pull requests and a larger campaign nightly.
Publish result files and seeds as CI artifacts.

### 5. Release build

After all required checks pass on `main`, produce a candidate archive containing:

- `cloud_engine/`;
- `pi_gateway/`;
- deployment scripts and service templates;
- release manifest: version, commit SHA, build timestamp, test results, and
  fault-injection seed(s);
- SHA-256 checksum and digest-bound manifest.

The implemented candidate manifest states `signed: false` and
`production_promotable: false`. Production promotion remains blocked until the
signing identity, verifier trust policy, state compatibility rules, and fixed
host installers are approved and implemented.

Never package virtual environments, `__pycache__`, databases, ingest state,
logs, or secret files.

## CD: controlled deployment

Use protected deployment environments for independent approvals:

- `production-vm`
- `production-gateway`

An approval selects a specific, already-tested release version. A deployment
must be idempotent, verify health after change, and retain a tested rollback
target.

### VM deployment

Do not install a GitHub Actions runner on the production VM. After the manual
runbook is proven, implement a fixed, least-privilege pull installer whose only
accepted operation is to retrieve an approved immutable digest, verify its
signature and compatibility manifest, perform predefined health/switch/rollback
steps, and write a deployment receipt. That installer is not part of the current
baseline.

For release `v0.2.0`, the deployment procedure is:

1. Download the specified release archive and verify its signed manifest and
   exact SHA-256 digest against the independently pinned trust policy.
2. Extract it into `/opt/reclaim/releases/v0.2.0`.
3. Create a release-local virtual environment and install the pinned
   dependencies.
4. Run imports, unit checks, and loopback health checks.
5. Stop `reclaim-ingest`.
6. Point `/opt/reclaim/current` at the selected release.
7. Start `reclaim-ingest` and verify it is active, binds only
   `127.0.0.1:8078`, and answers `/health` locally.
8. If any verification fails, restore `/opt/reclaim/current` to the previous
   release and restart that known-good service.

Keep `/etc/reclaim/reclaim-ingest.env` and `/var/lib/reclaim-ingest/` outside
release directories. CI must not read, copy, or log their contents.

Before unattended operation, replace the ephemeral Cloudflare quick tunnel with
a named tunnel and stable hostname. A quick-tunnel hostname changes after a
restart and would invalidate the gateway's cloud URL.

### Gateway deployment

The gateway rollout remains human-triggered until a narrowly scoped outbound
deployment capability is approved. The operator uses TeamViewer to run the
idempotent deployment script after approving `production-gateway`.

For release `v0.2.0`, the script must:

1. Download the selected release archive and verify its signed manifest and
   exact digest against the independently pinned trust policy.
2. Expand it to `C:\\RECLAIM\\releases\\v0.2.0`.
3. Build/update the release virtual environment.
4. Validate configuration without printing its token.
5. Run gateway tests.
6. Stop the `RECLAIM-EdgeGateway` scheduled task.
7. Switch a `C:\\RECLAIM\\current` junction or equivalent stable path to the
   chosen release.
8. Start the task and verify loopback health, queue state, and cloud
   acknowledgement.
9. If verification fails, switch back to the previous release and restart it.

Keep `C:\\RECLAIM\\pi_gateway\\config.windows.yaml` and
`C:\\ProgramData\\RECLAIM\\queue.db` outside release directories. Restrict the
configuration ACL because it contains the ingest token.

Do not deploy the gateway until its existing live gates are complete: cRIO IP
configuration, stable VM endpoint, real tokens, the six contract gates, and the
three-column `gw_` / `sim_` V&V.

## Deprecating and offlining old code

Deprecation is deliberate; it is not an automatic side effect of deploying new
code.

1. **Run side-by-side.** Deploy a new version into a fresh directory and, when
   needed, a new port. Do not overwrite the active service in place.
2. **Validate.** Complete health, duplicate/stale/restart contract gates and the
   `gw_` versus `sim_` validation.
3. **Cut over.** Stop the previous service or publisher only after the new one is
   proven. There must be one live gateway for the cRIO stream and one writer of
   the Convene `sim_` namespace.
4. **Retain rollback.** Preserve the previous release directory and manifest for
   a defined rollback period, such as 30 days or one validated production batch.
5. **Retire.** Disable the old service, remove its active tunnel/Convene binding,
   retain its Git tag, and only later remove its deployment directory using an
   approved housekeeping procedure.

Git preserves old source history permanently. A retired version need not remain
active in order to be recoverable.

## Promotion matrix

| Stage | Trigger | Evidence | May touch live data? |
|---|---|---|---|
| Pull-request CI | Every pull request | Unit, contract, small fault-injection suite | No |
| Nightly CI | Scheduled | Larger seeded Monte Carlo campaign | No |
| Release candidate | Tag/manual | Full local gateway-to-engine integration | No |
| VM production | Approved dispatch | Engine health and rollback verified | Yes, after gates |
| Gateway production | Approved operator action | cRIO ingest and durable forwarding verified | Yes, last step |

## Implementation sequence

1. Initialize the local Git repository and create a clean baseline commit.
2. Create the approved private remote; add protected branches/tags and CI-required checks.
3. Maintain the locked CI environment, compilation check, and repository hygiene scan.
4. Add end-to-end contract and deterministic Monte Carlo harnesses.
5. Add versioned release archives, checksums, and manifests.
6. Complete the VM manual deployment, then migrate it to a named Cloudflare
   Tunnel.
7. Add the approved, fixed pull-based VM installer and deployment receipt flow.
8. Add the TeamViewer-operated gateway release script.
9. Complete live contract gates and `gw_` / `sim_` V&V before production gateway
   promotion.

## Deliberately excluded complexity

At this stage, do not add Docker, Kubernetes, or a separate secrets platform.
GitHub Actions, protected approvals, immutable release archives, signed
digest-bound manifests, systemd, Windows Task Scheduler, the existing TeamViewer
workflow, and a named Cloudflare Tunnel meet the present operational need with
less failure surface.
