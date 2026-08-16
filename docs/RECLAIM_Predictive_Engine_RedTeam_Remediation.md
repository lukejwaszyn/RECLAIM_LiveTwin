# RECLAIM Predictive Engine — Red-Team Remediation & Command-Authority Plan

**Written:** 2026-08-16 · **Status:** integration plan (no code changed yet).
Companion to `RECLAIM_Predictive_Engine_Lifecycle_Memo.md` (the continuous-operation
fix) and the external `PREDICTIVE_ENGINE_RED_TEAM_ASSESSMENT.md` (findings RT-01..08).

**Framing.** The red-team was verified against source — all eight findings hold. They
are a *different axis* than the lifecycle work: that fixed continuous-operation
(reboot/discrepancy); this is about **predictive-control fitness** (forecast fidelity,
command safety, input integrity). The organizing decision is the one the assessment
raised: the engine emits a real `ControlCommand`, so we treat it as a first-class
control path **with an explicit authority mode** — not a visualization side effect.

---

## 1. Command authority — the feature, made real and safe

**Requirement.** `/command` shall be a real control interface, but with a deployment
setting that keeps it **advisory by default**: the `cmd_*` variable is *always
populated* (Convene can always show intended action), yet nothing actuates on it
unless authority is explicitly `active` **and** the safety gate is healthy.

**Config (new `CommandConfig` on `EngineConfig`):**

- `authority: "advisory" | "active"` — **default `advisory`**. Static per deployment.
- `deadline_ms: int` — command validity window (e.g. 2000). Drives `cmd_valid_until`.
- physical caps: `power_cap_W`, `reflected_ratio_max`, etc. (safety envelope).

**Published command fields (always present, both modes):**

| Field | Meaning |
|---|---|
| `cmd_chamber`, `cmd_mode`, `cmd_power_setpoint_W`, `cmd_safe_state_armed` | the command intent (as today) |
| `cmd_authority` | `"advisory"` or `"active"` — echoes the configured mode |
| `cmd_actionable` | **bool** — `true` only if `authority=="active"` AND `cmd_health=="ok"`. The actuator acts **iff** this is true |
| `cmd_health` | `ok` \| `sensor_missing` \| `stale` \| `seq_gap` \| `estimator_unhealthy` \| `degraded` |
| `cmd_valid_until` | `ts_engine + deadline_ms` (ISO). The actuator fails closed past this |
| `cmd_reason` | traceable text (which signal set the command / health) |

**Semantics:**

- **advisory (default):** `cmd_*` computed and published normally so operators/Convene
  see "what the engine would command"; `cmd_authority="advisory"`, `cmd_actionable=false`
  **always**. This is the shadow/relied-upon-by-nobody posture the red-team permits now.
- **active:** identical computation, but `cmd_actionable=true` **only** when `cmd_health=="ok"`.
  If health is anything else, the command is forced to the **fail-safe** (`mode=SAFE_STATE`
  or power 0) and `cmd_actionable=false`, with `cmd_reason` naming the cause.

**Actuator-side contract (cRIO / gateway / HMI) — documented, enforced downstream:**
act on a command **only** if `cmd_actionable && now < cmd_valid_until`; otherwise hold
the last safe state / fail closed. This must be enforced **independently of cloud
availability** — a blind or absent engine results in no command, which the receiver
treats as expire→safe. The hardware interlock remains the sole, independent fault
authority regardless of mode.

This single mechanism closes the *architecture* of RT-02 and RT-07 and makes authority
explicit; the per-signal gates below fill in `cmd_health`.

---

## 2. Remediation workstreams (grouped, with disposition)

### Workstream A — Integrity (mode-independent; land before any deploy)

Applies even in advisory/shadow, because it prevents silent state corruption — the
exact "unanticipated results, debugging made it worse" failure class.

- **RT-03 — transactional stepping.** Today `_step_locked` mutates `count`, `_last_ts`
  and steps PL then MT in place; a failure after PL leaves PL double-integratable on
  retry. Fix: validate all inputs first, integrate each chamber into an **isolated
  candidate state**, and commit engine + ingest state **only after the whole frame
  succeeds** (or snapshot/restore on failure). Regression test: force a failure after
  chamber 1, then prove an identical retry equals a clean one-pass run.
- **RT-05 — finite/range validation before any mutation.** Reject `inf`/`nan`, wrong
  types/dims, and operating-envelope violations (temperature, pressure, forward power,
  `reflected ≤ forward`, timestamp progression, sensor-bank disagreement) in
  `_validate_frame` *before* the estimator sees them. Fix `_mean` to drop `inf`
  (it currently keeps it). Chains with RT-03: a bad value raising mid-frame is what
  triggers the double-step.

### Workstream B — Command authority (§1)

- **RT-02** folds in as the `cmd_health` gate (sensor validity, frame age, sequence
  health, estimator health) + `cmd_valid_until` deadline + fail-safe on not-ok.
- **RT-07** folds in by separating **authorized demand** from **observed power**: derate
  the authorized setpoint, not the measured `P_fwd`. Near-term the setpoint source is
  config; longer-term an authorized `setpoint_W` envelope field (a gateway-schema
  negotiation). In advisory mode with no setpoint, keep the observed-power derate but
  label it `advisory` / non-actionable.

### Workstream C — Forecast & probability fidelity (before advisory is *relied upon*)

- **RT-01 — forecast uses the estimator model.** Add `q_rxn` and the evolving
  charge-mass state to the forecast integration (`forecaster.py` `deriv()`/`cbed()`),
  or explicitly disable the forecast for configs whose dynamics it can't propagate.
  Add parity tests for **every enabled physical feature**, not just the two-node base.
- **RT-04 — stop calling `p_event` a probability.** It's the fraction of (non-equal-weight,
  near-collapsed with `alpha=1e-3`) sigma points crossing threshold — effectively a
  near-binary indicator. Relabel as an **ensemble-risk indicator**, remove `>0.5`
  probability thresholds from the advisor's control paths, or replace with a justified
  method (constrained Monte Carlo from a validated posterior) and validate calibration.
- **RT-08 — residual against the complete model.** Compute the "unexplained heat"
  residual against the **full** modeled derivative (including `q_rxn`); if the
  reduced-model diagnostic is still wanted, expose it as a *separate, clearly named*
  signal. Test both semantics. (Default config is endothermic pyrolysis, so today the
  bias masks rather than fabricates — but it's still wrong and breaks the independence
  claim.)

### Workstream D — Continuity / degraded mode (gate for `active` authority)

- **RT-06 — max continuity interval.** `dt` is clamped 0.05–10 s and the unexplained-rate
  runs on that compressed base. Define a maximum continuity gap; beyond it, do **not**
  emit a normal forecast or actionable command — enter `degraded` (`cmd_health=degraded`),
  reinitialize state with uncertainty inflation, and require N healthy frames before
  regaining predictive authority. (The lifecycle already prevents a *spurious cycle
  reset* on a gap; this is the separate forecast/rate concern.)

---

## 3. Disposition matrix — does it block deployment?

| Finding | Workstream | Blocks **advisory** Convene deploy? | Blocks **active** command authority? |
|---|---|---|---|
| RT-03 non-atomic retry | A | **Yes** (integrity) | Yes |
| RT-05 finite/range validation | A | **Yes** (integrity) | Yes |
| RT-02 fail-safe on stale | B | No (advisory = not actionable) | **Yes** |
| RT-07 command from power | B | No (labeled advisory) | **Yes** |
| RT-01 forecast ≠ plant | C | No, if forecast labeled non-authoritative | **Yes** |
| RT-04 `p_event` not probability | C | No, if relabeled + not driving action | **Yes** |
| RT-08 residual excludes q_rxn | C | No (default config), label caveat | **Yes** for exotherm configs |
| RT-06 time-gap compression | D | No (advisory) | **Yes** |

**Net:** for the imminent **advisory** Convene deployment, only **Workstream A**
(RT-03, RT-05) is a true blocker; the command-authority mode (§1) *is* the advisory
posture, and C/D items are handled by clearly labeling forecast/`p_event`/advisory
fields non-authoritative. Everything is a hard gate before flipping authority to
`active`.

---

## 4. Sequencing

1. **Workstream A** (transactional step + input validation) + regression tests. Land
   before the Convene deploy.
2. **§1 command-authority mode** in `advisory` default — populate `cmd_authority`,
   `cmd_actionable=false`, `cmd_health`, `cmd_valid_until`; document the actuator
   fail-closed contract. Ship with the deploy so the field is real and visible.
3. **Workstream C** (forecast parity, `p_event` relabel, residual) before any operator
   *relies* on advisory output.
4. **Workstream D** + end-to-end safety review + interlock-independence proof before
   `active` authority is ever enabled. Requires the assessment's five exit criteria.

Each change ships with a regression test that reproduces the failure it fixes — the
gap the red-team correctly flagged (its environment couldn't run pytest; ours can).
