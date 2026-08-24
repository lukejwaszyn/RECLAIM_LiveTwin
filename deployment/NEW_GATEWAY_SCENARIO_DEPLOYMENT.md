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
and no cloud token. Confirm ports 9070 and 9080 listen only on loopback.

## Run generated scenarios

```bash
pi_gateway/macos/start-rehearsal-scenario.sh nominal
pi_gateway/macos/start-rehearsal-scenario.sh power-outage
pi_gateway/macos/start-rehearsal-scenario.sh lunar
pi_gateway/macos/start-rehearsal-scenario.sh loss-of-data
```

## Replay a capture

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" --max-frames 100 --speed 10
```

The capture is input data only. Exact field names and values are preserved;
unknown sequencer state is labeled `S_Unknown`. Convene-to-VM routing is outside
this deployment procedure.

## Accept

Require matching receive/deliver counts, zero queue depth, drops, dead letters,
and Convene failures, plus a scenario-labeled `/latest` frame. Never change the
MacBook to `mode=live`, a non-loopback listener, or direct cloud transport.
