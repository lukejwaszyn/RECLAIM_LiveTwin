# Convene Raw Gateway Mapping — gateway `/latest` → Convene Variables

> **Naming contract changed 2026-08-24:** the active publisher no longer emits
> the `gw_` prefix. Every table entry below should be read with that leading
> prefix removed: `gw_PL_surface_temp` is now `PL_surface_temp`, `gw_MW_power`
> is now `MW_power`, and `gw_seq` is now `seq`. The gateway remains a separate
> Convene machine and still never writes `sim_*`. This note supersedes the old
> prefixed labels retained below for historical V&V traceability.

> **Stage:** 3 — Contract gates + three-column V&V (reference artifact) ·
> **Status:** LIVING reference. Confirm the 27 raw `vars` names against the first
> real cRIO frame before trusting the mapping (GO_LIVE §9.5).

> **Pressure-unit release status (2026-08-19):** repository source, fixtures,
> tests, and this mapping use `kPa = Torr * 0.1333224`. The corresponding VM
> release remains a separate supervised deployment gate.

**Purpose.** Wire the laptop gateway into Convene as its **own machine**, publishing
the raw gateway audit set defined in `convene/RECLAIM_Convene_Live_Binding.md`
("Gateway audit machine"). This is the §6 losslessness audit of the preflight:
LabVIEW indicator ↔ exact-name gateway submitted frame ↔ `sim_*` cloud state, three columns
per signal.

**Hard rule.** This machine **never writes a `sim_` variable.** The cloud engine's
publisher is the single writer of the `sim_` set. The raw gateway tap is read-only and
sits outside the delivery path — it can never block, slow, or reorder the durable
queue feeding the cloud.

**Audit source:** the same canonical frame exposed at
`http://127.0.0.1:9080/latest`. After the frame is durably enqueued for VM
delivery, `reclaim_edge.convene` flattens the nine envelope values and scalar raw
channels under their exact canonical names and submits them to
`/api/machine/publish` using the
MacBook machine credential. Port 9080 remains loopback-only.

The publisher does not blindly add or strip `gw_`: normal engine-input fields
remain unprefixed, and any approved field whose canonical source name already
contains `gw_` retains it. The binding must therefore follow the active source
profile exactly. `sim_` remains forbidden on the MacBook.

> **Current backend blocker (2026-08-19):** a heartbeat can update machine
> presence but then returns HTTP 500 because the Convene backend lacks the
> Firestore composite `machineCommands` index over `machineId`, `status`, and
> `createdAt`. This prevents heartbeat-returned `autoVars`, but the current
> gateway does **not** depend on that response: direct `/machine/publish` reached
> authenticated request validation successfully. The missing index still
> degrades the separate connected-machine heartbeat/command plane and should be
> fixed, while raw gateway acceptance is proven from the gateway's Convene counters.

**Derived from code, not invented.** Every row below traces to
`pi_gateway/reclaim_edge/status.py`, `framer.py`, `main.py`, and
`cloud_engine/labview_map.py`. No field is listed that the code cannot produce.

---

## 1. What `/latest` actually returns

`status.py:39-40` serves `receiver.last_frame` verbatim; `receiver.py:48` sets that
to the framer's output. So `/latest` **is** the canonical wire frame built at
`framer.py:84-95` — nine envelope keys plus a `vars` object:

```json
{
  "schema_version": "reclaim.telemetry.v1",
  "mode": "live",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_id": "reclaim-crio-laptop-01",
  "cycle_id": "2026-08-05T16:20:00Z-pl-01",
  "seq": 1842,
  "ts": "2026-08-05T16:24:03.250Z",
  "source_op_state": "S_MicrowaveHeating",
  "active_chamber": "PL",
  "vars": { "PL_bottom1": 100.2, "MW_power": 3000.0 }
}
```

`vars` content is governed by `framer.py:58-76`. With `strict_fields: false` (the
staged configuration, per preflight §4.2), every adapter-provided key is
preserved; only envelope aliases are stripped (`framer.py:60-63`). The current
evidence-gated PSP profile deliberately provides module/channel audit names,
not unapproved LabVIEW process aliases. Normalization to engine names and SI
units happens later, in the cloud (`labview_map.py`) — never here.

**Before the first frame arrives,** `/latest` returns:

```json
{ "note": "no frame received yet" }
```

(`status.py:40`). Every jsonPath below misses in that state. Collectors must
tolerate it rather than alarm — it is the current state of this laptop with the
cRIO disconnected.

---

## 2. Envelope variables (9)

| Convene variable | jsonPath | Type | Notes / code |
|---|---|---|---|
| `schema_version` | `$.schema_version` | string | `framer.py:85`, from config (`reclaim.telemetry.v1`) |
| `mode` | `$.mode` | string | `framer.py:86`, from config (`live`) |
| `run_id` | `$.run_id` | string | `framer.py:87`. Fresh uuid4 per gateway start unless `run_id` is pinned (`framer.py:36`) |
| `source_id` | `$.source_id` | string | `framer.py:88`. `reclaim-crio-laptop-01` unless the cRIO overrides |
| `cycle_id` | `$.cycle_id` | string | `framer.py:89`. **Empty string** if the cRIO omits it |
| `seq` | `$.seq` | integer | `framer.py:90`. Monotone from 1; resumes past the high-water mark on restart when `run_id` is pinned (M7) |
| `ts` | `$.ts` | string (ISO-8601 UTC) | `framer.py:91`. Source `ts` preferred; the gateway stamps arrival time only if absent |
| `source_op_state` | `$.source_op_state` | string | `framer.py:82`. **null** if the cRIO sends neither `source_op_state` nor `op_state` |
| `active_chamber` | `$.active_chamber` | string | `framer.py:83`. `PL` / `MT` / `NONE`; **null** if absent |

**Pipeline-lag readout (§6):** `seq − sim_seq`, displayed beside
`sim_ingest_age_ms`. `source_op_state` must equal `sim_source_op_state` at every
state transition — that equality is the losslessness proof.

---

## 3. Target raw channel variables (27)

All paths are `$.vars.<name>`. This is the target contract/reference mapping,
not the active PSP POC shape. The raw-name list is the docx concatenated-string
export reproduced at `labview_map.py:206-216`; the count independently matches
`CODE_REVIEW.md` M5 ("~27 warnings/frame"). It becomes live only after an
approved, versioned channel/scaling/quality profile binds physical scan
resources to these process names.

**Units here are RAW LabVIEW units — °C, Torr, and provisionally W — not the SI units of `sim_`.**
See §4.

### Plastics chamber — temperatures (°C)

| Convene variable | jsonPath | `sim_` counterpart | Conversion |
|---|---|---|---|
| `PL_bottom1` | `$.vars.PL_bottom1` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `PL_bottom2` | `$.vars.PL_bottom2` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `PL_bottom3` | `$.vars.PL_bottom3` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `PL_bottom4` | `$.vars.PL_bottom4` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `PL_surface_temp` | `$.vars.PL_surface_temp` | `sim_PL_T_wall_meas` | +273.15 |
| `PL_top_condenser_temp` | `$.vars.PL_top_condenser_temp` | `sim_PL_T_cond_top` | +273.15 |
| `PL_bottom_condenser_temp` | `$.vars.PL_bottom_condenser_temp` | `sim_PL_T_cond_bottom` | +273.15 |

The target worksheet associates the bed bank with NI-9213 TC4..TC7 ("Hot Spot
1..4"); that association is not active in the evidence-gated POC. In the
target model, `PL_surface_temp` is the AI2 IR pyrometer, mapped to the
**wall/outer node**, not the bed (modeling choice LV-2,
`labview_map.py:168`).

### Plastics chamber — pressures (Torr)

| Convene variable | jsonPath | `sim_` counterpart | Conversion |
|---|---|---|---|
| `PL_chamber_pressure` | `$.vars.PL_chamber_pressure` | `sim_PL_P_chamber` | ×0.1333224 (Torr→kPa) |
| `PL_output_pressure` | `$.vars.PL_output_pressure` | `sim_PL_P_downstream` | ×0.1333224 |

### Plastics chamber — process flags (boolean)

| Convene variable | jsonPath | `sim_` counterpart |
|---|---|---|
| `PL_process` | `$.vars.PL_process` | `sim_PL_process` |
| `PL_preprocess` | `$.vars.PL_preprocess` | `sim_PL_preprocess` |
| `PL_postprocess` | `$.vars.PL_postprocess` | `sim_PL_postprocess` |
| `PL_chamber_pump` | `$.vars.PL_chamber_pump` | `sim_PL_chamber_pump` |
| `PL_purge_pump` | `$.vars.PL_purge_pump` | `sim_PL_purge_pump` |

Booleans ride through prefixed but otherwise untouched (`labview_map.py:181-183`).

### Metals chamber — temperatures (°C)

| Convene variable | jsonPath | `sim_` counterpart | Conversion |
|---|---|---|---|
| `MT_bottom` | `$.vars.MT_bottom` | `sim_MT_T_bed_meas` | +273.15 |
| `MT_top` | `$.vars.MT_top` | `sim_MT_T_wall_meas` | +273.15 |

Bottom = crucible/bed core, top = chamber wall/head (`labview_map.py:52-53`).

### Shared SSMG — power (W)

| Convene variable | jsonPath | `sim_` counterpart |
|---|---|---|
| `MW_power` | `$.vars.MW_power` | `sim_PL_P_fwd` **or** `sim_MT_P_fwd` — see §4.3 |
| `MW_reverse` | `$.vars.MW_reverse` | `sim_PL_P_refl` **or** `sim_MT_P_refl` |

### Shared SSMG — globals (pass-through)

| Convene variable | jsonPath | Type |
|---|---|---|
| `MW_freq` | `$.vars.MW_freq` | number |
| `MW_width` | `$.vars.MW_width` | number |
| `MW_period` | `$.vars.MW_period` | number |
| `MW_water_temp` | `$.vars.MW_water_temp` | number |
| `MW_flow_rate` | `$.vars.MW_flow_rate` | number |
| `MW_water_state` | `$.vars.MW_water_state` | boolean |
| `MW_flow_state` | `$.vars.MW_flow_state` | boolean |
| `MW_RF` | `$.vars.MW_RF` | boolean |
| `MW_status` | `$.vars.MW_status` | boolean |

These are not chamber-tagged; they ride through to `/state` untouched
(`labview_map.py:55-56, 199`).

---

## 4. Reading the three-column audit view correctly

Four behaviors will otherwise look like faults when the chain is healthy.

### 4.1 Gateway variables are raw; `sim_` is SI

The audit view compares **unlike units**. A bed TC at 100.2 °C appears as
`PL_bottom1 = 100.2`, while `/state` publishes one
`sim_PL_T_bed_meas` equal to the mean of the valid four-channel bank after the
°C→K conversion. The current cloud record does **not** publish individual
`sim_PL_T_bed_tc1..4` fields. Compare the converted bank mean, not each raw TC,
and apply the pressure conversion column above before declaring a mismatch.

### 4.2 Exact `0.0` remains a measurement

Without an explicit controls-approved validity/status signal, fault sentinel, or
range-and-quality rule, exact zero is preserved. Thus `0 degC` becomes `273.15 K`
and `0 Torr` becomes `0 kPa`. A later approved quality channel may mark a zero
invalid, but neither the adapter nor cloud infers that from the numeric value.

### 4.3 `MW_power` is shared and unattributed

There is one SSMG serving both chambers. The cloud attributes its power to the
**active chamber** and zeroes the idle one (`labview_map.py:184-196`):

- `active_chamber == "PL"` → `sim_PL_P_fwd = MW_power`, `sim_MT_P_fwd = 0.0`
- `active_chamber == "MT"` → `sim_MT_P_fwd = MW_power`, `sim_PL_P_fwd = 0.0`
- `active_chamber == "NONE"` or null → **both** are `0.0` (sequencer-authoritative
  idle, `labview_map.py:113-114`)

So `MW_power` will not equal either `sim_*_P_fwd` unless you account for the
attribution. Gate the comparison on `active_chamber`.

### 4.4 Missing channels do not refresh; retained values are not live

`strict_fields: false` preserves whatever the cRIO sends; it never injects a
field the cRIO omitted. `/latest` and the VM frame therefore contain no value for
an absent channel. The Convene connected-machine store is last-value retained,
however, so a value written by an older commissioning source can remain visible
even though the current source no longer publishes that name. That is exactly
what happened for `MW_width`, `MW_period`, `MW_flow_rate`,
`MW_flow_state`, `MW_status`, the other `MW_*` fields, and
`PL_purge_pump`: they came from the synthetic commissioning shape and are not
present in the current PSP scan stream.

Never refresh these names with fabricated zero/false values. The audit view must
gate them unavailable unless their update carries the current `source_id`,
`run_id`, `seq`, and fresh `ts` from a source profile that actually
contains them. Until the approved PSP/readback mapping supplies those fields,
their retained values are historical, not telemetry.

The evidence-gated PSP profile also withholds every earlier semantic TC alias.
Its current audit values are `scan_Mod2_TC0_degC` through
`scan_Mod2_TC7_degC` and `scan_Mod3_AI0_raw` through
`scan_Mod3_AI2_raw`. They have no `sim_` counterpart and must not enter PL or
MT normalization until the approved profile exists. Any retained
`PL_top_condenser_temp`, `PL_bottom_condenser_temp`, `MT_top`,
`MT_bottom`, or `PL_bottom1..4` value is therefore historical when this
profile is the active source.

---

## 5. Security note

The gateway status server performs **no authentication on any endpoint**
(`status.py:72-86` — there is no token check) and serves raw process telemetry.
It is safe here only because it binds `127.0.0.1` (`status.py:84`) and the
Convene agent is local. If `/latest` is ever exposed through a tunnel, the
**tunnel** must carry authentication (`CODE_REVIEW.md` §Low; preflight §1.2
Cloudflare Access policy). Do not add an inbound firewall rule for 9080.

---

## 6. Status of this mapping

Initially derived statically on 2026-08-14. A real input-only Windows PSP scan
stream was observed on 2026-08-19 and narrows—but does not complete—the mapping.

- **Live transport verified:** the gateway received Mod2 thermocouple and Mod3
  analog scan values. The evidence-gated source shape is eight audit-only
  `scan_Mod2_TC0_degC..TC7_degC` values plus three deliberately unscaled
  `scan_Mod3_AI0_raw..AI2_raw` values. This describes repository source; it is
  not a claim that the revised profile has been deployed.
- **Why semantic aliases are quarantined:** the operator-panel screenshot at
  2026-08-19 22:37:54 EDT and sequence 1984 about 97 seconds later contradicted
  the former `TC2 -> MT_top` and `TC5..TC7 -> PL_bottom2..4` assignments.
  Repeated values near 1379 did not identify a channel and do not establish
  invalid semantics. Offline replay showed the old TC2/TC3 aliases could form a
  false complete MT measurement and drive `CRITICAL`/`SAFE_STATE`, so all eight
  Mod2 semantic aliases are withheld pending the approved profile.
- **Not verified or present:** scaled pressure/surface-temperature fields, every
  `MW_*` field, `PL_purge_pump` and the remaining process flags, authoritative
  state/chamber/cycle identity, source time, ranges, and invalid semantics.
- The 27-name table remains the target worksheet, not a claim about the current
  live frame. None of the eleven audit-only scan values may be treated as a
  canonical PL/MT measurement; Mod2 units are known °C, while Mod3 engineering
  units and scaling remain unapproved.
