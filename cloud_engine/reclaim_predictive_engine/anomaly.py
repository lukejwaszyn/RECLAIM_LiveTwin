"""
Anomaly detection and filter-consistency monitoring.

Statistical, not black-box. The Normalized Innovation Squared

    NIS_k = nu_k^T S_k^-1 nu_k  ~  chi-square(n_z)

is chi-square distributed with degrees of freedom equal to the measurement
dimension. A sustained breach of the chi-square gate signals dynamics outside
the residual bank (a fault). The same statistic averaged over a run (with its
companion NEES on state error vs the synthetic plant) is the formal evidence
that the filter is consistent—neither over- nor under-confident. One
mechanism, two scored purposes: anomaly detection and V&V.
Reference: Bar-Shalom, Li & Kirubarajan (2001).

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import numpy as np
from scipy.stats import chi2


@dataclass
class ConsistencyReport:
    avg_nis: float
    lo: float
    hi: float
    consistent: bool
    n: int


class NISMonitor:
    def __init__(self, dim_z: int, alpha: float = 0.01, window: int = 30):
        self.dim_z = dim_z
        self.alpha = alpha
        # single-sample gate (upper tail)
        self.gate = float(chi2.ppf(1.0 - alpha, dim_z))
        self.history = deque(maxlen=window)
        self.window = window
        self.consec_breach = 0

    def reset(self) -> None:
        """Clear the per-cycle NIS history and breach counter (cycle boundary)."""
        self.history.clear()
        self.consec_breach = 0

    def update(self, nis: float) -> bool:
        """Return True if this sample breaches the chi-square gate."""
        self.history.append(float(nis))
        breach = nis > self.gate
        self.consec_breach = self.consec_breach + 1 if breach else 0
        return breach

    def anomaly(self, persistence: int = 3) -> bool:
        """Anomaly declared only on a *sustained* breach (debounced)."""
        return self.consec_breach >= persistence

    def consistency(self) -> ConsistencyReport:
        """Time-averaged NIS test: N*avg ~ chi-square(N*n_z)/N two-sided band."""
        n = len(self.history)
        if n == 0:
            return ConsistencyReport(float("nan"), 0, 0, False, 0)
        avg = float(np.mean(self.history))
        lo = chi2.ppf(self.alpha / 2, n * self.dim_z) / n
        hi = chi2.ppf(1 - self.alpha / 2, n * self.dim_z) / n
        return ConsistencyReport(avg, float(lo), float(hi), lo <= avg <= hi, n)


class CUSUMDetector:
    """Two-sided cumulative-sum drift detector on standardized innovations.

    NIS flags sudden inconsistency; over a 30-45 min run the more insidious
    failure is slow drift—a small persistent bias the per-step gate never
    trips. CUSUM accumulates the standardized residual and fires when the
    running sum exceeds a threshold, catching creep the instant it becomes
    statistically undeniable. (Page 1954; standard SPC change-point test.)
    """

    def __init__(self, k: float = 0.5, h: float = 6.0):
        self.k = k          # slack (allowed drift in sigmas before accumulating)
        self.h = h          # decision threshold (sigmas of accumulated drift)
        self.reset()

    def reset(self):
        self.s_hi = 0.0
        self.s_lo = 0.0

    def update(self, z_std: float) -> bool:
        """z_std = standardized innovation (innovation / predicted std)."""
        self.s_hi = max(0.0, self.s_hi + z_std - self.k)
        self.s_lo = max(0.0, self.s_lo - z_std - self.k)
        return self.level() > self.h

    def level(self) -> float:
        return max(self.s_hi, self.s_lo)


class SealMonitor:
    """Vacuum seal-integrity residual (plastics pyrolysis path).

    Compares measured chamber pressure to the expected pump-down curve
    P_exp(t) = P_floor + (P0 - P_floor) exp(-(t-t0)/tau). A persistent positive
    residual means the chamber is not holding vacuum—a seal leak. This is the
    pressure/vacuum integrity check; it is distinct from the 5 mW/cm^2 microwave-
    leakage limit (FDA 21 CFR 1030.10 / SYS-SR-003), which is enforced by the
    hardware interlock chain and is not modeled by this thermal-pressure engine.

    ALL UNITS ARE PASCALS. Callers holding kPa (the labview_map canonical unit)
    must convert before calling (QA fix C5). The monitor is phase-gated by the
    engine: it is reset at each S_Evacuate entry so t0 anchors to the actual
    pump-down start, and it is not evaluated outside evacuation/seal-check
    states (where "measured minus pump-down curve" is meaningless and would
    false-alarm at atmospheric pressure).
    """

    def __init__(self, p0: float = 101325.0, p_floor: float = 80.0,
                 tau: float = 60.0, resid_limit: float = 500.0):
        self.p0, self.p_floor, self.tau, self.resid_limit = p0, p_floor, tau, resid_limit
        self.t0 = None

    def reset(self) -> None:
        """Re-anchor the expected pump-down curve (call at S_Evacuate entry)."""
        self.t0 = None

    def expected(self, t: float) -> float:
        if self.t0 is None:
            self.t0 = t
        return self.p_floor + (self.p0 - self.p_floor) * np.exp(-(t - self.t0) / self.tau)

    def residual(self, t: float, p_meas: float) -> float:
        return float(p_meas - self.expected(t))

    def breach(self, t: float, p_meas: float) -> bool:
        return self.residual(t, p_meas) > self.resid_limit


def nees(x_true: np.ndarray, x_est: np.ndarray, P: np.ndarray) -> float:
    """Normalized Estimation Error Squared (requires ground truth)."""
    e = np.asarray(x_true, float) - np.asarray(x_est, float)
    return float(e @ np.linalg.inv(P) @ e)
