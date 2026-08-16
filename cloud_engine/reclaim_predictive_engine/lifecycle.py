"""
Per-chamber cycle lifecycle — the autonomous idle/running/suspended state machine.

Design of record: docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md §4.1.

The predictive engine runs continuously and must never require a manual reset. This
FSM gives each chamber engine an explicit lifecycle inferred from telemetry it
already receives (sequencer op_state, cycle_id, forward power, bed temperature), so
per-cycle analytics reset themselves at real batch boundaries — with no operator
step, and without touching the ingest/validation/identity pipeline.

Governing principle — the RESET AUTHORITY is *batch identity*, never a power edge
and never run_id:

  * A power edge cannot trigger a reset: a mid-run power cut and a finished batch
    look identical if you only watch power, yet they are opposite events. The three
    low-power situations IDLE / SUSPENDED / COOLDOWN must never be collapsed.
  * run_id cannot trigger a reset: a gateway/cRIO reboot is a transport event that
    can happen mid-batch. Identity churn is guarded against (see below).
  * The trigger is a change in batch identity (cycle_id), bracketed physically by a
    load -> unload sequence and protected by a batch-present latch.

Phases: IDLE, LOADING, ACTIVE, COOLDOWN, SUSPENDED, COMPLETE. Each chamber runs its
own instance, so "one chamber runs a cycle" and "both in short succession" need no
special handling.

RECLAIM Digital Twin. Author: LJW (engine lifecycle reconciliation, 2026-08).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LifecycleConfig:
    """Tunable behavior (config, not code). Defaults track the thread.py state
    vocabulary; confirm the sets and thresholds against the real sequencer."""
    power_on_w: float = 50.0          # forward power above this = "powered"
    ambient_k: float = 300.0          # reference ambient
    hot_margin_k: float = 40.0        # bed > ambient+this = "hot / batch in progress"
    # op_state category sets (source_op_state, the sequencer's authoritative label)
    load_states: frozenset = field(default_factory=lambda: frozenset({"S_BatchLoad"}))
    process_states: frozenset = field(default_factory=lambda: frozenset({
        "S_SealCheck", "S_Evacuate", "S_ChamberSelect",
        "S_MicrowaveHeating", "S_MetalsCast", "S_PlasticsCollect"}))
    cooldown_states: frozenset = field(default_factory=lambda: frozenset({"S_CoolDown"}))
    complete_states: frozenset = field(default_factory=lambda: frozenset({"S_Complete", "S_Unload"}))
    # SUSPEND = power interrupted mid-batch: HOLD state, never reset, resume in place.
    suspend_states: frozenset = field(default_factory=lambda: frozenset({
        "S_PowerInterrupted", "S_Restart", "S_SafeState"}))
    idle_states: frozenset = field(default_factory=lambda: frozenset({"S_Idle"}))


@dataclass
class LifecycleResult:
    phase: str
    new_cycle: bool      # True on the frame where a new batch begins -> reset_cycle()
    suspended: bool      # True while power is interrupted mid-batch (held, no reset)


class CycleLifecycle:
    """One chamber's lifecycle FSM. Pure bookkeeping: the engine acts on
    `new_cycle` by calling its own reset_cycle(); this class holds no engine state."""

    PHASES = ("IDLE", "LOADING", "ACTIVE", "COOLDOWN", "SUSPENDED", "COMPLETE")

    def __init__(self, cfg: Optional[LifecycleConfig] = None):
        self.cfg = cfg or LifecycleConfig()
        self.phase = "IDLE"
        self.batch_present = False
        self.last_cycle_id: Optional[str] = None
        self._suspended = False
        # published durations
        self.cycle_elapsed_s = 0.0    # wall-clock since batch load (counts through suspends)
        self.active_heating_s = 0.0   # accumulated powered time only (pauses on suspend)

    def _category(self, op: str) -> str:
        c = self.cfg
        if op in c.suspend_states:
            return "SUSPEND"
        if op in c.complete_states:
            return "COMPLETE"
        if op in c.load_states:
            return "LOAD"
        if op in c.cooldown_states:
            return "COOLDOWN"
        if op in c.process_states:
            return "PROCESS"
        if op in c.idle_states:
            return "IDLE"
        return "UNKNOWN"

    def update(self, *, op_state: Optional[str], cycle_id, p_fwd, t_bed, dt: float) -> LifecycleResult:
        cfg = self.cfg
        op = op_state or "S_Unknown"
        cat = self._category(op)
        powered = (p_fwd is not None) and (float(p_fwd) > cfg.power_on_w)
        hot = (t_bed is not None) and (float(t_bed) > cfg.ambient_k + cfg.hot_margin_k)
        cid = str(cycle_id) if cycle_id not in (None, "") else None

        # 1) SUSPEND has highest precedence. Hold everything; never reset. The batch
        #    is still physically present, so the latch stays set and we resume in place.
        if cat == "SUSPEND":
            self._suspended = True
            self.phase = "SUSPENDED"
            if self.batch_present:
                self.cycle_elapsed_s += dt      # wall-clock keeps running through the outage
            return LifecycleResult(self.phase, new_cycle=False, suspended=True)
        was_suspended = self._suspended
        self._suspended = False

        # 2) New-cycle detection = batch identity turnover, guarded against churn.
        new_cycle = False
        if cid is not None and cid != self.last_cycle_id:
            # Identity-churn guard: a still-hot, in-progress batch that merely resumes
            # (e.g. a cRIO reset renumbered cycle_id) must NOT read as a new batch.
            # A genuine new batch enters via LOAD/COMPLETE or from a cold chamber.
            churn_resume = (hot and self.batch_present
                            and cat not in ("LOAD", "COMPLETE")
                            and (was_suspended or powered or cat in ("PROCESS", "COOLDOWN")))
            new_cycle = not churn_resume
        elif cid is None and cat == "LOAD" and not self.batch_present:
            new_cycle = True                     # legacy / no-cycle_id fallback

        if cid is not None:
            self.last_cycle_id = cid

        if new_cycle:
            self.batch_present = True
            self.cycle_elapsed_s = 0.0
            self.active_heating_s = 0.0

        # 3) Batch-present latch: set on load/process/cooldown, cleared ONLY on a
        #    qualified completion. A power loss never clears it (handled above).
        if cat in ("LOAD", "PROCESS", "COOLDOWN"):
            self.batch_present = True
        elif cat == "COMPLETE":
            self.batch_present = False

        # 4) Phase resolution + duration accounting.
        if self.batch_present:
            self.cycle_elapsed_s += dt
            if powered:
                self.active_heating_s += dt
                self.phase = "ACTIVE"
            elif cat == "LOAD":
                self.phase = "LOADING"
            elif cat == "COOLDOWN" or hot:
                self.phase = "COOLDOWN"
            else:
                self.phase = "LOADING"
        else:
            self.phase = "COMPLETE" if cat == "COMPLETE" else "IDLE"

        return LifecycleResult(self.phase, new_cycle=new_cycle, suspended=False)
