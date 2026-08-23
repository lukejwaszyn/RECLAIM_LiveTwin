"""The rehearsal publisher must never be mistakable for a live writer."""
from __future__ import annotations

import json

import pytest

from rehearsal_convene import (
    PRODUCTION_CREDENTIAL,
    PROFILES,
    RESERVED_PREFIXES,
    UNCONTRACTED_PORTS,
    load_credential,
    resolve_profile,
    state_to_variables,
)


def _state():
    return {
        "status": "running",
        "t_sim": 412.5,
        "PL_T_bed_meas": 655.25,
        "MW_RF": True,
        "cycle": 3,
        "missing": None,
        "nested": {"unsafe": 1},
        "not_a_number": float("inf"),
    }


def test_state_is_prefixed_and_scalar_only():
    variables = state_to_variables(_state(), "rehearsal_nominal_")

    assert variables["rehearsal_nominal_status"] == "running"
    assert variables["rehearsal_nominal_t_sim"] == 412.5
    assert variables["rehearsal_nominal_PL_T_bed_meas"] == 655.25
    assert variables["rehearsal_nominal_MW_RF"] is True
    assert variables["rehearsal_nominal_cycle"] == 3
    # Nulls, nested objects and non-finite floats are dropped, never coerced.
    assert "rehearsal_nominal_missing" not in variables
    assert "rehearsal_nominal_nested" not in variables
    assert "rehearsal_nominal_not_a_number" not in variables
    assert all(name.startswith("rehearsal_nominal_") for name in variables)


def test_never_emits_a_live_namespace():
    for profile in PROFILES.values():
        variables = state_to_variables(_state(), profile.prefix)
        assert variables
        for name in variables:
            assert not name.startswith(RESERVED_PREFIXES)


def test_a_sim_named_scenario_field_is_still_confined_to_rehearsal():
    """A scenario field literally named sim_* must not escape its namespace."""
    variables = state_to_variables({"sim_x": 1.0, "gw_y": 2.0}, "rehearsal_lunar_")

    assert variables == {"rehearsal_lunar_sim_x": 1.0, "rehearsal_lunar_gw_y": 2.0}
    assert not any(name.startswith(RESERVED_PREFIXES) for name in variables)


def test_prefix_outside_the_rehearsal_namespace_is_refused():
    for bad in ("sim_", "gw_", "", "live_"):
        with pytest.raises(ValueError):
            state_to_variables(_state(), bad)


def test_profiles_match_the_isolation_contract():
    """Identity, prefix and port are transcribed from the contract table."""
    assert PROFILES["nominal"].identity == "reclaim-rehearsal-nominal"
    assert PROFILES["nominal"].prefix == "rehearsal_nominal_"
    assert PROFILES["nominal"].port == 8177
    assert PROFILES["power-outage"].identity == "reclaim-rehearsal-outage"
    assert PROFILES["power-outage"].prefix == "rehearsal_outage_"
    assert PROFILES["power-outage"].port == 8178
    assert PROFILES["lunar"].identity == "reclaim-rehearsal-lunar"
    assert PROFILES["lunar"].prefix == "rehearsal_lunar_"
    assert PROFILES["lunar"].port == 8179
    # Every identity and prefix is distinct: no two rehearsals can collide.
    assert len({p.identity for p in PROFILES.values()}) == len(PROFILES)
    assert len({p.prefix for p in PROFILES.values()}) == len(PROFILES)
    assert len({p.port for p in PROFILES.values()}) == len(PROFILES)


def test_uncontracted_profile_is_refused_not_invented():
    assert "loss-of-data" in UNCONTRACTED_PORTS
    assert "loss-of-data" not in PROFILES
    with pytest.raises(SystemExit) as excinfo:
        resolve_profile("loss-of-data")
    assert "isolation contract" in str(excinfo.value)


def test_production_credential_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "rehearsal_convene.PRODUCTION_CREDENTIAL", str(tmp_path / "prod.json")
    )
    production = tmp_path / "prod.json"
    production.write_text(json.dumps({"agentToken": "t", "machineId": "m"}), encoding="utf-8")

    with pytest.raises(ValueError, match="production"):
        load_credential(str(production))


def test_rehearsal_credential_loads():
    assert PRODUCTION_CREDENTIAL.endswith(".convene_agent.json")


def test_credential_requires_both_fields(tmp_path):
    incomplete = tmp_path / "rehearsal.json"
    incomplete.write_text(json.dumps({"agentToken": "t"}), encoding="utf-8")
    with pytest.raises(ValueError, match="agentToken and machineId"):
        load_credential(str(incomplete))

    good = tmp_path / "good.json"
    good.write_text(json.dumps({"agentToken": "t", "machineId": "m"}), encoding="utf-8")
    assert load_credential(str(good)) == ("t", "m")
