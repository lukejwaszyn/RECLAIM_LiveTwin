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
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

Only one generated scenario may run at a time. Every start requires an explicit
active chamber (`PL` or `MT`), and the generated LabVIEW-shaped sensor bank and
shared microwave-power attribution follow that selection.

## Replay a capture

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" --active-chamber MT --max-frames 100 --speed 10
```

The capture is input data only. Exact field names and values are preserved;
unknown sequencer state is labeled `S_Unknown`. The gateway atomically writes the
flat scenario variables to the owner-private File Watch JSON. Convene's internal routing owns
the engine request and computed-state return. In automatic mode, a record-level `active_chamber`
is promoted into the envelope; an explicit command option overrides it. `NaN`
sensor readings are omitted as unavailable because strict JSON cannot carry
them.

## Accept

Require matching receive/deliver counts, zero queue depth, drops, dead letters,
and File Watch failures, plus a scenario-labeled `/latest` frame. Confirm the
JSON file advances with `seq` and `ts`. This is source-to-Convene acceptance only
after Convene heartbeat evidence. The common engine accepts the preserved
`harness`/`replay` mode, but one engine process must receive only one active
source stream at a time.
Never change the MacBook to `mode=live`, a non-loopback listener, or direct cloud
transport.
