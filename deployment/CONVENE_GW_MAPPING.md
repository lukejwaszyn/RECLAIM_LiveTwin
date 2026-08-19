# Convene `gw_` Audit Mapping — gateway `/latest` → Convene Variables

> **Stage:** 3 — Contract gates + three-column V&V (reference artifact) ·
> **Status:** LIVING reference. Confirm the 27 raw `vars` names against the first
> real cRIO frame before trusting the mapping (GO_LIVE §9.5).

**Purpose.** Wire the laptop gateway into Convene as its **own machine**, publishing
the `gw_` audit set defined in `convene/RECLAIM_Convene_Live_Binding.md`
("Gateway audit machine"). This is the §6 losslessness audit of the preflight:
LabVIEW indicator ↔ `gw_*` submitted frame ↔ `sim_*` cloud state, three columns
per signal.

**Hard rule.** This machine **never writes a `sim_` variable.** The cloud engine's
publisher is the single writer of the `sim_` set. The `gw_` tap is read-only and
sits outside the delivery path — it can never block, slow, or reorder the durable
queue feeding the cloud.

**Audit source:** the same canonical frame exposed at
`http://127.0.0.1:9080/latest`. After the frame is durably enqueued for VM
delivery, `reclaim_edge.convene` flattens the nine envelope values and scalar raw
channels with `gw_` prefixes and submits them to `/api/machine/publish` using the
desktop machine credential. Port 9080 remains loopback-only.

> **Current backend blocker (2026-08-19):** a heartbeat can update machine
> presence but then returns HTTP 500 because the Convene backend lacks the
> Firestore composite `machineCommands` index over `machineId`, `status`, and
> `createdAt`. This prevents heartbeat-returned `autoVars`, but the current
> gateway does **not** depend on that response: direct `/machine/publish` reached
> authenticated request validation successfully. The missing index still
> degrades the separate connected-machine heartbeat/command plane and should be
> fixed, while `gw_` acceptance is proven from the gateway's Convene counters.

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
staged configuration, per preflight §4.2) **every raw cRIO key is preserved under
its original LabVIEW name**; only envelope aliases are stripped (`framer.py:60-63`).
Normalization to engine names and SI units happens later, in the cloud
(`labview_map.py`) — never here.

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
| `gw_schema_version` | `$.schema_version` | string | `framer.py:85`, from config (`reclaim.telemetry.v1`) |
| `gw_mode` | `$.mode` | string | `framer.py:86`, from config (`live`) |
| `gw_run_id` | `$.run_id` | string | `framer.py:87`. Fresh uuid4 per gateway start unless `run_id` is pinned (`framer.py:36`) |
| `gw_source_id` | `$.source_id` | string | `framer.py:88`. `reclaim-crio-laptop-01` unless the cRIO overrides |
| `gw_cycle_id` | `$.cycle_id` | string | `framer.py:89`. **Empty string** if the cRIO omits it |
| `gw_seq` | `$.seq` | integer | `framer.py:90`. Monotone from 1; resumes past the high-water mark on restart when `run_id` is pinned (M7) |
| `gw_ts` | `$.ts` | string (ISO-8601 UTC) | `framer.py:91`. Source `ts` preferred; the gateway stamps arrival time only if absent |
| `gw_source_op_state` | `$.source_op_state` | string | `framer.py:82`. **null** if the cRIO sends neither `source_op_state` nor `op_state` |
| `gw_active_chamber` | `$.active_chamber` | string | `framer.py:83`. `PL` / `MT` / `NONE`; **null** if absent |

**Pipeline-lag readout (§6):** `gw_seq − sim_seq`, displayed beside
`sim_ingest_age_ms`. `gw_source_op_state` must equal `sim_source_op_state` at every
state transition — that equality is the losslessness proof.

---

## 3. Raw channel variables (27)

All paths are `$.vars.<name>`. The authoritative raw-name list is the docx
concatenated-string export reproduced at `labview_map.py:206-216`; the count
independently matches `CODE_REVIEW.md` M5 ("~27 warnings/frame").

**Units here are RAW LabVIEW units — °C, mbar, W — not the SI units of `sim_`.**
See §4.

### Plastics chamber — temperatures (°C)

| Convene variable | jsonPath | `sim_` counterpart | Conversion |
|---|---|---|---|
| `gw_PL_bottom1` | `$.vars.PL_bottom1` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `gw_PL_bottom2` | `$.vars.PL_bottom2` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `gw_PL_bottom3` | `$.vars.PL_bottom3` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `gw_PL_bottom4` | `$.vars.PL_bottom4` | `sim_PL_T_bed_meas` (bank aggregate) | mean after +273.15 |
| `gw_PL_surface_temp` | `$.vars.PL_surface_temp` | `sim_PL_T_wall_meas` | +273.15 |
| `gw_PL_top_condenser_temp` | `$.vars.PL_top_condenser_temp` | `sim_PL_T_cond_top` | +273.15 |
| `gw_PL_bottom_condenser_temp` | `$.vars.PL_bottom_condenser_temp` | `sim_PL_T_cond_bottom` | +273.15 |

Bed TCs are NI-9213 TC4..TC7 ("Hot Spot 1..4"); `PL_surface_temp` is the AI2
IR pyrometer, mapped to the **wall/outer node**, not the bed (modeling choice
LV-2, `labview_map.py:168`).

### Plastics chamber — pressures (mbar)

| Convene variable | jsonPath | `sim_` counterpart | Conversion |
|---|---|---|---|
| `gw_PL_chamber_pressure` | `$.vars.PL_chamber_pressure` | `sim_PL_P_chamber` | ×0.1 (mbar→kPa) |
| `gw_PL_output_pressure` | `$.vars.PL_output_pressure` | `sim_PL_P_downstream` | ×0.1 |

### Plastics chamber — process flags (boolean)

| Convene variable | jsonPath | `sim_` counterpart |
|---|---|---|
| `gw_PL_process` | `$.vars.PL_process` | `sim_PL_process` |
| `gw_PL_preprocess` | `$.vars.PL_preprocess` | `sim_PL_preprocess` |
| `gw_PL_postprocess` | `$.vars.PL_postprocess` | `sim_PL_postprocess` |
| `gw_PL_chamber_pump` | `$.vars.PL_chamber_pump` | `sim_PL_chamber_pump` |
| `gw_PL_purge_pump` | `$.vars.PL_purge_pump` | `sim_PL_purge_pump` |

Booleans ride through prefixed but otherwise untouched (`labview_map.py:181-183`).

### Metals chamber — temperatures (°C)

| Convene variable | jsonPath | `sim_` counterpart | Conversion |
|---|---|---|---|
| `gw_MT_bottom` | `$.vars.MT_bottom` | `sim_MT_T_bed_meas` | +273.15 |
| `gw_MT_top` | `$.vars.MT_top` | `sim_MT_T_wall_meas` | +273.15 |

Bottom = crucible/bed core, top = chamber wall/head (`labview_map.py:52-53`).

### Shared SSMG — power (W)

| Convene variable | jsonPath | `sim_` counterpart |
|---|---|---|
| `gw_MW_power` | `$.vars.MW_power` | `sim_PL_P_fwd` **or** `sim_MT_P_fwd` — see §4.3 |
| `gw_MW_reverse` | `$.vars.MW_reverse` | `sim_PL_P_refl` **or** `sim_MT_P_refl` |

### Shared SSMG — globals (pass-through)

| Convene variable | jsonPath | Type |
|---|---|---|
| `gw_MW_freq` | `$.vars.MW_freq` | number |
| `gw_MW_width` | `$.vars.MW_width` | number |
| `gw_MW_period` | `$.vars.MW_period` | number |
| `gw_MW_water_temp` | `$.vars.MW_water_temp` | number |
| `gw_MW_flow_rate` | `$.vars.MW_flow_rate` | number |
| `gw_MW_water_state` | `$.vars.MW_water_state` | boolean |
| `gw_MW_flow_state` | `$.vars.MW_flow_state` | boolean |
| `gw_MW_RF` | `$.vars.MW_RF` | boolean |
| `gw_MW_status` | `$.vars.MW_status` | boolean |

These are not chamber-tagged; they ride through to `/state` untouched
(`labview_map.py:55-56, 199`).

---

## 4. Reading the three-column audit view correctly

Four behaviors will otherwise look like faults when the chain is healthy.

### 4.1 `gw_` is raw, `sim_` is SI

The audit view compares **unlike units**. A bed TC at 100.2 °C appears as
`gw_PL_bottom1 = 100.2`, while `/state` publishes one
`sim_PL_T_bed_meas` equal to the mean of the valid four-channel bank after the
°C→K conversion. The current cloud record does **not** publish individual
`sim_PL_T_bed_tc1..4` fields. Compare the converted bank mean, not each raw TC,
and apply the pressure conversion column above before declaring a mismatch.

### 4.2 Exact `0.0` means "unwired", and only `gw_` shows it

`_temp_K` and `_press_kPa` (`labview_map.py:62-88`) treat an exact `0.0` as the
LabVIEW default for an unwired channel (REVIEW FLAG LV-5) and **drop it**. So a
channel reading `gw_MT_top = 0.0` has **no `sim_` counterpart at all** — the
variable is absent downstream, not zero. That absence is correct behavior, not
data loss. In the current stream the condenser and metals TCs read `0.000000`.

### 4.3 `gw_MW_power` is shared and unattributed

There is one SSMG serving both chambers. The cloud attributes its power to the
**active chamber** and zeroes the idle one (`labview_map.py:184-196`):

- `active_chamber == "PL"` → `sim_PL_P_fwd = MW_power`, `sim_MT_P_fwd = 0.0`
- `active_chamber == "MT"` → `sim_MT_P_fwd = MW_power`, `sim_PL_P_fwd = 0.0`
- `active_chamber == "NONE"` or null → **both** are `0.0` (sequencer-authoritative
  idle, `labview_map.py:113-114`)

So `gw_MW_power` will not equal either `sim_*_P_fwd` unless you account for the
attribution. Gate the comparison on `gw_active_chamber`.

### 4.4 Missing channels simply do not appear

`strict_fields: false` preserves whatever the cRIO sends; it never injects a
field the cRIO omitted. A jsonPath for an absent channel returns nothing rather
than a default. If a `gw_` variable stays permanently empty, the channel is
missing from the cRIO stream — check LabVIEW, not the gateway.

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

Derived statically on 2026-08-14 during gateway staging, with the cRIO
disconnected and the cloud endpoint not yet provisioned.

- **Verified:** endpoint shape, envelope keys, jsonPaths, and the null/empty
  behaviors — confirmed against a live `/latest` during the console shakedown
  (returned `{"note": "no frame received yet"}`, as documented).
- **Not yet verified:** the `vars` key set, which no live frame has exercised.
  The 27 names come from the docx export in `labview_map.py:206-216`. Confirm
  them against the first real cRIO frame and correct this table if the stream
  differs — that check is a §6 V&V entry, not an assumption to carry forward.
