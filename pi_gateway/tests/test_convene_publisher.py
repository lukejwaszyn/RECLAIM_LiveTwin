from __future__ import annotations

import json
import threading
import time

from reclaim_edge.buffer import Buffer
from reclaim_edge.config import Config
from reclaim_edge.convene import LABVIEW_RAW_FIELDS, ConvenePublisher, frame_to_variables
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
            "gw_quality_code": 7,
            "missing": None,
            "nested": {"unsafe": 1},
        },
    }


def test_frame_to_variables_uses_exact_source_names_without_prefixes():
    variables = frame_to_variables(_frame())

    assert variables["seq"] == 7
    assert variables["source_op_state"] == "S_MicrowaveHeating"
    assert variables["PL_bottom1"] == 100.2
    assert variables["MW_RF"] is True
    assert "missing" not in variables
    assert "nested" not in variables
    assert not any(name.startswith(("gw_", "sim_")) for name in variables)


def test_all_34_live_source_fields_are_published_verbatim():
    frame = _frame()
    frame["vars"] = {
        name: (False if name in {
            "PL_process", "PL_preprocess", "PL_postprocess", "PL_chamber_pump",
            "PL_purge_pump", "MW_water_state", "MW_flow_state", "MW_RF",
            "MW_status",
        } else float(index))
        for index, name in enumerate(LABVIEW_RAW_FIELDS)
    }

    variables = frame_to_variables(frame)

    assert set(LABVIEW_RAW_FIELDS) <= variables.keys()
    assert all(variables[name] == frame["vars"][name] for name in LABVIEW_RAW_FIELDS)


def test_frame_to_variables_rejects_cloud_owned_sim_name():
    frame = _frame()
    frame["vars"]["sim_forbidden"] = 1

    try:
        frame_to_variables(frame)
    except ValueError as exc:
        assert "sim_" in str(exc)
    else:
        raise AssertionError("gateway accepted a cloud-owned sim_ variable")


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
    assert request["json"]["variables"]["seq"] == 7
    assert request["json"]["variables"]["PL_bottom1"] == 100.2
    assert not any(
        key.startswith(("gw_", "sim_"))
        for key in request["json"]["variables"]
    )


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
    receiver._handle_line(
        '{"source_op_state":"S_Evacuate","vars":{"MW_power":50.0}}'
    )

    assert buffer.depth() == 1
    assert events[0][0] == 1
    assert events[0][1]["vars"]["MW_power"] == 50.0


def test_submit_coalesces_without_blocking():
    publisher = ConvenePublisher(Config(), threading.Event())
    publisher.submit({"seq": 1})
    publisher.submit({"seq": 2})

    assert publisher.coalesced == 1
    assert publisher._pending.get_nowait()["seq"] == 2


def test_transient_failure_retries_latest_value_until_success(tmp_path):
    credential = tmp_path / "credential.json"
    credential.write_text(json.dumps({"machineId": "desktop-1", "agentToken": "secret"}))
    stop = threading.Event()
    publisher = ConvenePublisher(
        Config(convene_enabled=True, convene_credentials_path=str(credential)), stop
    )
    delivered = []

    def flaky(frame):
        if not delivered:
            delivered.append(("failed", frame["seq"]))
            raise RuntimeError("transient")
        delivered.append(("accepted", frame["seq"]))
        return True

    publisher._deliver = flaky
    publisher.start()
    publisher.submit({"seq": 1})
    deadline = time.time() + 3
    while publisher.delivered < 1 and time.time() < deadline:
        time.sleep(0.02)
    stop.set()
    publisher.join(timeout=2)

    assert delivered == [("failed", 1), ("accepted", 1)]
    assert publisher.failed == 1
    assert publisher.delivered == 1
