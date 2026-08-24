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
                                      -> Convene scenario machine

BOTH
Convene internal route -> cloud engine POST /ingest -> stochastic dual engine
                       -> computed state -> Convene -> sim_* visualization
```

## Fixed machine roles

| Responsibility | Owner | Required behavior |
|---|---|---|
| Real cRIO acquisition | Windows 10 desktop | Sole live-data gateway; publishes exact source variables to its Convene machine |
| Fabricated/replayed telemetry | MacBook | Scenario-only, loopback receiver, `mode=harness` or `mode=replay`; publishes to its Convene machine |
| Telemetry routing | Convene | Routes either machine's source variables to the cloud engine using the canonical envelope |
| Computation | Cloud-engine VM | Sole stochastic estimator and sole producer of computed state |
| Result routing and display | Convene | Receives processed state and binds the `sim_*` variables to the visualization |

The MacBook is not a live cRIO client. The Windows desktop does not run MacBook
scenarios. Neither source machine directly targets the cloud engine. All engine
output remains advisory and has no actuator authority.

## Source-to-Convene contract

The gateway flattens each accepted source frame into scalar Convene variables.
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

Convene's internal route must reconstruct one newline-delimited JSON object per
source update. The cloud endpoint is `POST /ingest` and expects:

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
  "vars": {
    "PL_surface_temp": -143.75,
    "PL_process": true
  }
}
```

The internal route must nest the raw LabVIEW variables under `vars`; flattening
them at the engine boundary is not compatible with the production ingest
contract. It must preserve `run_id`, monotone `seq`, timestamps, cycle identity,
mode, operating state, and active chamber. Authentication and the deployed
Convene route configuration are external secrets/infrastructure and are not
stored in this repository.

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
disabled.

## Repository state and verified evidence

At commit `2f536f8` before this documentation consolidation:

- Windows live and MacBook scenario publishers send canonical envelope scalars
  and exact raw LabVIEW names to Convene without a generated prefix.
- The MacBook scenario controller supports nominal, power-outage, lunar, and
  loss-of-data profiles with an explicit `PL` or `MT` chamber.
- The cloud engine supports the 34-field LabVIEW record and continues gracefully
  when individual raw fields are `NaN`/unavailable.
- The full local integration suite passed: 318 tests.
- No predictive engine or direct cloud telemetry transport is intended to run on
  the MacBook.

## Open integration gaps — do not claim these are proven

1. The deployed Convene internal mapping and authentication have not been
   captured in this repository or exercised by an automated end-to-end test.
2. Production cloud ingest currently accepts only `mode=live`. MacBook scenarios
   publish `mode=harness` or `mode=replay`, so they cannot use the same production
   engine instance until the engine interface deliberately supports an isolated,
   labeled scenario identity or Convene routes them to a non-production instance.
3. The current VM return bridge also rejects any state whose mode is not `live`.
   Scenario return requires an explicit, isolated bridge policy; changing the
   mode in transit to disguise scenario data as live is forbidden.
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

1. Configure and inspect Convene's source-machine-to-engine transformation.
2. Decide and implement the isolated scenario-mode engine/return policy.
3. Confirm one and only one `sim_*` writer.
4. Deploy the same SHA to the Windows gateway and cloud-engine VM.
5. Run the three rehearsal profiles and retain correlated end-to-end evidence.
6. Run the supervised live cRIO smoke test.

Older handoffs are retained only as historical evidence under
`Past_Deprecated/deployment/retired-2026-08-24-convene-routing/`. They are not
operational instructions and must not override this document.
