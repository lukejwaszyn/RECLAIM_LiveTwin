"""
Advisory / decision-support layer—the co-pilot voice.

This is the top of the predictive stack. It does not run any new estimation; it
*synthesizes* the outputs of the layers below (forecast, residuals, anomaly,
seal, thermal margin) into a single ranked, explainable recommendation, plus a
model-trust score telling the operator how much to weight the advice. It is
advisory only—strictly partitioned from the hardware interlock, which remains
the sole fault authority (NASA DT template 2.5).

Defensibility: every advisory is a transparent rule over a named signal and
carries its triggering evidence—there is no opaque scoring. Trust degrades
automatically when the filter is statistically inconsistent (NIS hot) or drifting
(CUSUM high), so the co-pilot tells you when to distrust the co-pilot.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math

# severity ladder (low -> high)
SEVERITY = ["NOMINAL", "CAUTION", "WARNING", "CRITICAL"]
CHI2_GATE_2DOF = 9.21   # 99% gate, 2 measurements


@dataclass
class Advisory:
    severity: str
    action: str
    message: str
    trigger: str          # the named signal that fired (evidence)
    trust: float          # model-trust [0,1]

    def to_dict(self):
        return asdict(self)


class Advisor:
    def __init__(self, t_crit: float = 60.0, t_warn: float = 180.0,
                 margin_warn_K: float = 150.0, seal_limit_pa: float = 500.0,
                 cusum_limit: float = 6.0,
                 wall_warn_K: float = 40.0, wall_caution_K: float = 90.0,
                 unexplained_warn_Kps: float = 0.8, unexplained_crit_Kps: float = 2.0):
        self.t_crit = t_crit
        self.t_warn = t_warn
        self.margin_warn = margin_warn_K
        self.seal_limit = seal_limit_pa
        self.cusum_limit = cusum_limit
        # hard chamber-wall material limit (e.g. 304L 700 C) caution/warn bands
        self.wall_warn = wall_warn_K
        self.wall_caution = wall_caution_K
        # measured-acceleration trigger bands (K/s). The runaway residual r =
        # measured dT/dt - power-driven model rate; sustained above these means the
        # bed gains heat the input power cannot explain (exotherm/mass-loss) -> a
        # forecast-independent runaway precursor the adaptive filter cannot mask.
        self.unexplained_warn = unexplained_warn_Kps
        self.unexplained_crit = unexplained_crit_Kps

    def trust(self, v: dict) -> float:
        """Model trust in [0,1]: degrades when the filter is inconsistent (NIS
        above its chi-square gate) or drifting (CUSUM rising)."""
        nis = float(v.get("nis", 0.0))
        cusum = float(v.get("cusum", 0.0))
        t_nis = 1.0 - max(0.0, nis - CHI2_GATE_2DOF) / 20.0
        t_drift = 1.0 - cusum / 12.0
        return round(max(0.0, min(t_nis, t_drift, 1.0)), 2)

    def assess(self, v: dict) -> Advisory:
        trust = self.trust(v)
        ts = v.get("t_star")
        ts_ok = ts is not None and isinstance(ts, (int, float)) and math.isfinite(ts)
        pe = float(v.get("p_event", 0.0) or 0.0)
        margin = float(v.get("thermal_margin_K", 1e9))
        seal = float(v.get("seal_residual", 0.0) or 0.0)
        nis = float(v.get("nis", 0.0))
        cusum = float(v.get("cusum", 0.0))
        wmar = float(v.get("wall_margin_K", 1e9))
        twc = v.get("t_wall_cross")
        twc = float(twc) if (twc is not None and math.isfinite(float(twc))) else float("inf")
        unexplained = float(v.get("unexplained_rate_Kps", 0.0) or 0.0)

        # --- NIS-conditioned conservatism (does NOT touch the physics) ----------
        # When the filter is statistically inconsistent (NIS above its chi-square
        # gate) the model is demonstrably wrong -> an unmodeled exotherm/mass-loss
        # is present and the forecast is biased LATE. We therefore (a) widen the
        # forecast warning windows so warnings fire earlier, and (b) lower the
        # unexplained-heating trigger thresholds. aggr=0 when consistent (no change
        # to nominal behaviour); ->1 when badly inconsistent.
        aggr = max(0.0, min(1.0, (nis - CHI2_GATE_2DOF) / 12.0))
        t_crit_eff = self.t_crit * (1.0 + 1.0 * aggr)
        t_warn_eff = self.t_warn * (1.0 + 1.0 * aggr)
        u_warn = self.unexplained_warn * (1.0 - 0.5 * aggr)
        u_crit = self.unexplained_crit * (1.0 - 0.5 * aggr)

        # priority order: wall over hard limit > imminent runaway (forecast OR
        #   measured-acceleration) > wall imminent > approaching runaway > ... .
        # The 304L wall limit is a HARD ceiling (loss-of-chamber), so an actual or
        # imminent breach ranks with thermal runaway.
        if wmar <= 0.0:
            return Advisory("CRITICAL", "Remove microwave power immediately",
                            f"Chamber wall OVER material limit by {-wmar:.0f} K (304L 700 C)",
                            "wall_margin_K", trust)
        if ts_ok and pe > 0.5 and ts <= t_crit_eff:
            return Advisory("CRITICAL", "Reduce forward power; arm safe-state",
                            f"Thermal runaway predicted in {ts:.0f} s (p={pe:.0%})",
                            "forecast t* + p_event", trust)
        # measured-acceleration trigger: unexplained heating, forecast-independent.
        if unexplained >= u_crit:
            return Advisory("CRITICAL", "Reduce forward power; arm safe-state",
                            f"Bed heating {unexplained:.1f} K/s faster than power explains—likely exotherm",
                            "unexplained_rate_Kps", trust)
        if twc <= self.t_crit:
            return Advisory("CRITICAL", "Reduce power now; wall limit imminent",
                            f"304L wall limit breach predicted in {twc:.0f} s",
                            "t_wall_cross", trust)
        if ts_ok and pe > 0.5 and ts <= t_warn_eff:
            return Advisory("WARNING", "Throttle power; watch coupling (beta)",
                            f"Runaway approaching (~{ts:.0f} s, p={pe:.0%})",
                            "forecast t*", trust)
        if unexplained >= u_warn:
            return Advisory("WARNING", "Throttle power; bed hotter than model",
                            f"Bed heating {unexplained:.1f} K/s faster than power explains",
                            "unexplained_rate_Kps", trust)
        if twc <= self.t_warn or wmar < self.wall_warn:
            return Advisory("WARNING", "Throttle power; wall approaching 304L limit",
                            f"Wall near 700 C material limit ({wmar:.0f} K margin)",
                            "wall_margin_K", trust)
        if seal > self.seal_limit:
            return Advisory("WARNING", "Inspect vacuum seals; verify pump-down",
                            f"Chamber not holding vacuum (residual {seal:.0f} Pa)",
                            "seal_residual", trust)
        if cusum > self.cusum_limit:
            return Advisory("CAUTION", "Inspect sensor/coupling; predictions degraded",
                            "Slow model-data drift detected (CUSUM)", "cusum", trust)
        if v.get("nis_anomaly"):                 # debounced (sustained) breach
            return Advisory("CAUTION", "Check telemetry; filter inconsistent",
                            "Sustained innovation gate breach", "nis", trust)
        if wmar < self.wall_caution:
            return Advisory("CAUTION", "Wall margin to 304L limit narrowing",
                            f"Wall {wmar:.0f} K below 700 C service limit",
                            "wall_margin_K", trust)
        if margin < self.margin_warn:
            return Advisory("CAUTION", "Thermal margin low; ready to throttle",
                            f"Approaching surface limit ({margin:.0f} K margin)",
                            "thermal_margin_K", trust)
        return Advisory("NOMINAL", "Continue cycle",
                        "All residuals within bounds", "none", trust)
