# RECLAIM Convene Live Binding

This binding starts clean. Configure exactly one live `sim_` publisher: the
headless Windows Server 2025 VM Convene agent installed during bootstrap and
reading the repository state
bridge's atomic `C:\ConveneAgent\sim_vars.json` output. The bridge alone reads
the cloud dual engine's loopback `/state` endpoint. Do not run the legacy state publisher,
simulation bridge, CSV importer, or harness publisher against this same
Convene variable set.

Convene adds `sim_` to received fields. Bind these variables:

| Convene field | Purpose |
|---|---|
| `sim_op_state` | authoritative system state for the shared sequential process |
| `sim_source_op_state` | cRIO sequencer audit value |
| `sim_active_chamber` | `PL`, `MT`, or `NONE` |
| `sim_PL_op_state`, `sim_MT_op_state` | chamber-local state |
| `sim_run_id`, `sim_cycle_id`, `sim_seq`, `sim_ts_source` | traceability and ordering |
| `sim_mode`, `sim_ingest_status`, `sim_state_age_ms` | live-data validity gate |
| `sim_data_live`, `sim_bridge_status`, `sim_bridge_valid_until` | bridge validation and downstream publication lease |
| `sim_PL_sensor_valid`, `sim_MT_sensor_valid` | chamber measurement-availability gates |
| `sim_PL_T_bed_est`, `sim_MT_T_bed_est` | principal predicted temperatures |
| `sim_PL_advisory_severity`, `sim_MT_advisory_severity` | chamber risk/advisory display |

The primary system dashboard binds `sim_op_state`, not either chamber state.
It visibly displays `sim_mode`, `sim_run_id`, `sim_seq`, and
`sim_state_age_ms`. If mode is not `live`, status is not `accepted`, or the
age exceeds the agreed limit, show **DATA NOT LIVE**. The VM state bridge also
publishes a short `bridge_valid_until` lease. Convene must compare its own UTC
clock to that deadline; an expired lease shows **DATA NOT LIVE** even if the last
complete heartbeat payload still says `data_live: true`. This closes the case in
which a bridge crash or persistent Windows sharing violation prevents a newer
`sim_vars.json` replacement.

Transport liveness and measurement availability are separate. A fresh bridge
record may legitimately have `sim_PL_sensor_valid == false` or
`sim_MT_sensor_valid == false`; gray or suppress that chamber's retained process
and forecast values instead of presenting them as current. Do not manufacture a
numeric zero to clear a missing measurement.

First bind these fields in a separate test view. After a successful shadow run,
remove legacy writers and promote this binding set to the operator view.

## Convene-native `.stp` visualization

Live 3D visualization is done with Convene's **native visualization tool** — not
Unreal (the Unreal/Twinmotion path is retired and not carried forward). The tool
loads a `.stp` (STEP, ISO 10303) CAD model of the system and **binds incoming
`sim_` variables to specific geometry elements**, so the model animates as the
plant operates (e.g. chamber temperatures drive color/heat overlays on the
corresponding bodies, `sim_active_chamber` highlights the live chamber,
`sim_op_state` drives the stage indicator).

Rules:

1. **Read-only consumer of the VM agent's `sim_` publication.** The visualization
   binds the same fields delivered from the bridge through the installed VM
   Convene agent. It does not call `/state`, possess `RECLAIM_READ_TOKEN`, become
   a second writer, or talk to the cRIO.
2. **Bind to the published `sim_` set only**, not raw channels — the `sim_`
   variables above are the contract surface.
3. **Same freshness and lease gate as the dashboard.** When `sim_mode` is not `live`,
   `sim_ingest_status` is not `accepted`, or `sim_state_age_ms` exceeds the
   agreed limit, or the viewer's current UTC time exceeds
   `sim_bridge_valid_until`, the view must show **DATA NOT LIVE** rather than
   freezing on a stale pose.
4. **Element mapping is a maintained artifact.** Keep the variable→`.stp`-element
   binding table with the model so a geometry revision can't silently detach a
   signal from its body.

## Gateway audit machine (laptop as a second Convene machine)

The laptop gateway is additionally registered in Convene as its **own
machine**, publishing the exact frame it received from LabVIEW and submitted
to the cloud. Purpose: prove, side by side, that LabVIEW's values, the
gateway's submitted frame, and the cloud's published state agree — the
losslessness audit for the whole chain.

Rules:

1. **Separate machine, exact source names.** The gateway publisher does not add
   a blanket prefix. It publishes canonical names such as
   `seq`, `ts`, `run_id`,
   `source_op_state`, `active_chamber`, and the raw channels
   (`MW_power`, `PL_bottom1`, …), while preserving `gw_` on any field whose
   approved source contract already includes it. It never writes any `sim_` variable —
   the cloud engine's publisher remains the single writer of that set.
2. **Best-effort tap, out of the delivery path.** Immediately after durably
   enqueuing a canonical frame for the VM, the gateway submits the same scalar
   envelope/raw values to the MacBook machine's `/machine/publish` endpoint with
   their exact canonical names. Its one-slot worker coalesces during a Convene outage and can
   never block, slow, reorder, or acknowledge the durable VM queue. `/latest`
   remains the independent local inspection surface; do not expose port 9080.
3. **The audit view** shows three columns per signal: LabVIEW indicator,
   exact-name gateway variables, `sim_*`. Matching `seq`/`sim_seq` and equal
   `source_op_state`/`sim_source_op_state` demonstrate the chain is
   lossless; the `seq − sim_seq` lag together with `sim_state_age_ms` is
   the live transport-delay readout.
4. This view is operator-adjacent (verification), not the operator dashboard —
   the primary view still binds `sim_op_state` and gates on freshness.
