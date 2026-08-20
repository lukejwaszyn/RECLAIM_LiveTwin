from __future__ import annotations

import math
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import labview_map  # noqa: E402


def test_torr_to_kpa_release_values():
    for torr, expected in ((0, 0), (1, 0.1333224), (100, 13.33224), (760, 101.325024)):
        assert labview_map._press_kPa(torr) == expected


def test_zero_celsius_is_valid_and_retained():
    assert labview_map._temp_K(0) == 273.15
    normalized, _, _ = labview_map.normalize({
        "PL_bottom1": 0.0,
        "PL_chamber_pressure": 0.0,
    })
    assert normalized["PL_T_bed_tc1"] == 273.15
    assert normalized["PL_P_chamber"] == 0.0


def test_invalid_numeric_inputs_are_not_promoted_to_measurements():
    assert labview_map._temp_K(None) is None
    assert labview_map._temp_K("not-a-number") is None
    assert labview_map._press_kPa(None) is None
    assert labview_map._press_kPa("not-a-number") is None
    for nonfinite in (math.nan, math.inf, -math.inf):
        assert labview_map._temp_K(nonfinite) is None
        assert labview_map._press_kPa(nonfinite) is None
