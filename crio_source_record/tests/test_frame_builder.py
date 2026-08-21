"""Contract tests for the source-frame builder (one JSON object + LF)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from crio_source_record.evidence_parser import QualityProfile, parse_record
from crio_source_record.frame_builder import (
    MAX_LINE_BYTES,
    MEASURED_MAX_BYTES,
    MEASURED_MIN_BYTES,
    FrameBuildError,
    build_frame,
)

FX = Path(__file__).resolve().parents[1] / "fixtures"

_META = dict(
    source_id="reclaim-crio-rt-01",
    ts="2026-08-20T15:42:10.250Z",
    cycle_id="batch-2026-08-20-004",
    source_op_state="S_MicrowaveHeating",
    active_chamber="PL",
)


def _nominal_vars(**profile_kw):
    prof = QualityProfile(**profile_kw) if profile_kw else None
    return parse_record((FX / "record_34_nominal.txt").read_text(), profile=prof).valid_vars()


def test_builds_one_json_object_plus_lf():
    line = build_frame(_nominal_vars(), **_META)
    assert isinstance(line, bytes)
    assert line.endswith(b"\n")
    assert line.count(b"\n") == 1
    obj = json.loads(line.decode("utf-8"))
    assert set(obj) == {"source_id", "ts", "cycle_id", "source_op_state",
                        "active_chamber", "vars"}
    assert obj["active_chamber"] == "PL"
    assert "PL_bottom2" not in obj["vars"]  # quarantined upstream


@pytest.mark.parametrize("missing", ["source_id", "cycle_id", "source_op_state"])
def test_missing_authoritative_metadata_is_rejected(missing):
    meta = dict(_META, **{missing: ""})
    with pytest.raises(FrameBuildError, match=missing):
        build_frame(_nominal_vars(), **meta)


def test_ts_without_utc_offset_is_rejected():
    meta = dict(_META, ts="2026-08-20T15:42:10.250")  # no offset
    with pytest.raises(FrameBuildError, match="ts"):
        build_frame(_nominal_vars(), **meta)


def test_ts_must_be_iso8601():
    meta = dict(_META, ts="last tuesday")
    with pytest.raises(FrameBuildError, match="ts"):
        build_frame(_nominal_vars(), **meta)


def test_active_chamber_must_be_explicit_member():
    meta = dict(_META, active_chamber="plastics")
    with pytest.raises(FrameBuildError, match="active_chamber"):
        build_frame(_nominal_vars(), **meta)


def test_active_chamber_none_is_accepted():
    meta = dict(_META, active_chamber="NONE")
    obj = json.loads(build_frame(_nominal_vars(), **meta).decode())
    assert obj["active_chamber"] == "NONE"


def test_non_finite_variable_is_rejected():
    with pytest.raises(FrameBuildError):
        build_frame({"PL_surface_temp": float("inf")}, **_META)


def test_variable_name_colliding_with_envelope_is_rejected():
    with pytest.raises(FrameBuildError, match="envelope"):
        build_frame({"seq": 1.0}, **_META)


def test_container_variable_is_rejected():
    with pytest.raises(FrameBuildError):
        build_frame({"PL_bottom_bank": [1.0, 2.0]}, **_META)


def test_oversize_frame_is_rejected():
    big = {f"chan_{i}": float(i) for i in range(2000)}
    with pytest.raises(FrameBuildError, match="bound"):
        build_frame(big, **_META)


def test_measured_size_bounds_hold_for_nominal_frame():
    line = build_frame(_nominal_vars(), **_META)
    size = len(line)
    assert MEASURED_MIN_BYTES <= size <= MEASURED_MAX_BYTES
    assert size < MAX_LINE_BYTES


def test_full_bank_frame_within_documented_max():
    # signed all-valid profile -> all 34 channels present (widest real frame)
    full = _nominal_vars(signed_by="controls-x", quarantine=frozenset())
    line = build_frame(full, **_META)
    assert len(line) <= MEASURED_MAX_BYTES
