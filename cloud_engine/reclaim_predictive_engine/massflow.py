"""
Mass-flow truth plant—the chamber loses mass once reactions start.

The baseline two-node model holds the charge thermal mass constant. In reality the
processed mass LEAVES the chamber during a cycle, so the bed thermal capacity
C_b(t) = C_inert + m(t)*cp_charge falls over time. With the same absorbed power the
*remaining* mass then heats faster (dT/dt = P/C_b rises)—a late-cycle acceleration
the constant-C model cannot see. Two physical mechanisms:

  METALS (drain)—aluminium melts at T_melt (latent heat absorbed across a melt
                       band), then the molten charge drip-casts out: dm/dt =
                       -k_drain * max(0, T_b - T_melt). C_b falls toward C_inert (the
                       SiC susceptor/crucible that stays). Modest drop (~10%): the
                       susceptor dominates the heat capacity.
  PLASTICS (pyrolysis)—PE decomposes by first-order Arrhenius kinetics, dm/dt =
                       -k0*exp(-Ea/(R*T_b))*m, the volatiles are pumped out, and the
                       decomposition is ENDOTHERMIC (a heat sink, q = +dh*|dm/dt|).
                       Mass loss is near-total, so C_b can fall ~45%—the dominant
                       mass-flow effect. The endothermic sink is stabilising; the
                       C_b collapse is destabilising; the net is what the MC probes.

This is a mass balance added alongside the energy balance—more first-principles
physics, not less. Kept as a separate 4-state truth stepper so the production
3-state engine path is untouched; the engine consumes its temperature measurements.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .config import SIGMA_SB, EnvironmentBlock, EARTH_LAB

R_GAS = 8.314462618


@dataclass
class MassFlowParams:
    mode: str                 # "drain" (metals) or "pyrolysis" (plastics)
    c_inert: float            # structural heat capacity that remains (J/K)
    cp_charge: float          # charge specific heat (J/kg/K)
    m0: float                 # initial charge mass (kg)
    # absorption (shared with plant): eta(T) = eta0*exp(beta*(T-t_ref)), clamped
    eta0: float = 0.5
    t_ref: float = 300.0
    eta_max: float = 0.98
    u_bw: float = 6.0
    c_wall: float = 4000.0
    area_s: float = 0.30
    emiss: float = 0.5
    # metals melt/drain
    t_melt: float = 933.0
    latent: float = 397000.0
    melt_band: float = 20.0
    k_drain: float = 1.0e-4   # kg/s per K of superheat
    # plastics pyrolysis (first-order Arrhenius) + endothermic enthalpy
    k0_pyro: float = 2.0e6    # 1/s
    ea_pyro: float = 1.2e5    # J/mol
    dh_pyro: float = 1.0e6    # J/kg endothermic (heat sink)
    # OPTIONAL contaminant exotherm (dirty chamber): an unmodeled EXOTHERMIC
    # Arrhenius source on a small reactive mass, on TOP of the nominal reaction.
    # Off by default (dh<=0). q_exo = dh_exo*m_exo*k0_exo*exp(-Ea_exo/RT) (into bed).
    exo_dh: float = 0.0       # J/kg exothermic
    exo_mass: float = 0.0     # kg reactive contaminant
    exo_k0: float = 1.0e8     # 1/s
    exo_ea: float = 1.2e5     # J/mol

    @staticmethod
    def metals(m0: float = 0.5, c_bed: float = 4815.0):
        # SiC susceptor/crucible stays; aluminium charge drains. c_inert = c_bed
        # minus the charge contribution so C_b(0) matches the CAD c_bed.
        cp = 900.0
        return MassFlowParams(mode="drain", c_inert=max(200.0, c_bed - m0*cp),
                              cp_charge=cp, m0=m0, eta0=0.5, area_s=0.415, emiss=0.85)

    @staticmethod
    def plastics(m0: float = 1.0, c_bed: float = 4374.0):
        # ZSM-5/SiC packed bed stays; the plastic charge decomposes to gas.
        cp = 2000.0
        return MassFlowParams(mode="pyrolysis", c_inert=max(200.0, c_bed - m0*cp),
                              cp_charge=cp, m0=m0, eta0=0.5, area_s=0.292, emiss=0.35)


def _eta(mp: MassFlowParams, T_b: float, beta: float) -> float:
    v = mp.eta0 * np.exp(beta * (T_b - mp.t_ref))
    return float(min(mp.eta_max, max(0.0, v)))


def _c_bed(mp: MassFlowParams, T_b: float, m: float) -> float:
    """Time-varying bed heat capacity with melt-band apparent-Cp widening (metals)."""
    c = mp.c_inert + max(0.0, m) * mp.cp_charge
    if mp.mode == "drain" and abs(T_b - mp.t_melt) < mp.melt_band and m > 0:
        c += mp.latent * m / (2.0 * mp.melt_band)        # latent load across the band
    return c


def deriv4(mp: MassFlowParams, x, p_fwd: float, env: EnvironmentBlock):
    """x = [T_b, T_w, beta, m]. Returns dx/dt with the mass balance coupled in."""
    T_b, T_w, beta, m = float(x[0]), float(x[1]), float(x[2]), max(0.0, float(x[3]))
    p_abs = p_fwd * _eta(mp, T_b, beta)
    # mass loss + reaction heat
    dm = 0.0; q_rxn = 0.0
    if mp.mode == "drain":
        if T_b > mp.t_melt and m > 0:
            dm = -mp.k_drain * (T_b - mp.t_melt)         # molten Al drains out
    elif mp.mode == "pyrolysis":
        if m > 0:
            rate = mp.k0_pyro * np.exp(-mp.ea_pyro / (R_GAS * max(T_b, 1.0))) * m
            dm = -rate
            q_rxn = -mp.dh_pyro * abs(dm)                # endothermic sink (cools)
    dm = max(dm, -m)                                     # cannot lose more than present
    # optional contaminant exotherm (dirty chamber), Arrhenius, into the bed
    q_exo = 0.0
    if mp.exo_dh > 0.0 and mp.exo_mass > 0.0:
        q_exo = mp.exo_dh * mp.exo_mass * mp.exo_k0 * np.exp(-mp.exo_ea / (R_GAS * max(T_b, 1.0)))
    c_b = _c_bed(mp, T_b, m)
    # drained/decomposed mass leaves at bed temperature (carries its own enthalpy),
    # so it removes no net heat from the remainder beyond reducing C_b; explicit
    # reaction heat is the endothermic pyrolysis sink q_rxn plus any contaminant q_exo.
    dTb = (p_abs - mp.u_bw * (T_b - T_w) + q_rxn + q_exo) / c_b
    dT = T_w - env.t_amb
    hconv = (1.3 * (env.g/env.G0)**0.25 * (env.p_atm/env.P0)**0.5 * dT**0.25) if (env.convection and dT > 0) else 0.0
    q_loss = hconv*mp.area_s*dT + mp.emiss*SIGMA_SB*mp.area_s*(T_w**4 - env.t_amb**4)
    dTw = (mp.u_bw * (T_b - T_w) - q_loss) / mp.c_wall
    return np.array([dTb, dTw, 0.0, dm])


def step4(mp: MassFlowParams, x, p_fwd: float, env: EnvironmentBlock, dt: float):
    """One RK4 step of the 4-state mass-flow truth plant."""
    k1 = deriv4(mp, x, p_fwd, env)
    k2 = deriv4(mp, x + 0.5*dt*k1, p_fwd, env)
    k3 = deriv4(mp, x + 0.5*dt*k2, p_fwd, env)
    k4 = deriv4(mp, x + dt*k3, p_fwd, env)
    xn = x + (dt/6.0)*(k1 + 2*k2 + 2*k3 + k4)
    xn[3] = max(0.0, xn[3])                              # mass non-negative
    return xn
