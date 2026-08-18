from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from convene_bridge.errors import BridgeFailure
from convene_bridge.state_bridge import StateBridge
from convene_bridge.writer import AtomicWriteError


class ScriptedClient:
    def __init__(self, values):
        self.values = iter(values)

    def fetch(self):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


class MemoryWriter:
    def __init__(self):
        self.payloads = []

    def write(self, payload):
        self.payloads.append(deepcopy(payload))


def test_fail_closed_startup_failure_recovery_and_stale_transition(
    bridge_config, valid_state, observed_at
):
    stale = deepcopy(valid_state)
    stale["seq"] = 11
    stale["state_age_ms"] = 15_001
    client = ScriptedClient(
        [
            BridgeFailure("engine_unavailable", "ENGINE_UNAVAILABLE", "offline"),
            valid_state,
            stale,
        ]
    )
    writer = MemoryWriter()
    times = iter(
        [observed_at, observed_at + timedelta(seconds=1), observed_at + timedelta(seconds=2), observed_at + timedelta(seconds=3)]
    )
    bridge = StateBridge(bridge_config, client, writer, now=lambda: next(times))

    assert bridge.publish_starting()
    assert bridge.run_once()
    assert bridge.run_once()
    assert bridge.run_once()

    assert [payload["data_live"] for payload in writer.payloads] == [False, False, True, False]
    assert [payload["bridge_status"] for payload in writer.payloads] == [
        "starting",
        "engine_unavailable",
        "ok",
        "stale",
    ]
    assert writer.payloads[-1]["seq"] == valid_state["seq"]


def test_same_identity_progression_and_equal_poll_are_valid(
    bridge_config, valid_state, observed_at
):
    equal = deepcopy(valid_state)
    progressed = deepcopy(valid_state)
    progressed["seq"] = 11
    writer = MemoryWriter()
    bridge = StateBridge(
        bridge_config,
        ScriptedClient([valid_state, equal, progressed]),
        writer,
        now=lambda: observed_at,
    )
    assert bridge.run_once() and bridge.run_once() and bridge.run_once()
    assert all(payload["data_live"] for payload in writer.payloads)


def test_same_identity_sequence_regression_fails_closed(
    bridge_config, valid_state, observed_at
):
    regressed = deepcopy(valid_state)
    regressed["seq"] = 9
    writer = MemoryWriter()
    bridge = StateBridge(
        bridge_config,
        ScriptedClient([valid_state, regressed]),
        writer,
        now=lambda: observed_at,
    )
    assert bridge.run_once()
    assert bridge.run_once()
    assert writer.payloads[-1]["data_live"] is False
    assert writer.payloads[-1]["bridge_status"] == "sequence_regression"
    assert writer.payloads[-1]["seq"] == 10


def test_new_run_or_source_resets_sequence_comparison(
    bridge_config, valid_state, observed_at, caplog
):
    transitioned = deepcopy(valid_state)
    transitioned.update({"run_id": "run-2", "source_id": "source-2", "seq": 1})
    writer = MemoryWriter()
    bridge = StateBridge(
        bridge_config,
        ScriptedClient([valid_state, transitioned]),
        writer,
        now=lambda: observed_at,
    )
    with caplog.at_level("INFO"):
        assert bridge.run_once() and bridge.run_once()
    assert writer.payloads[-1]["data_live"] is True
    assert "identity transition" in caplog.text


def test_write_failure_relies_on_previously_published_expiring_lease(
    bridge_config, valid_state, observed_at
):
    class FailSecondWrite(MemoryWriter):
        def write(self, payload):
            if self.payloads:
                raise AtomicWriteError("locked")
            super().write(payload)

    next_state = deepcopy(valid_state)
    next_state["seq"] = 11
    writer = FailSecondWrite()
    bridge = StateBridge(
        bridge_config,
        ScriptedClient([valid_state, next_state]),
        writer,
        now=lambda: observed_at,
    )
    assert bridge.run_once()
    assert bridge.run_once() is False
    retained = writer.payloads[0]
    assert retained["data_live"] is True
    assert retained["bridge_valid_until"] == "2026-08-17T12:00:06.000Z"
