from __future__ import annotations

import pytest

from reclaim_edge.config import Config
from reclaim_edge.framer import FrameContractError, Framer, parse_line


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


def test_latest_audit_frame_preserves_typed_envelope_and_raw_shared_power():
    framer = Framer(Config(run_id="gateway-audit-run", mode="live"))
    frame, _ = framer.build({
        "source_id": "reclaim-crio-audit",
        "cycle_id": "audit-cycle",
        "ts": "2026-08-16T16:00:00Z",
        "source_op_state": "S_MicrowaveHeating",
        "active_chamber": "MT",
        "MW_power": 2750.0,
        "MW_reverse": 75.0,
        "MW_RF": True,
    })

    assert set(frame) == {
        "schema_version", "mode", "run_id", "source_id", "cycle_id", "seq",
        "ts", "source_op_state", "active_chamber", "vars",
    }
    assert frame["run_id"] == "gateway-audit-run"
    assert frame["source_id"] == "reclaim-crio-audit"
    assert frame["seq"] == 1 and isinstance(frame["seq"], int)
    assert frame["active_chamber"] == "MT"
    assert frame["vars"]["MW_power"] == 2750.0
    assert frame["vars"]["MW_reverse"] == 75.0
    assert frame["vars"]["MW_RF"] is True
    assert not any(key.startswith("sim_") for key in frame | frame["vars"])


def test_parse_line_requires_structured_object_and_preserves_valid_scalars():
    raw = parse_line(
        '{"source_id":"source-1","vars":'
        '{"zero":0,"temperature":23.5,"enabled":true}}'
    )

    assert raw["source_id"] == "source-1"
    assert raw["vars"] == {"zero": 0, "temperature": 23.5, "enabled": True}


@pytest.mark.parametrize(
    "line",
    [
        "[]",
        '"not-an-object"',
        '{"source_id":"missing-vars"}',
        '{"vars":null}',
        '{"vars":[]}',
        '{"vars":{"value":null}}',
        '{"vars":{"value":"1.0"}}',
        '{"vars":{"value":[]}}',
        '{"vars":{"value":{}}}',
        '{"vars":{"value":NaN}}',
        '{"vars":{"value":Infinity}}',
        'value=1.0',
    ],
)
def test_parse_line_rejects_non_contract_shapes_and_values(line):
    with pytest.raises(FrameContractError):
        parse_line(line)


@pytest.mark.parametrize("bad_value", [None, "1.0", [], {}, float("nan"), float("inf")])
def test_framer_defensively_rejects_invalid_direct_variable_values(bad_value):
    framer = Framer(Config(run_id="gateway-run", mode="live"))

    with pytest.raises(FrameContractError):
        framer.build({"vars": {"PL_bottom1": bad_value}})
