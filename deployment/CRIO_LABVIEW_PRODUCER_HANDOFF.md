# RECLAIM cRIO -> Gateway Telemetry Producer — LabVIEW Implementation Handoff

**Audience:** the LabVIEW/controls engineer implementing the cRIO-side telemetry
producer.
**Purpose:** give you an exact, buildable specification of the one seam we need — a
lower-priority, outbound-only TCP producer that publishes the existing source record to
the Windows edge gateway as JSON — so you can code precisely what the downstream system
already accepts. Everything here has been validated offline against the real gateway
receiver and cloud ingest; the only unknown left at integration should be the cRIO
itself.

**Status / boundary:** this is the specification you build to, not authorization to
deploy. The change is gated: it goes onto the deployed control application only after
the controls owner signs the source-identity, coherence, authority, RT-safety, and
rollback gates. Build and bench-test it against the conformance tool first (Section 9).

---

## 1. What you are building, in one paragraph

Inside the existing RT application, after the per-record snapshot is assembled (the same
values that already feed `Data Stream.vi`), branch a copy of that snapshot into a small,
lossy, latest-value handoff. A separate, **lower-priority** loop reads the latest
snapshot, serializes it to a single JSON object, appends a line feed, and writes it over
one long-lived TCP connection to the gateway at `192.168.1.1:9070`. That is the whole
job. The telemetry loop must never block, delay, or backpressure control, sequencing,
interlocks, safety, the watchdog, or the existing USB logger. If telemetry can't keep
up or the link drops, it silently discards frames — losing telemetry is always
acceptable; disturbing the process never is.

## 2. Hard boundaries (non-negotiable)

- **Outbound TCP client only.** Open one connection *to* the gateway. Do not open a
  listener, do not read commands back, do not write shared variables to the gateway,
  and hold no output/setpoint/deploy/target-control reference anywhere in this code.
- **Never on the control path.** All socket and serialization work runs in a separate,
  lower-priority loop, decoupled from the deterministic loop by a depth-one lossy
  buffer. No TCP call may sit on the control loop's timing.
- **Preserve the USB logger unchanged.** This is additive; the existing file logging
  behavior must be identical before and after.
- **No invented data.** Every value you send must come from a real source. Where a value
  is missing or flagged invalid, omit it — never substitute a zero or a default.
- **Plaintext by design.** This link is on the isolated OT LAN. Do not add TLS, auth, or
  any return channel; encryption is handled downstream on the gateway's WAN side.

## 3. The wire contract — exactly what one frame looks like

One frame is **one UTF-8 JSON object followed by exactly one line feed (`0x0A`)**. You
emit only the six keys below (the *source frame*). The gateway adds `schema_version`,
`mode`, `run_id`, and `seq` itself — **do not send those.**

```json
{"source_id":"reclaim-crio-rt-01","ts":"2026-08-21T15:42:10.250Z","cycle_id":"BATCH-2026-08-21-004","source_op_state":"S_MicrowaveHeating","active_chamber":"PL","vars":{"PL_surface_temp":224.119084,"PL_chamber_pressure":1047.721528,"PL_bottom1":512.4471,"PL_bottom3":508.9927,"PL_bottom4":517.336,"PL_process":true,"MW_RF":true,"MW_power":3000.0}}
```

### 3.1 The six top-level fields

| Field | Type | Rule |
|---|---|---|
| `source_id` | string | Stable producer identity, e.g. `reclaim-crio-rt-01`. Non-empty. |
| `ts` | string | Per-frame timestamp, ISO-8601 **with a UTC offset** (`…Z` or `+00:00`). Must come from a documented, synchronized clock — see §5. |
| `cycle_id` | string | Restart-safe **physical batch** identity, not a telemetry counter. Non-empty. See §5. |
| `source_op_state` | string | The sequencer's actual state, mapped through the signed table to one of the 14 allowed values in §6. |
| `active_chamber` | string | Explicit physical value: exactly `"PL"`, `"MT"`, or `"NONE"`. Never inferred from RF or process flags. |
| `vars` | object | The measurement channels — flat `name -> value` pairs. Rules in §4. |

### 3.2 Formatting rules the receiver enforces

- **Compact JSON, one line.** No pretty-printing, no embedded newlines inside the
  object. Append a single `0x0A` after the closing brace. Emit LF only, never CRLF.
- **Booleans are JSON `true`/`false`** (lowercase) — *not* the `TRUE`/`FALSE` text the
  USB record uses.
- **Numbers are finite JSON numbers.** No `NaN`, no `Infinity`. If a value is not finite,
  omit that channel.
- **Bytes.** All names and values are ASCII, so a plain byte string is correct on the
  cRIO. The whole line including the LF must be **≤ 8192 bytes**. Real frames measure
  ~200–1319 bytes, so you have wide margin; treat an over-length frame as an error, never
  truncate it.
- **Whole frames only.** One snapshot produces one complete line. Never send a partial
  object.

Our reference implementation of this exact framing is `crio_source_record/frame_builder.py`
in the repo; its byte output is precisely what the gateway accepts. Use it as the
ground truth if any detail here is ambiguous.

## 4. The measurement channels (`vars`)

Send the **raw** channel names and **raw** units. Do **not** convert units on the cRIO —
the cloud adapter converts °C->K and Torr->kPa in exactly one place. Your job is to emit
the raw record faithfully. The full 34-channel set, with types and the unit each is
emitted in, is in Appendix A.

Two rules govern which channels appear:

1. **Omit invalid or withheld channels.** If a channel is flagged bad by the signed
   quality map (§7) or is genuinely unavailable this frame, leave it out of `vars`
   entirely. A present channel is a trusted channel.
2. **Bed thermocouple banks are all-or-nothing.** The plastics bed bank
   (`PL_bottom1..4`) and the metals bed (`MT_bottom`) must each be sent either
   **complete** or **entirely absent** — never partial. Sending three of the four
   plastics bed TCs causes the whole frame to be rejected downstream (see §7).

## 5. Metadata authority — where each envelope value comes from

These are the fields that make the telemetry authoritative, and they are the ones you
need controls to define before final coding. Wire them from the real sequencer/clock;
do not fabricate them.

| Field | Authoritative source you must wire in | Notes |
|---|---|---|
| `ts` | A synchronized clock, per frame | Must be UTC with offset. The cloud rejects a frame whose age is **older than 15 s** or **more than 5 s in the future**, so the cRIO clock must track real UTC within that window. Document the clock source and its offset/drift. |
| `cycle_id` | The physical batch identifier from the sequencer | Must survive a controller restart and identify the *physical* run, not the telemetry session. |
| `source_op_state` | The sequencer's current state -> signed mapping table -> one of the 14 allowed strings (§6) | If your internal state has no mapping yet, that is a signed-map item, not a guess. |
| `active_chamber` | The explicit chamber selection from the sequencer | `PL`, `MT`, or `NONE`. `NONE` is a valid, meaningful value and must never be overridden by inference. |

## 6. Allowed `source_op_state` values

The cloud accepts only these 14 state strings (anything else is rejected as
`state_invalid`). Your signed state-mapping table must land on one of them:

```
S_Idle            S_BatchLoad       S_ChamberSelect   S_Evacuate
S_SealCheck       S_MicrowaveHeating  S_MetalsCast    S_PlasticsCollect
S_CoolDown        S_Unload          S_Complete        S_SafeState
S_PowerInterrupted  S_Restart
```

## 7. Quality and the incomplete-bank rule (one integration decision)

The persistent-high channel `PL_bottom2` (reads ~1383) is **quarantined by default** —
its physical meaning is unproven, and if sent unqualified it corrupts the plastics bed
temperature estimate downstream. More generally, a channel is only ever excluded by the
signed quality map, and the **open-thermocouple trigger must be the NI-9213's own
open-TC status**, not a "value looks like 1383" guess.

Because the bed banks are all-or-nothing (§4.2), when the quality map excludes one bed
TC you must choose, with controls, between two behaviors — both realizable in your code
with no downstream change:

- **Send the bank complete** when every channel is valid, or
- **Drop the whole bed bank** (send none of `PL_bottom1..4`) when any one is invalid.

When you drop the bank, the downstream engine keeps the frame, marks that chamber
`sensor_valid=false`, and metals + microwave telemetry still flow. What you must **never**
do is send a partial bank (e.g. three of four): that rejects the entire frame and loses
MT and MW with it. Which policy to apply, and the exact ranges/sentinels, come from the
signed quality map (§11).

## 8. The socket

| Setting | Value |
|---|---|
| Target | `192.168.1.1` : `9070` (TCP) |
| Role | client — you connect; the gateway only listens and never sends |
| Connections | exactly one, long-lived; do not open a socket per frame |
| Framing | UTF-8 JSON + one `0x0A`; ≤ 8192 bytes per line incl. LF |
| Connect timeout | ~2000 ms, finite |
| Write timeout | < one send period (≈ 500 ms), finite |
| Reconnect | bounded backoff (e.g. 1 s -> 5–10 s cap) |
| Keepalive | enabled |
| Cadence | one frame per source snapshot (~0.38 s observed); driven by `ts`, not a fixed clock |

The gateway serves one connection at a time and drops a silent connection after ~15 s so
a reconnect can be served — so after an ungraceful drop, expect your reconnect to be
accepted only once that timer elapses; size your backoff accordingly. Do not wire an
infinite (`-1`) timeout anywhere; that is what turns a dead peer into a wedged loop.

## 9. LabVIEW architecture (reference sketch)

Two loops share one **size-one RT FIFO** (lossy, overwrite-on-full -> depth-one,
latest-wins, never blocks). Because RT FIFO elements must be fixed-size, the snapshot
carries scalars and enums only — put the operating state as a signed code, the chamber
as an enum, `cycle_id` as a fixed-width id, `ts` as a timestamp — and do the string
mapping and JSON build in the low-priority loop, off the control path.

```text
Shared:  SNAP = RT FIFO "telemetry_snap", size 1, element = fixed-size SnapshotCluster
         (the ~34 numeric/bool channels + op_state code + chamber enum + cycle_id + ts).

Control / sequencer loop  (time-critical — timing unchanged):
    after the existing record is assembled each iteration:
        RT FIFO Write(SNAP, snapshot)          # non-blocking; overwrites the unread value
    # no TCP, no JSON, no wait here

Telemetry loop  (lower priority; its own loop):
    conn    = <not connected>                  # shift register
    backoff = 1000 ms                          # shift register, cap 10000
    loop:
        if conn == <not connected>:
            conn, err = TCP Open Connection("192.168.1.1", 9070, timeout=2000 ms)
            if err:  Wait(backoff); backoff = min(backoff*2, 10000); next
            backoff = 1000
        val, empty = RT FIFO Read(SNAP, timeout=0 ms)      # latest only; empty -> skip
        if empty:  Wait(20 ms); next
        json = build_source_frame(val)         # map state code->string, chamber enum->PL/MT/NONE,
                                               # apply quality map, assemble compact JSON;
                                               # assert byte_length + 1 <= 8192
        n, err = TCP Write(conn, json + LF(0x0A), timeout=500 ms)
        if err:
            TCP Close Connection(conn); conn = <not connected>   # discard frame, NO replay
            Wait(backoff); backoff = min(backoff*2, 10000)
    on stop:  TCP Close Connection(conn)
```

Notes: keep variable-length strings out of the RT FIFO (a single-process shared variable
with buffering off, or a functional global, works too). On any write error, close and
reconnect — never retry the same frame; the gateway buffer and the cloud own recovery.
The base LabVIEW TCP palette does not expose `TCP_NODELAY`, and you do not need it — one
bounded write per frame ending in LF is fine.

## 10. How to self-test before integration (no gateway, no cRIO)

You can validate your output against our exact contract offline. Have your VI (or a
stub) write a handful of frames to a file, one JSON object + LF per line, then run the
conformance checker in the repo:

```
python -m crio_source_record.conformance my_frames.ndjson
python -m crio_source_record.conformance --cloud --refresh-ts my_frames.ndjson
```

The first command checks each frame against exactly what the gateway accepts (byte
bound, UTF-8, JSON shape, `vars`); the second additionally reports the full cloud
disposition (schema, envelope completeness, known state, chamber, bed-bank
completeness). It prints pass/fail with the reason per line and exits non-zero on any
failure, so it drops straight into a test loop. Green here means the gateway will accept
your frames on day one.

## 11. What you need from controls before final coding

These are the signed inputs the producer depends on; the mechanism is built and waiting
for the values:

- The **physical channel -> sensor map** for all 34 record fields (the raw names are
  known; the physical meaning and validity rules are not).
- The **`PL_bottom2` decision** and the **open-thermocouple semantics** (NI-9213 open-TC
  status as the trigger), plus per-channel ranges/sentinels — the quality map.
- The **incomplete-bed-bank policy** (§7): complete-or-drop.
- The **state mapping table** (sequencer state -> one of the 14 §6 values).
- The **`active_chamber`** source, the **`cycle_id`** source, and the **clock/offset**
  backing `ts`.

## 12. Acceptance (how we'll know it's right)

Supervised, gated steps once the code is reviewed: prove one frame at the gateway and
match it to the same-time LabVIEW indicators and the USB record; run ≥5 minutes of
sustained shadow telemetry with no change to cRIO load, loop timing, watchdogs, or USB
logging; then disconnect/reconnect the cable and restart the gateway to show bounded
reconnect, latest-wins, no stale replay, and no control impact. The goal is a telemetry
shadow whose failure cannot touch the process.

---

## Appendix A — the 34 record channels

Send raw names and raw units. Type `num` = finite JSON number, `bool` = JSON
`true`/`false`. "Cloud maps to" is what the downstream adapter does with it (for your
context only — you send the raw name either way). `—` means the field currently has no
downstream target and is preserved but unused.

| # | Channel | Type | Raw unit | Cloud maps to |
|---:|---|---|---|---|
| 1 | PL_surface_temp | num | °C | PL wall/surface temperature |
| 2 | PL_output_pressure | num | Torr | PL downstream pressure |
| 3 | PL_chamber_pressure | num | Torr | PL chamber pressure |
| 4 | PL_top_condenser_temp | num | °C | PL condenser (top) |
| 5 | PL_bottom_condenser_temp | num | °C | PL condenser (bottom) |
| 6 | PL_wall1 | num | °C | — |
| 7 | PL_wall2 | num | °C | — |
| 8 | PL_bottom1 | num | °C | PL bed TC1 |
| 9 | PL_bottom2 | num | °C | PL bed TC2 — **quarantined by default** |
| 10 | PL_bottom3 | num | °C | PL bed TC3 |
| 11 | PL_bottom4 | num | °C | PL bed TC4 |
| 12 | PL_flow_meter | num | (raw) | — |
| 13 | PL_process | bool | — | PL process flag |
| 14 | PL_preprocess | bool | — | PL preprocess flag |
| 15 | MW_reverse_coupler | num | (raw) | — |
| 16 | PL_postprocess | bool | — | PL postprocess flag |
| 17 | PL_chamber_pump | bool | — | PL chamber pump |
| 18 | PL_purge_pump | bool | — | PL purge pump |
| 19 | MT_crucible_temperature | num | °C | — (3rd MT temp, unmapped) |
| 20 | MT_top | num | °C | MT wall temperature |
| 21 | MT_bottom | num | °C | MT bed TC1 |
| 22 | MW_water_state | bool | — | SSMG chiller water state |
| 23 | MW_flow_state | bool | — | SSMG flow state |
| 24 | MW_RF | bool | — | RF on (chamber attribution input) |
| 25 | MW_status | bool | — | SSMG status |
| 26 | MW_power | num | W | forward power (active chamber) |
| 27 | MW_reverse | num | W | reflected power (active chamber) |
| 28 | MW_period | num | (raw) | — |
| 29 | MW_width | num | (raw) | — |
| 30 | MW_freq | num | (raw) | SSMG frequency (global) |
| 31 | MW_water_temp | num | °C | SSMG water temp (global) |
| 32 | MW_flow_rate | num | (raw) | SSMG flow rate (global) |
| 33 | PL_Probe1 | num | (raw) | — |
| 34 | PL_Probe2 | num | (raw) | — |

## Appendix B — one complete example frame

Plastics microwave heating, RF on, `PL_bottom2` quarantined (so it is absent and the
bed bank is dropped under the complete-or-drop policy; MT and MW still flow):

```json
{"source_id":"reclaim-crio-rt-01","ts":"2026-08-21T15:42:10.250Z","cycle_id":"BATCH-2026-08-21-004","source_op_state":"S_MicrowaveHeating","active_chamber":"PL","vars":{"PL_surface_temp":224.119084,"PL_output_pressure":1032.422165,"PL_chamber_pressure":1047.721528,"PL_top_condenser_temp":18.442,"PL_bottom_condenser_temp":17.918,"PL_process":true,"PL_preprocess":false,"PL_postprocess":false,"PL_chamber_pump":true,"PL_purge_pump":false,"MT_top":0.0,"MT_bottom":0.0,"MW_water_state":true,"MW_flow_state":true,"MW_RF":true,"MW_status":true,"MW_power":3000.0,"MW_reverse":42.5,"MW_freq":2450.0,"MW_water_temp":21.3}}
```

*This handoff mirrors the repository specs: `deployment/CRIO_TELEMETRY_SOCKET_SETUP.md`,
`deployment/CRIO_SOURCE_RECORD_SIGNED_MAPS.md`, and the executable reference
`crio_source_record/frame_builder.py` with the `crio_source_record.conformance` checker.*
