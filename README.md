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

### 3. MacBook rehearsal scenarios

Run these commands from the repository root on the MacBook. The one-time setup
locks the service to loopback-only scenario mode and enables its atomic File
Watch output:

```bash
.venv-macbook/bin/python pi_gateway/macos/configure_scenario_host.py
launchctl kickstart -k "gui/$(id -u)/com.reclaim.edge-gateway"
pi_gateway/macos/audit-scenario-host.sh
```

In Convene, keep the File Watch configuration that is already working:

- File path: `/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt`
- Variable name: keep the existing whole-frame telemetry variable name
- JSON path: blank
- Capture regex: blank

Do not rename the working Convene variable, change the file path, or create 35
individual bindings. Convene reads one complete text frame containing
`active_chamber` plus all 34 raw telemetry fields. The file name and the Convene
variable name do not need to match.

To run a scenario, pick one start command. Only one sender is allowed at a time,
and every start explicitly selects the authoritative chamber:

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh start lunar PL
pi_gateway/macos/start-rehearsal-scenario.sh start loss-of-data MT
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

Every profile supports either `PL` or `MT`; the examples above deliberately
exercise both. `start` runs in the background, `status` reports the active
sender, and `stop` ends it. By default every command runs one compressed
rehearsal cycle while emitting exactly one complete frame per wall-clock second,
then exits automatically. Power outage completes in about 3 minutes 30 seconds;
lunar surface completes in about 5 minutes; nominal and loss of data complete in
about 1 minute 40 seconds. Set
`RECLAIM_SCENARIO_SPEED` to override playback speed or
`RECLAIM_SCENARIO_CYCLES=0` to deliberately repeat until stopped. Leave
`RECLAIM_SCENARIO_EMIT_HZ` at its default of `1` for Convene.

The MacBook starts each scenario as a separate one-shot per-user launchd job,
not as a child of the Convene agent. Restarting Convene therefore cannot kill an
active scenario. An atomic start lock rejects duplicated Run-command dispatch,
and `KeepAlive=false` prevents launchd from restarting a completed cycle.

The MacBook never connects to the real cRIO. Obsolete Windows/Mac direct scenario
publishers are archived and cannot be invoked from the active tree.

| Profile | Scenario/environment | Behavior |
|---|---|---|
| `nominal` | `nominal` / `earth_lab` | Stable heat-and-hold; one compressed cycle, about 1:40 |
| `power-outage` | `power_outage` / `earth_lab` | MT reaches ~680°C, crosses the 660°C Al melt gate, exercises outage/restart, then ends powered off in cooldown; 211 frames over about 3:30 |
| `lunar` | `lunar_surface_process` / `lunar_surface` | PL reaches ~450°C at 700 Torr, then performs an extended radiation-limited powered-off cooldown; 301 frames over about 5:00 |
| `loss-of-data` | `nominal` / `earth_lab`, one cycle | Disconnects after one cycle so freshness must expire |

These profiles traverse the MacBook's loopback `9070` scenario ingress and its
atomic File Watch writer. They do not enter the Windows 10 live gateway or
directly target the VM. Convene owns the downstream route. The engine accepts the
identical 35-field text input through `/ingest` regardless of origin, then
returns computed `sim_*` variables in the
POST response. Inspect the scenario host on loopback `9080`.

**`loss-of-data` — what to watch.** After its single cycle finishes, the gateway
keeps answering and the last complete file remains readable, but its modification
time and values stop advancing. `/health` continues to report the gateway while
its last-success age grows. That is the condition the check exists to rehearse:
downstream consumers must detect staleness rather than trust a last-good value.

The watched frame intentionally has no source `ts` or `seq`, matching current live
telemetry. The engine creates unclassified receipt `ts_source`, monotone `seq`,
`ts_engine`, and `ingest_age_ms`. Convene must use advancing engine receipt/state
time to reject stale output rather than treating a last-good value as fresh.

**Verification.** While a scenario runs, the watched value in Convene should
change on each Convene poll (target approximately one second). Playback speed is
profile-specific, but the File Watch file is replaced exactly once per
wall-clock second using monotonic start-to-start deadlines, so processing time
does not accumulate timing drift. Local verification is:

```bash
curl --fail http://127.0.0.1:9080/health
curl --fail http://127.0.0.1:9080/latest
pi_gateway/macos/audit-scenario-host.sh
```

Require received and delivered counts to converge, queue depth zero, no drops or
dead letters, `file_watch.failed: 0`, one 35-field line, and the selected
`active_chamber`. This proves scenario-to-file delivery. The user confirms the
Convene heartbeat manually; the MacBook does not sign in to or automate Convene.

Run scenarios only on the MacBook scenario host. Never run them on the Windows
live gateway or predictive-engine VM, and never route rehearsal ports
`8177`–`8181` into production.

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
