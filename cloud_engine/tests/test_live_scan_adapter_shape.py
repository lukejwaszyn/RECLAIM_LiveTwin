"""Offline contract test for the evidence-gated Windows Scan Engine payload.

Panel correlation contradicted multiple semantic aliases, and the old TC2/TC3
pair produced a false sensor-valid model state. Every Mod2 and unscaled Mod3
value therefore stays visibly raw until a versioned mapping profile approves it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys


ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

import labview_map  # noqa: E402
from push_ingest_dual import DualPushEngine, TELEMETRY_SCHEMA  # noqa: E402


def _live_scan_vars() -> dict:
    """Exact key shape emitted by reclaim-psp-adapter.ps1 in PSP mode."""
    return {
        "scan_Mod2_TC0_degC": 20.0,
        "scan_Mod2_TC1_degC": 21.0,
        "scan_Mod2_TC2_degC": 22.0,
        "scan_Mod2_TC3_degC": 23.0,
        "scan_Mod2_TC4_degC": 24.0,
        "scan_Mod2_TC5_degC": 25.0,
        "scan_Mod2_TC6_degC": 26.0,
        "scan_Mod2_TC7_degC": 27.0,
        "scan_Mod3_AI0_raw": 1.1,
        "scan_Mod3_AI1_raw": 2.2,
        "scan_Mod3_AI2_raw": 3.3,
    }


def test_live_scan_shape_quarantines_every_unapproved_scan_channel(monkeypatch):
    raw = _live_scan_vars()
    pressure_inputs = []
    real_press_kpa = labview_map._press_kPa

    def record_pressure_input(value):
        pressure_inputs.append(value)
        return real_press_kpa(value)

    monkeypatch.setattr(labview_map, "_press_kPa", record_pressure_input)
    normalized, mw_globals, active = labview_map.normalize(
        {**raw, "active": "NONE"}
    )

    assert active is None
    assert mw_globals == {}
    assert normalized == {**raw, "active": "NONE"}
    # Physical scan names do not select the LabVIEW contract normalizer, so no
    # raw analog value can accidentally enter the Torr conversion seam.
    assert pressure_inputs == []
    assert all(name.startswith("scan_Mod") for name in normalized if name != "active")
    assert "PL_P_chamber" not in normalized
    assert "PL_P_downstream" not in normalized
    assert "PL_T_wall_meas" not in normalized


def test_live_scan_shape_has_expected_production_engine_state():
    frame = {
        "schema_version": TELEMETRY_SCHEMA,
        "mode": "live",
        "run_id": "offline-live-scan-shape",
        "source_id": "reclaim-crio-scan-poc",
        "seq": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycle_id": "ENGINEERING-POC-NO-AUTHORITATIVE-CYCLE",
        "source_op_state": "S_Idle",
        "active_chamber": "NONE",
        "vars": _live_scan_vars(),
    }

    state = DualPushEngine(production=True).ingest(frame)

    assert state["ingest_status"] == "accepted"
    assert state["source_op_state"] == state["op_state"] == "S_Idle"
    assert state["active_chamber"] == "NONE"
    assert state["PL_sensor_valid"] is False
    assert state["MT_sensor_valid"] is False

    # No raw scan field is promoted into a chamber model input.
    assert "PL_T_bed_meas" not in state
    assert "PL_T_wall_meas" not in state
    assert "PL_T_cond_top" not in state
    assert "PL_T_cond_bottom" not in state

    # Both chambers fail closed instead of interpreting audit-only raw values.
    assert "MT_T_bed_meas" not in state
    assert "MT_T_wall_meas" not in state

    # Unscaled analog inputs are neither pressure nor temperature model inputs.
    assert "PL_P_chamber" not in state
    assert "PL_P_downstream" not in state
    assert all(not name.startswith("scan_Mod") for name in state)
    assert state["PL_P_fwd"] == state["MT_P_fwd"] == 0.0


def test_missing_chamber_always_publishes_false_availability_gate():
    frame = {
        "schema_version": TELEMETRY_SCHEMA,
        "mode": "live",
        "run_id": "offline-empty-chamber-gate",
        "source_id": "reclaim-crio-scan-poc",
        "seq": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycle_id": "ENGINEERING-POC-NO-AUTHORITATIVE-CYCLE",
        "source_op_state": "S_Idle",
        "active_chamber": "NONE",
        "vars": {"scan_Mod2_TC2_degC": 0.0},
    }

    state = DualPushEngine(production=True).ingest(frame)

    assert state["PL_sensor_valid"] is False
    assert state["MT_sensor_valid"] is False
    assert state["PL_op_state"] == state["MT_op_state"] == "S_Idle"
