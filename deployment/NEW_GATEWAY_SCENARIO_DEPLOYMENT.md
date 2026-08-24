# MacBook scenario-host deployment

> Windows 10 remains the sole live-data client/gateway. This procedure deploys
> only the MacBook scenario service.

## Configure

```bash
.venv-macbook/bin/python pi_gateway/macos/configure_scenario_host.py
launchctl kickstart -k "gui/$(id -u)/com.reclaim.edge-gateway"
curl --fail http://127.0.0.1:9080/health
```

Confirm `src=reclaim-macbook-scenario-01`, `mode=harness`, `transport=console`,
`convene_enabled=false`, `file_watch_enabled=true`, and no cloud token. Confirm
ports 9070 and 9080 listen only on loopback.

## Run generated scenarios

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh start lunar PL
pi_gateway/macos/start-rehearsal-scenario.sh start loss-of-data MT
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

Only one generated scenario may run at a time. Every start requires an explicit
active chamber (`PL` or `MT`), and the generated LabVIEW-shaped sensor bank and
shared microwave-power attribution follow that selection. The default is one
cycle at 4× speed. Power outage completes in about 3 minutes 45 seconds; lunar
surface completes in about 1 minute 40 seconds. Convene polling is targeted at
approximately one second, so both profiles remain well sampled.

Use the existing single whole-frame Convene File Watch variable with this path:
`/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt`.
Leave JSON path and capture regex blank. Do not rename the working Convene
variable or split the frame into individual field bindings.

## Replay a capture

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" --active-chamber MT --max-frames 100 --speed 10
```

The capture is input data only. Exact field names and values are preserved;
unknown sequencer state is labeled `S_Unknown`. The gateway atomically writes the
same 35 fields to the owner-private, one-frame File Watch text file. Convene's
internal routing owns the engine request and computed-state return. In automatic
mode, a record-level `active_chamber` is preserved; an explicit command option
overrides it. `NaN`
sensor readings are represented as `NaN` and treated as unavailable, never as
fabricated measurements.

## Accept

Require matching receive/deliver counts, zero queue depth, drops, dead letters,
and File Watch failures, plus a scenario-labeled `/latest` frame. Confirm the
35-field text file is atomically replaced as values advance. This proves only
source-to-file behavior until Convene heartbeat evidence exists. The common engine
records unclassified telemetry, and one engine process must receive only one active
source stream at a time.
Never change the MacBook to `mode=live`, a non-loopback listener, or direct cloud
transport.
