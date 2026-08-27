# Gate 3 — RT Producer Review Checklist (evidence questionnaire)

**Date:** 2026-08-23
**Branch:** `desktop/edge-gateway`
**Status:** OPEN — awaiting VI-level evidence. The producer VI source was not available
to the integration reviewer this session; every item below is answered by the
LabVIEW/controls engineer **with evidence** (block-diagram capture, VI property
screenshot, measurement, or hash), and countersigned by the controls owner. A blank or
"trust me" answer keeps Gate 3 open. Current references:
the root `README.md`, `CRIO_TELEMETRY_SOCKET_SETUP.md`
§4–6 (socket + RT placement), and `CRIO_SOURCE_RECORD_SIGNED_MAPS.md`.

Evidence types: `BD` = block-diagram capture showing the wire, `PROP` = VI/loop property
capture, `MEAS` = measurement with method stated, `HASH` = recorded hash, `DIFF` =
project dependency diff, `TEST` = conformance/bench output.

## 1. Identity and build

| # | Item | Required evidence | Answer / reference | Pass |
|---:|---|---|---|---|
| 1.1 | Exact source revision reviewed (project + VI hashes) | HASH of every VI/ctl in the telemetry addition | | ☐ |
| 1.2 | Exact build hash of the candidate `startup.rtexe` (or build spec output) | HASH + build log | | ☐ |
| 1.3 | The reviewed source is the ONLY delta against the Gate 0 deployed-source baseline | DIFF vs the Gate 0 baseline | | ☐ |
| 1.4 | Dependency diff shows no new drivers/libraries beyond TCP primitives | DIFF (project dependencies before/after) | | ☐ |

## 2. Loop placement and priority (never on the control path)

| # | Item | Required evidence | Answer / reference | Pass |
|---:|---|---|---|---|
| 2.1 | Telemetry runs in its own loop/VI, not inside any deterministic/timed-critical loop | BD | | ☐ |
| 2.2 | Telemetry loop priority is strictly lower than every control/sequencer/safety loop (state the numeric priorities) | PROP | | ☐ |
| 2.3 | The control loop's only telemetry action is one non-blocking write into the depth-one handoff (RT FIFO size 1 / lossy tag, overwrite-on-full) | BD showing the write node and its FIFO config | | ☐ |
| 2.4 | The handoff element is fixed-size (scalars/enums only — op_state as code, chamber as enum, fixed-width cycle_id, timestamp); no strings/variable arrays cross the boundary | BD + ctl definition | | ☐ |
| 2.5 | No serialization, string building, or TCP call exists anywhere in a deterministic loop | BD (whole control loop visible) | | ☐ |
| 2.6 | Control-loop timing measured unchanged with telemetry loop running vs disabled | MEAS (loop period / finished-late counts) | | ☐ |

## 3. Socket behavior

| # | Item | Required evidence | Answer / reference | Pass |
|---:|---|---|---|---|
| 3.1 | Exactly one outbound TCP connection to `<WINDOWS10_GATEWAY_IP>:9070`; opened once, reused; no per-frame open/close | BD | | ☐ |
| 3.2 | TCP Open timeout finite (~2000 ms); TCP Write timeout finite (~500 ms, below one cadence); TCP Close finite; **no `-1` timeout anywhere** | BD showing every timeout terminal | | ☐ |
| 3.3 | On write error: close, mark disconnected, discard the frame — **never retry the same frame** | BD (error case) | | ☐ |
| 3.4 | Reconnect backoff bounded (e.g. 1 s doubling to 5–10 s cap), sized against the gateway's 15 s idle-drop | BD + stated values | | ☐ |
| 3.5 | After a disconnect, all unsent frames are discarded — no on-cRIO queue or replay of history | BD (no buffer between FIFO read and TCP write) | | ☐ |
| 3.6 | Framing: compact JSON, one object, single trailing `0x0A` (LF only, never CRLF); oversize (>8191 B pre-LF) treated as an error, never truncated | BD + TEST (§6) | | ☐ |

## 4. No command / output / return path (structural)

| # | Item | Required evidence | Answer / reference | Pass |
|---:|---|---|---|---|
| 4.1 | No TCP Listen / no read of inbound data on the telemetry connection | BD (no TCP Read node on this connection) | | ☐ |
| 4.2 | No shared-variable write toward the gateway; no network-published variable added | DIFF + BD | | ☐ |
| 4.3 | No output, setpoint, DO/AO, VISA, RF, deploy, or target-control reference anywhere in the telemetry addition (note: the inspected `Data Stream.vi` evidence copy references Mod1 DO / Mod4 AO / VISA — the telemetry addition must share none of those references) | DIFF + BD | | ☐ |
| 4.4 | VI Server TCP and web server remain disabled in the built target | PROP | | ☐ |

## 5. USB logger and platform headroom

| # | Item | Required evidence | Answer / reference | Pass |
|---:|---|---|---|---|
| 5.1 | USB logger path byte-for-byte unchanged: same file naming, same record content, same cadence, before vs after | DIFF + sample file comparison | | ☐ |
| 5.2 | CPU headroom with telemetry running (state idle + worst-case %, method) | MEAS | | ☐ |
| 5.3 | Memory headroom stable over a sustained run (no leak across reconnect cycles) | MEAS | | ☐ |
| 5.4 | Watchdog margin unchanged with telemetry running | MEAS/PROP | | ☐ |
| 5.5 | Behavior at telemetry-loop starvation (CPU contention): control unaffected, frames silently dropped | MEAS or reasoned BD analysis | | ☐ |

## 6. Frame content self-test (run before any live window)

Producer team runs, and attaches output for:

```
python -m crio_source_record.conformance my_frames.ndjson
python -m crio_source_record.conformance --cloud --refresh-ts my_frames.ndjson
```

| # | Item | Required evidence | Answer / reference | Pass |
|---:|---|---|---|---|
| 6.1 | A few hundred captured candidate frames pass the gateway stage (0 fail) | TEST | | ☐ |
| 6.2 | The `--cloud` stage shows 0 `rejected` | TEST | | ☐ |
| 6.3 | **Bed-bank policy is implemented and stated.** Verified live this session: with `PL_bottom2` quarantined and no bank policy, frames PASS the gateway but the cloud rejects **every frame whole** (`telemetry_invalid`, partial PL bank — MT and MW are lost too). The producer must send each bed bank complete or entirely absent. State which policy (complete-or-drop per the signed worksheet) and show a frame under quarantine conditions being accepted | TEST + BD | | ☐ |
| 6.4 | Booleans emit as lowercase `true`/`false` (not the USB record's `TRUE`/`FALSE`); non-finite values omitted, never sent | TEST + BD | | ☐ |
| 6.5 | Only the six top-level keys are emitted (`source_id`, `ts`, `cycle_id`, `source_op_state`, `active_chamber`, `vars`); `schema_version`/`mode`/`run_id`/`seq` are NOT sent | TEST | | ☐ |

## 7. Signed-map dependencies (blocks final coding, Gate 1 items)

Not producer code items, but the producer cannot be finished without them; list state:

| Dependency | Signed? | Reference |
|---|---|---|
| Channel→sensor map (34 rows) | ☐ | `CRIO_SOURCE_RECORD_SIGNED_MAPS.md` §1 |
| Quality profile incl. `PL_bottom2` + NI-9213 open-TC trigger | ☐ | worksheet §1/§3 |
| Incomplete-bed-bank policy choice | ☐ | worksheet §3 |
| Sequencer state → `source_op_state` table (14 values) | ☐ | worksheet §2 |
| `active_chamber`, `cycle_id`, clock/offset sources | ☐ | worksheet §2 |

## 8. Sign-off

Gate 3 closes only when every row above is Pass with evidence attached.

| Role | Name | Date | Signature |
|---|---|---|---|
| LabVIEW/controls developer (evidence provider) | | | |
| Controls owner (countersign) | | | |
| Integration reviewer (RECLAIM) | | | |
