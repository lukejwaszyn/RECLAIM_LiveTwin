"""Per-channel validity + incomplete-bank policy tests, verified end-to-end against
the REAL cloud ingest (via conftest's sibling-package path)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from push_ingest_dual import DualPushEngine
from reclaim_edge.config import Config
from reclaim_edge.framer import Framer, parse_line

from crio_source_record.evidence_parser import QualityProfile, parse_record
from crio_source_record.frame_builder import build_frame
from crio_source_record.quality_policy import BankPolicy, apply_policy

FX = Path(__file__).resolve().parents[1] / "fixtures"
_META = dict(source_id="reclaim-crio-rt-01", cycle_id="batch-004",
             source_op_state="S_MicrowaveHeating", active_chamber="PL")


def _record(profile=None):
    return parse_record((FX / "record_34_nominal.txt").read_text(), profile=profile)


def _ingest(result_vars):
    ts = datetime.now(timezone.utc).isoformat()
    line = build_frame(result_vars, ts=ts, **_META)
    frame, _ = Framer(Config()).build(parse_line(line.decode()))
    return DualPushEngine(production=True).ingest(frame)


# --- per-channel validity signal ---------------------------------------------

def test_channel_validity_names_the_withheld_channel():
    res = apply_policy(_record())          # default profile: PL_bottom2 quarantined
    assert res.channel_validity["PL_bottom2"] is False
    assert res.channel_validity["PL_bottom1"] is True
    assert res.invalid_channels() == ("PL_bottom2",)


def test_chamber_validity_flags_incomplete_pl_bank():
    res = apply_policy(_record())
    assert res.chamber_validity["PL"] is False   # bank incomplete (bottom2 out)
    assert res.chamber_validity["MT"] is True     # MT_bottom valid


# --- REJECT policy (default = current cloud behavior) -------------------------

def test_reject_policy_leaves_partial_bank_and_cloud_rejects():
    res = apply_policy(_record(), policy=BankPolicy.REJECT)
    assert "PL_bottom1" in res.vars and "PL_bottom2" not in res.vars
    disp = DualPushEngine(production=True).ingest_line(
        Framer(Config()).build(parse_line(
            build_frame(res.vars, ts=datetime.now(timezone.utc).isoformat(),
                        **_META).decode()))[0])
    assert disp["status"] == "rejected"
    assert disp["code"] == "telemetry_invalid"


# --- SUPPRESS policy (recommended) -------------------------------------------

def test_suppress_policy_drops_incomplete_bank_entirely():
    res = apply_policy(_record(), policy=BankPolicy.SUPPRESS_INCOMPLETE)
    for f in ("PL_bottom1", "PL_bottom2", "PL_bottom3", "PL_bottom4"):
        assert f not in res.vars              # whole PL bed bank stepped on
    assert "MT_bottom" in res.vars            # MT untouched


def test_suppress_policy_keeps_frame_and_flags_chamber_invalid():
    res = apply_policy(_record(), policy=BankPolicy.SUPPRESS_INCOMPLETE)
    state = _ingest(res.vars)
    assert state["ingest_status"] == "accepted"     # frame kept (MT + MW survive)
    assert state["PL_sensor_valid"] is False         # chamber flagged, not fabricated


def test_suppress_with_complete_bank_is_a_no_op():
    prof = QualityProfile(signed_by="controls-x", quarantine=frozenset())
    res = apply_policy(_record(prof), policy=BankPolicy.SUPPRESS_INCOMPLETE)
    assert res.chamber_validity["PL"] is True
    for f in ("PL_bottom1", "PL_bottom2", "PL_bottom3", "PL_bottom4"):
        assert f in res.vars
    assert _ingest(res.vars)["PL_sensor_valid"] is True


def test_suppress_handles_metals_single_channel_bank():
    prof = QualityProfile(quarantine=frozenset({"MT_bottom"}))
    res = apply_policy(_record(prof), policy=BankPolicy.SUPPRESS_INCOMPLETE)
    assert res.chamber_validity["MT"] is False
    assert "MT_bottom" not in res.vars
    # PL bank is complete under this profile (bottom2 not quarantined here)
    assert res.chamber_validity["PL"] is True
