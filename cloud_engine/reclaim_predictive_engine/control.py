"""
RECLAIM closed-loop control & interlock—software-in-the-loop (SITL).

This module makes the digital twin BI-DIRECTIONAL and ACTUATING in simulation,
ahead of the physical CD&H integration. It is the software stand-in for the path
that will, on hardware, run Convene -> LabVIEW (cRIO) -> SSMG:

    Controller—a CD&H/LabVIEW control-policy surrogate. Consumes the
                        predictive engine's published StateFrame (advisory,
                        forecast lead time, wall/thermal margins) and emits a
                        power-setpoint command + safe-state arm. Transparent,
                        rule-based, latched. This is the PREDICTIVE, advisory-
                        derived autonomy that acts BEFORE a limit is reached.

    HardwareInterlock—an INDEPENDENT over-temperature trip that does NOT use the
                        predictive engine. It is the sole fault authority (NASA DT
                        2.5): it trips on the measured temperature alone and cannot
                        be overridden by the model. The predictive controller's job
                        is to make sure the interlock never has to fire.

The partition is the safety story: the twin can throttle/optimize and recommend
safe-state, but a dumb, independent interlock remains authoritative. SITL here
becomes hardware-in-the-loop the moment `LiveFeed` and the LabVIEW command bridge
are wired—the control law and interlock are identical.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class ControlMode(str, Enum):
    TRACK = "TRACK"          # follow operator setpoint (nominal)
    LIMIT = "LIMIT"          # cap power (caution)
    THROTTLE = "THROTTLE"    # actively reduce power (warning)
    SAFE_STATE = "SAFE_STATE"  # remove microwave power (critical / latched)


@dataclass
class Command:
    power_setpoint_W: float
    mode: ControlMode
    safe_state_armed: bool
    reason: str
    source: str = "predictive_controller"


class Controller:
    """CD&H / LabVIEW control-policy surrogate driven by the twin's advisory.

    Rules mirror the advisor ladder but ACT on the plant. Escalation is monotone
    and the safe-state is LATCHED (requires explicit operator reset), so a cooled
    plant does not re-energize into the same runaway—matching real safe-state
    semantics.
    """

    def __init__(self, operator_setpoint_W: float,
                 limit_fraction: float = 0.80,
                 throttle_fraction: float = 0.30,
                 t_crit: float = 60.0, t_warn: float = 180.0):
        self.setpoint = float(operator_setpoint_W)
        self.limit_fraction = limit_fraction
        self.throttle_fraction = throttle_fraction
        self.t_crit = t_crit
        self.t_warn = t_warn
        self._latched = False           # safe-state latch
        self._latch_reason = ""

    def reset(self):
        self._latched = False
        self._latch_reason = ""

    def command(self, v: dict) -> Command:
        """Map a published StateFrame value-dict to a power command."""
        if self._latched:
            return Command(0.0, ControlMode.SAFE_STATE, True,
                           f"latched: {self._latch_reason}")

        sev = v.get("advisory_severity", "NOMINAL")
        ts = v.get("t_star", float("inf"))
        ts = float(ts) if (ts is not None and math.isfinite(float(ts))) else float("inf")
        pe = float(v.get("p_event", 0.0) or 0.0)
        wmar = float(v.get("wall_margin_K", 1e9))
        twc = v.get("t_wall_cross", float("inf"))
        twc = float(twc) if (twc is not None and math.isfinite(float(twc))) else float("inf")

        # CRITICAL -> latch safe-state (predictive intervention, ahead of the trip)
        critical = (sev == "CRITICAL") or (pe > 0.5 and ts <= self.t_crit) \
            or (wmar <= 0.0) or (twc <= self.t_crit)
        if critical:
            self._latched = True
            self._latch_reason = (f"predicted runaway t*={ts:.0f}s p={pe:.0%}"
                                  if math.isfinite(ts) else "wall/limit breach imminent")
            return Command(0.0, ControlMode.SAFE_STATE, True,
                           f"safe-state: {self._latch_reason}")

        # WARNING -> throttle hard (drop below the positive-feedback threshold)
        if (sev == "WARNING") or (pe > 0.5 and ts <= self.t_warn) or (twc <= self.t_warn):
            return Command(self.throttle_fraction * self.setpoint, ControlMode.THROTTLE,
                           False, f"throttle: runaway approaching (t*={ts:.0f}s)")

        # CAUTION -> cap power
        if sev == "CAUTION":
            return Command(self.limit_fraction * self.setpoint, ControlMode.LIMIT,
                           False, "limit: margin narrowing")

        # NOMINAL -> track operator setpoint
        return Command(self.setpoint, ControlMode.TRACK, False, "track operator setpoint")


class HardwareInterlock:
    """Independent over-temperature trip—the sole fault authority.

    Deliberately simple and model-free: it sees only the measured temperatures and
    trips when either crosses its hard limit. It is latched and cannot be cleared by
    the predictive layer. This is the backstop the predictive controller is designed
    to keep from ever firing.
    """

    def __init__(self, bed_limit_K: float, wall_limit_K: float = 1.0e9):
        self.bed_limit = float(bed_limit_K)
        self.wall_limit = float(wall_limit_K)
        self.tripped = False
        self.trip_reason = ""
        self.trip_time = None

    def check(self, t: float, T_bed_meas: float, T_wall_meas: float = -1e9) -> bool:
        if self.tripped:
            return True
        if T_bed_meas >= self.bed_limit:
            self.tripped = True; self.trip_time = t
            self.trip_reason = f"bed {T_bed_meas:.0f}K >= {self.bed_limit:.0f}K"
        elif T_wall_meas >= self.wall_limit:
            self.tripped = True; self.trip_time = t
            self.trip_reason = f"wall {T_wall_meas:.0f}K >= {self.wall_limit:.0f}K"
        return self.tripped
