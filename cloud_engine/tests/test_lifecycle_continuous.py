"""
Continuous-run lifecycle contract (R-7, lifecycle memo §4.1).

Drives MULTIPLE batches — including a mid-batch power cut — through ONE engine
instance with NO rebuild, and asserts the autonomous lifecycle:

  * a power interruption (SUSPENDED) never resets: energy / active-heating /
    charge-mass carry across the outage and resume in place;
  * a new batch identity (cycle_id turnover) DOES reset per-cycle analytics:
    charge mass recharges, q_scale returns to neutral, elapsed/energy zero;
  * IDLE between batches freezes the metrics instead of drifting.

This is the test the old harness could not catch, because service.py rebuilt the
engine every cycle (memo §3.4). Here the engine persists, like production.
"""
import numpy as np
import pytest

from reclaim_predictive_engine.config import EngineConfig, chamber_params
from reclaim_predictive_engine.engine import PredictiveEngine
from reclaim_predictive_engine.thread import StateStreamPublisher, default_manifest


def _engine():
    cfg = EngineConfig(physical=chamber_params("PL"), environment="earth_lab", chamber_id="PL")
    cfg.forecast.every = 1
    pub = StateStreamPublisher(default_manifest(), sink=lambda _m: None)
    return PredictiveEngine(cfg, publisher=pub, use_gp=False)


def _step(eng, t, op, cid, p_fwd, z_bed=600.0, z_wall=450.0, dt=1.0):
    out = eng.step(t, np.array([z_bed, z_wall]), p_fwd, 0.0,
                   op_state=op, system_op_state=op, cycle_id=cid, dt=dt)
    return out.frame.values


def test_power_cut_does_not_reset_but_new_cycle_does():
    eng = _engine()
    t = 0.0

    # --- Cycle A: load then heat under power ---
    _step(eng, t, "S_BatchLoad", "A", 0.0, z_bed=310.0); t += 1
    for _ in range(20):
        v = _step(eng, t, "S_MicrowaveHeating", "A", 2000.0); t += 1
    assert v["engine_phase"] == "ACTIVE"
    heating_before_cut = eng.lifecycle.active_heating_s
    energy_before_cut = v["consumed_energy_wh"]
    mass_before_cut = eng.model._mf_mass
    assert heating_before_cut > 0.0
    assert mass_before_cut < 1.0            # pyrolysis charge has decayed within the batch

    # --- Power cut mid-batch: SUSPENDED, same cycle_id. Must NOT reset. ---
    for _ in range(10):
        v = _step(eng, t, "S_PowerInterrupted", "A", 0.0, z_bed=560.0); t += 1
    assert v["engine_phase"] == "SUSPENDED"
    # active-heating frozen through the outage; wall-clock elapsed kept counting
    assert eng.lifecycle.active_heating_s == pytest.approx(heating_before_cut)
    assert eng.lifecycle.cycle_elapsed_s > heating_before_cut
    # charge mass NOT recharged during suspension (batch still in progress)
    assert eng.model._mf_mass <= mass_before_cut + 1e-9

    # --- Resume same batch: continues, still no reset ---
    for _ in range(10):
        v = _step(eng, t, "S_MicrowaveHeating", "A", 2000.0, z_bed=620.0); t += 1
    assert v["engine_phase"] == "ACTIVE"
    assert eng.lifecycle.active_heating_s > heating_before_cut     # resumed accumulating
    assert v["consumed_energy_wh"] >= energy_before_cut            # energy carried across

    # --- Complete batch A, then load a NEW batch B: reset MUST fire ---
    _step(eng, t, "S_Complete", "A", 0.0, z_bed=500.0); t += 1
    v = _step(eng, t, "S_BatchLoad", "B", 0.0, z_bed=320.0); t += 1
    assert eng.model._mf_mass == pytest.approx(1.0)               # charge recharged (R-3)
    assert eng.ukf.q_scale == pytest.approx(1.0)                  # adaptive Q reset (R-4)
    assert eng.lifecycle.active_heating_s == pytest.approx(0.0)   # per-cycle analytics zeroed
    assert v["consumed_energy_wh"] == pytest.approx(0.0)


def test_idle_freezes_metrics():
    eng = _engine()
    t = 0.0
    _step(eng, t, "S_BatchLoad", "C", 0.0, z_bed=310.0); t += 1
    for _ in range(15):
        v = _step(eng, t, "S_MicrowaveHeating", "C", 2000.0); t += 1
    energy_at_complete = v["consumed_energy_wh"]
    _step(eng, t, "S_Complete", "C", 0.0, z_bed=480.0); t += 1

    # IDLE between batches: accumulators must hold, not climb.
    for _ in range(10):
        v = _step(eng, t, "S_Idle", "C", 0.0, z_bed=330.0); t += 1
    assert v["engine_phase"] == "IDLE"
    assert v["consumed_energy_wh"] == pytest.approx(energy_at_complete)


def test_q_scale_anti_windup_bounded():
    eng = _engine()
    t = 0.0
    # feed inconsistent (noisy) measurements to drive NIS hot, then consistent ones;
    # q_scale must stay bounded and not latch at the ceiling.
    for i in range(120):
        noise = 60.0 if i < 60 else 0.0
        z = 600.0 + noise * ((-1) ** i)
        _step(eng, t, "S_MicrowaveHeating", "Q", 2000.0, z_bed=z); t += 1
    lo, hi = eng.ukf._q_bounds
    assert lo <= eng.ukf.q_scale <= hi
    assert eng.ukf.q_scale < hi          # not saturation-locked at the bound


# ---------------------------------------------------------------------------
# Identity-churn guard (lifecycle.py §2) — the transport-event cases.
#
# A gateway/cRIO reboot can renumber cycle_id in the middle of a live batch.
# That is a TRANSPORT event, not a batch boundary: it must never reset per-cycle
# analytics. These drive the FSM directly (pure bookkeeping, no engine needed)
# so the guard's individual terms — hot, batch_present, and the category/power
# qualifier — are each pinned independently.
# ---------------------------------------------------------------------------
from reclaim_predictive_engine.lifecycle import CycleLifecycle

HOT = 600.0
COLD = 300.0


def _drive(fsm, steps):
    """steps: (op_state, cycle_id, p_fwd, t_bed) at dt=1 s. Returns each result."""
    return [fsm.update(op_state=op, cycle_id=cid, p_fwd=p, t_bed=tb, dt=1.0)
            for op, cid, p, tb in steps]


def _reset_indices(results):
    return [i for i, r in enumerate(results) if r.new_cycle]


def test_reboot_renumbering_cycle_id_mid_batch_does_not_reset():
    """cRIO reboots mid-batch and renumbers cycle_id while still hot and powered."""
    fsm = CycleLifecycle()
    res = _drive(fsm, [("S_BatchLoad", "A", 0.0, COLD)]
                 + [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 5
                 + [("S_MicrowaveHeating", "A-renumbered", 2000.0, HOT)] * 5)
    assert _reset_indices(res) == [0]          # only the genuine load
    assert fsm.batch_present is True
    assert fsm.phase == "ACTIVE"


def test_reboot_renumbering_across_power_interruption_does_not_reset():
    """The renumbering lands on the resume frame, right after an outage."""
    fsm = CycleLifecycle()
    res = _drive(fsm, [("S_BatchLoad", "A", 0.0, COLD)]
                 + [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 5
                 + [("S_PowerInterrupted", "A", 0.0, HOT)] * 3
                 + [("S_MicrowaveHeating", "B", 2000.0, HOT)] * 3)
    assert _reset_indices(res) == [0]
    assert fsm.batch_present is True


def test_restart_and_safe_state_hold_the_batch_without_resetting():
    """S_Restart / S_SafeState are suspend states: hold, never reset, resume in place."""
    for held in ("S_Restart", "S_SafeState"):
        fsm = CycleLifecycle()
        _drive(fsm, [("S_BatchLoad", "A", 0.0, COLD)]
               + [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 5)
        heating_before = fsm.active_heating_s
        res = _drive(fsm, [(held, "A", 0.0, HOT)] * 4)
        assert all(r.suspended for r in res), held
        assert all(not r.new_cycle for r in res), held
        assert fsm.phase == "SUSPENDED", held
        assert fsm.batch_present is True, held           # latch survives the hold
        # resume the same batch: still no reset, accumulation continues
        res2 = _drive(fsm, [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 3)
        assert not any(r.new_cycle for r in res2), held
        assert fsm.active_heating_s > heating_before, held


def test_batch_identity_turnover_after_completion_resets():
    """Once COMPLETE clears the latch, a new cycle_id is a real batch boundary."""
    fsm = CycleLifecycle()
    res = _drive(fsm, [("S_BatchLoad", "A", 0.0, COLD)]
                 + [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 5
                 + [("S_Complete", "A", 0.0, HOT)]
                 + [("S_BatchLoad", "B", 0.0, COLD)]
                 + [("S_MicrowaveHeating", "B", 2000.0, HOT)] * 2)
    assert _reset_indices(res) == [0, 7]
    assert fsm.batch_present is True


def test_new_cycle_id_on_cold_chamber_resets():
    """The `hot` term: a cold chamber cannot be a resuming in-progress batch."""
    fsm = CycleLifecycle()
    res = _drive(fsm, [("S_BatchLoad", "A", 0.0, COLD)]
                 + [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 3
                 + [("S_MicrowaveHeating", "B", 2000.0, COLD)] * 2)
    assert _reset_indices(res) == [0, 4]


def test_new_cycle_id_while_hot_without_a_load_is_suppressed_by_design():
    """Documented guard behavior, pinned deliberately: with no LOAD/COMPLETE to
    bracket it, a cycle_id turnover on a hot in-progress batch reads as identity
    churn, NOT a new batch. This depends on the sequencer always emitting
    S_BatchLoad at a real boundary — if that ever stops being true, this test is
    the one that should fail and force the guard to be revisited."""
    fsm = CycleLifecycle()
    res = _drive(fsm, [("S_BatchLoad", "A", 0.0, COLD)]
                 + [("S_MicrowaveHeating", "A", 2000.0, HOT)] * 5
                 + [("S_MicrowaveHeating", "B", 2000.0, HOT)] * 5)
    assert _reset_indices(res) == [0]
