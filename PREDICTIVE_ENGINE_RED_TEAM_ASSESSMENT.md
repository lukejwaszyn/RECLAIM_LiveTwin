# Predictive Engine Red-Team Assessment

**Date:** 2026-08-16  
**Scope:** `cloud_engine/` predictive engine, its dual-chamber live-ingest path, and its returned command interface.  
**Method:** Static architecture and source review. No source files were modified.

## Executive conclusion

The current implementation is **not fit for autonomous or operator-relied predictive control**. It may be used in a clearly labeled **shadow / read-only digital-twin mode** while the findings below are remediated and verified.

The independent hardware interlock limits the likelihood of an ultimate over-temperature event, but does not make the predictive layer reliable. It cannot correct wrong lead-time forecasts, prevent nuisance intervention, protect state integrity after retry, or provide a fail-safe reaction to a blind/stale predictive engine.

The distinction mattered to the assessed historical route because the cloud engine also returned a `ControlCommand` to the gateway and local control hub/HMI. The final Convene-routed architecture authorizes no command or actuation path; the root README records that closed boundary.

## Severity interpretation in this digital-twin context

| Finding | Read-only / shadow twin | Live advisory relied on by operator | Automatic or control-connected use |
|---|---|---|---|
| Forecast differs from live plant | High: displayed forecast is invalid | Critical | **Release blocker** |
| No fail-safe on missing/stale telemetry | Medium | Critical | **Safety release blocker** |
| Non-transactional retry | High: silent state corruption | Critical | **Integrity release blocker** |
| Invalid `p_event` probability | High if shown as probability | Critical if it drives escalation | **Release blocker for probability-driven control** |
| No finite/range validation | High | Critical | **Release blocker for exposed live ingest** |
| Silent time-gap compression | High | High | **Release blocker unless degraded mode is enforced** |
| Command derived from observed power | Low | High | **Architectural blocker for closed-loop control** |
| Reaction term omitted from residual | Conditional high | Critical when chemical heat is enabled | **Release blocker for affected configurations** |

## Findings

### RT-01 — Forecast model is not the live plant model

**Severity:** Critical for predictive decisions; release blocker for live predictive control.

The live plant includes reaction heat in its bed-temperature derivative:

- [`plant.py`](cloud_engine/reclaim_predictive_engine/plant.py#L132-L141) adds `q_rxn(T_b)`.

The forecast sweep instead models only absorbed power and bed-to-wall transfer:

- [`forecaster.py`](cloud_engine/reclaim_predictive_engine/forecaster.py#L103-L109) omits `q_rxn()`.

It also has no evolving charge-mass state, even though both production chamber configurations enable mass flow:

- [`config.py`](cloud_engine/reclaim_predictive_engine/config.py#L314-L320) configures plastics pyrolysis mass flow.
- [`config.py`](cloud_engine/reclaim_predictive_engine/config.py#L329-L334) configures metals drain mass flow.

**Impact:** Forecasted time-to-limit, thermal margin, and recovery time can be systematically biased for the actual production paths. The report’s central predictive output is therefore not traceable to the dynamics being estimated.

**Required remediation:** Make future mass and reaction state part of the forecast state/integration, or explicitly disable the predictive forecast for configurations whose live dynamics cannot be propagated. Add parity tests for every enabled physical feature, not only the baseline two-node model.

### RT-02 — Missing or stale telemetry does not produce a fail-safe command

**Severity:** Critical for any control-connected deployment; safety release blocker.

When an active chamber has missing temperature measurements, it is not stepped and only a `SENSOR_MISSING` event is emitted:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L282-L305).

Command generation does not gate on sensor validity, frame age, timestamp discontinuity, or sequence-gap health:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L168-L186).

`/state` computes an age only for display, while `/command` returns the last command without a freshness gate:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L690-L704).

**Contextual mitigation and gap:** The deployment preflight says the HMI can invalidate a stale command. That is a downstream mitigation, not an enforced safety property of this engine-to-command interface. The system must show—through an end-to-end test—that the gateway/control hub fails closed if telemetry, state, or command freshness fails.

**Required remediation:** Publish a command validity deadline and explicit `DATA_NOT_LIVE`/safe-state result; gate command output locally on active-chamber sensor validity, freshness, sequence health, and estimator health. The actuator-side receiver must independently fail closed after its deadline.

### RT-03 — Retry path is not atomic and can double-integrate a chamber

**Severity:** Critical integrity fault; release blocker.

The live-ingest contract says an internal error does not commit identity and retry “re-steps cleanly”:

- [`RECLAIM_Live_Telemetry_Architecture.md`](docs/RECLAIM_Live_Telemetry_Architecture.md#L117-L122).

However, `_step_locked()` mutates timestamps, counters, and chamber engines before all operations can succeed:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L528-L593).

On a later exception it returns a retryable `internal_error`, but does not restore any of that mutated state:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L487-L498).

**Impact:** If plastics is stepped successfully and metals, service publication, or a later conversion fails, retrying the same frame can integrate plastics twice. This corrupts filter state, lifecycle state, charge mass, elapsed time, and accumulated metrics without a sequence-level audit record.

**Required remediation:** Make stepping transactional: validate all inputs first; calculate into isolated candidate state; commit all engine and ingest state only after the complete frame succeeds. Alternatively, snapshot and reliably restore all mutable state on failure. Add a test that forces failure after the first chamber has stepped, then verifies an identical retry produces the same state as a clean one-pass run.

### RT-04 — `p_event` is an uncalibrated score, not a probability

**Severity:** High for a display-only twin; critical when used for escalation/control.

The forecast takes UKF sigma points, treats them as equal-weight samples, and computes the event probability as the fraction with a finite event time:

- [`forecaster.py`](cloud_engine/reclaim_predictive_engine/forecaster.py#L207-L225).

Sigma points are deterministic quadrature points, not equally likely draws. With the configured scaled-UKF parameters, their weights are intentionally non-uniform and may include a negative central weight. Replacing them with equal weights does not yield a calibrated event probability.

The advisor uses `p_event > 0.5` in critical and warning decision paths:

- [`advisor.py`](cloud_engine/reclaim_predictive_engine/advisor.py#L105-L121).

**Required remediation:** Either relabel this output as a non-probabilistic ensemble-risk indicator and remove probability thresholds from control decisions, or estimate probability with a justified method (for example, constrained Monte Carlo drawn from a validated posterior) and validate calibration against held-out and fault data.

### RT-05 — Numeric finiteness and physical bounds are not enforced

**Severity:** High; release blocker for exposed live ingestion.

The documented production contract requires numeric finiteness, units, and sensor mapping validation before estimator input:

- [`RECLAIM_Live_Telemetry_Architecture.md`](docs/RECLAIM_Live_Telemetry_Architecture.md#L88-L100).

The implementation validates the envelope but not finite/range-safe values:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L366-L425).

The sensor averaging helper removes NaN but accepts `inf`:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L126-L129).

**Impact:** Corrupted inputs can propagate into the UKF/forecast, cause retryable exceptions that trigger RT-03, or create nonsensical control output.

**Required remediation:** Reject non-finite values, invalid dimensions/types, and operating-envelope violations before any mutation. Define explicit limits for temperatures, pressure, forward/reflected power, reflected-power relationship, timestamp progression, and sensor-bank disagreement.

### RT-06 — Large time gaps are silently compressed before physics and rate alarms

**Severity:** High; release blocker unless degraded mode is enforced.

Actual timestamp deltas are compressed to `0.05–10 s`:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L528-L535).

The engine later derives unexplained heating from that compressed local timebase:

- [`engine.py`](cloud_engine/reclaim_predictive_engine/engine.py#L161-L169).

**Impact:** A long outage can produce a false heating rate, skip an unmodeled thermal trajectory, or yield a stale forecast that still participates in a command decision. A `SEQ_GAP` event is not sufficient if safety logic continues normally.

**Required remediation:** Define a maximum continuity interval. Beyond it, do not create a normal forecast or command; enter degraded mode, re-acquire state with explicit uncertainty inflation/reinitialization, and require a defined number of healthy frames before returning to predictive authority.

### RT-07 — Returned command is derived from measured power, not commanded intent

**Severity:** Architectural blocker for closed-loop use.

The output command is computed as a severity-based fraction of the observed `P_fwd`:

- [`push_ingest_dual.py`](cloud_engine/push_ingest_dual.py#L168-L186).

The inbound schema has no validated operator or controller setpoint.

**Impact:** A nominal zero-power condition yields a zero-power command, so the interface cannot safely represent startup, distinguish a sensor observation from an actuator target, or make command authority explicit.

**Required remediation:** Separate telemetry, authorized demand/setpoint, safety envelope, and actuator command. Give each source, timestamp, authority, and validity deadline. Until then, constrain this endpoint to advisory derating guidance rather than a direct actuator command.

### RT-08 — “Unexplained heat” residual excludes heat the plant already models

**Severity:** Conditional high; critical for chemical/exothermic configurations.

The residual baseline uses absorbed microwave power minus bed-to-wall transfer:

- [`engine.py`](cloud_engine/reclaim_predictive_engine/engine.py#L154-L169).

The plant’s corresponding bed dynamics include `q_rxn()`:

- [`plant.py`](cloud_engine/reclaim_predictive_engine/plant.py#L90-L102) and [`plant.py`](cloud_engine/reclaim_predictive_engine/plant.py#L132-L141).

**Impact:** Enabling the optional chemical exotherm makes modeled heat look “unexplained,” potentially escalating to a false critical advisory. It also breaks the claim that this residual independently tests unmodeled heat.

**Required remediation:** Calculate the residual against the complete modeled derivative, then separately expose a residual against a deliberately reduced model if that diagnostic is needed. Test both semantics.

## Release recommendation

### Allowed now: shadow mode only

The engine may ingest live data and publish a read-only state/visualization **only if** all forecast, event, advisory, and command fields are clearly marked non-authoritative; operators are instructed not to use them for thermal intervention; and the physical hardware interlock remains independent.

### Not allowed now

Do not use the returned `ControlCommand` to autonomously set microwave power, arm safe-state logic, or serve as a relied-upon operator decision authority.

### Minimum exit criteria for a control-connected pilot

1. Close RT-01 through RT-06 and add regression tests that reproduce each failure mode.
2. Establish a single fail-closed command authority with actuator-side expiry, independent of cloud availability.
3. Test partial failure/retry, sensor loss, stale frames, sequence gaps, long network outages, malformed numeric values, and cloud restart against physical-safe expected outcomes.
4. Demonstrate forecast parity and probability/risk calibration on representative PL and MT data, including mass-flow transitions and off-nominal cases.
5. Conduct an end-to-end safety review proving the hardware interlock remains independent and that no predictive failure can bypass or weaken it.

## Verification note

Static source inspection and Python bytecode compilation completed successfully. The repository’s pytest suite was not executed in the review environment because `pytest` was unavailable.
