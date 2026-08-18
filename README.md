# RECLAIM Live Twin

This is the clean working release for the next RECLAIM deployment. It contains
only the active live-data path, its tests, its deployment templates, and the new
Convene binding contract (which includes the Convene-native `.stp` visualization).

It intentionally excludes archive folders, ZIP handoffs, cached environments,
synthetic emitters, old single-chamber services, scenario dashboards, trained
model artifacts, and previous Convene bridges. Those remain preserved in the
source workspace but are not part of this release.

## Runtime topology

```text
cRIO / LabVIEW -> Windows 10 gateway -> Cloudflare -> Windows Server 2025 VM
                                                       -> dual engine on loopback
                                                       -> Windows state bridge
                                                       -> existing VM Convene agent
                                                       -> Convene-native .stp visualization
```

The VM is cloud-hosted in Kubernetes-managed infrastructure, but the guest and
all repository-owned runtime procedures are Windows. There is no Linux host or
Raspberry Pi in the live path. The cloud engine owns state processing. The
existing VM Convene agent consumes the bridge's validated copy of the cloud
`/state` record; its native visualization tool binds the incoming
variables to specific elements of a `.stp` (STEP) model, animating the system's
geometry as data changes in operation. The visualization is a read-only view of
the same `/state` record — it does not talk to the cRIO and is not a second
predictive engine.

## Contents

- `pi_gateway/` — Windows 10 cRIO receiver, provenance framer, durable queue, HTTPS publisher,
  configuration template, Windows service + scheduled-task templates, and framing test.
- `cloud_engine/` — Windows Server 2025 dual plastics/metals predictive engine with the autonomous
  per-chamber lifecycle (idle/running/suspended, self-resetting at batch boundaries),
  LabVIEW adapter, production ingest service, deployment template, contract + lifecycle
  tests, and `tools/redteam_ingest.py` (live acceptance harness).
- `convene/` — fresh binding specification (publisher `sim_` set plus the
  Convene-native `.stp` visualization bindings); no legacy binding is carried forward.
- `docs/` — live telemetry architecture, remote deployment preflight, and the
  predictive-engine fault/lifecycle memo.
- `deployment/` — handoff (start at `VM_ENGINE_HANDOFF.md` for the VM session),
  go/no-go punch list, and stage-labeled runbooks (see `deployment/README.md`).

## What starts fresh

1. Gateway configuration and its `run_id` start with a new deployment configuration.
2. Cloud engine deployment uses `push_ingest_dual.py --production`, a new secret,
   and a free side-by-side port.
3. Convene receives one publisher and a new `sim_` binding set from this release.
4. The Convene-native visualization binds the same `/state` variables to `.stp`
   model elements, read-only.

## Hardening status

The 2026-08 review findings (`CODE_REVIEW.md`) are implemented — see
`FIXES.md`. Headlines: per-frame ingest acknowledgement (v1.1) with gateway-side
dead-lettering, run supersession on gateway reboot, persisted monotone
sequence identity (restart-safe dedup), no fabricated sensor values, sequencer
chamber authority, seal-monitor unit/phase correction, real-dt physics, and
half-open-socket protection on the gateway receiver.

## Before deployment

Run the contract tests on a supported Python environment, complete the remote
preflight, and deploy side-by-side. Do not use this folder to overwrite a live
gateway or cloud installation in place.

For local development and CI-equivalent checks, the root `uv.lock` is the
reproducible dependency source. The supported CI matrix is Python 3.11 and 3.13:

```bash
uv sync --locked --all-extras --dev --python 3.13
python3 scripts/check_repository_hygiene.py

cd cloud_engine
../.venv/bin/python -m pytest tests -q

cd ../pi_gateway
PYTHONPATH=. ../.venv/bin/python -m pytest tests -q
```

The RT-03/RT-05 integrity remediation is implemented on the current integration
branch. The locked local suite is green; deployment still requires review and CI
evidence for the exact committed SHA. See
`docs/RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md` before promotion.

```bash
cd cloud_engine
python3 -m pytest tests -q

cd ../pi_gateway
PYTHONPATH=. python3 -m pytest tests -q          # Windows: $env:PYTHONPATH="."; python -m pytest tests -q
```

See `docs/RECLAIM_Remote_Gateway_Preflight.md` for the remote deployment sequence.
