#!/usr/bin/env python3
"""
labview_map.py — normalize the REAL cRIO/LabVIEW SSMG telemetry into the engine's
canonical, chamber-tagged, SI measurement frame.

Authority for the raw names: SSMG_Variable_and_Sensor_List.docx (the controls-team
block-diagram export) + the LabVIEW "concatenated string" indicator. The physical
twin streams names, units, and a channel topology that DO NOT match the estimator's
internal contract, so this adapter is the single translation seam:

    raw LabVIEW frame  (real names, degC, Torr, one shared SSMG power)
        |  normalize()
        v
    canonical frame    (PL_/MT_ prefixed engine names, KELVIN, kPa, power attributed
                        to the active chamber)  ->  push_ingest_dual.py (unchanged)

Why an adapter and not an estimator rewrite: the estimator's two-node measurement
vector [T_bed, T_wall], its Kelvin interior, and the dual-chamber split are all
correct and tested. Only the I/O boundary changed. Keeping the translation here keeps
the naming invariant auditable in exactly one place.

TOPOLOGY (from the docx, NI-9213 TC0..TC7 + NI-9205 AI0..AI2):
    Plastics bed core    PL_bottom1..4      (TC4..TC7, "Hot Spot 1..4")  -> T_bed_tc1..4
    Plastics skin (IR)   PL_surface_temp    (AI2, chamber surface/IR)     -> T_wall_meas
    Plastics condenser   PL_top/bottom_condenser_temp (TC0/TC1)          -> T_cond_* (passthrough)
    Plastics pressure    PL_chamber_pressure / PL_output_pressure (AI0/AI1) -> P_chamber / P_downstream
    Metals               MT_bottom / MT_top (TC3/TC2)                     -> T_bed_tc1 / T_wall_meas
    Shared SSMG          MW_power / MW_reverse                            -> P_fwd / P_refl (active chamber)

UNITS (real -> engine):
    temperatures  degC -> K   (+273.15)
    pressures     Torr -> kPa  (*0.1333224)    [760 Torr = 101.325024 kPa]
    power         W    -> W    (identity, assumed watts — REVIEW FLAG LV-1)

REVIEW FLAGS (see the review package): the two-temperature filter is fed
T_bed = mean(bed hot-spots) and T_wall = IR skin. Whether PL_surface_temp is the bed
radiating surface or the external skin is a MODELING CHOICE (LV-2). Chamber selection
is inferred from PL_process because the stream carries no switch-position channel
(LV-3). O2, feed/product mass, and vent/purge flow are ABSENT from the stream, so the
DR-8 mass metric, the inert-atmosphere check, and cycle-closure have no live source
(LV-4). All are documented for the secondary review.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

import math

C_TO_K = 273.15
TORR_TO_KPA = 0.1333224  # 1 Torr = 0.1333224 kPa

# Plastics bed-core hot-spot thermocouples -> canonical bed bank.
_PL_BED = ("PL_bottom1", "PL_bottom2", "PL_bottom3", "PL_bottom4")
# Metals: bottom = crucible/bed core, top = chamber wall/head (2-TC bank).
_MT_BED = ("MT_bottom",)
# Shared, non-chamber SSMG globals passed straight to /state for display/diagnostics.
_MW_GLOBALS = ("MW_freq", "MW_width", "MW_period", "MW_water_temp", "MW_flow_rate",
               "MW_water_state", "MW_flow_state", "MW_RF", "MW_status")
# Per-chamber boolean/state passthroughs (plastics only in the current stream).
_PL_FLAGS = ("PL_process", "PL_preprocess", "PL_postprocess",
             "PL_chamber_pump", "PL_purge_pump")


def _temp_K(v):
    """degC -> K. Exact zero is a valid measurement unless a separate,
    controls-approved quality indication says otherwise."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f + C_TO_K


def _press_kPa(v):
    """Torr -> kPa. Exact zero is a valid vacuum measurement."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f * TORR_TO_KPA


def looks_like_labview(raw: dict) -> bool:
    """True if the frame uses the raw LabVIEW schema (needs normalization).
    Detected by any signature real-name key; canonical frames never carry these."""
    keys = raw.keys()
    return ("MW_power" in keys or "PL_bottom1" in keys or "PL_surface_temp" in keys
            or "MT_top" in keys or "PL_chamber_pressure" in keys)


def active_chamber(raw: dict) -> str | None:
    """Which chamber the shared SSMG is driving this frame.

    The sequencer is AUTHORITATIVE: an explicit hint ('active'/'chamber') of
    'PL', 'MT', or 'NONE' is honored as-is — including 'NONE', which must never
    be overridden by inference (live-contract operating rule 3).

    Inference is a fallback for legacy/dev frames only: a MISSING MW_RF flag is
    treated as RF OFF (never assume the magnetron is radiating without
    evidence); PL_process True -> plastics; else RF-on attributes to the metals
    path by elimination (no MT process flag exists in the stream — LV-3)."""
    hint = raw.get("active") or raw.get("chamber")
    if hint in ("PL", "MT"):
        return hint
    if hint == "NONE":
        return None                      # sequencer-authoritative idle
    rf = raw.get("MW_RF")
    if not rf:                           # missing or falsy -> RF off, no attribution
        return None
    if raw.get("PL_process"):
        return "PL"
    # RF on and plastics not processing -> attribute to metals by elimination.
    return "MT"


def inferred_chamber(raw: dict) -> str | None:
    """Chamber selection by sensor inference ONLY (ignores any sequencer hint).
    Used by the ingest seam as a plausibility cross-check against the envelope's
    explicit active_chamber; a mismatch raises a diagnostic event, never a
    silent override."""
    stripped = {k: v for k, v in raw.items() if k not in ("active", "chamber")}
    return active_chamber(stripped)


def normalize(raw: dict) -> tuple[dict, dict, str | None]:
    """Translate a raw LabVIEW frame to the canonical engine frame.

    Returns (engine_vars, mw_globals, active_chamber):
      engine_vars   PL_/MT_ prefixed engine-named channels in K / kPa / W, with the
                    shared SSMG power attributed to the active chamber (0 on the idle
                    one). Ready for push_ingest_dual's prefix split — no code change
                    downstream.
      mw_globals    shared SSMG diagnostics (MW_freq, chiller, status booleans) to
                    ride through to /state, untouched.
      active        'PL' | 'MT' | None (for logging / op_state labeling).
    """
    if not looks_like_labview(raw):
        # already canonical (legacy synthetic feed) — pass through unchanged.
        return dict(raw), {}, active_chamber(raw)

    active = active_chamber(raw)
    p_fwd = raw.get("MW_power")
    p_refl = raw.get("MW_reverse")
    try:
        p_fwd = float(p_fwd) if p_fwd is not None else 0.0
    except (TypeError, ValueError):
        p_fwd = 0.0
    try:
        p_refl = float(p_refl) if p_refl is not None else 0.0
    except (TypeError, ValueError):
        p_refl = 0.0

    out: dict = {}

    # ---- Plastics ----
    for i, k in enumerate(_PL_BED, start=1):
        t = _temp_K(raw.get(k))
        if t is not None:
            out[f"PL_T_bed_tc{i}"] = round(t, 3)
    tw = _temp_K(raw.get("PL_surface_temp"))          # IR skin -> wall/outer node
    if tw is not None:
        out["PL_T_wall_meas"] = round(tw, 3)
    for src, dst in (("PL_top_condenser_temp", "PL_T_cond_top"),
                     ("PL_bottom_condenser_temp", "PL_T_cond_bottom")):
        t = _temp_K(raw.get(src))
        if t is not None:
            out[dst] = round(t, 3)
    for src, dst in (("PL_chamber_pressure", "PL_P_chamber"),
                     ("PL_output_pressure", "PL_P_downstream")):
        p = _press_kPa(raw.get(src))
        if p is not None:
            out[dst] = round(p, 4)
    for f in _PL_FLAGS:                                 # booleans ride through, prefixed once
        if f in raw:
            out[f] = raw[f]
    out["PL_P_fwd"] = round(p_fwd, 1) if active == "PL" else 0.0
    out["PL_P_refl"] = round(p_refl, 2) if active == "PL" else 0.0

    # ---- Metals ----
    for i, k in enumerate(_MT_BED, start=1):
        t = _temp_K(raw.get(k))
        if t is not None:
            out[f"MT_T_bed_tc{i}"] = round(t, 3)
    tw = _temp_K(raw.get("MT_top"))                    # top chamber -> wall/outer node
    if tw is not None:
        out["MT_T_wall_meas"] = round(tw, 3)
    out["MT_P_fwd"] = round(p_fwd, 1) if active == "MT" else 0.0
    out["MT_P_refl"] = round(p_refl, 2) if active == "MT" else 0.0

    # ---- shared SSMG globals (not chamber-tagged) ----
    mw = {k: raw[k] for k in _MW_GLOBALS if k in raw}

    return out, mw, active


if __name__ == "__main__":
    # Self-check against the legacy sample. Zeroes are retained pending an
    # explicit controls-approved quality or invalid indicator.
    sample = {
        "PL_surface_temp": 22.599389, "PL_output_pressure": 1032.422165,
        "PL_chamber_pressure": 1047.721528, "PL_top_condenser_temp": 0.0,
        "PL_bottom_condenser_temp": 0.0, "PL_bottom1": 0.0, "PL_bottom2": 0.0,
        "PL_bottom3": 0.0, "PL_bottom4": 0.0, "PL_process": False,
        "PL_preprocess": True, "PL_postprocess": False, "PL_chamber_pump": False,
        "PL_purge_pump": False, "MT_top": 0.0, "MT_bottom": 0.0,
        "MW_water_state": True, "MW_flow_state": True, "MW_RF": True, "MW_status": True,
        "MW_power": 0.0, "MW_reverse": 0.0, "MW_period": 0.0, "MW_width": 0.0,
        "MW_freq": 0.0, "MW_water_temp": 0.0, "MW_flow_rate": 0.0,
    }
    ev, mw, act = normalize(sample)
    import json
    print("active:", act)
    print("engine_vars:", json.dumps(ev, indent=2))
    print("mw_globals:", json.dumps(mw, indent=2))
    # expectations: surface 22.6C -> 295.75K; pressures use Torr -> kPa;
    # zero temperatures remain 273.15 K; RF on + PL_process False -> active MT.
    assert abs(ev["PL_T_wall_meas"] - 295.749) < 0.01, ev.get("PL_T_wall_meas")
    assert abs(ev["PL_P_chamber"] - 139.6847) < 0.01, ev.get("PL_P_chamber")
    assert ev["PL_T_bed_tc1"] == 273.15, "0 degC must be retained"
    assert act == "MT", act
    print("OK labview_map self-check passed")
