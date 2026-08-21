"""Tests for the frame conformance checker."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from crio_source_record.conformance import check_frames, main
from crio_source_record.evidence_parser import QualityProfile, parse_record
from crio_source_record.frame_builder import build_frame

FX = Path(__file__).resolve().parents[1] / "fixtures"
_META = dict(source_id="reclaim-crio-rt-01", cycle_id="conf-001",
             source_op_state="S_MicrowaveHeating", active_chamber="PL")


def _good_line(profile=None) -> bytes:
    ts = datetime.now(timezone.utc).isoformat()
    rec = parse_record((FX / "record_34_nominal.txt").read_text(), profile=profile)
    return build_frame(rec.valid_vars(), ts=ts, **_META)


def test_good_frames_conform_at_gateway():
    signed = QualityProfile(signed_by="t", quarantine=frozenset())
    raw = _good_line(signed) + _good_line(signed)
    results = check_frames(raw)
    assert len(results) == 2
    assert all(r.ok for r in results)


def test_blank_lines_are_skipped():
    raw = b"\n\n" + _good_line() + b"\n\n"
    results = check_frames(raw)
    assert len(results) == 1 and results[0].ok


def test_missing_vars_is_rejected():
    line = b'{"source_id":"x","ts":"2026-08-21T00:00:00Z","cycle_id":"c",' \
           b'"source_op_state":"S_Idle","active_chamber":"PL"}\n'
    r = check_frames(line)[0]
    assert not r.ok and r.stage == "gateway"


def test_non_json_line_is_rejected():
    r = check_frames(b"this is not json\n")[0]
    assert not r.ok and r.stage == "gateway"


def test_oversize_line_is_rejected():
    r = check_frames(b"x" * 9000 + b"\n", max_line_bytes=8192)[0]
    assert not r.ok and "bound" in r.detail


def test_invalid_utf8_is_rejected():
    r = check_frames(b'\xff{"vars":{}}\n')[0]
    assert not r.ok and "UTF-8" in r.detail


def test_cloud_accepts_complete_bank():
    signed = QualityProfile(signed_by="t", quarantine=frozenset())
    r = check_frames(_good_line(signed), cloud=True)[0]
    assert r.ok and r.cloud_status == "accepted"


def test_cloud_reports_incomplete_bank_rejection():
    r = check_frames(_good_line(), cloud=True)[0]   # default profile: PL_bottom2 out
    assert r.ok                                     # gateway-valid
    assert r.cloud_status == "rejected" and r.cloud_code == "telemetry_invalid"


def test_main_exit_codes(tmp_path):
    signed = QualityProfile(signed_by="t", quarantine=frozenset())
    good = tmp_path / "good.ndjson"
    good.write_bytes(_good_line(signed))
    assert main([str(good)]) == 0

    bad = tmp_path / "bad.ndjson"
    bad.write_bytes(b"not json\n")
    assert main([str(bad)]) == 1
