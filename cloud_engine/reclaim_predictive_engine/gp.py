"""
Empirical discrepancy layer—Gaussian-process correction.

Physics-informed hybrid model:

    y(x) = f_physics(x; theta) + delta(x),   delta ~ GP(0, k(x,x'))

The GP is trained ONLY on the residual between measurement and physics, never
on the physics itself. Kernel = Matern-5/2 (twice-differentiable, physically
smooth) + WhiteKernel (sensor noise). Hyperparameters by marginal-likelihood
maximization (no hand tuning).

Safety property (defensible): far from the training data the covariance vector
-> 0, so the correction mean -> 0 (revert to first principles) while the
predictive variance grows (flagged low confidence). The variance is folded
into the UKF process noise so uncertain corrections are automatically
down-weighted. The physics backbone is never overridden by the data layer.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from typing import Optional
import numpy as np

try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel
    _HAVE_SKLEARN = True
except Exception:  # pragma: no cover
    _HAVE_SKLEARN = False


class GPDiscrepancy:
    def __init__(self, length_scale: float = 50.0, noise: float = 1.0):
        self.fitted = False
        self.prior_var = 1.0
        if _HAVE_SKLEARN:
            kernel = (ConstantKernel(1.0, (1e-3, 1e3))
                      * Matern(length_scale=length_scale, nu=2.5,
                               length_scale_bounds=(1e0, 1e4))
                      + WhiteKernel(noise_level=noise,
                                    noise_level_bounds=(1e-6, 1e3)))
            self.gp = GaussianProcessRegressor(
                kernel=kernel, normalize_y=True,
                n_restarts_optimizer=2, alpha=0.0)
        else:  # pragma: no cover
            self.gp = None

    def fit(self, X: np.ndarray, residual: np.ndarray) -> "GPDiscrepancy":
        X = np.atleast_2d(np.asarray(X, float))
        r = np.asarray(residual, float).ravel()
        if X.shape[0] != r.shape[0]:
            X = X.reshape(r.shape[0], -1)
        self.prior_var = float(np.var(r)) if r.size > 1 else 1.0
        if self.gp is not None and r.size >= 3:
            self.gp.fit(X, r)
            self.fitted = True
        return self

    def correct(self, x: np.ndarray):
        """Return (mu, var). Out-of-distribution -> mu~0, var->prior."""
        x = np.atleast_2d(np.asarray(x, float))
        if not self.fitted or self.gp is None:
            return 0.0, self.prior_var
        mu, std = self.gp.predict(x, return_std=True)
        return float(mu[0]), float(std[0] ** 2)

    def predict_many(self, X: np.ndarray):
        """Vectorized correction over rows of X -> (mu[], std[])."""
        X = np.atleast_2d(np.asarray(X, float))
        if not self.fitted or self.gp is None:
            return np.zeros(X.shape[0]), np.full(X.shape[0], self.prior_var ** 0.5)
        return self.gp.predict(X, return_std=True)

    # --- persistence: train offline, deploy at runtime ---------------------
    def save(self, path: str):
        import joblib
        joblib.dump({"gp": self.gp, "fitted": self.fitted,
                     "prior_var": self.prior_var}, path)

    @classmethod
    def load(cls, path: str) -> "GPDiscrepancy":
        import joblib
        d = joblib.load(path)
        obj = cls()
        obj.gp = d["gp"]; obj.fitted = d["fitted"]; obj.prior_var = d["prior_var"]
        return obj
