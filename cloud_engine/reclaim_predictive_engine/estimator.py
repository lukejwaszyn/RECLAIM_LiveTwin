"""
Unscented Kalman Filter—vendored, dependency-light, inspectable.

Scaled sigma-point formulation of Wan & van der Merwe (2000). Chosen over the
EKF because the exp(beta*T) absorption term is sharply nonlinear precisely in
the runaway region, where Jacobian linearization degrades; the UT propagates
the distribution through the true nonlinearity and supplies the forecast
covariance without analytic derivatives.

The implementation is intentionally self-contained (no filterpy dependency) so
every line is auditable for the V&V record.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from typing import Callable
from collections import deque
import numpy as np


def _cholesky_psd(M: np.ndarray, jitter: float = 1e-9) -> np.ndarray:
    """Cholesky with incremental jitter for numerical positive-definiteness."""
    M = 0.5 * (M + M.T)
    for k in range(8):
        try:
            return np.linalg.cholesky(M + (jitter * (10 ** k)) * np.eye(M.shape[0]))
        except np.linalg.LinAlgError:
            continue
    # last resort: eigenvalue floor
    w, V = np.linalg.eigh(M)
    w = np.clip(w, 1e-12, None)
    return np.linalg.cholesky((V * w) @ V.T + 1e-9 * np.eye(M.shape[0]))


class UKF:
    def __init__(self, dim_x: int, dim_z: int,
                 fx: Callable[[np.ndarray, float, object], np.ndarray],
                 hx: Callable[[np.ndarray], np.ndarray],
                 Q: np.ndarray, R: np.ndarray,
                 x0: np.ndarray, P0: np.ndarray,
                 alpha: float = 1e-3, beta: float = 2.0, kappa: float = 0.0,
                 adaptive: bool = False, q_window: int = 40,
                 q_scale_bounds: tuple = (0.2, 50.0), q_adapt_rate: float = 0.05,
                 q_leak: float = 0.02):
        self.n = dim_x
        self.dim_z = dim_z
        self.fx = fx
        self.hx = hx
        self.Q = np.asarray(Q, float)
        self.R = np.asarray(R, float)
        # --- adaptive process noise (covariance matching, Mehra-style) ---
        # Over a 30-45 min run the plant drifts (bed ageing, coupling change).
        # We hold the filter consistent by scaling Q so the realized innovation
        # magnitude matches what S predicts: if NIS runs hot, inflate Q (trust
        # the model less); if cold, deflate. Keeps NIS in-band without retuning.
        self.adaptive = adaptive
        self.q_scale = 1.0
        self._q_bounds = q_scale_bounds
        self._q_rate = q_adapt_rate
        self._q_leak = q_leak         # anti-windup: leak toward neutral (q_scale=1) each adapt
        self._niswin = deque(maxlen=q_window)
        self.x = np.asarray(x0, float).copy()
        self.P = np.asarray(P0, float).copy()

        self.alpha, self.beta, self.kappa = alpha, beta, kappa
        self.lam = alpha ** 2 * (self.n + kappa) - self.n
        c = self.n + self.lam
        self.gamma = np.sqrt(c)
        self.Wm = np.full(2 * self.n + 1, 1.0 / (2 * c))
        self.Wc = self.Wm.copy()
        self.Wm[0] = self.lam / c
        self.Wc[0] = self.lam / c + (1 - alpha ** 2 + beta)

        self.nis = float("nan")   # last normalized innovation squared
        self.nees = float("nan")  # filled by harness if ground truth available

    def sigma_points(self, x: np.ndarray, P: np.ndarray) -> np.ndarray:
        S = _cholesky_psd(P)
        pts = np.zeros((2 * self.n + 1, self.n))
        pts[0] = x
        for i in range(self.n):
            pts[1 + i] = x + self.gamma * S[:, i]
            pts[1 + self.n + i] = x - self.gamma * S[:, i]
        return pts

    def predict(self, dt: float, u) -> None:
        pts = self.sigma_points(self.x, self.P)
        prop = np.array([self.fx(p, dt, u) for p in pts])
        xp = self.Wm @ prop
        Pp = (self.q_scale * self.Q).copy()   # adaptive process noise
        for i in range(prop.shape[0]):
            d = prop[i] - xp
            Pp += self.Wc[i] * np.outer(d, d)
        self.x, self.P = xp, Pp
        self._sigmas_f = prop  # cache for cross-covariance

    def update(self, z: np.ndarray, R: np.ndarray | None = None) -> None:
        R = self.R if R is None else np.asarray(R, float)
        pts = self.sigma_points(self.x, self.P)
        Z = np.array([self.hx(p) for p in pts])
        zp = self.Wm @ Z
        S = R.copy()
        Pxz = np.zeros((self.n, self.dim_z))
        for i in range(Z.shape[0]):
            dz = Z[i] - zp
            dx = pts[i] - self.x
            S += self.Wc[i] * np.outer(dz, dz)
            Pxz += self.Wc[i] * np.outer(dx, dz)
        Sinv = np.linalg.inv(S)
        K = Pxz @ Sinv
        innov = np.asarray(z, float) - zp
        self.x = self.x + K @ innov
        self.P = self.P - K @ S @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        self.nis = float(innov @ Sinv @ innov)
        self._last_innov = innov
        self._last_S = S
        # adapt Q toward consistency (target NIS = dim_z), with anti-windup.
        if self.adaptive:
            self._niswin.append(self.nis)
            if len(self._niswin) >= self._niswin.maxlen:
                # ratio = realized NIS / expected: >1 => inflate Q (trust model less).
                ratio = float(np.mean(self._niswin)) / self.dim_z
                ratio = min(max(ratio, self._q_bounds[0]), self._q_bounds[1])
                # One-step corrected scale, then LEAK toward neutral (1.0). The leak is
                # the anti-windup: when the filter is consistent (ratio~1) the scale
                # relaxes back toward 1 instead of latching at a bound after a transient
                # (fixes the q_scale saturation-lock in the lifecycle memo §3.1/R-4).
                desired = self.q_scale * ratio
                desired = (1.0 - self._q_leak) * desired + self._q_leak * 1.0
                self.q_scale = (1 - self._q_rate) * self.q_scale + self._q_rate * desired
                self.q_scale = min(max(self.q_scale, self._q_bounds[0]), self._q_bounds[1])

    def reset_adaptation(self) -> None:
        """Soft-reset the adaptive process-noise scale to neutral and clear the NIS
        window. Called at a cycle boundary (reset_cycle). The filter STATE (x, P) is
        deliberately NOT touched — the bed/wall temperatures are physical, measured,
        and continuous across batches, so the estimator self-heals via the update."""
        self.q_scale = 1.0
        self._niswin.clear()
