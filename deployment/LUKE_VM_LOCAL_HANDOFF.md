# Luke Handoff — Windows Cloud VM, Convene, and Local Coordination

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

> **Owner:** Luke
> **Status:** Ready for Windows VM integration
> **Platform:** Windows Server 2025 VM in Kubernetes-managed cloud infrastructure

Read `DEPLOYMENT_TOPOLOGY.md` first. The edge gateway is a MacBook.
No Linux or Raspberry Pi runtime is part of the live pipeline.

## Finish line for Luke's lane

- Select and record the exact reviewed source revision.
- Discover and preserve the current Windows VM deployment before change.
- Run the production dual engine on `127.0.0.1:8078` with distinct ingest/read
  credentials and persistent run/sequence identity.
- Prove the Cloudflare ingress with the 20-check acceptance harness.
- Install and accept the independent Windows state bridge.
- Install the headless VM Convene agent and bind it to normalized state with single-writer,
  prefix, freshness, and publication-lease proof.
- Privately hand Adam only the `/ingest` URL and ingest credential.
- Capture one synthetic VM-to-Convene run and one real gateway-to-Convene run.

## Ownership

| Luke | Adam | Joint checkpoint |
|---|---|---|
| PR/CI, exact SHA, Windows VM engine, Cloudflare route, state bridge, VM `sim_` publisher, Convene coordination | Windows 10 live gateway and cRIO link; MacBook scenario publication | endpoint handoff, field reconciliation, full sequence, fail-closed evidence |

Kubernetes/hosting operators own the outer VM workload and storage policy. Controls
operators retain hardware authority and the independent interlock.

## Phase 1 — Source gate

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
gh pr checks 1
$env:UV_CACHE_DIR = Join-Path $env:TEMP 'reclaim-uv-cache'
$env:PYTHONPATH = 'pi_gateway'
uv run --frozen pytest -q convene_bridge\tests
uv run --frozen pytest -q cloud_engine\tests pi_gateway\tests
uv run --frozen python scripts\check_repository_hygiene.py
Remove-Item Env:PYTHONPATH
```

Record the full PR head or merged-main SHA as `TARGET_SHA`. Do not embed a moving
SHA in a durable runbook.

## Phase 2 — Windows VM discovery

Use the read-only commands in `VM_ENGINE_RUNBOOK.md`. Confirm Windows build,
services, tasks, port 8078, release directories, secret/state ACLs, cloudflared,
Convene agent identity, and `sim_vars.json` writers. Also confirm whether
`C:\ProgramData\RECLAIM` survives Kubernetes VM rescheduling.

Do not overwrite or stop an unexpected deployment.

## Phase 3 — Engine and tunnel

Follow `VM_ENGINE_RUNBOOK.md`:

1. stage `TARGET_SHA` under a fresh Windows release directory;
2. build the locked venv and run tests/import gates;
3. create ACL-protected, distinct ingest/read credentials;
4. install/reconcile `RECLAIMIngestEngine` through reviewed WinSW;
5. prove loopback-only port 8078 and durable identity;
6. preserve or establish the Windows cloudflared route; and
7. pass the 20-check endpoint harness and restart test.

## Phase 4 — Bridge and Convene

Follow `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`:

1. install/pair the headless VM agent and verify its identity and ACLs;
2. verify an approved WinSW binary/checksum;
3. install the bridge side-by-side with read credential only;
4. start in `passthrough` prefix mode;
5. use bridge metadata as the harmless prefix canary;
6. bind health/lease fields before process fields;
7. prove stale, unauthorized, engine-stop, bridge-stop, and file-lock behavior;
8. verify Convene computes current UTC against `bridge_valid_until`; and
9. confirm exactly one `sim_` writer and no change to `/command` authority.

Tuesday is complete only when authenticated synthetic ingest reaches Convene and
every failure case displays `DATA NOT LIVE`.

## Phase 5 — Gateway rendezvous

Privately provide Adam:

| Field | Value |
|---|---|
| Gateway destination | `https://<engine-host>/ingest` |
| Credential | ingest token only |
| Schema | `reclaim.telemetry.v1` |
| Maximum age | 15 seconds |
| Engine revision | full `TARGET_SHA` |
| Availability | agreed integration window |

Adam returns the gateway SHA, redacted first `/latest` record, actual raw field
names, identity/timestamp semantics, and confirmation that no advisory output is
wired to control.

## Wednesday full-pipeline sequence

1. Verify safe hardware state and the independent interlock.
2. Establish the Windows 10 desktop/cRIO direct network and narrow firewall rule.
3. Run the gateway manually before installing or starting its boot task.
4. Capture the first real `/latest` frame and reconcile names/units.
5. Pass fresh, duplicate, harness, stale, gateway-restart, engine-restart, and
   freshness-decay gates.
6. Publish the separate raw gateway audit namespace; never write `sim_` from the laptop.
7. Run one complete controlled process sequence with LabVIEW/raw gateway/`sim_`
   agreement and bounded lag.
8. Exercise network interruption, queue drain, telemetry stop, and component
   restart behavior.
9. Install the MacBook `launchd` LaunchAgent only after the foreground path passes.

## Evidence

Record operators, Windows VM identity, Kubernetes workload identity, VM/gateway
source SHAs, service identities, run/source IDs, sequence/time range, redacted
state/latest samples, test results, Convene screenshots, prefix mode, lease-expiry
evidence, deviations, and rollback result. Never record credentials.

## Stop conditions

Stop if source revisions are uncertain, port/service/file ownership is unexpected,
the engine is not loopback-only, durable identity is not persistent, gateway and
engine identity semantics differ, Convene remains live after lease expiry, multiple
writers exist, or advisory output gains hardware authority.
