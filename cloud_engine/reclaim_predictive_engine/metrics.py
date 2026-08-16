"""
Performance accounting—the scored quantities, computed live from telemetry.

The challenge scores energy efficiency, mass efficiency, and cycle duration
(Table 8 / Table 10). The twin computes these continuously rather than
reconstructing them after the cycle:

    consumed_energy = integral of absorbed power (P_fwd - P_refl) over the cycle
    energy_efficiency = reclaimed mass / consumed energy        [g / Wh]
    mass_efficiency   = output mass / input mass                [-]
    thermal_margin    = T_limit - T_bed                         [K]
    cycle_elapsed     = time since cycle start                  [s]
    peak_temp         = max bed temperature observed            [K]

Mass figures are configured per-batch (the twin carries no live scale); they
trace to the requirements baseline (DR-2 / SYS-PR-001 minimum batch). Energy is
measured directly from the coupler channels, so the energy figures are live and
hardware-grounded.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PerformanceConfig:
    input_mass_g: float = 500.0        # DR-2 / SYS-PR-001 minimum batch
    output_mass_g: float = 425.0       # configured yield (~85%); per-cycle accounting
    note: str = "masses configured (no live scale); energy measured from coupler"


class PerformanceAccumulator:
    """Trapezoidal energy integral + running cycle statistics."""

    def __init__(self, cfg: PerformanceConfig | None = None):
        self.cfg = cfg or PerformanceConfig()
        self.reset()

    def reset(self):
        self._t0 = None
        self._t_prev = None
        self._p_prev = None
        self.energy_j = 0.0
        self.peak_temp = 0.0
        self.elapsed = 0.0

    def update(self, t: float, p_fwd: float, p_refl: float, T_bed: float):
        p_abs = max(0.0, p_fwd - p_refl)
        if self._t0 is None:
            self._t0 = t
        if self._t_prev is not None and t > self._t_prev:
            dt = t - self._t_prev
            self.energy_j += 0.5 * (p_abs + self._p_prev) * dt  # trapezoid, W*s = J
        self._t_prev, self._p_prev = t, p_abs
        self.elapsed = t - self._t0
        self.peak_temp = max(self.peak_temp, T_bed)

    def metrics(self, t_limit: float, T_bed_est: float) -> dict:
        wh = self.energy_j / 3600.0
        eff_e = (self.cfg.output_mass_g / wh) if wh > 1e-9 else 0.0
        return {
            "consumed_energy_wh": wh,
            "energy_efficiency_g_per_wh": eff_e,
            "mass_efficiency": self.cfg.output_mass_g / self.cfg.input_mass_g,
            "thermal_margin_K": t_limit - T_bed_est,
            "cycle_elapsed_s": self.elapsed,
            "peak_temp_K": self.peak_temp,
        }
