# RECLAIM MacBook scenario-host runtime

> The Windows 10 desktop is the sole live-data client/gateway. The MacBook is
> loopback-only and scenario-only. It must never connect to the real cRIO,
> expose its receiver on a LAN, or publish directly to the cloud engine or
> Convene API.

The MacBook serves synthetic and approved capture-replay scenarios through one
owner-private local JSON file. Convene File Watch reads that file each heartbeat;
Convene's internal routing owns the downstream engine path and computed-state
return.

## Required installed configuration

Run from the repository root:

```bash
.venv-macbook/bin/python pi_gateway/macos/configure_scenario_host.py
launchctl kickstart -k "gui/$(id -u)/com.reclaim.edge-gateway"
curl --fail http://127.0.0.1:9080/health
```

Required health/config state:

- `src: reclaim-macbook-scenario-01`
- `mode: harness` (or deliberately selected `replay`)
- `listen_host: 127.0.0.1`
- `transport: console`
- empty cloud ingest token
- direct Convene API publishing disabled
- File Watch enabled at
  `/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.json`

`configure_production_interfaces.py` is a retired guard and always refuses.

## Built-in scenarios

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

The same command starts, reports, and stops the one allowed scenario process.
Every start requires an explicit `PL` or `MT`; the generated sensor bank,
`active_chamber`, cycle identity, PL process flag, and shared microwave-power
attribution all follow that selection. The launcher refuses unless health
reports `harness` or `replay`. For bounded checks, set
`RECLAIM_SCENARIO_MAX_FRAMES`; use `RECLAIM_SCENARIO_SPEED` to accelerate
playback. Use `run` in place of `start` only when a foreground process is useful.

## Convene File Watch setup

Create one File Watch variable for each required source field. Every variable
uses the same settings except its name/JSON path:

- **File path:** `/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.json`
- **Variable name:** the exact field name
- **JSON path:** the exact same field name
- **Capture regex:** leave blank

Required envelope bindings are `schema_version`, `mode`, `run_id`, `source_id`,
`cycle_id`, `seq`, `ts`, `source_op_state`, and `active_chamber`.

Required raw bindings are `PL_surface_temp`, `PL_output_pressure`,
`PL_chamber_pressure`, `PL_top_condenser_temp`, `PL_bottom_condenser_temp`,
`PL_wall1`, `PL_wall2`, `PL_bottom1`, `PL_bottom2`, `PL_bottom3`, `PL_bottom4`,
`PL_flow_meter`, `PL_process`, `PL_preprocess`, `MW_reverse_coupler`,
`PL_postprocess`, `PL_chamber_pump`, `PL_purge_pump`,
`MT_crucible_temperature`, `MT_top`, `MT_bottom`, `MW_water_state`,
`MW_flow_state`, `MW_RF`, `MW_status`, `MW_power`, `MW_reverse`, `MW_period`,
`MW_width`, `MW_freq`, `MW_water_temp`, `MW_flow_rate`, `PL_Probe1`, and
`PL_Probe2`.

The file is atomically replaced with mode `0600`, so a heartbeat sees either the
previous complete frame or the next complete frame, never partial JSON. Missing
or `NaN` sensors are omitted rather than fabricated.

## Windows capture replay

The supplied comma-separated `name: value` capture format is replayed with:

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" --active-chamber MT --max-frames 100 --speed 10
```

The replayer preserves exact channel names and scalar values. It labels unknown
sequencer state `S_Unknown`; it never claims the file is current physical data.
With the default `--active-chamber auto`, a record-level `active_chamber: PL`
or `active_chamber: MT` is promoted into the scenario envelope. Explicit command
selection overrides it. LabVIEW `NaN` sensor readings are omitted because they
are unavailable values and are invalid in the strict JSON/Convene contract.

## Acceptance

During a bounded run, `/health` must show received equals delivered, queue depth
zero, no drops/dead letters, and `file_watch.failed: 0`. `/latest` must show
`mode: harness` or `replay` and a scenario-labeled `source_id`. This proves
source-to-file delivery; confirm Convene heartbeat timestamps separately. The
cloud ingest accepts honestly labeled `harness` and `replay` frames through the
same naming adapter as live data. Only one source stream may drive one engine
process at a time.

Ports `9070` and `9080` must both listen only on `127.0.0.1`. The MacBook must
hold no VM ingest token and needs no Convene API token for scenario telemetry.
Preserve the configuration backup, logs, evidence, and exact Git SHA.
