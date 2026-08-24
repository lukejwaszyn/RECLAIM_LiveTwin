# RECLAIM cRIO Data Acquisition Options Trade Study

**Date:** 2026-08-20

**Target:** NI cRIO-9024, VxWorks/PowerPC, LabVIEW 2019 evidence set

**Purpose:** Select the least-invasive path to coherent, durable, authoritative
telemetry without changing the control application until the existing seams have
been inspected.

**Status:** Decision support updated with the proven USB log seam. The selected
direction and deployment gates are in
`CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md` and
`CRIO_SOURCE_RECORD_DECISION_RECORD.md`.
No RT change or production source is approved by this document.

## 1. Executive decision

Do **not** commit to an RT-application change yet.

Discovery has now proven an existing serialized bundle associated with
`Data Stream.vi`: thirteen retained `*_data_stream.txt` captures contain repeating
named process records, and a block-diagram capture proves initialization beneath
`U:\Data Stream`. The latest captures use one stable 34-field schema at an
approximate 0.38-second period.

What remains unproven is whether the record is a source-latched coherent snapshot,
whether the inspected VI is the deployed-source revision, and where the repeating
record can be branched without affecting control or logging. The evidence now
establishes that:

- `Data Stream.vi` initializes timestamp-named files beneath `U:\Data Stream`;
- retained files contain 30-, 32-, and stable 34-field record generations;
- the latest record includes sensors, MW values, and process flags but no
  per-record timestamp, authoritative state, explicit active chamber, or cycle ID;
- early captures contain missing delimiters and are not strictly parseable;
- the discovered file is not proven to be the authoritative deployed RT source;
- the repeating record writer and its acquisition-loop boundaries still require
  diagram evidence.

The selected direction is to preserve the USB logger and reuse its existing
source-built record through a bounded, lower-priority direct TCP telemetry branch,
subject to source/deploy/rollback authority and RT headroom evidence. Publishing
one JSON/string shared variable is the controls fallback.

## 2. Facts, observations, and unknowns

### Proven or observed in the current repository evidence

| Evidence | What it supports |
|---|---|
| Desktop LabVIEW held a connection to cRIO TCP 2343 with NI Variable Engine/PSP services running | An NI-PSP/shared-variable path existed in the observed desktop configuration |
| The earlier adapter transported eight Mod2 thermocouples and three Mod3 analog values at an observed sustainable three-second cadence | Per-item PSP is technically capable of an engineering POC in at least one observed configuration |
| After desktop LabVIEW was fully closed, TC0 returned an untyped/default zero and opening TC1 failed with NI error `-1967390704` | The path was not shown to be durable or independent of the desktop LabVIEW/publisher state |
| The eleven live names are quarantined as audit-only scan channels | Exact physical aliases, scaling, and validity remain unapproved |
| No authoritative state, active chamber, cycle ID, or cRIO source timestamp was proven | The existing POC cannot validate a full operational twin |
| `Data Stream.vi` exists in a discovered project and has a retained hash | The file can be inspected as evidence; it is not proof of deployed logic |
| Thirteen retained `_data_stream.txt` files contain roughly 23,700 records | A real, repeating named record already exists for logging |
| Latest captures contain 34 fields in one stable order at an approximate 0.38-second period | The record is a strong source seam; cadence remains approximate without per-record time |
| File initialization targets `U:\Data Stream` and writes one start timestamp | The seam is storage logging, not network publication, and lacks per-record source time |
| The current inspected VIs reference output resources, VISA, and RF dependencies | The "Read Only" evidence project must never be run as a telemetry adapter |

### Decisive unknowns

1. What process published the values during the successful PSP POC, and why did
   valid publishing cease when desktop LabVIEW closed?
2. Is the proven record actually one-scan coherent rather than a string assembled
   from independently updated values?
3. Where is its repeating writer and can the record wire be branched through a
   bounded handoff without changing USB logging or control timing?
4. Are authoritative sequencer state, physical chamber selection, stable physical
   cycle identity, quality, and source time available at the same seam?
5. Is the retained project the source of the deployed `startup.rtexe`, with a
   controlled build, maintenance window, backup, and exercised rollback?

## 3. Requirements and scoring basis

The selected seam must be:

1. telemetry-only, with no command, setpoint, output, deploy, or target-control
   path;
2. non-blocking with respect to deterministic acquisition, sequencing, interlocks,
   and safety;
3. coherent enough for the approved estimator cadence, with measured source age
   and snapshot skew;
4. durable without an interactive LabVIEW IDE session;
5. capable of carrying authoritative `source_op_state`, `active_chamber`,
   `cycle_id`, quality/validity, and source time for a validated production twin;
6. bounded and latest-wins, with no stale physical replay;
7. isolated to the cRIO-to-gateway network;
8. compatible with the existing LF-delimited JSON gateway contract where doing so
   does not increase controls risk.

Transport and authority are separate decisions. A coherent sensor bundle without
sequencer metadata is still only an engineering sensor stream. Conversely,
authoritative metadata cannot repair an incoherent or stale acquisition record.

## 4. Decision-relevant transport options

This is the practical menu for the installed system, not a claim that every
LabVIEW communication API ever shipped is useful here.

| ID | Option | RT app change | Coherence potential | Durable potential | Authority potential | Existing gateway reuse | Decision |
|---|---|:---:|:---:|:---:|:---:|:---:|---|
| A1 | Existing USB record assembly as the source seam | none to inspect; change required to publish | high if source-built from one scan | storage only today | low today | none today | **Reuse the record, not the file transport** |
| A2 | Existing per-item NI-PSP subscriber | none | limited until skew is measured | not yet proven | low unless metadata items exist | high | Engineering POC/diagnostic; not rejected outright, not production-approved |
| A3 | Existing bundle plus separately published metadata | none | high for sensors; metadata alignment must be measured | unknown | medium/high | high | Viable only if temporal alignment and publisher independence are proven |
| B1 | Publish one existing cluster/string as one network shared variable | small | high | high if deployed SVE is stable | high if metadata is included | high via desktop relay | Smallest likely RT change |
| B2 | Direct RT TCP producer to `<WINDOWS10_GATEWAY_IP>:9070` | yes | high | high | high | **highest** | Preferred deliberate production change when authorized |
| B3 | NI Network Stream from RT to Windows host | yes | high | high | high | medium; requires host relay | Supported on LabVIEW RT, including published NI measurements on cRIO-9024; manage buffers so stale data is not replayed |
| B4 | UDP push from RT to gateway | yes | high | high for a lossy stream | high | low; gateway needs UDP input | Useful if minimal RT overhead outweighs gateway change |
| B5 | Modbus TCP | yes | high if registers are latched together | high | medium | low; requires register-map translation | Only with an existing site Modbus standard |
| B6 | LabVIEW web service/HTTP pull | yes | high if response is source-snapshotted | medium/high | high | low; gateway poller required | No clear advantage here over TCP push |
| X1 | OPC UA server on this target with LabVIEW 2019 | yes | — | — | — | — | **Not viable as stated:** NI documents current OPC UA Toolkit support for Windows and NI Linux RT, not VxWorks; VxWorks support requires the 2013–2016-era API stack |
| X2 | File/TDMS/FTP retrieval | none/small | high per record | offline only | medium | low | Discovery and correlation only, not live telemetry |
| X3 | Independent duplicate sensors/DAQ | external hardware | variable | high | low | low | Out of scope and adds a second physical truth source |

NI documents Network Streams as supported on Windows and LabVIEW Real-Time, with
the feature installed separately on an RT target, and publishes cRIO-9024
performance measurements. That confirms platform feasibility, not installation on
this particular controller or safety in this application. See [NI Network Streams
architecture and platform support](https://www.ni.com/en/shop/labview/lossless-communication-with-network-streams--components--architecture.html).

NI documents the modern OPC UA Toolkit as Windows/NI Linux RT only and states that
VxWorks use requires LabVIEW RT/DSC 2013–2016. That makes OPC UA incompatible with
the evidenced LabVIEW 2019/VxWorks stack unless the architecture moves the OPC UA
endpoint to Windows or undertakes an unjustified legacy toolchain change. See [NI
OPC UA RT compatibility](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA03q0000019bypCAA&l=en-US%2F1000).

## 5. Option findings

### A1 — existing USB record assembly

The record is now proven as a storage seam and the best source boundary found so
far. It must pass all of these tests before a network branch is designed:

- identify the exact deployed producer and item/endpoint;
- demonstrate that the record is assembled from one acquisition iteration or a
  source-side latched snapshot;
- demonstrate that the authoritative deployed application creates it without an
  interactive LabVIEW IDE session;
- document delimiter/escaping, scalar types, units, quality, invalid sentinels,
  maximum length, cadence, and source age;
- add or prove sequencer state/chamber/cycle/per-frame time at the same snapshot;
- correlate the record to same-time trusted indicators and raw channels.

One string is not automatically coherent. A UI string built sequentially from
front-panel values can still combine different update times. Coherence comes from
the source snapshot, not the serialization format.

### A2 — per-item PSP

The evidence supports a bounded engineering POC, not a categorical transport
failure. Its unresolved weaknesses are publisher dependence, the post-IDE-close
socket/default-value behavior, unapproved aliases, per-item temporal skew, missing
quality semantics, and missing authority metadata. Keep it as a diagnostic and a
fallback engineering stream while investigating why the successful and failed
publisher states differed.

### B1/B2 — likely production choices if an RT change is needed

If the application already creates a suitable bundle but does not publish it, B1
is likely the smallest application change. If a controlled RT change is already
being accepted, B2 avoids the desktop NI relay and preserves the existing gateway
wire contract. In both cases, move data from the acquisition/sequencer context by
a bounded, non-blocking handoff to a lower-priority telemetry loop. Network failure
must drop or replace telemetry, never delay control.

### B3 — Network Streams

Network Streams are a credible NI-native alternative, not merely theoretical on a
cRIO-9024. Their lossless, buffered model conflicts with the project's latest-wins
rule unless endpoint depth, timeout, flush/reconnect behavior, and discard policy
are explicitly bounded. Confirm the feature is installed on the target. The host
would still need to translate the stream to the gateway contract.

## 6. Controls discovery worksheet

Complete this against the **deployed** application. Record screenshots/exports and
revision identifiers; do not infer deployed behavior from a similarly named VI.

### A. Publisher and existing bundle

| Question | Answer/evidence | Decision impact |
|---|---|---|
| What process/VI was running during the successful 11-item PSP stream? |  | Explains whether A2 is durable |
| What changed when desktop LabVIEW closed? |  | Separates cRIO SVE publishing from desktop-hosted publishing |
| Does deployed code create one all-values cluster/string/record? Exact VI and wire? |  | Opens A1/B1 |
| Is it source-latched from one scan? How is that proven? |  | Establishes coherence |
| Is it readable now with IDE/display VIs closed? URL, variable, port, or endpoint? |  | Distinguishes A1 from B1 |
| What are its cadence, maximum size, delimiter/escaping, types, and quality rules? |  | Parser and safety contract |
| Does it include source timestamp, state, chamber, and cycle identity? |  | Determines authority |

### B. Channel and authority map

| Required field | Exact deployed source | Type/unit/enum | Cadence/age | Quality/invalid semantics | Correlation evidence |
|---|---|---|---|---|---|
| `source_op_state` |  |  |  |  |  |
| `active_chamber` (`PL`/`MT`/`NONE`) |  |  |  |  |  |
| `cycle_id` |  |  |  |  |  |
| UTC source time |  |  |  |  |  |
| Mod2/TC0..TC7 |  | degC (to confirm) |  |  |  |
| Mod3/AI0..AI2 |  | raw/Torr/scaled (identify) |  |  |  |
| microwave/process fields |  |  |  |  |  |

Do not promote a channel from `scan_*` to a physical PL/MT/MW alias until this map
is signed. Do not derive `active_chamber` from RF/process flags in production when
the physical selector or sequencer source is available.

### C. Deployed-source and RT-change gate

| Gate | Answer/evidence |
|---|---|
| Exact startup application/build spec/revision matches deployed image |  |
| Complete dependency inventory and licensed LabVIEW 2019 toolchain |  |
| Backup/export and tested rollback |  |
| Named deploy authority and maintenance window |  |
| Loop rates/priorities and CPU/memory headroom |  |
| Watchdogs/interlocks and acceptable telemetry failure behavior |  |
| Network Streams/SVE features installed on target |  |
| cRIO clock source, synchronization, measured offset/drift |  |

### D. Read-only session procedure

1. Preserve the current target and project inventory; hash the evidence copy.
2. Observe current PSP/shared-variable items in NI Distributed System Manager with
   the LabVIEW IDE and display VIs closed.
3. On an offline copy, trace the "concatenated string" indicator upstream and
   determine whether `Data Stream.vi` creates, consumes, or merely displays it.
4. Identify the exact write/read node or TCP endpoint, if any, for the bundle.
5. Capture a short same-time comparison among the bundle, raw scan items, and
   trusted panel indicators while the process is in an approved idle test state.
6. Record state/chamber/cycle/time sources and their alignment to the sensor record.

Do not deploy, edit a VI on-target, change Scan Engine mode, start/stop the startup
application, change networking, or write a shared variable during this read-only
session.

## 7. Decision tree

1. **Existing bundle is readable, source-coherent, publisher-independent, and
   complete:** select A1, build the smallest input-only parser/relay, then run
   correlation and fault acceptance.
2. **Bundle is readable and coherent but metadata is separate:** select A3 only if
   measured timestamps prove acceptable alignment; otherwise add metadata to the
   source bundle under B1/B2.
3. **Bundle exists but is not externally readable:** if RT change authority passes,
   select B1 for the smallest change or B2 if removing the desktop relay is worth
   the additional RT networking code.
4. **No coherent bundle exists and RT change authority passes:** select B2; select
   B3 only if NI-native endpoint management is preferred and bounded stale-data
   behavior is demonstrated.
5. **No coherent bundle and no RT change authority:** retain A2 only as a clearly
   labeled engineering stream if its publisher dependence and skew are acceptable.
   The validated live twin remains NO-GO.

## 8. Acceptance and rollback

No option becomes production merely because bytes arrive. Acceptance requires:

- signed channel/unit/quality/authority map;
- same-time correlation to trusted controls evidence;
- measured cadence, source age, skew, frame bound, and clock offset;
- IDE-independent startup and recovery;
- disconnect/reconnect with no control impact and no stale replay;
- exactly one telemetry writer into the single-client gateway receiver;
- no output/write/deploy/command execution path;
- retained build/config hashes, first frames, counters, and fault evidence;
- an exercised rollback that removes only the telemetry addition.

Until those gates pass, the existing adapter remains an engineering POC and the
full live-twin declaration remains NO-GO.
