"""
RECLAIM Predictive Engine
=========================

Simulation-independent, first-principles state estimation and forecasting for
the RECLAIM digital twin (NASA LunaRecycle Phase 2). See
`RECLAIM_Predictive_Engine_TechNote.docx` for the governing mathematics.

Layered architecture:
    config      provenance-tagged parameters + environment block
    plant       two-node energy balance, eta(T) absorption, Semenov criterion
    estimator   vendored sigma-point UKF (augmented state, online feedback ID)
    forecaster  forward-integrated lead-time t* +/- sigma
    gp          Gaussian-process discrepancy correction (reverts to physics)
    anomaly     NIS/NEES chi-square consistency + anomaly gate
    thread      self-describing state stream (Convene sensing-agent contract)
    engine      orchestration: ingest -> estimate -> forecast -> publish
    harness     synthetic plant + scenario driver (virtual prototyping / V&V)

RECLAIM Digital Twin. Author: LJW.
"""
from .config import (EngineConfig, PhysicalParams, FilterConfig, ForecastConfig,
                     EnvironmentBlock, ENVIRONMENTS, EARTH_LAB, LUNAR_HABITAT,
                     LUNAR_SURFACE, Provenance, biot_number, recommend_node_count)
from .plant import ForwardModel, Inputs
from .estimator import UKF
from .forecaster import Forecaster, ForecastResult
from .gp import GPDiscrepancy
from .anomaly import NISMonitor, ConsistencyReport, nees
from .thread import (StateStreamPublisher, StreamManifest, StateFrame,
                     VariableDescriptor, Role, default_manifest)
from .engine import PredictiveEngine, StepOutput

__version__ = "0.1.0"
__all__ = [
    "EngineConfig", "PhysicalParams", "FilterConfig", "ForecastConfig",
    "EnvironmentBlock", "ENVIRONMENTS", "EARTH_LAB", "LUNAR_HABITAT",
    "LUNAR_SURFACE", "Provenance", "biot_number", "recommend_node_count",
    "ForwardModel", "Inputs", "UKF", "Forecaster", "ForecastResult",
    "GPDiscrepancy", "NISMonitor", "ConsistencyReport", "nees",
    "StateStreamPublisher", "StreamManifest", "StateFrame",
    "VariableDescriptor", "Role", "default_manifest",
    "PredictiveEngine", "StepOutput",
]
