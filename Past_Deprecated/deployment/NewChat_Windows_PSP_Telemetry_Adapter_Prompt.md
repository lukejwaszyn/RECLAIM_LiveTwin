# Prompt — Windows NI-PSP cRIO Telemetry Adapter Implementation

> **Superseded for production source work.** Retain only for diagnostic PSP-adapter
> maintenance. Start new cRIO acquisition work from
> `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`.

You are implementing the RECLAIM Live Twin's input-only Windows adapter for the
existing cRIO Scan Engine / NI-PSP interface.

Read, in order:

1. `deployment/CRIO_PSP_ADAPTER_DEVELOPMENT_PLAN.md`
2. `deployment/CRIO_TELEMETRY_LINK_HANDOFF.md`
3. `deployment/THREE_ENDPOINT_HANDOFF.md`
4. `pi_gateway/reclaim_edge/receiver.py`
5. `pi_gateway/reclaim_edge/framer.py`
6. `cloud_engine/labview_map.py`
7. `deployment/CONVENE_GW_MAPPING.md`

## Fixed endpoint identities

- cRIO and NI-PSP publisher: `192.168.1.2`.
- Windows 10 edge gateway and adapter host: `192.168.1.1`.
- Existing gateway TCP receiver: `192.168.1.1:9070`.
- Windows Server 2025 predictive-engine VM: downstream; it owns normalization
  and predictive processing.
- Convene: downstream visualization only.

## Selected design

Reuse the existing network-published variables from a new input-only Windows
subscriber. Do not modify or deploy the cRIO startup application. Do not reuse
the existing desktop VIs as trusted adapter code: discovery found cRIO analog
and digital output references and RF/serial dependencies in them.

The raw source units are:

- temperature: degrees Celsius;
- pressure: Torr, not mbar;
- power and remaining engineering units: provisional until the channel worksheet
  is approved.

Raw values remain raw through the adapter and gateway. The cloud converts
temperature with `K = degC + 273.15` and pressure with
`kPa = Torr * 0.1333224`. The current mbar conversion is a release blocker.

Do not treat exact zero as unwired without explicit controls evidence. Zero Torr
and zero degrees Celsius can both be valid measurements.

## First turn

Start with read-only discovery and an implementation readiness report. Confirm:

1. the approved channel mapping, units, ranges, and invalid semantics;
2. authoritative sources for state, chamber, cycle ID, and timestamp;
3. the approved adapter technology and its read-only API surface;
4. exact project/source revision, build procedure, deployment owner, test window,
   and rollback;
5. the VM release process for the Torr conversion;
6. the reviewed maximum frame size, cadence, freshness, and snapshot-skew limits.

If any are absent, stop at the evidence-gap report. Do not browse-and-bind unknown
variables, run the discovered VIs, deploy a VI, write a shared variable, start or
stop a cRIO application, connect to port 9070, or change the VM.

## Implementation rules after explicit approval

- Subscribe only to an approved allowlist.
- No write nodes/APIs, output references, deployment calls, target control,
  commands, setpoints, advisory returns, or actuation.
- One adapter instance and one TCP writer.
- Bounded latest-value snapshot storage; no stale replay.
- Finite typed scalars, compact UTF-8 JSON, exactly one LF, and a byte limit.
- Preserve raw names and raw Celsius/Torr values.
- Add unit, type, zero, maximum-size, coherence, disconnect, and restart tests.
- Commit source/docs/tests only. Do not commit LabVIEW binaries, builds, secrets,
  runtime configuration, logs, or captured live telemetry.

Deployment is a separate supervised approval gate after offline implementation
and review pass.
