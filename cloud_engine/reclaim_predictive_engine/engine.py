"""
Predictive engine orchestration.

Per step:  ingest measurement -> UKF predict/update -> residuals & NIS
           -> (periodic) forecast lead-time -> GP discrepancy (optional)
           -> assemble self-describing StateFrame -> publish to the thread.

The engine is the physics/state PRODUCER. Convene (thread + knowledge graph +
decision intelligence) is the CONSUMER: its sensing agent binds the published
manifest/variables into the digital thread. No renderer is assumed here.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from collections import deque
import numpy as np

from .config import EngineConfig
from .plant import ForwardModel, Inputs
from .estimator import UKF
from .forecaster import Forecaster, ForecastResult
from .gp import GPDiscrepancy
from .anomaly import NISMonitor, CUSUMDetector, SealMonitor
from .metrics import PerformanceAccumulator
from .advisor import Advisor
from .lifecycle import CycleLifecycle
from .thread import (StateStreamPublisher, StateFrame, default_manifest)


@dataclass
class StepOutput:
    t: float
    x_est: np.ndarray
    P: np.ndarray
    forecast: Optional[ForecastResult]
    nis: float
    anomaly: bool
    frame: StateFrame


class PredictiveEngine:
    def __init__(self, cfg: EngineConfig, publisher: Optional[StateStreamPublisher] = None,
                 use_gp: bool = True):
        self.cfg = cfg
        self.p = cfg.physical
        self.model = ForwardModel(self.p)

        # UKF wiring -------------------------------------------------------
        fc = cfg.filt
        Q = np.diag(fc.q_diag).astype(float)
        R = np.diag(fc.r_diag).astype(float)
        P0 = np.diag(fc.p0_diag).astype(float)
        x0 = np.array([cfg.env().t_amb, cfg.env().t_amb, float(self.p.beta0)])

        def fx(x, dt, u):
            return self.model.step(x, u, dt)

        def hx(x):
            return self.model.measure(x)

        self.ukf = UKF(dim_x=3, dim_z=2, fx=fx, hx=hx, Q=Q, R=R, x0=x0, P0=P0,
                       alpha=fc.alpha, beta=fc.beta_ukf, kappa=fc.kappa,
                       adaptive=fc.adaptive, q_window=fc.q_window)

        # downstream layers ------------------------------------------------
        self.forecaster = Forecaster(self.model, t_limit=float(self.p.t_limit),
                                     horizon=cfg.forecast.horizon, dt=cfg.forecast.dt)
        self.nis_mon = NISMonitor(dim_z=2, alpha=0.01)
        self.cusum = CUSUMDetector()
        self.seal = SealMonitor()
        self.perf = PerformanceAccumulator()
        self.advisor = Advisor()
        self.gp = GPDiscrepancy() if use_gp else None
        # bounded window: recent residuals only -> fits stay O(window^3), realtime-safe
        self._gp_X: deque = deque(maxlen=80)
        self._gp_r: deque = deque(maxlen=80)
        # measurement window for the runaway residual (measured dT/dt vs the
        # power-driven rate the model predicts). Filter-independent on purpose: the
        # adaptive UKF would otherwise absorb an unmodeled exotherm into Q and hide
        # it. Stores (t, z_bed, z_wall, p_fwd).
        self._meas_win: deque = deque(maxlen=10)

        # autonomous per-chamber lifecycle: infers idle/running/suspended and the
        # real batch boundaries from telemetry, so per-cycle analytics reset
        # themselves — no manual reset per run (lifecycle memo §4.1).
        self.lifecycle = CycleLifecycle(getattr(cfg, "lifecycle", None))

        self.publisher = publisher or StateStreamPublisher(default_manifest())
        self.publisher.emit_manifest()

        self._k = 0
        self.last_forecast: Optional[ForecastResult] = None
        self._last_op_state: Optional[str] = None   # for seal-monitor phase gating

    # ----------------------------------------------------------------------
    def reset_cycle(self) -> None:
        """Re-initialize per-cycle analytics at a real batch boundary. Called by the
        lifecycle FSM's new-cycle edge — never by an operator. Resets ONLY analytics;
        the UKF state (x, P) is left to track the measured, continuous plant."""
        self.perf.reset()
        self.cusum.reset()
        self.nis_mon.reset()
        self.ukf.reset_adaptation()      # q_scale -> 1.0, clear NIS window (anti-windup)
        self.model.recharge()            # re-seed charge mass for the new batch
        self._meas_win.clear()
        self._gp_X.clear()
        self._gp_r.clear()

    # states during which the pump-down curve comparison is physically meaningful
    _SEAL_STATES = ("S_Evacuate", "S_SealCheck")

    # ----------------------------------------------------------------------
    def step(self, t: float, z, p_fwd: float, p_refl: float = 0.0,
             op_state: str = "S_MicrowaveHeating", extra_events=None,
             power_schedule=None, p_chamber=None, dt: float | None = None,
             system_op_state: str | None = None, cycle_id=None) -> StepOutput:
        """Advance one telemetry step.

        `dt` is the REAL elapsed time (s) since the previous accepted frame,
        derived from source timestamps by the caller. When None, the nominal
        cfg.filt.dt is used (synthetic/harness feeds at fixed rate). Fix H1:
        live physics must integrate at the actual telemetry cadence, not an
        assumed 1 Hz.

        `system_op_state` is the sequencer's SYSTEM state, used for
        phase-gating the seal monitor. It matters because `op_state` here may
        be the chamber-local label, which relabels zero-power phases
        (S_Evacuate has no forward power) as S_Idle — gating on it would blind
        the seal check during the very phase it exists for.
        """
        cfg = self.cfg
        step_dt = float(dt) if dt is not None and dt > 0.0 else cfg.filt.dt
        u = Inputs(p_fwd=p_fwd, env=cfg.env(), p_refl=p_refl)

        # --- autonomous lifecycle: idle/running/suspended + real batch boundaries ---
        # Uses the sequencer's authoritative op_state, cycle_id, power, and the
        # MEASURED bed temperature. A new-cycle edge resets per-cycle analytics only;
        # a power interruption holds state and never resets (lifecycle memo §4.1).
        life = self.lifecycle.update(op_state=(system_op_state or op_state),
                                     cycle_id=cycle_id, p_fwd=p_fwd,
                                     t_bed=float(z[0]), dt=step_dt)
        if life.new_cycle:
            self.reset_cycle()

        self.ukf.predict(step_dt, u)
        self.ukf.update(np.asarray(z, float))

        nis = self.ukf.nis
        breach = self.nis_mon.update(nis)
        anomaly = self.nis_mon.anomaly()
        # runaway residual (T-05): r = (observed dT_b/dt) - (power-driven model rate).
        # The observed rate is the slope of the FILTERED bed estimate (the UKF tracks
        # the true bed even when it mis-models the rate, but with the 2 K sensor noise
        # removed, so the rate is clean); the model rate is what the input power alone
        # explains. Positive and sustained => heat the power cannot account for
        # (exotherm / mass-loss)—forecast-independent and not maskable by adaptive Q.
        xb, xw, xbeta = float(self.ukf.x[0]), float(self.ukf.x[1]), float(self.ukf.x[2])
        self._meas_win.append((t, xb, xw, float(p_fwd)))
        unexplained_rate = 0.0
        if len(self._meas_win) >= 5:
            ts_ = np.array([w[0] for w in self._meas_win])
            xb_ = np.array([w[1] for w in self._meas_win])
            obs_rate = float(np.polyfit(ts_ - ts_[0], xb_, 1)[0])      # filtered slope, K/s
            p_abs = float(p_fwd) * self.model.eta(xb, xbeta)
            model_rate = (p_abs - float(self.p.u_bw) * (xb - xw)) / self.model.c_bed_eff(xb)
            unexplained_rate = obs_rate - model_rate
        # slow-drift detection (CUSUM on standardized bed innovation)
        z_std = float(self.ukf._last_innov[0] / np.sqrt(max(self.ukf._last_S[0, 0], 1e-9)))
        drift = self.cusum.update(z_std)
        # vacuum seal-integrity residual (Pa). Phase-gated (fix C5): evaluated
        # only during evacuation/seal-check, re-anchored at each S_Evacuate
        # entry so the expected pump-down curve starts when pump-down starts.
        # p_chamber arrives in Pa — push_ingest_dual converts from the kPa
        # canonical unit before calling.
        seal_resid = 0.0; seal_breach = False
        seal_op = system_op_state or op_state
        in_seal_phase = seal_op in self._SEAL_STATES
        if in_seal_phase and self._last_op_state not in self._SEAL_STATES:
            self.seal.reset()
        if p_chamber is not None and in_seal_phase:
            seal_resid = self.seal.residual(t, p_chamber)
            seal_breach = self.seal.breach(t, p_chamber)
        self._last_op_state = seal_op

        # GP discrepancy bookkeeping (innovation as residual proxy)
        if self.gp is not None:
            self._gp_X.append([self.ukf.x[0]])
            self._gp_r.append(float(self.ukf._last_innov[0]))
            if len(self._gp_r) >= 8 and self._k % 16 == 0:
                self.gp.fit(np.array(self._gp_X), np.array(self._gp_r))

        # periodic forecast
        fr = None
        if self._k % max(1, cfg.forecast.every) == 0:
            fr = self.forecaster.forecast(self.ukf, u, power_schedule=power_schedule)
            self.last_forecast = fr
        self._k += 1

        x = self.ukf.x
        sig = np.sqrt(np.clip(np.diag(self.ukf.P), 0, None))
        eta_obs = self.model.eta_measured(p_fwd, p_refl)
        sem = self.model.semenov_margin(x, u)

        # HARD wall material limit (304L 700 C for the plastics chamber): margin
        # on the wall node and a model-based time-to-breach from the current wall
        # heating rate (cheap predictive lead time, no extra sigma sweep).
        wall_limit = float(self.p.t_wall_limit)
        wall_margin = wall_limit - float(x[1])
        dTw_dt = float(self.model.deriv(x, u)[1])
        t_wall_cross = (wall_margin / dTw_dt) if (dTw_dt > 1e-6 and wall_margin > 0.0) else float("inf")

        # performance accounting + restart-recovery forecast. Gated to batch-present:
        # during IDLE the accumulators freeze so metrics hold the last completed
        # cycle's values instead of drifting between batches (lifecycle memo §4.1).
        if self.lifecycle.batch_present:
            self.perf.update(t, p_fwd, p_refl, x[0])
        perf = self.perf.metrics(float(self.p.t_limit), x[0])
        t_recover = self.forecaster.time_to_target(x, u.p_fwd, u.env, float(self.p.t_operate))

        events = list(extra_events) if extra_events else []
        if breach:
            events.append("NIS_BREACH")
        if drift:
            events.append("DRIFT")
        if seal_breach:
            events.append("SEAL_LEAK")
        if anomaly:
            events.append("ANOMALY")
        if self.last_forecast and np.isfinite(self.last_forecast.t_star):
            if self.last_forecast.t_star <= 30.0:
                events.append("RUNAWAY_IMMINENT")

        lf = self.last_forecast
        vals = {
                "T_bed_meas": float(z[0]),
                "T_wall_meas": float(z[1]),
                "P_fwd": float(p_fwd),
                "P_refl": float(p_refl),
                "T_bed_est": float(x[0]),
                "T_wall_est": float(x[1]),
                "beta_est": float(x[2]),
                "T_bed_sigma": float(sig[0]),
                "eta_obs": eta_obs,
                "nis": float(nis),
                "nis_anomaly": bool(anomaly),
                "unexplained_rate_Kps": float(unexplained_rate),
                "q_scale": float(self.ukf.q_scale),
                "cusum": float(self.cusum.level()),
                "seal_residual": float(seal_resid),
                "semenov_margin": float(sem),
                "wall_limit_K": wall_limit,
                "wall_margin_K": float(wall_margin),
                "t_wall_cross": float(t_wall_cross),
                "t_star": float(lf.t_star) if lf else float("inf"),
                "t_star_sigma": float(lf.t_star_sigma) if lf else float("nan"),
                "p_event": float(lf.p_event) if lf else 0.0,
                "t_recover": float(t_recover),
                "consumed_energy_wh": perf["consumed_energy_wh"],
                "energy_efficiency_g_per_wh": perf["energy_efficiency_g_per_wh"],
                "mass_efficiency": perf["mass_efficiency"],
                "thermal_margin_K": perf["thermal_margin_K"],
                # lifecycle durations: wall-clock through suspends vs powered-only time
                "cycle_elapsed_s": float(self.lifecycle.cycle_elapsed_s),
                "active_heating_s": float(self.lifecycle.active_heating_s),
                "engine_phase": life.phase,
                "peak_temp_K": perf["peak_temp_K"],
                "charge_mass_kg": float(self.model._mf_mass) if self.model._mf_mass is not None else 0.0,
                "op_state": op_state,
        }
        adv = self.advisor.assess(vals)
        vals["advisory_severity"] = adv.severity
        vals["advisory_action"] = adv.action
        vals["advisory_message"] = adv.message
        vals["model_trust"] = adv.trust
        self.last_advisory = adv
        frame = StateFrame(t_sim=t, state=op_state, events=events, values=vals)
        self.publisher.publish(frame)

        # advance the live charge mass one step (deterministic companion to the UKF;
        # uses the current bed estimate). Pyrolysis: first-order Arrhenius decay;
        # metals: drain once molten. C_b(t) falls accordingly on the next step.
        if self.model._mf_mass is not None and self.model._mf_mass > 0.0:
            p = self.p
            Tb = float(x[0]); m = float(self.model._mf_mass); dt = step_dt
            if p.mf_mode == "pyrolysis":
                dm = -float(p.mf_k0) * np.exp(-float(p.mf_ea) / (8.314462618 * max(Tb, 1.0))) * m
            elif p.mf_mode == "drain":
                dm = -float(p.mf_k_drain) * max(0.0, Tb - float(p.t_melt))
            else:
                dm = 0.0
            self.model._mf_mass = max(0.0, m + dm * dt)

        return StepOutput(t=t, x_est=x.copy(), P=self.ukf.P.copy(),
                          forecast=fr, nis=nis, anomaly=anomaly, frame=frame)
