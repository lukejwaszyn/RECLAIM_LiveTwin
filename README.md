# RECLAIM Live Twin

The clean working release for the next RECLAIM deployment: the active live-data
path, its tests, its deployment templates, and the Convene binding contract
(including the Convene-native `.stp` visualization).

It intentionally excludes archive folders, ZIP handoffs, cached environments,
synthetic emitters, old single-chamber services, scenario dashboards, trained
model artifacts, and previous Convene bridges. Those remain preserved in the
source workspace but are not part of this release.

> **Standing status: labeled engineering shadow — NO-GO for any production
> claim.** All engine output is advisory. Computed state returns to Convene for
> visualization only; no command or actuation path exists in this repository.

---

## Quick start

### 1. Environment

The root `uv.lock` is the reproducible dependency source. Supported CI matrix is
Python 3.11 and 3.13.

```bash
uv sync --locked --all-extras --dev --python 3.13
python3 scripts/check_repository_hygiene.py
```

### 2. Tests — expect **264 passed**

Green across the combined gateway, tooling, cloud-engine, and source-record suite
is the pre-flight go-signal; **any red means stop, do not deploy.**

```bash
PYTHONPATH=pi_gateway:tools:cloud_engine:crio_source_record \
  python -m pytest -q pi_gateway/tests tools/tests cloud_engine/tests \
  crio_source_record/tests
```

Bench replay must end `{'accepted': 3, ..., 'rejected': 0, 'sent': 3}`:

```bash
PYTHONPATH="pi_gateway:cloud_engine:$PWD" python -m crio_source_record.bench_replay
```

### 3. Rehearsal scenarios — one command each, any time

**Pick ONE line and run it.** Each line below is a complete, self-contained
command — there is no setup step, and nothing above it needs to be run first. If
the locked environment does not exist yet, the runner builds it once on first use,
so these work from a fresh checkout.

On the MacBook, scenarios enter the loopback-only scenario listener. The same
controller starts, reports, and stops the one allowed sender; every start chooses
the active chamber:

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh start lunar PL
pi_gateway/macos/start-rehearsal-scenario.sh start loss-of-data MT
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

The MacBook never connects to the real cRIO. Obsolete Windows/Mac direct scenario
publishers are archived and cannot be invoked from the active tree.

| Profile | Scenario/environment | Behavior |
|---|---|---|
| `nominal` | `nominal` / `earth_lab` | Stable heat-and-hold; repeats until Ctrl+C |
| `power-outage` | `power_outage` / `earth_lab` | Outage, coast, and `S_Restart`; repeats until Ctrl+C |
| `lunar` | `nominal` / `lunar_surface` | Same source sequence under lunar physics |
| `loss-of-data` | `nominal` / `earth_lab`, one cycle | Disconnects after one cycle so freshness must expire |

These profiles traverse the MacBook's loopback `9070` scenario ingress and its
atomic File Watch writer. They do not enter the Windows 10 live gateway or
directly target the VM. Convene owns the downstream route. The engine accepts the
the identical 35-field text input through `/ingest` regardless of origin, then
returns computed `sim_*` variables in the
POST response. Inspect the scenario host on loopback `9080`.

**`loss-of-data` — what to watch.** After its single cycle finishes, the endpoints
keep answering and the last values stay readable, but the data stops advancing:
`/health` and `/state` report `status: stopped` and `t_sim` freezes. That is the
condition the check exists to rehearse — a consumer must detect staleness rather
than trust a last-good value.

The watched frame intentionally has no source `ts` or `seq`, matching current live
telemetry. The engine creates unclassified receipt `ts_source`, monotone `seq`,
`ts_engine`, and `ingest_age_ms`. Convene must use advancing engine receipt/state
time to reject stale output rather than treating a last-good value as fresh.

**Where to run them.** The scenarios are self-contained — they need only this
checkout, never the cRIO, the gateway, or a network feed. Run them on any machine
that is **not** currently serving production `8078`. In practice that means the
MacBook scenario host during a deploy or demo session, which keeps
machine-level separation from the VM's production port. Do not run them on the
predictive-engine VM while it serves production: the script's port guard is only
port-level protection, and `8177`–`8181` must never be routed to production or
bound as live mission state.

For every run retain: commit SHA, engine receipt run ID/timestamps, expected vs observed,
screenshots, and deviations. Keep synthetic services clearly labeled as rehearsal
data.

---

## Runtime topology

```text
cRIO / LabVIEW -> Windows 10 desktop live gateway -> Convene live machine

MacBook local scenarios -> loopback service -> atomic one-frame text -> Convene File Watch

Either Convene machine -> Convene internal route -> cloud dual engine
                        -> computed state -> Convene sim_* / .stp visualization
```

The VM guest procedures are Windows. Live-gateway procedures are Windows 10;
MacBook procedures are scenario-only. There is no Linux host or Raspberry Pi in
the live path. Convene is the common routing plane, the cloud engine owns state
processing, and the `.stp` visualization is a read-only view of returned state.

The cloud result path is the sole publisher of the `sim_` namespace. Source
machines preserve exact raw names without manufacturing `gw_` aliases and never
write a `sim_` variable.

## Contents

- `pi_gateway/` — shared gateway/scenario framing package, Windows live-gateway
  tooling, MacBook loopback scenario configuration, Convene publisher, and tests.
- `cloud_engine/` — Windows Server 2025 dual plastics/metals predictive engine with the
  autonomous per-chamber lifecycle (idle/running/suspended, self-resetting at batch
  boundaries), LabVIEW adapter, production ingest service, rehearsal scenario runner,
  deployment template, contract + lifecycle tests, and `tools/redteam_ingest.py`.
- `crio_source_record/` — offline source-record contract: parser, fixtures, conformance
  checker, and bench replay.
- `convene/` — binding specification (publisher `sim_` set plus the Convene-native
  `.stp` visualization bindings); no legacy binding is carried forward.
- `docs/` — live telemetry architecture, implementation baselines, and the
  predictive-engine fault/lifecycle memo.
- `deployment/` — current architecture, go/no-go records, and runbooks. Start at
  `deployment/CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`.

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

Run the contract tests on a supported Python environment, follow the pickup and
acceptance matrix in
`deployment/CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`, and deploy side-by-side.
**Do not use this folder to overwrite a live gateway or cloud installation in
place.**

## Bringing the cRIO online

When the cRIO is connected and something is not arriving, validating, or
returning through Convene, start at
**`deployment/CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`**. It defines the current
seams, exact naming contract, known gaps, and competition acceptance matrix.
