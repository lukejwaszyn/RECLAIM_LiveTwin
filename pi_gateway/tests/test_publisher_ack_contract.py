"""Gateway-side tests for the v1.1 per-frame ack contract and durability fixes."""
from __future__ import annotations

import threading
import time

import pytest

from reclaim_edge.buffer import Buffer
from reclaim_edge.config import Config
from reclaim_edge.framer import Framer
from reclaim_edge.publisher import Publisher


class ScriptedTransport:
    """Returns a queued list of disposition lists (or None for link failure)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def deliver(self, payloads):
        self.calls.append(list(payloads))
        return self.script.pop(0) if self.script else [("ack", "ok")] * len(payloads)


def _run_publisher_once(buffer, transport, batch=10):
    cfg = Config(publish_batch=batch, publish_interval_s=0.01)
    stop = threading.Event()
    pub = Publisher.__new__(Publisher)          # skip make_transport
    threading.Thread.__init__(pub, name="publisher", daemon=True)
    pub.cfg, pub.buffer, pub.stop = cfg, buffer, stop
    pub.transport = transport
    pub.delivered = 0
    pub.dead_lettered = 0
    pub.last_ack = time.time()
    pub._backoff = 0.01
    pub.start()
    time.sleep(0.3)
    stop.set()
    pub.join(timeout=2)
    return pub


def test_final_rejects_are_dead_lettered_and_stop_blocking_the_queue():
    buf = Buffer(":memory:", 1000)
    for i in range(3):
        buf.enqueue(f'{{"seq": {i}}}')
    # frame 0 stale (final), frames 1-2 accepted
    tr = ScriptedTransport([[("dead", "timestamp_stale"), ("ack", "accepted"),
                             ("ack", "accepted")]])
    pub = _run_publisher_once(buf, tr)

    assert buf.depth() == 0                      # nothing left blocking
    assert buf.dead_letter_count() == 1          # stale frame retained, auditable
    assert pub.delivered == 2
    assert pub.dead_lettered == 1


def test_transient_rejects_are_retried_until_delivered():
    buf = Buffer(":memory:", 1000)
    buf.enqueue('{"seq": 1}')
    tr = ScriptedTransport([[("retry", "internal_error")],
                            [("ack", "accepted")]])
    pub = _run_publisher_once(buf, tr)

    assert len(tr.calls) >= 2                    # same frame re-posted
    assert buf.depth() == 0
    assert pub.delivered == 1
    assert buf.dead_letter_count() == 0


def test_link_failure_keeps_everything_queued():
    buf = Buffer(":memory:", 1000)
    for i in range(2):
        buf.enqueue(f'{{"seq": {i}}}')
    tr = ScriptedTransport([None] * 200)         # dead link for the whole window
    pub = _run_publisher_once(buf, tr)

    assert buf.depth() == 2                      # at-least-once preserved
    assert pub.delivered == 0


def test_seq_high_water_mark_survives_restart_for_pinned_run():
    buf = Buffer(":memory:", 1000)
    cfg = Config(run_id="controlled-run-7")
    framer = Framer(cfg, seq_store=buf)
    for _ in range(3):
        frame, _ = framer.build({"op_state": "S_Evacuate", "active_chamber": "PL"})
        buf.enqueue(framer.dumps(frame), meta_key=f"seq:{frame['run_id']}",
                    meta_value=str(frame["seq"]))
    assert frame["seq"] == 3

    framer2 = Framer(cfg, seq_store=buf)         # simulated gateway restart
    frame2, _ = framer2.build({"op_state": "S_Evacuate", "active_chamber": "PL"})
    assert frame2["seq"] == 4                    # no reuse, no collision


def test_unknown_field_warns_once_not_per_frame():
    framer = Framer(Config(run_id="r", mode="live"))
    _, w1 = framer.build({"MW_novel_channel": 1.0})
    _, w2 = framer.build({"MW_novel_channel": 2.0})
    assert any("MW_novel_channel" in w for w in w1)
    assert not any("MW_novel_channel" in w for w in w2)   # fix M5: no log flood


def test_https_transport_relays_twin_command_signal(monkeypatch):
    """The /ingest response's ControlCommand must be captured for the HMI."""
    from reclaim_edge.publisher import HttpsTransport

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"results": [{"i": 0, "status": "accepted", "final": True}],
                    "command": {"chamber": "PL", "mode": "THROTTLE",
                                "power_setpoint_W": 1500.0,
                                "safe_state_armed": False}}

    class FakeRequests:
        @staticmethod
        def post(*a, **k):
            return FakeResp()

    tr = HttpsTransport(Config(transport="https", auth_token="t"))
    tr._requests = FakeRequests()
    disp = tr.deliver(['{"seq": 1}'])

    assert disp == [("ack", "accepted")]
    assert tr.last_command["mode"] == "THROTTLE"
    assert tr.last_command["power_setpoint_W"] == 1500.0


def test_config_load_fails_fast_on_missing_explicit_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        Config.load(str(tmp_path / "nope.yaml"))


def test_config_load_rejects_typo_keys(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("transport: https\nmode: live\nauth_token: t\ncloud_uri: oops\n")
    with pytest.raises(ValueError, match="cloud_uri"):
        Config.load(str(p))


def test_config_load_requires_token_for_live_https(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("transport: https\nmode: live\ncloud_url: https://engine.test/ingest\n")
    with pytest.raises(ValueError, match="auth_token"):
        Config.load(str(p))


@pytest.mark.parametrize(
    ("cloud_url", "auth_token", "message"),
    [
        ("PLACEHOLDER_CLOUD_INGRESS_NOT_PROVISIONED", "real-token", "absolute https"),
        ("http://engine.test/ingest", "real-token", "absolute https"),
        ("https://engine.test/state", "real-token", "/ingest"),
        ("https://engine.test/ingest?token=bad", "real-token", "query"),
        ("https://engine.test/ingest", "PLACEHOLDER_TOKEN", "placeholder"),
    ],
)
def test_live_https_rejects_unsafe_or_placeholder_endpoint_config(
        tmp_path, cloud_url, auth_token, message):
    p = tmp_path / "config.yaml"
    p.write_text(
        f"transport: https\nmode: live\ncloud_url: {cloud_url}\n"
        f"auth_token: {auth_token}\n"
    )
    with pytest.raises(ValueError, match=message):
        Config.load(str(p))


def test_live_https_requires_tls_verification(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "transport: https\nmode: live\n"
        "cloud_url: https://engine.test/ingest\n"
        "auth_token: real-token\nverify_tls: false\n"
    )
    with pytest.raises(ValueError, match="verify_tls=true"):
        Config.load(str(p))
