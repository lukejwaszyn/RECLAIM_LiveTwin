"""
Digital-thread state stream—the self-describing contract between the
predictive engine and everything downstream of it (Convene's sensing agent,
a live viewport, the logger).

Design intent (per Convene's capability model):
  * Convene has a SENSING AGENT that intelligently detects variables and
    states; it can also be mapped manually. So the stream is SELF-DESCRIBING:
    a one-time MANIFEST enumerates every variable (name, unit, dtype, role,
    semantic/SysML tag, range) and the operational-state enumeration, ahead of
    the value FRAMES. The agent introspects the manifest to auto-bind; a human
    can override the mapping in Convene's GUI.
  * Each variable carries a stable entity id that resolves to a SysML element
    in RECLAIM_MBSE_v4, so a bound variable participates in the Digital Thread
    Engine's traceability (state <-> channel <-> requirement <-> verification).
  * Frames carry an EVENT list; threshold/anomaly transitions raise events so
    Convene's change-propagation can fire.
  * The publisher is sink-agnostic: the same frames serialize to stdout, a
    file, or (later) a WebSocket/connector—no renderer is assumed.

This is a contract, not a transport. Wire it to Convene's connector or a
viewport without changing the engine.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Callable, Optional
import json
import time


SCHEMA_VERSION = "1.0"


class Role(str, Enum):
    MEASUREMENT = "measurement"  # sensor input
    ESTIMATE = "estimate"        # UKF posterior state
    UNCERTAINTY = "uncertainty"  # 1-sigma of an estimate
    RESIDUAL = "residual"        # physics residual / NIS
    FORECAST = "forecast"        # predicted quantity (e.g., lead time)
    STATE = "state"              # operational state machine label
    EVENT = "event"              # discrete transition flag


@dataclass
class VariableDescriptor:
    name: str
    unit: str
    dtype: str                 # "float" | "int" | "string" | "bool"
    role: Role
    sysml_id: str = ""         # entity id resolving to RECLAIM_MBSE_v4 element
    channel: str = ""          # SysML channel (Ch_*) if applicable
    min: Optional[float] = None
    max: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        return d


@dataclass
class StreamManifest:
    """Discoverable description emitted once (and on schema change)."""
    system: str = "RECLAIM"
    model_ref: str = "RECLAIM_MBSE_v4"
    schema_version: str = SCHEMA_VERSION
    variables: list = field(default_factory=list)   # VariableDescriptor
    states: list = field(default_factory=list)      # operational state names

    def to_json(self) -> str:
        return json.dumps({
            "type": "manifest",
            "system": self.system,
            "model_ref": self.model_ref,
            "schema_version": self.schema_version,
            "variables": [v.to_dict() for v in self.variables],
            "states": self.states,
        }, indent=2)


@dataclass
class StateFrame:
    t_sim: float                      # simulation/telemetry time, s
    values: dict                      # {variable_name: value}
    state: str = "UNKNOWN"            # current operational state
    events: list = field(default_factory=list)  # discrete event names
    wall_clock: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            "type": "frame",
            "t_sim": self.t_sim,
            "wall_clock": self.wall_clock,
            "state": self.state,
            "values": self.values,
            "events": self.events,
        })


# Default RECLAIM manifest -----------------------------------------------------
def default_manifest() -> StreamManifest:
    V, R = VariableDescriptor, Role
    variables = [
        V("T_bed_meas", "K", "float", R.MEASUREMENT, "PL-IR-001.1", "Ch_BedTemperature", 250, 1500, "IR bed surface temperature"),
        V("T_wall_meas", "K", "float", R.MEASUREMENT, "PL-IR-001", "Ch_BedTemperature", 250, 1500, "wall thermocouple"),
        V("P_fwd", "W", "float", R.MEASUREMENT, "MW-DirectionalCoupler", "Ch_ForwardPower", 0, 6500, "forward power"),
        V("P_refl", "W", "float", R.MEASUREMENT, "MW-DirectionalCoupler", "Ch_ReflectedPower", 0, 6500, "reflected power"),
        V("T_bed_est", "K", "float", R.ESTIMATE, "ThermalRunawayEstimator", "Ch_BedTemperature", 250, 1500, "UKF bed temperature"),
        V("T_wall_est", "K", "float", R.ESTIMATE, "ThermalRunawayEstimator", "", 250, 1500, "UKF wall temperature"),
        V("beta_est", "1/K", "float", R.ESTIMATE, "ThermalRunawayEstimator", "", 0, 0.05, "absorption-feedback strength (online)"),
        V("T_bed_sigma", "K", "float", R.UNCERTAINTY, "ThermalRunawayEstimator", "", 0, 200, "1-sigma bed temp"),
        V("eta_obs", "-", "float", R.RESIDUAL, "StandingWaveRatioProxy", "", 0, 1, "observed absorption efficiency"),
        V("nis", "-", "float", R.RESIDUAL, "MultiResidualEstimator", "", 0, 100, "normalized innovation squared"),
        V("q_scale", "-", "float", R.ESTIMATE, "ThermalRunawayEstimator", "", 0, 50, "adaptive process-noise scale (drift tracking)"),
        V("cusum", "-", "float", R.RESIDUAL, "MultiResidualEstimator", "", 0, 20, "CUSUM drift level on bed innovation"),
        V("seal_residual", "Pa", "float", R.RESIDUAL, "SealIntegrityResidual", "Ch_ChamberPressure", -1000, 10000, "measured pressure minus expected pump-down (vacuum leak)"),
        V("semenov_margin", "W/K", "float", R.RESIDUAL, "ThermalRunawayResidual", "", -100, 100, "dH/dT - dL/dT"),
        V("t_star", "s", "float", R.FORECAST, "RunawayThresholdCrossing", "", 0, 600, "predicted lead time to runaway"),
        V("t_star_sigma", "s", "float", R.UNCERTAINTY, "RunawayThresholdCrossing", "", 0, 300, "1-sigma of lead time"),
        V("p_event", "-", "float", R.FORECAST, "RunawayThresholdCrossing", "", 0, 1, "probability of event within horizon"),
        V("t_recover", "s", "float", R.FORECAST, "RunawayThresholdCrossing", "", 0, 600, "predicted time to operating set-point (restart recovery)"),
        V("consumed_energy_wh", "Wh", "float", R.RESIDUAL, "ConsumedEnergyIntegral", "", 0, 5000, "cycle energy from coupler"),
        V("energy_efficiency_g_per_wh", "g/Wh", "float", R.RESIDUAL, "EnergyEfficiency", "", 0, 50, "reclaimed mass per energy"),
        V("mass_efficiency", "-", "float", R.RESIDUAL, "MassEfficiency", "", 0, 1, "output/input mass"),
        V("thermal_margin_K", "K", "float", R.RESIDUAL, "ThermalMargin", "", -200, 1000, "T_limit - T_bed"),
        V("cycle_elapsed_s", "s", "float", R.RESIDUAL, "CycleDuration", "Ch_ElapsedTime", 0, 1200, "cycle elapsed time"),
        V("peak_temp_K", "K", "float", R.RESIDUAL, "ThermalMargin", "", 250, 1500, "peak bed temperature"),
        V("charge_mass_kg", "kg", "float", R.ESTIMATE, "PE_MassFlow", "", 0, 2, "live charge mass (pyrolysis decay / metals drain); 0 when mass balance off"),
        V("mode", "-", "string", R.STATE, "RECLAIM_RehearsalIdentity", "", None, None, "data mode; synthetic scenario service publishes harness"),
        V("scenario", "-", "string", R.STATE, "RECLAIM_RehearsalIdentity", "", None, None, "synthetic scenario identity when applicable"),
        V("environment", "-", "string", R.STATE, "RECLAIM_Environment", "", None, None, "physics environment identity"),
        V("speed", "x", "float", R.STATE, "RECLAIM_RehearsalIdentity", "", 0, None, "simulated seconds per wall-clock second"),
        V("op_state", "-", "string", R.STATE, "RECLAIM_OperationalStateMachine", "", None, None, "operational state"),
        V("advisory_severity", "-", "string", R.EVENT, "DecisionSupport", "", None, None, "co-pilot severity (NOMINAL/CAUTION/WARNING/CRITICAL)"),
        V("advisory_action", "-", "string", R.EVENT, "DecisionSupport", "", None, None, "recommended operator action"),
        V("advisory_message", "-", "string", R.EVENT, "DecisionSupport", "", None, None, "advisory rationale"),
        V("model_trust", "-", "float", R.RESIDUAL, "DecisionSupport", "", 0, 1, "model-trust score (degrades on inconsistency/drift)"),
        V("unexplained_rate_Kps", "K/s", "float", R.RESIDUAL, "RunawayResidual", "Ch_BedTemperature", -1, 10, "measured bed dT/dt minus power-driven model rate (filter-independent exotherm signature; PL-SR-002)"),
        V("nis_anomaly", "-", "bool", R.EVENT, "MultiResidualEstimator", "", None, None, "NIS exceeded consistency threshold (filter statistically inconsistent -> model wrong)"),
        V("t_wall_cross", "s", "float", R.FORECAST, "RunawayThresholdCrossing", "", 0, 600, "predicted lead time to chamber-wall limit crossing"),
        V("wall_limit_K", "K", "float", R.RESIDUAL, "ThermalMargin", "", 250, 1500, "chamber-wall temperature limit (material service limit; sentinel when inactive)"),
        V("wall_margin_K", "K", "float", R.RESIDUAL, "ThermalMargin", "", -200, 1000, "wall_limit_K minus estimated wall temperature"),
    ]
    states = [
        "S_Idle", "S_BatchLoad", "S_SealCheck", "S_Evacuate", "S_ChamberSelect",
        "S_MicrowaveHeating", "S_MetalsCast", "S_PlasticsCollect", "S_CoolDown",
        "S_Unload", "S_Complete", "S_SafeState", "S_PowerInterrupted", "S_Restart",
    ]
    return StreamManifest(variables=variables, states=states)


class StateStreamPublisher:
    """Sink-agnostic publisher. sink(str)->None; defaults to collecting frames."""
    def __init__(self, manifest: StreamManifest, sink: Optional[Callable[[str], None]] = None):
        self.manifest = manifest
        self.sink = sink
        self.frames: list = []          # retained when no external sink
        self._manifest_sent = False

    def emit_manifest(self) -> str:
        msg = self.manifest.to_json()
        if self.sink:
            self.sink(msg)
        self._manifest_sent = True
        return msg

    def publish(self, frame: StateFrame) -> str:
        if not self._manifest_sent:
            self.emit_manifest()
        msg = frame.to_json()
        if self.sink:
            self.sink(msg)
        else:
            self.frames.append(frame)
        return msg
