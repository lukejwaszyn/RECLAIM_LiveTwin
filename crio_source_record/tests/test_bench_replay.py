"""Bench replay harness tests — real TCP -> real receiver -> real cloud, no cRIO."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import labview_map
from crio_source_record.bench_replay import (
    build_stream,
    ingest_all,
    replay,
    run_bench,
)
from crio_source_record.evidence_parser import QualityProfile, parse_records
from crio_source_record.frame_builder import MAX_LINE_BYTES, build_frame
from crio_source_record.quality_policy import BankPolicy

FX = Path(__file__).resolve().parents[1] / "fixtures"
_META = dict(source_id="reclaim-crio-rt-01", cycle_id="bench-001",
             source_op_state="S_MicrowaveHeating", active_chamber="PL")
_SIGNED = QualityProfile(signed_by="bench", quarantine=frozenset())


def _stream(fixture="record_34_stream.txt", *, profile=_SIGNED,
            policy=BankPolicy.SUPPRESS_INCOMPLETE, **kw):
    recs = parse_records((FX / fixture).read_text(), profile=profile)
    return build_stream(recs, meta=_META, profile=profile, policy=policy, **kw)


def test_stream_flows_end_to_end_through_receiver_and_cloud():
    frames = _stream()
    res = replay(frames)
    assert res.sent == res.received == len(frames)
    disps, _engine = ingest_all(res.payloads)
    assert all(d["status"] == "accepted" for d in disps)


def test_all_frames_respect_the_byte_bound():
    frames = _stream()
    assert frames and all(len(f) <= MAX_LINE_BYTES for f in frames)


def test_conversions_survive_the_transport():
    frames = _stream()
    res = replay(frames)
    vars0 = json.loads(res.payloads[0])["vars"]
    ev, _mw, _active = labview_map.normalize(vars0)
    # Torr -> kPa on the chamber pressure that rode through the receiver.
    assert abs(ev["PL_P_chamber"] - 139.6847) < 0.001
    # complete bed bank -> four canonical bed TCs in kelvin
    assert {"PL_T_bed_tc1", "PL_T_bed_tc2", "PL_T_bed_tc3", "PL_T_bed_tc4"} <= ev.keys()


def test_pl_bottom2_quarantine_suppress_keeps_frame():
    # default profile quarantines PL_bottom2; SUPPRESS drops the bank, frame kept
    frames = _stream(profile=None, policy=BankPolicy.SUPPRESS_INCOMPLETE)
    res = replay(frames)
    disps, engine = ingest_all(res.payloads)
    assert all(d["status"] == "accepted" for d in disps)
    vars0 = json.loads(res.payloads[0])["vars"]
    ev, _mw, _active = labview_map.normalize(vars0)
    assert "PL_T_bed_tc2" not in ev            # never fabricated


def test_pl_bottom2_quarantine_reject_drops_frame():
    frames = _stream(profile=None, policy=BankPolicy.REJECT)
    res = replay(frames)
    disps, _engine = ingest_all(res.payloads)
    assert all(d["status"] == "rejected" and d["code"] == "telemetry_invalid"
               for d in disps)


def test_stale_timestamp_is_rejected_by_cloud():
    old = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    recs = parse_records((FX / "record_34_nominal.txt").read_text(), profile=_SIGNED)
    frames = build_stream(recs, meta=dict(_META, ts=old), profile=_SIGNED,
                          policy=BankPolicy.SUPPRESS_INCOMPLETE, fresh_ts=False)
    res = replay(frames)
    assert res.received == len(frames)          # receiver accepts it (framing ok)
    disps, _engine = ingest_all(res.payloads)   # cloud rejects on freshness
    assert disps[0]["status"] == "rejected"
    assert disps[0]["code"] == "timestamp_stale"


def test_duplicate_frame_is_deduped_by_cloud():
    frames = _stream("record_34_nominal.txt")
    res = replay(frames)
    disps, engine = ingest_all(res.payloads)
    assert disps[0]["status"] == "accepted"
    again = engine.ingest_line(json.loads(res.payloads[0]))
    assert again["status"] == "duplicate"


def test_reconnect_midstream_loses_no_frames():
    frames = _stream()
    res = replay(frames, reconnect_after=1)
    assert res.sent == res.received == len(frames)


def test_run_bench_smoke_summary():
    summary = run_bench()
    assert summary["sent"] == summary["received"] == 3
    assert summary["accepted"] == 3
    assert summary["max_frame_bytes"] <= MAX_LINE_BYTES
