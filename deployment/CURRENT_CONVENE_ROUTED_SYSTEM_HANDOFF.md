<!-- generated-by: gsd-doc-writer -->
# RECLAIM current system handoff: Convene-routed telemetry

**Effective:** 2026-08-24

**Status:** sole active handoff and architecture pickup point

**Supersedes:** every older handoff, handover, and session prompt in this repository

## Decision of record

Convene is now the common routing plane for both source telemetry and computed
state. A gateway/scenario host publishes its machine variables to Convene;
Convene's internal data routing sends either source record to the same cloud
endpoint; the cloud engine normalizes it and runs the stochastic dual-chamber algorithm;
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
  -> atomic one-frame scenario text -> Convene File Watch -> Convene scenario machine

BOTH
Convene internal route -> cloud engine POST /ingest -> stochastic dual engine
                       -> computed state -> Convene -> sim_* visualization
```

## Fixed machine roles

| Responsibility | Owner | Required behavior |
|---|---|---|
| Real cRIO acquisition | Windows 10 desktop | Sole live-data gateway; publishes exact source variables to its Convene machine |
| Fabricated/replayed telemetry | MacBook | Scenario-only, loopback receiver, `mode=harness` or `mode=replay`; atomically writes one current Convene File Watch text frame |
| Telemetry routing | Convene | Routes either machine's identical 35-field record to the common engine endpoint |
| Computation | Cloud-engine VM | Sole stochastic estimator and sole producer of computed state |
| Result routing and display | Convene | Receives processed state and binds the `sim_*` variables to the visualization |

The MacBook is not a live cRIO client. The Windows desktop does not run MacBook
scenarios. Neither source machine directly targets the cloud engine. All engine
output remains advisory and has no actuator authority.

## Source-to-Convene contract

The Windows live gateway flattens each accepted source frame into scalar Convene
variables and publishes them to its machine API. The MacBook scenario gateway
flattens the same contract into one owner-private text file which Convene File
Watch reads each heartbeat. The file is replaced, not appended. Direct MacBook
Convene API publishing is disabled. The watched scenario/replay record has exactly
the same current interface shape as live telemetry: authoritative
`active_chamber` followed by the 34 raw fields. It carries no source envelope.
The common engine endpoint adds unclassified receipt provenance.

The exact, case-sensitive LabVIEW variables are:

`PL_surface_temp`, `PL_output_pressure`, `PL_chamber_pressure`,
`PL_top_condenser_temp`, `PL_bottom_condenser_temp`, `PL_wall1`, `PL_wall2`,
`PL_bottom1`, `PL_bottom2`, `PL_bottom3`, `PL_bottom4`, `PL_flow_meter`,
`PL_process`, `PL_preprocess`, `MW_reverse_coupler`, `PL_postprocess`,
`PL_chamber_pump`, `PL_purge_pump`, `MT_crucible_temperature`, `MT_top`,
`MT_bottom`, `MW_water_state`, `MW_flow_state`, `MW_RF`, `MW_status`,
`MW_power`, `MW_reverse`, `MW_period`, `MW_width`, `MW_freq`, `MW_water_temp`,
`MW_flow_rate`, `PL_Probe1`, and `PL_Probe2`.

The current physical live record contains authoritative `active_chamber` (`PL`,
`MT`, or `NONE`) plus the exact 34 raw fields. Older retained captures may lack
the chamber field; engine inference for those records is fallback-only.
Convene routes it to `/ingest`, where the engine generates explicitly
receipt-owned provenance for missing envelope values. It does not claim that
LabVIEW produced a run ID, source ID, sequence, timestamp, or cycle ID.

Do not add a blanket `gw_` prefix. The source publisher must never emit `sim_*`.
If an independently defined source field already contains `gw_`, preserve that
name, but do not manufacture new gateway aliases. The cloud result path is the
only `sim_*` writer.

LabVIEW `NaN` means the sensor value is unavailable. The MacBook text frame keeps
the complete 34-field source layout and writes `NaN` for an unmodeled/unavailable
channel. Convene extracts those values by regex; the cloud adapter converts them
to unavailable values before inference and preserves the rest of the frame. It
must not invent replacement measurements.

## Convene-to-engine contract

Convene's internal route sends live, scenario, and approved replay records to the
same `POST /ingest`. It accepts the flat 35-field snapshot, the complete one-frame
LabVIEW-style text record, or a legacy complete canonical envelope with raw fields
nested under `vars`.

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
Current text ingest assigns `mode=telemetry`, preserves authoritative
`active_chamber`, and generates clearly receipt-owned run, sequence, timestamp,
cycle, and state fields. It does not infer whether the frame was live or scenario.

Every ingest-route response contains the accepted computed `state` and a flat
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
pi_gateway/macos/start-rehearsal-scenario.sh start loss-of-data MT
pi_gateway/macos/start-rehearsal-scenario.sh status
pi_gateway/macos/start-rehearsal-scenario.sh stop
```

`PL` drives the plastics sensor bank and `MT` drives the metals sensor bank. The
selected value is also published as `active_chamber`. Only one scenario sender
may run at a time. Each command defaults to one compressed cycle with
profile-specific pacing: power outage emits 211 frames over about 3 minutes 30
seconds, reaches approximately 680°C (above the 660°C aluminum melt threshold),
and ends powered off in cooldown. Lunar surface emits 301 frames over about 5
minutes, reaches approximately 450°C at 700 Torr, and ends powered off after an
extended radiation-limited cooldown. Output is fixed
at one complete frame per wall-clock second to match Convene's approximately
one-second poll. The MacBook receiver remains on `127.0.0.1:9070`, its status
surface remains on `127.0.0.1:9080`, and its direct cloud transport remains
disabled. Its File Watch path is
`/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt`.
Keep the existing single whole-frame Convene variable name. Leave JSON path and
capture regex blank. Do not rename the working variable or split the frame into
35 individual bindings; the file name and Convene variable name need not match.

## Repository state and verified evidence

Verified locally on 2026-08-24 before the final commit:

- Windows live and MacBook scenarios publish the identical `active_chamber` plus
  34-field text contract without fabricated envelope fields or a blanket prefix.
- The MacBook scenario controller supports nominal, power-outage, lunar, and
  loss-of-data profiles with an explicit `PL` or `MT` chamber.
- The cloud engine supports the 34-field LabVIEW record and continues gracefully
  when individual raw fields are `NaN`/unavailable.
- The active local integration suite passes: 264 tests. Historical
  state-bridge/direct-route tests are archived and intentionally excluded.
- No predictive engine or direct cloud telemetry transport is intended to run on
  the MacBook.

## Open integration gaps — do not claim these are proven

1. The deployed Convene internal mapping and authentication have not been
   captured in this repository or exercised by an automated end-to-end test.
2. The updated common-frame engine contract must be deployed to the VM
   before Convene forwards MacBook scenarios to it.
3. One engine process has one active run/model state. Convene must route only one
   live or scenario source stream to that process at a time. Simultaneous streams
   require separate engine instances; mixing them is forbidden.
4. Exactly one deployed component must publish each `sim_*` variable. Disable any
   older VM agent, bridge, or Convene mapping that would create a second writer.
5. The exact repository SHA must be deployed to the VM and Windows live gateway
   before acceptance evidence is valid.

The prepared VM audit/rework procedure is
`deployment/CLOUD_ENGINE_VM_AUDIT_AND_REWORK.md`. The active
`deployment/windows-vm/` directory contains only the read-only inventory and
current contract-test entry points; all former bridge/tunnel deployment scripts
are archived. These files are prepared on the scenario desktop but are executed
only after logging onto the actual VM; no cloud engine or `sim_*` publisher runs
on the MacBook.

## Required competition acceptance

For each route, retain the Git SHA, source machine ID, run ID, timestamps,
Convene screenshots/logs, engine acceptance response, returned `sim_*` state, and
any deviation.

| Test | Source | Pass condition |
|---|---|---|
| Live smoke | cRIO through Windows 10 | Authoritative `active_chamber` plus the exact 34 source fields appear in Convene, `/ingest` generates receipt provenance, and correlated `sim_*` state returns |
| Nominal PL | MacBook scenario | Full PL processing cycle, monotone engine receipt sequence, no cross-chamber activation, and correlated result returns |
| Power outage MT | MacBook scenario | Outage/coast/restart state progression is visible while MT remains authoritative |
| Lunar | MacBook scenario | Lunar profile completes with explicit chamber identity and correlated result |
| Loss of data | MacBook scenario | Stale state fails closed; the last-good value is not represented as fresh |
| Unavailable sensors | Either isolated route | `NaN`/omitted sensors do not crash routing or inference and are never fabricated |

Until all relevant rows pass through the actual Convene internal route, the
system is an engineering demonstration, not a proven flawless end-to-end path.

## Pickup order

1. Configure and inspect Convene's File Watch and source-machine routes.
2. Audit the actual VM with the read-only script and preserve rollback evidence.
3. Deploy the common-frame cloud-engine SHA and exercise its loopback contract.
4. Confirm one and only one active source stream and `sim_*` writer.
5. Run the three rehearsal profiles through Convene and retain correlated evidence.
6. Run the supervised current-frame live cRIO smoke test through `/ingest`.

Older handoffs are retained only as historical evidence under
`Past_Deprecated/deployment/retired-2026-08-24-convene-routing/`. They are not
operational instructions and must not override this document.
