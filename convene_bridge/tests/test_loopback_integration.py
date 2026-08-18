from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
from pathlib import Path
import socket
import threading

import pytest

import convene_bridge.client as client_module
from convene_bridge.client import StateClient
from convene_bridge.errors import BridgeFailure


@contextmanager
def fake_state_server(body, *, status=200, expected_token="integration-read-token"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/state":
                self.send_error(404)
                return
            if self.headers.get("Authorization") != f"Bearer {expected_token}":
                self.send_error(401)
                return
            encoded = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/state"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_authenticated_loopback_get_returns_state(valid_state):
    with fake_state_server(valid_state) as url:
        assert StateClient(url, "integration-read-token", 1).fetch() == valid_state


def test_authentication_failure_is_classified(valid_state):
    with fake_state_server(valid_state) as url:
        with pytest.raises(BridgeFailure) as caught:
            StateClient(url, "wrong-test-token", 1).fetch()
    assert caught.value.status == "unauthorized"


def test_malformed_json_is_classified():
    with fake_state_server(b"{not-json") as url:
        with pytest.raises(BridgeFailure) as caught:
            StateClient(url, "integration-read-token", 1).fetch()
    assert caught.value.status == "invalid_json"


def test_connection_failure_is_classified():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(BridgeFailure) as caught:
        StateClient(
            f"http://127.0.0.1:{port}/state", "integration-read-token", 0.2
        ).fetch()
    assert caught.value.status == "engine_unavailable"


def test_timeout_is_classified(monkeypatch):
    def time_out(*_args, **_kwargs):
        raise socket.timeout("fake loopback timeout")

    monkeypatch.setattr(client_module, "urlopen", time_out)
    with pytest.raises(BridgeFailure) as caught:
        StateClient(
            "http://127.0.0.1:8078/state", "integration-read-token", 0.2
        ).fetch()
    assert (caught.value.status, caught.value.code) == (
        "engine_unavailable",
        "ENGINE_TIMEOUT",
    )


def test_client_has_only_authenticated_get_state_call_path():
    source = inspect.getsource(client_module)
    compact = "".join(source.split())
    assert 'method="GET"' in compact
    assert '"Authorization"' in source and '"Bearer' in source
    for prohibited in ("do_POST", "method=\"POST\"", "/command", "/ingest", "actuator", "PLC", "LabVIEW", "cRIO"):
        assert prohibited not in source
