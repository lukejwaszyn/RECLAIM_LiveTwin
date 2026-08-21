"""End-to-end contract tests binding the source record to the REAL gateway framer
and the REAL cloud ingest/adapter (via the sibling-package path in conftest).

These prove the documented seams rather than restating them: the Torr/degC
conversions actually applied by ``labview_map``, and the whole-frame rejection that
happens today when one plastics bed TC is quarantined.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

# real sibling packages (see conftest.py)
import labview_map
from push_ingest_dual import DualPushEngine
from reclaim_edge.config import Config
from reclaim_edge.framer import Framer, parse_line

from crio_source_record.evidence_parser import QualityProfile, parse_record
from crio_source_record.frame_builder import build_frame

FX = Path(__file__).resolve().parents[1] / "fixtures"
_META = dict(
    source_id="reclaim-crio-rt-01",
    ts="2026-08-20T15:42:10.250Z",
    cycle_id="batch-2026-08-20-004",
    source_op_state="S_MicrowaveHeating",
    active_chamber="PL",
)


def _fresh_ts() -> str:
    # The cloud enforces a freshness window; ingest tests need a current source ts.
    return datetime.now(timezone.utc).isoformat()


def _vars(profile=None):
    return parse_record((FX / "record_34_nominal.txt").read_text(),
                        profile=profile).valid_vars()


def _gateway_frame(profile=None, **meta_over):
    line = build_frame(_vars(profile), **dict(_META, **meta_over))
    raw = parse_line(line.decode("utf-8"))
    frame, warnings = Framer(Config()).build(raw)
    return frame, warnings


def test_built_frame_parses_through_the_real_gateway_framer():
    frame, _ = _gateway_frame()
    assert frame["active_chamber"] == "PL"
    assert frame["source_op_state"] == "S_MicrowaveHeating"
    assert frame["source_id"] == "reclaim-crio-rt-01"
    assert "PL_surface_temp" in frame["vars"]     # raw LabVIEW name preserved


def test_unmapped_field_is_preserved_not_dropped():
    # MW_reverse_coupler has no labview_map target (a signed-map gap) but must still
    # survive the framer for the cloud to normalize/route.
    frame, _ = _gateway_frame()
    assert "MW_reverse_coupler" in frame["vars"]


def test_torr_and_degc_conversions_are_correct():
    frame, _ = _gateway_frame()
    ev, _mw, _active = labview_map.normalize(frame["vars"])
    # PL_surface_temp 224.119084 degC -> K
    assert abs(ev["PL_T_wall_meas"] - 497.269) < 0.01
    # PL_chamber_pressure 1047.721528 Torr * 0.1333224 = 139.6847 kPa.
    # (The labview_map __main__ self-check still asserts the STALE 139.6986;
    #  this pins the correct converted value.)
    assert abs(ev["PL_P_chamber"] - 139.6847) < 0.001


def test_quarantined_channel_is_never_fabricated_downstream():
    frame, _ = _gateway_frame()                    # default profile: PL_bottom2 out
    ev, _mw, _active = labview_map.normalize(frame["vars"])
    assert "PL_T_bed_tc2" not in ev                # no default/zero substitution


def test_full_valid_bank_is_accepted_by_the_cloud():
    prof = QualityProfile(signed_by="controls-x", quarantine=frozenset())
    frame, _ = _gateway_frame(profile=prof, ts=_fresh_ts())
    disp = DualPushEngine(production=True).ingest_line(frame)
    assert disp["status"] == "accepted"


def test_default_quarantine_makes_cloud_reject_the_whole_frame():
    # The core documented problem: dropping one PL bed TC fails the tc1..tc4
    # completeness gate and rejects MT + MW with it. Backlog item 1 addresses this.
    frame, _ = _gateway_frame(ts=_fresh_ts())      # default profile: PL_bottom2 out
    disp = DualPushEngine(production=True).ingest_line(frame)
    assert disp["status"] == "rejected"
    assert disp["code"] == "telemetry_invalid"
