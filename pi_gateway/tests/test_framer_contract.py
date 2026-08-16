from __future__ import annotations

from reclaim_edge.config import Config
from reclaim_edge.framer import Framer


def test_framer_stamps_live_provenance_and_preserves_labview_schema():
    framer = Framer(Config(run_id="gateway-run", mode="live"))
    frame, warnings = framer.build({
        "op_state": "S_Evacuate", "active_chamber": "PL",
        "PL_process": True, "MW_power": 0.0,
    })

    assert frame["schema_version"] == "reclaim.telemetry.v1"
    assert frame["mode"] == "live"
    assert frame["run_id"] == "gateway-run"
    assert frame["source_op_state"] == "S_Evacuate"
    assert frame["active_chamber"] == "PL"
    assert frame["vars"]["PL_process"] is True
    assert frame["vars"]["MW_power"] == 0.0
    assert warnings  # raw LabVIEW fields are intentionally preserved, not dropped
