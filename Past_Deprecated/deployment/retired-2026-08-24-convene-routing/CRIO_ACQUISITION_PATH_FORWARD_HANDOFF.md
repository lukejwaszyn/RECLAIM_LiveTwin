# RECLAIM cRIO Acquisition Path-Forward Handoff

**Date:** 2026-08-20

**Branch:** `desktop/edge-gateway`

**Decision:** Reuse the existing source-assembled data record; do not tail the USB
log or promote per-item PSP as the production seam.

**Deployment status:** **NO-GO** until the deployed-source, coherence, authority,
RT-safety, rollback, and supervised acceptance gates in this handoff pass.

## 1. Executive handoff

Discovery has now proven that `Data Stream.vi` creates timestamp-named
`*_data_stream.txt` files beneath `U:\Data Stream` and writes a repeating,
named process record. Thirteen retained captures show that the current record has
grown from 30 to 32 to 34 fields. The latest captures have one stable 34-field
schema at an observed approximate 0.38-second record period and roughly 817
characters per record.

This is the lowest-risk source seam found so far: the control application already
assembles nearly all known measurements and process flags into one record before
writing it. It is not yet a production telemetry contract:

- the file contains only one start timestamp, not a timestamp per record;
- it has no stable physical `cycle_id`, authoritative `source_op_state`, or
  explicit physical `active_chamber`;
- one serialized line does not by itself prove all inputs came from one Scan Engine
  iteration;
- older captures contain delimiter defects;
- at least one channel exhibits a persistent high value that may be an invalid or
  open-thermocouple indication and requires controls evidence;
- the record is written to storage, not proven network-readable;
- the discovered project copy is not proven to be the deployed `startup.rtexe`
  source.

The selected direction is therefore:

```text
existing acquisition/sequencer values
              |
      source-latched snapshot             <-- prove this boundary
              |
     existing record assembly
          /                 \
existing USB logger     bounded latest-wins handoff
                              |
                    low-priority TCP producer
                              |
                  <WINDOWS10_GATEWAY_IP>:9070, JSON + LF
                              |
                    existing edge gateway/VM
```

The existing USB logger remains unchanged during the first telemetry release. The
telemetry branch must never block or backpressure acquisition, sequencing,
interlocks, safety, or file logging. A single network-published string plus the
Windows relay is the fallback if the controls owner rejects an RT-side TCP client.

## 2. Evidence record

### 2.1 Project and VI evidence

The inspected evidence copy is under `C:\Users\latitude4\Desktop\Read Only` and is
not committed to this repository.

| Artifact | SHA-256 of inspected copy | Finding |
|---|---|---|
| `Data Stream.vi` | `D120133ECFB516F69E0EFF22A7E42C17E0E7943629C80DE6C28A91F8290ED2C1` | Assigned beneath the cRIO RT target; references numerous inputs, Mod1 digital outputs, Mod4 analog outputs, VISA, and `RF Testing.vi` |
| `Preheating Metals.vi` | `818F18474F8041AA783C3CEC416173039C1110067BD13AD58F1D768B3ADDBE27` | Assigned beneath the RT target; references inputs, outputs, VISA, and RF dependencies |
| `Read Only Sensors.lvproj` | `198C7E412EDDC06FA399189DAEB5F30CF0B0578F4366B37B214FE5F89B4F2DE8` | LabVIEW 2019 project for cRIO-9024/VxWorks/PowerPC at `<CRIO_SOURCE_IP>`; contains no populated build specification proving deployed-source identity |

These hashes differ from earlier hashes recorded in the PSP development plan.
Treat the inspected files as a distinct evidence revision. The folder name "Read
Only" is not a safety property: the VIs contain output-capable references and must
not be run as a telemetry adapter.

Project metadata names `/c/ni-rt/startup/startup.rtexe`, but the evidence copy does
not establish that its VIs built the image currently deployed on the cRIO. Project
metadata also has VI Server TCP and the web server disabled.

### 2.2 File-initialization block diagram

The inspected block-diagram capture proves that the logger:

1. generates a short date/time string;
2. replaces filename separators with underscores;
3. appends `_data_stream.txt`;
4. builds the path beneath `U:\Data Stream`;
5. opens the file read/write using a replace-or-create-with-confirmation mode;
6. writes the initial timestamp plus blank lines; and
7. passes the file reference onward.

`U:` is consistent with an NI RT removable-storage volume, but the controls owner
must confirm the actual mounted device. The retained desktop files appear to be
copies of this storage output, not a live network publication.

The captured section is initialization only. It does not show the repeating record
writer, the record-assembly wire, loop boundaries, or scan-latching behavior.

### 2.3 Retained data captures

Thirteen `*_data_stream.txt` files were found under
`C:\Users\latitude4\Desktop\Data Copy`; they are not committed here. Together they
contain approximately 23,700 process records.

| Capture generation | Fields per record | Observed schema result |
|---|---:|---|
| Earliest captures | 30 | Two fields lack the `: ` delimiter in some/all records (`MT_crucible_temperature` and `MW_reverse_coupler`), so strict parsing fails |
| Intermediate captures | 32 | Schema evolved; some early intermediate records are not fully stable |
| Latest captures | 34 | One stable field order/schema within each of the final three captures |

The latest 34-field record contains:

```text
PL_surface_temp
PL_output_pressure
PL_chamber_pressure
PL_top_condenser_temp
PL_bottom_condenser_temp
PL_wall1
PL_wall2
PL_bottom1
PL_bottom2
PL_bottom3
PL_bottom4
PL_flow_meter
PL_process
PL_preprocess
MW_reverse_coupler
PL_postprocess
PL_chamber_pump
PL_purge_pump
MT_crucible_temperature
MT_top
MT_bottom
MW_water_state
MW_flow_state
MW_RF
MW_status
MW_power
MW_reverse
MW_period
MW_width
MW_freq
MW_water_temp
MW_flow_rate
PL_Probe1
PL_Probe2
```

The latest capture contains 5,894 records over approximately 2,215 seconds, or an
approximate 0.376-second period based on file creation-name time and last-write
time. This is an estimate, not a per-record timing measurement, because the file
does not timestamp each record.

`PL_bottom2` remains around 1382.8–1384.3 in the inspected latest capture. Do not
interpret or map this as a valid temperature until the NI-9213 configuration,
open-thermocouple behavior, physical channel map, and same-time panel evidence are
signed by controls.

## 3. Architecture decision

### Selected production direction — existing record to direct TCP

After the controls gates pass, branch the existing per-record snapshot before its
file write into a bounded, non-blocking handoff. A lower-priority telemetry loop
serializes one reviewed JSON object, appends one LF, and maintains one TCP client
connection to the existing gateway listener at `<WINDOWS10_GATEWAY_IP>:9070`.

Why this is selected:

- reuses the existing source-side aggregation instead of reopening 11+ PSP items;
- preserves the proven gateway framing, queue, VM, and Convene chain;
- avoids a new desktop LabVIEW/NI relay in the production topology;
- carries sensors and authoritative metadata in one frame;
- permits explicit bounded latest-wins behavior and no stale replay;
- keeps the cRIO isolated to the existing gateway cable.

This is a direction, not permission to edit or deploy the current VI.

### Controls fallback — one published string

If controls rejects an outbound TCP client on the RT target, publish exactly one
source-built JSON/string variable and adapt the Windows PSP relay to read that one
item. This still requires a supervised RT change, but avoids the observed per-item
subscription behavior and retains a desktop relay.

### Diagnostic fallback — per-item PSP

The existing PSP adapter remains valuable for read-only scan-resource diagnostics
and an explicitly labeled engineering stream. It previously moved eleven audit
channels at a sustainable three-second cadence in one observed configuration, but
valid publishing was not independent of the desktop LabVIEW state and subsequent
multi-item reads failed. It is not the selected production seam.

### Rejected as production — tail the USB file

The USB files are excellent schema and correlation evidence but are not a live
twin transport. Tailing or periodically copying them lacks per-record source time,
quality, explicit loss accounting, authoritative state/cycle/chamber metadata, and
reliable flush/rotation semantics. It also couples telemetry availability to file
I/O and removable storage.

## 4. Source-frame contract

The source should emit one UTF-8 JSON object followed by one LF:

```json
{
  "source_id": "reclaim-crio-rt-01",
  "ts": "2026-08-20T15:42:10.250Z",
  "cycle_id": "<stable-physical-cycle-id>",
  "source_op_state": "S_MicrowaveHeating",
  "active_chamber": "PL",
  "vars": {
    "PL_surface_temp": 224.119084,
    "MW_RF": false,
    "MW_power": 0.0
  }
}
```

Requirements:

- source time is per frame and comes from a documented synchronized clock;
- `cycle_id` is restart-safe physical batch identity, not a telemetry-process ID;
- `source_op_state` is the sequencer's actual state mapped through a signed table;
- `active_chamber` is an explicit physical/sequencer value (`PL`, `MT`, `NONE`),
  not inferred from RF or process flags;
- raw names and units remain at this boundary; SI conversion remains in
  `cloud_engine/labview_map.py`;
- numeric values are finite JSON numbers, booleans are JSON booleans, and missing
  or invalid channels are omitted or accompanied by an approved quality contract;
- serialized size is measured and remains within the gateway's 8192-byte bound;
- one snapshot produces one frame; partial frames are never sent.

The 34-field text record is an evidence fixture, not the final wire syntax. JSON
eliminates the delimiter defects observed in early files and supports typed
metadata without positional parsing.

## 5. Work plan and gates

### Gate 0 — preserve evidence and identify deployed source

**Owners:** controls/NI owner and onsite operator

**Mutation:** none

- Capture NI MAX target software, startup application, Scan Engine mode, mounted
  storage, and clock configuration.
- Identify the authoritative source project, revision, build specification, and
  complete dependencies for the deployed application.
- Hash the deployed-source evidence and compare it with the inspected copies.
- Capture backup/export and demonstrate the rollback procedure before editing.

**Exit:** deployed source and rollback are proven. Otherwise stop.

### Gate 1 — prove the existing snapshot boundary

**Owners:** controls/NI owner with RECLAIM integration reviewer

**Mutation:** none; offline source inspection

- Capture the repeating Write Text File node, its record-string input, containing
  loop, loop timing, and file-reference shift register.
- Trace every record field to its acquisition/sequencer source.
- Prove whether the values are latched in one iteration; measure or bound skew.
- Identify authoritative state, chamber, cycle, per-frame time, and quality
  sources.
- Complete and sign the channel/unit/range/validity map, including the persistent
  `PL_bottom2` high reading.

**Exit:** one reviewed source snapshot and signed authority/channel maps exist.

### Gate 2 — offline contract and parser

**Owners:** RECLAIM repository developer

**Mutation:** repository only; no cRIO/network connection

- Create sanitized 30-, 32-, and 34-field fixtures without committing raw runs.
- Parse strict `name: value` records for evidence only; fail closed on missing
  delimiters, duplicates, non-finite values, containers, and unknown required
  fields.
- Define the reviewed JSON frame and expected cloud conversions.
- Add regression tests for open/overrange/invalid semantics once controls signs
  them.

**Exit:** offline fixtures and tests pass; raw evidence remains outside Git.

### Gate 3 — telemetry implementation review

**Owners:** controls/NI developer, controls owner, gateway owner

**Mutation:** source-controlled offline copy only

- Preserve the existing USB logger behavior.
- Add a bounded depth-one/latest-wins handoff from the reviewed snapshot.
- Run all serialization and TCP operations in a lower-priority telemetry loop.
- Use finite timeouts, bounded reconnect backoff, counters, and discard unsent
  stale frames after failure.
- Provide no listener, input command, shared-variable write from the gateway,
  output reference, setpoint, deploy API, or target-control path.
- Review loop priorities, CPU/memory headroom, watchdogs, failure behavior, and
  dependency diff.

**Exit:** controls signs the diagram/dependency review and exact build hash.

### Gate 4 — supervised idle-process deployment

**Owners:** onsite operator, controls owner, gateway owner, VM owner

**Mutation:** explicit go required

1. Confirm process safe/idle and capture baseline outputs/interlocks.
2. Deploy only the reviewed build during the approved window.
3. Prove one frame at the gateway and compare it to same-time LabVIEW indicators
   and the USB record.
4. Run at least five minutes of sustained shadow telemetry.
5. Verify cRIO load, loop timing, watchdogs, USB logging, gateway counters, VM
   freshness, and no actuation changes.

**Exit:** one-frame and sustained correlation pass with retained evidence.

### Gate 5 — fault and restart acceptance

- Disconnect/reconnect the Ethernet cable.
- Stop/restart only the telemetry loop where supported.
- Restart the gateway.
- Demonstrate bounded reconnect, latest-wins behavior, no stale replay, no file
  logger disruption, and no control-loop impact.
- Only after all prior gates pass, perform the separately approved cRIO boot test.

**Exit:** production enablement is explicitly approved. Until then the system
remains an engineering shadow stream.

## 6. Go/no-go checklist

- [ ] Deployed source/build identity is proven.
- [ ] Backup and rollback have been exercised.
- [ ] Repeating record wire and loop boundaries are captured.
- [ ] Snapshot coherence/skew is proven or bounded.
- [ ] Channel/unit/range/quality map is signed.
- [ ] `PL_bottom2` and other sentinel behavior is resolved.
- [ ] State/chamber/cycle/time sources are authoritative and signed.
- [ ] Clock offset/drift fits the cloud freshness window.
- [ ] Telemetry is lower priority and cannot block control or logging.
- [ ] One writer targets `<WINDOWS10_GATEWAY_IP>:9070`; no command path exists.
- [ ] Frame size, cadence, reconnect, drop, and stale policies are reviewed.
- [ ] Same-time USB/LabVIEW/gateway/VM correlation passes.
- [ ] Disconnect and restart tests show no control impact or stale replay.
- [ ] Named controls and onsite owners approve production enablement.

Any unchecked item keeps production declaration **NO-GO**.

## 7. Rollback

1. Stop or disable only the telemetry addition.
2. Restore the captured prior startup application using the exercised controls
   procedure.
3. Leave the gateway, durable queue, firewall, VM, Convene bindings, process logic,
   setpoints, interlocks, and retained evidence unchanged.
4. Verify the original control application and USB logger behavior.
5. Retain source/build/config hashes, first frames, load/timing evidence, fault
   results, and rollback results.

## 8. Read next

- `deployment/NewChat_cRIO_Source_Record_TCP_Implementation_Prompt.md`
- `deployment/CRIO_ACQUISITION_OPTIONS_TRADE_STUDY.md`
- `deployment/CRIO_PSP_LIVE_ADAPTER_HANDOFF.md`
- `Past_Deprecated/deployment/CRIO_PSP_ADAPTER_DEVELOPMENT_PLAN.md`
- `Past_Deprecated/deployment/CRIO_TELEMETRY_LINK_HANDOFF.md`
- `docs/RECLAIM_Live_Telemetry_Architecture.md`
