# RECLAIM Live Twin — Fast Integration Plan

> **Objective:** get the advisory-only Live Twin integrated and demonstration-ready
> in the next few days. Production-grade CD is out of scope.

> **Authoritative schedule/platform:** Tuesday 2026-08-18 is the cloud-hosted
> Windows Server 2025 VM deployment and Convene binding day. Wednesday
> 2026-08-19 is the full cRIO → Windows 10 gateway → Cloudflare → Windows VM →
> Convene pipeline with hardware-bound telemetry. Kubernetes hosts the Windows
> VM; it is not a Linux guest deployment.

## Ownership

| Owner | Workstream |
|---|---|
| Luke / MacBook | Repository, pull request, CI, release identity, Windows VM engine/state bridge, Convene coordination |
| Adam / lab | Physical RECLAIM system, cRIO, Windows edge gateway, real telemetry validation |
| Both | End-to-end test, nominal/outage/lunar demonstrations, final evidence |

Adam has direct physical access to RECLAIM and the Windows desktop. He should work
locally on that machine rather than routing routine lab work through the MacBook.
Remote-control connectors remain useful for coordination and troubleshooting, but
they are not the deployment architecture.

## Guardrails

- Keep all twin output advisory and non-actionable.
- The existing physical interlocks and LabVIEW sequencer retain sole authority.
- Do not commit tokens, live URLs, credentials, queue data, or machine-specific
  configuration.
- Do not overwrite `C:\RECLAIM\pi_gateway`; preserve it as the submission-era
  baseline until the new checkout passes its tests.
- Work on branches and use pull requests; do not develop directly on `main`.
- Run the gateway from a console first. Install or change its boot task only after
  the end-to-end path is proven.

## Tuesday 2026-08-18 — VM integration and gateway preparation

### 1. Repository access

Invite Adam to `lukejwaszyn/RECLAIM_LiveTwin` with **Write** permission. Admin
permission is unnecessary.

Adam then runs:

```powershell
git config --global user.name "Adam <surname>"
git config --global user.email "<Adam's GitHub email>"
New-Item -ItemType Directory -Force C:\RECLAIM\src
Set-Location C:\RECLAIM\src
git clone https://github.com/lukejwaszyn/RECLAIM_LiveTwin.git
Set-Location RECLAIM_LiveTwin
git switch main
git pull --ff-only
git switch -c adam/gateway-integration
```

If the integrity pull request has not yet merged, use its exact reviewed commit
instead of assuming `main` contains the new backend contract.

### 2. Preserve what is already on the gateway

Before changing the Windows runtime, capture:

- hash inventory of files under `C:\RECLAIM\pi_gateway`;
- Python version and installed packages;
- paths and file metadata for configuration and `queue.db`, without displaying
  secrets or copying operational data into Git;
- listeners on 9070/9080 and any running gateway process;
- `RECLAIM-EdgeGateway` and `Convene-Agent` scheduled-task definitions.

Do not delete, rename, update, or run `git pull` inside the existing directory.
The new repository checkout under `C:\RECLAIM\src` is the working copy.

### 3. Prove the clean checkout

From the cloned repository:

```powershell
py -3.13 -m pip install "uv==0.11.21"
py -3.13 -m uv sync --locked --all-extras --dev --python 3.13
Set-Location pi_gateway
$env:PYTHONPATH = "."
..\.venv\Scripts\python.exe -m pytest tests -q
```

Expected result: all gateway tests pass. If dependency installation does not
match the repository lock/install instructions, stop and reconcile it rather
than improvising a second environment definition.

### 4. Bring up the real gateway path

Adam owns these physical steps:

1. Confirm the cRIO and Windows Ethernet addresses.
2. Confirm the expected raw LabVIEW field names from one real frame.
3. Run the gateway with console configuration and no boot task.
4. Verify `/health` and `/latest` on loopback.
5. Confirm sequence, timestamp, active chamber, operation state, and raw values.
6. Capture one redacted nominal frame for mapping verification.

Day 1 handback from Adam:

- branch/commit used;
- gateway test result;
- actual cRIO field-name list;
- redacted `/latest` sample;
- any mapping or configuration deviations;
- confirmation that no active command path was connected.

## Tuesday in parallel — MacBook and Windows Server 2025 VM

Luke's parallel lane:

1. Restore GitHub CLI authentication.
2. Review and merge the integrity PR when checks and review are complete.
3. Deploy the exact reviewed engine commit to the Windows Server 2025 VM using
   `VM_ENGINE_RUNBOOK.md`.
4. Run it on loopback in advisory mode with persistent identity state.
5. Verify `/health`, `/manifest`, `/state`, `/history`, and authenticated
   `/ingest` locally.
6. Establish the demonstration tunnel/hostname and create the separate ingest
   and read tokens.
7. Install and validate the Windows state bridge; bind its output through the
   existing VM Convene agent with the fail-closed publication lease.
8. Hand Adam only the gateway endpoint and ingest token through the agreed
   private channel—not through Git, issues, logs, or screenshots.

The VM does not need an automated production installer for this event. Record
the commit, directory, Python version, configuration path, and restart command so
the manual deployment is reproducible.

## Wednesday 2026-08-19 — hardware-bound full pipeline

Adam updates the external Windows configuration with the VM ingest endpoint and
token, then runs the gateway in a console.

Verify in order:

1. A fresh frame is accepted once.
2. A duplicate does not step the engine twice.
3. Stale or malformed data is rejected without state mutation.
4. Gateway queue drains after a temporary network interruption.
5. VM `/state` matches gateway `/latest` for identity, sequence, timestamp,
   active chamber, operation state, and mapped process values.
6. Advisory output returns to the gateway/HMI but remains visibly non-actionable.
7. Stopping telemetry makes freshness grow and the display fail closed.

Fix real schema/mapping differences in Adam's branch, add or update tests, and
open a pull request. Keep machine-specific configuration outside the commit.

## Wednesday after pipeline proof — Convene V&V and demonstration

Connect exactly two live consumers:

- one `sim_` publisher reading normalized VM `/state`;
- one `gw_` audit publisher reading raw gateway `/latest`.

Bind the existing `.stp` model parts to the corresponding operational variables.
The visualization should make the active chamber, process phase, thermal state,
power state, advisory, prediction, model trust, and data freshness obvious.

Run and record:

1. Nominal Earth-lab scenario twice.
2. Five-minute power-outage scenario once.
3. Lunar-surface scenario once.
4. Loss-of-data/freshness behavior once.

For every run, retain the commit, run ID, timestamps, expected result, observed
result, screenshots/video, and deviations. Keep the synthetic services as the
fallback, clearly labeled as rehearsal data.

## Definition of done

- Adam can clone, branch, test, and open a pull request.
- The existing gateway baseline remains recoverable and unchanged.
- Real cRIO telemetry reaches the clean Windows checkout.
- The gateway publishes accepted frames to the VM.
- Convene shows raw `gw_` and normalized/predictive `sim_` data with correct
  provenance and freshness.
- The `.stp` visualization responds to the bound live variables.
- Nominal, outage, and lunar scenarios are demonstrated.
- All recommendations remain advisory; hardware safety authority is unchanged.

## Immediate sequence

1. Obtain Adam's GitHub username and send the Write invitation.
2. Merge or identify the exact integrity commit Adam should use.
3. Adam clones and validates the gateway while Luke brings up the VM.
4. Exchange endpoint/token privately and perform the Day 2 integration.
5. Bind Convene and rehearse the final presentation.
