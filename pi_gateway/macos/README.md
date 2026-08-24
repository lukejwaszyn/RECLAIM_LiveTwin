# RECLAIM MacBook scenario-host runtime

> The Windows 10 desktop is the sole live-data client/gateway. The MacBook is
> loopback-only and scenario-only. It must never connect to the real cRIO,
> expose its receiver on a LAN, or publish directly to the cloud engine.

The MacBook serves synthetic and approved capture-replay scenarios through its
own Convene machine. The downstream Convene-to-VM scenario pipe is configured
elsewhere.

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
- Convene enabled with the MacBook machine credential

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
zero, no drops/dead letters, and zero Convene failures. `/latest` must show
`mode: harness` or `replay` and a scenario-labeled `source_id`.

Ports `9070` and `9080` must both listen only on `127.0.0.1`. The MacBook must
hold no VM ingest token. Preserve the configuration backup, logs, evidence, and
exact Git SHA.
