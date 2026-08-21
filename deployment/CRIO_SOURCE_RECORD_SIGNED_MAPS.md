# cRIO Source-Record — Signed Maps Worksheet (UNSIGNED)

**Status: UNSIGNED TEMPLATE.** Every "physical channel", "sensor / meaning", "unit",
"range", and "open/invalid semantics" cell below is a controls/NI deliverable. Rows are
pre-filled ONLY with cells that committed evidence supports (record order, the current
adapter's conversion/mapping behavior, and the known map gaps). Nothing here is a
signed channel→sensor assignment. Do not treat a filled cell as controls truth unless a
signature block at the bottom covers it.

Legend for the **Map target** column: the canonical name `labview_map.normalize`
currently produces, or `—` where the record field has **no** adapter target today.

## 1. 34-field record worksheet (authoritative order — PATH_FORWARD §2.3)

| # | Record field | Type | Map target (today) | Unit (raw→SI) | Physical channel | Sensor / meaning | Range | Open/invalid semantics |
|---:|---|---|---|---|---|---|---|---|
| 1 | PL_surface_temp | num | PL_T_wall_meas | degC→K | _____ | IR skin? bed radiating surface? (LV-2) | _____ | _____ |
| 2 | PL_output_pressure | num | PL_P_downstream | Torr→kPa | _____ | _____ | _____ | _____ |
| 3 | PL_chamber_pressure | num | PL_P_chamber | Torr→kPa | _____ | _____ | _____ | _____ |
| 4 | PL_top_condenser_temp | num | PL_T_cond_top | degC→K | _____ | _____ | _____ | _____ |
| 5 | PL_bottom_condenser_temp | num | PL_T_cond_bottom | degC→K | _____ | _____ | _____ | _____ |
| 6 | PL_wall1 | num | **—** | degC→K? | _____ | _____ | _____ | _____ |
| 7 | PL_wall2 | num | **—** | degC→K? | _____ | _____ | _____ | _____ |
| 8 | PL_bottom1 | num | PL_T_bed_tc1 | degC→K | _____ | plastics bed hot-spot 1 | _____ | NI-9213 open-TC status |
| 9 | PL_bottom2 | num | PL_T_bed_tc2 | degC→K | _____ | **QUARANTINED** (persistent ~1383) | _____ | **UNPROVEN — sign before use** |
| 10 | PL_bottom3 | num | PL_T_bed_tc3 | degC→K | _____ | plastics bed hot-spot 3 | _____ | NI-9213 open-TC status |
| 11 | PL_bottom4 | num | PL_T_bed_tc4 | degC→K | _____ | plastics bed hot-spot 4 | _____ | NI-9213 open-TC status |
| 12 | PL_flow_meter | num | **—** | _____ | _____ | _____ | _____ | _____ |
| 13 | PL_process | bool | PL_process (passthrough) | — | _____ | plastics process flag | — | — |
| 14 | PL_preprocess | bool | PL_preprocess | — | _____ | _____ | — | — |
| 15 | MW_reverse_coupler | num | **—** | _____ | _____ | _____ | _____ | _____ |
| 16 | PL_postprocess | bool | PL_postprocess | — | _____ | _____ | — | — |
| 17 | PL_chamber_pump | bool | PL_chamber_pump | — | _____ | _____ | — | — |
| 18 | PL_purge_pump | bool | PL_purge_pump | — | _____ | _____ | — | — |
| 19 | MT_crucible_temperature | num | **—** (3rd MT temp, unmapped) | degC→K? | _____ | metals crucible | _____ | _____ |
| 20 | MT_top | num | MT_T_wall_meas | degC→K | _____ | metals chamber top/head | _____ | NI-9213 open-TC status |
| 21 | MT_bottom | num | MT_T_bed_tc1 | degC→K | _____ | metals bed/core | _____ | NI-9213 open-TC status |
| 22 | MW_water_state | bool | MW_water_state (global) | — | _____ | chiller water state | — | — |
| 23 | MW_flow_state | bool | MW_flow_state (global) | — | _____ | _____ | — | — |
| 24 | MW_RF | bool | (chamber attribution input) | — | _____ | magnetron RF on | — | — |
| 25 | MW_status | bool | MW_status (global) | — | _____ | _____ | — | — |
| 26 | MW_power | num | PL_P_fwd / MT_P_fwd (active) | W→W (LV-1) | _____ | forward SSMG power | _____ | _____ |
| 27 | MW_reverse | num | PL_P_refl / MT_P_refl (active) | W→W (LV-1) | _____ | reflected SSMG power | _____ | _____ |
| 28 | MW_period | num | **—** (global) | _____ | _____ | _____ | _____ | _____ |
| 29 | MW_width | num | **—** (global) | _____ | _____ | _____ | _____ | _____ |
| 30 | MW_freq | num | MW_freq (global) | _____ | _____ | _____ | _____ | _____ |
| 31 | MW_water_temp | num | MW_water_temp (global) | degC→K? | _____ | _____ | _____ | _____ |
| 32 | MW_flow_rate | num | MW_flow_rate (global) | _____ | _____ | _____ | _____ | _____ |
| 33 | PL_Probe1 | num | **—** | _____ | _____ | _____ | _____ | _____ |
| 34 | PL_Probe2 | num | **—** | _____ | _____ | _____ | _____ | _____ |

### Recorded map gaps (evidence-backed, for controls attention)

- **MT has three record temperatures but only two are mapped:** `MT_top`→wall,
  `MT_bottom`→bed; `MT_crucible_temperature` has no adapter target.
- **Unmapped record fields:** `PL_wall1`, `PL_wall2`, `PL_flow_meter`, `PL_Probe1`,
  `PL_Probe2`, `MW_reverse_coupler`, `MW_period`, `MW_width`. The gateway framer
  *preserves* these (logged once as "unknown field preserved"); the cloud adapter does
  not consume them. Controls must decide which become model inputs vs display-only.
- **Unit uncertainty (LV-1):** `MW_power`/`MW_reverse` are assumed watts by the adapter.
- **`MW_water_temp` / `PL_wall*` / `MT_crucible_temperature` units** are assumed degC by
  analogy only; confirm.

## 2. Authority maps to sign (currently absent at source)

| Map | What controls must provide | Current offline placeholder |
|---|---|---|
| State map | Sequencer state → `source_op_state` (signed table) | required arg to `frame_builder`; no default |
| Chamber map | Explicit physical `active_chamber` ∈ {PL, MT, NONE} | required arg; never inferred by the builder |
| Cycle map | Restart-safe physical `cycle_id` source | required arg; no default |
| Time source | Per-frame UTC time + clock offset/drift bound | `frame_builder` requires UTC ISO `ts`; per-frame source TBD |
| Quality profile | Signed ranges + open-TC/overrange sentinels + quarantine set | `QualityProfile(signed_by=…)`; unsigned default quarantines only `PL_bottom2` |

## 3. Incomplete-bed-bank policy — controls decision required

Select one (see `quality_policy.BankPolicy` and the decision record):

- [ ] **REJECT** (current cloud behavior) — one open bed TC rejects the whole frame,
  losing MT + MW.
- [ ] **SUPPRESS_INCOMPLETE** (recommended) — drop the incomplete bed bank; the cloud
  keeps the frame and marks that chamber `sensor_valid=false`; MT + MW survive.
- [ ] Other: ____________________________________________

Open-TC trigger to sign: [ ] NI-9213 open-thermocouple status (ground truth)  [ ] value
sentinel (inference only) — value: __________

## 4. Signatures

| Map / decision | Signer (name) | Role | Date | Evidence reference |
|---|---|---|---|---|
| Channel→sensor rows 1–34 | | controls/NI | | |
| `PL_bottom2` semantics | | controls/NI | | |
| State / chamber / cycle / time authority | | controls/NI | | |
| Quality profile (ranges/sentinels) | | controls/NI | | |
| Incomplete-bank policy | | controls owner | | |
