# RECLAIM Predictive Engine — Fault & Autonomous-Lifecycle Memo

**Written:** 2026-08-15 · **Author:** engine review (LJW project) · **Status:**
§4.1 adopted as design of record and **IMPLEMENTED** (2026-08-15). New per-chamber
lifecycle FSM (`reclaim_predictive_engine/lifecycle.py`), `reset_cycle()`, adaptive-Q
anti-windup, charge-mass recharge, and `engine_phase`/`active_heating_s` outputs;
ingest/validation/identity pipeline unchanged. Verified by the continuous-run suite
(`tests/test_lifecycle_continuous.py`) and a full HTTP red-team through a Cloudflare
tunnel (20/20: pipeline contract + power-cut-no-reset + new-cycle-reset). Companion to
`CODE_REVIEW.md`, `docs/RECLAIM_Live_Telemetry_Architecture.md`, and `deployment/`.

**Bottom line.** The predictive engine is sound as a per-cycle estimator but was
never given a *lifecycle*. In continuous operation several of its sub-components
accumulate per-cycle/per-run state that nothing ever resets except restarting the
process. That is why a reboot "fixed" results — the restart was silently doing the
reset the code never does. The goal of this memo is a design that removes the
reboot entirely: a single always-on engine that infers **idle vs. running** from
the telemetry it already receives, resets its own analytics at batch boundaries,
and requires **no operator startup** — while leaving the ingest/validation/identity
pipeline **completely untouched**.

---

## 1. Scope and the integrity boundary

Two layers must be kept strictly separate, and this memo only proposes changes to
the second:

1. **The ingest pipeline (DO NOT TOUCH).** Envelope validation, auth, schema/mode
   enforcement, timestamp freshness, run supersession, monotone-sequence dedup,
   and the v1.1 per-frame ack contract — all in `push_ingest_dual.py`
   (`_validate_frame`, `ingest_line`). This is the contract the gateway depends on
   and the basis of the V&V. Every reconciliation below is **downstream of an
   already-accepted frame**; none alters a single validation or ack rule.

2. **The estimator lifecycle (WHERE THE WORK IS).** Everything that happens after
   a frame is accepted and handed to the chamber engines: UKF stepping, the
   residual/anomaly bank, the performance accumulator, charge-mass bookkeeping,
   the advisor. This layer is missing a notion of "which cycle am I in, and is the
   plant idle or running?"

Holding this boundary is what lets us make the engine autonomous **without**
risking the pipeline's proven behavior.

---

## 2. Architecture as it runs today

The production path is `push_ingest_dual.py`. One `DualPushEngine` owns **two
long-lived `ChamberEngine` instances** (plastics `PL`, metals `MT`), each wrapping
one `PredictiveEngine`. They are constructed once and never rebuilt
(`push_ingest_dual.py:312-314`, `256-266`).

Per accepted frame, under one lock (`ingest_line` → `_step_locked`):

```
accepted frame
  → labview_map.normalize            (real cRIO names/units → canonical vars)
  → prefix split PL_/MT_             (_split)
  → ChamberEngine.step(dt = real elapsed from source timestamps)
       → UKF.predict → UKF.update    (estimator.py; 3-state [T_b, T_w, β])
       → NIS gate / CUSUM drift / seal residual / unexplained-rate  (anomaly.py)
       → periodic forecaster          (forecaster.py)
       → GP discrepancy (DISABLED in prod, use_gp=False)
       → PerformanceAccumulator       (metrics.py)
       → Advisor                      (advisor.py; advisory + model-trust)
  → assemble flat reclaim.state.v1 record
  → TwinStateService  (/state, /manifest, /history[600], /health)
```

The forward model (`plant.py`) is a two-node lumped energy balance
`x = [T_bed, T_wall, β]` with an optional live **charge-mass** balance that lowers
apparent bed heat capacity as the batch decomposes/drains
(`plant.py:66-77, 82-94`).

Key structural fact: **the engine is a continuous integrator with no cycle
concept.** `cycle_id` arrives on every frame and is copied straight into the
output (`push_ingest_dual.py:573`), but nothing keys off a change in it.

---

## 3. The fault, told in full

### 3.1 What actually persists across cycles and runs

The engine is built once and stepped forever, yet these sub-components carry state
that is only meaningful *within one batch* or *within one run* — and none of them
is reset anywhere in the live path except the SealMonitor:

| Component | Persistent state | Reset today? | Consequence in a continuous run | Cite |
|---|---|---|---|---|
| `PerformanceAccumulator` | `energy_j`, `peak_temp`, `elapsed`, `_t0` | `reset()` exists but is **never called** post-construction | `_t0` anchors to the first frame ever seen; `consumed_energy_wh`, `cycle_elapsed_s`, `peak_temp_K` grow across all batches — stakeholder metrics drift upward without bound | `metrics.py:41-58`; built `engine.py:73`, only `update` called `engine.py:186` |
| Charge mass `_mf_mass` | set once from `mf_m0` | **Never recharged** on a new batch | Decays to ~0 during batch 1 (`engine.py:249-258`), so from batch 2 on `charge_mass_kg→0`, `c_bed_eff` reverts to inert capacity, and the endotherm term vanishes → wrong bed dynamics | `plant.py:51`; decay `engine.py:249-258` |
| `CUSUMDetector` | `s_hi`, `s_lo` | `reset()` only in `__init__` | A small persistent bias latches the drift sum; `DRIFT` can stay asserted across cycles that should read clean | `anomaly.py:80-93`; used `engine.py:142,193` |
| Adaptive Q `q_scale` | multiplicative noise scale | never reset; no leak-back | Compounding update saturates at the bound (50) and does not recover after a transient, so the filter permanently distrusts the model | `estimator.py:118-124` |
| UKF `x`, `P` | full filter state | never re-seeded | On a new run (gateway/cRIO reboot) the estimator continues from pre-outage state instead of re-acquiring | `estimator.py:61-62`, run path `push_ingest_dual.py:500-506` |

The **only** lifecycle reset wired into the live path is the SealMonitor,
re-anchored on each `S_Evacuate` entry (`engine.py:151-152`). It is the proof of
concept that boundary-aware resets belong here — it just needs to be generalized
to the rest of the stack.

### 3.2 The run-supersession gap

Run supersession is the "recovers automatically after a Pi reboot" feature. When a
fresh, valid frame arrives with a new `run_id`, `ingest_line` retires the old run's
sequence keys and swaps `active_run_id` (`push_ingest_dual.py:500-506`) — the
**identity** layer recovers correctly. But the **estimator** is not told anything:
UKF state, `q_scale`, charge mass, perf, and CUSUM all bleed across the outage. So
"automatic recovery" restores the sequence contract while carrying stale physics
into the new run.

### 3.3 Why this is exactly the "reboot fixes it" signature

Restarting the service re-instantiates `DualPushEngine`, which reconstructs both
`ChamberEngine`s and therefore zeroes every accumulator above. That is the entire
mechanism: **the reboot was a full-state reset masquerading as a fix.** It is not a
crash, a leak, or a deadlock — memory and identity stores are correctly bounded
(`_MAX_SEQ_KEYS`, `_MAX_RETIRED_RUNS`, the 600-frame history deque). It is
lifecycle state living at process scope instead of cycle/run scope.

### 3.4 Why the test suite never caught it

The simulation service `service.py` is structurally different from production. Its
driver rebuilds the engine **inside** the per-cycle loop
(`service.py:157`, `replay_driver` `service.py:192`), so every simulated cycle gets
a fresh engine and the accumulators always look correct. Production
(`push_ingest_dual.py`) keeps one engine for all cycles. The harness therefore
resets exactly what production never resets, which is why multi-cycle behavior
looked fine in testing and diverged only on a live continuous run. This divergence
is itself a finding: **the thing we validated is not the thing we shipped.**

---

## 4. The target: an autonomous, always-on engine

The desired end state, stated as requirements:

- **R1 — No startup.** The engine runs as one persistent service and is correct
  from the first frame onward. Operators never restart it to get right numbers.
- **R2 — Idle recognition.** When the plant is idle (no active batch / no power),
  the engine knows it, holds per-cycle analytics at their last completed values,
  stops integrating energy, and reports an explicit `IDLE` posture rather than a
  drifting one.
- **R3 — Running recognition.** When a batch begins, the engine detects the new
  cycle, resets per-cycle analytics automatically, and tracks the batch to
  completion.
- **R4 — Continuous health + advisory.** Across idle and running alike it keeps
  producing health/metrics and advisory/command guidance for stakeholders — never
  goes dark, never needs a nudge.
- **R5 — Pipeline untouched.** All of the above sits downstream of the accepted
  frame; the ingest contract and its V&V are unchanged.

The essential insight is that **the engine already receives everything it needs to
be autonomous** — it just doesn't act on it. Each frame carries `cycle_id`,
`run_id`, `source_op_state` (the sequencer's authoritative state: `S_Idle`,
`S_BatchLoad`, `S_Evacuate`, `S_MicrowaveHeating`, `S_CoolDown`, `S_Complete`, …,
from `thread.py:145-149`), `active_chamber`, and power. Autonomy is a matter of
adding a small, explicit lifecycle that consumes those signals — not new sensors,
not operator input.

### 4.1 Design of record — the three-phase autonomous lifecycle (directive 2026-08-15)

**Requirement (adopted).** The predictive engine **shall not require manual
interference for a reset upon each run.** Reset is an event the engine detects for
itself, per chamber, from telemetry it already receives. There is no operator step
anywhere in the reset path.

**Governing principle — the reset authority is *batch identity*, never a power
edge and never `run_id`.** A power edge cannot be the trigger because a mid-run
power cut and a finished batch look identical if you only watch power, yet they are
opposite events. `run_id` cannot be the trigger because a gateway/cRIO reboot is a
*transport* event that can happen mid-batch. The one thing that actually means "a
new batch began" is a change in batch identity, expressed by `cycle_id` and
bracketed physically by a load→unload sequence.

**Three low-power situations that must never be collapsed.** "Power is low" is not
one state:

| Phase | Meaning | Charge present? | Reset on entry? |
|---|---|---|---|
| `IDLE` | Between batches — chamber empty, cold | No | No (already reset) |
| `SUSPENDED` | Power interrupted mid-batch (`S_PowerInterrupted`/`S_Restart`), same `cycle_id` | **Yes** | **Never** — hold & resume |
| `COOLDOWN` | Batch finished, cooling before unload | Yes (until unload) | No |

**Per-chamber phase model.** Each `ChamberEngine` runs its own independent
finite-state machine over `{IDLE, LOADING, ACTIVE, COOLDOWN, SUSPENDED, COMPLETE}`,
driven by the sequencer's authoritative `source_op_state`, `cycle_id`, forward
power, and bed temperature. Because the two chambers time-share one SSMG but each
owns its own engine instance, "one chamber runs a cycle" and "both in short
succession" need no special handling — each chamber detects its own transitions on
its own timeline.

**Batch-present latch.** A per-chamber latch is **set** when a batch loads
(`S_BatchLoad`, or the first qualified `ACTIVE` of a new `cycle_id`) and **cleared
only** on a qualified completion (`S_Complete`/`S_Unload`, or a `cycle_id`
turnover). A power loss never clears it. This latch is what prevents any low-power
event mid-batch from being mistaken for completion.

**Reset rule (precise).** For a chamber, a new cycle — and therefore a
`reset_cycle()` — fires when:

> `cycle_id` differs from the last committed `cycle_id` for that chamber **and** the
> chamber is **not** in a SUSPENDED state, **or** a `S_BatchLoad` is seen while the
> batch-present latch is clear.

Entry into SUSPENDED (`S_PowerInterrupted`/`S_Restart`) **blocks reset
unconditionally** and freezes per-cycle state; on resume the chamber returns to
ACTIVE within the *same* batch and continues accumulating where it left off.

**What `reset_cycle()` clears — and what it never touches.** It re-initializes only
the per-cycle *analytics*: the performance accumulator (`metrics.py`), the CUSUM
drift detector, the adaptive-Q scale (soft reset toward 1.0), and it recharges the
charge-mass `_mf_mass` for the batch. It **does not force-reset the UKF state
(`x`,`P`)**: the bed/wall temperatures are physical, measured, and continuous, so
the filter is left to track them and self-heal via the measurement update. This
resolves the earlier warm-vs-cold question: the estimator is *never* boundary-reset;
only analytics are. A brief power outage therefore introduces no reconvergence
transient.

**Decoupling from `run_id`.** Cycle-metric resets key off the physical batch edge
only. Run supersession continues to be handled entirely by the ingest identity layer
(unchanged); the estimator ignores it for reset purposes.

**Identity-churn guard.** If a power event also resets the cRIO — churning `run_id`
*and* restarting `cycle_id` numbering — a resumed batch could masquerade as new. The
guard is physical: if a chamber returns while still **hot with a batch in progress**
(batch-present latch set, bed well above ambient) and the sequencer reports
`S_Restart`/`S_PowerInterrupted`, treat it as *resume* regardless of identity churn.
The hot-bed/batch-present evidence outranks a suspicious identity change.

**Cycle-duration metrics.** Two are published because they diverge exactly during a
suspension: `cycle_elapsed_s` (wall-clock since batch load, counting *through* an
outage — total batch duration) and `active_heating_s` (accumulated powered time
only, which pauses during SUSPENDED). Energy (`consumed_energy_wh`) needs no special
suspend handling — no power means no joules accrue.

**Published lifecycle signal.** Every frame now carries an explicit
`engine_phase` field (the FSM state) so the Convene `.stp` visualization, dashboards,
and the V&V audit read idle/running/suspended directly instead of inferring it from a
drifting integral.

**Tunable parameters (config, not code).** Power-on threshold, the ACTIVE debounce
dwell, and the op-state category sets (load/active/cooldown/complete/suspend) are
configuration so the behavior can be tuned to the real sequencer without edits.

This subsection is the design of record. The options in §5 remain the menu; the
adopted path is **R-2 as the phase/idle classifier with batch-identity as the reset
authority, plus R-3, R-4, and R-7.**

---

## 5. Reconciliation options

Presented as a menu with trade-offs. They compose; the recommended path is R-1 +
R-2 + R-4 + R-7 first, with R-5/R-6 as follow-ons.

### R-1 — Cycle/run boundary orchestration (core fix)

Add boundary detection in `DualPushEngine._step_locked` (post-accept) that compares
the incoming `cycle_id`/`run_id` to the last seen, and on a change invokes new
`PredictiveEngine.reset_cycle()` / `reset_run()` methods that re-init the per-cycle
accumulators. **Trade-off:** minimal surface, no pipeline change; requires deciding
precisely what each reset clears (§7). This is the smallest change that removes the
reboot dependency.

### R-2 — Explicit idle/active/cooldown phase model

Introduce an engine-internal phase enum (e.g. `IDLE`, `LOADING`, `ACTIVE`,
`COOLDOWN`, `COMPLETE`) inferred from `source_op_state` + forward power. Gate energy
integration and cycle-elapsed to `ACTIVE`/`COOLDOWN`; during `IDLE`, freeze and
publish the **last completed cycle's** metrics plus a clear `engine_phase: IDLE`
field. **Trade-off:** gives stakeholders stable, meaningful numbers at idle instead
of a monotonically climbing integral, and directly satisfies R2/R3. Slightly more
logic; needs an agreed idle-output convention.

### R-3 — Charge-mass recharge on batch start

On a detected new cycle, re-seed `_mf_mass` for the active chamber. Source options:
(a) from batch config (`mf_m0`, current behavior but re-applied per cycle); or
(b) from a per-batch `charge_mass` field if the cRIO/LabVIEW envelope can carry the
actual load. **Trade-off:** (b) is more accurate and is the honest long-term answer
but needs a gateway/schema conversation; (a) is zero-integration-cost and correct
enough for identical batches. Recommend (a) now, design toward (b).

### R-4 — Adaptive-Q anti-windup

Replace the compounding `q_scale` update with a bounded form that leaks back toward
1.0 (or reset `q_scale` on cycle boundary via R-1). **Trade-off:** keeps the filter
self-consistent over long runs without permanent saturation; purely numerical, no
external contract impact. Low risk, high value for long-run fidelity.

### R-5 — UKF numerical hardening (optional)

Move the covariance update to Joseph form for guaranteed symmetry/PD over very long
continuous runs; today's `P − K S Kᵀ` is symmetrized and Cholesky is jitter-guarded
(`estimator.py:22-33, 112-113`), so this is defense-in-depth, not an active bug.
**Trade-off:** marginal robustness for a small compute cost; can defer.

### R-6 — Autonomous safe-state / command semantics (design-ahead)

Today the live path emits **advisory only**; the `Controller`/`HardwareInterlock`
safe-state latch in `control.py` is not wired into `push_ingest_dual.py`. If
autonomous commanding is ever enabled, its latch is another piece of per-run state
needing explicit, well-defined reset authority (operator vs. autonomous), with the
hardware interlock remaining the sole fault authority (`control.py:114-139`).
**Trade-off:** out of scope for the reboot fix, but the lifecycle we build in R-1/R-2
should leave a clean seam for it so we don't retrofit later.

### R-7 — Continuous-run soak test (process reconciliation)

Add a test that drives **several batches through one engine instance with no
rebuild** and asserts that per-cycle metrics reset at each boundary and match the
single-cycle baselines, and that `q_scale`/CUSUM/charge-mass behave across cycles.
This is the test that would have caught the fault; it also permanently closes the
"validated ≠ shipped" gap from §3.4 by testing production's lifecycle, not the
harness's. **Trade-off:** some test-authoring effort; it is the guardrail that keeps
this from regressing.

---

## 6. Recommended sequencing

1. **R-7 first (write the failing test).** Encode the continuous-run expectation so
   the fix is measurable and regression-proof.
2. **R-1 + R-3 + R-4.** Add `reset_cycle()`/`reset_run()`, boundary detection,
   charge-mass recharge, and Q anti-windup. Make R-7 pass.
3. **R-2.** Layer the idle/active phase model and the idle-output convention on top;
   this is what turns "doesn't need a reboot" into "genuinely autonomous."
4. **R-5 / R-6** as follow-ons when warranted.

Throughout, the ingest/validation/identity code is not edited — only engine-internal
lifecycle and the `_step_locked` boundary hook, which runs after acceptance.

---

## 7. Design decisions — resolved in §4.1, plus remaining stakeholder calls

Decisions **taken** and implemented per the §4.1 directive:

1. **Estimator is never boundary-reset (resolves warm/cold).** The UKF tracks the
   measured, continuous bed/wall temperatures across cycle and run boundaries; only
   per-cycle *analytics* reset. No reconvergence transient is introduced.
2. **Reset authority = batch identity, not power edge, not `run_id`.** `cycle_id`
   turnover (guarded by the batch-present latch and the not-SUSPENDED condition) is
   the trigger; a `S_BatchLoad` with a clear latch is the fallback trigger.
3. **Idle presentation = freeze last completed cycle + explicit `engine_phase`.**
   During `IDLE` the last batch's metrics are held (not zeroed, not nulled) and the
   phase is published, so dashboards and the `.stp` view show a stable, labeled state.
4. **Charge-mass source = per-cycle config re-seed (R-3a)** now, with R-3b (a real
   per-batch `charge_mass` envelope field) left as a future gateway negotiation.
5. **Per-chamber boundaries.** PL and MT reset independently on their own
   transitions — direct consequence of each chamber owning its own engine.
6. **Cycle-duration = both.** `cycle_elapsed_s` (wall-clock, through suspends) and
   `active_heating_s` (powered time) are both published.

Remaining **stakeholder calls** (not blocking; defaults chosen are safe):

- **Power-on threshold and ACTIVE debounce dwell.** Defaults are configured
  (see `config.py` lifecycle block); confirm against the real sequencer cadence.
- **Op-state category membership.** The load/active/cooldown/complete/suspend sets
  are configured from the `thread.py` vocabulary; confirm the sequencer emits
  `S_PowerInterrupted`/`S_Restart` on an actual outage (vs. simply dropping frames —
  both are handled, but the mapping should be confirmed against real logs).

---

## 8. V&V implications

- The three-column V&V (LabVIEW ↔ `gw_` ↔ `sim_`) is unaffected by these changes —
  they are downstream of ingest and change only engine-internal analytics, not the
  transported frame identity the audit compares.
- Per-cycle metrics become **reproducible**: the same batch yields the same
  `consumed_energy_wh` / `cycle_elapsed_s` regardless of how many batches preceded
  it in the continuous run. That reproducibility is itself a testable V&V assertion
  (R-7).
- `engine_phase` (R-2) gives the audit and the dashboards an explicit, checkable
  idle/running signal instead of inferring it from a drifting integral.

---

## 9. Summary

The engine's algorithms are not the problem; its **lifecycle** is. It was designed
and validated as a per-cycle estimator, then deployed as a process-lifetime one
without the boundary resets that difference demands, so a reboot became the de-facto
reset. The reconciliations above give the engine an explicit, telemetry-driven
lifecycle — cycle/run boundary resets, idle/active recognition, anti-windup, and a
continuous-run test — so it runs truly autonomously alongside the plant, needs no
startup, and keeps the ingest pipeline and its V&V exactly as they are.
