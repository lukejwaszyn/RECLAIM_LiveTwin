# RECLAIM cRIO-to-Edge Telemetry Link Architecture Handoff

> **Scope:** produce real, read-only telemetry from the cRIO/LabVIEW application
> and deliver it over the isolated Ethernet seam to the Windows 10 edge gateway.
>
> **Status:** architecture and source-discovery work pending; physical link and
> receiving endpoint are ready, but no real cRIO frame has been observed.
>
> **Branch:** `desktop/edge-gateway`

## 1. Endpoint boundary

The work covered by this handoff stops at the edge-gateway TCP receiver:

```text
cRIO 192.168.1.2 / LabVIEW RT application
  -> producer-initiated plaintext TCP on the isolated cable
  -> Windows 10 edge gateway 192.168.1.1:9070
  -> existing RECLAIM-EdgeGateway processing
```

The cRIO must not connect to Cloudflare, the predictive-engine VM, Convene, or a
command endpoint. The telemetry addition must not acquire control authority or
alter the existing sequencer, microwave, pump, purge, interlock, PLC, or HMI
behavior. Returned gateway/cloud commands remain disconnected from hardware.

## 2. Proven facts

| Item | Proven state |
|---|---|
| Edge-gateway Ethernet | `192.168.1.1/24`, Private profile, no default route |
| cRIO address | Operator-confirmed `192.168.1.2/24`; ping replies received |
| Physical link | Up at 1 Gbps |
| Gateway listener | SYSTEM-owned process on `192.168.1.1:9070` |
| Firewall | Allows inbound TCP 9070 only from `192.168.1.2` on the Ethernet/Private seam |
| Gateway status | Loopback only at `127.0.0.1:9080` |
| Synthetic proof | One labeled frame traversed gateway -> VM and gateway -> desktop Convene |
| Real source proof | None; gateway receive count has not advanced from a cRIO frame |

The actual cRIO model, operating system image, LabVIEW version, deployed startup
VI, project source location, deployment owner, time source, telemetry loop rate,
and existing data-export mechanisms have not been captured in the repository.
Do not assume they exist or are modifiable.

## 3. Preferred architecture

When the LabVIEW project source and safe deployment authority are available, use
a producer-initiated persistent TCP client on the cRIO:

```text
deterministic acquisition/sequencer loop
  -> bounded RT-safe queue containing a telemetry snapshot
  -> lower-priority telemetry/network loop
  -> serialize one UTF-8 JSON object
  -> append LF (0x0A)
  -> persistent TCP connection to 192.168.1.1:9070
  -> reconnect with bounded backoff after disconnect
```

Network connection, JSON formatting, DNS, retries, and blocking writes must never
run in the deterministic control loop. The telemetry queue must be bounded and
must expose a local drop/error counter; telemetry backpressure must not delay or
change physical control. A connection failure is an observability fault, not a
reason to change process commands.

The edge receiver is single-client and supplies no application-level cRIO ACK.
Use a single telemetry writer. Do not add an unbounded cRIO retry queue or replay
old physical samples after reconnect; the edge gateway becomes the durability
boundary after it receives a line.

## 4. Preferred source line

Send one JSON object followed by one LF. A structured object is preferred over
the receiver's legacy flat or `k=v` compatibility formats:

```json
{
  "source_id": "reclaim-crio-01",
  "cycle_id": "<stable physical cycle identity>",
  "ts": "<UTC ISO-8601 source timestamp>",
  "source_op_state": "S_MicrowaveHeating",
  "active_chamber": "PL",
  "vars": {
    "PL_bottom1": 100.2,
    "PL_process": true,
    "MW_power": 3000.0
  }
}
```

The gateway owns `schema_version`, `mode`, `run_id`, and monotone `seq`; the cRIO
must not attempt to control those envelope fields. The cRIO should provide source
time, physical cycle identity, sequencer state, and explicit chamber selection
when those values are authoritative and available.

### Type and framing rules

- Encode real JSON numbers as numbers, booleans as `true`/`false`, and state/ID
  values as strings. Do not encode numeric values as strings.
- Use UTF-8 without a BOM and terminate every complete object with LF.
- Do not send arrays, nested variable objects, NaN, Infinity, binary data, log
  text, partial JSON, or multiple samples on one line.
- Preserve the raw LabVIEW names and raw units. Conversion occurs in
  `cloud_engine/labview_map.py`, not on the cRIO or edge gateway.
- Measure the serialized first frame and select a reviewed maximum line size.
  The current receiver lacks a maximum-frame guard, so the isolated link and
  exact source restriction remain mandatory until both ends enforce a bound.
- Send often enough to stay below the gateway's 30-second idle timeout. The
  final cadence must also be appropriate for estimator dynamics and cRIO load;
  one sample per second is the commissioning baseline, not an assumption about
  the final controls requirement.

## 5. Expected raw variables — provisional

The repository-derived list has not been confirmed against a live cRIO frame:

```text
PL_bottom1
PL_bottom2
PL_bottom3
PL_bottom4
PL_surface_temp
PL_top_condenser_temp
PL_bottom_condenser_temp
PL_chamber_pressure
PL_output_pressure
PL_process
PL_preprocess
PL_postprocess
PL_chamber_pump
PL_purge_pump
MT_bottom
MT_top
MW_power
MW_reverse
MW_freq
MW_width
MW_period
MW_water_temp
MW_flow_rate
MW_water_state
MW_flow_state
MW_RF
MW_status
```

Current mapping assumptions are raw temperatures in degrees Celsius, pressures
in mbar, microwave power in watts, and exact `0.0` on an unwired temperature or
pressure channel meaning missing/unwired. Confirm every name, type, unit, range,
and unwired convention against LabVIEW indicators and controls-team evidence.

## 6. Required discovery before design approval

Capture a non-secret, read-only inventory before changing or redeploying a VI:

1. cRIO model, serial/asset identifier, NI Linux RT or Phar Lap image, firmware,
   installed drivers/modules, and boot/startup application.
2. LabVIEW and Real-Time Module versions plus the exact project/source location,
   commit/revision, build specification, and deployment procedure.
3. Current control-loop rates, priorities, CPU/memory headroom, watchdogs,
   interlocks, and failure behavior.
4. Existing telemetry snapshots, clusters, queues, RT FIFOs, network streams,
   shared/network-published variables, OPC UA, TCP/UDP endpoints, loggers, or
   host applications that already expose the required values.
5. Exact source of `source_op_state`, `active_chamber`, `cycle_id`, and UTC time;
   document whether the cRIO clock is synchronized and how.
6. Current network adapter/IP/default-gateway/DNS configuration and any existing
   listeners or outbound connections. Preserve `192.168.1.2/24` unless the lab
   owner explicitly changes the approved subnet.
7. A controls-owner-approved quiet window, backup/export of the deployed startup
   application, and a tested rollback method.

Record screenshots or exports of the relevant LabVIEW block-diagram seam without
capturing secrets. Do not infer the deployed VI from a similarly named local file.

## 7. Architecture decision tree

### Option A — cRIO TCP producer (preferred)

Use when the authoritative LabVIEW project is available and a supervised deploy
is approved. Reuse a single existing telemetry snapshot if available, queue it to
a lower-priority sender loop, and target `192.168.1.1:9070`.

### Option B — read-only desktop adapter

Use only when the cRIO already exposes the complete telemetry set through a
proven read-only NI Network Stream, shared-variable service, OPC UA endpoint, or
controls-owned host process and modifying the startup VI is riskier. The adapter
must be designed as a separate Windows service and feed the existing gateway
without broadening the cRIO firewall rule or creating a second `gw_` writer.
The current repository does not contain such an adapter.

### Option C — file/log extraction

Acceptable only for offline schema discovery. It is not a live-twin transport and
cannot satisfy freshness, source-time, or loss accounting requirements.

Do not select an option until discovery establishes what the deployed LabVIEW
application already provides.

## 8. Phased implementation and evidence

1. **Offline contract fixture:** produce one representative JSON line from a
   recorded or manually entered snapshot, with no network connection.
2. **Parser proof:** validate the fixture against `framer.py` and
   `labview_map.py`; retain names/types/units and expected conversions.
3. **Bench sender proof:** run the new telemetry loop while the physical process
   is idle and RF/control outputs remain under existing local authority.
4. **One-frame network proof:** connect only to `192.168.1.1:9070`; verify the
   gateway `/latest` identity and raw values against LabVIEW indicators.
5. **Sustained shadow proof:** stream at the approved cadence long enough to
   cross gateway, VM bridge, and Convene heartbeats. Compare `gw_` raw values and
   `sim_` converted/derived state without enabling actuation.
6. **Fault proof:** unplug/reconnect Ethernet and restart only the telemetry loop;
   verify bounded reconnect, no control-loop delay, no stale replay, and clear
   local/gateway loss indicators.
7. **Boot proof:** after all earlier gates pass, reboot the cRIO in an approved
   window and prove the unchanged control startup plus telemetry recovery.

## 9. Acceptance gate

- [ ] Authoritative LabVIEW source/revision and deployed startup VI are identified.
- [ ] Controls owner approves the isolated telemetry-only seam and rollback.
- [ ] No telemetry/network operation executes in the deterministic control loop.
- [ ] Exactly one cRIO telemetry client targets `192.168.1.1:9070`.
- [ ] One complete LF-delimited JSON line has bounded size and correct scalar types.
- [ ] Names, types, units, cadence, zero/unwired semantics, state, chamber, cycle,
      and time source are documented from a real frame.
- [ ] Gateway `/latest` matches the same-time LabVIEW indicators.
- [ ] Sustained `gw_` and VM `sim_` paths correlate by run/source/sequence.
- [ ] Disconnect/reconnect cannot block control or replay stale process data.
- [ ] No cloud/Convene command reaches cRIO, LabVIEW, HMI, PLC, or an actuator.
- [ ] Deployment backup and rollback have been exercised under supervision.

## 10. Rollback

Rollback removes or disables only the telemetry producer/adapter and restores the
captured startup application or build. Do not change process logic, setpoints,
interlocks, firewall scope, edge queue, VM services, Convene bindings, or tunnel
configuration during cRIO rollback. Retain the first real frame, logs, hashes,
deployment revision, and failure evidence.

## 11. Read-next

- `deployment/THREE_ENDPOINT_HANDOFF.md`
- `deployment/GATEWAY_GO_LIVE.md`
- `deployment/CONVENE_GW_MAPPING.md`
- `pi_gateway/windows/README.md`
- `pi_gateway/reclaim_edge/receiver.py`
- `pi_gateway/reclaim_edge/framer.py`
- `cloud_engine/labview_map.py`

