from __future__ import annotations

from dataclasses import replace

import pytest

from convene_bridge.contract import apply_prefix, enrich, validate_live_state
from convene_bridge.errors import BridgeFailure


def test_valid_live_state_preserves_scalar_types(valid_state):
    result = validate_live_state(valid_state, 15_000)
    assert result == valid_state
    assert type(result["temperature"]) is float
    assert type(result["sensor_valid"]) is bool
    assert result["nullable"] is None


@pytest.mark.parametrize("age", [14_999, 15_000])
def test_freshness_at_or_below_boundary_is_live(valid_state, age):
    valid_state["state_age_ms"] = age
    assert validate_live_state(valid_state, 15_000)["state_age_ms"] == age


def test_freshness_above_boundary_is_stale(valid_state):
    valid_state["state_age_ms"] = 15_001
    with pytest.raises(BridgeFailure) as caught:
        validate_live_state(valid_state, 15_000)
    assert (caught.value.status, caught.value.code) == ("stale", "STATE_STALE")


@pytest.mark.parametrize("payload", [None, [], "state", 7])
def test_non_object_json_is_rejected(payload):
    with pytest.raises(BridgeFailure) as caught:
        validate_live_state(payload, 15_000)
    assert caught.value.code == "JSON_NOT_OBJECT"


@pytest.mark.parametrize("schema", [None, "reclaim.state.v2", 1])
def test_missing_or_wrong_schema_is_rejected(valid_state, schema):
    valid_state["schema_version"] = schema
    with pytest.raises(BridgeFailure) as caught:
        validate_live_state(valid_state, 15_000)
    assert caught.value.status == "schema_mismatch"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", 4),
        ("source_id", None),
        ("cycle_id", ""),
        ("seq", True),
        ("seq", 1.5),
        ("ts_source", []),
        ("active_chamber", "XX"),
        ("state_age_ms", -1),
    ],
)
def test_invalid_identity_types_are_rejected(valid_state, field, value):
    valid_state[field] = value
    with pytest.raises(BridgeFailure) as caught:
        validate_live_state(valid_state, 15_000)
    assert caught.value.status == "identity_invalid"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("mode", "harness", "MODE_NOT_LIVE"),
        ("ingest_status", "rejected", "INGEST_NOT_ACCEPTED"),
    ],
)
def test_mode_and_ingest_status_fail_closed(valid_state, field, value, code):
    valid_state[field] = value
    with pytest.raises(BridgeFailure) as caught:
        validate_live_state(valid_state, 15_000)
    assert caught.value.code == code


def test_nested_or_nonfinite_values_are_rejected(valid_state):
    for bad in ({"nested": True}, [1, 2], float("nan")):
        valid_state["bad"] = bad
        with pytest.raises(BridgeFailure) as caught:
            validate_live_state(valid_state, 15_000)
        assert caught.value.code == "NON_SCALAR_VALUE"


def test_enrichment_adds_live_metadata_and_expiring_lease(
    bridge_config, valid_state, observed_at
):
    result = enrich(
        valid_state,
        bridge_config,
        observed_at=observed_at,
        live=True,
        status="ok",
        error_code="NONE",
    )
    assert result["data_live"] is True
    assert result["bridge_status"] == "ok"
    assert result["bridge_valid_until"] == "2026-08-17T12:00:06.000Z"
    assert result["engine_source_sha"] == "a" * 40
    assert result["bridge_source_sha"] == "b" * 40
    assert result["freshness_limit_ms"] == 15_000
    assert "nullable" not in result
    assert all(value is not None for value in result.values())


def test_fail_closed_payload_has_immediately_expired_lease(
    bridge_config, valid_state, observed_at
):
    result = enrich(
        valid_state,
        bridge_config,
        observed_at=observed_at,
        live=False,
        status="stale",
        error_code="STATE_STALE",
    )
    assert result["data_live"] is False
    assert result["bridge_valid_until"] == result["bridge_observed_at"]


def test_passthrough_and_single_sim_prefix(bridge_config, valid_state, observed_at):
    passthrough = apply_prefix({"seq": 1, "sim_existing": 2}, "passthrough")
    assert passthrough == {"seq": 1, "sim_existing": 2}
    prefixed = apply_prefix({"seq": 1, "sim_existing": 2}, "sim")
    assert prefixed == {"sim_seq": 1, "sim_existing": 2}


def test_sim_prefix_collision_is_rejected():
    with pytest.raises(BridgeFailure) as caught:
        apply_prefix({"seq": 1, "sim_seq": 2}, "sim")
    assert caught.value.code == "PREFIX_COLLISION"


def test_unknown_prefix_mode_is_rejected():
    with pytest.raises(ValueError):
        apply_prefix({}, "automatic")
