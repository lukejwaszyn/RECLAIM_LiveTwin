# RECLAIM cRIO NI-PSP Telemetry Adapter Development and Deployment Plan

> **Stage:** 2-3 — real-source telemetry seam and contract validation
>
> **Status:** HISTORICAL DEVELOPMENT PLAN. The adapter was completed and exercised
> as a partial engineering POC, but this is no longer the selected production
> source. See `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`.
>
> **Branch:** `desktop/edge-gateway`
>
> **Historical architecture:** reuse the existing cRIO Scan Engine / NI-PSP read
> interface from a new input-only Windows adapter. Retain this implementation for
> audit-only diagnostics; do not use this document to authorize production or a
> cRIO redeploy.

The later evidence copy of `Data Stream.vi`, `Preheating Metals.vi`, and the
project has different hashes from §2 and proves an existing repeating USB log
record. The authoritative evidence revision and path forward are recorded in
`CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`.

## 1. Outcome

Build one bounded, read-only Windows telemetry adapter that subscribes to the
existing network-published cRIO values, assembles a reviewed snapshot, and sends
one UTF-8 LF-terminated JSON object per sample to the existing Windows 10 edge
gateway receiver at `192.168.1.1:9070`.

The adapter is a telemetry producer only. It must contain no network-variable
write nodes, cRIO output references, command listener, setpoint path, advisory
return, or actuator authority. The existing gateway remains the only canonical
framer, durable VM queue owner, and desktop `gw_` publisher.

## 2. Evidence captured on the Windows 10 edge gateway

Read-only discovery on 2026-08-19 established:

| Evidence | Observed state |
|---|---|
| Existing connection | LabVIEW process had an established TCP connection from `192.168.1.1` to cRIO `192.168.1.2:2343` |
| Desktop software | 32-bit LabVIEW 2019; NI Variable Engine and NI PSP Service Locator running |
| Open project | `C:\Users\latitude4\Desktop\Read Only\Read Only Sensors.lvproj` |
| Target identity in project | `NI-cRIO9024-016F1385`, address `192.168.1.2`, VxWorks, PowerPC |
| Chassis in project | cRIO-9111 |
| Slot 1 | NI-9474, eight digital outputs, network-published |
| Slot 2 | NI-9213, 16 thermocouple inputs, network-published |
| Slot 3 | NI-9205, 32 analog inputs, network-published |
| Slot 4 | NI-9263, four analog outputs, network-published |
| Project timing metadata | 10 ms Scan Engine period and 100 ms network-variable period; live behavior still requires measurement |
| Source files | `Data Stream.vi` and `Preheating Metals.vi` plus dependencies outside the folder |
| Project SHA-256 | `075958E284513B5CB3F626BCC242850B5482E1B9BAFDB60CC60C0AFAD55383C6` |
| `Data Stream.vi` SHA-256 | `95F499E6970A5751E5EAFEA8CFC8C30B3992D8B7472DA8D61081E040A0AF84CB` |
| `Preheating Metals.vi` SHA-256 | `50FC84BD2CF06EC30044FD2F34BD08A335F79B595017D6E361D5EE6039E4CA41` |

These files are discovery evidence, not authoritative deployed-source evidence.
The project metadata names `/c/ni-rt/startup/startup.rtexe`, but it does not prove
which application is currently deployed or whether its local source matches.

The folder name `Read Only` is not a safety control. Static VI metadata shows
references to NI-9263 analog outputs, NI-9474 digital outputs, `RF Testing.vi`,
and serial/VISA components. Do not run, copy, extend, build, or deploy those VIs
as the telemetry adapter without a separate controls-owner review.

## 3. Architecture decision record

### Selected — new Windows NI-PSP subscriber

```text
cRIO 192.168.1.2
  Scan Engine / existing network-published variables
       |
       | NI-PSP over the existing isolated Ethernet link
       v
Windows 10 edge gateway 192.168.1.1
  new input-only telemetry adapter, one instance
       |
       | compact UTF-8 JSON + LF, one current snapshot at a time
       v
existing RECLAIM-EdgeGateway 192.168.1.1:9070
       |-- durable VM queue -> Windows Server 2025 predictive-engine VM
       `-- nonblocking gw_ audit publisher -> Convene
```

Reasons:

- The Ethernet data-export seam already exists and is actively readable.
- No cRIO startup VI or deterministic control loop needs to change.
- NI-PSP is designed for network-published variables on LabVIEW RT targets.
- Adapter failure is isolated to observability when the adapter has no write API
  and no cRIO output references.

Rejected for this release:

- Adding TCP/JSON/reconnect logic to the undocumented cRIO startup application.
- Electrically duplicating or parallel-tapping physical sensors.
- Reusing the existing desktop VIs without proving that every output-capable
  dependency is absent from the execution path.
- Adding a second gateway, durable queue, `gw_` writer, VM bridge, or Convene
  binding.

## 4. Source and unit contract

The source JSON keeps raw instrument units. The Windows adapter does not convert
engineering units; normalization remains centralized in
`cloud_engine/labview_map.py`.

| Signal class | Raw `gw_` unit | VM `sim_` unit | Required conversion |
|---|---:|---:|---:|
| Temperature | degrees Celsius | kelvin | `K = degC + 273.15` |
| Pressure | Torr | kilopascal | `kPa = Torr * 0.1333224` |
| Microwave power | controls-confirmed raw unit, provisionally W | W | identity only after confirmation |
| Boolean/state | boolean or documented enum | same semantic type | no numeric-string coercion |

[NIST's pressure conversion table](https://www.nist.gov/pml/owm/metric-si/unit-conversion/pressure-and-gas-flow-unit-conversions)
lists 1 Torr as 133.3224 Pa; the implementation uses the reviewed constant
`TORR_TO_KPA = 0.1333224` unless metrology owners require additional precision.

### Blocking correction to current code

The current cloud adapter uses `MBAR_TO_KPA = 0.1`. Applying that factor to Torr
would under-report pressure by approximately 25%. Before any real-source frame is
accepted by the predictive model:

1. Replace the mbar-specific conversion with a Torr-specific conversion.
2. Rename variables, comments, fixture parameters, and assertions that claim mbar.
3. Update the `gw_` mapping so raw pressures are labeled Torr.
4. Update all synthetic fixtures so their physical intent remains unchanged.
5. Deploy the cloud change before enabling the real adapter.

### Zero and unwired semantics

Do not retain the current generic `0.0 -> missing` behavior without evidence.
`0 Torr` can be a valid vacuum measurement, and `0 degC` can be a valid
temperature. Before implementation, the controls/instrumentation owner must
provide one of:

- an explicit validity/status variable per measurement;
- a documented sensor fault/sentinel value;
- an approved range-and-quality rule tied to the exact transmitter/module setup.

Until then, zero is a finite measurement, not an unwired marker. No adapter or
cloud component may silently discard it.

## 5. Required channel-mapping worksheet

The owner must complete this table from same-time LabVIEW indicator observations.
Do not infer labels solely from old VI names.

| Contract field | PSP resource | Raw type | Raw unit | Valid range | Invalid/unwired indication | Update period | Evidence |
|---|---|---|---|---|---|---|---|
| `PL_bottom1` | candidate `Mod2/TC4` | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_bottom2` | candidate `Mod2/TC5` | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_bottom3` | candidate `Mod2/TC6` | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_bottom4` | candidate `Mod2/TC7` | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_surface_temp` | candidate `Mod3/AI2` after existing scale | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_top_condenser_temp` | candidate `Mod2/TC0` | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_bottom_condenser_temp` | candidate `Mod2/TC1` | number | degC | TBD | TBD | measured | screenshot/log |
| `PL_chamber_pressure` | candidate `Mod3/AI0` after existing scale | number | Torr | TBD | TBD | measured | screenshot/log |
| `PL_output_pressure` | candidate `Mod3/AI1` after existing scale | number | Torr | TBD | TBD | measured | screenshot/log |
| `MT_top` | candidate `Mod2/TC2` | number | degC | TBD | TBD | measured | screenshot/log |
| `MT_bottom` | candidate `Mod2/TC3` | number | degC | TBD | TBD | measured | screenshot/log |
| Process/MW fields | TBD; may include readback variables or serial source | scalar | TBD | TBD | TBD | measured | screenshot/log |

The candidate mappings above come from existing repository documentation and
must be confirmed. The mapping must also identify authoritative sources for:

- `source_op_state`;
- `active_chamber` as `PL`, `MT`, or `NONE`;
- stable physical `cycle_id`;
- source timestamp and its clock authority;
- the remaining microwave and process variables.

If those metadata sources do not exist, the initial release may be limited to an
explicitly labeled engineering sensor stream, but it cannot be declared the full
live-twin contract and must not invent values.

## 6. Adapter block-level design

The implementation owner selects either a fresh minimal LabVIEW 2019 Windows VI
or a supported NI client API after a short offline spike. The deployed adapter
must satisfy the same observable contract regardless of implementation language.

### Acquisition

- Open only an approved allowlist of PSP resources.
- Use read/subscription operations only. No generic browse-and-bind at runtime.
- Do not reference Mod1 digital outputs or Mod4 analog outputs unless the
  controls owner explicitly approves an input-only readback needed for metadata.
- Sample at 1 Hz for commissioning; final cadence follows measured update rate,
  coherence, model needs, and Windows/cRIO load.
- Record per-value update age and calculate snapshot skew. Reject a snapshot if
  any required value is stale or the measured skew exceeds the approved bound.
- Hold at most the current and immediately-being-sent snapshots. Latest wins.

### Framing and transport

- Use `source_id: reclaim-crio-psp-01` unless the owner approves another stable ID.
- Generate one complete JSON object using finite JSON numbers, real booleans,
  strings for IDs/state, and one flat `vars` object.
- Encode UTF-8 without BOM, append exactly one LF, and enforce a reviewed maximum
  byte count before write.
- Maintain one persistent client connection to `192.168.1.1:9070`.
- Use bounded reconnect backoff and discard stale unsent snapshots after failure.
- Never buffer an unbounded history or replay old physical samples.

### Diagnostics

Expose locally without creating a network listener:

- subscription connected/disconnected;
- snapshot captured/rejected;
- stale value and maximum skew;
- serialization/type/finiteness failures;
- maximum observed line bytes;
- TCP connect/write failures and reconnects;
- frames sent, local drops, last-success time, and source-data age.

## 7. Development work packages and ownership

### WP0 — controls evidence and freeze

**Owner:** controls/NI owner with onsite operator

- Copy the existing read-only project and dependency inventory to protected
  evidence storage; retain hashes.
- Capture NI MAX target/software/module inventory and actual startup application.
- Complete the channel mapping and source metadata worksheet.
- Record current LabVIEW indicators against raw PSP resource values.
- Confirm that subscribing does not change values, deployment state, or outputs.

**Exit:** signed channel/unit/quality map and explicit authorization to build a
separate Windows subscriber.

### WP1 — adapter spike and offline fixture

**Owner:** Windows/LabVIEW integration developer

- Create a new project; do not modify the discovered `Read Only` or `SSMG Panel`
  projects.
- Prove input-only subscription to recorded/test variables.
- Emit fixtures to a file or in-memory capture only; do not connect to port 9070.
- Demonstrate no output-variable write nodes, property writes, VISA writes,
  deploy calls, or target-control calls in the dependency review.

**Exit:** reviewed source diagram/API inventory, fixture, dependency manifest,
and deterministic evidence that the spike cannot write to the cRIO.

### WP2 — gateway/cloud contract correction

**Owner:** RECLAIM repository developer

- Implement Torr-to-kPa normalization and explicit validity handling.
- Add strict scalar/finiteness checks and a bounded gateway line size.
- Add adapter fixtures and regression tests.
- Update `CONVENE_GW_MAPPING.md`, handoffs, and synthetic commissioning values.
- Preserve raw Celsius/Torr in `gw_`; publish Kelvin/kPa only in `sim_`.

**Exit:** all tests green; peer-reviewed change on the assigned integration
branch; no secrets, LabVIEW binaries, runtime artifacts, or live data committed.

### WP3 — production adapter

**Owner:** Windows/LabVIEW integration developer and Windows gateway owner

- Add bounded snapshot/coherence logic, JSON framing, counters, and TCP reconnect.
- Build a pinned release outside the repository and record source/build hashes.
- Define a dedicated least-privilege startup task. Do not reuse or replace the
  `RECLAIM-EdgeGateway` task.
- Confirm there is exactly one adapter and one TCP writer.

**Exit:** offline and disconnected fault tests pass; deployment package and
rollback package are approved.

### WP4 — supervised deployment

**Owner:** onsite operator, controls owner, gateway owner, VM owner

Every mutation requires an explicit go at the relevant gate:

1. Deploy the reviewed cloud unit-conversion release on the Windows Server 2025
   predictive-engine VM and prove synthetic regression.
2. Stage the adapter on the Windows 10 edge gateway without enabling startup.
3. With the process idle, start the adapter and prove one real frame.
4. Compare same-time LabVIEW indicators, gateway `/latest`, `gw_`, and `sim_`.
5. Run a sustained shadow stream through approved state transitions.
6. Test PSP loss, Ethernet loss, gateway restart, adapter restart, and stale expiry.
7. Only after all previous gates pass, enable adapter startup and run boot recovery.

No cRIO application, network configuration, firewall scope, VM binding, or
Convene identity is changed as part of adapter deployment.

## 8. Test and acceptance matrix

| Gate | Required evidence | Pass condition |
|---|---|---|
| Input-only audit | Source/API dependency review | No write/deploy/control-capable execution path |
| Unit conversion | `0`, `1`, `100`, and `760 Torr` fixtures | `760 Torr -> 101.325024 kPa` within selected precision |
| Temperature | negative, zero, ambient, and upper-range fixtures | `K = degC + 273.15`; zero is retained unless explicit invalid status exists |
| Types | numbers, booleans, strings, NaN/Infinity/container cases | Only contract-approved finite scalars accepted |
| Coherence | per-variable timestamps/update observations | Required fields inside approved skew and freshness bounds |
| Frame bound | minimum/nominal/maximum fixtures | One LF line within reviewed byte limit |
| One-frame proof | retained raw line and `/latest` | Names/types/units match same-time indicators |
| Sustained stream | adapter/gateway/VM counters | No unexplained drops; queue drains; cadence remains stable |
| Correlation | LabVIEW / `gw_` / `sim_` worksheet | Raw °C/Torr and converted K/kPa agree |
| Disconnect | PSP and cable interruption | Control unaffected; bounded reconnect; no stale replay |
| Stop/stale | source halted | VM/Convene transition to not-live; no stale green state |
| Boot recovery | approved Windows restart | One adapter, one gateway, correct listeners, fresh new data |
| No actuation | controls-owner observation and code audit | No output changes or command path |

## 9. Deployment rollback

Rollback is adapter-first and does not touch the cRIO:

1. Stop and disable only the new adapter startup task.
2. Leave `RECLAIM-EdgeGateway`, its durable queue, firewall, and status binding
   unchanged.
3. If required, restore the prior VM release using the VM release rollback while
   the adapter remains stopped.
4. Do not delete queues, evidence, dead letters, logs, or Convene records.
5. Verify the existing LabVIEW read display and physical control continue without
   change.

Retain the adapter release hash, project/source revision, configuration hash,
first real frame, conversion evidence, counters, failure evidence, and rollback
result.

## 10. Deployment authorization gate

Implementation approval does not imply deployment approval. Before the first
live adapter connection, obtain explicit approval for:

- the completed channel/unit/validity map;
- the input-only source/dependency audit;
- the cloud Torr conversion release;
- the exact adapter build hash and configuration;
- the maximum line size, cadence, skew, and stale limits;
- the test window, named operators, and rollback procedure.

The cRIO seam remains **NO-GO for live declaration** until every applicable box
in `CRIO_TELEMETRY_LINK_HANDOFF.md` is supported by retained evidence.
