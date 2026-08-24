from __future__ import annotations

from tools.three_path_acceptance import correlation


def test_correlation_proves_identity_namespace_and_raw_to_computed_mapping():
    snapshot = {
        "latest_gw": {
            "run_id": "run-1",
            "source_id": "source-1",
            "seq": 17,
            "cycle_id": "cycle-1",
            "source_op_state": "S_MicrowaveHeating",
            "PL_bottom1": 100.0,
            "PL_bottom2": 101.0,
            "PL_bottom3": 99.0,
            "PL_bottom4": 100.0,
        },
        "latest_sim": {
            "sim_run_id": "run-1",
            "sim_source_id": "source-1",
            "sim_seq": 17,
            "sim_cycle_id": "cycle-1",
            "sim_source_op_state": "S_MicrowaveHeating",
            "sim_PL_T_bed_meas": 373.15,
            "sim_data_live": True,
            "sim_bridge_status": "ok",
        },
    }

    result = correlation(snapshot, "source-1")

    assert result is not None
    assert result["seq"] == 17
    assert result["raw_bed_mean_degC"] == 100.0
    assert result["computed_bed_K"] == 373.15


def test_correlation_rejects_identity_drift_or_stale_state():
    base = {
        "latest_gw": {
            "run_id": "run-1",
            "source_id": "source-1",
            "seq": 1,
            "cycle_id": "cycle-1",
            "source_op_state": "S_Idle",
            "PL_bottom1": 0.0,
            "PL_bottom2": 0.0,
            "PL_bottom3": 0.0,
            "PL_bottom4": 0.0,
        },
        "latest_sim": {
            "sim_run_id": "run-1",
            "sim_source_id": "different-source",
            "sim_seq": 1,
            "sim_cycle_id": "cycle-1",
            "sim_source_op_state": "S_Idle",
            "sim_PL_T_bed_meas": 273.15,
            "sim_data_live": False,
            "sim_bridge_status": "stale",
        },
    }

    assert correlation(base, "source-1") is None
