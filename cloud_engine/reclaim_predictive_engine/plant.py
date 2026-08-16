"""
RECLAIM forward model—two-node lumped energy balance.

State (baseline):  x = [T_b, T_w, beta]
    T_b   bed / susceptor core temperature      [K]
    T_w   chamber wall / surface temperature    [K]
    beta  absorption-feedback strength          [1/K]   (slowly-varying)

Governing equations (Technical Note, Section 3):
    C_b dT_b/dt = P_abs(T_b,beta,t) - U_bw (T_b - T_w) + q_rxn(T_b)
    C_w dT_w/dt = U_bw (T_b - T_w) - Q_loss(T_w; env)
    dbeta/dt    = 0                              (random-walk via process noise)

    P_abs = P_fwd * eta(T_b),  eta(T) = eta0 * exp(beta (T - T_ref))   [primary
            dielectric-loss runaway driver]
    Q_loss = h_conv(env) A_s (T_w - T_amb) + eps sigma A_s (T_w^4 - T_amb^4)

The model is deliberately renderer- and simulation-independent: it consumes
only logged/commanded inputs and tagged parameters.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
import numpy as np

from .config import PhysicalParams, EnvironmentBlock, SIGMA_SB

R_GAS = 8.314462618  # J/mol/K


@dataclass
class Inputs:
    """Exogenous inputs at a step."""
    p_fwd: float                 # commanded/measured forward power, W
    env: EnvironmentBlock
    p_refl: Optional[float] = None  # measured reflected power, W (for eta obs)


class ForwardModel:
    """First-principles two-node plant. Pure functions of (x, u, params)."""

    N_STATE = 3  # [T_b, T_w, beta]

    def __init__(self, p: PhysicalParams):
        self.p = p
        # Live charge mass (kg). Advanced once per real step by the engine when
        # p.use_massflow is set; None means constant-capacity (legacy) behavior.
        self._mf_mass = float(getattr(p, "mf_m0", 0.0)) if getattr(p, "use_massflow", False) else None

    def recharge(self) -> None:
        """Re-seed the live charge mass for a new batch (cycle boundary). No-op when
        the mass balance is off. Fixes the batch-2+ 'charge_mass -> 0' discrepancy:
        the charge only decayed and was never restored without a process restart."""
        p = self.p
        if getattr(p, "use_massflow", False):
            self._mf_mass = float(getattr(p, "mf_m0", 0.0))

    # --- constitutive relations ---------------------------------------------
    def eta(self, T_b: float, beta: float) -> float:
        p = self.p
        if getattr(p, "use_ignition", False):
            # coupling-onset (ignition): weak residual coupling (eta_floor) below
            # T_ign lets the bed start cold; absorption then rises sharply through
            # the onset to the ceiling—SiC's real cold-start-then-ignite behavior.
            floor = float(getattr(p, "eta_floor", 0.10))
            val = floor + (float(p.eta_max) - floor) / (1.0 + np.exp(-float(p.k_ign) * (T_b - float(p.t_ign))))
        else:
            val = float(p.eta0) * np.exp(beta * (T_b - float(p.t_ref)))
        return float(np.clip(val, 0.0, float(p.eta_max)))

    def c_bed_eff(self, T_b: float) -> float:
        """Apparent bed heat capacity. Falls with the live charge mass when the
        mass balance is on (C_b = c_inert + m*cp), and is widened across the melt
        band to absorb the latent load (metals path)."""
        p = self.p
        if getattr(p, "use_massflow", False) and self._mf_mass is not None:
            c = float(p.mf_c_inert) + max(0.0, self._mf_mass) * float(p.mf_cp_charge)
        else:
            c = float(p.c_bed)
        if getattr(p, "use_melt", False) and abs(T_b - float(p.t_melt)) < float(p.melt_band):
            c += float(p.latent_heat) * float(p.melt_mass) / (2.0 * float(p.melt_band))
        return c

    def p_abs(self, T_b: float, beta: float, p_fwd: float) -> float:
        return p_fwd * self.eta(T_b, beta)

    def q_rxn(self, T_b: float) -> float:
        p = self.p
        q = 0.0
        # Pyrolysis endotherm (heat SINK) from the live mass balance: as the charge
        # decomposes at rate k0*exp(-Ea/RT)*m, it absorbs mf_dh per kg -> cools bed.
        if getattr(p, "use_massflow", False) and p.mf_mode == "pyrolysis" and self._mf_mass:
            rate = float(p.mf_k0) * np.exp(-float(p.mf_ea) / (R_GAS * max(T_b, 1.0))) * max(0.0, self._mf_mass)
            q -= float(p.mf_dh) * rate
        # Optional contaminant exotherm (heat SOURCE), unchanged.
        if p.use_chemical and float(p.reactive_mass) > 0.0:
            rate = float(p.k0) * np.exp(-float(p.e_a) / (R_GAS * max(T_b, 1.0)))
            q += float(p.delta_h) * float(p.reactive_mass) * rate
        return q

    def q_loss(self, T_w: float, env: EnvironmentBlock) -> float:
        p = self.p
        dT = T_w - env.t_amb
        h = env.h_conv(dT)
        conv = h * float(p.area_s) * dT
        rad = float(p.emiss_wall) * SIGMA_SB * float(p.area_s) * (T_w ** 4 - env.t_amb ** 4)
        return conv + rad

    # --- generation / loss curves for the Semenov criterion -----------------
    def H(self, T: float, beta: float, p_fwd: float) -> float:
        """Total heat generation as a function of (bed) temperature."""
        return self.p_abs(T, beta, p_fwd) + self.q_rxn(T)

    def L(self, T: float, env: EnvironmentBlock) -> float:
        """Heat loss as a function of temperature (evaluated at the loss node)."""
        return self.q_loss(T, env)

    def semenov_margin(self, x: np.ndarray, u: Inputs, dT: float = 1.0) -> float:
        """
        dH/dT - dL/dT  (numerical). > 0 => generation slope exceeds loss slope
        => approaching/at the thermal-explosion tangency (runaway-prone).
        """
        T_b, T_w, beta = x[0], x[1], x[2]
        dH = (self.H(T_b + dT, beta, u.p_fwd) - self.H(T_b - dT, beta, u.p_fwd)) / (2 * dT)
        dL = (self.L(T_w + dT, u.env) - self.L(T_w - dT, u.env)) / (2 * dT)
        return dH - dL

    # --- dynamics -----------------------------------------------------------
    def deriv(self, x: np.ndarray, u: Inputs) -> np.ndarray:
        p = self.p
        T_b, T_w, beta = x[0], x[1], x[2]
        dTb = (self.p_abs(T_b, beta, u.p_fwd)
               - float(p.u_bw) * (T_b - T_w)
               + self.q_rxn(T_b)) / self.c_bed_eff(T_b)
        dTw = (float(p.u_bw) * (T_b - T_w)
               - self.q_loss(T_w, u.env)) / float(p.c_wall)
        dbeta = 0.0
        return np.array([dTb, dTw, dbeta], dtype=float)

    def step(self, x: np.ndarray, u: Inputs, dt: float) -> np.ndarray:
        """One RK4 step. Inputs held constant across the step."""
        k1 = self.deriv(x, u)
        k2 = self.deriv(x + 0.5 * dt * k1, u)
        k3 = self.deriv(x + 0.5 * dt * k2, u)
        k4 = self.deriv(x + dt * k3, u)
        xn = x + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        # beta is a parameter-state; keep it non-negative-bounded lightly
        return xn

    def integrate(self, x0: np.ndarray, u: Inputs, horizon: float, dt: float):
        """Forward-integrate holding u constant. Returns (t, X[:,3])."""
        n = max(1, int(round(horizon / dt)))
        t = np.zeros(n + 1)
        X = np.zeros((n + 1, self.N_STATE))
        X[0] = x0
        for k in range(n):
            X[k + 1] = self.step(X[k], u, dt)
            t[k + 1] = t[k] + dt
        return t, X

    # --- measurement model --------------------------------------------------
    @staticmethod
    def measure(x: np.ndarray) -> np.ndarray:
        """Observed quantities: [T_b, T_w]. (eta optionally appended elsewhere.)"""
        return np.array([x[0], x[1]], dtype=float)

    @staticmethod
    def eta_measured(p_fwd: float, p_refl: float) -> float:
        """Online absorption efficiency from the directional coupler."""
        if p_fwd <= 0:
            return 0.0
        return float(np.clip((p_fwd - p_refl) / p_fwd, 0.0, 1.0))
