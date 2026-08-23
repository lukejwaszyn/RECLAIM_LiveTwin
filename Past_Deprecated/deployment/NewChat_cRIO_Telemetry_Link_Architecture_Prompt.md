# Prompt — cRIO/LabVIEW Telemetry Link Architecture and Integration

You are continuing the RECLAIM Live Twin integration with a narrowly bounded
task: architect and, only after explicit approval, implement the telemetry-only
path from the cRIO/LabVIEW application to the dedicated Windows 10 edge gateway.

Repository branch:

```text
desktop/edge-gateway
```

Read these files before taking action, in order:

1. `deployment/CRIO_TELEMETRY_LINK_HANDOFF.md`
2. `deployment/THREE_ENDPOINT_HANDOFF.md`
3. `deployment/GATEWAY_GO_LIVE.md`
4. `pi_gateway/windows/README.md`
5. `pi_gateway/reclaim_edge/receiver.py`
6. `pi_gateway/reclaim_edge/framer.py`
7. `cloud_engine/labview_map.py`
8. `deployment/CONVENE_GW_MAPPING.md`

## Endpoint identities

- cRIO/LabVIEW telemetry producer: `192.168.1.2/24`.
- Windows 10 edge-gateway laptop: `192.168.1.1/24`, TCP receiver 9070.
- Windows Server 2025 predictive-engine VM: downstream of the edge gateway and
  outside the cRIO implementation scope.
- Convene: downstream visualization and outside the cRIO implementation scope.

Do not use phrases such as “this machine” or “here” when identifying endpoints.
Name the cRIO, Windows 10 edge gateway, Windows Server 2025 VM, or Convene.

## Known state

- The direct cable is up at 1 Gbps and the cRIO replies to ping.
- The edge gateway runs as SYSTEM and listens at `192.168.1.1:9070`.
- Windows Firewall accepts 9070 only from `192.168.1.2` on the Private Ethernet
  interface; port 9080 remains loopback-only.
- A synthetic frame already proved edge gateway -> VM and edge gateway -> desktop
  Convene `gw_` fan-out.
- A later five-minute stream delivered 300/300 frames to the VM; the operator
  confirmed predictive processing and the separate VM `sim_` Convene display.
  Treat every downstream boundary as commissioned for synthetic input.
- No real cRIO frame has reached the gateway.
- The repository does not establish the cRIO model, LabVIEW version, deployed
  startup VI, project source/revision, current data-export seam, or deployment
  authority. Treat all as unknown until inspected.

## Mission

Produce an evidence-backed architecture and implementation plan for extracting a
coherent telemetry snapshot from the deployed LabVIEW application and sending
one UTF-8, LF-terminated JSON object per sample to `192.168.1.1:9070` without
affecting deterministic control, safety interlocks, or actuation.

The preferred design is a bounded RT-safe queue from the acquisition/sequencer
logic to a lower-priority, single-writer TCP client with bounded reconnect
backoff. Do not force that design if discovery finds a safer existing read-only
export such as an NI Network Stream, shared-variable service, OPC UA endpoint, or
controls-owned host process. Compare alternatives using actual evidence.

## First turn — discovery only

Start with a concise plan and read-only discovery. Do not modify or deploy a VI,
change the cRIO IP, start/stop the startup application, change Windows networking
or firewall policy, send test telemetry, or touch VM/Convene components.

Work with the onsite operator to capture:

1. cRIO model, OS/firmware, installed modules/drivers, and current startup app.
2. LabVIEW/RT versions and authoritative project/build/source revision.
3. Exact source of the 27 candidate raw values and the sequencer state, active
   chamber, cycle identity, and source timestamp.
4. Existing RT FIFO/queue/telemetry clusters and any existing network/log export.
5. Loop rates, priorities, CPU/memory headroom, watchdogs, and failure behavior.
6. Current network configuration, listeners/connections, and time synchronization.
7. Backup, deployment, approval, test-window, and rollback procedures.

If source code or deploy authority is absent, stop at a design and evidence-gap
report. Do not reverse-engineer or replace the running control application.

## Wire contract to preserve

Prefer the following input shape; the edge gateway adds schema/mode/run/sequence:

```json
{
  "source_id": "reclaim-crio-01",
  "cycle_id": "<physical-cycle-id>",
  "ts": "<UTC ISO-8601>",
  "source_op_state": "<authoritative-sequencer-state>",
  "active_chamber": "PL",
  "vars": {
    "PL_bottom1": 100.2,
    "PL_process": true,
    "MW_power": 3000.0
  }
}
```

Requirements:

- one complete UTF-8 JSON object plus LF per sample;
- numbers and booleans remain typed, never numeric strings;
- no NaN, Infinity, arrays, nested variable values, logs, or partial frames;
- raw LabVIEW names and units are preserved;
- explicit, evidence-backed `source_op_state`, `active_chamber`, `cycle_id`, and
  source timestamp semantics;
- a measured and reviewed maximum line size;
- cadence below the gateway's 30-second idle timeout and justified for the model;
- one client/writer with no unbounded retry queue or stale replay.

The candidate variable inventory is in the cRIO handoff. It is provisional until
the first real frame is compared with LabVIEW indicators. Do not silently rename,
default, invent, or discard a live field.

## Safety constraints

- Telemetry only; no command, advisory, setpoint, or safe-state return path.
- No networking, serialization, retry, or blocking file I/O in a deterministic
  control loop.
- Telemetry backpressure or failure must never delay or alter physical control.
- Preserve the deployed startup VI, project, network settings, and process logic.
- No cRIO route to the Internet, Cloudflare, the VM, or Convene.
- Do not broaden the 9070 firewall scope or expose gateway port 9080.
- Do not install a second gateway, `gw_` writer, predictive engine, or Convene
  binding as part of the cRIO work.
- Keep cloud-returned `/command` disconnected from all hardware authority.
- Ask for explicit operator approval before every mutation or live send.

## Required deliverables

1. A factual discovery report separating verified state from assumptions.
2. A decision record comparing cRIO TCP producer, existing read-only export plus
   desktop adapter, and offline-only extraction.
3. A LabVIEW block-level design showing queue ownership, loop priority, snapshot
   coherence, serialization, TCP lifetime, reconnect, counters, and shutdown.
4. The exact source-frame schema with names, types, units, ranges, cadence,
   unwired semantics, state/chamber/cycle/time authority, and maximum size.
5. A supervised implementation/deployment/rollback procedure tied to the exact
   project revision and startup build.
6. An acceptance evidence template covering offline fixture, one-frame proof,
   sustained shadow stream, disconnect/reconnect, boot recovery, gateway `/latest`,
   `gw_`/`sim_` correlation, and absence of actuation.
7. Repository updates committed on a `codex/` branch or the explicitly assigned
   integration branch, with no binaries, credentials, build artifacts, or secrets.

Do not declare the cRIO seam live until every acceptance box in
`deployment/CRIO_TELEMETRY_LINK_HANDOFF.md` is supported by retained evidence.
