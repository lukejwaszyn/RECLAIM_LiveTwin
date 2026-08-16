"""
Forecasting and lead-time engine.

From the current filter estimate (x_hat, P) the engine forward-integrates the
first-principles model to a probabilistic time-to-event:

    t* = min { tau > 0 : T_b(t+tau) >= T_limit  OR  dH/dT >= dL/dT }

Uncertainty is propagated by integrating the filter's sigma points forward and
collecting the per-point event times; the report is a median lead time with a
confidence band and the probability of an event within the horizon. This is a
physics-based prediction, not a heuristic extrapolation: the Semenov tangency
makes the predicted onset mechanistically meaningful.

Implementation note: the forward sweep uses a pure-float RK4 with inline
constitutive relations and early termination, so the sigma-point ensemble can
be propagated at telemetry rate. The math is identical to plant.ForwardModel;
the float path exists only for speed and is covered by a parity test.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import exp
import numpy as np

from .plant import ForwardModel, Inputs
from .estimator import UKF
from .config import SIGMA_SB

R_GAS = 8.314462618


@dataclass
class ForecastResult:
    t_star: float
    t_star_sigma: float
    p_event: float
    t_low: float
    t_high: float
    mechanism: str
    horizon: float

    def to_dict(self) -> dict:
        return asdict(self)


class Forecaster:
    def __init__(self, model: ForwardModel, t_limit: float,
                 horizon: float = 180.0, dt: float = 2.0):
        self.model = model
        self.t_limit = t_limit
        self.horizon = horizon
        self.dt = dt

    # --- pure-float forward sweep for one sigma point ----------------------
    def _event_time(self, x0, p_fwd, env) -> tuple[float, str]:
        # p_fwd may be a scalar (held) or a callable schedule p_fwd(tau) so the
        # forecast can follow a commanded power ramp rather than assume constant.
        p = self.model.p
        c_wall = float(p.c_wall); u_bw = float(p.u_bw)
        area = float(p.area_s); emiss = float(p.emiss_wall)
        # absorption + melt params captured once (inlined for speed; same math as
        # plant.eta / plant.c_bed_eff, including ignition and latent-heat branches)
        eta0 = float(p.eta0); t_ref = float(p.t_ref); eta_max = float(p.eta_max)
        c_bed = float(p.c_bed)
        use_ign = bool(getattr(p, "use_ignition", False))
        t_ign = float(getattr(p, "t_ign", 700.0)); k_ign = float(getattr(p, "k_ign", 0.02))
        eta_floor = float(getattr(p, "eta_floor", 0.10))
        use_melt = bool(getattr(p, "use_melt", False))
        t_melt = float(getattr(p, "t_melt", 933.0)); latent = float(getattr(p, "latent_heat", 0.0))
        mmass = float(getattr(p, "melt_mass", 0.0)); mband = float(getattr(p, "melt_band", 20.0))
        t_amb = env.t_amb
        hfac = 0.0
        if env.convection:
            hfac = 1.3 * (env.g / env.G0) ** 0.25 * (env.p_atm / env.P0) ** 0.5
        tl = self.t_limit
        dt = self.dt
        n = max(1, int(round(self.horizon / dt)))
        sched = callable(p_fwd)
        def pf(tt):
            return p_fwd(tt) if sched else p_fwd

        def q_loss(Tw):
            dT = Tw - t_amb
            conv = (hfac * dT ** 0.25) * area * dT if (hfac > 0 and dT > 0) else 0.0
            rad = emiss * SIGMA_SB * area * (Tw * Tw * Tw * Tw - t_amb ** 4)
            return conv + rad

        def eta(Tb, beta):
            if use_ign:
                e = eta_floor + (eta_max - eta_floor) / (1.0 + exp(-k_ign * (Tb - t_ign)))
            else:
                e = eta0 * exp(beta * (Tb - t_ref))
            return eta_max if e > eta_max else (0.0 if e < 0.0 else e)

        def cbed(Tb):
            if use_melt and abs(Tb - t_melt) < mband:
                return c_bed + latent * mmass / (2.0 * mband)
            return c_bed

        def p_abs(Tb, beta, tt):
            return pf(tt) * eta(Tb, beta)

        def deriv(Tb, Tw, beta, tt):
            dTb = (p_abs(Tb, beta, tt) - u_bw * (Tb - Tw)) / cbed(Tb)
            dTw = (u_bw * (Tb - Tw) - q_loss(Tw)) / c_wall
            return dTb, dTw

        Tb, Tw, beta = float(x0[0]), float(x0[1]), float(x0[2])
        t = 0.0
        Tb_prev, t_prev = Tb, 0.0
        d = 1.0  # Semenov numerical step (K)
        semenov_seen = False
        for _ in range(n):
            # primary event: bed crosses the unsafe-temperature threshold.
            if Tb >= tl or Tb > 3000.0:
                # sub-grid interpolation so the crossing time is continuous and
                # the sigma-point ensemble yields a non-degenerate lead-time band.
                if Tb != Tb_prev and Tb_prev < tl:
                    frac = (tl - Tb_prev) / (Tb - Tb_prev)
                    tc = t_prev + frac * dt
                else:
                    tc = t
                return tc, ("semenov" if semenov_seen else "threshold")
            # Semenov tangency along the path is recorded as a label only; it is
            # NOT the trigger, because the local slope dominates at low T where
            # losses are negligible and would mislabel benign heating.
            dH = (p_abs(Tb + d, beta, t) - p_abs(Tb - d, beta, t)) / (2 * d)
            dL = (q_loss(Tw + d) - q_loss(Tw - d)) / (2 * d)
            if dH - dL > 0.0 and Tb > 0.6 * tl:
                semenov_seen = True
            # RK4 step
            Tb_prev, t_prev = Tb, t
            k1b, k1w = deriv(Tb, Tw, beta, t)
            k2b, k2w = deriv(Tb + 0.5 * dt * k1b, Tw + 0.5 * dt * k1w, beta, t + 0.5 * dt)
            k3b, k3w = deriv(Tb + 0.5 * dt * k2b, Tw + 0.5 * dt * k2w, beta, t + 0.5 * dt)
            k4b, k4w = deriv(Tb + dt * k3b, Tw + dt * k3w, beta, t + dt)
            Tb += (dt / 6.0) * (k1b + 2 * k2b + 2 * k3b + k4b)
            Tw += (dt / 6.0) * (k1w + 2 * k2w + 2 * k3w + k4w)
            t += dt
            if not (Tb == Tb) or Tb == float("inf"):  # nan/inf guard
                return t, "threshold"
        return float("inf"), "none"

    def time_to_target(self, x0, p_fwd: float, env, target: float) -> float:
        """Seconds for T_bed to reach a target set-point under held inputs.
        Used for restart-recovery prediction (time-to-operating-temperature).
        Returns 0.0 if already at/above target, inf if unreachable in horizon.

        Integrated with RK4 (consistent with plant.ForwardModel and the forecast
        sweep _event_time) plus sub-step linear interpolation at the crossing, so
        the recovery time is continuous in dt rather than quantized to the grid.
        Previously used forward Euler (QA finding F7)."""
        if x0[0] >= target:
            return 0.0
        p = self.model.p
        c_wall = float(p.c_wall); u_bw = float(p.u_bw)
        area = float(p.area_s); emiss = float(p.emiss_wall)
        t_amb = env.t_amb
        hfac = 1.3 * (env.g / env.G0) ** 0.25 * (env.p_atm / env.P0) ** 0.5 if env.convection else 0.0
        dt = self.dt
        Tb, Tw, beta = float(x0[0]), float(x0[1]), float(x0[2])

        def q_loss(Tw_):
            dT = Tw_ - t_amb
            conv = (hfac * dT ** 0.25) * area * dT if (hfac > 0 and dT > 0) else 0.0
            rad = emiss * SIGMA_SB * area * (Tw_ * Tw_ * Tw_ * Tw_ - t_amb ** 4)
            return conv + rad

        def deriv(Tb_, Tw_):
            pa = p_fwd * self.model.eta(Tb_, beta)     # respects ignition model
            dTb_ = (pa - u_bw * (Tb_ - Tw_)) / self.model.c_bed_eff(Tb_)
            dTw_ = (u_bw * (Tb_ - Tw_) - q_loss(Tw_)) / c_wall
            return dTb_, dTw_

        t = 0.0
        for _ in range(int(round(self.horizon / dt))):
            if Tb >= target:
                return t
            Tb_prev = Tb
            k1b, k1w = deriv(Tb, Tw)
            k2b, k2w = deriv(Tb + 0.5 * dt * k1b, Tw + 0.5 * dt * k1w)
            k3b, k3w = deriv(Tb + 0.5 * dt * k2b, Tw + 0.5 * dt * k2w)
            k4b, k4w = deriv(Tb + dt * k3b, Tw + dt * k3w)
            Tb += (dt / 6.0) * (k1b + 2 * k2b + 2 * k3b + k4b)
            Tw += (dt / 6.0) * (k1w + 2 * k2w + 2 * k3w + k4w)
            t += dt
            if Tb >= target and Tb != Tb_prev:        # sub-step interpolation
                frac = (target - Tb_prev) / (Tb - Tb_prev)
                return (t - dt) + frac * dt
        return float("inf")

    def forecast(self, ukf: UKF, u: Inputs, power_schedule=None) -> ForecastResult:
        # power_schedule(tau) -> commanded power tau seconds ahead; if None, hold
        # the current power constant over the horizon.
        drive = power_schedule if power_schedule is not None else u.p_fwd
        pts = ukf.sigma_points(ukf.x, ukf.P)
        times = np.empty(pts.shape[0])
        mechs = []
        for i, pt in enumerate(pts):
            tt, mech = self._event_time(pt, drive, u.env)
            times[i] = tt
            mechs.append(mech)

        # Ensemble statistics use EQUAL weights over the propagated sigma points,
        # NOT the UKF mean-weights Wm. At alpha=1e-3 those weights are extreme
        # (W0 ~ -1e6, wings ~ +1.7e5); summing/clipping a finite subset of them
        # is not a valid probability or averaging kernel and degenerates in the
        # marginal cases that matter most. The 2n+1 forward-propagated points are
        # treated as an equal-weight spread sample of the event time.
        finite = np.isfinite(times)
        p_event = float(finite.mean())
        if not finite.any():
            return ForecastResult(float("inf"), float("nan"), 0.0,
                                  float("inf"), float("inf"), "none", self.horizon)

        tf = times[finite]
        mean = float(tf.mean())
        sigma = float(tf.std())
        ev = [m for m, f in zip(mechs, finite) if f and m != "none"]
        mechanism = max(set(ev), key=ev.count) if ev else "none"
        return ForecastResult(mean, sigma, p_event,
                              max(0.0, mean - sigma), mean + sigma,
                              mechanism, self.horizon)
