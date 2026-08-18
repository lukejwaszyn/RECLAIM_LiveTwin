# Luke Handoff — Local Source, VM Engine, and Convene Lane

> **Owner:** Luke  
> **Status:** Ready for the next integration session (2026-08-17)  
> **Objective:** make the reviewed engine reachable and demonstrably correct while
> Adam deploys and validates the Windows gateway against the physical RECLAIM system.
> This is an advisory-only demonstration deployment. Production-grade CD is out of
> scope.

## Finish line for this lane

Luke's lane is complete when:

- the exact reviewed source revision is recorded and passes the local source gate;
- the synthetic services remain available as a labeled fallback;
- the production-mode ingest service runs on the VM at `127.0.0.1:8078` with
  persistent state and separate ingest/read tokens;
- a Cloudflare hostname or quick-tunnel URL reaches that service;
- the live acceptance harness passes through the public URL;
- Adam privately receives only the `/ingest` URL and ingest token;
- Convene reads normalized engine state using the read token and the existing STEP
  model/bindings are reconciled to the final field contract; and
- one synthetic run and one real-gateway run are captured with source revision,
  run identity, timestamps, and evidence.

This lane does **not** include automatic promotion, fleet management, signed
artifacts, blue/green deployment, or production-grade secret management.

## Ownership boundary

| Luke owns | Adam owns | Rendezvous |
|---|---|---|
| Branch/PR/CI, exact source revision, local tests, VM engine, tunnel, engine acceptance, Convene coordination | Physical RECLAIM system, cRIO link, Windows gateway, real raw-frame validation, local gateway configuration | Endpoint handoff, first accepted frame, field reconciliation, end-to-end V&V, demonstration rehearsal |

Remote control of the lab endpoints is a support channel. It is useful for a
joint troubleshooting session, but it does not change ownership or become a
runtime dependency.

## Starting point

- Repository: `lukejwaszyn/RECLAIM_LiveTwin`
- Integration branch: `agent/rt03-rt05-convene-integrity`
- Draft PR: `#1`
- Last recorded branch revision: `d87bbae4b097dff3ac7eacfbc909e59b0259b0da`
- Integrity implementation begins at `3379402`; subsequent commits add tests and
  integration documentation.
- Adam's GitHub account `adamzim30` has a pending Write invitation.
- `Convene-Systems` is a GitHub organization, not an individual collaborator;
  repository access still requires a named user or a separately approved transfer.

Treat these as a pickup point, not a permanent deployment identity. Refresh the PR
and record the exact revision used before copying anything to the VM.

## Phase 1 — Close the local source gate

From the repository root on the MacBook:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
gh pr checks 1
uv sync --locked --all-extras --dev --python 3.13
python3 scripts/check_repository_hygiene.py
cd cloud_engine
../.venv/bin/python -m pytest tests/test_rt03_rt05_integrity.py -q
../.venv/bin/python -m pytest tests -q
cd ../pi_gateway
PYTHONPATH=. ../.venv/bin/python -m pytest tests -q
```

Gate:

- worktree changes are intentional;
- repository hygiene passes;
- RT-03/RT-05 and full cloud tests pass;
- gateway tests pass; and
- all required PR checks pass before merge or release selection.

After review, choose either the reviewed PR head or the merged `main` revision.
Record the full SHA as `TARGET_SHA` in the session notes. Never deploy the old
candidate manifest under `artifacts/`; its recorded revision predates the current
integrity work.

## Phase 2 — Keep the local demonstration fallback ready

These services are synthetic and must be labeled as such. They are not the public
ingest endpoint and should not be exposed through the tunnel.

From `cloud_engine/`, run each in its own terminal when needed:

```bash
../.venv/bin/python -m reclaim_predictive_engine.service --scenario nominal --env earth_lab --host 127.0.0.1 --port 8177 --speed 6
../.venv/bin/python -m reclaim_predictive_engine.service --scenario outage --env earth_lab --host 127.0.0.1 --port 8178 --speed 12
../.venv/bin/python -m reclaim_predictive_engine.service --scenario nominal --env lunar_surface --host 127.0.0.1 --port 8179 --speed 6
```

Smoke-test `/health`, `/manifest`, `/state`, and `/history` on each port. The
nominal service is the fallback for visualization work while Adam is offline; the
outage and lunar services are rehearsal scenarios.

## Phase 3 — Discover before changing the VM

On the VM, collect the following without printing tokens or environment-file
contents into captured logs:

```bash
hostnamectl
python3 --version
df -h
systemctl status reclaim-ingest.service --no-pager
systemctl status cloudflared.service --no-pager
sudo ss -ltnp
sudo find /opt/reclaim -maxdepth 3 -type d 2>/dev/null
```

Also record:

- login user and intended service user;
- current engine directory and revision, if any;
- whether `/etc/reclaim/reclaim-ingest.env` exists and its permissions;
- whether `/var/lib/reclaim-ingest/ingest_state.json` exists; and
- the current tunnel type and hostname, if any.

Do not overwrite an unexpected running deployment. If the VM is not in the state
described by `VM_ENGINE_RUNBOOK.md`, preserve it, identify what owns port 8078, and
reconcile the discrepancy first.

## Phase 4 — Deploy the exact revision to the VM

Use a fresh directory for the selected revision. If this is genuinely the first VM
install, the supplied unit expects `/opt/reclaim/engine`. If that path already
contains a deployment, stage the new revision under
`/opt/reclaim/releases/<TARGET_SHA>` and deliberately update a copy of the unit's
`WorkingDirectory` and `ExecStart`; do not overwrite the existing tree in place.

Minimum deployment record:

| Item | Record |
|---|---|
| Full source SHA | `TARGET_SHA` |
| VM directory | Exact absolute path |
| Python | Version and virtual-environment path |
| Unit | Unit name and installed unit-file checksum |
| Configuration | Path only; never values |
| State | Persistent state-file path |
| Tunnel | Type and public base URL |

Follow `VM_ENGINE_RUNBOOK.md` for transfer and environment setup. Before starting
the service, run this import gate from the VM virtual environment:

```bash
python -c "import numpy, scipy, sklearn; print('engine dependencies import')"
```

The supplied unit is designed for:

- `127.0.0.1:8078` only;
- `--production` and `--max-frame-age-s 15`;
- configuration at `/etc/reclaim/reclaim-ingest.env`; and
- persistent identity at `/var/lib/reclaim-ingest/ingest_state.json`.

Generate independent, high-entropy ingest and read tokens. Store them only in the
root-owned environment file with mode `0600`. Do not paste tokens into GitHub,
session notes, screenshots, recorded terminals, or this document.

Start and inspect the engine:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reclaim-ingest.service
systemctl status reclaim-ingest.service --no-pager
sudo ss -ltnp | grep 8078
curl --fail --silent http://127.0.0.1:8078/health
```

Pass the read token only in the authorization mechanism expected by the endpoint
when checking `/manifest`, `/state`, `/history`, and `/command`. Avoid commands that
echo secrets into shell history.

## Phase 5 — Establish and prove the external endpoint

A Cloudflare quick tunnel is acceptable for this event if a stable named tunnel is
not already configured. Record that a quick-tunnel URL is ephemeral and reissue the
endpoint handoff if it changes. Expose only `127.0.0.1:8078`; never expose the local
synthetic ports.

Run the repository's acceptance harness through the public URL from the MacBook:

```bash
cd cloud_engine
../.venv/bin/python tools/redteam_ingest.py \
  --url https://<engine-host> \
  --ingest-token '<private-ingest-token>' \
  --read-token '<private-read-token>'
```

Required result: all 20 checks pass. Then restart the ingest service and verify:

- `active_run_id` persists;
- the accepted sequence boundary persists;
- replaying the last accepted frame does not step the engine again; and
- fresh telemetry is accepted after restart.

## Endpoint packet for Adam

Send this privately after VM acceptance:

| Field | Value |
|---|---|
| Base URL | `https://<engine-host>` |
| Gateway destination | `https://<engine-host>/ingest` |
| Credential | Ingest token only |
| Schema | `reclaim.telemetry.v1` |
| Maximum frame age | 15 seconds |
| Engine source | Full `TARGET_SHA` |
| Availability window | Planned integration start/end |
| Support | Luke plus agreed remote-control channel |

Do not send Adam the read token unless his gateway implementation demonstrably
requires it; the normal gateway path only writes to `/ingest`. Ask Adam to return:

- gateway branch and SHA;
- redacted `/latest` sample;
- actual raw cRIO field-name list;
- timestamp, sequence, active chamber, and operation-state semantics; and
- confirmation that the advisory output is not wired to control authority.

## First-frame rendezvous

Luke watches the VM while Adam starts the gateway:

```bash
sudo journalctl -fu reclaim-ingest.service
```

Verify in this order:

1. `/health` stays healthy before traffic.
2. One fresh frame is accepted.
3. Engine `/state` matches Adam's `/latest` for source, sequence, timestamp,
   active chamber, operation state, and mapped process values.
4. A duplicate is acknowledged without a second model step.
5. A malformed or stale frame is rejected without state mutation.
6. A short network interruption queues data on the gateway and drains cleanly.
7. Loss of telemetry increases freshness age and the UI fails closed.

If fields disagree, fix the contract and tests in Adam's branch. Do not patch
machine-specific configuration into the repository or normalize unexplained values
silently on the VM.

## Convene cutover

Use exactly two live data paths:

- `sim_`: normalized/predictive state from VM `/state`, authenticated with the
  read token;
- `gw_`: raw audit state from the Windows gateway `/latest`.

Reuse the submission-era `.stp` model and existing part-to-variable bindings.
Reconcile them against the actual final field names; do not rebuild the visualization
unless a binding is genuinely missing. Confirm the display clearly distinguishes
source, environment, run, sequence, freshness, model trust, active process state,
and advisory output. `DATA LIVE` must fail closed when either required source is
stale or mismatched.

The `/command` surface remains advisory. Physical interlocks and the LabVIEW
sequencer retain sole control authority.

## Checkpoints with Adam

| Checkpoint | Luke brings | Adam brings | Exit condition |
|---|---|---|---|
| A — Source | Reviewed `TARGET_SHA`, passing checks | Clean checkout and passing gateway tests | Both lanes use known revisions |
| B — Endpoint | Accepted public URL and private ingest token | Console-ready gateway configuration | No secret or URL committed |
| C — First frame | VM logs and authenticated state view | Real `/latest` frame and raw field list | Identity and process fields agree |
| D — V&V | `sim_` feed, engine evidence, Convene view | `gw_` feed, physical observations | Nominal, outage, lunar, and stale-data behaviors captured |

## Evidence to retain

For each accepted run, capture:

- date/time and operator;
- MacBook, VM, and gateway source SHAs;
- engine run ID and source identity;
- environment and scenario;
- first/last sequence and timestamps;
- harness/test results;
- redacted state and gateway samples;
- Convene screenshots or video showing model-part response and freshness; and
- deviations, decisions, and follow-up owner.

Never include tokens, operational credentials, or unredacted machine configuration.

## Stop conditions

Stop and reconcile rather than improvising if:

- the selected revision does not pass its gate;
- port 8078 or the service directory is owned by an unknown deployment;
- the engine binds anything other than loopback;
- identity changes unexpectedly after restart;
- source/sequence/timestamp semantics differ between the gateway and VM;
- Convene shows data as live when either source is stale; or
- any advisory output is connected to hardware control authority.

## Immediate sequence tomorrow

1. Refresh PR #1, close the source gate, and record `TARGET_SHA`.
2. Confirm the synthetic nominal fallback locally.
3. Discover the VM's real state and deploy the exact revision side-by-side.
4. Start the loopback production-mode engine and external tunnel.
5. Pass the 20-check acceptance harness and restart-persistence test.
6. Send Adam the private endpoint packet.
7. Meet at the first-frame checkpoint, reconcile real fields, then connect Convene.
8. Rehearse and record nominal, outage, lunar, and stale-data behavior.

