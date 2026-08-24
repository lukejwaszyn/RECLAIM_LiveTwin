"""Repository-owned Convene read contract and gateway/cloud audit semantics."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import copy
import sys


ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from push_ingest_dual import DualPushEngine, STATE_SCHEMA, TELEMETRY_SCHEMA


def _canonical_frame() -> dict:
    return {
        "schema_version": TELEMETRY_SCHEMA,
        "mode": "live",
        "run_id": "convene-contract-run",
        "source_id": "reclaim-crio-contract",
        "seq": 17,
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycle_id": "convene-contract-cycle",
        "source_op_state": "S_MicrowaveHeating",
        "active_chamber": "PL",
        "vars": {
            "PL_T_bed_tc1": 600.0,
            "PL_T_bed_tc2": 601.0,
            "PL_T_bed_tc3": 599.0,
            "PL_T_bed_tc4": 600.0,
            "PL_T_wall_meas": 450.0,
            "PL_P_fwd": 3000.0,
            "PL_P_refl": 100.0,
            "MT_T_bed_tc1": 700.0,
            "MT_T_wall_meas": 500.0,
            "MT_P_fwd": 0.0,
            "MT_P_refl": 0.0,
        },
    }


def test_cloud_state_exposes_typed_convene_binding_contract():
    engine = DualPushEngine(production=True)
    disposition = engine.ingest_line(_canonical_frame())
    state = engine.svc.state()

    assert disposition["status"] == "accepted"
    assert state["schema_version"] == STATE_SCHEMA
    assert state["mode"] == "live"
    assert state["ingest_status"] == "accepted"
    assert isinstance(state["run_id"], str) and state["run_id"]
    assert isinstance(state["source_id"], str) and state["source_id"]
    assert isinstance(state["ts_source"], str) and state["ts_source"].endswith("Z")
    assert isinstance(state["seq"], int) and not isinstance(state["seq"], bool)
    assert isinstance(state["ingest_age_ms"], int) and state["ingest_age_ms"] >= 0
    assert state["active_chamber"] in {"PL", "MT", "NONE"}
    assert state["op_state"] == state["source_op_state"]
    assert isinstance(state["PL_op_state"], str)
    assert isinstance(state["MT_op_state"], str)
    for chamber in ("PL", "MT"):
        assert isinstance(state[f"{chamber}_sensor_valid"], bool)
        assert isinstance(state[f"{chamber}_advisory_severity"], str)
        assert isinstance(state[f"{chamber}_advisory_action"], str)
        assert isinstance(state[f"{chamber}_advisory_message"], str)
    assert isinstance(state["cmd_mode"], str)
    assert isinstance(state["cmd_power_setpoint_W"], (int, float))
    assert isinstance(state["cmd_safe_state_armed"], bool)
    assert "events" not in state
    assert all(
        value is None or isinstance(value, (str, bool, int, float))
        for value in state.values()
    )

    manifest_names = {item["name"] for item in engine.svc.manifest()["variables"]}
    assert {
        "mode", "run_id", "source_id", "seq", "ts_source", "cycle_id",
        "active_chamber", "source_op_state", "op_state", "ingest_status",
        "ingest_age_ms", "state_age_ms", "PL_op_state", "MT_op_state",
        "PL_advisory_severity", "MT_advisory_severity", "cmd_mode",
        "cmd_power_setpoint_W", "cmd_safe_state_armed",
    } <= manifest_names


def test_gateway_raw_view_and_cloud_normalization_remain_distinct():
    frame = _canonical_frame()
    frame["vars"] = {
        "PL_bottom1": 100.0,
        "PL_bottom2": 101.0,
        "PL_bottom3": 99.0,
        "PL_bottom4": 100.0,
        "PL_surface_temp": 40.0,
        "PL_chamber_pressure": 760.0,
        "PL_process": True,
        "PL_purge_pump": False,
        "MT_bottom": 0.0,
        "MT_top": 0.0,
        "MW_RF": True,
        "MW_power": 3000.0,
        "MW_reverse": 100.0,
    }
    gateway_raw = copy.deepcopy(frame)

    state = DualPushEngine(production=True).ingest(frame)

    # The gateway machine reads this raw object and therefore retains LabVIEW units.
    assert frame == gateway_raw
    assert gateway_raw["vars"]["PL_bottom1"] == 100.0  # degC
    assert gateway_raw["vars"]["PL_chamber_pressure"] == 760.0  # Torr
    assert gateway_raw["vars"]["MW_power"] == 3000.0  # shared W

    # The sim_ view receives normalized aggregate engine state in SI units, and
    # shared microwave power is attributed only to the declared active chamber.
    assert state["PL_T_bed_meas"] == 373.15
    assert state["PL_T_wall_meas"] == 313.15
    assert state["PL_P_chamber"] == 101.325
    assert state["PL_P_fwd"] == 3000.0
    assert state["MT_P_fwd"] == 0.0
    assert state["PL_process"] is True
    assert state["PL_purge_pump"] is False
    assert state["MW_RF"] is True
    assert "PL_T_bed_tc1" not in state


def test_state_manifest_preserves_units_types_and_passthrough_names():
    manifest = {
        item["name"]: item
        for item in DualPushEngine(production=True).svc.manifest()["variables"]
    }

    assert manifest["PL_T_bed_meas"]["unit"] == "K"
    assert manifest["PL_T_bed_meas"]["dtype"] == "float"
    assert manifest["PL_P_chamber"]["unit"] == "kPa"
    assert manifest["PL_process"]["dtype"] == "bool"
    assert manifest["MW_flow_state"]["dtype"] == "bool"
    assert manifest["MW_flow_rate"]["unit"] == "provisional"
    assert manifest["state_age_ms"]["unit"] == "ms"
    assert manifest["seq"]["dtype"] == "int"
