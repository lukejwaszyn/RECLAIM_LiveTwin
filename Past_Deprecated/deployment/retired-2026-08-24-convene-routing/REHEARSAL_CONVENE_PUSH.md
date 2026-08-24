# Scenario -> gateway -> engine -> Convene

> Current route as of 2026-08-23. This supersedes the separate 8177-8181
> estimator services and the `rehearsal_*` direct publisher for operational
> scenario runs.

## One canonical path

Every scenario uses the installed data path, with no side estimator and no
second source of predicted state:

```text
TruthPlant scenario
  -> raw LabVIEW-shaped TCP frame
  -> installed edge gateway :9070
       -> direct Convene audit publish (exact-name gateway variables)
       -> durable HTTPS publish to the production cloud /ingest
  -> DualPushEngine /state
  -> installed VM state bridge / Convene agent (sim_*)
```

The gateway is the single fan-out point. The exact canonical frame represented
by exact-name gateway variables is the frame consumed by the cloud engine. Only the cloud engine may
produce predicted `sim_*` state.

The older scenario services on 8177-8181 and
`tools/windows/start-rehearsal-convene-publisher.ps1` remain diagnostic tools,
but are not part of this route and must not be started alongside it.

## Fixed contract defect

The first synthetic-cRIO implementation omitted `active_chamber`. The gateway
therefore emitted `active_chamber: null`; production `/ingest` rejects that
envelope before estimator stepping. This explains the observed split where a
gateway-side exact-name gateway variables audit could advance without a corresponding engine/sim
output.

`tools/synthetic_crio.py` now emits every required upstream hint:

- `source_id` identifies the scenario, scenario name, and environment;
- `source_op_state` carries the sequencer state;
- `active_chamber` is explicitly `PL`;
- `cycle_id` is non-empty and unique per scenario cycle;
- `ts` is generated immediately before transmission;
- `vars` contains the raw LabVIEW channel block.

The installed gateway still owns `schema_version`, `mode`, `run_id`, and `seq`.
For this explicitly initiated commissioning/scenario route it remains
`mode=live`, which is required by the production engine and the installed
`sim_*` bridge. Synthetic provenance remains visible in both `source_id` and
`sim_source_id`. The launcher refuses to run while the real cRIO is connected.

## Run

First deploy/restart the gateway from the same repository revision. Then, with
the real cRIO disconnected:

```powershell
cd C:\Users\latitude4\Documents\Codex\2026-08-16\i\RECLAIM_LiveTwin
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal
```

Other profiles are `power-outage`, `lunar`, and `loss-of-data`.

The launcher refuses to start unless all of these are true:

- exactly one gateway listener exists on `<WINDOWS10_GATEWAY_IP>:9070`;
- no `<CRIO_SOURCE_IP>` cRIO session is connected or waiting;
- loopback gateway status is available on port 9080;
- transport is HTTPS and mode is live;
- the independent Convene gateway fan-out is enabled.

While running, inspect the common path:

```powershell
curl --fail http://127.0.0.1:9080/health
curl --fail http://127.0.0.1:9080/latest
```

Expected evidence:

- `received` advances: scenario reached the gateway;
- `delivered` advances and `queue_depth` returns to zero: the cloud engine
  acknowledged the same frames;
- `convene.delivered` advances: exact-name gateway variables reached Convene;
- `/latest.source_id` starts with `reclaim-synthetic-scenario:`;
- Convene `source_id` and `sim_source_id` match that source;
- `sim_seq` advances behind `seq`, subject to the VM bridge cadence.

If exact-name gateway variables advances but `sim_*` does not, do not add another estimator or desktop
publisher. The remaining fault is after cloud ingest: inspect the cloud engine
`/state`, then the installed VM state bridge and Convene agent. The known
`machineCommands` composite-index heartbeat failure is documented in
`CONVENE_FIRESTORE_INDEX_HANDOVER.md`; exact-name gateway variables bypasses it through direct publish,
while the VM agent's `simVars` heartbeat can still be affected.

## Verification

`tools/tests/test_synthetic_crio.py` proves the complete local contract against
real components: raw scenario frames traverse an actual TCP receiver and gateway
framer, the exact resulting `mode=live` canonical frame is accepted by a
production `DualPushEngine`, and it publishes valid PL state. The gateway and
synthetic-cRIO suite currently passes 64 tests.

## Live deployment result: 2026-08-23

Sandbox tests were not treated as deployment verification. Four bounded streams
were sent to the actual `<WINDOWS10_GATEWAY_IP>:9070` listener with the real cRIO
disconnected. The installed gateway then performed its real HTTPS and Convene
operations.

| Run | Rate / frames | Gateway received | exact-name gateway variables delivered | Cloud ack | Dead-letter |
|---|---:|---:|---:|---:|---:|
| contract smoke | 10 Hz / 30 | 30 | 4 | 0 | 30 |
| accelerated continuous | 10 Hz / 150 | 150 | 20 | 0 | 150 |
| configured-rate check | 2 Hz / 120 | 120 | 74 | 0 | 120 |
| conservative check | 1 Hz / 180 | 180 | 178 | 0 | 180 |

All gateway-Convene deliveries reported zero failures and carried
`reclaim-synthetic-scenario:nominal:earth_lab`. Thus real scenario data did land
in Convene under exact-name gateway variables. Every cloud rejection was final `timestamp_stale`; the
measured source-to-dead-letter delay was 15.5-85.9 seconds. An isolated single
frame also took 27.8 seconds and was rejected. The public engine `/health`
remained fast (~0.5 seconds), at `ingested_total=2830`, and retained active run
`e61a982f-2d31-456b-9213-7a403361a4af`; it never adopted gateway run
`c26e3f03-d380-4e1b-adbf-58edba146ac5`.

This is a live **FAIL** for the engine/`sim_*` leg. Do not claim Convene `sim_*`
verification and do not work around it with a second estimator. On the VM,
inspect the engine service logs and durable identity state for the gateway run:

```powershell
$run = 'c26e3f03-d380-4e1b-adbf-58edba146ac5'
Get-ChildItem C:\ProgramData\RECLAIM\engine\logs -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 6 |
  ForEach-Object { Select-String -Path $_.FullName -Pattern $run,'internal_error','persist','supersession','timestamp_stale' }

Get-Acl C:\ProgramData\RECLAIM\engine\state\ingest_state.json | Format-List
Get-Content C:\ProgramData\RECLAIM\engine\state\ingest_state.json
Invoke-RestMethod http://127.0.0.1:8078/health
```

Do not print either engine token. Repair the actual pre-commit/persistence fault
shown by those logs, restart only `RECLAIMIngestEngine` if required, then repeat
one bounded 1 Hz stream. A pass requires cloud acknowledgements above zero, the
engine active run matching the gateway run, and visible advancing `sim_*` values.
