# RECLAIM Live Twin

The clean working release for the next RECLAIM deployment: the active live-data
path, its tests, its deployment templates, and the Convene binding contract
(including the Convene-native `.stp` visualization).

It intentionally excludes archive folders, ZIP handoffs, cached environments,
synthetic emitters, old single-chamber services, scenario dashboards, trained
model artifacts, and previous Convene bridges. Those remain preserved in the
source workspace but are not part of this release.

> **Standing status: labeled engineering shadow — NO-GO for any production
> claim.** All engine output is advisory. No command, return, or actuation path
> exists anywhere in this repository.

---

## Quick start

### 1. Environment

The root `uv.lock` is the reproducible dependency source. Supported CI matrix is
Python 3.11 and 3.13.

```powershell
py -3.13 -m uv sync --locked --all-extras --dev --python 3.13
python scripts\check_repository_hygiene.py
```

### 2. Tests — expect **55 / 73 / 70**

Each suite needs its own package root on `PYTHONPATH`. Green across all three is
the pre-flight go-signal; **any red means stop, do not deploy.**

```powershell
$env:PYTHONPATH="pi_gateway";         python -m pytest pi_gateway -q          # 55
$env:PYTHONPATH="cloud_engine";       python -m pytest cloud_engine -q        # 73
$env:PYTHONPATH="crio_source_record"; python -m pytest crio_source_record -q  # 70
```

```bash
PYTHONPATH=pi_gateway         python -m pytest pi_gateway -q          # 55
PYTHONPATH=cloud_engine       python -m pytest cloud_engine -q        # 73
PYTHONPATH=crio_source_record python -m pytest crio_source_record -q  # 70
```

Bench replay must end `{'accepted': 3, ..., 'rejected': 0, 'sent': 3}`:

```powershell
$env:PYTHONPATH="pi_gateway;cloud_engine;$PWD"; python -m crio_source_record.bench_replay
```

### 3. Rehearsal scenarios — 3 to 5 minutes each

Three one-command targets. Each is **fully synthetic** (`--feed harness`), binds
loopback-only, refuses to start if its port is already taken, and prints its
expected behavior before running. Stop any of them with `Ctrl+C`.

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal        # 8177  ~3 min 20 s
.\cloud_engine\windows\start-rehearsal-scenario.ps1 power-outage   # 8178  ~3 min 45 s
.\cloud_engine\windows\start-rehearsal-scenario.ps1 lunar          # 8179  ~3 min 20 s
```

| Profile | Port | Physics | Wall time | What it shows |
|---|---:|---|---:|---|
| `nominal` | 8177 | `earth_lab`, 2x | ~3 min 20 s | Stable 2200 W heat-and-hold, steady advisory display |
| `power-outage` | 8178 | `earth_lab`, 4x | ~3 min 45 s | Outage at ~1 min 53 s, thermal coast, `S_Restart` at ~3 min 8 s, recovery |
| `lunar` | 8179 | `lunar_surface`, 2x | ~3 min 20 s | Same cycle under lunar physics, for environment contrast |

The runner uses the locked `.venv\Scripts\python.exe` created by step 1 and
refuses to start without it; pass `-PythonExe <path>` to point at a different
interpreter.

Inspect a running scenario on loopback:

```powershell
Invoke-RestMethod http://127.0.0.1:8177/health
Invoke-RestMethod http://127.0.0.1:8177/state
Invoke-RestMethod http://127.0.0.1:8177/history
```

**Where to run them.** The scenarios are self-contained — they need only this
checkout and the locked `.venv`, never the cRIO, the gateway, or a network feed.
Run them on any machine that is **not** currently serving production `8078`. In
practice that means the Windows 10 desktop/gateway during a deploy or demo
session, which keeps machine-level separation from the VM's production port. Do
not run them on the predictive-engine VM while it serves production: the script's
port guard is only port-level protection, and `8177`–`8179` must never be routed
to production or bound as live mission state.

**Loss-of-data / freshness check.** The rehearsal plan calls for a fourth run,
but it has **no scenario target** (it is installer build scope). Run it by hand:
start any profile, confirm `/health` is advancing, then stop the producer feed and
confirm the rx counter stops advancing and `last_ack_age_s` / `last_success_age_s`
climb. The stack must *report staleness*, not hold or fabricate a last-good value.

For every run retain: commit SHA, run ID, timestamps, expected vs observed,
screenshots, and deviations. Keep synthetic services clearly labeled as rehearsal
data.

---

## Runtime topology

```text
cRIO / LabVIEW -> Windows 10 gateway -> Cloudflare -> Windows Server 2025 VM
                                                       -> dual engine on loopback
                                                       -> Windows state bridge
                                                       -> headless VM Convene agent installed during bootstrap
                                                       -> Convene-native .stp visualization
```

The VM is cloud-hosted in Kubernetes-managed infrastructure, but the guest and
all repository-owned runtime procedures are Windows. There is no Linux host or
Raspberry Pi in the live path. The cloud engine owns state processing. The
headless VM Convene agent consumes the bridge's validated copy of the cloud
`/state` record; its native visualization binds the incoming variables to
elements of a `.stp` (STEP) model, animating the system's geometry as data
changes. The visualization is a read-only view of the same `/state` record — it
does not talk to the cRIO and is not a second predictive engine.

The VM is the sole publisher of the `sim_` namespace; the gateway publishes only
the read-only `gw_` audit namespace, and never writes a `sim_` variable.

## Contents

- `pi_gateway/` — Windows 10 cRIO receiver, provenance framer, durable queue, HTTPS
  publisher, configuration template, Windows service + scheduled-task templates, tests.
- `cloud_engine/` — Windows Server 2025 dual plastics/metals predictive engine with the
  autonomous per-chamber lifecycle (idle/running/suspended, self-resetting at batch
  boundaries), LabVIEW adapter, production ingest service, rehearsal scenario runner,
  deployment template, contract + lifecycle tests, and `tools/redteam_ingest.py`.
- `crio_source_record/` — offline source-record contract: parser, fixtures, conformance
  checker, and bench replay.
- `convene/` — binding specification (publisher `sim_` set plus the Convene-native
  `.stp` visualization bindings); no legacy binding is carried forward.
- `docs/` — live telemetry architecture, remote deployment preflight, and the
  predictive-engine fault/lifecycle memo.
- `deployment/` — handoffs, go/no-go punch list, and stage-labeled runbooks (see
  `deployment/README.md`; start at `VM_ENGINE_HANDOFF.md` for the VM session).

## What starts fresh

1. Gateway configuration and its `run_id` start with a new deployment configuration.
2. Cloud engine deployment uses `push_ingest_dual.py --production`, a new secret,
   and a free side-by-side port.
3. Convene receives one publisher and a new `sim_` binding set from this release.
4. The Convene-native visualization binds the same `/state` variables to `.stp`
   model elements, read-only.

## Hardening status

The 2026-08 review findings (`CODE_REVIEW.md`) are implemented — see `FIXES.md`.
Headlines: per-frame ingest acknowledgement (v1.1) with gateway-side
dead-lettering, run supersession on gateway reboot, persisted monotone sequence
identity (restart-safe dedup), no fabricated sensor values, sequencer chamber
authority, seal-monitor unit/phase correction, real-dt physics, and
half-open-socket protection on the gateway receiver.

RT-03/RT-05 integrity remediation is implemented on the current integration
branch. The locked local suite is green; deployment still requires review and CI
evidence for the exact committed SHA. See
`docs/RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md` before promotion.

## Before deployment

Run the contract tests on a supported Python environment, complete the remote
preflight, and deploy side-by-side. **Do not use this folder to overwrite a live
gateway or cloud installation in place.**

See `docs/RECLAIM_Remote_Gateway_Preflight.md` for the remote deployment sequence,
and `deployment/LIFECYCLE_RESTART_AUDIT_RECORD.md` for the current
graceful-closure/restart audit state and open items.
