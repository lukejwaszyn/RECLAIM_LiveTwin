# ADR-001: Frequency-Steered Impedance Matching for SSMG Heating Optimization

**Status:** Proposed — architecture only. NO implementation is authorized by this
document; nothing in the live-twin codebase changes until this ADR is Accepted.
**Date:** 2026-08-14
**Deciders:** RECLAIM controls lead (LJW), thermal/RF lead, safety engineer
**Scope:** cRIO/LabVIEW control, SSMG drive, predictive engine modeling, telemetry
contract (additive only)

## Context

The SSMG is solid-state, which is the enabling fact: unlike a magnetron, it can
command its output frequency agilely across 2.45 ± 0.05 GHz (2.40–2.50 GHz,
within the ISM allocation). The chamber + charge form a resonant load whose
input impedance — hence reflection coefficient S11(f) and coupled power — varies
strongly with frequency AND with the state of the charge: permittivity and loss
tangent change as plastics pyrolyze and as aluminium approaches/crosses melt.
The optimum drive frequency therefore *drifts through a cycle*.

Today the drive frequency is fixed and matching is mechanical (tuner/coupler).
Preliminary thinking indicates heating can be optimized by steering frequency
to the instantaneous impedance minimum ("impedance steering"): same forward
power, more absorbed power, less reflected power stressing the isolator.

Existing assets this builds on, none of which require rework:

- `MW_freq` already rides in the telemetry stream (`_MW_GLOBALS`); `MW_power` /
  `MW_reverse` give per-frame `eta_obs = (P_fwd − P_refl)/P_fwd` — the engine
  already computes this from the directional coupler.
- The twin's GP discrepancy layer is architected exactly for "physics backbone
  plus learned residual" — an absorption surface η(T, f) is its natural use.
- The v1.1 CommandSignal return path (cloud → gateway `/command` → control hub)
  already carries a structured, latency-tolerant advisory command.
- The advisory/interlock partition (twin advises, cRIO actuates, hardware
  interlock is sole fault authority) is unchanged by this proposal.

Constraints: frequency must stay hard-clamped to 2.40–2.50 GHz in LabVIEW (not
in the model); the isolator, circulator, and launcher must be verified rated
across the full band; the 5 mW/cm² @ 5 in leakage requirement is enforced by
the existing interlock chain and is frequency-independent; the mechanical tuner
and a frequency loop must never optimize against each other.

## Decision (proposed)

Adopt a **two-tier steering architecture**: a fast, model-free
reflection-minimizing frequency loop in the cRIO (authoritative, self-
sufficient), plus a slow, twin-informed feedforward layer that learns the
per-chamber absorption surface η(T, f) and recommends the starting/center
frequency through the existing CommandSignal — advisory only, delivered
through the channel that already exists.

## Options Considered

### Option A — Status quo: fixed frequency, mechanical tuner only
| Dimension | Assessment |
|---|---|
| Complexity | None |
| Heating benefit | None; optimum drifts away mid-cycle |
| Risk | None new |

**Pros:** proven; nothing to verify.
**Cons:** leaves SSMG's defining capability unused; reflected power is wasted
heat in the isolator; tuner alone is slow and coarse against melt transitions.

### Option B — Local extremum-seeking only (cRIO inner loop)
Dither f by a few MHz, measure P_refl, step toward the minimum (classic
extremum-seeking / hill-climb on S11). Entirely in LabVIEW RT, ms–s timescale.

| Dimension | Assessment |
|---|---|
| Complexity | Low–Med (one control loop, one clamp, tuner coordination rule) |
| Heating benefit | Captures most of the gain; tracks drift automatically |
| Cloud dependency | None — correct for a control loop |
| Risk | Local minima in multi-mode cavities; dither transients in telemetry |

**Pros:** self-contained, fail-safe (falls back to fixed f), no new
infrastructure.
**Cons:** greedy — can sit in a local S11 minimum when a better mode exists;
learns nothing across cycles; no diagnostic leverage.

### Option C — Two-tier: Option B + twin-learned η(T, f) feedforward (recommended)
The engine fits the absorption surface per chamber from sweep telemetry
(GP over (T_bed_est, f) with η_obs as target — the existing gp.py pattern).
The twin recommends f₀ for the current thermal state via a new advisory field
in the ControlCommand; the cRIO loop fine-tunes around it locally.

| Dimension | Assessment |
|---|---|
| Complexity | Med (modeling additive; control unchanged from B) |
| Heating benefit | B's gain + escapes local minima + right frequency at phase transitions |
| Cloud dependency | Advisory only; loss of link degrades to Option B exactly |
| Risk | Same as B, plus surface-fit trust management (already have model_trust) |

**Pros:** turns frequency response into an *observable*: the shape of S11(f) is
a fingerprint of load state (mass remaining, melt fraction, arc/foreign-object
anomalies) — feeding the mass-flow estimate and a new anomaly channel for free.
**Cons:** needs a characterization campaign before the surface is trustworthy.

## Trade-off Analysis

The decisive point is loop placement. Frequency matching is a fast control
problem coupled to plant safety-adjacent hardware (isolator thermal load); it
belongs in the cRIO, full stop — the cloud round-trip (Wi-Fi + tunnel + engine)
is architecturally forbidden from being in that loop. What the cloud is good at
is *memory and shape*: cross-cycle learning of where the optimum lives as a
function of thermal state, per chamber. Option C assigns each tier what it is
structurally suited for and degrades exactly to Option B on any cloud/link
failure — the same graceful-degradation posture as the rest of the twin.

Tuner coordination rule (applies to B and C): the mechanical tuner is the slow,
coarse authority set per phase; the frequency loop is fast and fine. The tuner
must be frozen while the frequency loop is active (or moved only between
cycles/phases), so the two matchers never chase each other.

## Telemetry & Contract Impact (additive only — no schema break)

All additions are new flat scalars; `reclaim.telemetry.v1` and
`reclaim.state.v1` tolerate additive vars, `strict_fields: false` preserves
them, and `labview_map` passes unknown `MW_*` through `_MW_GLOBALS` untouched.

| Addition | Where | Purpose |
|---|---|---|
| `MW_freq_setpoint` | telemetry vars | commanded f (actual `MW_freq` already streams) |
| `MW_sweep_active` (bool) | telemetry vars | marks dither/sweep frames so the UKF/residuals can exclude or specially model them — sweep transients must not be read as thermal anomalies |
| `PL_f_opt_Hz`, `MT_f_opt_Hz` | /state | twin's current recommended frequency per chamber |
| `PL_eta_at_f_opt`, `MT_eta_at_f_opt` | /state | predicted absorption at the recommendation |
| `f_surface_confidence` | /state | GP variance-derived trust in the surface (mirrors `model_trust`) |
| `cmd_freq_setpoint_Hz` | ControlCommand / `/command` | advisory feedforward to the control hub; HMI gates on `command_age_s` as it already does |

Convene bindings follow mechanically: `sim_MT_f_opt_Hz`, etc.

## Safety Invariants (unchanged authorities)

1. LabVIEW clamps f to [2.400, 2.500] GHz in hardware-adjacent code; the model
   never holds the clamp.
2. The hardware interlock chain (over-temperature, 5 mW/cm² leakage) is
   untouched and remains the sole fault authority; frequency steering is
   subordinate to it exactly as power derating is.
3. On any anomaly (`NIS_BREACH`, `SEAL_LEAK`, safe-state), frequency reverts to
   the fixed default before/with power removal — one recovery state, not two.
4. Isolator/circulator/launcher band-rating verification is a **precondition**
   to any powered sweep.

## Consequences

- Easier: higher net absorbed power per commanded watt; automatic tracking
  through melt/pyrolysis transitions; a new frequency-domain observable that
  strengthens mass-flow estimation and anomaly detection; better energy
  efficiency scores (a challenge metric).
- Harder: the estimator must distinguish "η changed because T changed" from
  "η changed because f changed" — η becomes η(T, f) wherever the plant model
  consumes it, and sweep frames need the `MW_sweep_active` marker end-to-end.
- Revisit: forecaster parity (the inlined float path in `forecaster.py` must
  gain the same η(T, f) form as `plant.py` when this lands — flagged now to
  avoid repeating review finding M4); SSMG amplifier efficiency varies with f,
  so late-phase optimization should target *delivered-to-load per wall-plug
  watt*, not merely minimum reflection.

## Phasing (verification-gated, no code until P0 data exists)

1. [ ] **P0 — Characterize:** with each chamber, log stepped-frequency sweeps
   (cold, mid-cycle, near-melt/near-complete): f, P_fwd, P_refl → η_obs(T, f).
   Verify isolator band ratings. Exit gate: repeatable η surfaces per chamber.
2. [ ] **P1 — Model offline:** fit η(T, f) per chamber from P0 logs; validate
   predicted vs measured optimum on held-out cycles. Display-only in Convene.
3. [ ] **P2 — Local loop:** implement Option B in LabVIEW RT with the clamp,
   tuner-freeze rule, and fixed-f fallback. Twin remains observer.
4. [ ] **P3 — Feedforward:** enable `cmd_freq_setpoint_Hz` through the existing
   CommandSignal path; cRIO treats it as a starting point, never an override of
   its own reflection measurement.
5. [ ] **P4 — Exploit observability:** S11(f)-shape features into mass-flow /
   anomaly channels.

## Action Items

1. [ ] RF lead: confirm isolator, circulator, coupler, and launcher ratings
   across 2.40–2.50 GHz (precondition).
2. [ ] Controls lead: confirm SSMG frequency-command interface, settling time,
   and minimum dwell (sets the inner-loop rate).
3. [ ] Safety: confirm the leakage survey remains valid across the band.
4. [ ] Schedule the P0 characterization campaign; only after its exit gate does
   any implementation ticket get cut.
