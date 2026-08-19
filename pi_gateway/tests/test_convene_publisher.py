from __future__ import annotations

import json
import threading

from reclaim_edge.buffer import Buffer
from reclaim_edge.config import Config
from reclaim_edge.convene import ConvenePublisher, frame_to_variables
from reclaim_edge.framer import Framer
from reclaim_edge.receiver import Receiver


def _frame():
    return {
        "schema_version": "reclaim.telemetry.v1",
        "mode": "live",
        "run_id": "run-1",
        "source_id": "reclaim-crio-laptop-01",
        "cycle_id": "cycle-1",
        "seq": 7,
        "ts": "2026-08-19T20:00:00Z",
        "source_op_state": "S_MicrowaveHeating",
        "active_chamber": "PL",
        "vars": {
            "PL_bottom1": 100.2,
            "MW_RF": True,
            "missing": None,
            "nested": {"unsafe": 1},
        },
    }


def test_frame_to_variables_is_scalar_and_gw_only():
    variables = frame_to_variables(_frame())

    assert variables["gw_seq"] == 7
    assert variables["gw_source_op_state"] == "S_MicrowaveHeating"
    assert variables["gw_PL_bottom1"] == 100.2
    assert variables["gw_MW_RF"] is True
    assert "gw_missing" not in variables
    assert "gw_nested" not in variables
    assert all(name.startswith("gw_") for name in variables)
    assert not any(name.startswith("sim_") for name in variables)


def test_direct_publish_uses_machine_token_and_does_not_emit_sim(tmp_path):
    credential = tmp_path / "credential.json"
    credential.write_text(json.dumps({"machineId": "desktop-1", "agentToken": "secret"}))
    cfg = Config(
        convene_enabled=True,
        convene_credentials_path=str(credential),
    )
    publisher = ConvenePublisher(cfg, threading.Event())

    class Response:
        status_code = 200

    class Requests:
        calls = []

        @classmethod
        def post(cls, url, **kwargs):
            cls.calls.append((url, kwargs))
            return Response()

    publisher._requests = Requests
    assert publisher._deliver(_frame()) is True

    url, request = Requests.calls[0]
    assert url.endswith("/api/machine/publish")
    assert request["headers"] == {"X-Agent-Token": "secret"}
    assert request["json"]["variables"]["gw_seq"] == 7
    assert all(key.startswith("gw_") for key in request["json"]["variables"])


def test_receiver_durably_enqueues_before_best_effort_audit_submit():
    cfg = Config(run_id="run-1", strict_fields=False)
    buffer = Buffer(":memory:", 100)
    events = []

    class Audit:
        def submit(self, frame):
            events.append((buffer.depth(), frame))

    receiver = Receiver(
        cfg,
        Framer(cfg, seq_store=buffer),
        buffer,
        threading.Event(),
        audit_publisher=Audit(),
    )
    receiver._handle_line('{"op_state":"S_Evacuate","MW_power":50.0}')

    assert buffer.depth() == 1
    assert events[0][0] == 1
    assert events[0][1]["vars"]["MW_power"] == 50.0


def test_submit_coalesces_without_blocking():
    publisher = ConvenePublisher(Config(), threading.Event())
    publisher.submit({"seq": 1})
    publisher.submit({"seq": 2})

    assert publisher.coalesced == 1
    assert publisher._pending.get_nowait()["seq"] == 2
