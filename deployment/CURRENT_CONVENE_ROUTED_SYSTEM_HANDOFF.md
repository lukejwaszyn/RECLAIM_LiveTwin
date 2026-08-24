<!-- generated-by: gsd-doc-writer -->
# RECLAIM current system handoff: Convene-routed telemetry

**Effective:** 2026-08-24

**Status:** sole active handoff and architecture pickup point

**Supersedes:** every older handoff, handover, and session prompt in this repository

## Decision of record

Convene is now the common routing plane for both source telemetry and computed
state. A gateway/scenario host publishes its machine variables to Convene;
Convene's internal data routing builds and sends the canonical telemetry frame to
the cloud engine; the cloud engine runs the stochastic dual-chamber algorithm;
and the computed result returns to Convene for visualization.

There is no production gateway-to-cloud telemetry route over a separately
managed HTTPS or Cloudflare tunnel. Cloudflare may still be used by infrastructure
outside this repository, but it is not an application-level telemetry seam and
must not be configured on either source machine.

```text
LIVE
cRIO / LabVIEW -> Windows 10 live gateway -> Convene live machine

SCENARIO
synthetic generator or approved replay -> MacBook scenario gateway
  -> atomic local scenario JSON -> Convene File Watch -> Convene scenario machine

BOTH
Convene internal route -> cloud engine POST /ingest -> stochastic dual engine
                       -> computed state -> Convene -> sim_* visualization
```

## Fixed machine roles

| Responsibility | Owner | Required behavior |
|---|---|---|
| Real cRIO acquisition | Windows 10 desktop | Sole live-data gateway; publishes exact source variables to its Convene machine |
| Fabricated/replayed telemetry | MacBook | Scenario-only, loopback receiver, `mode=harness` or `mode=replay`; atomically writes the Convene File Watch JSON |
| Telemetry routing | Convene | Routes either machine's source variables to the cloud engine using the canonical envelope |
| Computation | Cloud-engine VM | Sole stochastic estimator and sole producer of computed state |
| Result routing and display | Convene | Receives processed state and binds the `sim_*` variables to the visualization |

The MacBook is not a live cRIO client. The Windows desktop does not run MacBook
scenarios. Neither source machine directly targets the cloud engine. All engine
output remains advisory and has no actuator authority.

## Source-to-Convene contract

The Windows live gateway flattens each accepted source frame into scalar Convene
variables and publishes them to its machine API. The MacBook scenario gateway
flattens the same contract into one owner-private JSON file which Convene File
Watch reads each heartbeat. Direct MacBook Convene API publishing is disabled.
Envelope variables are:

`schema_version`, `mode`, `run_id`, `source_id`, `cycle_id`, `seq`, `ts`,
`source_op_state`, and `active_chamber`.

The exact, case-sensitive LabVIEW variables are:

`PL_surface_temp`, `PL_output_pressure`, `PL_chamber_pressure`,
`PL_top_condenser_temp`, `PL_bottom_condenser_temp`, `PL_wall1`, `PL_wall2`,
`PL_bottom1`, `PL_bottom2`, `PL_bottom3`, `PL_bottom4`, `PL_flow_meter`,
`PL_process`, `PL_preprocess`, `MW_reverse_coupler`, `PL_postprocess`,
`PL_chamber_pump`, `PL_purge_pump`, `MT_crucible_temperature`, `MT_top`,
`MT_bottom`, `MW_water_state`, `MW_flow_state`, `MW_RF`, `MW_status`,
`MW_power`, `MW_reverse`, `MW_period`, `MW_width`, `MW_freq`, `MW_water_temp`,
`MW_flow_rate`, `PL_Probe1`, and `PL_Probe2`.

Do not add a blanket `gw_` prefix. The source publisher must never emit `sim_*`.
If an independently defined source field already contains `gw_`, preserve that
name, but do not manufacture new gateway aliases. The cloud result path is the
only `sim_*` writer.

LabVIEW `NaN` means the sensor value is unavailable. The source-to-Convene
publisher omits non-finite values because strict JSON cannot carry them. The
cloud adapter accepts LabVIEW-shaped frames containing unavailable sensor values,
removes those values before inference, and preserves the rest of the frame. It
must not invent replacement measurements.

## Convene-to-engine contract

Convene's internal route sends one newline-delimited JSON object per source
update to `POST /ingest`. The engine accepts either the flat File Watch snapshot
or the equivalent canonical envelope with raw fields nested under `vars`. The
flat form is preferred because Convene can forward the file without renaming:

```json
{
  "schema_version": "reclaim.telemetry.v1",
  "mode": "live",
  "run_id": "unique-run-id",
  "source_id": "source-machine-id",
  "cycle_id": "source-cycle-id",
  "seq": 1,
  "ts": "2026-08-24T12:00:00.000Z",
  "source_op_state": "S_Unknown",
  "active_chamber": "PL",
  "PL_surface_temp": -143.75,
  "PL_process": true
}
```

The engine collects only exact, case-sensitive LabVIEW names into its internal
`vars` block. `PL_*` values feed the plastics estimator, `MT_*` values feed the
metals estimator, shared `MW_*` power is attributed by authoritative
`active_chamber`, and `sim_*` input is rejected as a feedback loop. Production
ingest accepts `mode=live`, `mode=harness`, and `mode=replay` without changing
the label. It preserves `run_id`, monotone `seq`, timestamps, cycle identity,
operating state, and active chamber.

The `POST /ingest` response contains the accepted computed `state` and a flat
`variables` object with every finite scalar under its cloud-owned `sim_*` name.
Convene routes that response directly to the visualization; the old VM file
state bridge is not part of this path. Authentication and the deployed Convene
route configuration are external secrets/infrastructure and are not stored in
this repository.

<!-- VERIFY: capture the deployed Convene route mapping, authentication owner, and one accepted response without storing credentials. -->

## Scenario operation on the MacBook

The one command controller starts, reports, and stops the only allowed generated
scenario process. Every start explicitly chooses the active chamber:

```bash
pi_gateway/macos/start-rehearsal-scenario.sh start nominal PL
pi_gateway/macos/start-rehearsal-scenario.sh start power-outage MT
pi_gateway/macos/start-rehearsal-scenario.sh start lunar PL
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

`PL` drives the plastics sensor bank and `MT` drives the metals sensor bank. The
selected value is also published as `active_chamber`. Only one scenario sender
may run at a time. The MacBook receiver remains on `127.0.0.1:9070`, its status
surface remains on `127.0.0.1:9080`, and its direct cloud transport remains
disabled. Its File Watch path is
`/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.json`.
For every File Watch binding, use the exact variable name as the JSON path and
leave capture regex blank.

## Repository state and verified evidence

Verified locally on 2026-08-24 before the final commit:

- Windows live and MacBook scenario publishers send canonical envelope scalars
  and exact raw LabVIEW names to Convene without a generated prefix.
- The MacBook scenario controller supports nominal, power-outage, lunar, and
  loss-of-data profiles with an explicit `PL` or `MT` chamber.
- The cloud engine supports the 34-field LabVIEW record and continues gracefully
  when individual raw fields are `NaN`/unavailable.
- The full local integration suite passes: 324 tests.
- No predictive engine or direct cloud telemetry transport is intended to run on
  the MacBook.

## Open integration gaps — do not claim these are proven

1. The deployed Convene internal mapping and authentication have not been
   captured in this repository or exercised by an automated end-to-end test.
2. The updated flat-frame/multi-mode engine contract must be deployed to the VM
   before Convene forwards MacBook scenarios to it.
3. One engine process has one active run/model state. Convene must route only one
   live or scenario source stream to that process at a time. Simultaneous streams
   require separate engine instances; mixing them is forbidden.
4. Exactly one deployed component must publish each `sim_*` variable. Disable any
   older VM agent, bridge, or Convene mapping that would create a second writer.
5. The exact repository SHA must be deployed to the VM and Windows live gateway
   before acceptance evidence is valid.

## Required competition acceptance

For each route, retain the Git SHA, source machine ID, run ID, timestamps,
Convene screenshots/logs, engine acceptance response, returned `sim_*` state, and
any deviation.

| Test | Source | Pass condition |
|---|---|---|
| Live smoke | cRIO through Windows 10 | Exact source fields appear in Convene, engine accepts a fresh `mode=live` frame, and matching `sim_*` identity returns |
| Nominal PL | MacBook scenario | Full PL processing cycle, monotone sequence, no cross-chamber activation, and correlated result returns through the isolated scenario route |
| Power outage MT | MacBook scenario | Outage/coast/restart state progression is visible and remains labeled scenario data |
| Lunar | MacBook scenario | Lunar profile completes with explicit chamber identity and correlated result |
| Loss of data | MacBook scenario | Stale state fails closed; the last-good value is not represented as fresh |
| Unavailable sensors | Either isolated route | `NaN`/omitted sensors do not crash routing or inference and are never fabricated |

Until all relevant rows pass through the actual Convene internal route, the
system is an engineering demonstration, not a proven flawless end-to-end path.

## Pickup order

1. Configure and inspect Convene's File Watch and source-machine route.
2. Deploy the flat-frame/multi-mode cloud-engine SHA.
3. Confirm one and only one active source stream and `sim_*` writer.
4. Deploy the same SHA to the Windows gateway and cloud-engine VM.
5. Run the three rehearsal profiles and retain correlated end-to-end evidence.
6. Run the supervised live cRIO smoke test.

Older handoffs are retained only as historical evidence under
`Past_Deprecated/deployment/retired-2026-08-24-convene-routing/`. They are not
operational instructions and must not override this document.
