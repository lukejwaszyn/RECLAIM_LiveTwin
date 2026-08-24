"""The synthetic cRIO must be indistinguishable from the real one downstream.

These tests import `cloud_engine` read-only and assert against its actual
mapper and engine, rather than against a restated copy of their behaviour.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (str(ROOT / "tools"), str(ROOT / "cloud_engine")):
    if path not in sys.path:
        sys.path.insert(0, path)

from synthetic_crio import build_channels, build_raw_frame, plant_frames  # noqa: E402
from labview_map import looks_like_labview, normalize  # noqa: E402
from push_ingest_dual import DualPushEngine, TELEMETRY_SCHEMA  # noqa: E402

C_TO_K = 273.15


def _envelope(raw, mode="harness", seq=1):
    """What the gateway framer builds around the raw frame (framer.py:128-139)."""
    vars_only = raw["vars"]
    return {
        "schema_version": TELEMETRY_SCHEMA,
        "mode": mode,
        "run_id": "synthetic-run-001",
        "source_id": raw.get("source_id", "synthetic-crio-01"),
        "cycle_id": raw.get("cycle_id", ""),
        "seq": seq,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_op_state": raw.get("source_op_state"),
        "active_chamber": raw.get("active_chamber"),
        "vars": vars_only,
    }


def test_wire_frame_has_the_vars_block_the_receiver_requires():
    """parse_line rejects any network object without an explicit vars block."""
    raw = build_raw_frame(600.0, 500.0, 2200.0, 110.0, "S_MicrowaveHeating")
    assert "vars" in raw
    assert looks_like_labview(raw["vars"])
    # Envelope hints stay at the top level, where the framer reads them.
    for key in ("source_id", "ts", "source_op_state", "active_chamber", "cycle_id"):
        assert key in raw and key not in raw["vars"]
    assert raw["source_id"] == "reclaim-synthetic-scenario"
    assert raw["active_chamber"] == "PL"


def test_units_round_trip_through_the_real_mapper():
    """Emitted degC/Torr must come back as the Kelvin/kPa we started from."""
    t_bed_K, t_wall_K = 655.25, 512.75
    channels = build_channels(t_bed_K, t_wall_K, 2200.0, 110.0,
                              p_chamber_kPa=101.325024)
    engine_vars, _mw, active = normalize(channels)

    # The four-TC mean is the true bed temperature: the offsets are symmetric,
    # which is what makes the raw gateway audit comparison meaningful.
    bed = [engine_vars[f"PL_T_bed_tc{i}"] for i in range(1, 5)]
    assert sum(bed) / 4 == pytest.approx(t_bed_K, abs=1e-3)
    assert engine_vars["PL_T_wall_meas"] == pytest.approx(t_wall_K, abs=1e-3)
    assert engine_vars["PL_P_chamber"] == pytest.approx(101.325024, abs=1e-3)
    assert active == "PL"
    # Power is attributed to the active chamber and zeroed on the idle one.
    assert engine_vars["PL_P_fwd"] == pytest.approx(2200.0)
    assert engine_vars["MT_P_fwd"] == 0.0


def test_mt_scenario_uses_mapped_mt_sensors_and_power():
    t_bed_K, t_wall_K = 586.568, 510.25
    channels = build_channels(
        t_bed_K, t_wall_K, 1800.0, 45.0, active_chamber="MT"
    )
    assert "PL_bottom1" not in channels
    assert "PL_surface_temp" not in channels
    assert channels["PL_process"] is False
    assert "MT_bottom" in channels and "MT_top" in channels

    # The envelope supplies this same authoritative hint before normalization.
    channels["active"] = "MT"
    engine_vars, _mw, active = normalize(channels)
    assert active == "MT"
    assert engine_vars["MT_T_bed_tc1"] == pytest.approx(t_bed_K, abs=1e-3)
    assert engine_vars["MT_T_wall_meas"] == pytest.approx(t_wall_K, abs=1e-3)
    assert engine_vars["MT_P_fwd"] == pytest.approx(1800.0)
    assert engine_vars["PL_P_fwd"] == 0.0


def test_pressure_is_omitted_rather_than_faked_when_absent():
    raw = build_raw_frame(600.0, 500.0, 2200.0, 110.0, "S_MicrowaveHeating")
    assert "PL_chamber_pressure" not in raw["vars"]


def test_rf_off_when_power_is_zero():
    raw = build_raw_frame(600.0, 500.0, 0.0, 0.0, "S_PowerInterrupted")
    assert raw["vars"]["MW_RF"] is False


def test_frames_stream_from_the_real_harness():
    frames = []
    for _t, raw, dt in plant_frames("nominal", "earth_lab"):
        frames.append(raw)
        if len(frames) >= 5:
            break
    assert len(frames) == 5
    assert dt > 0
    assert all(looks_like_labview(f["vars"]) for f in frames)
    assert all(f["source_id"] == "reclaim-synthetic-scenario:PL:nominal:earth_lab"
               for f in frames)
    # Temperatures advance rather than repeating a constant.
    assert len({f["vars"]["PL_bottom1"] for f in frames}) > 1


def test_mt_frames_stream_from_the_real_harness():
    _t, raw, _dt = next(plant_frames("nominal", "earth_lab", active_chamber="MT"))
    assert raw["active_chamber"] == "MT"
    assert raw["source_id"] == "reclaim-synthetic-scenario:MT:nominal:earth_lab"
    assert raw["cycle_id"].startswith("synthetic-MT-nominal-earth_lab-")
    assert "MT_bottom" in raw["vars"] and "MT_top" in raw["vars"]
    assert raw["vars"]["PL_process"] is False


def test_non_production_engine_accepts_a_harness_frame():
    engine = DualPushEngine(production=False)
    raw = build_raw_frame(600.0, 500.0, 2200.0, 110.0, "S_MicrowaveHeating")
    out = engine.ingest(_envelope(raw, mode="harness"))
    assert out is not None


def test_production_engine_accepts_and_labels_a_harness_frame():
    """Convene may route scenarios, but their harness identity must survive."""
    engine = DualPushEngine(production=True)
    raw = build_raw_frame(600.0, 500.0, 2200.0, 110.0, "S_MicrowaveHeating")
    out = engine.ingest(_envelope(raw, mode="harness"))
    assert out["mode"] == "harness"
    assert out["source_id"] == "reclaim-synthetic-scenario"
    assert out["PL_sensor_valid"] is True


def test_gateway_stamped_scenario_advances_the_production_engine(tmp_path):
    """The deployed gateway's live envelope is the route that produces sim_."""
    engine = DualPushEngine(production=True, state_file=str(tmp_path / "identity.json"))
    raw = build_raw_frame(600.0, 500.0, 2200.0, 110.0, "S_MicrowaveHeating")
    out = engine.ingest(_envelope(raw, mode="live"))

    assert out["mode"] == "live"
    assert out["source_id"] == "reclaim-synthetic-scenario"
    assert out["active_chamber"] == "PL"
    assert out["PL_sensor_valid"] is True


def test_frames_traverse_the_real_gateway_receiver(tmp_path):
    """End-to-end over an actual socket, through the gateway's own receiver.

    This is the claim that matters: the receiver, framer and buffer accept the
    synthetic stream unmodified, and the gateway -- not this tool -- stamps the
    frame `mode` from its config.
    """
    import json
    import threading
    import time

    sys.path.insert(0, str(ROOT / "pi_gateway"))
    from reclaim_edge.buffer import Buffer
    from reclaim_edge.config import Config
    from reclaim_edge.framer import Framer
    from reclaim_edge.receiver import Receiver
    from synthetic_crio import SyntheticCrio

    # An ephemeral port keeps this off the real 9070 listener.
    import socket as _socket
    probe = _socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    cfg = Config(run_id="synthetic-run", mode="live", strict_fields=False,
                 listen_host="127.0.0.1", listen_port=port)
    buffer = Buffer(str(tmp_path / "buf.db"), max_frames=100)
    stop = threading.Event()
    receiver = Receiver(cfg, Framer(cfg), buffer, stop)
    receiver.start()
    time.sleep(0.5)  # let the listener bind

    try:
        with SyntheticCrio("127.0.0.1", port) as crio:
            for _t, raw, _dt in plant_frames("nominal", "earth_lab"):
                crio.send(raw)
                if crio.sent >= 5:
                    break
            deadline = time.time() + 5.0
            while receiver.received < 5 and time.time() < deadline:
                time.sleep(0.05)
    finally:
        stop.set()
        receiver.join(timeout=3.0)

    assert receiver.received >= 5, f"receiver saw only {receiver.received} frames"

    frame = receiver.last_frame
    assert frame is not None
    # The gateway owns identity and labeling, exactly as it does for the cRIO.
    assert frame["mode"] == "live", "installed gateway owns the cloud acceptance mode"
    assert frame["run_id"] == "synthetic-run"
    assert frame["source_id"] == "reclaim-synthetic-scenario:PL:nominal:earth_lab"
    assert frame["seq"] >= 1
    assert frame["vars"]["MW_power"] == 2200.0
    assert "PL_bottom1" in frame["vars"]
    # It is a real canonical frame: the cloud mapper recognises it.
    assert looks_like_labview(frame["vars"])

    # The exact canonical frame that produced the raw gateway values also advances the production
    # engine; its existing state bridge is therefore what produces sim_*.
    engine = DualPushEngine(production=True, state_file=str(tmp_path / "identity.json"))
    state = engine.ingest(frame)
    assert state["mode"] == "live"
    assert state["source_id"] == frame["source_id"]
    assert state["PL_sensor_valid"] is True
