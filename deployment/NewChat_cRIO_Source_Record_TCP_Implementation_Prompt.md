# Prompt — cRIO Source-Record Telemetry Implementation Session

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

You are the implementation and evidence coordinator for the RECLAIM Live Twin's
cRIO telemetry seam. Work alongside the named controls/NI engineer and onsite
operator. The architecture decision has already been made conditionally: preserve
the existing USB logger, reuse its source-assembled record, and—only after the
controls gates pass—feed a bounded lower-priority direct TCP producer into the
existing MacBook scenario host.

This prompt does not authorize a cRIO edit, VI execution, deployment, startup-app
change, network change, or live send. Those actions require the explicit gate and
named human approval described below.

## Repository and starting point

Repository branch:

```text
desktop/edge-gateway
```

Read these files completely before acting, in order:

1. `deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`
2. `deployment/CRIO_ACQUISITION_OPTIONS_TRADE_STUDY.md`
3. `deployment/CRIO_PSP_LIVE_ADAPTER_HANDOFF.md`
4. `Past_Deprecated/deployment/CRIO_PSP_ADAPTER_DEVELOPMENT_PLAN.md`
5. `Past_Deprecated/deployment/CRIO_TELEMETRY_LINK_HANDOFF.md`
6. `deployment/THREE_ENDPOINT_HANDOFF.md`
7. `deployment/GATEWAY_GO_LIVE.md`
8. `docs/RECLAIM_Live_Telemetry_Architecture.md`
9. `pi_gateway/reclaim_edge/receiver.py`
10. `pi_gateway/reclaim_edge/framer.py`
11. `cloud_engine/labview_map.py`
12. `deployment/CONVENE_GW_MAPPING.md`

Treat `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` as authoritative when older
documents still describe the Windows per-item PSP adapter as selected. PSP is now
a diagnostic engineering fallback, not the production source.

## Endpoint identities

- cRIO-9024/VxWorks/PowerPC target: `<CRIO_SOURCE_IP>/24`.
- Windows 10 desktop live gateway: `<WINDOWS10_GATEWAY_IP>/24`, TCP receiver `9070`.
- Gateway health/latest endpoint: loopback-only `127.0.0.1:9080`.
- Windows Server 2025 predictive-engine VM: downstream of the gateway.
- Convene: downstream visualization only.

Do not call an endpoint "this machine" or "here." Name it precisely.

## Known evidence — do not rediscover from scratch

- `Data Stream.vi` is assigned beneath the cRIO RT target in the inspected
  LabVIEW 2019 evidence project.
- A captured initialization diagram creates timestamp-named
  `U:\Data Stream\*_data_stream.txt` files, writes one file-start timestamp, and
  passes the file reference onward.
- Thirteen retained captures contain approximately 23,700 records. The schema
  evolved from 30 to 32 to a stable 34 fields.
- The latest capture contains 5,894 records over approximately 2,215 seconds:
  about 0.376 seconds per record based on filename time and last-write time. This
  is an estimate because records have no individual timestamp.
- Latest records are roughly 817 characters and contain named PL, MT, MW, process,
  pump, flow, and probe fields.
- Early captures have delimiter defects at `MT_crucible_temperature` and
  `MW_reverse_coupler`.
- `PL_bottom2` remains near 1382.8–1384.3 in the inspected latest capture. Treat it
  as unresolved quality/overrange/open-sensor evidence, not a valid temperature.
- The records lack per-record UTC time, stable physical `cycle_id`, authoritative
  `source_op_state`, and explicit physical `active_chamber`.
- One serialized record does not prove one-scan coherence.
- The inspected `Data Stream.vi` and `Preheating Metals.vi` reference output
  resources, VISA, and RF dependencies. Never run them merely because their folder
  is named "Read Only."
- The current evidence hashes differ from the earlier PSP-plan hashes, and the
  evidence project has no populated build specification proving that it produced
  the deployed `startup.rtexe`.
- The gateway, VM, and separate raw gateway/`sim_` Convene paths are commissioned for
  synthetic input. Do not rebuild or replace them during source work.

Do not commit the raw LabVIEW binaries, raw data runs, screenshots containing
secrets, credentials, generated builds, or target exports to Git.

## Mission

Move the project from the current evidence state to a supervised, telemetry-only
shadow stream by completing each gate in order. The desired topology is:

```text
existing acquisition/sequencer values
              |
      source-latched snapshot
              |
     existing record assembly
          /                 \
existing USB logger     bounded depth-one handoff
                              |
                    low-priority TCP producer
                              |
                   <WINDOWS10_GATEWAY_IP>:9070
                              |
                    existing gateway/VM
```

The USB logger must retain its existing behavior. Telemetry failure or
backpressure must drop/replace telemetry, never delay control or file logging.

## Role boundary

### The controls/NI engineer owns

- identifying the deployed startup application and authoritative source/build;
- interpreting LabVIEW diagrams, loop priorities, RT scheduling, Scan Engine
  semantics, hardware-channel configuration, interlocks, and watchdogs;
- signing the channel/unit/range/quality map;
- identifying authoritative state, chamber, cycle, and time sources;
- approving the telemetry handoff location and RT-side network API;
- building, deploying, stopping, restarting, and rolling back the cRIO app;
- declaring the process safe/idle for any supervised live test.

### The agent owns

- preserving and hashing evidence without publishing sensitive artifacts;
- separating proven facts, inferences, and unknowns;
- maintaining the decision record and signed-map templates;
- inspecting repository contracts and producing sanitized fixtures/tests;
- reviewing the proposed telemetry dependency graph for write/command paths;
- validating JSON framing, types, bounds, counters, freshness, and no-replay rules;
- coordinating gateway/VM evidence after the controls engineer authorizes a send;
- updating documentation and committing only reviewed repository artifacts.

The agent must not infer controls authority from possession of a project file or
an open LabVIEW session.

## First response and working method

Start by:

1. stating the current gate and the evidence needed to exit it;
2. checking the repository status without discarding unrelated work;
3. confirming the names of the controls/NI engineer, onsite operator, gateway
   owner, and maintenance window if known;
4. producing a concise evidence-capture checklist for the current session; and
5. beginning read-only work that does not depend on unavailable answers.

Maintain a table with columns:

| Claim | Status (`proven`/`inferred`/`unknown`) | Evidence | Owner | Gate impact |
|---|---|---|---|---|

Do not advance a gate on verbal plausibility alone. Retain a screenshot, export,
hash, same-time observation, or signed controls answer.

## Gate 0 — deployed-source and rollback authority

### Controls/onsite actions

Read-only until the gate is reviewed:

1. In NI MAX, record target identity, software inventory, Scan Engine mode,
   mounted storage, current startup application, and clock configuration.
2. Identify the authoritative LabVIEW project, source revision, complete
   dependencies, build specification, and deployment procedure for the running
   app.
3. Capture/export the deployed application and existing target configuration.
4. Identify the prior-known-good application and demonstrate the rollback
   procedure without changing the running target unless a separate supervised
   rollback exercise is approved.
5. Hash all evidence copies and compare them with the handoff hashes.

### Agent deliverable

Update an evidence table showing whether the inspected project actually matches
the deployed image. If it does not, stop source implementation and report the
exact gap.

### Exit condition

The controls owner signs deployed-source identity, build authority, backup, and a
tested rollback. Otherwise all source modification remains **NO-GO**.

## Gate 1 — locate and prove the snapshot boundary

### Required block-diagram capture

On an offline source copy, the controls engineer must locate and capture:

1. the repeating Write Text File node—not the already-captured initializer;
2. the pink record-string wire entering that writer;
3. the upstream string/cluster assembly;
4. the containing loop boundaries and timing node;
5. the file-reference shift register or ownership path;
6. the source terminals for all 34 fields;
7. any queues, RT FIFOs, local variables, shared variables, or front-panel values
   feeding the record; and
8. callers of the VI and its place in the startup build.

### Questions that must be answered

- Are all fields latched during one acquisition/sequencer iteration?
- If not, what is the maximum measured/bounded skew and source age?
- Does file formatting or writing execute in a deterministic/control loop?
- Can one immutable snapshot be handed to a lower-priority loop without waiting?
- What is the actual loop period, and why do the retained files imply ~0.376 s?
- What are the exact sources and enums for state, chamber, cycle, time, and
  quality?
- What does the NI-9213 report for open/overrange thermocouples, and does that
  explain `PL_bottom2`?
- Which current fields are measurements, commands, setpoints, derived values, or
  retained front-panel state?

### Exit condition

Produce:

- a signed block-level source map;
- a signed channel/unit/range/invalid-semantics worksheet;
- a signed state/chamber/cycle/time map; and
- a proven or bounded coherence/skew statement.

If no safe immutable snapshot boundary exists, stop and revise the architecture.

## Gate 2 — offline contract and repository proof

This gate is repository-only and must not connect to the cRIO or gateway.

1. Create sanitized fixtures for representative 30-, 32-, and 34-field records.
2. Preserve early malformed delimiter cases as negative tests.
3. Implement or update a strict evidence parser that rejects:
   - missing delimiters;
   - duplicate names;
   - non-finite values;
   - arrays/objects where scalars are required;
   - invalid booleans;
   - partial records; and
   - unapproved required-field omissions.
4. Encode controls-approved quality/sentinel behavior without treating exact zero
   as invalid by default.
5. Define the final typed JSON frame and measure minimum/nominal/maximum byte size.
6. Prove the frame through `framer.py`, `labview_map.py`, and the relevant cloud
   tests without a network send.

Do not use the legacy text syntax as the production wire contract. It is evidence
input only. Production output is one UTF-8 JSON object plus one LF.

## Gate 3 — LabVIEW telemetry design and review

Work only on a source-controlled offline copy until controls signs the design.

The design must:

- preserve the existing USB logger;
- copy one reviewed snapshot into a depth-one/latest-wins, non-blocking handoff;
- perform JSON serialization and TCP operations only in a lower-priority telemetry
  loop;
- maintain one TCP client to `<WINDOWS10_GATEWAY_IP>:9070`;
- use finite connect/write timeouts and bounded reconnect backoff;
- discard stale unsent frames after disconnect;
- expose local counters for snapshot accepted/rejected, overwrite/drop, serialize
  failure, connect/write failure, reconnect, frames sent, and last-success age;
- avoid unbounded queues, lossless stale replay, dialogs, and operator prompts;
- contain no TCP listener, command reader, network-variable write from the
  gateway, setpoint, output reference, deploy API, or target-control path; and
- leave Cloudflare, the VM, Convene, and gateway port 9080 unreachable from the
  cRIO.

Preferred frame:

```json
{
  "source_id": "reclaim-crio-rt-01",
  "ts": "<per-frame synchronized UTC ISO-8601>",
  "cycle_id": "<stable physical cycle identity>",
  "source_op_state": "<signed sequencer state>",
  "active_chamber": "PL",
  "vars": {
    "PL_surface_temp": 224.119084,
    "MW_RF": false,
    "MW_power": 0.0
  }
}
```

Raw names and units remain at this boundary. The cloud owns reviewed SI
conversion. `active_chamber` must be explicit (`PL`, `MT`, `NONE`), not inferred
from RF or process flags.

### Controls fallback

If the controls owner rejects an RT-side TCP client, publish exactly one
source-built typed JSON/string shared variable and adapt the existing Windows
relay to read that one item. Apply the same snapshot, authority, boundedness, and
no-stale-replay gates. Do not fall back to per-item PSP as production without a
new signed decision record.

### Exit condition

Controls signs:

- the diagram and dependency diff;
- loop priorities and RT headroom;
- watchdog/failure behavior;
- exact build hash;
- test window; and
- rollback package.

## Gate 4 — supervised idle-process deployment

Stop and request action-time approval immediately before any deployment or live
send. Approval must name the exact build hash and window.

The controls engineer—not the agent—performs the deployment:

1. Declare the process safe/idle and capture baseline outputs/interlocks.
2. Verify the gateway listener and scoped firewall without changing them.
3. Deploy only the reviewed build.
4. Prove one frame at gateway `/latest`.
5. Compare the same instant across LabVIEW indicators, the USB record, gateway
   `/latest`, raw gateway variables, and converted/derived VM `sim_` state.
6. Run at least five minutes of shadow telemetry while monitoring cRIO CPU/memory,
   loop timing, watchdogs, USB logging, gateway counters, VM freshness, and
   physical outputs.

Any unexpected output/interlock/control change, logger interruption, stale frame,
timestamp rejection, or unexplained mapping mismatch is an immediate rollback.

## Gate 5 — fault, restart, and production acceptance

Under separate supervised approvals:

- disconnect/reconnect the isolated Ethernet cable;
- restart the gateway;
- stop/restart only the telemetry task if independently controllable;
- prove bounded reconnect and no stale replay;
- prove the USB logger and control loops are unaffected; and
- only after all earlier gates pass, perform the separately approved cRIO boot
  recovery test.

Production remains **NO-GO** until every checklist item in
`CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` is supported by retained evidence and
the named controls owner explicitly approves enablement.

## Required repository deliverables

1. Updated evidence/decision record with proven/inferred/unknown separation.
2. Sanitized record fixtures and negative delimiter/sentinel cases.
3. Parser/framing/mapping tests and results.
4. Signed-map templates populated only with evidence-backed values.
5. LabVIEW block-level design and dependency inventory, without committing VI
   binaries.
6. Exact supervised deployment, observation, stop, and rollback runbook.
7. One-frame, sustained-stream, correlation, fault, and restart evidence template.
8. Updated go/no-go and handoff documents.
9. A focused commit on the assigned branch with `git diff --check` clean and no
   secrets, raw runs, binaries, build products, or unrelated changes.

## Stop conditions

Stop and report the blocker rather than improvising if:

- deployed-source identity or rollback is unproven;
- the controls engineer is absent for a controls-owned decision;
- the snapshot cannot be shown coherent or bounded;
- state/chamber/cycle/time authority is unavailable;
- open-sensor/quality semantics are unresolved for model-required channels;
- the proposed network path can execute in or backpressure a deterministic loop;
- a VI contains unexpected output/write/command dependencies;
- the process cannot be placed in an approved safe/idle state;
- the exact build hash or deployment window changes; or
- any test affects control, interlocks, outputs, watchdogs, or USB logging.

The goal is not merely to make bytes arrive. The goal is an evidence-backed,
authoritative, coherent telemetry shadow stream whose failure cannot affect the
physical process.
