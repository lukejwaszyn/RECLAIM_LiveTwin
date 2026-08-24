# RECLAIM MacBook scenario-host runtime

> The Windows 10 desktop is the sole live-data client/gateway. The MacBook is
> loopback-only and scenario-only. It must never connect to the real cRIO,
> expose its receiver on a LAN, or publish directly to the cloud engine or
> Convene API.

The MacBook serves synthetic and approved capture-replay scenarios through one
owner-private local text file. Convene File Watch reads that file each heartbeat;
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
  `/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt`

`configure_production_interfaces.py` is a retired guard and always refuses.

## Built-in scenarios

Run from the repository root. Pick one `start` command; only one scenario sender
may run at a time:

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh start lunar PL
pi_gateway/macos/start-rehearsal-scenario.sh start loss-of-data MT
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

The same command starts, reports, and stops the one allowed scenario process.
`start` runs in the background. Every start requires an explicit `PL` or `MT`;
all four profiles support either chamber. The default is one bounded cycle at 4×
speed. Power outage therefore finishes in about 3 minutes 45 seconds, while
nominal, lunar surface, and loss of data finish in about 1 minute 40 seconds.
The generated sensor bank,
`active_chamber`, cycle identity, PL process flag, and shared microwave-power
attribution all follow that selection. The launcher refuses unless health
reports `harness` or `replay`. For bounded checks, set
`RECLAIM_SCENARIO_MAX_FRAMES`; use `RECLAIM_SCENARIO_SPEED` to accelerate
or slow playback. Set `RECLAIM_SCENARIO_CYCLES=0` only when deliberate repetition
until `stop` is required. Use `run` in place of `start` only when a foreground
process is useful.

Examples:

```bash
# Default: one complete nominal PL cycle at 4x, then stop automatically
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL

# Short accelerated local plumbing check
RECLAIM_SCENARIO_MAX_FRAMES=20 RECLAIM_SCENARIO_SPEED=10 \
  pi_gateway/macos/start-rehearsal-scenario.sh start nominal MT
```

Convene polling is targeted at approximately one second. At the 4× default the
file updates roughly four times per second, so power-outage and lunar-surface
runs remain well sampled while both finish below five minutes. `loss-of-data`
stops updating the watched file after its one cycle.

## Convene File Watch setup

The file contains exactly one current frame and is replaced on every source
update. It uses the live LabVIEW style from the supplied data stream:
`name: value, name: value`. Configure one Convene File Watch variable for the
entire frame:

- **File path:** `/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt`
- **Variable name:** use the existing whole-frame telemetry variable
- **JSON path:** leave blank
- **Capture regex:** leave blank

Do not rename this working Convene variable, and do not change the file path.
The local file name and Convene variable name do not need to match. Do not split
the frame into 35 Convene variables. Keeping the record intact preserves
LabVIEW `NaN` tokens and gives the cloud engine the same payload shape for live
and scenario telemetry. The frame itself contains `active_chamber` plus all 34
raw fields. Do not add `schema_version`, `mode`, `run_id`, `source_id`,
`cycle_id`, `seq`, `ts`, or `source_op_state`; the common `/ingest` endpoint owns
receipt metadata and does not classify the source as live or scenario.

The file is atomically replaced with mode `0600`, so a heartbeat sees either the
previous complete frame or the next complete frame, never partial text. It
contains `active_chamber` followed by all 34 raw fields in the live-record order,
matching the current one-frame convention. Booleans are `TRUE`/`FALSE`, finite
floats use six decimal places, and unavailable fields are `NaN` rather than
fabricated measurements.

## Windows capture replay

The supplied comma-separated `name: value` capture format is replayed with:

```bash
.venv-macbook/bin/python tools/replay_windows_data_stream.py \
  "/path/to/data_stream.txt" --active-chamber MT --max-frames 100 --speed 10
```

The replayer preserves exact channel names and scalar values. It labels unknown
sequencer state `S_Unknown`; it never claims the file is current physical data.
With the default `--active-chamber auto`, a record-level `active_chamber: PL`
or `active_chamber: MT` is preserved into the watched 35-field record. Explicit
command selection overrides it. LabVIEW `NaN` sensor readings remain unavailable through
the text/regex boundary and are removed before cloud inference.

## Acceptance

Run the read-only local interference gate:

```bash
pi_gateway/macos/audit-scenario-host.sh
```

It requires one owner-only, one-line, 35-field text frame; only loopback 9070/9080;
no local engine/rehearsal ports; File Watch enabled; and both direct cloud and
direct Convene API publication disabled. Port 6080 and its Cloudflare process
belong to the separately authorized screen-sharing session and are deliberately
outside this telemetry audit.

Configuration validation also refuses to start if File Watch is combined with
direct Convene publishing, a non-console cloud transport, `mode=live`, or a
non-loopback listener. A stale config therefore cannot silently recreate a
competing scenario route.

During a bounded run, `/health` must show received and delivered converging,
queue depth zero after drain, no drops/dead letters, and
`file_watch.failed: 0`. `/latest` must show
`mode: harness` or `replay` and a scenario-labeled `source_id`. This proves
source-to-file delivery; manually confirm that the whole-frame Convene value
changes across heartbeat timestamps. The MacBook does not automate or sign in to
Convene. The common cloud ingest receives the same raw 35-field text shape as
live telemetry and does not infer whether it originated from live or scenario
data. Only one source stream may drive one engine process at a time.

Ports `9070` and `9080` must both listen only on `127.0.0.1`. The MacBook must
hold no VM ingest token and needs no Convene API token for scenario telemetry.
Preserve the configuration backup, logs, evidence, and exact Git SHA.
