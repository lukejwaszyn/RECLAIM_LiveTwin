"""
Plant / scenario harness—synthetic ground truth for virtual prototyping
and V&V (NEES against a known state). Generates a noisy measurement stream
from a truth model so the estimator/forecaster can be exercised without
hardware. This is the "plant" half of model-in-the-loop testing.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np

from .config import PhysicalParams, EnvironmentBlock, EARTH_LAB, LUNAR_SURFACE
from .plant import ForwardModel, Inputs


@dataclass
class Scenario:
    name: str
    beta_true: float            # true absorption-feedback strength
    p_fwd: Callable[[float], float]  # commanded power schedule, W(t)
    env: EnvironmentBlock = field(default_factory=lambda: EARTH_LAB)
    duration: float = 400.0
    dt: float = 1.0
    meas_noise_K: float = 2.0
    refl_frac: float = 0.05     # reflected fraction (coupler) baseline
    op_state_fn: Optional[Callable[[float], str]] = None  # phase -> operational state
    event_fn: Optional[Callable[[float], list]] = None    # phase -> discrete events
    beta_drift: float = 0.0   # true feedback drift per second (ageing / coupling change)
    pressure_fn: Optional[Callable[[float], float]] = None  # chamber pressure (kPa) vs t
    downstream_pressure_fn: Optional[Callable[[float], float]] = None  # PL output (kPa)


class TruthPlant:
    """Runs the ForwardModel with a chosen true beta as ground truth."""
    def __init__(self, params: PhysicalParams, scenario: Scenario, seed: int = 0):
        self.params = params
        self.sc = scenario
        self.model = ForwardModel(params)
        self.rng = np.random.default_rng(seed)
        self.x = np.array([scenario.env.t_amb, scenario.env.t_amb,
                           scenario.beta_true], float)

    def crossing_time(self) -> float:
        """Forward-run truth to find when T_bed actually crosses t_limit."""
        x = self.x.copy()
        t = 0.0
        tl = float(self.params.t_limit)
        while t < self.sc.duration:
            u = Inputs(p_fwd=self.sc.p_fwd(t), env=self.sc.env)
            x = self.model.step(x, u, self.sc.dt)
            x[2] += self.sc.beta_drift * self.sc.dt
            t += self.sc.dt
            if x[0] >= tl:
                return t
        return float("inf")

    def stream(self):
        """Yield (t, z_noisy[2], p_fwd, p_refl) telemetry frames."""
        x = self.x.copy()
        t = 0.0
        while t <= self.sc.duration:
            p_fwd = self.sc.p_fwd(t)
            p_refl = p_fwd * self.sc.refl_frac
            z = np.array([x[0], x[1]]) + self.rng.normal(0, self.sc.meas_noise_K, 2)
            yield t, z, p_fwd, p_refl, x.copy()
            u = Inputs(p_fwd=p_fwd, env=self.sc.env)
            x = self.model.step(x, u, self.sc.dt)
            x[2] += self.sc.beta_drift * self.sc.dt
            t += self.sc.dt


# Canonical scenarios ---------------------------------------------------------
def runaway_scenario(env: EnvironmentBlock = EARTH_LAB) -> Scenario:
    """Constant high power + strong feedback -> dielectric-loss runaway."""
    return Scenario(
        name="dielectric_runaway",
        beta_true=5.0e-3,
        p_fwd=lambda t: 5500.0,
        env=env,
        duration=600.0,
    )


def nominal_scenario(env: EnvironmentBlock = EARTH_LAB) -> Scenario:
    """Moderate power + weak feedback -> stable heat-and-hold (no runaway)."""
    return Scenario(
        name="nominal_hold",
        beta_true=1.0e-3,
        p_fwd=lambda t: 2200.0,
        env=env,
        duration=400.0,
    )


def long_run_scenario(env: EnvironmentBlock = EARTH_LAB, minutes: float = 45.0) -> Scenario:
    """A sustained 30-45 min processing cycle with slowly drifting absorption
    feedback (bed ageing / coupling change). Stable (no runaway); its purpose is
    to exercise long-duration tracking and the adaptive filter, which must follow
    the drift and stay statistically consistent where a fixed-gain filter would
    grow over-confident and lose the trail."""
    # Mild power modulation (±350 W, 10-min period) reflects real process
    # variation and provides the persistent excitation that keeps the absorption
    # feedback observable for online identification over a long hold.
    return Scenario(
        name="long_run_drift",
        beta_true=1.0e-3,
        p_fwd=lambda t: 2600.0 + 350.0 * np.sin(2 * np.pi * t / 600.0),
        env=env,
        duration=minutes * 60.0,
        beta_drift=3.0e-7,            # ~ +0.0005 over 45 min
    )


def seal_leak_scenario(env: EnvironmentBlock = EARTH_LAB, leak_start: float = 200.0,
                       leak_rate: float = 20.0) -> Scenario:
    """Plastics pyrolysis with a vacuum seal leak: the chamber pumps down, then
    at `leak_start` a seal begins to leak (pressure rises at `leak_rate` Pa/s).
    The seal-integrity residual should detect the deviation from the pump-down
    curve shortly after onset."""
    def pressure_fn(t):
        base_pa = 80.0 + (101325.0 - 80.0) * np.exp(-t / 60.0)
        leak_pa = max(0.0, t - leak_start) * leak_rate
        return (base_pa + leak_pa) / 1000.0  # scenario pressure contract is kPa
    # The seal monitor is phase-gated to evacuation/seal-check (fix C5), so the
    # scenario must report the state in which pump-down physically happens.
    def op_state_fn(t):
        return "S_Evacuate" if t < leak_start + 120.0 else "S_MicrowaveHeating"
    return Scenario(name="seal_leak", beta_true=2.0e-3, p_fwd=lambda t: 2600.0,
                    env=env, duration=400.0, pressure_fn=pressure_fn,
                    op_state_fn=op_state_fn)


def ramp_scenario(env: EnvironmentBlock = EARTH_LAB, target: float = 5500.0,
                  ramp_s: float = 120.0) -> Scenario:
    """Soft-start: microwave power ramps linearly from 0 to `target` over
    `ramp_s`, then holds. Exercises cold-start coupling and ramp-time
    forecasting (the engine integrates the actual power profile)."""
    def p_fwd(t):
        return min(target, target * t / ramp_s)
    return Scenario(name="soft_start_ramp", beta_true=5.0e-3, p_fwd=p_fwd,
                    env=env, duration=600.0)


def power_outage_scenario(env: EnvironmentBlock = EARTH_LAB) -> Scenario:
    """NASA off-nominal 1: power interrupted at 50% cycle completion for 5 min,
    then restart to completion. Power -> 0 over the outage window; the twin tracks
    the free thermal decay (whose rate measures the true loss coefficient) and the
    recovery on restart. Stable feedback -> no runaway; the value is state tracking
    through the interruption."""
    # A credible MT rehearsal must actually cross the aluminium melt threshold
    # (933 K / ~660 C). The former 3.5 kW, 900 s profile ended near 114 C and was
    # only a plumbing demonstration. This 45-minute physical timeline reaches
    # melt despite a five-minute outage, then provides a five-minute powered-off
    # cooldown so the retained terminal frame is safe. The MacBook compresses it
    # to 3:30 wall.
    duration = 2700.0
    heat_end = 2400.0
    out_start = 1200.0
    out_end = out_start + 300.0         # +5 min
    restart_window = 20.0
    p_heat = 6000.0

    def p_fwd(t):
        return 0.0 if out_start <= t < out_end or t >= heat_end else p_heat

    def op_state_fn(t):
        if out_start <= t < out_end:
            return "S_PowerInterrupted"
        if out_end <= t < out_end + restart_window:
            return "S_Restart"
        if t >= heat_end:
            return "S_Cooldown"
        return "S_MicrowaveHeating"

    def event_fn(t):
        if out_start <= t < out_start + 1.0:
            return ["POWER_INTERRUPTED"]
        if out_end <= t < out_end + 1.0:
            return ["POWER_RESTORED"]
        return []

    return Scenario(
        name="power_outage",
        beta_true=2.0e-3,
        p_fwd=p_fwd,
        env=env,
        duration=duration,
        op_state_fn=op_state_fn,
        event_fn=event_fn,
    )


def lunar_surface_process_scenario(
    env: EnvironmentBlock = LUNAR_SURFACE,
) -> Scenario:
    """45-minute PL pyrolysis heat followed by 30-minute lunar cooldown.

    A 45-minute ramp to 6 kW drives the modeled PL bed to approximately 450 C
    near the end of the heat phase instead of reaching an early plateau. The
    pressure traces reproduce the operating-vacuum bands in the supplied cRIO
    capture: roughly 50.8 Torr in the chamber and 61.6 Torr downstream. Small,
    smooth oscillations keep the synthetic sensors realistic without exceeding
    the observed ranges. The extended power-off tail exercises radiation-limited
    cooldown and leaves a safe terminal frame. The MacBook compresses this
    75-minute physical timeline to 5:00 wall.
    """
    heat_end = 2700.0
    duration = 4500.0

    def chamber_pressure_kpa(t: float) -> float:
        # Capture range: 48.660-53.420 Torr; median 50.794 Torr.
        torr = 50.794 + 0.85 * np.sin(2 * np.pi * t / 181.0) \
            + 0.30 * np.sin(2 * np.pi * t / 47.0)
        return torr * 0.1333224

    def downstream_pressure_kpa(t: float) -> float:
        # Capture range: 58.181-64.978 Torr; median 61.596 Torr.
        torr = 61.596 + 1.55 * np.sin(2 * np.pi * t / 223.0 + 0.6) \
            + 0.55 * np.sin(2 * np.pi * t / 59.0)
        return torr * 0.1333224

    return Scenario(
        name="lunar_pyrolysis_cooldown",
        beta_true=1.0e-3,
        p_fwd=lambda t: 6000.0 * t / heat_end if t < heat_end else 0.0,
        env=env,
        duration=duration,
        pressure_fn=chamber_pressure_kpa,
        downstream_pressure_fn=downstream_pressure_kpa,
        op_state_fn=lambda t: "S_MicrowaveHeating" if t < heat_end else "S_Cooldown",
    )
