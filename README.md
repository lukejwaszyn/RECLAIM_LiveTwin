# RECLAIM Live Twin

RECLAIM Live Twin is the completed engineering deliverable for the LunaRecycle
demonstration digital twin. It connects cRIO/LabVIEW telemetry and bounded
rehearsal scenarios to a dual-chamber stochastic predictive engine through
Convene, while keeping every computed result advisory and physically isolated
from process actuation.

**Project status:** closed on 2026-08-27. This README is the final project-level
source of truth. Session handoffs, chat prompts, superseded routing designs, and
deprecated implementations have been removed. Durable architecture decisions,
source-record evidence, test baselines, and executable runbooks remain in the
repository.

> **Safety status:** engineering shadow only. The cloud engine estimates,
> forecasts, and reports state, but this repository does not authorize or
> implement a command path to cRIO, LabVIEW, microwave controls, pumps, valves,
> or other process hardware.

## Final architecture

There are two source hosts and one common downstream route:

```text
LIVE TELEMETRY
cRIO / LabVIEW
  -> Windows 10 desktop live gateway
  -> Convene live machine

SCENARIO TELEMETRY
MacBook synthetic or approved capture replay
  -> loopback gateway (127.0.0.1:9070)
  -> atomic one-frame text file
  -> Convene File Watch scenario machine

COMMON PROCESSING
Either Convene source machine
  -> Convene internal routing
  -> Windows Server 2025 cloud dual engine
  -> computed sim_* state returned to Convene
  -> read-only STEP visualization
```

The platform responsibilities are fixed:

| Component | Final responsibility |
|---|---|
| cRIO + LabVIEW | Authoritative physical telemetry, sequencing, interlocks, and hardware control |
| Windows 10 desktop | Sole live cRIO client and live source publisher |
| MacBook | Scenario-only host; never a live cRIO client |
| Convene | Common source ingress, internal routing, result return, and visualization |
| Windows Server 2025 VM | Dual PL/MT stochastic engine and sole owner of computed `sim_*` state |

The repository directory name `pi_gateway` is retained for compatibility. It
does not imply that a Raspberry Pi is present in the final system.

## Core invariants

These rules define the closed architecture:

1. The Windows 10 desktop is the only live-data gateway.
2. The MacBook is loopback-only and scenario-only.
3. Live and scenario sources use the same 35-field text contract.
4. The source record does not identify whether telemetry is live or simulated.
5. Convene owns source-to-engine and engine-to-display routing.
6. Source hosts preserve exact LabVIEW names and do not manufacture `gw_`
   aliases.
7. Only the cloud result path may publish the `sim_` namespace.
8. Missing or non-finite measurements remain unavailable; they are never
   replaced with plausible values.
9. Only one source stream may drive one engine process at a time.
10. All predictive output is advisory and disconnected from actuation.

## Telemetry contract

Each live-shaped record is one line of comma-separated `name: value` pairs. The
first field is authoritative `active_chamber`, followed by the 34 signed raw
LabVIEW fields in this exact order:

```text
active_chamber,
PL_surface_temp, PL_output_pressure, PL_chamber_pressure,
PL_top_condenser_temp, PL_bottom_condenser_temp,
PL_wall1, PL_wall2,
PL_bottom1, PL_bottom2, PL_bottom3, PL_bottom4,
PL_flow_meter, PL_process, PL_preprocess, MW_reverse_coupler,
PL_postprocess, PL_chamber_pump, PL_purge_pump,
MT_crucible_temperature, MT_top, MT_bottom,
MW_water_state, MW_flow_state, MW_RF, MW_status,
MW_power, MW_reverse, MW_period, MW_width, MW_freq,
MW_water_temp, MW_flow_rate, PL_Probe1, PL_Probe2
```

Contract rules:

- `active_chamber` is `PL`, `MT`, or `NONE`.
- Booleans are rendered as `TRUE` or `FALSE` in the File Watch text.
- Finite floating-point values use six decimal places.
- Unavailable sensors are `NaN`.
- Field names and capitalization are exact and case-sensitive.
- The one-line record contains no required `run_id`, `source_id`, `cycle_id`,
  `seq`, `ts`, `mode`, or `source_op_state`.
- The engine assigns receipt-owned identity and timing when source metadata is
  absent.
- `active_chamber` is authoritative; chamber inference is fallback behavior for
  older 34-field captures only.
- The engine accepts `NaN` frames gracefully by omitting unavailable values
  from inference instead of retaining or fabricating a fresh measurement.

The canonical field definition is shared by
`pi_gateway/reclaim_edge/convene.py`,
`pi_gateway/reclaim_edge/file_watch.py`, and `cloud_engine/labview_map.py`.

## Repository layout

| Path | Purpose |
|---|---|
| `pi_gateway/` | Gateway receiver, framing, buffering, source publishing, File Watch output, status API, platform templates, and tests |
| `pi_gateway/macos/` | MacBook scenario-only configuration, audit, and one-command scenario launcher |
| `pi_gateway/windows/` | Windows live-gateway operating notes |
| `tools/` | Synthetic cRIO source, Windows capture replay, and integration utilities |
| `cloud_engine/` | Dual-chamber ingest service, LabVIEW mapping, predictive engine, Windows service assets, and tests |
| `crio_source_record/` | Offline source-record parser, quality policy, conformance checks, fixtures, and bench replay |
| `crio_psp_adapter/` | Diagnostic PSP acquisition proof of concept; not the final live source path |
| `deployment/` | Durable topology, decisions, source-record runbooks, signed maps, and VM audit tools |
| `docs/` | Architecture decisions, lifecycle notes, integrity baselines, and remediation evidence |

No deprecated code or historical handoff archive is part of the final tree.

## Prerequisites

- Python 3.11, 3.12, or 3.13
- `uv` 0.11.x as constrained by `pyproject.toml`
- macOS with `launchd` for the scenario host
- Windows 10 for the physical live gateway
- Windows Server 2025 and PowerShell for the cloud VM service assets
- A manually configured Convene machine and route for each source host

Install the locked development environment from the repository root:

```bash
uv sync --locked --all-extras --dev --python 3.13
python3 scripts/check_repository_hygiene.py
```

Real credentials, tokens, and environment-specific IDs must remain outside Git.
The repository contains examples and loaders, not production secrets.

## Verification

The final combined pre-flight suite contains **270 tests**:

```bash
PYTHONPATH=pi_gateway:tools:cloud_engine:crio_source_record \
  .venv/bin/python -m pytest -q \
  pi_gateway/tests tools/tests cloud_engine/tests crio_source_record/tests
```

The source-record bench replay must finish with three accepted and zero rejected
records:

```bash
PYTHONPATH="pi_gateway:cloud_engine:$PWD" \
  .venv/bin/python -m crio_source_record.bench_replay
```

Expected terminal summary:

```text
{'accepted': 3, ..., 'rejected': 0, 'sent': 3}
```

Any failed test, malformed source record, nonzero dead-letter count, growing
queue, or failed File Watch write invalidates a deployment claim for that exact
commit.

## MacBook scenario host

### One-time configuration

The MacBook configuration is intentionally fail-closed. It binds scenario
ingress to loopback, disables direct cloud transport and direct Convene API
publishing, and writes a single owner-private File Watch file.

From the repository root:

```bash
.venv-macbook/bin/python pi_gateway/macos/configure_scenario_host.py
launchctl kickstart -k "gui/$(id -u)/com.reclaim.edge-gateway"
pi_gateway/macos/audit-scenario-host.sh
```

Required runtime state:

- source identity `reclaim-macbook-scenario-01`
- mode `harness` or deliberately selected `replay`
- scenario ingress `127.0.0.1:9070`
- status API `127.0.0.1:9080`
- transport `console`
- no cloud ingest token
- direct Convene API publication disabled
- File Watch output enabled

### Convene File Watch

Configure one Convene File Watch variable for the entire line:

| Setting | Value |
|---|---|
| File path | `/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt` |
| Variable name | Keep the existing whole-frame telemetry variable |
| JSON path | Blank |
| Capture regex | Blank |

Do not rename the working Convene variable, split the frame into 35 bindings,
or add source metadata to the text. The file name and Convene variable name do
not need to match.

The writer creates the parent directory as owner-only, writes a complete frame
to a temporary file, flushes it, and atomically replaces the watched file with
mode `0600`. A heartbeat therefore sees either the previous complete frame or
the next complete frame, never a partially written line.

### Scenario commands

Only one scenario sender may run at a time. Every start explicitly chooses the
authoritative chamber:

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh start lunar PL
pi_gateway/macos/start-rehearsal-scenario.sh start loss-of-data MT

pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

`start` creates a separate one-shot per-user `launchd` job. It survives a
Convene-agent restart, has `KeepAlive=false`, and cannot relaunch itself after a
completed cycle. An atomic start lock rejects duplicate commands before two
senders can connect.

Default scenario behavior:

| Profile | Default example | Frames / wall time | Result |
|---|---|---|---|
| `nominal` | `nominal PL` | about 101 / 1:40 | Stable Earth-lab heat-and-hold |
| `power-outage` | `power-outage MT` | 211 / 3:30 | Reaches about 680°C, crosses the 660°C aluminum melt gate, interrupts power, restarts, and ends powered off |
| `lunar` | `lunar PL` | 301 / 5:00 | Ramps toward 450°C, then performs extended radiation-limited cooldown |
| `loss-of-data` | `loss-of-data MT` | about 101 / 1:40 | Stops updating after one bounded cycle so freshness handling can be observed |

All scenarios emit one complete frame per wall-clock second by default. Keep
`RECLAIM_SCENARIO_EMIT_HZ=1` for Convene. Optional controls are:

```bash
RECLAIM_SCENARIO_MAX_FRAMES=20 RECLAIM_SCENARIO_SPEED=10 \
  pi_gateway/macos/start-rehearsal-scenario.sh start nominal MT

RECLAIM_SCENARIO_CYCLES=0 \
  pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
```

Use unlimited cycles only deliberately; stop them explicitly.

### Lunar pressure model

The lunar scenario separates the external environment from the sealed process
path:

- external lunar ambient: `3e-10 Pa`
- convection: disabled
- external cooling: radiation only
- sealed PL chamber: approximately 50.8 Torr
- PL downstream/output pressure: approximately 61.6 Torr

The two internal pressure traces vary smoothly inside the observed ranges from
the supplied 5,894-frame cRIO capture. They are not the lunar ambient pressure.

### Local scenario acceptance

While a scenario runs:

```bash
curl --fail http://127.0.0.1:9080/health
curl --fail http://127.0.0.1:9080/latest
pi_gateway/macos/audit-scenario-host.sh
```

Require:

- receiver and File Watch counts advance;
- received and delivered counts converge after drain;
- queue depth returns to zero;
- drops and dead letters remain zero;
- `file_watch.failed` remains zero;
- the watched file is one line with 35 fields;
- `active_chamber` matches the selected command; and
- the Convene whole-frame value changes on successive heartbeats.

The final Convene check is manual. Repository tooling does not sign in to or
automate the Convene web application.

### Approved capture replay

Replay a retained Windows data-stream file through the same loopback path:

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" \
  --active-chamber MT --max-frames 100 --speed 10
```

The replayer preserves raw names and scalar values. It does not claim the
MacBook acquired the record live. Unknown source state remains `S_Unknown`, and
`NaN` remains unavailable.

## Windows 10 live gateway

The Windows desktop is the sole physical source gateway. Begin with
`pi_gateway/config.crio-live.example.yaml` and replace the refusal-by-default
loopback listener only after the dedicated OT interface and cRIO peer are
confirmed.

Final live-gateway requirements:

- `mode: live`
- TCP ingress on the dedicated cRIO-facing interface, port `9070`
- status API loopback-only on `9080`
- bounded frame size and half-open connection timeout
- direct gateway-to-cloud transport disabled (`transport: console`)
- exact source names with no generated `gw_` prefix
- source publishing to the paired Convene machine
- no `sim_*` publication

Read-only checks on Windows are:

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Physical acceptance requires a correlated cRIO frame, a fresh raw update in
Convene, an accepted engine receipt, and the corresponding `sim_*` result back
in Convene. See `pi_gateway/windows/README.md` and the durable source-record
documents listed below.

## Cloud dual engine

`cloud_engine/push_ingest_dual.py` is the common PL/MT ingest service. It
normalizes LabVIEW names and units, advances independent chamber models,
maintains restart-safe receipt identity, and exposes flat computed state for
Convene.

HTTP surface:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ingest` | Accept one text/flat record, one canonical envelope, or NDJSON batch |
| `GET` | `/state` | Latest combined PL/MT computed state |
| `GET` | `/manifest` | Self-describing variables and states |
| `GET` | `/history` | Recent computed frames |
| `GET` | `/health` | Liveness and counters |
| `GET` | `/command` | Latest advisory command object for diagnostics only |

Production mode requires:

- a nonempty `RECLAIM_INGEST_TOKEN`;
- a distinct `RECLAIM_READ_TOKEN` for protected reads;
- a durable `RECLAIM_INGEST_STATE` path; and
- loopback service binding behind the approved Convene route.

The Windows service runner is `cloud_engine/windows/run-ingest-engine.ps1` and
the WinSW template is `cloud_engine/windows/reclaim-ingest.xml`. The runner
loads tokens from an ACL-restricted file and does not place them on the command
line.

VM audit and supervised contract checks:

```powershell
Set-Location C:\path\to\RECLAIM_LiveTwin
.\deployment\windows-vm\Audit-ConveneRoutedEngine.ps1
.\deployment\windows-vm\Test-ConveneRoutedEngineContract.ps1
```

The endpoint exercise mutates estimator state and must only run in a supervised
window with source input paused:

```powershell
$env:RECLAIM_INGEST_TOKEN = '<existing ingest token>'
$env:RECLAIM_READ_TOKEN = '<existing read token>'
.\deployment\windows-vm\Test-ConveneRoutedEngineContract.ps1 -ExerciseEndpoint
```

## Observability and failure behavior

Gateway health is available only on loopback port `9080`:

- `/health` reports receive, delivery, queue, drop, failure, and freshness data.
- `/latest` reports the last canonical gateway frame.
- `/command` may expose the latest advisory object for diagnostics, but it is
  not an authorized hardware command path.

Important failure behavior:

- File Watch writes are atomic and owner-private.
- Scenario submissions coalesce to the newest pending frame rather than block
  source generation.
- Network or Convene failure cannot block cRIO receipt.
- The gateway durable queue and per-frame disposition prevent silent loss on
  supported direct transports, although the final Convene-routed architecture
  leaves direct cloud transport disabled.
- A finished loss-of-data scenario intentionally leaves the last file in place;
  consumers must reject it by freshness, not mistake it for a continuing stream.
- The cloud engine creates receipt timing for metadata-free records and uses
  advancing engine time to detect stale output.

## Security boundaries

- Never commit Convene credentials, ingest tokens, read tokens, private keys,
  tunnel credentials, or environment-local IDs.
- Never expose MacBook ports `9070` or `9080` beyond loopback.
- Never route rehearsal ports `8177`-`8181` into a production path.
- Never run scenarios on the Windows live gateway or cloud VM.
- Never run a second `sim_*` publisher.
- Never infer a valid sensor value from `NaN`.
- Never deploy or restart the engine during an active physical batch without a
  separately approved safe-state procedure.
- Never connect predictive output to actuation based on this repository.

## Durable documentation

The final documentation set intentionally contains records that remain useful
after project closure:

- `deployment/DEPLOYMENT_TOPOLOGY.md` — authoritative host and route topology
- `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md` — final source-host decision
- `deployment/CRIO_SOURCE_RECORD_DECISION_RECORD.md` — source acquisition decision
- `deployment/CRIO_SOURCE_RECORD_RUNBOOK.md` — source-record verification procedure
- `deployment/CRIO_SOURCE_RECORD_SIGNED_MAPS.md` — signed channel mapping worksheets
- `deployment/CRIO_TELEMETRY_SOCKET_SETUP.md` — cRIO producer/socket design
- `deployment/CRIO_TELEMETRY_WRITE_PATH_AUDIT.md` — deterministic write-path audit
- `deployment/CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` — controls review checklist
- `deployment/windows-vm/README.md` — VM audit and contract-test instructions
- `pi_gateway/macos/README.md` — detailed MacBook scenario-host operations
- `docs/RECLAIM_Live_Telemetry_Architecture.md` — telemetry architecture
- `docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md` — engine lifecycle behavior
- `docs/RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md` — release and CI evidence baseline
- `docs/RECLAIM_RT03_RT05_Test_Baseline.md` — integrity regression baseline

`deployment/README.md` indexes the remaining deployment records.

## Project closure

The repository is closed as a completed engineering snapshot. There is no
active handoff document and no implied next implementation session. Future work
must begin from a new issue, branch, and explicit scope, using this README and
the durable records above as historical technical evidence.

The final accepted boundaries remain unchanged: Windows owns live telemetry,
MacBook owns scenarios, Convene owns routing, the VM owns computed state, and
all predictive output remains advisory.
