"""Validation, liveness, enrichment, and prefix policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from .config import BridgeConfig
from .errors import BridgeFailure


STATE_SCHEMA = "reclaim.state.v1"
REQUIRED_STRINGS = (
    "run_id",
    "source_id",
    "cycle_id",
    "ts_source",
    "ts_engine",
    "active_chamber",
    "source_op_state",
    "op_state",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def validate_live_state(value: object, freshness_limit_ms: int) -> dict:
    if not isinstance(value, dict):
        raise BridgeFailure("invalid_json", "JSON_NOT_OBJECT", "state must be an object")
    if value.get("schema_version") != STATE_SCHEMA:
        raise BridgeFailure(
            "schema_mismatch", "SCHEMA_MISMATCH", "state schema did not match"
        )
    for key, item in value.items():
        if not _is_json_scalar(item):
            raise BridgeFailure(
                "identity_invalid", "NON_SCALAR_VALUE", f"state field {key} was not scalar"
            )
    for key in REQUIRED_STRINGS:
        item = value.get(key)
        if not isinstance(item, str) or not item:
            raise BridgeFailure(
                "identity_invalid", "IDENTITY_INVALID", f"state field {key} was invalid"
            )
    if value["active_chamber"] not in {"PL", "MT", "NONE"}:
        raise BridgeFailure(
            "identity_invalid", "IDENTITY_INVALID", "active_chamber was invalid"
        )
    seq = value.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise BridgeFailure(
            "identity_invalid", "IDENTITY_INVALID", "state seq was invalid"
        )
    age = value.get("state_age_ms")
    if isinstance(age, bool) or not isinstance(age, int) or age < 0:
        raise BridgeFailure(
            "identity_invalid", "STATE_AGE_INVALID", "state age was invalid"
        )
    if value.get("mode") != "live":
        raise BridgeFailure(
            "identity_invalid", "MODE_NOT_LIVE", "engine state mode was not live"
        )
    if value.get("ingest_status") != "accepted":
        raise BridgeFailure(
            "identity_invalid", "INGEST_NOT_ACCEPTED", "engine state was not accepted"
        )
    if age > freshness_limit_ms:
        raise BridgeFailure("stale", "STATE_STALE", "engine state was stale")
    return dict(value)


def _is_json_scalar(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def enrich(
    state: dict,
    config: BridgeConfig,
    *,
    observed_at: datetime,
    live: bool,
    status: str,
    error_code: str,
) -> dict:
    result = dict(state)
    result.update(
        {
            "data_live": live,
            "bridge_status": status,
            "bridge_observed_at": iso_utc(observed_at),
            "bridge_error_code": error_code,
            "bridge_instance_id": config.bridge_instance_id,
            "environment": config.environment,
            "engine_source_sha": config.engine_source_sha,
            "bridge_source_sha": config.bridge_source_sha,
            "freshness_limit_ms": config.freshness_limit_ms,
            # Convene must compare its own UTC clock to this value. This lease is
            # the fail-closed guard when the bridge cannot replace the file.
            "bridge_valid_until": iso_utc(
                observed_at + timedelta(milliseconds=config.lease_duration_ms)
                if live
                else observed_at
            ),
        }
    )
    return apply_prefix(result, config.prefix_mode)


def apply_prefix(payload: dict, mode: str) -> dict:
    if mode == "passthrough":
        return dict(payload)
    if mode != "sim":
        raise ValueError("unknown prefix mode")
    result: dict = {}
    for key, value in payload.items():
        target = key if key.startswith("sim_") else f"sim_{key}"
        if target in result:
            raise BridgeFailure(
                "identity_invalid", "PREFIX_COLLISION", "sim prefix would collide"
            )
        result[target] = value
    return result
