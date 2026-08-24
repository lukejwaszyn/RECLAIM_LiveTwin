"""Regression tests for the live dual-engine telemetry contract (v1.1).

Covers the 2026-08 review fixes: per-frame ack dispositions (C1/H3), run
supersession (C2), monotone sequence + gap accounting (C3), restart-persistent
identity (C4), seal-monitor units and phase gating (C5), no fabricated
measurements (C6), sequencer chamber authority (C7), and real-dt integration
(H1).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from push_ingest_dual import (
    DualPushEngine,
    FrameRejected,
    STATE_SCHEMA,
    TELEMETRY_SCHEMA,
    _make_handler,
    convene_result_variables,
)


def _now():
    return datetime.now(timezone.utc)


def _frame(**overrides):
    f = {
        "schema_version": TELEMETRY_SCHEMA,
        "mode": "live",
        "run_id": "unit-run-001",
        "source_id": "unit-crio-01",
        "seq": 1,
        "ts": _now().isoformat(),
        "cycle_id": "unit-cycle-001",
        "source_op_state": "S_MicrowaveHeating",
        "active_chamber": "PL",
        "vars": {
            "PL_bottom1": 100.0, "PL_bottom2": 100.0,
            "PL_bottom3": 100.0, "PL_bottom4": 100.0,
            "PL_surface_temp": 40.0, "PL_chamber_pressure": 1000.0,
            "PL_process": True, "MT_top": 0.0, "MT_bottom": 0.0,
            "MW_RF": True, "MW_power": 3000.0, "MW_reverse": 100.0,
        },
    }
    f.update(overrides)
    return f


# --------------------------------------------------------------- original suite

def test_production_frame_publishes_system_and_chamber_state():
    engine = DualPushEngine(production=True)
    out = engine.ingest(_frame())

    assert out["schema_version"] == STATE_SCHEMA
    assert out["op_state"] == "S_MicrowaveHeating"
    assert out["PL_op_state"] == "S_MicrowaveHeating"
    assert out["MT_op_state"] == "S_Idle"
    assert out["run_id"] == "unit-run-001"
    assert out["source_id"] == "unit-crio-01"
    assert out["seq"] == 1
    assert out["ingest_status"] == "accepted"
    names = {v["name"] for v in engine.svc.manifest()["variables"]}
    assert {"op_state", "PL_op_state", "MT_op_state", "run_id", "seq",
            "gap_count", "PL_sensor_valid", "MT_sensor_valid"} <= names


def test_cloud_accepts_and_type_checks_complete_34_field_source_record():
    import labview_map

    frame = _frame()
    frame["vars"] = {
        name: (False if name in labview_map.LABVIEW_BOOLEAN_FIELDS else float(index))
        for index, name in enumerate(labview_map.LABVIEW_RAW_FIELDS)
    }
    frame["vars"]["PL_process"] = True
    frame["vars"]["MW_RF"] = True

    out = DualPushEngine(production=True).ingest(frame)

    assert out["ingest_status"] == "accepted"


@pytest.mark.parametrize("field", [
    "PL_wall1", "PL_wall2", "PL_flow_meter", "MW_reverse_coupler",
    "MT_crucible_temperature", "PL_Probe1", "PL_Probe2",
])
def test_cloud_rejects_non_numeric_values_in_auxiliary_source_channels(field):
    frame = _frame()
    frame["vars"][field] = "not-a-number"

    with pytest.raises(FrameRejected, match=f"{field} must be a numeric scalar"):
        DualPushEngine(production=True).ingest(frame)


def test_duplicate_frame_does_not_step_the_estimator_twice():
    engine = DualPushEngine(production=True)
    frame = _frame()
    engine.ingest(frame)
    count = engine.count

    engine.ingest(frame)

    assert engine.last_ingest["duplicate"] is True
    assert engine.count == count


@pytest.mark.parametrize("field,value,code", [
    ("mode", "simulated", "mode_invalid"),
    ("source_op_state", "not-a-state", "state_invalid"),
    ("active_chamber", "both", "chamber_invalid"),
])
def test_production_rejects_invalid_provenance(field, value, code):
    engine = DualPushEngine(production=True)
    with pytest.raises(FrameRejected) as error:
        engine.ingest(_frame(**{field: value}))
    assert error.value.code == code


@pytest.mark.parametrize("mode", ["live", "harness", "replay"])
def test_production_accepts_flat_convene_snapshot_in_all_labeled_modes(mode):
    nested = _frame(
        mode=mode,
        source_id=f"convene-{mode}-machine",
        active_chamber="MT",
    )
    nested["vars"]["PL_process"] = False
    flat = {key: value for key, value in nested.items() if key != "vars"}
    flat.update(nested["vars"])

    out = DualPushEngine(production=True).ingest(flat)

    assert out["mode"] == mode
    assert out["source_id"] == f"convene-{mode}-machine"
    assert out["active_chamber"] == "MT"
    assert out["MT_sensor_valid"] is True
    assert out["MT_P_fwd"] == 3000.0
    assert out["PL_P_fwd"] == 0.0


def test_flat_convene_snapshot_rejects_sim_feedback_loop():
    frame = _frame()
    flat = {key: value for key, value in frame.items() if key != "vars"}
    flat.update(frame["vars"])
    flat["sim_PL_T_bed_est"] = 500.0

    disposition = DualPushEngine(production=True).ingest_line(flat)

    assert disposition["status"] == "rejected"
    assert disposition["code"] == "feedback_rejected"


def test_flat_text_extractions_restore_labview_scalar_types():
    nested = _frame(mode="harness", active_chamber="MT")
    flat = {key: str(value) for key, value in nested.items() if key != "vars"}
    flat.update({
        "MT_bottom": "313.418000",
        "MT_top": "300.000000",
        "MT_crucible_temperature": "NaN",
        "MW_power": "2200.000000",
        "MW_RF": "TRUE",
        "PL_process": "FALSE",
    })

    out = DualPushEngine(production=True).ingest(flat)

    assert out["mode"] == "harness"
    assert out["seq"] == nested["seq"]
    assert out["active_chamber"] == "MT"
    assert out["MT_sensor_valid"] is True
    assert out["MT_P_fwd"] == 2200.0
    assert out["MW_RF"] is True


def test_convene_result_variables_prefixes_only_finite_scalars():
    variables = convene_result_variables({
        "mode": "harness",
        "active_chamber": "PL",
        "PL_T_bed_est": 500.0,
        "missing": None,
        "bad": math.nan,
        "nested": {"unsafe": True},
    })

    assert variables == {
        "sim_mode": "harness",
        "sim_active_chamber": "PL",
        "sim_PL_T_bed_est": 500.0,
    }


def test_ingest_http_returns_computed_sim_variables_for_convene():
    engine = DualPushEngine(production=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(engine, "token"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        nested = _frame(mode="harness", source_id="convene-scenario-machine")
        flat = {key: value for key, value in nested.items() if key != "vars"}
        flat.update(nested["vars"])
        request = Request(
            f"http://127.0.0.1:{server.server_port}/ingest",
            data=(json.dumps(flat) + "\n").encode("utf-8"),
            headers={
                "Authorization": "Bearer token",
                "Content-Type": "application/x-ndjson",
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert payload["ingested"] == 1
    assert payload["state"]["mode"] == "harness"
    assert payload["variables"]["sim_mode"] == "harness"
    assert payload["variables"]["sim_active_chamber"] == "PL"
    assert payload["variables"]["sim_PL_sensor_valid"] is True


# ----------------------------------------------------- C3: monotone sequencing

def test_regressed_sequence_is_swallowed_as_duplicate_and_never_regresses_state():
    engine = DualPushEngine(production=True)
    engine.ingest(_frame(seq=100))
    engine.ingest(_frame(seq=101))
    count = engine.count

    d = engine.ingest_line(_frame(seq=50))

    assert d["status"] == "duplicate"
    assert d["final"] is True
    assert engine.count == count
    assert engine.svc.state()["seq"] == 101      # /state never moves backward


def test_sequence_gap_is_counted_and_evented_not_fabricated():
    engine = DualPushEngine(production=True)
    engine.ingest(_frame(seq=1))
    out = engine.ingest(_frame(seq=5))

    assert out["gap_count"] == 3
    assert "SEQ_GAP:3" in out["last_event"]
    assert engine.count == 2                     # missing frames were not invented


# ------------------------------------------------------- C2: run supersession

def test_new_run_id_supersedes_instead_of_wedging():
    engine = DualPushEngine(production=True)
    engine.ingest(_frame(run_id="run-A", seq=10))

    out = engine.ingest(_frame(run_id="run-B", seq=1))

    assert engine.active_run_id == "run-B"
    assert "RUN_SUPERSEDED:run-A" in out["last_event"]
    # the retired run can no longer write (final => gateway dead-letters it)
    d = engine.ingest_line(_frame(run_id="run-A", seq=11))
    assert d["status"] == "rejected"
    assert d["code"] == "run_superseded"
    assert d["final"] is True


# --------------------------------------------- C1: stale frames rejected FINAL

def test_stale_frame_is_rejected_final_so_the_gateway_can_dead_letter_it():
    engine = DualPushEngine(production=True)
    old = (_now() - timedelta(seconds=60)).isoformat()

    d = engine.ingest_line(_frame(ts=old))

    assert d["status"] == "rejected"
    assert d["code"] == "timestamp_stale"
    assert d["final"] is True                    # gateway must NOT retry forever


def test_mixed_batch_semantics_one_bad_frame_does_not_block_good_ones():
    engine = DualPushEngine(production=True)
    old = (_now() - timedelta(seconds=60)).isoformat()
    dispositions = [engine.ingest_line(_frame(seq=1)),
                    engine.ingest_line(_frame(seq=2, ts=old)),
                    engine.ingest_line(_frame(seq=3))]
    statuses = [d["status"] for d in dispositions]
    assert statuses == ["accepted", "rejected", "accepted"]
    assert engine.svc.state()["seq"] == 3


# ------------------------------------- C4: identity survives a service restart

def test_restart_with_state_file_does_not_double_step(tmp_path):
    state = str(tmp_path / "ingest_state.json")
    e1 = DualPushEngine(production=True, state_file=state)
    e1.ingest(_frame(seq=7))

    e2 = DualPushEngine(production=True, state_file=state)   # simulated restart
    d = e2.ingest_line(_frame(seq=7))                        # gateway retry

    assert d["status"] == "duplicate"
    assert e2.count == 0                                     # estimator untouched
    assert e2.active_run_id == "unit-run-001"


# --------------------------------------------- C6: no fabricated measurements

def test_zero_celsius_is_a_valid_measurement_without_quality_evidence():
    engine = DualPushEngine(production=True)
    out = engine.ingest(_frame())

    assert out["MT_sensor_valid"] is True
    assert out["MT_T_bed_meas"] == 273.15
    assert out["MT_T_wall_meas"] == 273.15
    assert out["PL_sensor_valid"] is True
    assert out["PL_T_bed_est"] > 0


def test_active_chamber_with_no_sensors_raises_sensor_missing_event():
    engine = DualPushEngine(production=True)
    f = _frame(active_chamber="MT")
    f["vars"]["PL_process"] = False
    del f["vars"]["MT_top"]
    del f["vars"]["MT_bottom"]
    out = engine.ingest(f)
    assert "MT:SENSOR_MISSING" in out["last_event"]


def test_raw_labview_nan_is_missing_observation_not_whole_frame_failure():
    engine = DualPushEngine(production=True)
    frame = _frame()
    frame["vars"]["PL_bottom2"] = math.nan

    out = engine.ingest(frame)

    assert out["ingest_status"] == "accepted"
    assert out["PL_sensor_valid"] is True  # remaining three bed TCs are usable
    assert "SYS:SENSOR_NAN:PL_bottom2" in out["last_event"]
    json.dumps(engine.svc.state(), allow_nan=False)


def test_mt_nan_scan_is_accepted_and_next_valid_scan_recovers():
    import labview_map

    engine = DualPushEngine(production=True)
    first = _frame(active_chamber="MT")
    first["vars"].update({
        "PL_process": True,  # contradictory legacy flag; envelope stays authoritative
        "MT_crucible_temperature": 313.418,
        "MT_top": math.nan,
        "MT_bottom": math.nan,
        "MW_power": 0.0,
    })

    unavailable = engine.ingest(first)

    assert unavailable["ingest_status"] == "accepted"
    assert unavailable["active_chamber"] == "MT"
    assert unavailable["MT_sensor_valid"] is False
    assert "SENSOR_NAN:MT_bottom,MT_top" in unavailable["last_event"]
    assert "MT:SENSOR_MISSING" in unavailable["last_event"]
    assert "CHAMBER_MISMATCH" in unavailable["last_event"]
    json.dumps(engine.svc.state(), allow_nan=False)

    second = _frame(
        seq=2,
        ts=(_now() + timedelta(seconds=1)).isoformat(),
        active_chamber="MT",
    )
    second["vars"].update({
        "PL_process": False,
        "MT_crucible_temperature": 313.418,
        "MT_top": 237.1,
        "MT_bottom": 313.418,
        "MW_power": 2200.0,
    })
    recovered = engine.ingest(second)

    assert recovered["MT_sensor_valid"] is True
    assert recovered["MT_T_bed_meas"] == pytest.approx(586.568, abs=1e-3)
    assert recovered["MT_P_fwd"] == 2200.0
    assert engine.count == 2
    json.dumps(engine.svc.state(), allow_nan=False)

    mapped, _mw, active = labview_map.normalize({
        "active": "MT",
        "MT_crucible_temperature": 313.418,
        "MT_top": 237.1,
        "MT_bottom": math.nan,
        "MW_power": 2200.0,
    })
    assert active == "MT"
    assert "MT_T_bed_tc1" not in mapped


def test_raw_labview_infinity_remains_a_contract_rejection():
    frame = _frame()
    frame["vars"]["MT_top"] = math.inf

    with pytest.raises(FrameRejected, match="MT_top must be finite"):
        DualPushEngine(production=True).ingest(frame)


# --------------------------------------------------- C7: sequencer authority

def test_explicit_none_active_chamber_is_never_overridden_by_inference():
    engine = DualPushEngine(production=True)
    f = _frame(seq=1, active_chamber="NONE")
    out = engine.ingest(f)

    assert out["active_chamber"] == "NONE"
    # power must not be attributed to either chamber when sequencer says NONE
    assert out.get("PL_P_fwd", 0.0) == 0.0
    assert out.get("MT_P_fwd", 0.0) == 0.0
    # sensors imply RF-on -> plausibility diagnostic fires (never an override)
    assert "CHAMBER_MISMATCH" in out["last_event"]


# -------------------------------------------- C5: seal-monitor units + phase

def test_seal_leak_detected_during_evacuate_with_kpa_input():
    engine = DualPushEngine(production=True)
    base = _now()
    # Chamber stuck at ~1 atm (760 Torr -> 101.325 kPa) while evacuating: leak.
    for i, seq in enumerate([1, 2, 3], start=0):
        f = _frame(seq=seq, source_op_state="S_Evacuate",
                   ts=(base + timedelta(seconds=2 * i)).isoformat())
        f["vars"]["PL_chamber_pressure"] = 760.0
        f["vars"]["MW_power"] = 0.0
        out = engine.ingest(f)
    assert out["PL_seal_residual"] > 500          # sensible Pa-scale residual
    assert "PL:SEAL_LEAK" in out["last_event"]


def test_seal_monitor_silent_outside_evacuation_phase():
    engine = DualPushEngine(production=True)
    base = _now()
    for i, seq in enumerate([1, 2, 3], start=0):
        f = _frame(seq=seq, ts=(base + timedelta(seconds=2 * i)).isoformat())
        f["vars"]["PL_chamber_pressure"] = 760.0   # atmospheric during heating
        out = engine.ingest(f)
    assert out["PL_seal_residual"] == 0.0
    assert "SEAL_LEAK" not in out["last_event"]


# --------------------------------------------------------- H1: real dt

def test_engine_integrates_real_time_between_source_timestamps():
    engine = DualPushEngine(production=True)
    base = _now()
    engine.ingest(_frame(seq=1, ts=base.isoformat()))
    engine.ingest(_frame(seq=2, ts=(base + timedelta(seconds=2.0)).isoformat()))
    engine.ingest(_frame(seq=3, ts=(base + timedelta(seconds=4.5)).isoformat()))
    # first frame defaults to 1.0 s, then 2.0 s and 2.5 s real deltas
    assert engine.pl.t == pytest.approx(1.0 + 2.0 + 2.5, abs=1e-6)


# ------------------------------------------------ transient errors retryable

def test_internal_error_is_retryable_and_does_not_commit_identity(monkeypatch):
    engine = DualPushEngine(production=True)

    def boom(*a, **k):
        raise RuntimeError("synthetic engine fault")
    monkeypatch.setattr(engine.pl, "step", boom)

    d = engine.ingest_line(_frame(seq=1))
    assert d["status"] == "rejected"
    assert d["code"] == "internal_error"
    assert d["final"] is False                    # gateway may retry
    assert engine.ident.last_seq("unit-run-001", "unit-crio-01") is None

    monkeypatch.undo()
    d2 = engine.ingest_line(_frame(seq=1))        # the retry succeeds cleanly
    assert d2["status"] == "accepted"
