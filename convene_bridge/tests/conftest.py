from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from convene_bridge.config import BridgeConfig


VALID_SHA = "a" * 40


@pytest.fixture
def bridge_config(tmp_path):
    config = BridgeConfig(
        output_path=str(tmp_path / "sim_vars.json"),
        secret_file=str(tmp_path / "read-token.txt"),
        lock_path=str(tmp_path / "bridge.lock"),
        health_path=str(tmp_path / "health.json"),
        log_path=str(tmp_path / "bridge.log"),
        engine_source_sha=VALID_SHA,
        bridge_source_sha="b" * 40,
    )
    return config


@pytest.fixture
def valid_state():
    return {
        "schema_version": "reclaim.state.v1",
        "mode": "live",
        "ingest_status": "accepted",
        "run_id": "run-1",
        "source_id": "source-1",
        "cycle_id": "cycle-1",
        "seq": 10,
        "ts_source": "2026-08-17T12:00:00Z",
        "ts_engine": "2026-08-17T12:00:00.050Z",
        "active_chamber": "PL",
        "source_op_state": "S_MicrowaveHeating",
        "op_state": "S_MicrowaveHeating",
        "state_age_ms": 100,
        "temperature": 625.4,
        "sensor_valid": True,
        "nullable": None,
        "label": "nominal",
    }


@pytest.fixture
def observed_at():
    return datetime(2026, 8, 17, 12, 0, 1, tzinfo=timezone.utc)
