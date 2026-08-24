# Engine-Side Updates — Owner Handoff

> **For:** the `cloud_engine` owner. **Why this is a document and not a commit:**
> `cloud_engine` is the Windows VM's software and is **not deployed on the gateway**,
> so changes there cannot be validated in their real runtime from here. Everything
> below is a proposal with exact locations and reasoning — **apply, adjust, or
> reject on your own judgement.** Nothing here has been applied.

Ordered by impact. Item 1 is the only one that affects what a demo actually shows.

---

## 1. Rehearsal runs physics matching neither chamber (recommended fix)

**Where:** `cloud_engine/reclaim_predictive_engine/service.py:184`

```python
cfg = EngineConfig(physical=PhysicalParams(), environment=env_name)
```

`chamber_id` defaults to `"PL"` (`config.py:197`) so the service *labels* itself
plastics, but `physical=PhysicalParams()` is the **raw default** — it never calls
`chamber_params(...)`, so none of the CAD-derived geometry is applied:

| param | `PhysicalParams()` (in use) | `chamber_params("PL")` | `chamber_params("MT")` |
|---|---:|---:|---:|
| `c_bed` | 1500 | 4374 | 4815 |
| `c_wall` | 4000 | 2840 | 3804 |
| `area_s` | 0.5 | 0.2917 | 0.4149 |
| `emiss_wall` | 0.35 | 0.35 | 0.85 |
| `t_wall_limit` | **1e9** | **973** | 1e9 |

Two consequences worth caring about:

- The rehearsal demonstrates physics belonging to **no real chamber**.
- `t_wall_limit = 1e9` means **no wall ceiling is enforced**, so
  `thermal_margin_K` (computed as `t_limit - T_bed_est`) is meaningless in every
  rehearsal display. PL's real limit is 973 K — the 304L continuous-service
  ceiling, PL-FR-010.

Note the production path already does this correctly: `push_ingest_dual.py:273-275`
builds each engine with `chamber_params(chamber_id)`.

**Minimal fix — single chamber:**

```python
cfg = EngineConfig(physical=chamber_params("MT"), environment=env_name,
                   chamber_id="MT")          # or "PL"
```

**Fuller option — dual, matching production.** Costs **no extra wall time**: the
chambers are independent engine instances stepping the same simulated clock, so
dual is ~2x CPU per timestep over the same 400/900 s of sim. It also demonstrates
the actual fan-out (`PL_*` + `MT_*`), which is the stronger story if the pitch is
the cloud architecture.

*Selection note:* MT is the chamber with the **least** instrumentation on the
current channel list — no pressure, no pumps, no phase flags — so an MT-only demo
cannot show evacuation or seal-check behavior. This does not affect the rehearsal
itself (the harness synthesizes bed/wall directly and never reads raw channels),
only what the narrative can claim.

---

## 2. `/state` cannot answer "how stale" (optional, affects freshness stories)

**Where:** `TwinStateService` in `service.py`

The rehearsal `/state` exposes `t_sim` and `status` but **no wall-clock timestamp
and no age field**. A consumer can therefore detect "not advancing" only by
comparing successive polls — it can never answer "stale by how long?"

Contrast the bridge contract (`convene_bridge/contract.py:35`), which *requires*
`state_age_ms`, `seq`, and `mode: live`, and rejects anything else with
`MODE_NOT_LIVE`. That is why rehearsal output is not bridge-consumable, and why
rehearsal exercises the engine but **not** the freshness/identity gating.

If you want the `loss-of-data` rehearsal to demonstrate real freshness rather than
just frozen values, add a monotonic `state_age_ms` (or a UTC `generated_at`) to the
published record. Not required for the current demo — `status: stopped` plus a
frozen `t_sim` is already an honest staleness signal.

---

## 3. Batch-boundary edge, only if you go multi-batch continuous (defer)

**Where:** `cloud_engine/reclaim_predictive_engine/lifecycle.py`

Accepted for now: **no change needed** for the planned runs. Each demo run is a
single batch, and the rehearsal driver already rebuilds the engine on every loop
iteration (`_build_engine` sits inside the `while` loop in `driver()`), so charge
mass re-seeds and per-cycle analytics zero automatically with no `cycle_id`.

This only becomes a defect if an engine ever **persists across batches** — the
`push_ingest_dual` live path. Measured, four consecutive batches with `cycle_id=None`
and no reset firing:

| batch | charge_mass | energy_wh | active_heat_s |
|---|---:|---:|---:|
| 1 | 0.9958 | 32.8 | 60 |
| 2 | 0.9915 | 66.1 | 120 |
| 3 | 0.9871 | 99.4 | 180 |
| 4 | 0.9827 | 132.8 | 240 |

Charge mass decays monotonically and never recharges (`reset_cycle()` is what calls
`model.recharge()`), so the mass-flow model eventually believes there is no
feedstock; energy and heating time become lifetime totals and
`energy_efficiency_g_per_wh` trends toward zero.

**If that becomes the operating mode**, the edge to implement is **cold dwell then
reheat** — robust against the case the module's own docstring warns about, since a
power cut does not cool the bed to ambient (a 300 s outage barely dents it) while an
unloaded chamber goes to ambient and stays there. Two constraints:

- It belongs in the **engine**, never the gateway — the gateway's stated invariant
  is that it fabricates no values.
- A derived counter is an ordinal **local to an engine run**: unlike a real ID it
  cannot survive a restart, so mid-batch restarts lose batch continuity unless it
  is persisted. If controls can supply *any* stable identifier, that is worth more
  than a perfect derivation.

Hold this until the VI semantics land — the current channel list is expected to
change.

---

## 4. Already applied, for the record (do not redo)

These `cloud_engine` changes were made earlier in this work and are merged to
`main`. Listed so you know what is already in your tree:

| File | Change |
|---|---|
| `lifecycle.py` | `active_heating_s` now measured from forward power (step 0), not from `op_state`. Closed a 20 s / 19.4 Wh undercount during `S_Restart`, which is a suspend state that carries full power. Verified 600 s counted of 600 s true. |
| `service.py` | Added `mark_stopped()`; a finished driver now reports `status: stopped` instead of advertising `running` over a frozen record. |
| `tests/test_lifecycle_continuous.py` | +8 tests: identity-churn guard (previously **zero** coverage), `S_Restart`/`S_SafeState` holds, and the power-vs-temperature accounting rule. |
| `tests/test_scenario_service_metadata.py` | +1 regression for the stalled-status fix. |
| `windows/start-rehearsal-scenario.ps1` | Retimed to 3–5 min/cycle; added `loss-of-data` profile (8181); bootstraps the locked env on first use; converted to pure ASCII (a BOM-less non-ASCII `.ps1` will not parse under Windows PowerShell 5.1 — and `pwsh` 7 will **not** catch it). |

Suites green at the time of writing: **`pi_gateway` 55 / `cloud_engine` 76 /
`crio_source_record` 70**. If you change `service.py:184` per item 1, re-run
`cloud_engine` and expect the count to hold — no existing test pins the raw
`PhysicalParams()` default.

---

## 5. Related handovers

- **`CONVENE_FIRESTORE_INDEX_HANDOVER.md`** — the Convene backend fix. Blocks
  rehearsal scenarios from appearing in Convene at all (no collectors are delivered
  while the heartbeat 500s). Live raw gateway publishing is unaffected.
- **`CRIO_INTERFACING_TROUBLESHOOTING_HANDOFF.md`** — for the first-frame session
  once the cRIO is connected.

**Standing status: labeled engineering shadow — NO-GO for any production claim.**
No command, return, or actuation path exists or is proposed above.
