# ADR-002: Lunar Counterfactual Projection from Live State

**Status:** Proposed (small, additive; implementation may be scheduled any time
after live-pipeline cutover — it touches no ingest/contract code paths)
**Date:** 2026-08-14
**Deciders:** RECLAIM controls lead (LJW), thermal lead
**Depends on:** live pipeline operating (v1.1 contract); ADR-001 independent

## Context

We want to demonstrate, with live data, the operational difference between
terrestrial and lunar-surface processing — above all the cooldown, where the
absence of convection on the surface changes system behavior most.

The engine already contains everything needed: the environment block is the
single point where scenario physics enters (convection scaled by gravity and
ambient pressure; disabled entirely for `lunar_surface`, radiating to a 250 K
sink), and the forecaster already forward-integrates the plant model from the
current filtered state. What does NOT work is feeding live measurements to an
estimator configured with lunar physics: the measurement-update step corrects
the model toward the Earth data every frame, the consistency monitors flag the
deliberate model/plant mismatch as a fault, and the adaptive process noise
works to absorb exactly the difference we want to display.

## Decision (proposed)

Add a **counterfactual projection layer**: at each forecast tick (and always on
entry to `S_CoolDown`), take the live, measurement-grounded state estimate from
the production engine and forward-integrate the SAME plant model twice with no
measurement correction — once under `earth_lab`, once under `lunar_surface`.
Publish both trajectories' scalar summaries in `/state`. Live data in, two
physics futures out; the production estimator is untouched.

## Options Considered

### Option A — Second live-fed estimator with lunar environment
| Dimension | Assessment |
|---|---|
| Complexity | Low (a third ChamberEngine pair) |
| Scientific validity | **Broken** — measurement updates fight the counterfactual physics; output is neither environment |
| Side effects | NIS/CUSUM/advisory channels alarm continuously; adaptive Q masks the contrast |

**Rejected.** An estimator's job is to converge on the data; a counterfactual's
job is to diverge from it. One component cannot do both.

### Option B — Offline replay through lunar physics
Re-run logged cycles through a lunar-configured engine after the fact.

**Pros:** valid for reports; zero live-system risk.
**Cons:** not live; loses the "watch the two futures diverge in real time"
demonstration value. Kept as a complementary analysis path, not the decision.

### Option C — Live-anchored projection sweep (recommended)
| Dimension | Assessment |
|---|---|
| Complexity | Low–Med (second environment in the existing forecast sweep) |
| Scientific validity | Sound: identical hardware state, identical model, only the environment differs — a controlled comparison anchored to measurements every frame |
| Runtime cost | One extra forward integration per chamber per tick (the float sweep already runs at telemetry rate) |
| Live-contract impact | None on ingest; additive `/state` scalars only |

## Physics expectation (what the demo will show)

Heat loss is convection + radiation. At high temperature, radiation (∝ T⁴)
dominates in both environments, so the curves start close. As the chamber
cools, radiation collapses and convection takes over on Earth — but on the
surface there is nothing to take over. The divergence is therefore in the
**tail**: the final few hundred kelvin of lunar cooldown stretch dramatically.
That tail is the operationally meaningful number — it sets cycle cadence and
safe-unload timing for extraterrestrial operation.

## Published additions (flat, additive — no contract break)

| Field (per chamber, PL_/MT_) | Meaning |
|---|---|
| `t_cool_lab_s` | projected time from current state to safe-unload temperature, lab physics |
| `t_cool_lunar_s` | same projection under lunar-surface physics |
| `q_loss_lab_W` / `q_loss_lunar_W` | instantaneous heat-loss rate under each environment at the current state |
| `cool_ratio` | `t_cool_lunar_s / t_cool_lab_s` — the single headline number |

Convene binds these as `sim_PL_t_cool_lunar_s` etc. and charts the two cooldown
curves side by side. Fields are forecast-role values (`_jsonable` null when no
finite projection), never measurements — dashboards must not render them as
sensor data.

## Honest caveats (attach to the demo)

1. The lunar curve is a model projection with no possible measurement
   correction; its credibility rests on the loss-model coefficients. The live
   Earth run continuously exercises the radiation + conduction terms, which is
   the supporting argument.
2. It is a **thermal** counterfactual only. True surface operation also changes
   seal behavior, outgassing, and pressure dynamics; the projection makes no
   claim there.
3. The safe-unload target temperature must be agreed (thermal lead) — the tail
   ratio is sensitive to how low "cool" means.

## Consequences

- Easier: real-time terrestrial-vs-lunar contrast from live data; reuses the
  validated forecaster; strengthens the LunaRecycle narrative with a
  measurement-anchored (not synthetic) comparison.
- Harder: one more projection per tick (bounded, same float path); dashboards
  must label projections clearly to avoid confusing them with estimates.
- Revisit: if ADR-001 lands, η(T, f) must enter this sweep identically
  (same parity obligation flagged there).

## Action Items

1. [ ] Thermal lead: define the safe-unload target temperature per chamber.
2. [ ] Confirm forecaster horizon is long enough for the lunar tail (the lab
   horizon of minutes will NOT cover it — the sweep needs a longer, coarser
   second pass for the lunar case).
3. [ ] Convene: reserve the `sim_*_t_cool_*` bindings and a side-by-side
   cooldown panel in the operator-adjacent (not operator-primary) view.
4. [ ] Schedule implementation after live cutover; cover with a test asserting
   `t_cool_lunar_s > t_cool_lab_s` from an identical hot state and that lunar
   `q_loss` at low ΔT is radiation-only.
